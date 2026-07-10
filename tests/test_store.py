import time
from pathlib import Path

import pytest

from x4analyzer import store
from x4analyzer.config import Config
from x4analyzer.refdata import load_refdata
from x4analyzer.saveparser import parse_savegame

from test_saveparser import FIXTURE


@pytest.fixture(scope="module")
def ref():
    # nonexistent user dir -> falls back to the packaged reference CSVs
    return load_refdata(Path("/nonexistent"))


@pytest.fixture
def save_data(tmp_path):
    p = tmp_path / "save.xml"
    p.write_text(FIXTURE)
    return parse_savegame(p)


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path
    return c


@pytest.fixture
def conn(cfg, save_data, ref):
    conn = store.open_db(cfg, save_data.guid)
    store.write_reference(conn, ref)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    yield conn
    conn.close()


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# fixture save -> exact row counts per table
EXPECTED_COUNTS = {
    "save": 1,
    "component": 4,       # cluster, sector, station, ship_s
    "fleet_edge": 1,
    "module": 2,
    "module_upgrade": 0,
    "workforce": 1,
    "npc": 1,
    "npc_skill": 3,
    "post": 2,
    "people": 2,
    "cargo": 0,
    "trade_offer": 1,
    "build_resource": 1,
    "ship_order": 1,
    "resource": 2,
    "floating_ware": 1,
}


def test_snapshot_row_counts(conn):
    for table, expected in EXPECTED_COUNTS.items():
        assert count(conn, table) == expected, table


def test_save_row(conn):
    row = conn.execute(
        "SELECT guid, game_version, game_time, modified, player_name,"
        " player_money_cr, faction_name FROM save").fetchone()
    assert row == ("ABCD-1234", "900", 5000.5, 1, "Test Pilot",
                   1234.56, "Testers")


def test_component_values(conn):
    ship = conn.execute(
        "SELECT parent_id, macro, owner, name, cluster_id, sector_macro"
        " FROM component WHERE class = 'ship_s'").fetchone()
    # containment, lowercased macro, ""->NULL name
    assert ship == ("[0x20]", "ship_test_macro", "player", None,
                    "[0x10]", "cluster_01_sector001_macro")
    station = conn.execute(
        "SELECT parent_id, code, contested FROM component"
        " WHERE class = 'station'").fetchone()
    assert station == ("[0x11]", "STA-001", None)
    sector = conn.execute(
        "SELECT contested, knownto FROM component"
        " WHERE class = 'sector'").fetchone()
    assert sector == (1, "player")


def test_fleet_edge_resolved(conn):
    assert conn.execute("SELECT follower_id, commander_id FROM fleet_edge"
                        ).fetchall() == [("[0x30]", "[0x20]")]


def test_world_details(conn):
    assert conn.execute(
        "SELECT host_id, entry_id, idx, macro, built FROM module"
        " ORDER BY idx").fetchall() == [
        ("[0x20]", "[0x50]", 1, "mod_a_macro", 0),
        ("[0x20]", "[0x51]", 3, "mod_b_macro", 0),
    ]
    assert conn.execute(
        "SELECT object_id, side, ware, amount, price_cr FROM trade_offer"
        ).fetchall() == [("[0x20]", "buy", "energycells", 500.0, 1.0)]
    assert conn.execute(
        "SELECT object_id, order_name, is_default, state FROM ship_order"
        ).fetchall() == [("[0x30]", "Wait", 1, "started")]
    assert conn.execute(
        "SELECT npc_id, value FROM npc_skill JOIN npc ON npc.id = npc_id"
        " WHERE skill = 'piloting'").fetchall() == [("[0x99]", 9.0)]
    assert sorted(conn.execute(
        "SELECT role, count FROM people").fetchall()) == [
        ("passenger", 1), ("service", 2)]


def test_reimport_replaces_snapshot(conn, save_data, ref):
    store.write_snapshot(conn, save_data, ref, "save.xml")
    assert count(conn, "save") == 2
    for table, expected in EXPECTED_COUNTS.items():
        if table == "save":
            continue
        assert count(conn, table) == expected, table
    # the remaining world rows belong to the latest snapshot
    assert conn.execute(
        "SELECT DISTINCT save_id FROM component").fetchall() == [(2,)]


def test_reference_loaded(conn):
    for table in ("ware", "recipe", "ship_ref", "faction", "sector_ref",
                  "cluster_ref", "gate", "modcap", "module_ref", "text"):
        assert count(conn, table) > 0, table
    # replaced wholesale, never accreted
    n = count(conn, "ware")
    ref2 = load_refdata(Path("/nonexistent"))
    store.write_reference(conn, ref2)
    assert count(conn, "ware") == n


def test_schema_version_reset_keeps_event_tables(cfg, save_data, ref):
    conn = store.open_db(cfg, save_data.guid)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    conn.execute("INSERT INTO log_entry (time, category, title) "
                 "VALUES (1.0, '', 'kept')")
    conn.commit()
    conn.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    conn = store.open_db(cfg, save_data.guid)
    assert count(conn, "component") == 0          # rebuildable: dropped
    assert count(conn, "log_entry") == 1          # event history: kept
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone()[0] != "0"
    conn.close()


def test_bulk_insert_speed(cfg, save_data, ref):
    t0 = time.perf_counter()
    conn = store.open_db(cfg, save_data.guid)
    store.write_reference(conn, ref)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    conn.close()
    assert time.perf_counter() - t0 < 2.0
