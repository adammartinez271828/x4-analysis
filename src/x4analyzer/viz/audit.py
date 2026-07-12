"""Empire bottleneck audit: everything currently wrong with YOUR assets.

Sections (see docs/analytics-ideas.md #5):
- production input starvation: hours of input cover per station, from stock
  vs the station's own recipe consumption rates;
- output pile-up: product stock measured in hours of production;
- storage saturation: per transport class, stock volume vs module capacity;
- constructions waiting for materials (insufficient blocks on own sites);
- idle ships: empty order queue, a Wait/DockAndWait-style standing order,
  or a standing order that is not running; excludes fleet subordinates;
- staffing: workforce vs what production modules want vs housing;
- crew gaps: M/L/XL ships without engineers, low-skill pilots on big ships,
  stations without managers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..analysis.frames import Frames
from ..analysis.mining import OBSERVED_WINDOW_H, raw_inflow
from ..gamedata.refdata import RefData
from .common import DARK_BG, DARK_FG, DARK_MUTED
from .market import _station_rates

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

INPUT_LOW_H = 3.0        # input cover below this is flagged, 0 = stalled
OUTPUT_PILE_H = 8.0      # product stock above this many hours of production
STORAGE_FULL_PCT = 85.0  # storage fill considered saturated
IDLE_DEFAULTS = {"Wait", "HoldPosition", "DockAndWait", "DockAt"}
PILOT_SKILL_LOW = 3


def _table(df: pd.DataFrame, tid: str) -> str:
    if df.empty:
        return "<p class='ok'>Nothing found — all clear.</p>"
    return df.to_html(index=False, border=0, table_id=tid,
                      classes="display nowrap", justify="left", escape=False,
                      float_format=lambda v: f"{v:,.1f}")


def _mining_cards(inflow: pd.DataFrame, st_name: dict,
                  wname) -> tuple[str, int]:
    """Raw-supply cards, one per station: per hold class (solid/liquid)
    the OVERALL shortfall — raw consumption not covered by current inflow
    — as a coverage bar, headlined by the miners needed to close it at
    the fleet's measured rate; the per-ware rates are fine print. Returns
    (html, number of class pools that need miners)."""
    if inflow.empty:
        return "", 0
    n_need = 0
    cards: list[tuple[float, str]] = []
    for sid, sgrp in inflow.groupby("id", sort=False):
        blocks = []
        total_need = 0.0
        for cls in sorted(sgrp["class"].unique(), reverse=True):
            grp = sgrp[sgrp["class"] == cls]
            r0 = grp.iloc[0]
            cons, obs = float(r0["class_cons"]), float(r0["class_obs"])
            need = r0["more_miners"]
            rate = float(r0["rate"])
            miners = int(r0["miners"])
            per_miner = float(r0["avg_cap"]) * rate
            if pd.isna(need):
                n_need += 1
                head = ("<span class='neg'>shortfall, but no known miner "
                        "type to size</span>")
            elif need > 0:
                n_need += 1
                total_need += float(need)
                head = (f"<span class='neg'>assign +{int(need)} "
                        f"miner{'s' if need > 1 else ''}</span>")
            else:
                head = "<span class='pos'>✓ covered</span>"

            if cons > 0:
                pct = 100.0 * obs / cons
                colour = ("#4ecf71" if pct >= 100
                          else "#e8b84e" if pct >= 50 else "#ff6b6b")
                bar = (f"<div class='mbar'><div style='width:"
                       f"{min(pct, 100.0):.0f}%;background:{colour}'>"
                       "</div></div>"
                       f"<div class='mnums'>inflow {obs:,.0f} of "
                       f"{cons:,.0f} m³/h consumed ({pct:.0f}%)</div>")
            else:
                bar = ("<div class='mnums'>no raw consumption — "
                       "inflow only</div>")
            rate_s = (f"{rate:.2f} loads/h measured"
                      if float(r0["measured"]) > 0
                      else f"~{rate:.2f} loads/h assumed")
            fleet = (f"{miners} miner{'s' if miners != 1 else ''} @ "
                     f"{rate_s} · one more adds ≈ {per_miner:,.0f} m³/h")
            wrows = "".join(
                f"<tr><td>{wname(r['ware'])}</td>"
                f"<td>{r['observed']:,.0f}</td><td>{r['cons']:,.0f}</td>"
                f"<td class='{'pos' if r['balance'] >= 0 else 'neg'}'>"
                f"{r['balance']:+,.0f}</td></tr>"
                for _, r in grp.iterrows())
            blocks.append(
                f"<div class='mclass'><div class='mhead'>"
                f"<b>{str(cls).capitalize()}</b>{head}</div>{bar}"
                f"<div class='mnums'>{fleet}</div>"
                "<table class='mwares'><tr><th>ware</th><th>in /h</th>"
                f"<th>used /h</th><th>&Delta; /h</th></tr>{wrows}</table>"
                "</div>")
        cards.append((total_need,
                      f"<div class='mcard'><h4>{st_name.get(sid, sid)}</h4>"
                      + "".join(blocks) + "</div>"))
    cards.sort(key=lambda c: -c[0])
    return ("<div class='mcards'>" + "".join(h for _n, h in cards)
            + "</div>"), n_need


def _remaining_construction(frames: Frames, ref: RefData,
                            host_ids: set) -> pd.DataFrame:
    """Estimated materials to finish each station's queued modules:
    unbuilt sequence entries (no constructed component references them)
    costed by module + loadout equipment build recipes. Whatever wares the
    recipes list count as build materials — no filtering."""
    mods = frames.station_modules
    if mods.empty:
        return pd.DataFrame(columns=["id", "ware", "amount"])
    mods = mods[mods["id"].isin(host_ids)]
    # a build-storage expansion plan repeats the already-planned entries
    # (same entry ids as the station sequence) — count each entry once
    mods = pd.concat([
        mods[mods["entry"].ne("")].drop_duplicates(subset=["entry"]),
        mods[mods["entry"].eq("")],
    ])
    unbuilt = mods[~mods["entry"].isin(frames.built_refs)]
    if unbuilt.empty:
        return pd.DataFrame(columns=["id", "ware", "amount"])

    w = ref.wares
    macro2ware = dict(zip(w["component"].astype(str).str.lower(), w["id"]))
    rec = ref.recipes
    rec = rec[rec["input_ware"].astype(str).ne("")]
    inputs: dict = {}
    for r in rec.itertuples(index=False):
        inputs.setdefault((r.ware, r.method), []).append(
            (r.input_ware, float(r.input_amount)))

    rows: list[dict] = []

    def cost(sid: str, macro: str, method: str) -> None:
        ware = macro2ware.get(macro)
        recipe = inputs.get((ware, method)) or inputs.get((ware, "default"))
        for inp, amt in recipe or []:
            rows.append({"id": sid, "ware": inp, "amount": amt})

    ups = frames.module_upgrades
    ups_by_entry = ups.groupby("entry")["macro"].apply(list).to_dict() \
        if not ups.empty else {}
    for r in unbuilt.itertuples(index=False):
        cost(r.id, r.macro, r.method)
        for equip in ups_by_entry.get(r.entry, []):
            cost(r.id, equip, r.method)
    if not rows:
        return pd.DataFrame(columns=["id", "ware", "amount"])
    return (pd.DataFrame(rows)
            .groupby(["id", "ware"], as_index=False)["amount"].sum())


def build_audit(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
                guid: str) -> str | None:
    stations = frames.stations
    ships = frames.ships
    if stations.empty and ships.empty:
        return None
    log("-> Empire audit")

    st_ids = set(stations["id"])
    st_name = dict(zip(stations["id"],
                       stations["name"].astype(str) + " ("
                       + stations["code"].astype(str) + ")"))
    sec_name = dict(zip(frames.sectors["sector.id"], frames.sectors["name"]))

    rates = _station_rates(frames, ref)
    my_rates = rates[rates["id"].isin(st_ids)]
    cargo = frames.station_cargo
    held = (cargo.groupby(["id", "ware"])["amount"].sum()
            if not cargo.empty else pd.Series(dtype=float))

    def wname(w):
        return ref.ware_name.get(w, w)

    # ---- 1. input starvation ----------------------------------------------
    rows = []
    for r in my_rates[my_rates["cons"] > 0].itertuples(index=False):
        stock = float(held.get((r.id, r.ware), 0.0))
        cover = stock / r.cons
        if cover < INPUT_LOW_H:
            state = ("<span class='neg'>STALLED</span>" if stock <= 0
                     else f"<span class='warn'>{cover:.1f}h left</span>")
            rows.append({"Station": st_name.get(r.id, r.id),
                         "Input": wname(r.ware), "Consumes/h": round(r.cons),
                         "Stock": round(stock), "Status": state,
                         "_sort": cover})
    starving = (pd.DataFrame(rows).sort_values("_sort").drop(columns="_sort")
                if rows else pd.DataFrame())

    # ---- 1b. raw resource supply ----------------------------------------------
    # per station and hold class: the overall shortfall (raw consumption
    # not covered by current inflow) and the miners needed to close it at
    # the fleet's measured delivery rate, rendered as cards
    inflow = raw_inflow(frames, ref, rates)
    mining_html, n_need = _mining_cards(inflow, st_name, wname)

    # ---- 2. output pile-up ---------------------------------------------------
    rows = []
    sell_price = {}
    off = frames.trade_offers
    if not off.empty:
        mine = off[(off["side"] == "sell") & off["id"].isin(st_ids)]
        sell_price = dict(zip(zip(mine["id"], mine["ware"]), mine["price"]))
    for r in my_rates[my_rates["prod"] > 0].itertuples(index=False):
        stock = float(held.get((r.id, r.ware), 0.0))
        hours = stock / r.prod
        if hours > OUTPUT_PILE_H:
            price = sell_price.get((r.id, r.ware))
            rows.append({"Station": st_name.get(r.id, r.id),
                         "Product": wname(r.ware), "Makes/h": round(r.prod),
                         "Stock": round(stock),
                         "Hours of output": round(hours, 1),
                         "Asking": f"{price:,.0f} Cr" if price else "no offer"})
    piling = (pd.DataFrame(rows).sort_values("Hours of output",
                                             ascending=False)
              if rows else pd.DataFrame())

    # ---- 3. storage saturation ----------------------------------------------
    caps = ref.modcaps.copy()
    caps["cargo_max"] = pd.to_numeric(caps["cargo_max"], errors="coerce")
    storage = caps[caps["cargo_max"] > 0][["macro", "cargo_max", "cargo_tags"]]
    mods = frames.built_modules   # unbuilt storage modules hold nothing
    ware_vol = dict(zip(ref.wares["id"],
                        pd.to_numeric(ref.wares["volume"], errors="coerce")
                        .fillna(1)))
    ware_trans = dict(zip(ref.wares["id"], ref.wares["transport"]))
    rows = []
    if not mods.empty:
        inst = mods[mods["id"].isin(st_ids)].merge(storage, on="macro")
        for (sid, tags), grp in inst.groupby(["id", "cargo_tags"]):
            cls = str(tags).strip()
            capacity = float(grp["cargo_max"].sum())
            if capacity <= 0:
                continue
            scargo = cargo[cargo["id"] == sid] if not cargo.empty else cargo
            used = sum(a * ware_vol.get(w, 1)
                       for w, a in zip(scargo["ware"], scargo["amount"])
                       if ware_trans.get(w, "") in cls)
            pct = 100.0 * used / capacity
            if pct > STORAGE_FULL_PCT:
                rows.append({"Station": st_name.get(sid, sid),
                             "Storage": cls, "Capacity (m³)": round(capacity),
                             "Used (m³)": round(used),
                             "Fill": f"<span class='neg'>{pct:.0f}%</span>"})
    saturated = pd.DataFrame(rows)

    # ---- 4. constructions waiting for materials ------------------------------
    # construction demand = the plot's build storage buy offers: the game's
    # own per-ware "still needed beyond deliveries under way" numbers
    rows = []
    uni = frames.universe.set_index("id")
    bs_mine = set(uni.index[(uni["class"] == "buildstorage")
                            & (uni["owner"] == "player")])
    offers_all = frames.trade_offers
    site_offers = (offers_all[(offers_all["side"] == "buy")
                              & offers_all["id"].isin(bs_mine)]
                   if not offers_all.empty else offers_all)
    if not site_offers.empty:
        smacro_name = dict(zip(frames.sectors["macro"],
                               frames.sectors["name"]))
        own_station_in = {}
        for _, st in stations.iterrows():
            own_station_in.setdefault(st["sector.id"], st_name[st["id"]])

        def _site_label(sid):
            sector = smacro_name.get(uni["sector.macro"].get(sid), "?")
            hint = own_station_in.get(uni["sector.id"].get(sid))
            return (f"Build plot in {sector} ({uni['code'].get(sid, '?')})"
                    + (f" — likely {hint}" if hint else ""))

        offered_sites = set(site_offers["id"])
        silent_sites = [sid for sid in bs_mine - offered_sites
                        if not _remaining_construction(
                            frames, ref, {sid}).empty]
        groups = list(site_offers.groupby("id")) \
            + [(sid, site_offers.iloc[0:0]) for sid in silent_sites]
        for sid, grp in groups:
            active = grp[grp["amount"] > 0]
            if not active.empty:
                for r in active.itertuples(index=False):
                    rows.append({"Site": _site_label(sid),
                                 "Missing": wname(r.ware),
                                 "Still needed": round(r.amount)})
            else:
                # offers exist but all at 0 units: the plot is not buying —
                # unfunded, or "buy from others" disabled. Estimate what
                # completion takes from the queued modules' build recipes,
                # minus materials already delivered to the site.
                rows.append({
                    "Site": _site_label(sid),
                    "Missing": "—",
                    "Still needed":
                        "<span class='neg'>site inactive — no funded "
                        "material orders (fund the plot / enable buying)"
                        "</span>",
                })
                est = _remaining_construction(frames, ref, {sid})
                delivered = (frames.station_cargo[
                    frames.station_cargo["id"] == sid]
                    .set_index("ware")["amount"]
                    if not frames.station_cargo.empty
                    else pd.Series(dtype=float))
                for r in est.groupby("ware")["amount"].sum().items():
                    ware_id, amt = r
                    left = amt - float(delivered.get(ware_id, 0.0))
                    if left > 0.5:
                        rows.append({
                            "Site": _site_label(sid),
                            "Missing": wname(ware_id),
                            "Still needed":
                                f"≈ {left:,.0f} <span class='note'>"
                                "(estimated from build plan)</span>",
                        })
    waiting = pd.DataFrame(rows)

    # ---- 5. idle ships --------------------------------------------------------
    orders = frames.orders
    followers = set(frames.wings["follower"])
    rows = []
    if not ships.empty:
        per_ship = orders.groupby("id") if not orders.empty else None
        for _, d in ships.iterrows():
            sid = d["id"]
            if str(d["size"]) == "XS":
                continue  # escape pods etc. — not orderable
            if sid in followers:
                continue  # subordinates work for their commander
            olist = (per_ship.get_group(sid)
                     if per_ship is not None and sid in per_ship.groups
                     else pd.DataFrame(columns=["order", "default", "state"]))
            nondefault = olist[~olist["default"]]
            if not nondefault.empty:
                continue
            default = olist[olist["default"]]
            if default.empty:
                standing = "none"
            else:
                standing = str(default.iloc[0]["order"])
                running = str(default.iloc[0]["state"]) == "started"
                if standing not in IDLE_DEFAULTS and running:
                    continue  # standing order is doing its job
                if standing not in IDLE_DEFAULTS:
                    standing += " (not running)"
            rows.append({
                "Ship": f"{d['name']} ({d['code']})",
                "Size": str(d["size"]),
                "Sector": sec_name.get(d["sector.id"], "?"),
                "Standing order": standing,
            })
    idle = pd.DataFrame(rows)

    # ---- 6. staffing -----------------------------------------------------------
    caps["housing"] = pd.to_numeric(caps["housing"], errors="coerce").fillna(0)
    caps["workers"] = pd.to_numeric(caps["workers"], errors="coerce").fillna(0)
    wf_now = (frames.workforce_all.groupby("id")["amount"].sum()
              if not frames.workforce_all.empty else pd.Series(dtype=float))
    rows = []
    if not mods.empty:
        inst = mods[mods["id"].isin(st_ids)].merge(
            caps[["macro", "housing", "workers"]], on="macro", how="left")
        agg = inst.groupby("id")[["housing", "workers"]].sum()
        for sid, r in agg.iterrows():
            need, housing = float(r["workers"]), float(r["housing"])
            have = float(wf_now.get(sid, 0.0))
            if need <= 0:
                continue
            if have < 0.9 * need:
                pct = 100.0 * have / need
                note = ("<span class='warn'>not enough housing</span>"
                        if housing < need else "")
                rows.append({"Station": st_name.get(sid, sid),
                             "Workforce": round(have), "Wanted": round(need),
                             "Housing": round(housing),
                             "Staffed": f"<span class='{'neg' if pct < 50 else 'warn'}'>{pct:.0f}%</span>",
                             "Note": note})
    staffing = pd.DataFrame(rows)

    # ---- 7. crew gaps ------------------------------------------------------------
    # every ship missing a captain or below full crew complement; the last
    # (hidden) column flags S ships whose only problem is crew, so the
    # checkbox can drop them while missing captains stay visible
    rows = []
    if not ships.empty:
        for _, d in ships.iterrows():
            size = str(d["size"])
            if size == "XS":
                continue
            problems = []
            no_pilot = pd.isna(d["aipilot"])
            if no_pilot:
                problems.append("<span class='neg'>no captain</span>")
            if size in ("M", "L", "XL") and pd.isna(d["engineer"]):
                problems.append("no engineer")
            skill = d["pilot.skill"]
            if not no_pilot and pd.notna(skill) \
                    and skill < PILOT_SKILL_LOW and size in ("L", "XL"):
                problems.append(f"pilot skill {skill:.0f}")
            cmax = d.get("crew.max")
            have = int(d.get("crew.have") or 0)
            missing = (int(cmax - have)
                       if pd.notna(cmax) and cmax > have else 0)
            if not problems and missing == 0:
                continue
            rows.append({
                "Ship": f"{d['name']} ({d['code']})",
                "Size": size,
                "Crew": (f"{have}/{cmax:.0f}" if pd.notna(cmax)
                         else str(have)),
                "Missing crew": missing,
                "Issues": ", ".join(problems),
                "_f": 1 if size == "S" and not problems else 0,
            })
    rows.sort(key=lambda r: ("no captain" not in r["Issues"],
                             -r["Missing crew"]))
    if not stations.empty:
        for _, d in stations.iterrows():
            if pd.isna(d.get("manager.id")):
                rows.append({"Ship": f"{d['name']} ({d['code']})",
                             "Size": "Station", "Crew": "",
                             "Missing crew": 0,
                             "Issues": "<span class='neg'>no manager</span>",
                             "_f": 0})
    crew = pd.DataFrame(rows)

    sections = [
        ("Production starving for inputs",
         f"inputs below {INPUT_LOW_H:g}h of cover at your stations "
         "(STALLED = stock is empty)", starving, "t1"),
        ("Raw resource supply",
         "how many more miners to assign, per station and hold class: "
         "shortfall = raw consumption not covered by current inflow (own "
         f"miners + purchases, rolling window up to {OBSERVED_WINDOW_H:g}h"
         "), converted to miners at the fleet's measured full-load rate "
         "(~ = nothing measured yet, rate borrowed from your other "
         "fleets). One solid pool feeds all mineral wares and one liquid "
         "pool all gases — the per-ware rates are the fine print inside "
         "each card", inflow, "t8"),
        ("Output piling up",
         f"products holding more than {OUTPUT_PILE_H:g}h of production — "
         "sell it or production will choke", piling, "t2"),
        ("Storage saturated",
         f"storage classes above {STORAGE_FULL_PCT:g}% of module capacity",
         saturated, "t3"),
        ("Constructions waiting for materials",
         "your build sites' open material orders — still needed beyond deliveries already under way",
         waiting, "t4"),
        ("Idle ships",
         "no orders, only a Wait/Dock standing order, or a standing order "
         "that is not running; fleet subordinates excluded", idle, "t5"),
        ("Understaffed stations",
         "workforce below 90% of what production modules want", staffing,
         "t6"),
        ("Crew gaps",
         f"ships without a captain or below full crew, M/L/XL without "
         f"engineer, L/XL pilots below skill {PILOT_SKILL_LOW}, stations "
         "without manager &nbsp; <label><input type='checkbox' id='hideS'> "
         "hide S ships that are only missing crew</label>", crew, "t7"),
    ]

    # the raw-supply cards list every mining pool; only pools that need
    # miners count as findings
    flagged = {"t8": n_need}

    chips = " ".join(
        f"<span class='chip {'chip0' if flagged.get(tid, len(df)) == 0 else 'chip1'}'>"
        f"{title}: {flagged.get(tid, len(df))}</span>"
        for title, _d, df, tid in sections)

    body = []
    for title, desc, df, tid in sections:
        body.append(f"<h3>{title} <small>({flagged.get(tid, len(df))})"
                    "</small></h3>")
        body.append(f"<p class='note'>{desc}</p>")
        if tid == "t8":
            body.append(mining_html
                        or "<p class='ok'>Nothing found — all clear.</p>")
        else:
            body.append(_table(df, tid))

    tables_js = "\n".join(
        f"$('#{tid}').DataTable({{order: [], pageLength: 10}});"
        for _t, _d, df, tid in sections
        if not df.empty and tid not in ("t7", "t8"))
    if not crew.empty:
        flag_idx = len(crew.columns) - 1
        tables_js += f"""
