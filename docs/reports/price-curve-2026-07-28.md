# The sell-side curve and the production-input offset — 2026-07-28

Research only; no `src/` change. Measured on `save_001.xml.gz` (game time
82,130, DB `save_id` 65). Verification: `uv run pytest -q` → **234 passed**;
`uv run python tests/readings.py` → **40/41 in-game readings within 1 %**
(unchanged — nothing under `src/` was touched).

All work is on the normalised coordinate
`s = (price/avg − 1) / spread`, spread = the band half-width on the relevant
side. Fill is the pending-corrected net position `stock + inbound − outbound`
over the modelled allocation. Main-sequence population rebuilt from the
mechanistic partition in
[fill-price-spread-2026-07-28.md](fill-price-spread-2026-07-28.md): 7,216
offers, 7,102 after removing the narrow-span output cohorts
(computronicsubstrate / claytronics / siliconwafers). Baseline against
`s = cos(π · fill / 1.095)`:

| population | n | MAD | median res | \|r\|>0.25 |
|---|---:|---:|---:|---:|
| rations (role=food) | 2,372 | 0.0165 | −0.017 | 0.2 % |
| all buys | 5,492 | 0.0203 | +0.000 | 8.8 % |
| production inputs (buy) | 3,085 | 0.0788 | +0.068 | 15.5 % |
| outputs (sell) | 1,544 | 0.1321 | −0.131 | 9.7 % |

## Headline

Both open items resolve to the **same one-parameter deformation of the
confirmed cosine**: an additive offset on the fill axis.

```
s = cos(π · (fill + a) / 1.095)
```

with `a = +0.053` on the sell/output side, `a ≈ 0` on rations, and a
**per-station constant** `a < 0` on production inputs. The span `S = 1.095` and
the cosine shape are unchanged from the confirmed buy-side law; nothing else
about Layer 4 moves. Save-wide, applying the offsets takes the main sequence
from **MAD 0.0392 / 9.04 % beyond 0.25** to **MAD 0.0144 / 5.89 %**.

---

# A. The sell side: the same cosine, shifted by a constant fill offset

## The function and its parameters

```
s_sell = cos(π · (fill + a) / 1.095)        a = +0.053
```

Equivalently: a producer prices as though it held 5.3 % of its allocation more
than it does. The price floor is reached at fill 1.042 rather than 1.095; the
band ceiling is reached only at exactly zero stock, where a separate clamp
holds (74 offers at fill 0 sit at `s = 1.000` exactly, all with `amount = 0`).

## Bin-median fit (equal-count bins, equal weight per bin)

1,610 sell offers, 22 bins of ~73. Fill medians per bin, observed `s` median,
and four candidate curves:

| fill (median) | n | s (median) | **shift a=.053** | pure cosine S=1.095 | warped cos S=1.06 k=.89 | power 1−2(f/.79)^1.48 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.000 | 74 | +1.000 | +0.988 | +1.000 | +1.000 | +1.000 |
| 0.021 | 73 | +0.986 | +0.978 | +0.998 | +0.996 | +0.991 |
| 0.059 | 73 | +0.958 | +0.949 | +0.986 | +0.972 | +0.957 |
| 0.116 | 73 | +0.889 | +0.884 | +0.945 | +0.907 | +0.883 |
| 0.156 | 73 | +0.815 | +0.825 | +0.901 | +0.843 | +0.818 |
| 0.194 | 73 | +0.747 | +0.760 | +0.849 | +0.773 | +0.750 |
| 0.236 | 73 | +0.668 | +0.676 | +0.780 | +0.683 | +0.666 |
| 0.263 | 74 | +0.603 | +0.617 | +0.729 | +0.619 | +0.607 |
| 0.287 | 73 | +0.547 | +0.562 | +0.680 | +0.560 | +0.554 |
| 0.311 | 73 | +0.485 | +0.502 | +0.627 | +0.497 | +0.496 |
| 0.337 | 73 | +0.439 | +0.437 | +0.569 | +0.430 | +0.434 |
| 0.353 | 73 | +0.387 | +0.394 | +0.529 | +0.384 | +0.392 |
| 0.366 | 73 | +0.358 | +0.361 | +0.498 | +0.350 | +0.361 |
| 0.380 | 73 | +0.313 | +0.324 | +0.464 | +0.311 | +0.324 |
| 0.397 | 74 | +0.269 | +0.277 | +0.419 | +0.263 | +0.278 |
| 0.417 | 73 | +0.213 | +0.220 | +0.365 | +0.204 | +0.222 |
| 0.437 | 73 | +0.161 | +0.165 | +0.313 | +0.148 | +0.168 |
| 0.462 | 73 | +0.092 | +0.093 | +0.243 | +0.075 | +0.096 |
| 0.501 | 73 | −0.014 | −0.018 | +0.134 | −0.036 | −0.019 |
| 0.610 | 73 | −0.325 | −0.325 | −0.179 | −0.339 | −0.364 |
| 0.952 | 73 | −0.970 | −0.967 | −0.917 | −0.959 | −1.000 |
| 1.000 | 74 | −1.000 | −0.993 | −0.963 | −0.987 | −1.000 |

| model | free params | bin RMSE |
|---|---:|---:|
| **`cos(π(f+0.053)/1.095)`** | 1 | **0.0087** |
| power `1 − 2(f/0.79)^1.48` | 2 | 0.0120 |
| warped cosine `cos(π(f/1.06)^0.89)` | 2 | 0.0144 |
| pure cosine `cos(π f/1.095)` (the buy law) | 0 | 0.1180 |
| clamped linear (best S) | 1 | 0.0941 |

