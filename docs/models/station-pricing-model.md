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

## The closed form

One station, one ware, everything substituted. `stock` is the only variable;
`m` and `a` are the two parameters that vary by population.

```
                ⎧  avg + s · (max − avg)          if s ≥ 0
  price   =     ⎨
                ⎩  avg + s · (avg − min)          if s < 0

  s       = cos( π · clamp( (fill/m + a) / 1.095, 0, 1 ) )

  fill    = (stock + undelivered inbound − committed outbound) / allocation
```

Branchless, if you prefer one line:

```
  price = avg + max(s, 0) · (max − avg) + min(s, 0) · (avg − min)
```

The two branches exist only because **40 of 1,891 wares have asymmetric bands**
(ore is −14 % / +16 %). For the other 1,851 the whole thing collapses to a
single multiply:

```
  price = avg · (1 + spread · s)              spread = max/avg − 1
```

So the model is: **turn stock into an angle, take its cosine, and interpolate
from the band average out to whichever edge that cosine points at.**

**Checked against the two readings the game states outright** [UI], UDX-946:

| ware | band (min / avg / max) | `s` | closed form | observed |
|---|---|---:|---:|---:|
| ore (buying) | 43 / 50 / 58 | +0.4125 | **53.30** | 53.30 |
| refined metals (selling) | 89 / 148 / 207 | −0.9708 | **90.72** | 90.72 |

Everything below unpacks that expression and says where each parameter comes
from.

## Unpacked

```
price   = avg × (1 + Σ modifiers)

supply/demand modifier = s × spread(sign of s)

  s     = cos(π · clamp(u / S, 0, 1))              S = 1.095
  u     = fill / m + a
  fill  = (stock + undelivered inbound − committed outbound) / allocation

  spread(+) = price_max/avg − 1        spread(−) = 1 − price_min/avg
```

The supply/demand term is the only modifier that moves with the station's
state; the rest are flat adjustments applied on top (§ The other modifiers).
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

### The price target `m` — a 5-million-credit cap

`m` is **not a free parameter and not a cohort constant**. The price target is
the storage allocation capped at a fixed credit value [OBS]:

```
target = min( allocation , V / ware.price_avg )        V = 5,000,000 Cr
m      = min( 1 , V / (price_avg × allocation) )
```

applied **only where the station posts a SELL offer** for the ware — the same
predicate that selects the `+0.053` offset. Equivalently: a supplier prices on
whichever runs out first, its storage or five million credits of that ware,
`u = max(net/allocation, net·price_avg/V) + a`.

`m = 1` for the bulk of the economy because most allocations are worth less
than 5 M Cr. It binds on **399 supplier offers over 331 stations, 29 wares and
17 factions** — two populations that look unrelated on a fill/`s` scatter until
you multiply by the band average: expensive wares in small quantities
(computronic substrate 8,280 Cr × 5,338 units = 44 M ⇒ `m` = 0.113; Protectyon
25,000 Cr × 5,000 = 125 M ⇒ `m` = 0.040) and cheap wares in enormous ones
(energy cells 16 Cr × 992,397 = 15.9 M ⇒ `m` = 0.315).

Bin RMSE on that population **0.3459 → 0.0285 with zero free parameters**;
`|res| > 0.25` on the whole supplier side **9.77 % → 1.48 %**. `V` is a value,
not a volume or a unit count: per-offer implied V on the Terran energy-cell
solar design is **5,002,645 Cr (IQR 5,001,555–5,007,379, n = 20)**, while
normalising on `price_min`/`price_max` loosens the fit 3–6× and on ware volume
gives no constant at all. Full derivation:
[../reports/price-categories-2026-07-29.md](../reports/price-categories-2026-07-29.md).

After the cap there is **no residual cohort structure in `m`**: the mean
within-group IQR of implied `m` is 0.0281 pooled, and no grouping tried — ware,
faction, sector, design, module count, transport pool, allocation-hours —
beats it. The per-(ware, role) "constants" previously listed here
(computronicsubstrate 0.10, claytronics 0.56 bimodal, siliconwafers 0.60) were
`5 M / (avg × that design's allocation)`; claytronics collapses from IQR/median
0.95 to **0.014**.

