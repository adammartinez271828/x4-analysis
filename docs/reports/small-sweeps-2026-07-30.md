# Small sweeps: internal cycles, the `shady` tier driver, and E-128's corpus re-check — 2026-07-30

Plan item **P9** of [../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md).
Analysis only — nothing under `src/`, `tests/` or `docs/experiments/` was
touched. Sources: the analysis DB at `save_id` **71** (`save_002`, game time
82,688, resolved from `current_save`) and the 13-save corpus (game time
69,324 → 84,643).

Corpus caveats applied everywhere below: `station_module` repeats the build
plan twice (dedupe on `(host_id, entry_id, idx)`), and `trade_pending` stores
every trade twice (dedupe on `trade_id`).

---

## (a) Multi-stage internally-cycled wares — a precise negative

**Question.** A ware produced by one built module on a station and consumed by
another module on the *same* station: the model sizes it on
`max(production, consumption)` (E-044, gross). Should it be sized on the *net*
external flow instead?

### Census (snapshot 71)

- **192 (station, ware) pairs on 152 stations** are internally cycled.
- Top wares: energy cells 27, quantum tubes 20, refined metals 19, graphene 18,
  plasma conductors 13, hull parts 12, scrap metal 12, microchips 11,
  superfluid coolant 11, silicon wafers 8, metallic microlattice 6, spices 4.
- Production/consumption ratio: median **3.44**, quartiles 1.78 / 3.44 / 7.38;
  production dominates on 172 pairs, consumption on 19.
- The test has real power: `|net − max| / max` has median **0.290**, so the two
  rules differ by ~29 % on the typical pair (and by 10–100× on the extremes).

### Scoring, with the lower-bound rule

The net counterfactual is exact inside a pool: `T = max_units / throughput` on
any non-ration row and `Σ(throughput × volume)` are both recoverable from the
model's own rows, so re-splitting the pool with `|out − in|` on the cycled
wares needs no re-derivation of capacities. Ground truth is
`stock + inbound + open buy amount`, a **lower bound** — a model value *above*
it proves nothing, *below* it is a real error.

| population | n | max-rule below the bound | max-rule within 1 % | net-rule below the bound | net-rule within 1 % |
|---|---:|---:|---:|---:|---:|
| the cycled wares themselves | 58 | **0** | 23 | **33** | 5 |
| their pool-mates (indirect effect) | 5,378 | 77 | 5,082 | 78 | 4,382 |
| all rows on cycled stations | 5,436 | 77 | 5,105 | 111 | 4,387 |

**CONFIRMED (refutation): the net rule is wrong.** It puts 33 of 58 cycled
wares *below* their own offer-derived floor, several by an order of magnitude —
SYX-439 quantum tubes 30 modelled against a 3,714 floor, XBM-030 refined metals
4,351 against 27,329, ZZY-447 khaak scrap metal 12,000 against 36,000 — and it
drags 700 pool-mates out of the 1 % band as the freed volume is redistributed.
The current gross `max(out, in)` rule has **zero** below-bound violations on
the cycled cohort. *Falsified by:* any internally-cycled ware whose in-game
allocation reads below its gross-rule model value.

