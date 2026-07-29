"""SQLite schema for the analysis database (docs/reference/db-schema.md).

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

import hashlib

# v6: resource rows carry the yieldid's level/speed tokens (replenishment)
# v7: resource rows carry per-area starttime (respawn-eligibility clock)
# v8: recipe.work_effect (workforce output bonus) + station_storage table
# v9: station_storage.source (computed model vs stock+buy proxy)
# v10: unit_storage drone slots on the module-capacity table (renamed
#      module_cap in v15) + station_munition table
# v11: component.entity_id (the entity spine: snapshot rows join the
#      registry directly) + W/E access-path indices
# v12: economylog ingestion typed by ledger (plan T15 / review B1):
#      money_event table, trade_tx.kind, money-block rows re-typed out of
#      stock_event
# v13: the trend layer (plan T4/T5): A-class aggregate-history tables
#      (sector_presence, station_metric, market_stat), appended once per
#      distinct snapshot, never dropped. (The roadmap penciled this phase
#      in as "v12" before T15 took that number.)
# v14: coverage backfill (plan T3/M4): historical event ranges filled
#      into the coverage table from the epoch-stamped E rows, and the
#      three meta *_window_start keys it supersedes retired (the merge
#      writes coverage.window_start instead)
# v15: naming/convention cleanups (plan T11): module -> build_entry (it
#      holds build-PLAN entries, the misnomer behind the 2x-capacity bug
#      class), modcap -> module_cap, faction_meta.account -> account_cr
#      (credits at load, the last raw-cents column), trade_offer.object_id
#      '' -> NULL (the last empty-string exception)
# v16: log_entry.interact fix (plan T12): the save's attribute is
#      `interact`, the loader read `interaction` — never populated; the
#      column is renamed to match the save and history is backfilled
#      from raw_attrs
# v17: migration-machinery hygiene (plan T13): the managed-table
#      inventory in meta('managed_tables') lets bumps drop tables a
#      newer version renamed or removed (zombies — retroactively drops
#      station_drones via the LEGACY_TABLES seed), and
#      removed_object.first_save_id records the import that first merged
#      each graveyard row (its only obtainable timestamp: the save-side
#      time attr does not exist in v9)
# v18: supply-offer discriminator (docs/reports/supply-offer-discriminator
#      .md): trade_offer.flags (the save's raw |-joined offer flags —
#      "supplies" marks station self-supply drone/munition-component buys)
#      + trade_offer.desired (wanted total); station_storage grows
#      role='supply' rows sourced from those offers, so its PK gains role
# v19: player_subscription (the player's trade-info subscriptions with
#      absolute expiry, from <memory><subscriptions>) + build_price_factor
#      (per-station <trade><prices buildpricefactor>, the deployable/ship
#      pricing M — drifts between saves, so per-save capture)
# v20: player knowledge + trade-block completions: player_scan (permanent
#      module scan levels, <memory><scan>), station_trade_setting
#      (trade-station buy/sell/lockavgprice ware whitelists),
#      trade_active (escrow-stage in-flight trades with transferred
#      units), component.known (the broad discovery flag next to knownto)
# v21: build method (which recipe variant gets built): faction_meta
#      .build_method (<faction><buildrules>) + build_method (per-station
#      <build method=> override). build_entry.build_method dropped — it
#      was never populated and its name invited confusion with these.
# v22: station self-supply bookkeeping (station_supply: <supplies><orders>
#      build targets + <wares> set-aside inputs) and manual per-ware price
#      overrides (price_override: <trade><prices><override>, whole credits)
# v23: price_override generalised to price_setting (kind reference|override
#      — <prices><reference> is the station's configured price, Layer 5 of
#      the pricing model) and ware_limit (<overrides>: the manual per-ware
#      stock/buy/sell limits set in the station UI)
# v24: ware_limit.amount — a missing amount= means 1 (the UI's floor for
#      stock/buy/sell limits), not NULL/0 as v23 assumed
# v25: ware.price_min / price_max — the economy price BAND, not just the
#      average (the supply curve interpolates between them by fill)
# v26: trade_pending supersedes trade_active — ALL committed in-flight
#      trades (the supply curve's `pending` term), merged from the two
#      places the save keeps each one; the escrow subset keeps its own
#      flag. trade_active dropped (it held 49 of these 2,510 rows).
# v27: module_production (live per-production-module state: queued ware,
#      <efficiency product=> runtime multiplier, state, module count)
# v28: module_upgrade.host_id — station build-sequence entry ids are unique
#      only PER STATION (2,235 of 22,562 ids in one save are shared, up to
#      33 stations on one id), so keying loadouts on the bare entry id
#      merged the plans of every station running the same design. The same
#      collision reached build_entry.built through the parser's flat
#      built_refs list: one station's FINISHED entry marked the same id
#      built on stations where it was still under construction (14 entries
#      across 11 stations), inventing capacity. Both are now keyed on
#      (host_id, entry_id).
SCHEMA_VERSION = "28"

# E tables survive schema resets; everything else is rebuildable from the
# save + game files and is dropped on a schema_version mismatch.
EVENT_TABLES = ("trade_tx", "stock_event", "money_event", "log_entry",
                "removed_object", "entity", "entity_event")

# P tables: persistent bookkeeping, never dropped on a version bump. save
# is the provenance log and the time dimension anything cross-run keys
# into (its ids must not recycle); meta carries cross-run flags that the
# bump path itself reads; coverage records what the event history covers.
# Their DDL is version-stable — if their shape ever must change, they
# migrate like E tables via EVENT_MIGRATIONS.
PERSISTENT_TABLES = ("save", "meta", "coverage")

# Former managed-table names from before the managed-table inventory
# existed (meta 'managed_tables', v17): pre-v17 DBs carry no inventory to
# consult, so the known zombies are seeded here and dropped on the next
# bump. Never list E/A/P names. (module/modcap need no entry: their
# rename's own migration drops them on the 14->15 step.)
LEGACY_TABLES = ("station_drones",)

# A tables: accumulated aggregate history (the trend layer, plan T4) —
# small per-snapshot aggregates appended once per DISTINCT snapshot
# (keyed on v_snapshot's canonical save_id, so reruns append nothing),
# never dropped on a version bump. Like the E tables, their history is
# irreplaceable: it spans saves the game has since overwritten.
AGGREGATE_TABLES = ("sector_presence", "station_metric", "market_stat")

# coverage's DDL is shared between TABLES and the v13->v14 backfill
# migration: the migration walk runs BEFORE the CREATE loop at connect,
# and its INSERT...SELECTs need the table to exist already. Streams:
# 'trade_tx', 'stock_event', 'money_event', 'log:<category>'. Epochs
# match the E tables' epoch column for the economylog streams; log
# streams get coverage-level epochs (log_entry has no epoch column).
_COVERAGE_DDL = """CREATE TABLE IF NOT EXISTS coverage (
  stream       TEXT NOT NULL,
  epoch        INTEGER NOT NULL,
  t_min        REAL NOT NULL,    -- covered interval, game seconds
  t_max        REAL NOT NULL,
  window_start REAL,             -- most recent merged window's start
                                 -- (rate denominators), newest epoch only
  updated_save_id INTEGER,       -- FK save.save_id (doc only): the
                                 -- import that last extended this row
  PRIMARY KEY (stream, epoch)
)"""

# money_event's DDL is shared between TABLES and the v11->v12 migration:
# the migration walk runs BEFORE the CREATE loop at connect, and its
# INSERT...SELECT needs the table to exist already.
_MONEY_EVENT_DDL = """CREATE TABLE IF NOT EXISTS money_event (
  time       REAL NOT NULL,
  owner_id   TEXT NOT NULL,
  partner_id TEXT,
  kind       TEXT,             -- money-block log type: trade, transfer,
                               -- orderqueue_add/_remove, script_add, ...
  tradeentry INTEGER,          -- 1-based ordinal into the save's trade
                               -- ledger (kind='trade'/'orderqueue_add')
  value_cr   REAL,             -- money moved, credits (save stores cents;
                               -- amended v2 preferred); NULL = none moved
  raw_attrs  TEXT,
  owner_faction TEXT, owner_code TEXT, owner_name TEXT,
  partner_faction TEXT, partner_code TEXT, partner_name TEXT,
  epoch      INTEGER NOT NULL DEFAULT 0,
  owner_entity INTEGER, partner_entity INTEGER
)"""

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
    # v12 types the economylog ingestion by ledger (plan T15 / review B1).
    # The pre-v12 merge shunted money-block rows (the player's per-object
    # money ledger: no ware, v in cents, tradeentry = ordinal into the
    # trade ledger) into stock_event as fake ware='' stock snapshots —
    # the sole source of ware='' rows there (the csv legacy import never
    # wrote stock rows). Re-type them into money_event, extracting the
    # money-ledger fields from raw_attrs; epoch and merge-time owner
    # identity survive the move. trade_tx.kind distinguishes real trades
    # from the newly ingested internal transfers; every pre-v12 row passed
    # the buyer+seller+price criterion, so they are all kind='trade'.
    "11": (
        _MONEY_EVENT_DDL,
        "ALTER TABLE trade_tx ADD COLUMN kind TEXT",
        "UPDATE trade_tx SET kind = 'trade'",
        """INSERT INTO money_event (time, owner_id, partner_id, kind,
             tradeentry, value_cr, raw_attrs, owner_faction, owner_code,
             owner_name, partner_faction, partner_code, partner_name,
             epoch, owner_entity, partner_entity)
           SELECT time, owner_id, json_extract(raw_attrs, '$.partner'),
                  json_extract(raw_attrs, '$.type'),
                  CAST(json_extract(raw_attrs, '$.tradeentry') AS INTEGER),
                  CAST(COALESCE(json_extract(raw_attrs, '$.v2'),
                                json_extract(raw_attrs, '$.v')) AS REAL)
                    / 100.0,
                  raw_attrs, owner_faction, owner_code, owner_name,
                  NULL, NULL, NULL, epoch, owner_entity, NULL
           FROM stock_event
           WHERE ware = '' AND raw_attrs IS NOT NULL""",
        "DELETE FROM stock_event WHERE ware = '' AND raw_attrs IS NOT NULL",
    ),
    # v14 backfills the coverage table from the event history (plan T3):
    # the merge-side hook only records merges since the table existed
    # (v11), so pre-coverage stretches were invisible to it. E-stream
    # bounds come exactly from the epoch-stamped rows; log streams have
    # no epoch column, so their history lands in coverage epoch 0 per
    # category (precise whenever a stream has a single coverage epoch —
    # true in every observed DB; with real gaps the old range is folded
    # into epoch 0, a known imprecision the stamped E streams don't
    # share). Existing hook-written rows are extended, never clobbered.
    # The three meta *_window_start keys retire: their value seeds
    # coverage.window_start where the hook never wrote one, then the
    # keys are deleted and the merge stops writing them.
    "13": (
        _COVERAGE_DDL,
        """INSERT INTO coverage (stream, epoch, t_min, t_max)
           SELECT 'trade_tx', epoch, MIN(time), MAX(time)
           FROM trade_tx WHERE true GROUP BY epoch
           ON CONFLICT(stream, epoch) DO UPDATE SET
             t_min = MIN(t_min, excluded.t_min),
             t_max = MAX(t_max, excluded.t_max)""",
        """INSERT INTO coverage (stream, epoch, t_min, t_max)
           SELECT 'stock_event', epoch, MIN(time), MAX(time)
           FROM stock_event WHERE true GROUP BY epoch
           ON CONFLICT(stream, epoch) DO UPDATE SET
             t_min = MIN(t_min, excluded.t_min),
             t_max = MAX(t_max, excluded.t_max)""",
        """INSERT INTO coverage (stream, epoch, t_min, t_max)
           SELECT 'money_event', epoch, MIN(time), MAX(time)
           FROM money_event WHERE true GROUP BY epoch
           ON CONFLICT(stream, epoch) DO UPDATE SET
             t_min = MIN(t_min, excluded.t_min),
             t_max = MAX(t_max, excluded.t_max)""",
        """INSERT INTO coverage (stream, epoch, t_min, t_max)
           SELECT 'log:' || COALESCE(category, ''), 0, MIN(time), MAX(time)
           FROM log_entry WHERE true GROUP BY category
           ON CONFLICT(stream, epoch) DO UPDATE SET
             t_min = MIN(t_min, excluded.t_min),
             t_max = MAX(t_max, excluded.t_max)""",
        """UPDATE coverage SET window_start =
             (SELECT CAST(value AS REAL) FROM meta
               WHERE key = 'trade_tx_window_start')
           WHERE stream = 'trade_tx' AND window_start IS NULL
             AND epoch = (SELECT MAX(epoch) FROM coverage
                           WHERE stream = 'trade_tx')
             AND EXISTS (SELECT 1 FROM meta
                          WHERE key = 'trade_tx_window_start')""",
        """UPDATE coverage SET window_start =
             (SELECT CAST(value AS REAL) FROM meta
               WHERE key = 'stock_event_window_start')
           WHERE stream = 'stock_event' AND window_start IS NULL
             AND epoch = (SELECT MAX(epoch) FROM coverage
                           WHERE stream = 'stock_event')
             AND EXISTS (SELECT 1 FROM meta
                          WHERE key = 'stock_event_window_start')""",
        """UPDATE coverage SET window_start =
             (SELECT CAST(value AS REAL) FROM meta
               WHERE key = 'money_event_window_start')
           WHERE stream = 'money_event' AND window_start IS NULL
             AND epoch = (SELECT MAX(epoch) FROM coverage
                           WHERE stream = 'money_event')
             AND EXISTS (SELECT 1 FROM meta
                          WHERE key = 'money_event_window_start')""",
        """DELETE FROM meta WHERE key IN ('trade_tx_window_start',
             'stock_event_window_start', 'money_event_window_start')""",
    ),
    # v15 renames two W/R tables (plan T11). The bump's drop path only
    # knows CURRENT table names, so the old names must be dropped here or
    # they linger as zombies; their replacements (build_entry, module_cap)
    # are created and repopulated by the normal rebuild right after the
    # walk (the bump path also clears reference_digest, so module_cap
    # reloads despite the digest guard).
    "14": (
        "DROP TABLE IF EXISTS module",
        "DROP TABLE IF EXISTS modcap",
    ),
    # v16 fixes the log_entry.interaction defect (plan T12 / review C11):
    # the loader read an attribute the save never writes (`interaction`
    # vs the save's `interact`), so the column was NULL everywhere while
    # the value survived in raw_attrs. Backfill from the JSON, then
    # rename the column to the save's spelling (the loader reads
    # `interact` from v16 on). json_extract is NULL for rows without the
    # attr, so the backfill only fills what the save actually carried.
    "15": (
        """UPDATE log_entry
           SET interaction = json_extract(raw_attrs, '$.interact')
           WHERE interaction IS NULL AND raw_attrs IS NOT NULL""",
        "ALTER TABLE log_entry RENAME COLUMN interaction TO interact",
    ),
    # v17 adds arrival provenance to the graveyard (plan T13): rows
    # merged from here on record the import that first saw them. The
    # save-side `time` attr does not exist in v9 (the existing column is
    # NULL everywhere), so the DB-side arrival save is the only
    # obtainable timestamp. Historical rows stay NULL — their arrival
    # import was never recorded.
    # (the guard CREATE matches the pre-v17 shape — same pattern as the
    # v12/v14 steps, whose DDL must exist before their statements run)
    "16": (
        """CREATE TABLE IF NOT EXISTS removed_object (
  time  REAL,
  id    TEXT, name TEXT, code TEXT, owner TEXT,
  raw_attrs TEXT
)""",
        "ALTER TABLE removed_object ADD COLUMN first_save_id INTEGER",
    ),
}

# The complete version chain: every historical version steps to the next
# so a DB parked at ANY version — including ones whose bump only touched
# W/R/D tables and so has no EVENT_MIGRATIONS entry — walks all the way
# to SCHEMA_VERSION. (The old hand-written map stopped at 4 and stranded
# off-chain DBs: a real v5 database skipped every later migration.)
NEXT_VERSION = {str(v): str(v + 1) for v in range(1, int(SCHEMA_VERSION))}

WORLD_TABLES = (
    "component", "fleet_edge", "build_entry", "module_upgrade", "workforce",
    "npc", "npc_skill", "post", "people", "cargo", "trade_offer",
    "build_resource", "ship_order", "resource", "floating_ware",
    "datavault", "wormhole", "wormhole_link", "ship_engine",
    "faction_relation", "faction_meta", "faction_licence",
    "player_subscription", "build_price_factor",
    "player_scan", "station_trade_setting", "trade_pending",
    "module_production",
)

REFERENCE_TABLES = (
    "ware", "recipe", "module_ref", "ship_ref", "faction", "cluster_ref",
    "sector_ref", "gate", "module_cap", "region_yield", "text",
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
    # coverage of the event history (P): which time ranges each stream
    # actually covers — maintained by the merges, historical stretches
    # backfilled by the v14 migration (which also retired the meta
    # *_window_start keys this table supersedes). DDL above (shared with
    # the migration).
    "coverage": _COVERAGE_DDL,
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
  entity_id     INTEGER,          -- FK entity.entity_id (doc only): NULL
                                  -- outside the registry domain (sectors,
                                  -- clusters) or when unresolvable
  known         INTEGER,          -- component@known: broad discovery flag
                                  -- (v20; superset of knownto='player')
  PRIMARY KEY (save_id, id)
)""",
    "fleet_edge": """CREATE TABLE IF NOT EXISTS fleet_edge (
  save_id      INTEGER NOT NULL,
  follower_id  TEXT NOT NULL,
  commander_id TEXT NOT NULL,
  PRIMARY KEY (save_id, follower_id)
)""",
    # build-PLAN entries, not modules (renamed from `module` in v15, plan
    # T11): a station lists its plan twice and sequences include unbuilt
    # entries — anything measuring existing capacity must filter built = 1
    # (v_built_module), which is the 2x-capacity gotcha the old name caused
    "build_entry": """CREATE TABLE IF NOT EXISTS build_entry (
  save_id      INTEGER NOT NULL,
  host_id      TEXT NOT NULL,
  entry_id     TEXT,
  idx          INTEGER,
  macro        TEXT,
  built        INTEGER NOT NULL
)""",
    "module_production": """CREATE TABLE IF NOT EXISTS module_production (
  save_id    INTEGER NOT NULL,
  station_id TEXT NOT NULL,
  macro      TEXT NOT NULL,   -- production module macro
  ware       TEXT,            -- <queue ware=>: what it is making now
  efficiency REAL,            -- <efficiency product=>: the COMPLETE runtime
                              -- multiplier on the recipe amount (workforce
                              -- bonus x sunlight x mod effects)
  state      TEXT,            -- producing / waiting / ...
  n_modules  INTEGER NOT NULL -- modules sharing this (macro, ware, efficiency)
)""",
    "module_upgrade": """CREATE TABLE IF NOT EXISTS module_upgrade (
  save_id  INTEGER NOT NULL,
  host_id  TEXT NOT NULL,   -- owning station/build storage: entry ids are
                            -- unique only per host (v28)
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
    # PLAYER EMPLOYEES only, despite the generic name (the parser collects
    # <npc> entries under player-owned posts; plan T11 kept the name and
    # documents the scope instead — lowest-value rename of the set)
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
    # object_id NULL = hostless offer (was '' before v15; plan T11 made it
    # follow the schema-wide absent-is-NULL convention)
    # flags: the save's raw |-joined offer flag set (NULL = none). The
    # "supplies" token marks station self-supply buys (drone/munition build
    # inputs) as opposed to production resources — CONFIRMED sweep-wide, see
    # docs/reports/supply-offer-discriminator.md. desired = wanted total
    # (open amount + already-reserved portion).
    "trade_offer": """CREATE TABLE IF NOT EXISTS trade_offer (
  save_id   INTEGER NOT NULL,
  object_id TEXT,
  side      TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  price_cr  REAL,
  flags     TEXT,
  desired   REAL
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
  yield        REAL,
  level        TEXT,
  speed        TEXT,
  starttime    REAL
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
    # wormholes / anomalies (map overlay): every galaxy anomaly. transition_dest
    # is NULL for an inert lore anomaly, else the destination-state string
    # ("0" = a dormant/story warp). See docs/models/wormhole-connection-model.md
    "wormhole": """CREATE TABLE IF NOT EXISTS wormhole (
  save_id        INTEGER NOT NULL,
  object_id      TEXT NOT NULL,
  macro          TEXT NOT NULL,
  code           TEXT,
  knownto        TEXT,
  cluster_macro  TEXT,
  sector_macro   TEXT,
  sx             REAL,
  sz             REAL,
  source_entry   TEXT,
  source_class   TEXT,
  transition_dest TEXT,
  PRIMARY KEY (save_id, object_id)
)""",
    # directional warp links: role "origin" (entry) / "destination" (exit);
    # target_conn is the partner wormhole's own_conn (resolved in frames)
    "wormhole_link": """CREATE TABLE IF NOT EXISTS wormhole_link (
  save_id     INTEGER NOT NULL,
  object_id   TEXT NOT NULL,
  own_conn    TEXT NOT NULL,
  role        TEXT,
  target_conn TEXT
)""",
    # faction diplomacy (universe/factions). kind: base | booster | discount
    # (discount value is a trade discount fraction, not a standing). time is
    # the application game-time (NULL for base). Effective standing = base +
    # active boosters, computed in frames. See docs/models/faction-relations-model.md
    "faction_relation": """CREATE TABLE IF NOT EXISTS faction_relation (
  save_id  INTEGER NOT NULL,
  faction  TEXT NOT NULL,
  other    TEXT NOT NULL,
  kind     TEXT NOT NULL,
  value    REAL,
  time     REAL
)""",
    # per-faction scalars (currently the treasury). account_cr is credits
    # (÷100 at load, renamed from raw-cents `account` in v15): the schema
    # convention is _cr everywhere money appears
    "faction_meta": """CREATE TABLE IF NOT EXISTS faction_meta (
  save_id      INTEGER NOT NULL,
  faction      TEXT NOT NULL,
  account_cr   REAL,
  build_method TEXT,
  PRIMARY KEY (save_id, faction)
)""",
    # rep-gated unlocks: which factions a licence type is granted for
    "faction_licence": """CREATE TABLE IF NOT EXISTS faction_licence (
  save_id  INTEGER NOT NULL,
  faction  TEXT NOT NULL,
  type     TEXT NOT NULL,
  factions TEXT
)""",
    # the player's trade-info subscriptions (v19): <memory><subscriptions>
    # under the player component. expires_at is an ABSOLUTE game-seconds
    # expiry (duration constant: parameters.xml subscriptiondurations,
    # 18,000 s); NULL = permanent. The game retains expired rows — filter
    # on expires_at > the save's game_time (or expires_at IS NULL).
    "player_subscription": """CREATE TABLE IF NOT EXISTS player_subscription (
  save_id    INTEGER NOT NULL,
  object_id  TEXT NOT NULL,
  expires_at REAL,
  PRIMARY KEY (save_id, object_id)
)""",
    # per-station build price factor (v19): <trade><prices buildpricefactor>,
    # present only on ship/deployable-selling stations. The deployable/ship
    # pricing M: NPC values are the engine variation clamped to [0.9, 1.15]
    # and DRIFT between saves (12 of 67 changed across one save pair);
    # player yards store the price slider (up to 1.5). Snapshot data — never
    # treat as a station constant.
    # per-station build-method override (v21): <build method=> directly
    # under a station/buildstorage component, absent when the station
    # inherits its owner faction's rule (faction_meta.build_method).
    # 3 rows universe-wide in save_009 — resolution order and the tag
    # collision with build tasks are in v_build_method / parser.py.
    "build_method": """CREATE TABLE IF NOT EXISTS build_method (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  method    TEXT NOT NULL,
  PRIMARY KEY (save_id, object_id)
)""",
    # station self-supply bookkeeping (v22): what a station is building for
    # ITSELF (drones/munitions) and what it has already set aside for those
    # builds. kind 'order' = <supplies><orders> (the build TARGET per
    # product ware), 'ware' = <supplies><wares> (inputs held back).
    # Stations/build storages only — a ship's <supplies> is its own ammo
    # reserve, a different concept, deliberately not loaded here.
    "station_supply": """CREATE TABLE IF NOT EXISTS station_supply (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  kind      TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  PRIMARY KEY (save_id, object_id, kind, ware)
)""",
    # the station's configured per-ware prices (v22 as price_override,
    # generalised in v23): <trade><prices><reference> (kind 'reference',
    # the configured reference price = pricing Layer 5) and <override>
    # (kind 'override', a hard manual override). WHOLE CREDITS in the save
    # — this block is the one exception to the cents rule — so stored as
    # credits with no /100. NULL = that side unset (the save writes 0).
    "price_setting": """CREATE TABLE IF NOT EXISTS price_setting (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  kind      TEXT NOT NULL,
  ware      TEXT NOT NULL,
  buy_cr    REAL,
  sell_cr   REAL,
  PRIMARY KEY (save_id, object_id, kind, ware)
)""",
    # manual per-ware trade/storage limits (v23): the station-config UI's
    # per-ware sliders, stored as <overrides><max|buy|sell><ware>.
    # kind 'max'  = stock (storage allocation) limit for that ware
    #      'buy'  = buy up to this stock level (offer = limit - stock)
    #      'sell' = keep this much, sell the excess (offer = stock - limit)
    # amount: a missing amount= in the save means 1 — the UI floors all
    # three limits at 1, so the minimum is the omitted default (v24).
    "ware_limit": """CREATE TABLE IF NOT EXISTS ware_limit (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  kind      TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  PRIMARY KEY (save_id, object_id, kind, ware)
)""",
    "build_price_factor": """CREATE TABLE IF NOT EXISTS build_price_factor (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  factor    REAL NOT NULL,
  PRIMARY KEY (save_id, object_id)
)""",
    # the player's permanent per-component module scan levels (v20):
    # <memory><scan> under the player component. Levels 0-3; targets are
    # mostly storage modules — join component.parent chain for the station.
    "player_scan": """CREATE TABLE IF NOT EXISTS player_scan (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  level     INTEGER NOT NULL,
  PRIMARY KEY (save_id, object_id)
)""",
    # trade-station / pirate-base ware whitelists (v20): <trade><settings>.
    # setting in (buy, sell, lockavgprice). lockavgprice pegs the economy
    # price at band average (sell = avg exactly, buy = avg - 1 Cr; verified
    # 588/588 sell offers in save_008 + in-game) — the storage curve does
    # not apply, but player-facing reputation/event discounts still do.
    # supplies-flagged self-supply buys are EXEMPT from the lock (they keep
    # need pricing; join trade_offer.flags to tell the two apart).
    "station_trade_setting": """CREATE TABLE IF NOT EXISTS station_trade_setting (
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  setting   TEXT NOT NULL,
  ware      TEXT NOT NULL,
  PRIMARY KEY (save_id, object_id, setting, ware)
)""",
    # escrow-stage in-flight trades (v20): <trade><active><trade> — money
    # committed (escrow_cr), possibly partially delivered (transferred).
    # side is the host's side ('' when the host is only the partner).
    # committed in-flight trades (v26) — the supply curve's PENDING term
    # (economy_price = max - (max-min) x (stock - pending) / target_level).
    # One row per trade id, merged from the executing ship's
    # <orders><order><trade> and the counterpart station's
    # <trade><reservations><reservation>: the save keeps every committed
    # trade in BOTH places, attribute-identical (2,510/2,510 in save_009).
    "trade_pending": """CREATE TABLE IF NOT EXISTS trade_pending (
  save_id     INTEGER NOT NULL,
  trade_id    TEXT NOT NULL,
  ware        TEXT,
  amount      REAL,
  desired     REAL,
  transferred REAL,
  price_cr    REAL,
  escrow_cr   REAL,
  buyer_id    TEXT,
  seller_id   TEXT,
  ship_id     TEXT,
  station_id  TEXT,
  is_active   INTEGER NOT NULL DEFAULT 0,
  expires_at  REAL,
  flags       TEXT,
  PRIMARY KEY (save_id, trade_id)
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
  buyer_cmdr_entity INTEGER, seller_cmdr_entity INTEGER,
  kind      TEXT              -- trade-block log type: 'trade' (real
                              -- transaction) or 'transfer' (player-
                              -- internal ware movement, no price)
)""",
    "money_event": _MONEY_EVENT_DDL,
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
  interact    TEXT,             -- the save's attribute name (was the
                                -- never-populated `interaction`, v16)
  component_id TEXT,
  highlighted TEXT,
  raw_attrs   TEXT
)""",
    # the graveyard: the save's cumulative removed-objects catalog.
    # time is NULL everywhere in v9 saves (the attr no longer exists);
    # first_save_id (v17) is the import that first merged the row — the
    # only obtainable arrival timestamp (NULL for rows merged pre-v17)
    "removed_object": """CREATE TABLE IF NOT EXISTS removed_object (
  time  REAL,
  id    TEXT, name TEXT, code TEXT, owner TEXT,
  raw_attrs TEXT,
  first_save_id INTEGER          -- FK save.save_id (doc only)
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
  tags TEXT,
  price_min REAL, price_avg REAL, price_max REAL,
  component TEXT,
  source TEXT
)""",
    "recipe": """CREATE TABLE IF NOT EXISTS recipe (
  ware TEXT NOT NULL, method TEXT NOT NULL,
  time REAL, amount REAL,
  input_ware TEXT, input_amount REAL,
  work_effect REAL
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
    "module_cap": """CREATE TABLE IF NOT EXISTS module_cap (
  macro TEXT PRIMARY KEY, class TEXT,
  housing REAL, workers REAL, cargo_max REAL, cargo_tags TEXT,
  unit_storage REAL
)""",
    # resource replenishment reference (regionyields.csv, T9): what a
    # yield class refills to and how fast. respawn_min is MINUTES (the
    # source unit — the CSV, the XSD and frames all use minutes; -1 =
    # never respawns): anyone joining against resource.starttime
    # (SECONDS) must convert ×60, and the column name says so (review
    # X21 — a `respawn_s` name over minute values would hand SQL ETA
    # arithmetic a silent 60× bug). Keyed by (level, ware), not a game
    # id — deliberately no `_ref` suffix.
    "region_yield": """CREATE TABLE IF NOT EXISTS region_yield (
  level       TEXT NOT NULL,         -- verylow .. veryhigh
  ware        TEXT NOT NULL,
  capacity    REAL,                  -- full-area yield
  respawn_min REAL,                  -- MINUTES (source unit); -1 = never
  PRIMARY KEY (level, ware)
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
    # per-snapshot storage-allocation model (analysis/storage.py): the max
    # amount of each ware a station allocates storage for, derived from its
    # production/consumption throughput at full workforce. Written after the
    # frames are built (store.write_station_storage), so grouped on its own.
    # role 'supply' (source 'offer') rows are the station's open self-supply
    # demand (supplies-flagged buy offers, v18) — outstanding drone/munition
    # build inputs, NOT cargo-storage allocation. A ware can hold both a
    # production-side row and a supply row, hence role in the PK.
    "station_storage": """CREATE TABLE IF NOT EXISTS station_storage (
  save_id    INTEGER NOT NULL,
  station_id TEXT NOT NULL,
  ware       TEXT NOT NULL,
  transport  TEXT,
  role       TEXT,
  throughput REAL,
  max_units  REAL,
  max_volume REAL,
  source     TEXT,
  PRIMARY KEY (save_id, station_id, ware, role)
)""",
    # per-snapshot station munition census (analysis/drones.py): every item in
    # a station's own <ammunition><available> -- one row per macro with a
    # category and is_unit flag. is_unit rows (drones + police) share the
    # units.maxcount pool; the rest (missiles/countermeasures/deployables) are
    # separate inventories, captured for reference. capacity_floor = Sum
    # module_cap.unit_storage over the station's built modules -- the READABLE lower
    # bound on the drone pool (exact unless the station has production modules,
    # which add ~10 each with no readable field). Written after frames build.
    "station_munition": """CREATE TABLE IF NOT EXISTS station_munition (
  save_id        INTEGER NOT NULL,
  station_id     TEXT NOT NULL,
  macro          TEXT NOT NULL,
  category       TEXT,
  is_unit        INTEGER,
  count          REAL,
  capacity_floor REAL,
  PRIMARY KEY (save_id, station_id, macro)
)""",
    # ---- aggregate history (A: appended per snapshot, never dropped) -------
    # save_id is the CANONICAL snapshot id (v_snapshot / store.snapshot_id);
    # joining save.game_time gives the time axis. Key columns that are NULL
    # in the source (sector while in transit, ownerless objects) use the ''
    # sentinel instead: SQLite treats NULL in a non-INTEGER PK column as
    # distinct-from-everything, which would make the key decorative and
    # duplicate appends succeed (plan review F6).
    #
    # territory & military presence: object counts per (sector, owner,
    # class), ships/stations/buildstorages only (~1,500 rows / snapshot)
    "sector_presence": """CREATE TABLE IF NOT EXISTS sector_presence (
  save_id      INTEGER NOT NULL,   -- canonical snapshot id (v_snapshot)
  sector_macro TEXT NOT NULL DEFAULT '',  -- '' = no sector (in transit)
  owner        TEXT NOT NULL DEFAULT '',  -- '' = ownerless
  class        TEXT NOT NULL,      -- station | ship_xl | ship_l | ...
  n            INTEGER NOT NULL,
  PRIMARY KEY (save_id, sector_macro, owner, class)
)""",
    # per-player-station economics: one row per station per snapshot.
    # entity_id comes from the registry (never NULL there; stations the
    # registry could not resolve are skipped)
    "station_metric": """CREATE TABLE IF NOT EXISTS station_metric (
  save_id       INTEGER NOT NULL,  -- canonical snapshot id (v_snapshot)
  entity_id     INTEGER NOT NULL,  -- durable station identity (T2)
  workforce     REAL,              -- Σ workforce.amount
  modules_built INTEGER,           -- COUNT(module WHERE built=1)
  cargo_value_cr REAL,             -- Σ cargo.amount × ware.price_avg
  buy_open_cr   REAL,              -- Σ open buy offers × price
  sell_open_cr  REAL,              -- Σ open sell offers × price
  PRIMARY KEY (save_id, entity_id)
)""",
    # market history at sector granularity: per (sector, ware, side) price
    # band + open volume over the whole offer book. The only obtainable
    # NPC price signal over time — the save's economylog carries no
    # NPC↔NPC transactions, but the offer book is complete every snapshot.
    "market_stat": """CREATE TABLE IF NOT EXISTS market_stat (
  save_id      INTEGER NOT NULL,   -- canonical snapshot id (v_snapshot)
  sector_macro TEXT NOT NULL DEFAULT '',  -- '' = offer host has no sector
  ware         TEXT NOT NULL,
  side         TEXT NOT NULL,      -- buy | sell
  n_offers     INTEGER NOT NULL,
  units        REAL,               -- Σ amount
  price_min_cr REAL, price_avg_cr REAL, price_max_cr REAL,
  PRIMARY KEY (save_id, sector_macro, ware, side)
)""",
}

# Applied idempotently at every connect — deliberately NOT via
# EVENT_MIGRATIONS, so E-table indices reach every DB whatever version it
# sits at (the chain only runs on a version mismatch).
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_build_entry_host ON "
    "build_entry(save_id, host_id)",
    "CREATE INDEX IF NOT EXISTS idx_offer_ware ON trade_offer(save_id, ware)",
    # the entity spine's access paths (T2): durable identity into the
    # snapshot, and entity-keyed event history
    "CREATE INDEX IF NOT EXISTS idx_component_entity ON "
    "component(save_id, entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_component_class ON "
    "component(save_id, class, owner)",
    "CREATE INDEX IF NOT EXISTS idx_component_sector ON "
    "component(save_id, sector_macro)",
    "CREATE INDEX IF NOT EXISTS idx_stock_entity ON "
    "stock_event(owner_entity, ware, time)",
    "CREATE INDEX IF NOT EXISTS idx_tx_buyer ON trade_tx(buyer_entity) "
    "WHERE buyer_entity IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tx_seller ON trade_tx(seller_entity) "
    "WHERE seller_entity IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tx_time ON trade_tx(time)",
    "CREATE INDEX IF NOT EXISTS idx_tx_ware ON trade_tx(ware)",
    "CREATE INDEX IF NOT EXISTS idx_money_time ON money_event(time)",
    "CREATE INDEX IF NOT EXISTS idx_stock ON stock_event(owner_id, ware, time)",
    "CREATE INDEX IF NOT EXISTS idx_log_time ON log_entry(category, time)",
    "CREATE INDEX IF NOT EXISTS idx_recipe ON recipe(ware, method)",
    "CREATE INDEX IF NOT EXISTS idx_entity_slot ON entity(code, class)",
    "CREATE INDEX IF NOT EXISTS idx_entity_event ON entity_event(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_station_storage ON "
    "station_storage(station_id)",
    "CREATE INDEX IF NOT EXISTS idx_station_munition ON "
    "station_munition(station_id)",
)

# The frames.py replacement layer. (Re)created at every connect so
# definition updates propagate; all filter to the current snapshot via
# MAX(save_id). Joins are LEFT JOINs — dangling references are normal
# (event history outlives objects; modded content references unknown ids).
VIEWS: dict[str, str] = {
    # the current snapshot, named (T1): every snapshot-scoped query joins
    # or subselects this instead of repeating the MAX(save_id) idiom
    "current_save": """CREATE VIEW current_save AS
SELECT MAX(save_id) AS save_id FROM save""",
    # effective faction standing (T7): base + boosters clamped to [-1, 1],
    # reproducing the frames.py pivot. Discount-only pairs emit no row
    # (frames keys on base ∪ booster); discounts stay a plain filter on
    # faction_relation. Whether boosters decay in-save is unsettled
    # (faction-model F1) — this view just sums what the save stores.
    "v_faction_standing": """CREATE VIEW v_faction_standing AS
SELECT faction, other,
       SUM(CASE WHEN kind = 'base'    THEN value ELSE 0 END) AS base,
       SUM(CASE WHEN kind = 'booster' THEN value ELSE 0 END) AS booster,
       MIN(1.0, MAX(-1.0, SUM(value))) AS effective
FROM faction_relation
WHERE save_id = (SELECT save_id FROM current_save)
  AND kind IN ('base', 'booster')
GROUP BY faction, other""",
    # distinct snapshots (T5): the save table logs one row per IMPORT, so
    # dashboard-dev reruns pollute any series keyed on it. This view
    # collapses the import log to distinct saves; its save_id (the first
    # import of each snapshot) is the canonical id the A tables key on.
    # SQLite's bare-column rule picks the remaining columns from the
    # MIN(save_id) row.
    "v_snapshot": """CREATE VIEW v_snapshot AS
SELECT MIN(save_id) AS save_id, guid, game_time, save_date,
       player_money_cr, player_name
FROM save
GROUP BY guid, game_time, save_date""",
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
    # trades in domain terms (T6): commander-redirected ("Executed by"
    # rule), current display names via the registry, ware names resolved.
    # Redirection keys on cmdr_id — frames' rule is cmdr_id.notna(), and
    # the csv-import path writes cmdr ids with NULL entities, so an
    # entity-keyed redirect would silently diverge on those rows (review
    # plan-F3). Executor DISPLAY columns (exec_*) survive because
    # viz/history.py renders them ({side}.proxy.name/.code) and entity
    # ids alone cannot recover them for NULL-entity rows; they are
    # registry-resolved like the main names. What this view deliberately
    # does NOT keep from the frames-era assembly: the latest-name-per-code
    # fallback — parties without registry identity degrade to the stored
    # merge-time name (permanent, not transitional: NULL-entity parties
    # are minted at every merge for removed-object-resolved and
    # registry-missed parties; they have no registry identity to resolve
    # against, so the stored name is the best available either way).
    "v_trade": """CREATE VIEW v_trade AS
SELECT t.time, t.ware, COALESCE(w.name, t.ware) AS ware_name,
       t.price_cr, t.amount, t.price_cr * t.amount AS total_cr,
       t.kind, t.epoch,
       t.buyer_faction, t.seller_faction,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL
            THEN t.buyer_cmdr_id     ELSE t.buyer_id      END AS buyer_id,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL
            THEN t.buyer_cmdr_entity ELSE t.buyer_entity  END AS buyer_entity,
       COALESCE(be.name, CASE WHEN t.buyer_cmdr_id IS NOT NULL
            THEN t.buyer_cmdr_name   ELSE t.buyer_name    END) AS buyer_name,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL
            THEN t.buyer_cmdr_code   ELSE t.buyer_code    END AS buyer_code,
       CASE WHEN t.seller_cmdr_id IS NOT NULL
            THEN t.seller_cmdr_id     ELSE t.seller_id     END AS seller_id,
       CASE WHEN t.seller_cmdr_id IS NOT NULL
            THEN t.seller_cmdr_entity ELSE t.seller_entity END AS seller_entity,
       COALESCE(se.name, CASE WHEN t.seller_cmdr_id IS NOT NULL
            THEN t.seller_cmdr_name   ELSE t.seller_name   END) AS seller_name,
       CASE WHEN t.seller_cmdr_id IS NOT NULL
            THEN t.seller_cmdr_code   ELSE t.seller_code   END AS seller_code,
       -- the executing ship when a subordinate traded, display identity
       -- included; present only when proxied
       CASE WHEN t.buyer_cmdr_id IS NOT NULL THEN t.buyer_id END
         AS buyer_exec_id,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL THEN t.buyer_entity END
         AS buyer_exec_entity,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL
            THEN COALESCE(bx.name, t.buyer_name) END AS buyer_exec_name,
       CASE WHEN t.buyer_cmdr_id IS NOT NULL THEN t.buyer_code END
         AS buyer_exec_code,
       CASE WHEN t.seller_cmdr_id IS NOT NULL THEN t.seller_id END
         AS seller_exec_id,
       CASE WHEN t.seller_cmdr_id IS NOT NULL THEN t.seller_entity END
         AS seller_exec_entity,
       CASE WHEN t.seller_cmdr_id IS NOT NULL
            THEN COALESCE(sx.name, t.seller_name) END AS seller_exec_name,
       CASE WHEN t.seller_cmdr_id IS NOT NULL THEN t.seller_code END
         AS seller_exec_code,
       t.buyer_cmdr_id IS NOT NULL  AS buyer_proxied,
       t.seller_cmdr_id IS NOT NULL AS seller_proxied
FROM trade_tx t
LEFT JOIN ware w    ON w.id = t.ware
LEFT JOIN entity be ON be.entity_id = CASE WHEN t.buyer_cmdr_id IS NOT NULL
       THEN t.buyer_cmdr_entity ELSE t.buyer_entity END
LEFT JOIN entity se ON se.entity_id = CASE WHEN t.seller_cmdr_id IS NOT NULL
       THEN t.seller_cmdr_entity ELSE t.seller_entity END
LEFT JOIN entity bx ON bx.entity_id = t.buyer_entity
LEFT JOIN entity sx ON sx.entity_id = t.seller_entity""",
    # stock flows partitioned by durable identity (T6; renames
    # v_stock_delta, kept below as an alias for one release). The
    # entity-first partition heals a station's series across renames and
    # captures where the registry resolved it; text identity (faction|
    # code) and raw owner_id remain the fallbacks for pre-registry rows —
    # verified delta-identical to the text-first keying on both real DBs
    # at introduction (tests/test_views_parity.py pins it). No ware
    # guard: the pre-v12 `ware != ''` rows were the mis-typed money-
    # ledger family, re-typed into money_event by the v12 migration.
    "v_stock_flow": """CREATE VIEW v_stock_flow AS
SELECT owner_entity, owner_id, owner_faction, owner_code, owner_name,
       ware, time, level, epoch,
       MAX(level - LAG(level) OVER w, 0) AS inflow,
       MAX(LAG(level) OVER w - level, 0) AS outflow
FROM stock_event
WINDOW w AS (PARTITION BY COALESCE('e' || owner_entity,
                                   owner_faction || '|' || owner_code,
                                   owner_id),
             ware, epoch ORDER BY time, rowid)""",
    # the epoch term stops LAG from computing a delta across a coverage
    # gap; rowid breaks time ties in save order: stations log several
    # stock levels within the same second, and an arbitrary tie order
    # would reshuffle which deltas count as positive.
    # compat alias (one release): the pre-T6 name and column spellings
    "v_stock_delta": """CREATE VIEW v_stock_delta AS
SELECT owner_id, owner_faction, owner_code, owner_name, ware, time, level,
       epoch, inflow AS dv, outflow AS dv_neg
FROM v_stock_flow""",
    # entity biographies (T6): lifespan + liveness + where the entity is
    # in the current snapshot (component join NULL when absent from it)
    "v_entity_life": """CREATE VIEW v_entity_life AS
SELECT e.*,
       COALESCE(e.gone_time,
                (SELECT game_time FROM save
                 WHERE save_id = (SELECT save_id FROM current_save)))
         - e.first_seen                        AS observed_span_s,
       e.gone_time IS NULL                     AS alive,
       c.id                                    AS component_id,
       c.sector_macro
FROM entity e
LEFT JOIN component c ON c.entity_id = e.entity_id
  AND c.save_id = (SELECT save_id FROM current_save)""",
    # the concept "station", assembled (T8): one row per station in the
    # current snapshot, with the rollups frames used to build in pandas.
    # modules_built counts BUILT plan entries (the capacity-overcount
    # gotcha); correlated subqueries are index-served (idx_build_entry_host,
    # idx_offer_ware's cousins) and fine at ~1,800 stations.
    "v_station": """CREATE VIEW v_station AS
SELECT c.id, c.entity_id, c.name, c.basename, c.code, c.owner,
       c.sector_macro, sec.name AS sector_name, c.sx, c.sz, c.knownto,
       (SELECT COUNT(*) FROM build_entry m
         WHERE m.save_id = c.save_id AND m.host_id = c.id AND m.built = 1)
         AS modules_built,
       (SELECT SUM(w.amount) FROM workforce w
         WHERE w.save_id = c.save_id AND w.station_id = c.id) AS workforce,
       (SELECT SUM(cg.amount * COALESCE(wr.volume, 0)) FROM cargo cg
         LEFT JOIN ware wr ON wr.id = cg.ware
         WHERE cg.save_id = c.save_id AND cg.object_id = c.id)
         AS cargo_volume_m3
FROM component c
LEFT JOIN sector_ref sec ON sec.macro = c.sector_macro
WHERE c.class = 'station'
  AND c.save_id = (SELECT save_id FROM current_save)""",
    # player fleet edges, entity-keyed (T8): the ONE fleet resolution
    # (write_snapshot's), filtered to player-owned on both sides — the
    # commander map merge_events attributes trades with, and frames.wings'
    # source. Joining component excludes edges touching connectionless
    # objects; _player_edges resolved those from the raw save lists —
    # measured equivalent (0 divergent edges) on the real DBs, pinned in
    # tests/test_views_parity.py so divergence fails loudly (plan-F10).
    "v_player_fleet": """CREATE VIEW v_player_fleet AS
SELECT fe.follower_id, cf.entity_id AS follower_entity,
       fe.commander_id, cc.entity_id AS commander_entity
FROM fleet_edge fe
JOIN component cf ON cf.id = fe.follower_id  AND cf.save_id = fe.save_id
JOIN component cc ON cc.id = fe.commander_id AND cc.save_id = fe.save_id
WHERE cf.owner = 'player' AND cc.owner = 'player'
  AND fe.save_id = (SELECT save_id FROM current_save)""",
    # per-area resource status (T9): the confirmed timer/eligibility
    # layer of the respawn model (docs/models/resource-depletion-model.md
    # — starttime = depletion + delay, arm-at-zero, eligibility gating;
    # starttime = 0 folds into <= since game_time > 0 always). An
    # empty area past its starttime is respawned & full even though its
    # stored yield reads 0 (it only "materializes" when mined). Caveats
    # (review X21 / resource-model): 'full' reports the REFERENCE
    # capacity — for nividium materializations as low as 4.4% of cap
    # were measured (B11 tracks it); and respawn usually RELOCATES the
    # area within its sector (B5), so nothing keyed on per-area position
    # may be layered on this view — at the (sector, ware) grain it
    # exposes, relocation is immaterial.
    "v_resource_area": """CREATE VIEW v_resource_area AS
SELECT r.sector_macro, r.ware, r.yield, r.level, r.speed, r.starttime,
       ry.capacity, ry.respawn_min,
       CASE WHEN r.yield > 0 THEN 'live'
            WHEN ry.capacity IS NULL OR ry.capacity = 0 THEN 'unknown'
            WHEN ry.respawn_min < 0 THEN 'never'
            WHEN r.starttime <= (SELECT game_time FROM save
                                 WHERE save_id = (SELECT save_id
                                                  FROM current_save))
                 THEN 'full'
            ELSE 'respawning' END AS status
FROM resource r
LEFT JOIN region_yield ry ON ry.level = r.level AND ry.ware = r.ware
WHERE r.save_id = (SELECT save_id FROM current_save)""",
    # built modules only (measure reality, not plans — CLAUDE.md gotcha)
    # effective build method per station (v21): the station's own override
    # wins, else its owner faction's rule; stations with neither emit no
    # row (they build on their race default, which the save never states).
    # Per WARE the engine still falls back to the 'default' recipe when the
    # ware has no variant under this method — join recipe accordingly.
    "v_build_method": """CREATE VIEW v_build_method AS
SELECT c.id AS object_id, c.owner,
       COALESCE(bm.method, fm.build_method) AS method,
       CASE WHEN bm.method IS NOT NULL THEN 'station' ELSE 'faction' END
         AS source
FROM component c
LEFT JOIN build_method bm
       ON bm.save_id = c.save_id AND bm.object_id = c.id
LEFT JOIN faction_meta fm
       ON fm.save_id = c.save_id AND fm.faction = c.owner
WHERE c.class IN ('station', 'buildstorage')
  AND c.save_id = (SELECT save_id FROM current_save)
  AND COALESCE(bm.method, fm.build_method) IS NOT NULL""",
    # station self-supply, labeled (v22): build targets and set-aside
    # inputs with station/ware display names. Join station_munition on
    # (station, ware) to compare a drone target against the actual count.
    "v_station_supply": """CREATE VIEW v_station_supply AS
SELECT s.object_id, c.code AS station_code, c.name AS station_name,
       c.owner, s.kind, s.ware, w.name AS ware_name, s.amount
FROM station_supply s
LEFT JOIN component c ON c.id = s.object_id AND c.save_id = s.save_id
LEFT JOIN ware w ON w.id = s.ware
WHERE s.save_id = (SELECT save_id FROM current_save)""",
    # committed in-flight trades, labeled (v26). `pending_out` on the
    # seller side is the supply curve's numerator term.
    "v_trade_pending": """CREATE VIEW v_trade_pending AS
SELECT p.trade_id, p.ware, w.name AS ware_name, p.amount, p.desired,
       p.transferred, p.price_cr, p.escrow_cr, p.is_active,
       p.buyer_id, cb.code AS buyer_code, cb.owner AS buyer_faction,
       p.seller_id, cs.code AS seller_code, cs.owner AS seller_faction,
       p.ship_id, csh.code AS ship_code, p.station_id, p.expires_at, p.flags
FROM trade_pending p
LEFT JOIN ware w ON w.id = p.ware
LEFT JOIN component cb ON cb.id = p.buyer_id AND cb.save_id = p.save_id
LEFT JOIN component cs ON cs.id = p.seller_id AND cs.save_id = p.save_id
LEFT JOIN component csh ON csh.id = p.ship_id AND csh.save_id = p.save_id
WHERE p.save_id = (SELECT save_id FROM current_save)""",
    "v_built_module": """CREATE VIEW v_built_module AS
SELECT * FROM build_entry
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
    # storage-allocation model with station + ware display names
    "v_station_storage": """CREATE VIEW v_station_storage AS
SELECT ss.station_id, c.code AS station_code, c.name AS station_name,
       sec.name AS sector_name, ss.ware, w.name AS ware_name,
       ss.transport, ss.role, ss.throughput, ss.max_units, ss.max_volume,
       ss.source
FROM station_storage ss
LEFT JOIN component c   ON c.id = ss.station_id AND c.save_id = ss.save_id
LEFT JOIN sector_ref sec ON sec.macro = c.sector_macro
LEFT JOIN ware w        ON w.id = ss.ware
WHERE ss.save_id = (SELECT MAX(save_id) FROM save)""",
    # full station munition census with station + sector display names
    "v_station_munition": """CREATE VIEW v_station_munition AS
SELECT sm.station_id, c.code AS station_code, c.name AS station_name,
       c.owner AS owner, sec.name AS sector_name,
       sm.category, sm.is_unit, sm.macro, sm.count, sm.capacity_floor
FROM station_munition sm
LEFT JOIN component c    ON c.id = sm.station_id AND c.save_id = sm.save_id
LEFT JOIN sector_ref sec ON sec.macro = c.sector_macro
WHERE sm.save_id = (SELECT MAX(save_id) FROM save)""",
    # drone/unit pool only (defence/repair/transport/build/mining/police) --
    # answers "how many drones does station X have, of its cap floor"
    "v_station_drones": """CREATE VIEW v_station_drones AS
SELECT * FROM v_station_munition WHERE is_unit = 1""",
}

# Fingerprint of the view definitions, stored in meta('views_version'):
# views are recreated only when it changes, so read-only connections (a
# live-mode server) always see current views without every connect
# performing DDL writes. Changing any view DDL above bumps it for free.
VIEWS_VERSION = hashlib.sha256(
    "\n".join(VIEWS.values()).encode()).hexdigest()[:16]
