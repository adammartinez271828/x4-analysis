"""Trade-opportunity pairing (analysis/opportunities.py) on synthetic
offers: spread metrics, player-endpoint pricing, exclusions, jumps, route
lengths and loadout travel speeds."""

from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.opportunities import (build_opportunities,
                                               player_trade_ships)


def _ref(**over):
    base = dict(
        wares=pd.DataFrame({
            "id": ["silicon", "advancedelectronics"],
            "name": ["Silicon Wafers", "Advanced Electronics"],
            "volume": [18, 30],
        }),
        # chain a -(gates at a:+100km / b:-50km)- b -(b:+50km / c:-20km z)- c
        gates=pd.DataFrame({
            "sector_a": ["sec_a", "sec_b"],
            "sector_b": ["sec_b", "sec_c"],
            "ax": [100_000.0, 50_000.0],
            "az": [0.0, 0.0],
            "bx": [-50_000.0, 0.0],
            "bz": [0.0, -20_000.0],
        }),
        sectors=pd.DataFrame({
            "cluster": ["cl_a", "cl_b", "cl_c"],
            "macro": ["sec_a", "sec_b", "sec_c"],
            "highway": [0, 1, 0],       # only the middle sector has a ring
        }),
        ships=pd.DataFrame({
            "macro": ["ship_arg_m_trans_1_macro", "ship_arg_m_fight_1_macro"],
            "model": ["Boa", "Jaguar"],
            "class": ["M", "M"],
            "cargo": [4900.0, 0.0],
            "cargo_tags": ["container", ""],
            "drag_forward": [50.0, 20.0],
        }),
        engines=pd.DataFrame({
            "macro": ["engine_arg_m_travel_01_mk1_macro"],
            "size": ["m"], "type": ["travel"], "mk": [1],
            "forward": [1000.0], "travel_thrust": [10.0],
        }),
        faction_short={"argon": "ARG", "teladi": "TEL", "kaori": "QUE"},
        ware_name={"silicon": "Silicon Wafers",
                   "advancedelectronics": "Advanced Electronics"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _universe():
    return pd.DataFrame({
        "id": ["sell_npc", "buy_npc", "sell_pla", "buy_pla",
               "sell_xen", "site", "buy_que", "ship1"],
        "class": ["station"] * 5 + ["buildstorage", "station", "ship_m"],
        "owner": ["argon", "teladi", "player", "player",
                  "xenon", "teladi", "kaori", "player"],
        "name": ["Foundry", "Fab", "My Mine", "My Fab", "X", "",
                 "Barter Post", "Hauler One"],
        "code": ["AAA-111", "BBB-222", "PPP-111", "PPP-222",
                 "XXX-666", "CCC-333", "QQQ-444", "HHH-001"],
        "knownto": ["player", "player", "player", "player",
                    "player", "", "player", "player"],
        "stype": [""] * 8,
        "sector.macro": ["sec_a", "sec_c", "sec_a", "sec_c",
                         "sec_b", "sec_b", "sec_c", "sec_a"],
        "macro": [""] * 7 + ["ship_arg_m_trans_1_macro"],
        "sx": [0.0, 0.0, 30_000.0, None, 0.0, 0.0, 0.0, 0.0],
        "sz": [0.0, 10_000.0, 40_000.0, None, 0.0, 0.0, 0.0, 0.0],
    })


def _frames(offers, ship_engines=None):
    sectors = pd.DataFrame({
        "macro": ["sec_a", "sec_b", "sec_c"],
        "name": ["Alpha", "Beta", "Gamma"],
    })
    return SimpleNamespace(
        trade_offers=offers, universe=_universe(), sectors=sectors,
        ship_engines=ship_engines if ship_engines is not None
        else pd.DataFrame(columns=["id", "macro", "n"]))


def _cfg(**over):
    base = dict(spoilers_hide=False)
    base.update(over)
    return SimpleNamespace(**base)


def _offers(rows):
    return pd.DataFrame(rows, columns=["id", "side", "ware", "amount",
                                       "price"])


def test_npc_pair_metrics_and_route():
    rows = build_opportunities(_frames(_offers([
        ("sell_npc", "sell", "silicon", 500.0, 171.0),
        ("buy_npc", "buy", "silicon", 300.0, 460.0),
    ])), _ref(), _cfg())
    (r,) = rows
    assert r["spread"] == 289.0
    assert r["pm3"] == round(289 / 18, 2)
    assert r["j"] == 2                       # sec_a -> sec_b -> sec_c
    assert r["rate"] == round(289 / 18 / 2, 2)
    assert r["du"] == 300.0                  # depth = min(500, 300)
    assert r["dm3"] == 5400.0
    assert r["total"] == 300 * 289
    # route legs: 100 km to the gate in sec_a (plain), 100 km across
    # sec_b (highway sector), 30 km entry gate -> station in sec_c
    assert (r["kp"], r["kh"]) == (130.0, 100.0)
    assert r["s"]["l"] == "Foundry (AAA-111)" and r["s"]["sec"] == "Alpha"
    assert r["b"]["f"] == "TEL"


def test_same_sector_route_is_direct_distance():
    rows = build_opportunities(_frames(_offers([
        ("sell_pla", "sell", "silicon", 100.0, 171.0),   # at (30, 40) km
        ("sell_npc", "buy", "silicon", 300.0, 460.0),    # at (0, 0)
    ])), _ref(), _cfg())
    (r,) = rows
    assert r["j"] == 0
    assert (r["kp"], r["kh"]) == (50.0, 0.0)   # 3-4-5 triangle, no highway


def test_player_seller_is_pure_profit_and_player_buyer_drops():
    rows = build_opportunities(_frames(_offers([
        ("sell_pla", "sell", "silicon", 100.0, 171.0),   # own goods: cost 0
        ("buy_npc", "buy", "silicon", 300.0, 460.0),
        ("sell_npc", "sell", "silicon", 500.0, 171.0),
        ("buy_pla", "buy", "silicon", 300.0, 999.0),     # own buyer: earns 0
    ])), _ref(), _cfg())
    # pairs: pla->npc (spread 460) and npc->npc (289); npc->pla and
    # pla->pla go non-positive and drop
    assert [(r["s"]["l"], r["b"]["l"]) for r in rows] == [
        ("My Mine (PPP-111)", "Fab (BBB-222)"),
        ("Foundry (AAA-111)", "Fab (BBB-222)"),
    ]
    assert rows[0]["ask"] == 0 and rows[0]["spread"] == 460.0
    assert rows[0]["s"]["p"] == 1
    assert rows[0]["s"]["price"] == 171.0    # the save's price, for the UI


def test_exclusions_flags_and_construction_buyer():
    rows = build_opportunities(_frames(_offers([
        ("sell_xen", "sell", "silicon", 500.0, 1.0),     # xenon: out
        ("sell_npc", "sell", "silicon", 500.0, 0.0),     # junk 0-price: out
        ("site", "sell", "silicon", 500.0, 100.0),       # sites never sell
        ("sell_npc", "sell", "advancedelectronics", 50.0, 863.0),
        ("site", "buy", "advancedelectronics", 20.0, 1404.0),
        ("buy_que", "buy", "advancedelectronics", 10.0, 1500.0),
    ])), _ref(), _cfg())
    assert len(rows) == 2
    que = next(r for r in rows if r["b"]["f"] == "QUE")
    assert que["b"]["qt"] == 1               # barter faction, UI-excluded
    site = next(r for r in rows if r["b"].get("c"))
    assert site["pm3"] == round((1404 - 863) / 30, 2)


def test_spoilers_hide_unknown_endpoints():
    offers = _offers([
        ("sell_npc", "sell", "advancedelectronics", 50.0, 863.0),
        ("site", "buy", "advancedelectronics", 20.0, 1404.0),   # knownto ""
    ])
    assert len(build_opportunities(_frames(offers), _ref(), _cfg())) == 1
    assert build_opportunities(_frames(offers), _ref(),
                               _cfg(spoilers_hide=True)) == []


def test_player_trade_ships_loadout_speed():
    engines = pd.DataFrame({
        "id": ["ship1", "ship1"],
        "macro": ["engine_arg_m_travel_01_mk1_macro",
                  "engine_unknown_macro"],
        "n": [2, 1],
    })
    (s,) = player_trade_ships(
        _frames(_offers([]), ship_engines=engines), _ref())
    # 2 engines x 1000 thrust x 10 travel mult / 50 drag; the unknown
    # engine contributes nothing
    assert s["l"] == "Hauler One (HHH-001)"
    assert (s["model"], s["cls"], s["cargo"]) == ("Boa", "M", 4900.0)
    assert s["speed"] == 400


def test_player_ship_without_engine_data_has_no_speed():
    (s,) = player_trade_ships(_frames(_offers([])), _ref())
    assert s["speed"] is None
