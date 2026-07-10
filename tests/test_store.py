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
    store.merge_events(conn, save_data)
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
    # event history (merged, not rebuilt)
    "trade_tx": 1,
    "stock_event": 1,
    "log_entry": 1,
    "removed_object": 1,
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


# ---- event-history merges (phase 2) ----------------------------------------

def events_save(log=(), trades=(), removed=()):
    from x4analyzer.saveparser import SaveData
    s = SaveData()
    s.log_entries = list(log)
    s.trades = list(trades)
    s.removed_objects = list(removed)
    return s


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
    assert conn.execute(
        "SELECT time, category, title FROM log_entry").fetchall() == [
        (100.0, "upkeep", "Test entry")]
    assert conn.execute(
        "SELECT id, name, owner FROM removed_object").fetchall() == [
        ("115", "TEL Trader", "teladi")]


def test_merge_idempotent(conn, save_data):
    before = {t: dump(conn, t) for t in
              ("trade_tx", "stock_event", "log_entry", "removed_object")}
    store.merge_events(conn, save_data)
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


# ---- dual-write equivalence: SQL merge == csv.gz merge (phase 2) ------------

def test_dual_write_log_equivalence(cfg, conn):
    from x4analyzer.caches import merge_log_cache
    import pandas as pd

    conn.execute("DELETE FROM log_entry")
    conn.commit()
    windows = [
        [("10.0", "", "old news"), ("20.0", "upkeep", "old upkeep")],
        [("30.0", "", "new news"), ("15.0", "upkeep", "reissued upkeep")],
    ]
    for w in windows:
        df = pd.DataFrame(
            [(float(t), c, title, "t", None, None) for t, c, title in w],
            columns=["time", "category", "title", "text", "money",
                     "component"])
        csv_merged = merge_log_cache(cfg, "CSVEQ", df)
        store.merge_events(conn, events_save(log=[
            {"time": t, "category": c, "title": title, "text": "t"}
            for t, c, title in w]))

    sql_rows = sorted(
        (t, c or "", title, text)
        for t, c, title, text in conn.execute(
            "SELECT time, category, title, text FROM log_entry"))
    csv_rows = sorted(
        (r["time"], r["category"], r["title"], r["text"])
        for _, r in csv_merged.iterrows())
    assert sql_rows == csv_rows


def test_dual_write_tradelog_equivalence(cfg, conn):
    from x4analyzer.caches import merge_tradelog_cache
    import pandas as pd

    conn.execute("DELETE FROM trade_tx")
    conn.commit()

    def csv_frame(times, sid, bid):
        return pd.DataFrame([{
            "time": t, "commodity": "Energy Cells", "price": 15.0,
            "amount": 100, "money": 1500,
            "seller.faction": "PLA", "seller.id": sid, "seller.name": "S",
            "seller.code": "AAA-111", "seller.proxy.id": None,
            "seller.proxy.name": None, "seller.proxy.code": None,
            "buyer.faction": "ARG", "buyer.id": bid, "buyer.name": "B",
            "buyer.code": "BBB-222", "buyer.proxy.id": None,
            "buyer.proxy.name": None, "buyer.proxy.code": None,
        } for t in times])

    # same playthrough, drifted runtime ids in the second save
    windows = [
        ([100.0, 200.0], "[0x1]", "[0x2]"),
        ([100.0, 200.0, 300.0], "[0x999]", "[0x888]"),
    ]
    for times, sid, bid in windows:
        csv_merged = merge_tradelog_cache(cfg, "CSVEQ", csv_frame(times, sid, bid))
        store.merge_events(conn, events_save(trades=[
            trade_attrs(str(t), bid, sid) for t in times]))

    sql_rows = sorted(conn.execute(
        "SELECT time, price_cr, amount FROM trade_tx"))
    csv_rows = sorted(
        (r["time"], r["price"], float(r["amount"]))
        for _, r in csv_merged.iterrows())
    assert sql_rows == csv_rows
    # commodity display name and raw ware id describe the same ware
    assert {r[0] for r in conn.execute("SELECT ware FROM trade_tx")} \
        == {"energycells"}
    assert set(csv_merged["commodity"]) == {"Energy Cells"}


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
    from x4analyzer.frames import build_frames

    frames = build_frames(save_data, ref, cfg, conn)

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
