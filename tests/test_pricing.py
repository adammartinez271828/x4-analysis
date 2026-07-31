"""Station ware-price model (analysis/pricing.py).

Three layers:

* **closed-form arithmetic** — the worked examples the game itself prints
  (UDX-946's ore and refined metals) plus the fixed-point books, all
  synthetic and DB-free;
* **a synthetic snapshot** — a hand-built in-memory analysis DB exercising
  book classification, the value cap, the self-consumption exemption and the
  defensive paths (unknown ware / faction / macro, missing allocation);
* **population regression guards** on the real 8E0C analysis DB, skipped
  cleanly where it is absent. Those pin the figures published in
  `docs/models/station-pricing-model.md` § How well it fits and the
  2026-07-30 Phase-2 reports; a drift in either the model or the storage
  allocation feeding it fails here first.

Numbers marked "in-game" come from the trade panel or the Logical Station
Overview, i.e. from the engine rather than from a fit.
"""
import math
import sqlite3
from pathlib import Path

import pytest

from x4analyzer.analysis import pricing as P

REAL_DB = (Path.home() / ".local/share/x4analyzer"
           / "x4_8E0C8E37-2192-49FD-BF4B-F535782A1C55.sqlite")

# bands used below, all stock (base+DLC) values: (min, avg, max)
ORE = (43.0, 50.0, 58.0)                    # asymmetric: −14 % / +16 %
REFINEDMETALS = (89.0, 148.0, 207.0)
ENERGYCELLS = (10.0, 16.0, 22.0)
HULLPARTS = (146.0, 209.0, 272.0)


# ---------------------------------------------------------------------------
# the closed form
# ---------------------------------------------------------------------------

def test_s_is_a_cosine_in_fill_with_the_global_span():
    # s = +1 at the band max, 0 at the average, −1 at the minimum, and the
    # cosine spans 1.095 fill units before it clamps
    assert P.s_of_u(0.0) == pytest.approx(1.0)
    assert P.s_of_u(P.SPAN / 2) == pytest.approx(0.0, abs=1e-12)
    assert P.s_of_u(P.SPAN) == pytest.approx(-1.0)
    # clamped either side: past the span it stays at the band edge
    assert P.s_of_u(-3.0) == pytest.approx(1.0)
    assert P.s_of_u(9.0) == pytest.approx(-1.0)


def test_u_of_s_inverts_s_of_u_away_from_the_clamps():
    for u in (0.1, 0.35, 0.5474, 0.9, 1.05):
        assert P.u_of_s(P.s_of_u(u)) == pytest.approx(u, abs=1e-12)


def test_price_branches_on_the_sign_of_s_for_asymmetric_bands():
    # 40 of 1,891 wares have asymmetric bands; on those, band position and s
    # disagree and only s is usable
    lo, avg, hi = ORE
    assert P.price_of_s(1.0, lo, avg, hi) == pytest.approx(hi)
    assert P.price_of_s(-1.0, lo, avg, hi) == pytest.approx(lo)
    assert P.price_of_s(0.0, lo, avg, hi) == pytest.approx(avg)
    # +0.5 reaches half the UP spread (4), −0.5 half the DOWN spread (3.5)
    assert P.price_of_s(0.5, lo, avg, hi) == pytest.approx(54.0)
    assert P.price_of_s(-0.5, lo, avg, hi) == pytest.approx(46.5)
    assert P.s_of_price(54.0, lo, avg, hi) == pytest.approx(0.5)
    assert P.s_of_price(46.5, lo, avg, hi) == pytest.approx(-0.5)


def test_degenerate_band_does_not_divide_by_zero():
    assert P.s_of_price(7.0, 7.0, 7.0, 7.0) == 0.0


