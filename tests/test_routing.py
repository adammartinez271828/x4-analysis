"""Routing payloads (analysis/routing.py): the exported gate graph must
be the very graph opportunities._Router walks, the station list must
honour spoilers_hide, and the page's self-test pairs must be real
finite routes."""

import math
from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.opportunities import _Router, player_trade_ships
from x4analyzer.analysis.routing import (build_gate_graph, check_routes,
                                         graph_payload, routing_stations)


# same three-sector chain as tests/test_opportunities.py:
# sec_a -(a:+100km / b:-50km)- sec_b -(b:+50km / c:-20km z)- sec_c
def _ref(**over):
    base = dict(
        gates=pd.DataFrame({
            "sector_a": ["sec_a", "sec_b"],
            "sector_b": ["sec_b", "sec_c"],
            "ax": [100_000.0, 50_000.0],
            "az": [0.0, 0.0],
            "bx": [-50_000.0, 0.0],
            "bz": [0.0, -20_000.0],
        }),
        sectors=pd.DataFrame({
            "cluster": ["cl_a", "cl_b", "cl_b", "cl_c"],
            "macro": ["sec_a", "sec_b", "sec_b2", "sec_c"],
            "highway": [0, 1, 0, 0],
        }),
        ships=pd.DataFrame({
            "macro": ["ship_arg_m_trans_1_macro", "ship_arg_m_fight_1_macro"],
            "model": ["Boa", "Jaguar"],
            "class": ["M", "M"],
            "cargo": [4900.0, 0.0],
            "cargo_tags": ["container", ""],
            "drag_forward": [50.0, 20.0],
        }),
        engines=pd.DataFrame({
            "macro": ["engine_arg_m_travel_01_mk1_macro"],
            "size": ["m"], "type": ["travel"], "mk": [1],
            "forward": [1000.0], "travel_thrust": [10.0],
        }),
        faction_short={"argon": "ARG", "teladi": "TEL"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _universe():
    return pd.DataFrame({
        "id": ["st_a", "st_c", "st_pla", "plot_pla", "plot_npc", "ship1",
               "ship2"],
        "class": ["station", "station", "station", "buildstorage",
                  "buildstorage", "ship_m", "ship_m"],
        "owner": ["argon", "teladi", "player", "player", "teladi",
                  "player", "player"],
        "name": ["Foundry", "Fab", "My Mine", "", "", "Hauler One",
                 "Fighter One"],
        "code": ["AAA-111", "BBB-222", "PPP-111", "PPP-999", "NNN-888",
                 "HHH-001", "FFF-002"],
        "knownto": ["player", "", "player", "player", "player", "player",
                    "player"],
        "stype": ["", "", "", "Build plot", "Build plot", "", ""],
        "sector.macro": ["sec_a", "sec_c", "sec_a", "sec_b", "sec_c",
                         "sec_a", "sec_a"],
        "macro": ["", "", "", "", "", "ship_arg_m_trans_1_macro",
                  "ship_arg_m_fight_1_macro"],
        "parent.id": ["", "", "", "", "", "st_a", ""],
        "sx": [0.0, 0.0, 30_000.0, 0.0, 0.0, None, None],
        "sz": [0.0, 10_000.0, 40_000.0, 0.0, 0.0, None, None],
    })


def _frames():
    return SimpleNamespace(
        universe=_universe(),
        sectors=pd.DataFrame({
            "macro": ["sec_a", "sec_b", "sec_b2", "sec_c"],
            "name": ["Alpha", "Beta", "Beta II", "Gamma"],
        }),
        ship_engines=pd.DataFrame({
            "id": ["ship1", "ship2"],
            "macro": ["engine_arg_m_travel_01_mk1_macro"] * 2,
            "n": [1, 1],
        }),
    )


def _cfg(**over):
    base = dict(spoilers_hide=False)
    base.update(over)
    return SimpleNamespace(**base)


def test_graph_payload_matches_the_router_graph():
    ref = _ref()
    router = _Router(ref)
    p = graph_payload(ref)
    macros = [s[0] for s in p["sec"]]
    assert [macros[n[0]] for n in p["nodes"]] == router.sector
    assert [(n[1], n[2]) for n in p["nodes"]] == \
        [(round(x, 1), round(z, 1)) for x, z in router.pos]
    assert [tuple(x) for x in p["portals"]] == \
        [tuple(x) for x in router.portals]
    assert dict(p["sec"])["sec_b"] == 1 and dict(p["sec"])["sec_a"] == 0


def test_router_consumes_the_shared_builder():
    ref = _ref()
    g = build_gate_graph(ref)
    r = _Router(ref)
    assert (g.sector, g.pos, g.portals) == (r.sector, r.pos, r.portals)
    # same-cluster pair without a gates row still gets a free portal
    assert any({g.sector[i], g.sector[j]} == {"sec_b", "sec_b2"}
               for i, j in g.portals)


def test_stations_payload_shape_and_ordering():
    rows, names = routing_stations(_frames(), _ref(), _cfg())
    labels = [r[0] for r in rows]
    assert "Foundry (AAA-111)" in labels and "Fab (BBB-222)" in labels
    # NPC build storage is not a destination; the player's plot is
    assert "TEL Build plot (NNN-888)" not in labels
    plot = [r for r in rows if r[0] == "PLA Build plot (PPP-999)"]
    assert len(plot) == 1 and plot[0][5] == 1 | 2      # own + site
    assert [r[0] for r in rows if r[1] == "PLA" and r[5] == 1] == \
        ["My Mine (PPP-111)"]
    # sorted by sector display name, then label
    secs = [names[r[2]] for r in rows]
    assert secs == sorted(secs)
    assert names[rows[0][2]] == "Alpha"


def test_spoilers_hide_drops_undiscovered_stations_and_their_sector():
    rows, names = routing_stations(_frames(), _ref(), _cfg(spoilers_hide=True))
    labels = [r[0] for r in rows]
    assert "Fab (BBB-222)" not in labels            # knownto != player
    assert "Gamma" not in names.values()            # not even the sector
    assert "Foundry (AAA-111)" in labels


def test_check_pairs_are_finite_and_agree_with_the_router():
    ref = _ref()
    rows, _ = routing_stations(_frames(), ref, _cfg())
    chk = check_routes(ref, rows)
    assert chk
    macros = [s[0] for s in graph_payload(ref)["sec"]]
    router = _Router(ref)
    for i, j, sm, kp, kh in chk:
        assert 0 <= i < len(rows) and 0 <= j < len(rows) and i != j
        assert math.isfinite(kp) and math.isfinite(kh)
        a, b = rows[i], rows[j]
        km = router.route_km(macros[a[2]], (a[3], a[4]),
                             macros[b[2]], (b[3], b[4]), bool(sm))
        assert km is not None
        assert abs(km[0] - kp) < 0.01 and abs(km[1] - kh) < 0.01


def test_all_ships_superset_of_the_container_subset():
    frames, ref = _frames(), _ref()
    traders = player_trade_ships(frames, ref)
    every = player_trade_ships(frames, ref, container_only=False)
    assert {s["model"] for s in traders} == {"Boa"}
    assert {s["model"] for s in every} >= {"Boa", "Jaguar"}
    assert len(every) > len(traders)


def test_ship_locations_dock_to_the_host_station():
    ships = player_trade_ships(_frames(), _ref(), container_only=False,
                               with_location=True)
    by_model = {s["model"]: s for s in ships}
    # the Boa is docked at st_a and inherits its exact position; the
    # free-flying Jaguar only gets its sector centre, undocked
    assert by_model["Boa"]["loc"] == ["sec_a", 0.0, 0.0, 1]
    assert by_model["Jaguar"]["loc"] == ["sec_a", 0.0, 0.0, 0]
