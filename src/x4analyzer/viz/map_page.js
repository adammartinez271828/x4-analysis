"use strict";
/* Sector map client renderer. Inlined into the map page by viz/map.py with
 * the payload injected as window.X4MAP (see map.py _payload for the record
 * shapes). Everything is drawn in reference-pixel space (y-down, one unit =
 * one px at the R-tuned 1536x864 density), so all geometry is regular and
 * zooming is a uniform viewBox scale. */
(function () {
  var D = window.X4MAP;
  var C = D.const, SC = D.scene;
  var NS = "http://www.w3.org/2000/svg";
  var R3_4 = Math.sqrt(3) / 4;

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function div(cls, parent) {
    var d = document.createElement("div");
    if (cls) d.className = cls;
    if (parent) parent.appendChild(d);
    return d;
  }

  // plotly's hexagon2 (flat-top): size = point-to-point width
  function hexPoints(cx, cy, size) {
    var n = size / 2, i = size / 4, a = size * R3_4;
    return [[-i, a], [i, a], [n, 0], [i, -a], [-i, -a], [-n, 0]]
      .map(function (p) { return (cx + p[0]) + "," + (cy + p[1]); })
      .join(" ");
  }

  // overlay symbol paths, ported verbatim from plotly.js's symbol defs
  // (all coefficients are relative to r = size/2; y-down like our space)
  function starPath(cx, cy, size) {
    var n = size / 2 * 1.4;
    function p(mx, my) {
      return (cx + mx * n).toFixed(2) + "," + (cy + my * n).toFixed(2);
    }
    return "M" + p(0.225, -0.309) + "L" + p(0.951, -0.309) +
      "L" + p(0.363, 0.118) + "L" + p(0.588, 0.809) + "L" + p(0, 0.382) +
      "L" + p(-0.588, 0.809) + "L" + p(-0.363, 0.118) +
      "L" + p(-0.951, -0.309) + "L" + p(-0.225, -0.309) +
      "L" + p(0, -1) + "Z";
  }
  function starTriDownPath(cx, cy, size) {
    var r = size / 2, n = Math.sqrt(3) * 0.8 * r, i = 0.8 * r,
      a = 1.6 * r, o = (4 * r).toFixed(2);
    var arc = "A" + o + "," + o + " 0 0 1 ";
    function p(x, y) { return (cx + x).toFixed(2) + "," + (cy + y).toFixed(2); }
    return "M" + p(n, -i) + arc + p(-n, -i) + arc + p(0, a) +
      arc + p(n, -i) + "Z";
  }
  function diamondXPath(cx, cy, size) {
    var r = size / 2, n = 1.3 * r, i = 0.65 * r;
    function p(x, y) { return (cx + x).toFixed(2) + "," + (cy + y).toFixed(2); }
    return "M" + p(n, 0) + "L" + p(0, n) + "L" + p(-n, 0) + "L" + p(0, -n) +
      "ZM" + p(-i, -i) + "L" + p(i, i) + "M" + p(-i, i) + "L" + p(i, -i);
  }

  // the plotly_dark colorway the resource traces used to cycle through
  // (offset 1: the gates trace took the first slot)
  var COLORWAY = ["#636efa", "#EF553B", "#00cc96", "#ab63fa", "#FFA15A",
                  "#19d3f3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"];

  var svg = document.getElementById("map");

  // --- viewBox pan/zoom controller. home = the whole scene plus the edge
  // pad ring, so overhanging edge hexes stay visible (the svg clips at the
  // viewBox, which is what keeps zoomed content out of the legend). The
  // svg fills the page, so the viewBox aspect always tracks the element
  // aspect; zoom level 1 = the whole scene fitted into the element. ---
  var home = {x: -SC.pad, y: -SC.pad,
              w: SC.w + 2 * SC.pad, h: SC.h + 2 * SC.pad};
  var view = {x: home.x, y: home.y, w: home.w, h: home.h};
  var MAX_ZOOM = 10;

  function elemAspect() {
    var r = svg.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? r.height / r.width
                                       : home.h / home.w;
  }
  // view width at fit-the-scene (zoom 1) for the current element aspect
  function fitW() { return Math.max(home.w, home.h / elemAspect()); }

  function applyView() {
    var ar = elemAspect(), fw = fitW();
    view.w = Math.min(fw, Math.max(fw / MAX_ZOOM, view.w));
    view.h = view.w * ar;
    // clamp each axis inside the scene; when the view is larger than the
    // scene on an axis (window wider/taller than the map), centre instead
    view.x = view.w >= home.w
      ? home.x + (home.w - view.w) / 2
      : Math.min(home.x + home.w - view.w, Math.max(home.x, view.x));
    view.y = view.h >= home.h
      ? home.y + (home.h - view.h) / 2
      : Math.min(home.y + home.h - view.h, Math.max(home.y, view.y));
    svg.setAttribute("viewBox",
      view.x + " " + view.y + " " + view.w + " " + view.h);
    // labels counter-scale against the true screen px per scene unit:
    // ~8 screen px at overview, growing to at most 13 when zoomed in;
    // suffix labels of multi-sector clusters only appear once zoomed in
    var sPx = svg.getBoundingClientRect().width / view.w || 1;
    layers.labels.style.fontSize =
      Math.min(13 / sPx, Math.max(8, 7.5 / sPx)).toFixed(2) + "px";
    layers.labels.classList.toggle("zoomed-out", sPx < 1.6);
    // stroke weights stop growing beyond 1.3x their base screen weight
    svg.style.setProperty("--sw", Math.min(1, 1.3 / sPx).toFixed(3));
    saveState();
  }

  function sceneXY(ev) {
    var r = svg.getBoundingClientRect();
    return {x: view.x + (ev.clientX - r.left) / r.width * view.w,
            y: view.y + (ev.clientY - r.top) / r.height * view.h};
  }

  // zoom by factor f (>1 = out) keeping scene point (px,py) under the cursor
  function zoomAt(px, py, f) {
    var fw = fitW();
    var w2 = Math.min(fw, Math.max(fw / MAX_ZOOM, view.w * f));
    f = w2 / view.w;
    view.x = px - (px - view.x) * f;
    view.y = py - (py - view.y) * f;
    view.w = w2;
    view.h = view.h * f;
    applyView();
  }

  function resetView() {
    var fw = fitW();
    view.w = fw;
    view.h = fw * elemAspect();
    view.x = home.x + (home.w - view.w) / 2;
    view.y = home.y + (home.h - view.h) / 2;
    applyView();
  }

  // --- scene graph, in stacking order (matches the old plotly trace order:
  // gates under resources under outlines under overlays under faction hexes
  // under labels; transparent hover targets on top) ---
  var layers = {};
  ["gates", "resources", "clusters", "contested",
   "police", "pirates", "player", "factions", "highlight", "labels",
   "hover"]
    .forEach(function (n) { layers[n] = el("g", {id: "ly-" + n}, svg); });

  // gate records: [ia, ib, x1, y1, x2, y2] — the endpoints sit at the
  // gates' approximate in-sector positions, so lines attach there and
  // each endpoint gets a small dot
  D.gates.forEach(function (g) {
    el("line", {x1: g[2], y1: g[3], x2: g[4], y2: g[5]}, layers.gates);
    el("circle", {cx: g[2], cy: g[3], r: 2}, layers.gates);
    el("circle", {cx: g[4], cy: g[5], r: 2}, layers.gates);
  });

  // hover adjacency from the gate links
  var neighbors = D.sectors.map(function () { return []; });
  var gatesByI = D.sectors.map(function () { return []; });
  D.gates.forEach(function (g) {
    neighbors[g[0]].push(g[1]);
    neighbors[g[1]].push(g[0]);
    gatesByI[g[0]].push(g);
    gatesByI[g[1]].push(g);
  });

  // hovering a sector shows its gate links and neighbour hexes (also
  // while the gates layer itself is off)
  function showGateHighlight(i) {
    clearGateHighlight();
    gatesByI[i].forEach(function (g) {
      var n = D.sectors[g[0] === i ? g[1] : g[0]];
      // +2 keeps the ring snug against the hex edge — sub-sector hexes
      // sit only ~2px apart, so a wider ring would lap onto siblings
      el("line", {x1: g[2], y1: g[3], x2: g[4], y2: g[5],
                  "class": "glhl-line"}, layers.highlight);
      el("polygon", {points: hexPoints(n.x, n.y,
                                       (n.big ? C.big : C.small) + 2),
                     "class": "glhl-hex"}, layers.highlight);
    });
  }
  function clearGateHighlight() { layers.highlight.textContent = ""; }

  // cluster grouping boxes: neutral and subtle so the faction colours
  // carry the map
  D.clusters.forEach(function (c) {
    el("polygon", {points: hexPoints(c.x, c.y, C.big + C.border),
                   fill: "none", stroke: "#B0B0B0", "stroke-width": 2,
                   "stroke-opacity": 0.45}, layers.clusters);
  });

  // one hex per sector, the faction colour IS the sector edge (no
  // separate neutral outline ring): bright while the faction is
  // selected, dimmed via .dim (never hidden) while deselected
  var factionG = {};   // faction name -> <g> of its sector hexes
  D.factions.forEach(function (f) {
    factionG[f.name] = el("g", {"data-faction": f.name}, layers.factions);
  });
  D.sectors.forEach(function (s) {
    el("polygon", {points: hexPoints(s.x, s.y, s.big ? C.big : C.small),
                   fill: "none", stroke: s.colour,
                   "stroke-width": C.border}, factionG[s.owner]);
  });

  // --- overlays (all default off, toggled from the legend) ---
  D.sectors.forEach(function (s) {
    if (s.contested !== 1) return;
    el("path", {d: diamondXPath(s.x, s.y, s.big ? C.cbig : C.csmall),
                fill: "#EEEE33", "fill-opacity": C.opacity,
                stroke: "#ffffff", "stroke-width": 1,
                "stroke-opacity": C.opacity}, layers.contested);
  });
  [["police", starPath, "#3333EE"],
   ["pirates", starTriDownPath, "#EE3333"]].forEach(function (row) {
    D[row[0]].forEach(function (r) {
      var s = D.sectors[r.i];
      el("path", {d: row[1](s.x, s.y, r.size),
                  fill: row[2], "fill-opacity": C.opacity,
                  stroke: "#ffffff", "stroke-width": 1,
                  "stroke-opacity": C.opacity}, layers[row[0]]);
    });
  });

  // player assets overlay: sectors holding player stations get a dashed
  // hex ring in the player colour plus a station-count badge
  var playerColour = (D.factions.filter(function (f) {
    return f.name === "Player";
  })[0] || {}).colour || "#00E060";
  D.sectors.forEach(function (s) {
    var n = (D.stations[s.macro] || []).filter(function (st) {
      return st.owner === "Player";
    }).length;
    if (!n) return;
    var sz = s.big ? C.big : C.small;
    el("polygon", {points: hexPoints(s.x, s.y, sz + 8), fill: "none",
                   stroke: playerColour, "stroke-width": 2,
                   "stroke-dasharray": "5,3"}, layers.player);
    var bx = s.x + sz * 0.38, by = s.y - sz * 0.38;
    el("circle", {cx: bx, cy: by, r: 8, fill: "#1e1e1e",
                  stroke: playerColour, "stroke-width": 1.5}, layers.player);
    var t = el("text", {x: bx, y: by, dy: "0.35em", "class": "pbadge",
                        "text-anchor": "middle"}, layers.player);
    t.textContent = n;
  });

  // resource overlay: one hidden group per resource; hex sizes are set by
  // renormalize() (yield normalized to the max over visible factions'
  // sectors — a direct port of the old plotly legend JS)
  var resourceG = {};   // resource id -> {g, polys, yields, colour}
  D.resources.forEach(function (r, ri) {
    var g = el("g", {"data-resource": r.id}, layers.resources);
    g.style.display = "none";
    var polys = D.sectors.map(function (s) {
      return el("polygon", {fill: resColour(ri), "fill-opacity": 0.85,
                            stroke: "#444444", "stroke-width": 1,
                            "stroke-opacity": 0.85}, g);
    });
    resourceG[r.id] = {g: g, polys: polys, yields: r.yields,
                       colour: resColour(ri)};
  });
  function resColour(ri) { return COLORWAY[(ri + 1) % COLORWAY.length]; }

  function renormalize() {
    if (!state.resource) return;
    var res = resourceG[state.resource];
    var maxv = 0;
    res.yields.forEach(function (v, i) {
      if (state.factions[D.sectors[i].owner] && v > maxv) maxv = v;
    });
    res.polys.forEach(function (poly, i) {
      var v = res.yields[i];
      if (v <= 0 || maxv <= 0 || !state.factions[D.sectors[i].owner]) {
        poly.style.display = "none";
        return;
      }
      poly.style.display = "";
      var sz = Math.max(C.res_min, v / maxv * C.res_max);
      var s = D.sectors[i];
      poly.setAttribute("points", hexPoints(s.x, s.y, sz));
    });
  }

  D.labels.forEach(function (lb) {
    // sector names hang from just under their hex's top edge (the text
    // block grows downward); the cluster base name of multi-sector
    // clusters stays centred — the sub-hexes occupy the cluster's top
    // edge, so there is no free top line for it
    var size = lb.kind === "single" ? C.big
      : lb.kind === "suffix" ? C.small : 0;
    var y = size ? lb.y - size * R3_4 + 1.5 : lb.y;
    var t = el("text", {"class": "seclabel k-" + lb.kind, x: lb.x, y: y,
                        "text-anchor": "middle"}, layers.labels);
    var k = lb.lines.length;
    lb.lines.forEach(function (line, j) {
      var ts = el("tspan", {
        x: lb.x,
        // top-anchored: first baseline one cap-height below the edge;
        // centred (base labels): baseline of line j sits at 0.35em minus
        // half the block height
        dy: j > 0 ? "1.1em"
          : size ? "0.95em"
          : (0.35 - (k - 1) * 0.55).toFixed(2) + "em",
      }, t);
      ts.textContent = line;
    });
  });

  // --- tooltip (the payload tip strings are the same HTML the plotly
  // hovertext used) ---
  var tip = document.getElementById("tip");
  function moveTip(ev) {
    var pad = 14;
    var x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + tip.offsetWidth > window.innerWidth - 4)
      x = ev.clientX - tip.offsetWidth - pad;
    if (y + tip.offsetHeight > window.innerHeight - 4)
      y = ev.clientY - tip.offsetHeight - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function hideTip() { tip.style.display = "none"; }

  // transparent hover/hit hexes, one per sector, on top of everything;
  // dimmed sectors stay hoverable (they are still on the map)
  D.sectors.forEach(function (s, si) {
    var p = el("polygon", {points: hexPoints(s.x, s.y,
                                             s.big ? C.big : C.small),
                           fill: "transparent", "data-i": si}, layers.hover);
    p.addEventListener("mouseenter", function (ev) {
      tip.innerHTML = s.tip;
      tip.style.display = "block";
      moveTip(ev);
      showGateHighlight(si);
    });
    p.addEventListener("mousemove", moveTip);
    p.addEventListener("mouseleave", function () {
      hideTip();
      clearGateHighlight();
    });
  });

  // --- legend state + panel ---
  var state = {
    layers: {gates: false, clusters: true, labels: true,
             contested: false, police: false, pirates: false,
             player: false},
    factions: {},
    resource: null,   // id of the single-selected resource overlay
  };
  D.factions.forEach(function (f) { state.factions[f.name] = true; });

  // view-state persistence: toggles and the view survive tab switches and
  // reloads within the session. Ignored when the scene changed (other
  // save / spoiler mode) since coordinates would no longer match.
  var saved = null;
  try { saved = JSON.parse(sessionStorage.getItem("x4map") || "null"); }
  catch (e) { saved = null; }
  if (saved && saved.sw === SC.w && saved.sh === SC.h
      && saved.nsec === D.sectors.length) {
    Object.keys(state.layers).forEach(function (k) {
      if (saved.layers && typeof saved.layers[k] === "boolean")
        state.layers[k] = saved.layers[k];
    });
    D.factions.forEach(function (f) {
      if (saved.factions && typeof saved.factions[f.name] === "boolean")
        state.factions[f.name] = saved.factions[f.name];
    });
  } else {
    saved = null;
  }
  function saveState() {
    try {
      sessionStorage.setItem("x4map", JSON.stringify({
        sw: SC.w, sh: SC.h, nsec: D.sectors.length,
        layers: state.layers, factions: state.factions,
        resource: state.resource,
        cx: view.x + view.w / 2, cy: view.y + view.h / 2,
        z: fitW() / view.w,
      }));
    } catch (e) { /* storage unavailable: persistence is best-effort */ }
  }

  var layerG = {gates: layers.gates, clusters: layers.clusters,
                labels: layers.labels,
                contested: layers.contested, police: layers.police,
                pirates: layers.pirates, player: layers.player};

  function applyLayer(name) {
    layerG[name].style.display = state.layers[name] ? "" : "none";
    saveState();
  }
  function applyFaction(name) {
    // deselected factions dim instead of vanishing, so the map keeps its
    // shape even with No factions selected
    factionG[name].classList.toggle("dim", !state.factions[name]);
    saveState();
  }

  var legend = document.getElementById("legend");

  function lgroup(title) {
    var g = div("lgroup", legend);
    var t = div("ltitle", g);
    t.textContent = title;
    return g;
  }
  function litem(group, labelHtml, swatch, isOn, toggle) {
    var it = div("litem", group);
    var sw = div("sw", it);
    sw.innerHTML = swatch;
    var span = document.createElement("span");
    span.innerHTML = labelHtml;
    it.appendChild(span);
    if (!isOn()) it.classList.add("off");
    it.addEventListener("click", function () {
      toggle();
      it.classList.toggle("off", !isOn());
    });
    return it;
  }
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function hexSwatch(colour) {
    return "<svg width='18' height='14' viewBox='-9 -7 18 14'>" +
      "<polygon points='" + hexPoints(0, 0, 12) + "' fill='none' stroke='" +
      colour + "' stroke-width='2'/></svg>";
  }
  function lineSwatch(colour) {
    return "<svg width='18' height='14'><line x1='1' y1='7' x2='17' y2='7'" +
      " stroke='" + colour + "' stroke-width='2'/></svg>";
  }

  var facItems = {};  // faction name -> legend item element
  var gFac = lgroup("Factions");
  var allBtn = div("litem lbtn", gFac);
  allBtn.textContent = "All factions";
  var noneBtn = div("litem lbtn", gFac);
  noneBtn.textContent = "No factions";
  function setAllFactions(on) {
    D.factions.forEach(function (f) {
      state.factions[f.name] = on;
      applyFaction(f.name);
      facItems[f.name].classList.toggle("off", !on);
    });
    renormalize();
  }
  allBtn.addEventListener("click", function () { setAllFactions(true); });
  noneBtn.addEventListener("click", function () { setAllFactions(false); });
  D.factions.forEach(function (f) {
    facItems[f.name] = litem(gFac, esc(f.name), hexSwatch(f.colour),
      function () { return state.factions[f.name]; },
      function () {
        state.factions[f.name] = !state.factions[f.name];
        applyFaction(f.name);
        renormalize();
      });
  });

  var gBase = lgroup("Base Map");
  [["clusters", "Cluster Outlines", hexSwatch("#B0B0B0")],
   ["labels", "Sector Names",
    "<span style='color:rgba(240,240,96,0.8);font-size:11px;" +
    "font-weight:bold'>Aa</span>"],
   ["gates", "Gates &amp; Accelerators", lineSwatch("rgba(140,170,200,0.8)")],
  ].forEach(function (row) {
    litem(gBase, row[1], row[2],
      function () { return state.layers[row[0]]; },
      function () {
        state.layers[row[0]] = !state.layers[row[0]];
        applyLayer(row[0]);
      });
  });

  function pathSwatch(pathFn, fill, size) {
    return "<svg width='18' height='14' viewBox='-9 -7 18 14'><path d='" +
      pathFn(0, 0, size) + "' fill='" + fill +
      "' stroke='#ffffff' stroke-width='0.8'/></svg>";
  }
  var hoursTxt = " (" + C.hours.toFixed(0) + "h)";
  var gOver = lgroup("Overlays");
  var overlayRows = [["contested", "Contested Sectors",
                      pathSwatch(diamondXPath, "#EEEE33", 9)]];
  if (D.police.length)
    overlayRows.push(["police", "Police Interdictions" + hoursTxt,
                      pathSwatch(starPath, "#3333EE", 10)]);
  if (D.pirates.length)
    overlayRows.push(["pirates", "Pirate Harassments" + hoursTxt,
                      pathSwatch(starTriDownPath, "#EE3333", 9)]);
  if (layers.player.childNodes.length)
    overlayRows.push(["player", "Player Assets",
      "<svg width='18' height='14' viewBox='-9 -7 18 14'><polygon points='" +
      hexPoints(0, 0, 12) + "' fill='none' stroke='" + playerColour +
      "' stroke-width='1.5' stroke-dasharray='3,2'/></svg>"]);
  overlayRows.forEach(function (row) {
    litem(gOver, row[1], row[2],
      function () { return state.layers[row[0]]; },
      function () {
        state.layers[row[0]] = !state.layers[row[0]];
        applyLayer(row[0]);
      });
  });

  // resources are single-select: showing one hides the others; clicking
  // the shown one again clears the overlay (same semantics as before)
  function selectResource(id) {
    state.resource = state.resource === id ? null : id;
    D.resources.forEach(function (r) {
      var sel = state.resource === r.id;
      resourceG[r.id].g.style.display = sel ? "" : "none";
      resItems[r.id].classList.toggle("off", !sel);
    });
    renormalize();
    saveState();
  }
  var resItems = {};
  if (D.resources.length) {
    var gRes = lgroup("Resources");
    D.resources.forEach(function (r) {
      resItems[r.id] = litem(gRes, esc(r.name),
        "<svg width='18' height='14' viewBox='-9 -7 18 14'><polygon points='"
        + hexPoints(0, 0, 11) + "' fill='" + resourceG[r.id].colour +
        "' fill-opacity='0.85'/></svg>",
        function () { return state.resource === r.id; },
        function () { selectResource(r.id); });
    });
  }

  Object.keys(layerG).forEach(applyLayer);
  D.factions.forEach(function (f) { applyFaction(f.name); });

  // --- pan/zoom input wiring ---
  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();   // never scroll the page/dashboard from the map
    hideTip();
    var p = sceneXY(ev);
    zoomAt(p.x, p.y, Math.exp(ev.deltaY * 0.002));
  }, {passive: false});

  var drag = null, dragged = false;
  svg.addEventListener("pointerdown", function (ev) {
    if (ev.button !== 0) return;
    drag = {x: ev.clientX, y: ev.clientY};
    dragged = false;
    svg.setPointerCapture(ev.pointerId);
    svg.classList.add("dragging");
  });
  svg.addEventListener("pointermove", function (ev) {
    if (!drag) return;
    if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3)
      dragged = true;
    if (!dragged) return;
    hideTip();
    var r = svg.getBoundingClientRect();
    view.x -= (ev.clientX - drag.x) * view.w / r.width;
    view.y -= (ev.clientY - drag.y) * view.h / r.height;
    drag = {x: ev.clientX, y: ev.clientY};
    applyView();
  });
  ["pointerup", "pointercancel"].forEach(function (n) {
    svg.addEventListener(n, function () {
      drag = null;
      svg.classList.remove("dragging");
    });
  });
  svg.addEventListener("dblclick", resetView);

  // click (not drag) on a sector opens the detail panel; pointer capture
  // can retarget the click to the svg, so fall back to a point hit-test
  svg.addEventListener("click", function (ev) {
    if (dragged) return;
    var t = ev.target;
    if (!(t && t.dataset && t.dataset.i !== undefined))
      t = document.elementFromPoint(ev.clientX, ev.clientY);
    if (t && t.dataset && t.dataset.i !== undefined)
      openPanel(+t.dataset.i);
  });

  window.addEventListener("keydown", function (ev) {
    if (ev.target && /^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName))
      return;
    var cx = view.x + view.w / 2, cy = view.y + view.h / 2, step = 0.15;
    switch (ev.key) {
      case "+": case "=": zoomAt(cx, cy, 1 / 1.3); break;
      case "-": case "_": zoomAt(cx, cy, 1.3); break;
      case "ArrowLeft": view.x -= view.w * step; applyView(); break;
      case "ArrowRight": view.x += view.w * step; applyView(); break;
      case "ArrowUp": view.y -= view.h * step; applyView(); break;
      case "ArrowDown": view.y += view.h * step; applyView(); break;
      case "Home": case "0": resetView(); break;
      case "Escape": closePanel(); break;
      default: return;
    }
    ev.preventDefault();
  });

  var homeBtn = document.createElement("div");
  homeBtn.id = "x4home";
  homeBtn.title = "Reset view (or double-click / Home)";
  homeBtn.innerHTML = "&#x2302;";
  homeBtn.addEventListener("click", resetView);
  document.body.appendChild(homeBtn);

  // window/iframe resizes (incl. fullscreen) keep the zoom but re-fit the
  // aspect and clamps
  window.addEventListener("resize", applyView);

  // --- search / jump-to-sector ---
  var anim = null, animEnd = null;
  function animateViewTo(cx, cy, w2) {
    var c0 = {x: view.x + view.w / 2, y: view.y + view.h / 2, w: view.w};
    var t0 = performance.now(), dur = 350, done = false;
    cancelAnimationFrame(anim);
    clearTimeout(animEnd);
    function at(u) {
      u = u * (2 - u);   // ease-out
      var w = c0.w + (w2 - c0.w) * u;
      view.w = w;
      view.h = w * elemAspect();
      view.x = c0.x + (cx - c0.x) * u - w / 2;
      view.y = c0.y + (cy - c0.y) * u - view.h / 2;
      applyView();
    }
    function step(t) {
      var u = Math.min(1, (t - t0) / dur);
      at(u);
      if (u < 1) anim = requestAnimationFrame(step);
      else done = true;
    }
    anim = requestAnimationFrame(step);
    // rAF pauses in hidden/background frames — always land on the target
    animEnd = setTimeout(function () {
      if (done) return;
      cancelAnimationFrame(anim);
      at(1);
    }, dur + 80);
  }

  function pulseSector(i) {
    var s = D.sectors[i];
    var p = el("polygon", {
      points: hexPoints(s.x, s.y, (s.big ? C.big : C.small) + 14),
      "class": "pulse",
    }, svg);
    setTimeout(function () { p.remove(); }, 2000);
  }

  // --- sector detail panel. It takes layout space next to the map (the
  // svg shrinks and re-fits) instead of overlaying it, so the rightmost
  // map content is never hidden behind it. ---
  var panel = document.getElementById("panel");
  var panelBody = document.getElementById("panelbody");
  var policeByI = {}, piratesByI = {};
  D.police.forEach(function (r) { policeByI[r.i] = r.count; });
  D.pirates.forEach(function (r) { piratesByI[r.i] = r.count; });

  // track the svg's changing size while the panel's width transition runs
  // (rAF can stall in hidden iframes, so always settle once at the end)
  function reflow() {
    var t0 = performance.now();
    (function step() {
      applyView();
      if (performance.now() - t0 < 300) requestAnimationFrame(step);
    })();
    setTimeout(applyView, 350);
  }

  function openPanel(i) {
    var s = D.sectors[i];
    var h = "<span id='panelclose' title='Close (Esc)'>&#x2715;</span>" +
      "<h3>" + esc(s.name) + "</h3>" +
      "<div class='prow'>" + esc(s.owner) +
      (s.contested === 1 ? " <b>(Contested)</b>" : "") + "</div>";
    if (policeByI[i] !== undefined)
      h += "<div class='prow'>Police interdictions (" +
        C.hours.toFixed(0) + "h): " + policeByI[i] + "</div>";
    if (piratesByI[i] !== undefined)
      h += "<div class='prow'>Pirate harassments (" +
        C.hours.toFixed(0) + "h): " + piratesByI[i] + "</div>";

    var res = D.resources.filter(function (r) { return r.yields[i] > 0; });
    h += "<h4>Resources</h4>";
    h += res.length
      ? res.map(function (r) {
          return "<div class='pstat'>" + esc(r.name) + " <small>" +
            Math.round(r.yields[i]) + "</small></div>";
        }).join("")
      : "<div class='pstat'><small>None</small></div>";

    h += "<h4>Connections</h4>";
    h += neighbors[i].length
      ? neighbors[i].map(function (j) {
          return "<div class='pstat'><span class='plink' data-j='" + j +
            "'>" + esc(D.sectors[j].name) + "</span></div>";
        }).join("")
      : "<div class='pstat'><small>None known</small></div>";

    var sts = D.stations[s.macro] || [];
    h += "<h4>Stations (" + sts.length + ")</h4>";
    h += sts.length
      ? sts.map(function (st) {
          return "<div class='pstat'>" + esc(st.name) +
            (st.code ? " (" + esc(st.code) + ")" : "") + "<br><small>" +
            esc(st.owner) + (st.type ? " &middot; " + esc(st.type) : "") +
            "</small></div>";
        }).join("")
      : "<div class='pstat'><small>None known</small></div>";

    panelBody.innerHTML = h;
    var wasOpen = panel.classList.contains("open");
    panel.classList.add("open");
    if (!wasOpen) reflow();
    document.getElementById("panelclose")
      .addEventListener("click", closePanel);
    panelBody.querySelectorAll(".plink").forEach(function (a) {
      a.addEventListener("click", function () {
        var j = +a.dataset.j;
        var n = D.sectors[j];
        animateViewTo(n.x, n.y, Math.min(view.w, fitW() / 4));
        pulseSector(j);
        openPanel(j);
      });
    });
  }
  function closePanel() {
    if (!panel.classList.contains("open")) return;
    panel.classList.remove("open");
    reflow();
  }

  var searchBox = document.getElementById("search");
  var searchInfo = document.getElementById("searchinfo");
  var matches = [], mi = -1;
  function runSearch() {
    var q = searchBox.value.trim().toLowerCase();
    matches = [];
    mi = -1;
    if (q)
      D.sectors.forEach(function (s, i) {
        if (s.name.toLowerCase().indexOf(q) >= 0) matches.push(i);
      });
    searchBox.classList.toggle("nomatch", !!q && !matches.length);
    searchInfo.textContent = !q ? ""
      : matches.length ? matches.length + " match" +
        (matches.length > 1 ? "es" : "")
      : "no match";
  }
  searchBox.addEventListener("input", runSearch);
  searchBox.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      searchBox.value = "";
      runSearch();
      searchBox.blur();
      return;
    }
    if (ev.key !== "Enter" || !matches.length) return;
    mi = (mi + 1) % matches.length;   // repeated Enter cycles the matches
    var i = matches[mi];
    var s = D.sectors[i];
    animateViewTo(s.x, s.y, fitW() / 4);
    pulseSector(i);
    searchInfo.textContent = s.name +
      (matches.length > 1 ? " (" + (mi + 1) + "/" + matches.length + ")" : "");
  });

  resetView();

  // restore the saved resource selection and view (validated against the
  // current scene above)
  if (saved) {
    if (saved.resource && resourceG[saved.resource]) {
      state.resource = null;
      selectResource(saved.resource);
    }
    if (saved.z >= 1 && saved.z <= MAX_ZOOM
        && saved.cx >= home.x && saved.cx <= home.x + home.w
        && saved.cy >= home.y && saved.cy <= home.y + home.h) {
      view.w = fitW() / saved.z;
      view.h = view.w * elemAspect();
      view.x = saved.cx - view.w / 2;
      view.y = saved.cy - view.h / 2;
      applyView();
    }
  }
})();
