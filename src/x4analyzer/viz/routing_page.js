// Trade > Routing: client-side transcription of analysis/opportunities.py
// _Router over the gate graph exported by analysis/routing.py, plus the
// jump BFS of analysis/sectorgraph.py. The time arithmetic below is the
// Trade Opportunities model verbatim (viz/market.py) — the two panes are
// deliberately one model; a future per-gate transit cost must change both.
(function () {
'use strict';
const D = window.X4RT;
const SEC = D.graph.sec, NODES = D.graph.nodes, PORTALS = D.graph.portals;
const ST = D.stations, SECN = D.secnames, SHIPS = D.ships;
const SM_HW_COST = 0.1;   // must match opportunities._SM_HW_COST

// ---- graph indices -------------------------------------------------
const bySector = [];      // sector index -> node indices
for (let i = 0; i < SEC.length; i++) bySector.push([]);
NODES.forEach((n, i) => bySector[n[0]].push(i));
const portalOf = NODES.map(() => []);
PORTALS.forEach(p => { portalOf[p[0]].push(p[1]); portalOf[p[1]].push(p[0]); });
// sector adjacency (jumps) is the portal graph collapsed onto sectors —
// gates.csv rows plus same-cluster pairs, one-way gates treated two-way,
// exactly what sectorgraph.build_adjacency does
const adj = SEC.map(() => []);
PORTALS.forEach(p => {
  const a = NODES[p[0]][0], b = NODES[p[1]][0];
  if (a === b) return;
  if (adj[a].indexOf(b) < 0) adj[a].push(b);
  if (adj[b].indexOf(a) < 0) adj[b].push(a);
});
const isHW = s => SEC[s][1];
const wOf = (s, sm) => (sm && SEC[s][1]) ? SM_HW_COST : 1;
const dkm = (ax, az, bx, bz) => Math.hypot(ax - bx, az - bz) / 1000;

// single-source relaxation over the whole gate graph (array-scan
// Dijkstra; ~360 nodes, so the O(n^2) scan is far cheaper than a heap)
function dijkstra(sa, x, z, sm) {
  const N = NODES.length;
  const best = new Float64Array(N).fill(Infinity);
  const kp = new Float64Array(N), kh = new Float64Array(N);
  const done = new Uint8Array(N);
  bySector[sa].forEach(n => {
    const d = dkm(x, z, NODES[n][1], NODES[n][2]);
    const c = d * wOf(sa, sm);
    if (c < best[n]) {
      best[n] = c;
      if (isHW(sa)) { kp[n] = 0; kh[n] = d; } else { kp[n] = d; kh[n] = 0; }
    }
  });
  for (;;) {
    let n = -1, bc = Infinity;
    for (let i = 0; i < N; i++) if (!done[i] && best[i] < bc) { bc = best[i]; n = i; }
    if (n < 0) break;
    done[n] = 1;
    // portal transits are free: step to the twin endpoint, then fly to
    // every gate of the arrival sector
    portalOf[n].forEach(m => {
      const msec = NODES[m][0];
      bySector[msec].forEach(k => {
        const d = k !== m
          ? dkm(NODES[m][1], NODES[m][2], NODES[k][1], NODES[k][2]) : 0;
        const c2 = bc + d * wOf(msec, sm);
        if (c2 >= best[k] - 1e-9) return;
        best[k] = c2;
        if (isHW(msec)) { kp[k] = kp[n]; kh[k] = kh[n] + d; }
        else { kp[k] = kp[n] + d; kh[k] = kh[n]; }
      });
    });
  }
  return { best: best, kp: kp, kh: kh };
}

// (km_plain, km_highway) from a source solution to one destination point
function arrive(sol, sb, x, z, sm) {
  let out = null, bestTotal = Infinity;
  bySector[sb].forEach(n => {
    if (!isFinite(sol.best[n])) return;
    const d = dkm(NODES[n][1], NODES[n][2], x, z);
    const total = sol.best[n] + d * wOf(sb, sm);
    if (total >= bestTotal) return;
    bestTotal = total;
    out = isHW(sb) ? [sol.kp[n], sol.kh[n] + d] : [sol.kp[n] + d, sol.kh[n]];
  });
  return out;
}

function routeFrom(origin, sm) {
  // origin: {sec, x, z}; returns per-station [kp, kh] (null = unreachable)
  const sol = dijkstra(origin.sec, origin.x, origin.z, sm);
  return ST.map(s => {
    if (s[2] === origin.sec) {
      const d = dkm(origin.x, origin.z, s[3], s[4]);
      return isHW(s[2]) ? [0, d] : [d, 0];
    }
    return arrive(sol, s[2], s[3], s[4], sm);
  });
}

function jumpsFrom(sec) {
  const dist = new Int32Array(SEC.length).fill(-1);
  dist[sec] = 0;
  const q = [sec];
  for (let h = 0; h < q.length; h++) {
    const c = q[h];
    adj[c].forEach(n => { if (dist[n] < 0) { dist[n] = dist[c] + 1; q.push(n); } });
  }
  return dist;
}

// ---- self-test: the page's router against Python's -----------------
(function selfTest() {
  let worst = 0, bad = 0;
  (D.chk || []).forEach(c => {
    const a = ST[c[0]], b = ST[c[1]];
    const km = a[2] === b[2]
      ? (isHW(a[2]) ? [0, dkm(a[3], a[4], b[3], b[4])]
                    : [dkm(a[3], a[4], b[3], b[4]), 0])
      : arrive(dijkstra(a[2], a[3], a[4], !!c[2]), b[2], b[3], b[4], !!c[2]);
    if (!km) { bad++; return; }
    const e = Math.abs(km[0] - c[3]) + Math.abs(km[1] - c[4]);
    if (e > worst) worst = e;
    if (e > 0.5) bad++;
  });
  const msg = 'Routing self-test: ' + (D.chk || []).length
    + ' reference routes, worst deviation ' + worst.toFixed(3) + ' km';
  if (bad) console.warn(msg + ' — ' + bad + ' MISMATCHED against the'
    + ' Python router (analysis/routing.py chk payload)');
  else console.log(msg);
})();

// ---- time model (verbatim from viz/market.py Opportunities) --------
let SHIP = null;
const el = id => document.getElementById(id);
const fmt = n => Math.round(n).toLocaleString('en-US');
function cruise() {
  const v = +el('rtcruise').value;
  return (v > 0 && v <= 1) ? v : 0.9;
}
function isSM() { return SHIP && (SHIP.cls === 'S' || SHIP.cls === 'M'); }
function useHW() { return el('rthw').checked; }
function hwSpeed() {            // m/s
  const v = +el('rthwv').value;
  return (v > 0 ? v : 10) * 1000;
}
function dockSeconds() {
  const id = SHIP && (SHIP.cls === 'L' || SHIP.cls === 'XL')
    ? 'rtdockl' : 'rtdock';
  return (+el(id).value || 0) * 60;
}
function routeKm(r) {
  if (isSM() && useHW() && r.kps !== null) return [r.kps, r.khs];
  return [r.kp, r.kh];
}
function tripSeconds(r) {
  if (!SHIP || !SHIP.speed || r.kp === null) return null;
  const v = cruise() * SHIP.speed;
  const hwv = (isSM() && useHW()) ? hwSpeed() : v;
  const km = routeKm(r);
  return km[0] * 1000 / v + km[1] * 1000 / hwv + dockSeconds();
}
function fmtMin(sec) {
  if (sec < 90) return Math.round(sec) + ' s';
  return sec >= 5400 ? (sec / 3600).toFixed(1) + ' h'
                     : Math.round(sec / 60) + ' min';
}

// ---- labels --------------------------------------------------------
const FCOL = D.colours;
function stLabel(i) {
  const s = ST[i];
  const l = s[0].indexOf(s[1] + ' ') === 0 ? s[0].slice(s[1].length + 1) : s[0];
  let h = "<span style='color:" + (FCOL[s[1]] || '#4ecf71') + "'>" + s[1]
    + '</span> ' + l + ', ' + (SECN[s[2]] || '?');
  if (s[5] & 1) h += " <span class='pos' title='your station'>own</span>";
  if (s[5] & 2) h += " <span class='warn' title='construction site'>site</span>";
  return h;
}
function stPlain(i) {
  const s = ST[i];
  return s[1] + ' ' + s[0] + ' ' + (SECN[s[2]] || '');
}
function originLabel() {
  const o = currentOrigin();
  if (!o) return '&mdash;';
  if (o.st !== null) return stLabel(o.st);
  return "<span class='warn'>" + o.name + '</span>';
}

// ---- selectors -----------------------------------------------------
// options grouped by sector, with a plain substring filter above each
// select (no dependencies: filtering just hides options and any group
// left empty)
function fillSelect(sel, lead) {
  sel.appendChild(new Option(lead, ''));
  let group = null, gsec = -1;
  ST.forEach((s, i) => {
    if (s[2] !== gsec) {
      gsec = s[2];
      group = document.createElement('optgroup');
      group.label = SECN[gsec] || '?';
      sel.appendChild(group);
    }
    const o = new Option(s[0] + (s[5] & 1 ? ' ★' : ''), i);
    o.dataset.hay = (s[0] + ' ' + (SECN[s[2]] || '')).toLowerCase();
    group.appendChild(o);
  });
}
function wireFilter(inputId, selId) {
  el(inputId).addEventListener('input', () => {
    const q = el(inputId).value.trim().toLowerCase();
    const sel = el(selId);
    sel.querySelectorAll('optgroup').forEach(g => {
      let any = false;
      g.querySelectorAll('option').forEach(o => {
        const hit = !q || o.dataset.hay.indexOf(q) >= 0
          || g.label.toLowerCase().indexOf(q) >= 0;
        o.hidden = !hit;
        if (hit) any = true;
      });
      g.hidden = !any;
    });
  });
}
const fromSel = el('rtfrom'), toSel = el('rtto'), shipSel = el('rtship');
fillSelect(fromSel, '— pick an origin station —');
fillSelect(toSel, '— all destinations —');
wireFilter('rtfromq', 'rtfrom');
wireFilter('rttoq', 'rtto');
// the ship's own position as an origin, prepended so it is the first
// thing offered
if (SHIPS.some(s => s.loc)) {
  const o = new Option('— selected ship’s current location —',
                       'ship');
  fromSel.insertBefore(o, fromSel.firstChild.nextSibling);
}
shipSel.appendChild(new Option(
  SHIPS.length ? '— pick one of your ships —'
               : '— no player ships in this save —', ''));
SHIPS.forEach((s, i) => shipSel.appendChild(new Option(
  s.l + ' (' + s.cls + (s.speed ? ', ' + fmt(s.speed) + ' m/s travel' : '')
  + ')', i)));

const SECIDX = {};   // sector macro -> index, for the ship origin
SEC.forEach((s, i) => { SECIDX[s[0]] = i; });

function currentOrigin() {
  const v = fromSel.value;
  if (v === '') return null;
  if (v === 'ship') {
    if (!SHIP || !SHIP.loc) return null;
    const sec = SECIDX[SHIP.loc[0]];
    if (sec === undefined) return null;
    return {
      sec: sec, x: SHIP.loc[1], z: SHIP.loc[2], st: null,
      name: SHIP.l + ' — ' + (SECN[sec] || SHIP.loc[0])
        + (SHIP.loc[3] ? ' (docked)' : ' (≈ sector centre)'),
    };
  }
  const i = +v, s = ST[i];
  return { sec: s[2], x: s[3], z: s[4], st: i };
}

// ---- table ---------------------------------------------------------
let ROWS = [];
const table = $('#rtroutes').DataTable({
  data: [], deferRender: true, pageLength: 25, order: [[4, 'asc']],
  columns: [
    { data: null, render: (d, t) => {
      const o = currentOrigin();
      if (t === 'display') return originLabel();
      return o ? (o.st !== null ? stPlain(o.st) : o.name) : '';
    } },
    { data: null, render: (d, t, r) => t === 'display' ? stLabel(r.i)
        : stPlain(r.i) },
    { data: 'j', render: (d, t) => d === null
        ? (t === 'display' ? '&mdash;' : 1e12) : d },
    { data: null, render: (d, t, r) => {
      if (r.kp === null) return t === 'display' ? '&mdash;' : 1e12;
      const km = routeKm(r);
      return t === 'display' ? fmt(km[0] + km[1]) : km[0] + km[1];
    } },
    { data: null, render: (d, t, r) => {
      const v = tripSeconds(r);
      if (t === 'display') return v === null
        ? "<span class='note' title='pick one of your ships above'>"
          + '&mdash;</span>'
        : fmtMin(v);
      return v === null ? 1e12 : v;
    } },
  ],
});
$.fn.dataTable.ext.search.push(function (settings, data, dataIndex, rowData) {
  if (settings.nTable.id !== 'rtroutes') return true;
  const to = toSel.value;
  if (to !== '' && rowData && rowData.i !== +to) return false;
  return true;
});

function recompute() {
  const o = currentOrigin();
  el('rtorigin').innerHTML = o ? originLabel()
    : "<span class='note'>pick an origin</span>";
  if (!o) { ROWS = []; table.clear().draw(); return; }
  const plain = routeFrom(o, false);
  const hwr = routeFrom(o, true);
  const jd = jumpsFrom(o.sec);
  ROWS = [];
  ST.forEach((s, i) => {
    if (o.st === i) return;                 // the origin itself
    const a = plain[i], b = hwr[i];
    const diff = a && b && (Math.abs(a[0] - b[0]) > 0.5
                            || Math.abs(a[1] - b[1]) > 0.5);
    ROWS.push({
      i: i,
      j: jd[s[2]] < 0 ? null : jd[s[2]],
      kp: a ? +a[0].toFixed(1) : null,
      kh: a ? +a[1].toFixed(1) : null,
      kps: diff ? +b[0].toFixed(1) : null,
      khs: diff ? +b[1].toFixed(1) : null,
    });
  });
  table.clear().rows.add(ROWS).draw();
  el('rtcount').textContent = ROWS.length.toLocaleString('en-US')
    + ' destinations';
}
function redraw() { table.rows().invalidate('data').draw(false); }

function updShipInfo() {
  el('rtspeed').innerHTML = SHIP && SHIP.speed
    ? fmt(SHIP.speed) + ' m/s (&asymp;' + fmt(cruise() * SHIP.speed)
      + ' m/s effective)'
    : '&mdash;';
  el('rtwhere').innerHTML = SHIP && SHIP.loc
    ? (SECN[SECIDX[SHIP.loc[0]]] || SHIP.loc[0])
      + (SHIP.loc[3] ? ' (docked)'
                     : " <span class='note'>&asymp; sector centre</span>")
      + (SHIP.locn > 1 ? " <span class='note' title='this row rolls up "
         + SHIP.n + " identical ships in different places'>(1 of "
         + SHIP.n + ')</span>' : '')
    : '&mdash;';
}
shipSel.addEventListener('change', () => {
  // '' must be handled BEFORE any numeric coercion: +'' is 0, which would
  // silently select the first ship (the bug the Opportunities pane has)
  SHIP = shipSel.value === '' ? null : (SHIPS[+shipSel.value] || null);
  updShipInfo();
  if (fromSel.value === 'ship') recompute(); else redraw();
});
fromSel.addEventListener('change', recompute);
toSel.addEventListener('change', () => table.draw());
['rtdock', 'rtdockl', 'rtcruise', 'rthwv'].forEach(
  id => el(id).addEventListener('input', redraw));
el('rtcruise').addEventListener('input', updShipInfo);
el('rthw').addEventListener('change', redraw);
updShipInfo();
recompute();

// self-size inside the dashboard iframe
function post() { parent.postMessage({ x4h: document.body.scrollHeight + 24 }, '*'); }
new ResizeObserver(post).observe(document.body);
window.addEventListener('load', function () { setTimeout(post, 400); });
})();
