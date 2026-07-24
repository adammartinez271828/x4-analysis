# Phase 1 de-risk probes: B6, B3, B12

Executed 2026-07-23 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 1. All three probes ran read-only against the real DBs or on scratch
copies; the DBs in `~/.local/share/x4analyzer` were checksum-verified
byte-identical before and after. Methods per
[data-model-review.md](../plans/data-model-review.md) backlog items 6, 3, 12.

Summary of verdicts:

| Probe | Question | Verdict |
|---|---|---|
| B6 | XPU-790: one ship (registry bug) or two (rule kill)? | **Two physical ships** — CONFIRMED; duplicate-mint refuted |
| B3 | Does merging an older save destroy E history? | **CONFIRMED** — all rows newer than the old window destroyed; guard should be **skip-with-warning** |
| B12 | Does the epoch machinery isolate coverage gaps? | **CONFIRMED** — db-schema F9 upgraded from hypothesis |

---

## B6 — XPU-790 forensics + registry idempotency

**Question.** The 8E0C DB holds two open entities (5318, 11691) with
identical slot evidence: code XPU-790, class `ship_s`, macro
`ship_ter_s_fighter_01_a_macro`, owner terran, spawntime 0. Is that one
physical ship double-minted by `update_entity_registry` (the double `save`
row for one file was the suspect path), or two simultaneously-alive
same-faction same-class ships?

**Method.** (a) Read-only queries against the real 8E0C DB for the XPU-790
entity rows and the `save` table; (b) a targeted `lxml.iterparse` sweep
(scratchpad script modeled on `save/landmarks.py`) over save_001 and
save_002 collecting every component with `code="XPU-790"`, with
class/macro/owner/spawntime and sector/cluster ancestry.

**Evidence.**

DB (read-only, `sqlite3 … ?mode=ro`):

```
SELECT entity_id, code, class, macro, spawntime, owner, first_seen, last_seen,
       gone_time, gone_reason FROM entity WHERE code='XPU-790';
(2178,  'XPU-790', 'ship_m', 'ship_spl_m_corvette_01_a_macro', 0.0,     'split',      39304.349, 71874.829, None,      None)
(2801,  'XPU-790', 'ship_s', 'ship_arg_s_scout_01_b_macro',    1033.967,'argon',      39304.349, 39304.349, 49634.568, 'disappeared')
(5318,  'XPU-790', 'ship_s', 'ship_ter_s_fighter_01_a_macro',  0.0,     'terran',     39304.349, 71874.829, None,      None)
(11691, 'XPU-790', 'ship_s', 'ship_ter_s_fighter_01_a_macro',  0.0,     'terran',     39304.349, 71874.829, None,      None)
(13168, 'XPU-790', 'ship_s', 'ship_tel_s_scout_01_a_macro',    0.0,     'scaleplate', 39304.349, 71874.829, None,      None)
```

The `save` table holds two rows for the same file
(`save_001.xml.gz`, game_time 71874.829, imported 01:49 and 02:04 UTC on
2026-07-23) — the review's suspect path.