**Before → after, sell population (n = 1,610):** bin RMSE **0.1183 → 0.0110**,
per-offer MAD **0.1313 → 0.0124**, \|res\|>0.25 **9.69 % → 7.52 %**. On
role=output sells only (n = 1,544): bin RMSE **0.1192 → 0.0086**, MAD **0.1321
→ 0.0121**.

## Why the offset is additive and not a rescaled span — CONFIRMED

Invert the confirmed law to an implied fill `f̂ = 1.095·arccos(s)/π` and ask
whether `f̂ − fill` (a shift) or `fill/f̂` (a scale) is the invariant. Within
single cohorts the shift is flat and the scale is not:

**energy-cell sell offers, by fill octile (n = 177):**

| fill | 0.30 | 0.39 | 0.44 | 0.47 | 0.52 | 0.91 |
|---|---:|---:|---:|---:|---:|---:|
| implied shift `a` | 0.0480 | 0.0486 | 0.0487 | 0.0485 | 0.0484 | 0.0489 |
| implied scale `c` | 0.861 | 0.888 | 0.899 | 0.906 | 0.915 | 0.934 |

`a` is constant to four significant figures over a 3× range of fill while `c`
moves 8 %. medicalsupplies (n = 94) reproduces this at a = 0.0488 / 0.0494 /
0.0520 / 0.0497 / 0.0497 / 0.0498. The same test on the buy side returns
`a ≈ −0.003, c ≈ 0.99` flat, i.e. no offset — which is why rations fit the
plain cosine.

**The offset is a fraction of allocation, not an absolute or time quantity.**
Energy-cell sellers grouped by allocation size give `a` = 0.0488 (alloc 98 k),
0.0484 (146 k), 0.0483 (250 k), each with an IQR under 0.001, while the same
offset expressed in hours of production swings 0.25 → 0.65 h. Across all sells
the offset drifts mildly with allocation — 0.0578 at alloc ≈ 2,500 down to
0.0487 at alloc ≈ 250,000 — a residual structure worth ~0.01 of a band and not
modelled here.

## The power law is falsified

The preliminary `cos(π(f/S)^k)` at S 1.125 / k 0.86 and the older
`1 − (u/0.766)^1.55` both put the price floor at fill ≈ 0.79–0.85. The 0.55–0.98
region was previously empty at the bin thresholds used; at `minn = 8` it holds
135 offers and **only 8 of them are at the floor**. Observed: fill 0.80 → s
−0.79, 0.85 → −0.86, 0.89 → −0.91, 0.95 → −0.98. A curve that reaches −1 at
0.79 is wrong by a full 0.2 of a band through that whole stretch. The floor is
reached at ≈ 1.04, as the shift model says.

## The per-ware sell offsets are a composition artifact

open-items listed shieldcomponents −0.158, fieldcoils −0.143,
weaponcomponents −0.136, turretcomponents −0.130, advancedelectronics −0.064 as
per-ware offsets. On the shifted coordinate the per-ware implied `a` collapses
to 0.041–0.066 across 18 wares with n ≥ 20, and its ordering is simply the
ordering of the wares' median fill (corr +0.37). There is **no per-ware
sell-side term**; the apparent one was the pure cosine's error evaluated at
different points of the curve.

## CONFIRMED vs hypothesis

- **CONFIRMED**: the sell side is the same cosine at the same span S = 1.095
  with an additive fill offset; the offset is a constant fraction of the
  allocation, not a scale, not a warp, not a per-ware constant. Bin RMSE
  0.0087 on 22 bins / 1,610 offers, beating every two-parameter alternative
  with one parameter.
- **HYPOTHESIS**: the offset is exactly 0.05 and the observed drift to 0.058 at
  small allocations is a second, smaller effect. *Falsified by* any single
  cohort at small allocation reading a stable 0.050.
- **Not established**: what the offset *is*. It is a fixed fraction of the
  price target, so it is not a production cycle, not a delivery lot and not a
  time constant — all of those would vary with allocation-hours, which the
  data rules out at IQR < 0.001.

---

# B. Production inputs: one station-level fill offset, not a ware effect

## The finding

The input residual is **not a ware property, not a fill property and not
noise — it is a single constant per station, shared by every production input
that station buys.**

Over 547 stations with ≥ 3 unclamped input offers:

| quantity | value |
|---|---:|
| within-station sd of the implied offset `a` | **0.0114** |
| between-station sd of the per-station median `a` | **0.0542** |
| within-station sd of allocation-hours | 0.0000 |

Four of the five stations open-items flagged as anomalies are single-constant
stations, tight to a few thousandths:

| station | inputs used | implied `a` | within-station sd | alloc hours |
|---|---:|---:|---:|---:|
| CCN-497 (holyorder) | 2 | −0.3896 | **0.0014** | 1.15 |
| FSL-235 (antigone) | 4 | −0.3385 | **0.0049** | 2.59 |
| NRD-991 (teladi) | 3 | −0.1736 | **0.0004** | 4.51 |
| JQZ-281 (split) | 4 | −0.2511 | **0.0075** | 1.67 |

### CCN-497 is explained

