"""Diplomacy views — player standings (Empire) and the faction relations
matrix (Universe).

Both are self-contained client-rendered pages (the map.py pattern): a `_PAGE`
template with `__TOKEN__` placeholders and a shared `diplomacy_page.js` that
branches on the payload's `view`. Everything comes from the savegame's
`universe/factions` block (frames.faction_*): the effective standing is the
active booster when the pair has one, else the base relation, clamped to
[-1, 1], as of the save (E-145). See docs/models/faction-relations-model.md.

`build_standing_history` is the odd one out: a plain plotly widget (dark
theme via common.save_widget) stacked under the standings table, drawn from
the LOG's absolute per-event rank readings rather than the save's relations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import plotly.graph_objects as go

from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from .common import (DARK_BG, DARK_FG, DARK_MUTED,
                     fullscreen_button_html, save_widget)

# Canonical roster + display order, grouped by allegiance (player first). Only
# factions present in this save's data are emitted; the rest silently drop, so
# non-DLC saves just show fewer rows. Generic buckets (civilian, smuggler,
# outlaw, ownerless, the anonymous visitor### factions) are deliberately absent.
_ORDER = [
    "player",
    "argon", "antigone", "hatikvah", "alliance",       # Argon sphere
    "teladi", "ministry",                              # Teladi
    "paranid", "holyorder", "trinity", "holyorderfanatic",  # Paranid
    "split", "freesplit", "fallensplit",               # Split
    "terran", "pioneers",                              # Terran
    "boron",                                           # Boron
    "scaleplate", "buccaneers", "loanshark", "scavenger",   # pirates/traders
    "yaki", "kaori", "court",
    "criminal", "xenon", "khaak",                      # hostiles
]


def _uivalue(r: float) -> float:
    """Map a relation (-1..1) to the in-game -30..+30 rank value. Fixed
    log formula from libraries/factions.xml; linear in the near-zero band."""
    a = abs(r)
    if a <= 1e-12:
        return 0.0
    if a <= 0.0032:
        uv = r / 0.00064                       # linear, +/-5 at +/-0.0032
    else:
        uv = math.copysign(10.0 * math.log10(a * 1000.0), r)
    return round(max(-30.0, min(30.0, uv)), 1)


def _rank(r: float) -> str:
    """A single standing label from the documented relation bands."""
    if r >= 0.5:
        return "Ally"
    if r >= 0.1:
        return "Friend"
    if r >= 0.01:
        return "Friendly"
    if r > -0.01:
        return "Neutral"
    if r <= -0.999:
        return "War"
    if r <= -0.32:
        return "Hostile"
    return "Enemy"


def _present(frames: Frames) -> set[str]:
    fr = frames.faction_relations
    if fr is None or len(fr) == 0:
        return set()
    return set(fr["faction"]) | set(fr["other"])


def _fac_meta(ref: RefData, fid: str) -> dict:
    return {
        "id": fid,
        "name": ref.faction_name.get(fid, fid.capitalize()),
        "short": ref.faction_short.get(fid, fid[:3].upper()),
        "colour": ref.faction_colour.get(fid, "#808080"),
    }


def _roster(frames: Frames) -> list[str]:
    present = _present(frames)
    return [f for f in _ORDER if f == "player" or f in present]


def _standings_payload(frames: Frames, ref: RefData) -> dict:
    fr = frames.faction_relations
    pr = fr[fr["faction"] == "player"].set_index("other") if fr is not None \
        else None
    # discount faction X grants the player: faction_discounts (X, player, d)
    disc: dict[str, float] = {}
    fd = frames.faction_discounts
    if fd is not None and len(fd):
        for _, r in fd[fd["other"] == "player"].iterrows():
            disc[str(r["faction"])] = float(r["discount"])
    # licences the player has unlocked FROM each faction: player's <licences>
    # list each type with the factions it applies to
    lic: dict[str, int] = {}
    fl = frames.faction_licences
    if fl is not None and len(fl):
        for _, r in fl[fl["faction"] == "player"].iterrows():
            for other in str(r["factions"] or "").split():
                lic[other] = lic.get(other, 0) + 1

    rows = []
    for fid in _roster(frames):
        if fid == "player":
            continue
        base = booster = eff = 0.0
        if pr is not None and fid in pr.index:
            base = float(pr.loc[fid, "base"])
            booster = float(pr.loc[fid, "booster"])
            # composition lives in frames.py: a booster replaces the base
            # (E-145). Never recompute it here.
            eff = max(-1.0, min(1.0, float(pr.loc[fid, "effective"])))
        m = _fac_meta(ref, fid)
        m.update({
            "base": round(base, 4), "booster": round(booster, 4),
            "eff": round(eff, 4), "uiv": _uivalue(eff), "rank": _rank(eff),
            "discount": round(disc.get(fid, 0.0), 3),
            "licences": lic.get(fid, 0),
        })
        rows.append(m)

    treasury = None
    fm = frames.faction_meta
    if fm is not None and len(fm):
        prow = fm[fm["faction"] == "player"]
        if len(prow):
            treasury = float(prow.iloc[0]["account_cr"])

    return {
        "view": "standings",
        "player_name": getattr(frames, "player_faction_name", "Player"),
        "treasury": treasury,
        "rows": rows,
    }


def _relations_payload(frames: Frames, ref: RefData) -> dict:
    roster = _roster(frames)
    fr = frames.faction_relations
    eff: dict[tuple, float] = {}
    if fr is not None and len(fr):
        for _, r in fr.iterrows():
            eff[(str(r["faction"]), str(r["other"]))] = float(r["effective"])
    facs = [_fac_meta(ref, f) for f in roster]
    # directional matrix: values[i][j] = effective(roster[i] -> roster[j]),
    # None on the diagonal (a faction has no relation with itself)
    values = []
    for a in roster:
        row = []
        for b in roster:
            row.append(None if a == b else round(eff.get((a, b), 0.0), 4))
        values.append(row)
    return {"view": "relations", "factions": facs, "values": values}


_PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Diplomacy</title>
<link rel='stylesheet' href='lib/datatables.min.css'>
<script src='lib/jquery.min.js'></script>
<script src='lib/datatables.min.js'></script>
<style>
html,body{margin:0;background:__BG__;color:__FG__;
font-family:'Open Sans',verdana,arial,sans-serif;font-size:13px;}
#wrap{padding:16px 20px 40px;}
h1{font-size:18px;margin:0 0 4px;font-weight:600;}
.sub{color:__MUTED__;font-size:12px;margin:0 0 16px;}
.chip{display:inline-block;width:10px;height:10px;border-radius:2px;
margin-right:7px;vertical-align:middle;border:1px solid rgba(255,255,255,0.2);}
table.dataTable{color:__FG__;border-collapse:collapse;width:100%;}
table.dataTable thead th{color:__MUTED__;border-bottom:1px solid #3a3a3a;
font-weight:600;text-align:left;}
table.dataTable td{border-bottom:1px solid #2a2a2a;padding:5px 8px;}
table.dataTable tbody tr:hover{background:#262626;}
.rank{padding:1px 7px;border-radius:9px;font-size:11px;font-weight:600;}
.num{text-align:right;font-variant-numeric:tabular-nums;}
.dataTables_wrapper .dataTables_filter input,
.dataTables_wrapper .dataTables_length select{background:#2a2a2a;color:__FG__;
border:1px solid #3a3a3a;border-radius:3px;}
.dataTables_wrapper{color:__MUTED__;}
/* relations heatmap */
#heat{overflow:auto;}
#heat svg{font-size:10px;}
#heat text{fill:__FG__;}
#heat text.mut{fill:__MUTED__;}
#tip{position:fixed;pointer-events:none;display:none;z-index:30;max-width:260px;
background:#0d0d0d;border:1px solid #444;border-radius:5px;padding:7px 9px;
font-size:12px;color:__FG__;box-shadow:0 2px 10px rgba(0,0,0,0.6);}
.legwrap{margin:14px 0 4px;color:__MUTED__;font-size:11px;}
</style></head><body>
<div id='wrap'><div id='content'></div></div>
<div id='tip'></div>
__FSBTN__
<script>window.X4DIPLO = __DATA__;</script>
<script>__JS__</script>
</body></html>"""


