import time
from pathlib import Path

import pytest

from x4analyzer.db import store
from x4analyzer.config import Config
from x4analyzer.gamedata.refdata import load_refdata
from x4analyzer.save.parser import parse_savegame

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
    store.merge_events(conn, save_data, ref)
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
    "floating_ware": 2,   # scrap cube + the Erlking vault's loot wares
    "datavault": 2,
    "ship_engine": 1,     # 2 identical engines aggregate to one n=2 row
    # event history (merged, not rebuilt)
    "trade_tx": 1,
    "stock_event": 1,
    "log_entry": 1,
    "removed_object": 1,
}


def test_snapshot_row_counts(conn):
    for table, expected in EXPECTED_COUNTS.items():
        assert count(conn, table) == expected, table


def test_ship_engine_rows(conn):
    rows = conn.execute(
        "SELECT object_id, macro, n FROM ship_engine").fetchall()
    assert rows == [("[0x30]", "engine_arg_s_travel_01_mk3_macro", 2)]


def test_resource_rows_carry_replenish_classes(conn):
    rows = conn.execute(
        "SELECT ware, yield, level, speed FROM resource ORDER BY ware"
    ).fetchall()
    # the fixture's silicon area has no gatherspeed token -> NULL
    assert rows == [("ore", 1000.0, "high", "slow"),
                    ("silicon", 200.0, "low", None)]


def test_datavault_rows(conn):
    rows = conn.execute(
        "SELECT object_id, macro, code, knownto, sector_macro, sx, sz,"
        " unlocked, loot, blueprints FROM datavault ORDER BY object_id"
    ).fetchall()
    assert rows == [
        ("[0x70]", "landmarks_vault_02_macro", "KBE-495", "player",
         "cluster_01_sector001_macro", 900.0, -1700.0, 1, 0, None),
        ("[0x80]", "landmarks_erlking_vault_04_macro", "WYH-699", None,
         "cluster_01_sector001_macro", 5000.0, -2500.0, 0, 2,
         "turret_pir_l_battleship_01_laser_01_mk1"),
    ]


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


# ---- event-history merges (phase 2) ----------------------------------------

def events_save(log=(), trades=(), removed=(), components=(),
                links=(), conns=()):
    from x4analyzer.save.parser import SaveData
    s = SaveData()
    s.log_entries = list(log)
    s.trades = list(trades)
    s.removed_objects = list(removed)
    s.components = list(components)
    s.commander_links = list(links)
    s.subordinate_conns = list(conns)
    return s


def comp(cid, code, owner, name="", clazz="station", spawn=""):
    """Minimal 16-field component tuple (id/name/code/owner populated)."""
    return (cid, clazz, "macro", name, code, owner,
            "", "", "conn", spawn, "", "", "", "", "", "")


def dump(conn, table):
    return sorted(map(repr, conn.execute(f"SELECT * FROM {table}")))


def test_event_values(conn):
    assert conn.execute(
        "SELECT time, ware, buyer_id, seller_id, price_cr, amount"
        " FROM trade_tx").fetchall() == [
        (10.5, "energycells", "[0x20]", "[0x77]", 16.0, 100.0)]
    assert conn.execute(
        "SELECT time, owner_id, ware, level FROM stock_event").fetchall() \
        == [(11.0, "[0x20]", "ice", 50.0)]
    # save-stable identity, resolved at merge time against this save's
    # universe; unknown parties ([0x77]) stay NULL
    assert conn.execute(
        "SELECT owner_faction, owner_code, epoch FROM stock_event"
        ).fetchall() == [("player", "STA-001", 0)]
    assert conn.execute(
        "SELECT buyer_code, seller_faction, seller_code FROM trade_tx"
        ).fetchall() == [("STA-001", None, None)]
    assert conn.execute(
        "SELECT time, category, title FROM log_entry").fetchall() == [
        (100.0, "upkeep", "Test entry")]
    assert conn.execute(
        "SELECT id, name, owner FROM removed_object").fetchall() == [
        ("115", "TEL Trader", "teladi")]


def test_merge_idempotent(conn, save_data, ref):
    before = {t: dump(conn, t) for t in
              ("trade_tx", "stock_event", "log_entry", "removed_object")}
    store.merge_events(conn, save_data, ref)
    for table, rows in before.items():
        assert dump(conn, table) == rows, table


