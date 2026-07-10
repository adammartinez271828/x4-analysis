# Feasibility study: SQLite + ORM as the v2.0 data model

**Question:** Can the parsing logic be converted into a more flexible ORM
mapping — extracting as much as possible from the savegame into a SQLite
database — so analysis becomes natural queries instead of pandas pipelines?

**Verdict: yes, and cheaply.** Measured on the real save (`save_008.xml.gz`,
45 MB): writing every record the parser currently collects into SQLite adds
**0.4 s** on top of the 13.6 s parse and produces a **28 MB** database
(~450 k rows, 21 tables). The queries that are hardest in pandas today —
fleet hierarchy, stock-delta trade volume, market joins — become short,
fast SQL (34 ms, 100 ms, <1 ms). The one thing that is **not** feasible is
mapping the XML generically: this save has **8.35 M elements**; an
element/attribute EAV store would be tens of millions of rows, gigabytes on
disk, and every query a self-join. v2.0 should be a **curated relational
schema**, not a reflection of the XML.

All numbers below were measured this session with a prototype
(raw `sqlite3.executemany`, the performance floor an ORM must not fall far
from).

## 1. What was measured

| Step | Result |
|---|---|
| Parse (existing `saveparser.py`) | 13.6 s |
| Insert all 21 tables | 0.3 s |
| Create 8 indexes | 0.1 s |
| DB size | 27.8 MB (source .gz: 45 MB) |
| Whole-save element count (reject generic mapping) | 8,348,221 elements, 9.6 s just to walk |
| `pd.read_sql` round-trip | component 18 k rows / 39 ms, trade 82 k rows / 84 ms |

Row counts: component 18,280 · trade 82,491 · module 38,663 ·
module_upgrade 192,849 · post 26,939 · built_ref 22,943 · order 18,035 ·
trade_offer 13,209 · people 12,991 · cargo 11,859 · commander/subordinate
links 6,155 each · resource 3,238 · workforce 1,100 · the rest small.
Storage is dominated by module_upgrade (9.7 MB) and trade (3.6 MB).

Reference data (wares, recipes, factions, sectors, gates, modcaps, ships,
textdb) is ~80 k rows / 2.3 MB total — it belongs **in the same database**,
so save data joins against game data in SQL.

### Query naturalness — the actual point

**Fleet hierarchy** (today: imperative link-matching in `frames.py`) is a
recursive CTE, 34 ms:

```sql
WITH cmd AS (
  SELECT cl.follower_id AS ship, sc.leader_id AS commander
  FROM commander_link cl JOIN subordinate_conn sc ON cl.conn_ref = sc.conn_id
),
chain(ship, top, depth) AS (
  SELECT ship, commander, 1 FROM cmd
  UNION ALL
  SELECT chain.ship, cmd.commander, chain.depth + 1
  FROM chain JOIN cmd ON chain.top = cmd.ship
)
SELECT ... -- fleets of arbitrary depth, roots, sizes
```

Verified against the save: top fleet ATO-898 has 120 ships, depth 3.

**Traded volume from stock deltas** (today: groupby/diff/clip in
`frames.global_trades`) is a window function, 100 ms over 82 k rows:

```sql
SELECT ware, SUM(dv) FROM (
  SELECT ware, v - LAG(v) OVER (PARTITION BY owner, ware ORDER BY time) AS dv
  FROM trade WHERE owner != '' AND buyer = ''
) WHERE dv > 0 GROUP BY ware
```

Reproduces the Market-tab numbers (energycells 23.4 M top, as expected).
(A real view filters rows with empty `ware` — the prototype surfaced that
some owner-only entries carry none.)

**Ad-hoc market questions** become one-liners: "claytronics buy demand per
sector excluding Xenon" is a two-table join, <1 ms. This is exactly the
"query more naturally" ask.

## 2. Proposed v2.0 architecture

```
savegame.xml.gz ──saveparser (unchanged idea)──▶ x4_<guid>.sqlite ──▶ views/queries ──▶ viz
                                                     ▲
                       reference tables (extract-gamedata output) ─┘
```

Key principle: **the database is a rebuildable artifact** derived from
save + game files — *except* the history tables (log, tradelog), which
carry data the game has already discarded. That split drives every design
decision below.

### Schema sketch (curated, not generic)

- `save` — snapshot dimension: save_id, guid, save_date, game_time,
  game_version, player_name, player_money. Every world-state row carries
  `save_id`; event rows are global per guid (see history).
- `component` — id PK, class, macro, name, code, owner, knownto, contested,
  spawntime, basename, cluster/sector denormalized **plus a new
  `parent_id`** (the nearest collected ancestor on the parser's component
  stack — the immediate XML parent is an uncollected zone/dockingbay).
  Storing real
  containment unlocks queries we currently can't do at all — "ships docked
  at station X", "everything inside sector Y" — via one recursive CTE.
- World-state satellites keyed by component id: `module`, `built_ref`,
  `module_upgrade`, `cargo`, `trade_offer`, `build_resource`, `order`,
  `post`, `workforce`, `people`, `npc` + `npc_skill`, `commander_link` /
  `subordinate_conn`, `resource`, `floating_ware`.
- Event tables (append/merge, never rebuilt from scratch): `log_entry`,
  `trade`, `removed_object`. These **replace the csv.gz caches**: the
  R-derived merge semantics (per-category min-time replacement; tradelog
  min-time cutoff) become two DELETE + bulk INSERT statements inside one
  transaction, with idempotence enforced by the same dedup keys.
- Reference tables loaded from the packaged CSVs (or straight from
  `extract-gamedata`): `ware`, `recipe`, `faction`, `sector_ref`,
  `cluster_ref`, `gate`, `ship_ref`, `modcap`, `text` (page, tid, text).
