# War-pressure separation (E-053) and the EIJ-609 discrimination (E-051) — 2026-07-30

Plan item **P6** of [../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md).
Analysis only: nothing under `src/`, `tests/` or `docs/experiments/` was touched
to produce this. Two data sources, both re-derived here:

- the analysis DB at `save_id` **71** (`save_002`, game time 82,688), resolved
  from `current_save`, and
- the Phase-1 corpus of **13 archived saves**, game time 69,324 → 84,643
  (~15,319 s), station identity keyed on `(code, class, macro)`.

Corpus handling caveats applied throughout: the corpus `trade_pending` stores
every trade **twice** (`source='order'` and `source='reservation'`), so all
inbound/outbound terms below are deduplicated on `trade_id`; the analysis DB's
`trade_pending` is keyed on `(save_id, trade_id)` and needs no such treatment.
The corpus `station_module` table repeats the whole build plan twice (the
construction sequence and the expand queue carry the same entry ids), so every
per-epoch model run below dedupes on `(host_id, entry_id, idx)` — without it
every pool capacity doubles and the save-wide within-1 % score collapses from
92 % to 10 %.

**Headline.** E-053 is dead as stated — there is no war-pressure term inside
`<production><efficiency>` to separate, so the separation candidate is a
bit-for-bit no-op save-wide. E-051's *lag* is real but its *prediction* is
falsified: EIJ-609's allocation did not drift toward 37,228, it stepped the
other way, from tracking its live efficiency to a multiplier of exactly 1.0,
and the model reproduces its 34,829 reading with **no special rule** on every
corpus epoch from game time 83,025 onward.

---

## 1. E-053: there is nothing to separate

E-053 says the mod's war-pressure efficiency term enters the production RATE
but not the ALLOCATION, and proposes recovering the vanilla part as
`efficiency / (1 + work_effect)`.

Measured on snapshot 71 over all **1,630** `module_production` rows, with the
ceiling taken as `(1 + work_effect) × sunlight` (sunlight only for
`energycells`, which is the only solar product):

| recipe basis | rows above the ceiling | stations |
|---|---:|---:|
| **mod-patched recipes** (what the pipeline runs on) | **0** | **0** |
| stock recipes (bundled CSVs) | 44 | 44 |

The 44 stock-recipe breaches are all `advancedelectronics` — exactly E-105's
fingerprint, and entirely explained by Faction Fix Pack's recipe rewrite
(`work_effect` 0.36 → 0.40), which `gamedata/modpatch.py` already applies at
runtime. Under the patched recipes the ratio distribution is

```
efficiency / ((1+work_effect) × sunlight):   == 1.000 exactly  1,019 rows
                                             <  1.000            611 rows
                                             >  1.000              0 rows
```