$('#t7').DataTable({{order: [], pageLength: 10,
  columnDefs: [{{targets: {flag_idx}, visible: false, searchable: false}}]}});
$.fn.dataTable.ext.search.push(function(settings, data, idx, rowData) {{
  if (settings.nTable.id !== 't7') return true;
  if (!document.getElementById('hideS').checked) return true;
  // searchable:false columns are blank in `data`; use the raw row data
  return String(rowData[{flag_idx}]).trim() !== '1';
}});
$('#hideS').on('change', function() {{ $('#t7').DataTable().draw(); }});"""

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
h3{{margin:22px 0 2px 0;}} h3 small{{color:{DARK_MUTED};font-weight:normal;}}
.note{{color:{DARK_MUTED};font-size:12px;margin:2px 0 8px 0;}}
.ok{{color:#4ecf71;}}
.pos{{color:#4ecf71;}} .neg{{color:#ff6b6b;}} .warn{{color:#e8b84e;}}
.chip{{display:inline-block;padding:3px 10px;border-radius:12px;margin:2px;
  font-size:12px;border:1px solid #444;}}
.chip0{{color:{DARK_MUTED};}} .chip1{{color:#e8b84e;border-color:#e8b84e;}}
.mcards{{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;}}
.mcard{{background:#252525;border:1px solid #3a3a3a;border-radius:8px;
  padding:10px 14px;flex:1 1 340px;max-width:520px;}}
.mcard h4{{margin:0 0 4px 0;}}
.mclass{{margin:10px 0 2px 0;}}
.mhead{{display:flex;justify-content:space-between;gap:10px;
  margin-bottom:4px;}}
.mbar{{background:#333;border-radius:4px;height:10px;overflow:hidden;}}
.mbar div{{height:100%;}}
.mnums{{color:{DARK_MUTED};font-size:12px;margin:3px 0;}}
table.mwares{{border-collapse:collapse;font-size:12px;margin:2px 0 0 0;}}
table.mwares th{{color:{DARK_MUTED};font-weight:normal;text-align:left;
  padding:1px 14px 1px 0;}}
table.mwares td{{padding:1px 14px 1px 0;}}
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
<h3 style='margin-top:4px'>Empire bottleneck audit</h3>
<p class='note'>Everything currently limiting YOUR assets, worst first.
Consumption/production rates are base recipe capacity for your stations'
modules.</p>
<p>{chips}</p>
{"".join(body)}
<script>$(function() {{ {tables_js} }});</script>
<script>
(function() {{
  function post() {{
    parent.postMessage({{x4h: document.body.scrollHeight + 24}}, '*');
  }}
  new ResizeObserver(post).observe(document.body);
  window.addEventListener('load', function() {{ setTimeout(post, 400); }});
}})();
</script>
</body></html>"""

    name = f"Empire Audit_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
