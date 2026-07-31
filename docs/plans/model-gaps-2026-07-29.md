# Storage & pricing model gaps: triage and plan of action — 2026-07-29

## STATUS — 2026-07-30: Phases 0–4 complete

Executed as planned; the body below is left as written (it is the triage, not a
record of outcomes). Each Phase-2 item has its own dated report in
`../reports/`; the register is the authority on every status. Per item:

| item | outcome |
|---|---|
| P0 | views refreshed; `v_station_supply_position` exists. |
| P-corpus | 13 saves parsed. **Defect found and worked around everywhere: the scratch corpus stores every pending trade twice (`source='order'` + `'reservation'`) — dedupe on `trade_id` or every pending term doubles.** The analysis DB is keyed `(save_id, trade_id)` and is unaffected. |
| P1 | **E-027 → SUPERSEDED by E-129 (CONFIRMED).** `supplies` = the band midpoint, `s = +0.5`, 15,345 offers × 13 saves, max deviation 0.00 Cr. |
| P2 | **E-116 stays PENDING** — the (V, a) ridge is exact and 13 epochs do not break it; reading R6 still decisive. **New E-130 CONFIRMED:** V has no per-station/ware/faction structure. **E-007** narrowed: its drift is probably an allocation-model artifact. |
| P3 | **E-011 → FALSIFIED** (fill fraction, not a unit reserve). **E-015 → CONFIRMED** (role/predicate-keyed). **E-017 stays PENDING** — the storage-only population is 3 stations wide. Incidental: the yard constant −0.202, handed to P8. |
| P4 | Cap **strengthened**: confirmed above the target (30/30). **New E-132 (PENDING)** self-consumption exemption; **E-133 FALSIFIED** (net-saturation scope). The **"1.21–1.30× scavenger storage scale error" is WITHDRAWN** — it was the `a = +0.053` assumption, not the storage model. RAN-388 is `lockavgprice`; E-115's needs list is dead. Contradiction (8) narrowed to **DHI-588 alone**. **E-059 → FALSIFIED** as formulated. |
| P5 | **E-035 → CONFIRMED.** Clamp [0.90, 1.15] with zero escapes, sticky bounds, 15-value alphabet, corr(new, prev) +0.888. MXH-411's 1.5 stays a player check (R10). |
| P6 | **E-053 → FALSIFIED** (premise removed by E-106; the candidate is a no-op). **E-051 → FALSIFIED as stated**; replaced by **E-136 (PENDING)**, a latched allocation. Recommended and accepted: **no `analysis/storage.py` change**. |
| P7 | **E-061 → CONFIRMED**, with corrections — the mod moves habitat *capacity*, not the employment target, and nothing in the storage or pricing model consumes housing. Second blocker split out as **E-139**. |
| P8 | **E-028 → FALSIFIED as a mechanism** (BOM is a median 0 % of the allocation). **E-118 CONFIRMED on an independent denominator.** BOM-proportional build-station allocation **rejected**. **New E-135 (PENDING):** build storages fund loadout replacement. Promoted to `src/`: the build-task tree (schema v29). |
| P9 | Multi-stage net rule **FALSIFIED (E-137)**; **new E-134 CONFIRMED** — fixed `shady` tier ⇒ unstaffed (necessary, not sufficient), and the tier is mutable state; **E-128** stays PENDING and player-blocked, now on 13 epochs. |
| Phase 3 | `analysis/pricing.py` + `build_task` (schema v29) landed. Its own new result: **the yard book is the ordinary cosine, not a clamped power — E-131 CONFIRMED**, beating k = 2.62 by 27× on bin RMSE at equal parameter count. |
| Phase 4 | register, `reference/`, `models/` and this block synced; one addendum appended to the readings report. |

Net: 25 triaged items → 8 statuses moved, 11 new register entries (E-129…E-139),
no in-game reading consumed. What still needs the player: **R1** (VOM-540,
unchanged and still first), **R5**, **R6**, **R7–R11** — see the addendum to
[../reports/high-value-readings-2026-07-29.md](../reports/high-value-readings-2026-07-29.md).

