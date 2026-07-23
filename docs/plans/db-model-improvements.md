# DB model improvements: critique and target design

Status: **proposal** (2026-07-23). Review of the analysis-database model at
schema/store/frames depth, and a target design reachable by incremental
migration. Companion to [db-schema.md](../reference/db-schema.md) (what is)
— this document is *what should change and why*. Nothing here is
implemented; every proposal states its migration path.

Design goals, in priority order:

1. **Live/serve mode readiness** — incremental updates while the game runs
   (the watch/analyzer-split direction from the parked `live-db-spike`
   branch), repeated cheap queries against changing state, readers and the
   writer coexisting.
2. **Ad-hoc analytical SQL** — the ontology should read naturally in
   hand-written queries: game-domain names, obvious join paths, no pandas
   required for common questions.

Constraints kept throughout: SQLite, `pd.read_sql` consumption, slim
dependencies, no ORM, no engine swap. Event history is preserved by every
proposal — **no change below loses history** (a few explicitly discard
derivable data that rebuilds from the next run, which is stated inline).

---

## 1. Current-model critique

Each finding cites the code it lives in. Severity is about how much the
finding fights the two design goals, not code quality — most of these are
deliberate, documented decisions that made sense for a one-shot batch
pipeline and stop making sense for live mode.

### C1. World state is single-snapshot: no trends, nothing to serve incrementally

`store.write_snapshot` deletes **all** W-table rows before every import
(`store.py:192-193`, comment: "phases 1-3 keep only the latest snapshot;
retention is phase 5"). The `save` table accumulates one row per import,
but it is the *only* record older imports happened — `DISTINCT save_id`
in `component` is always one value. The live-db-spike inventory
(`live-db-features.md` on branch `live-db-spike`) measured the
consequence directly: 46 analyzed runs, zero cross-snapshot world data;
every trend-shaped feature (territory pressure, fleet attrition, market
price evolution, empire net worth) is blocked. For live mode this is the
single most limiting property: a watcher that analyzes every autosave
produces a dense stream of snapshots and the schema throws each one away.

Full snapshot retention is the wrong fix (≈120 MB × N). The right fix is
**append-only aggregate history** written per snapshot — see T4.

### C2. The current-snapshot concept is a repeated idiom, not a name

Every view filters with `(SELECT MAX(save_id) FROM save)`
(`schema.py:518-598`, eight occurrences) and `frames.py` interpolates the
same subquery as `_CUR` into ~20 query strings (`frames.py:124`).
Hand-written SQL must know and repeat the trick; there is no
`current_save` to join. Cosmetic, but it is the first thing every ad-hoc
query trips over. See T1.

### C3. The entity registry is not joined to the world it describes

The registry is the model's best idea — surrogate identity over recycled
codes and remapping runtime ids — and the **snapshot tables cannot reach
it**. `component` carries no `entity_id` (`schema.py:115-134`);
db-schema.md says it outright: "Event rows are stamped with entity ids at
merge time; `component` rows are not (join through code+class or via the
event tables)". The cause is pipeline ordering: `write_snapshot` runs
before `update_entity_registry` (`analyze.py:32-33`), and the mapping the
registry returns (`store.py:389+`) is used only to stamp event rows
(`merge_events`, `store.py:524+`).

Consequences: "show this station's stock history" requires a
code+class join that is exactly the unreliable join the registry exists
to replace; the entity graveyard cannot say "which of these is on the map
right now" without string matching; fleet edges, cargo, offers, orders —
every per-object W table — key on runtime ids that mean nothing across
snapshots. This is the highest-leverage single change available: one
column turns `entity` into the hub of the whole schema. See T2.

### C4. Event-stream coverage lives in `meta` strings and an unexplained column

Coverage/provenance — *which time ranges does the history actually
cover* — is a first-class analytical concept (every rate denominator
needs it, every gap must be visible) but is smeared across:

- `meta.trade_tx_window_start` / `meta.stock_event_window_start`,
  stringly-typed (`store.py:746-748`), read back with a raw `meta` lookup
  in `frames.py:566-571`;
- the `epoch` column on `trade_tx`/`stock_event`, which marks gaps but has
  no table describing what an epoch spans;
- `log_entry`, which has per-category windows (`store.py:634-643`) and
  **no epoch column at all** — a coverage gap in the logbook is silently
  invisible.

Ad-hoc SQL cannot answer "what stretches of the playthrough do I have
trade data for?" without window-aggregating the event tables. See T3.

### C5. `v_stock_delta` partitions on a string concat and scans unindexed

The view partitions its LAG by
`COALESCE(owner_faction || '|' || owner_code, owner_id)`
(`schema.py:542-551`) — a synthesized text identity — although 99.3 % of
rows carry `owner_entity` (measured in `live-db-features.md`), the exact
durable identity the registry mints. And the only stock index is
`idx_stock ON stock_event(owner_id, ware, time)` (`schema.py:500`), which
serves the *merge* but not the *analysis*: per-station history by durable
identity was measured at 30 ms/station and the full delta scan at 888 ms
— the one interactive-latency failure in the spike's endpoint table. See
T6 + the index in T2.

### C6. Frames re-derives in pandas what the schema already knows

`analysis/frames.py` contains several blocks that are relational work
done in pandas, per run, invisible to SQL consumers:

- **Trade display-name re-resolution and proxy redirect**
  (`frames.py:456-513`): re-resolving each party's current name (entity
  registry first, then latest-name-per-code, then stored), then melting
  the wide `trade_tx` columns into commander-redirected `buyer.*` /
  `seller.*` / `*.proxy.*` columns. This is a view — the "Executed by"
  attribution rule is a `COALESCE(cmdr_entity, entity)`. See T6/v_trade.
