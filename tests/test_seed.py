"""Archive seeding of the trend layer (analyze.run_seed): chronological
import, A-row backfill for historic saves, and the guard interactions —
read-only entity resolution, the stale-save merge guard, and the
world-state invariant (W tables end at the newest save)."""

from x4analyzer.analyze import run_seed
from x4analyzer.config import Config
from x4analyzer.db import store
from x4analyzer.save.parser import peek_save_info

from test_saveparser import FIXTURE

GUID = "ABCD-1234"


def write_save(tmp_path, name, time, date):
    p = tmp_path / name
    p.write_text(FIXTURE.replace('time="5000.5"', f'time="{time}"')
                 .replace('date="1700000000"', f'date="{date}"'))
    return p


def make_cfg(tmp_path):
    cfg = Config()
    cfg.data_dir = tmp_path            # DB here; CSVs fall back to packaged
    return cfg


def counts(conn):
    return {t: conn.execute(
        f"SELECT COUNT(DISTINCT save_id) FROM {t}").fetchone()[0]
        for t in ("sector_presence", "station_metric", "market_stat")}


def test_peek_save_info(tmp_path):
    p = write_save(tmp_path, "old.xml", "4000.0", "1699990000")
    assert peek_save_info(p) == (GUID, 4000.0, "1699990000")


def test_seed_imports_chronologically(tmp_path):
    cfg = make_cfg(tmp_path)
    old = write_save(tmp_path, "old.xml", "4000.0", "1699990000")
    new = write_save(tmp_path, "new.xml", "5000.5", "1700000000")
    assert run_seed(cfg, [new, old]) == 0      # input order is irrelevant

    conn = store.open_db(cfg, GUID)
    assert conn.execute("SELECT COUNT(*) FROM v_snapshot").fetchone()[0] == 2
    assert counts(conn) == {"sector_presence": 2, "station_metric": 2,
                            "market_stat": 2}
    # the W tables ended at the NEWEST save
    (w_sid,) = conn.execute(
        "SELECT DISTINCT save_id FROM component").fetchone()
    assert conn.execute("SELECT game_time FROM save WHERE save_id = ?",
                        (w_sid,)).fetchone() == (5000.5,)
    conn.close()


def test_seed_backfills_older_save_without_touching_state(tmp_path):
    cfg = make_cfg(tmp_path)
    old = write_save(tmp_path, "old.xml", "4000.0", "1699990000")
    new = write_save(tmp_path, "new.xml", "5000.5", "1700000000")
    # the real DBs' starting state: head imported, trend layer empty for
    # everything older
    assert run_seed(cfg, [new]) == 0
    conn = store.open_db(cfg, GUID)
    e_before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("trade_tx", "stock_event", "money_event",
                          "log_entry", "entity", "entity_event")}
    conn.close()

    assert run_seed(cfg, [old, new]) == 0
    conn = store.open_db(cfg, GUID)
    # the historic snapshot got its A rows — station_metric included,
    # via the registry's read-only resolution
    assert counts(conn) == {"sector_presence": 2, "station_metric": 2,
                            "market_stat": 2}
    # E history untouched: the merge guard skipped the older window and
    # the registry minted/edited nothing
    for t, n in e_before.items():
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] \
            == n, t
    # world state still the head's
    (w_sid,) = conn.execute(
        "SELECT DISTINCT save_id FROM component").fetchone()
    assert conn.execute("SELECT game_time FROM save WHERE save_id = ?",
                        (w_sid,)).fetchone() == (5000.5,)
    # rerunning the whole seed is a no-op
    before = conn.execute("SELECT COUNT(*) FROM sector_presence"
                          ).fetchone()[0]
    conn.close()
    assert run_seed(cfg, [old, new]) == 0
    conn = store.open_db(cfg, GUID)
    assert conn.execute("SELECT COUNT(*) FROM sector_presence"
                        ).fetchone()[0] == before
    conn.close()


def test_seed_refuses_batch_that_would_regress_world_state(tmp_path):
    cfg = make_cfg(tmp_path)
    old = write_save(tmp_path, "old.xml", "4000.0", "1699990000")
    new = write_save(tmp_path, "new.xml", "5000.5", "1700000000")
    assert run_seed(cfg, [new]) == 0
    assert run_seed(cfg, [old]) == 1           # head file not in the batch
    conn = store.open_db(cfg, GUID)
    assert counts(conn)["sector_presence"] == 1   # nothing was imported
    conn.close()