def test_log_merge_replaces_per_category_window(conn):
    def entry(time, category, title):
        e = {"time": time, "title": title, "text": "t"}
        if category:
            e["category"] = category
        return e

    store.merge_events(conn, events_save(log=[
        entry("10.0", "", "old news"), entry("20.0", "upkeep", "old upkeep"),
    ]))
    # second run: the game dropped the old "" entry and has new ones;
    # upkeep window now starts at 15 -> cached upkeep >= 15 is replaced
    store.merge_events(conn, events_save(log=[
        entry("30.0", "", "new news"),
        entry("15.0", "upkeep", "reissued upkeep"),
    ]))
    titles = {r[0] for r in conn.execute(
        "SELECT title FROM log_entry WHERE time < 100")}
    assert titles == {"old news", "new news", "reissued upkeep"}


def trade_attrs(time, buyer="[0x2]", seller="[0x1]"):
    return {"time": time, "ware": "energycells", "buyer": buyer,
            "seller": seller, "price": "1500", "v": "100"}


def stock_attrs(time, level, owner="[0x9]"):
    return {"time": time, "ware": "energycells", "owner": owner, "v": level}


def test_trade_merge_keeps_history_and_dedupes_drifted_ids(conn):
    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    store.merge_events(conn, events_save(
        trades=[trade_attrs("100.0"), trade_attrs("200.0")]))
    # next run, same playthrough: runtime component ids were reassigned,
    # and the game dropped nothing yet — the t=100/200 trades recur with
    # new ids and must not accrete as duplicates
    store.merge_events(conn, events_save(trades=[
        trade_attrs("100.0", "[0x888]", "[0x999]"),
        trade_attrs("200.0", "[0x888]", "[0x999]"),
        trade_attrs("300.0", "[0x888]", "[0x999]"),
    ]))
    assert [r[0] for r in conn.execute(
        "SELECT time FROM trade_tx ORDER BY time")] == [100.0, 200.0, 300.0]
    # and the surviving copies are the fresh ones (current save's ids)
    assert {r[0] for r in conn.execute("SELECT buyer_id FROM trade_tx")} \
        == {"[0x888]"}


def test_stock_merge_window_cutoff(conn):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    store.merge_events(conn, events_save(
        trades=[stock_attrs("100.0", "10"), stock_attrs("200.0", "30")]))
    # the fresh window is authoritative from its oldest entry on: the old
    # t=200 level was superseded
    store.merge_events(conn, events_save(
        trades=[stock_attrs("200.0", "35"), stock_attrs("300.0", "60")]))
    assert conn.execute(
        "SELECT time, level FROM stock_event ORDER BY time").fetchall() \
        == [(100.0, 10.0), (200.0, 35.0), (300.0, 60.0)]


def test_merge_skips_entries_without_time(conn):
    # a missing/unparseable time must not collapse the window cutoff to 0
    # and wipe the preserved history (the tables' whole reason to exist)
    store.merge_events(conn, events_save(
        log=[{"title": "no time", "text": "t"}],
        trades=[{"ware": "ice", "owner": "[0x9]", "v": "5"},
                {"ware": "ice", "owner": "[0x9]", "v": "5", "time": "bogus"}],
    ))
    # fixture history untouched, timeless entries not inserted
    assert count(conn, "log_entry") == 1
    assert count(conn, "stock_event") == 1


def test_malformed_price_does_not_crash(conn):
    store.merge_events(conn, events_save(trades=[
        {"time": "12.0", "ware": "ice", "buyer": "[0x1]", "seller": "[0x2]",
         "price": "not-a-number", "v": "10"}]))
    assert conn.execute(
        "SELECT price_cr FROM trade_tx WHERE time = 12.0").fetchall() \
        == [(None,)]


def test_duplicate_ids_never_fail(cfg, save_data, ref):
    # modded saves repeat ids; the run must load, never crash on the PKs
    save_data.components.append(save_data.components[-1])
    save_data.npcs.append(save_data.npcs[0])
    conn = store.open_db(cfg, save_data.guid)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    assert count(conn, "component") == 4
    assert count(conn, "npc") == 1
    conn.close()


