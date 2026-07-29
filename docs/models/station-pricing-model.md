# How X4 station pricing works (generalized form)

Reference for the market/price work. Assembled 2026-07-29 from three sessions
of reverse engineering against `save_001` (game time 82,130) plus in-game
readings taken by the player from the Logical Station Overview and the station
trade panel. The detailed derivations, fits and rejected alternatives live in
[../reports/price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md)
(6 addenda) and
[../reports/fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md)
(3 addenda); the rule-by-rule notes live in
[../reference/save-semantics.md](../reference/save-semantics.md) § Ware pricing
model. This document is the *shape* of the model, not its history.

Each claim is tagged by confidence:

- **[UI]** — the game states it outright in the station trade panel or the
  Logical Station Overview (authoritative).
- **[OBS]** — measured in save data, with the population size given.
- **[EXP]** — established by a controlled in-game action or reading.
- **[INF]** — inferred, consistent with the data, not independently verified.

## The model in one paragraph

A ware's price at a station is its **band average** times one plus a sum of
**additive modifiers, each expressed as a percentage of that average** — this
is not a reconstruction, it is what the trade panel prints. The only modifier
that moves with the station's state is the **supply/demand term**, and that
term is a **cosine in how full the station's storage is**. Everything else is
either a fixed per-station or per-relation adjustment applied on top, or a
different price book entirely. The savegame's offer price carries the
supply/demand term alone; the reputation discount is applied at display time.
So the whole model is: pick the band, evaluate one cosine, add the flat terms.

## The generalized form

```
price   = avg × (1 + Σ modifiers)

supply/demand modifier = s × spread(sign of s)

  s     = cos(π · clamp(u / S, 0, 1))              S = 1.095
  u     = fill / m + a
  fill  = (stock + undelivered inbound − committed outbound) / allocation

  spread(+) = price_max/avg − 1        spread(−) = 1 − price_min/avg
```

The `allocation` in `fill` is the storage model's output —
[station-storage-model.md](station-storage-model.md).

`s` is the **normalised price coordinate**: `+1` = band maximum, `0` = band
average, `−1` = band minimum. Two shape parameters:

| symbol | meaning | usual value |
|---|---|---|
| `S` | span of the cosine in fill units | **1.095**, global |
| `m` | price target ÷ storage allocation | **1**, but not always |
| `a` | additive offset on the fill axis | population-dependent, ±0.05 |

**`S = 1.095` is global [OBS].** Fitted on 5,428 buy offers over 40 bins, and
independently on 2,369 ration offers at 1.085 — same law, same span, disjoint
populations. Bin RMSE 0.0124 against a clamped line's 0.1207: the cosine beats
a straight line by **10×**.

**Always work on `s`, never on `(price − min)/(max − min)` [OBS].** 1,851 of
1,891 wares have symmetric bands and the two agree; the **40 that do not** —
ore (−14 %/+16 %), food rations, graphene, engine parts, ice — kink at avg on
the band-position axis and will corrupt any fit.

**`fill` uses the net position, not raw cargo [OBS].** Undelivered inbound
already counts as held and committed outbound counts as gone. 2,510 pending
trades touch 17.8 % of offers; ignoring them was the single largest measurement
defect in this work and it inverted a curve-shape conclusion.

### The offset `a`

Selected by **whether the station posts a sell offer for that ware**, not by
the ware's role [OBS]:

| population | `a` | n | MAD |
|---|---:|---:|---:|
| station posts a SELL offer (supplier side) | **+0.053** | 1,704 | 0.0125 |
| buy-only production input | **−0.039** | 3,024 | 0.0714 |
| buy-only ration | **+0.006** | 2,361 | **0.0015** |
| condensate / Protectyon | +0.048 | 16 | 0.0053 |

An input-role ware the station *also sells* takes the supplier offset
(+0.049, IQR 0.024) rather than the consumer one (−0.040, IQR 0.086). This
follows from a confirmed corollary: **`buy = sell − 1 Cr` on the same
(station, ware)** [OBS], 704 of 706 pairs exactly, the two exceptions
player-owned. There is one price per (station, ware); when both sides are
posted it is the seller's.

The offset is **additive in fill and scale-invariant** [OBS], not a rescaled
span: energy-cell sell offers hold `a` at 0.0480–0.0489 across a 3× range of
fill and across allocations from 98 k to 250 k units, with an IQR under 0.001,
while the equivalent multiplicative parameter moves 8 %.

**The −0.039 input offset is a per-station constant** [OBS] — one number shared
by every production input a station buys (within-station sd 0.0114 against
between-station sd 0.0542), running 0 to a ceiling of ~0.78 h of consumption
and shrinking monotonically with the station's production module count. **Its
cause is unknown.** It is not an allocation error: for inputs posting a buy
offer, `stock + inbound + amount` equals the modelled allocation at median
ratio 0.9999.

