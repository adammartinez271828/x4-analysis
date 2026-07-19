"""Interactive hex sector map (R lines 802-1005).

Map x = galaxy x, map y = galaxy z. The R script hand-tuned offsets for every
multi-sector cluster by sector name; since extract-gamedata captures the real
in-cluster sector offsets, positions are derived from those instead (quantized
to the same grid steps the R script used), which covers DLC sectors
automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from .common import DARK_BG, save_widget

X_DIV = 20_000_000
Y_DIV = 17_320_000
X_RANGE = (-230_000_000, 200_000_000)
Y_RANGE = (-86_600_000, 147_220_000)

# label wrapping: break on spaces except before roman numerals / short words
_WRAP = re.compile(
    r" (?![IVX]+ )(?![IVX]+$)(?!of )(?!to )(?!Sun$)(?!Plate )(?!First )(?!Dead )"
)
_SUFFIX = re.compile(r" [12IVX]+.*$")


# slot patterns for n sectors sharing one cluster hex, in (dx, dy) grid units
# of (X_DIV/8, Y_DIV/4); |dx| == 2 means X_DIV/4 on the x axis. Matches the
# arrangements the R script hand-tuned per sector name (e.g. Grand Exchange).
_SLOTS = {
    1: [(0, 0)],
    2: [(-1, 1), (1, -1)],
    3: [(1, 1), (-2, 0), (1, -1)],
    4: [(-1, 1), (1, 1), (-1, -1), (1, -1)],
    5: [(-1, 1), (1, 1), (-2, 0), (-1, -1), (1, -1)],
    6: [(-1, 1), (1, 1), (-2, 0), (2, 0), (-1, -1), (1, -1)],
}


# Legend interactivity for the resource overlay and faction group, injected
# into the widget page via save_widget(extra_html=...). Traces are identified
# by the meta.kind set on them in build_map; __MAX_PX__/__MIN_PX__ are filled
# from the same constants the Python-side initial sizes use.
_LEGEND_JS = """
<script>
(function () {
  var MAX_PX = __MAX_PX__, MIN_PX = __MIN_PX__;

  function isShown(t) {
    return t.visible === true || t.visible === undefined || t.visible === null;
  }
  function indicesOf(gd, kind) {
    var idx = [];
    gd.data.forEach(function (t, i) {
      if (t.meta && t.meta.kind === kind) idx.push(i);
    });
    return idx;
  }
  function visibleFactions(gd) {
    var names = {};
    gd.data.forEach(function (t) {
      if (t.meta && t.meta.kind === "faction" && isShown(t)) {
        names[t.meta.faction] = true;
      }
    });
    return names;
  }

  // resize the (single) visible resource trace: normalize to the max over
  // sectors of visible factions; hidden factions' sectors drop to nothing
  function renormalize(gd) {
    var shown = indicesOf(gd, "resource").filter(function (i) {
      return isShown(gd.data[i]);
    });
    if (shown.length !== 1) return;
    var t = gd.data[shown[0]];
    var facs = visibleFactions(gd);
    var maxv = 0;
    t.meta.raw.forEach(function (v, i) {
      if (facs[t.meta.faction[i]] && v > maxv) maxv = v;
    });
    var sizes = t.meta.raw.map(function (v, i) {
      if (v <= 0 || maxv <= 0 || !facs[t.meta.faction[i]]) return 0;
      return Math.max(MIN_PX, v / maxv * MAX_PX);
    });
    Plotly.restyle(gd, {"marker.size": [sizes]}, shown);
  }

  function attach() {
    var gd = document.querySelector(".plotly-graph-div");
    if (!gd || !gd.on) { setTimeout(attach, 50); return; }
    gd.on("plotly_legendclick", function (ev) {
      var t = gd.data[ev.curveNumber];
      if (!t.meta || !t.meta.kind) return;  // default toggle for base/overlays

      if (t.meta.kind === "faction-control") {
        Plotly.restyle(gd,
            {visible: t.meta.action === "all" ? true : "legendonly"},
            indicesOf(gd, "faction"))
          .then(function () { renormalize(gd); });
        return false;
      }
      if (t.meta.kind === "resource") {
        // single-select: show only the clicked resource, or hide it if it
        // was already the visible one
        var wasShown = isShown(t);
        var idx = indicesOf(gd, "resource");
        Plotly.restyle(gd,
            {visible: idx.map(function (i) {
              return (!wasShown && i === ev.curveNumber) ? true : "legendonly";
            })}, idx)
          .then(function () { renormalize(gd); });
        return false;
      }
      if (t.meta.kind === "faction") {
        // do the toggle ourselves so renormalize runs after it, not before
        Plotly.restyle(gd, {visible: isShown(t) ? "legendonly" : true},
                       [ev.curveNumber])
          .then(function () { renormalize(gd); });
        return false;
      }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
})();
</script>
"""


def _slot_xy(dx: int, dy: int) -> tuple[float, float]:
    x = dx * (X_DIV / 4 if abs(dx) == 2 else X_DIV / 8)
    return x, dy * (Y_DIV / 4)


def _layout_sectors(frames: Frames, ref: RefData, cfg: Config) -> pd.DataFrame:
    clusters = ref.clusters.set_index("macro")
    offsets = ref.sectors.set_index("macro")
    per_cluster = ref.sectors.groupby("cluster")["macro"].count()

    df = frames.sectors.copy()
    if cfg.spoilers_hide:
        df = df[df["knownto"] == "player"]

    recs = []
    for cluster_macro, group in df.groupby("cluster.macro"):
        if cluster_macro not in clusters.index:
            continue
        cx = float(clusters.loc[cluster_macro, "x"])
        cy = float(clusters.loc[cluster_macro, "z"])
        multi = per_cluster.get(cluster_macro, 1) > 1

        # order sectors by their real in-cluster position (top first, then
        # left) and assign them to the same-ordered display slots
        group = group.assign(
            _ox=group["macro"].map(offsets["x"]).fillna(0.0),
            _oz=group["macro"].map(offsets["z"]).fillna(0.0),
        ).sort_values(["_oz", "_ox"], ascending=[False, True])
        n = len(group)
        slots = _SLOTS.get(n) if multi else _SLOTS[1]
        if slots is None:  # 7+ sectors: ring layout
            slots = [(-1, 1), (1, 1), (-2, 0), (2, 0), (-1, -1), (1, -1),
                     (0, 2), (0, -2)][:n]
        slots = sorted(slots, key=lambda s: (-s[1], s[0]))

        for (_, row), (dx, dy) in zip(group.iterrows(), slots):
            sx, sy = _slot_xy(dx, dy) if multi else (0.0, 0.0)
            recs.append({
                "x": cx + sx, "y": cy + sy, "cluster.x": cx, "cluster.y": cy,
                "cluster.macro": cluster_macro, "macro": row["macro"],
                "name": row["name"], "owner": row["owner"],
                "knownto": row["knownto"], "contested": row["contested"],
                "sizecat": "s" if multi else "b",
            })
    out = pd.DataFrame(recs)
    out["colour"] = out["owner"].map(ref.faction_colour).fillna("#808080")
    out["ownername"] = out["owner"].map(ref.faction_name).fillna(
        out["owner"].str.capitalize())
    out.loc[out["owner"] == "player", "ownername"] = "Player"
    return out


def _labels(plot_sectors: pd.DataFrame, ref: RefData) -> pd.DataFrame:
    """Sector labels: multi-sector clusters get one base-name label at the
    cluster centre plus per-sector suffix labels (R 840-864)."""
    cluster_names = dict(zip(ref.clusters["macro"], ref.clusters["name"]))
    recs = []
    for cmacro, group in plot_sectors.groupby("cluster.macro"):
        if len(group) == 1:
            row = group.iloc[0]
            recs.append({"x": row["x"], "y": row["y"], "altname": row["name"]})
            continue
        base = str(cluster_names.get(cmacro, "")) or \
            _SUFFIX.sub("", str(group.iloc[0]["name"]))
        base_used = False
        for row in group.itertuples():
            name = str(row.name)
            if name.startswith(base + " ") and len(name) > len(base) + 1:
                recs.append({"x": row.x, "y": row.y,
                             "altname": name[len(base) + 1:]})
                base_used = True
            else:
                recs.append({"x": row.x, "y": row.y, "altname": name})
        if base_used:
            recs.append({
                "x": float(group.iloc[0]["cluster.x"]),
                "y": float(group.iloc[0]["cluster.y"]),
                "altname": base,
            })
    return pd.DataFrame(recs).dropna(subset=["altname"])


def _overlay(events: pd.DataFrame, plot_sectors: pd.DataFrame,
             time_limit: float, count_name: str) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["x", "y", "sizecat", count_name, "scale",
                                     "name"])
    recent = events[events["time"] > time_limit]
    counts = (recent.groupby("sector.name").size()
              .rename(count_name).reset_index())
    merged = plot_sectors.merge(counts, left_on="name",
                                right_on="sector.name", how="inner")
    if merged.empty:
        return merged
    merged["scale"] = merged[count_name] / merged[count_name].max()
    return merged


def _resource_levels(plot_sectors: pd.DataFrame, sectors: pd.DataFrame,
                     resource_cols: list[str]) -> pd.DataFrame:
    """Quartile-bin each resource: 3=top quartile, 2=third, 1=any, 0=none."""
    res = plot_sectors.merge(
        sectors[["macro"] + resource_cols], on="macro", how="left")
    for col in resource_cols:
        vals = res[col].fillna(0.0)
        positive = vals[vals > 0]
        if positive.empty:
            res[col] = 0
            continue
        q50, q75 = positive.quantile(0.5), positive.quantile(0.75)
        res[col] = pd.cut(vals, [-1, 0, q50, q75, float("inf")],
                          labels=[0, 1, 2, 3]).astype(int)
    return res


def _tooltips(res: pd.DataFrame, resource_cols: list[str], ref: RefData,
              overlay_hours: float) -> pd.Series:
    tips = []
    level_names = [(3, "High"), (2, "Medium"), (1, "Low")]
    for row in res.itertuples(index=False):
        d = row._asdict()
        parts = [f"<b>{d['name']}</b>"]
        owner = d["ownername"]
        parts.append(f"{owner} <b>(Contested)</b>" if d["contested"] == 1
                     else str(owner))
        if pd.notna(d.get("interdictions")):
            parts.append(f"{overlay_hours:.0f}h Police Interdictions: "
                         f"{int(d['interdictions'])}")
        if pd.notna(d.get("harassments")):
            parts.append(f"{overlay_hours:.0f}h Pirate Harassments: "
                         f"{int(d['harassments'])}")
        parts.append("<b>Resources</b>")
        for level, label in level_names:
            names = [ref.ware_name.get(c, c) for c in resource_cols
                     if d.get(c) == level]
            parts.append(f"{label}: " + (", ".join(names) if names else "None"))
        tips.append("<br>".join(parts))
    return pd.Series(tips, index=res.index)


def build_map(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
              guid: str) -> str:
    plot_sectors = _layout_sectors(frames, ref, cfg)
    plot_clusters = ref.clusters[
        ref.clusters["macro"].isin(plot_sectors["cluster.macro"])
    ][["x", "z", "name", "macro"]].rename(columns={"z": "y"})

    time_limit = frames.time_now - 3600 * cfg.overlay_hours
    police = _overlay(frames.police, plot_sectors, time_limit, "interdictions")
    pirates = _overlay(frames.pirates, plot_sectors, time_limit, "harassments")

    res = _resource_levels(plot_sectors, frames.sectors, frames.resource_cols)
    res = res.merge(police[["name", "interdictions"]], on="name", how="left") \
        if not police.empty else res.assign(interdictions=pd.NA)
    res = res.merge(pirates[["name", "harassments"]], on="name", how="left") \
        if not pirates.empty else res.assign(harassments=pd.NA)
    plot_sectors["tooltip"] = _tooltips(res, frames.resource_cols, ref,
                                        cfg.overlay_hours)
    labels = _labels(plot_sectors, ref)

    # marker sizing for a 1536x864 map (R makeMap defaults)
    big, small, border = 62, 25, 6
    contested_big, contested_small = 44, 20
    opacity = 0.6
    hexsym = "hexagon2-open"

    def sizes(df, b, s):
        return [b if c == "b" else s for c in df["sizecat"]]

    fig = go.Figure()

    # resource overlay: one hidden trace per resource, markers sized by the
    # sector's yield normalized to the galaxy max. Added first so the filled
    # hexes render underneath the base-map linework. The inline JS below
    # single-selects them from the legend and renormalizes against the max
    # over visible factions only (meta carries the raw yields for that).
    res_max_px, res_min_px = 56, 4
    if frames.resource_cols:
        res_raw = plot_sectors.merge(
            frames.sectors[["macro"] + frames.resource_cols],
            on="macro", how="left")
        for i, col in enumerate(frames.resource_cols):
            vals = res_raw[col].fillna(0.0)
            maxv = float(vals.max())
            fig.add_scatter(
                x=res_raw["x"], y=res_raw["y"], mode="markers",
                name=ref.ware_name.get(col, col),
                legendgroup="Resources", legendrank=1002,
                legendgrouptitle={"text": "Resources",
                                  "font": {"color": "#b0b0b0"}}
                if i == 0 else None,
                visible="legendonly", hoverinfo="text",
                hovertext=res_raw["tooltip"],
                marker={"symbol": "hexagon2", "opacity": 0.85,
                        "line": {"width": 1},
                        "size": [0.0 if v <= 0 or maxv <= 0 else
                                 max(res_min_px, v / maxv * res_max_px)
                                 for v in vals]},
                meta={"kind": "resource",
                      "raw": [float(v) for v in vals],
                      "faction": [str(o) for o in res_raw["ownername"]]})

    fig.add_scatter(
        x=plot_clusters["x"], y=plot_clusters["y"], mode="markers",
        name="Cluster Outlines", hoverinfo="skip", legendgroup="Base Map",
        legendgrouptitle={"text": "Base Map", "font": {"color": "#b0b0b0"}},
        marker={"color": "#B0B0B0", "opacity": opacity, "size": big + border,
                "symbol": hexsym, "line": {"width": 2}})
    fig.add_scatter(
        x=plot_sectors["x"], y=plot_sectors["y"], mode="markers",
        name="Sector Outlines", hoverinfo="skip", legendgroup="Base Map",
        marker={"color": "#F0F0F0", "opacity": opacity,
                "size": sizes(plot_sectors, big + border, small + border),
                "symbol": hexsym, "line": {"width": 2}})

    contested = plot_sectors[plot_sectors["contested"] == 1]
    fig.add_scatter(
        x=contested["x"], y=contested["y"], mode="markers",
        name="Contested Sectors", hoverinfo="skip", legendgroup="Overlays",
        legendgrouptitle={"text": "Overlays", "font": {"color": "#b0b0b0"}},
        visible="legendonly", legendrank=1001,
        marker={"color": "#EEEE33", "opacity": opacity,
                "size": sizes(contested, contested_big, contested_small),
                "symbol": "diamond-x",
                "line": {"color": "#ffffff", "width": 1}})
    for overlay, name, colour, symbol in (
        (police, f"Police Interdictions ({cfg.overlay_hours:.0f}h)",
         "#3333EE", "star"),
        (pirates, f"Pirate Harassments ({cfg.overlay_hours:.0f}h)",
         "#EE3333", "star-triangle-down"),
    ):
        if overlay.empty:
            continue
        size = [int(1 + round(sc * ((contested_big if c == "b"
                                     else contested_small) - 1)))
                for sc, c in zip(overlay["scale"], overlay["sizecat"])]
        fig.add_scatter(
            x=overlay["x"], y=overlay["y"], mode="markers", name=name,
            hoverinfo="skip", legendgroup="Overlays", visible="legendonly",
            legendrank=1001,
            marker={"color": colour, "opacity": opacity, "size": size,
                    "symbol": symbol,
                    "line": {"color": "#ffffff", "width": 1}})

    owner_order = (plot_sectors.groupby("owner")["ownername"].first()
                   .sort_values().index)
    for owner in owner_order:
        sub = plot_sectors[plot_sectors["owner"] == owner]
        fig.add_scatter(
            x=sub["x"], y=sub["y"], mode="markers",
            name=str(sub["ownername"].iloc[0]), hoverinfo="text",
            hovertext=sub["tooltip"], legendgroup="Factions", legendrank=999,
            legendgrouptitle={"text": "Factions", "font": {"color": "#b0b0b0"}},
            marker={"color": sub["colour"].iloc[0], "opacity": opacity,
                    "size": sizes(sub, big, small), "symbol": hexsym,
                    "line": {"width": border}},
            meta={"kind": "faction",
                  "faction": str(sub["ownername"].iloc[0])})

    # legend-only show-all / hide-all buttons for the faction group, handled
    # by the inline JS. They need one real (invisible) data point so plotly
    # emits legendclick for them; visible=True avoids the greyed-out styling.
    for rank, label, action in ((997, "All factions", "all"),
                                (998, "No factions", "none")):
        fig.add_scatter(
            x=[0], y=[0], mode="markers", name=label, hoverinfo="skip",
            legendgroup="Factions", legendrank=rank,
            marker={"size": 0, "opacity": 0},
            meta={"kind": "faction-control", "action": action})

    fig.add_scatter(
        x=labels["x"], y=labels["y"], mode="text", name="Sector Names",
        hoverinfo="skip", legendgroup="Base Map",
        text=["<b>" + _WRAP.sub("<br>", str(n)) + "</b>"
              for n in labels["altname"]],
        textfont={"size": 8, "color": "rgba(240,240,96,0.63)"})

    # the legend lives in a dedicated right-hand strip (outside the plot
    # area) so it never overlaps sectors; the plot area stays the exact
    # 1536x864 the marker px sizes are tuned for
    legend_w = 220
    fig.update_layout(
        width=1536 + legend_w, height=864, autosize=False,
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        margin={"b": 0, "l": 0, "r": legend_w, "t": 0},
        legend={"x": 1.0, "y": 0.96, "xanchor": "left", "yanchor": "top",
                "itemsizing": "constant",
                "groupclick": "toggleitem",
                "traceorder": "grouped",
                "font": {"size": 13, "color": "#b0b0b0"},
                "bgcolor": "rgba(30,30,30,0)"},
        # R's fixed 5.10 ranges, widened if DLC content falls outside them
        xaxis={"range": (min(X_RANGE[0], plot_sectors["x"].min() - X_DIV / 2),
                         max(X_RANGE[1], plot_sectors["x"].max() + X_DIV / 2)),
               "fixedrange": True, "visible": False},
        yaxis={"range": (min(Y_RANGE[0], plot_sectors["y"].min() - Y_DIV / 2),
                         max(Y_RANGE[1], plot_sectors["y"].max() + Y_DIV / 2)),
               "fixedrange": True, "visible": False},
    )
    return save_widget(fig, files_dir, "Sector map", guid,
                       extra_html=_LEGEND_JS
                       .replace("__MAX_PX__", str(res_max_px))
                       .replace("__MIN_PX__", str(res_min_px)))