def test_window_boundary_keeps_dropped_siblings(conn):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    store.merge_events(conn, events_save(trades=[
        stock_attrs("100.0", "10", "[0xA]"),
        stock_attrs("100.0", "20", "[0xB]"),
        stock_attrs("200.0", "30", "[0xA]"),
    ]))
    # the game dropped [0xB]'s t=100 snapshot: the new window is thinner at
    # the boundary, so the cached siblings there must survive the merge
    store.merge_events(conn, events_save(trades=[
        stock_attrs("100.0", "10", "[0xA]"),
        stock_attrs("200.0", "30", "[0xA]"),
    ]))
    assert count(conn, "stock_event") == 3
    assert conn.execute("SELECT COUNT(*) FROM stock_event WHERE time = 100.0"
                        ).fetchone()[0] == 2


def test_epoch_increments_on_coverage_gap(conn):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    store.merge_events(conn, events_save(
        trades=[stock_attrs("100.0", "10"), stock_attrs("200.0", "30")]))
    # next analyzed save's window starts after everything stored: the game
    # discarded the events in between, deltas must not span the gap
    store.merge_events(conn, events_save(
        trades=[stock_attrs("500.0", "90"), stock_attrs("600.0", "95")]))
    assert conn.execute("SELECT time, epoch FROM stock_event ORDER BY time"
                        ).fetchall() == [
        (100.0, 0), (200.0, 0), (500.0, 1), (600.0, 1)]
    assert conn.execute(
        "SELECT dv FROM v_stock_delta WHERE time = 500.0").fetchall() \
        == [(None,)]  # not 90 - 30: the gap is not a delivery


def test_identity_heals_series_across_sessions(conn):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    # session 1: the station is [0xA]
    store.merge_events(conn, events_save(
        trades=[stock_attrs("100.0", "10", "[0xA]"),
                stock_attrs("120.0", "20", "[0xA]")],
        components=[comp("[0xA]", "STA-001", "argon")]))
    # session 2 (game reload): same station, remapped to [0xB]; the new
    # window overlaps at t=120 so coverage is continuous
    store.merge_events(conn, events_save(
        trades=[stock_attrs("120.0", "20", "[0xB]"),
                stock_attrs("150.0", "40", "[0xB]")],
        components=[comp("[0xB]", "STA-001", "argon")]))
    # the faction|code partition bridges the id change: the t=120 row's
    # delta is computed against the [0xA] row at t=100
    assert conn.execute(
        "SELECT time, dv FROM v_stock_delta ORDER BY time").fetchall() \
        == [(100.0, None), (120.0, 10.0), (150.0, 20.0)]


def test_v1_database_migrates_keeping_history(cfg):
    import sqlite3

    conn = sqlite3.connect(store.db_path(cfg, "MIG"))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
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

    conn = store.open_db(cfg, "MIG")
    # event history survived with the new columns defaulted; version bumped
    assert conn.execute("SELECT time, owner_id, owner_faction, epoch"
                        " FROM stock_event").fetchall() \
        == [(5.0, "[0x1]", None, 0)]
    from x4analyzer.db.schema import SCHEMA_VERSION
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone() == (SCHEMA_VERSION,)
    conn.close()


def test_global_trades_covers_only_current_window(cfg, save_data, ref, conn):
    from x4analyzer.analysis.frames import build_frames

    # a later save whose window no longer overlaps the fixture's history
    store.merge_events(conn, events_save(trades=[
        stock_attrs("5000.0", "10", "[0x20]"),
        stock_attrs("5100.0", "60", "[0x20]"),
    ]))
    frames = build_frames(save_data, ref, conn)
    # the table keeps all history; the dashboard frame sees only the
    # current window, so the Market rate denominators keep their meaning
    assert count(conn, "stock_event") == 3
    assert sorted(frames.global_trades["time"]) == [5000.0, 5100.0]


def test_stock_missing_level_is_zero(conn):
    # the game omits default attrs: no v = empty stock, not unknown
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    store.merge_events(conn, events_save(
        trades=[{"time": "10.0", "ware": "ice", "owner": "[0x9]"}]))
    assert conn.execute("SELECT level FROM stock_event").fetchall() \
        == [(0.0,)]


