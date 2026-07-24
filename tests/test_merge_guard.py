"""Pins the stale-save merge guard (T14/H4, review backlog item 3 /
db-schema F4): merging a save OLDER than the stored event history must
not destroy rows newer than that save's window. Before the guard,
`merge_events` deleted from the incoming window's mintime forward
unconditionally — verified against a real DB copy on 2026-07-23: merging
save_008 (t=66,772) into the 8E0C DB (window head t=71,874) destroyed
606 trade_tx, 29,063 stock_event and 244 log_entry rows. The high-water
guard now skips the whole merge with a warning (originally pinned as
xfail; flipped to a plain test when H4 landed).
"""
import sqlite3

from x4analyzer.db import store
from x4analyzer.save.parser import parse_savegame

SAVE_TEMPLATE = """<?xml version="1.0"?>
<savegame>
  <info>
    <save name="#001" date="1700000000"/>
    <game guid="ABCD-1234" version="900" time="{time}" modified="1"/>
    <player name="Test Pilot" money="123456"/>
  </info>
  <universe>
    <factions><faction id="player"/></factions>
    <component class="galaxy" id="[0x1]" connection="space">
      <connections/>
    </component>
  </universe>
  <economylog>
    <entries type="trade">
{trades}
    </entries>
  </economylog>
  <log>
{logs}
  </log>
</savegame>
"""


def make_save(tmp_path, name, time, trades, logs):
    p = tmp_path / name
    p.write_text(SAVE_TEMPLATE.format(
        time=time,
        trades="\n".join(trades),
        logs="\n".join(logs)))
    return parse_savegame(p)


def test_older_save_merge_preserves_newer_history(tmp_path):
    newer = make_save(
        tmp_path, "newer.xml", 6000.0,
        trades=[
            '<log time="5500.0" type="trade" ware="energycells" '
            'buyer="[0x20]" seller="[0x21]" price="1600" v="100"/>',
            '<log time="5500.0" type="trade" ware="ice" owner="[0x20]" v="50"/>',
            '<log time="5900.0" type="trade" ware="ice" owner="[0x20]" v="70"/>',
        ],
        logs=['<entry time="5500.0" category="upkeep" title="new" text="t"/>'])
    older = make_save(
        tmp_path, "older.xml", 5000.0,
        trades=[
            '<log time="4500.0" type="trade" ware="energycells" '
            'buyer="[0x20]" seller="[0x21]" price="1500" v="90"/>',
            '<log time="4900.0" type="trade" ware="ice" owner="[0x20]" v="40"/>',
        ],
        logs=['<entry time="4500.0" category="upkeep" title="old" text="t"/>'])

    conn = sqlite3.connect(":memory:")
    store._ensure_schema(conn)
    store.merge_events(conn, newer)

    # an out-of-order import (wrong --save, autosave rotation in watch mode)
    store.merge_events(conn, older)

    survived = {
        t: conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE time > 5000.0").fetchone()[0]
        for t in ("trade_tx", "stock_event", "log_entry")}
    assert survived == {"trade_tx": 1, "stock_event": 2, "log_entry": 1}, (
        "history newer than the merged older save was destroyed: "
        f"{survived}")
    # the skip is whole-merge: nothing from the older save landed either
    assert conn.execute("SELECT COUNT(*) FROM trade_tx WHERE time < 5000.0"
                        ).fetchone() == (0,)
    # and the high-water mark still belongs to the newer save
    assert conn.execute("SELECT value FROM meta"
                        " WHERE key = 'merge_events_time'").fetchone() \
        == ("6000.0",)


def test_guard_falls_back_to_event_times(tmp_path):
    """DBs whose history predates the guard have no meta stamp: the
    newest stored event time is the fallback high-water mark."""
    newer = make_save(
        tmp_path, "newer.xml", 6000.0,
        trades=['<log time="5900.0" type="trade" ware="ice" owner="[0x20]"'
                ' v="70"/>'],
        logs=[])
    older = make_save(
        tmp_path, "older.xml", 5000.0,
        trades=['<log time="4900.0" type="trade" ware="ice" owner="[0x20]"'
                ' v="40"/>'],
        logs=[])
    conn = sqlite3.connect(":memory:")
    store._ensure_schema(conn)
    store.merge_events(conn, newer)
    conn.execute("DELETE FROM meta WHERE key = 'merge_events_time'")
    conn.commit()

    store.merge_events(conn, older)
    assert conn.execute("SELECT time FROM stock_event").fetchall() \
        == [(5900.0,)]


def test_same_save_remerge_proceeds(tmp_path):
    """Equal game time is NOT stale: re-analyzing the same save must
    still merge (and stay idempotent via the window semantics)."""
    save = make_save(
        tmp_path, "save.xml", 6000.0,
        trades=['<log time="5900.0" type="trade" ware="ice" owner="[0x20]"'
                ' v="70"/>'],
        logs=['<entry time="5500.0" category="upkeep" title="n" text="t"/>'])
    conn = sqlite3.connect(":memory:")
    store._ensure_schema(conn)
    store.merge_events(conn, save)
    store.merge_events(conn, save)
    assert conn.execute("SELECT COUNT(*) FROM stock_event").fetchone() \
        == (1,)
    assert conn.execute("SELECT COUNT(*) FROM log_entry").fetchone() == (1,)
