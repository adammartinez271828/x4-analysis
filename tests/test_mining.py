from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.mining import (ASSUMED_TRIPS_PER_H,
                                        OBSERVED_WINDOW_H, raw_inflow,
                                        storage_blocked,
                                        typical_miner_capacity)
from x4analyzer.viz.audit import _mining_cards

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
            ["miner_solid_a", "mine", 8800.0, "solid", "M"],
            ["miner_solid_l", "mine", 40000.0, "solid", "L"],
            ["miner_liquid_a", "mine", 10000.0, "liquid", "M"],
            ["trans_a", "trade", 5000.0, "container", "M"],
        ]
    return SimpleNamespace(
        wares=wares,
        ships=pd.DataFrame(ships, columns=["macro", "purpose", "cargo",
                                           "cargo_tags", "class"]),
        ware_name={"ore": "Ore", "silicon": "Silicon", "methane": "Methane"},
    )


def _frames(stations, wings, ships, tradelog, cargo=None, time_now=NOW,
            limits=None, offers=None, storage=None):
    tl_cols = ["time", "commodity", "amount", "buyer.code", "seller.code",
               "seller.proxy.code"]
    f = SimpleNamespace(
        stations=pd.DataFrame(stations, columns=["id", "code", "name"]),
        wings=pd.DataFrame(wings, columns=["leader", "follower"]),
        ships=pd.DataFrame(ships, columns=["id", "macro", "code"]),
        tradelog=pd.DataFrame(tradelog, columns=tl_cols),
        station_cargo=pd.DataFrame(cargo or [],
                                   columns=["id", "ware", "amount"]),
        time_now=time_now,
    )
    # the storage-acceptance frames are optional everywhere: raw_inflow
    # reads them defensively, so most fixtures leave them off entirely
    if limits is not None:
        f.ware_limits = pd.DataFrame(limits,
                                     columns=["id", "kind", "ware", "amount"])
    if offers is not None:
        f.trade_offers = pd.DataFrame(
            offers, columns=["id", "side", "ware", "amount"])
    if storage is not None:
        f.station_storage = pd.DataFrame(
            storage, columns=["station_id", "ware", "max_units"])
    return f


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
    df, pools = raw_inflow(frames, _ref(), rates)
    df = df.set_index("ware")
    pl = pools.set_index(["class", "size"])

    # deliveries started 2h ago -> window clamps to 2h, 1760 units / 2h
    assert df.at["ore", "observed"] == 880.0
    assert df.at["ore", "own"] == 880.0
    assert df.at["ore", "deliveries"] == 2
    assert df.at["ore", "window_h"] == 2.0
    # solid M pool 2 x 8800 m³; measured 8800 m³/h delivered / 17600 m³
    assert pl.at[("solid", "M"), "miners"] == 2
    assert pl.at[("solid", "M"), "cap"] == 17600.0
    assert pl.at[("solid", "M"), "measured"] == 0.5
    assert pl.at[("solid", "M"), "rate_src"] == "measured"
    # solid inflow 8800 m³/h covers the 8000 m³/h demand -> no extra miners
    assert pl.at[("solid", "M"), "class_obs"] == 8800.0
    assert pl.at[("solid", "M"), "class_cons"] == 8000.0
    assert pl.at[("solid", "M"), "more_miners"] == 0
    # the L alternative is offered from game data, at the assumed L rate
    assert pl.at[("solid", "L"), "miners"] == 0
    assert pl.at[("solid", "L"), "avg_cap"] == 40000.0
    assert pl.at[("solid", "L"), "rate"] == ASSUMED_TRIPS_PER_H["L"]
    assert pl.at[("solid", "L"), "rate_src"] == "assumed"
    # gas pool never delivered: borrows the empire median of M pools
    assert pl.at[("liquid", "M"), "measured"] == 0.0
    assert pl.at[("liquid", "M"), "rate"] == 0.5
    assert pl.at[("liquid", "M"), "rate_src"] == "empire"
    # nothing arrives: 600 m³/h gap / (10000 m³ x 0.5 loads/h) -> 1 M miner
    assert pl.at[("liquid", "M"), "more_miners"] == 1
    # no liquid L miner exists in the game data -> no L option row
    assert ("liquid", "L") not in pl.index

    # theoretical: solid supply 17600 x 0.5 = 8800 m³/h, split by
    # consumption volume 6000:2000, converted back to units
    assert df.at["ore", "share"] == 0.75
    assert df.at["ore", "theoretical"] == 660.0
    assert df.at["silicon", "theoretical"] == 220.0
    assert df.at["methane", "theoretical"] == 10000.0 * 0.5 / 6
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
    df, pools = raw_inflow(frames, _ref(), rates)
    df = df.set_index("ware")
    pl = pools.set_index(["class", "size"])
    assert df.at["ore", "observed"] == 880.0 / OBSERVED_WINDOW_H
    assert df.at["ore", "theoretical"] == 0.0
    # the delivering ship is not assigned to the station -> not "own"
    assert df.at["ore", "own"] == 0.0
    # no fleet, nothing measured anywhere -> per-size assumptions; the
    # external deliveries count as supply: gap = 6000 - 1466.7 m³/h
    assert round(df.at["ore", "class_obs"], 1) == round(8800 / 6, 1)
    assert pl.at[("solid", "M"), "miners"] == 0
    assert pl.at[("solid", "M"), "avg_cap"] == 8800.0
    assert pl.at[("solid", "M"), "rate"] == ASSUMED_TRIPS_PER_H["M"]
    assert pl.at[("solid", "M"), "more_miners"] == 1
    # the same shortfall quoted in L miners (bigger hold, slower assumed)
    assert pl.at[("solid", "L"), "avg_cap"] == 40000.0
    assert pl.at[("solid", "L"), "rate"] == ASSUMED_TRIPS_PER_H["L"]
    assert pl.at[("solid", "L"), "more_miners"] == 1