def test_removed_merge_appends_unseen(conn):
    store.merge_events(conn, events_save(removed=[
        {"id": "115", "owner": "teladi", "name": "TEL Trader",
         "code": "TDR-001"},   # already present from the fixture merge
        {"id": "116", "owner": "argon", "name": "ARG Miner",
         "code": "MIN-002"},
    ]))
    assert count(conn, "removed_object") == 2


# ---- views + the frames.py port (phase 3) -----------------------------------

def test_v_fleet(conn):
    assert conn.execute("SELECT ship, cmdr, depth, is_root_edge FROM v_fleet"
                        ).fetchall() == [("[0x30]", "[0x20]", 1, 1)]


def test_v_npc(conn):
    assert conn.execute(
        "SELECT name, piloting, engineering, morale, boarding FROM v_npc"
        ).fetchall() == [("Jane Doe", 9.0, 3.0, 7.0, None)]


def test_v_built_module(conn):
    # both fixture entries are planned, not built
    assert count(conn, "v_built_module") == 0


def test_v_universe(conn):
    assert count(conn, "v_universe") == 4
    assert conn.execute(
        "SELECT sector_name FROM v_universe WHERE class = 'station'"
        ).fetchone() == ("Grand Exchange I",)  # sector_ref resolved the macro


def test_v_stock_delta(conn):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    store.merge_events(conn, events_save(trades=[
        stock_attrs("10.0", "100"), stock_attrs("20.0", "150"),
        stock_attrs("30.0", "120"), stock_attrs("40.0", "200"),
    ]))
    rows = conn.execute("SELECT time, level, dv, dv_neg FROM v_stock_delta"
                        " ORDER BY time").fetchall()
    assert rows == [
        (10.0, 100.0, None, None),   # no predecessor: no delta
        (20.0, 150.0, 50.0, 0.0),
        (30.0, 120.0, 0.0, 30.0),
        (40.0, 200.0, 80.0, 0.0),
    ]


def test_build_frames_from_db(cfg, save_data, ref, conn):
    from x4analyzer.analysis.frames import build_frames

    frames = build_frames(save_data, ref, conn)

    assert set(frames.universe["class"]) == {"cluster", "sector", "station",
                                             "ship_s"}
    ship = frames.universe[frames.universe["class"] == "ship_s"].iloc[0]
    assert ship["parent.id"] == "[0x20]"
    assert ship["cluster.id"] == "[0x10]" and ship["name"] == ""

    assert frames.wings[["leader", "follower"]].values.tolist() \
        == [["[0x20]", "[0x30]"]]
    assert list(frames.npcs["name"]) == ["Jane Doe"]
    assert frames.npcs.iloc[0]["piloting"] == 9.0

    assert len(frames.station_modules) == 2
    assert frames.built_modules.empty
    assert list(frames.ships["crew.have"]) == [2]
    assert list(frames.orders["default"]) == [True]
    assert list(frames.trade_offers["price"]) == [1.0]
    assert list(frames.sectors["ore"]) == [1000.0]

    gt = frames.global_trades
    assert list(gt["ware"]) == ["ice"] and "dv_neg" in gt.columns
    assert list(frames.tradelog["commodity"]) == ["Energy Cells"]


def test_bulk_insert_speed(cfg, save_data, ref):
    t0 = time.perf_counter()
    conn = store.open_db(cfg, save_data.guid)
    store.write_reference(conn, ref)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    conn.close()
    assert time.perf_counter() - t0 < 2.0


# ---- csv cache retirement: merge-time display identity + legacy import ------

def test_commander_attribution_at_merge(conn, ref):
    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    store.merge_events(conn, events_save(
        trades=[{"time": "50.0", "ware": "energycells", "buyer": "[0xB]",
                 "seller": "[0x30]", "price": "1000", "v": "10"}],
        components=[comp("[0x20]", "STA-001", "player", "My Station"),
                    comp("[0x30]", "SHP-001", "player", "My Trader"),
                    comp("[0xB]", "NPC-001", "argon")],
        links=[("[0x30]", "[0xC1]")], conns=[("[0x20]", "[0xC1]")],
    ), ref)
    assert conn.execute(
        "SELECT seller_cmdr_id, seller_cmdr_name, seller_cmdr_code,"
        " buyer_cmdr_id FROM trade_tx").fetchall() == [
        ("[0x20]", "My Station", "STA-001", None)]