Save sweep (`sweep_code.py XPU-790 save_001.xml.gz save_002.xml.gz`),
ship-class hits only (10 total hits include NPCs/computers/props sharing
the code, which are outside the registry's entity domain):

```
=== save_001.xml.gz ===  guid 8E0C8E37-…  components with code=XPU-790: 10
[0x1bcad] ship_m ship_spl_m_corvette_01_a_macro  split   spawntime=0  cluster_408
[0x40558] ship_s ship_ter_s_fighter_01_a_macro   terran  spawntime=0  cluster_101
[0x7cf36] ship_s ship_ter_s_fighter_01_a_macro   terran  spawntime=0  cluster_100
[0x8ec61] ship_s ship_tel_s_scout_01_a_macro     scaleplate spawntime=0 cluster_712
=== save_002.xml.gz ===  guid 8E0C8E37-…  components with code=XPU-790: 10
[0x1b755] ship_m ship_spl_m_corvette_01_a_macro  split   spawntime=0  cluster_408
[0x3ff43] ship_s ship_ter_s_fighter_01_a_macro   terran  spawntime=0  cluster_101
[0x7cb17] ship_s ship_ter_s_fighter_01_a_macro   terran  spawntime=0  cluster_100
[0x8e843] ship_s ship_tel_s_scout_01_a_macro     scaleplate spawntime=0 cluster_712
```

**Verdict — CONFIRMED: two physical ships; duplicate-mint refuted.**
Both saves contain two *distinct* live terran `ship_ter_s_fighter_01_a`
components coded XPU-790, in different clusters (100 and 101), with
identical code, class, macro, owner **and spawntime**. The registry's five
XPU-790 entities map 1:1 to the four live ships plus one dead earlier
generation (the argon scout, closed `disappeared`) — exactly correct.
The double `save` row did not double-mint: both fighter entities have
`first_seen` = 39304.349, the *first* registry import, not the
double-imported save's time; and the re-run is idempotent by construction
(matching claims the same entities deterministically; an equal-spawntime
match never mints). Registry idempotency stands; `save`-table provenance
duplication is a separate, known issue (db-schema F3, lands with H0).

Corollary sharpening X2: the collision is worse than the review's "add the
class condition" — these two ships are indistinguishable on *every* piece
of slot evidence the registry holds (code, class, macro, owner,
spawntime). The `(macro, owner)` tiebreak cannot separate them;
resolution falls to deterministic entity_id order, which keeps each
entity's own timeline consistent but can in principle swap which physical
ship is which between the two.

**Consequence.** H1 (entity spine) may proceed on this verdict: the
registry has no open duplicate-mint suspicion. The code-fallback rule is
corrected in three docs (applied with this report): a code fallback needs
at least the full (code, class) slot and even then is a heuristic —
same-faction same-class live collisions are real. No change to
`update_entity_registry` is needed for this finding (the H1 build can
proceed as designed); db-schema F2's "cross-faction" parenthetical is
fixed.

---

## B3 — older-save merge destruction

**Question.** db-schema F4 / plan C13: `_merge_window` executes
`DELETE FROM {table} WHERE time >= mintime` unconditionally, and
`_merge_log` the per-category equivalent — does feeding an older save of
the same playthrough (one wrong `--save`, or autosave rotation in a future
watch mode) actually destroy newer E-table history? And which guard
semantics should T14/H4 implement: skip-with-warning or backfill-only?

**Method.** Copied the 8E0C DB to scratch; parsed save_008
(same guid, game_time 66,772.675 — 5,102 s older than the DB's stored head
71,874.829); ran the pipeline's exact merge sequence
(`update_entity_registry` then `merge_events`, per analyze.py:33-35);
diffed per-table `COUNT/MIN(time)/MAX(time)` and boundary counts.

**Evidence** (`b3_probe.py` on `b3_scratch.sqlite`):

```
update_entity_registry: WARNING … skipped (returned 0 mappings)   ← registry guard works
merge_events: ran unconditionally                                  ← no guard

table            state     count    min(time)    max(time)
log_entry        before     3827        5.003    71874.684
log_entry        after      3583        5.003    66738.044
trade_tx         before     3133      961.477    71852.338
trade_tx         after      2527      961.477    66764.038
stock_event      before   375015       83.300    71874.797
stock_event      after    345978       83.300    66772.675

rows with time > 66772.675 (the old save's game_time):
  trade_tx:    before 606     after 0
  stock_event: before 29063   after 0
  log_entry:   before 244     after 0
```

**Verdict — CONFIRMED: history destruction, total within the window.**
Every row newer than the older save's window is gone: 606 trade_tx,
29,063 stock_event, 244 log_entry rows. Worse than a "tail truncation":
the old and new economylog windows share the same mintime (961.477 /
83.3 — the game's rolling window still reached back that far in both
saves), so the DELETE rewrote essentially the *entire* table with the
older window's contents. `removed_object` (append-only) and the entity
registry (high-water guard, `store.py:412-417`) were unaffected — the
guard asymmetry between `update_entity_registry` and `merge_events` is
exactly the bug.

One nuance for the guard decision: the scratch DB ended with 26 *more*
old stock_event rows than the real DB (345,978 vs 345,952 at or below the
cutoff) — the older save's window carried same-timestamp boundary
siblings that earlier merges' keep-fewer boundary rule had dropped. So
older saves do hold small amounts of data the DB lacks — but it lives
*inside* the covered range, not before it.

**Pinned test.** `tests/test_merge_guard.py::`
`test_older_save_merge_preserves_newer_history` — synthetic newer+older
save pair through the real `merge_events` path; asserts no post-older-save
rows are lost across trade_tx/stock_event/log_entry. Marked
`xfail(strict=True)` (suite stays green; H4's fix will flip it loudly).

**Recommended guard semantics: skip-with-warning** (T14's default), for
two evidence-backed reasons:

1. **Backfill-only would be a no-op in practice.** A safe backfill is
   insert-only *below* the stored minimum, but the observed windows share
   their minimum with the stored history — the strictly-older region is
   empty. The economylog's window reaches back nearly the whole
   playthrough, so this is structural, not incidental.
2. **The only real backfill value observed (the 26 rows) lives inside the
   covered range**, where insert-only requires row-level identity
   matching across saves — which does not exist (runtime ids drift; that
   is why `_merge_window` replaces at boundaries instead of matching
   rows). Recovering it means re-solving exactly the subtle overlap
   problem T14's design defers, for a 0.008 % gain.

Mirror the registry guard at the top of `merge_events`: compare
`save.game_time` to the stored high-water mark, skip the whole merge with
a warning when older. Implementation is H4's job.

**Consequence.** H4 can ship T14 as designed (skip-with-warning), with
this probe's numbers as the pinned justification and the xfail test as
the acceptance flip. db-schema F4's "undocumented" half is *not* yet
fixed here — the merge-semantics section still describes the destructive
behavior as designed; documenting the guard belongs with H4's
implementation, so the doc keeps matching the code.

---

## B12 — epoch machinery, fired for the first time

**Question.** db-schema F9: `MAX(epoch) = 0` in both populated DBs — the
coverage-epoch increment and `v_stock_delta`'s epoch-partitioned LAG had
zero empirical instances. Does the machinery actually work?

**Method.** Fresh scratch copy of the 8E0C DB; merged two synthetic
disjoint stock_event windows for a probe owner (`TST-001`) via
`store._merge_window` — window A [80,000, 80,010] starting past the
stored head (71,874.797), window B [90,000, 90,010] disjoint from A —
then recreated the views (as `open_db` does) and read `v_stock_delta`,
plus a control query with the epoch term removed from the partition.

**Evidence** (`b12_probe.py` on `b12_scratch.sqlite`):

```
stored MAX(time), MAX(epoch) before: (71874.797, 0)
after window A: [(80000.0, 100.0, epoch=1), (80010.0, 150.0, epoch=1)]
after window B: [... epoch=1 ..., (90000.0, 300.0, epoch=2), (90010.0, 340.0, epoch=2)]
rows per epoch: [(0, 375015), (1, 2), (2, 2)]   — real rows untouched

v_stock_delta (probe owner):          control without epoch partition:
  (80000.0, 100.0, e1, dv=None)        (80000.0, 100.0, dv=None)
  (80010.0, 150.0, e1, dv=50.0)        (80010.0, 150.0, dv=50.0)
  (90000.0, 300.0, e2, dv=None)        (90000.0, 300.0, dv=150.0)  ← phantom
  (90010.0, 340.0, e2, dv=40.0)        (90010.0, 340.0, dv=40.0)
```

**Verdict — CONFIRMED; F9 upgraded from hypothesis.** The increment path
fires exactly on gap (0→1 when the window starts past the stored head,
1→2 on the second disjoint window); within-epoch deltas are correct
(50, 40); the first row of each new epoch yields `dv = NULL` — the
control shows the 150-unit phantom delta the epoch term suppresses.
`SUM(dv)` consumers are unaffected by the NULLs. Two properties worth
noting for M4: `epoch` is **global per table** (one counter across all
owners — `MAX(epoch)` at merge time, not per-stream), and a gap yields
`NULL`, not 0, at the boundary row.

**Consequence.** M4 (coverage table keyed on epochs) and M2's
epoch-partitioned `v_stock_flow` can build on verified gap semantics.
db-schema.md's coverage-epochs bullet restated as CONFIRMED-by-synthetic-
probe (applied with this report), keeping the caveat that no *real*
import has ever incremented it.

---

## Integrity check

`sha256sum` of both real DBs taken before any work and after all probes —
byte-identical:

```
f06b61d7…  x4_8E0C8E37-2192-49FD-BF4B-F535782A1C55.sqlite
8f656415…  x4_94062A45-1DA1-47B2-911E-41A1AA606B8F.sqlite
```

All destructive work ran on scratch copies under the session scratchpad.
