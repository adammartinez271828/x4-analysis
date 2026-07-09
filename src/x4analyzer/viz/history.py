"""Per-object trade history browser.

One self-contained page: the player's sales/buys are embedded as JSON and a
dropdown picks a station or ship; charts and the trade table re-render
client-side. Trades made by a subordinate on behalf of a commander are
attributed to both, so a station's history includes its trade ships and each
ship can also be inspected on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..cli import log
from ..frames import Frames
from .common import DARK_BG, DARK_FG, DARK_MUTED, DARK_PLOT

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"


def _label(name, code) -> str | None:
    if pd.isna(name) or str(name) == "":
        return None
    if pd.isna(code) or str(code) == "":
        return str(name)
    return f"{name} ({code})"


def _commander_prefix(frames: Frames) -> dict[str, str]:
    """Follower code -> commander label ('Osaka (BBB-222)'), from the
    save-time fleet hierarchy (ship AND station commanders)."""
    po = frames.playerowned.set_index("id")
    pre: dict[str, str] = {}
    for _, w in frames.wings.iterrows():
        f, l = w["follower"], w["leader"]
        if f in po.index and l in po.index:
            leader = _label(po.at[l, "name"], po.at[l, "code"])
            code = str(po.at[f, "code"])
            if leader and code:
                pre[code] = leader
    return pre


def _records(frames: Frames) -> list[dict]:
    """One record per (trade, attributed object)."""
    tl = frames.tradelog
    prefix = _commander_prefix(frames)
    recs: list[dict] = []

    def add(df, own_side: str, sign: int) -> None:
        other = "buyer" if own_side == "seller" else "seller"
        for _, r in df.iterrows():
            own = _label(r[f"{own_side}.name"], r[f"{own_side}.code"])
            proxy = _label(r[f"{own_side}.proxy.name"],
                           r[f"{own_side}.proxy.code"])
            # subordinates are listed under "Commander - Ship" so fleet
            # members group together in the (sorted) dropdown
            oc = prefix.get(str(r[f"{own_side}.code"]))
            if own and oc:
                own = f"{oc} - {own}"
            pc = prefix.get(str(r[f"{own_side}.proxy.code"]))
            if proxy and pc:
                proxy = f"{pc} - {proxy}"
            counter = _label(r[f"{other}.name"], r[f"{other}.code"]) or "?"
            base = {
                "t": round(float(r["time"]), 1),
                "c": str(r["commodity"]),
                "a": int(r["amount"]) if pd.notna(r["amount"]) else 0,
                "m": sign * (int(r["money"]) if pd.notna(r["money"]) else 0),
                "p": f"{r[f'{other}.faction']}: {counter}",
            }
            if proxy:
                # executed by a subordinate: one record for the ship itself
                # and one attributing it to the commander (marked "via" so it
                # can be filtered out — the save only knows the CURRENT fleet
                # hierarchy, so commander attribution of old trades is a guess)
                recs.append({**base, "o": proxy, "v": ""})
                if own:
                    recs.append({**base, "o": own, "v": proxy})
            elif own:
                recs.append({**base, "o": own, "v": ""})
    sales = tl[(tl["seller.faction"] == "PLA") & (tl["buyer.faction"] != "PLA")]
    buys = tl[(tl["seller.faction"] != "PLA") & (tl["buyer.faction"] == "PLA")]
    add(sales, "seller", +1)
    add(buys, "buyer", -1)
    return recs


def build_trade_history(frames: Frames, files_dir: Path, guid: str) -> str | None:
    recs = _records(frames)
    if not recs:
        return None
    log("-> Trade History browser")

    objects = sorted({r["o"] for r in recs}, key=str.casefold)

    data_json = json.dumps(recs, separators=(",", ":"))
    options = "\n".join(f"<option>{o}</option>" for o in objects)

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<script src='lib/plotly.min.js'></script>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
label{{color:{DARK_MUTED};margin-right:6px;}}
select{{background:#2a2a2a;color:{DARK_FG};border:1px solid #555;padding:4px 8px;
        font-size:14px;margin-right:16px;}}
#summary{{color:{DARK_MUTED};font-size:13px;margin-left:8px;}}
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
.sale{{color:#4ecf71;}} .buy{{color:#ff6b6b;}}
</style></head><body>
<p>
<label for='obj'>Station / Ship:</label><select id='obj'>{options}</select>
<label for='side'>Show:</label>
<select id='side'><option value='all'>Sales &amp; Buys</option>
<option value='sale'>Sales only</option><option value='buy'>Buys only</option></select>
<label><input type='checkbox' id='redirect' checked>
include trades executed by subordinates</label>
<span id='summary'></span>
</p>
<p class='note' style='color:{DARK_MUTED};font-size:12px;margin-top:-6px'>
Subordinate attribution uses the fleet hierarchy at save time — trades made
before a ship was (re)assigned may show under the wrong commander. Uncheck the
box to attribute every trade to the ship that executed it.</p>
<div id='hourly' style='height:340px'></div>
<div id='bycommodity' style='height:300px'></div>
<table id='trades' class='display nowrap' style='width:100%'>
<thead><tr><th>Hours Ago</th><th>Type</th><th>Commodity</th><th>Amount</th>
<th>Credits</th><th>Counterparty</th><th>Executed by</th></tr></thead>
<tbody></tbody></table>
<script>
const DATA = {data_json};
const TIME_NOW = {frames.time_now};
const LAYOUT = () => ({{
  paper_bgcolor:'{DARK_BG}', plot_bgcolor:'{DARK_PLOT}',
  font:{{color:'{DARK_FG}'}}, margin:{{t:40,l:60,r:20,b:40}},
  xaxis:{{gridcolor:'#3a3a3a'}}, yaxis:{{gridcolor:'#3a3a3a'}},
  legend:{{orientation:'h', y:1.12}},
}});
const CFG = {{displaylogo:false}};
let table = null;

function fmt(n) {{ return n.toLocaleString('en-US'); }}

function render() {{
  const obj = document.getElementById('obj').value;
  const side = document.getElementById('side').value;
  const redirect = document.getElementById('redirect').checked;
  const rows = DATA.filter(r => r.o === obj &&
    (redirect || r.v === '') &&
    (side === 'all' || (side === 'sale' ? r.m > 0 : r.m < 0)));

  // hourly sales/buys bars + cumulative net line
  const sales = {{}}, buys = {{}};
  let totSale = 0, totBuy = 0;
  rows.forEach(r => {{
    const h = Math.floor((r.t - TIME_NOW) / 3600);
    if (r.m > 0) {{ sales[h] = (sales[h] || 0) + r.m; totSale += r.m; }}
    else {{ buys[h] = (buys[h] || 0) + r.m; totBuy += r.m; }}
  }});
  const hours = [];
  const hMin = Math.min(...rows.map(r => Math.floor((r.t - TIME_NOW) / 3600)), 0);
  for (let h = hMin; h <= 0; h++) hours.push(h);
  let cum = 0;
  const net = hours.map(h => (cum += (sales[h] || 0) + (buys[h] || 0)) / 1e6);
  Plotly.react('hourly', [
    {{type:'bar', name:'Sales', x:hours, y:hours.map(h => (sales[h] || 0) / 1e6),
      marker:{{color:'#4ecf71'}}}},
    {{type:'bar', name:'Buys', x:hours, y:hours.map(h => (buys[h] || 0) / 1e6),
      marker:{{color:'#ff6b6b'}}}},
    {{type:'scatter', name:'Cumulative net', x:hours, y:net, mode:'lines',
      line:{{color:'#e8e8e8', dash:'dash'}}}},
  ], Object.assign({{}}, LAYOUT(), {{
    title:{{text: obj + ' — hourly trade volume', font:{{size:15}}}},
    barmode:'relative',
    xaxis:{{title:'Hours until Now', gridcolor:'#3a3a3a'}},
    yaxis:{{title:'Credits (millions)', gridcolor:'#3a3a3a'}},
  }}), CFG);

  // per-commodity totals
  const byC = {{}};
  rows.forEach(r => {{
    byC[r.c] = byC[r.c] || {{sale:0, buy:0}};
    if (r.m > 0) byC[r.c].sale += r.m; else byC[r.c].buy += -r.m;
  }});
  const cs = Object.keys(byC).sort(
    (a, b) => (byC[b].sale + byC[b].buy) - (byC[a].sale + byC[a].buy));
  Plotly.react('bycommodity', [
    {{type:'bar', name:'Sales', orientation:'h', y:cs.slice().reverse(),
      x:cs.slice().reverse().map(c => byC[c].sale / 1e6),
      marker:{{color:'#4ecf71'}}}},
    {{type:'bar', name:'Buys', orientation:'h', y:cs.slice().reverse(),
      x:cs.slice().reverse().map(c => -byC[c].buy / 1e6),
      marker:{{color:'#ff6b6b'}}}},
  ], Object.assign({{}}, LAYOUT(), {{
    title:{{text:'By commodity', font:{{size:15}}}},
    barmode:'relative',
    xaxis:{{title:'Credits (millions)', gridcolor:'#3a3a3a'}},
    margin:{{t:40,l:170,r:20,b:40}},
  }}), CFG);

  // trade table, newest first
  const body = rows.sort((a, b) => b.t - a.t).map(r => [
    ((TIME_NOW - r.t) / 3600).toFixed(1),
    r.m > 0 ? '<span class=sale>Sale</span>' : '<span class=buy>Buy</span>',
    r.c, fmt(r.a), fmt(r.m), r.p, r.v || '—',
  ]);
  if (table) {{ table.clear(); table.rows.add(body).draw(); }}
  else {{
    table = $('#trades').DataTable({{data: body, order: [], pageLength: 15}});
  }}

  document.getElementById('summary').textContent =
    rows.length + ' trades — sales ' + fmt(totSale) + ' Cr, buys ' +
    fmt(-totBuy) + ' Cr, net ' + fmt(totSale + totBuy) + ' Cr';
}}

document.getElementById('obj').addEventListener('change', render);
document.getElementById('side').addEventListener('change', render);
document.getElementById('redirect').addEventListener('change', render);
render();
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

    name = f"Trade History_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