### The price target `m`

`m = 1` for the bulk of the economy — the price runs over the storage
allocation the equal-hours model computes (see
[../reference/save-semantics.md](../reference/save-semantics.md) § storage).
**But `m ≠ 1` genuinely exists** [EXP]:

Tidebreak (VOM-540) prices Protectyon over a **173-unit target against a
5,000-unit allocation**, `m = 0.035`. The allocation is confirmed twice on the
offer-derived floor (23 + 4,977 and 22 + 4,978 = 5,000). Two readings one unit
apart — its shield generator consumes ~1/hour — moved the price **+17.41 Cr**;
the 5,000-unit allocation permits **0.67 Cr** per unit and a 173-unit target
predicts **19.28 Cr**. A constant additive stock reserve over the full
allocation cannot fit both points (the implied reserve moves 28 units for a
1-unit change); a smaller denominator fits exactly.

Save-wide, implied `m` peaks at 0.9–1.0 with a long low tail: **247 offers at
`m < 0.65` across 232 stations and 28 wares**, 235 of them sell/output. Per
(ware, role): computronicsubstrate output ≈ 0.10, claytronics 0.56 **bimodal**
(clusters near 0.28 and 0.80), siliconwafers 0.60, microchips 0.76, hullparts
0.80; inputs cluster at 1.10–1.19. Some cohorts are tight (weaponcomponents
IQR/median 0.09, quantumtubes 0.07), others are not.

**`m` and `a` trade off at any single fill** — the decomposition `u = fill/m + a`
is a convention, not a derived fact. Which of the two the engine actually
carries is **[INF]** and open.

## The other modifiers

**Reputation discount, applied at display time [UI].** `player price =
economy price × (1 − tier% − event%)`. Tiers: Known Associate 5 % (relation
≥ 0.01), Prized Investor 15 % (≥ 0.1), Partnership Agreement 25 % (≥ 1.0).
The savegame's offer price does **not** include it: UDX-946's refined-metals
sell offer reads −38.70 % against a panel showing −38.9 % supply plus −9.1 %
reputation.

**The panel rounds its percentages UP [EXP].** Tidebreak displays "Low Supply
+9.2 %" against a true +9.109 %. A panel figure is a *ceiling* on the true
modifier, good to 0.1 pp — **fit the offer price, not the panel figure**.

**Worked example [UI]** — UDX-946 (ARG Ore Refinery I, The Reach):

| ware | panel | price | check |
|---|---|---:|---|
| refined metals (sell) | High Supply −38.9 %, Prized Investor −9.1 %, Total −48.0 % | 76.82 | 148 × 0.520 = 76.96 |
| ore (buy) | High Demand +6.6 % | 53.30 | 50 × 1.066 = **53.30 exact** |

## Populations that do NOT use this model

Each is a separate book, confirmed by measurement rather than assumed [OBS]:

| book | n | behaviour |
|---|---:|---|
| `lockavgprice` whitelist | 1,175 | pegged at band **average** regardless of stock; sell = avg exactly, buy = avg − 1 |
| `supplies` (self-supply) | 1,309 | a fixed per-ware multiple of avg — **10 distinct constants**, 1.07–1.22× |
| `shady` (black market) | 3,273 | ≈ **1.055 × band max**, no fill dependence; opened per station by a `shadyguy` post |
| build storages | 1,771 | sit at band max; hold no allocation, so they have no fill coordinate at all |
| yards / wharfs / docks | 701 | same family, different exponent (`k ≈ 2.6`); run much fuller, median fill 76 % vs 54 % |
| player-owned | 54 | manual thresholds — `price_setting` and `ware_limit`, off-model by design |

`supplies` and `yard` are characterised but **not explained**. The rest are
understood.

**Deployables are priced by recipe, not by stock [OBS].** Satellites, mines and
the like are built on demand at
`base_price × (Σ recipe·E / Σ recipe·band_avg) × M`, where `M` is the save's
own `<trade><prices buildpricefactor>` — and they take **no reputation
discount** (confirmed twice). `M` drifts between saves; read it per save.

## Two facts about offers

- **`allocation = stock + inbound + open buy amount` is a LOWER BOUND** [OBS],
  not an equality. A station bids only for what it can use: MAL-475 reads
  157,810 derived against a true 1,498,962 because its consumers are unbuilt.
  A model value *below* it is a real error; a model value *above* it proves
  nothing. It **is** saturated for production inputs that post a buy offer
  (median ratio 0.9999), so it pins the denominator there.