def _write_page(payload: dict, files_dir: Path, guid: str, name: str) -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    js = Path(__file__).with_name("diplomacy_page.js").read_text(
        encoding="utf-8")
    html = (
        _PAGE
        .replace("__JS__", js)
        .replace("__DATA__", data)
        .replace("__FSBTN__", fullscreen_button_html(resize_plotly=False))
        .replace("__BG__", DARK_BG)
        .replace("__FG__", DARK_FG)
        .replace("__MUTED__", DARK_MUTED)
    )
    fname = f"{name}_{guid}.html"
    (files_dir / fname).write_text(html, encoding="utf-8")
    return f"files/{fname}"


def build_diplomacy(frames: Frames, ref: RefData, cfg: Config,
                    files_dir: Path, guid: str) -> tuple[str, str] | None:
    """Emit the Standings (Empire) and Relations (Universe) pages.

    Returns (standings_src, relations_src), or None when the save carries no
    faction relations (older snapshots pre-dating this extraction).
    """
    if getattr(frames, "faction_relations", None) is None \
            or len(frames.faction_relations) == 0:
        return None
    standings = _write_page(_standings_payload(frames, ref), files_dir, guid,
                            "Diplomacy standings")
    relations = _write_page(_relations_payload(frames, ref), files_dir, guid,
                            "Diplomacy relations")
    return standings, relations