def test_display_name_fallback_at_merge(conn, ref):
    conn.execute("DELETE FROM stock_event")
    conn.commit()
    # unnamed NPC station -> "<SHORT> <stype>"; unnamed player ship -> model
    unnamed_station = comp("[0xA]", "FAC-001", "argon")
    ship = ("[0xS]", "ship_s", "ship_test_macro", "", "SHP-002", "player",
            "", "", "conn", "", "", "", "", "", "", "")
    store.merge_events(conn, events_save(
        trades=[stock_attrs("10.0", "5", "[0xA]"),
                stock_attrs("11.0", "5", "[0xS]")],
        components=[unnamed_station, ship],
    ), ref, stypes={"[0xA]": "Solar Power Plant"})
    names = dict(conn.execute(
        "SELECT owner_id, owner_name FROM stock_event"))
    assert names["[0xA]"] == "ARG Solar Power Plant"
    # fixture macro is unknown to ships.csv -> falls back to the macro
    assert names["[0xS]"] == "ship_test_macro"


def test_frames_log_and_tradelog_from_db(cfg, save_data, ref, conn):
    from x4analyzer.analysis.frames import build_frames

    store.merge_events(conn, events_save(log=[
        {"time": "40.0", "category": "upkeep", "title": "paid",
         "text": "t", "money": "123456"},
    ]), ref)
    frames = build_frames(save_data, ref, conn)
    # money surfaces in cents, like the parser produced (logparse does /100)
    paid = frames.log[frames.log["title"] == "paid"]
    assert list(paid["money"]) == [123456.0]

    tl = frames.tradelog
    assert list(tl["commodity"]) == ["Energy Cells"]
    assert list(tl["money"]) == [1600]
    assert list(tl["buyer.faction"]) == ["PLA"]
    assert list(tl["seller.faction"]) == ["OTH"]     # [0x77] never existed
    assert list(tl["seller.name"]) == ["OTH Station"]
    assert list(tl["buyer.name"]) == ["PLA Station"]  # unnamed player station
    assert tl["seller.proxy.id"].isna().all()


def test_tradelog_renders_commander_and_proxy(cfg, save_data, ref, conn):
    from x4analyzer.analysis.frames import build_frames

    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    # the fixture's ship [0x30] is a subordinate of station [0x20]
    store.merge_events(conn, events_save(
        trades=[{"time": "50.0", "ware": "ice", "buyer": "[0x77]",
                 "seller": "[0x30]", "price": "1000", "v": "10"}],
        components=list(save_data.components),
        links=list(save_data.commander_links),
        conns=list(save_data.subordinate_conns),
    ), ref)
    tl = build_frames(save_data, ref, conn).tradelog
    assert list(tl["seller.id"]) == ["[0x20]"]        # attributed to commander
    assert list(tl["seller.code"]) == ["STA-001"]
    assert list(tl["seller.proxy.id"]) == ["[0x30]"]  # executed by the ship
    assert list(tl["seller.proxy.code"]) == ["SHP-001"]


def test_tradelog_rename_does_not_split_history(cfg, save_data, ref, conn):
    """Names are display-only; the code is the identity. Trades merged under
    an object's old name must show its latest name so per-object views don't
    split a renamed ship in two."""
    from x4analyzer.analysis.frames import build_frames

    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    trade = {"ware": "ice", "buyer": "[0xB]", "seller": "[0x30]",
             "price": "1000", "v": "10"}
    fleet = {"links": [("[0x30]", "[0xC1]")], "conns": [("[0x20]", "[0xC1]")]}
    # run 1: trade merged under the ship's (and commander's) original names
    store.merge_events(conn, events_save(
        trades=[{"time": "100.0", **trade}],
        components=[comp("[0x20]", "STA-001", "player", "Old Station"),
                    comp("[0x30]", "SHP-001", "player", "Old Ship"),
                    comp("[0xB]", "NPC-001", "argon", "Buyer Co")],
        **fleet), ref)
    # run 2: both renamed, new trade merged under the new names
    store.merge_events(conn, events_save(
        trades=[{"time": "200.0", **trade}],
        components=[comp("[0x20]", "STA-001", "player", "New Station"),
                    comp("[0x30]", "SHP-001", "player", "New Ship"),
                    comp("[0xB]", "NPC-001", "argon", "Buyer Co")],
        **fleet), ref)

    tl = build_frames(save_data, ref, conn).tradelog
    # both rows carry the latest observed names, keyed by code
    assert list(tl["seller.name"]) == ["New Station", "New Station"]
    assert list(tl["seller.proxy.name"]) == ["New Ship", "New Ship"]

    # a rename in the current snapshot wins over the trade history: the
    # fixture ship [0x30] is SHP-001 — give it a name and re-snapshot
    save_data.components = [
        c[:3] + ("Current Ship",) + c[4:] if c[4] == "SHP-001" else c
        for c in save_data.components]
    store.write_snapshot(conn, save_data, ref, "save.xml")
    tl = build_frames(save_data, ref, conn).tradelog
    assert list(tl["seller.proxy.name"]) == ["Current Ship", "Current Ship"]


