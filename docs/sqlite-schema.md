# v2.0 SQLite schema reference

Companion to [sqlite-orm-feasibility.md](sqlite-orm-feasibility.md). Status:
proposed, not implemented. DDL is SQLite dialect; every save-derived column
lists its provenance in the save XML so the parser mapping stays auditable.

## Conventions

- **One database per game** (`x4_<guid>.sqlite`), so no `guid` column on
  data tables; the `save` table records each imported snapshot.
- **Scoping classes** — every table is one of:
  - **W** world state: rebuilt per snapshot, rows carry `save_id`.
  - **E** event history: append/merge across runs (the old csv.gz caches);
    survives rebuilds, needs migration care.
  - **R** reference: game data from `extract-gamedata`, replaced wholesale.
  - **D** derived: materialized from E/W tables at load time, always
    rebuildable (e.g. logparse regex output).
- **Units**: money is credits (`_cr` suffix; save stores cents, ÷100 at
  load). Times are game seconds (`time`/`spawntime`). Volumes are units of
  ware; m³ comes from joining `ware.volume`.
- **Casing**: macros and ware/faction ids lowercased at load (save vs game
  files disagree on case).
- **NULLs**: absent XML attributes load as NULL, not `""` (a change from
  SaveData's empty-string convention — SQL predicates read better).
- **Permissiveness**: TEXT everywhere identifiers appear; no FK constraint
  enforcement (`PRAGMA foreign_keys=OFF`) because modded saves reference
  macros/factions/wares the reference tables have never heard of. FKs below
  are documentation, not constraints.
- Booleans are INTEGER 0/1.

## Core dimension

```sql
CREATE TABLE meta (            -- schema bookkeeping
  key   TEXT PRIMARY KEY,      -- 'schema_version', 'created_by', ...
  value TEXT
);

CREATE TABLE save (            -- one row per imported snapshot
  save_id       INTEGER PRIMARY KEY,   -- autoincrement rowid
  guid          TEXT NOT NULL,         -- /savegame/info/game@guid
  game_version  TEXT,                  -- game@version
  game_time     REAL,                  -- game@time (seconds)
  save_date     TEXT,                  -- save@date (unix epoch)
  modified      INTEGER,               -- game@modified
  player_name   TEXT,                  -- player@name
  player_money_cr REAL,                -- player@money / 100
  faction_name  TEXT,                  -- faction[player]/custom/name@name
  source_file   TEXT,                  -- path of the parsed save
  imported_at   TEXT                   -- wall-clock ISO timestamp
);
```

The **current snapshot** is `MAX(save_id)`; views below implicitly filter
to it. Older snapshots exist only if snapshot retention is enabled
(feasibility doc §4.2), and pruning is `DELETE FROM <W-table> WHERE
save_id < ?`.

## World state (W — rebuilt per snapshot)

### component

One row per universe object the parser keeps: clusters, sectors, stations,
build storages, all `ship_*` classes. Provenance: `<component>` attributes;
ancestry from the parse-time element stack.

```sql
CREATE TABLE component (
  save_id       INTEGER NOT NULL,
  id            TEXT NOT NULL,      -- @id, e.g. '[0x1a2b]'
  class         TEXT NOT NULL,      -- @class: cluster|sector|station|buildstorage|ship_xs..ship_xl
  macro         TEXT,               -- @macro, lowercased
  name          TEXT,               -- @name (may be a {page,id} text ref)
  basename      TEXT,               -- @basename
  code          TEXT,               -- @code, e.g. 'ATO-898'
  owner         TEXT,               -- @owner faction id
  knownto       TEXT,               -- @knownto ('player' = discovered)
  contested     INTEGER,            -- @contested
  spawntime     REAL,               -- @spawntime (game seconds; NULL for pre-existing)
  parent_id     TEXT,               -- NEW: enclosing component (containment tree)
  cluster_id    TEXT, cluster_macro TEXT,   -- denormalized ancestry, kept for
  sector_id     TEXT, sector_macro  TEXT,   -- cheap filtering without recursion
  PRIMARY KEY (save_id, id)
);
```

`parent_id` is the one net-new parser field: the nearest **collected**
ancestor on the parse-time component stack (not the immediate XML parent —
saves interpose `zone`/`dockingbay` components that never become rows). It
stores real containment (ship docked at station, station in sector), which
the flattened cluster/sector columns can't express, and always resolves
within the table (NULL at the tree root).

### Fleet hierarchy

Resolved at load time from the two raw link lists (follower's
`<connected connection="[X]">` matched to commander's
`<connection connection="subordinates" id="[X]">`) into what we actually
mean:

```sql
CREATE TABLE fleet_edge (
  save_id      INTEGER NOT NULL,
  follower_id  TEXT NOT NULL,      -- ship component.id
  commander_id TEXT NOT NULL,      -- direct commander component.id
  PRIMARY KEY (save_id, follower_id)
);
```

The raw conn-id pairs are not stored; the resolution join is done once
during load (it is unambiguous), and storing the resolved edge makes the
recursive fleet CTE self-contained.

### Station composition

```sql
CREATE TABLE module (            -- construction-sequence entries
  save_id      INTEGER NOT NULL,
  host_id      TEXT NOT NULL,    -- station or buildstorage component.id
  entry_id     TEXT,             -- <entry>@id (plan-entry identity)
  idx          INTEGER,          -- @index
  macro        TEXT,             -- @macro, lowercased -> module_ref.macro
  build_method TEXT,             -- enclosing <build>@method
  built        INTEGER NOT NULL  -- 1 if a finished component references this
                                 -- entry via @construction (state !=
                                 -- "construction"); folds the built_refs list
);
-- rows are deduped by (host_id, entry_id) at load: stations list their plan
-- twice (construction sequence + expand queue). See CLAUDE.md gotcha.
CREATE INDEX idx_module_host ON module(save_id, host_id);

CREATE TABLE module_upgrade (    -- planned loadout equipment per plan entry
  save_id  INTEGER NOT NULL,
  entry_id TEXT NOT NULL,        -- module.entry_id
  equipment_macro TEXT NOT NULL  -- <shields|turrets|engines>@macro under <groups>
);

CREATE TABLE workforce (
  save_id    INTEGER NOT NULL,
  station_id TEXT NOT NULL,
  race       TEXT NOT NULL,      -- <workforce>@race
  amount     REAL,               -- @amount
  PRIMARY KEY (save_id, station_id, race)
);
```

### Crew and people

```sql
CREATE TABLE npc (               -- player-owned named NPCs only
  save_id INTEGER NOT NULL,
  id      TEXT NOT NULL,         -- npc component @id
  name    TEXT, code TEXT, owner TEXT,
  PRIMARY KEY (save_id, id)
);

CREATE TABLE npc_skill (         -- long form; v_npc pivots wide
  save_id INTEGER NOT NULL,
  npc_id  TEXT NOT NULL,
  skill   TEXT NOT NULL,         -- <skills> attr name: piloting, morale, ...
  value   REAL,
  PRIMARY KEY (save_id, npc_id, skill)
);

CREATE TABLE post (              -- crew assignments
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,       -- station/ship component.id
  post      TEXT NOT NULL,       -- <control><post>@id: manager|aipilot|engineer|...
  npc_id    TEXT                 -- @component -> npc.id
);

CREATE TABLE people (            -- anonymous headcount aboard
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  role      TEXT NOT NULL,       -- <person>@role: service|marine|passenger|prisoner
  count     INTEGER NOT NULL,
  PRIMARY KEY (save_id, object_id, role)
);
```

### Economy state

```sql
CREATE TABLE cargo (             -- <cargo><ware> under nearest station/ship/buildstorage
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  ware      TEXT NOT NULL,
  amount    REAL,
  PRIMARY KEY (save_id, object_id, ware)
);

CREATE TABLE trade_offer (       -- open offers: <trade> under <offers>
  save_id   INTEGER NOT NULL,
  object_id TEXT NOT NULL,
  side      TEXT NOT NULL,       -- 'buy' (@buyer set) | 'sell' (@seller set)
  ware      TEXT NOT NULL,
  amount    REAL,                -- @amount
  price_cr  REAL                 -- @price / 100
);
CREATE INDEX idx_offer_ware ON trade_offer(save_id, ware);

CREATE TABLE build_resource (    -- missing construction materials
  save_id INTEGER NOT NULL,
  host_id TEXT,                  -- nearest station/buildstorage/ship; NULL if none
  ware    TEXT NOT NULL,
  amount  REAL,
  kind    TEXT NOT NULL          -- 'insufficient' | 'shortage'
);
-- only <build type=""|"build"> blocks; buildship aggregates are excluded at
-- parse (wharf-wide garbage — see CLAUDE.md). Consumers still max-dedupe
-- per (host, ware).

CREATE TABLE ship_order (        -- order queues ("order" is reserved-ish; renamed)
  save_id    INTEGER NOT NULL,
  object_id  TEXT NOT NULL,
  order_name TEXT NOT NULL,      -- <order>@order
  is_default INTEGER NOT NULL,   -- @default == "1"
  state      TEXT                -- @state
);

CREATE TABLE resource (          -- sector resource areas (v9 yieldid format)
  save_id      INTEGER NOT NULL,
  sector_macro TEXT NOT NULL,
  ware         TEXT NOT NULL,    -- parsed out of <area>@yieldid
  yield        REAL              -- summed <area>@yield
);

CREATE TABLE floating_ware (     -- scrap cubes / dropped cargo in space
  save_id      INTEGER NOT NULL,
  sector_macro TEXT,
  ware         TEXT NOT NULL,
  amount       REAL
);
-- only classes recyclable|collectablewares|lockbox; <supplies><wares>
-- (ship ammo reserves) are excluded at parse.
```

## Event history (E — merged across runs, replaces csv.gz caches)

The save's log/economylog are rolling windows; these tables preserve what
the game has already discarded. **Never dropped on rebuild.** Both keep a
`raw_attrs` JSON column (full original attribute dict) so game wording or
attribute drift can never lose data — SQLite's `json_extract` can query it.

The economylog's `type="trade"` entries are **two different record types**
and get two tables (fixing a modeling wart the current code handles with
row filters):

Both trade tables carry two things the raw window can't provide later:
**save-stable identity** (runtime `[0x..]` ids are remapped on every game
load, so each party is resolved to `(faction, code, name)` at merge time —
the only moment its id is unambiguous; NULL when unresolvable) and a
**coverage `epoch`** (incremented when a merged window does not overlap the
stored history, i.e. the game discarded events in between — delta queries
must not span that gap).

```sql
CREATE TABLE trade_tx (          -- real transactions: buyer AND seller AND price
  time      REAL NOT NULL,       -- <log>@time
  ware      TEXT NOT NULL,
  buyer_id  TEXT,                -- @buyer component id
  seller_id TEXT,                -- @seller component id
  price_cr  REAL,                -- @price / 100
  amount    REAL,                -- @v — here v IS a traded amount
  raw_attrs TEXT,                -- JSON
  buyer_faction TEXT, buyer_code TEXT, buyer_name TEXT,    -- resolved at merge
  seller_faction TEXT, seller_code TEXT, seller_name TEXT,
  epoch     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_tx_time ON trade_tx(time);
CREATE INDEX idx_tx_ware ON trade_tx(ware);

CREATE TABLE stock_event (       -- owner-only entries: stock level snapshots
  time      REAL NOT NULL,
  owner_id  TEXT NOT NULL,       -- @owner component id
  ware      TEXT NOT NULL,
  level     REAL,                -- @v — here v is the stock AFTER a trade,
  raw_attrs TEXT,                -- NOT an amount (overcounts ~40x if summed)
  owner_faction TEXT, owner_code TEXT, owner_name TEXT,    -- resolved at merge
  epoch     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_stock ON stock_event(owner_id, ware, time);

CREATE TABLE log_entry (         -- /savegame/log/entry
  time        REAL NOT NULL,
  category    TEXT,              -- @category ('' | upkeep | ...)
  title       TEXT,
  text        TEXT,
  faction     TEXT,
  money_cr    REAL,              -- @money / 100
  interaction TEXT,
  component_id TEXT,             -- @component
  highlighted TEXT,
  raw_attrs   TEXT
);
CREATE INDEX idx_log_time ON log_entry(category, time);

CREATE TABLE removed_object (    -- /savegame/economylog/removed/object
  time  REAL,
  id    TEXT, name TEXT, code TEXT, owner TEXT,
  raw_attrs TEXT
);
```

**Merge semantics** (ported verbatim from `db/caches.py`, executed as one
transaction per table so a crash never half-merges):

- `log_entry`: for each category in the fresh window, `DELETE WHERE
  category = ? AND time >= <oldest new time for that category>`, then bulk
  INSERT the window; dedupe on the full natural row.
- `trade_tx` / `stock_event`: the new window is authoritative from its
  oldest timestamp on — `DELETE WHERE time >= <oldest new time>` then bulk
  INSERT, except that cached rows at exactly that timestamp survive when
  the new window is thinner there (the game dropped same-timestamp
  siblings the cache still knows). Each merge records the window start in
  `meta` (`<table>_window_start`) so dashboard rate math can scope to the
  current window, and stamps rows with the coverage `epoch`.
- Idempotence (run twice on the same save = no change) is the existing
  cache contract and becomes a direct SQL test.
- E-table schema changes are additive `ALTER TABLE`s applied on version
  bump (`db/schema.py` `EVENT_MIGRATIONS`); pre-migration rows keep NULL
  identity and epoch 0, degrading to per-id behavior.

## Reference data (R — from extract-gamedata, replaced wholesale)

Column-for-column the packaged CSVs; loaded into the DB so save data joins
game data without pandas merges.

```sql
CREATE TABLE ware (        -- wares.csv
  id TEXT PRIMARY KEY, name TEXT, grp TEXT,       -- 'group' renamed
  transport TEXT,          -- container|solid|liquid|...
  volume REAL,             -- m3 per unit
  tags TEXT, price_avg REAL,
  component TEXT,          -- module macro this ware builds (module<->ware link)
  source TEXT              -- base | ego_dlc_*
);

CREATE TABLE recipe (      -- recipes.csv: one row per (ware, method, input)
  ware TEXT NOT NULL, method TEXT NOT NULL,       -- method: default|terran|processing|workunit_busy|...
  time REAL, amount REAL,                          -- output per cycle
  input_ware TEXT, input_amount REAL
);
CREATE INDEX idx_recipe ON recipe(ware, method);

CREATE TABLE module_ref (  -- modules.csv: production/processing modules
  macro TEXT NOT NULL, name TEXT,
  ware TEXT, method TEXT,  -- what one queue option produces
  scale REAL,              -- processing-module recipe multiplier
  workforce REAL, source TEXT
);                          -- one row PER queue option: macro is NOT unique

CREATE TABLE ship_ref (    -- ships.csv
  macro TEXT PRIMARY KEY, model TEXT, class TEXT, race TEXT,
  purpose TEXT, hull REAL, mass REAL, cargo REAL, crew REAL,
  price REAL, source TEXT
);

CREATE TABLE faction (     -- factions.csv
  id TEXT PRIMARY KEY, shortname TEXT, name TEXT,
  primaryrace TEXT, colour TEXT, source TEXT
);

CREATE TABLE cluster_ref ( -- clusters.csv
  macro TEXT PRIMARY KEY, x REAL, y REAL, z REAL,
  name TEXT, description TEXT, source TEXT
);

CREATE TABLE sector_ref (  -- sectors.csv
  cluster TEXT, macro TEXT PRIMARY KEY,
  x REAL, y REAL, z REAL, name TEXT, source TEXT
);

CREATE TABLE gate (        -- gates.csv: sector adjacency (undirected pairs)
  sector_a TEXT NOT NULL, sector_b TEXT NOT NULL, source TEXT
);

CREATE TABLE modcap (      -- modcaps.csv: module housing/storage capacities
  macro TEXT PRIMARY KEY, class TEXT,
  housing REAL, workers REAL, cargo_max REAL, cargo_tags TEXT
);

CREATE TABLE text (        -- textdb.csv.gz: localization dump (~71k rows)
  page INTEGER NOT NULL, tid INTEGER NOT NULL, text TEXT,
  PRIMARY KEY (page, tid)
);
```

## Derived tables (D — rebuilt every run from E tables)

`logparse.py`'s regex extraction stays in Python (English wording,
version-sensitive) but its output is materialized so SQL sees it:

