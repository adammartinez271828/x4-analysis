# Plan: integrate the storage / production discoveries (2026-07-28)

Session context: a fill-vs-price spread taxonomy turned into a sequence of
findings about how the game actually sizes storage and rates production. Several
invalidate assumptions currently baked into `analysis/storage.py`. This plan
lists what is CONFIRMED, what is still open, the experiments that close the open
questions, and the implementation order.

Anchor case: **EIJ-609** (Holy Order hull-parts factory, True Sight), the first
station for which we hold in-game readings of *both* a production rate and an
allocation.

---

## Part 1 — What is CONFIRMED

### C1. The save states the production multiplier outright

Every production module carries it:

```xml
<production start="81852.263" end="82752.263" item="0" cycle="0" state="producing">
  <efficiency product="1.12634"/>
  <queue ware="hullparts"/>
</production>
```

`floor(recipe.amount × efficiency) / recipe.time × 3600 × modules` — EIJ-609:
`floor(294 × 1.12634) = 331` → **3,972/h**, matching the in-game logical
overview to the unit (model said 4,824/h).

It is the **complete** multiplier — workforce bonus, sector sunlight and
third-party modifiers all collapse into it. Save-wide distribution:

| value | modules | what it is |
|---|---:|---|
| 1.37 | 307 | exactly the hull-parts `work_effect` (fed, unmodified) |
| 1.43 / 1.53 / 1.28 / 1.40 / 1.46 | 293/192/182/92/71 | other recipes' `work_effect` |
| 0.71 | 11 | a sunlight value (Family Zhin) |
| 7.14 / 10.21 / 19.88 / 2.97 | 35/11/18/36 | high-sunlight solar × workforce |
| 1.12634 | 3 | EIJ-609 — unfed workforce × a mod's war-pressure bonus |

The playthrough runs Faction Fix Pack, which injects a per-faction "production
efficiency from war pressure" term seen on ARG and ANT stations at *differing*
percentages. **No static game-file model can reproduce this.** Reading the field
is the only mod-proof route, and this repo's whole premise is modded saves.

### C2. A buy offer's amount is the allocation gap — free ground truth

`offer.amount = allocation − stock − inbound_pending`. Verified on EIJ-609
(graphene is the only ware with inbound: 2,466 + 426 + 1,846 = 4,738, and only
then do all three inputs land on an identical 9.872 h). Save-wide the derived
value matches the model at median ratio **1.0000** over 5,334 offers.

This converts allocation validation from "18 hand-read numbers" into **thousands
of per-save ground-truth points**, and it must become a permanent regression
check.

### C3. ~~The allocation ignores the efficiency multiplier~~ — SUPERSEDED

