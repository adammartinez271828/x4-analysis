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
  ["gates", "resources", "clusters", "sectors", "contested",
   "police", "pirates", "factions", "highlight", "labels", "hover"]
    .forEach(function (n) { layers[n] = el("g", {id: "ly-" + n}, svg); });

  D.gates.forEach(function (g) {
    var a = D.sectors[g[0]], b = D.sectors[g[1]];
    el("line", {x1: a.x, y1: a.y, x2: b.x, y2: b.y}, layers.gates);
  });

  // hover adjacency from the gate links
  var neighbors = D.sectors.map(function () { return []; });
  D.gates.forEach(function (g) {
    neighbors[g[0]].push(g[1]);
    neighbors[g[1]].push(g[0]);
  });

  // hovering a sector shows its gate links and neighbour hexes (also
  // while the gates layer itself is off)
  function showGateHighlight(i) {
    clearGateHighlight();
    var s = D.sectors[i];
    neighbors[i].forEach(function (j) {
      var n = D.sectors[j];
      el("line", {x1: s.x, y1: s.y, x2: n.x, y2: n.y,
                  "class": "glhl-line"}, layers.highlight);
      el("polygon", {points: hexPoints(n.x, n.y,
                                       (n.big ? C.big : C.small) + 6),
                     "class": "glhl-hex"}, layers.highlight);
    });
  }
  function clearGateHighlight() { layers.highlight.textContent = ""; }

  D.clusters.forEach(function (c) {
    el("polygon", {points: hexPoints(c.x, c.y, C.big + C.border),
                   fill: "none", stroke: "#B0B0B0", "stroke-width": 2,
                   "stroke-opacity": C.opacity}, layers.clusters);
  });

  D.sectors.forEach(function (s) {
    el("polygon", {points: hexPoints(s.x, s.y,
                                     (s.big ? C.big : C.small) + C.border),
                   fill: "none", stroke: "#F0F0F0", "stroke-width": 2,
                   "stroke-opacity": C.opacity}, layers.sectors);
  });

  var factionG = {};   // faction name -> <g> of its sector hexes
  D.factions.forEach(function (f) {
    factionG[f.name] = el("g", {"data-faction": f.name}, layers.factions);
  });
  D.sectors.forEach(function (s) {
    el("polygon", {points: hexPoints(s.x, s.y, s.big ? C.big : C.small),
                   fill: "none", stroke: s.colour, "stroke-width": C.border,
                   "stroke-opacity": C.opacity}, factionG[s.owner]);
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
    var t = el("text", {"class": "seclabel k-" + lb.kind, x: lb.x, y: lb.y,
                        "text-anchor": "middle"}, layers.labels);
    var k = lb.lines.length;
    lb.lines.forEach(function (line, j) {
      // centre the line block on the point: baseline of line j sits at
      // 0.35em (visual centre of one line) minus half the block height
      var ts = el("tspan", {
        x: lb.x,
        dy: j === 0 ? (0.35 - (k - 1) * 0.55).toFixed(2) + "em" : "1.1em",
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
  // they follow their faction's visibility like plotly hover did
  var hoverByFaction = {};
  D.sectors.forEach(function (s, si) {
    var p = el("polygon", {points: hexPoints(s.x, s.y,
                                             s.big ? C.big : C.small),
                           fill: "transparent", "data-i": si}, layers.hover);
    (hoverByFaction[s.owner] = hoverByFaction[s.owner] || []).push(p);
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
    layers: {gates: false, clusters: true, sectors: true, labels: true,
             contested: false, police: false, pirates: false},
    factions: {},
    resource: null,   // id of the single-selected resource overlay
  };
  D.factions.forEach(function (f) { state.factions[f.name] = true; });

  var layerG = {gates: layers.gates, clusters: layers.clusters,
                sectors: layers.sectors, labels: layers.labels,
                contested: layers.contested, police: layers.police,
                pirates: layers.pirates};

  function applyLayer(name) {
    layerG[name].style.display = state.layers[name] ? "" : "none";
  }
  function applyFaction(name) {
    var on = state.factions[name];
    factionG[name].style.display = on ? "" : "none";
    (hoverByFaction[name] || []).forEach(function (p) {
      p.style.display = on ? "" : "none";
    });
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
   ["sectors", "Sector Outlines", hexSwatch("#F0F0F0")],
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

  // --- pan/zoom input wiring ---
  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();   // never scroll the page/dashboard from the map
    hideTip();
    var p = sceneXY(ev);
    zoomAt(p.x, p.y, Math.exp(ev.deltaY * 0.002));
  }, {passive: false});

  var drag = null;
  svg.addEventListener("pointerdown", function (ev) {
    if (ev.button !== 0) return;
    drag = {x: ev.clientX, y: ev.clientY};
    svg.setPointerCapture(ev.pointerId);
    svg.classList.add("dragging");
  });
  svg.addEventListener("pointermove", function (ev) {
    if (!drag) return;
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
})();
