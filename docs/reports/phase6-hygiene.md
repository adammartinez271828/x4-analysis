# Phase 6: hygiene batch + fix-now doc propagation — L1, L2, L3, DF-1 (schema v17)

Executed 2026-07-24 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 6, specs in [db-model-improvements.md](../plans/db-model-improvements.md)
(T11, T12, T13 as revised) and the X-item evidence in
[data-model-review.md](../plans/data-model-review.md). One commit per
item, `uv run pytest -q` green at every commit — **205 passed** at phase
end (202 at entry; 3 new migration regression tests, several assertions
extended).

| Item | Commit | What shipped |
|---|---|---|
| L1 (T11) | `c75d3a6` | v15: `module` → `build_entry`, `modcap` → `module_cap`, `faction_meta.account` → `account_cr` (credits at load), `trade_offer.object_id` `''` → NULL, `npc` documented not renamed |
| L2 (T12) | `08b8f7d` | v16: `log_entry.interact` — loader reads the save's real attribute, history backfilled from `raw_attrs` on the chain, column renamed |
| L3 (T13) | `dcdbc12` | v17: managed-table inventory + bump-time zombie drop (`station_drones` retired), `removed_object.first_save_id` stamped at merge; **plus a live fix**: bumps drop all views before the migration walk |
| DF-1 | `624dab1` | 8 X-items applied, 1 already discharged (disposition table below) |
| report | this commit | phase report, ER render v17 |

## Per-item notes and spec deviations

### L1 (T11) — naming/convention cleanups, v15

- All four cleanups shipped; `npc` kept its name with the
  player-employees-only scope documented in the DDL and db-schema.md
  (the spec's lowest-priority option).
- **Deviation: no compatibility views.** The spec offers them "where
  consumers exist" — every in-repo consumer (frames, views, viz,
  aggregates, tests) was updated instead, and the phase requirement
  that grep find no old names in src/ and tests/ rules the shims out.
  Post-phase grep for `module`/`modcap`/`account`/`idx_module_host` as
  live identifiers: only the migration statements themselves, old-shape
  test fixtures, and version-history comments remain.
- The renamed tables are dropped by the `"14"` migration entry — the
  bump's drop path only knows current names, so without those two
  statements the old tables would linger as zombies (exactly the T13
  defect class).
- `frames.trade_offers` keeps its historic `''` id convention via the
  established `fill=` mechanism; the DB now stores NULL. Both analyzed
  saves have 0 hostless offers, so the change is currently latent.
- **User-visible fix:** the diplomacy tab's treasury was displayed in
  raw cents as credits (100× too high — `fmtMoney` never divided).
  `account_cr` = cents ÷ 100 at load corrects it; verified on the real
  DBs (8E0C: 48,925,669 stored cents → 489,256.69 cr at the pre-phase
  snapshot).

### L2 (T12) — `interact` fix + backfill, v16

- Loader fix (`_merge_log` reads `e.get("interact")`), the spec's
  `json_extract` backfill, and the optional column rename all shipped
  as `EVENT_MIGRATIONS["15"]` on the repaired chain — an off-chain DB
  in any pre-16 state corrects on open (same durability rule as T15).
- Fixture save now carries an `interact` attribute, pinning
  parser → merge → column end-to-end; the migration regression test
  covers backfill, no-attr rows, and csv-legacy (NULL raw_attrs) rows.
- Real DBs: **599 / 4,190** (8E0C) and **2,733 / 13,840** (9406)
  log entries recovered a value; the column was NULL everywhere before.

### L3 (T13) — migration hygiene, v17