```sql
CREATE TABLE event_destroyed  (time REAL, victim TEXT, victim_code TEXT,
                               attacker TEXT, sector TEXT);
CREATE TABLE event_construction (time REAL, ship TEXT, code TEXT,
                               wharf TEXT, kind TEXT);  -- construct|repair|resupply
CREATE TABLE event_transfer   (time REAL, money_cr REAL, station TEXT);
CREATE TABLE event_pirate     (time REAL, sector_macro TEXT);
CREATE TABLE event_police     (time REAL, faction TEXT, sector_macro TEXT);
```

Cheap to rebuild (regex over `log_entry`), so no migration burden.

## Views (the frames.py replacement layer)

Definitions live in the schema module and are (re)created at connect time;
all filter to the current snapshot via `save_id = (SELECT MAX(save_id) FROM
save)`. The load-bearing ones:

```sql
-- resolved universe: names via textdb refs already resolved at load,
-- sector/cluster display names, faction shortnames
CREATE VIEW v_universe AS
SELECT c.*, s.name AS sector_name, f.shortname AS owner_code
FROM component c
LEFT JOIN sector_ref s ON s.macro = c.sector_macro
LEFT JOIN faction f    ON f.id = c.owner
WHERE c.save_id = (SELECT MAX(save_id) FROM save);

-- transitive fleet membership (validated: 34 ms on the real save)
CREATE VIEW v_fleet AS
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
         AS is_root_edge                       -- cmdr is the fleet root here
FROM chain;

-- market traded volume: positive stock deltas (validated: 100 ms).
-- Partitioned by the save-stable identity so a station's series heals
-- across game sessions (ids drift, faction|code doesn't) and by epoch so
-- deltas never span a coverage gap; rowid breaks time ties in save order.
-- level/dv_neg columns beyond dv: the Market actual-flows mode needs
-- stock leaving the station too.
CREATE VIEW v_stock_delta AS
SELECT owner_id, owner_faction, owner_code, owner_name, ware, time, level,
       epoch,
       MAX(level - LAG(level) OVER w, 0) AS dv,
       MAX(LAG(level) OVER w - level, 0) AS dv_neg
FROM stock_event
WHERE ware != ''
WINDOW w AS (PARTITION BY COALESCE(owner_faction || '|' || owner_code,
                                   owner_id),
             ware, epoch ORDER BY time, rowid);

-- built modules only (the "measure reality, not plans" gotcha)
CREATE VIEW v_built_module AS
SELECT * FROM module
WHERE built = 1 AND save_id = (SELECT MAX(save_id) FROM save);

-- wide NPC skills for the crew tables
CREATE VIEW v_npc AS
SELECT n.*,
  MAX(CASE WHEN s.skill='piloting'    THEN s.value END) AS piloting,
  MAX(CASE WHEN s.skill='engineering' THEN s.value END) AS engineering,
  MAX(CASE WHEN s.skill='boarding'    THEN s.value END) AS boarding,
  MAX(CASE WHEN s.skill='management'  THEN s.value END) AS management,
  MAX(CASE WHEN s.skill='morale'      THEN s.value END) AS morale
FROM npc n LEFT JOIN npc_skill s
  ON s.save_id = n.save_id AND s.npc_id = n.id
WHERE n.save_id = (SELECT MAX(save_id) FROM save)
GROUP BY n.save_id, n.id;
```