def test_udx946_worked_example_reproduces_the_model_doc():
    """UDX-946 (ARG Ore Refinery I), the station whose price decomposition the
    game prints. Refined metals: fill 31,759 / 33,362.09, supplier offset
    +0.053 (it posts a sell offer) ⇒ 90.96 against the save's 90.33, i.e.
    0.0106 of a band — inside the supplier population's MAD of 0.0125."""
    net, allocation = 31759.0, 33362.092391
    price = P.main_sequence_price(net, allocation, *REFINEDMETALS,
                                  P.A_SUPPLIER)
    assert net / allocation == pytest.approx(0.9519, abs=5e-5)
    assert net / allocation + P.A_SUPPLIER == pytest.approx(1.0049, abs=5e-5)
    assert P.s_of_u(net / allocation + P.A_SUPPLIER) == pytest.approx(
        -0.9668, abs=5e-4)
    assert price == pytest.approx(90.96, abs=0.01)


def test_udx946_ore_the_two_readings_the_game_states_outright():
    """The panel prints *High Demand +6.6 %* on ore and 50 × 1.066 = 53.30
    exactly, which inverts to s = +0.4125 — and the ordinary consumer rule
    misses it badly (44.19). This is the model's documented honest edge, not a
    passing case: the pin is that the arithmetic still reproduces both."""
    assert P.price_of_s(0.4125, *ORE) == pytest.approx(53.30, abs=0.01)
    assert P.s_of_price(53.30, *ORE) == pytest.approx(0.4125, abs=1e-3)
    net, allocation = 9276.0, 10000.0
    assert P.main_sequence_price(net, allocation, *ORE,
                                 P.A_INPUT) == pytest.approx(44.19, abs=0.01)


def test_the_value_cap_is_a_credit_cap_not_a_unit_or_volume_cap():
    # energy cells at 16 Cr: 5 M / 16 = 312,500 units, well under a solar
    # plant's 992,398-unit allocation, so the cap binds
    assert P.capped_target(992398.0, 16.0) == pytest.approx(312500.0)
    # computronic substrate at 8,280 Cr: 604 units
    assert P.capped_target(5376.0, 8280.0) == pytest.approx(603.86, abs=0.01)
    # below 5 M of value the allocation itself is the target (m = 1)
    assert P.capped_target(1000.0, 16.0) == pytest.approx(1000.0)
    # a ware with no usable band must not divide by zero
    assert P.capped_target(1000.0, 0.0) == 1000.0
    assert P.capped_target(1000.0, float("nan")) == 1000.0


def test_gux488_energy_cells_the_in_game_anchored_solar_plant():
    """GUX-488 (Teladi, allocation 994,471 read in game), net 205,740 energy
    cells. The save's offer reads 13.36. `V` and `a` trade off along an exact
    ridge, so this lands on the cent at (5.00 M, 0.048) and 0.08 Cr away at
    the model doc's (5.00 M, 0.053) — E-116 is PENDING precisely because save
    data cannot tell those apart."""
    net, allocation = 205740.0, 994471.0
    target = P.capped_target(allocation, ENERGYCELLS[1])
    assert target == pytest.approx(312500.0)
    assert P.main_sequence_price(net, target, *ENERGYCELLS,
                                 0.048) == pytest.approx(13.36, abs=0.005)
    assert P.main_sequence_price(net, target, *ENERGYCELLS,
                                 P.A_SUPPLIER) == pytest.approx(13.28, abs=0.01)
    # uncapped, the same station would be told it is nearly empty
    assert P.main_sequence_price(net, allocation, *ENERGYCELLS,
                                 P.A_SUPPLIER) > 20.0


def test_main_sequence_price_is_nan_without_a_target():
    for target in (0.0, -5.0, float("nan")):
        assert math.isnan(P.main_sequence_price(100.0, target, *ORE,
                                                P.A_SUPPLIER))


# ---------------------------------------------------------------------------
# the fixed-point books
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("avg,mx,midpoint", [
    (209.0, 272.0, 240.5),        # hullparts   — the half-credit prices are
    (50.0, 57.0, 53.5),           # metallic…   — the strongest evidence that
    (1414.0, 1627.0, 1520.5),     # siliconcarb.  this is a midpoint rule and
    (57.0, 69.0, 63.0),           # smartchips    not ten per-ware constants
    (2040.0, 2346.0, 2193.0),     # claytronics
])
def test_supplies_is_the_band_midpoint(avg, mx, midpoint):
    assert P.supplies_price(avg, mx) == pytest.approx(midpoint)
    assert P.s_of_price(midpoint, 0.0, avg, mx) == pytest.approx(P.SUPPLIES_S)


