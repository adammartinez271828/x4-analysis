"""Earnings tables: the external / external+internal variant split."""

from __future__ import annotations

import pandas as pd

from x4analyzer.viz.tables import (
    _commodity_keys,
    _seller_keys,
    earnings_variants,
    internal_sales,
    save_table_variants,
)


def _sales() -> pd.DataFrame:
    """External sales (what frames.sales carries), already windowed."""
    return pd.DataFrame({
        "time": [100.0, 200.0],
        "money": [1000, 500],
        "seller.name": ["Ore Mk1", "Trade Hub"],
        "seller.code": ["AAA-111", "BBB-222"],
        "amount": [10, 5],
        "commodity": ["Silicon", "Energy Cells"],
        "buyer.faction": ["ARG", "ARG"],
        "buyer.name": ["Argon Wharf", "Argon Wharf"],
        "buyer.code": ["CCC-333", "CCC-333"],
    })


def _tradelog() -> pd.DataFrame:
    """Full tradelog: the external rows plus player->player rows, one of
    them from a seller that never trades externally."""
    rows = [
        # external (PLA -> ARG): must not leak into the internal set
        (100.0, 1000, 10, "Silicon", "Ore Mk1", "AAA-111", "PLA", "ARG"),
        # internal: same seller as an external row
        (150.0, 300, 3, "Silicon", "Ore Mk1", "AAA-111", "PLA", "PLA"),
        # internal: seller seen ONLY internally
        (160.0, 700, 7, "Silicon", "Miner Two", "DDD-444", "PLA", "PLA"),
        # internal but priced at 0 -> dropped by the money > 0 filter
        (170.0, 0, 4, "Silicon", "Miner Two", "DDD-444", "PLA", "PLA"),
        # internal but outside the window
        (10.0, 900, 9, "Silicon", "Miner Two", "DDD-444", "PLA", "PLA"),
        # external buy (ARG -> PLA)
        (180.0, 200, 2, "Ore", "Argon Miner", "EEE-555", "ARG", "PLA"),
    ]
    cols = ["time", "money", "amount", "commodity", "seller.name",
            "seller.code", "seller.faction", "buyer.faction"]
    return pd.DataFrame(rows, columns=cols)


def test_internal_sales_filters_side_window_and_price():
    got = internal_sales(_tradelog(), time_limit=50.0)
    assert list(got["money"]) == [300, 700]
    assert list(got["seller.code"]) == ["AAA-111", "DDD-444"]


def test_internal_sales_defensive():
    assert internal_sales(pd.DataFrame(), 0.0).empty
    assert internal_sales(None, 0.0).empty
    # a tradelog without the faction columns must not crash
    assert internal_sales(pd.DataFrame({"time": [1.0]}), 0.0).empty


def test_seller_variants_external_matches_today_and_combined_adds_rows():
    sales, internal = _sales(), internal_sales(_tradelog(), 50.0)
    ext, comb = earnings_variants(sales, internal, _seller_keys, 1.0)

    assert set(ext["Seller"]) == {"Ore Mk1 (AAA-111)", "Trade Hub (BBB-222)"}
    assert ext.loc[ext["Seller"] == "Ore Mk1 (AAA-111)", "Earnings"].iat[0] == 1000

    # the internal-only seller appears ONLY in the combined variant
    assert "Miner Two (DDD-444)" not in set(ext["Seller"])
    assert "Miner Two (DDD-444)" in set(comb["Seller"])
    assert comb.loc[comb["Seller"] == "Miner Two (DDD-444)",
                    "Earnings"].iat[0] == 700
    # and the shared seller gains its internal earnings
    assert comb.loc[comb["Seller"] == "Ore Mk1 (AAA-111)",
                    "Earnings"].iat[0] == 1300
    assert comb.loc[comb["Seller"] == "Ore Mk1 (AAA-111)", "Trades"].iat[0] == 2
    # untouched seller is identical in both variants
    assert comb.loc[comb["Seller"] == "Trade Hub (BBB-222)",
                    "Earnings"].iat[0] == 500


def test_commodity_variants():
    sales, internal = _sales(), internal_sales(_tradelog(), 50.0)
    ext, comb = earnings_variants(sales, internal, _commodity_keys, 2.0)
    assert ext.loc[ext["Commodity"] == "Silicon", "Earnings"].iat[0] == 1000
    assert comb.loc[comb["Commodity"] == "Silicon", "Earnings"].iat[0] == 2000
    assert comb.loc[comb["Commodity"] == "Silicon", "Items"].iat[0] == 20
    # Cr/Hour uses the window, not the row count
    assert comb.loc[comb["Commodity"] == "Silicon", "Cr/Hour"].iat[0] == 1000


def test_empty_internal_gives_identical_variants():
    sales = _sales()
    ext, comb = earnings_variants(sales, pd.DataFrame(), _seller_keys, 1.0)
    pd.testing.assert_frame_equal(ext, comb)


def test_save_table_variants_renders_both_tables(tmp_path):
    sales, internal = _sales(), internal_sales(_tradelog(), 50.0)
    ext, comb = earnings_variants(sales, internal, _seller_keys, 1.0)
    rel = save_table_variants(ext, comb, tmp_path, "Gross Earnings per Seller",
                              "GUID")
    html = (tmp_path / rel.split("/")[-1]).read_text(encoding="utf-8")
    assert 'id="tbl"' in html and 'id="tbl_all"' in html
    assert "x4internal" in html and "include internal trades" in html
    assert "Miner Two" in html            # only in the combined table
    assert html.count("Miner Two") == 1
    assert "x4h" in html                  # iframe height postMessage
