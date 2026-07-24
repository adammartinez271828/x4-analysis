# Phase 4: the trend layer — M1, H3, archive seeding (schema v13)

Executed 2026-07-24 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 4, specs in [db-model-improvements.md](../plans/db-model-improvements.md)
(T5, T4 as revised — plan-F1/F6 preconditions landed in Phase 2), on top
of the Phase-2 machinery (H0 never-dropped `save`, H1 entity spine, H4
stale-save merge guard) and Phase 3's v12. One commit per item, the full
suite (`uv run pytest -q`) green at every commit: **191 passed**.

**Numbering note:** the roadmap penciled this phase in as "schema bump
v12", written before Phase 3's T15 took that number — the trend layer
ships as **v13**. The bump itself is an empty walk (no
`EVENT_MIGRATIONS` entry): the A tables are new and ride the idempotent
`CREATE TABLE IF NOT EXISTS` pass.

| Item | Commit | What shipped |
|---|---|---|
| M1 (T5) | `d7314a6` | `v_snapshot` + rerun detection; canonical snapshot id (`store.snapshot_id`) |
| H3 (T4) | `235d0c6` | A-tables `sector_presence` / `station_metric` / `market_stat`, `write_aggregates`, SCHEMA_VERSION 13, ER render |
| Seeding | this commit | read-only registry resolution, `seed-trends` CLI, both real DBs seeded |

## Per-item summary

### M1 (T5) — snapshot vs import run

`v_snapshot` collapses the per-import `save` log to distinct
(guid, game_time, save_date) snapshots; its `save_id` is the MIN over
the group — the snapshot's first import. **Deviation from the spec's
store rule** (annotated in the plan): instead of "rerun ⇒ skip
A-appends", the store resolves every import to its **canonical snapshot
id** (`store.snapshot_id()`) and A-appends happen only when that
snapshot has no rows in the target table yet. Same rerun-immunity, one
extra property the seeding needs: a snapshot first imported *before*
the A layer existed (the real 8E0C DB had four) still receives its
trend rows on its next import, keyed to its original id.

### H3 (T4) — the A tables

DDL per the revised spec: text key columns `NOT NULL DEFAULT ''` with
`COALESCE(x, '')` at insert (plan F6 — a NULL in a text PK column is
distinct-from-everything in SQLite and would let duplicate appends
succeed). `test_aggregate_null_keys_stay_unique` inserts a duplicate
''-keyed row-set and asserts the `IntegrityError`. `AGGREGATE_TABLES`
joins the never-dropped classes in the bump path
(`test_schema_bump_spares_aggregate_tables` pins it). The three
`INSERT … SELECT`s read the W tables the same import just wrote;
`sector_presence` filters to `class LIKE 'ship_%' OR class IN
('station', 'buildstorage')` (the territory/military concept — spec
listed the classes but no filter; deviation annotated in the plan).
`station_metric` covers player stations with a resolved `entity_id`.

### Seeding — historic imports (the spec extension)

T4/T5 as specced cover only forward accrual; importing an *archived*
(older) save had to be designed. Shipped as the minimal extension:

- **`seed-trends` CLI**: peeks each file's `<info>` header
  (`parser.peek_save_info`, milliseconds vs a ~20 s full parse), groups
  by GUID, imports oldest→newest through the **normal snapshot path** —
  no parallel machinery. Saves whose snapshot already has trend rows
  are skipped without a parse, so re-running the command is a fast
  no-op.
- **World state**: each historic import transiently rebuilds the W
  tables, so ordering ends the sequence at the newest save. The command
  refuses a batch whose newest save is older than the stored head
  (nothing is imported in that case), and re-runs the head file when
  needed purely to restore W — guaranteeing the W tables never end
  older than before the seed.
- **Entity identity**: `update_entity_registry` now resolves saves
  older than its high-water mark **read-only** — the slot matching
  returns a component → entity mapping (stamping `component.entity_id`
  and feeding `station_metric`), but mints, closes, edits and the
  high-water stamp are all skipped; stale observations still cannot
  corrupt lifecycle history. Entities that died before the observed
  history began stay unmapped (their stations simply have no
  `station_metric` row in historic snapshots).
- **Event history**: untouched by design — the H4 merge guard keeps
  skipping every stale window (each historic import logs the expected
  guard warning), and an archived save *newer* than the head merges
  normally, exactly like any fresh import.

## Rehearsal and real-run evidence

### DB safety protocol

Backups taken before any real-DB write (WAL checkpointed first),
checksums recorded:

```
~/.local/share/x4analyzer/backup/
  x4_8E0C8E37-….20260724T143434Z.pre-phase4.sqlite
    fb800b057bbeb772f86b8037b0c2da6fb754be6ec56e30e9632a98b87c955dec
  x4_94062A45-….20260724T143434Z.pre-phase4.sqlite
    11417ce2c72760a6e24a6ee7d38093a66e74b36ec7b18a0160fc899c39658e9c
  checksums-20260724T143434Z-pre-phase4.txt
```

Both are byte-identical to the Phase-3 report's post-run checksums —
nothing touched the DBs in between.

### Input census

13 archived saves of the 8E0C playthrough in the save dir (game times
61,948 → 76,511) plus the 9406 playthrough's newest save
(`~/Downloads/save_006.xml.gz`, its only archived file — 9406 seeds
its head snapshot and accrues forward from here). **The game was
running during this phase**: between the initial census and the seed
runs it rotated `autosave_02` from game time 64,067 to **76,511** —
*newer* than the stored head (save_005, 75,210). The seed handled it as
designed: sorted last, merged as a normal fresh head (E history
extended, not guarded), W tables ended at it. The head game_time
therefore legitimately *advanced* during seeding; nothing regressed.

