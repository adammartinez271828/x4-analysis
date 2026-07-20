"""Trade-opportunity pairing (analysis/opportunities.py) on synthetic
offers: spread metrics, player-endpoint pricing, exclusions, jumps."""

from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.opportunities import build_opportunities, ship_presets


def _ref(**over):
    base = dict(
        wares=pd.DataFrame({
            "id": ["silicon", "advancedelectronics"],
            "name": ["Silicon Wafers", "Advanced Electronics"],
            "volume": [18, 30],
        }),
        gates=pd.DataFrame({
            "sector_a": ["sec_a", "sec_b"],
            "sector_b": ["sec_b", "sec_c"],
        }),
        sectors=pd.DataFrame({
            "cluster": ["cl_a", "cl_b", "cl_c"],
            "macro": ["sec_a", "sec_b", "sec_c"],
        }),
        ships=pd.DataFrame({
            "model": ["Vulture", "Vulture", "Boa"],
            "class": ["L", "L", "M"],
            "cargo": [12000.0, 11000.0, 4900.0],
            "cargo_tags": ["container", "container", "container"],
        }),
        faction_short={"argon": "ARG", "teladi": "TEL"},
        ware_name={"silicon": "Silicon Wafers",
                   "advancedelectronics": "Advanced Electronics"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _frames(offers, universe=None):
    if universe is None:
        universe = pd.DataFrame({
            "id": ["sell_npc", "buy_npc", "sell_pla", "buy_pla",
                   "sell_xen", "site"],
            "class": ["station"] * 5 + ["buildstorage"],
            "owner": ["argon", "teladi", "player", "player",
                      "xenon", "teladi"],
            "name": ["Foundry", "Fab", "My Mine", "My Fab", "X", ""],
            "code": ["AAA-111", "BBB-222", "PPP-111", "PPP-222",
                     "XXX-666", "CCC-333"],
            "knownto": ["player", "player", "player", "player",
                        "player", ""],
            "stype": [""] * 6,
            "sector.macro": ["sec_a", "sec_c", "sec_a", "sec_c",
                             "sec_b", "sec_b"],
        })
    sectors = pd.DataFrame({
        "macro": ["sec_a", "sec_b", "sec_c"],
        "name": ["Alpha", "Beta", "Gamma"],
    })
    return SimpleNamespace(trade_offers=offers, universe=universe,
                           sectors=sectors)


def _cfg(**over):
    base = dict(spoilers_hide=False)
    base.update(over)
    return SimpleNamespace(**base)


def _offers(rows):
    return pd.DataFrame(rows, columns=["id", "side", "ware", "amount",
                                       "price"])


def test_npc_pair_metrics():
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
    assert r["s"]["l"] == "Foundry (AAA-111)" and r["s"]["sec"] == "Alpha"
    assert r["b"]["f"] == "TEL"


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


def test_exclusions_and_construction_buyer():
    rows = build_opportunities(_frames(_offers([
        ("sell_xen", "sell", "silicon", 500.0, 1.0),     # xenon: out
        ("sell_npc", "sell", "silicon", 500.0, 0.0),     # junk 0-price: out
        ("site", "sell", "silicon", 500.0, 100.0),       # sites never sell
        ("sell_npc", "sell", "advancedelectronics", 50.0, 863.0),
        ("site", "buy", "advancedelectronics", 20.0, 1404.0),
    ])), _ref(), _cfg())
    (r,) = rows
    assert r["w"] == "advancedelectronics"
    assert r["b"].get("c") == 1              # construction-site buyer
    assert r["pm3"] == round((1404 - 863) / 30, 2)


def test_spoilers_hide_unknown_endpoints():
    offers = _offers([
        ("sell_npc", "sell", "advancedelectronics", 50.0, 863.0),
        ("site", "buy", "advancedelectronics", 20.0, 1404.0),   # knownto ""
    ])
    assert len(build_opportunities(_frames(offers), _ref(), _cfg())) == 1
    assert build_opportunities(_frames(offers), _ref(),
                               _cfg(spoilers_hide=True)) == []


def test_ship_presets_dedupe_largest_variant():
    ps = ship_presets(_ref())
    assert {p["m"]: p["cargo"] for p in ps} == \
        {"Vulture": 12000.0, "Boa": 4900.0}
