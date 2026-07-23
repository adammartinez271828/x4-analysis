"""Station munition & drone census (analysis/drones.py).

Every item in a station's <ammunition> is captured with a category and is_unit
flag; only drones + police (is_unit=1) count toward the shared units.maxcount
pool. capacity_floor = Sum modcap.unit_storage over built modules -- exact for
stations without production modules (validated in-game: ABR-398 40, EBT-957 92,
QJI-262 220), a lower bound otherwise (MXH-411 40 floor vs 310 true cap).
"""
from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.drones import station_munition, _classify


def _ref():
    modcaps = pd.DataFrame([
        ["dockarea_x", "dockarea", 0, 0, 0, "", 20],
        ["pier_x", "pier", 0, 0, 0, "", 20],
        ["defence_x", "defencemodule", 0, 0, 0, "", 15],
        ["prod_x", "production", 0, 1500, 0, "", ""],   # no unit storage
    ], columns=["macro", "class", "housing", "workers",
                "cargo_max", "cargo_tags", "unit_storage"])
    return SimpleNamespace(modcaps=modcaps)


def _frames():
    return SimpleNamespace(built_modules=pd.DataFrame([
        ["st1", "dockarea_x", 1],
        ["st1", "pier_x", 1],
        ["st1", "defence_x", 1],
        ["st1", "prod_x", 1],
        ["st1", "prod_x", 1],
    ], columns=["id", "macro", "built"]))


def _save(items):
    return SimpleNamespace(ammunition=items)


def _run(items):
    df = station_munition(_save(items), _frames(), _ref())
    return {r.macro: r for r in df.itertuples()}


def test_classify():
    assert _classify("ship_gen_s_fightingdrone_01_a_macro") == ("defence", 1)
    assert _classify("ship_gen_xs_repairdrone_01_a_macro") == ("repair", 1)
    assert _classify("ship_gen_xs_cargodrone_empty_01_a_macro") == ("transport", 1)
    assert _classify("ship_gen_xs_buildingdrone_01_a_macro") == ("build", 1)
    assert _classify("ship_gen_s_miningdrone_solid_01_a_macro") == ("mining", 1)
    assert _classify("ship_ter_xs_police_01_a_macro") == ("police", 1)
    # non-units are captured too, flagged is_unit=0
    assert _classify("missile_gen_l_dumbfire_01_mk1_macro") == ("missile", 0)
    assert _classify("countermeasure_flares_01_macro") == ("countermeasure", 0)
    assert _classify("eq_arg_satellite_02_macro") == ("deployable", 0)
    assert _classify("something_unknown_macro") == ("other", 0)


def test_counts_flags_and_floor():
    rows = _run([
        ("st1", "ship_gen_s_fightingdrone_01_a_macro", "10"),
        ("st1", "ship_gen_xs_cargodrone_empty_01_a_macro", "30"),
        ("st1", "missile_gen_l_dumbfire_01_mk1_macro", "30000"),
    ])
    assert rows["ship_gen_s_fightingdrone_01_a_macro"].is_unit == 1
    assert rows["ship_gen_xs_cargodrone_empty_01_a_macro"].count == 30
    # munitions captured but flagged non-unit
    assert rows["missile_gen_l_dumbfire_01_mk1_macro"].is_unit == 0
    assert rows["missile_gen_l_dumbfire_01_mk1_macro"].count == 30000
    # capacity_floor = dockarea 20 + pier 20 + defence 15; production adds none
    assert all(r.capacity_floor == 55 for r in rows.values())


def test_count_may_exceed_floor():
    # production-heavy station: engine cap exceeds the unit-storage floor
    rows = _run([("st1", "ship_gen_s_fightingdrone_01_a_macro", "300")])
    r = rows["ship_gen_s_fightingdrone_01_a_macro"]
    assert r.count == 300 and r.capacity_floor == 55   # 300 > floor allowed


def test_empty_returns_empty():
    out = station_munition(_save([]), _frames(), _ref())
    assert out.empty
    assert list(out.columns) == ["station_id", "macro", "category", "is_unit",
                                 "count", "capacity_floor"]
