from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.mining import (MINER_TRIPS_PER_H,
                                        OBSERVED_WINDOW_H, raw_inflow,
                                        typical_miner_capacity)

NOW = 100_000.0
H = 3600.0


def _ref(ships=None):
    wares = pd.DataFrame([
        ["ore", "solid", "economy minable mineral solid", "10"],
        ["silicon", "solid", "economy minable mineral solid", "10"],
        ["methane", "liquid", "economy gas liquid minable", "6"],
        ["energycells", "container", "economy", "1"],
    ], columns=["id", "transport", "tags", "volume"])
    if ships is None:
        # cargo is hold VOLUME (m³): 8800 m³ = 880 ore at 10 m³/unit
        ships = [
            ["miner_solid_a", "mine", 8800.0, "solid"],
            ["miner_liquid_a", "mine", 10000.0, "liquid"],
            ["trans_a", "trade", 5000.0, "container"],
        ]
    return SimpleNamespace(
        wares=wares,
        ships=pd.DataFrame(ships, columns=["macro", "purpose", "cargo",
                                           "cargo_tags"]),
        ware_name={"ore": "Ore", "silicon": "Silicon", "methane": "Methane"},
    )


def _frames(stations, wings, ships, tradelog, cargo=None, time_now=NOW):
    tl_cols = ["time", "commodity", "amount", "buyer.code", "seller.code",
               "seller.proxy.code"]
    return SimpleNamespace(
        stations=pd.DataFrame(stations, columns=["id", "code", "name"]),
        wings=pd.DataFrame(wings, columns=["leader", "follower"]),
        ships=pd.DataFrame(ships, columns=["id", "macro", "code"]),
        tradelog=pd.DataFrame(tradelog, columns=tl_cols),
        station_cargo=pd.DataFrame(cargo or [],
                                   columns=["id", "ware", "amount"]),
        time_now=time_now,
    )


def _rates(rows):
    df = pd.DataFrame(rows, columns=["id", "ware", "cons"])
    df["faction"] = "PLA"
    df["prod"] = 0.0
    return df


def test_observed_theoretical_and_split():
    frames = _frames(
        stations=[["st1", "STA-001", "Refinery"]],
        wings=[["st1", "m1"], ["st1", "m2"], ["st1", "g1"], ["st1", "f1"]],
        ships=[["m1", "miner_solid_a", "MIN-001"],
               ["m2", "miner_solid_a", "MIN-002"],
               ["g1", "miner_liquid_a", "GAS-001"],
               ["f1", "trans_a", "TRD-001"]],       # trader: not a miner
        tradelog=[
            [NOW - 2 * H, "Ore", 880, "STA-001", "MIN-001", None],
            [NOW - 1 * H, "Ore", 880, "STA-001", "MIN-002", None],
        ],
    )
    rates = _rates([["st1", "ore", 600.0], ["st1", "silicon", 200.0],
                    ["st1", "methane", 100.0]])
    df = raw_inflow(frames, _ref(), rates).set_index("ware")

    # deliveries started 2h ago -> window clamps to 2h, 1760 units / 2h
    assert df.at["ore", "observed"] == 880.0
    assert df.at["ore", "own"] == 880.0
    assert df.at["ore", "deliveries"] == 2
    assert df.at["ore", "window_h"] == 2.0
    # solid pool 2 x 8800 m³, split ore:silicon by consumption VOLUME
    # 6000:2000 m³/h; per fleet trip: 17600 x 0.75 / 10 = 1320 ore units
    assert df.at["ore", "share"] == 0.75
    assert df.at["ore", "per_trip"] == 1320.0
    assert df.at["silicon", "per_trip"] == 440.0
    assert df.at["ore", "miners"] == 2
    assert df.at["ore", "class_cap"] == 17600.0
    assert df.at["ore", "class_cons"] == 8000.0     # m³/h
    assert df.at["ore", "avg_cap"] == 8800.0
    # measured: 880 ore/h x 10 m³ = 8800 m³/h over a 17600 m³ pool = 0.5x
    assert df.at["ore", "measured"] == 0.5
    assert df.at["silicon", "measured"] == 0.5      # class-level value
    # theoretical runs at the fleet's MEASURED rate
    assert df.at["ore", "rate"] == 0.5
    assert df.at["ore", "theoretical"] == 1320.0 * 0.5
    assert df.at["silicon", "theoretical"] == 440.0 * 0.5
    # solid supply at measured rate: 17600 x 0.5 = 8800 m³/h covers the
    # 8000 m³/h class demand -> no extra miners
    assert df.at["ore", "more_miners"] == 0
    # liquid pool: 10000 m³ / 6 m³ per methane; the gas fleet never
    # delivered, so it borrows the measured median of the other fleets
    assert df.at["methane", "per_trip"] == 10000.0 / 6
    assert df.at["methane", "miners"] == 1
    assert df.at["methane", "measured"] == 0.0
    assert df.at["methane", "rate"] == 0.5
    assert df.at["methane", "theoretical"] == 10000.0 / 6 * 0.5
    assert df.at["ore", "balance"] == 880.0 - 600.0
    assert df.at["silicon", "observed"] == 0.0


