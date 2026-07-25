# Execution roadmap: DB-model plan + review backlog

Status: **executed — main sequence complete** (Phases 1–6 shipped
2026-07-23/24; schema at v17). This header and the per-item ✓ ledger
lines below record completion; the ordering text is kept as written
(originally: Status: ordering, 2026-07-23). The parallel research
track and the play track are the open remainder. Sequences every
activity in
[db-model-improvements.md](db-model-improvements.md) (T0–T14, via its §4
ids H0–H4 / M1–M6 / L1–L3) and the full P1/P2/P3 research backlog of
[data-model-review.md](data-model-review.md) (items 1–22, written **B1–B22**
here), plus the review's cross-document doc-propagation fixes (X1–X21,
batched). This file orders work; it executes nothing and edits neither
source doc.

**Ordering principle.** Fix the DB first — except where research, doc
corrections, or hygiene done first removes a named unknown or rework risk
for a named DB item. Every non-DB item scheduled ahead of DB work states
exactly what it de-risks. Research is placed where its evidence is
*consumed*; research that only upgrades documentation runs parallel or
after. Play items (require in-game action) live on a separate track and
are never a dependency of the main sequence.

Entry format: **id(s)** — description · *deps* · *executor* · *unblocks*.

---

## Main sequence

### Phase 1 — De-risk probes (one session; all three independent, run in parallel)

Cheap agent probes whose answers change how the first schema bump is
built. All read-only or scratch-copy work.

- **B6** (P1) — XPU-790 forensics + registry idempotency: one physical
  ship = duplicate-mint bug in `update_entity_registry`; two = live
  same-faction same-class collision. · deps: — · agent ·
  unblocks: **H1** (the entity spine should not be built on a registry
  with an open duplicate-mint suspicion — rework prevented: re-auditing
  every stamped `component.entity_id` after the fact); also the evidence
  for the X2 doc fix (DF-2).
  ✓ `2908837` — two physical ships; duplicate-mint refuted
  ([phase1-derisk-probes.md](../reports/phase1-derisk-probes.md) § B6).
- **B3** (P1) — Prove the older-save merge destruction on a scratch DB
  copy, pin it in a failing test, and pick the guard semantics
  (skip-with-warning vs backfill-only). · deps: — · agent ·
  unblocks: **H4** (T14's design explicitly defers the skip-vs-backfill
  choice to this evidence — rework prevented: shipping a guard whose
  semantics must change after the failure is finally characterized).
  ✓ `2908837` — destruction CONFIRMED on a scratch copy, pinned in a
  test; skip-with-warning chosen (phase1 report § B3).
- **B12** (P2) — Fire the epoch machinery once: merge two synthetic
  disjoint windows in a scratch copy, verify epoch increment + LAG gap
  isolation. · deps: — · agent · unblocks: **M4** (T3's coverage table
  keys on epochs whose increment path has zero empirical instances —
  rework prevented: a coverage backfill built on untested gap semantics)
  and confidence in **M2**'s epoch-partitioned `v_stock_flow`; upgrades
  db-schema F9.
  ✓ `2908837` — epoch increment + LAG gap isolation fired and confirmed
  (phase1 report § B12).

### Phase 2 — Schema bump v11 (one session; the plan's own first-bump batch)

The plan's §4 sequencing, plus M6 pulled forward (see refinement R1).