def test_lockavgprice_sells_at_average_and_buys_one_credit_under():
    assert P.lockavgprice_price(510.0, "sell") == 510.0
    assert P.lockavgprice_price(510.0, "buy") == 509.0


def test_shady_has_two_tiers_and_the_tier_is_read_off_the_price():
    assert P.shady_price("continuum", 57.0, 69.0) == pytest.approx(71.898)
    assert P.shady_price("fixed", 57.0, 69.0) == pytest.approx(156.75)
    assert P.shady_tier_of_price(71.9, 57.0, 69.0) == "continuum"
    assert P.shady_tier_of_price(156.75, 57.0, 69.0) == "fixed"


def test_build_storage_shape_is_flat_then_falling():
    assert P.build_storage_band(0.0) == 1.0
    assert P.build_storage_band(P.BUILD_STORAGE_KNEE) == 1.0
    assert P.build_storage_band(P.BUILD_STORAGE_KNEE
                                + P.BUILD_STORAGE_WIDTH / 2) == pytest.approx(0.5)
    assert P.build_storage_band(5.0) == 0.0


def test_yard_power_band_is_clamped():
    assert P.yard_band(0.0) == 1.0
    assert P.yard_band(1.0) == 0.0
    assert P.yard_band(3.0) == 0.0
    assert 0.0 < P.yard_band(0.5) < 1.0


# ---------------------------------------------------------------------------
# a synthetic snapshot
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE save (save_id INTEGER PRIMARY KEY, guid TEXT);
CREATE VIEW current_save AS SELECT MAX(save_id) AS save_id FROM save;
CREATE TABLE component (save_id INT, id TEXT, class TEXT, macro TEXT,
                        name TEXT, code TEXT, owner TEXT);
CREATE TABLE trade_offer (save_id INT, object_id TEXT, side TEXT, ware TEXT,
                          amount REAL, price_cr REAL, flags TEXT,
                          desired REAL);
CREATE TABLE cargo (save_id INT, object_id TEXT, ware TEXT, amount REAL);
CREATE TABLE trade_pending (save_id INT, trade_id TEXT, ware TEXT,
                            amount REAL, transferred REAL, buyer_id TEXT,
                            seller_id TEXT);
CREATE TABLE station_storage (save_id INT, station_id TEXT, ware TEXT,
                              role TEXT, max_units REAL);
CREATE TABLE ware (id TEXT, price_min REAL, price_avg REAL, price_max REAL,
                   tags TEXT);
CREATE TABLE recipe (ware TEXT, method TEXT, input_ware TEXT);
CREATE TABLE module_ref (macro TEXT, ware TEXT, method TEXT);
CREATE TABLE build_entry (save_id INT, host_id TEXT, macro TEXT, built INT);
CREATE TABLE workforce (save_id INT, station_id TEXT, race TEXT, amount REAL);
CREATE TABLE station_trade_setting (save_id INT, object_id TEXT,
                                    setting TEXT, ware TEXT);
CREATE TABLE price_setting (save_id INT, object_id TEXT, kind TEXT,
                            ware TEXT);