- Derived layer: the reusable parts of `frames.py` become SQL **views**
  (`v_universe`, `v_stations`, `v_fleet`, `v_station_rates` inputs,
  `v_global_trades`). Views cost nothing at write time and keep the
  "one obvious place to look" property.

What stays Python: the streaming XML parse itself (an ORM changes the
*sink*, not the parser), `logparse.py` regexes, the market/advisor scoring
math, and all plotting. pandas remains the bridge (`read_sql` is
milliseconds); viz code barely changes — it swaps `frames.x` for
`read_sql(view)`.

## 3. ORM layer options

| Option | Deps added | Bulk-insert speed | Notes |
|---|---|---|---|
| stdlib `sqlite3` + schema module | none | floor (measured 0.3 s) | What the prototype used. A ~150-line `store.py` with CREATE TABLE strings and executemany. No query builder, but our queries are static SQL anyway. |
| SQLAlchemy 2.0 (Core for bulk, declarative dataclass models for typed access) | `sqlalchemy` (~1 pure-Python pkg + optional C speedups) | ≈ floor via Core `insert()` executemany | The standard. Typed model classes double as documentation; migrations via Alembic *available* but likely unnecessary (see risks). |
| peewee | 1 small pkg | good | Lighter than SQLAlchemy, but its ActiveRecord style tempts row-at-a-time inserts (10–50× slower for our volumes). |
| SQLModel | sqlalchemy + pydantic | ≈ SQLAlchemy | Pulls pydantic; more dep weight for no benefit here. |

**Recommendation:** SQLAlchemy 2.0, used in a disciplined split — declarative
dataclass models define the schema and serve typed single-object access;
all bulk loading goes through Core `insert(...).values(...)`/executemany so
we stay at the measured floor. The ORM "unit of work" (one object per row)
must never touch the 200 k-row tables. If dependency slimness wins the
argument, the stdlib version is genuinely fine — our query set is static
SQL and the prototype *is* that design. This is a project-policy decision
(CLAUDE.md: no heavier deps without asking), flagged here rather than made.

## 4. What v2.0 unlocks

1. **Ad-hoc analysis.** `sqlite3 x4_<guid>.sqlite` or any DB browser gives
   direct interactive querying of the empire — no Python required. This is
   the flexibility the current tuple-lists/dataframes can't offer.
2. **History across saves.** The `save` snapshot dimension makes the
   autosave-watch idea (analytics-ideas.md) storage-ready: each run appends
   one snapshot. Size math: ~28 MB/save full-fidelity → 100 snapshots ≈
   2.8 GB, so snapshots should keep only trend-worthy tables (component
   summary, cargo, trade_offer, workforce ≈ 3–4 MB/save), while `trade`/
   `log_entry` are already append-only globals. Old snapshots pruneable
   with one DELETE.
3. **Cache subsystem deleted.** `caches.py`, the csv.gz files, and the
   compressed/uncompressed leftover-handling all collapse into the event
   tables' merge transaction.
4. **Cross-cutting joins with game data.** Recipes × modules × offers in
   one statement (today: three dataframes and careful merge keys).
5. **A stable contract for other tools.** The DB file is an API: anything
   (scripts, notebooks, a future live-mode watcher) can consume it without
   importing the package.

## 5. Risks and costs

- **Schema drift / migrations.** Because the world-state tables are
  rebuildable from the save in ~14 s, migrations are mostly "bump
  `schema_version` in `meta`, drop and rebuild". Only `log_entry`/`trade`/
  `removed_object` carry irreplaceable history and need real (but simple,
  additive) migration care. Alembic is overkill for this; a
  `schema_version` check + targeted ALTERs suffices.
- **Modded saves.** Keep every text column permissive (no enums/FK
  constraints on owner/ware/macro); unknown values must land, not fail —
  same defensive posture frames.py has today. For attr-dict records
  (log entries, trades) keep a `raw_attrs` JSON column so wording/schema
  drift in the game never loses data (SQLite's JSON functions can query it).
- **ORM bulk-insert trap.** The only real performance hazard. Mitigated by
  the Core-for-bulk rule above; the floor is measured and CI-testable
  (assert insert < 2 s in the e2e test).
- **Two sources of truth during migration.** Mitigated by the phase plan
  below: frames.py keeps working off the same SaveData until its consumers
  are ported, then thins into views.
- **Not a live game link.** Nothing here changes the fundamental
  save-snapshot model; "continuous" anything still means per-save deltas.

## 6. Incremental migration plan

1. **`store.py` + schema** — writes `x4_<guid>.sqlite` from SaveData after
   parse (additive; nothing else changes). Load reference CSVs in. Add
   `parent_id` to the parser. Tests: fixture save → known row counts;
   insert-twice idempotence for event tables.
2. **Port the caches** — log/tradelog merge semantics as SQL transactions;
   dual-write with csv.gz for one release to verify identical output, then
   delete `caches.py`.
3. **Views for frames** — recreate `universe`, `stations`, `ships`,
   fleet hierarchy, `global_trades` as views; `frames.py` builds its
   dataframes via `read_sql(view)` and shrinks accordingly.
4. **Viz reads the DB** — each viz module takes a connection instead of
   Frames where natural; Frames remains as a thin typed façade.
5. **Snapshot dimension** — add `save_id`, keep-N pruning, and the trend
   queries the history-charts idea needs.
6. **Optional ORM models** — if SQLAlchemy is approved, introduce the
   declarative models at step 1; if not, the stdlib schema module carries
   the whole plan unchanged.

Prototype code: `scratchpad/orm_proto.py` (session-local); all measurements
reproduce in one run against the newest save.
