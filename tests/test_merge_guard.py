"""Pins the older-save merge destruction (review backlog item 3 / db-schema
F4): merging a save OLDER than the stored event history must not destroy
rows newer than that save's window, but `merge_events` today deletes from
the incoming window's mintime forward unconditionally
(`_merge_window`/`_merge_log`). Verified against a real DB copy on
2026-07-23: merging save_008 (t=66,772) into the 8E0C DB (window head
t=71,874) destroyed 606 trade_tx, 29,063 stock_event and 244 log_entry
rows. The xfail flips when T14's high-water guard lands in `merge_events`
(H4) — remove the marker then.
"""
import sqlite3

import pytest

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


@pytest.mark.xfail(
    reason="merge_events has no high-water guard: an older save's window "
           "deletes newer history from its mintime forward (db-schema F4; "
           "fixed by T14/H4)",
    strict=True)
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
