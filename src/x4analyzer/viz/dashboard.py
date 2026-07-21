"""Assembles the dashboard HTML.

Widgets are standalone files under output/files/ shown in iframes,
organised into five question-shaped top-level tabs with sub-tab pills
(Map; Trade: how's my trading; Empire: what needs my attention; Market:
galaxy economy & opportunities; Universe: galaxy stats). Iframes carry
only a data-src until their sub-tab is first opened, so the initial page
load stays light. The active view persists in sessionStorage and in the
URL hash (#trade/history), so views are bookmarkable.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..cli import log
from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from ..save.parser import SaveData
from .advisor import build_advisor
from .charts import build_charts
from .common import DARK_BG, DARK_FG, DARK_MUTED, ensure_lib
from .audit import build_audit
from .history import build_trade_history
from .map import build_map
from .market import build_market
from .pnl import build_pnl
from .sunbursts import build_sunbursts
from .tables import build_tables

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
section{{display:none;padding:0 16px 12px 16px;}}
section.active{{display:block;}}
.subnav{{display:flex;gap:8px;padding:10px 0;}}
.subnav button{{background:none;color:{DARK_MUTED};border:1px solid #444;
  border-radius:14px;padding:4px 14px;font-size:13px;cursor:pointer;}}
.subnav button:hover{{color:{DARK_FG};border-color:#666;}}
.subnav button.active{{background:#3a3a3a;color:{DARK_FG};font-weight:bold;
  border-color:#777;}}
.subpane{{display:none;padding-top:8px;}}
.subpane.active{{display:block;}}
section.nosub .subpane{{padding-top:12px;}}
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

// view state: chosen sub-tab per tab survives reloads (sessionStorage) and
// the active view is addressable as #tab/sub for bookmarking
let state = {};
try { state = JSON.parse(sessionStorage.getItem('x4tabs') || '{}'); }
catch (e) { state = {}; }

function loadPane(pane) {
  pane.querySelectorAll('iframe[data-src]').forEach(f => {
    f.src = f.dataset.src; f.removeAttribute('data-src');
  });
}

function showSub(section, subId, remember) {
  let target = null;
  section.querySelectorAll('.subpane').forEach(p => {
    if (p.dataset.sub === subId) target = p;
  });
  if (!target) target = section.querySelector('.subpane');
  section.querySelectorAll('.subnav button').forEach(
    b => b.classList.toggle('active', b.dataset.sub === target.dataset.sub));
  section.querySelectorAll('.subpane').forEach(
    p => p.classList.toggle('active', p === target));
  loadPane(target);
  if (remember) {
    state[section.dataset.tab] = target.dataset.sub;
    try { sessionStorage.setItem('x4tabs', JSON.stringify(state)); }
    catch (e) { /* best-effort */ }
  }
  history.replaceState(null, '',
    '#' + section.dataset.tab +
    (target.dataset.sub ? '/' + target.dataset.sub : ''));
}

function showTab(tabId, subId) {
  let target = null;
  document.querySelectorAll('section').forEach(s => {
    if (s.dataset.tab === tabId) target = s;
  });
  if (!target) target = document.querySelector('section');
  document.querySelectorAll('nav button').forEach(
    b => b.classList.toggle('active', b.dataset.tab === target.dataset.tab));
  document.querySelectorAll('section').forEach(
    s => s.classList.toggle('active', s === target));
  showSub(target, subId || state[target.dataset.tab] || '', !!subId);
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('nav button').forEach(
    b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  document.querySelectorAll('section').forEach(s => {
    s.querySelectorAll('.subnav button').forEach(
      b => b.addEventListener('click', () => showSub(s, b.dataset.sub, true)));
  });
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash) {
    const [t, sub] = hash.split('/');
    showTab(t, sub);
  } else {
    showTab(document.querySelector('section').dataset.tab);
  }
});
"""


