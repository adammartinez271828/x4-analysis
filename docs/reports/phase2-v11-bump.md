# Phase 2: schema bump v11 — H0, H1, H2, H4(+R7 hook), M6, B15

Executed 2026-07-23/24 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 2, specs in [db-model-improvements.md](../plans/db-model-improvements.md)
(T0, T2, T10, T14 + T3's DDL, T1, T7), consuming the Phase 1 verdicts of
[phase1-derisk-probes.md](phase1-derisk-probes.md) (B6 → H1 proceeds
unchanged; B3 → skip-with-warning guard semantics; B12 → epoch/gap
semantics confirmed for the coverage hook). One commit per item; the full
suite (`uv run pytest -q`) was green at every commit, finishing at
**179 passed** with B3's pinned merge-guard test passing un-xfailed.

| Item | Commit | What shipped |
|---|---|---|
| H0 (T0) | `a074dae` | never-dropped `save`/`meta` (P class); complete migration version chain |
| H1 (T2) | `3dea48f` | `component.entity_id` spine, pipeline reorder, W+E indices, SCHEMA_VERSION 11 |
| H2 (T10) | `23a8d26` | WAL + busy_timeout + synchronous=NORMAL; versioned view lifecycle; reference digest guard |
| H4 (T14+R7) | `a6fa760` | stale-save merge guard (skip-with-warning); coverage table + merge-side updates |
| M6 (T1+T7) | `9bfde80` | `current_save` + `v_faction_standing` views |
| B15 | this commit | v5→v11 live migration + end-to-end import validated on both real DBs |

## Per-item summary

### H0 (T0) — migration machinery

`PERSISTENT_TABLES = ("save", "meta")` (H4 later added `coverage`); the
bump drop-loop spares `EVENT_TABLES + PERSISTENT_TABLES`. `NEXT_VERSION`
is now derived as the complete `1 → … → SCHEMA_VERSION` chain, and the
walk steps through versions with no `EVENT_MIGRATIONS` entry (v4–v10)
instead of stopping — the defect that had stranded the real v5 DB.
Regression tests: a bump preserves `save`/`meta` rows and ids; an
off-chain v5 DB walks to current keeping E history; a v1 DB crosses the
full chain including the empty tail. No spec deviations.

### H1 (T2) — entity spine

`component.entity_id` added to the fresh W DDL (v11 bump rebuilds the
table); `update_entity_registry` now runs *before* `write_snapshot` in
`analyze.py` and its mapping stamps component rows. Indices added via the
idempotent `INDEXES` path (not the chain, per T2 as revised):
`idx_component_entity`, `idx_component_class`, `idx_component_sector`,
`idx_stock_entity`, and partial `idx_tx_buyer`/`idx_tx_seller`. Per B6's
verdict, `update_entity_registry` itself is untouched. No spec deviations.

### H2 (T10) — live-mode operations

`open_db` sets `journal_mode=WAL` (persistent), `busy_timeout=5000`,
`synchronous=NORMAL`. Views are recreated only when a fingerprint of
their definitions (`meta.views_version`) differs — plain connects are
DDL-write-free (the `schema_version` stamp is also only rewritten on
change). `write_reference` digests its full payload and skips the
ten-table rewrite when unchanged (`meta.reference_digest`). One
interaction surfaced by tests and fixed in the same commit: `meta` now
survives bumps (H0), so the bump path must delete both fingerprint
stamps — a stale stamp would otherwise leave views missing and R tables
empty after a bump. A second latent bug fixed here: the migration walk
advanced the same variable the new stamp check read, leaving the stored
`schema_version` stale after a walk.

Spec note: T10 offered "digest of the reference CSVs (or their mtimes)".
Implemented as a digest of the loaded payload (the row tuples fed to
SQLite) rather than file mtimes — `write_reference` receives `RefData`,
not paths, and the payload digest also covers packaged-vs-user-dir
overrides. Same guard shape, slightly stronger invariant.

### H4 (T14 + R7's M4 hook) — merge guard + coverage

Guard at the top of `merge_events`, mirroring the registry's high-water
check (`store.py` registry guard): incoming `save.game_time` below the
high-water mark → whole merge skipped with a warning. High-water mark =
`meta.merge_events_time` (game time of the last merged save, stamped
after each merge), falling back to the newest stored event time for DBs
whose history predates the guard — so pre-existing DBs are protected
from their first post-upgrade run. Equal game time merges normally
(idempotent re-analysis); synthetic saves without a game time are
exempt (they cannot be judged, and the test corpus relies on it). B3's
pinned test runs un-xfailed and passes, extended to assert the skip is
whole-merge and the stamp survives.

R7 fold-in: the `coverage` table (T3's DDL verbatim, P class) is created
and maintained by the same `_merge_window`/`_merge_log` change —
economylog streams reuse the E tables' epoch counter; `log:<category>`
streams get coverage-level epochs (gap = window starts past everything
stored for that category), giving the logbook the gap-awareness it
lacked. Per R7/plan, the backfill and the retirement of the two
`meta.*_window_start` keys stay in Phase 5's M4; until then coverage
rows describe only post-H4 merges (documented in db-schema.md). In
practice the first real merges already covered nearly the full
playthrough (below) because the economylog windows reach far back.

### M6 (T1 + T7) — views

`current_save` and `v_faction_standing` added to `VIEWS` (riding the
bump per R1). `v_faction_standing` reproduces the frames pivot —
effective = clamp(base + Σboosters, [−1, 1]), discount-only pairs emit
no row — and, per the revised T7, assumes nothing about booster decay.
No spec deviations.

## B15 — rehearsal and real-run evidence

### DB safety protocol

Backups taken before any real-DB write, checksums recorded and
re-verified afterwards (`sha256sum -c` → OK for both):

```
~/.local/share/x4analyzer/backup/
  x4_8E0C8E37-2192-49FD-BF4B-F535782A1C55.20260724T014105Z.pre-phase2.sqlite
    f06b61d74911ae78aa2f040ed12ed2e8c35462d3f1c11a7392f52fced5e441c0
  x4_94062A45-1DA1-47B2-911E-41A1AA606B8F.20260724T014105Z.pre-phase2.sqlite
    8f656415be9c901047c118c3f413bbda300e294fd35a827e14d2033b0a723d61
  checksums-20260724T014105Z-pre-phase2.txt
```

The pre-phase checksums are byte-identical to the ones the Phase 1
report recorded — nothing had touched the DBs in between.

### Rehearsal (scratch copies, session scratchpad `b15/`)

Both real DBs plus the reference CSVs were copied to a scratch data dir
and the real CLI run against it (`--data-dir`). All four rehearsal runs
behaved exactly as the real runs below (same commands, same counts), and
a fifth run validated the H4 guard on real data: feeding save_010
(t = 70,213) into the scratch 8E0C DB after the quicksave import
produced both skip warnings —

```
WARNING: save predates the entity registry's newest snapshot; …
WARNING: save (game time 70213) predates the stored event history
         (high-water mark 73392); event merge skipped — an older window
         would destroy newer history
```

— with E-table counts unchanged and 18,139 stored rows newer than the
stale save intact (pre-guard, B3 measured this exact scenario deleting
tens of thousands of rows).

### Real run: 9406 (the 559 h playthrough, v5 → v11)

Input: `/home/adam/Downloads/save_006.xml.gz` (guid 94062A45-…,
game_time 2,012,678.695 — the playthrough's newest save, per the DB's
own `source_file` provenance).

```
uv run x4-analyzer --save /home/adam/Downloads/save_006.xml.gz --no-browser
```

| table | pre (v5) | after run 1 | after run 2 |
|---|---|---|---|
| save | 2 | 3 | 4 (provenance row per import, by design) |
| trade_tx | 16,222 | 16,222 | 16,222 |
| stock_event | 476,569 | 476,569 | 476,569 |
| log_entry | 13,840 | 13,840 | 13,840 |
| removed_object | 863 | 863 | 863 |
| entity | 16,250 | 16,250 | 16,250 |
| entity_event | 0 | 0 | 0 |
| schema_version | 5 | **11** | 11 |

Every pre-existing E-table row survived the v5→v11 walk (the stored head
was this same save, imported twice in the v5 era, so the merge correctly
added nothing — count-identity here is simultaneously the migration
proof and an idempotency proof). Run 2 added **zero** rows to every
event table. Spine: 15,560 of 15,841 component rows stamped with
`entity_id` (the rest are clusters/sectors, outside the registry
domain). Dashboard built without errors both runs. This settles the
plan-F2 evidence loop: the repaired chain migrates a real off-chain DB.

### Real run: 8E0C (current playthrough, v10 → v11)

Input: `~/.config/EgoSoft/X4/12073019/save/quicksave.xml.gz`
(game_time 73,391.761, the playthrough's newest save).

| table | pre (v10) | after run 1 | after run 2 |
|---|---|---|---|
| save | 2 | 3 | 4 |
| trade_tx | 3,133 | 3,313 | 3,313 |
| stock_event | 375,015 | 383,778 | 383,778 |
| log_entry | 3,827 | 3,910 | 3,910 |
| removed_object | 1,014 | 1,115 | 1,115 |
| entity | 35,456 | 36,825 | 36,825 |
| entity_event | 62 | 65 | 65 |
| schema_version | 10 | **11** | 11 |

History extended (the quicksave is 1,517 game-seconds past the stored
head), then run 2 added zero event rows. Spine: 17,264 of 17,543
components stamped. Coverage after the merges (epoch 0 everywhere —
no real gap yet, consistent with B12's F9 caveat):

```
trade_tx     0  [   961.5, 73385.8]  window_start    961.5
stock_event  0  [    83.3, 73391.8]  window_start     83.3
log:upkeep   0  [    21.4, 72771.7]  … (7 more log:<category> streams)
```

Both DBs now run WAL (`-wal`/`-shm` sidecars present; checkpointed
before final checksums). Post-phase checksums:

```
78c953f780d4c042f274e7b2a0a5d055005936746290f324eb4d6a060b3bd391  x4_8E0C8E37-….sqlite
fb9f5591dbf5d16c27108eb2876f47c95c09a71f8c502a03303785c75e8717e1  x4_94062A45-….sqlite
```

Optional B15 re-run after B2 revives the log parsers (refinement R6)
remains open on the roadmap.

## Verification summary

- `uv run pytest -q`: **179 passed**, 0 xfailed —
  `test_older_save_merge_preserves_newer_history` passes as a normal test.
- Both real DBs at `schema_version` 11 with `save`/`meta` preserved and
  all E-table counts ≥ pre-migration values (tables above).
- Second identical import: 0 rows added to every event table, both DBs.
- Dashboards built without errors for the newest save of each
  playthrough (4 real runs + 5 rehearsal runs).
- Backups exist with recorded checksums; `sha256sum -c` verifies them.
