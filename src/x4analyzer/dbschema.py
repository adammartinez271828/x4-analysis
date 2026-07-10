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

SCHEMA_VERSION = "1"

# E tables survive schema resets; everything else is rebuildable from the
# save + game files and is dropped on a schema_version mismatch.
EVENT_TABLES = ("trade_tx", "stock_event", "log_entry", "removed_object")

WORLD_TABLES = (
    "component", "fleet_edge", "module", "module_upgrade", "workforce",
    "npc", "npc_skill", "post", "people", "cargo", "trade_offer",
    "build_resource", "ship_order", "resource", "floating_ware",
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
    # ---- event history (E) -------------------------------------------------
    "trade_tx": """CREATE TABLE IF NOT EXISTS trade_tx (
  time      REAL NOT NULL,
  ware      TEXT NOT NULL,
  buyer_id  TEXT,
  seller_id TEXT,
  price_cr  REAL,
  amount    REAL,
  raw_attrs TEXT
)""",
    "stock_event": """CREATE TABLE IF NOT EXISTS stock_event (
  time      REAL NOT NULL,
  owner_id  TEXT NOT NULL,
  ware      TEXT NOT NULL,
  level     REAL,
  raw_attrs TEXT
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
)

# (Re)created at every connect so definition updates propagate. Filled in
# migration phase 3 (views for frames.py).
VIEWS: dict[str, str] = {}