# ---- entity registry ---------------------------------------------------------

def snap(t, comps):
    """A minimal SaveData acting as one analyzed snapshot at game time t."""
    s = events_save(components=comps)
    s.game_time = t
    return s


def entity_rows(conn):
    return conn.execute(
        "SELECT entity_id, code, class, owner, name, spawntime,"
        " gone_time, gone_reason FROM entity ORDER BY entity_id").fetchall()


def test_entity_registry_mint_and_idempotent(conn, ref):
    comps = [comp("[0x1]", "SHP-001", "argon", "Alpha",
                  clazz="ship_s", spawn="10.0"),
             comp("[0x2]", "STA-001", "argon", "Dock"),
             comp("[0x3]", "", "argon"),          # no code: not registered
             comp("[0x4]", "ZON-001", "argon", clazz="zone")]  # wrong class
    m1 = store.update_entity_registry(conn, snap(1000.0, comps), ref)
    assert sorted(m1) == ["[0x1]", "[0x2]"]
    m2 = store.update_entity_registry(conn, snap(1000.0, comps), ref)
    assert m2 == m1                                # same save: same entities
    assert len(entity_rows(conn)) == 2


def test_entity_registry_capture_and_rename(conn, ref):
    m1 = store.update_entity_registry(conn, snap(1000.0, [
        comp("[0x1]", "SHP-001", "xenon", "Prey", clazz="ship_s",
             spawn="10.0")]), ref)
    m2 = store.update_entity_registry(conn, snap(2000.0, [
        comp("[0x9]", "SHP-001", "player", "Trophy", clazz="ship_s",
             spawn="10.0")]), ref)
    # same spawntime = the same physical ship, boarded and renamed
    assert m2["[0x9]"] == m1["[0x1]"]
    (eid, code, clazz, owner, name, spawn, gone, reason), = entity_rows(conn)
    assert (owner, name, gone) == ("player", "Trophy", None)
    assert conn.execute(
        "SELECT event, old_value, new_value FROM entity_event"
        " ORDER BY event").fetchall() == [
        ("captured", "xenon", "player"), ("renamed", "Prey", "Trophy")]


def test_entity_registry_recycle_and_disappear(conn, ref):
    m1 = store.update_entity_registry(conn, snap(1000.0, [
        comp("[0x1]", "SHP-001", "xenon", clazz="ship_s", spawn="10.0"),
        comp("[0x2]", "STA-001", "argon", "Dock")]), ref)
    # the fighter died; its code resurfaced on a new hull (new spawntime),
    # the station is simply absent
    m2 = store.update_entity_registry(conn, snap(2000.0, [
        comp("[0x9]", "SHP-001", "xenon", clazz="ship_s",
             spawn="1500.0")]), ref)
    assert m2["[0x9]"] != m1["[0x1]"]
    by_id = {r[0]: r for r in entity_rows(conn)}
    assert by_id[m1["[0x1]"]][6:] == (2000.0, "recycled")
    assert by_id[m1["[0x2]"]][6:] == (2000.0, "disappeared")
    assert by_id[m2["[0x9]"]][6:] == (None, None)