*(EIJ-609 alone suggested this; the 281 differential-efficiency stations
disproved it. Retained because EIJ-609's numbers are still the anchor and its
exception is unexplained — see Q1's answer.)*

EIJ-609, equal hours over **unmodified base** recipe rates, T = 9.8722 h:

| ware | base rate/h | model @ base | observed | source of observation |
|---|---:|---:|---:|---|
| hullparts | 3,528 | 34,829.1 | **34,829** | in-game |
| energycells | 960 | 9,477.3 | **9,477** | offer-derived |
| graphene | 480 | 4,738.6 | **4,738** | offer-derived |
| refinedmetals | 3,360 | 33,170.5 | **33,170** | offer-derived |
| medicalsupplies | (4 h) | 4,374.0 | **4,374** | offer-derived |
| sojahusk | (4 h) | 4,665.6 | **4,665** | offer-derived |

All six inside 0.6 units, pool closing to exactly 1,000,000 m³. With the
efficiency applied to outputs only it gives 37,228 (+6.9 %); with the current
model's `work_effect` on outputs only, 41,210 (**+18.3 %**).

**The bug is the asymmetry, not the multiplier.** A factor applied uniformly to
every ware cancels out of an equal-hours split; applied to outputs alone it does
not. `storage.py` line ~10 states the asymmetry as a rule
(`Work_effect applies to output only`) — that is what has to go.

### C4. Other findings already landed or pending elsewhere

- Stations price off the **net position** (`stock + inbound − committed
  outbound`), not cargo. 17.8 % of main-sequence offers carry pending; folding
  it in halves their residual (MAD 0.083 → 0.041).
- `buy price = sell price − 1.00 Cr` on the same (station, ware): 704/706.
- Shady offers are a separate book — **fixed and committed** (546 phantom proxy
  allocations removed).
- `supplies` buys price at a fixed per-ware multiple of band average (10
  distinct values across 1,207 offers).
- `<workforces><bonus busy=>` is **not** a bonus on/off switch (busy=0 on
  1,132 of 1,244 workforce stations, including plainly bonused ones). Do not
  use it as a gate.

---

## Part 2 — Open questions and the experiments that close them

### Q1. Does the allocation basis include sunlight? — **ANSWERED, S1/S3 shipped**

C3 says the allocation uses unmodified base rates. But `SOLAR_WARE` scaling was
added on the strength of DLB-176, recorded as matching *only* with sunlight
folded in — and sunlight lives inside `efficiency`, which C3 says is ignored.
Both cannot be right.

**Experiment.** DLB-176 (Family Zhin, sunlight 0.71) makes energy cells *and*
graphene, so its two module types carry *different* `efficiency` values. That
breaks the uniformity that made EIJ-609 undetermined:

- if the allocation ignores efficiency, energy cells : graphene allocation
  follows the **base rate ratio**;
- if it uses efficiency, it follows the **efficiency-weighted ratio**.

Read both modules' `<efficiency product>` from the save, compute both
predictions, compare against DLB-176's offer-derived allocations (graphene is
an output there, so use the energy-cell input side plus the pool-closure
identity). *Falsifies whichever branch it contradicts.*

Prefer any station where one product is solar and another is not — that is the
maximally-separating case and there are several.

### Q2. Is the multiplier absent, or present-and-uniform? — **ANSWERED**

C3 cannot distinguish "base rates" from "efficiency applied to everything"
because a uniform factor cancels. Q1's differential test settles this too. Log
the answer explicitly — it decides whether we need `efficiency` in the
allocation path at all, or only in the reported production rate.

### Q3. Processing modules and their energy cells

The scrap-works exclusion (`method != "processing"`) was fitted under the old,
asymmetric model (KWC-232: counting the scrap works' 90,000 energy cells/h
missed by 5 % / 15 %). Once the asymmetry is removed the arithmetic changes.

**Experiment.** Re-derive KWC-232 under the corrected basis, against its
offer-derived allocations rather than the three hand-read numbers. Determine
whether the exclusion is still needed or was compensating for the asymmetry.

### Q4. Partial feeding

Stations with *some* rations stocked fit neither branch cleanly (n=550, median
error 0.083 either way) against 0.0010 for fully-stocked. Likely a graded
bonus. Low priority — it should fall out of C1 for free, since `efficiency` is
read rather than derived. **Use it as a check**: if reading `efficiency` makes
the partial group fit, the graded-bonus hypothesis is confirmed without
modelling it.

### Q5. Downstream: does correct fill collapse the price scatter?

The standing hypothesis from review is that the price-curve noise — the
narrow-span cohorts, the output/ration shape disagreement (power k≈1.55 vs pure
cosine), the input population's MAD 0.044 — is an artifact of a wrong
denominator, not several different curves. Re-run the fill-vs-price taxonomy
after Part 3 and re-test. **Do not** re-litigate curve shape before the
denominator is fixed.

---

## Answers (2026-07-28)

**Q1/Q2 — the allocation DOES use the multiplier, applied to outputs only.**
Decisive population: the 281 stations whose modules carry *different*
efficiency values (a uniform factor cancels out of an equal-hours split, a
differential one does not). Scored against offer-derived allocations:

| basis | n | median \|err\| | within 1% |
|---|---:|---:|---:|
| save `efficiency`, outputs only | 4,914 | 0.0000 | **87.2%** |
| reconstructed `work_effect` x sunlight | 4,914 | 0.0001 | 76.7% |
| no multiplier | 4,914 | 0.0036 | 50.9% |
| `efficiency` on outputs AND inputs | 4,914 | 0.0103 | 49.9% |