- **`global_trades` enrichment** (`frames.py:566-616`): mapping
  `owner_id` → universe columns, falling back to `removed_object`, a
  dagger flag, a faction-short label, an unnamed-station synthesized name.
  Three-way identity resolution done in pandas maps, again per run. See
  T6/v_stock_flow.
- **Faction standing pivot** (`frames.py:624-651`): effective standing =
  base + boosters clamped to [−1, 1] — a three-line GROUP BY. See T7.
- **Resource-area classification** (`frames.py:212-283`): the
  live/full/respawning/never state machine needs `(level, ware) →
  (capacity, respawndelay)` from `ref.region_yields`
  (`gamedata/refdata.py:142`) — reference data that exists as a packaged
  CSV (`regionyields.csv`, csv-reference.md) but was never loaded into
  the DB (`schema.py:85-88`), so the classification *cannot* be SQL
  today. See T9.
- **Station rollups** (`frames.py:336-366, 380-388`): workforce pivots,
  crew sums, module counts, the hull/mass estimate (`modules × 250_000`,
  `frames.py:333-334`) — assembled in pandas each run, unavailable to a
  `SELECT`. See T8.
- **`station_types`** (`frames.py:137-176`) is computed **twice per
  run** — once via `station_types_from_db` before the merge
  (`analyze.py:35`) and again inside `build_frames`
  (`frames.py:327-328`).

None of these are wrong for a dashboard build; all of them mean the
serve-mode API and any hand-written query get a dumber database than the
dashboard does.

### C7. Fleet-edge resolution is implemented twice

`write_snapshot` resolves follower→commander from
`save.commander_links`/`save.subordinate_conns` (`store.py:213-231`), and
`_player_edges` does the same matching again, independently, for merge
attribution (`store.py:596-610`) — same algorithm, different filters,
diverging warning behavior (the first warns on conflicts, the second
silently `setdefault`s). `frames.wings` then re-filters the table to
player-owned in pandas (`frames.py:295-299`). One resolution, one table,
one player-filtered view. See T2/T8.

### C8. Import-run and snapshot are conflated in `save`

`save` gets a row per *import*, not per *distinct save*: the spike DB had
46 rows for 2 distinct saves. Any series keyed on `save` (the
player-money series, and every aggregate-history table T4 proposes) is
polluted by dashboard-dev reruns. There is no is-rerun signal and no
distinct-snapshot view. See T5.

### C9. View lifecycle fights read-only consumers

Views are dropped and recreated at **every connect**
(`store.py:82-85`) — a write. The serve prototype had to work around
this by re-declaring every view as TEMP on its read-only connections
(`live-db-plan.md`: "DBs opened mode=ro with TEMP view definitions"),
duplicating the definitions. A live-mode reader should be able to open
`mode=ro` and see current views. Also missing for live mode: WAL journal
mode (writer blocks readers under the default rollback journal),
`busy_timeout`. See T10.

### C10. Naming fights the domain

- `module` holds **build-plan entries**, not modules — the name is the
  direct cause of the "capacity nearly 2× reality" gotcha that CLAUDE.md
  has to warn about (unbuilt plan entries counted as modules); the
  catalog table is `module_ref` and the capacity table `modcap`.
- Suffix conventions are mixed: `sector_ref`/`cluster_ref`/`ship_ref`/
  `module_ref` vs bare `ware`/`faction`/`gate`/`recipe`/`modcap`.
