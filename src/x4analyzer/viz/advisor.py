"""Station build advisor (docs/plans/analytics-ideas.md #2).

Scores "build a factory for ware W in sector S" for every producible
economy ware and every known, non-hostile sector. The score decomposes
into visible factors — demand nearby, input availability, competition,
danger, workforce food supply — each distance-discounted over the gate
graph (sectorgraph.py), normalized per ware, and weighted client-side
with sliders so the ranking is never an opaque oracle.

Unit conventions: production/consumption are capacity units/h (from the
market tab's station rates); open buy offers are a one-off unit backlog,
folded into the demand factor at 1/24th per hour and shown separately.

Logistics (trade-fleet sizing) reuses the Trade Opportunities machinery:
`opportunities._Router` for real route km between sector centres over the
gate graph, and `opportunities.player_trade_ships` for the player's real
haulers (cargo m³ + loadout travel speed). The trip-time arithmetic on
the page mirrors the Opportunities page exactly (0.9 travel-drive ratio,
S/M highway legs at 10 km/s), minus its dock-time overhead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from ..analysis.sectorgraph import build_adjacency, bfs_distances
from ..analysis.opportunities import _Router, player_trade_ships
from .common import DARK_BG, DARK_FG, DARK_MUTED
from .market import (EXCLUDED_OWNERS, _recipe_table, _station_rates,
                     actual_flows, construction_rates)

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

RADIUS = 4            # gate hops considered "nearby"
HOSTILE_SCAN = 6      # how far to look for xenon/khaak sectors
TOP_SECTORS = 10      # sectors kept per ware
BACKLOG_H = 24.0      # one-off buy backlog counts as amount/24 per hour
INPUT_CAP = 3.0       # input availability ratio cap
_HOSTILE = ("xenon", "khaak")

# Distances are measured between sector CENTRES ((0,0) sector-local): the
# advisor scores a sector, not a plot, so there is no station position to
# measure from yet. Demand inside the build sector itself would come out
# as a zero-length route that way, which would imply free hauling — it is
# charged this fixed one-way leg instead (~100 km round trip, a typical
# intra-sector station-to-station hop).
IN_SECTOR_KM = 50.0
# generic preset offered when the save has no player trade ships: a plain
# M freighter, clearly labelled as an assumption on the page
GENERIC_SHIP = {"l": "generic M freighter (assumed)", "model": "generic",
                "cls": "M", "cargo": 8000.0, "speed": 3000, "n": 0,
                "gen": 1}


def _disc(d: int) -> float:
    return 1.0 / (1.0 + d)


def _avg_route_km(router, s: str, weights: dict[str, float],
                  cache: dict | None = None) -> tuple[float, float] | None:
    """Demand-weighted average one-way route from the centre of sector `s`
    to every sector in `weights` (sector macro -> weight), as
    (km_plain, km_highway) under S/M routing. Same-sector demand is
    charged IN_SECTOR_KM instead of the degenerate 0 km centre-to-centre
    distance; unreachable sectors are dropped. None when nothing with a
    positive weight is reachable."""
    kp = kh = tw = 0.0
    for s2, wgt in weights.items():
        if wgt <= 0:
            continue
        if s2 == s:
            leg: tuple[float, float] | None = (IN_SECTOR_KM, 0.0)
        else:
            key = (s, s2)
            if cache is not None and key in cache:
                leg = cache[key]
            else:
                leg = router.route_km(s, (0.0, 0.0), s2, (0.0, 0.0), True)
                if cache is not None:
                    cache[key] = leg
        if leg is None:
            continue
        kp += leg[0] * wgt
        kh += leg[1] * wgt
        tw += wgt
    if tw <= 0:
        return None
    return round(kp / tw, 1), round(kh / tw, 1)


def compute_advice(frames: Frames, ref: RefData, cfg: Config) -> dict:
    """Returns {"rows": [...], "wares": [...]} ready for the page JSON."""
    uni = frames.universe.set_index("id")
    secf = frames.sectors
    sname = dict(zip(secf["macro"], secf["name"]))
    sowner = dict(zip(secf["macro"], secf["owner"]))

    known = secf if not cfg.spoilers_hide \
        else secf[secf["knownto"] == "player"]
    cands = [m for m in known["macro"] if sowner.get(m) not in _HOSTILE]
    hostiles = [m for m in secf["macro"] if sowner.get(m) in _HOSTILE]

    adj = build_adjacency(ref)
    dist = {s: bfs_distances(adj, s, RADIUS) for s in cands}
    # real route lengths for fleet sizing (shared with Trade
    # Opportunities); the router caches one Dijkstra per source sector
    router = _Router(ref)
    km_cache: dict[tuple, tuple | None] = {}
    hdist: dict[str, int] = {}
    for h in hostiles:
        for s2, d in bfs_distances(adj, h, HOSTILE_SCAN).items():
            hdist[s2] = min(hdist.get(s2, HOSTILE_SCAN), d)

    # station capacity rates and open buy offers, keyed by (ware, sector)
    rates = _station_rates(frames, ref)
    rates["sector"] = rates["id"].map(uni["sector.macro"])
    rates = rates[rates["sector"].notna()]
    prod_ws = rates.groupby(["ware", "sector"])["prod"].sum().to_dict()
    cons_ws = rates.groupby(["ware", "sector"])["cons"].sum().to_dict()
    # estimated ACTUAL flows (stock-delta stream) per (ware, sector) —
    # the second basis for demand/competition, and the only basis for
    # input availability (capacity-based input ratios mislead: starved
    # producers' capacity cannot be bought)
    pa_df, ca_df = actual_flows(frames, ref)

    def _ws(df) -> dict:
        if df.empty:
            return {}
        d = df.assign(sector=df["id"].map(uni["sector.macro"]))
        d = d.dropna(subset=["sector"])
        return d.groupby(["ware", "sector"])["rate"].sum().to_dict()

    prod_act_ws, cons_act_ws = _ws(pa_df), _ws(ca_df)
    gprod_act = (pa_df.groupby("ware")["rate"].sum().to_dict()
                 if not pa_df.empty else {})
    gcons_act = (ca_df.groupby("ware")["rate"].sum().to_dict()
                 if not ca_df.empty else {})

    # estimated construction intake at shipyards/wharves/docks counts as
    # local demand in BOTH bases — but only for build materials: those
    # are what actual_flows excludes at yards, so intake complements
    # rather than double-counts (yard habitats' food etc. is already in
    # the consumer-side flows)
    constr_ware, yard_st, _w = construction_rates(frames, ref)
    if not yard_st.empty:
        yard_st = yard_st.assign(
            sector=yard_st["id"].map(uni["sector.macro"]))
        for r in yard_st.dropna(subset=["sector"]).itertuples(index=False):
            if r.ware not in constr_ware:
                continue
            key = (r.ware, r.sector)
            cons_ws[key] = cons_ws.get(key, 0.0) + float(r.rate)
            cons_act_ws[key] = cons_act_ws.get(key, 0.0) + float(r.rate)

    off = frames.trade_offers.copy()
    off["sector"] = off["id"].map(uni["sector.macro"])
    off["owner"] = off["id"].map(uni["owner"])
    off["class"] = off["id"].map(uni["class"])
    off = off[~off["owner"].isin(EXCLUDED_OWNERS) & off["sector"].notna()
              & (off["amount"] > 0)]
    buys = off[off["side"] == "buy"]
    buy_ws = buys.groupby(["ware", "sector"])["amount"].sum().to_dict()

    # workforce food: everything any race's workunit recipe consumes
    rec = _recipe_table(ref)
    food_wares = set(rec[(rec["ware"] == "workunit_busy")
                         & rec["input_ware"].astype(str).ne("")]["input_ware"])

    # candidate wares: economy, produced by a station module, not minable
    w = ref.wares.set_index("id")
    module_wares = set(ref.modules["ware"]) - {""}
    def_rec = rec[rec["method"] == "default"]
    ware_ids = sorted(
        wid for wid in module_wares
        if wid in w.index
        and "economy" in str(w.loc[wid, "tags"])
        and "minable" not in str(w.loc[wid, "tags"])
        and not def_rec[def_rec["ware"] == wid].empty)

    minable_cols = [c for c in
                    ("helium", "hydrogen", "ice", "methane", "nividium",
                     "ore", "rawscrap", "silicon") if c in secf.columns]
    yields = {c: dict(zip(secf["macro"], secf[c])) for c in minable_cols}
    # reference yield: 75th percentile of sectors that have the resource
    ref_yield = {}
    for c in minable_cols:
        pos = secf[secf[c] > 0][c]
        ref_yield[c] = float(pos.quantile(0.75)) if not pos.empty else 1.0

    # ware volume (m³/unit) for haul sizing — defensively 1 m³ for
    # anything missing or unparseable, never 0 (a 0 would silently claim
    # a ware needs no cargo space at all)
    vol_map = {
        str(i): (float(v) if pd.notna(v) and float(v) > 0 else 1.0)
        for i, v in zip(ref.wares["id"],
                        pd.to_numeric(ref.wares["volume"], errors="coerce"))}

    code_of = uni["code"].to_dict()
    cls_of = uni["class"].to_dict()
    wname = ref.ware_name
    # display labels like the market tab: real name, else "FAC <type>"
    lbl_of: dict[str, str] = {}
    for oid in set(buys["id"]):
        nm = str(uni["name"].get(oid) or "")
        if not nm:
            facs = ref.faction_short.get(str(uni["owner"].get(oid, "")),
                                         "OTH")
            nm = f"{facs} {uni['stype'].get(oid) or 'Station'}"
        lbl_of[oid] = nm

    # workforce food supply depends only on the sector, not the ware
    food_sec = {
        s: sum(prod_ws.get((fw, s2), 0.0) * _disc(d)
               for s2, d in dd.items() for fw in food_wares)
        for s, dd in dist.items()
    }

    rows: list[dict] = []
    ware_meta: list[dict] = []
    for wid in ware_ids:
        try:
            pavg = float(w.loc[wid, "price_avg"])
        except (ValueError, TypeError):
            pavg = 0.0
        r0 = def_rec[def_rec["ware"] == wid]
        time, amount = float(r0.iloc[0]["time"]), float(r0.iloc[0]["amount"])
        out_h = amount / time * 3600.0
        inputs = [(str(x.input_ware), float(x.input_amount) / time * 3600.0)
                  for x in r0.itertuples()
                  if isinstance(x.input_ware, str) and x.input_ware]

        gprod = sum(v for (ww, _s), v in prod_ws.items() if ww == wid)
        gcons = sum(v for (ww, _s), v in cons_ws.items() if ww == wid)
        gbuy = sum(v for (ww, _s), v in buy_ws.items() if ww == wid)
        wbuys = [(r.id, r.sector, r.amount, r.price)
                 for r in buys[buys["ware"] == wid].itertuples(index=False)]
        ware_meta.append({
            "ware": wname.get(wid, wid), "prod_h": round(gprod),
            "cons_h": round(gcons), "backlog": round(gbuy),
            "out_h": round(out_h),
            "prod_act": round(gprod_act.get(wid, 0.0)),
            "cons_act": round(gcons_act.get(wid, 0.0)),
        })

        vol = vol_map.get(wid, 1.0)
        # what one production module has to have hauled IN, per hour
        in_m3h = sum(need_h * vol_map.get(iw, 1.0) for iw, need_h in inputs)

        cand_rows = []
        for s in cands:
            dd = dist[s]
            demand_h = comp_h = backlog = demand_act = comp_act = 0.0
            wmap: dict[str, float] = {}
            for s2, d in dd.items():
                k = _disc(d)
                demand_h += cons_ws.get((wid, s2), 0.0) * k
                comp_h += prod_ws.get((wid, s2), 0.0) * k
                backlog += buy_ws.get((wid, s2), 0.0) * k
                demand_act += cons_act_ws.get((wid, s2), 0.0) * k
                comp_act += prod_act_ws.get((wid, s2), 0.0) * k
                # route weight = this sector's share of the demand factor
                # (capacity basis + the backlog's hourly slice), i.e. the
                # numerator of `nd` — where the goods actually have to go
                wgt = (cons_ws.get((wid, s2), 0.0) * k
                       + buy_ws.get((wid, s2), 0.0) * k / BACKLOG_H)
                if wgt > 0:
                    wmap[s2] = wgt
            km = _avg_route_km(router, s, wmap, km_cache)
            food_h = food_sec[s]

            # input availability: bottleneck ratio over recipe inputs.
            # Basis: estimated ACTUAL net flow (production minus existing
            # consumption nearby) — capacity would count starved
            # producers' output that cannot actually be bought
            in_detail = []
            ratio_min, bottleneck = INPUT_CAP, ""
            for iw, need_h in inputs:
                pa = ca = 0.0
                for s2, d in dd.items():
                    k = _disc(d)
                    pa += prod_act_ws.get((iw, s2), 0.0) * k
                    ca += cons_act_ws.get((iw, s2), 0.0) * k
                avail = max(pa - ca, 0.0)
                ratio = avail / need_h if need_h > 0 else INPUT_CAP
                note = (f"~{pa:,.0f}/h actually produced − ~{ca:,.0f}/h "
                        f"already consumed nearby vs {need_h:,.0f}/h needed")
                if iw in yields:
                    ydisc = sum(yields[iw].get(s2, 0.0) * _disc(d)
                                for s2, d in dd.items())
                    yratio = ydisc / ref_yield[iw]
                    if yratio > ratio:
                        ratio = yratio
                        note += f"; minable nearby ({yratio:.1f}x reference yield)"
                ratio = min(ratio, INPUT_CAP)
                if ratio < ratio_min:
                    ratio_min, bottleneck = ratio, wname.get(iw, iw)
                in_detail.append(f"{wname.get(iw, iw)}: {note} "
                                 f"(ratio {ratio:.2f})")
            if not inputs:
                in_detail.append("no inputs (solar/ambient production)")

            hd = min(hdist.get(s, HOSTILE_SCAN), HOSTILE_SCAN)

            # top buyers for the detail view
            near = [(oid, s2, amt, pr, dd[s2])
                    for oid, s2, amt, pr in wbuys if s2 in dd]
            near.sort(key=lambda t: t[2] / (1 + t[4]), reverse=True)
            lines = []
            for oid, s2, amt, pr, d in near[:3]:
                kind = ("construction site"
                        if cls_of.get(oid) == "buildstorage" else "buyer")
                lines.append(
                    f"{lbl_of.get(oid, oid)} ({code_of.get(oid, '?')}) in"
                    f" {sname.get(s2, '?')}, {d} hops — {kind} wants"
                    f" {amt:,.0f} @ {pr:,.0f} Cr")

            cand_rows.append({
                "sector": sname.get(s, s), "owner": sowner.get(s, ""),
                "demand_h": demand_h, "backlog": backlog, "comp_h": comp_h,
                "demand_act": demand_act, "comp_act": comp_act,
                "input_ratio": ratio_min, "bottleneck": bottleneck,
                "hostile_d": hd, "food_h": food_h,
                "km_p": None if km is None else km[0],
                "km_h": None if km is None else km[1],
                "detail": {"inputs": in_detail, "buyers": lines},
            })

        # normalize per ware (per basis) and keep the most promising sectors
        dmax = max((c["demand_h"] + c["backlog"] / BACKLOG_H
                    for c in cand_rows), default=0) or 1.0
        cmax = max((c["comp_h"] for c in cand_rows), default=0) or 1.0
        damax = max((c["demand_act"] + c["backlog"] / BACKLOG_H
                     for c in cand_rows), default=0) or 1.0
        camax = max((c["comp_act"] for c in cand_rows), default=0) or 1.0
        fmax = max((c["food_h"] for c in cand_rows), default=0) or 1.0
        for c in cand_rows:
            c["nd"] = (c["demand_h"] + c["backlog"] / BACKLOG_H) / dmax
            c["nc"] = c["comp_h"] / cmax
            c["nda"] = (c["demand_act"] + c["backlog"] / BACKLOG_H) / damax
            c["nca"] = c["comp_act"] / camax
            c["ni"] = c["input_ratio"] / INPUT_CAP
            c["ns"] = c["hostile_d"] / HOSTILE_SCAN
            c["nw"] = c["food_h"] / fmax
        # default-weight preview score just for the server-side cut —
        # a sector must rank on either basis to survive
        def _preview(c, dk, ck):
            return (0.35 * c[dk] + 0.25 * c["ni"] + 0.15 * c["ns"]
                    + 0.10 * c["nw"] - 0.15 * c[ck])
        cand_rows.sort(key=lambda c: max(_preview(c, "nd", "nc"),
                                         _preview(c, "nda", "nca")),
                       reverse=True)
        for c in cand_rows[:TOP_SECTORS]:
            if c["nd"] <= 0 and c["nda"] <= 0 and c["backlog"] <= 0:
                continue  # nobody within reach wants this ware
            rows.append({
                "ware": wname.get(wid, wid),
                "price": round(pavg, 1),
                "sector": c["sector"], "owner": c["owner"],
                "demand_h": round(c["demand_h"]),
                "backlog": round(c["backlog"]),
                "comp_h": round(c["comp_h"]),
                "demand_act": round(c["demand_act"]),
                "comp_act": round(c["comp_act"]),
                "input_ratio": round(c["input_ratio"], 2),
                "bottleneck": c["bottleneck"],
                "hostile_d": c["hostile_d"],
                "food_h": round(c["food_h"]),
                "vol": vol, "in_m3h": round(in_m3h, 1),
                "km_p": c["km_p"], "km_h": c["km_h"],
                "nd": round(c["nd"], 4), "ni": round(c["ni"], 4),
                "nc": round(c["nc"], 4), "ns": round(c["ns"], 4),
                "nw": round(c["nw"], 4),
                "nda": round(c["nda"], 4), "nca": round(c["nca"], 4),
                "detail": c["detail"],
            })

    ships = player_trade_ships(frames, ref)
    # a ship without resolvable engines has no speed and cannot be timed
    # (the Opportunities page shows such a pick with a blank trip time —
    # here a preset that can never size a fleet is simply not offered)
    ships = [s for s in ships if s.get("speed")]
    return {"rows": rows, "wares": ware_meta,
            "ships": ships or [dict(GENERIC_SHIP)]}


def build_advisor(frames: Frames, ref: RefData, cfg: Config,
                  files_dir: Path, guid: str) -> str | None:
    if frames.trade_offers.empty or frames.sectors.empty:
        return None
    log("-> Station build advisor")
    data = compute_advice(frames, ref, cfg)
    if not data["rows"]:
        return None

    payload = json.dumps(data, separators=(",", ":"))
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
h3{{margin:4px 0;}}
.note{{color:{DARK_MUTED};font-size:12px;margin:2px 0 8px 0;}}
.pos{{color:#4ecf71;}} .neg{{color:#ff6b6b;}} .warn{{color:#e8b84e;}}
.controls{{display:flex;gap:18px;flex-wrap:wrap;align-items:center;
  background:#262626;padding:8px 12px;border-radius:8px;margin:8px 0;}}
.controls label{{font-size:12px;color:{DARK_MUTED};}}
.controls input[type=range]{{vertical-align:middle;width:110px;}}
.controls select{{background:#2a2a2a;color:{DARK_FG};border:1px solid #555;
  padding:3px;}}
.wv{{display:inline-block;width:24px;text-align:right;color:{DARK_FG};}}
td.det{{cursor:pointer;color:#7ab8ff;}}
.childrow{{background:#20242a !important;font-size:12px;color:{DARK_MUTED};}}
.childrow ul{{margin:4px 0 4px 18px;padding:0;}}
table.dataTable, table.dataTable th, table.dataTable td{{color:{DARK_FG};}}
table.dataTable.display tbody tr{{background:{DARK_BG};}}
table.dataTable.display tbody tr.odd{{background:#252525;}}
table.dataTable.display tbody tr:hover{{background:#333;}}
table.dataTable thead th, table.dataTable.no-footer{{border-color:#555;}}
.dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter,
.dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_paginate,
.dataTables_wrapper .dataTables_paginate .paginate_button{{color:{DARK_FG} !important;}}
.dataTables_wrapper .dataTables_paginate .paginate_button.current,
.dataTables_wrapper .dataTables_paginate .paginate_button:hover{{
  color:#fff !important;background:#3a3a3a;border-color:#555;}}
.dataTables_wrapper input, .dataTables_wrapper select{{
  background:#2a2a2a;color:{DARK_FG};border:1px solid #555;}}
</style></head><body>
<h3>Station build advisor</h3>
<p class='note'>Where to build what: every producible ware scored per known
sector. Demand, competition and input supply are capacity within
{RADIUS} gates, discounted by distance (÷(1+hops)); open buy orders count
as backlog. The <b>estimated actual flows</b> checkbox swaps
demand/competition/shortfall/untapped (and the balance table) between
theoretical capacity and stock-flow ESTIMATES of what really happens —
starved factories run far below capacity. Input ratios always use actual
net flow (production minus existing consumption nearby): starved
producers' capacity cannot be bought. Demand includes estimated
construction intake at shipyards/wharves in both modes. Untapped Cr/h
values the shortfall at average game price. <b>Haul m&sup3;/h</b> is that
same shortfall in cargo volume (units &times; ware m&sup3;), and
<b>&asymp; Traders</b> divides it by what one of your ships moves per
hour on this route: distances are real routes between sector CENTRES over
the gate graph (same router as Trade Opportunities), demand-weighted over
the sectors that want the ware, with demand in the build sector itself
charged a flat {IN_SECTOR_KM:.0f} km leg. Trips run at 0.9 &times; the
ship's loadout travel speed (S/M cross highway sectors at 10 km/s) with
<i>no</i> docking or spool-up overhead &mdash; a floor, so round up.
Factors are normalized per
ware — scores compare sectors for the same ware, and the weights below
are yours to tune. Click a row's &#9432; for the reasoning.</p>
<div class='controls'>
  <label>Ware <select id='wsel'><option value=''>All wares</option></select></label>
  <label title='sizes the &asymp; Traders column: cargo hold and loadout
    travel speed of one of your real haulers'>Trader
    <select id='ssel'></select></label>
  <label style='color:{DARK_FG};font-size:13px;border:1px solid #e8b84e;
    border-radius:6px;padding:4px 8px'>
    <input type='checkbox' id='actual'> estimated <b>actual</b>
    flows</label>
  <label>Demand <input type='range' id='w_d' min='0' max='100' value='35'>
    <span class='wv' id='v_d'>35</span></label>
  <label>Inputs <input type='range' id='w_i' min='0' max='100' value='25'>
    <span class='wv' id='v_i'>25</span></label>
  <label>Competition &minus;<input type='range' id='w_c' min='0' max='100' value='15'>
    <span class='wv' id='v_c'>15</span></label>
  <label>Safety <input type='range' id='w_s' min='0' max='100' value='15'>
    <span class='wv' id='v_s'>15</span></label>
  <label>Workforce <input type='range' id='w_w' min='0' max='100' value='10'>
    <span class='wv' id='v_w'>10</span></label>
</div>
<table id='adv' class='display nowrap' style='width:100%'>
<thead><tr><th></th><th>Score</th><th>Ware</th><th>Sector</th><th>Owner</th>
<th>Demand/h</th><th>Competition/h</th><th>Shortfall/h</th>
<th>Untapped Cr/h</th><th>Haul m&sup3;/h</th><th>&asymp; Traders</th>
<th>Backlog</th><th>Hostile (hops)</th></tr></thead>
</table>
<h3 style='margin-top:24px'>Global ware balance</h3>
<p class='note'>Universe-wide capacity per ware (non-Xenon): production vs
consumption plus the open buy backlog — the market gap that makes a ware
worth building at all. Output/h is one production module's yield.</p>
<table id='bal' class='display nowrap' style='width:100%'>
<thead><tr><th>Ware</th><th>Production/h</th><th>Consumption/h</th>
<th>Buy backlog</th><th>Balance/h</th><th>1 module makes/h</th></tr></thead>
</table>
<script>
const DATA = {payload};
let ACT = false;   // false = theoretical capacity, true = estimated actual
function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}
const numCol = (d, t) => t === 'display' ? fmt(d) : d;
const est = (v) => "<span class=warn title='estimated actual flows "
  + "(stock-flow deltas)'>~" + fmt(v) + "</span>";
const dOf = r => ACT ? r.demand_act : r.demand_h;
const cOf = r => ACT ? r.comp_act : r.comp_h;

// ---- logistics: haul volume and fleet sizing ----
// Mirrors the Trade Opportunities client exactly: plain-space km at
// 0.9 x the loadout travel speed, highway-sector km at 10 km/s for S/M
// only (L/XL fly everything at travel speed). No dock/spool-up
// overhead here, so the trader count is a lower bound.
const CRUISE = 0.9, HW_MS = 10000;
let SHIP = DATA.ships[0] || null;
const haulOf = r => (dOf(r) - cOf(r)) * r.vol;
function tripSeconds(r) {{   // round trip, seconds
  if (!SHIP || !SHIP.speed || r.km_p === null) return null;
  const v = CRUISE * SHIP.speed;
  const sm = SHIP.cls === 'S' || SHIP.cls === 'M';
  const one = sm ? (r.km_p * 1000 / v + r.km_h * 1000 / HW_MS)
                 : ((r.km_p + r.km_h) * 1000 / v);
  return 2 * one;
}}
function shipM3h(r) {{       // m³/h one ship of the preset moves
  const t = tripSeconds(r);
  return (t === null || t <= 0) ? null : SHIP.cargo * 3600 / t;
}}
function tradersOf(r) {{
  const h = haulOf(r), per = shipM3h(r);
  if (per === null || h <= 0) return null;
  return Math.ceil(h / per);
}}
function fmtMin(sec) {{
  if (sec < 90) return Math.round(sec) + ' s';
  return sec >= 5400 ? (sec / 3600).toFixed(1) + ' h'
                     : Math.round(sec / 60) + ' min';
}}
function logisticsHtml(r) {{
  let h = '<b>Logistics</b><ul>';
  if (r.km_p === null) {{
    h += '<li>no reachable demand for this ware &mdash; no route</li>';
  }} else {{
    h += '<li>demand-weighted one-way route &asymp; '
      + fmt(r.km_p + r.km_h) + ' km (' + fmt(r.km_p) + ' km plain'
      + (r.km_h ? ' + ' + fmt(r.km_h) + ' km in highway sectors' : '')
      + '), sector centre to sector centre; demand in '
      + r.sector + ' itself counts as {IN_SECTOR_KM:.0f} km</li>';
    const out = haulOf(r);
    h += '<li>output haul: ' + fmt(dOf(r) - cOf(r)) + ' u/h shortfall'
      + ' &times; ' + r.vol + ' m&sup3;/u = <b>' + fmt(out)
      + ' m&sup3;/h</b>' + (ACT ? ' (estimated actual flows)' : '')
      + '</li>';
    const t = tripSeconds(r), per = shipM3h(r);
    if (t !== null)
      h += '<li>' + SHIP.l + ': ' + fmt(SHIP.cargo) + ' m&sup3; @ '
        + fmt(SHIP.speed) + ' m/s travel &times;' + CRUISE
        + ((SHIP.cls === 'S' || SHIP.cls === 'M') && r.km_h
           ? ' (highways at ' + (HW_MS / 1000) + ' km/s)' : '')
        + ' &rarr; round trip &asymp; ' + fmtMin(t) + ' = <b>'
        + fmt(per) + ' m&sup3;/h</b> per ship'
        + (out > 0 ? ' &rarr; <b>' + tradersOf(r)
           + '</b> trader(s), no docking overhead counted' : '')
        + (SHIP.gen ? ' &mdash; assumed generic ship, not one of yours'
           : '') + '</li>';
  }}
  h += '<li>input haul: <b>' + fmt(r.in_m3h) + ' m&sup3;/h</b> per'
    + ' production module (recipe inputs at full rate &times; their'
    + ' volumes) &mdash; the goods that must arrive, whatever the'
    + ' station ends up sized at</li></ul>';
  return h;
}}

function weights() {{
  return {{d: +$('#w_d').val(), i: +$('#w_i').val(), c: +$('#w_c').val(),
           s: +$('#w_s').val(), w: +$('#w_w').val()}};
}}
function score(r, W) {{
  const total = W.d + W.i + W.c + W.s + W.w || 1;
  const nd = ACT ? r.nda : r.nd, nc = ACT ? r.nca : r.nc;
  return 100 * (W.d * nd + W.i * r.ni + W.s * r.ns + W.w * r.nw
                - W.c * nc) / total;
}}

const rows = DATA.rows.map(r => {{
  const det = '<b>Inputs</b><ul>' +
    r.detail.inputs.map(x => '<li>' + x + '</li>').join('') + '</ul>' +
    (r.detail.buyers.length
      ? '<b>Biggest buyers nearby</b><ul>' +
        r.detail.buyers.map(x => '<li>' + x + '</li>').join('') + '</ul>'
      : '<i>no open buy orders nearby — demand is consumption capacity</i>');
  return Object.assign(r, {{det}});
}});

[...new Set(rows.map(r => r.ware))].sort().forEach(w =>
  $('#wsel').append(`<option>${{w}}</option>`));

const table = $('#adv').DataTable({{
  data: rows, pageLength: 15, order: [[1, 'desc']],
  columns: [
    {{data: null, orderable: false, defaultContent: '&#9432;',
      className: 'det', width: '18px'}},
    {{data: r => score(r, weights()), render: (d, t) =>
        t === 'display' ? d.toFixed(1) : d}},
    {{data: 'ware'}},
    {{data: 'sector'}},
    {{data: 'owner'}},
    {{data: r => dOf(r), render: (d, t) => t === 'display'
        ? (ACT ? est(d) : fmt(d)) : d}},
    {{data: r => cOf(r), render: (d, t) => t === 'display'
        ? (ACT ? est(d) : fmt(d)) : d}},
    {{data: r => dOf(r) - cOf(r), render: (d, t) => t === 'display'
        ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
          + '</span>' + (ACT ? " <span class=warn>~</span>" : "") : d}},
    {{data: r => (dOf(r) - cOf(r)) * r.price,
      render: (d, t) => t === 'display'
        ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
          + '</span>' + (ACT ? " <span class=warn>~</span>" : "") : d}},
    {{data: r => haulOf(r), render: (d, t) => t === 'display'
        ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
          + '</span>' + (ACT ? " <span class=warn>~</span>" : "") : d}},
    {{data: r => tradersOf(r), render: (d, t, r) => t === 'display'
        ? (d === null
           ? "<span class='note' title='" + (r.km_p === null
              ? 'no reachable demand' : 'nothing to haul on this basis')
             + "'>&mdash;</span>"
           : "<span title='" + fmt(shipM3h(r)) + " m³/h per "
             + SHIP.l.replace(/'/g, '') + ", round trip &asymp; "
             + fmtMin(tripSeconds(r)) + "'>" + d + '</span>')
        : (d === null ? -1 : d)}},
    {{data: 'backlog', render: numCol}},
    {{data: 'hostile_d', render: (d, t) => t === 'display'
        ? (d >= {HOSTILE_SCAN} ? '{HOSTILE_SCAN}+'
           : "<span class='" + (d <= 1 ? 'neg' : d <= 2 ? 'warn' : '')
             + "'>" + d + '</span>')
        : d}},
  ],
}});

$('#adv tbody').on('click', 'td.det', function() {{
  const tr = $(this).closest('tr');
  const row = table.row(tr);
  if (row.child.isShown()) {{ row.child.hide(); }}
  else {{ row.child($('<tr class="childrow">').html(
      '<td></td><td colspan="12">' + logisticsHtml(row.data())
      + row.data().det + '</td>')).show(); }}
}});

const ssel = $('#ssel');
DATA.ships.forEach((s, i) => ssel.append(
  $('<option>').val(i).text(s.l + ' (' + s.cls + ', ' + fmt(s.cargo)
    + ' m³, ' + fmt(s.speed) + ' m/s travel'
    + (s.n > 1 ? ', ×' + s.n + ' owned' : '') + ')')));
ssel.on('change', function() {{
  SHIP = DATA.ships[+this.value] || null;
  table.rows().invalidate('data').draw(false);
}});

$('#wsel').on('change', function() {{
  table.column(2).search(this.value ? '^' + $.fn.dataTable.util.escapeRegex(
    this.value) + '$' : '', true, false).draw();
}});
$('.controls input[type=range]').on('input', function() {{
  ['d','i','c','s','w'].forEach(k =>
    $('#v_' + k).text($('#w_' + k).val()));
  table.rows().invalidate('data').draw(false);
}});

function balRows() {{
  return DATA.wares.map(w => {{
    const p = ACT ? w.prod_act : w.prod_h;
    const c = ACT ? w.cons_act : w.cons_h;
    return [w.ware, p, c, w.backlog, p - c, w.out_h];
  }});
}}
const bal = $('#bal').DataTable({{
  data: balRows(),
  pageLength: 15, order: [[4, 'asc']],
  columnDefs: [
    {{targets: [3, 5], render: numCol}},
    {{targets: [1, 2], render: (d, t) => t === 'display'
      ? (ACT ? '~' : '') + fmt(d) : d}},
    {{targets: 4, render: (d, t) => t === 'display'
      ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
        + '</span>' + (ACT ? " <span class=warn>~</span>" : "") : d}},
  ],
}});

$('#actual').on('change', function() {{
  ACT = this.checked;
  const th = $('#adv thead th');
  th.eq(5).text(ACT ? '~Demand/h (act)' : 'Demand/h');
  th.eq(6).text(ACT ? '~Competition/h (act)' : 'Competition/h');
  th.eq(7).text(ACT ? '~Shortfall/h (act)' : 'Shortfall/h');
  th.eq(8).text(ACT ? '~Untapped Cr/h (act)' : 'Untapped Cr/h');
  th.eq(9).html(ACT ? '~Haul m&sup3;/h (act)' : 'Haul m&sup3;/h');
  const bh = $('#bal thead th');
  bh.eq(1).text(ACT ? '~Production/h (act)' : 'Production/h');
  bh.eq(2).text(ACT ? '~Consumption/h (act)' : 'Consumption/h');
  bh.eq(4).text(ACT ? '~Balance/h (act)' : 'Balance/h');
  table.rows().invalidate('data').draw(false);
  bal.clear().rows.add(balRows()).draw(false);
}});

(function() {{
  function post() {{
    parent.postMessage({{x4h: document.body.scrollHeight + 24}}, '*');
  }}
  new ResizeObserver(post).observe(document.body);
  window.addEventListener('load', function() {{ setTimeout(post, 400); }});
}})();
</script></body></html>"""

    name = f"Build Advisor_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
