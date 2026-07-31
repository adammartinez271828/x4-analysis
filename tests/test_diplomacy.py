"""Diplomacy: parser collection of the factions block, standing maths, and
the standings / relations payload builders."""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from x4analyzer.save.parser import parse_savegame
from x4analyzer.viz.diplomacy import (
    _rank, _relations_payload, _standings_payload, _uivalue,
)

FIXTURE = """<?xml version="1.0"?>
<savegame>
  <info><game guid="G-1" version="900" time="1000"/></info>
  <universe>
    <factions>
      <faction id="player">
        <relations>
          <relation faction="alliance" relation="1"/>
          <relation faction="xenon" relation="-1"/>
          <booster faction="argon" relation="0.24" time="900.5"/>
        </relations>
        <discounts>
          <booster faction="argon" amount="0.15" time="800"/>
        </discounts>
        <licences>
          <licence type="capitalship" factions="argon alliance"/>
          <licence type="police" factions="argon"/>
        </licences>
        <account id="[0x1]" amount="500000"/>
      </faction>
      <faction id="argon">
        <relations>
          <relation faction="antigone" relation="0.67"/>
          <relation faction="xenon" relation="-1"/>
          <relation faction="scaleplate" relation="-0.32"/>
          <booster faction="player" relation="0.24" time="900.5"/>
        </relations>
        <discounts>
          <booster faction="player" amount="0.15" time="800"/>
        </discounts>
        <account id="[0x2]" amount="99"/>
      </faction>
      <faction id="antigone">
        <relations>
          <relation faction="scaleplate" relation="-0.1"/>
        </relations>
      </faction>
    </factions>
  </universe>
</savegame>"""


@pytest.fixture(params=["plain", "gz"])
def save_file(tmp_path, request):
    import gzip
    if request.param == "gz":
        p = tmp_path / "save.xml.gz"
        with gzip.open(p, "wt") as fh:
            fh.write(FIXTURE)
    else:
        p = tmp_path / "save.xml"
        p.write_text(FIXTURE)
    return p


def test_parser_collects_factions(save_file):
    d = parse_savegame(save_file)
    rel = {(a, b): v for a, b, v in d.faction_relations}
    assert rel[("player", "alliance")] == 1.0
    assert rel[("argon", "antigone")] == 0.67
    assert rel[("argon", "scaleplate")] == -0.32
    assert rel[("antigone", "scaleplate")] == -0.1     # asymmetry preserved

    boost = {(a, b): (v, t) for a, b, v, t in d.faction_boosters}
    assert boost[("player", "argon")] == (0.24, "900.5")
    # a discount <booster amount=> must NOT be read as a relation booster
    assert ("player", "argon") not in \
        {(a, b) for a, b, v, t in d.faction_discounts if v == 0.24}

    disc = {(a, b): v for a, b, v, t in d.faction_discounts}
    assert disc[("argon", "player")] == 0.15

    acct = dict(d.faction_accounts)
    assert acct["player"] == 500000.0 and acct["argon"] == 99.0

    lic = {(f, t): facs for f, t, facs in d.faction_licences}
    assert lic[("player", "capitalship")] == "argon alliance"


def test_uivalue_anchors():
    # fixed anchors documented in libraries/factions.xml
    for r, uv in [(1.0, 30), (0.5, 27), (0.1, 20), (0.032, 25 - 10),
                  (0.01, 10), (0.0032, 5)]:
        assert round(_uivalue(r)) == uv
    assert _uivalue(-1.0) == -30.0
    assert _uivalue(0.0) == 0.0
    assert _uivalue(-0.5) == -_uivalue(0.5)     # sign symmetry


def test_rank_bands():
    assert _rank(1.0) == "Ally"
    assert _rank(0.5) == "Ally"
    assert _rank(0.2) == "Friend"
    assert _rank(0.02) == "Friendly"
    assert _rank(0.0) == "Neutral"
    assert _rank(-0.5) == "Hostile"
    assert _rank(-1.0) == "War"


def _ref():
    ids = ["player", "argon", "antigone", "xenon", "civilian", "visitor001"]
    return SimpleNamespace(
        faction_name={i: i.capitalize() for i in ids},
        faction_short={i: i[:3].upper() for i in ids},
        faction_colour={i: "#123456" for i in ids},
    )


def _frames():
    # player -> argon via booster (0.24), player -> alliance base 1.0 (alliance
    # absent from ref/order -> dropped); argon -> antigone 0.67, etc.
    rel = pd.DataFrame({
        "faction": ["player", "player", "argon", "argon", "antigone"],
        "other":   ["argon", "xenon", "antigone", "xenon", "xenon"],
        "base":    [0.0, -1.0, 0.67, -1.0, -1.0],
        "booster": [0.24, 0.0, 0.0, 0.0, 0.0],
        "effective": [0.24, -1.0, 0.67, -1.0, -1.0],
    })
    return SimpleNamespace(
        faction_relations=rel,
        faction_discounts=pd.DataFrame({
            "faction": ["argon"], "other": ["player"], "discount": [0.15]}),
        faction_meta=pd.DataFrame({
            "faction": ["player"], "account_cr": [5000.0]}),
        faction_licences=pd.DataFrame({
            "faction": ["player"], "type": ["capitalship"],
            "factions": ["argon antigone"]}),
        player_faction_name="Testers",
    )