def test_modded_miner_capacity_fallbacks():
    # macro absent from ships.csv: hold volume falls back to the ship's
    # biggest observed delivery in m³ (via the proxy "Executed by" code),
    # then to its current cargo volume; size falls back to M
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
    df, pools = raw_inflow(frames, _ref(), rates)
    df = df.set_index("ware")
    pl = pools.set_index(["class", "size"])
    assert pl.at[("solid", "M"), "miners"] == 2
    assert pl.at[("solid", "M"), "cap"] == (700 + 500) * 10.0   # m³
    assert df.at["ore", "own"] == 700.0
    # measured 7000 m³/h over the 12000 m³ pool; theoretical at that rate
    # equals what the fleet actually delivered
    assert round(pl.at[("solid", "M"), "measured"], 4) \
        == round(7000 / 12000, 4)
    assert round(df.at["ore", "theoretical"], 6) == 700.0
    # inflow 7000 m³/h covers the 6000 m³/h demand
    assert pl.at[("solid", "M"), "more_miners"] == 0


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
    df, pools = raw_inflow(frames, _ref(), _rates([]))
    df = df.set_index("ware")
    pl = pools.set_index(["class", "size"])
    assert df.at["ore", "share"] == 0.5
    assert df.at["ore", "cons"] == 0.0
    # measured still works without consumption: 2000 m³/h over 8800 m³,
    # and theoretical at that rate reproduces the actual deliveries
    assert round(pl.at[("solid", "M"), "measured"], 4) \
        == round(2000 / 8800, 4)
    assert round(df.at["ore", "theoretical"], 6) == 100.0
    assert pl.at[("solid", "M"), "more_miners"] == 0    # nothing consumed


def _starved(**kw):
    """A station consuming ore it barely receives — short on miners unless
    its ore storage turns out to be full."""
    return _frames(
        stations=[["st1", "STA-001", "Refinery"]],
        wings=[["st1", "m1"]],
        ships=[["m1", "miner_solid_a", "MIN-001"]],
        tradelog=[[NOW - 1 * H, "Ore", 100, "STA-001", "MIN-001", None]],
        cargo=[["st1", "ore", 39_610.0]],
        **kw)


def test_zero_buy_offer_alone_does_not_block():
    # offer amount = allocation - stock - inbound: in-flight deliveries
    # zero the bid on a station that is nowhere near full (MXH-411 read
    # "storage full" at 37% fill while draining), so a zero offer without
    # a trusted ceiling must NOT read as blocked
    frames = _starved(offers=[["st1", "buy", "ore", 0]])
    df, _pools = raw_inflow(frames, _ref(), _rates([["st1", "ore", 600.0]]))
    r = df.set_index("ware").loc["ore"]
    assert r["stock"] == 39_610.0
    assert r["want"] == 0.0
    assert pd.isna(r["limit"])
    assert not storage_blocked(r)


def test_proxy_allocation_is_not_a_ceiling():
    # build stations' proxy model is stock + inbound + open buys — a
    # ceiling derived from the stock itself can never evidence fullness
    frames = _starved()
    frames.station_storage = pd.DataFrame(
        [["st1", "ore", 40_000.0, "proxy"]],
        columns=["station_id", "ware", "max_units", "source"])
    df, _pools = raw_inflow(frames, _ref(), _rates([["st1", "ore", 600.0]]))
    r = df.set_index("ware").loc["ore"]
    assert pd.isna(r["limit"])
    assert not storage_blocked(r)
    # the same allocation from the computed model IS trusted
    frames.station_storage["source"] = "computed"
    df, _pools = raw_inflow(frames, _ref(), _rates([["st1", "ore", 600.0]]))
    r = df.set_index("ware").loc["ore"]
    assert r["limit"] == 40_000.0
    assert storage_blocked(r)


