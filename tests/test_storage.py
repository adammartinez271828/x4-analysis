"""Storage-allocation model (analysis/storage.py).

Two paths: producing stations get the exact throughput x T model
(source='computed'); non-producers (wharfs/shipyards/docks/trade) get the
stock+buy proxy (source='proxy'). See docs in analysis/storage.py; the compute
path is validated in-game against GDR-378 / UBX-812, the proxy against
same-faction wharves matching to r=0.9984.
"""
import math
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
    # universe rows are [id, class] or [id, class, station macro]
    universe = [list(r) + [""] * (3 - len(r)) for r in universe]
    return SimpleNamespace(
        module_production=pd.DataFrame(
            production or [],
            columns=["id", "macro", "ware", "efficiency", "state",
                     "n_modules"]),
        built_modules=pd.DataFrame(built, columns=["id", "macro", "built"]),
        universe=pd.DataFrame(universe, columns=["id", "class", "macro"]),
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


def test_no_production_block_means_the_bare_recipe():
    # the save carries production data, but not for THIS module -- it has no
    # <production> block, so it is running the unbonused recipe (KRV-460).
    frames = _producer()
    frames.built_modules = pd.DataFrame(
        [["st1", "prod_widget", 1], ["st1", "prod_other", 1],
         ["st1", "store_container", 1]], columns=["id", "macro", "built"])
    frames.module_production = pd.DataFrame(
        [["st1", "prod_other", "other", 1.5, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    assert _run(frames)["widget"].throughput == 100.0   # not 200.0


def test_no_production_data_at_all_keeps_the_reconstruction():
    # a pre-v27 database or a hand-built frame: a missing row means "unknown",
    # not "idle", so the recipe work_effect must still apply
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [], columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    assert _run(frames)["widget"].throughput == 200.0
    frames.module_production = None
    assert _run(frames)["widget"].throughput == 200.0


def test_unparseable_efficiency_is_ignored_not_fatal():
    # defensive: a modded save with a junk/zero product must not zero the
    # station's storage or crash. Such a row is indistinguishable from a
    # module with no <production> block, so it takes the bare recipe.
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "widget", None, "producing", 1],
         ["st1", "prod_widget", "widget", 0.0, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    rows = _run(frames)
    assert rows["widget"].throughput == 100.0
    assert rows["widget"].max_units > 0


# ---- multi-queue modules (v27) --------------------------------------------

def _multi_ref():
    """A module that alternates between two wares with DIFFERENT work effects."""
    r = _ref()
    r.recipes = pd.DataFrame([
        ["widget", "default", 3600, 100, "energy", 100, 1.0],
        ["gadget", "default", 3600, 200, "energy", 50, 0.5],
        ["workunit_busy", "default", 600, 200, "food1", 90, ""],
    ], columns=["ware", "method", "time", "amount",
                "input_ware", "input_amount", "work_effect"])
    r.modules = pd.DataFrame([
        ["prod_widget", "widget", "default", 1.0],
        ["prod_widget", "gadget", "default", 1.0],
    ], columns=["macro", "ware", "method", "scale"])
    return r


def test_module_level_efficiency_is_used_when_the_queue_ware_is_unknown():
    # a module caught between products reports an efficiency with NO
    # <queue ware>; keying only on (station, macro, ware) would miss it
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "", 1.5, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    assert _run(frames)["widget"].throughput == 150.0     # not the 1.0 fallback


def test_unqueued_efficiency_is_rescaled_per_recipe_work_effect():
    # KWC-232's shape. The module reports 1.25, which read against its
    # SMALLEST work effect (gadget, 0.5) is a workforce ratio of 0.5; widget
    # then runs at 1 + 1.0 x 0.5 = 1.5 and gadget at its reported 1.25.
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "", 1.25, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    rows = {r.ware: r for r in station_storage(frames, _multi_ref()).itertuples()}
    # weight is 1/2 across the two options, so rates are halved
    assert rows["widget"].throughput == 150.0 * 0.5
    assert rows["gadget"].throughput == 250.0 * 0.5


def test_rescaling_is_a_no_op_on_a_single_recipe_module():
    frames = _producer()
    frames.module_production = pd.DataFrame(
        [["st1", "prod_widget", "", 1.42, "producing", 1]],
        columns=["id", "macro", "ware", "efficiency", "state", "n_modules"])
    # one recipe, work_effect 1.0: ratio 0.42, back to 1 + 1.0 x 0.42 = 1.42
    assert _run(frames)["widget"].throughput == 142.0


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


# ---- storage-only pool (condensate / Protectyon) ---------------------------

def _condensate_ref():
    """Reference data with a fourth transport pool no recipe touches."""
    ref = _ref()
    ref.wares = pd.DataFrame([
        ["widget", "container", "1", "container economy"],
        ["energy", "container", "1", "container economy"],
        ["food1", "container", "1", "container economy"],
        ["condensate", "condensate", "10", "condensate economy"],
    ], columns=["id", "transport", "volume", "tags"])
    ref.modcaps = pd.concat([ref.modcaps.reset_index(drop=True), pd.DataFrame([
        ["store_condensate", "storage", "", 0, 50, "condensate"],
    ], columns=ref.modcaps.columns)], ignore_index=True)
    return ref


def test_storage_only_pool_is_capacity_over_volume():
    # IRD-672's ground truth: one storage_pir_l_condensate_01 (50 m3) at 10 m3
    # per unit = 5 Protectyon, read in game. No recipe produces or consumes
    # condensate, so there is no throughput and no equal-hours split.
    frames = _frames(
        built=[["st1", "store_condensate", 1],
               # a condensate module with NO module_cap row must not crash
               # or contribute capacity (landmarks_soh_storage_condensate_01)
               ["st1", "store_condensate_unknown", 1]],
        universe=[["st1", "station"]],
        cargo=[["st1", "condensate", 4]])
    df = station_storage(frames, _condensate_ref())
    rows = [r for r in df.itertuples() if r.ware == "condensate"]
    assert len(rows) == 1                       # computed, not also proxied
    r = rows[0]
    assert r.max_units == 5.0 and r.max_volume == 50.0
    assert r.source == "computed" and r.role == "input"
    assert r.transport == "condensate" and r.throughput is None


def test_storage_only_pool_applies_to_producers_too():
    frames = _frames(
        built=[["st1", "prod_widget", 1], ["st1", "store_container", 1],
               ["st1", "store_condensate", 1]],
        universe=[["st1", "station"]],
        workforce=[["st1", "default", 100]])
    rows = {r.ware: r for r in station_storage(
        frames, _condensate_ref()).itertuples()}
    assert rows["condensate"].max_units == 5.0
    # the container pool split is untouched by the fourth pool
    assert abs(rows["widget"].max_units / rows["widget"].throughput
               - 98920 / 300) < 1e-6


def test_empty_inputs_return_empty():
    empty = SimpleNamespace(built_modules=pd.DataFrame(),
                            universe=pd.DataFrame(columns=["id", "class"]),
                            workforce_all=pd.DataFrame())
    out = station_storage(empty, _ref())
    assert out.empty
    assert list(out.columns) == ["station_id", "ware", "transport", "role",
                                 "throughput", "max_units", "max_volume",
                                 "source"]


# ---- non-producers: the equal-VOLUME split (v29, DHI-588) ------------------

def _trade_ref():
    """Two container wares of different volume, one solid ware, two races'
    rations -- enough to exercise every rule of the non-producer split."""
    ref = _ref()
    ref.wares = pd.DataFrame([
        ["widget", "container", "10", "container economy"],
        ["energy", "container", "1", "container economy"],
        ["food1", "container", "1", "container economy"],
        ["food2", "container", "2", "container economy"],
        ["rock", "solid", "5", "economy solid"],
    ], columns=["id", "transport", "volume", "tags"])
    ref.recipes = pd.DataFrame([
        ["widget", "default", 3600, 100, "energy", 100, 1.0],
        # argon-style: 90 food1 per 200 workers / 600 s
        ["workunit_busy", "default", 600, 200, "food1", 90, ""],
        # a second race eating a DIFFERENT ware at a different rate
        ["workunit_busy", "other", 600, 200, "food2", 45, ""],
    ], columns=["ware", "method", "time", "amount",
                "input_ware", "input_amount", "work_effect"])
    ref.modcaps = pd.DataFrame([
        ["prod_widget", "buildmodule", "", 100, 0, ""],
        ["store_container", "storage", "", 0, 100000, "container"],
        ["store_solid", "storage", "", 0, 50000, "solid"],
        ["store_mixed", "storage", "", 0, 120000, "container solid"],
    ], columns=["macro", "class", "housing", "workers",
                "cargo_max", "cargo_tags"])
    return ref


def _trader(built=None, workforce=None, offers=None, cargo=None):
    return _frames(
        built=built or [["t1", "store_container", 1], ["t1", "store_solid", 1]],
        universe=[["t1", "station"]],
        workforce=workforce,
        cargo=cargo,
        offers=offers if offers is not None else [
            ["t1", "buy", "widget", 5, 1, "", None],
            ["t1", "sell", "energy", 0, 1, "", None],
            ["t1", "buy", "rock", 7, 1, "", None]])


def _trade_rows(**kw):
    df = station_storage(_trader(**kw), _trade_ref())
    return {r.ware: r for r in df.itertuples()}


def test_non_producer_splits_each_pool_equally_by_volume():
    # container 100,000 m3 over the two traded container wares = 50,000 m3
    # each; solid 50,000 m3 over its one ware.
    rows = _trade_rows()
    assert rows["widget"].max_units == 50000 / 10
    assert rows["energy"].max_units == 50000 / 1     # a sell offer counts too
    assert rows["rock"].max_units == 50000 / 5
    assert all(r.source == "computed" for r in rows.values())
    assert rows["widget"].role == "input" and rows["widget"].throughput is None


def test_the_split_is_over_the_trade_list_not_the_cargo():
    # loot: a ware held with no offer against it gets no allocation at all,
    # and must not enter the divisor (KPU-477's teladianium).
    rows = _trade_rows(cargo=[["t1", "energy", 40], ["t1", "food1", 999]])
    assert "food1" not in rows                       # no offer -> no row
    assert rows["energy"].max_units == 50000         # still 2-way, not 3-way


def test_rations_are_keyed_on_the_races_PRESENT():
    # food1 is a ration for the race that works here; food2 is some other
    # race's ration and is an ordinary traded ware (DHI-588's water).
    offers = [["t1", "buy", "widget", 5, 1, "", None],
              ["t1", "buy", "food1", 5, 1, "", None],
              ["t1", "buy", "food2", 5, 1, "", None]]
    rows = _trade_rows(workforce=[["t1", "default", 200]], offers=offers)
    assert rows["food1"].role == "food"
    assert rows["food1"].max_units == 90 * 6 * FOOD_HOURS       # 2,160
    assert rows["food2"].role == "input"                        # not a ration
    # the buffer comes off the pool first, then the rest splits two ways
    share = (100000 - 2160 * 1) / 2
    assert rows["widget"].max_units == share / 10
    assert rows["food2"].max_units == share / 2


def test_no_workforce_means_no_ration_reserve_at_all():
    # JJX-981: a trade station with an empty workforce allocates its ration
    # wares a full ordinary share.
    offers = [["t1", "buy", "widget", 5, 1, "", None],
              ["t1", "buy", "food1", 5, 1, "", None]]
    rows = _trade_rows(offers=offers)
    assert rows["food1"].role == "input"
    assert rows["food1"].max_units == 50000


def test_the_ration_buffer_is_floored_PER_RACE():
    # DCO-580: two races on different wares AND both on medical supplies --
    # here both eat food1 at rates that each leave a fraction: 90/200 and
    # 45/200 per 200 workers per 600 s, over a 4 h buffer.
    ref = _trade_ref()
    ref.recipes = pd.DataFrame([
        ["widget", "default", 3600, 100, "energy", 100, 1.0],
        ["workunit_busy", "default", 600, 200, "food1", 90, ""],
        ["workunit_busy", "other", 600, 200, "food1", 45, ""],
    ], columns=["ware", "method", "time", "amount",
                "input_ware", "input_amount", "work_effect"])
    frames = _trader(workforce=[["t1", "default", 7], ["t1", "other", 7]],
                     offers=[["t1", "buy", "widget", 5, 1, "", None],
                             ["t1", "buy", "food1", 5, 1, "", None]])
    rows = {r.ware: r for r in station_storage(frames, ref).itertuples()}
    # per race: floor(18.9/h x 4 h) = 75 and floor(9.45/h x 4 h) = 37 -> 112.
    # One floor on the summed rate gives floor(28.35 x 4) = 113 and misses.
    assert rows["food1"].max_units == 112


def test_a_mixed_tag_storage_module_is_ONE_shared_pool():
    # JDV-447: cargo_tags "container solid" is one bay, so the container and
    # solid wares divide a single 120,000 m3 budget three ways, not
    # 120,000 twice.
    rows = _trade_rows(built=[["t1", "store_mixed", 1]])
    assert rows["widget"].max_units == 40000 / 10
    assert rows["energy"].max_units == 40000 / 1
    assert rows["rock"].max_units == 40000 / 5


def test_yards_keep_the_proxy_and_count_inbound():
    # build stations are NOT governed by the split (33% of their wares exceed
    # an equal share). They keep stock + inbound + open buy -- and the
    # inbound term is part of the definition save-semantics.md always gave.
    frames = _frames(
        built=[["w1", "buildmodule_ships", 1], ["w1", "store_container", 1]],
        universe=[["w1", "station"]],
        cargo=[["w1", "energy", 100]],
        offers=[["w1", "buy", "energy", 200, 5, "", None]])
    frames.trade_pending = pd.DataFrame(
        [["energy", 90, 40, "w1"], ["energy", 10, 10, "w1"],
         ["energy", 500, 0, "other"]],
        columns=["ware", "amount", "transferred", "buyer.id"])
    rows = {r.ware: r for r in station_storage(frames, _trade_ref()).itertuples()}
    # 100 stock + 200 bid + (90-40) in flight; the settled trade and another
    # station's inbound contribute nothing
    assert rows["energy"].max_units == 350
    assert rows["energy"].source == "proxy"


# ---- the employment target (v29, E-124) ------------------------------------

def _target_ref(target=1000.0):
    """A trade-station design that declares <workforce max> of its own."""
    ref = _trade_ref()
    ref.modcaps = pd.concat([ref.modcaps, pd.DataFrame([
        ["st_trade_design", "station", "", target, 0, ""],
    ], columns=ref.modcaps.columns)], ignore_index=True)
    return ref


def test_the_ration_basis_is_the_station_macros_employment_target():
    # PTW-627: the design declares 1,000 and the reserve is 4 h at 1,000
    # even though 10 workers live there. NOT the live workforce.
    frames = _frames(
        built=[["t1", "store_container", 1]],
        universe=[["t1", "station", "st_trade_design"]],
        workforce=[["t1", "default", 10]],
        offers=[["t1", "buy", "widget", 5, 1, "", None],
                ["t1", "buy", "food1", 5, 1, "", None]])
    rows = {r.ware: r for r in station_storage(frames, _target_ref()).itertuples()}
    assert rows["food1"].role == "food"
    assert rows["food1"].max_units == math.floor(
        90 / 200 / 600 * 3600 * 1000 * FOOD_HOURS)         # 10,800
    # and the reserve comes off the pool before the equal-volume split
    assert rows["widget"].max_units == (100000 - 10800) / 1 / 10


def test_the_target_and_the_job_slots_ADD():
    # MOP-635: an Argon trade-station macro (250 here: the design) carrying
    # build modules (100 job slots) reserves for 350, not for either alone.
    frames = _frames(
        built=[["t1", "store_container", 1], ["t1", "prod_widget", 1]],
        universe=[["t1", "station", "st_trade_design"]],
        workforce=[["t1", "default", 10]],
        offers=[["t1", "buy", "food1", 5, 1, "", None]])
    ref = _target_ref(250.0)
    rows = {r.ware: r for r in station_storage(frames, ref).itertuples()}
    assert rows["food1"].max_units == math.floor(
        90 / 200 / 600 * 3600 * (250 + 100) * FOOD_HOURS)


def test_a_declared_target_reserves_NOTHING_without_workers():
    # GMJ-316: same Argon design (target 250), no habitat and no workforce,
    # so its ration wares take full trading shares.
    frames = _frames(
        built=[["t1", "store_container", 1]],
        universe=[["t1", "station", "st_trade_design"]],
        offers=[["t1", "buy", "widget", 5, 1, "", None],
                ["t1", "buy", "food1", 5, 1, "", None]])
    rows = {r.ware: r for r in station_storage(frames, _target_ref(250)).itertuples()}
    assert rows["food1"].role == "input"
    assert rows["food1"].max_units == 50000


def test_the_target_splits_by_the_LIVE_race_mix_floored_per_race():
    # DHI-588: target 250 over argon 179 / other 72 (251 live) gives
    # floor(250 x 179/251) = 178 and floor(250 x 72/251) = 71.
    ref = _target_ref(250.0)
    ref.recipes = pd.DataFrame([
        ["widget", "default", 3600, 100, "energy", 100, 1.0],
        ["workunit_busy", "default", 600, 200, "food1", 90, ""],
        ["workunit_busy", "other", 600, 200, "food2", 45, ""],
    ], columns=["ware", "method", "time", "amount",
                "input_ware", "input_amount", "work_effect"])
    frames = _frames(
        built=[["t1", "store_container", 1]],
        universe=[["t1", "station", "st_trade_design"]],
        workforce=[["t1", "default", 179], ["t1", "other", 72]],
        offers=[["t1", "buy", "food1", 5, 1, "", None],
                ["t1", "buy", "food2", 5, 1, "", None],
                ["t1", "buy", "widget", 5, 1, "", None]])
    rows = {r.ware: r for r in station_storage(frames, ref).itertuples()}
    assert rows["food1"].max_units == math.floor(
        90 / 200 / 600 * 3600 * 178 * FOOD_HOURS)          # 1,922
    assert rows["food2"].max_units == math.floor(
        45 / 200 / 600 * 3600 * 71 * FOOD_HOURS)           # 383


def test_packaged_modcaps_carry_the_station_class_employment_targets():
    """Regression guard on the extraction glob: station macros live at
    assets/structures/macros/*.xml, one level shallower than module macros,
    and requiring the middle directory dropped all but the landmark one."""
    from pathlib import Path
    from x4analyzer.gamedata.refdata import load_refdata
    mc = load_refdata(Path("/nonexistent")).modcaps      # packaged copies
    st = mc[mc["class"].astype(str) == "station"]
    got = dict(zip(st["macro"], pd.to_numeric(st["workers"], errors="coerce")))
    assert got.get("station_arg_tradestation_base_01_macro") == 250
    assert got.get("station_gen_piratebase_base_01_macro") == 150
    assert got.get("landmarks_tel_tradestation_01_macro") == 1000
    assert len(st) >= 8