- `faction_meta.account` is the one raw-cents money column in a schema
  whose stated convention is `_cr` credits (db-schema.md § Conventions;
  `schema.py:289-294`).
- `trade_offer.object_id` keeps `''` instead of NULL — the one deliberate
  empty-string exception (`store.py:296-300`).
- `trade_tx.ware`/`stock_event.ware` use `''` for absent
  (`store.py:686,697`) against the schema-wide NULL convention.
- `npc` is player-employees-only but the name doesn't say so.

Individually trivial; together they are why ad-hoc SQL against this DB
needs the reference doc open. See T11.

### C11. Small defects worth folding into any migration pass

- `log_entry.interaction` is never populated — loader reads `interaction`
  where the save writes `interact` (db-schema.md § Defined-but-never-
  populated; `schema.py:350`). The value survives in `raw_attrs` JSON and
  is backfillable with `json_extract`. See T12.
- Schema resets drop only *current* table names (`store.py:70-74`), so
  renamed tables become zombies — the reference DB carries
  `station_drones` + its index (db-schema.md § Schema versioning). See
  T13.
- `removed_object` rows record no provenance of when they were first
  merged (their save-side `time` attr doesn't exist in v9, so the DB-side
  arrival save is the only timestamp obtainable). See T13.

---

## 2. Ontology assessment

Does the schema carry the concepts the analysis is *about*? Concept by
concept:

| Concept | Where it lives today | Verdict |
|---|---|---|
| **Entity lifecycle** | `entity` + `entity_event` | **Good core, isolated.** Lifespan bounds, capture/rename events, recycled-slot semantics — the best-modeled concept in the DB. But it is reachable only from event rows (C3), and lifecycle *state transitions* are half table-columns (`gone_time`/`gone_reason`, reopening resets them losing the fact a disappearance ever happened) and half events. |
| **Ownership** | `component.owner` (now), `entity.owner` (current) + `captured` events (history) | **Adequate.** Ownership history exists per entity; faction-level rollups (territory) don't — see below. |
| **Station economics** | Smeared: `cargo`, `trade_offer`, `workforce`, `module`, `build_resource`, `station_storage`, `station_munition` + pandas rollups (C6) | **Present but unassembled.** Every ingredient exists; no station-level object a query can `SELECT` from. No history of any of it (C1). |
| **Market offers** | `trade_offer` (snapshot only) | **Half-modeled.** The offer *book* of the current instant exists; offer/price *evolution* is discarded every import. NPC↔NPC trades are structurally absent from the save's economylog (savegame-structure.md § economylog: owner-only stock flavor) — offer history is the only obtainable NPC price signal, and we throw it away. |
| **Trade history** | `trade_tx` (player-involved, entity-linked, commander-attributed) | **Good**, with the display/attribution logic trapped in frames (C6) and the party model denormalized into 23 columns — tolerable, but only a view makes it queryable in domain terms. |
| **Stock flows** | `stock_event` + `v_stock_delta` | **Good data, weak access path** (C5). This is half the DB by bytes and the only universe-wide economic signal. |
| **Fleet hierarchy** | `fleet_edge` (runtime ids, snapshot), `v_fleet` closure, `*_cmdr_*` frozen into trade rows | **Snapshot-only and id-fragile.** No durable (entity-level) fleet membership; merge-time freezing into trade rows is the right call for attribution but is the *only* fleet history that exists. |
| **Sector territory** | Nowhere. `component.sector_macro` + owner enables the 9.5 ms presence query (spike), but no table/view names the concept; the map computes it in Python per build | **Missing.** Highest-value absent concept, and the cheapest history to keep (T4). |
| **Coverage/provenance of evidence** | `epoch` columns + `meta` strings + `save.source_file` | **Implicit** (C4). The model *has* the discipline (epochs, merge cutoffs, registry high-water mark) but no queryable representation of it. |
| **Player empire over time** | `save.player_money_cr` per import | **Accidental.** One useful series exists because `save` happens to accumulate; polluted by reruns (C8). |

Summary: identity and event history — the hard parts — are genuinely well
modeled. What's missing is (a) the *joins* that let the good parts reach
each other (entity ↔ snapshot), (b) *time depth* for anything outside the
economylog (territory, offers, station metrics), and (c) *SQL-visible
assemblies* of concepts the frames layer builds privately. The target
design is those three things.

---

## 3. Target design