def test_standings_payload():
    p = _standings_payload(_frames(), _ref())
    assert p["view"] == "standings"
    assert p["treasury"] == 5000.0
    rows = {r["id"]: r for r in p["rows"]}
    # only real factions present in the data, player excluded from its own list
    assert "player" not in rows and "visitor001" not in rows
    assert rows["argon"]["eff"] == pytest.approx(0.24)
    assert rows["argon"]["rank"] == "Friend"
    assert rows["argon"]["discount"] == 0.15         # argon grants player 15%
    assert rows["argon"]["licences"] == 1            # player holds 1 from argon
    assert rows["antigone"]["licences"] == 1
    assert rows["xenon"]["eff"] == -1.0 and rows["xenon"]["rank"] == "War"
    # a faction present in the matrix but with no player relation -> Neutral
    assert rows["antigone"]["eff"] == 0.0
    assert rows["antigone"]["rank"] == "Neutral"


def test_v_faction_standing_composition():
    """v_faction_standing must mirror the frames pivot: booster if the pair
    has one (even a negative or zero-summing one), else base, clamped."""
    import sqlite3
    from x4analyzer.db import schema
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE save (save_id INTEGER)")
    conn.execute("INSERT INTO save VALUES (1)")
    conn.execute(schema.TABLES["faction_relation"])
    for name in ("current_save", "v_faction_standing"):
        conn.execute(schema.VIEWS[name])
    rows = [
        ("player", "yaki", "base", -0.32), ("player", "yaki", "booster", 0.2),
        ("player", "split", "base", -0.032),
        ("player", "split", "booster", -0.01004),
        ("player", "scaleplate", "base", -0.0032),      # no booster
        ("player", "hydra", "booster", 0.0),            # booster present, 0.0
        ("player", "hydra", "base", -0.5),
        ("player", "over", "base", 0.4),                # clamp
        ("player", "over", "booster", 1.4),
        ("player", "argon", "discount", 0.15),          # ignored kind
    ]
    conn.executemany(
        "INSERT INTO faction_relation (save_id, faction, other, kind, value)"
        " VALUES (1,?,?,?,?)", rows)
    got = {o: (b, bo, e) for o, b, bo, e in conn.execute(
        "SELECT other, base, booster, effective FROM v_faction_standing")}
    assert got["yaki"] == (-0.32, 0.2, 0.2)
    assert got["split"] == pytest.approx((-0.032, -0.01004, -0.01004))
    assert got["scaleplate"] == (-0.0032, 0.0, -0.0032)
    assert got["hydra"] == (-0.5, 0.0, 0.0)       # a 0.0 booster still wins
    assert got["over"] == (0.4, 1.4, 1.0)         # clamped
    assert "argon" not in got                     # discount-only pair


def test_standings_payload_takes_effective_verbatim():
    """The composition (booster replaces base, E-145) lives in frames.py —
    the payload must not recompute it as base + booster (E-083, FALSIFIED)."""
    f = _frames()
    # yaki-shaped row: hostile base, positive story booster
    f.faction_relations = pd.concat([f.faction_relations, pd.DataFrame({
        "faction": ["player"], "other": ["antigone"], "base": [-0.32],
        "booster": [0.2], "effective": [0.2]})], ignore_index=True)
    rows = {r["id"]: r for r in _standings_payload(f, _ref())["rows"]}
    assert rows["antigone"]["eff"] == pytest.approx(0.2)     # not -0.12
    assert rows["antigone"]["rank"] == "Friend"
    assert rows["antigone"]["base"] == -0.32                 # raw values kept
    assert rows["antigone"]["booster"] == 0.2
    assert round(rows["antigone"]["uiv"]) == 23


# In-game rep-bar readings, 2026-07-31, taken a few game-hours after save
# 8E0C…/save_010 (save_id 79, t = 82,687 s), whose <factions> block holds the
# base/booster values below. They are the evidence for E-145 and against the
# additive law E-083; tests/readings.py is storage-specific, so they live here.
# Tolerances reflect post-save drift, not model slack:
#   yaki    exact 0.2 sits ON the rank-23 threshold (10^2.3/1000 = 0.19953),
#           so 22 and 23 are the same prediction.
#   split   the reading post-dates the save; the booster decayed/was traded
#           back toward 0, so only sign and band are asserted.
#   loans.  linear band, no meaningful decay in the interval: exact.
STANDING_READINGS = [
    # faction,      base,     booster,     in-game rank, tolerance
    ("yaki",       -0.32,     0.2,         22, 1.1),
    ("split",      -0.032,   -0.01004,     -6, 5.0),
    ("loanshark",  -0.0032,   0.0026712,    4, 0.5),
    ("scaleplate", -0.0032,   None,        -5, 0.5),
    ("buccaneers", -0.032,    None,       -15, 0.5),
    ("fallensplit", -0.0032,  None,        -5, 0.5),
    ("alliance",    1.0,      None,        30, 0.5),
]


@pytest.mark.parametrize("fid,base,booster,read,tol", STANDING_READINGS)
def test_ingame_standing_readings(fid, base, booster, read, tol):
    eff = base if booster is None else booster        # E-145: replace, not add
    assert _uivalue(eff) == pytest.approx(read, abs=tol), fid
    # the additive law would have missed the two big ones outright
    if booster is not None and base:
        add = _uivalue(max(-1.0, min(1.0, base + booster)))
        assert abs(add - read) > tol, f"{fid}: additive law not discriminated"


def test_relations_payload_directional():
    p = _relations_payload(_frames(), _ref())
    ids = [f["id"] for f in p["factions"]]
    assert ids[0] == "player"                         # player first
    assert "civilian" not in ids and "visitor001" not in ids
    ai, ni, xi = ids.index("argon"), ids.index("antigone"), ids.index("xenon")
    assert p["values"][ai][ni] == 0.67                # argon -> antigone
    assert p["values"][ai][xi] == -1.0                # argon -> xenon
    assert p["values"][ai][ai] is None                # diagonal (self)
    # a pair with no stored relation defaults to neutral 0.0
    assert p["values"][ni][ai] == 0.0                 # antigone -> argon unset