- Every schema write records `meta('managed_tables')` (JSON array of
  the code's table names). On a bump, names in the stored inventory
  that the current code no longer lists are dropped; E/A/P tables are
  excluded by the keep-set and user tables are in no inventory. The
  regression test pins all four behaviors (zombie dropped, legacy seed
  dropped, E table kept even if listed, user table kept).
- Pre-v17 DBs have no stored inventory, so `LEGACY_TABLES =
  ("station_drones",)` seeds the known pre-inventory zombie:
  **8E0C dropped `station_drones` + its index (5,953 stale rows);
  9406 never had it** — the asymmetry the inventory mechanism now
  handles generically.
- `removed_object.first_save_id` (chain entry `"16"`, with a
  create-if-missing guard in the pre-v17 shape, following the
  v12/v14 pattern): stamped at merge from the current import. The
  always-NULL `time` column stays in the DDL (spec allows either) so
  fresh and migrated DBs keep identical shapes. All 1,339 / 863
  existing graveyard rows keep NULL — their arrival was never
  recorded; only rows merged from v17 on carry provenance.
- **Live bug found by the full-chain rehearsal, fixed here:** the v14
  backups carry views referencing `module`; after the 14→15 step drops
  it, SQLite's whole-schema validation fails the 15→16
  `RENAME COLUMN`. Views are code-owned and recreated after every
  bump, so `_ensure_schema` now drops ALL views before the walk. The
  incremental per-bump path never hit this (each bump recreated views
  before the next), which is precisely why rehearsing the full chain
  from a frozen backup is part of the protocol.

### DF-1 — doc-propagation disposition

Every claim was verified against the doc's *current* text before
editing (Phases 2–5 already rewrote parts of these pages), and against
the live data where cheap. No test was modified toward a doc — X17 and
X19 went the other direction.

| Item | Target doc | Disposition |
|---|---|---|
| X1 | db-schema.md | **Applied** (both spots: `component.spawntime`, `entity.spawntime`). Re-verified: 0 NULL spawntimes in `entity`, 9,757 zeros; component NULLs are only clusters/sectors (attribute absent, outside the registry domain) |
| X4 | db-schema.md | **Applied**: relations stored per-direction, measured fully reciprocal across all 486 pairs *in this save* — asymmetry stated as unobserved, not impossible (no game-invariant claim). The faction model doc's instance is research-gated (B9), untouched per the roadmap |
| X11 | savegame-structure.md | **Applied**, both halves. Re-verified on the live quicksave: 202 of 3,246 areas omit the `yield` attribute entirely, 0 write `yield="0"`; and in both playthroughs' DBs every area carries both yieldid suffix tokens and no `scrap`-ware area exists — the token/ware claims are now scoped to the analyzed saves |
| X12 | db-schema.md (its half) | **Applied**: `idx_stock` documented as serving ad-hoc owner-keyed reads only — not the `v_stock_flow` window (expression partition; EXPLAIN shows SCAN) nor the merge. Plan half was fixed in reconciliation |
| X13 | db-schema.md (its half) | **Already discharged** by Phase 2's rewrite: the save section and P-class table state never-dropped semantics correctly, and the versioning section documents the machinery. Added one residual sentence: persistence holds *since v11* — earlier bumps did drop the table, so the import log effectively begins there (the review's 13-imports-vs-2-rows evidence). Plan half fixed in reconciliation |
| X15 | save-semantics.md | **Applied**: the `≈ 6.105 h` universal constant replaced by storage.py's validated model — per-station per-pool `T` from pool capacity net of `FOOD_HOURS = 4.0` food buffers; workforce-adjustment warning kept. Labeled as the model the earlier single-station fit approximated; B8 tracks refinement beyond this restatement |
| X16 | architecture.md | **Applied**, siding with viz-internals.md and engines.py's own docstring: only `weapons.py` + `weaponsim.py` feed the gamedata dashboard (one tab); `engines.py`/`shields.py`/`shipmods.py` feed the external engine-mod rebalance harness |
| X17 | viz-internals.md | **Applied**, corrected toward `tests/test_weaponsim.py` (CLAUDE.md's designated source of truth): discrete heat cycle (EM Gun 29 shots / ~20.0 s cold, not the continuous 28.57 / 20.41 s), reload mods divide a stored reload *time* (Plasma Cannon validation), cooling happens between shots once `cooldelay` elapses. The tests were not touched |
| X19 | save-semantics.md | **Applied**: MXH-411's 310 moved out of the "validated in-game" list — it is the single data point the `+10/production` term was FIT from (circular as validation); the floor's three genuine validations (ABR-398/EBT-957/QJI-262) remain, matching test_drones.py's framing. The test was not touched |

Also swept the other reference docs for the L1 renames:
csv-reference.md's `modcap` feed pointer updated; no other doc
references the old names outside historical context.

## DB safety protocol

Backups before any phase write (WAL checkpointed first):

```
~/.local/share/x4analyzer/backup/
  x4_8E0C8E37-….20260724T200124Z.pre-phase6.sqlite
    9936a5f749124b802f98f7ca940c5a84fd9b8af7bb962dbe03078090f2fe0060
  x4_94062A45-….20260724T200124Z.pre-phase6.sqlite
    bda5b3e5f292a083756850fa1e1af66236ee1ea3ac2d236a0eb393eeba5c3a64
  checksums-20260724T200124Z-pre-phase6.txt
```

9406 was byte-identical to the Phase-5 report's post-run checksum;
8E0C had moved since Phase 5 (re-analyzed by the user on 2026-07-24
between the phases — expected, it is the live playthrough).

**Rehearsals** (scratch copies under the session scratchpad, reference
CSVs copied alongside; nothing touched the real DBs until each step's
rehearsal passed):

- *Per-bump, incremental*: v15 via full analyzer runs against the
  scratch data dir for both playthroughs (dashboards built, no errors;
  `account_cr` exactly = stored cents ÷ 100; old tables + index gone);
  v16 and v17 via `open_db` walks on the same copies (backfill counts
  below, inventory recorded, `station_drones` dropped).
- *Full-chain*: fresh copies of both **pre-Phase-6 backups** walked
  v14→v17 in one open — the required pre-phase-backup migration proof.
  Result on both: v17; **every E/P/A row count byte-preserved**
  (trade_tx, stock_event, money_event, log_entry, removed_object,
  entity, entity_event, save, coverage, and the three A tables —
  pre == post exactly); zero old-name/zombie leftovers; interact
  backfilled 587/4,141 (8E0C) and 2,733/13,840 (9406);
  `first_save_id` present. This rehearsal caught the stale-view /
  RENAME COLUMN failure described under L3 before it could reach a
  real DB.

**Real runs** (per item, after its rehearsal: full analyzer run per
playthrough — 8E0C from the current quicksave, 9406 from its archived
`save_006`):

| | 8E0C | 9406 |
|---|---:|---:|
| schema_version | 17 | 17 |
| trade_tx / stock_event | 4,144 / 412,385 | 16,337 / 469,522 |
| money_event / log_entry | 5,053 / 4,190 | 16,408 / 13,840 |
| log_entry.interact filled | 599 | 2,733 |
| removed_object (first_save_id) | 1,339 (0 — all pre-v17) | 863 (0) |
| entity | 41,507 | 16,250 |
| build_entry / module_cap | 42,380 / 240 | 40,410 / 240 |
| old tables/zombies left | 0 | 0 |
| save rows / distinct snapshots | 34 / 15 | 14 / 1 |

8E0C's event counts grew slightly during the phase (e.g. trade_tx
4,025 → 4,144): the quicksave had advanced past the last import, so
the first phase run merged genuinely new history — the merge doing its
job, not migration drift. 9406's counts are unchanged to the row
(its save is a frozen rerun). The frozen-backup full-chain rehearsal
above is the count-preservation proof.

