"""Storage-allocation model (analysis/storage.py).

Two paths: producing stations get the exact throughput x T model
(source='computed'); non-producers (wharfs/shipyards/docks/trade) get the
stock+buy proxy (source='proxy'). See docs in analysis/storage.py; the compute
path is validated in-game against GDR-378 / UBX-812, the proxy against
same-faction wharves matching to r=0.9984.
"""
from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.storage import station_storage, FOOD_HOURS

_CARGO = ["id", "ware", "amount"]
_OFFERS = ["id", "side", "ware", "amount", "price"]


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


def _frames(built, universe, workforce=None, cargo=None, offers=None):
    return SimpleNamespace(
        built_modules=pd.DataFrame(built, columns=["id", "macro", "built"]),
        universe=pd.DataFrame(universe, columns=["id", "class"]),
        workforce_all=pd.DataFrame(workforce or [],
                                   columns=["id", "race", "amount"]),
        station_cargo=pd.DataFrame(cargo or [], columns=_CARGO),
        trade_offers=pd.DataFrame(offers or [], columns=_OFFERS),
    )


# ---- producing station (throughput x T) ------------------------------------

def _producer():
    return _frames(
        built=[["st1", "prod_widget", 1], ["st1", "store_container", 1]],
        universe=[["st1", "station"]],
        workforce=[["st1", "default", 100]])


def _run(frames=None):
    df = station_storage(frames or _producer(), _ref())
    return {r.ware: r for r in df.itertuples()}


def test_roles_and_throughput():
    rows = _run()
    assert rows["widget"].role == "output" and rows["widget"].source == "computed"
    assert rows["widget"].throughput == 200.0        # 100/h * (1 + 1.0 bonus)
    assert rows["energy"].role == "input"            # consumed at base (no bonus)
    assert rows["energy"].throughput == 100.0
    assert rows["food1"].role == "food"              # 90/200 * 6 * 100 jobs
    assert rows["food1"].throughput == 270.0


def test_food_fixed_4h_buffer():
    assert _run()["food1"].max_units == 270.0 * FOOD_HOURS  # 1080


def test_uniform_hours_and_capacity_conservation():
    rows = _run()
    t_widget = rows["widget"].max_units / rows["widget"].throughput
    t_energy = rows["energy"].max_units / rows["energy"].throughput
    assert abs(t_widget - t_energy) < 1e-6            # uniform T
    assert abs(t_widget - 98920 / 300) < 1e-6
    total = sum(r.max_volume for r in rows.values())
    assert abs(total - 100000) < 1e-3                 # capacity conserved


# ---- non-producing station (stock + buy proxy) -----------------------------

def test_proxy_non_producer():
    frames = _frames(
        built=[["w1", "buildmodule_ships", 1]],       # not in ref.modules
        universe=[["w1", "station"]],
        cargo=[["w1", "energy", 100], ["w1", "food1", 50], ["w1", "widget", 40]],
        offers=[["w1", "buy", "energy", 200, 5],
                ["w1", "buy", "food1", 30, 3],
                ["w1", "sell", "widget", 25, 9]])
    rows = _run(frames)
    assert all(r.source == "proxy" for r in rows.values())
    assert rows["energy"].max_units == 300            # stock 100 + buy 200
    assert rows["energy"].role == "input"
    assert rows["food1"].max_units == 80              # stock 50 + buy 30
    assert rows["food1"].role == "food"               # workunit input -> food
    assert rows["widget"].max_units == 40             # sell-only: floor at stock
    assert rows["widget"].throughput is None


def test_empty_inputs_return_empty():
    empty = SimpleNamespace(built_modules=pd.DataFrame(),
                            universe=pd.DataFrame(columns=["id", "class"]),
                            workforce_all=pd.DataFrame())
    out = station_storage(empty, _ref())
    assert out.empty
    assert list(out.columns) == ["station_id", "ware", "transport", "role",
                                 "throughput", "max_units", "max_volume",
                                 "source"]
