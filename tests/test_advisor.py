"""Build advisor (viz/advisor.py) logistics layer: ware haul volume,
demand-weighted route distance and the trade-ship presets that size a
fleet. The weighted-distance helper is tested on its own (it is pure and
carries the modelling assumptions); compute_advice is exercised once
end-to-end on a synthetic three-sector universe."""

from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.opportunities import _Router
from x4analyzer.viz.advisor import IN_SECTOR_KM, _avg_route_km, compute_advice


# ---------------------------------------------------------------- fixtures
# chain: sec_a -(gate at a:+100km / b:-50km)- sec_b -(b:+50km / c:-20km z)-
# sec_c, exactly the geometry of tests/test_opportunities.py. Centre to
# centre: a->b = 100 + 50 = 150 km, a->c = 100 + 100 + 20 = 220 km (the
# 100 km across sec_b are highway km).
_GATES = pd.DataFrame({
    "sector_a": ["sec_a", "sec_b"],
    "sector_b": ["sec_b", "sec_c"],
    "ax": [100_000.0, 50_000.0],
    "az": [0.0, 0.0],
    "bx": [-50_000.0, 0.0],
    "bz": [0.0, -20_000.0],
})
_REF_SECTORS = pd.DataFrame({
    "cluster": ["cl_a", "cl_b", "cl_c", "cl_x"],
    "macro": ["sec_a", "sec_b", "sec_c", "sec_x"],   # sec_x: no gates
    "highway": [0, 1, 0, 0],
})