Dashboards built end-to-end for both playthroughs at every applied
bump, without errors.

Post-phase state (WAL checkpointed):

```
cf4ccf029250e02bb22733aac42d604634a545bf6436b446fa158e49e26d653a  x4_8E0C8E37-….sqlite
9a1911420401faebbcff7d99dfa1939ea1f0999657f4570e4572155cffc167a2  x4_94062A45-….sqlite
```

## Verification summary

- `uv run pytest -q`: green at every commit; **205 passed** at phase
  end. New: v14→v15 rename-drop, v15→v16 interact backfill/rename, and
  v16→v17 zombie-drop/first_save_id regression tests; the fixture save
  pins `interact` end-to-end; migration tests that build old-shape DBs
  from current DDL now un-shape `log_entry`/`removed_object` first
  (same pattern as the existing `DROP COLUMN kind`).
- grep for pre-rename identifiers (`FROM/INTO/JOIN module`, `modcap`,
  `account`, `interaction`, `idx_module_host`, `station_drones`) in
  src/ and tests/: only migration statements, old-shape test fixtures,
  and version-history comments — no live references.
- Both real DBs at v17 via per-bump applies; pristine pre-Phase-6
  backup copies also walk v14→v17 cleanly in one open (rehearsal
  above), E/P/A row counts preserved exactly.
- Every DF-1 X-item dispositioned (8 applied, 1 already discharged
  with a residual note); corrections cite the review and keep the
  CONFIRMED-vs-hypothesis discipline; no test modified toward a doc.
- db-schema.md updated for renames/drops/new columns (tables,
  conventions, meta keys, versioning, index table, erDiagram);
  ER diagram rendered to `output/db-schema-er-v17.png` (earlier
  renders untouched).

## Left open (tracked, not Phase-6 scope)

- `v_stock_delta` alias removal after one release (Phase-5 carryover).
- DF-2 research-gated doc fixes ride their B-item gates (parallel
  track); X15's deeper pricing refinement is B8's.
- db-schema.md's header verification numbers (145 MB / v11 /
  17,543 components…) date from the review snapshot; B20's number
  refresh re-measures after the pipeline stops moving.
