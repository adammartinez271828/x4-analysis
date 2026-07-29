# What is still unexplained — 2026-07-28

State after a day on the storage-allocation and price models. Measured on
`save_001` (game time 82,130), against
`s = cos(pi * fill / 1.095)` on the normalised price coordinate
(`price/avg - 1` over the band half-width on the relevant side).

## Where things stand

Allocation: **40 of 41 in-game readings within 1%**
(`uv run python tests/readings.py`), and 93.9 % of computed rows within 1 % of
their offer-derived floor save-wide.

Price, main sequence (6,997 offers):

| population | n | MAD | \|r\|>0.25 |
|---|---:|---:|---:|
| **rations** (role=food) | 2,342 | **0.017** | 5.8 % |
| all buys | 5,428 | 0.028 | 14.1 % |
| production inputs | 3,075 | 0.091 | 20.6 % |
| outputs / sells | 1,580 | 0.125 | 11.7 % |

Rations are effectively solved. Everything below is what is not.

---

## A. The sell side needs its own curve

Outputs sit a systematic **−0.115** below the buy-side cosine (MAD 0.125
against buys' 0.028). Fitting the sell side alone on bin medians prefers
`cos(pi (f/S)^k)` at **S 1.125, k 0.86** — bin RMSE 0.0352, against a clamped
line's 0.1248 — so it is the same family with a different span and a real warp.
1,569 offers over 26 bins is thin; more sell-side data would sharpen it.

The per-ware offsets are probably a facet of this, since they are all outputs
and all negative: shieldcomponents **−0.158**, fieldcoils −0.143,
weaponcomponents −0.136, turretcomponents −0.130, advancedelectronics −0.064.

## B. Production inputs carry a +0.05 offset and a one-sided tail

The buy residual is a sharp spike at zero (3,172 of 5,428 within ±0.05) with an
**asymmetric positive tail** — 759 at +0.1, 368 at +0.2, 224 at +0.3, 117 at
+0.4 — and a much smaller negative one.

It is a role effect, not a fill effect. Restricted to the same fill band
(0.2–0.8):

| role | n | MAD | \|r\|>0.25 |
|---|---:|---:|---:|
| production input | 1,558 | **0.130** | **27.4 %** |
| ration | 1,189 | **0.017** | 8.8 % |

Same curve, same fills, an order of magnitude apart.

**Tested and rejected as the cause:**

- *Recipe completion* — that a station bids up whichever input it is shortest
  of. The scarcest input at its station residuals **+0.048**, the most abundant
  **+0.047**, everything else +0.055. No effect whatsoever.
- *Fill relative to the station's other inputs* — flat at +0.03…+0.07 across
  the whole range of relative fill, no monotone trend.
- *Hours of cover* instead of fill fraction — binning on hours leaves a median
  deviation of 0.136 against fill's 0.068, and is not even monotone.
- *Owner faction* — every faction with n ≥ 100 sits between −0.018 and −0.003.

This is the single biggest open item.

## C. Station-level anomalies

953 offers exceed 0.25, spread across **632 stations and 51 wares** — a broad
thin tail, not a handful of broken stations. The worst few:

| station | n wares | median residual |
|---|---:|---:|
| IRD-672 (scavenger, Avarice I) | 7 | −0.806 |
| JAR-041 (holyorder) | 6 | −0.805 |
| FSL-235 (antigone) | 6 | +0.600 |
| CCN-497 (holyorder, Cardinal's Redress) | 6 | +0.137, MAD 0.530 |

CCN-497 is the instructive one: graphene **+1.03** and refined metals **+1.02**
— a full band width above the curve at 78 % and 68 % fill — energy cells +0.33,
while both its rations sit on the curve. A station-level premium would move all
five together. It does not.

## D. The narrow-span output cohorts (114 offers)

Their price span is a fraction of their allocation: computronicsubstrate
**0.19×**, claytronics 0.80×, siliconwafers 0.82×, against ~1.07× for the pack.
Excluded from the main sequence. **Not** an allocation error — the correlation
between a ware's sell-side span/allocation and its offer-derived allocation
ratio is +0.11 over 18 wares, and GDR-378 reads 0.144 on computronicsubstrate
while its five inputs sit at 1.02–1.12 in the same pool on the same station.

## E. Books that are characterised but not modelled

| category | n | what it does |
|---|---:|---|
| shady | 3,273 | ~1.055 × band max, no fill dependence (separate black-market book) |
| construction | 1,771 | sits at band max; build storages hold no allocation |
| supplies | 1,309 | a fixed per-ware multiple of avg — 10 distinct constants, source unidentified |
| locked | 1,175 | avg / avg − 1 regardless of stock (Layer 6, understood) |
| yard | 701 | different shape, `k ≈ 2.6`, runs much fuller (median fill 76 % vs 54 %) |
| proxy / ship-host / player / no-alloc | 262 | allocation is proxied, hosted elsewhere, or manual |

Only `supplies` and `yard` are genuinely unexplained; the rest are understood
and correctly excluded.

## F. Allocation: EIJ-609

Its production rate follows the reported efficiency 1.12634 exactly (3,972/h)
but its allocation follows a multiplier of **1.0** — 34,829 hull parts read in
game, twice, against a modelled 37,228. A starving-workforce gate fits it
perfectly and is **wrong save-wide** (tested: every definition scores worse
than no gate, 93.8 % → 83.6–91.6 %), so it is an exception, not a rule.
Leading hypothesis is a lazily-recomputed allocation; falsifiable only by
playing forward and re-reading.

## G. Reference-data gaps

`nd_habitat_cap_boost` replaces habitat workforce capacity with
S 2500 / M 5000 / L 10000 against a stock 333/666/999 — a 7.5–10× housing
boost. It is **not** registered in `gamedata/modpatch.py`, and
`extract_modcaps` cannot read it either: those are `<diff>` files with no
`<macro>` element. Workforce drives the ration buffer and the efficiency, so
this is the next registry entry. Relatedly, `extract_wares` handles only
`<add sel=…>` and never `<replace>`, so extraction could not pick up mod
recipe changes even with extensions loaded.

---

## Ranked

1. **B** — the production-input offset and tail. Biggest population, four
   hypotheses already eliminated, and it is what keeps the scatter wide.
2. **A** — fit the sell side its own curve. Cheap, well-posed, and would take
   outputs from MAD 0.125 toward the buy side's 0.028.
3. **C** — CCN-497 first: five wares on one station, two off by a full band
   and two exactly right, is the sharpest single clue available.
4. **G** — habitat capacity, because it is a known-wrong input rather than an
   unknown rule.
5. **D**, **E-supplies**, **F** — real but small or already boxed in.

Every item above is registered with its status and settling experiment in
[docs/experiments/README.md](../experiments/README.md).
