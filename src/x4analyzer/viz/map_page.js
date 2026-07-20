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

  var svg = document.getElementById("map");

  // --- viewBox pan/zoom controller. home = the whole scene plus the edge
  // pad ring, so overhanging edge hexes stay visible (the svg clips at the
  // viewBox, which is what keeps zoomed content out of the legend);
  // zoom level 1 = home. ---
  var home = {x: -SC.pad, y: -SC.pad,
              w: SC.w + 2 * SC.pad, h: SC.h + 2 * SC.pad};
  var view = {x: home.x, y: home.y, w: home.w, h: home.h};
  var MAX_ZOOM = 10;

  function zoomLevel() { return home.w / view.w; }

  function applyView() {
    // keep the view inside the scene; at zoom 1 this pins it exactly
    view.w = Math.min(home.w, Math.max(home.w / MAX_ZOOM, view.w));
    view.h = view.w * home.h / home.w;
    view.x = Math.min(home.x + home.w - view.w, Math.max(home.x, view.x));
    view.y = Math.min(home.y + home.h - view.h, Math.max(home.y, view.y));
    svg.setAttribute("viewBox",
      view.x + " " + view.y + " " + view.w + " " + view.h);
    var z = zoomLevel();
    // labels counter-scale (8px at home, capped at 13 screen px when
    // zoomed in) and the per-sector suffix labels of multi-sector
    // clusters only appear once zoomed in enough to separate them
    layers.labels.style.fontSize = Math.min(8, 13 / z).toFixed(2) + "px";
    layers.labels.classList.toggle("zoomed-out", z < 1.6);
  }

  function sceneXY(ev) {
    var r = svg.getBoundingClientRect();
    return {x: view.x + (ev.clientX - r.left) / r.width * view.w,
            y: view.y + (ev.clientY - r.top) / r.height * view.h};
  }

  // zoom by factor f (>1 = out) keeping scene point (px,py) under the cursor
  function zoomAt(px, py, f) {
    var w2 = Math.min(home.w, Math.max(home.w / MAX_ZOOM, view.w * f));
    f = w2 / view.w;
    view.x = px - (px - view.x) * f;
    view.y = py - (py - view.y) * f;
    view.w = w2;
    view.h = view.h * f;
    applyView();
  }

  function resetView() {
    view = {x: home.x, y: home.y, w: home.w, h: home.h};
    applyView();
  }

  // --- scene graph, in stacking order (matches the old plotly trace order:
  // gates under resources under outlines under overlays under faction hexes
  // under labels; transparent hover targets on top) ---
  var layers = {};
  ["gates", "resources", "clusters", "sectors", "contested",
   "police", "pirates", "factions", "labels", "hover"]
    .forEach(function (n) { layers[n] = el("g", {id: "ly-" + n}, svg); });

  D.gates.forEach(function (g) {
    el("line", {x1: g[0], y1: g[1], x2: g[2], y2: g[3]}, layers.gates);
  });

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
  D.sectors.forEach(function (s) {
    var p = el("polygon", {points: hexPoints(s.x, s.y,
                                             s.big ? C.big : C.small),
                           fill: "transparent"}, layers.hover);
    (hoverByFaction[s.owner] = hoverByFaction[s.owner] || []).push(p);
    p.addEventListener("mouseenter", function (ev) {
      tip.innerHTML = s.tip;
      tip.style.display = "block";
      moveTip(ev);
    });
    p.addEventListener("mousemove", moveTip);
    p.addEventListener("mouseleave", hideTip);
  });

  // --- legend state + panel ---
  var state = {
    layers: {gates: false, clusters: true, sectors: true, labels: true},
    factions: {},
  };
  D.factions.forEach(function (f) { state.factions[f.name] = true; });

  var layerG = {gates: layers.gates, clusters: layers.clusters,
                sectors: layers.sectors, labels: layers.labels};

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
  }
  allBtn.addEventListener("click", function () { setAllFactions(true); });
  noneBtn.addEventListener("click", function () { setAllFactions(false); });
  D.factions.forEach(function (f) {
    facItems[f.name] = litem(gFac, esc(f.name), hexSwatch(f.colour),
      function () { return state.factions[f.name]; },
      function () {
        state.factions[f.name] = !state.factions[f.name];
        applyFaction(f.name);
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

  applyView();
})();