The report's sharpest clue dissolves. CCN-497 runs an allocation of **1.15
hours** against a save-wide median of ~6 h, so a station offset that is modest
in hours is enormous in fill. Both its unclamped inputs land on one constant:

| ware | fill | s | implied `a` |
|---|---:|---:|---:|
| graphene | 0.779 | +0.436 | −0.3896 |
| refined metals | 0.675 | +0.685 | −0.3906 |
| energy cells | 0.273 | **+1.000** | ≤ −0.436 (censored at band max) |

Energy cells at fill 0.273 with `a = −0.39` would price at `s = 1.09`, above
the ceiling, so it clamps at exactly band max — which is what the save shows.
The earlier argument ("a station-level premium would move all five together;
it does not") failed on two counts: it did not account for the **ceiling
clamp**, and it expected rations to move too, when rations carry their own
offset of ≈ 0.

## Bin-median fit for the pooled input population

3,085 input buys, 20 equal-count bins of ~154:

| fill (median) | n | s (median) | a = −0.039 | a = 0 (buy law) |
|---:|---:|---:|---:|---:|
| 0.004 | 155 | +1.073 | +1.000 | +1.000 |
| 0.065 | 154 | +1.000 | +0.997 | +0.982 |
| 0.190 | 154 | +0.913 | +0.908 | +0.856 |
| 0.299 | 154 | +0.724 | +0.735 | +0.654 |
| 0.407 | 154 | +0.461 | +0.492 | +0.392 |
| 0.493 | 155 | +0.268 | +0.265 | +0.156 |
| 0.558 | 154 | +0.061 | +0.081 | −0.031 |
| 0.607 | 154 | −0.056 | −0.059 | −0.170 |
| 0.648 | 154 | −0.175 | −0.175 | −0.284 |
| 0.692 | 154 | −0.319 | −0.298 | −0.402 |
| 0.730 | 155 | −0.365 | −0.400 | −0.500 |
| 0.770 | 154 | −0.487 | −0.502 | −0.595 |
| 0.807 | 154 | −0.586 | −0.591 | −0.677 |
| 0.846 | 154 | −0.667 | −0.677 | −0.755 |
| 0.893 | 154 | −0.770 | −0.771 | −0.837 |
| 0.933 | 155 | −0.832 | −0.838 | −0.894 |
| 0.959 | 154 | −0.868 | −0.877 | −0.925 |
| 0.979 | 154 | −0.902 | −0.903 | −0.945 |
| 0.992 | 154 | −0.917 | −0.918 | −0.957 |
| 1.000 | 155 | −0.923 | −0.927 | −0.963 |

Bin RMSE **0.0819 → 0.0213**. Per-offer MAD 0.0788 → 0.0723, \|r\|>0.25
15.49 % → 9.27 %. The pooled offset only centres the population; the remaining
per-offer scatter *is* the between-station spread.

## It is not an allocation error — CONFIRMED

The obvious objection is that the fill denominator is wrong for these stations.
It is not. `stock + inbound + open buy amount` — the offer-derived lower bound
— **equals the modelled allocation to four decimal places in every bucket**
(median ratio 0.99992–0.99995, and > 1.01 for only 2–4 % of offers). Where an
input buy offer exists the bound is saturated, so the denominator is not merely
bounded but pinned. Independently, a wrong denominator would be a *scale* error,
and CCN-497's two inputs sit at fill 0.779 and 0.675 with implied fills 0.390
and 0.284 — a constant difference (−0.390) and not a constant ratio (0.50 vs
0.42).

## What the offset scales with

The offset shrinks monotonically with the station's **production module
count**, and this holds within single wares at fixed allocation-hours:

| production modules | stations | median `a` | IQR of `a` | median offset in hours (`−a × alloc_h`) | share with \|a·alloc_h\| < 0.05 h |
|---:|---:|---:|---:|---:|---:|
| 1 | 160 | −0.083 | 0.062 | 0.642 | 0.6 % |
| 2 | 117 | −0.043 | 0.049 | 0.259 | 8.5 % |
| 3 | 83 | −0.017 | 0.055 | 0.119 | 18.1 % |
| 4 | 69 | −0.003 | 0.044 | 0.018 | 34.8 % |
| 5–6 | 56 | −0.001 | 0.042 | 0.004 | 23.9 % |
| 7+ | 15 | +0.013 | 0.047 | −0.053 | — |

Energy cells alone, controlled for allocation-hours, reproduce it exactly:
`a` = −0.068 / −0.111 / −0.075 / −0.026 at ≤ 2 modules across the four
allocation-hour quartiles, rising to +0.024 … +0.043 at 7+ modules. graphene,
water, quantum tubes, microchips and ore all show the same monotone pattern.
The dispersion collapses with it: the IQR of `a` for energy-cell inputs is
0.069 at ≤ 2 modules and 0.014 at ≥ 5.

Expressed as **hours of the station's own consumption withheld from the fill it
prices on**, the offset runs from 0 to a hard ceiling at ≈ 0.78 h. The
distribution is a broad continuum with a mode near 0.6–0.75 h and a pile at 0;
nothing exceeds ~0.8 h except a handful of negative outliers.

## What it is *not* — tested and rejected here

Rank correlations of the per-offer input residual against every remaining lead
from the brief (n = 2,696–3,085):

| candidate | corr(res) | corr(\|res\|) |
|---|---:|---:|
| recipe cycle time | +0.134 | +0.025 |
| number of inputs in the recipe | +0.170 | +0.025 |
| input's share of recipe input value | +0.199 | −0.048 |
| chain tier (0 = raw) | +0.105 | +0.069 |
| inbound pending / allocation | +0.017 | −0.035 |
| ware's share of its transport pool | +0.086 | −0.106 |
| station workforce | −0.061 | +0.004 |
| production efficiency | +0.118 | −0.038 |
| number of wares at the station | +0.017 | +0.035 |
| fill | −0.001 | −0.067 |
| **production module count** | **−0.409** | +0.001 |
| allocation (units) | −0.358 | −0.067 |
| allocation in hours | −0.236 | −0.144 |

All four of the brief's untried recipe leads are weak (≤ 0.20) and all of them
are ware-level, which cannot in principle explain a station constant. Grouped
medians confirm: chain tier 0/1/2 give residuals −0.001 / +0.012 / +0.014;
recipe input count 0/2/3 give −0.018 / +0.002 / +0.038. Rejected.

`module_production.state` is never `waiting` in a way that helps — the states
present are `producing` (1,324), `waitingforresources` (192) and
`choosingitem` (89), and station-level `frac_waiting` is 0 for every station in
the input population.

## Scoring the module-count rule against the whole population — and rejecting it as a rule

Turning the module-count table into a lookup offset improves the per-offer
scatter but **degrades the bin-median fit**, so it does not belong in the
curve:

| input-buy model | n | MAD | \|r\|>0.25 | bin RMSE |
|---|---:|---:|---:|---:|
| a = 0 (buy cosine) | 3,085 | 0.0788 | 15.49 % | 0.0828 |
| **a = −0.039 flat** | 3,085 | 0.0723 | 9.27 % | **0.0213** |
| a by module count | 3,085 | 0.0560 | 8.88 % | 0.0649 |

Save-wide the same holds: main sequence MAD 0.0392 → **0.0144** with flat role
offsets, and only 0.0136 with the module-count table — a 6 % gain in MAD bought
with a 3× worse aggregate curve. The module-count relation is a **real
description of where the offset comes from**, not a calibrated law; it should
not be shipped as one on this evidence.

## CONFIRMED vs hypothesis

- **CONFIRMED**: the production-input offset is a per-station constant applied
  to the fill axis, identical across the station's inputs (within-station sd
  0.011 against between-station 0.054), and it is not an allocation error
  (offer-derived allocation = modelled allocation, median ratio 0.9999).
