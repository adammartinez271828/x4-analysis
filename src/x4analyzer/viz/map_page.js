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
    // the zoom-state class lives on the svg root: labels AND the
    // facility overlay modes key off it
    svg.classList.toggle("zoomed-out", sPx < 1.6);
    // stroke weights stop growing beyond 1.3x their base screen weight
    svg.style.setProperty("--sw", Math.min(1, 1.3 / sPx).toFixed(3));
    applyFacTransforms(sPx);
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
  ["gates", "shighways", "highways", "resources", "clusters", "contested",
   "police", "pirates", "player", "factions", "highlight", "labels",
   "hover"]
    .forEach(function (n) { layers[n] = el("g", {id: "ly-" + n}, svg); });
  // vault overlay markers also sit above the hover layer (hoverable at
  // every zoom level — spotting unopened vaults galaxy-wide is their
  // point); one group per toggle
  layers.vaults = el("g", {id: "ly-vaults"}, svg);
  layers.erlking = el("g", {id: "ly-erlking"}, svg);
  // player station markers sit above the hover layer so they can take
  // pointer events for their tooltips (zoomed-in only: the zoomed-out
  // CSS hides them — the dashed ring + count badge covers that mode);
  // facilities come after so their icons stay on top where both overlap
  layers.playerStations = el("g", {id: "ly-plystations"}, svg);
  // facilities sit above the hover layer so their icons can take
  // pointer events for their own tooltips (zoomed-in only, via CSS)
  layers.facilities = el("g", {id: "ly-facilities"}, svg);
  layers.facClusters = el("g", {id: "fac-clusters"}, layers.facilities);
  layers.facStations = el("g", {id: "fac-stations"}, layers.facilities);

  // facility icon glyphs, drawn in a ~10x10 box around the origin with a
  // white backing disc so they pop against the dark map; glyph colours
  // are darkened to read on white
  var defs = el("defs", {}, svg);
  function iconDef(id, draw) {
    var g = el("g", {id: "ic-" + id}, defs);
    el("circle", {r: 5, fill: "rgba(245,245,245,0.95)",
                  stroke: "#333", "stroke-width": 0.5}, g);
    draw(g);
  }
  iconDef("shipyard", function (g) {   // single large ship silhouette
    el("path", {d: "M0,-3.4 L3.5,2.7 L0,1.3 L-3.5,2.7 Z",
                fill: "#1D5FCC"}, g);
  });
  iconDef("wharf", function (g) {      // pair of small craft
    el("path", {d: "M-1.9,-2.4 L-0.3,1.1 L-1.9,0.4 L-3.5,1.1 Z",
                fill: "#1E8F4E"}, g);
    el("path", {d: "M1.9,-0.4 L3.5,3.1 L1.9,2.4 L0.3,3.1 Z",
                fill: "#1E8F4E"}, g);
  });
  iconDef("equipdock", function (g) {  // hex nut
    el("polygon", {points: hexPoints(0, 0, 6.4), fill: "#7A3FD1"}, g);
    el("circle", {r: 1.3, fill: "#F5F5F5"}, g);
  });
  iconDef("trading", function (g) {    // stacked crates
    el("rect", {x: -2.7, y: 0.1, width: 2.4, height: 2.4,
                fill: "#C77800"}, g);
    el("rect", {x: 0.3, y: 0.1, width: 2.4, height: 2.4,
                fill: "#C77800"}, g);
    el("rect", {x: -1.2, y: -2.6, width: 2.4, height: 2.4,
                fill: "#C77800"}, g);
  });
  iconDef("hq", function (g) {         // flag
    el("line", {x1: -1.8, y1: -3.2, x2: -1.8, y2: 3.2,
                stroke: "#333", "stroke-width": 0.7}, g);
    el("path", {d: "M-1.4,-3.2 L3.2,-1.9 L-1.4,-0.6 Z",
                fill: "#D62828"}, g);
  });
  iconDef("khaak", function (g) {      // crystal spike cluster
    el("path", {d: "M0,-3.7 L0.9,-0.9 L3.7,0 L0.9,0.9 L0,3.7 " +
                   "L-0.9,0.9 L-3.7,0 L-0.9,-0.9 Z",
                fill: "#B012B0"}, g);
  });

  // gate records: [ia, ib, x1, y1, x2, y2] — the endpoints sit at the
  // gates' approximate in-sector positions, so lines attach there and
  // each endpoint gets a small dot. Links between sectors of one
  // cluster are superhighways (accelerators) and draw in their own
  // toggleable layer; only jump gates ever cross clusters
  D.gates.forEach(function (g) {
    var sh = D.sectors[g[0]].cluster === D.sectors[g[1]].cluster;
    var ly = sh ? layers.shighways : layers.gates;
    el("line", {x1: g[2], y1: g[3], x2: g[4], y2: g[5]}, ly);
    el("circle", {cx: g[2], cy: g[3], r: 2}, ly);
    el("circle", {cx: g[4], cy: g[5], r: 2}, ly);
  });

  // local (ring) highway segments: [si, x1, y1, x2, y2] inside their
  // sector hex — the 6-14 km/s tracks S/M ships ride
  (D.hws || []).forEach(function (h) {
    el("line", {x1: h[1], y1: h[2], x2: h[3], y2: h[4]}, layers.highways);
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
  // hex ring in the player colour plus a station-count badge; zoomed in,
  // each station also gets a diamond marker at its in-hex position with
  // a name/code tooltip (markers live in the top playerStations group so
  // they are hoverable through the hit hexes)
  var playerColour = (D.factions.filter(function (f) {
    return f.name === "Player";
  })[0] || {}).colour || "#00E060";
  var ptMarkers = []; // {el, x, y} point markers (player stations
  // and vaults), counter-scaled with zoom together
  D.sectors.forEach(function (s) {
    var mine = (D.stations[s.macro] || []).filter(function (st) {
      return st.owner === "Player";
    });
    if (!mine.length) return;
    var sz = s.big ? C.big : C.small;
    el("polygon", {points: hexPoints(s.x, s.y, sz + 8), fill: "none",
                   stroke: playerColour, "stroke-width": 2,
                   "stroke-dasharray": "5,3"}, layers.player);
    var bx = s.x + sz * 0.38, by = s.y - sz * 0.38;
    el("circle", {cx: bx, cy: by, r: 8, fill: "#1e1e1e",
                  stroke: playerColour, "stroke-width": 1.5}, layers.player);
    var t = el("text", {x: bx, y: by, dy: "0.35em", "class": "pbadge",
                        "text-anchor": "middle"}, layers.player);
    t.textContent = mine.length;
    mine.forEach(function (stn) {
      var g = el("g", {}, layers.playerStations);
      el("path", {d: "M0,-3.2 L3.2,0 L0,3.2 L-3.2,0 Z",
                  fill: playerColour, stroke: "#1e1e1e",
                  "stroke-width": 0.8}, g);
      g.addEventListener("mouseenter", function (ev) {
        tip.innerHTML = "<b>" + esc(stn.name || stn.type || "Station") +
          (stn.code ? " (" + esc(stn.code) + ")" : "") + "</b>" +
          (stn.type ? "<br>" + esc(stn.type) : "");
        tip.style.display = "block";
        moveTip(ev);
      });
      g.addEventListener("mousemove", moveTip);
      g.addEventListener("mouseleave", hideTip);
      ptMarkers.push({el: g, x: stn.x, y: stn.y});
    });
  });

  // data vault overlays: solid glyph = unopened, hollow dimmed = opened.
  // Regular vaults are cyan squares, Erlking vaults gold stars; a
  // transparent hit disc keeps hollow glyphs hoverable
  var VAULT_STYLE = {
    vault: {colour: "#19d3f3", layer: "vaults", title: "Data Vault"},
    erlking: {colour: "#FFD24D", layer: "erlking", title: "Erlking Data Vault"},
  };
  function vaultGlyph(g, kind, open) {
    var st = VAULT_STYLE[kind];
    var attrs = open
      ? {fill: "none", stroke: st.colour, "stroke-width": 1, opacity: 0.55}
      : {fill: st.colour, stroke: "#1e1e1e", "stroke-width": 0.8};
    if (kind === "erlking") attrs.d = starPath(0, 0, 5.2);
    else attrs.d = "M-2.3,-2.3 L2.3,-2.3 L2.3,2.3 L-2.3,2.3 Z";
    el("path", attrs, g);
  }
  D.vaults.forEach(function (v) {
    var st = VAULT_STYLE[v.kind];
    var g = el("g", {}, layers[st.layer]);
    el("circle", {r: 4.5, fill: "transparent"}, g);
    vaultGlyph(g, v.kind, v.open);
    g.addEventListener("mouseenter", function (ev) {
      var h = "<b>" + st.title +
        (v.code ? " (" + esc(v.code) + ")" : "") + "</b><br>" +
        (v.open ? (v.loot ? "Opened &mdash; loot still inside" : "Opened")
                : "Unopened");
      if (v.bp) h += "<br>Blueprint inside: " + esc(v.bp);
      else if (v.kind === "erlking" && v.open)
        h += "<br>Blueprint collected";
      tip.innerHTML = h;
      tip.style.display = "block";
      moveTip(ev);
    });
    g.addEventListener("mousemove", moveTip);
    g.addEventListener("mouseleave", hideTip);
    ptMarkers.push({el: g, x: v.x, y: v.y});
  });

  // resource overlay: one hidden group per resource; hex sizes are set by
  // renormalize() (yield normalized to the max over visible factions'
  // sectors — a direct port of the old plotly legend JS)
  var resourceG = {};   // resource id -> {g, polys, yields, colour}
  var resColourIdx = 0;
  D.resources.forEach(function (r) {
    // sunlight gets a fixed sun-yellow; the save resources keep their
    // established colorway positions
    var colour = r.id === "sunlight" ? "#FFD24D"
      : COLORWAY[(++resColourIdx) % COLORWAY.length];
    var g = el("g", {"data-resource": r.id}, layers.resources);
    g.style.display = "none";
    var polys = D.sectors.map(function (s) {
      return el("polygon", {fill: colour, "fill-opacity": 0.85,
                            stroke: "#444444", "stroke-width": 1,
                            "stroke-opacity": 0.85}, g);
    });
    resourceG[r.id] = {g: g, polys: polys, yields: r.yields,
                       colour: colour};
  });

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

  function labelText(cls, x, y, lines, firstDy) {
    var t = el("text", {"class": cls, x: x, y: y,
                        "text-anchor": "middle"}, layers.labels);
    lines.forEach(function (line, j) {
      var ts = el("tspan", {x: x, dy: j > 0 ? "1.1em" : firstDy}, t);
      ts.textContent = line;
    });
  }
  D.labels.forEach(function (lb) {
    // every name hangs from just under its hex's top edge (the text
    // block grows downward): single sectors and sub-sector suffixes
    // under their own hex, the cluster base name under the cluster hex.
    // Base and suffix labels are never visible together (CSS swaps them
    // at the zoomed-out threshold), so they cannot collide.
    var size = lb.kind === "base" ? C.big + C.border
      : lb.big ? C.big : C.small;
    labelText("seclabel k-" + lb.kind, lb.x,
              lb.y - size * R3_4 + 1.5, lb.lines, "0.95em");
    if (lb.kind !== "base") return;
    // zoomed-in companion: the cluster name floats above the hex's top
    // line (the block ends just above it), or below the bottom line when
    // another sector hex encroaches on the strip above (lb.flip)
    var hh = size * R3_4;
    if (lb.flip) {
      labelText("seclabel k-basein", lb.x, lb.y + hh + 1.5,
                lb.lines, "0.95em");
    } else {
      labelText("seclabel k-basein", lb.x, lb.y - hh - 1.5, lb.lines,
                (-((lb.lines.length - 1) * 1.1 + 0.25)).toFixed(2) + "em");
    }
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

  // --- facility overlays: per-cluster icon rows while zoomed out,
  // per-station icons at their in-hex positions once zoomed in (mode
  // switching is pure CSS off the svg's zoomed-out class) ---
  var FAC_KINDS = [["hq", "Faction HQs"], ["shipyard", "Shipyards"],
                   ["wharf", "Wharfs"], ["equipdock", "Equipment Docks"],
                   ["trading", "Trading Stations"],
                   ["khaak", "Kha'ak Stations"]];
  var clusterPos = {};
  D.clusters.forEach(function (c) { clusterPos[c.macro] = c; });

  // per-cluster facility kinds with the owners contributing each kind
  // (derived from the stations; drives the low-zoom rows and dimming)
  var FAC_ORDER = ["hq", "shipyard", "wharf", "equipdock", "trading",
                   "khaak"];
  var secByMacro = {};
  D.sectors.forEach(function (s) { secByMacro[s.macro] = s; });
  var clusterFacs = {};   // cluster macro -> kind -> [owner names]
  Object.keys(D.stations).forEach(function (m) {
    var sec = secByMacro[m];
    if (!sec) return;
    D.stations[m].forEach(function (stn) {
      var kinds = [];
      if (stn.fac) kinds.push(stn.fac);
      if (stn.hq) kinds.push("hq");
      kinds.forEach(function (k) {
        var e = clusterFacs[sec.cluster] = clusterFacs[sec.cluster] || {};
        (e[k] = e[k] || []).push(stn.owner);
      });
    });
  });

  var facRows = [];       // {el, x, y} zoomed-out cluster rows
  var facRowIcons = [];   // {el, kind, owners} for dimming
  function buildClusterRows() {
    layers.facClusters.textContent = "";
    facRows = [];
    facRowIcons = [];
    Object.keys(clusterFacs).forEach(function (cl) {
      var c = clusterPos[cl];
      var kinds = FAC_ORDER.filter(function (k) {
        return clusterFacs[cl][k] && state.layers["fac_" + k];
      });
      if (!c || !kinds.length) return;
      var g = el("g", {}, layers.facClusters);
      kinds.forEach(function (k, j) {
        var u = el("use", {href: "#ic-" + k, "class": "fk-" + k,
                           x: (j - (kinds.length - 1) / 2) * 11, y: 0}, g);
        facRowIcons.push({el: u, kind: k, owners: clusterFacs[cl][k]});
      });
      // just inside the cluster hex's bottom edge
      facRows.push({el: g, x: c.x, y: c.y + (C.big + C.border) * R3_4 - 6});
    });
    updateFacDim();
    applyFacTransforms(svg.getBoundingClientRect().width / view.w || 1);
  }

  // non-Kha'ak facility icons dim with their owning faction: a station
  // icon when its owner is deselected, a cluster-row icon when EVERY
  // faction contributing that kind is deselected. Owners without a
  // legend entry (Kha'ak owns no sectors) never dim.
  function ownerOff(o) { return state.factions[o] === false; }
  function updateFacDim() {
    facRowIcons.forEach(function (r) {
      r.el.classList.toggle("fdim",
        r.kind !== "khaak" && r.owners.every(ownerOff));
    });
    facSt.forEach(function (r) {
      r.el.classList.toggle("fdim",
        r.kind !== "khaak" && ownerOff(r.owner));
    });
  }

  var facSt = [];     // {el, x, y} zoomed-in per-station icons
  Object.keys(D.stations).forEach(function (m) {
    D.stations[m].forEach(function (stn) {
      if (!stn.fac && !stn.hq) return;
      var g = el("g", {}, layers.facStations);
      if (stn.fac)
        el("use", {href: "#ic-" + stn.fac, "class": "fk-" + stn.fac}, g);
      if (stn.hq)
        el("use", {href: "#ic-hq", "class": "fk-hq",
                   x: stn.fac ? 7 : 0, y: stn.fac ? -6 : 0}, g);
      g.addEventListener("mouseenter", function (ev) {
        tip.innerHTML = "<b>" + esc(stn.name || stn.type || "Station") +
          (stn.code ? " (" + esc(stn.code) + ")" : "") + "</b><br>" +
          esc(stn.owner) + (stn.type ? " &middot; " + esc(stn.type) : "") +
          (stn.hq ? "<br>Faction headquarters" : "");
        tip.style.display = "block";
        moveTip(ev);
      });
      g.addEventListener("mousemove", moveTip);
      g.addEventListener("mouseleave", hideTip);
      facSt.push({el: g, x: stn.x, y: stn.y, owner: stn.owner,
                  kind: stn.fac || "hq"});
    });
  });

  // icons counter-scale with zoom: cluster rows grow to a ~13 screen px
  // cap while zoomed out; station icons hold ~16 screen px zoomed in
  function applyFacTransforms(sPx) {
    var kLow = Math.min(0.9, 1.3 / sPx).toFixed(3);
    facRows.forEach(function (r) {
      r.el.setAttribute("transform",
        "translate(" + r.x + "," + r.y + ") scale(" + kLow + ")");
    });
    var kHi = Math.min(0.8, 1.6 / sPx).toFixed(3);
    facSt.forEach(function (r) {
      r.el.setAttribute("transform",
        "translate(" + r.x + "," + r.y + ") scale(" + kHi + ")");
    });
    // point markers (player stations, vaults) hold ~5 screen px once
    // past the zoom threshold
    var kPly = Math.min(1, 1.7 / sPx).toFixed(3);
    ptMarkers.forEach(function (r) {
      r.el.setAttribute("transform",
        "translate(" + r.x + "," + r.y + ") scale(" + kPly + ")");
    });
  }

  // --- legend state + panel ---
  var state = {
    layers: {gates: false, shighways: false, highways: false,
             clusters: true, labels: true,
             contested: false, police: false, pirates: false,
             player: false, vaults: false, erlking: false,
             fac_hq: true, fac_shipyard: true, fac_wharf: true,
             fac_equipdock: true, fac_trading: true, fac_khaak: true},
    factions: {},
    resource: null,   // id of the single-selected resource overlay
    collapsed: {},    // legend group title -> collapsed
    panelSec: {},     // detail panel section id -> collapsed
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
    if (saved.collapsed)
      Object.keys(saved.collapsed).forEach(function (k) {
        if (typeof saved.collapsed[k] === "boolean")
          state.collapsed[k] = saved.collapsed[k];
      });
    if (saved.panelSec)
      Object.keys(saved.panelSec).forEach(function (k) {
        if (typeof saved.panelSec[k] === "boolean")
          state.panelSec[k] = saved.panelSec[k];
      });
  } else {
    saved = null;
  }
  function saveState() {
    try {
      sessionStorage.setItem("x4map", JSON.stringify({
        sw: SC.w, sh: SC.h, nsec: D.sectors.length,
        layers: state.layers, factions: state.factions,
        resource: state.resource, collapsed: state.collapsed,
        panelSec: state.panelSec,
        cx: view.x + view.w / 2, cy: view.y + view.h / 2,
        z: fitW() / view.w,
      }));
    } catch (e) { /* storage unavailable: persistence is best-effort */ }
  }

  var layerG = {gates: layers.gates, shighways: layers.shighways,
                highways: layers.highways,
                clusters: layers.clusters, labels: layers.labels,
                contested: layers.contested, police: layers.police,
                pirates: layers.pirates, player: layers.player,
                vaults: layers.vaults, erlking: layers.erlking};

  function applyLayer(name) {
    var on = state.layers[name] ? "" : "none";
    layerG[name].style.display = on;
    // the station markers live outside layers.player (they must sit
    // above the hover hexes) but toggle with it
    if (name === "player") layers.playerStations.style.display = on;
    saveState();
  }
  function applyFaction(name) {
    // deselected factions dim instead of vanishing, so the map keeps its
    // shape even with No factions selected
    factionG[name].classList.toggle("dim", !state.factions[name]);
    updateFacDim();
    saveState();
  }

  var legend = document.getElementById("legend");

  function lgroup(title) {
    var g = div("lgroup", legend);
    var t = div("ltitle", g);
    var caret = document.createElement("span");
    caret.className = "lcaret";
    t.appendChild(caret);
    t.appendChild(document.createTextNode(title));
    var body = div("lbody", g);
    function apply() {
      var off = !!state.collapsed[title];
      g.classList.toggle("collapsed", off);
      caret.textContent = off ? "▸" : "▾";
    }
    t.addEventListener("click", function () {
      state.collapsed[title] = !state.collapsed[title];
      apply();
      saveState();
    });
    apply();
    return body;   // legend items append into the collapsible body
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

  function dashSwatch(colour) {
    return "<svg width='18' height='14'><line x1='1' y1='7' x2='17' y2='7'" +
      " stroke='" + colour + "' stroke-width='2'" +
      " stroke-dasharray='3,2'/></svg>";
  }
  var gBase = lgroup("Base Map");
  [["clusters", "Cluster Outlines", hexSwatch("#B0B0B0")],
   ["labels", "Sector Names",
    "<span style='color:rgba(240,240,96,0.8);font-size:11px;" +
    "font-weight:bold'>Aa</span>"],
   ["gates", "Gates", lineSwatch("rgba(140,170,200,0.8)")],
   ["shighways", "Superhighways", dashSwatch("rgba(110,220,190,0.85)")],
   ["highways", "Highways", lineSwatch("rgba(232,184,78,0.85)")],
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
  // vault rows carry an opened/unopened progress count in the label
  function vaultCount(kind) {
    var all = D.vaults.filter(function (v) { return v.kind === kind; });
    var open = all.filter(function (v) { return v.open; }).length;
    return {n: all.length, open: open};
  }
  var vc = vaultCount("vault"), ec = vaultCount("erlking");
  if (vc.n)
    overlayRows.push(["vaults",
      "Data Vaults (" + vc.open + "/" + vc.n + " opened)",
      "<svg width='18' height='14' viewBox='-9 -7 18 14'>" +
      "<rect x='-4' y='-4' width='8' height='8' fill='" +
      VAULT_STYLE.vault.colour + "'/></svg>"]);
  if (ec.n)
    overlayRows.push(["erlking",
      "Erlking Vaults (" + ec.open + "/" + ec.n + " opened)",
      pathSwatch(starPath, VAULT_STYLE.erlking.colour, 9)]);
  overlayRows.forEach(function (row) {
    litem(gOver, row[1], row[2],
      function () { return state.layers[row[0]]; },
      function () {
        state.layers[row[0]] = !state.layers[row[0]];
        applyLayer(row[0]);
      });
  });

  function applyFacKind(k) {
    layers.facilities.classList.toggle("off-" + k,
                                       !state.layers["fac_" + k]);
    buildClusterRows();
    saveState();
  }
  var gFacil = lgroup("Facilities");
  FAC_KINDS.forEach(function (row) {
    var k = row[0];
    litem(gFacil, row[1],
      "<svg width='18' height='14' viewBox='-6.5 -6.5 13 13'>" +
      "<use href='#ic-" + k + "'/></svg>",
      function () { return state.layers["fac_" + k]; },
      function () {
        state.layers["fac_" + k] = !state.layers["fac_" + k];
        applyFacKind(k);
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
  FAC_KINDS.forEach(function (row) {
    layers.facilities.classList.toggle("off-" + row[0],
                                       !state.layers["fac_" + row[0]]);
  });
  buildClusterRows();

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

  // mini facility icon for HTML contexts (panel sublines); references
  // the shared svg defs
  function facBadge(k) {
    return "<svg width='11' height='11' viewBox='-6.5 -6.5 13 13' " +
      "style='vertical-align:-2px'><use href='#ic-" + k + "'/></svg>";
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

    // collapsible sections, default open, collapse state remembered in
    // the shared view state (same caret pattern as the legend groups)
    function sec(id, title, inner) {
      var off = !!state.panelSec[id];
      return "<div class='psec" + (off ? " collapsed" : "") +
        "' data-sec='" + id + "'><h4><span class='lcaret'>" +
        (off ? "▸" : "▾") + "</span>" + title + "</h4>" +
        "<div class='psbody'>" + inner + "</div></div>";
    }

    var resInner = D.resources.length
      ? D.resources.map(function (r) {
          var v = Math.round(r.yields[i]);
          return "<div class='pstat'>" + esc(r.name) + " <small>" +
            (r.id === "sunlight" ? v + "%" : v) + "</small></div>";
        }).join("")
      : "<div class='pstat'><small>None</small></div>";
    h += sec("resources", "Resources", resInner);

    var connInner = neighbors[i].length
      ? neighbors[i].slice().sort(function (a, b) {
          return D.sectors[a].name.localeCompare(D.sectors[b].name);
        }).map(function (j) {
          return "<div class='pstat'><span class='plink' data-j='" + j +
            "'>" + esc(D.sectors[j].name) + "</span></div>";
        }).join("")
      : "<div class='pstat'><small>None known</small></div>";
    h += sec("connections", "Connections", connInner);

    var sts = D.stations[s.macro] || [];
    var stInner = "";
    if (sts.length) {
      // grouped by owning faction (the payload is sorted by owner)
      var lastOwner = null;
      sts.forEach(function (st) {
        if (st.owner !== lastOwner) {
          stInner += "<div class='pfac'>" + esc(st.owner) + "</div>";
          lastOwner = st.owner;
        }
        var nm = st.name || st.type || "Station";
        stInner += "<div class='pstat pind'>" + esc(nm) +
          (st.code ? " <small>(" + esc(st.code) + ")</small>" : "");
        if (st.name && st.type)
          stInner += "<br><small>" + esc(st.type) + "</small>";
        var fl = {shipyard: "Shipyard", wharf: "Wharf",
                  equipdock: "Equipment Dock",
                  trading: "Trading Station"}[st.fac];
        if (fl)
          stInner += "<br><small>" + facBadge(st.fac) + " " + fl +
            "</small>";
        if (st.hq)
          stInner += "<br><small>" + facBadge("hq") +
            " Faction headquarters</small>";
        stInner += "</div>";
      });
    } else {
      stInner = "<div class='pstat'><small>None known</small></div>";
    }
    h += sec("stations", "Stations (" + sts.length + ")", stInner);

    panelBody.innerHTML = h;
    panelBody.querySelectorAll(".psec > h4").forEach(function (hd) {
      hd.addEventListener("click", function () {
        var p = hd.parentElement, id = p.dataset.sec;
        state.panelSec[id] = !state.panelSec[id];
        p.classList.toggle("collapsed", state.panelSec[id]);
        hd.querySelector(".lcaret").textContent =
          state.panelSec[id] ? "▸" : "▾";
        saveState();
      });
    });
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
