# Phase 5: the domain read layer — M2, M3, M4, M5 (schema v14)

Executed 2026-07-24 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 5 (refinements R3/R5 applied), specs in
[db-model-improvements.md](../plans/db-model-improvements.md) (T6, T8,
T3, T9 as revised; shipped-notes annotated there per item). One commit
per item, `uv run pytest -q` green at every commit — **202 passed** at
the end (11 new tests; two frames-era tests rewritten for the new
semantics).

| Item | Commit | What shipped |
|---|---|---|
| M2 (T6) | `da2f247` | `v_trade`, `v_stock_flow` (+`v_stock_delta` alias), `v_entity_life`; tradelog/global_trades/entities frames blocks retired |
| M3 (T8) | `7bdae74` | `v_station`, `v_player_fleet`; `_player_edges` deleted (fleet resolution deduplicated) |
| M4 (T3) | `589f119` | coverage backfill migration, SCHEMA_VERSION 14; the meta `*_window_start` keys retired |
| M5 (T9) | `275866f` | `region_yield` reference table; `v_resource_area`; frames `_classify` retired |
| report | this commit | phase report, ER render v14 |

## Parity method

Every view that replaced a frames/pandas block is proven against the
code it retired on the **real 8E0C database**, in
`tests/test_views_parity.py` — a permanent test module, not a one-off
script. The retired pandas logic is reimplemented verbatim inside the
tests, so the equivalence stays pinned after the production copy is
gone. The module opens the real DB **read-only** and instantiates the
checked-out view DDL as TEMP views (shadowing whatever the file
stores), so the suite never writes to a real database and never
triggers a migration as a side effect. Where the plan documents a known
theoretical divergence, the current equivalence is asserted explicitly
so future divergence fails loudly (mandated for plan-F10; also done for
the v_stock_flow partition change and the plan-F4 name degradation).

Frames-level widget parity used a capture script
(scratchpad `widget_baseline.py`): the full import pipeline + frames
build, emitting the counts behind the affected widgets. Captured before
any change and re-captured after each item for 8E0C (both playthroughs
at phase end) — **byte-identical at every step**:

| Count | 8E0C | 9406 |
|---|---:|---:|
| tradelog rows (Trade History source) | 3,702 | 16,222 |
| sales / buys rows | 1,229 / 138 | 5,771 / 950 |
| history-browser records / objects | 1,840 / 42 | 9,376 / 77 |
| history money sum (spot value) | 175,809,704 | 278,712,155 |
| wings rows (fleet tables/sunburst) | 110 | 406 |
| stations rows | 8 | 74 |
| entities rows | 39,646 | 16,250 |
| global_trades rows (Market flows) | 400,482 | 469,522 |
| global_trades Σdv / Σdv_neg (spot) | 311,730,804 / 287,313,689 | 313,435,823 / 305,084,625 |
| resource areas live / full / respawning | 3,048 / 154 / 44 | 2,722 / 488 / 36 |

Dashboards built end-to-end after every retirement commit (8E0C) and
for both playthroughs at phase end, without errors.

## Per-item notes and spec deviations

### M2 (T6) — `v_trade`, `v_stock_flow`, `v_entity_life`