- **CONFIRMED**: CCN-497 is one station constant plus a ceiling clamp, not
  three separate anomalies; its short 1.15 h allocation is what magnifies it.
- **CONFIRMED**: the offset falls monotonically with production module count,
  within ware and at fixed allocation-hours.
- **HYPOTHESIS (leading): the offer price is stale relative to the station's
  last lumpy trade.** A per-station price-update timer explains (a) why the
  offset is one constant shared by all of a station's wares, (b) the hard
  ceiling at ≈ 0.78 h and the continuum below it, (c) the sign flip between
  sides — a buyer's stock jumps *up* on delivery so a stale price reads too
  high (`a < 0`), a seller's stock drops in a lump when a trader loads so a
  stale price reads too low (`a > 0`) — and (d) the sharp spike at zero
  residual. *Falsified by:* reading one station's buy price twice a few minutes
  apart with stock changing continuously; the stale-price model requires the
  price to step discretely and reset the offset to ~0 at each step. It is also
  falsified if the offset is stable across a save-reload at the same station,
  since a timer-based lag should re-roll.
- **AGAINST the staleness hypothesis**, and unexplained: rations are consumed
  and delivered in lumps like any input, yet carry `a ≈ +0.006`. Either their
  4 h buffer is refilled by a different mechanism, or the offset has a
  different source.
- **HYPOTHESIS (alternative): a per-module input reserve** — the engine
  withholds roughly one module's worth of consumption from the priced fill, so
  `a ∝ 1/n_modules`. Supports: `a` = −0.083 / −0.043 at 1 and 2 modules is an
  exact halving. Against: the 1/n law over-predicts at n ≥ 3 (predicts −0.028,
  observes −0.017) and `a` turns *positive* at n ≥ 5, which a reserve cannot
  do. `reserve / (one module's cycle input)` × cycle time spans 1,100–2,500 s
  across 20 wares — a factor of 2, not a constant.

---

# Recorded, not pursued (per the non-goals)

- The offer-derived allocation is **saturated, not merely bounded**, for
  production inputs that post a buy offer: `stock + inbound + amount` equals the
  modelled allocation at median ratio 0.99995 in every module-count bucket.
  That is a much stronger validation of the allocation model than "lower
  bound", for the subset that is actually bidding.
- `trade_offer.desired` is identical to `amount` for all 12,912 buy rows and
  NULL for all 2,372 sell rows. It carries no target-level information.
- All of a station's wares in one transport pool share an identical
  allocation-in-hours (within-station sd 0.0000 over 547 stations), as the
  equal-hours model requires.
- Sell offers are censored in the mid-high fill range: 135 offers between fill
  0.55 and 0.98 against 1,100 below 0.55. A seller drains toward its
  equilibrium, so the sell sample piles at 0.25–0.50 and again at ~0.96.

---

# Ranked remaining leads, and the readings that would settle them