def test_storage_blocked_by_stock_at_limit():
    # the manual buy limit wins over the modelled allocation: 39,610 of
    # 40,000 is 99% full, while the 80,000 model ceiling would read as room
    frames = _starved(limits=[["st1", "buy", "ore", 40_000.0],
                              ["st1", "max", "ore", 60_000.0]],
                      storage=[["st1", "ore", 80_000.0]])
    df, _pools = raw_inflow(frames, _ref(), _rates([["st1", "ore", 600.0]]))
    r = df.set_index("ware").loc["ore"]
    assert r["limit"] == 40_000.0
    assert storage_blocked(r)
    # well below the same limit -> accepting again
    r2 = r.copy()
    r2["stock"] = 1_000.0
    assert not storage_blocked(r2)


def test_storage_columns_absent_frames_means_accepting():
    frames = _starved()          # no ware_limits / trade_offers / storage
    df, _pools = raw_inflow(frames, _ref(), _rates([["st1", "ore", 600.0]]))
    r = df.set_index("ware").loc["ore"]
    assert r["stock"] == 39_610.0
    assert pd.isna(r["limit"]) and pd.isna(r["want"])
    assert not storage_blocked(r)


def test_mining_cards_flags_storage_full_pool():
    ref, rates = _ref(), _rates([["st1", "ore", 600.0]])
    short = raw_inflow(_starved(), ref, rates)
    full = raw_inflow(_starved(limits=[["st1", "buy", "ore", 40_000.0]]),
                      ref, rates)
    name = {"st1": "Refinery (STA-001)"}
    sector = {"st1": "Grand Exchange I"}

    html_short, n_short = _mining_cards(*short, name, sector, str)
    html_full, n_full = _mining_cards(*full, name, sector, str)
    # the card header names the station's sector as muted fine print
    assert "Refinery (STA-001)" in html_short
    assert "Grand Exchange I" in html_short
    assert n_short == 1 and "assign +" in html_short
    assert "storage full" not in html_short
    # storage-blocked: flagged, no advice, and not counted as a finding
    assert n_full == 0
    assert "storage full" in html_full and "assign +" not in html_full


def test_mining_cards_partial_block_keeps_advice():
    # ore blocked, silicon still accepting -> the class stays a finding,
    # with a warn line naming the blocked ware
    frames = _frames(
        stations=[["st1", "STA-001", "Refinery"]],
        wings=[["st1", "m1"]],
        ships=[["m1", "miner_solid_a", "MIN-001"]],
        tradelog=[[NOW - 1 * H, "Ore", 100, "STA-001", "MIN-001", None]],
        cargo=[["st1", "ore", 39_610.0]],
        limits=[["st1", "buy", "ore", 40_000.0]])
    html, n = _mining_cards(*raw_inflow(
        frames, _ref(), _rates([["st1", "ore", 600.0],
                                ["st1", "silicon", 600.0]])),
        {"st1": "Refinery (STA-001)"}, {"st1": "Grand Exchange I"}, str)
    assert n == 1
    assert "assign +" in html
    assert "at storage limit" in html and "storage full" not in html


def test_typical_miner_capacity_prefers_own_fleet():
    ref = _ref(ships=[
        ["miner_solid_a", "mine", 8800.0, "solid", "M"],
        ["miner_solid_big", "mine", 12000.0, "solid", "M"],
        ["miner_solid_l", "mine", 40000.0, "solid", "L"],
        ["miner_liquid_a", "mine", 10000.0, "liquid", "M"],
    ])
    frames = _frames(
        stations=[["st1", "STA-001", "X"]], wings=[],
        ships=[["m1", "miner_solid_a", "MIN-001"]], tradelog=[])
    t = typical_miner_capacity(frames, ref)
    # player's own model wins over the game median of its size class
    assert t[("solid", "M")] == 8800.0
    assert t[("solid", "L")] == 40000.0
    assert t[("liquid", "M")] == 10000.0


def test_empty_inputs():
    frames = _frames(stations=[], wings=[], ships=[], tradelog=[])
    df, pools = raw_inflow(frames, _ref(), _rates([]))
    assert df.empty and pools.empty
    assert list(df.columns) == [
        "id", "ware", "class", "observed", "own", "theoretical", "cons",
        "balance", "share", "class_cons", "class_obs", "deliveries",
        "window_h", "stock", "limit", "want"]
    assert list(pools.columns) == [
        "id", "class", "size", "miners", "cap", "avg_cap", "measured",
        "rate", "rate_src", "class_cons", "class_obs", "more_miners"]
