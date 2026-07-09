"""Assembles the dashboard HTML.

Widgets are standalone files under output/files/ shown in iframes, organised
into tabs (Map / Trade / Trade Breakdown / Universe / Fleet / Tables).
Iframes in inactive tabs carry only a data-src and are loaded the first time
their tab is opened, so the initial page load stays light.
"""

from __future__ import annotations

from pathlib import Path

from .cli import log
from .config import Config
from .frames import Frames
from .refdata import RefData
from .saveparser import SaveData
from .viz.advisor import build_advisor
from .viz.charts import build_charts
from .viz.common import DARK_BG, DARK_FG, DARK_MUTED, ensure_lib
from .viz.audit import build_audit
from .viz.history import build_trade_history
from .viz.map import build_map
from .viz.market import build_market
from .viz.pnl import build_pnl
from .viz.sunbursts import build_sunbursts
from .viz.tables import build_tables

_CSS = f"""
body{{font-family:sans-serif;background:{DARK_BG};color:{DARK_FG};margin:0;}}
header{{padding:12px 16px 0 16px;}}
h2{{margin:0 0 12px 0;color:{DARK_FG};font-size:20px;}}
h2 small{{color:{DARK_MUTED};font-weight:normal;}}
iframe{{border:none;overflow:hidden;margin:0;background:{DARK_BG};}}
nav{{display:flex;gap:4px;padding:0 16px;border-bottom:1px solid #444;}}
nav button{{background:#2a2a2a;color:{DARK_MUTED};border:1px solid #444;
  border-bottom:none;border-radius:6px 6px 0 0;padding:8px 18px;font-size:14px;
  cursor:pointer;}}
nav button:hover{{color:{DARK_FG};background:#333;}}
nav button.active{{background:{DARK_BG};color:{DARK_FG};font-weight:bold;
  border-bottom:1px solid {DARK_BG};margin-bottom:-1px;}}
section{{display:none;padding:12px 16px;}}
section.active{{display:block;}}
"""

_JS = """
// dynamic pages (Market, Trade History) report their content height so the
// iframe never clips them (direct DOM access is blocked for file:// origins)
window.addEventListener('message', e => {
  if (!e.data || !e.data.x4h) return;
  document.querySelectorAll('iframe').forEach(f => {
    if (f.contentWindow === e.source) f.style.height = e.data.x4h + 'px';
  });
});

function showTab(id) {
  document.querySelectorAll('nav button').forEach(
    b => b.classList.toggle('active', b.dataset.tab === id));
  document.querySelectorAll('section').forEach(s => {
    const on = s.id === id;
    s.classList.toggle('active', on);
    if (on) s.querySelectorAll('iframe[data-src]').forEach(f => {
      f.src = f.dataset.src; f.removeAttribute('data-src');
    });
  });
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('nav button').forEach(
    b => b.addEventListener('click', () => showTab(b.dataset.tab)));
});
"""


def _iframe(src: str, style: str, lazy: bool) -> str:
    attr = f'data-src="{src}"' if lazy else f'src="{src}"'
    return (f'<iframe {attr} style="{style}" scrolling="no" '
            'allowfullscreen allow="fullscreen"></iframe>')


def _categorize_sunburst(src: str) -> str:
    name = src.lower()
    if "fleet composition" in name:
        return "Fleet"
    if ("resource" in name or "station modules" in name
            or "hull mass" in name or "ships per faction" in name):
        return "Universe"
    return "Trade Breakdown"


def build_dashboard(cfg: Config, save: SaveData, ref: RefData,
                    frames: Frames) -> Path:
    files_dir = cfg.output_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    ensure_lib(files_dir)
    guid = save.guid

    wide = "width:1536px;height:560px;"
    half = "width:49%;height:870px;"
    table = "width:100%;height:512px;"

    log("Generating sector map")
    tabs: dict[str, list[str]] = {
        "Map": ["<p>" + _iframe(build_map(frames, ref, cfg, files_dir, guid),
                                "width:1756px;height:864px;", lazy=False)
                + "</p>"],
        "Trade": [], "Trade Breakdown": [], "Trade History": [],
        "Station P&L": [], "Market": [], "Audit": [], "Build Advisor": [],
        "Universe": [], "Fleet": [], "Tables": [],
    }

    log("Generating time-series charts")
    for src in build_charts(frames, ref, files_dir, guid):
        tabs["Trade"].append("<p>" + _iframe(src, wide, lazy=True) + "</p>")

    log("Generating trade history browser")
    history = build_trade_history(frames, files_dir, guid)
    if history:
        tabs["Trade History"].append(
            "<p>" + _iframe(history, "width:100%;height:1400px;", lazy=True)
            + "</p>")

    log("Generating station P&L")
    pnl = build_pnl(frames, ref, cfg, files_dir, guid)
    if pnl:
        tabs["Station P&L"].append(
            "<p>" + _iframe(pnl, "width:100%;height:1300px;", lazy=True)
            + "</p>")

    log("Generating empire audit")
    audit = build_audit(frames, ref, cfg, files_dir, guid)
    if audit:
        tabs["Audit"].append(
            "<p>" + _iframe(audit, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating build advisor")
    advisor = build_advisor(frames, ref, cfg, files_dir, guid)
    if advisor:
        tabs["Build Advisor"].append(
            "<p>" + _iframe(advisor, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating market overview")
    market = build_market(frames, ref, files_dir, guid)
    if market:
        tabs["Market"].append(
            "<p>" + _iframe(market, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating sunburst plots")
    for src in build_sunbursts(frames, ref, cfg, files_dir, guid):
        tabs[_categorize_sunburst(src)].append(_iframe(src, half, lazy=True))

    log("Generating tables")
    for src in build_tables(frames, ref, cfg, files_dir, guid):
        tabs["Tables"].append("<p>" + _iframe(src, table, lazy=True) + "</p>")

    tabs = {name: content for name, content in tabs.items() if content}

    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
             f"<title>X4 Analysis - {frames.player_faction_name}</title>",
             f"<style>{_CSS}</style><script>{_JS}</script></head><body>",
             "<header>",
             f"<h2>{frames.player_faction_name} &mdash; {save.player_name} "
             f"<small>game v{save.game_version}, "
             f"{frames.logged_hours:.1f}h of log history</small></h2>",
             "</header><nav>"]
    for i, name in enumerate(tabs):
        active = " class='active'" if i == 0 else ""
        parts.append(f"<button{active} data-tab='tab{i}'>{name}</button>")
    parts.append("</nav>")
    for i, (name, content) in enumerate(tabs.items()):
        active = " class='active'" if i == 0 else ""
        parts.append(f"<section id='tab{i}'{active}>")
        parts.extend(content)
        parts.append("</section>")
    parts.append("</body></html>")

    out = cfg.output_dir / f"dashboard_{guid}.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