1. **What the sell-side +0.053 actually is.** It is a fixed fraction of the
   price target and survives a 3× range of allocation, which excludes every
   time- or lot-based explanation. *Needs:* the Logical Station Overview and
   trade panel for one single-output producer (a solar plant is ideal — one
   ware, no input coupling) read at three stock levels across one restock
   cycle, with the allocation and the price-modifier percentage noted each
   time. The shift model predicts the modifier hits exactly +100 % of spread
   only at zero stock and −100 % at 104 % of allocation.
2. **Whether the input offset is staleness.** *Needs:* one station's trade
   panel for a production input read twice, ~5 and ~30 minutes apart, with
   stock noted both times, plus the station's module count. A stale price is
   piecewise constant while stock moves; a reserve rule moves the price
   continuously with stock. CCN-497 (Cardinal's Redress) is the best subject —
   its 1.15 h allocation makes the offset ~0.39 of a band, impossible to miss —
   with FSL-235 as a second at 0.34.
3. **The rations exception.** Rations sit at `a ≈ +0.006` while every other
   consumed ware at the same stations sits at a station-wide negative offset.
   *Needs:* one habitat's ration buy price and one production input's buy price
   read from the same station at the same moment. If both carry the same offset
   the station-constant rule is universal and my ration measurement is a
   sampling artifact; if they differ, the offset is keyed on ware role.
4. **The mild sell-side drift with allocation size** (a = 0.058 at alloc 2,500
   → 0.049 at 250,000). Worth ~0.01 of a band. *Needs:* two producers of the
   same ware with allocations an order of magnitude apart, both read in game.
5. **The negative-offset stations** (JAR-041 −1.00, IRD-672 −1.32 on energy
   cells, JUK-948 −0.40). These sit on the wrong side of every rule above and
   are the only stations left whose sign is unexplained. IRD-672 and JAR-041
   are both scavenger/holyorder hosts with unusual pools; check first whether
   they are processing (scrap) stations, which the storage model excludes by
   design.
6. Untouched by this work and still open, unchanged from
   [open-items-2026-07-28.md](open-items-2026-07-28.md): the narrow-span output
   cohorts (D), `supplies` and `yard` pricing (E), EIJ-609 (F), and the
   `nd_habitat_cap_boost` reference-data gap (G).

---

# Addendum (same day): lead 5 — the three negative-offset stations

Raised in review. They are **not one phenomenon**, and the shift-vs-scale test
from § A separates them. For each ware, compare *implied fill − actual* (a
shift ⇒ price offset) against *implied ÷ actual* (a scale ⇒ wrong allocation
denominator). One ware cannot tell them apart; three can.

## JAR-041 (holyorder, Cardinal's Redress) — an allocation error, scale 2.00

| ware | fill | s | shift | **scale** |
|---|---:|---:|---:|---:|
| energy cells | 0.348 | −0.410 | +0.347 | **1.998** |
| soja beans | 0.325 | −0.285 | +0.323 | **1.994** |
| spices | 0.491 | −0.963 | +0.509 | **2.037** |
| water | 0.231 | +0.254 | +0.227 | **1.984** |

The shift spans a factor of 2.2; the scale is 2.00 on all four. The station is
on the standard curve and **our denominator is doubled**. Its container pool is
500,000 m³ from two `storage_par_m_container_01` at 250,000 each and the
allocation arithmetic closes on that exactly, so the fault is in the capacity:
either that module's `cargo_max` is wrong/mod-overridden at 2×, or only one of
the two contributes. Not the double-listing gotcha — 35 build entries, 35
built, zero duplicate `entry_id`s — and `module_production` independently
confirms 4 production modules, so the production side is not doubled.
*Falsifiable in one reading:* energy-cell max should read **21,258**, not the
modelled 42,516 (water 12,755 vs 25,510).

## JUK-948 (teladi, CEO's Doubt) — same shape, weaker: scale ≈ 1.37

Scale 1.365 / 1.396 / 1.362 / 1.229 on its four inputs, shift 0.101–0.232.
Scale is the tighter axis but water is well off the other three. Single
production module and **15.9 h of allocation** against a save-wide median ~6 h
— the regime where the § B offset is largest and noisiest — so this is likely a
mixture of a real price offset and a modest allocation error. *Reading:* energy
cells modelled 19,089; a pure scale error predicts ~14,000.

## IRD-672 (scavenger, Avarice I) — neither; not diagnosable from the save

| ware | shift | scale |
|---|---:|---:|
| energy cells | +0.563 | 6.44 |
| scrap metal | +0.361 | 3.23 |
| hull parts | +0.117 | 1.39 |

Three wares, three answers on both axes; its two rations sit on the curve
(+0.014, +0.006). Four known-hard cases intersect here: six scrap recyclers of
which only four carry a `<production>` block and those report **no
`<queue ware>`** (the multi-queue case); a `proc_gen_scrapworks` processing
module, excluded from the storage model by design; energy cells **dual-role**
(208,680/h produced at Avarice's 19.877 efficiency against 279,000/h consumed
by the recyclers) where the price implies a target near 258,400 matching
neither rate; and a `rawscrap` buy at 99.7 % of band max, the confirmed
non-economy feedstock rule. Needs in-game rates *and* maxima for energy cells,
hull parts, claytronics and scrap metal together.

## Population context

Of 847 stations with ≥ 3 usable offers, only **two** show a clean scale
signature (JAR-041 at 2.00, JUZ-209 split at 1.365) — a rare failure mode, not
a systemic allocation problem. Seven show the clean-shift signature at
\|shift\| > 0.08, led by JQZ-281 (−0.251, sd 0.007). JAR-041 shares a sector
with CCN-497, a textbook *shift* station (−0.390, sd 0.0014), so nothing
regional drives either.

**Revised lead 5:** JAR-041's storage maxima first (one reading settles a 2×
capacity bug that may be silently affecting other Paranid stations), then
IRD-672's rates and maxima together, then JUK-948's energy-cell max.

