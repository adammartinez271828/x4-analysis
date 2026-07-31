"""Empire → Combat: kills, losses, captures.

Four sections, all fed by the merged log history (which outlives the
game's own rolling window) plus the save's lifetime counters:

- **Personal combat record** — the save's own `<stats>` counters (kills,
  boarding, ranks). These are the PLAYER'S OWN actions, not the fleet's
  (E-148; the empire-wide reading E-147 was falsified by the fleet's
  bounty-paid kills alone exceeding `ships_destroyed`), and the card
  says so.
- **Losses** — every player object the log ever recorded as destroyed,
  with the killer and a killer-faction summary. This is the full merged
  history, not the old "Last 50 Destroyed Objects" table it replaced.
- **Bounty-confirmed kills per ship** — the ONLY per-ship kill
  attribution the game logs: faction bounty payouts (`Combat Reward`).
  Kills nobody witnessed and paid for exist only in the aggregate
  counters above.
- **Captures & claims** — abandoned-ship sightings and forced-bail
  events.

Everything here concerns the player's own assets and the log text the
game wrote for them, so `spoilers_hide` has nothing to hide: no
undiscovered sector or object name can reach the page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from .common import DARK_BG, DARK_FG, DARK_MUTED

_DT_CSS = "lib/datatables.min.css"
_DT_JS = "lib/datatables.min.js"
_JQ_JS = "lib/jquery.min.js"

_FAC_TAG_RE = re.compile(r"^([A-Z]{3})\b")

#: stat id -> label, grouped into the cards of the combat record
_KILL_STATS = [
    ("ships_destroyed", "Ships destroyed"),
    ("capships_destroyed", "Capital ships"),
    ("xenon_ships_destroyed", "Xenon ships"),
    ("khaak_ships_destroyed", "Kha'ak ships"),
    ("modules_destroyed", "Station modules"),
    ("turrets_destroyed", "Turrets"),
    ("adsigns_destroyed", "Advertisement signs"),
]
_BOARD_STATS = [
    ("boarding_attempts", "Boarding attempts"),
    ("ships_boarded", "Ships boarded"),
    ("ships_claimed", "Ships claimed"),
    ("pilots_bailed", "Pilots bailed"),
]
_RANK_STATS = [
    ("fight_rank", "Fight rank"),
    ("fight_score", "Fight score"),
    ("bullets_fired", "Bullets fired"),
    ("bullets_hit", "Bullets hit"),
    ("bullets_hit_percent", "Hit rate %"),
    ("missiles_fired", "Missiles fired"),
]


def _table(df: pd.DataFrame, tid: str, empty: str = "Nothing recorded.") -> str:
    if df is None or df.empty:
        return f"<p class='ok'>{empty}</p>"
    return df.to_html(index=False, border=0, table_id=tid,
                      classes="display nowrap", justify="left", escape=False,
                      float_format=lambda v: f"{v:,.1f}")


def killer_faction(killer: str, short_by_tag: dict) -> str:
    """Short faction code from a killer string like
    "XEN Raiding Party F (GZM-478)" — the leading 3-letter tag when it is
    a known faction short, "?" otherwise (unnamed killers, mod content,
    and the rows the log left without a killer at all)."""
    m = _FAC_TAG_RE.match(str(killer or "").strip())
    if not m:
        return "?"
    return m.group(1) if m.group(1) in short_by_tag else "?"


def _stat_cards(stats: dict) -> str:
    def value(sid: str) -> str:
        v = stats.get(sid)
        if v is None or pd.isna(v):
            return "—"
        return f"{float(v):,.0f}"

    def block(title: str, items: list) -> str:
        cells = "".join(
            f"<div class='stat'><div class='sv'>{value(sid)}</div>"
            f"<div class='sl'>{label}</div></div>"
            for sid, label in items)
        return (f"<div class='scard'><h4>{title}</h4>"
                f"<div class='stats'>{cells}</div></div>")

    return ("<div class='scards'>"
            + block("Kills", _KILL_STATS)
            + block("Boarding &amp; claims", _BOARD_STATS)
            + block("Gunnery &amp; rank", _RANK_STATS)
            + "</div>")


def build_combat(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
                 guid: str) -> str | None:
    stats = frames.player_stats or {}
    destroyed = frames.destroyed
    rewards = frames.combat_rewards
    claims = frames.ship_claims
    bails = frames.pilot_bails
    if not stats and all(df is None or df.empty
                         for df in (destroyed, rewards, claims, bails)):
        return None
    log("-> Empire combat")

    short_by_tag = {s: s for s in ref.faction_short.values()}
    name_of = {s: ref.name_of_short(s) for s in short_by_tag}

    # ---- losses ------------------------------------------------------------
    losses = pd.DataFrame()
    by_killer = pd.DataFrame()
    if destroyed is not None and not destroyed.empty:
        d = destroyed.copy()
        d["killer"] = d["killer"].fillna("")
        d["fac"] = [killer_faction(k, short_by_tag) for k in d["killer"]]
        hours = (d["HoursAgo"] if "HoursAgo" in d
                 else (frames.time_now - d["time"]) / 3600.0)
        losses = pd.DataFrame({
            "Hours ago": hours.round(1).values,
            "Object": d["object"].fillna("?").values,
            "Sector": d["location"].fillna("?").values,
            "Killed by": d["killer"].replace("", "—").values,
            "Killer faction": [
                f"{f} <span class='note'>{name_of.get(f, 'unknown')}</span>"
                if f != "?" else "<span class='note'>unknown</span>"
                for f in d["fac"]],
            "Timestamp": d["time"].values,
        }).sort_values("Hours ago", ignore_index=True)
        agg = (d.groupby("fac").size().sort_values(ascending=False)
               .reset_index(name="Losses"))
        by_killer = pd.DataFrame({
            "Killer faction": [
                (f"{f} — {name_of.get(f, 'unknown')}" if f != "?"
                 else "unknown / unattributed") for f in agg["fac"]],
            "Losses": agg["Losses"].values,
        })

    # ---- bounty-confirmed kills per ship -------------------------------------
    per_ship = pd.DataFrame()
    n_rewards = 0
    total_bounty = 0.0
    if rewards is not None and not rewards.empty:
        r = rewards.copy()
        # bounty_cr repeats the whole payout on every credited row: the
        # empire total sums over DISTINCT rewards, the per-ship column
        # keeps the shared payout on each credited ship (and says so)
        per_reward = r.drop_duplicates("reward")
        n_rewards = len(per_reward)
        total_bounty = float(per_reward["bounty_cr"].fillna(0).sum())
        r["who"] = (r["ship.name"].astype(str) + " ("
                    + r["ship.code"].astype(str) + ")")
        grp = r.groupby(["who", "kind"], as_index=False).agg(
            rewards_n=("reward", "nunique"),
            bounty=("bounty_cr", "sum"),
            factions=("faction", "nunique"),
            last=("time", "max"))
        grp = grp.sort_values("rewards_n", ascending=False, ignore_index=True)
        per_ship = pd.DataFrame({
            "Ship / station": grp["who"].values,
            "Kind": grp["kind"].replace("", "?").values,
            "Rewards": grp["rewards_n"].values,
            "Bounty credited (Cr)":
                grp["bounty"].fillna(0).round().astype("int64").values,
            "Paying factions": grp["factions"].values,
            "Hours ago (last)":
                ((frames.time_now - grp["last"]) / 3600.0).round(1).values,
        })

    # ---- captures & claims ----------------------------------------------------
    claims_tbl = pd.DataFrame()
    if claims is not None and not claims.empty:
        c = claims.sort_values("time", ascending=False)
        claims_tbl = pd.DataFrame({
            "Hours ago": ((frames.time_now - c["time"]) / 3600.0).round(1).values,
            "Spotted by": (c["finder"].astype(str) + " ("
                           + c["finder.code"].astype(str) + ")").values,
            "Sector": c["sector"].values,
            "Abandoned ship": (c["claimed"].astype(str) + " ("
                               + c["claimed.code"].astype(str) + ")").values,
        })
    bails_tbl = pd.DataFrame()
    if bails is not None and not bails.empty:
        b = bails.sort_values("time", ascending=False)
        bails_tbl = pd.DataFrame({
            "Hours ago": ((frames.time_now - b["time"]) / 3600.0).round(1).values,
            "Ship": b["ship"].values,
            "Sector": b["sector"].values,
        })

    n_losses = 0 if losses.empty else len(losses)
    chips = " ".join([
        f"<span class='chip {'chip0' if n_losses == 0 else 'chip1'}'>"
        f"Losses: {n_losses}</span>",
        f"<span class='chip chip0'>Bounty rewards: {n_rewards}</span>",
        f"<span class='chip chip0'>Abandoned ships found: "
        f"{0 if claims_tbl.empty else len(claims_tbl)}</span>",
        f"<span class='chip chip0'>Forced bails: "
        f"{0 if bails_tbl.empty else len(bails_tbl)}</span>",
    ])

    body = [
        "<h3>Personal combat record</h3>",
        "<p class='note'>The game's own lifetime counters, straight from "
        "the save's <code>&lt;stats&gt;</code> block. These count "
        "<b>your personal actions only</b> — your fleet's kills are not "
        "in them (its bounty-paid kills alone exceed the ships-destroyed "
        "counter, and capital kills by your fleet leave the capital "
        "counter untouched). The empire's attributable kills are the "
        "bounty table below. A dash means the save carries no such "
        "counter.</p>",
        _stat_cards(stats) if stats
        else "<p class='ok'>No &lt;stats&gt; block in this save.</p>",

        "<h3>Losses <small>(" + str(n_losses) + ")</small></h3>",
        "<p class='note'>Every object of yours the log ever recorded as "
        "destroyed — the full merged history, which reaches further back "
        "than the game's own rolling logbook. Killer faction is read from "
        "the leading faction tag of the killer's name; “unknown” means no "
        "killer was logged or the tag is not a known faction.</p>",
        _table(losses, "t1", "No losses recorded — nothing of yours has "
                             "been destroyed."),
    ]
    if not by_killer.empty:
        body.append("<h4>Losses by killer faction</h4>")
        body.append(_table(by_killer, "t2"))

    body += [
        "<h3>Bounty-confirmed kills per ship <small>("
        + f"{n_rewards} rewards, {total_bounty:,.0f} Cr" + ")</small></h3>",
        "<p class='note'>Faction bounty payouts are the <b>only</b> "
        "per-ship kill attribution the game logs — a kill counts here "
        "only if a faction witnessed it and paid for it. Unwitnessed "
        "kills exist solely in the aggregate counters above, so this "
        "table is a lower bound on what each ship has killed. One reward "
        "shared by several ships is credited to each of them: the Bounty "
        "column therefore double-counts shared payouts across rows, while "
        "the total in the heading counts each reward once. Rows are keyed "
        "on the name and code the log recorded at the time, which is a "
        "heuristic, not an identity: rename a ship and its older rewards "
        "stay under the old name, and codes are recycled after a "
        "death.</p>",
        _table(per_ship, "t3", "No combat rewards in the logged history."),

        "<h3>Captures &amp; claims</h3>",
        "<p class='note'>Abandoned ships your ships spotted, with the "
        "standing “claim if possible” response. The log records the "
        "sighting, not the outcome — the save's <code>ships_claimed</code> "
        "counter above is the only total of successful claims.</p>",
        _table(claims_tbl, "t4", "No abandoned ships found."),
        "<h4>Pilots forced to leave their ship</h4>",
        "<p class='note'>An attack or boarding made the pilot bail, "
        "leaving the hull claimable. The log names no actor, so these "
        "cannot be attributed to one of your ships.</p>",
        _table(bails_tbl, "t5", "No forced bails recorded."),
    ]

    tables = [("t1", losses), ("t2", by_killer), ("t3", per_ship),
              ("t4", claims_tbl), ("t5", bails_tbl)]
    tables_js = "\n".join(
        f"$('#{tid}').DataTable({{order: [], pageLength: 10}});"
        for tid, df in tables if not df.empty)

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<link rel='stylesheet' href='{_DT_CSS}'>
<script src='{_JQ_JS}'></script><script src='{_DT_JS}'></script>
<style>
body{{font-family:sans-serif;margin:8px;background:{DARK_BG};color:{DARK_FG};}}
h3{{margin:22px 0 2px 0;}} h3 small{{color:{DARK_MUTED};font-weight:normal;}}
h4{{margin:18px 0 2px 0;}}
.note{{color:{DARK_MUTED};font-size:12px;margin:2px 0 8px 0;}}
.ok{{color:#4ecf71;}}
.neg{{color:#ff6b6b;}} .warn{{color:#e8b84e;}}
.chip{{display:inline-block;padding:3px 10px;border-radius:12px;margin:2px;
  font-size:12px;border:1px solid #444;}}
.chip0{{color:{DARK_MUTED};}} .chip1{{color:#e8b84e;border-color:#e8b84e;}}
.scards{{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;}}
.scard{{background:#252525;border:1px solid #3a3a3a;border-radius:8px;
  padding:10px 14px;flex:1 1 300px;}}
.scard h4{{margin:0 0 8px 0;}}
.stats{{display:flex;flex-wrap:wrap;gap:14px;}}
.stat{{min-width:86px;}}
.sv{{font-size:20px;font-weight:bold;}}
.sl{{color:{DARK_MUTED};font-size:11px;}}
code{{color:{DARK_MUTED};}}
table.dataTable, table.dataTable th, table.dataTable td{{color:{DARK_FG};}}
table.dataTable.display tbody tr{{background:{DARK_BG};}}
table.dataTable.display tbody tr.odd{{background:#252525;}}
table.dataTable.display tbody tr:hover{{background:#333;}}
table.dataTable thead th, table.dataTable.no-footer{{border-color:#555;}}
.dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter,
.dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_paginate,
.dataTables_wrapper .dataTables_paginate .paginate_button{{color:{DARK_FG} !important;}}
.dataTables_wrapper .dataTables_paginate .paginate_button.current,
.dataTables_wrapper .dataTables_paginate .paginate_button:hover{{
  color:#fff !important;background:#3a3a3a;border-color:#555;}}
.dataTables_wrapper input, .dataTables_wrapper select{{
  background:#2a2a2a;color:{DARK_FG};border:1px solid #555;}}
</style></head><body>
<h3 style='margin-top:4px'>Combat record</h3>
<p class='note'>What you have killed, what you have lost, and what you
took intact.</p>
<p>{chips}</p>
{"".join(body)}
<script>$(function() {{ {tables_js} }});</script>
<script>
(function() {{
  function post() {{
    parent.postMessage({{x4h: document.body.scrollHeight + 24}}, '*');
  }}
  new ResizeObserver(post).observe(document.body);
  window.addEventListener('load', function() {{ setTimeout(post, 400); }});
}})();
</script>
</body></html>"""

    name = f"Empire Combat_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"