def test_rolling_window_excludes_old_deliveries():
    frames = _frames(
        stations=[["st1", "STA-001", "Refinery"]],
        wings=[], ships=[],
        tradelog=[
            [NOW - 10 * H, "Ore", 880, "STA-001", "MIN-001", None],
            [NOW - 1 * H, "Ore", 880, "STA-001", "MIN-001", None],
        ],
    )
    rates = _rates([["st1", "ore", 600.0]])
    df = raw_inflow(frames, _ref(), rates).set_index("ware")
    assert df.at["ore", "observed"] == 880.0 / OBSERVED_WINDOW_H
    assert df.at["ore", "miners"] == 0
    assert df.at["ore", "theoretical"] == 0.0
    # the delivering ship is not assigned to the station -> not "own"
    assert df.at["ore", "own"] == 0.0
    assert df.at["ore", "measured"] == 0.0
    # nothing measured anywhere -> the hardcoded assumption steps in
    assert df.at["ore", "rate"] == MINER_TRIPS_PER_H
    # "one more miner" sized from game data although none are assigned:
    # gap 6000 m³/h / (8800 m³ x rate) -> 1 miner
    assert df.at["ore", "avg_cap"] == 8800.0
    assert df.at["ore", "more_miners"] == 1


def test_modded_miner_capacity_fallbacks():
    # macro absent from ships.csv: hold volume falls back to the ship's
    # biggest observed delivery in m³ (via the proxy "Executed by" code),
    # then to its current cargo volume
    frames = _frames(
        stations=[["st1", "STA-001", "Refinery"]],
        wings=[["st1", "m1"], ["st1", "m2"]],
        ships=[["m1", "modded_miner_solid_x", "MOD-001"],
               ["m2", "modded_miner_solid_y", "MOD-002"]],
        tradelog=[
            # proxied trade: seller.code is the commander, proxy = the miner
            [NOW - 1 * H, "Ore", 700, "STA-001", "STA-001", "MOD-001"],
        ],
        cargo=[["m2", "ore", 500.0]],
    )
    rates = _rates([["st1", "ore", 600.0]])
    df = raw_inflow(frames, _ref(), rates).set_index("ware")
    assert df.at["ore", "miners"] == 2
    assert df.at["ore", "class_cap"] == (700 + 500) * 10.0   # m³
    assert df.at["ore", "per_trip"] == 1200.0
    assert df.at["ore", "own"] == 700.0
    # measured 7000 m³/h over the 12000 m³ pool; theoretical at that rate
    # equals what the fleet actually delivered
    assert round(df.at["ore", "rate"], 4) == round(7000 / 12000, 4)
    assert round(df.at["ore", "theoretical"], 6) == 700.0


def test_even_split_without_consumption():
    frames = _frames(
        stations=[["st1", "STA-001", "Depot"]],
        wings=[["st1", "m1"]],
        ships=[["m1", "miner_solid_a", "MIN-001"]],
        tradelog=[
            [NOW - 1 * H, "Ore", 100, "STA-001", "MIN-001", None],
            [NOW - 1 * H, "Silicon", 100, "STA-001", "MIN-001", None],
        ],
    )
    df = raw_inflow(frames, _ref(), _rates([])).set_index("ware")
    assert df.at["ore", "share"] == 0.5
    assert df.at["ore", "per_trip"] == 440.0
    assert df.at["silicon", "per_trip"] == 440.0
    assert df.at["ore", "cons"] == 0.0
    # measured still works without consumption: 2000 m³/h over 8800 m³,
    # and theoretical at that rate reproduces the actual deliveries
    assert round(df.at["ore", "measured"], 4) == round(2000 / 8800, 4)
    assert round(df.at["ore", "theoretical"], 6) == 100.0
    assert df.at["ore", "more_miners"] == 0    # nothing consumed


def test_typical_miner_capacity_prefers_own_fleet():
    ref = _ref(ships=[
        ["miner_solid_a", "mine", 8800.0, "solid"],
        ["miner_solid_big", "mine", 40000.0, "solid"],
        ["miner_liquid_a", "mine", 10000.0, "liquid"],
    ])
    frames = _frames(
        stations=[["st1", "STA-001", "X"]], wings=[],
        ships=[["m1", "miner_solid_a", "MIN-001"]], tradelog=[])
    t = typical_miner_capacity(frames, ref)
    assert t["solid"] == 8800.0      # player's own model, not the game median
    assert t["liquid"] == 10000.0    # no own liquid miner -> game data


def test_empty_inputs():
    frames = _frames(stations=[], wings=[], ships=[], tradelog=[])
    df = raw_inflow(frames, _ref(), _rates([]))
    assert df.empty
    assert list(df.columns) == [
        "id", "ware", "class", "observed", "own", "theoretical", "per_trip",
        "cons", "balance", "miners", "share", "class_cap", "class_cons",
        "avg_cap", "measured", "rate", "more_miners", "deliveries",
        "window_h"]