---

# Addendum 2: player readings on the three, and what they change

In-game readings supplied by the player, 2026-07-28. Added to
`tests/data/station_readings.json`; baseline raised 40 → **41 of 43**.

## JAR-041 — a PARSER defect, and it is fully explained

In game: **21,001 energy cells**, against a modelled 42,516 (+102.4 %). The
player's diagnosis: **the second storage module is not complete.**

The save agrees, and the mechanism is precise. Sequence entry `[0x20f1]`
(`storage_par_m_container_01_macro`) has a component with
`state="construction"` — and `parser.py` already knows to skip those. But it
collects `built_refs` as a **flat list of entry ids with no host**, and entry
ids are only unique **per station**: 2,235 of 22,562 ids are shared by more
than one station, up to 33 stations on one id. **ETP-594** runs the same
station plan and has `[0x20f1]` finished, so *its* component marks JAR-041's
entry built. The result is 250,000 m³ of phantom container capacity, a doubled
pool factor, and every allocation on the station at 2×.

The arithmetic closes to 0.01 %:

| | value |
|---|---:|
| model pool factor (42,516.2 / 4,800) | 8.85754 h |
| ⇒ capacity − reserves | 494,059.5 m³ (of 500,000 counted) |
| corrected: (250,000 − 5,940.5) / 55,776 | 4.37567 h |
| ⇒ energy cells 4,800 × 4.37567 | **21,003** |
| **read in game** | **21,001** |

**Save-wide scope**: 335 (station, entry) pairs are in progress with no
finished twin, across 314 stations; the collision wrongly marks **14 of them
built across 11 stations** — 1 storage, 2 production, 2 habitation, 5 defence,
1 build, 3 structural. Small, but it is a correctness bug on capacity,
throughput *and* workforce, and JAR-041 is entirely accounted for by it.
**Fix: key `built_refs` on `(host, entry_id)`.** (Not applied — this task is
research-only.)

## JUK-948 — the allocation is right, so the deviation is price

In game: **18,957 energy cells** against a modelled 19,089, **−0.7 %**. That
**kills the ~1.37× allocation-error reading in Addendum 1.** The model is
correct here and the entire deviation is a price effect.

The player reports the station is labelled **[HACKED]**, and the save records
it: 13 `hacked="82283.124"` attributes on its components — an *expiry*
timestamp, against a game time of 82,130.2. **14 stations save-wide carry the
flag.** It is not parsed today.

This makes JUK-948 the first identified member of a **positive-offset**
population: it bids +0.10 to +0.23 of a band *low*, the opposite direction to
the production-input stations (CCN-497 −0.39, FSL-235 −0.34). A station state
with a known expiry is an attractive candidate for a price modifier, and it is
cheap to test — parse `hacked=` and compare the 14 flagged stations against the
rest.

## IRD-672 — three recyclers, not six; my count was wrong

The player reports **three** scrap processor modules, each listed **twice** in
the Logical Station Overview because each carries two products (claytronics and
hull parts) and only one is active at a time, swapping when a cycle completes.
`build_entry` agrees at 3 — **the "6" in Addendum 1 was my own join artifact**
against `module_ref`, which holds one row per product.

The model already halves each recipe for the alternation:
3 × (144,000 + 42,000)/2 = 279,000 energy cells/h, and the claytronics and
hull-parts rates reproduce to ~2 %. Yet the prices imply a target near
**258,500 units on a 4.9 h pool factor**, i.e. an energy throughput near
**52,600/h** — a fifth of the modelled figure — and the station's three wares
still disagree with each other (implied scales 6.44 / 3.23 / 1.39).

**HYPOTHESIS**: the engine sizes storage on the recipe **currently queued**
rather than the average of the alternation. That would contradict
save-semantics.md's "the alternation split does not matter — it scales every
rate on the module equally and cancels out", which was justified for ratios
*within* one module and does not hold when the split changes what a shared
input is rated at. *Needs:* in-game rates **and** storage maxima for energy
cells, hull parts, claytronics and scrap metal together.

## The price-update timer — found, and it FALSIFIES the staleness hypothesis

Stations carry `<event event="updatetradeoffers" time=…>`: **3,555 events over
1,804 stations**, next-fire times distributed uniformly 0–65 s ahead of game
time, so the trade-offer refresh period is **~65 s**. This is exactly the
per-station clock § B's leading hypothesis needed.

It does not work. Over the 541 stations with ≥ 3 input offers and a timer:

| dt to next fire (s) | 4.9 | 12.3 | 23.1 | 37.0 | 50.6 | 57.4 |
|---|---:|---:|---:|---:|---:|---:|
| median offset | −0.042 | −0.053 | −0.036 | −0.045 | −0.039 | −0.031 |

`corr(offset, time since last update) = −0.08`; `corr(|offset|, …) = +0.04`.
Flat. And a 65-second period cannot accumulate the ~0.78 h of throughput the
largest offsets correspond to — it is off by two orders of magnitude.

