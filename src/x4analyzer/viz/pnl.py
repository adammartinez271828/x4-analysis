"""Station P&L statements (docs/analytics-ideas.md #6).

Per player station: revenue, input costs, net profit/h and trend from the
(cross-run cached) tradelog — trades executed by a station's subordinate
traders are already attributed to the station by the R-inherited proxy
logic. Station value is the sum of its modules' ware prices (module wares
carry a <component ref> back to the macro), giving a payback estimate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..frames import Frames
from ..refdata import RefData
from .common import DARK_BG, DARK_FG, DARK_MUTED, DARK_PLOT, mixed_rainbow

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

TREND_WINDOW_H = 3.0


def _station_value(frames: Frames, ref: RefData) -> pd.Series:
    """Station id -> credits value of its built modules (module ware avg
    prices; macros without a module ware — build storages etc. — count 0)."""
    w = ref.wares
    mod_wares = w[w["component"].astype(str) != ""]
    price_by_macro = dict(zip(
        mod_wares["component"].astype(str).str.lower(),
        pd.to_numeric(mod_wares["price_avg"], errors="coerce").fillna(0),
    ))
    mods = frames.built_modules   # value what exists, not what's planned
    if mods.empty:
        return pd.Series(dtype=float)
    vals = mods.assign(v=mods["macro"].map(price_by_macro).fillna(0))
    return vals.groupby("id")["v"].sum()


def build_pnl(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
              guid: str) -> str | None:
    stations = frames.stations
    tl = frames.tradelog
    if stations.empty or tl.empty:
        return None
    log("-> Station P&L")

    span_start = float(tl["time"].min())
    span_h = max((frames.time_now - span_start) / 3600.0, 0.1)
    trend_start = frames.time_now - 3600 * TREND_WINDOW_H

    sales = tl[(tl["seller.faction"] == "PLA")
               & (tl["buyer.faction"] != "PLA")]
    buys = tl[(tl["seller.faction"] != "PLA")
              & (tl["buyer.faction"] == "PLA")]
    value = _station_value(frames, ref)

    rows = []
    series: dict[str, dict] = {}
    for _, d in stations.iterrows():
        code = str(d["code"])
        label = f"{d['name']} ({code})"
        rev = sales[sales["seller.code"] == code]
        cost = buys[buys["buyer.code"] == code]
        revenue = float(rev["money"].sum())
        costs = float(cost["money"].sum())          # positive credits spent
        net = revenue - costs
        recent = (float(rev[rev["time"] > trend_start]["money"].sum())
                  - float(cost[cost["time"] > trend_start]["money"].sum()))
        recent_h = recent / TREND_WINDOW_H
        net_h = net / span_h
        val = float(value.get(d["id"], 0.0))
        payback = val / net_h if net_h > 0 and val > 0 else None
        rows.append({
            "label": label, "trades": len(rev) + len(cost),
            "revenue": revenue, "costs": costs, "net": net,
            "net_h": net_h, "recent_h": recent_h,
            "value": val, "payback": payback,
        })
        # cumulative net series (hour bins) for the chart
        ev = pd.concat([
            rev[["time", "money"]],
            cost[["time", "money"]].assign(money=lambda x: -x["money"]),
        ])
        if not ev.empty:
            ev = ev.sort_values("time")
            hours = ((ev["time"] - frames.time_now) / 3600.0)
            series[label] = {
                "h": [round(float(v), 2) for v in hours],
                "c": [round(float(v)) for v in ev["money"].cumsum()],
            }
    rows.sort(key=lambda r: r["net_h"], reverse=True)

    table_rows = json.dumps([[
        r["label"], r["trades"], round(r["revenue"]), round(r["costs"]),
        round(r["net"]), round(r["net_h"]), round(r["recent_h"]),
        round(r["value"]), round(r["payback"], 1) if r["payback"] else None,
    ] for r in rows], separators=(",", ":"))

    colours = dict(zip([r["label"] for r in rows],
                       mixed_rainbow(len(rows))))

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<script src='lib/plotly.min.js'></script>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
.note{{color:{DARK_MUTED};font-size:12px;}}
.pos{{color:#4ecf71;}} .neg{{color:#ff6b6b;}} .warn{{color:#e8b84e;}}
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
<h3 style='margin:4px 0'>Station P&amp;L
<small style='color:{DARK_MUTED};font-weight:normal'>
({span_h:.1f}h of trade history incl. cache)</small></h3>
<p class='note'>Revenue = external sales, Costs = external purchases
(subordinate traders count toward their station); intra-empire transfers
are excluded. Value = sum of built modules at average game prices; Payback
= value ÷ net/h. Trend compares the last {TREND_WINDOW_H:g}h against the
whole history.</p>
<table id='pnl' class='display nowrap' style='width:100%'>
<thead><tr><th>Station</th><th>Trades</th><th>Revenue</th><th>Costs</th>
<th>Net</th><th>Net/h</th><th>Last {TREND_WINDOW_H:g}h /h</th>
<th>Value</th><th>Payback (h)</th></tr></thead></table>
<div id='cumnet' style='height:420px'></div>
<script>
const ROWS = {table_rows};
const SERIES = {json.dumps(series, separators=(",", ":"))};
const COLOURS = {json.dumps(colours, separators=(",", ":"))};
function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}
const numCol = (d, t) => t === 'display' ? fmt(d) : d;

$('#pnl').DataTable({{
  data: ROWS, order: [], pageLength: 15,
  columnDefs: [
    {{targets: [1, 2, 3, 7], render: numCol}},
    {{targets: [4, 5], render: (d, t) => t === 'display'
      ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
        + "</span>" : d}},
    {{targets: 6, render: (d, t, row) => {{
      if (t !== 'display') return d;
      const base = row[5];
      const arrow = d > base * 1.15 ? ' ▲' : (d < base * 0.85 ? ' ▼' : '');
      return (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
        + arrow + "</span>";
    }}}},
    {{targets: 8, render: (d, t) => {{
      if (t === 'display') return d === null ? '&mdash;' : fmt(d) + 'h';
      return d === null ? 1e12 : d;
    }}}},
  ],
}});

const traces = Object.entries(SERIES).map(([name, s]) => ({{
  type:'scatter', mode:'lines', name:name, x:s.h,
  y:s.c.map(v => v / 1e6), line:{{width:2, color:COLOURS[name]}},
}}));
Plotly.react('cumnet', traces, {{
  paper_bgcolor:'{DARK_BG}', plot_bgcolor:'{DARK_PLOT}',
  font:{{color:'{DARK_FG}'}},
  title:{{text:'Cumulative net profit per station', font:{{size:15}}}},
  xaxis:{{title:'Hours until Now', gridcolor:'#3a3a3a'}},
  yaxis:{{title:'Credits (millions)', gridcolor:'#3a3a3a'}},
  legend:{{orientation:'h', y:-0.2, traceorder:'normal'}},
  margin:{{t:40,l:60,r:20,b:40}},
}}, {{displaylogo:false}});

(function() {{
  function post() {{
    parent.postMessage({{x4h: document.body.scrollHeight + 24}}, '*');
  }}
  new ResizeObserver(post).observe(document.body);
  window.addEventListener('load', function() {{ setTimeout(post, 400); }});
}})();
</script></body></html>"""

    name = f"Station PnL_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
