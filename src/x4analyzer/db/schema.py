"""SQLite schema for the analysis database (docs/sqlite-schema.md).

Every table is one of four scoping classes:

- **W** world state: rebuilt per snapshot, rows carry ``save_id``.
- **E** event history: merged across runs (the csv.gz cache semantics);
  survives rebuilds and schema resets, never dropped.
- **R** reference: game data from extract-gamedata, replaced wholesale.
- **D** derived: logparse regex output, rebuilt every run.

Conventions (from the schema doc): absent XML attributes are NULL, not "";
money is credits (``_cr``, save stores cents); macros/ids lowercased; TEXT
everywhere identifiers appear and no FK enforcement, because modded saves
must load, never fail. FK comments are documentation only.
"""

from __future__ import annotations

SCHEMA_VERSION = "5"

# E tables survive schema resets; everything else is rebuildable from the
# save + game files and is dropped on a schema_version mismatch.
EVENT_TABLES = ("trade_tx", "stock_event", "log_entry", "removed_object",
                "entity", "entity_event")

# Event-history migrations: old version -> targeted ALTERs bringing the E
# tables to the next version (everything else is dropped and recreated).
# v2 adds save-stable identity + coverage epochs to the economylog tables:
# runtime component ids are remapped on every game load, so identity is
# resolvable only at merge time, and LAG deltas must not span stretches
# the game discarded between analyzed saves. New columns append at the
# END of the fresh DDL below so ALTERed and fresh tables line up.
EVENT_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "1": (
        "ALTER TABLE stock_event ADD COLUMN owner_faction TEXT",
        "ALTER TABLE stock_event ADD COLUMN owner_code TEXT",
        "ALTER TABLE stock_event ADD COLUMN owner_name TEXT",
        "ALTER TABLE stock_event ADD COLUMN epoch INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE trade_tx ADD COLUMN buyer_faction TEXT",
        "ALTER TABLE trade_tx ADD COLUMN buyer_code TEXT",
        "ALTER TABLE trade_tx ADD COLUMN buyer_name TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_faction TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_code TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_name TEXT",
        "ALTER TABLE trade_tx ADD COLUMN epoch INTEGER NOT NULL DEFAULT 0",
    ),
    # v3 adds merge-time commander attribution: buyer/seller stay the
    # actual executor, *_cmdr_* is the commander a player subordinate was
    # trading for (NULL otherwise). The csv tradelog cache baked this in
    # at parse time; storing it keeps the attribution across id drift.
    "2": (
        "ALTER TABLE trade_tx ADD COLUMN buyer_cmdr_id TEXT",
        "ALTER TABLE trade_tx ADD COLUMN buyer_cmdr_name TEXT",
        "ALTER TABLE trade_tx ADD COLUMN buyer_cmdr_code TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_cmdr_id TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_cmdr_name TEXT",
        "ALTER TABLE trade_tx ADD COLUMN seller_cmdr_code TEXT",
    ),
    # v4 links event rows to the entity registry: *_entity columns carry
    # the surrogate entity_id resolved at merge time (NULL for rows merged
    # before the registry existed or parties absent from the snapshot).
    "3": (
        "ALTER TABLE trade_tx ADD COLUMN buyer_entity INTEGER",
        "ALTER TABLE trade_tx ADD COLUMN seller_entity INTEGER",
        "ALTER TABLE trade_tx ADD COLUMN buyer_cmdr_entity INTEGER",
        "ALTER TABLE trade_tx ADD COLUMN seller_cmdr_entity INTEGER",
        "ALTER TABLE stock_event ADD COLUMN owner_entity INTEGER",
    ),
}
NEXT_VERSION = {"1": "2", "2": "3", "3": "4"}

WORLD_TABLES = (
    "component", "fleet_edge", "module", "module_upgrade", "workforce",
    "npc", "npc_skill", "post", "people", "cargo", "trade_offer",
    "build_resource", "ship_order", "resource", "floating_ware",
    "datavault", "ship_engine",
)

REFERENCE_TABLES = (
    "ware", "recipe", "module_ref", "ship_ref", "faction", "cluster_ref",
    "sector_ref", "gate", "modcap", "text",
)

DERIVED_TABLES = (
    "event_destroyed", "event_construction", "event_transfer",
    "event_pirate", "event_police",
)