Isolating the mod term — stations whose efficiency equals `1 + work_effect`
versus those where it does not — shows the war-pressure term genuinely enters
the allocation (55.5% -> 79.7% within 1%). Sunlight is inside `efficiency`, so
the separate `SOLAR_WARE` scaling survives only as the no-`<production>`
fallback.

**EIJ-609 remains an exception** and is recorded as such in save-semantics.md
with a falsifiable lag hypothesis. It is the only station here with a direct
in-game allocation reading, so it is worth re-reading later.

**Shipped result** (offer-derived score on the reimported quicksave, all
6,778 comparable pairs): 82.7% within 1%, 87.0% within 5%; rations 95.0%
within 1%. `role='output'` rows score badly (48 pairs, 10.4%) but those are
stations *buying* their own output ware — a different quantity, not a
regression.

## Part 3 — Implementation order

Each step is independently committable and test-covered.

### S1. Parse `<production><efficiency product>` *(schema v27)* — **DONE**

New table `module_production`: `(save_id, host_id, module_id, entry_id, ware,
efficiency, state, cycle, start, end)`. Single-pass handler in `save/parser.py`
keyed off the enclosing module component (`construction=` gives the entry id,
so it joins to `build_entry`). Defensive: missing/unparseable `product` → NULL,
never a crash. View `v_module_production`; `frames.module_production`.

### S2. Real production rate

`floor(recipe.amount × efficiency) / time × 3600`, summed per (station, ware).
Expose alongside the existing recipe-derived throughput rather than replacing
it — they are genuinely different quantities and both have consumers.
Fall back to the recipe rate where no efficiency is recorded.

### S3. Fix the allocation basis *(depends on Q1/Q2)* — **DONE**

Remove the output-only `work_effect` asymmetry. Whether the basis becomes
"unmodified recipe rates" or "efficiency applied uniformly" is Q1's answer.
Keep sunlight only if Q1 says the basis is efficiency-weighted.

Regression gate: EIJ-609 all six wares within 1 unit; the 18 archived readings
must not regress; and the save-wide offer-derived comparison (S4) must improve.

### S4. Offer-derived allocation as a standing check

Add `analysis/` helper producing, per (station, ware) with an open unflagged
buy offer, `derived_max = stock + inbound + amount`, and a comparison against
the modelled value. Ship it as a diagnostic (and a test over a fixture), so any
future model change is scored against thousands of points instead of 18.

### S5. Net position everywhere fill is computed

`stock + inbound − committed outbound`. Audit consumers: the understocked /
fill measures in `frames`, `analysis/opportunities.py`, the market widgets.

### S6. Re-run Q3, then Q5

Re-derive the processing-module rule, then regenerate the fill-vs-price
taxonomy and re-test the curve-shape question with a correct denominator.

### S7. Documentation

`docs/reference/save-semantics.md` — `<efficiency product>` as the production
multiplier, the allocation-basis correction, the offer-derived allocation
identity, the net-position pricing rule, the 1 Cr bid-ask spread, and the
`busy` non-result. `docs/reference/db-schema.md` — the new table.
`docs/reference/savegame-structure.md` — the `<production>` block.

---

## Sequencing

```
Q1/Q2 (experiment)  ->  S1 (parse)  ->  S3 (fix basis)  ->  S4 (standing check)
                          |                                     |
                          +-> S2 (production rate)               +-> Q3 -> S6 -> Q5
                                                                 +-> S5
S7 last, once the answers are settled.
```

**Do not** start S3 before Q1 returns — the two branches differ by whether
sunlight survives, and guessing costs a revalidation cycle against every
archived reading.

## Risks

- The 18 archived in-game readings were taken under the old model. Some may
  have been fitted *to* the asymmetry. Re-score all of them against the
  offer-derived truth before treating any as a regression failure.
- `efficiency` is runtime state and **drifts** — it is a per-save read, never a
  calibration. Same discipline as `build_price_factor`.
- Faction Fix Pack's war term means allocation and production predictions are
  only valid for the save they were read from. Never assert cross-save
  stability without evidence.