**§ B's leading hypothesis is withdrawn.** The per-station constancy, the
0.78 h ceiling and the sign flip between sides all still stand as measurements;
the staleness story that tied them together does not. The per-module reserve
remains the weaker surviving candidate, and `hacked=` is a new one worth a
cheap test.

## Revised ranking of the remaining leads

1. **Fix `built_refs` keying** — a confirmed correctness bug with a
   one-line-ish fix and an exact in-game validation already in the fixture.
2. **Parse `hacked=`** and score the 14 flagged stations against the rest.
   Cheap, and JUK-948 says price offsets exist in both directions.
3. **IRD-672's rates and maxima**, to settle queued-recipe vs averaged
   alternation.
4. **CCN-497 read twice** — still the sharpest test of whether the input
   offset is stable state or something that moves.
5. The sell-side +0.053, unchanged from § A.

---

# Addendum 3: IRD-672 as a test case — the allocation is exact

Player readings, 2026-07-28, now locked in `tests/data/station_readings.json`
with IRD-672 added to `EXACT_STATIONS`. Baseline raised 41 → **47 of 49**;
235 tests pass.

| ware | in game | model | err |
|---|---:|---:|---:|
| energy cells | 1,665,000 | 1,664,647 | −0.02 % |
| food rations | 34,560 | 34,560 | **exact** |
| medical supplies | 20,736 | 20,736 | **exact** |
| scrap metal | 40,000 | 40,000 | **exact** |
| claytronics | 8,577 | 8,592 | +0.17 % |
| hull parts | 29,379 | 29,427 | +0.16 % |
| raw scrap | *no allocation* | *no row* | ✓ |
| protectyon | 5 | **missing** | — |

## What this settles

**The alternation-split hypothesis is dead, and save-semantics.md is right.**
Three recyclers, each alternating between claytronics and hull parts, are
modelled as `3 × (144,000 + 42,000)/2 = 279,000` energy cells/h — and that
reproduces the 1,665k reading. So "the alternation split does not matter — it
scales every rate on the module equally and cancels out" **stands**, and
Addendum 2's "the engine sizes on the currently queued recipe" is withdrawn.

**Two structural rules confirmed from the game side.** Raw scrap holds 1,993
units and carries **no allocation** — and the player reports the UI itself
keeps it distinct from ware storage, which is the non-economy feedstock rule
confirmed from the other direction. And the scrapworks processing module
contributes its *output* (scrap metal, 40,000 exact) while its own energy draw
stays out of the split — exactly the KWC-232 rule, now reproduced on a second
station.

**Known gap:** the station allocates 5 **protectyon**, and the model emits no
row for it at all. Protectyon is the Boron shield-generator ware with its own
module. Small, but it is a *missing row*, not a wrong number — worth a check
that no protectyon-hosting station is mis-split because of it.

## And it re-frames IRD-672's prices

With the allocation confirmed exact, IRD-672's deviation is **entirely price**,
like JUK-948. Its implied fill shifts are +0.56 (energy cells), +0.36 (scrap
metal), +0.12 (hull parts) while both rations sit on the curve (+0.014,
+0.006). It is **not** one of the 14 hacked stations, so that candidate does
not cover it either.

## A better discriminator for the § A offset — CONFIRMED

Looking at why IRD-672's two dual-sided wares behave unlike its one-sided one
turns up a cleaner rule. The +0.053 offset is **not** keyed on the ware's role;
it is keyed on **whether the station posts a sell offer for it**:

| role | posts | n | offset | IQR |
|---|---|---:|---:|---:|
| input | buy only | 2,763 | −0.040 | 0.086 |
| input | **buy and sell** | **94** | **+0.049** | **0.024** |
| output | sell only | 1,388 | +0.053 | 0.015 |
| output | buy and sell | 58 | +0.057 | 0.019 |
| food | buy only | 1,837 | +0.007 | 0.008 |

An input-role ware that the station also sells takes the **supplier** offset,
not the consumer one — and takes it with the supplier's tight dispersion. This
follows naturally from the already-confirmed "buy = sell − 1 Cr on the same
(station, ware)": there is one price per (station, ware), and when both sides
are posted it is the seller's.

Scored on the 117 offers where the two rules disagree:

| rule | n | MAD | \|r\|>0.25 | bin RMSE |
|---|---:|---:|---:|---:|
| offset by ware role (a = −0.039) | 117 | 0.1800 | 23.1 % | 0.1984 |
| **offset by "does it sell it" (a = +0.053)** | 117 | **0.0156** | 10.3 % | **0.1411** |

Save-wide the change is small — 7,102 offers, MAD 0.0144 → 0.0141,
\|r\|>0.25 5.89 % → 5.67 % — because only 117 offers move. But the rule is
better *stated* this way, and it removes "output" from the § A statement:

```
s = cos(π · (fill + a) / 1.095)
a = +0.053   if the station posts a SELL offer for the ware
a = +0.007   ration, buy only
a = −0.040   production input, buy only  (a per-station constant, § B)
```

## The hacked-station test — inconclusive, not supporting

The 14 stations carrying `hacked=` give 11 with ≥ 2 unclamped input offers:
median offset −0.010 against −0.042 for the other 891, and 45 % positive
against 20 %. Suggestive, but the group spans −0.076 (IAZ-139) to +0.117
(JUK-948) and n = 11. **Not an explanation** — JUK-948 looks like the tail of a
small sample rather than a hack effect. Recording it as tested and weak.

