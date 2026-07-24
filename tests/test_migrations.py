"""Migration-machinery regression tests (T0/H0).

Two properties the drop-and-recreate scheme must now guarantee:

- `save` and `meta` are P-class (persistent bookkeeping): a
  SCHEMA_VERSION bump drops W/R/D tables but must preserve both — `save`
  ids are the time dimension cross-run data keys into (recycling them
  silently corrupts anything that outlives a bump), and `meta` carries
  flags the bump path itself reads.
- The version chain is complete: a DB parked at an OFF-chain version
  (the real case: a v5 database, whose bump versions 4-9 touched only
  W/R/D tables) must still walk to the current version, applying any
  E-migrations it passes on the way, without losing event history.
"""
import sqlite3

from x4analyzer.config import Config
from x4analyzer.db import schema, store


def make_cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path
    return c


def test_version_chain_is_complete():
    # every version from 1 up to (but excluding) the current one steps
    # forward, and every EVENT_MIGRATIONS key is on the chain
    version = "1"
    seen = [version]
    while version in schema.NEXT_VERSION:
        version = schema.NEXT_VERSION[version]
        seen.append(version)
    assert version == schema.SCHEMA_VERSION
    assert set(schema.EVENT_MIGRATIONS) <= set(seen)


def test_schema_bump_preserves_save_and_meta(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = store.open_db(cfg, "BUMP")
    conn.execute(
        "INSERT INTO save (guid, game_time, save_date, source_file)"
        " VALUES ('BUMP', 100.0, '1700000000', 'save.xml')")
    conn.execute("INSERT INTO meta VALUES ('csv_caches_imported', '1')")
    conn.execute("INSERT INTO component VALUES "
                 "(1, '[0x1]', 'sector', NULL, NULL, NULL, NULL, NULL,"
                 " NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,"
                 " NULL, NULL)")
    conn.commit()
    # simulate a future bump: stamp an unknown old version
    conn.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    conn = store.open_db(cfg, "BUMP")
    # W tables dropped, P tables preserved with their rows and ids
    assert conn.execute("SELECT COUNT(*) FROM component").fetchone() == (0,)
    assert conn.execute("SELECT save_id, guid, game_time FROM save"
                        ).fetchall() == [(1, "BUMP", 100.0)]
    assert conn.execute("SELECT value FROM meta"
                        " WHERE key = 'csv_caches_imported'"
                        ).fetchone() == ("1",)
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone() == (schema.SCHEMA_VERSION,)
    conn.close()


def test_off_chain_v5_database_migrates(tmp_path):
    """The real 559 h playthrough's DB sits at v5: versions 4-9 changed
    only W/R/D tables, so v5 has no EVENT_MIGRATIONS entry — the old walk
    (`while version in EVENT_MIGRATIONS`) skipped it entirely and left
    the version stamp stale forever."""
    cfg = make_cfg(tmp_path)
    conn = sqlite3.connect(store.db_path(cfg, "V5"))
    # v5-era P + E tables are already at the current shape (E migrations
    # end at v3->v4); W tables had fewer columns — component stands in
    conn.execute(schema.TABLES["meta"])
    conn.execute(schema.TABLES["save"])
    conn.execute(schema.TABLES["trade_tx"])
    conn.execute(schema.TABLES["stock_event"])
    conn.execute("CREATE TABLE component (save_id INTEGER, id TEXT)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', '5')")
    conn.execute("INSERT INTO save (guid, game_time, source_file)"
                 " VALUES ('V5', 2000000.0, 'save_006.xml.gz')")
    conn.execute("INSERT INTO trade_tx (time, ware) VALUES (5.0, 'ice')")
    conn.execute("INSERT INTO stock_event (time, owner_id, ware, level)"
                 " VALUES (6.0, '[0x1]', 'ice', 10.0)")
    conn.commit()
    conn.close()

    conn = store.open_db(cfg, "V5")
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone() == (schema.SCHEMA_VERSION,)
    # event history and provenance survived the walk
    assert conn.execute("SELECT time, ware FROM trade_tx").fetchall() \
        == [(5.0, "ice")]
    assert conn.execute("SELECT time, level FROM stock_event").fetchall() \
        == [(6.0, 10.0)]
    assert conn.execute("SELECT save_id, guid FROM save").fetchall() \
        == [(1, "V5")]
    # the old-shape W table was dropped and recreated at the current shape
    cols = [r[1] for r in conn.execute("PRAGMA table_info(component)")]
    assert "sector_macro" in cols
    conn.close()


def test_v1_database_walks_full_chain(tmp_path):
    """A v1 DB crosses every E-migration AND the empty 4..current tail."""
    cfg = make_cfg(tmp_path)
    conn = sqlite3.connect(store.db_path(cfg, "V1"))
    conn.execute(schema.TABLES["meta"])
    conn.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    conn.execute("CREATE TABLE stock_event (time REAL NOT NULL,"
                 " owner_id TEXT NOT NULL, ware TEXT NOT NULL, level REAL,"
                 " raw_attrs TEXT)")
    conn.execute("CREATE TABLE trade_tx (time REAL NOT NULL,"
                 " ware TEXT NOT NULL, buyer_id TEXT, seller_id TEXT,"
                 " price_cr REAL, amount REAL, raw_attrs TEXT)")
    conn.execute("INSERT INTO stock_event VALUES (5.0, '[0x1]', 'ice',"
                 " 10.0, '{}')")
    conn.commit()
    conn.close()

    conn = store.open_db(cfg, "V1")
    assert conn.execute("SELECT time, owner_id, owner_faction, owner_entity,"
                        " epoch FROM stock_event").fetchall() \
        == [(5.0, "[0x1]", None, None, 0)]
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone() == (schema.SCHEMA_VERSION,)
    conn.close()