### Rehearsal (scratch copies, session scratchpad `phase4/`)

Both real DBs + reference CSVs copied to a scratch data dir, the real
CLI run against it (`--data-dir`). Results identical in kind to the
real runs below. Full sequence validated: v12→v13 bump on open,
chronological seed (13 + 1 snapshots), idempotent re-seed ("trend layer
already covers all N saves", zero parses), dashboard build against the
seeded DB with A-counts unchanged.

### Real run: 8E0C (current playthrough, v12 → v13)

One `seed-trends` invocation over all 14 files (both GUIDs). 13 imports
(the 13 archived saves — four were reruns of already-recorded snapshots
that lacked trend rows), `save` 7 → 20 rows, 13 distinct snapshots.
Per-snapshot A rows:

| game_time | sector_presence | station_metric | market_stat |
|---:|---:|---:|---:|
| 61,948.6 | 1,890 | 5 | 4,494 |
| 64,376.6 | 1,899 | 6 | 4,512 |
| 65,599.3 | 1,877 | 6 | 4,512 |
| 66,772.7 | 1,897 | 7 | 4,513 |
| 67,536.9 | 1,894 | 7 | 4,502 |
| 69,324.1 | 1,865 | 7 | 4,497 |
| 70,212.6 | 1,889 | 7 | 4,497 |
| 71,874.8 | 1,901 | 8 | 4,529 |
| 72,813.2 | 1,923 | 8 | 4,534 |
| 73,391.8 | 1,911 | 7 | 4,536 |
| 74,720.0 | 1,908 | 7 | 4,571 |
| 75,210.1 | 1,888 | 7 | 4,566 |
| 76,511.1 | 1,901 | 8 | 4,566 |
| **total** | **24,643** | **90** | **58,829** |

The station_metric column is already a readable trend: the player
station count grows 5 → 8 across the 14½ observed game-hours (the
read-only registry resolution is what populates the historic rows).
The W tables ended at the newest save (`component` save_id 20 =
autosave_02, game_time 76,511.093 — the mid-session rotation described
above). E tables: extended **only** by that genuinely-new head, via the
normal merge path — trade_tx 3,716 → 3,891, stock_event 392,963 →
400,482, money_event 4,795 → 4,901, log_entry 3,989 → 4,079,
removed_object 1,331 → 1,333, entity 38,552 → 39,646, entity_event
69 → 72; **every stale window was skipped by the H4 guard** (12
skip-warnings, one per historic import).

After seeding: a re-seed reports "trend layer already covers all 13
saves" with zero parses, and a full analyzer run (autosave_02, a rerun)
rebuilt the dashboard without errors adding **0** A rows (24,643 / 13
unchanged, still 13 snapshots).

### Real run: 9406 (the 559 h playthrough, v12 → v13)

Only the head save is archived (`~/Downloads/save_006.xml.gz`,
game_time 2,012,678.695 — same as the stored head), so 9406 seeds one
snapshot and accrues forward from here: `save` 6 → 7, 1 distinct
snapshot, sector_presence 1,836 / station_metric 74 / market_stat
4,106 rows. Head rerun ⇒ W rebuilt identically, all E-table counts
byte-identical to the Phase-3 report (16,337 / 469,522 / 16,408 /
13,840 / 863 / 16,250 / 0). Re-seed: "already covers all 1 saves".

### Guard interactions observed (both rehearsal and real)

Every historic import produced exactly the two expected notices —
registry read-only resolution + merge-guard skip:

```
NOTE: save predates the entity registry's newest snapshot; resolving
      entities read-only (no registry updates)
WARNING: save (game time NNNNN) predates the stored event history
      (high-water mark NNNNN); event merge skipped — an older window
      would destroy newer history
```

and reruns of already-recorded snapshots logged the M1 detection
("Snapshot already recorded (rerun)…").

## Verification summary

- `uv run pytest -q`: **191 passed** at every commit (9 new tests:
  v_snapshot ×2, aggregates ×5 incl. the F6 duplicate-row rejection and
  bump-survival, seeding ×4 incl. the world-state refusal; the stale
  registry test rewritten for read-only resolution).
- Distinct snapshot count = archived save count: **13** (8E0C) and
  **1** (9406), and every A table holds exactly that many distinct
  `save_id`s (per-snapshot row counts above).
- Re-running the seed and re-importing the newest save add **0** A
  rows (verified on scratch and real DBs).
- W tables end at the newest save in both DBs (`component`'s single
  `save_id` = the head import; its `save.game_time` = the head).
- 9406's E-table counts byte-identical to Phase 3's; 8E0C's extended
  only by the genuinely-new autosave head via the normal merge path.
- Dashboards build without errors against both seeded DBs.
- Backups exist with recorded checksums; `sha256sum -c` verifies them;
  post-run checksums recorded below.

Post-run checksums (WAL checkpointed first):

```
b9b3c790fb601bc4f8b48c83c15e15663a92b5aa74988d9ee2efedc4f56ba0fd  x4_8E0C8E37-….sqlite
08339bc2c7d9ccdd5f287e740cbd03be540854b35e85f053d2611fdaf0c85c6a  x4_94062A45-….sqlite
```
