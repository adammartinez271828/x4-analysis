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
_OFFERS = ["id", "side", "ware", "amount", "price", "flags", "desired"]


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


def _frames(built, universe, workforce=None, cargo=None, offers=None,
            production=None):
    return SimpleNamespace(
        module_production=pd.DataFrame(
            production or [],
            columns=["id", "macro", "ware", "efficiency", "state",
                     "n_modules"]),
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
        offers=[["w1", "buy", "energy", 200, 5, "", None],
                ["w1", "buy", "food1", 30, 3, "", None],
                ["w1", "sell", "widget", 25, 9, "", None]])
    rows = _run(frames)
    assert all(r.source == "proxy" for r in rows.values())
    assert rows["energy"].max_units == 300            # stock 100 + buy 200
    assert rows["energy"].role == "input"
    assert rows["food1"].max_units == 80              # stock 50 + buy 30
    assert rows["food1"].role == "food"               # workunit input -> food
    assert rows["widget"].max_units == 40             # sell-only: floor at stock
    assert rows["widget"].throughput is None


# ---- supplies-flagged offers (self-supply demand, v18) ----------------------

def test_supply_buys_excluded_from_proxy_and_emitted_as_supply_rows():
    # non-producer buying energy for production AND for drone building: the
    # flagged buy must not inflate the proxy max; it becomes a supply row
    frames = _frames(
        built=[["w1", "buildmodule_ships", 1]],
        universe=[["w1", "station"]],
        cargo=[["w1", "energy", 100]],
        offers=[["w1", "buy", "energy", 200, 5, "", None],
                ["w1", "buy", "energy", 0, 5, "supplies|invertfactionrestriction", 2150],
                ["w1", "buy", "widget", 40, 9, "supplies", None]])
    df = station_storage(frames, _ref())
    by_role = {(r.ware, r.role): r for r in df.itertuples()}
    assert by_role[("energy", "input")].max_units == 300   # proxy unchanged
    sup = by_role[("energy", "supply")]
    assert sup.max_units == 2150                     # desired wins over amount
    assert sup.source == "offer" and sup.throughput is None
    assert by_role[("widget", "supply")].max_units == 40   # no desired -> amount


def test_supply_rows_on_producing_stations_too():
    # ABR-398 pattern: computed path for production, supply row alongside
    frames = _producer()
    frames.station_cargo = pd.DataFrame([], columns=_CARGO)
    frames.trade_offers = pd.DataFrame(
        [["st1", "buy", "food1", 0, 2, "supplies", 190]], columns=_OFFERS)
    df = station_storage(frames, _ref())
    by_role = {(r.ware, r.role): r for r in df.itertuples()}
    assert by_role[("food1", "supply")].max_units == 190
    assert by_role[("food1", "food")].source == "computed"  # model untouched
    assert by_role[("widget", "output")].source == "computed"


# ---- <production><efficiency product> (v27) --------------------------------

def test_efficiency_from_the_save_overrides_the_recipe_work_effect():
    # the widget recipe carries work_effect 1.0, so the reconstructed rate is
    # 200/cycle. The save says the module is actually running at 1.5, and the
    # engine truncates per cycle: floor(100 x 1.5) = 150. Storage is sized off
    # the real rate, so the allocation must follow the save, not the recipe.
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "widget", 1.5, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    rows = _run(frames)
    assert rows["widget"].throughput == 150.0          # not 200.0
    # energy input is NOT scaled by the multiplier (outputs only)
    assert rows["energy"].throughput == 100.0


def test_efficiency_truncates_per_cycle_like_the_recipe_path():
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "widget", 1.12634, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    # floor(100 x 1.12634) = 112, never 112.634
    assert _run(frames)["widget"].throughput == 112.0


def test_missing_efficiency_falls_back_to_the_recipe_work_effect():
    # an idle module reports no <production> block at all; the reconstructed
    # workforce bonus is all we have and must still apply
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [], columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    assert _run(frames)["widget"].throughput == 200.0


def test_unparseable_efficiency_is_ignored_not_fatal():
    # defensive: a modded save with a junk/zero product must not zero the
    # station's storage, it must fall back
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "widget", None, "producing", 1],
         ["st1", "prod_widget", "widget", 0.0, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    assert _run(frames)["widget"].throughput == 200.0


def test_shady_buys_get_no_storage_at_all():
    # black-market book: a non-producing station bids for an illegal ware it
    # holds none of. It must neither inflate an existing proxy row nor mint a
    # row of its own (546 such phantom rows universe-wide before this).
    frames = _frames(
        built=[["w1", "buildmodule_ships", 1]],
        universe=[["w1", "station"]],
        cargo=[["w1", "energy", 100]],
        offers=[["w1", "buy", "energy", 200, 5, "invertfactionrestriction", None],
                ["w1", "buy", "energy", 60, 9,
                 "buyercargovirtual|invertfactionrestriction|shady", 60],
                ["w1", "buy", "widget", 500, 90,
                 "buyercargovirtual|buyermoneyvirtual|shady", 500]])
    df = station_storage(frames, _ref())
    rows = {(r.ware, r.role): r for r in df.itertuples()}
    assert rows[("energy", "input")].max_units == 300   # proxy: 100 + 200 only
    assert not any(r.ware == "widget" for r in df.itertuples())


def test_offers_without_flags_column_still_work():
    # defensive: a hand-built frame without the v18 columns must not crash
    frames = _frames(
        built=[["w1", "buildmodule_ships", 1]],
        universe=[["w1", "station"]],
        cargo=[["w1", "energy", 100]])
    frames.trade_offers = pd.DataFrame(
        [["w1", "buy", "energy", 200, 5]],
        columns=["id", "side", "ware", "amount", "price"])
    rows = _run(frames)
    assert rows["energy"].max_units == 300


def test_empty_inputs_return_empty():
    empty = SimpleNamespace(built_modules=pd.DataFrame(),
                            universe=pd.DataFrame(columns=["id", "class"]),
                            workforce_all=pd.DataFrame())
    out = station_storage(empty, _ref())
    assert out.empty
    assert list(out.columns) == ["station_id", "ware", "transport", "role",
                                 "throughput", "max_units", "max_volume",
                                 "source"]