def _ref(**over):
    base = dict(
        wares=pd.DataFrame({
            "id": ["silicon", "advancedelectronics", "hullparts"],
            "name": ["Silicon Wafers", "Advanced Electronics",
                     "Hull Parts"],
            "volume": [18.0, 30.0, 10.0],
            "price_avg": [130.0, 1100.0, 200.0],
            "tags": ["economy minable", "economy", "container"],
        }),
        modules=pd.DataFrame({
            "macro": ["mod_ae", "mod_hp"],
            "ware": ["advancedelectronics", "hullparts"],
            "method": ["default", "default"],
            "scale": [1.0, 1.0],
        }),
        # advanced electronics: 100 per 600 s from silicon;
        # hull parts: 50 per 600 s from 20 advanced electronics
        # -> one hull-parts module wants 120 AE/h
        recipes=pd.DataFrame({
            "ware": ["advancedelectronics", "hullparts"],
            "method": ["default", "default"],
            "time": [600.0, 600.0],
            "amount": [100.0, 50.0],
            "input_ware": ["silicon", "advancedelectronics"],
            "input_amount": [40.0, 20.0],
        }),
        gates=_GATES,
        sectors=_REF_SECTORS,
        ships=pd.DataFrame({
            "macro": ["ship_arg_m_trans_1_macro"],
            "model": ["Boa"], "class": ["M"], "cargo": [4900.0],
            "cargo_tags": ["container"], "drag_forward": [50.0],
        }),
        engines=pd.DataFrame({
            "macro": ["engine_arg_m_travel_01_mk1_macro"],
            "size": ["m"], "type": ["travel"], "mk": [1],
            "forward": [1000.0], "travel_thrust": [10.0],
        }),
        faction_short={"argon": "ARG", "teladi": "TEL"},
        ware_name={"silicon": "Silicon Wafers",
                   "advancedelectronics": "Advanced Electronics",
                   "hullparts": "Hull Parts"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _frames(consumers=(("st_c", "sec_c", 1),), ship_engines=None):
    """`consumers`: (station id, sector, hull-parts modules) — each module
    consumes 120 Advanced Electronics/h."""
    ids = [c[0] for c in consumers]
    uni = pd.DataFrame({
        "id": ids + ["ship1"],
        "class": ["station"] * len(ids) + ["ship_m"],
        "owner": ["argon"] * len(ids) + ["player"],
        "name": ["Fab"] * len(ids) + ["Hauler One"],
        "code": [f"AAA-{i}" for i in range(len(ids))] + ["HHH-001"],
        "knownto": ["player"] * (len(ids) + 1),
        "stype": [""] * (len(ids) + 1),
        "sector.macro": [c[1] for c in consumers] + ["sec_a"],
        "macro": [""] * len(ids) + ["ship_arg_m_trans_1_macro"],
    })
    mods = pd.DataFrame(
        [(c[0], "mod_hp", "default") for c in consumers for _ in range(c[2])],
        columns=["id", "macro", "method"])
    sectors = pd.DataFrame({
        "macro": ["sec_a", "sec_b", "sec_c", "sec_x"],
        "name": ["Alpha", "Beta", "Gamma", "Exile"],
        "owner": ["argon", "argon", "teladi", "argon"],
        "knownto": ["player"] * 4,
    })
    empty_gt = pd.DataFrame(columns=["id", "owner", "ware", "time"])
    return SimpleNamespace(
        universe=uni, sectors=sectors, built_modules=mods,
        workforce_all=pd.DataFrame(columns=["id", "race", "amount"]),
        global_trades=empty_gt,
        trade_offers=pd.DataFrame(columns=["id", "side", "ware", "amount",
                                           "price"]),
        ship_engines=ship_engines if ship_engines is not None
        else pd.DataFrame(columns=["id", "macro", "n"]))


def _cfg():
    return SimpleNamespace(spoilers_hide=False)


def _engines():
    return pd.DataFrame({"id": ["ship1"],
                         "macro": ["engine_arg_m_travel_01_mk1_macro"],
                         "n": [2]})


# ------------------------------------------------- weighted route helper
def test_single_target_route_split():
    r = _Router(_ref())
    # sec_a -> sec_c: 100 km to the gate (plain) + 100 km across the
    # highway sector + 20 km from the arrival gate to the centre
    assert _avg_route_km(r, "sec_a", {"sec_c": 1.0}) == (120.0, 100.0)
    assert _avg_route_km(r, "sec_a", {"sec_b": 1.0}) == (100.0, 50.0)


def test_distance_is_demand_weighted_between_the_two_targets():
    r = _Router(_ref())
    near = _avg_route_km(r, "sec_a", {"sec_b": 1.0})
    far = _avg_route_km(r, "sec_a", {"sec_c": 1.0})
    # 3:1 in favour of the nearer sector -> the average sits between the
    # two single-target values and close to the heavier one
    got = _avg_route_km(r, "sec_a", {"sec_b": 3.0, "sec_c": 1.0})
    tot = got[0] + got[1]
    assert near[0] + near[1] < tot < far[0] + far[1]
    assert got == (round((3 * 100 + 120) / 4, 1),
                   round((3 * 50 + 100) / 4, 1))
    # symmetric weights land exactly halfway
    assert _avg_route_km(r, "sec_a", {"sec_b": 2.0, "sec_c": 2.0}) == (
        110.0, 75.0)


def test_same_sector_demand_uses_the_fixed_leg():
    r = _Router(_ref())
    # centre-to-centre would be 0 km — the flat in-sector leg is charged
    assert _avg_route_km(r, "sec_a", {"sec_a": 1.0}) == (IN_SECTOR_KM, 0.0)
    assert _avg_route_km(r, "sec_a", {"sec_a": 1.0, "sec_b": 1.0}) == (
        round((IN_SECTOR_KM + 100) / 2, 1), 25.0)


def test_no_demand_or_unreachable_demand_has_no_route():
    r = _Router(_ref())
    assert _avg_route_km(r, "sec_a", {}) is None
    assert _avg_route_km(r, "sec_a", {"sec_b": 0.0}) is None      # zero weight
    assert _avg_route_km(r, "sec_a", {"sec_x": 1.0}) is None      # no gates
    # unreachable demand is dropped, the rest still averages
    assert _avg_route_km(r, "sec_a", {"sec_x": 5.0, "sec_b": 1.0}) == (
        100.0, 50.0)


def test_route_cache_is_reused():
    r = _Router(_ref())
    cache: dict = {}
    _avg_route_km(r, "sec_a", {"sec_c": 1.0}, cache)
    assert cache == {("sec_a", "sec_c"): (120.0, 100.0)}
    cache[("sec_a", "sec_c")] = (7.0, 0.0)      # poisoned: proves the hit
    assert _avg_route_km(r, "sec_a", {"sec_c": 1.0}, cache) == (7.0, 0.0)


# ------------------------------------------------------ compute_advice
def _rows(data):
    return {r["sector"]: r for r in data["rows"]
            if r["ware"] == "Advanced Electronics"}


def test_rows_carry_volume_haul_inputs_and_route():
    data = compute_advice(_frames(), _ref(), _cfg())
    rows = _rows(data)
    assert set(rows) == {"Alpha", "Beta", "Gamma"}   # sec_x sees no demand
    a, c = rows["Alpha"], rows["Gamma"]
    # one hull-parts module in sec_c: 20 AE per 600 s = 120 AE/h, seen
    # from sec_a at 2 hops (÷3) and from sec_c itself undiscounted
    assert a["vol"] == 30.0 and c["vol"] == 30.0
    assert (a["demand_h"], c["demand_h"]) == (40, 120)
    # haul m³/h is the client's shortfall × vol; with no competitor the
    # shortfall IS the demand
    assert a["demand_h"] * a["vol"] == 1200
    # inputs: 40 silicon per 600 s = 240/h × 18 m³ = 4320 m³/h per module
    assert a["in_m3h"] == 4320.0
    # route to the only demand sector; the build sector's own demand is
    # charged the flat in-sector leg
    assert (a["km_p"], a["km_h"]) == (120.0, 100.0)
    assert (c["km_p"], c["km_h"]) == (IN_SECTOR_KM, 0.0)


def test_advice_route_is_weighted_across_demand_sectors():
    plain = _rows(compute_advice(_frames(), _ref(), _cfg()))["Alpha"]
    two = _rows(compute_advice(
        _frames(consumers=(("st_c", "sec_c", 1), ("st_b", "sec_b", 3))),
        _ref(), _cfg()))["Alpha"]
    # sec_b now carries far more (and nearer) demand: the average route
    # from sec_a shortens towards the sec_b-only distance of 150 km
    assert two["km_p"] + two["km_h"] < plain["km_p"] + plain["km_h"]
    assert 150.0 <= two["km_p"] + two["km_h"] < 220.0


def test_ship_presets_come_from_player_traders_else_generic():
    data = compute_advice(_frames(ship_engines=_engines()), _ref(), _cfg())
    (s,) = data["ships"]
    assert s["cargo"] == 4900.0 and s["speed"] == 400 and s["cls"] == "M"
    assert "gen" not in s
    # no resolvable engines -> no timeable ship -> the labelled generic
    gen = compute_advice(_frames(), _ref(), _cfg())["ships"]
    assert len(gen) == 1 and gen[0]["gen"] == 1 and "assumed" in gen[0]["l"]