**`m` and `a` trade off at any single fill** — the decomposition `u = fill/m + a`
is a convention, not a derived fact. That trade-off is why `V` fits best at
5.05–5.10 M with `a` fixed at the rule value while the one cohort with a
verified allocation and a wide fill range returns 5.0026 M; it is also why
Tidebreak's target reads 200 (cap, zero parameters) against E-018's 173.1 (two
free parameters). Which of the two the engine carries is **[INF]** and open.

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

**Worked example [UI]** — UDX-946 (ARG Ore Refinery I, The Reach), the same
station the next section works end to end:

| ware | panel | panel price | check |
|---|---|---:|---|
| refined metals (sell) | High Supply −38.9 %, Prized Investor −9.1 %, Total −48.0 % | 76.82 | 148 × 0.520 = 76.96 |
| ore (buy) | High Demand +6.6 % | 53.30 | 50 × 1.066 = **53.30 exact** |

The panel reading was taken at a slightly earlier moment than the snapshot used
below, so its refined-metals offer was 90.72 where the current save reads 90.33
— the station's stock ticks. Reputation applies to the panel price only.

## A worked example, end to end — UDX-946

ARG Ore Refinery I, The Reach. Argon, 452 workforce. Chosen because the game
prints its price decomposition on the trade panel, so every step can be checked
against something the engine states rather than something we fitted.

**The station.** 2 × `prod_gen_refinedmetals` (225 workers each), 2 ×
`storage_arg_m_container` (250,000 m³ each), 1 × `storage_arg_s_solid`
(100,000 m³), 2 habitats. The production modules report
`<efficiency product="1.43">`.

### Step 1 — throughput, from the recipe

`refinedmetals/default`: 150 s, amount 88, inputs 90 energy cells + 240 ore.

```
output  refinedmetals = floor(88 × 1.43) / 150 × 3600 × 2 modules
                      = floor(125.84) = 125 → 125/150 × 3600 × 2 =  6,000 /h
input   energycells   =        90     / 150 × 3600 × 2          =  4,320 /h
input   ore           =       240     / 150 × 3600 × 2          = 11,520 /h
```

Both rules from [station-storage-model.md](station-storage-model.md) are load
bearing here: the output is multiplied by `efficiency` **and floored per
cycle** (125.84 → 125), while the inputs stay at the **base** recipe rate with
no efficiency applied at all. Rations come from workforce, not recipes:
1,012.5 food rations/h and 607.5 medical supplies/h.

### Step 2 — the equal-hours split, per pool

**Container pool** — capacity 2 × 250,000 = 500,000 m³. Rations take their 4 h
buffer off the top first:

```
food_volume = (1,012.5 × 4) × 1  +  (607.5 × 4) × 2   =  4,050 + 4,860 = 8,910 m³
Σ throughput×volume = 4,320 × 1 (energy) + 6,000 × 14 (refined metals) = 88,320
T = (500,000 − 8,910) / 88,320 = 5.5603 h
```

```
refinedmetals max = 6,000 × 5.5603 = 33,362.09
energycells   max = 4,320 × 5.5603 = 24,020.71
```

**Solid pool** — capacity 100,000 m³, one ware in it:

```
T = 100,000 / (11,520 × 10) = 0.8681 h      ore max = 11,520 × 0.8681 = 10,000
```

Note how different the two pools are: this refinery holds **5.6 hours** of
refined metals and **52 minutes** of ore. That asymmetry is the whole reason
allocation has to be computed per pool rather than per station.

### Step 3 — fill

Refined metals: 31,759 in cargo, nothing pending either way.

```
fill = 31,759 / 33,362.09 = 0.9519
```

### Step 4 — which `a`

The station posts a **sell** offer for refined metals, so it takes the supplier
offset `a = +0.053` — not because refined metals is an "output", but because it
is the side the station is on for that ware.

### Step 5 — the closed form

