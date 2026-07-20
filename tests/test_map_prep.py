"""Tests for the sector map data preparation (viz/map.py).

The payload builder is exercised with small synthetic frames/refdata
stand-ins (SimpleNamespace + DataFrames) — no savegame or game data needed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from x4analyzer.viz.map import (
    _UPX, _UPY, _labels, _layout_sectors, _payload, _resource_levels,
    _slot_xy,
)


def _ref(**over):
    base = dict(
        clusters=pd.DataFrame({
            "macro": ["cluster_a", "cluster_b"],
            "x": [0.0, 40_000_000.0],
            "z": [0.0, 17_320_000.0],
            "name": ["Alpha", "Beta"],
        }),
        sectors=pd.DataFrame({
            "cluster": ["cluster_a", "cluster_b", "cluster_b"],
            "macro": ["sec_a1", "sec_b1", "sec_b2"],
            "x": [0.0, -1e6, 1e6],
            "z": [0.0, 1e6, -1e6],
            "name": ["Alpha", "Beta I", "Beta II"],
        }),
        gates=pd.DataFrame({
            "sector_a": ["sec_a1", "sec_b1"],
            "sector_b": ["sec_b1", "sec_b2"],
        }),
        faction_colour={"argon": "#0000ff", "player": "#00ff00"},
        faction_name={"argon": "Argon Federation"},
        ware_name={"ore": "Ore"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _frames(**over):
    sectors = pd.DataFrame({
        "cluster.macro": ["cluster_a", "cluster_b", "cluster_b"],
        "macro": ["sec_a1", "sec_b1", "sec_b2"],
        "name": ["Alpha", "Beta I", "Beta II"],
        "owner": ["argon", "argon", "player"],
        "knownto": ["player", "player", "unknown"],
        "contested": [0, 1, 0],
        "ore": [100.0, 0.0, 50.0],
    })
    universe = pd.DataFrame({
        "class": ["station", "station", "station", "sector"],
        "name": ["Trade Post", "Hidden Base", "HQ", "Alpha"],
        "code": ["AAA-111", "BBB-222", "CCC-333", ""],
        "owner": ["argon", "argon", "player", "argon"],
        "knownto": ["player", "unknown", "player", "player"],
        "sector.macro": ["sec_a1", "sec_a1", "sec_b1", ""],
        "stype": ["trading", "defence", pd.NA, pd.NA],
    })
    empty_events = pd.DataFrame(columns=["time", "sector.name"])
    base = dict(
        sectors=sectors, universe=universe,
        police=empty_events, pirates=empty_events.copy(),
        resource_cols=["ore"], time_now=100_000.0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _cfg(**over):
    base = dict(spoilers_hide=False, overlay_hours=24.0)
    base.update(over)
    return SimpleNamespace(**base)


def test_slot_xy_grid_steps():
    assert _slot_xy(1, 1) == (8 * _UPX, 14 * _UPY)
    assert _slot_xy(-2, 0) == (-16 * _UPX, 0.0)


def test_layout_sectors_slots_and_spoilers():
    out = _layout_sectors(_frames(), _ref(), _cfg())
    assert len(out) == 3
    # lone sector sits at the cluster centre, multi-sector ones are offset
    a1 = out[out["macro"] == "sec_a1"].iloc[0]
    assert (a1["x"], a1["y"]) == (0.0, 0.0)
    assert a1["sizecat"] == "b"
    assert set(out[out["cluster.macro"] == "cluster_b"]["sizecat"]) == {"s"}
    # unknown factions fall back to capitalized code; player is special
    assert a1["ownername"] == "Argon Federation"
    assert out[out["owner"] == "player"].iloc[0]["ownername"] == "Player"

    hidden = _layout_sectors(_frames(), _ref(), _cfg(spoilers_hide=True))
    assert set(hidden["macro"]) == {"sec_a1", "sec_b1"}


def _two_sector_cluster(z_top, x_top, z_bot, x_bot, cluster="cl"):
    """A ref/frames pair with one 2-sector cluster at given offsets."""
    ref = _ref(
        clusters=pd.DataFrame({"macro": [cluster], "x": [0.0], "z": [0.0],
                               "name": ["Pair"]}),
        sectors=pd.DataFrame({
            "cluster": [cluster, cluster], "macro": ["top", "bot"],
            "x": [x_top, x_bot], "z": [z_top, z_bot],
            "name": ["Pair I", "Pair II"],
        }),
        gates=pd.DataFrame(columns=["sector_a", "sector_b"]),
    )
    frames = _frames(sectors=pd.DataFrame({
        "cluster.macro": [cluster, cluster], "macro": ["top", "bot"],
        "name": ["Pair I", "Pair II"], "owner": ["argon", "argon"],
        "knownto": ["player", "player"], "contested": [0, 0],
        "ore": [0.0, 0.0],
    }))
    return frames, ref


def test_layout_handedness():
    def slot_dx(out, macro):
        return out[out["macro"] == macro].iloc[0]["x"] / (8 * _UPX)

    # unlisted clusters keep the right-handed default (2-sector: top-right
    # + bottom-left) regardless of their offsets — the offsets do not
    # predict the in-game arrangement
    f, r = _two_sector_cluster(1e6, -5e6, -1e6, 5e6)
    out = _layout_sectors(f, r, _cfg())
    assert slot_dx(out, "top") == 1 and slot_dx(out, "bot") == -1

    # clusters in the in-game-audited _LEFT_HANDED table are mirrored
    f, r = _two_sector_cluster(1e6, 0.0, -1e6, 0.0, cluster="cluster_06_macro")
    out = _layout_sectors(f, r, _cfg())
    assert slot_dx(out, "top") == -1 and slot_dx(out, "bot") == 1


def test_labels_kinds():
    plot = _layout_sectors(_frames(), _ref(), _cfg())
    labels = _labels(plot, _ref())
    kinds = dict(zip(labels["altname"], labels["kind"]))
    assert kinds["Alpha"] == "single"
    assert kinds["I"] == "suffix"
    assert kinds["II"] == "suffix"
    assert kinds["Beta"] == "base"
    # the base label sits at the cluster centre
    base = labels[labels["kind"] == "base"].iloc[0]
    assert (base["x"], base["y"]) == (40_000_000.0, 17_320_000.0)


def test_resource_levels_quartiles():
    plot = _layout_sectors(_frames(), _ref(), _cfg())
    res = _resource_levels(plot, _frames().sectors, ["ore"])
    by_macro = dict(zip(res["macro"], res["ore"]))
    assert by_macro["sec_b1"] == 0      # no yield
    assert by_macro["sec_a1"] == 3      # top quartile
    assert by_macro["sec_b2"] in (1, 2)


@pytest.fixture
def payload():
    return _payload(_frames(), _ref(), _cfg())


def test_payload_scene_and_sectors(payload):
    # everything inside the base ranges -> exactly the reference density
    assert (payload["scene"]["w"], payload["scene"]["h"]) == (1536.0, 864.0)
    assert len(payload["sectors"]) == 3
    for s in payload["sectors"]:
        assert 0 <= s["x"] <= 1536 and 0 <= s["y"] <= 864
        assert s["tip"].startswith("<b>")
    # y is inverted (galaxy +z is up = smaller px y): cluster_b sits above
    a = next(s for s in payload["sectors"] if s["macro"] == "sec_a1")
    b = next(s for s in payload["sectors"] if s["macro"] == "sec_b1")
    assert b["y"] < a["y"] and b["x"] > a["x"]


def test_payload_gates_are_index_pairs(payload):
    idx = {s["macro"]: i for i, s in enumerate(payload["sectors"])}
    assert sorted(map(tuple, payload["gates"])) == sorted([
        (idx["sec_a1"], idx["sec_b1"]), (idx["sec_b1"], idx["sec_b2"])])


def test_payload_stations_grouped_and_typed(payload):
    st = payload["stations"]
    # sorted by (owner, name): Hidden Base before Trade Post
    assert [s["code"] for s in st["sec_a1"]] == ["BBB-222", "AAA-111"]
    assert st["sec_a1"][1]["type"] == "trading"
    assert st["sec_b1"] == [
        {"name": "HQ", "code": "CCC-333", "owner": "Player", "type": ""}]


def test_payload_resources_aligned(payload):
    (ore,) = payload["resources"]
    assert ore["name"] == "Ore"
    by_macro = dict(zip((s["macro"] for s in payload["sectors"]),
                        ore["yields"]))
    assert by_macro == {"sec_a1": 100.0, "sec_b1": 0.0, "sec_b2": 50.0}


def test_payload_spoilers_hide_drops_everything_hidden():
    p = _payload(_frames(), _ref(), _cfg(spoilers_hide=True))
    macros = {s["macro"] for s in p["sectors"]}
    assert macros == {"sec_a1", "sec_b1"}
    # the gate to the hidden sector is gone, the known-known one stays
    assert len(p["gates"]) == 1
    # undiscovered stations are dropped too
    assert [s["code"] for s in p["stations"]["sec_a1"]] == ["AAA-111"]
    blob = str(p)
    assert "Hidden Base" not in blob and "sec_b2" not in blob