**Recommendation: no model change.** Record as a rejected candidate under the
storage model ("net internal flow for a ware the station both makes and
consumes") and close the "multi-stage internally-cycled wares (gross vs net)"
unmodelled-area row with this negative. E-044 is unaffected and now has a
save-wide population behind it rather than the two stations it was settled on.

*Caveat.* 39 of the 58 cycled pairs sit *above* the derived floor because the
station is a net producer and its buy offer is not saturated; those rows can
only refute, not confirm. The confirmation side rests on the 23 exact matches
and on the zero violations.

---

## (b) What sets a station's `shady` tier (E-112's open half)

**E-112** established two disjoint books: a **common** tier (a continuum,
median ~1.042 × band max) and a **fixed** tier at exactly **2.750 × band
average**, with no station on both. What sets the tier was open, and the
register recorded save-side settlement as impossible.

### Snapshot 71

3,269 `shady` offers over **822 stations**: **728 common**, **94 fixed**
(classified per offer as `|price/avg − 2.75| < 0.02`; every station is
internally consistent, no mixed station).

The `post` table (28,689 rows) turns out to carry **no** discriminating
attribute:

- every one of the 822 shady stations has **exactly one** `shadyguy` post, and
  822 distinct NPC ids — no sharing, no count difference between tiers;
- post *sets* are the same (`aipilot`/`defence`/`engineer`/`shadyguy`, four
  posts on 787 stations, five on 35, all common-tier);
- no faction or macro split: both tiers appear under 9 of the 12 owner
  factions, fixed share ~11.4 % overall (Terran is enriched at 17/42, Teladi
  16/136); 65 of 104 sectors hold both tiers.

**The discriminator is the workforce.**

| tier | n | median workforce | stations with ZERO workforce |
|---|---:|---:|---:|
| common | 728 | 362 | **6** |
| fixed | 94 | 0 | **94 (all of them)** |

The fixed tier's offer amounts are a different book too: median **100**, max
**200**, against the common tier's median 254 and max 2,387.

### Corpus: the tier moves, and it moves with the workforce

Across all 13 epochs, **1,227 of 1,228 fixed-tier station-epochs are unstaffed**
(the single exception is EIP-860 at 69,324 — the epoch immediately before it
switches). Two of 825 stations change tier in the corpus, and both switches sit
on a workforce crossing:

```
RNJ-168  workforce 540 -> 540 -> 456 -> 134 -> 0 ...
         tier     common common common common  FIXED (from t=80,387 on)

EIP-860  workforce 2500 -> 2760 -> ... (habitat count 1 -> 2)
         tier      FIXED -> common (from t=76,511 on)
```

**Proposed claim [OBS], one-directional: a `shady` station on the fixed
2.750 × average tier has no workforce** — 1,227/1,228 station-epochs, with the
one exception caught in transition. The converse is false: 5–8 unstaffed
stations per epoch stay on the common tier, and all six on snapshot 71 sit at
the *top* of the common continuum (1.548–1.556 × average on all four wares),
which is what an empty station on a fill-driven curve should read. So the
honest form is **unstaffed is necessary, not sufficient**, plus a transition
lag of up to one epoch (EIP-860 was fixed while already carrying 2,500
workers).

*Falsified by:* any staffed station reading exactly 2.750 × band average that
is not within one epoch of losing its workforce.

**Recommendation.** This is decisive enough to move: open a **new register
entry** for the driver (leaving E-112 CONFIRMED and untouched), status
CONFIRMED for the necessary condition with the sufficiency explicitly recorded
as false, and update the "shady tier driver" unmodelled-area row and E-112's
*Open:* clause to point at it. It also corrects E-112's implication that the
tier is a permanent station property: it is **persistent state that can flip**,
observed in both directions.

---

## (c) E-128 corpus re-check — the expected negative, confirmed

**Question.** Does any station in any of the 13 epochs have a habitat race set
differing from its workforce race set? Such a station would be a new
discriminator for the live-mix vs habitat-mix contradiction (register
contradiction (9)).

Habitat race from built `hab_<race>_*` macros (`arg`→argon, `par`→paranid,
`spl`→split, `tel`→teladi, `bor`→boron, `ter`→terran); workforce race from the
`workforce` table (amount > 0).

| epoch | stations with built habitats | race-set mismatches | multi-race workforces |
|---|---:|---:|---|
| all 13, game time 69,324 → 84,643 | 1,176 → 1,212 | **0 in every epoch** | **3 in every epoch**: DCO-580, DHI-588, EMY-219 |

- **Zero mismatches, 13/13 epochs.** The autonomous side of E-128 is exhausted
  exactly as the plan expected.
- The only unmapped habitat prefix is `hab_pir_*` (78 built modules per epoch,
  43 stations — scavenger and loanshark). Those are race-agnostic pirate
  habitats and every one of them houses a **single-race argon** workforce
  (IRD-672 3,358, KWC-232 5,091, …), so they cannot discriminate either. Worth
  knowing: a pirate habitat does not imply a pirate race in the workforce.
- **DCO-580 stays player-unknown in every epoch, including the newest**
  (`knownto` empty at game time 84,643), so the direct read remains
  unavailable.
- The multi-race population is exactly the three stations the register already
  names, in all 13 epochs.

**Recommendation: E-128 stays PENDING and PLAYER-blocked**, with the blocking
clause strengthened — it now rests on 13 epochs spanning 15,319 s and ~1,200
habitat-bearing stations per epoch, not on one snapshot. Contradiction (9) is
unchanged. The only remaining experiment is the player-built multi-race station
(reading R5).
