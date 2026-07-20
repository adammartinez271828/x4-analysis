"""Shared helpers for the dashboard widgets.

Each widget is written as its own HTML file under output/files/ referencing a
single shared plotly.js in output/files/lib/ (mirrors the R script's
saveWidget(selfcontained=FALSE, libdir='lib') layout), and embedded into the
dashboard as an iframe.
"""

from __future__ import annotations

import colorsys
import shutil
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

_PLOTLY_JS = "lib/plotly.min.js"

# dark theme shared by the dashboard shell and every widget
DARK_BG = "#1e1e1e"      # page / paper background
DARK_PLOT = "#262626"    # plot area background
DARK_FG = "#d8d8d8"      # foreground text
DARK_MUTED = "#9a9a9a"   # secondary text


def ensure_lib(files_dir: Path) -> None:
    """Copy plotly + vendored jQuery/DataTables into output/files/lib/ so
    dashboards work fully offline."""
    lib = files_dir / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    import plotly.offline as po

    sources = [Path(po.__file__).parent.parent / "package_data"
               / "plotly.min.js"]
    vendor = Path(__file__).resolve().parents[1] / "vendor"
    sources += sorted(vendor.glob("*"))
    for src in sources:
        dst = lib / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy(src, dst)


def fullscreen_button_html(resize_plotly: bool = True) -> str:
    """The ⛶ fullscreen toggle appended to widget pages. Needs
    allowfullscreen on the dashboard iframes. resize_plotly adds the
    fullscreenchange redraw hook plotly figures need (pages that lay
    themselves out with CSS don't)."""
    resize = (
        "document.addEventListener('fullscreenchange',function(){"
        "var g=document.querySelector('.plotly-graph-div');"
        "if(g&&window.Plotly){Plotly.Plots.resize(g);}});"
    ) if resize_plotly else ""
    return (
        "<div id='x4fs' title='Fullscreen (Esc to leave)' "
        "style='position:fixed;bottom:6px;right:10px;z-index:20;"
        "cursor:pointer;font-size:22px;line-height:1;color:#b0b0b0;"
        "opacity:0.45;user-select:none'>&#x26F6;</div>"
        "<script>(function(){"
        "var b=document.getElementById('x4fs');"
        "b.onmouseenter=function(){b.style.opacity=1;};"
        "b.onmouseleave=function(){b.style.opacity=0.45;};"
        "b.onclick=function(){"
        "if(document.fullscreenElement){document.exitFullscreen();}"
        "else{document.documentElement.requestFullscreen()"
        ".catch(function(){});}};"
        f"{resize}"
        "})();</script>"
    )


def save_widget(fig: go.Figure, files_dir: Path, title: str, guid: str,
                extra_html: str = "") -> str:
    """Write a plotly figure as a standalone dark-themed widget page; returns
    the dashboard-relative src path. extra_html is appended to the body
    (widget-specific scripts, e.g. the map's legend interactivity)."""
    # plotly_dark supplies dark-friendly grid/axis/hover colours; figures that
    # set their own backgrounds (the map) keep them, everything else gets the
    # shared dark grey
    fig.update_layout(template="plotly_dark")
    if fig.layout.paper_bgcolor is None:
        fig.update_layout(paper_bgcolor=DARK_BG, plot_bgcolor=DARK_PLOT)
    if fig.layout.font.color is None:
        fig.update_layout(font={"color": DARK_FG})

    body = fig.to_html(full_html=False, include_plotlyjs=False,
                       div_id=None, config={"displaylogo": False})
    # fullscreen zoom: figures are responsive, so fullscreening the widget
    # page redraws the chart at screen size (small sunburst slices become
    # readable)
    fs_btn = fullscreen_button_html(resize_plotly=True)
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<script src='{_PLOTLY_JS}'></script>"
        f"<style>html,body{{height:100%;}}"
        f"body{{margin:0;background:{DARK_BG};}}</style></head>"
        f"<body>{body}{fs_btn}{extra_html}</body></html>"
    )
    name = f"{title}_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"


def mixed_rainbow(n: int) -> list[str]:
    """Port of the R mixedRainbow(): rainbow hues reordered so neighbouring
    series get visually distinct colours."""
    if n <= 0:
        return []
    hues = [i / n for i in range(n)]
    reps = -(-n // 6)  # ceiling
    order: list[int] = []
    for start in range(reps):
        order.extend(range(start, n, reps))
    cols = []
    for i in order[:n]:
        r, g, b = colorsys.hsv_to_rgb(hues[i], 1.0, 1.0)
        cols.append(f"#{round(r*255):02x}{round(g*255):02x}{round(b*255):02x}")
    return cols


def with_alpha(hex_colour: str, alpha: int) -> str:
    """'#rrggbb' + alpha byte -> 'rgba(...)' plotly colour."""
    hex_colour = (hex_colour or "#808080").lstrip("#")
    if len(hex_colour) < 6:
        hex_colour = "808080"
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{max(0, min(255, alpha)) / 255:.3f})"


