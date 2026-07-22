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
            "faction": ["player"], "account": [500000.0]}),
        faction_licences=pd.DataFrame({
            "faction": ["player"], "type": ["capitalship"],
            "factions": ["argon antigone"]}),
        player_faction_name="Testers",
    )


def test_standings_payload():
    p = _standings_payload(_frames(), _ref())
    assert p["view"] == "standings"
    assert p["treasury"] == 500000.0
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
