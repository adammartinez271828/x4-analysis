"""Empire bottleneck audit: everything currently wrong with YOUR assets.

Sections (see docs/analytics-ideas.md #5):
- production input starvation: hours of input cover per station, from stock
  vs the station's own recipe consumption rates;
- output pile-up: product stock measured in hours of production;
- storage saturation: per transport class, stock volume vs module capacity;
- constructions waiting for materials (insufficient blocks on own sites);
- idle ships: empty order queue, or only a default Wait/DockAndWait-style
  order, excluding fleet subordinates;
- staffing: workforce vs what production modules want vs housing;
- crew gaps: M/L/XL ships without engineers, low-skill pilots on big ships,
  stations without managers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..frames import Frames
from ..refdata import RefData
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
    mods = frames.station_modules
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
    build = frames.build_demand
    rows = []
    if not build.empty:
        uni = frames.universe.set_index("id")
        smacro_name = dict(zip(frames.sectors["macro"],
                               frames.sectors["name"]))
        # a build storage is the materials depot of a station plot; name it
        # by its sector and the player station there (if any), since the
        # game never shows the storage's own code
        own_station_in = {}
        for _, st in stations.iterrows():
            own_station_in.setdefault(st["sector.id"], st_name[st["id"]])
        mine = build[(build["kind"] == "insufficient")
                     & build["id"].map(uni["owner"]).eq("player")]
        mine = mine.groupby(["id", "ware"], as_index=False)["amount"].max()
        for r in mine.itertuples(index=False):
            label = st_name.get(r.id)
            if not label:
                sector = smacro_name.get(uni["sector.macro"].get(r.id), "?")
                hint = own_station_in.get(uni["sector.id"].get(r.id))
                label = (f"Build plot in {sector} ({uni['code'].get(r.id, '?')})"
                         + (f" — likely {hint}" if hint else ""))
            rows.append({"Site": label, "Missing": wname(r.ware),
                         "Amount": round(r.amount)})
    waiting = (pd.DataFrame(rows).sort_values("Amount", ascending=False)
               if rows else pd.DataFrame())

    # ---- 5. idle ships --------------------------------------------------------
    orders = frames.orders
    followers = set(frames.wings["follower"])
    rows = []
    if not ships.empty:
        per_ship = orders.groupby("id") if not orders.empty else None
        for _, d in ships.iterrows():
            sid = d["id"]
            if sid in followers:
                continue  # subordinates work for their commander
            olist = (per_ship.get_group(sid)
                     if per_ship is not None and sid in per_ship.groups
                     else pd.DataFrame(columns=["order", "default", "state"]))
            nondefault = olist[~olist["default"]]
            if not nondefault.empty:
                continue
            default = olist[olist["default"]]
            current = (str(default.iloc[0]["order"]) if not default.empty
                       else "none")
            if default.empty or current in IDLE_DEFAULTS:
                rows.append({
                    "Ship": f"{d['name']} ({d['code']})",
                    "Size": str(d["size"]),
                    "Sector": sec_name.get(d["sector.id"], "?"),
                    "Order": current,
                    "Pilot": str(d["pilot.name"]) if pd.notna(d["pilot.name"])
                    else "—",
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
    rows = []
    if not ships.empty:
        big = ships[ships["size"].isin(["M", "L", "XL"])]
        for _, d in big.iterrows():
            problems = []
            if pd.isna(d["engineer"]):
                problems.append("no engineer")
            skill = d["pilot.skill"]
            if pd.isna(d["aipilot"]):
                problems.append("no pilot")
            elif pd.notna(skill) and skill < PILOT_SKILL_LOW \
                    and str(d["size"]) in ("L", "XL"):
                problems.append(f"pilot skill {skill:.0f}")
            if problems:
                rows.append({"Ship": f"{d['name']} ({d['code']})",
                             "Size": str(d["size"]),
                             "Issue": ", ".join(problems)})
    if not stations.empty:
        for _, d in stations.iterrows():
            if pd.isna(d.get("manager.id")):
                rows.append({"Ship": f"{d['name']} ({d['code']})",
                             "Size": "Station", "Issue": "no manager"})
    crew = pd.DataFrame(rows)

    sections = [
        ("Production starving for inputs",
         f"inputs below {INPUT_LOW_H:g}h of cover at your stations "
         "(STALLED = stock is empty)", starving, "t1"),
        ("Output piling up",
         f"products holding more than {OUTPUT_PILE_H:g}h of production — "
         "sell it or production will choke", piling, "t2"),
        ("Storage saturated",
         f"storage classes above {STORAGE_FULL_PCT:g}% of module capacity",
         saturated, "t3"),
        ("Constructions waiting for materials",
         "your build sites' missing wares (deliver or assign builders)",
         waiting, "t4"),
        ("Idle ships",
         "no orders, or only a default Wait/Dock order; fleet subordinates "
         "excluded", idle, "t5"),
        ("Understaffed stations",
         "workforce below 90% of what production modules want", staffing,
         "t6"),
        ("Crew gaps",
         f"M/L/XL ships without engineer/pilot, L/XL pilots below skill "
         f"{PILOT_SKILL_LOW}, stations without manager", crew, "t7"),
    ]

    chips = " ".join(
        f"<span class='chip {'chip0' if df.empty else 'chip1'}'>"
        f"{title}: {len(df)}</span>"
        for title, _d, df, _t in sections)

    body = []
    for title, desc, df, tid in sections:
        body.append(f"<h3>{title} <small>({len(df)})</small></h3>")
        body.append(f"<p class='note'>{desc}</p>")
        body.append(_table(df, tid))

    tables_js = "\n".join(
        f"$('#{tid}').DataTable({{order: [], pageLength: 10}});"
        for _t, _d, df, tid in sections if not df.empty)

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