## Revised leads

1. **Fix `built_refs` keying** — unchanged, still the only confirmed bug.
2. **The § B per-station input offset** — hypothesis-free again after both
   staleness and hacking failed. What survives is the measurement: a station
   constant, 0 → 0.78 h of consumption, shrinking with module count.
   CCN-497 read twice remains the sharpest test.
3. **Protectyon rows** — a missing allocation row on a known ware.
4. **IRD-672's prices**, now a clean price-only anomaly on a station whose
   allocation is confirmed to 0.2 % — the best-instrumented member of the
   positive-offset population.

---

# Addendum 4: lead 1 closed — the fix landed, and JAR-041 validates the chain

`built_refs` and `module_upgrades` are now keyed on `(host_id, entry_id)`
(commit `398208f`, schema v28). Verified independently of the change:
**237 tests pass**, readings **48 of 49** in-game, `analysis/storage.py`
untouched — the storage model landed on the number unaided.

## JAR-041, before and after

| | before | after |
|---|---:|---:|
| energy cells modelled | 42,516 | **21,002** |
| against in game | 21,001 | 21,001 |
| error | +102.4 % | **+0.0 %** |

And the station now prices **on the curve**, which is the part worth recording:

| ware | role | fill | s | implied shift |
|---|---|---:|---:|---:|
| energy cells | input | 0.704 | −0.410 | **−0.009** |
| soja beans | input | 0.658 | −0.285 | **−0.010** |
| water | input | 0.467 | +0.254 | **−0.009** |
| spices | input | 0.993 | −0.963 | +0.006 |
| soja husk | food | 0.829 | −0.742 | +0.009 |
| medical supplies | output | 0.436 | +0.177 | **+0.050** |

Station shift **+0.323 (sd 0.108) → −0.002 (sd 0.023)**; scale
**1.998 → 0.997**. Its output lands on **+0.050** against the § A constant of
+0.053, and its three buy-only inputs on −0.009 against the § B population
median of −0.040.

**This is a complete round trip.** The price model predicted a denominator
error of exactly 2× from prices alone; the player confirmed the second storage
module was still under construction; the parser fix removed the phantom
capacity; and the station now sits on the curve derived from the other 1,800.
Each step was measured independently of the others.

## The price population is unmoved

Re-run on the corrected import, the main sequence is identical in size and
essentially identical in fit — so nothing in § A or § B depended on the defect:

| population | n | MAD before | MAD after |
|---|---:|---:|---:|
| all buys | 5,492 | 0.0203 | 0.0202 |
| rations | 2,372 | 0.0165 | 0.0165 |
| production inputs | 3,085 | 0.0788 | **0.0778** |
| outputs (sell) | 1,544 | 0.1321 | 0.1321 |

The only movement is the input population, and it is JAR-041's four wares
coming onto the curve.

## Blast radius of the `build_entry` restructure — checked

The fix also folded each build storage's `type="expand"` plan into its station
(the expand copy carries the *station's* entry ids, so per-host keying
otherwise left 643 storage hosts with zero built entries). `build_entry` goes
43,108 → 32,519 rows and 2,405 → 1,803 hosts. Verified that nothing was lost:

- All 602 `<build … component=>` refs of class `station` have build_entry rows
  — a one-to-one fold of the 602 vanished hosts. The other 232 refs are ship
  builds and never had station plans.
- Zero build_entry hosts are non-station; zero are missing from `component`.
- Unbuilt entries available to the audit: 4,154 across 457 stations — *more*
  complete than before, since 3,819 genuinely-queued entries previously existed
  only under the storage host.

## Revised lead list

1. ~~Fix `built_refs` keying~~ — **done**.
2. **The condensate transport pool.** `analysis/storage.py:227` iterates a
   hardcoded `("container", "liquid", "solid")`; condensate is a fourth pool and
   never gets a computed row. 18 stations hold a condensate storage module and
   all 6 condensate rows in the DB are `proxy`. Correction to Addendum 3:
   protectyon is **not** a missing ware — its ware id is `condensate` (display
   name "Protectyon", Pirate DLC) and it is present in `wares.csv`. The exact
   target: `storage_pir_l_condensate_01_macro` is 50 m³ ÷ volume 10 = **5
   units**, the reading taken on IRD-672. Single-ware pool, no equal-hours
   split to get right.
3. **`nd_habitat_cap_boost`** unregistered in `modpatch.py` (habitat capacity
   S 2500 / M 5000 / L 10000 against stock 333/666/999) — a known-wrong input to
   the ration buffer and the efficiency. Blocked on `extract_modcaps` being
   unable to read `<diff>` files with no `<macro>`, and `extract_wares`
   handling only `<add sel=…>` and never `<replace>`.
4. **§ B's per-station input offset** — hypothesis-free after staleness and
   hacking both failed. CCN-497 read twice remains the sharpest test.
5. The § A offset of +0.053, unchanged.

**Also closed:** the hull-parts allocation error from
[fill-price-spread-2026-07-28.md](fill-price-spread-2026-07-28.md) (follow-up 3,
"ratio 1.171, the only ware-level model error above 6 %") is **gone**. On the
current import `(stock + buy amount) / allocation` for hull parts is **0.9986
over 66 offers**, and every ware with n ≥ 40 sits within 0.8 % of 1.000 (worst:
ice 0.992). The efficiency, idle-module and multi-queue work since then fixed
it.