def test_entity_registry_live_collision(conn, ref):
    # two same-class live ships sharing a code (observed in a 559h save):
    # distinct spawntimes keep them two entities, stably re-matched
    comps = [comp("[0x1]", "VER-731", "split", clazz="ship_s", spawn="10.0"),
             comp("[0x2]", "VER-731", "teladi", clazz="ship_s", spawn="99.0")]
    m1 = store.update_entity_registry(conn, snap(1000.0, comps), ref)
    assert m1["[0x1]"] != m1["[0x2]"]
    m2 = store.update_entity_registry(conn, snap(2000.0, comps), ref)
    assert m2 == m1


def test_entity_registry_resurrects_exact_reappearance(conn, ref):
    # components drift in and out of the save's universe tree between
    # snapshots; an exact (code, class, spawntime) reappearance is the same
    # physical ship and must reopen its entity, not mint a duplicate
    m1 = store.update_entity_registry(conn, snap(1000.0, [
        comp("[0x1]", "SHP-001", "argon", clazz="ship_s", spawn="10.0")]), ref)
    store.update_entity_registry(conn, snap(2000.0, []), ref)
    assert entity_rows(conn)[0][7] == "disappeared"
    m3 = store.update_entity_registry(conn, snap(3000.0, [
        comp("[0x9]", "SHP-001", "argon", clazz="ship_s", spawn="10.0")]), ref)
    assert m3["[0x9]"] == m1["[0x1]"]
    (row,) = entity_rows(conn)
    assert row[6:] == (None, None)       # reopened


def test_entity_registry_skips_stale_snapshot(conn, ref):
    store.update_entity_registry(conn, snap(2000.0, [
        comp("[0x1]", "SHP-001", "argon", clazz="ship_s", spawn="10.0")]), ref)
    m = store.update_entity_registry(conn, snap(1000.0, [
        comp("[0x1]", "SHP-002", "argon", clazz="ship_s", spawn="10.0")]), ref)
    assert m == {}                       # older than the high-water mark
    assert len(entity_rows(conn)) == 1   # and nothing was minted or closed


def test_trade_tx_entity_linkage(conn, ref):
    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    comps = [comp("[0x20]", "STA-001", "player", "My Station"),
             comp("[0x30]", "SHP-001", "player", "My Trader",
                  clazz="ship_s", spawn="10.0"),
             comp("[0xB]", "NPC-001", "argon", "Buyer Co")]
    save = snap(5000.0, comps)
    save.commander_links = [("[0x30]", "[0xC1]")]
    save.subordinate_conns = [("[0x20]", "[0xC1]")]
    save.trades = [{"time": "50.0", "ware": "energycells", "buyer": "[0xB]",
                    "seller": "[0x30]", "price": "1000", "v": "10"}]
    ents = store.update_entity_registry(conn, save, ref)
    store.merge_events(conn, save, ref, entities=ents)
    assert conn.execute(
        "SELECT buyer_entity, seller_entity, seller_cmdr_entity,"
        " buyer_cmdr_entity FROM trade_tx").fetchall() == [
        (ents["[0xB]"], ents["[0x30]"], ents["[0x20]"], None)]


def test_frames_prefers_entity_name(cfg, save_data, ref, conn):
    """The registry's current name beats the merge-time snapshot: a trade
    merged under an old name displays the name after a later rename, keyed
    by entity id (immune to code recycling, unlike the code fallback)."""
    from x4analyzer.analysis.frames import build_frames

    conn.execute("DELETE FROM trade_tx")
    conn.commit()
    comps = [comp("[0x30]", "SHP-001", "player", "Old Name",
                  clazz="ship_s", spawn="10.0"),
             comp("[0xB]", "NPC-001", "argon", "Buyer Co")]
    save = snap(5000.0, comps)
    save.trades = [{"time": "50.0", "ware": "ice", "buyer": "[0xB]",
                    "seller": "[0x30]", "price": "1000", "v": "10"}]
    ents = store.update_entity_registry(conn, save, ref)
    store.merge_events(conn, save, ref, entities=ents)
    store.update_entity_registry(conn, snap(6000.0, [
        comp("[0x31]", "SHP-001", "player", "New Name",
             clazz="ship_s", spawn="10.0"),
        comp("[0xB]", "NPC-001", "argon", "Buyer Co")]), ref)

    tl = build_frames(save_data, ref, conn).tradelog
    assert list(tl["seller.name"]) == ["New Name"]
    assert list(tl["seller.entity"]) == [ents["[0x30]"]]