Ten changes, T1–T13, each with DDL sketch, rationale, and migration
notes. Migration mechanics use the existing machinery: W/R/D tables are
drop-and-recreate on a `SCHEMA_VERSION` bump (free — that is the designed
path, `store.py:70-74`), E tables take targeted statements via
`EVENT_MIGRATIONS` (`schema.py:38-75`; the values are arbitrary SQL
tuples, so `UPDATE`/`CREATE INDEX` work there too). New table classes
introduced: **A — accumulated aggregates** (append-only per snapshot,
never dropped, migrated like E tables).

### T1. Name the current snapshot

```sql
CREATE VIEW current_save AS
SELECT MAX(save_id) AS save_id FROM save;
```

Every view and every hand-written query becomes
`WHERE save_id = (SELECT save_id FROM current_save)`. Pure ergonomics,
zero risk, and the one place to change if current-snapshot semantics ever
change (see T5).

*Migration:* add to `VIEWS`. Independent.

### T2. Entity spine: `component.entity_id`

```sql
-- component (fresh W DDL, one added column + indices)
CREATE TABLE component (
  -- ... all existing columns ...
  entity_id INTEGER            -- FK entity.entity_id (doc only), NULL when
                               -- outside the registry domain (sectors,
                               -- clusters) or unresolvable
);
CREATE INDEX idx_component_entity ON component(save_id, entity_id);
CREATE INDEX idx_component_class  ON component(save_id, class, owner);
CREATE INDEX idx_component_sector ON component(save_id, sector_macro);
```

Pipeline change: run `update_entity_registry` **before** `write_snapshot`
(or apply the returned mapping with an `UPDATE component` immediately
after — equivalent; reordering is cleaner). The registry deliberately
covers connectionless components too, so its mapping is a superset of
`component` rows — every station/ship/buildstorage row gets its
`entity_id`.

This one column makes the registry the hub it was built to be:

```sql
-- a station's full stock history, durable identity, one join
SELECT s.time, s.level
FROM component c JOIN stock_event s ON s.owner_entity = c.entity_id
WHERE c.save_id = (SELECT save_id FROM current_save)
  AND c.code = 'ABC-123' AND s.ware = 'energycells'
ORDER BY s.time;
```

Also in this change, because they're the same spine:

```sql
-- durable event-table access paths (E-table index adds, no data change)
CREATE INDEX idx_stock_entity ON stock_event(owner_entity, ware, time);
CREATE INDEX idx_tx_buyer  ON trade_tx(buyer_entity)  WHERE buyer_entity  IS NOT NULL;
CREATE INDEX idx_tx_seller ON trade_tx(seller_entity) WHERE seller_entity IS NOT NULL;
```

*Migration:* W rebuild (free) + `CREATE INDEX` on E tables via
`EVENT_MIGRATIONS` (safe, no data touched). Fixes C3, C5's index half,
and unblocks T4/T6/T8. **Independent; most other changes want it.**

### T3. Coverage as a table

```sql
-- E-class: bookkeeping of what the event history covers; never dropped
CREATE TABLE IF NOT EXISTS coverage (
  stream       TEXT NOT NULL,   -- 'trade_tx' | 'stock_event' | 'log:<category>'
  epoch        INTEGER NOT NULL,
  t_min        REAL NOT NULL,   -- covered interval (game seconds)
  t_max        REAL NOT NULL,
  window_start REAL,            -- most recent merged window's start
                                -- (rate denominators), newest epoch only
  updated_save_id INTEGER,      -- provenance: which import last extended it
  PRIMARY KEY (stream, epoch)
);
```

The merge updates its stream's newest epoch row (extending `t_max`,
setting `window_start`) or inserts a new epoch row when it detects a gap
— exactly where `_merge_window` computes epochs today
(`store.py:722-748`). `log_entry` gets per-category streams, giving the
logbook the gap-awareness it currently lacks (C4).

Replaces `meta.trade_tx_window_start` / `meta.stock_event_window_start`;
`frames.py:566-571` reads the table instead. Ad-hoc SQL gains: "what does
my history cover?" is a `SELECT * FROM coverage`.

*Migration:* `CREATE TABLE` + one-time backfill inside the version bump:

```sql
INSERT INTO coverage (stream, epoch, t_min, t_max)
  SELECT 'trade_tx', epoch, MIN(time), MAX(time) FROM trade_tx GROUP BY epoch;
INSERT INTO coverage (stream, epoch, t_min, t_max)
  SELECT 'stock_event', epoch, MIN(time), MAX(time) FROM stock_event GROUP BY epoch;
INSERT INTO coverage (stream, epoch, t_min, t_max)
  SELECT 'log:' || COALESCE(category, ''), 0, MIN(time), MAX(time)
  FROM log_entry GROUP BY category;
```

