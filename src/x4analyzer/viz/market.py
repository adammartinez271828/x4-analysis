"""Global market tab: production/consumption, stock levels and logistics.

Per ware, from every station in the universe:
- production capacity: production modules x game recipes;
- consumption capacity: module inputs PLUS population needs (the game models
  workforce upkeep as per-race `workunit_busy` recipes: 200 workers consume
  e.g. 75 food rations + 45 medical supplies per 600s);
- global stock: summed station cargo, and "cover" = stock / consumption;
- understocked stations: consumers holding less than COVER_LOW_H hours of
  their own consumption — many understocked stations with healthy global
  stock indicates a logistics problem rather than a supply problem;
- construction demand: outstanding resources of builds currently waiting
  ("waitingforresources"), which is where end-tier wares like hull parts and
  claytronics are consumed.

Capacity is the base recipe rate — workforce production bonuses are not
modelled. Ship construction consumption is only visible via build demand and
traded volume; the save does not record shipyard consumption rates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..cli import log
from ..frames import Frames
from ..refdata import RefData
from .common import DARK_BG, DARK_FG, DARK_MUTED, DARK_PLOT

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

COVER_LOW_H = 3.0     # global cover below this many hours is flagged red
UNDERSTOCK_PCT = 0.25  # station stock below this share of its target level
WORKUNIT = "workunit_busy"


def _recipe_table(ref: RefData) -> pd.DataFrame:
    rec = ref.recipes.copy()
    for col in ("time", "amount", "input_amount"):
        rec[col] = pd.to_numeric(rec[col], errors="coerce")
    return rec[rec["time"] > 0]


# factions outside the tradeable economy: their stations consume and hoard
# large amounts (esp. silicon/ore) but the player can never trade with them
EXCLUDED_OWNERS = {"xenon"}


def _station_rates(frames: Frames, ref: RefData) -> pd.DataFrame:
    """Per (station id, faction, ware): prod/h and cons/h capacity."""
    uni = frames.universe.set_index("id")
    stations = set(uni.index[(uni["class"] == "station")
                             & ~uni["owner"].isin(EXCLUDED_OWNERS)])
    rec = _recipe_table(ref)
    methods = set(zip(rec["ware"], rec["method"]))
    rows: list[dict] = []

    def faction_of(sid):
        return ref.faction_short.get(uni["owner"].get(sid, ""), "OTH")

    # module production/consumption. A module with several queue options
    # (e.g. Scrap Recycler: claytronics OR hullparts) can only run one at a
    # time; assume an even split across its queues. Processing modules run
    # the ware's "processing" recipe scaled by their batch size.
    mods = frames.station_modules
    if not mods.empty and not ref.modules.empty:
        mref = ref.modules[["macro", "ware", "method", "scale"]].copy()
        mref["scale"] = pd.to_numeric(mref["scale"], errors="coerce").fillna(1)
        mref["weight"] = 1.0 / mref.groupby("macro")["macro"].transform("count")
        inst = mods.merge(mref, on="macro")
        inst = inst[inst["ware"] != ""]
        for (sid, ware, method), grp in inst.groupby(["id", "ware", "method"]):
            if sid not in stations:
                continue
            units = float((grp["weight"] * grp["scale"]).sum())
            use = method if (ware, method) in methods else "default"
            recipe = rec[(rec["ware"] == ware) & (rec["method"] == use)]
            if recipe.empty:
                continue
            time, amount = recipe.iloc[0]["time"], recipe.iloc[0]["amount"]
            fac = faction_of(sid)
            rows.append({"id": sid, "faction": fac, "ware": ware,
                         "prod": amount / time * 3600.0 * units, "cons": 0.0})
            for inp in recipe.itertuples():
                if isinstance(inp.input_ware, str) and inp.input_ware:
                    rows.append({
                        "id": sid, "faction": fac, "ware": inp.input_ware,
                        "prod": 0.0,
                        "cons": inp.input_amount / time * 3600.0 * units,
                    })

        # Protectyon (ware id "condensate"): the shield generator module has
        # no recipe — its Tide consumption is scripted, ~1 unit/h per module
        # (user-observed)
        shields = mods[mods["macro"] == "storage_pir_l_condensate_01_macro"]
        for sid, n in shields.groupby("id").size().items():
            if sid in stations:
                rows.append({"id": sid, "faction": faction_of(sid),
                             "ware": "condensate", "prod": 0.0,
                             "cons": 1.0 * n})

    # population needs: workforce x per-race workunit recipe
    wf = frames.workforce_all
    if not wf.empty:
        wu = rec[rec["ware"] == WORKUNIT]
        for row in wf.itertuples(index=False):
            if row.id not in stations or row.amount <= 0:
                continue
            method = row.race if (WORKUNIT, row.race) in methods else "default"
            recipe = wu[wu["method"] == method]
            if recipe.empty:
                continue
            time, amount = recipe.iloc[0]["time"], recipe.iloc[0]["amount"]
            fac = faction_of(row.id)
            for inp in recipe.itertuples():
                if isinstance(inp.input_ware, str) and inp.input_ware:
                    rows.append({
                        "id": row.id, "faction": fac, "ware": inp.input_ware,
                        "prod": 0.0,
                        "cons": inp.input_amount / amount / time * 3600.0
                        * row.amount,
                    })

    if not rows:
        return pd.DataFrame(columns=["id", "faction", "ware", "prod", "cons"])
    return (pd.DataFrame(rows)
            .groupby(["id", "faction", "ware"], as_index=False)
            [["prod", "cons"]].sum())


def build_market(frames: Frames, ref: RefData, files_dir: Path,
                 guid: str) -> str | None:
    rates = _station_rates(frames, ref)
    gt = frames.global_trades
    if rates.empty and gt.empty:
        return None
    log("-> Market overview")
    time_now = frames.time_now
    uni = frames.universe.set_index("id")
    stations = set(uni.index[(uni["class"] == "station")
                             & ~uni["owner"].isin(EXCLUDED_OWNERS)])
    excluded_hosts = set(uni.index[uni["owner"].isin(EXCLUDED_OWNERS)])

    # global stock: station cargo plus free-floating ware objects (raw scrap
    # exists almost entirely as scrap cubes drifting near processors, not as
    # station cargo); ships in transit excluded
    cargo = frames.station_cargo
    cargo = cargo[cargo["id"].isin(stations)] if not cargo.empty else cargo
    stock = cargo.groupby("ware")["amount"].sum() if not cargo.empty \
        else pd.Series(dtype=float)
    floating = frames.floating_wares
    if floating is not None and not floating.empty:
        stock = stock.add(floating.groupby("ware")["amount"].sum(),
                          fill_value=0.0)

    # outstanding STATION-construction resources ("insufficient"). Shipyard
    # <shortage> blocks are the backlog of endlessly queued NPC ship orders
    # — not near-term demand (their actionable needs appear as buy offers)
    build = frames.build_demand
    build = build[build["kind"] == "insufficient"] if not build.empty \
        else build
    # drop excluded factions' construction sites (buildstorage owners are in
    # the universe frame; unknown hosts are kept)
    if not build.empty:
        build = build[~build["id"].isin(excluded_hosts)]
    # stations report the same missing amount at station level AND per build
    # processor: max per (host, ware) instead of sum avoids double counting
    if not build.empty:
        build = (build.groupby(["id", "ware"], as_index=False)["amount"].max())
    build_by_ware = build.groupby("ware")["amount"].sum() if not build.empty \
        else pd.Series(dtype=float)

    # open trade offers with prices, enriched with station label + sector
    sec_name = dict(zip(frames.sectors["macro"], frames.sectors["name"]))
    off = frames.trade_offers
    off = off[off["id"].isin(stations) & (off["amount"] > 0)
              & (off["price"] > 0)].copy() if not off.empty else off
    if not off.empty:
        name = off["id"].map(uni["name"]).replace("", pd.NA)
        fac = off["id"].map(uni["owner"]).map(ref.faction_short).fillna("OTH")
        base = (off["id"].map(uni["stype"]).replace("", pd.NA)
                .fillna("Station"))
        off["faction"] = fac
        off["label"] = (name.fillna(fac + " " + base)
                        + " (" + off["id"].map(uni["code"]).fillna("?") + ") — "
                        + off["id"].map(uni["sector.macro"]).map(sec_name)
                        .fillna("?"))
    buys = off[off["side"] == "buy"] if not off.empty else off
    sells = off[off["side"] == "sell"] if not off.empty else off

    # buyers = stations with open buy offers PLUS constructions missing
    # materials; a buyer holding less than UNDERSTOCK_PCT of its target level
    # (stock + still-wanted amount) is understocked. Covers module consumers,
    # shipyards stocking end-tier parts, raw material buyers and builds alike.
    build_hosts = build[(build["id"] != "") & (build["amount"] > 0)] \
        if not build.empty else build

    wanted = pd.concat([
        buys.groupby(["id", "ware"])["amount"].sum()
        if not buys.empty else pd.Series(dtype=float),
        build_hosts.groupby(["id", "ware"])["amount"].sum()
        if not build_hosts.empty else pd.Series(dtype=float),
    ])
    if not wanted.empty:
        wanted = wanted.groupby(level=[0, 1]).sum()
        holdings = (frames.station_cargo.groupby(["id", "ware"])["amount"].sum()
                    if not frames.station_cargo.empty
                    else pd.Series(dtype=float))
        held = holdings.reindex(wanted.index).fillna(0.0)
        understocked = held < (UNDERSTOCK_PCT / (1 - UNDERSTOCK_PCT)) * wanted
        under = understocked.groupby(level="ware").sum()
        n_buyers = wanted.groupby(level="ware").count()
        # buyer-side market fill: how close buyers are to their target level
        # (their stock + what they still want); producer hoards don't count
        fill_held = held.groupby(level="ware").sum()
        fill_target = (held + wanted).groupby(level="ware").sum()
    else:
        under = pd.Series(dtype=int)
        n_buyers = pd.Series(dtype=int)
        fill_held = pd.Series(dtype=float)
        fill_target = pd.Series(dtype=float)
    buy_demand = buys.groupby("ware")["amount"].sum() if not buys.empty \
        else pd.Series(dtype=float)
    # money on the table: what stations offer to pay right now, and the best
    # open price you could sell each ware for
    demand_cr = (buys.assign(v=buys["amount"] * buys["price"])
                 .groupby("ware")["v"].sum()) if not buys.empty \
        else pd.Series(dtype=float)
    best_price = buys.groupby("ware")["price"].max() if not buys.empty \
        else pd.Series(dtype=float)

    total = rates.groupby("ware")[["prod", "cons"]].sum()
    gt = gt[gt["faction"] != "XEN"] if not gt.empty else gt
    traded = gt.groupby("ware")["dv"].agg(["sum", "count"]) if not gt.empty \
        else pd.DataFrame(columns=["sum", "count"])
    span_h = max((time_now - gt["time"].min()) / 3600.0, 1.0) if not gt.empty \
        else 1.0

    price_avg = dict(zip(
        ref.wares["id"],
        pd.to_numeric(ref.wares["price_avg"], errors="coerce").fillna(0),
    ))

    # station-economy wares only: transport classes a station can store and
    # trade. Excludes player inventory items, equipment, ships, research etc.
    _STATION_TRANSPORT = {"container", "solid", "liquid", "condensate"}
    transport = dict(zip(ref.wares["id"], ref.wares["transport"].fillna("")))

    vol_map = dict(zip(
        ref.wares["id"],
        pd.to_numeric(ref.wares["volume"], errors="coerce").fillna(0),
    ))

    # minable wares have no producing modules; their effective production is
    # what miners actually deliver to stations (the traded-volume estimate)
    minable = {i for i, t in zip(ref.wares["id"], ref.wares["tags"].fillna(""))
               if "minable" in t}

    wares = sorted(set(total.index) | set(traded.index) | set(stock.index))
    summary = []
    for w in wares:
        if w == WORKUNIT:
            continue
        if transport.get(w, "container") not in _STATION_TRANSPORT:
            continue
        prod = float(total["prod"].get(w, 0))
        cons = float(total["cons"].get(w, 0))
        st = float(stock.get(w, 0))
        cover_h = st / cons if cons > 0 else None
        traded_h = float(traded["sum"].get(w, 0)) / span_h
        est = w in minable
        if est:
            prod = traded_h
        avg = float(price_avg.get(w, 0))
        bp = float(best_price.get(w, 0))
        premium = (bp / avg - 1.0) * 100.0 if avg > 0 and bp > 0 else None

        target = float(fill_target.get(w, 0))
        fill = 100.0 * float(fill_held.get(w, 0)) / target if target > 0 \
            else None
        # hours until every open order could be filled from the production
        # surplus. Without a surplus the market can never converge —
        # consumption regenerates the order book — so we report the standing
        # backlog depth instead (open demand as hours of total delivery flow)
        gap = float(buy_demand.get(w, 0)) + float(build_by_ware.get(w, 0))
        surplus = prod - cons
        if gap <= 0:
            satisfy_h, satisfy_flag = 0.0, "sat"
        elif surplus > 0:
            satisfy_h, satisfy_flag = gap / surplus, ""
        elif traded_h > 0:
            satisfy_h, satisfy_flag = gap / traded_h, "backlog"
        else:
            satisfy_h, satisfy_flag = None, "never"
        summary.append({
            "ware": w, "name": ref.ware_name.get(w, w),
            "prod": round(prod), "cons": round(cons),
            "balance": round(prod - cons),
            "stock": round(st),
            "cover": round(cover_h, 1) if cover_h is not None else None,
            "buy": round(float(buy_demand.get(w, 0))),
            "buyers": int(n_buyers.get(w, 0)),
            "under": int(under.get(w, 0)),
            "build": round(float(build_by_ware.get(w, 0))),
            "traded_h": round(traded_h),
            # cash volume estimated at average game price (the global trade
            # events record volume only)
            "cr_h": round(traded_h * price_avg.get(w, 0)),
            "est": est,
            "best_price": round(bp) if bp > 0 else None,
            "premium": round(premium, 1) if premium is not None else None,
            "demand_cr": round(float(demand_cr.get(w, 0))),
            "fill": round(fill, 1) if fill is not None else None,
            "satisfy_h": round(satisfy_h, 1) if satisfy_h is not None
            else None,
            "satisfy_flag": satisfy_flag,
            "vol": int(vol_map.get(w, 0) or 0),
        })
    summary.sort(key=lambda r: r["cr_h"], reverse=True)

    # ---- per-ware detail ---------------------------------------------------
    detail: dict[str, dict] = {}
    if not gt.empty:
        g = gt.copy()
        g["hour"] = ((g["time"] - time_now) / 3600.0).astype(int)
        for w, grp in g.groupby("ware"):
            hourly = grp.groupby("hour")["dv"].sum()
            top = (grp.groupby("label")["dv"].sum()
                   .sort_values(ascending=False).head(12))
            lab_fac = grp.groupby("label")["faction"].first()
            d = detail.setdefault(w, {})
            d["hours"] = [int(h) for h in hourly.index]
            d["volume"] = [float(v) for v in hourly.values]
            d["stations"] = [str(s) for s in top.index]
            d["svolume"] = [float(v) for v in top.values]
            d["st_f"] = [str(lab_fac.get(s, "OTH")) for s in top.index]
            if w in minable:
                # deliveries by receiving faction = who gets the mined supply
                by_fac = (grp.groupby("faction")["dv"].sum() / span_h) \
                    .sort_values(ascending=False)
                d["delf"] = list(by_fac.index)
                d["delv"] = [float(v) for v in by_fac.values]
    for w, grp in rates.groupby("ware"):
        d = detail.setdefault(w, {})
        fp = grp.groupby("faction")[["prod", "cons"]].sum()
        fp = fp.loc[(fp["prod"] + fp["cons"]).sort_values(ascending=False).index]
        d["cfactions"] = list(fp.index)
        d["cprod"] = [float(v) for v in fp["prod"]]
        d["ccons"] = [float(v) for v in fp["cons"]]
        d["cons"] = float(fp["cons"].sum())  # capacity line in volume chart

    # unmet demand = open buy offers + construction shortfalls, attributed
    # to faction and sector via the universe frame (build hosts include
    # free-floating build storages)
    dem = pd.concat([
        buys[["id", "ware", "amount"]] if not buys.empty
        else pd.DataFrame(columns=["id", "ware", "amount"]),
        build[["id", "ware", "amount"]] if not build.empty
        else pd.DataFrame(columns=["id", "ware", "amount"]),
    ], ignore_index=True)
    dem = dem[dem["id"] != ""]
    if not dem.empty:
        dem["faction"] = (dem["id"].map(uni["owner"])
                          .map(ref.faction_short).fillna("OTH"))
        dem["sector"] = (dem["id"].map(uni["sector.macro"])
                         .map(sec_name).fillna("?"))

    # full offer books per ware (compact [label_idx, price, amount] triples
    # with a shared label table) so the min-volume slider can re-rank
    # client-side
    olabels: list[str] = []
    oindex: dict[str, int] = {}

    def _li(label: str) -> int:
        i = oindex.get(label)
        if i is None:
            i = len(olabels)
            olabels.append(label)
            oindex[label] = i
        return i

    if not buys.empty:
        for w, grp in buys.groupby("ware"):
            d = detail.setdefault(w, {})
            g = grp.sort_values("price", ascending=False)
            d["bo"] = [[_li(l), float(p), float(a), f] for l, p, a, f in
                       zip(g["label"], g["price"], g["amount"],
                           g["faction"])]

    if not sells.empty:
        for w, grp in sells.groupby("ware"):
            d = detail.setdefault(w, {})
            g = grp.sort_values("price")
            d["so"] = [[_li(l), float(p), float(a), f] for l, p, a, f in
                       zip(g["label"], g["price"], g["amount"],
                           g["faction"])]
    sector_fac = dict(zip(
        frames.sectors["name"],
        frames.sectors["owner"].map(ref.faction_short).fillna("OTH")))
    if not dem.empty:
        for w, grp in dem.groupby("ware"):
            d = detail.setdefault(w, {})
            sec = (grp.groupby("sector")["amount"].sum()
                   .sort_values(ascending=False).head(12))
            d["sec_l"] = list(sec.index)
            d["sec_v"] = [float(v) for v in sec.values]
            d["sec_f"] = [sector_fac.get(n, "OTH") for n in sec.index]
            bf = (grp.groupby("faction")["amount"].sum()
                  .sort_values(ascending=False))
            d["bf_l"] = list(bf.index)
            d["bf_v"] = [float(v) for v in bf.values]

    # wares used to build ships, equipment or station modules (for the
    # "build wares only" filter) — derived from the build recipes of ship/
    # equipment-transport wares and module wares
    targets = ref.wares[
        ref.wares["transport"].isin(["ship", "equipment"])
        | ref.wares["tags"].fillna("").str.contains("module")
    ]["id"]
    rec_all = ref.recipes
    build_wares = sorted(set(
        rec_all[rec_all["ware"].isin(set(targets))]["input_ware"].dropna()
    ) - {""})

    ware_names = {w: ref.ware_name.get(w, w) for w in detail}
    table_rows = json.dumps([[
        r["name"], r["prod"], r["cons"], r["balance"], r["stock"],
        r["cover"], r["buy"], r["build"], r["buyers"], r["under"],
        r["traded_h"], r["cr_h"], r["premium"], r["demand_cr"],
        r["fill"], r["satisfy_h"], r["satisfy_flag"], r["ware"], r["est"],
        r["best_price"],
    ] for r in summary], separators=(",", ":"))

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<script src='lib/plotly.min.js'></script>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
label{{color:{DARK_MUTED};margin-right:6px;}}
select{{background:#2a2a2a;color:{DARK_FG};border:1px solid #555;
        padding:4px 8px;font-size:14px;}}
.note{{color:{DARK_MUTED};font-size:12px;}}
details.note{{margin:6px 0 10px 0;}}
details.note summary{{cursor:pointer;color:{DARK_MUTED};font-size:13px;
  user-select:none;}}
details.note summary:hover{{color:{DARK_FG};}}
.notebody{{background:#252525;border:1px solid #3a3a3a;border-radius:6px;
  padding:10px 16px;margin-top:6px;max-width:1000px;line-height:1.5;}}
.notebody ul{{margin:4px 0 10px 0;padding-left:20px;}}
.notebody li{{margin-bottom:4px;}}
.notebody b{{color:{DARK_FG};}}
.notehead{{color:{DARK_FG};font-weight:bold;margin:8px 0 2px 0;}}
.pos{{color:#4ecf71;}} .neg{{color:#ff6b6b;}} .warn{{color:#e8b84e;}}
table.dataTable, table.dataTable th, table.dataTable td{{color:{DARK_FG};}}
table.dataTable.display tbody tr{{background:{DARK_BG};}}
table.dataTable.display tbody tr.odd{{background:#252525;}}
table.dataTable.display tbody tr:hover{{background:#333;cursor:pointer;}}
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
<h3 style='margin:4px 0'>Global ware production, consumption &amp; stock</h3>
<details class='note'>
<summary>How these numbers are computed &amp; caveats</summary>
<div class='notebody'>
<p class='notehead'>Column definitions</p>
<ul>
<li><b>Prod/h, Cons/h</b> — capacity of every station's production modules
&times; game recipes, plus population upkeep (workforce &times; per-race
recipes). Workforce production bonuses are not modelled.
A <span class='warn'>~</span> marks minable wares, whose production is
estimated from actual deliveries into stations.</li>
<li><b>Stock</b> — all station cargo plus free-floating collectables
(scrap cubes, dropped cargo). <b>Cover</b> = stock / consumption.</li>
<li><b>Buy demand</b> — units stations currently offer to buy;
<b>Demand (Cr)</b> — those offers valued at their offered prices.</li>
<li><b>Build demand</b> — materials still missing for station
constructions. Shipyard ship-order backlogs are excluded (their near-term
needs already appear as buy offers).</li>
<li><b>Buyers / Understocked</b> — stations with an open buy offer plus
constructions missing the ware; understocked = holding less than
{UNDERSTOCK_PCT:.0%} of their target level (stock + still wanted). Many
understocked buyers despite high global cover = a distribution problem,
not a supply problem.</li>
<li><b>Fill %</b> — buyer-side satisfaction: buyers' stock vs their target
level. Producer hoards don't count. Low = open market gap.</li>
<li><b>Satisfy (h)</b> — hours until all open buy+build demand could be
filled from the production surplus (optimistic floor — good for ranking,
not scheduling). Without a surplus the market can never converge, since
consumption regenerates the order book: shown as
<b>never (Xh backlog)</b>, where X is the standing order book measured in
hours of the market's total delivery flow — small X = tight but liquid
market, large X = deep chronic deficit.</li>
<li><b>Traded/h, Cr/h</b> — deliveries estimated from station stock
increases between logged trade events, valued at average game price.</li>
<li><b>Best sell</b> — highest open buy-offer price, with premium vs the
ware's average game price.</li>
</ul>
<p class='notehead'>Scope &amp; caveats</p>
<ul>
<li>Xenon stations and construction sites are excluded everywhere — they
consume and hoard heavily but never trade with anyone.</li>
<li>Delivery estimates slightly overcount when loads hop through trade
stations, and player-internal transfers may not be logged.</li>
</ul>
<p>Click a table row for ware detail: best places to sell and buy, unmet
demand by sector, and the delivery trend vs consumption capacity.</p>
</div>
</details>
<p><label><input type='checkbox' id='buildonly'>
show ship/station build wares only</label></p>
<table id='market' class='display nowrap' style='width:100%'>
<thead><tr><th>Ware</th><th>Prod/h</th><th>Cons/h</th><th>Balance/h</th>
<th>Stock</th><th>Cover (h)</th><th>Buy demand</th><th>Build demand</th>
<th>Buyers</th><th>Understocked</th><th>Traded/h</th>
<th>Cr/h (est.)</th><th>Best sell</th><th>Demand (Cr)</th>
<th>Fill %</th><th>Satisfy (h)</th></tr></thead>
</table>
<hr style='border-color:#444;margin:18px 0'>
<p><label for='ware'>Ware detail:</label><select id='ware'></select> <span id='wareinfo' class='note'></span></p>
<div id='volume' style='height:320px'></div>
<p><label for='minvol'>Min offer volume:</label>
<input type='range' id='minvol' min='0' max='100' value='0'
       style='width:280px;vertical-align:middle'>
<span id='minvol_lbl'>0 units</span></p>
<div style='display:flex'>
  <div id='topbuyers' style='height:400px;width:50%'></div>
  <div id='topsellers' style='height:400px;width:50%'></div>
</div>
<div style='display:flex'>
  <div id='byfaction' style='height:360px;width:50%'></div>
  <div id='bystation' style='height:360px;width:50%'></div>
</div>
<div style='display:flex'>
  <div id='bysector' style='height:320px;width:50%'></div>
  <div id='byfacdemand' style='height:320px;width:50%'></div>
</div>
<script>
const ROWS = {table_rows};
const DETAIL = {json.dumps(detail, separators=(",", ":"))};
const WNAMES = {json.dumps(ware_names, separators=(",", ":"))};
const BUILD_WARES = new Set({json.dumps(build_wares, separators=(",", ":"))});
const OLABELS = {json.dumps(olabels, separators=(",", ":"))};
const TRANSPORT = {json.dumps({r['ware']: transport.get(r['ware'], '') for r in summary}, separators=(',', ':'))};
const WVOL = {json.dumps({r['ware']: r['vol'] for r in summary}, separators=(',', ':'))};
const FCOLOURS = {json.dumps({s_: ref.colour_of_short(s_) for s_ in sorted(ref.faction_short.values())}, separators=(',', ':'))};
const LAYOUT = () => ({{
  paper_bgcolor:'{DARK_BG}', plot_bgcolor:'{DARK_PLOT}',
  font:{{color:'{DARK_FG}'}}, margin:{{t:40,l:60,r:20,b:40}},
  xaxis:{{gridcolor:'#3a3a3a'}}, yaxis:{{gridcolor:'#3a3a3a'}},
}});
const CFG = {{displaylogo:false}};
function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}

const sel = document.getElementById('ware');
ROWS.forEach(r => {{
  const o = document.createElement('option');
  o.value = r[17]; o.textContent = r[0]; sel.appendChild(o);
}});

// numeric data with display-only rendering so every column sorts numerically
const numCol = (d, t) => t === 'display' ? fmt(d) : d;
const table = $('#market').DataTable({{
  data: ROWS,
  order: [], pageLength: 15,
  columnDefs: [
    {{targets: [2, 4, 6, 7, 8, 10, 11, 13], render: numCol}},
    {{targets: 1, render: (d, t, row) => t === 'display'
      ? (row[18] ? "<span class=warn title='estimated from deliveries'>~"
                   + fmt(d) + "</span>" : fmt(d))
      : d}},
    {{targets: 3, render: (d, t) => t === 'display'
      ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d) + "</span>"
      : d}},
    {{targets: 5, render: (d, t) => {{
      if (t === 'display') return d === null ? '&mdash;'
        : (d < {COVER_LOW_H:g} ? "<span class=neg>" + d + "</span>"
           : (d < 10 ? "<span class=warn>" + d + "</span>" : d));
      return d === null ? 1e12 : d;   // no consumption sorts last
    }}}},
    {{targets: 9, render: (d, t, row) => {{
      const ratio = row[8] > 0 ? d / row[8] : 0;
      if (t === 'display') return row[8] === 0 ? '&mdash;'
        : ((ratio > 0.4 ? "<span class=neg>" : (ratio > 0.15
            ? "<span class=warn>" : "<span>")) + d + " / " + row[8]
           + "</span>");
      return ratio;                    // sort by understocked share
    }}}},
    {{targets: 12, render: (d, t, row) => {{
      if (t === 'display') return d === null ? '&mdash;'
        : fmt(row[19]) + " Cr <span class='" + (d >= 25 ? "pos" : (d >= 0
            ? "warn" : "neg")) + "'>(" + (d >= 0 ? "+" : "") + d + "%)</span>";
      return d === null ? -1e12 : d;   // sort by premium over average price
    }}}},
    {{targets: 14, render: (d, t) => {{
      if (t === 'display') return d === null ? '&mdash;'
        : "<span class='" + (d < 30 ? "pos" : (d < 70 ? "warn" : ""))
          + "'>" + d + "%</span>";     // low fill = open market gap
      return d === null ? 1e12 : d;
    }}}},
    {{targets: 15, render: (d, t, row) => {{
      const flag = row[16];
      if (t === 'display') {{
        if (flag === 'sat') return '&mdash;';
        if (flag === 'never') return "<span class=warn>never</span>";
        if (flag === 'backlog') return "<span class=warn title='no production "
          + "surplus: consumption regenerates demand, so the market cannot "
          + "converge; value = open orders as hours of current delivery flow'>"
          + "never (" + d + "h backlog)</span>";
        return fmt(d) + 'h';
      }}
      // sort: real fill times, then chronic markets by backlog depth, then never
      if (flag === 'sat') return 0;
      if (flag === 'backlog') return 1e6 + d;
      if (flag === 'never') return 1e12;
      return d;
    }}}},
    {{targets: [16, 17, 18, 19], visible: false}},
  ],
}});
$('#market tbody').on('click', 'tr', function() {{
  sel.value = ROWS[table.row(this).index()][17];
  render();
}});

$.fn.dataTable.ext.search.push(function(settings, data, dataIndex, rowData) {{
  if (!document.getElementById('buildonly').checked) return true;
  return BUILD_WARES.has(rowData[17]);
}});
document.getElementById('buildonly').addEventListener(
  'change', () => table.draw());

function render() {{
  const w = sel.value, d = DETAIL[w] || {{}}, name = WNAMES[w] || w;
  document.getElementById('wareinfo').textContent =
    (WVOL[w] || '?') + ' m\u00b3/unit \u00b7 ' + (TRANSPORT[w] || '?');
  const vol_traces = [
    {{type:'bar', x:d.hours || [], y:d.volume || [],
      marker:{{color:'#4e9fd1'}}, name:'Deliveries'}},
  ];
  if (d.cons > 0 && (d.hours || []).length) {{
    vol_traces.push({{type:'scatter', mode:'lines',
      x:[Math.min(...d.hours), 0], y:[d.cons, d.cons],
      name:'Consumption capacity/h',
      line:{{color:'#ff6b6b', dash:'dash'}}}});
  }}
  Plotly.react('volume', vol_traces, Object.assign({{}}, LAYOUT(), {{
    title:{{text:name + ' — traded volume per hour', font:{{size:15}}}},
    xaxis:{{title:'Hours until Now', gridcolor:'#3a3a3a'}},
    yaxis:{{title:'Units', gridcolor:'#3a3a3a'}},
  }}), CFG);

  const cf = d.cfactions || [], traces = [];
  if (cf.length) {{
    traces.push({{type:'bar', name:'Production/h', x:cf,
      y:d.cprod, marker:{{color:'#4ecf71'}}}});
    traces.push({{type:'bar', name:'Consumption/h', x:cf,
      y:d.ccons.map(v => -v), marker:{{color:'#ff6b6b'}}}});
  }}
  if (d.delf && d.delf.length) {{
    // minable wares: who actually receives the mined supply
    traces.push({{type:'bar', name:'Deliveries/h (est. production)',
      x:d.delf, y:d.delv, marker:{{color:'#4e9fd1'}}}});
  }}
  Plotly.react('byfaction', traces, Object.assign({{}}, LAYOUT(), {{
    title:{{text:'Capacity by faction (units/h)', font:{{size:15}}}},
    barmode:'relative', legend:{{orientation:'h', y:1.15}},
  }}), CFG);

  const st = (d.stations || []).slice().reverse();
  Plotly.react('bystation', [
    {{type:'bar', orientation:'h', y:st,
      x:(d.svolume || []).slice().reverse(),
      marker:{{color:(d.st_f || []).map(f => FCOLOURS[f] || '#c9a44e')
        .slice().reverse()}},
      name:'Traded volume'}},
  ], Object.assign({{}}, LAYOUT(), {{
    title:{{text:'Top trading stations (units)', font:{{size:15}}}},
    margin:{{t:40,l:260,r:20,b:40}},
  }}), CFG);

  // min-volume slider: cubic curve scaled to the ware's largest offer
  const pos = +document.getElementById('minvol').value;
  const maxA = Math.max(1, ...(d.bo || []).map(o => o[2]),
                        ...(d.so || []).map(o => o[2]));
  const minv = Math.round(maxA * Math.pow(pos / 100, 3));
  document.getElementById('minvol_lbl').textContent = fmt(minv)
    + ' units = ' + fmt(minv * (WVOL[w] || 0)) + ' m\u00b3';
  const offerChart = (id, offers, colour, title) => {{
    const top = (offers || []).filter(o => o[2] >= minv).slice(0, 10);
    Plotly.react(id, [
      {{type:'bar', orientation:'h',
        y:top.map(o => OLABELS[o[0]]).reverse(),
        x:top.map(o => o[1] * o[2]).reverse(),
        text:top.map(o => fmt(o[1]) + ' Cr × ' + fmt(o[2]) + ' = '
          + fmt(o[2] * (WVOL[w] || 0)) + ' m³').reverse(),
        textposition:'auto',
        marker:{{color:top.map(o => FCOLOURS[o[3]] || colour).reverse()}},
        name:'Open offers'}},
    ], Object.assign({{}}, LAYOUT(), {{
      title:{{text:title, font:{{size:15}}}},
      margin:{{t:40,l:340,r:20,b:40}},
    }}), CFG);
  }};
  offerChart('topbuyers', d.bo, '#4ecf71',
    'Sell here — best open buy offers ≥ ' + fmt(minv)
    + ' units (bar = Cr on the table)');
  offerChart('topsellers', d.so, '#c9a44e',
    'Buy here — cheapest open sell offers ≥ ' + fmt(minv) + ' units');

  Plotly.react('bysector', [
    {{type:'bar', x:d.sec_l || [], y:d.sec_v || [],
      marker:{{color:(d.sec_f || []).map(f => FCOLOURS[f] || '#b06ad1')}},
      name:'Unmet demand'}},
  ], Object.assign({{}}, LAYOUT(), {{
    title:{{text:'Unmet demand by sector (buy + build, units)', font:{{size:15}}}},
    margin:{{t:40,l:60,r:20,b:90}},
  }}), CFG);

  Plotly.react('byfacdemand', [
    {{type:'bar', x:d.bf_l || [], y:d.bf_v || [],
      marker:{{color:(d.bf_l || []).map(f => FCOLOURS[f] || '#808080')}},
      name:'Unmet buy demand'}},
  ], Object.assign({{}}, LAYOUT(), {{
    title:{{text:'Unmet demand by faction (buy + build, units)', font:{{size:15}}}},
    margin:{{t:40,l:60,r:20,b:60}},
  }}), CFG);
}}
sel.addEventListener('change', render);
document.getElementById('minvol').addEventListener('input', render);
if (ROWS.length) {{ sel.value = ROWS[0][17]; render(); }}
</script>
<script>
(function() {{
  function post() {{
    parent.postMessage({{x4h: document.body.scrollHeight + 24}}, '*');
  }}
  new ResizeObserver(post).observe(document.body);
  window.addEventListener('load', function() {{ setTimeout(post, 400); }});
}})();
</script></body></html>"""

    name = f"Market_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
