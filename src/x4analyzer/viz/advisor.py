"""Station build advisor (docs/analytics-ideas.md #2).

Scores "build a factory for ware W in sector S" for every producible
economy ware and every known, non-hostile sector. The score decomposes
into visible factors — demand nearby, input availability, competition,
danger, workforce food supply — each distance-discounted over the gate
graph (sectorgraph.py), normalized per ware, and weighted client-side
with sliders so the ranking is never an opaque oracle.

Unit conventions: production/consumption are capacity units/h (from the
market tab's station rates); open buy offers are a one-off unit backlog,
folded into the demand factor at 1/24th per hour and shown separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..frames import Frames
from ..refdata import RefData
from ..sectorgraph import build_adjacency, bfs_distances
from .common import DARK_BG, DARK_FG, DARK_MUTED
from .market import EXCLUDED_OWNERS, _recipe_table, _station_rates

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

RADIUS = 4            # gate hops considered "nearby"
HOSTILE_SCAN = 6      # how far to look for xenon/khaak sectors
TOP_SECTORS = 10      # sectors kept per ware
BACKLOG_H = 24.0      # one-off buy backlog counts as amount/24 per hour
INPUT_CAP = 3.0       # input availability ratio cap
_HOSTILE = ("xenon", "khaak")


def _disc(d: int) -> float:
    return 1.0 / (1.0 + d)


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
        })

        cand_rows = []
        for s in cands:
            dd = dist[s]
            demand_h = comp_h = backlog = 0.0
            for s2, d in dd.items():
                k = _disc(d)
                demand_h += cons_ws.get((wid, s2), 0.0) * k
                comp_h += prod_ws.get((wid, s2), 0.0) * k
                backlog += buy_ws.get((wid, s2), 0.0) * k
            food_h = food_sec[s]

            # input availability: bottleneck ratio over recipe inputs
            in_detail = []
            ratio_min, bottleneck = INPUT_CAP, ""
            for iw, need_h in inputs:
                avail = sum(prod_ws.get((iw, s2), 0.0) * _disc(d)
                            for s2, d in dd.items())
                ratio = avail / need_h if need_h > 0 else INPUT_CAP
                note = f"{avail:,.0f}/h nearby vs {need_h:,.0f}/h needed"
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
                "input_ratio": ratio_min, "bottleneck": bottleneck,
                "hostile_d": hd, "food_h": food_h,
                "detail": {"inputs": in_detail, "buyers": lines},
            })

        # normalize per ware and keep the most promising sectors
        dmax = max((c["demand_h"] + c["backlog"] / BACKLOG_H
                    for c in cand_rows), default=0) or 1.0
        cmax = max((c["comp_h"] for c in cand_rows), default=0) or 1.0
        fmax = max((c["food_h"] for c in cand_rows), default=0) or 1.0
        for c in cand_rows:
            c["nd"] = (c["demand_h"] + c["backlog"] / BACKLOG_H) / dmax
            c["nc"] = c["comp_h"] / cmax
            c["ni"] = c["input_ratio"] / INPUT_CAP
            c["ns"] = c["hostile_d"] / HOSTILE_SCAN
            c["nw"] = c["food_h"] / fmax
        # default-weight preview score just for the server-side cut
        cand_rows.sort(key=lambda c: (0.35 * c["nd"] + 0.25 * c["ni"]
                                      + 0.15 * c["ns"] + 0.10 * c["nw"]
                                      - 0.15 * c["nc"]), reverse=True)
        for c in cand_rows[:TOP_SECTORS]:
            if c["nd"] <= 0 and c["backlog"] <= 0:
                continue  # nobody within reach wants this ware
            rows.append({
                "ware": wname.get(wid, wid),
                "sector": c["sector"], "owner": c["owner"],
                "demand_h": round(c["demand_h"]),
                "backlog": round(c["backlog"]),
                "comp_h": round(c["comp_h"]),
                "input_ratio": round(c["input_ratio"], 2),
                "bottleneck": c["bottleneck"],
                "hostile_d": c["hostile_d"],
                "food_h": round(c["food_h"]),
                "nd": round(c["nd"], 4), "ni": round(c["ni"], 4),
                "nc": round(c["nc"], 4), "ns": round(c["ns"], 4),
                "nw": round(c["nw"], 4),
                "detail": c["detail"],
            })

    return {"rows": rows, "wares": ware_meta}


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
as backlog. Factors are normalized per ware — scores compare sectors for
the same ware, and the weights below are yours to tune. Click a row's
&#9432; for the reasoning.</p>
<div class='controls'>
  <label>Ware <select id='wsel'><option value=''>All wares</option></select></label>
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
<th>Demand/h</th><th>Backlog</th><th>Competition/h</th><th>Inputs</th>
<th>Hostile (hops)</th><th>Food/h</th></tr></thead></table>
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
function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}
const numCol = (d, t) => t === 'display' ? fmt(d) : d;

function weights() {{
  return {{d: +$('#w_d').val(), i: +$('#w_i').val(), c: +$('#w_c').val(),
           s: +$('#w_s').val(), w: +$('#w_w').val()}};
}}
function score(r, W) {{
  const total = W.d + W.i + W.c + W.s + W.w || 1;
  return 100 * (W.d * r.nd + W.i * r.ni + W.s * r.ns + W.w * r.nw
                - W.c * r.nc) / total;
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
    {{data: 'demand_h', render: numCol}},
    {{data: 'backlog', render: numCol}},
    {{data: 'comp_h', render: numCol}},
    {{data: 'input_ratio', render: (d, t, r) => t === 'display'
        ? d.toFixed(2) + (r.bottleneck ? ' (' + r.bottleneck + ')' : '')
        : d}},
    {{data: 'hostile_d', render: (d, t) => t === 'display'
        ? (d >= {HOSTILE_SCAN} ? '{HOSTILE_SCAN}+'
           : "<span class='" + (d <= 1 ? 'neg' : d <= 2 ? 'warn' : '')
             + "'>" + d + '</span>')
        : d}},
    {{data: 'food_h', render: numCol}},
  ],
}});

$('#adv tbody').on('click', 'td.det', function() {{
  const tr = $(this).closest('tr');
  const row = table.row(tr);
  if (row.child.isShown()) {{ row.child.hide(); }}
  else {{ row.child($('<tr class="childrow">').html(
      '<td></td><td colspan="10">' + row.data().det + '</td>')).show(); }}
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

$('#bal').DataTable({{
  data: DATA.wares.map(w => [w.ware, w.prod_h, w.cons_h, w.backlog,
                             w.prod_h - w.cons_h, w.out_h]),
  pageLength: 15, order: [[4, 'asc']],
  columnDefs: [
    {{targets: [1, 2, 3, 5], render: numCol}},
    {{targets: 4, render: (d, t) => t === 'display'
      ? (d >= 0 ? "<span class=pos>+" : "<span class=neg>") + fmt(d)
        + '</span>' : d}},
  ],
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