then seed `window_start` from the two meta keys and delete them. No
history loss. Independent (better with T5's rerun guard).

### T4. Aggregate history: the trend layer (A-class tables)

The C1 fix. Not snapshot retention — small append-only aggregates written
once per *distinct* snapshot (guard from T5), sized so a dense autosave
stream is cheap. All rows carry `save_id`; joining `save.game_time` gives
the time axis.

```sql
-- territory & military presence: ~1,500 rows / snapshot (measured shape:
-- the spike's 9.5 ms heatmap query), ≈60 KB per snapshot
CREATE TABLE IF NOT EXISTS sector_presence (
  save_id      INTEGER NOT NULL,
  sector_macro TEXT,
  owner        TEXT,
  class        TEXT NOT NULL,       -- station | ship_xl | ship_l | ...
  n            INTEGER NOT NULL,
  PRIMARY KEY (save_id, sector_macro, owner, class)
);

-- per-player-station economics: one row per station per snapshot
CREATE TABLE IF NOT EXISTS station_metric (
  save_id       INTEGER NOT NULL,
  entity_id     INTEGER NOT NULL,   -- durable station identity (T2)
  workforce     REAL,               -- Σ workforce.amount
  modules_built INTEGER,            -- COUNT(module WHERE built=1)
  cargo_value_cr REAL,              -- Σ cargo.amount × ware.price_avg
  buy_open_cr   REAL,               -- Σ open buy offers × price
  sell_open_cr  REAL,               -- Σ open sell offers × price
  PRIMARY KEY (save_id, entity_id)
);

-- market history, sector granularity: per (sector, ware, side) price
-- band + open volume. ~63 wares × active sectors × 2 ≈ 3–6 k rows
-- per snapshot. THE only obtainable NPC price signal over time —
-- the save's economylog carries no NPC↔NPC transactions
-- (savegame-structure.md § economylog), but the offer book is complete
-- every snapshot.
CREATE TABLE IF NOT EXISTS market_stat (
  save_id      INTEGER NOT NULL,
  sector_macro TEXT,
  ware         TEXT NOT NULL,
  side         TEXT NOT NULL,       -- buy | sell
  n_offers     INTEGER NOT NULL,
  units        REAL,                -- Σ amount
  price_min_cr REAL, price_avg_cr REAL, price_max_cr REAL,
  PRIMARY KEY (save_id, sector_macro, ware, side)
);
```

All three are `INSERT … SELECT` from tables `write_snapshot` just wrote —
no parser change, no new data source, single-digit milliseconds each.
Deliberately *not* proposed: per-station offer history (15 k rows ×
every autosave adds up; the sector band answers the analytical questions
— "where is energy-cell price heading" — and per-station current offers
are always in `trade_offer`). If a per-station price series is ever
wanted, add it as a change-only variant later; the A-class mechanics will
already exist.

*Migration:* three `CREATE TABLE`s, start empty — history accrues from
the next run. Nothing to lose. **Depends on T2** (entity_id for
`station_metric`) **and T5** (rerun guard so dev reruns don't append
duplicate rows). Migrated like E tables (never dropped) — add an
`AGGREGATE_TABLES` tuple beside `EVENT_TABLES` in `schema.py`.

### T5. Separate "import run" from "snapshot"

Keep `save` append-only (it is the provenance log and the A-tables' time
dimension) but make distinctness queryable and re-runs harmless:

```sql
-- distinct snapshots: first import row of each distinct save
CREATE VIEW v_snapshot AS
SELECT MIN(save_id) AS save_id, guid, game_time, save_date,
       player_money_cr, player_name
FROM save
GROUP BY guid, game_time, save_date;
```

Store-side rule (one EXISTS check in `write_snapshot`): an import whose
(`game_time`, `save_date`) already exists is a **rerun** — W tables still
rebuild (that's the point of a rerun), but A-table appends are skipped.
The player-money series and every T4 series then read from `v_snapshot`
density, immune to dashboard-dev reruns (C8).

*Migration:* view + store guard; no data change. Independent; T4 wants
it.

### T6. Event-history views: the domain read layer

Replaces the pandas re-derivations of C6 with connect-created views.

```sql
-- trades in domain terms: commander-redirected ("Executed by" rule),
-- current display names via the registry, ware names resolved
CREATE VIEW v_trade AS
SELECT t.time, t.ware, COALESCE(w.name, t.ware) AS ware_name,
       t.price_cr, t.amount, t.price_cr * t.amount AS total_cr,
       t.epoch,
       COALESCE(t.buyer_cmdr_entity,  t.buyer_entity)  AS buyer_entity,
       COALESCE(t.seller_cmdr_entity, t.seller_entity) AS seller_entity,
       t.buyer_faction, t.seller_faction,
       COALESCE(be.name, t.buyer_cmdr_name,  t.buyer_name)  AS buyer_name,
       COALESCE(se.name, t.seller_cmdr_name, t.seller_name) AS seller_name,
       COALESCE(t.buyer_cmdr_code,  t.buyer_code)  AS buyer_code,
       COALESCE(t.seller_cmdr_code, t.seller_code) AS seller_code,
       t.buyer_entity  AS buyer_exec_entity,   -- the executing ship when
       t.seller_entity AS seller_exec_entity,  -- a subordinate traded
       t.buyer_cmdr_entity IS NOT NULL  AS buyer_proxied,
       t.seller_cmdr_entity IS NOT NULL AS seller_proxied
FROM trade_tx t
LEFT JOIN ware w    ON w.id = t.ware
LEFT JOIN entity be ON be.entity_id = COALESCE(t.buyer_cmdr_entity,  t.buyer_entity)
LEFT JOIN entity se ON se.entity_id = COALESCE(t.seller_cmdr_entity, t.seller_entity);
```

This keeps the frames-layer subtlety that matters (rename-proof current
names via the registry; the proxy-attribution toggle stays possible
because executor columns survive) and drops the one that doesn't: the
latest-name-per-code pandas fallback (`frames.py:464-473`) degrades to
the stored merge-time name — it only ever applied to rows merged before
schema v4 stamped entities, a shrinking set. `frames.tradelog` becomes a
thin `read_sql` + Categorical dressing.

```sql
-- stock flows partitioned by durable identity (renames v_stock_delta;
-- keep the old name as an alias view for one release)
CREATE VIEW v_stock_flow AS
SELECT owner_entity, owner_id, owner_faction, owner_code, owner_name,
       ware, time, level, epoch,
       MAX(level - LAG(level) OVER w, 0) AS inflow,
       MAX(LAG(level) OVER w - level, 0) AS outflow
FROM stock_event
WHERE ware != ''
WINDOW w AS (PARTITION BY COALESCE('e' || owner_entity,
                                   owner_faction || '|' || owner_code,
                                   owner_id),
             ware, epoch ORDER BY time, rowid);
```

Entity-first partitioning (C5) with the existing text fallbacks for
pre-registry rows; with T2's `idx_stock_entity` the per-station query
drops from a scan to an index range.

```sql
-- entity biographies: lifespan + a uniform event stream
CREATE VIEW v_entity_life AS
SELECT e.*,
       COALESCE(e.gone_time,
                (SELECT game_time FROM save
                 WHERE save_id = (SELECT save_id FROM current_save)))
         - e.first_seen                        AS observed_span_s,
       e.gone_time IS NULL                     AS alive,
       c.id                                    AS component_id,   -- NULL if not in current snapshot
       c.sector_macro
FROM entity e
LEFT JOIN component c ON c.entity_id = e.entity_id
  AND c.save_id = (SELECT save_id FROM current_save);
```

*Migration:* views only (recreated at connect / on version bump per T10).
`v_stock_delta` survives one release as `CREATE VIEW v_stock_delta AS
SELECT *, inflow AS dv, outflow AS dv_neg FROM v_stock_flow` then goes.
**Depends on T2** for its performance half; the views themselves work
today. Which frames responsibilities move: `tradelog` assembly,
`global_trades` identity enrichment (the removed-object dagger logic
folds into `v_entity_life.alive`), stock-delta access.

### T7. Diplomacy view

```sql
CREATE VIEW v_faction_standing AS
SELECT faction, other,
       SUM(CASE WHEN kind = 'base'    THEN value ELSE 0 END) AS base,
       SUM(CASE WHEN kind = 'booster' THEN value ELSE 0 END) AS booster,
       MIN(1.0, MAX(-1.0,
         SUM(CASE WHEN kind IN ('base','booster') THEN value ELSE 0 END)))
         AS effective
FROM faction_relation
WHERE save_id = (SELECT save_id FROM current_save)
GROUP BY faction, other;
```

Verbatim the `frames.py:624-651` pivot (boosters are stored pre-decayed,
so SUM+clamp is the whole model per
docs/models/faction-relations-model.md). Discounts stay a plain filter on
`faction_relation`. *Migration:* view only. Independent.

### T8. Station and fleet assemblies

```sql
-- one row per station, the concept "station" assembled
CREATE VIEW v_station AS
SELECT c.id, c.entity_id, c.name, c.basename, c.code, c.owner,
       c.sector_macro, sec.name AS sector_name, c.sx, c.sz, c.knownto,
       (SELECT COUNT(*) FROM module m
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
  AND c.save_id = (SELECT save_id FROM current_save);
```

Correlated subqueries are fine at ~1,200 stations (all index-served after
T2's `idx_module_host` companions). The pandas rollups in
`frames.py:336-366` shrink to reading this plus the posts pivot; the
hull/mass estimate (`modules × 250_000`) can join on `modules_built` or
stay in pandas — it is a display heuristic, not data.

```sql
-- player fleet edges, entity-keyed (replaces _player_edges' second
-- resolution, C7): resolved once in write_snapshot, filtered here
CREATE VIEW v_player_fleet AS
SELECT fe.follower_id, cf.entity_id AS follower_entity,
       fe.commander_id, cc.entity_id AS commander_entity
FROM fleet_edge fe
JOIN component cf ON cf.id = fe.follower_id  AND cf.save_id = fe.save_id
JOIN component cc ON cc.id = fe.commander_id AND cc.save_id = fe.save_id
WHERE cf.owner = 'player' AND cc.owner = 'player'
  AND fe.save_id = (SELECT save_id FROM current_save);
```

`merge_events` then takes its commander map from this view's underlying
query instead of re-deriving from raw save lists, and `frames.wings`
becomes a `read_sql`. *Migration:* views + deleting `_player_edges`.
Depends on T2.

### T9. Load `region_yield` reference; resource status becomes SQL

```sql
CREATE TABLE IF NOT EXISTS region_yield (
  level     TEXT NOT NULL,           -- verylow … veryhigh
  ware      TEXT NOT NULL,
  capacity  REAL,                    -- full-area yield
  respawn_s REAL,                    -- -1 = never respawns
  PRIMARY KEY (level, ware)
);

CREATE VIEW v_resource_area AS
SELECT r.sector_macro, r.ware, r.yield, r.level, r.speed, r.starttime,
       ry.capacity, ry.respawn_s,
       CASE WHEN r.yield > 0 THEN 'live'
            WHEN ry.capacity IS NULL OR ry.capacity = 0 THEN 'unknown'
            WHEN ry.respawn_s < 0 THEN 'never'
            WHEN r.starttime <= (SELECT game_time FROM save
                                 WHERE save_id = (SELECT save_id FROM current_save))
                 THEN 'full'
            ELSE 'respawning' END AS status
FROM resource r
LEFT JOIN region_yield ry ON ry.level = r.level AND ry.ware = r.ware
WHERE r.save_id = (SELECT save_id FROM current_save);
```

Encodes the confirmed respawn model
(docs/models/resource-depletion-model.md; the `starttime = 0` case folds
into `<=` since game_time > 0 always) so "what can I mine right now,
where" is a query. Frames keeps only the wide sector pivot for the map.
*Migration:* one more R-table load in `write_reference` from the already-
packaged `regionyields.csv` + view. Independent.

### T10. Live-mode operations

- **WAL**: `PRAGMA journal_mode=WAL` once at `open_db` (persistent in the
  file), plus `PRAGMA busy_timeout=5000` and `PRAGMA synchronous=NORMAL`
  on every connection. Writer (analyzer/watch) and readers (serve) stop
  blocking each other. One-line change; WAL sidecar files are the only
  visible effect.
- **View lifecycle**: stop recreating views at every connect (C9).
  Store `views_version` in `meta`; recreate views only when it differs
  from the code's (bumping it is free — views are cheap DDL). Read-only
  connections then always see current views and the serve TEMP-view
  duplication dies.
- **Analyzer split** (parse→DB vs DB→render) is the spike's P7 and out of
  scope here, but note the schema is already split-ready: everything the
  render phase needs is in the DB except four `SaveData` scalars, which
  the spike's shim recovered — with T4/T5 in place, `has_highways` and
  `player_faction_name` belong as `save` columns (two W-side column adds)
  to close that gap.

*Migration:* pragmas + meta key; no table changes. Independent. High
leverage for goal 1.

### T11. Naming and convention cleanups (W/R rebuild = free renames)

All in one version bump; compatibility views keep old names alive for one
release where consumers exist:

| Change | Rationale |
|---|---|
| `module` → `build_entry` (+ compat view `module`) | it holds plan entries; the misnomer caused the 2× capacity bug class (C10). `v_built_module` keeps its name — its meaning was always right |
| `modcap` → `module_cap` | pairs with `module_ref` |
| `faction_meta.account` → `account_cr` (÷100 at load) | kills the one raw-cents exception |
| `trade_offer.object_id`: drop NOT NULL, `''` → NULL | kills the one empty-string exception; hostless offers become `object_id IS NULL`, consistent with every other column |
| `npc` → keep name, document; or `player_npc` if renamed anyway | lowest priority of the set |

Not proposed: renaming `*_ref` reference tables to bare names or vice
versa wholesale — churn without a defect; new reference tables should
follow `*_ref` (T9's `region_yield` deliberately has no `_ref` because it
is keyed by (level, ware), not a game id — judgment call, either is
defensible). E-table conventions (`trade_tx.ware = ''`) stay: changing
them is an UPDATE over irreplaceable history for zero analytical gain.

*Migration:* free for W tables (drop/recreate); compat views cost
nothing. Independent.

### T12. `log_entry.interact` fix + backfill

Loader reads the correct attribute going forward; one E-migration
statement recovers the past from `raw_attrs`:

```sql
UPDATE log_entry
SET interaction = json_extract(raw_attrs, '$.interact')
WHERE interaction IS NULL AND raw_attrs IS NOT NULL;
```

(`json_extract` is built into the sqlite3 Python ships.) Optionally
rename the column to `interact` to match the save; the backfill is the
part that matters. *Migration:* `EVENT_MIGRATIONS` entry. Independent.

### T13. Migration-machinery hygiene

- **Zombie tables** (C11): write the managed-table inventory to
  `meta('managed_tables', json array)` at every schema write; on a
  version bump, drop tables that are in the stored inventory but absent
  from the current code's list (never touching E/A tables or unknown
  user tables). Retroactively drops `station_drones` on the next bump.
- **`removed_object.first_save_id`**: `ALTER TABLE removed_object ADD
  COLUMN first_save_id INTEGER` — stamp at merge so graveyard rows carry
  arrival provenance (their only obtainable timestamp; the save-side
  `time` attr does not exist in v9, so the existing always-NULL `time`
  column can be dropped from the fresh DDL while the ALTER path leaves it
  in old DBs — harmless either way).

*Migration:* meta bookkeeping + one E-table ALTER. Independent.

---

## 4. Prioritized recommendations

Impact is against the two goals (live mode, ad-hoc SQL). "Independent"
means implementable and shippable alone.

| # | Change | Impact | Depends on | Notes |
|---|---|---|---|---|
| **H1** | T2 entity spine (`component.entity_id` + E-indices + pipeline reorder) | **High** | — | The keystone; do first. Unblocks H3, M2, M3 |
| **H2** | T10 WAL + view-lifecycle fix | **High** (live mode) | — | Smallest diff of any high item |
| **H3** | T4 aggregate history (`sector_presence`, `station_metric`, `market_stat`) | **High** | H1, M1 | The trend layer; value compounds with every analyzed save — start early |
| **M1** | T5 snapshot-vs-rerun (`v_snapshot` + A-write guard) | Medium | — | Trivial alone; H3 needs it |
| **M2** | T6 event views (`v_trade`, `v_stock_flow`, `v_entity_life`) | Medium-high | H1 (for perf; correct without) | Moves the biggest pandas blocks into SQL |
| **M3** | T8 assemblies (`v_station`, `v_player_fleet`) + de-duplicate fleet resolution | Medium | H1 | Kills C6-rollups and C7 |
| **M4** | T3 coverage table | Medium | — | Provenance made queryable; backfill preserves everything |
| **M5** | T9 `region_yield` + `v_resource_area` | Medium | — | Closes the one reference gap forcing pandas |
| **M6** | T1 `current_save` + T7 `v_faction_standing` | Medium (ergonomics) | — | Views only; can ride along with any bump |
| **L1** | T11 naming cleanups | Low | — | Batch into whichever bump comes first |
| **L2** | T12 `interact` backfill | Low | — | One migration statement |
| **L3** | T13 zombie-drop hygiene + `removed_object.first_save_id` | Low | — | Migration-machinery debt |

Suggested sequencing: **H1 + H2** in one schema bump (v11), **M1 + H3**
next (v12, starts accruing history — the sooner the better), then M2–M6
as view-mostly increments, L* batched opportunistically. Every step keeps
the DB consumable by the current frames.py; frames functions retire one
at a time as their view replacements land.

History-loss statement, explicitly: no proposal drops or rewrites rows in
`trade_tx`, `stock_event`, `log_entry`, `removed_object`, `entity`, or
`entity_event`. The only discarded artifacts are derivable-and-rebuilt
(W/R/D tables during version bumps — the designed path), the two
`meta` window keys (superseded by a backfilled `coverage`), and the
`v_stock_delta` view name (aliased for one release).
