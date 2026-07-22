"""Storage-allocation model (analysis/storage.py).

Deterministic synthetic station exercising the reverse-engineered rules:
output gets the workforce work_effect bonus, input consumption stays at base,
workforce food gets a fixed 4h buffer sized on *jobs* (full workforce), and the
remaining pool capacity is split so every production ware holds equal hours
(uniform T). See docs in analysis/storage.py; validated in-game against
GDR-378 / UBX-812 (single-stage) and food on all stations.
"""
from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.storage import station_storage, FOOD_HOURS


def _ref():
    wares = pd.DataFrame([
        ["widget", "container", "1"],
        ["energy", "container", "1"],
        ["food1", "container", "1"],
    ], columns=["id", "transport", "volume"])
    recipes = pd.DataFrame([
        # widget: 100/cycle out, 100 energy in, 1h cycle, +100% workforce bonus
        ["widget", "default", 3600, 100, "energy", 100, 1.0],
        # food: 90 food1 per 200 workers / 600s (Argon-style workunit)
        ["workunit_busy", "default", 600, 200, "food1", 90, ""],
    ], columns=["ware", "method", "time", "amount",
                "input_ware", "input_amount", "work_effect"])
    modules = pd.DataFrame([
        ["prod_widget", "widget", "default", 1.0],
    ], columns=["macro", "ware", "method", "scale"])
    modcaps = pd.DataFrame([
        ["prod_widget", "buildmodule", "", 100, 0, ""],
        ["store_container", "storage", "", 0, 100000, "container"],
    ], columns=["macro", "class", "housing", "workers",
                "cargo_max", "cargo_tags"])
    return SimpleNamespace(wares=wares, recipes=recipes, modules=modules,
                           modcaps=modcaps)


def _frames():
    built = pd.DataFrame([
        ["st1", "prod_widget", 1],
        ["st1", "store_container", 1],
    ], columns=["id", "macro", "built"])
    return SimpleNamespace(
        built_modules=built,
        universe=pd.DataFrame([["st1", "station"]], columns=["id", "class"]),
        workforce_all=pd.DataFrame([["st1", "default", 100]],
                                   columns=["id", "race", "amount"]),
    )


def _run():
    df = station_storage(_frames(), _ref())
    return {r.ware: r for r in df.itertuples()}


def test_roles_and_throughput():
    rows = _run()
    # output carries the +100% work_effect bonus: 100/h -> 200/h
    assert rows["widget"].role == "output"
    assert rows["widget"].throughput == 200.0
    # input consumption stays at base (no bonus): 100/h
    assert rows["energy"].role == "input"
    assert rows["energy"].throughput == 100.0
    # food: 90 per 200 workers/600s * 100 jobs = 270/h
    assert rows["food1"].role == "food"
    assert rows["food1"].throughput == 270.0


def test_food_fixed_4h_buffer():
    rows = _run()
    assert rows["food1"].max_units == 270.0 * FOOD_HOURS  # 1080


def test_uniform_hours_and_capacity_conservation():
    rows = _run()
    # food takes 4h * 270 = 1080 m³; production splits the remaining 98920 so
    # every production ware holds equal hours: T = 98920 / (200 + 100) = 329.73h
    t_widget = rows["widget"].max_units / rows["widget"].throughput
    t_energy = rows["energy"].max_units / rows["energy"].throughput
    assert abs(t_widget - t_energy) < 1e-6            # uniform T
    assert abs(t_widget - 98920 / 300) < 1e-6
    # every unit is volume 1, so max_volume == max_units and the pool fills
    total = sum(r.max_volume for r in rows.values())
    assert abs(total - 100000) < 1e-3                 # capacity conserved


def test_empty_inputs_return_empty():
    empty = SimpleNamespace(built_modules=pd.DataFrame(),
                            universe=pd.DataFrame(columns=["id", "class"]),
                            workforce_all=pd.DataFrame())
    ref = _ref()
    out = station_storage(empty, ref)
    assert out.empty
    assert list(out.columns) == ["station_id", "ware", "transport", "role",
                                 "throughput", "max_units", "max_volume"]