- **A full station withdraws its buy offer entirely** rather than pricing it at
  zero [OBS]. Offer coverage is 99.7 % below 90 % fill, 38 % at 100–110 %, 5 %
  above. The buy sample is censored at the top of the fill range, and a price
  history reading 0 means *no offer*.

## How well it fits

Save `save_id` 70, 7,109 main-sequence offers, with the role/side offsets and
`m = 1`:

| population | n | MAD | \|residual\| > 0.25 |
|---|---:|---:|---:|
| rations (buy only) | 2,361 | **0.0015** | 0.04 % |
| supplier side | 1,704 | 0.0125 | 7.69 % |
| production inputs (buy only) | 3,024 | 0.0714 | 8.63 % |
| condensate | 16 | 0.0053 | 0.00 % |
| **all** | **7,109** | **0.0141** | **5.54 %** |

Rations are the tightest law found anywhere in this project — tighter than the
storage allocation model that feeds it.

## How to score a change to this model

Two constraints, both learned the hard way:

1. **Fit shapes on BIN MEDIANS with equal weight per bin, never per-offer MAE.**
   Per-offer error is dominated by the crowded middle of the curve, where a
   straight line and a cosine are indistinguishable; it will report a clamped
   line as a good fit. The ends discriminate and they hold few offers. This
   mistake produced a wrong "piecewise linear, near-linear with knees"
   conclusion that had to be retracted.
2. **Score every candidate against the whole population before accepting it.**
   A rule that reproduces one station and degrades the save-wide fit is
   over-fitting. A starving-workforce gate reproduced EIJ-609's six wares
   exactly and was worse save-wide under every definition tried.

## Rejected — do not re-test without new evidence

| candidate | how it died |
|---|---|
| clamped linear supply curve | bin RMSE 0.1207 vs the cosine's 0.0124 |
| "near-linear with knees" | artifact of per-offer MAE scoring; retracted |
| sell side as a power law `1 − 2(f/0.79)^1.48` | predicts the floor at fill 0.79; the 0.55–0.98 region holds 135 offers of which only 8 are at the floor |
| sell side as a warped cosine `cos(π(f/1.06)^0.89)` | bin RMSE 0.0144 against the shift's 0.0087, with two free parameters instead of one |
| per-ware sell-side offsets | composition artifact of each ware's median fill (corr +0.37) |
| price staleness / update lag | the `updatetradeoffers` timer exists (~65 s, 3,555 events over 1,804 stations) but corr(offset, time since update) = −0.08, and 65 s cannot accumulate the 0.78 h of throughput the largest offsets need |
| station `hacked=` state | 11 usable stations spanning −0.076 to +0.117; inconclusive |
| recipe properties driving the input offset | cycle time +0.13, input count +0.17, input value share +0.20, chain tier +0.11 — all weak, and all ware-level, which cannot explain a station constant |
| hours of cover instead of fill | median deviation 0.136 against fill's 0.068, and not monotone |
| owner faction | every faction with n ≥ 100 sits between −0.018 and −0.003 |

## Open questions

1. **What sets `m`.** The low-`m` corridor (247 offers, 232 stations, 28 wares)
   is the largest unexplained structure left. Claytronics being bimodal — same
   ware, two clusters — is the sharpest available test case, because whatever
   separates the clusters must be a station property.
2. **What the −0.039 per-station input offset physically is.** Confirmed as a
   station constant with a 0.78 h ceiling; two hypotheses killed.
3. **Whether the engine carries `m` or `a`.** They are interchangeable at a
   single fill, so only a cohort spanning several fills can separate them.
4. **`supplies`' 10 per-ware constants** (1.07–1.22× avg), source unidentified.
   Not the recipe input value, which gives 0.72–0.95.
5. **Yard pricing** (`k ≈ 2.6`), likely priced off outstanding build demand
   rather than stock.

## One-pager

```
price      = avg × (1 + Σ modifiers)
modifier   = s × spread          spread(+) = max/avg − 1
                                 spread(−) = 1 − min/avg
s          = cos(π · clamp(u/1.095, 0, 1))
u          = fill/m + a
fill       = (stock + inbound − outbound) / allocation

a  = +0.053  station posts a sell offer for the ware
     −0.039  buy-only production input   (a per-station constant)
     +0.006  buy-only ration
m  =  1      almost always; 0.035 at Tidebreak, ~0.10 computronicsubstrate

then, at display time only:  × (1 − reputation tier% − event%)
and the panel rounds its percentages UP.

NOT this model: lockavgprice (avg), supplies (10 constants), shady
(1.055 × max), build storages (band max), yards (k ≈ 2.6), player (manual),
deployables (recipe × buildpricefactor, no rep discount).
```
