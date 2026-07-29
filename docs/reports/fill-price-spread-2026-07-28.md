# The fill-vs-price spread: a taxonomy

Save: `save_009.xml.gz` (game_time 81,948; DB save_id 58, schema v26).
Scatter: `output/fill_vs_price.html`, generator in the job scratch dir.
All 15,533 offers in the save are accounted for — no scope filter is applied
before classification.

## The partition

The main sequence is defined **mechanistically**, not by a residual cut. A
residual threshold would be circular: it would define the main sequence as
"whatever fits the model under test", and it would hide exactly the cases this
report is looking for — populations that fit for the wrong reason. An offer is
on the main sequence iff all six hold:

1. it comes from the station's own economy book — `flags` carry neither
   `shady` nor `supplies`;
2. the (station, ware) pair is not `lockavgprice`-pegged;
3. the price is engine-set — the host is not player-owned;
4. the host is a cargo-holding station, not a build storage and not a ship;
5. the host carries no build module;
6. the model produced a storage allocation for that (station, ware), in **any**
   role — output, input **or food**.

Deliberately *not* in the criterion: side, ware role, faction, allocation
source. Those were tested and are not discriminators (below).

Fill is the station's **net position** — `stock + undelivered inbound −
committed outbound` — not its cargo (see the addendum; the first cut of this
report used raw stock and that error propagated into its curve-shape finding).
Spread is measured as Σ|band_position − clamp(1 − fill)| over the offers
that have an allocation; offers with no allocation have no x-coordinate, never
appear in the scatter, and are reported by count only.

| category | n | buy | sell | n w/ alloc | Σ\|res\| | share of spread | MAD | median res | corr(fill,band) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **main sequence** | **7,229** | 5,507 | 1,722 | 7,229 | 628.5 | **48.9 %** | 0.053 | +0.028 | −0.90 |
| lockavgprice-pegged | 1,175 | 587 | 588 | 1,169 | 531.5 | 41.3 % | 0.500 | −0.500 | −0.04 |
| yard / wharf / dock | 701 | 679 | 22 | 699 | 104.2 | 8.1 % | 0.169 | +0.167 | −0.94 |
| player-owned | 54 | 38 | 16 | 36 | 12.6 | 1.0 % | 0.135 | +0.006 | −0.08 |
| self-supply (`supplies`) | 1,207 | 1,207 | 0 | 36 | 9.0 | 0.7 % | 0.250 | −0.250 | — |
| black-market (`shady`) | 3,273 | 3,273 | 0 | 0 | — | — | — | — | — |
| build-storage demand | 1,788 | 1,769 | 19 | 0 | — | — | — | — | — |
| ship-hosted | 72 | 72 | 0 | 0 | — | — | — | — | — |
| no modelled allocation | 34 | 30 | 4 | 0 | — | — | — | — | — |
| **total** | **15,533** | 13,162 | 2,371 | 9,169 | 1,285.7 | 100 % | | | |

Populations sum to 15,533 exactly. The four categories with no allocation
(shady, build-storage, ship-hosted, no-alloc) hold 5,167 offers — 33 % of the
save's book — and their share of the *spread* is nil by construction: with no
fill coordinate they never enter the scatter at all. Their diagnosis rests on
price statistics instead, given per category below.

## Category findings

### Main sequence — 7,229 offers, 48.9 % of spread

`band = clamp(1 − stock/allocation)`, MAD 0.053 band units, corr −0.90. Three
sub-populations previously excluded were re-admitted after measurement, and all
three sit on the same curve:

| sub-population | n | MAD | median res | \|res\|>0.25 |
|---|---:|---:|---:|---:|
| role = output | 1,702 | 0.047 | +0.024 | 3.8 % |
| role = input | 3,158 | 0.085 | +0.067 | 11.3 % |
| **role = food (was excluded)** | 2,369 | **0.033** | **+0.000** | 4.1 % |
| allocation = computed | 7,124 | 0.053 | +0.028 | 7.2 % |
| allocation = proxy | 105 | 0.053 | +0.019 | 3.8 % |
| **owner = xenon (was excluded)** | 41 | **0.039** | +0.021 | **0.0 %** |
| side = buy | 5,507 | 0.056 | +0.030 | 8.2 % |
| side = sell | 1,722 | 0.047 | +0.026 | 3.8 % |

**Diagnosis: the food-ware and Xenon exclusions were measurement defects
(scope).** Food-role offers are the *cleanest* population in the save — median
residual exactly 0.000, MAD 0.033, zero rows past 100 % fill. The prior
justification ("219 role='food' rows over allocation, worst 110×") is about
`station_storage` rows in general; it does not hold for the subset that posts
offers. Excluding them removed 2,369 of the best points, a third of the
addressable population. Xenon: 41 offers, MAD 0.039, not one residual over
0.25. Both are now in scope.

**CONFIRMED: side is not a discriminator; the two sides are one price.** Of the
706 (station, ware) pairs posting both a buy and a sell offer, **704 have
buy = sell − 1.00 Cr exactly** (the two exceptions are player-owned). This is a
universal 1 Cr bid-ask spread, not the `lockavgprice` quirk it was recorded as
in Layer 6. Corollary: buy offers on *output*-role wares (n=40) track the sell
curve (band by fill bucket 0.99 / 0.83 / 0.62 / 0.23 / 0.06) and sell offers on
*input*-role wares (n=19) do too. The apparent "buy side runs 6 % of a band
higher" is a composition effect — buys are mostly inputs, sells mostly outputs —
not a side effect. **Layer 4's "buy side: NOT modeled" should be retired.**

Residual structure that is *real*: a hump peaking at +0.11 band around
10–50 % fill and returning to ~0 at both ends, present in inputs and rations
alike. See the model proposals.

### lockavgprice-pegged — 1,175, 41.3 % of spread

Real behavior, already documented as Layer 6, and now the single largest
contributor to the spread. Price is band average regardless of stock:
corr(fill, band) = **−0.04**, median price/avg 1.0000 with 42 distinct values
across 1,175 offers, sells exactly at avg and buys at avg − 1. They sit as a
flat horizontal line at band ≈ 0.5 through the whole scatter. Correctly
excluded; no fix needed.

### Black market (`shady`) — 3,273, and one real defect

Real behavior: a separate book, opened per station by that station's
`shadyguy` post (823 posts ↔ 823 stations). Price-inelastic — median
**1.055 × band max**, identical to three decimals across all four wares
(stimulants 1.056, spacefuel 1.056, spaceweed 1.055, majadust 1.055), with a
tail to 2.75× avg; corr(amount, price) = −0.08. 3,245 of the save's 3,605
above-band buys are shady.

**Diagnosis: real behavior, but it was causing a measurement defect — FIXED.**
The storage proxy was folding shady buy amounts into `stock + buy` and minting
**546 phantom (station, ware) allocation rows across 143 non-producing
stations**, every one 100 % shady-sourced and all four illegal wares.
`analysis/storage.py` now drops `shady`-flagged buys from the proxy entirely
(no row: nothing is allocated for them). Effect on the DB:
`station_storage` role='input'/source='proxy' rows 1,831 → 1,278. Test:
`tests/test_storage.py::test_shady_buys_get_no_storage_at_all`. Their prior
absence from the scatter was accidental — they were filtered by the
"producers" and "excluded hosts" sets, not by anything that knew what they
were.

### Self-supply (`supplies`) — 1,207

Real behavior, and a **new CONFIRMED rule**: the self-supply buy price is a
fixed per-ware multiple of band average, independent of station, stock and
faction — only **10 distinct price/avg values across 1,207 offers**, one per
ware: smartchips 1.1053 (n=488), missilecomponents 1.2222 (359),
dronecomponents 1.1247 (222), energycells 1.1875 (59), metallicmicrolattice
1.0700 (36), siliconcarbide 1.0753 (23), silicon 1.0769, ore 1.0800,
hullparts 1.1507, claytronics 1.0750. The multiplier is **not** the recipe
input value (Σ inputs·avg / amount ÷ avg gives 0.72–0.95 against observed
1.07–1.22). Correctly out of scope for the fill curve.

### Yards / wharfs / docks — 701, 8.1 % of spread

Real behavior, and a **different calibration of the same functional form** —
not noise. Fitting `band = clamp(1 − fill^k)` on the pending-corrected net
position gives **k = 2.60, MAD 0.0382** — as tight as the main sequence's
0.0410, and against MAD 0.1705 at k = 1.00. They also run their inventories
much fuller: fill deciles 5 / 19 / 45 / 66 / **76** / 85 / 91 / 97 / 100
against the main sequence's 1 / 17 / 31 / 42 / **54** / 66 / 79 / 91 / 98.
The proxy allocation is not the cause: `stock + buy_amount` reproduces the
proxy by construction, and the exact denominator gives the same k = 2.60
(MAD 0.0367).

Their **21 sell offers are noise** — band positions 0.02, 0.03, 0.04, 0.05,
0.07, 0.11, 0.12, 0.16, 0.18, 0.18, 0.24, 0.35, 0.43, 0.44, 0.52, 0.55, 0.58,
0.65, 0.72, 0.96, 1.00, with no fill structure. Too few and too scattered to
model; a yard is a buyer.

### Build-storage demand — 1,788

Real behavior. Construction buyers do not price off stock at all: median band
position **exactly 1.000**, median price/max exactly 1.000, 189 above band max.
They hold no allocation, so they cannot appear in the scatter.

### Player-owned — 54

Real behavior, off-model by design (Layer 5, manual thresholds).
|res|>0.25 on 38.9 % of the 36 that have an allocation. **MXH-411 does not
settle the hybrid-yard proxy question** as hoped: it carries player-set
`ware_limit` rows (`max` energycells 739,800 vs a proxy of 493,552), so what it
shows is the player's configuration, not the engine's allocation for a
production+build hybrid. That question stays open and needs an NPC hybrid.

### Ship-hosted (72) and no-allocation (34)

Ship-hosted offers are all `invertfactionrestriction|skipbuyerownaccount` buys
on XL ships across many factions — a trader book, not station storage.
No-allocation rows are `rawscrap`/`rawkhaakscrap` (the confirmed non-economy
feedstock rule) and `condensate` on non-producers. Both correctly carry no
allocation; neither is a defect.

## Rebutting the `a` non-goal

The non-goal said not to chase the price-curve scale `a` in
`1 − band = a × fill^k`. The evidence says `a` is not a free parameter, so the
non-goal is moot rather than deferred, and saying so changes the model.

**CONFIRMED: a buy offer's `amount` is exactly the allocation minus the
stock.** Across 5,334 main-sequence buys, `(stock + amount) / modelled
allocation` has median **1.0000**, 72.6 % within 5 % and 88.1 % within 20 %.
Two consequences:

1. The storage-allocation model now has an independent, save-derived
   validation on thousands of NPC offers, not only 18 in-game readings. It also
   localises the remaining model error precisely: **hullparts 1.171** (the model
   under-allocates hull parts by ~17 %) and quantumtubes 1.056; every other ware
   with n ≥ 40 lands within 0.7 % of 1.000.
2. The scatter's x-axis can use a *measured* denominator for any ware with an
   open buy offer, removing allocation-model error from the fill coordinate.

With the denominator pinned that way, `a = 1.000` — the floor arrives at 100 %
fill, not somewhere between 8.6 % and 82.3 %. The at-floor population
(band < 0.02, n = 334) sits at a median fill of **97.4 %**; the at-ceiling
population (band > 0.98, n = 1,092) at **0.0 %**. The wandering `a` was an
artifact of fitting through clamped points — a cohort that saturates at both
ends flattens the fitted slope arbitrarily — and of the pool-split error in the
modelled allocation being read as scale.

So `a` is **not a category discriminator**. The *exponent* is, and that is the
finding worth the exercise: see the addendum.

## Proposed follow-up models, ranked

1. **Mid-range curvature (the hump).** The engine's price is not exactly linear
   in stock; it bulges ~0.15 band above the line around a third full and
   rejoins at both ends. Functional form to try:
   `band = 1 − f + c·f·(1−f)` with c ≈ 0.45, or equivalently a quadratic
   interpolation between the two clamps. Driver unknown — test whether c varies
   with ware, faction or module count. *Validates/falsifies:* any single station
   read at three stock levels across a restock cycle; a solar plant is ideal
   because it has one ware and no input coupling. Falsified if c is not
   reproducible on a fixed station over time.
2. **Yard pricing (k = 2.60, +0.167 level).** *(The 2.38 first written here was
   measured on the uncorrected fill numerator; the addendum's 2.60 supersedes
   it — see "CORRECTION: `k = 1.00` was wrong" below.)* Yards likely price off outstanding
   build demand rather than stock, on the same clamped form but with the
   denominator being the funded order bill of materials rather than the
   allocation. *Validates:* an NPC wharf with a known order queue; compare
   `stock + amount` against Σ recipe of its queued ships. Falsified if k stays
   ≈ 2.60 with a demand denominator.
3. **Hull-parts allocation error (ratio 1.171, n = 65).** The pool split gives
   hull parts ~17 % less than the game does, consistently. Likely a
   throughput input to the equal-hours split — hull parts are produced by
   modules whose recipe has an unusual cycle time or a `recycling`/`closedloop`
   variant the resolver is not picking. *Validates:* one in-game read of a hull
   parts allocation on a station that also makes something else. This is the
   only ware-level model error above 6 %.
4. **The 1 Cr bid-ask spread as a global rule.** Assert `buy = sell − 1` for
   every station-ware and use it to derive a sell reference for stations that
   only buy. *Falsified* by any (station, ware) pair with both sides and a
   delta ≠ 1 that is not player-owned; none exists in this save (704/706).
5. **Self-supply per-ware multiplier.** Ten constants, source unidentified.
   *Validates:* extract-gamedata sweep for a per-ware field near 1.07–1.22;
   candidates are a markup on the build-price factor path rather than the
   recipe value, which is already excluded numerically.
6. **Hybrid production+build stations.** Still on the proxy path on the
   strength of a now-invalidated over-fill argument. MXH-411 cannot settle it
   (player limits). *Needs:* an NPC station with both a production and a build
   module — ULG-519 is the candidate here — and an in-game read of one
   production ware's max. Falsified if the computed path matches within a few
   percent.

## Changes committed with this report

- `analysis/storage.py`: `shady`-flagged buys are dropped from the storage
  proxy (546 phantom allocation rows removed, 143 stations).
- `tests/test_storage.py`: `test_shady_buys_get_no_storage_at_all`.
- Scatter regenerated with the mechanistic partition; every off-sequence
  category is a toggleable legend entry rather than a silent filter.

Before → after on the scatter population:

| | before | after |
|---|---:|---:|
| sell n | 1,628 | 1,722 |
| buy n | 3,095 | 5,507 |
| sell above band | 0 | 0 |
| buy above band | 131 | 132 |
| sell past 100 % fill | 25 | 25 |
| buy past 100 % fill | 252 | 252 |
| sell median band by fill bucket | 0.99 / 0.85 / 0.66 / 0.46 / 0.01 | 0.99 / 0.85 / 0.67 / 0.45 / 0.01 |
| buy median band by fill bucket | 1.00 / 0.96 / 0.75 / 0.44 / 0.12 | 1.00 / 0.94 / 0.70 / 0.41 / 0.10 |

The population grew 53 % while the bucket medians moved by at most 0.05 — which
is itself the evidence that the re-admitted categories belong on the curve.


---

# Addendum (same day): pending, and the curve is not linear

Raised in review: *does the fill denominator account for pending
transactions?* **It did not — neither the numerator nor the denominator.** The
generator divided raw `cargo.amount` by the modelled allocation. That was the
largest remaining measurement defect in this analysis, and it invalidated this
report's headline curve-shape claim.

**CONFIRMED: stations price off their net position, not their cargo.**
Undelivered inbound already counts as held; committed outbound counts as
already gone. The save carries 2,510 pending trades (1,793 with a station
buyer, 717 with a station seller), touching **1,287 of 7,229 main-sequence
offers (17.8 %)**.

| fill numerator | n | MAD | median res | \|res\|>0.25 |
|---|---:|---:|---:|---:|
| stock only (as first published) | 7,229 | 0.0527 | +0.0283 | 7.18 % |
| stock − outbound | 7,229 | 0.0500 | +0.0250 | 6.82 % |
| stock + inbound | 7,229 | 0.0467 | +0.0361 | 4.77 % |
| **stock + inbound − outbound** | 7,229 | **0.0448** | +0.0328 | **4.40 %** |
| *…restricted to the 1,287 offers that carry pending* | 1,287 | 0.0832 → **0.0411** | −0.011 → +0.025 | |

**This dissolves the near-empty off-sequence tranche.** Offers at fill < 5 %
with band < 0.80 — visually a scatter of near-empty stations pricing as though
they were full — number 43. **35 of them (81 %) have inbound pending**, against
7 % of the near-empty offers that *are* on-sequence. Their median residual goes
from **−0.502 (MAD 0.502) to +0.013 (MAD 0.095)**. They were never a separate
category; they are main-sequence stations with a delivery in flight.

**CORRECTION: `k = 1.00` was wrong.** That fit was measured on the uncorrected
numerator, where pending noise was suppressing any exponent above 1. On the net
position the minimum moves off the boundary:

| population | denominator | best k | MAD @ best | MAD @ k=1.00 |
|---|---|---:|---:|---:|
| main sequence | modelled allocation | **1.14** | 0.0410 | 0.0448 |
| main-sequence buys | exact (stock + amount) | **1.30** | 0.0430 | 0.0443 |
| yards | proxy allocation | **2.60** | 0.0382 | 0.1705 |
| yard buys | exact (stock + amount) | **2.60** | 0.0367 | 0.1725 |

So the review's read is right on all counts: a linear model does not work, the
shape is a power curve, yards share that shape with a distinctly different
exponent, and yard sells are noise. The `a`-rebuttal above stands — the scale
is pinned at 1.000 by the offer-derived denominator — but the *exponent* is the
real category discriminator, and it is 1.14 / 2.60, not 1.00 / 2.38.

**On the buy/sell gap being the −1 Cr adjustment:** on the same (station, ware)
it is exactly that, 704/706. Across the population the role-matched median
residuals differ by ≈1 Cr in magnitude — output buy −0.44 Cr vs output sell
+0.72 Cr; input buy +2.27 Cr vs input sell +1.33 Cr — but the *direction*
flips, because these are different stations (only 706 pairs post both sides,
and the cross-side samples are n = 40 and n = 55). So: magnitude consistent
with the 1 Cr, direction unresolved at population level, exact on matched
pairs.

**Residual structure that survives all of this** — the "noise around the main
sequence" — is not symmetric noise. It is a systematic hump, and it is
role-selective:

| | 0–10 % | 10–25 % | 25–50 % | 50–75 % | 75–101 % | >101 % |
|---|---:|---:|---:|---:|---:|---:|
| main (all) | +0.000 | +0.080 | +0.062 | +0.031 | +0.006 | +0.089 |
| yards | +0.038 | +0.153 | +0.294 | +0.233 | +0.175 | +0.152 |

and by role, at k = 1: rations **+0.0000** (n = 2,364, exactly on the curve),
outputs +0.017, inputs **+0.081**. A single exponent of 1.14 absorbs most of
the hump (median residual +0.0065) but not its role dependence. That
role-selectivity — rations exact, production inputs biased high — is the
sharpest unexplained thing left and should lead the follow-up list, ahead of
the curvature item, which is now largely explained by k > 1.

No `src/` change follows from this: the pricing model is knowledge, not a
feature, and `analysis/storage.py` does not use pending. The fix is in the
scatter generator, and `output/fill_vs_price.html` is regenerated with the net
position on the x-axis and both power curves drawn.


---

# Addendum 2: the steep low-fill branch on the sell side

Raised in review from the scatter: a second locus among "main sequence — sell",
trending from band ≈ 0.85 at ~5 % fill down to ≈ 0.44 at ~20 %, far steeper
than the k = 1.14 curve. It is real, and it is not the allocation model being
wrong.

**Population.** 112 sell offers across **110 distinct stations** — so a
per-station-design property, not a few outliers. 110 of 112 are role='output';
111 of 112 have a `computed` allocation. It is essentially absent on the buy
side (3 of 1,323 low-fill buys).

**What separates them.** Expressing each offer as an implied *price span* —
the stock at which the price would reach the band floor, as a fraction of the
modelled allocation — the branch sits at **0.47** against **1.09** for the
low-fill sells that are on-curve. The span is a **per-(ware, role) cohort
constant**, and its distribution over interior sells is unimodal at 1.0–1.1
with a long low tail:

| ware (output) | n | span / allocation | IQR/med |
|---|---:|---:|---:|
| computronicsubstrate | 18 | **0.194** | 0.37 |
| claytronics | 46 | 0.797 | 0.86 |
| siliconwafers | 29 | 0.823 | 0.62 |
| *…the pack (energycells, hullparts, graphene, microchips…)* | | 0.99 – 1.16 | 0.08 – 0.32 |
| advancedelectronics | 43 | 1.319 | 0.35 |
| terranmre | 15 | 1.378 | 0.21 |

The computronic-substrate cohort is the branch's visible core and is tight:
18 stations sharing one design (allocation 5,359, throughput 642/h) trace band
0.916 → 0.698 as fill goes 1.83 % → 4.03 %, a slope ~10× the main sequence's.

**Diagnosis: real behavior, NOT an allocation defect.** Three independent
checks:

1. Correlation between a ware's sell-side span/allocation and its buy-derived
   *true* allocation ratio `(stock + amount)/model` is **+0.11** over 18 wares
   with both. The allocation is 1.000 for nearly every ware whose sell-side
   span ranges 0.82–1.38 — the two quantities are unrelated.
2. **GDR-378**, one of the in-game-validated stations, shows
   computronicsubstrate at span/allocation **0.144** while its five input wares
   in the same pool on the same station sit at 1.02–1.12. Same station, same
   save, same allocation model.
3. Within-station dispersion of span/allocation (IQR/med 0.34) is *worse* than
   global (0.27), so it is not a station constant either — it is per ware.

**What sets the multiplier is unknown.** Correlations over the 28 wares with
n ≥ 15: log avg price −0.49 (and computronicsubstrate, the most expensive ware
at 8,280 Cr, is almost single-handedly driving it), log volume −0.33,
allocation in hours −0.16, ware's share of its transport pool −0.05,
throughput +0.05, wares per station +0.02. Nothing explains it. Note also that
the multiplier is not purely per-ware: siliconwafers reads 0.823 as an output
and 1.184 as an input, on different stations.

**Falsification.** The hypothesis is "the price reference span is
`m(ware, role) × allocation` with m a game constant". It is falsified if a
single station's m moves between saves at constant allocation, or if an
in-game read of a computronic-substrate producer's storage max comes back near
1,000 rather than ~5,300 (which would make it an allocation error after all —
the one check I cannot do from the save, because no station posts a
computronicsubstrate *buy* offer to derive the allocation from).

Broken out in the scatter as a `narrow price span (output)` legend entry
(116 offers: computronicsubstrate, claytronics, siliconwafers outputs), defined
at **cohort** level rather than by a point-level residual cut. With it removed,
main-sequence sell drops 1,722 → 1,608.


---

# Addendum 3: there are two curves, selected by ware role — and one of them is a cosine

Raised in review: fit a cosine to the main-sequence sell population; the power
curves will never fit that shape. The cosine **is** there and it is essentially
exact — but not on the sell population. It is on the ration wares, which this
report re-admitted to the main sequence two addenda ago.

## Protocol

Shape parameters are **global**; the scale `S` is fitted **per cohort**
(span/allocation is already established as a per-(ware, role) constant, so a
free per-point scale would let any shape win). Criterion is **median |residual|**,
not SSE — the population has a known contaminating tail, and under SSE the
ranking inverts. Fill `u` is the pending-corrected net position over the
modelled allocation. Narrow-span cohorts excluded.

## Result: the shape depends on role, not side

| population | n | cohorts | best fit | MAD | 2nd best | MAD |
|---|---:|---:|---|---:|---|---:|
| **production wares** (role=output) | 1,331 | 24 | `1 − (u/0.766)^1.55` | **0.0076** | pure cosine (S 0.920) | 0.0138 |
| **ration wares** (role=food) | 2,369 | 9 | `(1 + cos(π·u/1.085))/2` | **0.0016** | power k=1.50 | 0.0080 |
| production inputs (role=input) | 3,006 | 25 | pure cosine (S 1.178) | 0.0439 | power k=1.45 | 0.0497 |
| yards | 613 | — | `1 − (u/1.0)^2.60` | 0.0367 | — | — |

Ranked on the full sell population the order was: power k=1.55 (0.0072),
warped cosine k=0.91 (0.0080), pure cosine (0.0138), quarter cosine (0.0186),
linear (0.0291). So the sell/output population really does prefer a power law —
but **linear is 4× worse than either**, which is the part of the review's read
that was dead right, and my earlier `k = 1.14` was a non-robust fit contaminated
by the tail. The robust value is **k ≈ 1.55**, which recovers the originally
reported 1.53–1.64.

## The ration cosine is exact

`band = (1 + cos(π · net / (1.085 × allocation))) / 2`

| ware | n | fitted S | MAD | \|r\|<0.005 | \|r\|<0.02 |
|---|---:|---:|---:|---:|---:|
| medicalsupplies | 1,065 | 1.084 | 0.00134 | 88.9 % | 94.3 % |
| foodrations | 292 | 1.094 | 0.00792 | 25.7 % | 93.5 % |
| sojahusk | 224 | 1.085 | 0.00025 | 84.4 % | 92.9 % |
| nostropoil | 212 | 1.100 | 0.00029 | 74.5 % | 92.9 % |
| cheltmeat | 193 | 1.068 | 0.00341 | 64.8 % | 91.7 % |
| scruffinfruits | 173 | 1.069 | 0.00082 | 87.3 % | 99.4 % |
| terranmre | 102 | 1.091 | 0.00012 | 87.3 % | 97.1 % |
| water | 50 | 1.085 | 0.00052 | 84.0 % | 90.0 % |
| bofu | 58 | 0.200 | 0.00000 | 91.4 % | 93.1 % |
| **pooled** | **2,369** | | **0.00163** | **77.2 %** | **94.1 %** |

Eight of nine cohorts land on **S = 1.068–1.100** — a constant, not a fitted
per-ware parameter. (`bofu` at 0.200 is degenerate: every point is on a clamp.)
Decile-by-decile median residual never exceeds **0.0038**; the power law on the
same population swings from +0.023 to +0.050. This is the tightest law found
anywhere in this work — tighter than the allocation model itself.

## The output power law is not an artifact of a noisy denominator

The obvious objection is that outputs prefer a power law only because their
allocation carries pool-split error, and rations do not. Slicing outputs by how
many wares share the station's pool tests it directly, and **the objection
fails — the power law gets *stronger* as the denominator gets cleaner**:

| output slice | n | cosine MAD | power MAD | winner |
|---|---:|---:|---:|---|
| 1–2 ware stations (no split error) | 50 | 0.0089 | **0.0012** | power ×7.2 |
| 3–5 ware stations | 283 | 0.0093 | **0.0035** | power ×2.7 |
| 6+ ware stations | 839 | 0.0149 | **0.0089** | power ×1.7 |

On the cleanest slice the power law fits to **MAD 0.0012 band units**. So the
two shapes are real and distinct, not one shape seen through different amounts
of noise.

## Where the cosine actually fails on outputs

Its flatness at the top is quadratic; the data's is order 1.5. Median residual
by decile of `u/S` for the output population:

| u/S | 0.05 | 0.15 | 0.25 | 0.35 | 0.45 | 0.55 | 0.65 | 0.75 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| power k=1.55 | −0.001 | −0.006 | −0.006 | −0.015 | −0.005 | −0.001 | +0.004 | +0.017 |
| pure cosine | −0.005 | **−0.021** | **−0.021** | −0.009 | +0.003 | +0.011 | +0.015 | **+0.064** |

The cosine sits systematically *above* the data through the upper-middle and
then undershoots badly approaching the floor. The power law's worst decile is
0.017 against the cosine's 0.064.

## Consequences

1. **Two engine price curves, selected by ware role.** This is a stronger
   statement than anything in Layer 2, and it explains why a single fitted
   exponent never sat right: the population is a mixture.
2. **Rations are now the best-characterised population in the save** — the very
   population the original scope excluded as "tabled, overshoots badly".
3. `S` differs between them (0.766 vs 1.085), so the *scale* differs by role
   too. Rations reach the floor slightly past their modelled 4 h buffer;
   production wares reach it at ~77 % of allocation.
4. **Inputs remain unexplained** (MAD 0.044 under either shape). They are now
   the largest open problem, not the curvature.

**Falsification.** Read one habitat's ration price at three stock levels and
one single-ware producer's output price at three levels. The ration reading
must sit within ~0.005 band of the cosine at S = 1.085; the producer within
~0.002 of `1 − (u/0.766)^1.55`. Either shape failing on a station with a
directly-read allocation kills it. Neither exponent should be assumed stable
across saves — both are fitted on this one.

The scatter now draws all three reference curves (production, rations, yards).