CREATE TABLE ware_limit (save_id INT, object_id TEXT, kind TEXT, ware TEXT);
"""

_SAVE = 7                       # deliberately not 1: nothing may hardcode it


def _synthetic():
    """A five-station snapshot: a refinery, a lockavgprice trade station, a
    black marketeer, a shipyard and the player's own station."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    ex, exm = conn.execute, conn.executemany
    ex("INSERT INTO save VALUES (?, 'TEST')", (_SAVE,))
    exm("INSERT INTO ware VALUES (?,?,?,?,?)", [
        ("ore", 43, 50, 58, "container economy minable"),
        ("refinedmetals", 89, 148, 207, "container economy"),
        ("energycells", 10, 16, 22, "container economy stationbuilding"),
        ("hullparts", 146, 209, 272, "container economy stationbuilding"),
        ("foodrations", 24, 32, 40, "container economy"),
        ("spaceweed", 351, 439, 527, "container economy illegal"),
        # a ware with a degenerate band: must not divide by zero anywhere
        ("nividium", 510, 510, 510, "container economy"),
    ])
    exm("INSERT INTO recipe VALUES (?,?,?)", [
        ("refinedmetals", "default", "ore"),
        ("refinedmetals", "default", "energycells"),
        ("workunit_busy", "default", "foodrations"),
    ])
    exm("INSERT INTO module_ref VALUES (?,?,?)", [
        ("prod_gen_refinedmetals_macro", "refinedmetals", "default"),
        # a modded macro whose ware has no recipe at all: must be ignored
        ("mod_mystery_macro", "unobtanium", "default"),
    ])
    exm("INSERT INTO component VALUES (?,?,?,?,?,?,?)", [
        (_SAVE, "s1", "station", "prod_macro", "Refinery", "AAA-111", "argon"),
        (_SAVE, "s2", "station", "trade_macro", "Trader", "BBB-222", "boron"),
        (_SAVE, "s3", "station", "pirate_macro", "Den", "CCC-333", "scavenger"),
        (_SAVE, "s4", "station", "yard_macro", "Wharf", "DDD-444", "teladi"),
        (_SAVE, "s5", "station", "player_macro", "Mine", "EEE-555", "player"),
        (_SAVE, "b1", "buildstorage", None, "Plot", "FFF-666", "argon"),
        # a station the reference data does not know: owner not in factions,
        # macro not in modcaps — the joins must fall back, never raise
        (_SAVE, "s6", "station", "modded_macro", "Odd", "GGG-777", "modfaction"),
    ])
    exm("INSERT INTO build_entry VALUES (?,?,?,?)", [
        (_SAVE, "s1", "prod_gen_refinedmetals_macro", 1),
        (_SAVE, "s1", "storage_arg_m_container_macro", 1),
        (_SAVE, "s4", "buildmodule_gen_ships_l_macro", 1),
        (_SAVE, "s6", "mod_mystery_macro", 1),
        # planned but unbuilt: must not make s2 a yard
        (_SAVE, "s2", "buildmodule_gen_ships_s_macro", 0),
    ])
    exm("INSERT INTO workforce VALUES (?,?,?,?)", [
        (_SAVE, "s1", "argon", 452.0), (_SAVE, "s4", "argon", 1000.0)])
    exm("INSERT INTO cargo VALUES (?,?,?,?)", [
        (_SAVE, "s1", "refinedmetals", 31759.0),
        (_SAVE, "s1", "ore", 8100.0),
        (_SAVE, "s1", "foodrations", 500.0),
        (_SAVE, "s4", "energycells", 400000.0),
        (_SAVE, "s4", "hullparts", 61494.0),
        (_SAVE, "s5", "ore", 100.0),
        (_SAVE, "s6", "ore", 50.0),
    ])
    exm("INSERT INTO trade_pending VALUES (?,?,?,?,?,?,?)", [
        # 1,176 units still to arrive on s1's ore
        (_SAVE, "t1", "ore", 1500.0, 324.0, "s1", "sh1"),
        # a PURGED trade: amount 0, transferred 5,166 — the remainder must be
        # floored at zero rather than adding 5,166 units of stock
        (_SAVE, "t2", "ore", 0.0, 5166.0, "s1", "sh2"),
        # committed outbound: leaves s1's net
        (_SAVE, "t3", "refinedmetals", 1000.0, 0.0, "sh3", "s1"),
    ])
    exm("INSERT INTO station_storage VALUES (?,?,?,?,?)", [
        (_SAVE, "s1", "refinedmetals", "output", 33362.092391),
        (_SAVE, "s1", "ore", "input", 10000.0),
        (_SAVE, "s1", "foodrations", "food", 4050.0),
        (_SAVE, "s4", "energycells", "input", 500000.0),
        (_SAVE, "s4", "hullparts", "input", 61494.0),
        (_SAVE, "s5", "ore", "output", 5000.0),
        # s6 has an offer but NO storage row at all
    ])
    exm("INSERT INTO trade_offer VALUES (?,?,?,?,?,?,?,?)", [
        (_SAVE, "s1", "sell", "refinedmetals", 500, 89.41, "", None),
        (_SAVE, "s1", "buy", "ore", 700, 44.19, "", None),
        (_SAVE, "s1", "buy", "foodrations", 3550, 32.2, "", None),
        (_SAVE, "s1", "buy", "energycells", 900, 19.0,
         "supplies|invertfactionrestriction", 900),
        (_SAVE, "s2", "sell", "nividium", 100, 510.0, "", None),
        (_SAVE, "s2", "buy", "nividium", 100, 509.0, "", None),
        (_SAVE, "s3", "buy", "spaceweed", 60, 549.0,
         "buyercargovirtual|shady", None),
        (_SAVE, "s4", "buy", "energycells", 100000, 12.0, "", None),
        (_SAVE, "s4", "sell", "hullparts", 500, 168.37, "", None),
        (_SAVE, "s5", "sell", "ore", 100, 61.0, "", None),
        (_SAVE, "s6", "buy", "ore", 100, 47.0, "", None),
        (_SAVE, "b1", "buy", "hullparts", 5000, 272.0, "", None),
    ])
    exm("INSERT INTO station_trade_setting VALUES (?,?,?,?)", [
        (_SAVE, "s2", "lockavgprice", "nividium")])
    exm("INSERT INTO price_setting VALUES (?,?,?,?)", [
        (_SAVE, "s1", "reference", "ore")])       # NOT a manual override
    exm("INSERT INTO ware_limit VALUES (?,?,?,?)", [
        (_SAVE, "s5", "max", "ore")])
    conn.commit()
    return conn