Further candidates (added as viz modules are ported): `v_station`
(modules + workforce + crew aggregates), `v_playerowned`, `v_sales`/
`v_buys` (PLA-vs-other split of `trade_tx`), `v_sector_demand`.

## Relationships at a glance

```
save 1──n component ──self── parent_id (containment)
             │ id
   ┌─────────┼──────────┬────────────┬───────────┐
   │         │          │            │           │
 cargo   trade_offer  module      fleet_edge   post ── npc ── npc_skill
                        │ entry_id             people, workforce, ship_order
                        └── module_upgrade     build_resource
component.macro ─▶ ship_ref.macro / module_ref.macro (via ware.component)
component.owner ─▶ faction.id        component.sector_macro ─▶ sector_ref.macro
cargo.ware / trade_offer.ware / recipe.ware ─▶ ware.id
trade_tx.buyer_id/seller_id, stock_event.owner_id ─▶ component.id
  (dangling allowed: objects die; removed_object + log history explain them)
gate.sector_a/b ─▶ sector_ref.macro  (sector adjacency graph)
```

Dangling references are **normal**, not errors: event history outlives the
objects it mentions, and modded content references unknown macros. Every
join in the view layer is a LEFT JOIN with COALESCE fallbacks, mirroring
frames.py's defensive-join convention.

## Sizing (measured, save_008)

| Table | Rows | Notes |
|---|---|---|
| module_upgrade | 192,849 | largest table, 9.7 MB |
| trade_tx + stock_event | 82,491 | grows with history retention |
| module | 38,663 | |
| post | 26,939 | |
| built (folded into module) | 22,943 | |
| ship_order | 18,035 | |
| component | 18,280 | 2.8 MB |
| everything else | < 14 k each | |
| **whole DB** | ~450 k rows | **27.8 MB**, written in 0.4 s |