Triage of **every open item** in the two subsystems — pricing (E-001…E-036,
E-112…E-118) and storage allocation (E-037…E-063, E-119…E-128) — plus the
recorded contradictions and the unmodelled areas, and a plan of action for the
subset that is settleable **without the player**. The in-game readings that
remain are ranked separately in
[../reports/high-value-readings-2026-07-29.md](../reports/high-value-readings-2026-07-29.md).

**Snapshot basis.** Everything in this document was re-derived on the current
snapshot, `save_id` **71** (`save_002`, game time 82,688). The numbers in
[price-categories-2026-07-29.md](../reports/price-categories-2026-07-29.md)
cite save 70, whose `cargo`/`trade_offer`/`station_storage` rows have been
rotated out of the DB; nothing below is carried over from that snapshot without
re-derivation. Baseline at time of writing: `uv run pytest -q` **277 passed**,
`uv run python tests/readings.py` **131/132**, register test green. Nothing
under `src/` or `tests/` was touched to produce this document.

**Status discipline.** Everything below marked *finding* is a HYPOTHESIS
verified on snapshot 71 only — none of it is registered, none of it is
CONFIRMED, and the register was deliberately not edited in this pass. Register
entries (next free id **E-129**) are created by the plan's execution, not by
this triage.

---

## New findings from the triage itself (snapshot 71, unregistered)

These emerged while re-verifying the seed items and change the triage; each is
stated with what would falsify it.

1. **The `supplies` price is the band midpoint: `price = (price_avg +
   price_max)/2`, i.e. a fixed `s = +0.5`.** All nine supplies wares on
   snapshot 71 match to the cent, including the half-credit ones (hullparts
   240.5 = (209+272)/2, metallicmicrolattice 53.5, siliconcarbide 1520.5), and
   save 70's tenth ware fits retroactively (claytronics constant 1.0750 =
   (2040+2346)/2 ÷ 2040). E-027's "10 unexplained per-ware constants" are one
   line: they were `(avg+max)/(2·avg)`, varying only with band spread.
   *Falsified by:* any supplies offer in any save ≠ its band midpoint.
   *Plan item P1; would supersede E-027 as a new entry.*

2. **The scavenger energy-cell cohort splits three ways, and the 5 M cap fails
   on eight of twelve stations.** On 71: three small stations (ANY-260,
   IDZ-231, AWU-079; allocations ≤ 248k = 3.9 M Cr) price on the ordinary
   uncapped supplier curve; **IRD-672 caps almost exactly** (implied target
   315,619 against 5 M/16 = 312,500, +1.0 %, resolving its old "throughput a
   fifth of modelled" price puzzle from E-047's investigation); and **eight
   stations (CGW-678, FXP-772, KWC-232, MDS-738, NDE-080, QIB-162, QTB-164,
   WIE-366) hold net positions of 0.68–1.79 M units — 2.2–5.7× the capped
   target — where the cap predicts band-min 10.00, and instead read
   11.27–15.10**, implying uncapped targets of 1.21–1.30× the modelled
   allocation. So the report's § 5 "storage scale error" and the register's
   contradiction (8) "do non-producers cap" are **entangled**: an allocation
   scale fix alone cannot explain prices above band min at these stocks, and
   the cap-scope question now has producer-side counterexamples, not just
   DHI-588. *Plan item P4; proposed new register entry.*

3. **E-115's "needs" list is stale on 71.** EOX-322, GMJ-316 and MOP-635 hold
   **no ware over 5 M Cr of allocation** any more, so they cannot settle the
   cap's scope. RAN-388 still discriminates (nividium 20,000 units = 10.2 M Cr,
   claytronics 4,367 = 8.9 M Cr) but is **not known to the player** (`knownto`
   and `known` both NULL) — and both of its qualifying wares sit at **exactly
   band average** (510.00, 2,040.00), which fits neither the capped nor the
   uncapped curve and smells of `lockavgprice` or a Boron special. Small check
   in P4.