so the sub-unity population is **understaffing** (the workforce ratio inside
the engine's own multiplier), not a mod bonus. This is consistent with
**E-106 · FALSIFIED**, which established that Faction Fix Pack's war-pressure
bonus is a post-hoc `<add_cargo>` on production-finished events and is
therefore *invisible* in `<efficiency>`. E-053 was written against the
assumption E-106 later killed.

### The mandated scoreboard

Every candidate scored against **all** offer-derived saturated input buys on
snapshot 71 (`stock + inbound + open buy amount`, `supplies`/`shady` excluded,
computed rows only), reported save-wide **and** per cohort, plus the in-game
readings fixture replayed through `tests/readings.py`'s `storage_fn` hook
(the fixture itself was not modified).

| multiplier basis for the ALLOCATION | save-wide within 1 % | n | `eff == ceiling` cohort | n | `eff != ceiling` cohort | n | readings (in-game) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **A · `efficiency` (current)** | **94.2 %** | 3,629 | 96.8 % | 1,908 | 86.9 % | 942 | **131/132** |
| B · `min(efficiency, ceiling)` — the E-053 separation | 94.2 % | 3,629 | 96.8 % | 1,908 | 86.9 % | 942 | 131/132 |
| C · the ceiling itself, `(1+work_effect)×sunlight` | 77.5 % | 3,628 | 96.8 % | 1,908 | 22.5 % | 941 | 121/132 |
| D · 1.0 (bare recipe) | 33.5 % | 3,641 | 13.4 % | 1,915 | 17.9 % | 949 | 105/132 |

B is **identical to A on every row** — 0 of 10,087 storage rows differ — which
is the expected consequence of "nothing breaches the ceiling". C, the
generalisation of E-053's spirit (ignore transient staffing, allocate on the
design's full work effect), is a clear regression: it costs 64 points of the
under-staffed cohort and 10 in-game readings.

The plan's pass condition for E-053 ("vanilla-basis must beat the current basis
on the mod-touched population without degrading the save-wide figure or the
readings") is therefore **not met — it cannot be met, because the candidate is
a no-op.**

*Cohort note.* The 539 "mod-touched stations" in
[../models/station-storage-model.md](../models/station-storage-model.md) are
the stations where `efficiency != 1 + work_effect`; on snapshot 71 that
population is 446 stations (942 scorable input rows), and the split above uses
it. It is a *staffing* cohort, not a mod cohort.

**Recommended status: E-053 → FALSIFIED** (premise removed by E-106; the
separation is unimplementable and, as `min(eff, ceiling)`, a no-op on
1,630/1,630 modules). *Falsifier if anyone wants to revive it:* any module in
any save whose reported `<efficiency>` exceeds `(1 + work_effect) × sunlight`
under mod-patched recipes.

---

## 2. E-051: EIJ-609 across the 13 epochs

### 2.1 The price route is uninformative here — state it first

The plan offered inverting the sell-side price curve (supplier `a = +0.053`,
`m = 1`) as one route to EIJ-609's implied allocation. Done for all 13 epochs
it gives a flat **24,208 – 24,360** (median 24,262, CV 0.0021, OLS trend
+0.05 % over the whole 15,319 s span). That number is **not the allocation**:
it is ≈ 1.015 × (5,000,000 Cr ÷ 209 Cr band average) = the **5 M Cr price
cap**, within the scatter on `a`. Calibrated against the 114 other hull-parts
sellers on snapshot 71 whose model allocation is computed, the price-implied
figure clusters at 24.2–25.0 k for the six largest stations regardless of their
model allocation (49,912 – 66,124), which is the cap turning on.

So for EIJ-609 the price carries **no information about the allocation** and
cannot show drift. Any conclusion drawn from it would be an artefact.
(Side value for P4/contradiction (8): EIJ-609 is a **producer** that *does*
cap — its hull-parts allocation is worth 7.8 M Cr — so it joins IRD-672 on the
capper side of the ledger.)

### 2.2 The input route: the allocation is directly readable, and it moved

EIJ-609's three production inputs post saturated buy offers in every epoch, so
`stock + inbound + open buy` is its allocation, to the unit. All three move in
exact lockstep (they share one pool and one `T`):

| save | game time | live `efficiency` | energy cells | graphene | refined metals | matches the model at |
|---|---:|---:|---:|---:|---:|---|
| autosave_01 | 69,324 | 1.13962 | 8,804 | 4,402 | 30,817 | — (implies ≈ 1.1837, stale) |
| autosave_02 | 76,511 | 1.13059 | 9,022 | 4,511 | 31,578 | — (implies ≈ 1.1225) |
| save_006 | 78,583 | 1.13059 | 8,985 | 4,492 | 31,448 | **1.13059 exactly** (model 8,985.3 / 4,492.7 / 31,448.6) |
| save_007 | 79,537 | 1.12634 | 8,997 | 4,498 | 31,491 | **1.12634 exactly** (model 8,997.6 / 4,498.8 / 31,491.6) |
| save_008 | 80,387 | 1.12634 | 8,997 | 4,498 | 31,491 | 1.12634 |
| autosave_03 | 81,588 | 1.12634 | 8,997 | 4,498 | 31,491 | 1.12634 |
| save_009 | 81,948 | 1.12634 | 8,997 | 4,498 | 31,491 | 1.12634 |
| **save_010** | **82,125** | 1.12634 | **9,477** | **4,738** | **33,170** | **1.0 exactly** (model 9,477.3 / 4,738.7 / 33,170.6) |
| save_001 | 82,130 | 1.12634 | 9,477 | 4,738 | 33,170 | 1.0 |
| save_002 | 82,688 | 1.12634 | — | 4,738 | 33,170 | 1.0 |
| save_003 | 83,025 | *no `<production>` block* | 9,477 | 4,738 | 33,170 | 1.0 — **and the model's own rule (E-043) now says 1.0** |
| quicksave | 83,987 | *no block* | 9,477 | 4,738 | 33,170 | 1.0 |
| save_005 | 84,643 | *no block* | 9,477 | 4,738 | 33,170 | 1.0 |

Its two ration wares (`medicalsupplies` 4,374, `sojahusk` 4,665) are constant
in all 13 epochs, as they must be — the buffer runs off the employment target,
not off `T`.

Solving the model for the multiplier that reproduces each epoch's derived
allocation (bisection on the energy-cell row, full universe model per epoch):

```
save          gtime  live eff  implied mult
autosave_01   69324   1.13962       1.18367     stale, from a higher past efficiency
autosave_02   76511   1.13059       1.12245
save_006      78583   1.13059       1.13265     = live  (+0.18 %)
save_007      79537   1.12634       1.12925     = live  (+0.26 %)
save_008      80387   1.12634       1.12925     = live
autosave_03   81588   1.12634       1.12925     = live
save_009      81948   1.12634       1.12925     = live
save_010      82125   1.12634       1.00340     <-- step to 1.0, live unchanged
save_001      82130   1.12634       1.00340
```

**Findings, with their falsifiers.**

1. **[OBS] EIJ-609's allocation tracked its LIVE efficiency for at least
   12,600 s** (78,583 → 81,948, four epochs, two different efficiency values,
   agreement 0.18–0.26 %). Its 34,829 reading is therefore *not* a station that
   never listens to efficiency. *Falsified by:* any epoch in that window whose
   derived inputs disagree with the live-efficiency model by more than ~1 %.
2. **[OBS] It stepped to a multiplier of exactly 1.0 between 81,948 and
   82,125**, with the live `efficiency` unchanged at 1.12634 across the step,
   and has stayed there for the remaining 2,518 s. *Falsified by:* a later save
   in which its derived inputs return to the 8,997 / 4,498 / 31,491 triple.
3. **[OBS] By 83,025 the station carries no `<production>` block at all**, at
   which point the model's own idle rule (E-043, multiplier 1.0) produces
   34,829 / 9,477 / 4,738 / 33,170 with no exception needed. The station had
   been starving throughout (`medicalsupplies` 0 in every epoch; `sojahusk`
   reached 0 at 81,588 and stayed there) with a constant 810 paranid workforce.
4. **[INF] The allocation is a latched snapshot of the module multiplier taken
   at some recompute event, not a continuously evaluated function.** It is
   stale at 69,324 (implying ≈ 1.1837, higher than any efficiency observed in
   the corpus) and again at 82,125–82,688 (implying 1.0 while the block still
   reports 1.12634 — the latch fired ~900 s *before* the block disappeared,
   presumably while the starving modules were stalled between cycles).
5. **[OBS] E-051's stated prediction is FALSIFIED.** It predicted the
   allocation drifts *toward* 37,228; over 15,319 s it went the other way, and
   the 34,829 value has been stable for the last four epochs.

### 2.3 Is the lag a general rule? No.

Scored across all 12 epoch transitions, on the rows whose module efficiency
actually changed since the previous epoch, live-efficiency versus
previous-epoch-efficiency (the lag), against the same saturated-buy ground
truth:

| save | game time | live, changed rows | stale, changed rows | n | live, save-wide | stale, save-wide |
|---|---:|---:|---:|---:|---:|---:|
| autosave_02 | 76,511 | **82.7 %** | 39.0 % | 896 | 91.9 % | 81.0 % |
| save_006 | 78,583 | **79.2 %** | 56.9 % | 802 | 91.5 % | 86.6 % |
| save_007 | 79,537 | **80.9 %** | 59.1 % | 528 | 93.7 % | 90.6 % |
| save_008 | 80,387 | **76.0 %** | 61.4 % | 578 | 91.8 % | 89.5 % |
| autosave_03 | 81,588 | **77.0 %** | 59.7 % | 640 | 91.8 % | 88.8 % |
| save_009 | 81,948 | **79.6 %** | 65.1 % | 388 | 91.2 % | 89.6 % |
| save_010 | 82,125 | **83.7 %** | 62.9 % | 221 | 94.2 % | 92.9 % |
| save_001 | 82,130 | 73.8 % | 73.8 % | 80 | 93.5 % | 93.5 % |
| save_002 | 82,688 | **83.7 %** | 70.1 % | 454 | 94.2 % | 92.5 % |
| save_003 | 83,025 | **83.1 %** | 65.7 % | 356 | 95.0 % | 93.3 % |
| quicksave | 83,987 | **81.9 %** | 63.7 % | 641 | 92.0 % | 88.7 % |
| save_005 | 84,643 | **81.8 %** | 64.1 % | 595 | 92.0 % | 89.1 % |

The live efficiency wins at every transition, by 10–44 points on the rows where
the two differ (save_001 is 5 game-seconds after save_010, so almost nothing
changed and the two bases coincide). The corpus model reproduces the analysis
DB exactly where they overlap — corpus `save_002` scores 94.2 %, the same as
snapshot 71 — which validates the per-epoch rebuild.

**So: reading the live `efficiency` is the right rule for the population, and
EIJ-609 is an exception whose latch happens to be visible.** Any global lag
model would cost 10–44 points on the moving rows and 1–11 points save-wide.

*Caveat inherited from P2:* about 3 % of corpus offer points carry a price
bit-identical to the previous epoch while the net position moved (the ~65 s
`updatetradeoffers` timer), and offers can be stale in the same way as
allocations. That noise is symmetric between the two candidates above and
cannot manufacture a 10–44 point gap, but it does mean the ~80 % (rather than
~95 %) live-basis figure on the *changed* rows is partly measurement, not
model error.

### 2.4 Recommended register outcome

- **E-051 → FALSIFIED as stated.** Its prediction (drift to ~37,228 on a later
  read) is contradicted by 13 epochs; the allocation moved to 1.0 and stayed.
  Its underlying intuition — that the allocation is *latched*, not live —
  survives and should get a **new id**, PENDING, with the evidence in § 2.2 and
  the falsifiers listed there. The in-game reading R3 is no longer the
  discriminator it was: the save data already answers it.
- **E-053 → FALSIFIED**, per § 1, cross-referencing E-106.
- **The storage model's "Known exceptions" item 1 (EIJ-609) can be rewritten**:
  the model does reproduce 34,829 — on every corpus epoch from 83,025, using
  the existing idle-module rule. The fixture entry is a snapshot of the
  anomalous window (82,125–82,688), not a permanent model failure. *Do not
  edit `tests/data/station_readings.json` on my account* — that is a separate
  decision, and the fixture is still a valid record of what was read.
- **Item 2 of the same section ("war-pressure bonuses enter the rate but not
  the allocation … not yet implemented") should be struck** and replaced with a
  pointer to E-106: the term is not in `<efficiency>` at all.

---

## 3. Is the Phase-3 `analysis/storage.py` change justified?

**No.** The E-053 separation is a no-op (0 of 10,087 rows change), and every
non-trivial variant of it regresses both the save-wide fit and the readings.
The one real defect this work exposed — a latched allocation that can disagree
with the live multiplier — is a *timing* property of the engine, not a rule the
model can evaluate from a single save; modelling it would require state the
save does not carry. Recommend Phase 3 drops the storage.py item and keeps the
current basis, whose scoreboard (94.2 % save-wide, 131/132 in game) is
unchanged.

## 4. Rejected here — do not re-test without new evidence

| candidate | how it died |
|---|---|
| `efficiency / (1 + work_effect)` as a recoverable war-pressure factor | 0 of 1,630 modules exceed the mod-patched ceiling; the factor is identically ≤ 1 and is the workforce ratio |
| allocation on `min(efficiency, ceiling)` | bit-for-bit identical to the current basis on snapshot 71 |
| allocation on the ceiling `(1+work_effect)×sunlight` | 77.5 % save-wide vs 94.2 %, 22.5 % on the under-staffed cohort, 121/132 readings |
| allocation on the bare recipe (1.0) everywhere | 33.5 % save-wide, 105/132 readings |
| a global one-epoch lag on the multiplier | loses at all 12 transitions, by 10–44 points on the rows it changes |
| EIJ-609's sell price as a probe of its allocation | its book is on the 5 M Cr cap; the implied figure is 24.3 k in all 13 epochs and never moves |