def moving_average(values: pd.Series, n: int) -> pd.Series:
    """Centered moving average like R's stats::filter(sides = 2)."""
    n = max(1, int(n))
    return values.rolling(window=n, center=True).mean()


def fmt_big(value: float) -> str:
    return f"{value:,.0f}"


class Sunburst:
    """Accumulates (id, label, parent, value, colour) rows and renders a
    plotly sunburst with branchvalues='total' like the R plots."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.labels: list[str] = []
        self.parents: list[str] = []
        self.values: list[float] = []
        self.colours: list[str | None] = []

    def add(self, id_: str, label: str, parent: str, value: float,
            colour: str | None = None) -> None:
        self.ids.append(id_)
        self.labels.append(label)
        self.parents.append(parent)
        self.values.append(value)
        self.colours.append(colour)

    def add_root(self, label: str, value: float, colour: str | None = None,
                 id_: str = "total") -> None:
        # white root when the sunburst is otherwise coloured; colourless roots
        # keep plotly's automatic palette for the whole plot
        self.add(id_, label, "", value, colour)

    def root_colour_if_needed(self) -> None:
        if self.colours and self.colours[0] is None and \
                any(c is not None for c in self.colours[1:]):
            self.colours[0] = "#FFFFFF"

    def annotate_money(self, total: float, per_hour_window: float) -> None:
        """Append 'N Cr.' + share/rate lines to every label (R style)."""
        for i in range(len(self.labels)):
            money = self.values[i]
            if self.parents[i] == "":
                rate = fmt_big(round(total / per_hour_window)) if per_hour_window \
                    else "0"
                self.labels[i] = (f"{self.labels[i]}<br>{fmt_big(money)} Cr.<br>"
                                  f"{rate} Cr/h")
            else:
                pct = 100.0 * money / total if total else 0.0
                self.labels[i] = (f"{self.labels[i]}<br>{fmt_big(money)} Cr.<br>"
                                  f"{pct:.1f}%")

    def annotate_amounts(self, unit: str = "") -> None:
        """Append '<value> <unit> · <pct>%' to every non-root label (pct of
        the grand total) and the total to the root label."""
        if not self.values:
            return
        tot = self.values[0]
        u = f" {unit}" if unit else ""
        for i in range(len(self.labels)):
            v = self.values[i]
            if self.parents[i] == "":
                self.labels[i] += f"<br>{fmt_big(v)}{u}"
            else:
                pct = 100.0 * v / tot if tot else 0.0
                pct_s = f"{pct:.1f}" if pct >= 0.1 else "<0.1"
                self.labels[i] += f"<br>{fmt_big(v)}{u} · {pct_s}%"

    def figure(self, title: str, maxdepth: int | None = None,
               values: bool = True) -> go.Figure:
        self.root_colour_if_needed()
        marker = None
        if any(c is not None for c in self.colours):
            marker = {"colors": [c or "#cccccc" for c in self.colours]}
        trace = go.Sunburst(
            ids=self.ids, labels=self.labels, parents=self.parents,
            values=self.values if values else None,
            branchvalues="total" if values else None,
            hoverinfo="label", marker=marker, maxdepth=maxdepth or -1,
        )
        fig = go.Figure(trace)
        # explicit height: plotly's 450px default renders the rings too small
        # to read; the dashboard iframes are sized to match
        fig.update_layout(title={"text": title, "font": {"size": 18}},
                          height=850,
                          margin={"t": 40, "l": 0, "r": 0, "b": 0})
        return fig


def hourly_series(df: pd.DataFrame, group_col: str, maxtime: float,
                  value_col: str = "money") -> pd.DataFrame:
    """Port of the R bar-plot prep: bin into relative hours (0 = latest,
    negative = past), zero-fill every group x hour, and sum."""
    binned = pd.DataFrame({
        "time": ((df["time"] - maxtime) / 3600.0).apply(lambda v: int(v)),
        "group": df[group_col].astype(str),
        "money": pd.to_numeric(df[value_col], errors="coerce").fillna(0),
    })
    times = binned["time"].unique()
    groups = binned["group"].unique()
    filler = pd.DataFrame([
        {"time": t, "group": g, "money": 0} for t in times for g in groups
    ])
    out = (pd.concat([binned, filler], ignore_index=True)
           .groupby(["time", "group"], as_index=False)["money"].sum()
           .sort_values(["group", "time"], ignore_index=True))
    return out


def hourly_average(df: pd.DataFrame, maxtime: float, smoothing: int = 12,
                   value_col: str = "money") -> pd.DataFrame:
    avg = pd.DataFrame({
        "time": ((df["time"] - maxtime) / 3600.0).apply(lambda v: int(v)),
        "money": pd.to_numeric(df[value_col], errors="coerce").fillna(0),
    }).groupby("time", as_index=False)["money"].sum().sort_values("time")
    window = min(smoothing, max(1, len(avg) // 2))
    avg["money"] = moving_average(avg["money"], window)
    return avg.dropna(subset=["money"])