@pytest.fixture(scope="module")
def synth():
    conn = _synthetic()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def synth_book(synth):
    return P.price_book(synth).set_index(["station_code", "ware", "side"])


def test_save_id_comes_from_current_save(synth):
    assert P.current_save_id(synth) == _SAVE
    assert (P.price_book(synth)["save_id"] == _SAVE).all()


def test_books_are_classified_by_flag_then_whitelist_then_host(synth_book):
    got = synth_book["book"].to_dict()
    assert got[("AAA-111", "refinedmetals", "sell")] == "main"
    assert got[("AAA-111", "energycells", "buy")] == "supplies"
    assert got[("BBB-222", "nividium", "sell")] == "lockavgprice"
    assert got[("CCC-333", "spaceweed", "buy")] == "shady"
    assert got[("DDD-444", "energycells", "buy")] == "yard"
    assert got[("EEE-555", "ore", "sell")] == "player"
    assert got[("FFF-666", "hullparts", "buy")] == "buildstorage"


def test_a_planned_build_module_does_not_make_a_yard(synth_book):
    # only BUILT entries count — station sequences list the whole plan twice
    assert synth_book.loc[("BBB-222", "nividium", "sell"), "book"] \
        == "lockavgprice"


def test_reference_price_settings_are_not_manual_overrides(synth_book):
    # price_setting kind='reference' is the engine's own bookkeeping (22,067
    # rows on the real save); only a non-reference row means a player override
    assert synth_book.loc[("AAA-111", "ore", "buy"), "book"] == "main"
    assert synth_book.loc[("EEE-555", "ore", "sell"), "book"] == "player"


def test_net_position_uses_pending_and_floors_the_purged_trade(synth_book):
    ore = synth_book.loc[("AAA-111", "ore", "buy")]
    assert ore["stock"] == 8100.0
    assert ore["inbound"] == 1176.0        # 1500 − 324, and NOT + 5,166
    assert ore["net"] == 9276.0
    rm = synth_book.loc[("AAA-111", "refinedmetals", "sell")]
    assert rm["outbound"] == 1000.0
    assert rm["net"] == 30759.0


def test_pending_duplication_is_detected_not_silently_doubled(synth):
    conn = _synthetic()
    conn.execute("INSERT INTO trade_pending VALUES (?,?,?,?,?,?,?)",
                 (_SAVE, "t1", "ore", 1500.0, 324.0, "s1", "sh1"))
    with pytest.raises(ValueError, match="duplicate trade_id"):
        P.price_book(conn)
    conn.close()


