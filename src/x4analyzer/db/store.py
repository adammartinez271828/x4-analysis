"""SQLite store: writes every parsed save record to x4_<guid>.sqlite.

The database (one per game GUID, in the user data dir next to the csv.gz
caches) is a rebuildable artifact derived from save + game files — EXCEPT
the event-history tables (schema.EVENT_TABLES), which preserve the
rolling log/economylog windows the game has already discarded, the
persistent bookkeeping tables (schema.PERSISTENT_TABLES: save/meta, the
provenance log and cross-run flags), and the aggregate-history tables
(schema.AGGREGATE_TABLES, the per-snapshot trend layer); none of these
classes is ever dropped.
Schema and conventions: docs/reference/db-schema.md.

Load rules worth calling out:
- "" from the parser becomes NULL (SQL predicates read better); macros are
  lowercased; money cents / 100 into *_cr columns.
- component rows with an empty @connection are not universe objects and are
  skipped, mirroring frames.universe's filter.
- {page,id} text refs in component names are resolved at load, so SQL
  consumers never see raw refs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import schema
from ..cli import log
from ..config import Config
from ..gamedata.refdata import OTHER_FACTION, RefData
from ..save.parser import SaveData

_CODE_RE = re.compile(r"[A-Z]{3}-[0-9]{3}")


def db_path(cfg: Config, guid: str) -> Path:
    return cfg.data_dir / f"x4_{guid}.sqlite"


def open_db(cfg: Config, guid: str) -> sqlite3.Connection:
    path = db_path(cfg, guid)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    # FKs in the schema are documentation: modded saves reference macros/
    # factions/wares the reference tables have never heard of
    conn.execute("PRAGMA foreign_keys=OFF")
    # live-mode coexistence: WAL (persistent in the file) lets readers and
    # the writer overlap; NORMAL sync is safe under WAL (a crash loses at
    # most the last transaction, never corrupts)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    have_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    version = None
    if have_meta:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        version = row[0] if row else None
    if version is not None and version != schema.SCHEMA_VERSION:
        # everything but event history and persistent bookkeeping is
        # rebuilt from the save in seconds: migration = drop and recreate.
        # Event tables carry irreplaceable history and save/meta carry
        # cross-run provenance; they get targeted statements instead,
        # walking the complete version chain so off-chain DBs migrate too.
        keep = (schema.EVENT_TABLES + schema.PERSISTENT_TABLES
                + schema.AGGREGATE_TABLES)
        with conn:
            # drop ALL views before the walk, not after: views are
            # code-owned (recreated below via the views_version path),
            # and a stale view referencing a table a migration step
            # drops/renames would fail SQLite's whole-schema validation
            # on any later ALTER ... RENAME in the walk (seen live: the
            # v14 v_station referenced `module`, dropped at step 14→15,
            # breaking step 15→16's RENAME COLUMN)
            for (name,) in conn.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type = 'view'").fetchall():
                conn.execute(f'DROP VIEW IF EXISTS "{name}"')
            step = version
            while (step != schema.SCHEMA_VERSION
                   and step in schema.NEXT_VERSION):
                for stmt in schema.EVENT_MIGRATIONS.get(step, ()):
                    conn.execute(stmt)
                step = schema.NEXT_VERSION[step]
            for name in schema.TABLES:
                if name not in keep:
                    conn.execute(f"DROP TABLE IF EXISTS {name}")
            # zombie drop (T13): tables the DB managed under an older
            # version that the current code no longer knows are dropped
            # too — the loop above only knows CURRENT names, so renames/
            # removals would otherwise linger forever. The candidate set
            # is what a previous version RECORDED as managed (its
            # meta 'managed_tables' inventory) plus the known pre-
            # inventory zombies (LEGACY_TABLES); user-created tables are
            # in neither, and E/A/P tables are excluded by `keep`.
            stored = conn.execute("SELECT value FROM meta"
                                  " WHERE key = 'managed_tables'").fetchone()
            inventory = set(json.loads(stored[0])) if stored else set()
            for name in sorted(inventory | set(schema.LEGACY_TABLES)):
                if name not in schema.TABLES and name not in keep:
                    conn.execute(f"DROP TABLE IF EXISTS {name}")
            # meta survives the bump (P class), so cache stamps describing
            # objects the bump just dropped must not: stale stamps would
            # skip recreating the views / repopulating the R tables
            conn.execute("DELETE FROM meta WHERE key IN"
                         " ('views_version', 'reference_digest')")
    with conn:
        for ddl in schema.TABLES.values():
            conn.execute(ddl)
        for ddl in schema.INDEXES:
            conn.execute(ddl)
        if version != schema.SCHEMA_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                (schema.SCHEMA_VERSION,))
            # record what this version manages, so a FUTURE version can
            # drop whatever it renames or removes (the zombie drop above)
            conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('managed_tables', ?)",
                (json.dumps(sorted(schema.TABLES)),))
        # views are recreated only when their definitions changed
        # (meta 'views_version'), so plain connects stay write-free and
        # read-only consumers always see current views
        stored = conn.execute("SELECT value FROM meta"
                              " WHERE key = 'views_version'").fetchone()
        if stored is None or stored[0] != schema.VIEWS_VERSION:
            for name, ddl in schema.VIEWS.items():
                conn.execute(f"DROP VIEW IF EXISTS {name}")
                conn.execute(ddl)
            conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('views_version', ?)",
                (schema.VIEWS_VERSION,))


# ---- value coercion (parser "" convention -> SQL NULL convention) ----------

def _s(v):
    """Optional TEXT: empty string -> NULL."""
    return v if v not in ("", None) else None


def _low(v):
    """Optional lowercased TEXT (save vs game files disagree on case)."""
    return v.lower() if v not in ("", None) else None


def _f(v):
    """Optional REAL."""
    if v in ("", None):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    """Optional INTEGER (permissive: unparseable -> NULL, never fail)."""
    f = _f(v)
    return int(f) if f is not None else None


def _pdval(v):
    """pandas cell -> SQL value (NaN/NA/"" -> NULL)."""
    if v is None or v == "" or (pd.api.types.is_scalar(v) and pd.isna(v)):
        return None
    return v


def _df_rows(df: pd.DataFrame, cols: list[str], table: str = "") -> list[tuple]:
    if df is None or df.empty:
        return []
    # reindex tolerates columns the CSV lacks (defensive by convention) —
    # but say so: the usual cause is a stale extract-gamedata output in the
    # user data dir shadowing a newer packaged CSV, which would otherwise
    # load as a column of silent NULLs
    missing = [c for c in cols if c not in df.columns]
    if missing and table:
        log(f"  WARNING: {table}: reference data has no {', '.join(missing)}"
            " column(s) — loading them as NULL; rerun extract-gamedata"
            " if a stale copy in the user data dir is shadowing the"
            " packaged one")
    sub = df.reindex(columns=cols)
    return [tuple(_pdval(v) for v in row)
            for row in sub.itertuples(index=False, name=None)]


# ---- reference data (R: replaced wholesale) ---------------------------------

def write_reference(conn: sqlite3.Connection, ref: RefData) -> None:
    """Load the reference tables + textdb, skipped entirely when the data
    is unchanged since the last import (digest in meta('reference_digest')
    — reference data only moves when extract-gamedata reruns, and a
    watcher analyzing every autosave should not rewrite ten tables per
    save)."""
    loads = (
        ("ware", ref.wares.rename(columns={"group": "grp"}),
         ["id", "name", "grp", "transport", "volume", "tags",
          "price_min", "price_avg", "price_max", "component", "source"]),
        ("recipe", ref.recipes,
         ["ware", "method", "time", "amount", "input_ware", "input_amount",
          "work_effect"]),
        ("module_ref", ref.modules,
         ["macro", "name", "ware", "method", "scale", "workforce", "source"]),
        ("ship_ref", ref.ships,
         ["macro", "model", "class", "race", "purpose", "hull", "mass",
          "cargo", "crew", "price", "source"]),
        ("faction", ref.factions,
         ["id", "shortname", "name", "primaryrace", "colour", "source"]),
        ("cluster_ref", ref.clusters,
         ["macro", "x", "y", "z", "name", "description", "source"]),
        ("sector_ref", ref.sectors,
         ["cluster", "macro", "x", "y", "z", "name", "source"]),
        ("gate", ref.gates, ["sector_a", "sector_b", "source"]),
        ("module_cap", ref.modcaps,
         ["macro", "class", "housing", "workers", "cargo_max", "cargo_tags",
          "unit_storage"]),
        # regionyields.csv reaches refdata as a dict; rebuild rows in a
        # deterministic order (the digest below hashes them). respawn_min
        # keeps the CSV's MINUTES unit — see the region_yield DDL note
        ("region_yield", pd.DataFrame(
            [(level, ware, cap, delay)
             for (level, ware), (cap, delay)
             in sorted(ref.region_yields.items())],
            columns=["level", "ware", "capacity", "respawn_min"]),
         ["level", "ware", "capacity", "respawn_min"]),
    )
    payload = [(table, cols, _df_rows(df, cols, table))
               for table, df, cols in loads]
    text_rows = list(ref.textdb.items())
    digest = hashlib.sha256()
    for table, cols, rows in payload:
        digest.update(repr((table, cols, rows)).encode())
    digest.update(repr(text_rows).encode())
    digest = digest.hexdigest()[:16]
    stored = conn.execute("SELECT value FROM meta"
                          " WHERE key = 'reference_digest'").fetchone()
    if stored is not None and stored[0] == digest:
        return

    with conn:
        for table, cols, rows in payload:
            conn.execute(f"DELETE FROM {table}")
            if rows:
                ph = ",".join("?" * len(cols))
                conn.executemany(
                    f"INSERT OR REPLACE INTO {table} VALUES ({ph})", rows)
        conn.execute("DELETE FROM text")
        conn.executemany("INSERT OR REPLACE INTO text VALUES (?,?,?)",
                         text_rows)
        conn.execute("INSERT OR REPLACE INTO meta VALUES"
                     " ('reference_digest', ?)", (digest,))


# ---- world state (W: one snapshot, replaced per import) ---------------------

def write_snapshot(conn: sqlite3.Connection, save: SaveData, ref: RefData,
                   source_file: Path | str,
                   entities: dict[str, int] | None = None) -> int:
    """Write the save's world snapshot. `entities` (component id ->
    entity_id, from update_entity_registry — which therefore runs first
    in the pipeline) stamps component rows with durable identity; rows
    it does not cover (sectors, clusters, registry-skipped runs) keep
    NULL."""
    entities = entities or {}

    def resolve(name):
        if name and "{" in name:
            return ref.resolve_name(name)
        return _s(name)

    # rerun detection (T5): an import whose (game_time, save_date) is
    # already recorded is a re-analysis of a known snapshot, not new
    # history. The W rebuild below still runs (that is the point of a
    # rerun); consumers of per-snapshot series key on snapshot_id() /
    # v_snapshot instead of raw save rows, which makes reruns harmless.
    rerun = conn.execute(
        "SELECT 1 FROM save WHERE guid IS ? AND game_time IS ?"
        " AND save_date IS ?",
        (save.guid, save.game_time, _s(save.save_date))).fetchone()
    if rerun:
        log("Snapshot already recorded (rerun): world state rebuilds, "
            "per-snapshot series gain nothing")

    with conn:
        cur = conn.execute(
            "INSERT INTO save (guid, game_version, game_time, save_date,"
            " modified, player_name, player_money_cr, faction_name,"
            " source_file, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (save.guid, _s(save.game_version), save.game_time,
             _s(save.save_date), int(save.modified), _s(save.player_name),
             save.player_money / 100.0, _s(save.player_faction_name),
             str(source_file),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        save_id = cur.lastrowid

        # phases 1-3 keep only the latest snapshot; retention is phase 5
        for table in schema.WORLD_TABLES:
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT OR REPLACE INTO component VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(save_id, cid, clazz, _low(macro), resolve(name),
              resolve(basename), _s(code), _s(owner), _s(knownto),
              _i(contested), _f(spawntime),
              _s(parent_id), _s(cluster_id), _low(cluster_macro),
              _s(sector_id), _low(sector_macro), sx, sz, _i(faction_hq),
              entities.get(cid), _i(known))
             for (cid, clazz, macro, name, code, owner, knownto, contested,
                  connection, spawntime, cluster_id, cluster_macro, sector_id,
                  sector_macro, basename, parent_id, sx, sz, faction_hq,
                  known)
             in save.components
             if connection])  # no @connection = not in the universe tree

        # fleet hierarchy, resolved once: follower's <connected> conn ref
        # matched to the commander's "subordinates" connection id (rows in
        # commander order, like the frames.wings merge always produced)
        followers_by_conn: dict[str, list] = {}
        for follower, conn_ref in save.commander_links:
            followers_by_conn.setdefault(conn_ref, []).append(follower)
        edges: dict[str, str] = {}
        conflicts = 0
        for leader, conn_id in save.subordinate_conns:
            for follower in followers_by_conn.get(conn_id, ()):
                # the PK allows one commander per follower; a save that
                # links a ship to two commanders is broken/modded data —
                # keep the first edge, but say so instead of silently
                # picking a fleet
                if edges.setdefault(follower, leader) != leader:
                    conflicts += 1
        if conflicts:
            log(f"WARNING: {conflicts} ships link to more than one "
                "commander; kept the first edge each")
        conn.executemany(
            "INSERT OR REPLACE INTO fleet_edge VALUES (?,?,?)",
            [(save_id, follower, leader)
             for follower, leader in edges.items()])

        # stations list their build plan twice (construction sequence + the
        # expand queue repeat the same entry ids): count each entry once per
        # host. Entries without ids are all kept, and count as built the way
        # frames.built_modules keeps them defensively.
        built = set(save.built_refs)
        seen: set[tuple] = set()
        entry_rows = []
        for host, idx, macro, entry in save.modules:
            if entry:
                if (host, entry) in seen:
                    continue
                seen.add((host, entry))
            entry_rows.append(
                (save_id, host, _s(entry), idx, _low(macro),
                 1 if (entry in built or not entry) else 0))
        conn.executemany(
            "INSERT INTO build_entry VALUES (?,?,?,?,?,?)", entry_rows)

        conn.executemany(
            "INSERT INTO module_upgrade VALUES (?,?,?)",
            [(save_id, entry, macro)
             for entry, macro in save.module_upgrades])

        wf: dict[tuple, float] = {}
        for station, race, amount in save.workforce:
            key = (station, race)
            wf[key] = wf.get(key, 0.0) + amount
        conn.executemany(
            "INSERT OR REPLACE INTO workforce VALUES (?,?,?,?)",
            [(save_id, station, race, amount)
             for (station, race), amount in wf.items()])

        conn.executemany(
            "INSERT OR REPLACE INTO npc VALUES (?,?,?,?,?)",
            [(save_id, nid, _s(name), _s(code), _s(owner))
             for nid, name, code, owner, _skills in save.npcs])
        conn.executemany(
            "INSERT OR REPLACE INTO npc_skill VALUES (?,?,?,?)",
            [(save_id, nid, skill, value)
             for nid, _n, _c, _o, skills in save.npcs
             for skill, value in skills.items()])

        conn.executemany(
            "INSERT INTO post VALUES (?,?,?,?)",
            [(save_id, oid, post, _s(npc_id))
             for oid, post, npc_id in save.posts])

        conn.executemany(
            "INSERT OR REPLACE INTO people VALUES (?,?,?,?)",
            [(save_id, oid, role, count)
             for (oid, role), count in save.people.items()])

        # a host may repeat a ware across storage components: sum per PK
        cg: dict[tuple, float] = {}
        for oid, ware, amount in save.cargo:
            key = (oid, ware)
            cg[key] = cg.get(key, 0.0) + amount
        conn.executemany(
            "INSERT OR REPLACE INTO cargo VALUES (?,?,?,?)",
            [(save_id, oid, ware, amount)
             for (oid, ware), amount in cg.items()])

        conn.executemany(
            "INSERT INTO trade_offer VALUES (?,?,?,?,?,?,?,?)",
            # hostless offers are NULL like every other absent value (the
            # '' exception retired in v15, plan T11)
            [(save_id, _s(oid), side, ware, amount, price_cr, _s(flags),
              desired)
             for oid, side, ware, amount, price_cr, flags, desired
             in save.trade_offers])

        conn.executemany(
            "INSERT INTO build_resource VALUES (?,?,?,?,?)",
            [(save_id, _s(host), ware, amount, kind)
             for host, ware, amount, kind in save.build_resources])

        conn.executemany(
            "INSERT INTO ship_order VALUES (?,?,?,?,?)",
            [(save_id, oid, order, int(is_default), _s(state))
             for oid, order, is_default, state in save.orders])

        conn.executemany(
            "INSERT INTO resource VALUES (?,?,?,?,?,?,?)",
            [(save_id, _low(sector), ware, yld, _s(level), _s(speed), start)
             for sector, ware, yld, level, speed, start in save.resources])

        conn.executemany(
            "INSERT INTO floating_ware VALUES (?,?,?,?)",
            [(save_id, _low(sector), ware, amount)
             for sector, ware, amount in save.floating_wares])

        # the game retains duplicate-free rows keyed on component; INSERT OR
        # REPLACE guards against a malformed modded save repeating one
        conn.executemany(
            "INSERT OR REPLACE INTO player_subscription VALUES (?,?,?)",
            [(save_id, oid, expires)
             for oid, expires in save.player_subscriptions])

        conn.executemany(
            "INSERT OR REPLACE INTO build_price_factor VALUES (?,?,?)",
            [(save_id, oid, factor)
             for oid, factor in save.build_price_factors])

        conn.executemany(
            "INSERT OR REPLACE INTO player_scan VALUES (?,?,?)",
            [(save_id, oid, level) for oid, level in save.player_scans])

        conn.executemany(
            "INSERT OR REPLACE INTO station_trade_setting VALUES (?,?,?,?)",
            [(save_id, oid, setting, ware)
             for oid, setting, ware in save.trade_settings])

        # committed in-flight trades: the save keeps each one twice (the
        # ship's order and the station's reservation, attribute-identical),
        # so merge by trade id — the ship side supplies ship_id, the
        # station side station_id, and either supplies the trade itself
        active = set(save.trade_active_ids)
        pending: dict[str, list] = {}
        for (source, tid, host, reserver, buyer, seller, partner, ware,
             amount, desired, transferred, price_cr, escrow_cr, flags,
             time) in save.trade_pending:
            row = pending.setdefault(tid, [
                save_id, tid, _low(ware), amount, desired, transferred,
                price_cr, escrow_cr, _s(buyer), _s(seller), None, None,
                1 if tid in active else 0, _f(time), _s(flags)])
            if source == "order":
                row[10] = _s(host) or row[10]
            else:
                row[11] = _s(host) or row[11]
                row[10] = row[10] or _s(reserver)
        conn.executemany(
            "INSERT OR REPLACE INTO trade_pending"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [tuple(r) for r in pending.values()])

        # engines of player ships only (speed-from-loadout; NPC loadouts
        # would multiply the table size for no analysis value)
        player_ships = {c[0] for c in save.components
                        if c[1].startswith("ship_") and c[5] == "player"}
        eng_counts: dict[tuple, int] = {}
        for sid, macro in save.ship_engines:
            if sid in player_ships:
                key = (sid, macro.lower())
                eng_counts[key] = eng_counts.get(key, 0) + 1
        conn.executemany(
            "INSERT OR REPLACE INTO ship_engine VALUES (?,?,?,?)",
            [(save_id, sid, macro, n)
             for (sid, macro), n in eng_counts.items()])

        conn.executemany(
            "INSERT OR REPLACE INTO datavault VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(save_id, vid, _low(macro), _s(code), _s(knownto),
              _low(sector), sx, sz, unlocked, loot, _s(bps))
             for (vid, macro, code, knownto, sector, sx, sz,
                  unlocked, loot, bps) in save.datavaults])

        conn.executemany(
            "INSERT OR REPLACE INTO wormhole VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(save_id, wid, _low(macro), _s(code), _s(knownto),
              _low(cluster), _low(sector), sx, sz, _s(entry), _s(sclass),
              tdest)
             for (wid, macro, code, knownto, cluster, sector, sx, sz,
                  entry, sclass, tdest) in save.wormholes])
        conn.executemany(
            "INSERT INTO wormhole_link VALUES (?,?,?,?,?)",
            [(save_id, wid, own, _s(role), tgt)
             for (wid, own, role, tgt) in save.wormhole_links])

        # faction diplomacy: base relations, boosters, discounts -> one table
        def _t(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        rel_rows = [(save_id, _low(a), _low(b), "base", v, None)
                    for (a, b, v) in save.faction_relations]
        rel_rows += [(save_id, _low(a), _low(b), "booster", v, _t(t))
                     for (a, b, v, t) in save.faction_boosters]
        rel_rows += [(save_id, _low(a), _low(b), "discount", v, _t(t))
                     for (a, b, v, t) in save.faction_discounts]
        conn.executemany(
            "INSERT INTO faction_relation VALUES (?,?,?,?,?,?)", rel_rows)
        # faction_meta carries the treasury and the preferred build method;
        # the two come from different blocks and neither is universal, so
        # key on the union (most factions have an account and no build rule)
        accounts = {_low(f): _cents(amount)
                    for (f, amount) in save.faction_accounts}
        rules = {_low(f): _low(m) for (f, m) in save.faction_build_rules}
        conn.executemany(
            "INSERT OR REPLACE INTO faction_meta VALUES (?,?,?,?)",
            # treasuries are cents in the save; account_cr is credits like
            # every other money column (v15, plan T11)
            [(save_id, f, accounts.get(f), rules.get(f))
             for f in dict.fromkeys([*accounts, *rules])])
        conn.executemany(
            "INSERT OR REPLACE INTO station_supply VALUES (?,?,?,?,?)",
            [(save_id, oid, kind, _low(ware), amount)
             for (oid, kind, ware, amount) in save.station_supplies
             if oid and ware])
        conn.executemany(
            # whole credits in the save already — <trade><prices> is the one
            # price block that is not in cents; 0 = that side unset
            "INSERT OR REPLACE INTO price_setting VALUES (?,?,?,?,?,?)",
            [(save_id, oid, kind, _low(ware), buy or None, sell or None)
             for (oid, kind, ware, buy, sell) in save.price_settings
             if oid and ware])
        conn.executemany(
            "INSERT OR REPLACE INTO ware_limit VALUES (?,?,?,?,?)",
            [(save_id, oid, kind, _low(ware), amount)
             for (oid, kind, ware, amount) in save.ware_limits
             if oid and ware])
        conn.executemany(
            "INSERT OR REPLACE INTO build_method VALUES (?,?,?)",
            [(save_id, oid, _low(method))
             for (oid, method) in save.station_build_methods if oid])
        conn.executemany(
            "INSERT INTO faction_licence VALUES (?,?,?,?)",
            [(save_id, _low(f), _s(typ), _s(facs))
             for (f, typ, facs) in save.faction_licences])

    return save_id


def snapshot_id(conn: sqlite3.Connection, save_id: int) -> int:
    """Canonical snapshot id for an import: the FIRST save row recording
    the same (guid, game_time, save_date) — i.e. v_snapshot's save_id.
    Reruns of a known snapshot resolve to the original import's id, so
    anything keyed on it (the A tables) is rerun-immune."""
    row = conn.execute(
        "SELECT guid, game_time, save_date FROM save WHERE save_id = ?",
        (save_id,)).fetchone()
    if row is None:
        return save_id
    return conn.execute(
        "SELECT MIN(save_id) FROM save WHERE guid IS ? AND game_time IS ?"
        " AND save_date IS ?", row).fetchone()[0]


# ---- aggregate history (A: the trend layer, appended per snapshot) ----------

def write_aggregates(conn: sqlite3.Connection, save_id: int) -> bool:
    """Append this import's per-snapshot aggregates (plan T4): small
    INSERT…SELECTs over the W tables write_snapshot just wrote. Rows key
    on the CANONICAL snapshot id (snapshot_id/v_snapshot), and each table
    is appended only if that snapshot has no rows there yet — so reruns
    add nothing, while a snapshot first imported before the A layer
    existed still receives its rows on the next import. Key columns that
    are NULL in the source COALESCE to '' (schema comment / plan F6).
    Returns True when anything was appended."""
    snap = snapshot_id(conn, save_id)
    appended = False
    with conn:
        have = {table: conn.execute(
                    f"SELECT 1 FROM {table} WHERE save_id = ? LIMIT 1",
                    (snap,)).fetchone() is not None
                for table in schema.AGGREGATE_TABLES}
        if not have["sector_presence"]:
            conn.execute(
                """INSERT INTO sector_presence
                   SELECT ?, COALESCE(sector_macro, ''),
                          COALESCE(owner, ''), class, COUNT(*)
                   FROM component
                   WHERE save_id = ?
                     AND (class LIKE 'ship_%'
                          OR class IN ('station', 'buildstorage'))
                   GROUP BY 2, 3, 4""", (snap, save_id))
            appended = True
        if not have["station_metric"]:
            conn.execute(
                """INSERT INTO station_metric
                   SELECT ?, c.entity_id,
                          (SELECT SUM(w.amount) FROM workforce w
                            WHERE w.save_id = c.save_id
                              AND w.station_id = c.id),
                          (SELECT COUNT(*) FROM build_entry m
                            WHERE m.save_id = c.save_id
                              AND m.host_id = c.id AND m.built = 1),
                          (SELECT SUM(cg.amount * COALESCE(wr.price_avg, 0))
                             FROM cargo cg
                             LEFT JOIN ware wr ON wr.id = cg.ware
                            WHERE cg.save_id = c.save_id
                              AND cg.object_id = c.id),
                          (SELECT SUM(o.amount * o.price_cr)
                             FROM trade_offer o
                            WHERE o.save_id = c.save_id
                              AND o.object_id = c.id AND o.side = 'buy'),
                          (SELECT SUM(o.amount * o.price_cr)
                             FROM trade_offer o
                            WHERE o.save_id = c.save_id
                              AND o.object_id = c.id AND o.side = 'sell')
                   FROM component c
                   WHERE c.save_id = ? AND c.class = 'station'
                     AND c.owner = 'player'
                     AND c.entity_id IS NOT NULL""", (snap, save_id))
            appended = True
        if not have["market_stat"]:
            conn.execute(
                """INSERT INTO market_stat
                   SELECT ?, COALESCE(c.sector_macro, ''), o.ware, o.side,
                          COUNT(*), SUM(o.amount), MIN(o.price_cr),
                          AVG(o.price_cr), MAX(o.price_cr)
                   FROM trade_offer o
                   LEFT JOIN component c
                     ON c.save_id = o.save_id AND c.id = o.object_id
                   WHERE o.save_id = ?
                   GROUP BY 2, 3, 4""", (snap, save_id))
            appended = True
    if not appended:
        log("Trend rows already recorded for this snapshot; append skipped")
    return appended


# ---- entity registry (E: surrogate identity across snapshots) ---------------

_ENTITY_CLASSES = ("station", "buildstorage")


def _entity_domain(clazz: str) -> bool:
    return clazz.startswith("ship_") or clazz in _ENTITY_CLASSES


def update_entity_registry(conn: sqlite3.Connection, save: SaveData,
                           ref: RefData | None = None) -> dict[str, int]:
    """Resolve this snapshot's ships/stations/buildstorages against the
    entity registry and return component id -> entity_id.

    Identity is the surrogate entity_id; the game's own fields are only
    matching evidence (codes are recycled after death, owner changes on
    capture, names on rename — see the entity DDL). Matching: within the
    (code, class) slot, an equal spawntime is the same physical entity —
    an owner/name difference is then a capture/rename recorded in
    entity_event, never a new entity. A different spawntime is a new
    generation: mint a new entity; the unmatched predecessor is closed as
    'recycled'. Open entities absent from the snapshot close as
    'disappeared'. A closed entity whose exact (code, class, spawntime)
    reappears is reopened, not duplicated — components drift in and out of
    the universe tree (frames.universe's @connection filter), so identity
    deliberately ignores placement and registers connectionless components
    too. Idempotent for the same save; snapshots older than the registry
    high-water mark are resolved READ-ONLY — the matching still returns a
    mapping (a historic snapshot's components stamp their entity_ids, the
    archive seeding relies on it), but nothing is minted, closed or
    updated: lifecycle edits from stale observations would corrupt newer
    history. Components a read-only pass cannot match (entities that died
    unobserved before the history began) stay unmapped.
    """
    t = save.game_time

    readonly = False
    prev = conn.execute("SELECT value FROM meta"
                        " WHERE key = 'entity_registry_time'").fetchone()
    if prev is not None and t < float(prev[0]):
        log("NOTE: save predates the entity registry's newest snapshot; "
            "resolving entities read-only (no registry updates)")
        readonly = True

    def resolve(name):
        if ref is not None and name and "{" in name:
            return ref.resolve_name(name)
        return _s(name)

    # open entities indexed by (code, class) slot; closed ones by the full
    # evidence triple — an exact reappearance reopens instead of duplicating
    slots: dict[tuple, list] = {}
    closed: dict[tuple, list] = {}
    for row in conn.execute(
            "SELECT entity_id, code, class, macro, spawntime, owner, name,"
            " gone_time FROM entity ORDER BY last_seen, entity_id"):
        if row[7] is None:
            slots.setdefault((row[1], row[2]), []).append(list(row))
        else:
            closed.setdefault((row[1], row[2], row[4]), []).append(list(row))

    mapping: dict[str, int] = {}
    claimed: set[int] = set()
    minted_slots: set[tuple] = set()
    new_rows: list[tuple] = []       # (cid, code, class, macro, spawn, owner, name)
    updates: list[tuple] = []        # matched entity ids -> last_seen = t
    reopened: list[tuple] = []       # resurrected entity ids
    events: list[tuple] = []         # (entity_id, t, event, old, new)
    field_updates: list[tuple] = []  # (owner, name, entity_id)

    for c in save.components:
        # (id, class, macro, name, code, owner, knownto, contested,
        #  connection, spawntime, ...) — unlike the component table there is
        # no @connection filter: identity is about the physical object, and
        # real ships drift in and out of the universe tree between saves
        cid, clazz, code = c[0], c[1], _s(c[4])
        if not (code and _entity_domain(clazz)):
            continue
        macro, owner = _low(c[2]), _s(c[5])
        name, spawn = resolve(c[3]), _f(c[9])

        # several live same-slot candidates can exist (cross-faction code
        # collisions in long games): prefer matching macro, then owner;
        # entity_id order breaks remaining ties deterministically
        best = None
        for cand in slots.get((code, clazz), ()):
            if cand[0] in claimed or cand[4] != spawn:
                continue
            if best is None or \
                    (cand[3] == macro, cand[5] == owner) > \
                    (best[3] == macro, best[5] == owner):
                best = cand
        if best is None:
            # most recently seen resurrect-able match (list is in
            # last_seen order)
            for cand in reversed(closed.get((code, clazz, spawn), ())):
                if cand[0] not in claimed:
                    best = cand
                    reopened.append((t, cand[0]))
                    break
        if best is not None:
            eid = best[0]
            claimed.add(eid)
            mapping[cid] = eid
            updates.append((t, eid))
            if best[5] != owner:
                events.append((eid, t, "captured", best[5], owner))
            if best[6] != name:
                events.append((eid, t, "renamed", best[6], name))
            if best[5] != owner or best[6] != name:
                field_updates.append((owner, name, eid))
        else:
            minted_slots.add((code, clazz))
            new_rows.append((cid, code, clazz, macro, spawn, owner, name))

    if readonly:
        # matching evidence only: a historic snapshot must not mint
        # entities, edit lifecycle fields, or move the high-water mark —
        # the "captures"/"renames" it sees are just old values of state
        # the registry already tracks
        return mapping

    with conn:
        for cid, code, clazz, macro, spawn, owner, name in new_rows:
            cur = conn.execute(
                "INSERT INTO entity (code, class, macro, spawntime, owner,"
                " name, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
                (code, clazz, macro, spawn, owner, name, t, t))
            mapping[cid] = cur.lastrowid
        conn.executemany(
            "UPDATE entity SET last_seen = ? WHERE entity_id = ?", updates)
        conn.executemany(
            "UPDATE entity SET last_seen = ?, gone_time = NULL,"
            " gone_reason = NULL WHERE entity_id = ?", reopened)
        conn.executemany(
            "UPDATE entity SET owner = ?, name = ? WHERE entity_id = ?",
            field_updates)
        conn.executemany(
            "INSERT INTO entity_event VALUES (?,?,?,?,?)", events)
        # unmatched open entities are gone: their code either resurfaced on
        # a new generation (recycled) or vanished with them (disappeared —
        # destroyed, sold or despawned; snapshots cannot tell which)
        gone = [(t, "recycled" if (e[1], e[2]) in minted_slots
                 else "disappeared", e[0])
                for entities in slots.values() for e in entities
                if e[0] not in claimed]
        conn.executemany(
            "UPDATE entity SET gone_time = ?, gone_reason = ?"
            " WHERE entity_id = ?", gone)
        conn.execute("INSERT OR REPLACE INTO meta VALUES "
                     "('entity_registry_time', ?)", (str(t),))
    return mapping


# ---- event history (E: merged across runs, replaces the csv.gz caches) -----

def merge_events(conn: sqlite3.Connection, save: SaveData,
                 ref: RefData | None = None, stypes: dict | None = None,
                 entities: dict[str, int] | None = None) -> None:
    """Merge the save's rolling log/economylog windows into the event
    tables (semantics originally ported from the retired csv cache layer;
    one transaction per table, so a crash never half-merges; running twice
    on the same save is a no-op):

    - log_entry: per category, cached entries at or after that category's
      oldest new timestamp are replaced by the new window.
    - trade_tx/stock_event/money_event: cached entries newer than the
      oldest new timestamp are replaced (the new window is authoritative
      from there).
    - removed_object: cumulative catalog, append unseen objects.

    Trade parties are resolved to their save-stable, display-ready
    identity (faction, code, name) here, at merge time — the game remaps
    every runtime id on load, so a window's ids are unambiguous only
    against the save they came from. `stypes` (station id -> display type,
    see frames.station_types) feeds the unnamed-station fallback. Player
    subordinates additionally record the commander they traded for.
    `entities` (component id -> entity_id, from update_entity_registry)
    additionally stamps rows with the surrogate entity identity; parties
    it does not cover get NULL.

    High-water guard (mirrors update_entity_registry's): a save OLDER
    than the merged history is skipped whole, with a warning — its
    windows would otherwise DELETE every stored row newer than their
    start and replace it with the shorter, older window (measured on a
    real DB: one stale merge destroyed 606 trade_tx / 29,063 stock_event
    / 244 log_entry rows). A save with no game_time (synthetic test
    data) cannot be judged and merges normally.
    """
    t = save.game_time
    if t:
        high = _merge_high_water(conn)
        if high is not None and t < high:
            log(f"WARNING: save (game time {t:.0f}) predates the stored "
                f"event history (high-water mark {high:.0f}); event merge "
                "skipped — an older window would destroy newer history")
            return
    ident = _identities(save, ref, stypes or {})
    # commander map for trade attribution: the fleet resolution
    # write_snapshot just stored, player-filtered (v_player_fleet) — the
    # ONE fleet resolution in the pipeline (T8; snapshots always precede
    # merges). Edges touching connectionless components are absent from
    # the view; the retired save-side resolver (_player_edges) kept them
    # — measured equivalent on the real DBs and pinned in
    # tests/test_views_parity.py (plan-F10).
    edges = dict(conn.execute(
        "SELECT follower_id, commander_id FROM v_player_fleet"))
    _merge_log(conn, save.log_entries)
    _merge_trades(conn, save, ident, edges, entities or {})
    _merge_removed(conn, save.removed_objects)
    if t:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES"
                         " ('merge_events_time', ?)", (str(t),))


def _merge_high_water(conn: sqlite3.Connection) -> float | None:
    """Newest game time the event history is authoritative for: the game
    time of the last merged save (meta) — falling back, for DBs whose
    history predates the guard, to the newest stored event time (a lower
    bound: events never postdate their save)."""
    row = conn.execute("SELECT value FROM meta"
                       " WHERE key = 'merge_events_time'").fetchone()
    if row is not None:
        return float(row[0])
    times = [conn.execute(f"SELECT MAX(time) FROM {table}").fetchone()[0]
             for table in ("trade_tx", "stock_event", "money_event",
                           "log_entry")]
    times = [t for t in times if t is not None]
    return max(times) if times else None


def _update_coverage(conn: sqlite3.Connection, stream: str, epoch: int,
                     t_min: float, t_max: float,
                     window_start: float) -> None:
    """Extend (or open) a stream's coverage row for this merge; the
    caller's transaction. updated_save_id = the current import (the
    newest save row — merges run right after write_snapshot)."""
    conn.execute(
        "INSERT INTO coverage VALUES (?,?,?,?,?,"
        " (SELECT MAX(save_id) FROM save))"
        " ON CONFLICT(stream, epoch) DO UPDATE SET"
        "  t_min = MIN(t_min, excluded.t_min),"
        "  t_max = MAX(t_max, excluded.t_max),"
        "  window_start = excluded.window_start,"
        "  updated_save_id = excluded.updated_save_id",
        (stream, epoch, t_min, t_max, window_start))


def _identities(save: SaveData, ref: RefData | None, stypes: dict) -> dict:
    """Component id -> display-ready (faction, code, name) from this save's
    universe and removed-objects catalog. Nameless objects get the same
    fallback the R-era tradelog used: player ships their model, everything
    else "<SHORT> <model|station type|Station>"."""
    model_map = (dict(zip(ref.ships["macro"], ref.ships["model"]))
                 if ref is not None else {})
    faction_short = ref.faction_short if ref is not None else {}

    def resolve(name):
        if ref is not None and name and "{" in name:
            return ref.resolve_name(name)
        return _s(name)

    def display(name, cid, clazz, macro, owner):
        if name:
            return name
        model = model_map.get(macro) if clazz.startswith("ship_") else None
        if owner == "player" and clazz.startswith("ship_"):
            return model or macro or None
        base = model or stypes.get(cid) or "Station"
        short = faction_short.get(owner, OTHER_FACTION)
        return f"{short} {base}"

    ident: dict[str, tuple] = {}
    for c in save.components:
        # (id, class, macro, name, code, owner, ...)
        cid, clazz, macro = c[0], c[1], (c[2] or "").lower()
        ident[cid] = (_s(c[5]), _s(c[4]),
                      display(resolve(c[3]), cid, clazz, macro, c[5]))
    for o in save.removed_objects:
        oid = o.get("id")
        if oid and oid not in ident:
            owner = _s(o.get("owner"))
            name = resolve(o.get("name"))
            if not name:
                name = f"{faction_short.get(owner, OTHER_FACTION)} Station"
            ident[oid] = (owner, _s(o.get("code")), name)
    return ident


def _cents(v) -> float | None:
    f = _f(v)
    return f / 100.0 if f is not None else None


def _time_of(e: dict) -> float | None:
    """Merge windows are keyed on time: an entry without a parseable time
    cannot participate (and coercing it to 0 would collapse the window's
    cutoff to 0, wiping the entire preserved history). Skip it."""
    return _f(e.get("time"))


def _merge_log(conn: sqlite3.Connection, entries: list[dict]) -> None:
    rows = list(dict.fromkeys(  # dedupe on the full natural row
        (_time_of(e), _s(e.get("category")), _s(e.get("title")),
         _s(e.get("text")), _s(e.get("faction")), _cents(e.get("money")),
         _s(e.get("interact")), _s(e.get("component")),
         _s(e.get("highlighted")), json.dumps(e, sort_keys=True))
        for e in entries if _time_of(e) is not None))
    if not rows:
        return
    mintime: dict = {}
    maxtime: dict = {}
    for r in rows:
        t, cat = r[0], r[1]
        if cat not in mintime or t < mintime[cat]:
            mintime[cat] = t
        if cat not in maxtime or t > maxtime[cat]:
            maxtime[cat] = t
    with conn:
        for cat, mt in mintime.items():
            # per-category coverage: log_entry has no epoch column, so
            # gap-awareness lives at the coverage level — a window that
            # starts past everything stored for its category opens a new
            # coverage epoch instead of extending the old one
            prev_max = conn.execute(
                "SELECT MAX(time) FROM log_entry WHERE category IS ?",
                (cat,)).fetchone()[0]
            gap = prev_max is not None and mt > prev_max
            conn.execute(
                "DELETE FROM log_entry WHERE category IS ? AND time >= ?",
                (cat, mt))
            stream = f"log:{cat or ''}"
            prev_epoch = conn.execute(
                "SELECT MAX(epoch) FROM coverage WHERE stream = ?",
                (stream,)).fetchone()[0]
            epoch = (0 if prev_epoch is None
                     else prev_epoch + 1 if gap else prev_epoch)
            _update_coverage(conn, stream, epoch, mt, maxtime[cat], mt)
        conn.executemany(
            "INSERT INTO log_entry VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


_TX_COLS = ("time", "ware", "buyer_id", "seller_id", "price_cr", "amount",
            "raw_attrs", "buyer_faction", "buyer_code", "buyer_name",
            "seller_faction", "seller_code", "seller_name",
            "buyer_cmdr_id", "buyer_cmdr_name", "buyer_cmdr_code",
            "seller_cmdr_id", "seller_cmdr_name", "seller_cmdr_code",
            "buyer_entity", "seller_entity",
            "buyer_cmdr_entity", "seller_cmdr_entity", "kind")
_STOCK_COLS = ("time", "owner_id", "ware", "level", "raw_attrs",
               "owner_faction", "owner_code", "owner_name", "owner_entity")
_MONEY_COLS = ("time", "owner_id", "partner_id", "kind", "tradeentry",
               "value_cr", "raw_attrs", "owner_faction", "owner_code",
               "owner_name", "partner_faction", "partner_code",
               "partner_name", "owner_entity", "partner_entity")


def _merge_trades(conn: sqlite3.Connection, save: SaveData,
                  ident: dict, edges: dict, entities: dict) -> None:
    # each economylog ledger is typed by its wrapper block (plan T15 /
    # review B1), and the parser collected them per block:
    # - save.trades (trade block): real transactions (type="trade", price
    #   in cents, v = traded amount) and player-internal transfers
    #   (type="transfer", no price) -> trade_tx, told apart by `kind`
    # - save.stock_logs (cargo block, type="trade" only): the owner's
    #   stock level after a trade touched that ware -> stock_event
    # - save.money_logs (money block): the player's per-object money
    #   ledger (v in cents; tradeentry = 1-based ordinal into the trade
    #   ledger) -> money_event
    nobody = (None, None, None)

    def cmdr(party_id):
        """(id, name, code) of the commander a player subordinate traded
        for — the hierarchy at save time, like the retired csv baked in."""
        leader = edges.get(party_id)
        if leader is None:
            return nobody
        faction, code, name = ident.get(leader, nobody)
        return (leader, name, code)

    def cmdr_entity(party_id):
        leader = edges.get(party_id)
        return entities.get(leader) if leader is not None else None

    tx, stock, money = [], [], []
    for t in save.trades:
        time = _time_of(t)
        if time is None or not (t.get("buyer") and t.get("seller")):
            continue
        tx.append((time, t.get("ware") or "", _s(t.get("buyer")),
                   _s(t.get("seller")), _cents(t.get("price")),
                   _f(t.get("v")), json.dumps(t, sort_keys=True),
                   *ident.get(t["buyer"], nobody),
                   *ident.get(t["seller"], nobody),
                   *cmdr(t["buyer"]), *cmdr(t["seller"]),
                   entities.get(t["buyer"]), entities.get(t["seller"]),
                   cmdr_entity(t["buyer"]), cmdr_entity(t["seller"]),
                   _s(t.get("type")) or "trade"))
    for s in save.stock_logs:
        time = _time_of(s)
        if time is None or not s.get("owner"):
            continue
        # absent v means an empty stock, not unknown (the game omits
        # default attrs; confirmed 2,591/2,591 against same-save <cargo>);
        # NULL would punch holes into the LAG deltas
        stock.append((time, s["owner"], s.get("ware") or "",
                      _f(s.get("v")) or 0.0, json.dumps(s, sort_keys=True),
                      *ident.get(s["owner"], nobody),
                      entities.get(s["owner"])))
    for m in save.money_logs:
        time = _time_of(m)
        if time is None or not m.get("owner"):
            continue
        partner = _s(m.get("partner"))
        # continuously-filled entries are amended in place with a second
        # point (t2, v2): v2 is the latest value; raw_attrs keeps both
        money.append((time, m["owner"], partner,
                      _s(m.get("type")), _i(m.get("tradeentry")),
                      _cents(m.get("v2") if m.get("v2") is not None
                             else m.get("v")),
                      json.dumps(m, sort_keys=True),
                      *ident.get(m["owner"], nobody),
                      *(ident.get(partner, nobody) if partner else nobody),
                      entities.get(m["owner"]), entities.get(partner)))

    _merge_window(conn, "trade_tx", tx, _TX_COLS)
    _merge_window(conn, "stock_event", stock, _STOCK_COLS)
    _merge_window(conn, "money_event", money, _MONEY_COLS)


def _merge_window(conn: sqlite3.Connection, table: str,
                  rows: list[tuple], cols: tuple[str, ...]) -> None:
    # Rows can't dedupe on their natural identity across runs (component ids
    # drift between saves), so replace at the window boundary instead of
    # matching rows: everything newer than mintime is authoritative from the
    # new window. At exactly mintime, replace the cached rows only when the
    # new window has at least as many (then it is a superset in content and
    # carries the current save's ids, like the csv cache's keep-last dedupe);
    # when it has fewer, the game dropped same-timestamp siblings the cache
    # still knows — keep the cached rows, they are the history this table
    # exists to preserve.
    if not rows:
        return
    mintime = min(r[0] for r in rows)
    maxtime = max(r[0] for r in rows)
    boundary = [r for r in rows if r[0] == mintime]
    with conn:
        # coverage epoch: the rolling window is a global time suffix, so if
        # the new window starts after everything stored, the game discarded
        # events in between — v_stock_delta must not LAG across that gap
        prev_max, prev_epoch = conn.execute(
            f"SELECT MAX(time), MAX(epoch) FROM {table}").fetchone()
        epoch = (prev_epoch or 0) + (
            1 if prev_max is not None and mintime > prev_max else 0)
        rows = [r + (epoch,) for r in rows]
        ph = ",".join("?" * len(rows[0]))

        cached_at_boundary = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE time = ?", (mintime,)
        ).fetchone()[0]
        if len(boundary) >= cached_at_boundary:
            conn.execute(f"DELETE FROM {table} WHERE time >= ?", (mintime,))
        else:
            conn.execute(f"DELETE FROM {table} WHERE time > ?", (mintime,))
            rows = [r for r in rows if r[0] > mintime]
        # explicit column list: migrated tables carry ALTER-appended
        # columns in a different physical order than a fresh CREATE
        conn.executemany(
            f"INSERT INTO {table} ({','.join(cols)}, epoch)"
            f" VALUES ({ph})", rows)
        # coverage row for this stream's current epoch (the window's full
        # extent, before any boundary thinning above). Its window_start
        # carries the current window's extent for the dashboards' rate
        # math — merged history would otherwise dilute every Cr/h
        # denominator. (Supersedes the retired meta *_window_start keys,
        # plan T3/M4.)
        _update_coverage(conn, table, epoch, mintime, maxtime, mintime)


def _merge_removed(conn: sqlite3.Connection, objects: list[dict]) -> None:
    rows = [(_f(o.get("time")), _s(o.get("id")), _s(o.get("name")),
             _s(o.get("code")), _s(o.get("owner")),
             json.dumps(o, sort_keys=True))
            for o in objects]
    with conn:
        # first_save_id = the current import (merges run right after
        # write_snapshot): arrival provenance for new graveyard rows,
        # their only obtainable timestamp (T13). Existing rows are never
        # restamped — the row's first arrival is the point.
        conn.executemany(
            "INSERT INTO removed_object"
            " (time, id, name, code, owner, raw_attrs, first_save_id)"
            " SELECT ?,?,?,?,?,?, (SELECT MAX(save_id) FROM save)"
            " WHERE NOT EXISTS"
            " (SELECT 1 FROM removed_object"
            "  WHERE id IS ? AND name IS ? AND code IS ? AND owner IS ?)",
            [r + (r[1], r[2], r[3], r[4]) for r in rows])


# ---- one-time import of the retired csv.gz caches ---------------------------

def import_legacy_caches(conn: sqlite3.Connection, cfg: Config, guid: str,
                         ref: RefData) -> None:
    """Import the retired csv cache files' history: rows older than
    anything the event tables cover (the overlap was dual-written while
    both stores existed and is already present, in richer form). Runs once
    per database (meta flag); the csv files themselves are left on disk
    untouched — they are the only backup of this history.
    """
    if conn.execute("SELECT 1 FROM meta WHERE key = 'csv_caches_imported'"
                    ).fetchone():
        return
    n_log = _import_log_cache(
        conn, _read_legacy(cfg.data_dir / f"cache_log_{guid}.csv"))
    n_tx = _import_tradelog_cache(
        conn, _read_legacy(cfg.data_dir / f"cache_tradelog_{guid}.csv"), ref)
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES"
                     " ('csv_caches_imported', '1')")
    if n_log or n_tx:
        log(f"Imported legacy csv cache history: {n_log} log entries, "
            f"{n_tx} trades")


def _read_legacy(base: Path) -> list[dict] | None:
    """Rows as plain dicts with None for empty cells — NaN would slip
    through the ""/None guards in _s/_f and defeat the cutoff lookups."""
    for p in (base.with_suffix(".csv.gz"), base):
        if p.exists():
            df = pd.read_csv(p, sep="\t", dtype=str)
            return [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                    for row in df.to_dict("records")]
    return None


def _import_log_cache(conn: sqlite3.Connection,
                      records: list[dict] | None) -> int:
    if not records:
        return 0
    # only rows from before the event table's coverage; the csv kept a
    # filtered subset, so within the overlap the table is authoritative
    cutoffs = dict(conn.execute(
        "SELECT category, MIN(time) FROM log_entry GROUP BY category"))
    rows = []
    for r in records:
        t = _f(r.get("time"))
        if t is None:
            continue
        cat = _s(r.get("category"))
        cut = cutoffs.get(cat)
        if cut is not None and t >= cut:
            continue
        rows.append((t, cat, _s(r.get("title")), _s(r.get("text")), None,
                     _cents(r.get("money")), None, _s(r.get("component")),
                     None, None))
    with conn:
        conn.executemany(
            "INSERT INTO log_entry (time, category, title, text, faction,"
            " money_cr, interact, component_id, highlighted, raw_attrs)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _import_tradelog_cache(conn: sqlite3.Connection,
                           records: list[dict] | None, ref: RefData) -> int:
    if not records:
        return 0
    cut = conn.execute("SELECT MIN(time) FROM trade_tx").fetchone()
    cutoff = cut[0] if cut else None
    ware_by_name = {v: k for k, v in ref.ware_name.items()}
    faction_by_short = {v: k for k, v in ref.faction_short.items()}

    rows = []
    for r in records:
        t = _f(r.get("time"))
        if t is None or (cutoff is not None and t >= cutoff):
            continue

        def party(side):
            """csv rows are post-redirect: main columns hold the commander
            when a proxy executed the trade. -> (faction_id, executor(id,
            name, code), commander(id, name, code))."""
            faction = faction_by_short.get(_s(r.get(f"{side}.faction")))
            main = (_s(r.get(f"{side}.id")), _s(r.get(f"{side}.name")),
                    _s(r.get(f"{side}.code")))
            proxy_id = _s(r.get(f"{side}.proxy.id"))
            if proxy_id:
                executor = (proxy_id, _s(r.get(f"{side}.proxy.name")),
                            _s(r.get(f"{side}.proxy.code")))
                return faction, executor, main
            return faction, main, (None, None, None)

        b_fac, b_exec, b_cmdr = party("buyer")
        s_fac, s_exec, s_cmdr = party("seller")
        commodity = _s(r.get("commodity"))
        rows.append((
            t, ware_by_name.get(commodity, commodity) or "",
            b_exec[0], s_exec[0], _f(r.get("price")), _f(r.get("amount")),
            None,
            b_fac, b_exec[2], b_exec[1],
            s_fac, s_exec[2], s_exec[1],
            *b_cmdr, *s_cmdr,
            None, None, None, None,  # entity ids: unresolvable for csv rows
            "trade",  # the csv tradelog cached real transactions only
            0,  # epoch: pre-DB history, one continuous csv timeline
        ))
    with conn:
        conn.executemany(
            f"INSERT INTO trade_tx ({','.join(_TX_COLS)}, epoch)"
            f" VALUES ({','.join('?' * (len(_TX_COLS) + 1))})", rows)
    return len(rows)


# ---- derived tables (D: logparse output, rebuilt every run) -----------------

_CONSTRUCTION_KINDS = {
    "Ship construction": "construct",
    "Ship repair": "repair",
    "Ship resupply": "resupply",
}


def write_derived(conn: sqlite3.Connection, frames) -> None:
    """Materialize the logparse frames so SQL sees them (cheap to rebuild,
    English-wording regexes stay in Python). `frames` is frames.Frames."""
    def code_of(v):
        m = _CODE_RE.search(v) if isinstance(v, str) else None
        return m.group(0) if m else None

    destroyed = [
        (_pdval(r["time"]), _pdval(r["object"]), code_of(r["object"]),
         _pdval(r["killer"]), _pdval(r["location"]))
        for _, r in frames.destroyed.iterrows()]
    construction = [
        (_pdval(r["time"]), _pdval(r["buyer.name"]), _pdval(r["buyer.code"]),
         _pdval(r["seller.name"]), _CONSTRUCTION_KINDS[r["commodity"]])
        for _, r in frames.sales.iterrows()
        if r["commodity"] in _CONSTRUCTION_KINDS]
    transfers = [
        (_pdval(r["time"]), _pdval(r["money"]), _pdval(r["station.name"]))
        for _, r in frames.transfers.iterrows()]
    pirates = [(_pdval(r["time"]), _pdval(r["sector.macro"]))
               for _, r in frames.pirates.iterrows()]
    police = [(_pdval(r["time"]), _pdval(r["police.faction"]),
               _pdval(r["sector.macro"]))
              for _, r in frames.police.iterrows()]

    with conn:
        for table in schema.DERIVED_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO event_destroyed VALUES (?,?,?,?,?)", destroyed)
        conn.executemany(
            "INSERT INTO event_construction VALUES (?,?,?,?,?)", construction)
        conn.executemany(
            "INSERT INTO event_transfer VALUES (?,?,?)", transfers)
        conn.executemany("INSERT INTO event_pirate VALUES (?,?)", pirates)
        conn.executemany("INSERT INTO event_police VALUES (?,?,?)", police)


_STATION_STORAGE_COLS = ["station_id", "ware", "transport", "role",
                         "throughput", "max_units", "max_volume", "source"]


def write_station_storage(conn: sqlite3.Connection, save_id: int,
                          df: pd.DataFrame) -> None:
    """Persist the storage-allocation model (analysis.storage.station_storage).
    Rebuilt every run — the reverse-engineered model is cheap to recompute."""
    rows = [(save_id, *r)
            for r in _df_rows(df, _STATION_STORAGE_COLS)]
    with conn:
        conn.execute("DELETE FROM station_storage")
        conn.executemany(
            "INSERT INTO station_storage VALUES (?,?,?,?,?,?,?,?,?)", rows)


_STATION_MUNITION_COLS = ["station_id", "macro", "category", "is_unit",
                          "count", "capacity_floor"]


def write_station_munition(conn: sqlite3.Connection, save_id: int,
                           df: pd.DataFrame) -> None:
    """Persist the station munition census (analysis.drones.station_munition).
    Rebuilt every run from the save's <ammunition> + module unit storage."""
    rows = [(save_id, *r)
            for r in _df_rows(df, _STATION_MUNITION_COLS)]
    with conn:
        conn.execute("DELETE FROM station_munition")
        conn.executemany(
            "INSERT INTO station_munition VALUES (?,?,?,?,?,?,?)", rows)