```
u     = 0.9519 + 0.053                      = 1.0049
s     = cos(π · clamp(1.0049/1.095, 0, 1))  = cos(π × 0.9177) = −0.9668
price = 148 + (−0.9668) × (148 − 89)        = 90.96
```

| | value |
|---|---:|
| model | **90.96** |
| the save's offer price | **90.33** |
| difference | +0.63 Cr = **0.0106 of a band** |

That sits inside the supplier population's MAD of 0.0125, i.e. this station is
an ordinary member of the population rather than an especially good fit. On the
trade panel the same offer appears as *High Supply −38.9 %, Prized Investor
−9.1 %, Total −48.0 %* — the reputation term is applied at display time and is
not in the 90.33.

### The same station's ore, which does NOT fit — and why that is the open question

Run the identical procedure on the ore buy and it fails badly:

```
net   = 8,100 stock + 1,176 inbound = 9,276
fill  = 9,276 / 10,000 = 0.9276
u     = 0.9276 − 0.039 = 0.8886
s     = cos(π × 0.8115) = −0.8297   →   price 44.19
```

The save says **53.30**, and the panel says *High Demand +6.6 %* — which is
`50 × 1.066` exactly. A station 93 % full of ore is being told it has high
demand.

Inverting gives `s = +0.4125`, an implied fill of 0.3993, and therefore

```
m = 0.9276 / 0.3993 = 2.32
```

So UDX-946 prices ore over a target **2.3× its storage allocation** — the
opposite tail from Tidebreak's 0.035, and consistent with the fact that its
solid pool holds under an hour of ore. The cosine, the span and the offset are
all unchanged; only the denominator moved.