- **Deviation (parity-driven):** the spec DDL's
  `COALESCE(cmdr_entity, entity)` redirects became
  `CASE WHEN cmdr_id IS NOT NULL …` — frames' rule keys on `cmdr_id`
  (a proxied row whose commander lacks a registry id must yield NULL,
  not fall back to the executor's identity), and the same applies to
  the registry-name join key. The proxied flags already keyed on
  `cmdr_id` in the revised spec (review plan-F3); this extends that
  reasoning to every redirected column.
- **Deviation (consumer-driven):** redirected `{side}_id` and
  `{side}_exec_id` columns added (the per-object trade views consume
  ids), and `{side}_exec_name` is registry-resolved like the main
  names (frames re-resolved the executor display column too).
- **R3 applied:** `v_stock_flow` ships **without** the `ware != ''`
  guard — dead code since T15's v12 migration re-typed the money-ledger
  rows out of `stock_event`; the view's comment restates that history.
  `v_stock_delta` survives one release as an alias view.
- Parity evidence: `v_trade` reproduces the retired assembly
  column-for-column on all 3,702 rows; name divergences **0** (the
  plan-F4 sanctioned set — parties without registry identity keeping
  their merge-time name — is empty on this DB today; the test asserts
  containment so any future divergence outside that set fails);
  proxied 288 buyer / 2,438 seller, matching frames' rule exactly.
  `v_stock_flow` matches a full pandas recompute of the LAG deltas
  per series, and the entity-first partition is **delta-identical** to
  the retired text-first keying on both real DBs (0 of 400,482 /
  469,522 rows differ) — pinned as its own test. `v_entity_life`
  matches entity + current-snapshot joins on all 39,646 rows.
- Retired: the ~70-line tradelog re-resolution/melt block (now
  `frames.tradelog_frame`, a thin read of `v_trade` + Categorical
  dressing), the latest-name-per-code fallback (rename healing now
  flows exclusively through the registry — the rename test was
  rewritten to model the real pipeline), `global_trades`' source view,
  and `frames.entities`' raw-table read.

### M3 (T8) — `v_station`, `v_player_fleet` + fleet dedupe

- The plan's either/or (equivalence test vs pre-filter resolution) was
  resolved toward the **equivalence test**: before deleting
  `_player_edges`, its output on the parsed real newest save was
  compared with the view — 110 = 110 edges, identical. Kept
  permanently: the plan-F10 invariant test (no fleet edge touches a
  connectionless component; 0 today) plus an edge-for-edge recompute of
  the retired wings filter.
- `merge_events` takes its commander map from `v_player_fleet`
  (snapshots always precede merges in the pipeline and in `seed-trends`).
  Two synthetic tests were updated: a merge whose synthetic save has no
  fleet must not inherit the fixture snapshot's edge — a state the real
  pipeline cannot produce.
- `frames.wings` reads the view through an EXISTS filter on
  `fleet_edge` so the commander insert order (which the view's join
  would not guarantee) is preserved for the sunburst walk.
- **Deviation (scope):** the stations frame keeps its identity columns
  and posts pivot but now merges `v_station`'s rollups (`entity_id`,
  `sector_name`, `modules_built`, `workforce`, `cargo_volume_m3`); the
  consumer-free R-era columns (per-race `workforce.*`, max-index
  `modules`/`hull`/`mass` on the *stations* frame — the universe-level
  ones the sunbursts read are untouched) retired with the pandas
  pivot. Verified consumer-free by grep before removal; widget counts
  unchanged.
- `v_station` rollups verified against pandas recomputes over the base
  tables for all 1,771 stations (modules_built / workforce exact,
  cargo volume < 1e-6).

### M4 (T3) — coverage backfill, v14, meta keys retired

- **Deviation:** **three** meta keys retired, not the plan's two —
  `money_event_window_start` was born with T15 in Phase 3. All three
  are seeded into `coverage.window_start` (newest epoch, only where the
  merge hook never wrote one) and deleted; `_merge_window` no longer
  writes them; frames' rate-denominator window reads
  `coverage.window_start`.
- Backfill (`EVENT_MIGRATIONS["13"]`, riding the repaired chain so any
  off-chain DB is corrected on open): exact per-epoch bounds for the
  three epoch-stamped economylog streams; per-category **epoch 0** for
  the epoch-less logbook — exact whenever a log stream has a single
  coverage epoch, which is true in every observed DB (all epochs are 0
  in both real DBs); with real pre-existing gaps the old range folds
  into epoch 0, a known imprecision the stamped streams don't share.
  Upsert semantics (`ON CONFLICT … t_min = MIN, t_max = MAX`) extend
  hook-written rows, never clobber (`window_start` preserved).
- **B12 grounding:** the epoch semantics the backfill relies on were
  empirically fired in Phase 1's probe; the migration groups by the
  stored `epoch` column rather than recomputing gaps.
- **On both real DBs the backfill changed no bounds**: the whole-history
  windows merged since Phase 2 already covered every stored row
  (coverage bounds == table bounds for all 10 / 9 streams before and
  after). The migration exists for pre-coverage DBs walking the chain;
  the regression test builds exactly such a DB (two trade epochs, a
  partial hook row, all three meta keys) and pins backfill, extension,
  seeding and deletion.

