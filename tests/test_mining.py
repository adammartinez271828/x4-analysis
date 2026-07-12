from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.mining import (MINER_TRIPS_PER_H,
                                        OBSERVED_WINDOW_H, raw_inflow)

NOW = 100_000.0
H = 3600.0


def _ref(ships=None):
    wares = pd.DataFrame([
        ["ore", "solid", "economy minable mineral solid"],
        ["silicon", "solid", "economy minable mineral solid"],
        ["methane", "liquid", "economy gas liquid minable"],
        ["energycells", "container", "economy"],
    ], columns=["id", "transport", "tags"])
    if ships is None:
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
    # solid pool 2 x 8800 split ore:silicon by consumption 600:200
    assert df.at["ore", "theoretical"] == 17600 * MINER_TRIPS_PER_H * 0.75
    assert df.at["silicon", "theoretical"] == 17600 * MINER_TRIPS_PER_H * 0.25
    assert df.at["ore", "miners"] == 2
    assert df.at["silicon", "miners"] == 2
    assert df.at["methane", "theoretical"] == 10000 * MINER_TRIPS_PER_H
    assert df.at["methane", "miners"] == 1
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


def test_modded_miner_capacity_fallbacks():
    # macro absent from ships.csv: capacity falls back to the ship's biggest
    # observed delivery (via the proxy "Executed by" code), then current cargo
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
    assert df.at["ore", "theoretical"] == (700 + 500) * MINER_TRIPS_PER_H


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
    assert df.at["ore", "theoretical"] == 4400.0 * MINER_TRIPS_PER_H
    assert df.at["silicon", "theoretical"] == 4400.0 * MINER_TRIPS_PER_H
    assert df.at["ore", "cons"] == 0.0


def test_empty_inputs():
    frames = _frames(stations=[], wings=[], ships=[], tradelog=[])
    df = raw_inflow(frames, _ref(), _rates([]))
    assert df.empty
    assert list(df.columns) == ["id", "ware", "class", "observed",
                                "theoretical", "cons", "balance", "miners"]
