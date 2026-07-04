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

_DT_CSS = "https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css"
_DT_JS = "https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"
_JQ_JS = "https://code.jquery.com/jquery-3.7.1.min.js"

COVER_LOW_H = 3.0     # global cover below this many hours is flagged red
UNDERSTOCK_PCT = 0.25  # station stock below this share of its target level
WORKUNIT = "workunit_busy"


def _recipe_table(ref: RefData) -> pd.DataFrame:
    rec = ref.recipes.copy()
    for col in ("time", "amount", "input_amount"):
        rec[col] = pd.to_numeric(rec[col], errors="coerce")
    return rec[rec["time"] > 0]


def _station_rates(frames: Frames, ref: RefData) -> pd.DataFrame:
    """Per (station id, faction, ware): prod/h and cons/h capacity."""
    uni = frames.universe.set_index("id")
    stations = set(uni.index[uni["class"] == "station"])
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
    stations = set(uni.index[uni["class"] == "station"])

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
    # stations report the same missing amount at station level AND per build
    # processor: max per (host, ware) instead of sum avoids double counting
    if not build.empty:
        build = (build.groupby(["id", "ware"], as_index=False)["amount"].max())
    build_by_ware = build.groupby("ware")["amount"].sum() if not build.empty \
        else pd.Series(dtype=float)

    # buyers = stations with open buy offers PLUS constructions missing
    # materials; a buyer holding less than UNDERSTOCK_PCT of its target level
    # (stock + still-wanted amount) is understocked. Covers module consumers,
    # shipyards stocking end-tier parts, raw material buyers and builds alike.
    offers = frames.buy_offers
    offers = offers[offers["id"].isin(stations) & (offers["amount"] > 0)] \
        if not offers.empty else offers
    build_hosts = build[(build["id"] != "") & (build["amount"] > 0)] \
        if not build.empty else build

    wanted = pd.concat([
        offers.groupby(["id", "ware"])["amount"].sum()
        if not offers.empty else pd.Series(dtype=float),
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
    else:
        under = pd.Series(dtype=int)
        n_buyers = pd.Series(dtype=int)
    buy_demand = offers.groupby("ware")["amount"].sum() if not offers.empty \
        else pd.Series(dtype=float)

    total = rates.groupby("ware")[["prod", "cons"]].sum()
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
            d = detail.setdefault(w, {})
            d["hours"] = [int(h) for h in hourly.index]
            d["volume"] = [float(v) for v in hourly.values]
            d["stations"] = [str(s) for s in top.index]
            d["svolume"] = [float(v) for v in top.values]
    for w, grp in rates.groupby("ware"):
        d = detail.setdefault(w, {})
        fp = grp.groupby("faction")[["prod", "cons"]].sum()
        fp = fp.loc[(fp["prod"] + fp["cons"]).sort_values(ascending=False).index]
        d["cfactions"] = list(fp.index)
        d["cprod"] = [float(v) for v in fp["prod"]]
        d["ccons"] = [float(v) for v in fp["cons"]]

    ware_names = {w: ref.ware_name.get(w, w) for w in detail}
    table_rows = json.dumps([[
        r["name"], r["prod"], r["cons"], r["balance"], r["stock"],
        r["cover"], r["buy"], r["build"], r["buyers"], r["under"],
        r["traded_h"], r["cr_h"], r["ware"],
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
<p class='note'>Consumption includes station modules and population needs
(workforce &times; per-race upkeep recipes); workforce production bonuses are
not modelled. Stock sums station cargo plus free-floating ware objects
(scrap cubes, dropped cargo). Cover = stock / consumption.
Buy demand = open buy offers (units stations still want); Buyers = stations
with an open buy offer plus constructions missing the ware. Understocked =
buyers holding less than
{UNDERSTOCK_PCT:.0%} of their target level (stock + open buy amount) — works
for end-tier and raw wares without module consumers, and many understocked
buyers despite high global cover indicates a logistics (distribution)
problem. Build demand = materials still missing for station constructions
(shipyard ship-order backlogs are excluded; their near-term needs show up
as buy offers). Traded volume is estimated from station stock
increases between logged trade events (deliveries; includes some production
accumulation). Cr/h values that volume at the ware's average game price.
Click a row for detail.</p>
<table id='market' class='display nowrap' style='width:100%'>
<thead><tr><th>Ware</th><th>Prod/h</th><th>Cons/h</th><th>Balance/h</th>
<th>Stock</th><th>Cover (h)</th><th>Buy demand</th><th>Build demand</th>
<th>Buyers</th><th>Understocked</th><th>Traded/h</th>
<th>Cr/h (est.)</th></tr></thead>
</table>
<hr style='border-color:#444;margin:18px 0'>
<p><label for='ware'>Ware detail:</label><select id='ware'></select></p>
<div id='volume' style='height:320px'></div>
<div style='display:flex'>
  <div id='byfaction' style='height:360px;width:50%'></div>
  <div id='bystation' style='height:360px;width:50%'></div>
</div>
<script>
const ROWS = {table_rows};
const DETAIL = {json.dumps(detail, separators=(",", ":"))};
const WNAMES = {json.dumps(ware_names, separators=(",", ":"))};
const LAYOUT = {{
  paper_bgcolor:'{DARK_BG}', plot_bgcolor:'{DARK_PLOT}',
  font:{{color:'{DARK_FG}'}}, margin:{{t:40,l:60,r:20,b:40}},
  xaxis:{{gridcolor:'#3a3a3a'}}, yaxis:{{gridcolor:'#3a3a3a'}},
}};
const CFG = {{displaylogo:false}};
function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}

const sel = document.getElementById('ware');
ROWS.forEach(r => {{
  const o = document.createElement('option');
  o.value = r[12]; o.textContent = r[0]; sel.appendChild(o);
}});

// numeric data with display-only rendering so every column sorts numerically
const numCol = (d, t) => t === 'display' ? fmt(d) : d;
const table = $('#market').DataTable({{
  data: ROWS,
  order: [], pageLength: 15,
  columnDefs: [
    {{targets: [1, 2, 4, 6, 7, 8, 10, 11], render: numCol}},
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
    {{targets: 12, visible: false}},
  ],
}});
$('#market tbody').on('click', 'tr', function() {{
  sel.value = ROWS[table.row(this).index()][12];
  render();
}});

function render() {{
  const w = sel.value, d = DETAIL[w] || {{}}, name = WNAMES[w] || w;
  Plotly.react('volume', [
    {{type:'bar', x:d.hours || [], y:d.volume || [],
      marker:{{color:'#4e9fd1'}}, name:'Volume'}},
  ], Object.assign({{}}, LAYOUT, {{
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
  Plotly.react('byfaction', traces, Object.assign({{}}, LAYOUT, {{
    title:{{text:'Capacity by faction (units/h)', font:{{size:15}}}},
    barmode:'relative', legend:{{orientation:'h', y:1.15}},
  }}), CFG);

  const st = (d.stations || []).slice().reverse();
  Plotly.react('bystation', [
    {{type:'bar', orientation:'h', y:st,
      x:(d.svolume || []).slice().reverse(),
      marker:{{color:'#c9a44e'}}, name:'Traded volume'}},
  ], Object.assign({{}}, LAYOUT, {{
    title:{{text:'Top trading stations (units)', font:{{size:15}}}},
    margin:{{t:40,l:260,r:20,b:40}},
  }}), CFG);
}}
sel.addEventListener('change', render);
if (ROWS.length) {{ sel.value = ROWS[0][12]; render(); }}
</script></body></html>"""

    name = f"Market_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