4. **E-116 has become (probably) autonomous.** AXO-574 and GUX-488 — same
   capped solar design, two well-separated fills — both fit
   `(V = 5.00 M, a = 0.048)` to ±0.01 Cr on 71 (AXO net 133,133 → 17.26
   predicted vs 17.25 observed; GUX net 205,740 → 13.36 vs 13.36), while
   `V = 5.10 M` misses both by 0.15–0.20 Cr and `a = 0.058` by 0.15–0.16 Cr.
   Two stations at two fills is the "two points, two unknowns" E-116 asked the
   player for — modulo the assumption that `a` is shared across the two
   same-design stations. The archived-save corpus removes even that: AXO-574's
   stock has historically ranged 2,840–493,754, so per-station multi-fill
   trajectories exist. *Plan item P2.*

5. **E-015's discriminator already exists in the save.** CCN-497 posts, in one
   snapshot, production inputs at implied `a` −0.388/−0.400 (graphene, refined
   metals) and rations at +0.0060/+0.0061 (medical supplies, soja husk). The
   station constant does not drag its rations with it. A save-wide per-station
   sweep settles E-015 up to trust in the ration allocations (the tightest law
   in the project, MAD 0.0015); the in-game read becomes confirmation.
   *Plan item P3.*

6. **E-051 and E-053 are competing explanations for the same reading, and the
   corpus can discriminate them.** EIJ-609's allocation (34,829 read twice,
   model 37,227.6 on 71) is explained either by a lazy recompute lagging a
   recent efficiency change (E-051) or by war-pressure efficiency entering the
   rate but never the allocation (E-053). Thirteen archived saves spanning
   game time 69,324–84,643 (measured by the Phase 1 corpus build, 2026-07-30;
   the save *files* have been overwritten since the DB's older imports, so the
   61,949-era versions of save_006/save_008 that some register entries cite no
   longer exist on disk) show whether its `efficiency` changed recently and
   whether the offer-implied allocation ever drifted. Constant efficiency +
   constant implied allocation across ~15,300 s kills the lag. *Plan item P6.*

7. **Repo hygiene: `v_station_supply_position` is defined in `db/schema.py`
   but absent from the analysis DB** — the view set has not been refreshed
   since commit a0e55da. Any query following E-127's documentation fails until
   a pipeline run recreates the views. *Plan item P0.*

---

## Triage

Route legend: **AUTO** = settleable from save/game-file data alone; **PLAYER**
= blocked on an in-game reading or action; **BOTH** = an autonomous test can
settle or sharply narrow it, a reading confirms or accelerates. Value/effort:
H/M/L. "Reading Rn" refers to the ranked readings report.

### Pricing — open PENDING entries

