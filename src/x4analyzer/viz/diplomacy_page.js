/* Diplomacy page renderer. Reads window.X4DIPLO (see viz/diplomacy.py) and
 * renders either the player-standings table (view "standings") or the
 * faction x faction relations heatmap (view "relations"). Self-sizes to its
 * lazy iframe via postMessage({x4h}). */
(function () {
  "use strict";
  var D = window.X4DIPLO;
  var content = document.getElementById("content");
  var tip = document.getElementById("tip");

  function el(tag, attrs, parent) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs) if (attrs.hasOwnProperty(k))
      e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function chip(colour) {
    return "<span class='chip' style='background:" + esc(colour) + "'></span>";
  }

  // -- shared standing maths (mirrors diplomacy.py _uivalue / _rank) --------
  function uiv(r) {
    var a = Math.abs(r);
    if (a <= 1e-12) return 0;
    var v = a <= 0.0032 ? r / 0.00064
                        : Math.sign(r) * 10 * Math.log10(a * 1000);
    return Math.max(-30, Math.min(30, v));
  }
  function rank(r) {
    if (r >= 0.5) return "Ally";
    if (r >= 0.1) return "Friend";
    if (r >= 0.01) return "Friendly";
    if (r > -0.01) return "Neutral";
    if (r <= -0.999) return "War";
    if (r <= -0.32) return "Hostile";
    return "Enemy";
  }
  var RANK_COL = {
    Ally: "#39c46e", Friend: "#6fce8a", Friendly: "#9fc8ac",
    Neutral: "#8a8a8a", Enemy: "#e08a4a", Hostile: "#e05a5a", War: "#c23b3b",
  };
  // diverging fill: sign from the relation, intensity from |uiv|/30 so the
  // log-scaled near-zero band still reads
  function relFill(v) {
    if (v === null || v === undefined) return "#2a2a2a";
    var t = Math.min(1, Math.abs(uiv(v)) / 30);
    var mid = [70, 70, 70];
    var end = v >= 0 ? [56, 190, 100] : [210, 66, 66];
    var c = [0, 1, 2].map(function (i) {
      return Math.round(mid[i] + (end[i] - mid[i]) * t);
    });
    return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")";
  }
  function fmtMoney(v) {
    if (v == null) return "—";
    return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
      + " Cr";
  }

  function moveTip(ev) {
    tip.style.left = (ev.clientX + 14) + "px";
    tip.style.top = (ev.clientY + 14) + "px";
  }
  function reportHeight() {
    try {
      parent.postMessage({ x4h: document.body.scrollHeight + 24 }, "*");
    } catch (e) { /* not framed */ }
  }

  // ======================================================================
  //  STANDINGS  (Empire tab)
  // ======================================================================
  function renderStandings() {
    var h = "<h1>Player Standings" +
      (D.player_name && D.player_name !== "Player"
        ? " — " + esc(D.player_name) : "") + "</h1>";
    h += "<p class='sub'>Effective standing = base relation + active " +
      "boosters, as of the save. Treasury: <b>" + fmtMoney(D.treasury) +
      "</b></p>";
    h += "<table id='stand' class='display' style='width:100%'><thead><tr>" +
      "<th>Faction</th><th>Standing</th><th>Rank</th>" +
      "<th class='num'>Base</th><th class='num'>Boosters</th>" +
      "<th class='num'>Discount</th><th class='num'>Licences</th>" +
      "</tr></thead><tbody>";
    D.rows.forEach(function (r) {
      var uv = r.uiv;
      // diverging bar centred on 0, span +/-30
      var W = 150, half = W / 2, px = Math.round(Math.abs(uv) / 30 * half);
      var barCol = uv >= 0 ? "#39c46e" : "#c23b3b";
      var bar = "<svg width='" + W + "' height='16' style='vertical-align:" +
        "middle'>" +
        "<line x1='" + half + "' y1='1' x2='" + half + "' y2='15' " +
        "stroke='#555'/>" +
        (uv >= 0
          ? "<rect x='" + half + "' y='4' width='" + px + "' height='8' " +
            "rx='1' fill='" + barCol + "'/>"
          : "<rect x='" + (half - px) + "' y='4' width='" + px + "' " +
            "height='8' rx='1' fill='" + barCol + "'/>") +
        "</svg> <span class='num'>" + (uv > 0 ? "+" : "") + uv.toFixed(1) +
        "</span>";
      var rk = "<span class='rank' style='background:" +
        (RANK_COL[r.rank] || "#555") + ";color:#111'>" + r.rank + "</span>";
      h += "<tr>" +
        "<td>" + chip(r.colour) + esc(r.name) +
        " <span style='color:#888'>" + esc(r.short) + "</span></td>" +
        "<td data-order='" + uv + "'>" + bar + "</td>" +
        "<td data-order='" + r.eff + "'>" + rk + "</td>" +
        "<td class='num'>" + (r.base ? r.base.toFixed(3) : "—") + "</td>" +
        "<td class='num'>" + (r.booster
          ? (r.booster > 0 ? "+" : "") + r.booster.toFixed(3) : "—") +
          "</td>" +
        "<td class='num'>" + (r.discount
          ? (r.discount * 100).toFixed(0) + "%" : "—") + "</td>" +
        "<td class='num'>" + (r.licences || "—") + "</td>" +
        "</tr>";
    });
    h += "</tbody></table>";
    content.innerHTML = h;
    $("#stand").DataTable({ order: [[1, "desc"]], paging: false, info: false });
    reportHeight();
  }

  // ======================================================================
  //  RELATIONS  (Universe tab) — directional faction x faction heatmap
  // ======================================================================
  function renderRelations() {
    var F = D.factions, V = D.values, n = F.length;
    var cell = 24, leftW = 128, topH = 104, pad = 8, legH = 46;
    var W = leftW + n * cell + pad, H = topH + n * cell + legH;

    content.innerHTML = "<h1>Faction Relations</h1>" +
      "<p class='sub'>Directional: row&rsquo;s standing <b>toward</b> " +
      "column. Green = allied, red = hostile. Hover a cell for both " +
      "directions.</p><div id='heat'></div>";
    var svg = el("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H },
      null);
    document.getElementById("heat").appendChild(svg);

    // column headers (rotated) + row labels
    F.forEach(function (f, j) {
      var cx = leftW + j * cell + cell / 2;
      var g = el("text", {
        x: cx, y: topH - 6, transform: "rotate(-55 " + cx + " " + (topH - 6) +
          ")", "text-anchor": "start",
        class: f.id === "player" ? "" : "mut",
      }, svg);
      g.textContent = f.short;
      el("rect", { x: leftW + j * cell + cell / 2 - 5, y: topH - 4, width: 10,
        height: 3, fill: f.colour, opacity: 0.9 }, svg);
    });
    F.forEach(function (f, i) {
      var cy = topH + i * cell + cell / 2;
      el("rect", { x: leftW - 96, y: cy - 5, width: 10, height: 10, rx: 2,
        fill: f.colour, stroke: "rgba(255,255,255,0.2)" }, svg);
      var t = el("text", { x: leftW - 80, y: cy + 4,
        class: f.id === "player" ? "" : "mut" }, svg);
      t.textContent = f.name.length > 20 ? f.name.slice(0, 19) + "…"
        : f.name;
    });

    // cells
    for (var i = 0; i < n; i++) {
      for (var j = 0; j < n; j++) {
        var v = V[i][j];
        var x = leftW + j * cell, y = topH + i * cell;
        var rect = el("rect", {
          x: x, y: y, width: cell - 1.5, height: cell - 1.5, rx: 2,
          fill: relFill(v),
        }, svg);
        if (v === null) { rect.setAttribute("fill", "#1a1a1a"); continue; }
        if (v <= -0.999)
          rect.setAttribute("stroke", "rgba(220,60,60,0.9)");
        else if (v >= 0.5)
          rect.setAttribute("stroke", "rgba(60,200,110,0.9)");
        if (F[i].id === "player" || F[j].id === "player")
          rect.setAttribute("stroke", "rgba(255,255,255,0.55)");
        (function (a, b, val) {
          rect.addEventListener("mouseenter", function (ev) {
            var rev = V[b][a];
            var s = "<b>" + esc(F[a].short) + " → " + esc(F[b].short) +
              "</b>: " + val.toFixed(3) + " (" + rank(val) + ", " +
              (uiv(val) > 0 ? "+" : "") + uiv(val).toFixed(0) + ")";
            if (rev !== null && rev !== undefined)
              s += "<br><span style='color:#999'>reverse " +
                esc(F[b].short) + " → " + esc(F[a].short) + ": " +
                rev.toFixed(3) + " (" + rank(rev) + ")</span>";
            tip.innerHTML = s; tip.style.display = "block"; moveTip(ev);
          });
          rect.addEventListener("mousemove", moveTip);
          rect.addEventListener("mouseleave", function () {
            tip.style.display = "none";
          });
        })(i, j, v);
      }
    }

    // legend gradient bar
    var ly = topH + n * cell + 20, lx = leftW, lw = 220;
    for (var s = 0; s <= lw; s += 4) {
      var val = (s / lw) * 2 - 1;
      el("rect", { x: lx + s, y: ly, width: 4, height: 12,
        fill: relFill(val) }, svg);
    }
    ["−1 War", "0 Neutral", "+1 Ally"].forEach(function (lab, k) {
      var t = el("text", { x: lx + (lw / 2) * k, y: ly + 26, class: "mut",
        "text-anchor": k === 0 ? "start" : k === 2 ? "end" : "middle" }, svg);
      t.textContent = lab;
    });
    reportHeight();
  }

  if (!D || !D.view) {
    content.innerHTML = "<p class='sub'>No faction data.</p>";
  } else if (D.view === "standings") {
    renderStandings();
  } else {
    renderRelations();
  }
  window.addEventListener("resize", reportHeight);
})();
