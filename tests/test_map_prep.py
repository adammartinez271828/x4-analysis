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
        "id": ["st1", "st2", "st3", "sec"],
        "class": ["station", "station", "station", "sector"],
        "name": ["Trade Post", "Hidden Base", "HQ", "Alpha"],
        "code": ["AAA-111", "BBB-222", "CCC-333", ""],
        "owner": ["argon", "argon", "player", "argon"],
        "knownto": ["player", "unknown", "player", "player"],
        "sector.macro": ["sec_a1", "sec_a1", "sec_b1", ""],
        "stype": ["trading", "defence", pd.NA, pd.NA],
        "sx": [10_000.0, None, None, None],
        "sz": [5_000.0, None, None, None],
        "faction_hq": [None, None, 1, None],
    })
    empty_events = pd.DataFrame(columns=["time", "sector.name"])
    datavaults = pd.DataFrame({
        "id": ["v1", "v2", "v3"],
        "macro": ["landmarks_vault_01_macro", "landmarks_erlking_vault_02_macro",
                  "landmarks_vault_03_macro"],
        "code": ["VLT-001", "ERL-002", "VLT-003"],
        "knownto": ["player", "", ""],   # "" = undiscovered
        "sector.macro": ["sec_a1", "sec_b1", "sec_a1"],
        "sx": [20_000.0, None, 0.0],
        "sz": [-10_000.0, None, 0.0],
        "unlocked": [1, 0, 0],
        "loot": [0, 2, 1],
        "blueprints": ["", "turret_pir_l_mk1", ""],
    })
    base = dict(
        sectors=sectors, universe=universe,
        police=empty_events, pirates=empty_events.copy(),
        resource_cols=["ore"], time_now=100_000.0,
        built_modules=pd.DataFrame(columns=["id", "macro"]),
        datavaults=datavaults,
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

    # clusters in _SWAP_ORDER assign their sectors to slots in reversed
    # offset order (Hewa's Twin, Ianamus Zura): the data's "top" sector
    # takes the bottom slot
    f, r = _two_sector_cluster(1e6, 0.0, -1e6, 0.0, cluster="cluster_19_macro")
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


def test_labels_multi_cluster_without_shared_prefix():
    # sectors that don't share the cluster base name (Earth/The Moon,
    # Kingdom End's Towering Wave) still become zoom-gated "suffix"
    # labels with their full names, and the cluster always gets a base
    # label
    f, r = _two_sector_cluster(1e6, 0.0, -1e6, 0.0)
    r.clusters.loc[0, "name"] = "Sol"
    r.sectors["name"] = ["Earth", "The Moon"]
    f.sectors["name"] = ["Earth", "The Moon"]
    plot = _layout_sectors(f, r, _cfg())
    labels = _labels(plot, r)
    kinds = dict(zip(labels["altname"], labels["kind"]))
    assert kinds["Earth"] == "suffix"
    assert kinds["The Moon"] == "suffix"
    assert kinds["Sol"] == "base"


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
    assert sorted((g[0], g[1]) for g in payload["gates"]) == sorted([
        (idx["sec_a1"], idx["sec_b1"]), (idx["sec_b1"], idx["sec_b2"])])
    # without endpoint columns the endpoints fall back to the hex centres
    for g in payload["gates"]:
        a, b = payload["sectors"][g[0]], payload["sectors"][g[1]]
        assert (g[2], g[3]) == (a["x"], a["y"])
        assert (g[4], g[5]) == (b["x"], b["y"])


def test_payload_gate_endpoints_scaled_into_hex():
    ref = _ref(gates=pd.DataFrame({
        "sector_a": ["sec_a1"], "sector_b": ["sec_b1"],
        "ax": [100_000.0], "az": [-200_000.0],   # east, south edge
        "bx": [0.0], "bz": [200_000.0],          # north edge
    }))
    p = _payload(_frames(), ref, _cfg())
    (g,) = p["gates"]
    a, b = p["sectors"][g[0]], p["sectors"][g[1]]
    # endpoint A: east of centre (px x greater), south (px y greater,
    # y-down), inside the hex (within half the hex width)
    assert 0 < g[2] - a["x"] < 31 and 0 < g[3] - a["y"] < 31
    # the farthest endpoint sits at 75% of the hex half-width
    dist = ((g[2] - a["x"]) ** 2 + (g[3] - a["y"]) ** 2) ** 0.5
    assert abs(dist - 0.75 * 62 / 2) < 0.1
    # endpoint B: due north of its centre
    assert g[4] == b["x"] and g[5] < b["y"]


def test_payload_highway_segments():
    ref = _ref(highways=pd.DataFrame({
        "sector": ["sec_a1", "sec_zzz"],   # unknown sector rows drop
        "x1": [50_000.0, 0.0], "z1": [0.0, 0.0],
        "x2": [0.0, 1.0], "z2": [50_000.0, 1.0],
    }))
    p = _payload(_frames(), ref, _cfg())
    (h,) = p["hws"]
    a = next(s for i, s in enumerate(p["sectors"])
             if s["macro"] == "sec_a1" and h[0] == i)
    # east of centre -> north of centre, scaled inside the hex
    assert h[1] > a["x"] and abs(h[2] - a["y"]) < 0.1
    assert abs(h[3] - a["x"]) < 0.1 and h[4] < a["y"]


def test_payload_vaults(payload):
    vs = payload["vaults"]
    assert len(vs) == 3
    v1 = next(v for v in vs if v["code"] == "VLT-001")
    assert v1["kind"] == "vault" and v1["open"] == 1 and v1["loot"] == 0
    # offset east/south of the sector centre, scaled inside the hex
    a = next(s for s in payload["sectors"] if s["macro"] == "sec_a1")
    assert v1["x"] > a["x"] and v1["y"] > a["y"]
    assert abs(v1["x"] - a["x"]) < 31 and abs(v1["y"] - a["y"]) < 31
    v2 = next(v for v in vs if v["code"] == "ERL-002")
    assert v2["kind"] == "erlking" and v2["open"] == 0
    assert v2["bp"] == "turret_pir_l_mk1"   # unresolved ids pass through
    # no recorded offset -> hex centre
    b = next(s for s in payload["sectors"] if s["macro"] == "sec_b1")
    assert (v2["x"], v2["y"]) == (b["x"], b["y"])


def test_payload_vaults_spoilers_hidden():
    p = _payload(_frames(), _ref(), _cfg(spoilers_hide=True))
    assert [v["code"] for v in p["vaults"]] == ["VLT-001"]


def test_payload_stations_grouped_and_typed(payload):
    st = payload["stations"]
    # sorted by (owner, name): Hidden Base before Trade Post
    assert [s["code"] for s in st["sec_a1"]] == ["BBB-222", "AAA-111"]
    assert st["sec_a1"][1]["type"] == "trading"
    (hq,) = st["sec_b1"]
    assert (hq["name"], hq["code"], hq["owner"]) == ("HQ", "CCC-333", "Player")
    assert hq["hq"] is True and hq["fac"] is None


def test_payload_station_facilities_and_positions():
    f = _frames()
    f.built_modules = pd.DataFrame({
        "id": ["st1", "st1", "st1", "st3"],
        "macro": ["buildmodule_gen_ships_m_dockarea_01_macro",
                  "buildmodule_gen_ships_xl_macro",
                  "buildmodule_gen_equip_l_macro",
                  "buildmodule_ter_equip_l_macro"],
    })
    f.universe.loc[f.universe["id"] == "st2", "stype"] = "Trading Station"
    p = _payload(f, _ref(), _cfg())
    by_code = {s["code"]: s for lst in p["stations"].values() for s in lst}
    # st1 builds S/M + XL ships AND equipment: display precedence shipyard
    assert by_code["AAA-111"]["fac"] == "shipyard"
    # st2 has no buildmodules; classified trading via its basename label
    assert by_code["BBB-222"]["fac"] == "trading"
    # st3 has only equip buildmodules
    assert by_code["CCC-333"]["fac"] == "equipdock"
    # st1 has a position: east (+x) and north (+z -> smaller py) of centre,
    # inside the hex
    s1 = by_code["AAA-111"]
    sec = next(s for s in p["sectors"] if s["macro"] == "sec_a1")
    assert 0 < s1["x"] - sec["x"] <= 31 and 0 < sec["y"] - s1["y"] <= 31
    # st2 has no sx/sz: falls back to the hex centre
    s2 = by_code["BBB-222"]
    assert (s2["x"], s2["y"]) == (sec["x"], sec["y"])
    # sector records carry their cluster macro (the renderer derives the
    # per-cluster facility rows from stations + this mapping)
    assert {s["macro"]: s["cluster"] for s in p["sectors"]} == {
        "sec_a1": "cluster_a", "sec_b1": "cluster_b", "sec_b2": "cluster_b"}


def test_payload_facility_stations_sort_first():
    f = _frames()
    f.built_modules = pd.DataFrame({
        "id": ["st1"], "macro": ["buildmodule_gen_ships_xl_macro"]})
    p = _payload(f, _ref(), _cfg())
    # Trade Post (shipyard) outranks Hidden Base (plain) despite the
    # alphabetical name order within the same faction
    assert [s["code"] for s in p["stations"]["sec_a1"]] == \
        ["AAA-111", "BBB-222"]


def test_payload_khaak_stations():
    f = _frames()
    f.universe.loc[f.universe["id"] == "st1", "owner"] = "khaak"
    p = _payload(f, _ref(), _cfg())
    by_code = {s["code"]: s for lst in p["stations"].values() for s in lst}
    assert by_code["AAA-111"]["fac"] == "khaak"


def test_payload_resources_aligned(payload):
    (ore,) = payload["resources"]   # no sunlight column in the synthetic ref
    assert ore["name"] == "Ore"
    by_macro = dict(zip((s["macro"] for s in payload["sectors"]),
                        ore["yields"]))
    assert by_macro == {"sec_a1": 100.0, "sec_b1": 0.0, "sec_b2": 50.0}


def test_payload_sunlight_first_and_player_faction():
    ref = _ref()
    ref.sectors["sunlight"] = [1.23, 0.5, 13.9]
    frames = _frames()
    frames.sectors["owner"] = ["argon", "argon", "argon"]   # player owns none
    p = _payload(frames, ref, _cfg())
    sun = p["resources"][0]
    assert sun["id"] == "sunlight" and sun["name"] == "Sunlight"
    by_macro = dict(zip((s["macro"] for s in p["sectors"]), sun["yields"]))
    assert by_macro == {"sec_a1": 123, "sec_b1": 50, "sec_b2": 1390}
    assert p["resources"][1]["id"] == "ore"
    # the player faction is always present, with the game colour
    names = [f["name"] for f in p["factions"]]
    assert "Player" in names
    player = next(f for f in p["factions"] if f["name"] == "Player")
    assert player["colour"] == "#00ff00"   # from ref.faction_colour


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