TABLES: dict[str, str] = {
    # ---- core dimension ----------------------------------------------------
    "meta": """CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
)""",
    "save": """CREATE TABLE IF NOT EXISTS save (
  save_id       INTEGER PRIMARY KEY,
  guid          TEXT NOT NULL,
  game_version  TEXT,
  game_time     REAL,
  save_date     TEXT,
  modified      INTEGER,
  player_name   TEXT,
  player_money_cr REAL,
  faction_name  TEXT,
  source_file   TEXT,
  imported_at   TEXT
)""",
    # ---- world state (W) ---------------------------------------------------
    "component": """CREATE TABLE IF NOT EXISTS component (
  save_id       INTEGER NOT NULL,
  id            TEXT NOT NULL,
  class         TEXT NOT NULL,
  macro         TEXT,
  name          TEXT,
  basename      TEXT,
  code          TEXT,
  owner         TEXT,
  knownto       TEXT,
  contested     INTEGER,
  spawntime     REAL,
  parent_id     TEXT,
  cluster_id    TEXT, cluster_macro TEXT,
  sector_id     TEXT, sector_macro  TEXT,
  sx            REAL,             -- sector-local position (stations/plots)
  sz            REAL,
  faction_hq    INTEGER,          -- factionheadquarters="1" on the station
  PRIMARY KEY (save_id, id)
)""",
    "fleet_edge": """CREATE TABLE IF NOT EXISTS fleet_edge (
  save_id      INTEGER NOT NULL,
  follower_id  TEXT NOT NULL,
  commander_id TEXT NOT NULL,
  PRIMARY KEY (save_id, follower_id)
)""",
    "module": """CREATE TABLE IF NOT EXISTS module (
  save_id      INTEGER NOT NULL,
  host_id      TEXT NOT NULL,
  entry_id     TEXT,
  idx          INTEGER,
  macro        TEXT,
  build_method TEXT,
  built        INTEGER NOT NULL
)""",
    "module_upgrade": """CREATE TABLE IF NOT EXISTS module_upgrade (
  save_id  INTEGER NOT NULL,
  entry_id TEXT NOT NULL,
  equipment_macro TEXT NOT NULL
)""",
    "workforce": """CREATE TABLE IF NOT EXISTS workforce (
  save_id    INTEGER NOT NULL,
  station_id TEXT NOT NULL,
  race       TEXT NOT NULL,
  amount     REAL,
  PRIMARY KEY (save_id, station_id, race)
)""",
    "npc": """CREATE TABLE IF NOT EXISTS npc (
  save_id INTEGER NOT NULL,
  id      TEXT NOT NULL,
  name    TEXT, code TEXT, owner TEXT,
  PRIMARY KEY (save_id, id)
)""",
    "npc_skill": """CREATE TABLE IF NOT EXISTS npc_skill (
  save_id INTEGER NOT NULL,
  npc_id  TEXT NOT NULL,
  skill   TEXT NOT NULL,
  value   REAL,
  PRIMARY KEY (save_id, npc_id, skill)
)""",
    "post": """CREATE TABLE IF NOT EXISTS post (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  post      TEXT NOT NULL,
  npc_id    TEXT
)""",
    "people": """CREATE TABLE IF NOT EXISTS people (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  role      TEXT NOT NULL,
  count     INTEGER NOT NULL,
  PRIMARY KEY (save_id, object_id, role)
)""",
    "cargo": """CREATE TABLE IF NOT EXISTS cargo (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  PRIMARY KEY (save_id, object_id, ware)
)""",
    "trade_offer": """CREATE TABLE IF NOT EXISTS trade_offer (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  side      TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  price_cr  REAL
)""",
    "build_resource": """CREATE TABLE IF NOT EXISTS build_resource (
  save_id INTEGER NOT NULL,
  host_id TEXT,
  ware    TEXT NOT NULL,
  amount  REAL,
  kind    TEXT NOT NULL
)""",
    "ship_order": """CREATE TABLE IF NOT EXISTS ship_order (
  save_id    INTEGER NOT NULL,
  object_id  TEXT NOT NULL,
  order_name TEXT NOT NULL,
  is_default INTEGER NOT NULL,
  state      TEXT
)""",
    "resource": """CREATE TABLE IF NOT EXISTS resource (
  save_id      INTEGER NOT NULL,
  sector_macro TEXT NOT NULL,
  ware         TEXT NOT NULL,
  yield        REAL
)""",
    "floating_ware": """CREATE TABLE IF NOT EXISTS floating_ware (
  save_id      INTEGER NOT NULL,
  sector_macro TEXT,
  ware         TEXT NOT NULL,
  amount       REAL
)""",
    # data vaults (regular landmarks_vault_* + Erlking): unlocked = the
    # vault has been opened; loot = collectable children still inside;
    # blueprints = blueprint macros still inside (Erlking, csv)
    "datavault": """CREATE TABLE IF NOT EXISTS datavault (
  save_id      INTEGER NOT NULL,
  object_id    TEXT NOT NULL,
  macro        TEXT NOT NULL,
  code         TEXT,
  knownto      TEXT,
  sector_macro TEXT,
  sx           REAL,
  sz           REAL,
  unlocked     INTEGER NOT NULL,
  loot         INTEGER NOT NULL,
  blueprints   TEXT,
  PRIMARY KEY (save_id, object_id)
)""",
    # equipped engines of PLAYER ships (speed-from-loadout for the trade
    # opportunity travel times); n = mounted count of that engine macro
    "ship_engine": """CREATE TABLE IF NOT EXISTS ship_engine (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  macro     TEXT NOT NULL,
  n         INTEGER NOT NULL,
  PRIMARY KEY (save_id, object_id, macro)
)""",
    # ---- event history (E) -------------------------------------------------
    # identity columns are resolved at merge time — the only moment the
    # window's runtime ids are unambiguous (the game remaps them on every
    # load); faction is the raw owner id, NULL when unresolvable. epoch
    # increments when a merged window does not overlap the stored history
    # (the game discarded events in between).
    "trade_tx": """CREATE TABLE IF NOT EXISTS trade_tx (
  time      REAL NOT NULL,
  ware      TEXT NOT NULL,
  buyer_id  TEXT,
  seller_id TEXT,
  price_cr  REAL,
  amount    REAL,
  raw_attrs TEXT,
  buyer_faction TEXT, buyer_code TEXT, buyer_name TEXT,
  seller_faction TEXT, seller_code TEXT, seller_name TEXT,
  epoch     INTEGER NOT NULL DEFAULT 0,
  buyer_cmdr_id TEXT, buyer_cmdr_name TEXT, buyer_cmdr_code TEXT,
  seller_cmdr_id TEXT, seller_cmdr_name TEXT, seller_cmdr_code TEXT,
  buyer_entity INTEGER, seller_entity INTEGER,
  buyer_cmdr_entity INTEGER, seller_cmdr_entity INTEGER
)""",
    "stock_event": """CREATE TABLE IF NOT EXISTS stock_event (
  time      REAL NOT NULL,
  owner_id  TEXT NOT NULL,
  ware      TEXT NOT NULL,
  level     REAL,
  raw_attrs TEXT,
  owner_faction TEXT, owner_code TEXT, owner_name TEXT,
  epoch     INTEGER NOT NULL DEFAULT 0,
  owner_entity INTEGER
)""",
    "log_entry": """CREATE TABLE IF NOT EXISTS log_entry (
  time        REAL NOT NULL,
  category    TEXT,
  title       TEXT,
  text        TEXT,
  faction     TEXT,
  money_cr    REAL,
  interaction TEXT,
  component_id TEXT,
  highlighted TEXT,
  raw_attrs   TEXT
)""",
    "removed_object": """CREATE TABLE IF NOT EXISTS removed_object (
  time  REAL,
  id    TEXT, name TEXT, code TEXT, owner TEXT,
  raw_attrs TEXT
)""",
    # entity registry: one row per physical ship/station/buildstorage ever
    # observed in a snapshot. entity_id is a surrogate key WE mint — the
    # game guarantees uniqueness for none of its own fields (codes are
    # recycled after death, owner changes on capture, names on rename, and
    # runtime ids remap every load). (code, class) is the slot, spawntime
    # the generation (0 = existed at world creation; only the first
    # generation of a slot can carry it). owner/name are the CURRENT
    # values; changes are recorded in entity_event. gone_time is the game
    # time of the first analyzed snapshot the entity was absent from
    # (death happened somewhere in [last_seen, gone_time]).
    "entity": """CREATE TABLE IF NOT EXISTS entity (
  entity_id  INTEGER PRIMARY KEY,
  code       TEXT NOT NULL,
  class      TEXT NOT NULL,
  macro      TEXT,
  spawntime  REAL,
  owner      TEXT,
  name       TEXT,
  first_seen REAL NOT NULL,
  last_seen  REAL NOT NULL,
  gone_time  REAL,
  gone_reason TEXT
)""",
    # observed identity changes on a living entity (capture, rename)
    "entity_event": """CREATE TABLE IF NOT EXISTS entity_event (
  entity_id INTEGER NOT NULL,
  time      REAL NOT NULL,
  event     TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT
)""",
    # ---- reference (R) -----------------------------------------------------
    "ware": """CREATE TABLE IF NOT EXISTS ware (
  id TEXT PRIMARY KEY, name TEXT, grp TEXT,
  transport TEXT,
  volume REAL,
  tags TEXT, price_avg REAL,
  component TEXT,
  source TEXT
)""",
    "recipe": """CREATE TABLE IF NOT EXISTS recipe (
  ware TEXT NOT NULL, method TEXT NOT NULL,
  time REAL, amount REAL,
  input_ware TEXT, input_amount REAL
)""",
    "module_ref": """CREATE TABLE IF NOT EXISTS module_ref (
  macro TEXT NOT NULL, name TEXT,
  ware TEXT, method TEXT,
  scale REAL,
  workforce REAL, source TEXT
)""",
    "ship_ref": """CREATE TABLE IF NOT EXISTS ship_ref (
  macro TEXT PRIMARY KEY, model TEXT, class TEXT, race TEXT,
  purpose TEXT, hull REAL, mass REAL, cargo REAL, crew REAL,
  price REAL, source TEXT
)""",
    "faction": """CREATE TABLE IF NOT EXISTS faction (
  id TEXT PRIMARY KEY, shortname TEXT, name TEXT,
  primaryrace TEXT, colour TEXT, source TEXT
)""",
    "cluster_ref": """CREATE TABLE IF NOT EXISTS cluster_ref (
  macro TEXT PRIMARY KEY, x REAL, y REAL, z REAL,
  name TEXT, description TEXT, source TEXT
)""",
    "sector_ref": """CREATE TABLE IF NOT EXISTS sector_ref (
  cluster TEXT, macro TEXT PRIMARY KEY,
  x REAL, y REAL, z REAL, name TEXT, source TEXT
)""",
    "gate": """CREATE TABLE IF NOT EXISTS gate (
  sector_a TEXT NOT NULL, sector_b TEXT NOT NULL, source TEXT
)""",
    "modcap": """CREATE TABLE IF NOT EXISTS modcap (
  macro TEXT PRIMARY KEY, class TEXT,
  housing REAL, workers REAL, cargo_max REAL, cargo_tags TEXT
)""",
    "text": """CREATE TABLE IF NOT EXISTS text (
  page INTEGER NOT NULL, tid INTEGER NOT NULL, text TEXT,
  PRIMARY KEY (page, tid)
)""",
    # ---- derived (D) -------------------------------------------------------
    "event_destroyed": """CREATE TABLE IF NOT EXISTS event_destroyed (
  time REAL, victim TEXT, victim_code TEXT,
  attacker TEXT, sector TEXT
)""",
    "event_construction": """CREATE TABLE IF NOT EXISTS event_construction (
  time REAL, ship TEXT, code TEXT,
  wharf TEXT, kind TEXT
)""",
    "event_transfer": """CREATE TABLE IF NOT EXISTS event_transfer (
  time REAL, money_cr REAL, station TEXT
)""",
    "event_pirate": """CREATE TABLE IF NOT EXISTS event_pirate (
  time REAL, sector_macro TEXT
)""",
    "event_police": """CREATE TABLE IF NOT EXISTS event_police (
  time REAL, faction TEXT, sector_macro TEXT
)""",
}

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_module_host ON module(save_id, host_id)",
    "CREATE INDEX IF NOT EXISTS idx_offer_ware ON trade_offer(save_id, ware)",
    "CREATE INDEX IF NOT EXISTS idx_tx_time ON trade_tx(time)",
    "CREATE INDEX IF NOT EXISTS idx_tx_ware ON trade_tx(ware)",
    "CREATE INDEX IF NOT EXISTS idx_stock ON stock_event(owner_id, ware, time)",
    "CREATE INDEX IF NOT EXISTS idx_log_time ON log_entry(category, time)",
    "CREATE INDEX IF NOT EXISTS idx_recipe ON recipe(ware, method)",
    "CREATE INDEX IF NOT EXISTS idx_entity_slot ON entity(code, class)",
    "CREATE INDEX IF NOT EXISTS idx_entity_event ON entity_event(entity_id)",
)