### M5 (T9) — `region_yield` + `v_resource_area`

- As specced: `respawn_min` keeps the CSV's **minutes** (review X21);
  the load rides `write_reference` (rows rebuilt in sorted order from
  refdata's dict — deterministic under the reference digest), no schema
  bump needed. 45 rows on both DBs.
- frames' `_classify` closure retired: the resource block reads
  `v_resource_area` and keeps only mineable/rate/eta dressing in
  pandas. The synthetic capacity-injection test now injects through the
  `region_yield` table — the DB is the classification's source.
- The plan's scripted 0-mismatch check is a **permanent test**
  (`test_v_resource_area_matches_retired_classify`): a verbatim copy of
  the retired classifier vs the view's status on every area —
  **0 of 3,246 mismatches** on the real 8E0C DB
  (3,048 live / 154 full / 44 respawning, exactly the pre-change
  dashboard histogram). Self-contained via a TEMP `region_yield` built
  from the checked-out CSV, so it also serves the **R5 cross-link:
  re-run this test after any B21 change to the regionyields extraction
  output.** B5 (relocation) and B11 (nividium materialization) caveats
  are carried on the view's documentation, not blockers, per the
  roadmap.

## DB safety protocol

Backups before any phase write (WAL checkpointed first):

```
~/.local/share/x4analyzer/backup/
  x4_8E0C8E37-….20260724T154843Z.pre-phase5.sqlite
    b9b3c790fb601bc4f8b48c83c15e15663a92b5aa74988d9ee2efedc4f56ba0fd
  x4_94062A45-….20260724T154843Z.pre-phase5.sqlite
    08339bc2c7d9ccdd5f287e740cbd03be540854b35e85f053d2611fdaf0c85c6a
  checksums-20260724T154843Z-pre-phase5.txt
```

Both byte-identical to the Phase-4 report's post-run checksums —
nothing touched the DBs in between.

**M4 rehearsal:** both real DBs + reference CSVs copied to a scratch
data dir; `open_db` fired the v13→v14 walk there (version 14, 0 window
keys left, coverage bounds exactly matching the tables, W dropped);
then full analyzer runs against the scratch dir (`--data-dir`) for both
playthroughs rebuilt W (17,544 components) and the dashboards without
errors, with no meta keys re-created. Only then the real run — same
results on both DBs (coverage 10 / 9 stream rows, v14, keys gone),
followed by full pipeline runs with byte-identical widget counts.

Post-phase state (WAL checkpointed): 8E0C 29 `save` rows / 13 distinct
snapshots; 9406 11 / 1 (import-log growth = this phase's pipeline runs;
snapshots unchanged — every run was a rerun of the two heads).

```
eb1155b0fe58b968865a8ba3391116192fd1185db4b1fe1c1b682cc2e4d02f5c  x4_8E0C8E37-….sqlite
bda5b3e5f292a083756850fa1e1af66236ee1ea3ac2d236a0eb393eeba5c3a64  x4_94062A45-….sqlite
```

## Verification summary

- `uv run pytest -q`: green at every commit; **202 passed** at phase
  end. New: 10 real-DB parity tests (skip cleanly where the DB is
  absent) + the v13→v14 migration regression test.
- Every retired frames block has a view-backed replacement wired into
  its consumers; grep shows no production references to
  `_player_edges`, the name-by-code fallback, or the meta window keys
  (the v14 migration statements are the retirement itself).
- Both real DBs at schema v14; the three window keys absent; coverage
  backfill verified bound-exact against the tables.
- `v_resource_area` vs retired classification: 0 mismatches on all
  3,246 areas.
- Dashboards build for both playthroughs; affected widgets carry
  byte-identical data (table above).
- ER diagram updated (`region_yield`, `coverage.window_start`) and
  rendered to `output/db-schema-er-v14.png` (earlier renders untouched).

## Left open (tracked, not Phase-5 scope)

- `v_stock_delta` alias removal after one release.
- B5 / B11 / B21 research items (parallel track); the R5 cross-link is
  now enforced by a test rather than a note.
- Phase 6: L1–L3 hygiene + DF-1 doc propagation.