def test_legacy_csv_import(cfg, save_data, ref):
    import gzip

    log_csv = ("time\tcategory\ttitle\ttext\tmoney\tcomponent\n"
               "5.0\t\told news\tt\t\t\n"
               "6.0\tupkeep\told upkeep\tt\t2000\t\n")
    trade_csv = (
        "time\tcommodity\tprice\tamount\tmoney\t"
        "seller.faction\tseller.id\tseller.name\tseller.code\t"
        "seller.proxy.id\tseller.proxy.name\tseller.proxy.code\t"
        "buyer.faction\tbuyer.id\tbuyer.name\tbuyer.code\t"
        "buyer.proxy.id\tbuyer.proxy.name\tbuyer.proxy.code\n"
        "3.0\tEnergy Cells\t15.0\t100\t1500\t"
        "PLA\t[0xC]\tCommander\tCMD-001\t[0xE]\tExecutor\tEXE-001\t"
        "ARG\t[0xB]\tB\tBBB-222\t\t\t\n")
    guid = save_data.guid
    with gzip.open(cfg.data_dir / f"cache_log_{guid}.csv.gz", "wt") as fh:
        fh.write(log_csv)
    with gzip.open(cfg.data_dir / f"cache_tradelog_{guid}.csv.gz", "wt") as fh:
        fh.write(trade_csv)

    conn = store.open_db(cfg, guid)
    store.write_reference(conn, ref)
    store.write_snapshot(conn, save_data, ref, "save.xml")
    store.merge_events(conn, save_data, ref)   # window starts at t=10.5
    store.import_legacy_caches(conn, cfg, guid, ref)

    # pre-window csv history landed; the dual-written overlap did not dupe
    assert count(conn, "log_entry") == 3
    assert conn.execute("SELECT money_cr FROM log_entry"
                        " WHERE title = 'old upkeep'").fetchall() == [(20.0,)]
    assert conn.execute(
        "SELECT ware, seller_id, seller_name, seller_code, seller_cmdr_id,"
        " seller_cmdr_name, seller_cmdr_code, seller_faction, buyer_faction"
        " FROM trade_tx WHERE time = 3.0").fetchall() == [
        ("energycells", "[0xE]", "Executor", "EXE-001",
         "[0xC]", "Commander", "CMD-001", "player", "argon")]
    # the buyer had no proxy: empty csv cells must not read as truthy NaN
    assert conn.execute("SELECT buyer_id, buyer_cmdr_id FROM trade_tx"
                        " WHERE time = 3.0").fetchall() == [("[0xB]", None)]
    # one-time: flag set, a second call is a no-op
    store.import_legacy_caches(conn, cfg, guid, ref)
    assert count(conn, "log_entry") == 3
    assert count(conn, "trade_tx") == 2
    conn.close()


def test_v2_database_migrates_keeping_trades(cfg):
    import sqlite3

    conn = sqlite3.connect(store.db_path(cfg, "MIG2"))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', '2')")
    conn.execute("CREATE TABLE trade_tx (time REAL NOT NULL,"
                 " ware TEXT NOT NULL, buyer_id TEXT, seller_id TEXT,"
                 " price_cr REAL, amount REAL, raw_attrs TEXT,"
                 " buyer_faction TEXT, buyer_code TEXT, buyer_name TEXT,"
                 " seller_faction TEXT, seller_code TEXT, seller_name TEXT,"
                 " epoch INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO trade_tx VALUES (5.0, 'ice', '[0x1]', '[0x2]',"
                 " 10.0, 3.0, NULL, 'argon', 'AAA-111', 'A',"
                 " 'teladi', 'BBB-222', 'B', 0)")
    conn.execute("CREATE TABLE stock_event (time REAL NOT NULL,"
                 " owner_id TEXT NOT NULL, ware TEXT NOT NULL, level REAL,"
                 " raw_attrs TEXT, owner_faction TEXT, owner_code TEXT,"
                 " owner_name TEXT, epoch INTEGER NOT NULL DEFAULT 0)")
    conn.commit()
    conn.close()

    conn = store.open_db(cfg, "MIG2")
    assert conn.execute("SELECT time, buyer_name, buyer_cmdr_id FROM trade_tx"
                        ).fetchall() == [(5.0, "A", None)]
    conn.close()