def test_populations_and_offsets(synth_book):
    rm = synth_book.loc[("AAA-111", "refinedmetals", "sell")]
    assert rm["population"] == "supplier" and rm["a"] == P.A_SUPPLIER
    ore = synth_book.loc[("AAA-111", "ore", "buy")]
    assert ore["population"] == "input" and ore["a"] == P.A_INPUT
    food = synth_book.loc[("AAA-111", "foodrations", "buy")]
    assert food["population"] == "ration" and food["a"] == P.A_RATION
    # a yard's inputs take the yard constant, not the −0.039 population median
    ec = synth_book.loc[("DDD-444", "energycells", "buy")]
    assert ec["population"] == "input"
    assert ec["a"] == pytest.approx(P.A_YARD, abs=0.05)


def test_fixed_point_books_predict_exactly(synth_book):
    assert synth_book.loc[("BBB-222", "nividium", "sell"),
                          "price_pred"] == 510.0
    assert synth_book.loc[("BBB-222", "nividium", "buy"),
                          "price_pred"] == 509.0
    # the supplies midpoint, and the price is independent of the position
    ec = synth_book.loc[("AAA-111", "energycells", "buy")]
    assert ec["price_pred"] == pytest.approx(19.0)
    assert ec["res"] == pytest.approx(0.0)


def test_the_cap_binds_on_the_supplier_side_only(synth_book):
    # s4 buys energy cells: consumer side, so the target is the allocation
    ec = synth_book.loc[("DDD-444", "energycells", "buy")]
    assert ec["target"] == pytest.approx(500000.0)
    # s1 sells refined metals worth 33,362 × 148 = 4.94 M — just under the cap
    rm = synth_book.loc[("AAA-111", "refinedmetals", "sell")]
    assert rm["target"] == pytest.approx(rm["allocation"])


def test_self_consumption_exemption_reverts_a_saturated_supplier(synth_book):
    """s4 is a wharf selling hull parts it also eats (built `buildmodule*` +
    a `stationbuilding` ware) at a net far above the capped target 5 M/209 =
    23,923. The cap would demand the band minimum; the exemption puts it back
    on the consumer book, which is what the observation shows (ULG-519 reads
    within 0.014 half-spreads that way, against +0.355 capped)."""
    hp = synth_book.loc[("DDD-444", "hullparts", "sell")]
    assert hp["self_consumed"]
    assert hp["exempt"]
    assert hp["target"] == pytest.approx(61494.0)     # back to the allocation
    assert abs(hp["res"]) < 0.10
    # without the exemption the same offer is sent to the band minimum
    capped = P.price_book(_synthetic(), self_consumed_exemption=False)
    row = capped[(capped["station_code"] == "DDD-444")
                 & (capped["ware"] == "hullparts")].iloc[0]
    assert not row["exempt"]
    assert row["target"] == pytest.approx(5_000_000 / 209.0)
    assert row["price_pred"] == pytest.approx(146.0)   # the band minimum


def test_unknown_wares_factions_and_macros_do_not_crash(synth):
    """Saves are modded (~60 mods here). A station whose owner, macro and
    module are absent from the reference CSVs, holding an offer with no
    storage row, must classify and yield NaN — never raise."""
    conn = _synthetic()
    conn.execute("INSERT INTO trade_offer VALUES (?,?,?,?,?,?,?,?)",
                 (_SAVE, "s6", "buy", "unobtanium", 10, 999.0, "", None))
    book = P.price_book(conn)
    odd = book[book["station_code"] == "GGG-777"]
    assert len(odd) == 2
    assert set(odd["book"]) == {"main"}
    assert odd["allocation"].isna().all()            # no station_storage row
    assert odd["price_pred"].isna().all()            # so no prediction
    assert odd["res"].isna().all()
    conn.close()


def test_scoring_harness_runs_on_a_tiny_population(synth_book):
    scores = P.population_scores(synth_book.reset_index())
    assert set(scores["population"]) >= {"main: all", "all offers"}
    assert (scores["n"] >= 0).all()
    yard = P.score_yard_forms(synth_book.reset_index())
    assert len(yard) == 3