# The frames.py replacement layer. (Re)created at every connect so
# definition updates propagate; all filter to the current snapshot via
# MAX(save_id). Joins are LEFT JOINs — dangling references are normal
# (event history outlives objects; modded content references unknown ids).
VIEWS: dict[str, str] = {
    # resolved universe: names were resolved at load; adds sector display
    # name and faction shortname
    "v_universe": """CREATE VIEW v_universe AS
SELECT c.*, s.name AS sector_name, f.shortname AS owner_code
FROM component c
LEFT JOIN sector_ref s ON s.macro = c.sector_macro
LEFT JOIN faction f    ON f.id = c.owner
WHERE c.save_id = (SELECT MAX(save_id) FROM save)""",
    # transitive fleet membership
    "v_fleet": """CREATE VIEW v_fleet AS
WITH RECURSIVE chain(ship, cmdr, depth) AS (
  SELECT follower_id, commander_id, 1 FROM fleet_edge
   WHERE save_id = (SELECT MAX(save_id) FROM save)
  UNION ALL
  SELECT chain.ship, fe.commander_id, chain.depth + 1
  FROM chain JOIN fleet_edge fe ON fe.follower_id = chain.cmdr
   AND fe.save_id = (SELECT MAX(save_id) FROM save)
)
SELECT ship, cmdr, depth,
       depth = (SELECT MAX(depth) FROM chain c2 WHERE c2.ship = chain.ship)
         AS is_root_edge
FROM chain""",
    # market traded volume: positive stock deltas between consecutive
    # owner-only snapshots (level/dv_neg beyond the schema doc: frames'
    # Market actual-flows mode needs stock leaving the station too).
    # Rows without a ware carry no delta information.
    "v_stock_delta": """CREATE VIEW v_stock_delta AS
SELECT owner_id, owner_faction, owner_code, owner_name, ware, time, level,
       epoch,
       MAX(level - LAG(level) OVER w, 0) AS dv,
       MAX(LAG(level) OVER w - level, 0) AS dv_neg
FROM stock_event
WHERE ware != ''
WINDOW w AS (PARTITION BY COALESCE(owner_faction || '|' || owner_code,
                                   owner_id),
             ware, epoch ORDER BY time, rowid)""",
    # Partitioning by the save-stable identity heals a station's series
    # across game sessions (ids drift, faction|code doesn't; unresolvable
    # rows degrade to per-id, today's behavior); the epoch term stops LAG
    # from computing a delta across a coverage gap. rowid breaks time ties
    # in save order: stations log several stock levels within the same
    # second, and an arbitrary tie order would reshuffle which deltas
    # count as positive.
    # built modules only (measure reality, not plans — CLAUDE.md gotcha)
    "v_built_module": """CREATE VIEW v_built_module AS
SELECT * FROM module
WHERE built = 1 AND save_id = (SELECT MAX(save_id) FROM save)""",
    # wide NPC skills for the crew tables
    "v_npc": """CREATE VIEW v_npc AS
SELECT n.*,
  MAX(CASE WHEN s.skill='piloting'    THEN s.value END) AS piloting,
  MAX(CASE WHEN s.skill='engineering' THEN s.value END) AS engineering,
  MAX(CASE WHEN s.skill='boarding'    THEN s.value END) AS boarding,
  MAX(CASE WHEN s.skill='management'  THEN s.value END) AS management,
  MAX(CASE WHEN s.skill='morale'      THEN s.value END) AS morale
FROM npc n LEFT JOIN npc_skill s
  ON s.save_id = n.save_id AND s.npc_id = n.id
WHERE n.save_id = (SELECT MAX(save_id) FROM save)
GROUP BY n.save_id, n.id""",
}