def _iframe(src: str, style: str, lazy: bool) -> str:
    attr = f'data-src="{src}"' if lazy else f'src="{src}"'
    return (f'<iframe {attr} style="{style}" scrolling="no" '
            'allowfullscreen allow="fullscreen"></iframe>')


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _categorize_sunburst(src: str) -> tuple[str, str]:
    name = src.lower()
    if "fleet composition" in name:
        return ("Empire", "Fleet")
    if ("resource" in name or "station modules" in name
            or "hull mass" in name or "ships per faction" in name):
        return ("Universe", "Overview")
    return ("Trade", "Breakdown")


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
    map_src, _, _ = build_map(frames, ref, cfg, files_dir, guid)
    # the map page pans/zooms inside itself, so its iframe just fills the
    # viewport instead of taking the scene's fixed size
    map_style = "width:100%;height:calc(100vh - 118px);min-height:600px;"

    # tab -> sub-tab -> widget html. "" = no sub-nav (single-view tab).
    # Grouped by the question being asked, not the chart type: Trade =
    # my trading business, Empire = what needs my attention, Market =
    # the galaxy economy, Universe = galaxy stats.
    tabs: dict[str, dict[str, list[str]]] = {
        "Map": {"": [_iframe(map_src, map_style, lazy=False)]},
        "Trade": {"Charts": [], "Breakdown": [], "History": [],
                  "Earnings": []},
        "Empire": {"Audit": [], "Station P&L": [], "Fleet": []},
        "Market": {"Overview": [], "Build Advisor": []},
        "Universe": {"Overview": [], "Contested": []},
    }

    log("Generating time-series charts")
    for src in build_charts(frames, ref, files_dir, guid):
        tabs["Trade"]["Charts"].append(
            "<p>" + _iframe(src, wide, lazy=True) + "</p>")

    log("Generating trade history browser")
    history = build_trade_history(frames, files_dir, guid)
    if history:
        tabs["Trade"]["History"].append(
            "<p>" + _iframe(history, "width:100%;height:1400px;", lazy=True)
            + "</p>")

    log("Generating station P&L")
    pnl = build_pnl(frames, ref, cfg, files_dir, guid)
    if pnl:
        tabs["Empire"]["Station P&L"].append(
            "<p>" + _iframe(pnl, "width:100%;height:1300px;", lazy=True)
            + "</p>")

    log("Generating empire audit")
    audit = build_audit(frames, ref, cfg, files_dir, guid)
    if audit:
        tabs["Empire"]["Audit"].append(
            "<p>" + _iframe(audit, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating build advisor")
    advisor = build_advisor(frames, ref, cfg, files_dir, guid)
    if advisor:
        tabs["Market"]["Build Advisor"].append(
            "<p>" + _iframe(advisor, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating market overview")
    market = build_market(frames, ref, cfg, files_dir, guid)
    if market:
        tabs["Market"]["Overview"].append(
            "<p>" + _iframe(market, "width:100%;height:1600px;", lazy=True)
            + "</p>")

    log("Generating sunburst plots")
    for src in build_sunbursts(frames, ref, cfg, files_dir, guid):
        tab, sub = _categorize_sunburst(src)
        tabs[tab][sub].append(_iframe(src, half, lazy=True))

    log("Generating tables")
    for src in build_tables(frames, ref, cfg, files_dir, guid):
        tab, sub = (("Universe", "Contested") if "contested" in src.lower()
                    else ("Trade", "Earnings"))
        tabs[tab][sub].append(
            "<p>" + _iframe(src, table, lazy=True) + "</p>")

    # drop empty sub-tabs, then empty tabs (fresh saves lack e.g. history)
    tabs = {name: {sub: c for sub, c in subs.items() if c}
            for name, subs in tabs.items()}
    tabs = {name: subs for name, subs in tabs.items() if subs}

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
        parts.append(
            f"<button{active} data-tab='{_slug(name)}'>{name}</button>")
    parts.append("</nav>")
    for i, (name, subs) in enumerate(tabs.items()):
        active = " active" if i == 0 else ""
        nosub = " nosub" if len(subs) == 1 else ""
        parts.append(f"<section class='tab{active}{nosub}' "
                     f"data-tab='{_slug(name)}'>")
        if len(subs) > 1:
            parts.append("<div class='subnav'>")
            for j, sub in enumerate(subs):
                sactive = " class='active'" if j == 0 else ""
                parts.append(f"<button{sactive} data-sub='{_slug(sub)}'>"
                             f"{sub}</button>")
            parts.append("</div>")
        for j, (sub, content) in enumerate(subs.items()):
            sactive = " active" if j == 0 else ""
            parts.append(f"<div class='subpane{sactive}' "
                         f"data-sub='{_slug(sub)}'>")
            parts.extend(content)
            parts.append("</div>")
        parts.append("</section>")
    parts.append("</body></html>")

    out = cfg.output_dir / f"dashboard_{guid}.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