def test_bin_median_rmse_ignores_non_finite_and_empty_input():
    import pandas as pd
    assert math.isnan(P.bin_median_rmse(pd.DataFrame()))
    frame = pd.DataFrame({"fill": [0.1, float("nan")], "abs_res": [0.2, 0.3]})
    assert P.bin_median_rmse(frame, bins=4) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# population regression guards on the real analysis DB
# ---------------------------------------------------------------------------

real_db = pytest.mark.skipif(
    not REAL_DB.exists(),
    reason=f"price-model population guards skipped — 8E0C analysis DB not "
           f"present at {REAL_DB}")


@pytest.fixture(scope="module")
def real_conn():
    if not REAL_DB.exists():
        pytest.skip("no real DB")
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def real_book(real_conn):
    return P.price_book(real_conn)


@pytest.fixture(scope="module")
def real_scores(real_book):
    return P.population_scores(real_book).set_index("population")


@real_db
def test_real_snapshot_is_resolved_not_hardcoded(real_conn, real_book):
    expected = real_conn.execute(
        "SELECT save_id FROM current_save").fetchone()[0]
    assert (real_book["save_id"] == expected).all()
    assert len(real_book) > 10000


@real_db
def test_fixed_point_books_are_exact_on_the_real_save(real_book):
    """`lockavgprice` and `supplies` are laws, not fits: every offer in each
    book must land on its rule to the cent."""
    for name in ("lockavgprice", "supplies"):
        sub = real_book[real_book["book"] == name]
        assert len(sub) > 500, name
        assert (sub["price_cr"] - sub["price_pred"]).abs().max() \
            == pytest.approx(0.0, abs=1e-9), name


@real_db
def test_shady_tiers_are_disjoint_by_station(real_book):
    """E-112: the two tiers do not mix within a station. The tier here is read
    off each offer independently, so a station carrying both would mean the
    classification (or the claim) is wrong."""
    shady = real_book[real_book["book"] == "shady"]
    mixed = shady.groupby("station_id")["shady_tier"].nunique()
    assert (mixed > 1).sum() == 0
    assert len(mixed) > 500


@real_db
def test_shady_fixed_tier_correlates_with_zero_workforce(real_conn, real_book):
    census = P.shady_tier_census(real_conn, real_book).set_index("tier")
    assert census.loc["fixed", "zero_workforce"] > 0.9
    assert census.loc["continuum", "zero_workforce"] < 0.1


@real_db
def test_gux488_energy_cells_offer_price(real_conn, real_book):
    """The in-game-anchored capped solar plant. Its offer reads 13.36; the
    capped target must land within a few hundredths of a band of it."""
    row = real_book[(real_book["station_code"] == "GUX-488")
                    & (real_book["ware"] == "energycells")
                    & (real_book["side"] == "sell")]
    if row.empty:
        pytest.skip("GUX-488 not selling energy cells on this snapshot")
    row = row.iloc[0]
    assert row["price_cr"] == pytest.approx(13.36, abs=0.01)
    assert row["target"] == pytest.approx(312500.0, rel=1e-6)
    assert abs(row["res"]) < 0.03
    # at a = 0.048 the same offer lands on the cent — the V/a ridge, E-116
    tuned = P.price_book(real_conn, a_supplier=0.048)
    t = tuned[(tuned["station_code"] == "GUX-488")
              & (tuned["ware"] == "energycells")
              & (tuned["side"] == "sell")].iloc[0]
    assert t["price_pred"] == pytest.approx(13.36, abs=0.01)


@real_db
def test_ulg519_hull_parts_takes_the_exemption(real_book):
    """The one station where the exemption's offset is independently
    checkable: ULG-519's input constant reads −0.202/−0.203 on three inputs
    and its saturated hull-parts sell offer reads −0.208."""
    row = real_book[(real_book["station_code"] == "ULG-519")
                    & (real_book["ware"] == "hullparts")
                    & (real_book["side"] == "sell")]
    if row.empty:
        pytest.skip("ULG-519 not selling hull parts on this snapshot")
    row = row.iloc[0]
    assert row["self_consumed"] and row["exempt"]
    assert abs(row["res"]) < 0.05