# ---------------------------------------------------------------------------
# Standing over time (Empire -> Standings, below the standings table)
# ---------------------------------------------------------------------------

def build_standing_history(frames: Frames, ref: RefData, files_dir: Path,
                           guid: str) -> str | None:
    """A step line per faction of the player's standing rank over time.

    Every point is a HARD reading: the game's "Reputation gained/lost" log
    entries carry the absolute -30..+30 rank AFTER the change
    (frames.reputation_events), so the line is measured, never accumulated
    from deltas — most entries carry no numeric delta at all, which is also
    why there is deliberately no contribution-by-type breakdown here.

    The log is a rolling window, so the chart only reaches as far back as
    the merged history goes; the covered span (coverage table, stream
    `log:`) is stated in the subtitle. Each line is extended flat from its
    last event to the right edge at the last known rank — that tail is an
    assumption of "nothing changed", not a measurement.

    Returns the widget src, or None when the history holds no reputation
    entries.
    """
    ev = getattr(frames, "reputation_events", None)
    if ev is None or len(ev) == 0:
        return None
    ev = ev.dropna(subset=["current_rank"]).sort_values("time")
    if ev.empty:
        return None

    t_end = max(float(ev["time"].max()), float(frames.time_now or 0.0))
    order = {fid: i for i, fid in enumerate(_ORDER)}
    latest = ev.groupby("faction")["current_rank"].last()
    # strongest feelings first, so the legend opens on what matters
    factions = sorted(latest.index,
                      key=lambda f: (-abs(float(latest[f])),
                                     order.get(f, len(order)), f))

    fig = go.Figure()
    for fid in factions:
        meta = _fac_meta(ref, fid)
        g = ev[ev["faction"] == fid]
        xs = [float(t) / 3600.0 for t in g["time"]]
        ys = [float(v) for v in g["current_rank"]]
        hover = []
        for _, r in g.iterrows():          # dotted column names: no itertuples
            reason = r["reason"] if isinstance(r["reason"], str) else "unknown"
            step = ("sub-rank tick" if bool(r["subunit"])
                    else f"{float(r['delta']):+.0f}")
            hover.append(f"{reason}<br>{step}")
        if xs[-1] < t_end / 3600.0:        # flat carry to the right edge
            xs.append(t_end / 3600.0)
            ys.append(ys[-1])
            hover.append("no further change logged")
        fig.add_trace(go.Scatter(
            x=xs, y=ys, name=f"{meta['short']} {meta['name']}",
            mode="lines", line={"shape": "hv", "width": 2,
                                "color": meta["colour"]},
            text=hover,
            hovertemplate=("%{fullData.name}<br>%{x:.1f} h &mdash; rank "
                           "%{y:.0f}<br>%{text}<extra></extra>"),
        ))

    cov = list(getattr(frames, "log_coverage", []) or [])
    if cov:
        spans = ", ".join(f"{a / 3600.0:.0f}&ndash;{b / 3600.0:.0f}"
                          for a, b in cov)
        note = (f"log history covers game hours {spans}"
                + (" (gaps between spans: the game discarded that stretch)"
                   if len(cov) > 1 else ""))
    else:
        note = (f"log history covers game hours "
                f"{float(ev['time'].min()) / 3600.0:.0f}&ndash;"
                f"{t_end / 3600.0:.0f}")
    note += ("; every point is the rank the game logged after the event, "
             "lines carried flat to the right edge")

    fig.update_layout(
        title={"text": "Faction standing over time<br>"
                       f"<span style='font-size:11px;color:{DARK_MUTED}'>"
                       f"{note}</span>"},
        xaxis={"title": "game time (hours)"},
        yaxis={"title": "standing rank", "range": [-30, 30],
               "zeroline": True, "zerolinecolor": DARK_MUTED,
               "dtick": 10},
        hovermode="closest",
        legend={"title": {"text": "faction"}},
        margin={"l": 60, "r": 20, "t": 70, "b": 50},
    )
    return save_widget(fig, files_dir, "Standing history", guid)