- **H0** (T0) — never-dropped `save`/`meta` (P class), repaired
  migration chain, regression tests. **B7** (P1, "make the plan's spine
  real") is folded in here: its column-enumeration half was discharged
  by the 2026-07-23 reconciliation (plan T6/F3 disposition); its residue
  *is* H0's implementation + tests. · deps: — · agent ·
  unblocks: H3, M1, M4, L2, L3.
  ✓ `a074dae` ([phase2-v11-bump.md](../reports/phase2-v11-bump.md)
  § H0 — no spec deviations; B7's residue implemented here).
- **H1** (T2) — entity spine: `component.entity_id`, pipeline reorder,
  W+E indices (via the idempotent `INDEXES` path). · deps: B6
  (advisory — proceed on its verdict) · agent · unblocks: H3, M2, M3.
  ✓ `3dea48f` (phase2 report § H1 — no spec deviations; B6's
  two-ships verdict consumed).
- **H2** (T10) — WAL + busy_timeout, view-lifecycle versioning,
  reference-write digest guard. · deps: — · agent · unblocks: live-mode
  reader/writer coexistence; removes C14 churn.
  ✓ `23a8d26` (phase2 report § H2 — no spec deviations).
- **H4** (T14) — stale-save merge guard. · deps: B3 (semantics
  evidence + the pinned test) · agent · unblocks: makes "no history
  loss" true; prerequisite for trusting any watch-mode ingestion.
  ✓ `a6fa760` (phase2 report § H4 — R7 applied: carries M4's
  merge-side coverage hook).
- **M6** (T1 `current_save` + T7 `v_faction_standing`) — views only,
  rides the bump. Pulled into v11 because `current_save` is referenced
  by the DDL of M2/M3/M5 as drafted (refinement R1). · deps: — · agent
  · unblocks: M2, M3, M5 (syntactic), ad-hoc SQL ergonomics.
  ✓ `9bfde80` (phase2 report § M6; R1 applied — rode the v11 bump).
- **B15** (P2) — re-import the 559 h playthrough's newest save (its DB
  is at schema v5): the live end-to-end test of H0's chain repair,
  run as this phase's validation capstone. · deps: H0 · agent ·
  unblocks: settles db-schema F10, save-semantics F9, and closes the
  plan-F2 evidence loop. (Optionally re-run after B2 to also validate
  the revived log parsers — refinement R6.)
  ✓ `095c174` — v5→v11 live walk + end-to-end import on both real DBs
  (phase2 report § B15); re-run per R6 as `1bf6f09` after B2
  ([phase3-event-semantics.md](../reports/phase3-event-semantics.md)
  § B15).

### Phase 3 — Event-stream semantics before the read layer (one session; two independent workstreams)

Research whose outcome shapes M2 and protects the E tables from
accumulating more mis-typed rows — the one research campaign that
genuinely belongs *before* more DB build-out.

- **B1** (P1) — re-model the economylog as four typed ledgers: what do
  money-block `tradeentry` records index; do `v`-less owner rows mean
  stock 0. · deps: — · agent · unblocks: **M2** (v_stock_flow's
  `ware != ''` guard and the stock=0 assumption are exactly what this
  settles — rework prevented: freezing view semantics around a
  pollution workaround, then re-typing the data under it); also the
  probable new ingestion T-item (refinement R2) — every import until
  then merges more tradeentry pollution into `stock_event`.
  ✓ `a07cf5a` — landed (with B18) as new plan item **T15**, schema v12
  (phase3 report § B1; R2 realized).
- **B18** (P3) — trade-block `transfer` entries (the missing 176 of
  `trades_executed`): rides B1's sweep infrastructure, same census
  method. · deps: B1 (shared tooling, not evidence) · agent ·
  unblocks: trade_tx completeness decision; savegame-structure/db-schema
  upgrades.
  ✓ `a07cf5a` — transfers ingested as `trade_tx.kind='transfer'`
  (phase3 report § B18).
- **B2** (P1) — harvest actual v9 log wordings, rewrite the logparse
  regexes. Independent of the schema work (D tables only) but fixes
  live features (`event_destroyed` is empty despite matching events).
  · deps: — · agent · unblocks: event_* tables + their dashboard tabs;
  the X7 doc fix (DF-2); makes a B15 re-run fully end-to-end.
  ✓ `daacd65` — v9 destroyed-wording harvest, `parse_destroyed`
  rewritten; X7 fixed with it (phase3 report § B2).

### Phase 4 — Trend layer, schema bump v12 (one session)

- **M1** (T5) — `v_snapshot` + rerun guard in `write_snapshot`.
  · deps: H0 · agent · unblocks: H3 (guard), rerun-immune series.
  ✓ `d7314a6` ([phase4-trend-layer.md](../reports/phase4-trend-layer.md)
  § M1 — deviation: canonical-snapshot-id rule instead of
  skip-on-rerun, annotated in the plan).
- **H3** (T4) — A-tables `sector_presence`, `station_metric`,
  `market_stat` + per-snapshot appends. · deps: H0, H1, M1 · agent ·
  unblocks: every trend-shaped feature; value compounds per analyzed
  save — the reason this phase comes right after v11.
  ✓ `235d0c6`, schema **v13** (this phase's "v12" label was written
  before T15 took that number; phase4 report § H3 — deviation:
  `sector_presence` class filter, annotated in the plan). Archive
  seeding shipped alongside as `18944d0` (`seed-trends` CLI, phase4
  report § Seeding — the spec extension for historic imports).

### Phase 5 — Domain read layer (one session; four largely independent items)

All view-mostly; M2/M3 need H1, M4 needs H0. Parallelizable except
where noted.

- **M2** (T6) — `v_trade`, `v_stock_flow`, `v_entity_life`; retire the
  frames blocks they replace. · deps: H1, M6; B1 (semantics — apply its
  ingestion verdict here or restate the guard, refinement R3) · agent ·
  unblocks: serve-mode API parity with the dashboard.
  ✓ `da2f247` ([phase5-read-layer.md](../reports/phase5-read-layer.md)
  § M2 — deviations: `cmdr_id`-keyed redirects, exec-id columns
  added; R3 applied, no `ware != ''` guard).
- **M3** (T8) — `v_station`, `v_player_fleet`, de-duplicate fleet
  resolution (equivalence test before deleting `_player_edges`).
  · deps: H1, M6 · agent · unblocks: kills C6 rollups + C7.
  ✓ `7bdae74` (phase5 report § M3 — equivalence-test branch taken;
  scope deviation: consumer-free R-era stations-frame columns
  retired).
- **M4** (T3) — coverage table + backfill, retire the two meta window
  keys. · deps: H0, B12 · agent · unblocks: queryable provenance;
  cheaper H4 guard checks.
  ✓ `589f119`, schema v14 (phase5 report § M4 — deviation: **three**
  meta keys retired, the third born with T15).
- **M5** (T9) — `region_yield` load (minutes) + `v_resource_area`.
  · deps: M6 · agent · unblocks: resource status as SQL. Caveats track
  B5/B11 (parallel/play) — the view is relocation-proof at sector
  granularity, so neither blocks it.
  ✓ `275866f` (phase5 report § M5 — as specced; R5's cross-link
  enforced by a permanent test).

### Phase 6 — Hygiene batch + fix-now doc propagation (one session)

- **L1** (T11) — naming/convention cleanups, rides this or any earlier
  bump. · deps: any bump · agent · unblocks: ad-hoc SQL ergonomics.
  ✓ `c75d3a6`, schema v15
  ([phase6-hygiene.md](../reports/phase6-hygiene.md) § L1 — deviation:
  no compat views; every consumer updated instead).
- **L2** (T12) — `interact` backfill via the repaired chain. · deps: H0
  · agent · unblocks: logbook interaction data.
  ✓ `08b8f7d`, schema v16 (phase6 report § L2 — the spec's optional
  column rename included).
- **L3** (T13) — zombie-table drop + `removed_object.first_save_id`.
  · deps: H0 · agent · unblocks: migration debt retired.
  ✓ `dcdbc12`, schema v17 (phase6 report § L3 — plus the live
  stale-view/RENAME-COLUMN walk fix the full-chain rehearsal caught).
- **DF-1** — doc-propagation batch, evidence already in the review (no
  research gate): X1 (spawntime NULL→0, db-schema), X4 (directionality
  claim vs measured reciprocity), X11 (depleted-area encoding scoping),
  X12 (db-schema's `idx_stock` half), X13 (db-schema's `save`
  provenance half), X15 (6.105 h → per-station T), X16 (gamedata module
  attribution), X17 (weapon-sim paragraph vs tests — highest doc risk:
  a reader could "correct" the tests toward the doc), X19 (MXH-411
  circularity). · deps: review only · agent · unblocks: docs stop
  contradicting code/tests.
  ✓ `624dab1` (phase6 report § DF-1 disposition table: 8 applied,
  X13 already discharged by Phase 2's rewrite).

---

## Parallel research track (agent; interleave with Phases 2–6, nothing in the main sequence waits on these)

**Status: P1 tranche executed (Phase 7, 2026-07-24: B4, B5, B13 — see
[phase7-research-p1.md](../reports/phase7-research-p1.md)); the
remaining tranche (B8, B10, B14, B16, B17, B19, B21, B22) and the play
track are the open remainder.**
(Exceptions already executed with the main sequence: B15 twice, B20's
number refresh ran as the post-Phase-6 close-out — see
[b20-number-refresh.md](../reports/b20-number-refresh.md); DF-2's
X7/X18 shipped with Phase 3.)

Ordered among themselves; each upgrades docs/models rather than gating
schema work.

- **B4** (P1) — settle the wormhole arrow (agent method: sweep archived
  saves for a tide-wave window; play confirmation is definitive but
  optional). · deps: — · agent (+play confirm, see play track) ·
  unblocks: X5/X6 doc fixes (DF-2); the map's one asymmetric arrow.
  ✓ `9dd0f74` — role names the PARTNER; arrow inverted (no wave window
  in 13 saves, but the script wiring is decisive); map fixed, X5/X6
  applied; play fly-both-ends still pending
  ([phase7-research-p1.md](../reports/phase7-research-p1.md) § B4).
- **B5** (P1) — rewrite the resource trackability/relocation model
  (displacement clustering + per-area `<reservations>` join). · deps: —
  · agent · unblocks: resource-model rewrite, T9/M5 caveat refresh,
  X9-adjacent doc fixes; any future per-area mining feature.
  ✓ `6307526` — relocation-on-depletion confirmed at scale (123 vs 6),
  20 km-lattice displacements, reservations = miner claims, contact
  trigger at population scale; model doc rewritten, T9/db-schema
  caveats refreshed (phase7 report § B5).
- **B13** (P2) — mod visibility end-to-end (why GameFiles sees 7 of ~60
  extensions; mod modcaps behind `capacity_floor`). Run before the
  remaining game-file research below — it sets the trust level of every
  "swept all game files" claim. · deps: — · agent · unblocks: B8/B10/B14
  interpretation, csv-reference fixes, wormhole W7.
  ✓ `35da463` — ego_dlc_* name filter is the whole gap (7 of 74
  folders); the 96 missing modcap macros are capacity-less vanilla
  content (mod hypothesis refuted); the live error is habitat capacity
  drift from an enabled mod; csv-reference trust scope + W7 recorded
  (phase7 report § B13).
- **B8** (P2) — full-galaxy Layer-2 pricing fit with pending trades.
  · deps: B13 (trust scope) · agent · unblocks: save-semantics pricing
  rewrite; X15 refinement beyond DF-1's restatement.
- **B10** (P2) — gatherspeed semantics for solids (agent: game-file
  analysis; play timing optional). · deps: B13 · agent (+play) ·
  unblocks: X9/X10 doc fixes (DF-2), map speed labels.
- **B14** (P2) — pricing Layer-3 structures: commissions/modifiers
  (agent census; play stacking-bound confirm optional). · deps: B13 ·
  agent (+play) · unblocks: X8 doc fix (DF-2), save-semantics F5.
- **B16** (P3) — re-measure the recycle rate (save_008+009 scratch
  import). · deps: — · agent · unblocks: the X14 stale-number
  replacement (DF-2).
- **B17** (P3) — mission `reward` / `distance_*` units (agent bounds;
  play stats-screen confirm optional). · deps: — · agent (+play) ·
  unblocks: savegame-structure unit fixes.
- **B19** (P3) — station oddments (`locked`, station `subordinates`,
  `economylog` attrs, NPC tolerance boosters; play halves optional).
  · deps: — · agent (+play) · unblocks: savegame-structure +
  faction-model gap fills.
- **B21** (P3) — reference-data provenance (record version/DLC at
  extraction, `source` columns for recipes/modcaps, regionyields via
  `_variant_paths`, decide sectorgraph `oneway`/X20). · deps: B13
  (shares the mod-path findings) · agent (+one play hop-validation) ·
  unblocks: X20 doc fix; note cross-link to M5 (if extraction output
  changes, re-run M5's cheap view verification — refinement R5).
- **B22** (P3) — encyclopedia `<known>` ledgers. · deps: — · agent ·
  unblocks: savegame-structure gap; `known`/`read` attr semantics.
- **B20** (P3) — perf + census refresh (re-time parse/find, anomaly
  census, relabel save-specific examples). Deliberately last: numbers
  should be re-measured after the pipeline changes above stop moving.
  · deps: Phases 2–5 landed · agent · unblocks: architecture.md /
  CLAUDE.md / viz-internals number refresh.
  ✓ `e1bf20f` — ran as the post-Phase-6 close-out
  ([b20-number-refresh.md](../reports/b20-number-refresh.md)).
- **DF-2** — research-gated doc-propagation batches, applied as each
  gate lands: X2 (gate B6), X3 (gate B9 — the plan's T7 instance is
  already discharged), X5/X6 (gate B4), X7 + X18 (gates B2/B1),
  X8 (gate B14), X9/X10 (gates B10/B5), X14 (gate B16), X20 (gate B21).
  X21 is already fully discharged in the plan (T9) — remaining
  propagation is the resource-model doc itself via B5. · deps: as
  listed · agent · unblocks: the five-document X3 correction and the
  rest of the cross-document contradictions.

---

## Play track (user in-game; never on the critical path)

**Status: OPEN.**

Nothing in the main sequence or research track *depends* on these; each
finishes or hardens a research item when done.

- **B9** (P2) — booster decay: observe or kill. Agent half is passive
  (diff future dated saves as they appear); the decisive halves are
  play: trigger a rep event + save twice ≥1 game-hour apart; compare
  clamp(base+Σboosters) to the in-game rep bar. · unblocks/upgrades
  when done: faction-model F1/F7 and the X3 propagation across the four
  remaining docs (DF-2); T7 needs no change either way (already
  decoupled).
- **B11** (P2) — nividium respawn amount: park a miner at a depleted
  nividium area past eligibility, save before/after first pull.
  · unblocks/upgrades when done: resource-model F5; tightens the
  `'full'`-overstates-nividium caveat in T9/M5's view.
- **Play confirmations of research-track items** (same ids as above,
  not separate entries): B4's fly-both-ends test (definitive arrow),
  B10's timed-miner comparison, B14's stacking-bound check (0.5×min),
  B17's stats-screen tie-breaker, B19's semantics halves, B21's Savage
  Spur hop validation. Each upgrades the corresponding doc fix from
  "probable" to confirmed when done.

---

## Dropped items

None. All 14 §4 ids (carrying all 15 T-items; M6 = T1+T7, B7 folded
into H0), all 22 backlog items, and all 21 X-fixes (batched into DF-1 /
DF-2, two already discharged in the plan) are scheduled above.

---

## Suggested further refinements (source docs *not* edited)

- **R1 — M6's priority understates a hard dependency.**
  *Disposition: applied in Phase 2 — M6 rode the v11 bump (`9bfde80`).* The plan's §4
  lists M6 (T1 `current_save`) as "medium, ride along with any bump",
  but the DDL of T4's populates and of T6/T8/T9's views references
  `current_save` directly — M6 is a syntactic prerequisite of M2/M3/M5
  and of H3's INSERT…SELECTs as drafted. The roadmap pulls it into the
  v11 bump; the plan's §4 dependency column could say so.
- **R2 — B1's outcome has no T-item to land in.**
  *Disposition: realized — the outcome became plan item T15, shipped as
  schema v12 (`a07cf5a`).* If the economylog
  re-model concludes `_merge_trades` must stop shunting `tradeentry`
  rows into `stock_event` (or re-type them), that is an ingestion +
  possibly E-data migration change with no home in the plan (T0–T14
  cover none of it). Expect a new T-item (T15?) after B1; until it
  lands, every import merges more mis-typed rows — the reason B1 sits
  at Phase 3 rather than the research track.
- **R3 — M2 bakes in the guard B1 may obsolete.**
  *Disposition: overtaken — T15 landed two phases before M2, so M2
  shipped without the guard; the view's comment restates the history
  (`da2f247`).* `v_stock_flow` keeps
  the `ware != ''` guard whose only known purpose is excluding
  tradeentry pollution (review savegame-structure F2). If B1's fix
  re-types those rows, the guard becomes dead code with a stale
  rationale; if M2 ships first, restate the guard's meaning when the
  ingestion fix lands.
- **R4 — B7 is now mostly discharged but the review still lists it as
  fully open.**
  *Disposition: held — B7's residue was implemented inside H0
  (`a074dae`); no re-enumeration occurred.* The reconciliation implemented its "enumerate the
  tradelog columns" half (plan F3 disposition) and specified the rest
  as T0; the backlog entry could be annotated the way the findings
  were, so a future session doesn't redo the enumeration.
- **R5 — M5 ↔ B21 extraction coupling is noted nowhere.**
  *Disposition: enforced — Phase 5 made the 0-mismatch check a
  permanent test, self-contained against the checked-out CSV
  (`275866f`); a B21 change now fails it loudly.* B21 routes
  regionyields through `_variant_paths`; if that changes the committed
  CSV, M5's `region_yield` load and view verification should be re-run
  (cheap — the 0-mismatch check is scripted in the plan's T9 notes).
- **R6 — B15 validates more than H0.**
  *Disposition: applied — B15 ran twice (`095c174` after Phase 2,
  `1bf6f09` after B2).* The review sells B15 as the
  chain test, but it also exercises `write_derived` end-to-end — which
  only becomes meaningful after B2 revives the destroyed-event parser.
  Running it twice (after Phase 2, again after B2) gets both proofs;
  the backlog entry implies a single run.
- **R7 — H4 and M4 touch the same merge seam in different bumps.**
  *Disposition: applied — H4's commit carries M4's merge-side hook
  (`a6fa760`); M4's backfill stayed in Phase 5 (`589f119`), and the
  seam was opened once.* T14's
  guard and T3's coverage updates both modify `_merge_window`'s
  entry/exit; implementing them a phase apart means reopening the same
  function twice. If session sizing allows, folding M4's merge-side
  hook (not the backfill) into the H4 change would touch it once.
