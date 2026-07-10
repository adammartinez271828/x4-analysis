"""SQLite store: writes every parsed save record to x4_<guid>.sqlite.

The database (one per game GUID, in the user data dir next to the csv.gz
caches) is a rebuildable artifact derived from save + game files — EXCEPT
the event-history tables (dbschema.EVENT_TABLES), which preserve the
rolling log/economylog windows the game has already discarded and are never
dropped. Schema and conventions: docs/sqlite-schema.md.

Load rules worth calling out:
- "" from the parser becomes NULL (SQL predicates read better); macros are
  lowercased; money cents / 100 into *_cr columns.
- component rows with an empty @connection are not universe objects and are
  skipped, mirroring frames.universe's filter.
- {page,id} text refs in component names are resolved at load, so SQL
  consumers never see raw refs.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import dbschema
from .config import Config
from .refdata import RefData
from .saveparser import SaveData

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
    if version is not None and version != dbschema.SCHEMA_VERSION:
        # everything but event history is rebuilt from the save in seconds:
        # migration = drop and recreate (event tables would need real care)
        with conn:
            for name in dbschema.TABLES:
                if name not in dbschema.EVENT_TABLES:
                    conn.execute(f"DROP TABLE IF EXISTS {name}")
            for name in dbschema.VIEWS:
                conn.execute(f"DROP VIEW IF EXISTS {name}")
    with conn:
        for ddl in dbschema.TABLES.values():
            conn.execute(ddl)
        for ddl in dbschema.INDEXES:
            conn.execute(ddl)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                     (dbschema.SCHEMA_VERSION,))
        # views are recreated every connect so definition updates propagate
        for name, ddl in dbschema.VIEWS.items():
            conn.execute(f"DROP VIEW IF EXISTS {name}")
            conn.execute(ddl)


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


def _df_rows(df: pd.DataFrame, cols: list[str]) -> list[tuple]:
    if df is None or df.empty:
        return []
    sub = df.reindex(columns=cols)
    return [tuple(_pdval(v) for v in row)
            for row in sub.itertuples(index=False, name=None)]


# ---- reference data (R: replaced wholesale) ---------------------------------

def write_reference(conn: sqlite3.Connection, ref: RefData) -> None:
    loads = (
        ("ware", ref.wares.rename(columns={"group": "grp"}),
         ["id", "name", "grp", "transport", "volume", "tags", "price_avg",
          "component", "source"]),
        ("recipe", ref.recipes,
         ["ware", "method", "time", "amount", "input_ware", "input_amount"]),
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
        ("modcap", ref.modcaps,
         ["macro", "class", "housing", "workers", "cargo_max", "cargo_tags"]),
    )
    with conn:
        for table, df, cols in loads:
            conn.execute(f"DELETE FROM {table}")
            rows = _df_rows(df, cols)
            if rows:
                ph = ",".join("?" * len(cols))
                conn.executemany(
                    f"INSERT INTO {table} VALUES ({ph})", rows)
        conn.execute("DELETE FROM text")
        conn.executemany("INSERT INTO text VALUES (?,?,?)",
                         ref.textdb.items())


# ---- world state (W: one snapshot, replaced per import) ---------------------

def write_snapshot(conn: sqlite3.Connection, save: SaveData, ref: RefData,
                   source_file: Path | str) -> int:
    def resolve(name):
        if name and "{" in name:
            return ref.resolve_name(name)
        return _s(name)

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
        for table in dbschema.WORLD_TABLES:
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT INTO component VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(save_id, cid, clazz, _low(macro), resolve(name),
              resolve(basename), _s(code), _s(owner), _s(knownto),
              _i(contested), _f(spawntime),
              _s(parent_id), _s(cluster_id), _low(cluster_macro),
              _s(sector_id), _low(sector_macro))
             for (cid, clazz, macro, name, code, owner, knownto, contested,
                  connection, spawntime, cluster_id, cluster_macro, sector_id,
                  sector_macro, basename, parent_id) in save.components
             if connection])  # no @connection = not in the universe tree

        # fleet hierarchy, resolved once: follower's <connected> conn ref
        # matched to the commander's "subordinates" connection id
        leader_by_conn = {conn_id: leader
                          for leader, conn_id in save.subordinate_conns}
        edges: dict[str, str] = {}
        for follower, conn_ref in save.commander_links:
            leader = leader_by_conn.get(conn_ref)
            if leader and follower not in edges:
                edges[follower] = leader
        conn.executemany(
            "INSERT INTO fleet_edge VALUES (?,?,?)",
            [(save_id, follower, leader)
             for follower, leader in edges.items()])

        # stations list their build plan twice (construction sequence + the
        # expand queue repeat the same entry ids): count each entry once per
        # host. Entries without ids are all kept, and count as built the way
        # frames.built_modules keeps them defensively.
        built = set(save.built_refs)
        seen: set[tuple] = set()
        module_rows = []
        for host, idx, macro, entry, method in save.modules:
            if entry:
                if (host, entry) in seen:
                    continue
                seen.add((host, entry))
            module_rows.append(
                (save_id, host, _s(entry), idx, _low(macro), _s(method),
                 1 if (entry in built or not entry) else 0))
        conn.executemany(
            "INSERT INTO module VALUES (?,?,?,?,?,?,?)", module_rows)

        conn.executemany(
            "INSERT INTO module_upgrade VALUES (?,?,?)",
            [(save_id, entry, macro)
             for entry, macro in save.module_upgrades])

        wf: dict[tuple, float] = {}
        for station, race, amount in save.workforce:
            key = (station, race)
            wf[key] = wf.get(key, 0.0) + amount
        conn.executemany(
            "INSERT INTO workforce VALUES (?,?,?,?)",
            [(save_id, station, race, amount)
             for (station, race), amount in wf.items()])

        conn.executemany(
            "INSERT INTO npc VALUES (?,?,?,?,?)",
            [(save_id, nid, _s(name), _s(code), _s(owner))
             for nid, name, code, owner, _skills in save.npcs])
        conn.executemany(
            "INSERT INTO npc_skill VALUES (?,?,?,?)",
            [(save_id, nid, skill, value)
             for nid, _n, _c, _o, skills in save.npcs
             for skill, value in skills.items()])

        conn.executemany(
            "INSERT INTO post VALUES (?,?,?,?)",
            [(save_id, oid, post, _s(npc_id))
             for oid, post, npc_id in save.posts])

        conn.executemany(
            "INSERT INTO people VALUES (?,?,?,?)",
            [(save_id, oid, role, count)
             for (oid, role), count in save.people.items()])

        # a host may repeat a ware across storage components: sum per PK
        cg: dict[tuple, float] = {}
        for oid, ware, amount in save.cargo:
            key = (oid, ware)
            cg[key] = cg.get(key, 0.0) + amount
        conn.executemany(
            "INSERT INTO cargo VALUES (?,?,?,?)",
            [(save_id, oid, ware, amount)
             for (oid, ware), amount in cg.items()])

        conn.executemany(
            "INSERT INTO trade_offer VALUES (?,?,?,?,?,?)",
            [(save_id, _s(oid), side, ware, amount, price_cr)
             for oid, side, ware, amount, price_cr in save.trade_offers])

        conn.executemany(
            "INSERT INTO build_resource VALUES (?,?,?,?,?)",
            [(save_id, _s(host), ware, amount, kind)
             for host, ware, amount, kind in save.build_resources])

        conn.executemany(
            "INSERT INTO ship_order VALUES (?,?,?,?,?)",
            [(save_id, oid, order, int(is_default), _s(state))
             for oid, order, is_default, state in save.orders])

        conn.executemany(
            "INSERT INTO resource VALUES (?,?,?,?)",
            [(save_id, _low(sector), ware, yld)
             for sector, ware, yld in save.resources])

        conn.executemany(
            "INSERT INTO floating_ware VALUES (?,?,?,?)",
            [(save_id, _low(sector), ware, amount)
             for sector, ware, amount in save.floating_wares])

    return save_id


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
        for table in dbschema.DERIVED_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO event_destroyed VALUES (?,?,?,?,?)", destroyed)
        conn.executemany(
            "INSERT INTO event_construction VALUES (?,?,?,?,?)", construction)
        conn.executemany(
            "INSERT INTO event_transfer VALUES (?,?,?)", transfers)
        conn.executemany("INSERT INTO event_pirate VALUES (?,?)", pirates)
        conn.executemany("INSERT INTO event_police VALUES (?,?,?)", police)
