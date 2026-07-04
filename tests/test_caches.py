import pandas as pd
import pytest

from x4analyzer.caches import merge_log_cache, merge_tradelog_cache
from x4analyzer.config import Config

GUID = "TEST-GUID"


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path
    c.cache_compress = True
    return c


def log_frame(rows):
    df = pd.DataFrame(rows, columns=["time", "category", "title", "text",
                                     "money", "component"])
    df["category"] = df["category"].fillna("")
    return df


def test_log_cache_replaces_per_category_window(cfg):
    run1 = log_frame([
        (10.0, "", "old news", "t", None, None),
        (20.0, "upkeep", "old upkeep", "t", None, None),
    ])
    merged1 = merge_log_cache(cfg, GUID, run1)
    assert len(merged1) == 2

    # second run: the game dropped the old "" entry and has new ones;
    # upkeep window now starts at 15 -> cached upkeep >= 15 is replaced
    run2 = log_frame([
        (30.0, "", "new news", "t", None, None),
        (15.0, "upkeep", "reissued upkeep", "t", None, None),
    ])
    merged2 = merge_log_cache(cfg, GUID, run2)
    titles = set(merged2["title"])
    assert titles == {"old news", "new news", "reissued upkeep"}
    # "old upkeep" (t=20 >= new upkeep mintime 15) was replaced


def test_log_cache_idempotent(cfg):
    run = log_frame([(10.0, "", "a", "t", None, None),
                     (11.0, "upkeep", "b", "t", None, None)])
    merge_log_cache(cfg, GUID, run)
    merged = merge_log_cache(cfg, GUID, run.copy())
    assert len(merged) == 2


def trade_frame(times):
    rows = []
    for t in times:
        rows.append({
            "time": t, "commodity": "Energy Cells", "price": 15.0,
            "amount": 100, "money": 1500,
            "seller.faction": "PLA", "seller.id": "[0x1]",
            "seller.name": "S", "seller.code": "AAA-111",
            "seller.proxy.id": None, "seller.proxy.name": None,
            "seller.proxy.code": None,
            "buyer.faction": "ARG", "buyer.id": "[0x2]",
            "buyer.name": "B", "buyer.code": "BBB-222",
            "buyer.proxy.id": None, "buyer.proxy.name": None,
            "buyer.proxy.code": None,
        })
    return pd.DataFrame(rows)


def test_tradelog_cache_keeps_history_and_dedupes(cfg):
    merge_tradelog_cache(cfg, GUID, trade_frame([100.0, 200.0]))
    # next run: game dropped the t=100 entry, window now starts at 200
    merged = merge_tradelog_cache(cfg, GUID, trade_frame([200.0, 300.0]))
    assert sorted(merged["time"]) == [100.0, 200.0, 300.0]
    assert merged.duplicated().sum() == 0


def test_tradelog_cache_idempotent(cfg):
    df = trade_frame([100.0, 200.0])
    merge_tradelog_cache(cfg, GUID, df)
    merged = merge_tradelog_cache(cfg, GUID, df.copy())
    assert len(merged) == 2