@real_db
def test_population_metrics_match_the_published_figures(real_scores):
    """`docs/models/station-pricing-model.md` § How well it fits, re-derived
    on the current snapshot. MAD is the MEDIAN absolute residual in band
    units; `tail` is the |res| > 0.25 fraction."""
    ration = real_scores.loc["main: ration"]
    assert ration["n"] > 2000
    assert ration["mad"] < 0.005            # published 0.0015 — the tightest
    assert ration["tail"] < 0.005           # published 0.04 %

    supplier = real_scores.loc["main: supplier"]
    assert supplier["n"] > 1500
    assert supplier["mad"] < 0.020          # published 0.0130
    assert supplier["tail"] < 0.030         # published 1.48 % with the cap

    inputs = real_scores.loc["main: input"]
    assert inputs["n"] > 2500
    assert inputs["mad"] < 0.090            # published 0.0717
    assert inputs["tail"] < 0.120           # published 8.64 %

    main = real_scores.loc["main: all"]
    assert main["n"] > 7000
    assert main["mad"] < 0.020              # published 0.0141
    assert main["tail"] < 0.060             # published 4.03 %
    # the published bin figure is the SIGNED per-bin median (0.0066)
    assert main["bin_rmse_signed"] < 0.015


@real_db
def test_the_value_cap_still_earns_its_place(real_conn, real_scores):
    """Removing the cap must blow up the supplier tail — published 9.77 % →
    1.48 %. Scored on the whole supplier population, not the binding cohort."""
    uncapped = P.population_scores(
        P.price_book(real_conn, value_cap=float("inf"))).set_index("population")
    assert uncapped.loc["main: supplier", "tail"] > 0.05
    assert real_scores.loc["main: supplier", "tail"] < 0.02


@real_db
def test_the_self_consumption_exemption_earns_its_place(real_conn, real_scores):
    """R5 of the cap-scope report: exempting a self-consumed ware ABOVE its
    capped target must fix the saturated cohort and stay neutral elsewhere."""
    without = P.population_scores(
        P.price_book(real_conn, self_consumed_exemption=False)
    ).set_index("population")
    binds = "main: supplier, cap binds"
    assert without.loc[binds, "bin_rmse"] > 5 * real_scores.loc[binds,
                                                                "bin_rmse"]
    # neutral save-wide: it must not buy the cohort by degrading the rest
    assert real_scores.loc["main: all", "mad"] \
        <= without.loc["main: all", "mad"] + 1e-6


@real_db
def test_yard_book_is_the_cosine_not_the_clamped_power(real_book):
    """The yard-form scoring this module was asked to settle. Both candidates
    carry one parameter fitted on this same population, so the comparison is
    like for like; the cosine on the ordinary storage allocation with the
    −0.202 station constant wins by more than an order of magnitude, and it
    also explains the ~0.17 band floor at full that the power form leaves
    unexplained."""
    forms = P.score_yard_forms(real_book).set_index("form")
    power = [i for i in forms.index if i.startswith("power")][0]
    flat = [i for i in forms.index if "flat" in i][0]
    assert forms.loc[flat, "bin_rmse"] < forms.loc[power, "bin_rmse"] / 10
    assert forms.loc[flat, "mad"] < forms.loc[power, "mad"] / 10
    assert forms.loc[flat, "tail"] < 0.05
    assert forms.loc[power, "tail"] > 0.15


@real_db
def test_yard_population_is_tightly_fitted(real_scores):
    yard = real_scores.loc["book: yard"]
    assert yard["n"] > 500
    assert yard["mad"] < 0.01
    assert yard["tail"] < 0.05


@real_db
def test_every_offer_is_classified_and_labelled(real_book):
    assert set(real_book["book"]) <= set(P.BOOKS)
    assert set(real_book["confidence"]) <= {"law", "descriptive", "none"}
    # player offers are off-model by design and must never claim a prediction
    player = real_book[real_book["book"] == "player"]
    assert len(player) > 0
    assert player["price_pred"].isna().all()
    # build storages hold no allocation at all — that is the reason they have
    # no closed form, and it must stay true
    build = real_book[real_book["book"] == "buildstorage"]
    assert len(build) > 1000
    assert build["allocation"].notna().sum() == 0
    assert (build["confidence"] == "descriptive").all()