**This is the model's honest edge.** For most of the economy `m = 1` and the
chain above lands within a hundredth of a band. Where the storage allocation is
small relative to the flow through it, `m` departs from 1 in both directions,
and what sets it is [the open question](#open-questions).

## Populations that do NOT use this model

Each is a separate book, confirmed by measurement rather than assumed [OBS]:

| book | n | behaviour |
|---|---:|---|
| `lockavgprice` whitelist | 1,175 | pegged at band **average** regardless of stock; sell = avg exactly, buy = avg − 1 |
| `supplies` (self-supply) | 1,309 | a fixed per-ware multiple of avg — **10 distinct constants**, 1.07–1.22× |
| `shady` (black market) | 3,273 | **two tiers, disjoint by station** (E-112): 2,897 offers over 727 stations at median 1.042 × band max, and 376 over 96 stations at exactly **2.750 × band avg**; no fill dependence either way. Opened per station by a `shadyguy` post; what sets a station's tier is unknown |
| build storages | 1,771 | hold **no allocation** (0 of 1,771), so no fill coordinate exists. 63 % sit at band max to the cent and 10.6 % *above* it; the unclamped rest do move with stock against `stock + inbound + open buy amount` (corr −0.79) but hold `s = +1` flat to fill ≈ 0.41 and are **not** on the cosine (bin RMSE 0.44–0.50). E-118 |
| yards / wharfs / docks | 701 | same family, different exponent (`k ≈ 2.6`); run much fuller, median fill 76 % vs 54 % |
| player-owned | 54 | manual thresholds — `price_setting` and `ware_limit`, off-model by design |

`supplies` and `yard` are characterised but **not explained**. The rest are
understood. All six were re-admitted as candidates and re-tested on 2026-07-29
against the value cap; only the seventh, the old `narrow price span (output)`
cohort (computronicsubstrate / claytronics / siliconwafers, 114 offers),
turned out **not** to be a separate book — it is ordinary supplier pricing with
the 5 M cap binding, bin RMSE 0.2382 → 0.0136. The cap was explicitly rejected
for yards (bin RMSE 0.3355 → 0.6310 on the 202 offers where it would bind) and
for buy-only production inputs (0.1058 → 0.2078 on 147).

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

Save `save_id` 70, 7,227 main-sequence offers (the 114 old narrow-span ones
re-admitted), with the role/side offsets. MAD is the *median* absolute
residual. `m = 1` is the pre-2026-07-29 model; `cap` is `m = min(1, 5 M /
(price_avg × allocation))` on the supplier side.

| population | n | MAD `m=1` | MAD cap | \|res\|>0.25 `m=1` | \|res\|>0.25 cap |
|---|---:|---:|---:|---:|---:|
| rations (buy only) | 2,372 | **0.0015** | **0.0015** | 0.04 % | 0.04 % |
| supplier side | 1,821 | 0.0129 | 0.0130 | 9.77 % | **1.48 %** |
| …of which the cap binds | 399 | 0.1770 | **0.0146** | 40.85 % | **3.01 %** |
| production inputs (buy only) | 3,044 | 0.0717 | 0.0717 | 8.64 % | 8.64 % |
| **all** | **7,227** | **0.0143** | **0.0141** | **6.12 %** | **4.03 %** |

Bin RMSE on the binding population: **0.3459 → 0.0285** over 16 equal-count
bins. The save-wide *bin-median* statistic barely moves (0.0063 → 0.0066)
because 24 bins of ~300 offers cannot see 399 of them however wrong they are —
which is exactly why `m = 1` also scored 0.0063 there while scoring 0.283 on
the offers it got wrong. Score a change to `m` on the population it binds on
**and** on the whole-population tail fraction, never on the save-wide bin
median alone.

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
| `m` as a per-(ware, role) game constant | claytronics output reads 0.109 and 1.214 for the *same* ware and role; `m × allocation` is flat at 2,480–2,525 across its 48 sellers (E-024) |
| the cap as a *volume* cap | `target × ware.volume` spans 31,000–609,000 m³ across cohorts sharing a value cap to 1 % |
| the cap normalising on `price_min` / `price_max` | implied-cap relative IQR 0.349 / 0.186 against `price_avg`'s 0.056 |
| the cap applying to buy-only inputs or to yards | bin RMSE 0.1058 → 0.2078 (147 inputs) and 0.3355 → 0.6310 (202 yard offers) where it would bind |
| the corridor as a faction / sector / design / module-count property | every such grouping has a *higher* within-group IQR of `m` than pooling, on both bases |

## Open questions

1. **Is `V` exactly 5,000,000 Cr?** The binding population optimises at
   5.05–5.10 M with `a` fixed; the one cohort with a verified allocation and a
   wide fill range returns 5.0026 M. `V` and `a` trade off, so it needs one
   station read at two well-separated stock levels (E-116).
2. **What the −0.039 per-station input offset physically is.** Confirmed as a
   station constant with a 0.78 h ceiling; two hypotheses killed.
3. **Whether the engine carries `m` or `a`.** They are interchangeable at a
   single fill, so only a cohort spanning several fills can separate them.
   Tidebreak is the open case: the cap says 200 units with no free parameters,
   E-018's two-parameter solve said 173.1 (E-117).
4. **`supplies`' 10 per-ware constants** (1.07–1.22× avg), source unidentified.
   Not the recipe input value, which gives 0.72–0.95.
5. **Yard pricing** (`k ≈ 2.6`), likely priced off outstanding build demand
   rather than stock.

## One-pager

```
price      = avg + max(s,0)·(max − avg) + min(s,0)·(avg − min)
             ( = avg · (1 + spread·s) for the 1,851 symmetric-band wares )
s          = cos(π · clamp((fill/m + a) / 1.095, 0, 1))
fill       = (stock + inbound − outbound) / allocation

a  = +0.053  station posts a sell offer for the ware
     −0.039  buy-only production input   (a per-station constant)
     +0.006  buy-only ration
m  = min(1, 5,000,000 Cr / (price_avg x allocation))     supplier side only
     ( = 1 almost always; 0.04 Tidebreak, 0.11 computronicsubstrate,
       0.32 the 992k-unit energy-cell solar design )

then, at display time only:  × (1 − reputation tier% − event%)
and the panel rounds its percentages UP.

NOT this model: lockavgprice (avg), supplies (10 constants), shady
(two tiers: 1.042 × max, or 2.750 × avg), build storages (band max),
yards (k ≈ 2.6), player (manual),
deployables (recipe × buildpricefactor, no rep discount).
```