| id | claim (one line) | blocked on | route | value | effort |
|---|---|---|---|---|---|
| E-007 | sell offset is exactly 0.050 + a small-allocation drift (0.058 → 0.049) | two same-ware producers with 10×-apart allocations, read in game | BOTH — corpus per-station `a` vs allocation (P2); small-allocation coverage is thin, so the reading may stay decisive | L–M (~0.01 band) | S (rides on P2) |
| E-011 | the −0.039 input offset is a per-module input reserve (`a ∝ 1/n`) | CCN-497 read twice, 5 and 30 min apart | BOTH — a reserve moves price *continuously with stock*; corpus gives CCN-497 at up to 13 epochs hours apart (P3); the reading adds the fine timescale (R4) | H (cause of open question #2) | M |
| E-015 | rations sit at +0.006 while the same station's inputs sit at its negative constant | one station, ration + input read at the same moment | BOTH — same-snapshot save data already shows it (finding 5); sweep settles modulo ration-allocation trust (P3); R4 confirms | M | S |
| E-017 | `a = +0.05` is the default and −0.039 the special case | a storage-only ware read on any station | BOTH — trade-station buy-only offers on 71 are the storage-only population; classify their implied `a` (P3) | M | S |
| E-027 | supplies price is a fixed per-ware multiple of avg (10 constants) | source of the constants unidentified | **AUTO — solved in triage** (finding 1); formalize + cross-save verify (P1) | H | S |
| E-028 | yards price off outstanding build demand, same form, k ≈ 2.6 | an NPC wharf with a known order queue | AUTO (hard) — parse yard ship-build queues from the save XML, build the demand denominator, refit k (P8) | H (701 offers) | L |
| E-031 | commission + event discounts clamp at 0.5 × min | holding a 25 % commission tier during a discount event | PLAYER only (R11) | L | — |
| E-034 | the deployable valuation vector E is a sampled, time-varying engine statistic | re-reading QJI-262's nine quotes a few game-hours later, paused | PLAYER only — the register records every offline candidate as already failed (R7) | M | — |
| E-035 | `buildpricefactor` re-rolls on an interval; the walk correlates with the previous value | sweeping the archived save series | **AUTO** — 13 archived saves; `build_price_factor` is parsed per save but only snapshot-retained, so re-parse the corpus (P5). The MXH-411 "stored 1.5 = slider" side-check stays PLAYER (R10) | M | S |
| E-116 | V is exactly 5,000,000 Cr (5.05–5.10 M optimum is the V/`a` trade-off) | one solar plant read at two well-separated stocks | **AUTO (probably)** — finding 4 + corpus trajectories (P2); reading R6 becomes confirmation | H | M |
| E-117 | Tidebreak is the 5 M cap (target 200.0), not E-018's fitted 173.1 | selling ~118 Protectyon to VOM-540 and reading the price | **PLAYER only** — VOM-540's stock has never left 1–22 in the recorded history (19 stock events over game time 397–79,057), so no archive point reaches the discriminating region; at stock ≤ 22 the two hypotheses differ by 20–30 Cr, inside the `a` scatter (on 71, stock 22: observed 27,277.26; E-018 predicts 27,277.71, cap 27,247.51) (R1) | H (separates whether the engine carries `m` or `a`) | — |

### Storage — open PENDING entries

| id | claim (one line) | blocked on | route | value | effort |
|---|---|---|---|---|---|
| E-051 | EIJ-609's allocation is recomputed lazily and lags an efficiency change | a third in-game read of its hull-parts max | BOTH — corpus efficiency/allocation history discriminates vs E-053 (P6, finding 6); the reading then confirms (R3) | M (the one readings failure) | S |
| E-053 | war-pressure efficiency enters the RATE but not the ALLOCATION | separation not implemented | **AUTO** — implement `efficiency/(1+work_effect)` split offline, score against saturated input buys on the 539 mod-touched stations + the readings fixture (P6) | M–H | M |
| E-059 | hybrid production+build stations belong on the computed path | an NPC hybrid + one in-game max | BOTH — ULG-519 confirmed hybrid on 71 (10 prod + 1 XL shipbuild module); computed-vs-derived comparison can *refute* offline (a computed value below the offer-derived lower bound is a real error); confirmation needs a reading | M | S |
| E-061 | `nd_habitat_cap_boost` (S 2500/M 5000/L 10000 vs stock 333/666/999) is a known-wrong input | `extract_modcaps` can't read `<diff>` without `<macro>`; `extract_wares` handles only `<add>` | **AUTO** — mod folder verified present; extend the diff handling, register in `gamedata/modpatch.py` (P7) | H (feeds ration buffer *and* efficiency on 2,499 built habitats) | M |
| E-062 | drone-pool capacity = Σ `unit_storage` + 10 per production module | any `units.maxcount` reading on a second production-heavy station | PLAYER only — the cap is not persisted in the save. Candidates on 71: EWQ-469 (floor 273 vs +10-rule 503), DIS-888 (141 vs 361) (R8) | L–M | — |
| E-063 | `<supplies><orders>` persists the drone build TARGET, not outstanding orders | raising a full station's target 30 → 40 and re-saving | PLAYER only (R9) | L–M | — |
| E-128 | the employment target splits across races by the LIVE mix (implemented) vs HABITAT mix (DCO-580 refutes live outright) | DCO-580 not player-visible; no other discriminating station exists; verified unchanged on 71 (bofu derived 225 > live-mix 221, water 405 > 398; workforce still 65/125/63) | **PLAYER only** — a player-built multi-race station is the one remaining experiment (R5). Autonomous side is exhausted: no station in any archived save has a habitat race set differing from its workforce race set (worth one corpus re-check in P9, cheap) | M (implemented rule is known-wrong at DCO-580) | — |

### Recorded contradictions in the two subsystems

| # | contradiction | state on 71 | route |
|---|---|---|---|
| (8) | do non-producers cap? VOM-540 yes, DHI-588 no, no single V fits both | **still open and now wider**: DHI-588 still refuses the cap (silicon obs 144.49 vs uncapped 144.18 vs capped 139.40; claytronics 2,223.59 vs 2,219.07 vs 2,180.34) and the scavenger cohort adds eight *producer* non-cappers + one capper (finding 2) | AUTO analysis (P4) + PLAYER acceleration (R2); the old "read RAN-388/EOX-322/GMJ-316/MOP-635" route is dead (finding 3) |
| (9) | live-mix vs habitat-mix race split (E-128) | unchanged, verified on 71 | PLAYER only (R5) |

Contradictions (3) faction symmetry and (4) anomaly census belong to other
subsystems and are out of scope here.

### Unmodelled areas and standing caveats

| area | state | route | value | effort |
|---|---|---|---|---|
| build-station allocation (68 stations with a built `buildmodule*` on 71) | no model; only the `stock + inbound + open buy` proxy; equal-volume rule known FALSE there | AUTO research — bill-of-materials candidate from queued module builds + ship queues (P8) | M–H | L |
| scavenger/Avarice allocation scale (~1.21–1.30× on eight stations, 71) | re-verified; entangled with the cap scope (finding 2) | BOTH — hypothesis tests offline (P4); LSO readings split storage from pricing decisively (R2) | H (largest off-model supplier block) | M |
| multi-stage internally-cycled wares (gross vs net flow) | not modelled; population never censused | AUTO — census + error quantification first; model only if material (P9) | L–M | M |
| `shady` tier driver (E-112's open half) | register says save-side settlement impossible; the `post` table (28,689 rows) and corpus tier-stability were never checked | AUTO for evidence, likely not for settlement (P9) | L | S |
| build-storage curve shape (E-118 caveat: denominator self-referential) | open | AUTO — outstanding module-build BOM as an independent denominator (P8) | M | M |
| E-127 zero-amount floor (satisfied station posts `amount = 0` supplies offer, so held+on-order under-floors) | **documented limitation, no experiment pending** — TDF-832 settled the sum rule incl. the both-terms case | no action; keep the caveat in db-schema.md | — | — |
| stale DB views (`v_station_supply_position` missing) | finding 7 | AUTO — refresh (P0) | hygiene | S |

**Counts.** 18 open PENDING entries (11 pricing, 7 storage) + 1 open
contradiction not itself a PENDING id ((8); (9) is E-128) + 6 unmodelled/
uncatalogued areas = **25 triaged items**, of which **2 closed-caveat/no-action**
(E-127 floor, and (9) folds into E-128). Routes: **9 AUTO**, **7 BOTH**
(autonomous test first, reading confirms), **7 PLAYER-only**.

---

## Plan of action — the autonomous subset

Ground rules, non-negotiable, restated from the model docs:

- **Fit shapes on BIN MEDIANS with equal weight per bin, never per-offer MAE.**
- **Score every candidate rule against the WHOLE population, not only the
  cohort it was derived from, and report both.** A rule that fits one cohort
  and degrades save-wide is over-fitting: say so and reject it.
- `stock + inbound + open buy amount` is a **lower bound**: a model value above
  it proves nothing; a derived value *exceeding* a prediction refutes it.
- Saves are modded: every join falls back on unknown macro/faction/ware.
  Reference CSVs stay STOCK; mod values are patched at runtime in
  `gamedata/modpatch.py` only.
- CONFIRMED vs HYPOTHESIS separated in every output; each claim states its
  falsifier.
- `docs/reports/` is append-only; register ids are stable; every settled claim
  syncs register + reference + models per CLAUDE.md before its task is done.
- Scratch work lives in the job dir (`$CLAUDE_JOB_DIR/tmp`), never in the repo.

### Phase 0 — hygiene (P0)

Re-run the pipeline once (`uv run x4-analyzer --save
~/.config/EgoSoft/X4/12073019/save/save_002.xml.gz --no-browser`) so the view
fingerprint refresh creates `v_station_supply_position`.
*Pass:* the view exists; event-table row counts unchanged (idempotent
re-import); baseline tests unchanged. *Files:* none.

### Phase 1 — corpus extraction (P-corpus)

One scratch script parses **all 13 archived saves** with the existing
`save/parser.py` (~22 s each) and writes per-save extracts to a scratch SQLite
in the job dir: trade offers (with flags), cargo, pending trades, per-module
`<production><efficiency>`, `build_price_factor`, workforce, and the module
build state of ~40 target stations. **Not** written to the analysis DB.
*Pass:* 13/13 parsed; the save_002 extract equals DB snapshot 71 on spot
checks. *Feeds:* P1, P2, P3, P4, P5, P6. *Files:* scratch only.

### Phase 2 — analyses (parallelizable after P-corpus)

**P1 — supplies midpoint rule (settles E-027).**
*Method:* for every `supplies`-flagged buy in all 13 saves, compare `price_cr`
to `(price_avg + price_max)/2` under the mod-patched band.
*Pass:* every offer equals the midpoint to the cent ⇒ new register entry
CONFIRMED, E-027 → SUPERSEDED pointing at it. *Fail:* any mismatch ⇒ record
the exception population, keep E-027 PENDING with the sharpened form.
*Files:* new `docs/reports/supplies-midpoint-2026-07-29.md`; docs-sync in
Phase 4.

**P2 — joint (V, a) solve (settles E-116, narrows E-007).**
*Method:* per-station multi-fill trajectories for the capped supplier cohort
(the ~55 energy-cell solar plants first, AXO-574/GUX-488 anchored by
in-game-verified allocations) across the corpus; solve (V, a) per station;
bin-median scoring per the ground rules, reported for the binding population
and save-wide.
*Pass (E-116):* per-station V confidence intervals cluster within ~1 % of one
value ⇒ CONFIRMED at that value (5.0 M expected); if intervals straddle
5.0–5.1 M with `a` absorbing the difference, E-116 stays PENDING and reading
R6 remains decisive. *E-007:* report `a` vs allocation across cohorts; the
small-allocation end (~2,500 units) has thin coverage, so expect narrowing,
not settlement.
*Files:* new `docs/reports/value-cap-solve-2026-07-29.md`.

**P3 — the offset family (E-011 reserve test, E-015 settle, E-017 test).**
*Method:* (a) per-station same-snapshot sweep on 71: every station with ≥ 1
unclamped ration buy AND ≥ 2 unclamped input buys — do rations ever track the
station's input constant? (b) corpus trajectories of implied input `a` vs
stock for the largest-|a| stations (CCN-497 −0.39 first): a per-module reserve
moves the price continuously with stock; a station constant stays flat.
(c) classify trade-station buy-only offers' implied `a` on 71 (the storage-only
population E-017 asks about).
*Pass (E-015):* rations at +0.006 on every such station while inputs vary ⇒
role/predicate-keyed offset CONFIRMED (reading R4 downgraded to confirmation).
*Pass (E-011):* implied `a` flat across epochs at moving stock ⇒ reserve
FALSIFIED; monotone drift with stock ⇒ reserve supported, R4 sizes the
timescale. *Pass (E-017):* storage-only wares read supplier-side `a` ⇒
supported; consumer offset ⇒ falsified.
*Files:* new `docs/reports/offset-family-2026-07-29.md`.

**P4 — cap scope + scavenger scale, jointly (contradiction (8)).**
*Method:* census every supplier offer with allocation value > 5 M Cr on 71
into cappers/non-cappers (the binding 399-analog, VOM-540, IRD-672 vs
DHI-588, the eight scavengers); test scope rules against ALL of them at once —
candidates: net-position-above-target saturation, faction, station design,
sector/tide phase (corpus gives Avarice at 13 epochs), produces-vs-resells;
separately test storage-side input fixes for the 1.21–1.30× scale (Avarice
sunlight, recycler multi-queue efficiency handling, storage-module macros/tag
groups) against the constraint that any fix must keep 131/132 readings and
must NOT explain the cap failure (no allocation change can lift a clamped
price off band min). Also the small RAN-388 check: are nividium/claytronics
`lockavgprice` there, or is exact-band-average pricing a Boron trade-station
property?
*Pass:* a scope rule that fits every capper and every non-capper without
degrading the save-wide fit ⇒ new register entry + E-115 refinement; a storage
fix reproducing the eight implied targets within ~2 % without regressing
readings ⇒ new storage finding. *Either failure is recorded in the rejected
tables.* This item may legitimately end "still contradictory, better bounded"
— that outcome updates contradiction (8) with the producer-side evidence and
the stale-needs correction (finding 3) regardless.
*Files:* new `docs/reports/cap-scope-scavenger-2026-07-29.md`.

**P5 — `buildpricefactor` dynamics (settles E-035's sweep half).**
*Method:* per-station factor across 13 saves; re-roll frequency, step-size
distribution, correlation with previous value, clamp behaviour at [0.9, 1.15].
*Pass:* the dynamics statement with population stats; register status moves on
whatever the data shows. The "MXH-411 stored 1.5 = slider" half stays PLAYER
(R10). *Files:* new `docs/reports/buildpricefactor-dynamics-2026-07-29.md`.

**P6 — war-pressure separation (E-053) and the EIJ-609 discrimination (E-051).**
*Method:* compute the vanilla multiplier `efficiency/(1+work_effect)` per
module; re-score the allocation basis (vanilla-part vs full efficiency)
against saturated input buys on the 539 mod-touched stations AND the readings
fixture; corpus history of EIJ-609's efficiency and offer-implied allocation.
*Pass (E-051 vs E-053):* efficiency constant across epochs + implied
allocation static ⇒ lag FALSIFIED, separation favored; a recent efficiency
step ⇒ lag stays live and R3 decides. *Pass (E-053 implementation):*
vanilla-basis must beat the current basis on the mod-touched population
without degrading the 87.2 % save-wide within-1 % figure or the readings —
else reject and record.
*Files:* `docs/reports/war-pressure-allocation-2026-07-29.md`; on a passing
result and approval, `src/x4analyzer/analysis/storage.py` + tests.

**P7 — `nd_habitat_cap_boost` registration (E-061).**
*Method:* extend the extraction to read `<diff>` files with no `<macro>`
element and `<replace>` payloads (the two recorded blockers), register the
boost in `gamedata/modpatch.py` (runtime patch — the committed CSVs stay
stock), re-score ration buffers and efficiency on affected stations.
*Pass:* readings stay ≥ 131/132; ration-implied employment targets on
habitat-boosted stations improve or stay; any regression rejects the patch
wiring, not the mod fact. *Files:* `src/x4analyzer/gamedata/modpatch.py`,
extraction module(s), `tests/` additions.

**P8 — yards, build storages, build stations (E-028, E-118 shape, the 68-station gap).**
The heavy item. *Method:* scratch-parse from `save_002.xml.gz` the outstanding
build bills: queued ship builds at yards (blueprint recipes from gamedata) and
unbuilt queued modules per station (module recipes already in `recipes.csv`),
net of build-storage stock. Then: (a) refit the yard curve's k on the demand
denominator (E-028 predicts k ≈ 2.60 survives; k drifting back toward 2.38 on
a demand basis falsifies); (b) re-test the build-storage curve (E-118) against
the BOM denominator instead of the self-referential `stock + amount`; (c)
score a BOM-proportional allocation model for the 68 build stations against
the proxy (Pearson per station-pair, and the lower-bound rule: model below
derived = error).
*Pass/fail per sub-item as stated; every rejected shape goes in the models'
rejected tables.* *Files:* new `docs/reports/build-demand-2026-07-29.md`;
parser handler in `src/x4analyzer/save/parser.py` (single pass, per
convention) + tests **only if** the scratch results justify promoting it, on
approval.

**P9 — small sweeps.**
(a) multi-stage internally-cycled wares: census stations whose output feeds a
later stage of the same station; quantify the gross-vs-net error; model only
if material. (b) `shady` tier: join tiers against `post` rows and corpus
tier-stability (evidence, not settlement — E-112 stays open unless the post
state discriminates). (c) corpus re-check that no historical save holds a
habitat-vs-workforce race-set divergence (E-128 stays PLAYER unless one
exists). *Files:* one combined report.

### Phase 3 — implementation (on approval, gated on Phase 2 results)

- **The price model enters `src/` for the first time**: `analysis/pricing.py`
  implementing the closed form + the book classification (main sequence,
  lockavgprice, supplies midpoint from P1, shady tiers, build storage, yards,
  player), with the cap per P4's outcome; tests seeded from the in-game
  validated numbers (UDX-946 53.30/90.72, GUX-488 13.36, EBT-957 46.75) and
  the scoring harness enforcing the bin-median rules. No widget yet.
- `analysis/storage.py` changes only as P6/P7 justify; DB schema/views as
  needed (e.g., persisting corpus-derived series if we decide to keep them —
  default is not to).

### Phase 4 — docs sync (serialized, single owner)

One agent applies ALL register/reference/models edits after the analyses
land: new entries (supplies midpoint superseding E-027; the scavenger/cap
producer-side evidence; P-item outcomes), E-115's stale needs-list correction,
contradiction (8) update, summary-table refresh, rejected-table additions.
Verified by `uv run pytest tests/test_experiments_register.py -q`.

### Dependency order

```
P0 ──────────────────────────────┐
P-corpus ──► P1 P2 P3 P4 P5 P6 ──┤
P7 (independent) ────────────────┼──► Phase 3 (approval-gated) ──► Phase 4
P8 (independent, heavy) ─────────┤
P9 (after P-corpus) ─────────────┘
```

### Proposed subagent split (all `model: opus`; no shared files)

| agent | items | owns (exclusive) |
|---|---|---|
| corpus | P0, P-corpus, P2, P5 | scratch corpus DB; `docs/reports/value-cap-solve-…`, `…/buildpricefactor-dynamics-…` |
| offsets | P1, P3 | `docs/reports/supplies-midpoint-…`, `…/offset-family-…` |
| cap-scope | P4, E-059 offline half | `docs/reports/cap-scope-scavenger-…` |
| build-demand | P8 | `docs/reports/build-demand-…`; (on approval) `src/x4analyzer/save/parser.py` + its tests |
| gamedata | P7 | `src/x4analyzer/gamedata/modpatch.py`, extraction modules, their tests |
| storage-model | P6, P9 | `docs/reports/war-pressure-allocation-…`, P9 report; (on approval) `src/x4analyzer/analysis/storage.py` + its tests |
| pricing-impl | Phase 3 price model | `src/x4analyzer/analysis/pricing.py` + its tests |
| docs-sync | Phase 4, runs LAST, alone | `docs/experiments/README.md`, `docs/reference/save-semantics.md`, `docs/models/*.md` |

**`docs/experiments/README.md` is single-owner (docs-sync) — no other agent
touches it, ever.** Analysis agents write only their own report file and
scratch; implementation agents write only their listed src/tests files.

### Verification (after execution)

```bash
uv run pytest -q                                   # ≥ 277 passed, no regressions
uv run python tests/readings.py                    # ≥ 131/132
uv run pytest tests/test_experiments_register.py -q
# idempotency: re-run the P0 import; event-table counts must not change
```

Plus per-item pass/fail criteria above, and the standing rule: any claim
settled ⇒ register + reference + models agree before the task closes.
