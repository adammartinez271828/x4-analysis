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

**Revised 2026-07-30** against the eight Phase-2 reports of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md) — the
`supplies` book, the yard book, the cap's scope, `V`'s structure and the offset
family all moved — and against the first implementation.

**The model now exists in code: `src/x4analyzer/analysis/pricing.py`.** It
implements this document — the closed form, the book classification, and a
bin-median scoring harness that enforces the rules in § How to score a change —
and it is *research-grade*: no widget, no pipeline wiring, nothing else in the
package imports it. Where this document and the module disagree about a
*number*, the module is the one that was scored; where they disagree about a
*rule*, that is a bug in one of them and the register (E-…) is the tiebreak.
Two conventions the module carries that this document should be read with:
every prediction is labelled `law`, `descriptive` or `none`, and residuals are
scored in **band units** (`(observed − predicted)` over the half-spread on the
observed side), never in `u` — near `s = ±1` the cosine is flat and a four-cent
price difference manufactures a `u` residual of 2–5.

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
| host carries a built `buildmodule` (yard) | **−0.202** | 61 stations | 0.0007 (MAD of the per-station median) |

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
ratio 0.9999. **−0.039 is only the population default**; the real number ranges
over roughly 0 to −0.8, so any per-station work should measure it rather than
assume it (`pricing.station_input_offsets()` does).

**Three things it is now known NOT to be** [OBS, 2026-07-30]:

- **Not a per-module reserve of goods** (E-011 FALSIFIED). It is a *fill
  fraction*: NVF-801 posts twelve inputs at −0.198…−0.214 over allocations from
  210 to 366,112 units, which would need the same modules to hold back 41.7 and
  73,500 units — a factor of 1,764. 169 of 909 stations carry a **positive**
  constant, which no reserve can produce. A reserve denominated in *hours of
  consumption* is algebraically indistinguishable from the fill offset and is
  not refuted — but it is not what E-011 claimed, and it is in the rejected
  table so it is not re-tested as if new.
- **Not stock-dependent.** Over 13 epochs and 15,319 s the implied `a` is flat
  to a median spread of **0.0059**, 227 of 241 epochs within 0.01 of their
  series median, while net positions move 10–50 % of allocation. CCN-497 holds
  graphene at −0.3884…−0.3911 across all 12 unclamped epochs while its price
  runs 233.00 → 158.98.
- **Not shared with rations** (E-015 CONFIRMED, role/predicate-keyed). Over the
  829 stations posting both, ration `a` sits at +0.0066 (MAD 0.0021) while the
  same stations' inputs range −0.97 to +0.54; on the 445 discriminating
  stations the role rule scores bin-median 0.0045 against 0.1074 for "rations
  take the station's constant".

### The price target `m` — a 5-million-credit cap

`m` is **not a free parameter and not a cohort constant**. The price target is
the storage allocation capped at a fixed credit value [OBS]:

```
target = min( allocation , V / ware.price_avg )        V = 5,000,000 Cr
m      = min( 1 , V / (price_avg × allocation) )
```

applied **only where the station posts a SELL offer** for the ware — the same
predicate that selects the `+0.053` offset. The station need **not** produce
the ware: 23 offers over 12 producing stations reselling a ware they buy cap
cleanly (median |res| 0.1151 → 0.0142). Whether *non*-producers cap is open and
contradictory — VOM-540 caps, DHI-588 (in-game-verified allocations) does not,
and no single V fits both (E-115 § scope, register § Contradictions item 8). Equivalently: a supplier prices on
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
is a convention, not a derived fact. That trade-off is why `V` fitted best at
5.05–5.10 M with `a` fixed at the pooled rule value while the one cohort with
a verified allocation and a wide fill range returned 5.0026 M — resolved
2026-07-31 by the uncapped same-ware control: **V = 5.00 M with the EC-cohort
a = 0.0483** (E-116 CONFIRMED, open question 1). For Tidebreak specifically —
200 units (cap, zero parameters) against E-018's fitted 173.1 — the m-vs-a
question is still open and is reading R1 (E-117).

#### `V` is one global constant — of an unsettled value [OBS, 2026-07-30]

Two results, and they point in opposite directions about how done this is.

**No cohort structure, and that is settled.** Solving `V` per station at fixed
`a` over 153 multi-epoch trajectories gives **IQR/median 0.008**; ware medians
spread only 5.025–5.060 M and faction medians 5.030–5.080 M, and **nothing
beats pooling** (E-130). So "is the cap per-design or per-faction" is closed,
and any one well-conditioned capped station is as good as a cohort.

**The absolute value is not, and 13 epochs did not break it.** `V` and the
supplier offset `a` lie on an exact ridge of slope ≈ **+0.0009 in `a` per +1 %
in `V`** — the corpus ridge and the single-snapshot ridge trace the same line
to within one grid cell — so per-station `V` intervals with `a` free are ~23 %
wide. Conditional on `a`, `V` is pinned to ±0.1 %: at `a = 0.048` the two
in-game-anchored solar plants both return 5,001,8xx Cr as 13-epoch medians; at
`a = 0.053` they return 5.043–5.057 M. The non-binding suppliers, which carry
no `V` at all, prefer `a = 0.052` and hence `V ≈ 5.05 M` — but their `a` is
measured *through* the storage-allocation model, so a 1 % bias there would move
it by the whole disputed amount. **Use `V = 5,000,000` and treat both numbers
as parameters** (which is what `pricing.py` does, with `a = 0.053`). E-116 —
**settled 2026-07-31**: the uncapped same-ware control pins `a = 0.0483` and
breaks the ridge (see § Open questions item 1), and the constant is in the
game files verbatim: `libraries/parameters.xml` `<economy><prices><product
factor="5000000"/>`.

#### Above the capped target: the cap holds, unless the station eats the ware

Two refinements to the cap's scope, both from the whole >5 M Cr population at
once [OBS, 2026-07-30]:

**The cap is confirmed ABOVE the target, not only below it.** Of the 49
saturated NPC supplier offers on snapshot 71, the **30 the station does not
itself consume sit at exactly the band minimum**, bin-median error 0.0000 in
all seven bins, where reverting to the allocation curve scores 0.4245. That
kills the leading alternative scope rule — "the cap applies only while
net ≤ target" — whose falsifiers are offers at fill 0.51–0.94 already past the
capped target (CAC-761, MBP-961, PAC-481, TFH-220, XXF-947 …).

**But a ware the station itself CONSUMES does not clamp there.** Above the
capped target it leaves the supplier book for the consumer book — target = the
storage allocation, offset = that station's own input constant. The split on
those 49 offers is perfect with **no tuned parameter**: 0/19 self-consumed at
the band minimum, 30/30 non-self-consumed at it. *Below* the target the
exemption does not apply — all 51 self-consumed sub-target offers fit the
**capped** curve (0.008–0.019 of a half-spread) — which is why a blanket
exemption degrades that cohort (0.0144 → 0.0303) while the above-target-only
form is neutral everywhere else. *Self-consumed* means: an input to one of the
station's own production recipes, **or** a build resource while it carries a
built `buildmodule*`, **or** a ration of a race present in its workforce.

**HYPOTHESIS on the price form, not on the split.** The exempted offers do not
land on the allocation curve at `+0.053` either; solved individually they want
a negative `a` (energy cells −0.108…−0.153, scrap metal −0.015…−0.071, silicon
−0.162, hull parts −0.208). The one station where that is independently
checkable settles it: **ULG-519** reads −0.202/−0.203/−0.202 on its production
inputs and −0.208 on its saturated hull-parts sell, and predicting from
`T = allocation, a = −0.203` lands within **0.014** of the observation against
+0.348 (allocation at +0.053) and +0.355 (capped). The eight Avarice scavengers
buy no inputs at all, so their constant is unobservable — the rule predicts
*that* their price stays off the floor, not *where* it lands, and it has no
closed form until the per-station input constant is modelled. E-132/E-133.

## The other modifiers

**Reputation discount, applied at display time [UI].** `player price =
economy price × (1 − tier% − event%)`. Tiers: Known Associate 5 % (relation
≥ 0.01), Prized Investor 15 % (≥ 0.1), Partnership Agreement 25 % (≥ 1.0).
The savegame's offer price does **not** include it: UDX-946's refined-metals
sell offer reads −38.70 % against a panel showing −38.9 % supply plus −9.1 %
reputation. **Resolved 2026-07-31: the tiers are real** — the save stores them
as md-created records on the *player* component, one per faction
(`md_relation_discount_1/2/3`, amounts 0.05/0.15/0.25) — **and the base the
tier multiplies is the band WIDTH, not the price**: `discount = tier ×
(price_max − price_min)`, displayed as a % of avg (which is why the shown
percentage varies per ware), applied against the player on buys as "Discount
offset". Twelve same-day panels reproduce it to the cent across two factions,
two tiers, ten wares, both sides and both books (E-142). One recorded panel
(UDX-946, −9.1 %) instead matches `tier × price` and awaits a decisive
re-read: the width law predicts a stock-independent −12.0 % there.

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
| `shady` (black market) | 3,273 | **two tiers, disjoint by station** (E-112): 2,897 offers over 727 stations at median 1.042 × band max, and 376 over 96 stations at exactly **2.750 × band avg**; no fill dependence either way. Opened per station by a `shadyguy` post. The tier is **mutable state**, and the only correlate is the workforce: fixed ⇒ unstaffed on 1,227 of 1,228 station-epochs, converse false (E-134). Not derivable from the save — classify it off the observed price |
| build storages | 1,771 | hold **no allocation** (0 of 1,771), so no fill coordinate exists. 63 % sit at band max to the cent and 10.6 % *above* it; the unclamped rest do move with stock but hold `s = +1` flat to a knee and are **not** on the cosine. Confirmed on an *independent* denominator (outstanding module-build BOM): free flat-then-line 0.0725 against the cosine's 0.3084, the warped cosine's 0.4261 and the clamped line's 0.2844. Take the knee as a **spread** — 0.41 / 0.50 / 0.57 on three denominators — not a value. E-118 |
| player-owned | 54 | manual thresholds — `price_setting` and `ware_limit`, off-model by design |

**Two former members of this table are back in the main sequence**
[OBS, 2026-07-30]:

- **`supplies` (self-supply)** is a *fixed point on the same cosine*:
  `price = (avg + max)/2`, i.e. **`s = +0.5` exactly** — `u = 0.3650` — with no
  parameters and no stock dependence. 15,345 offers over 13 saves, maximum
  deviation **0.00 Cr**. Its ten "per-ware constants" were `1 + spread/2`; the
  half-credit prices (53.50, 240.50, 1,520.50) are what a midpoint rule
  produces and a rounded constant does not. E-129.
- **Yards / wharfs / docks** are *the ordinary cosine on the storage
  allocation*, with a yard station constant `a ≈ −0.202` (rations still +0.006,
  sells still +0.053). Scored like for like against E-028's clamped power on
  the offer-derived proxy — one fitted parameter each, whole yard buy book
  n = 675, bin medians on a rule-independent x — the cosine wins by **27×**
  (0.0054 against 0.1483), and it *explains* the ~0.17 band floor at full fill
  that the power form leaves as an anomaly: at fill 1 the shifted cosine
  reaches only `s = cos(0.728π)`, band position 0.18. What is left unexplained
  is one cohort constant, which is the same open question as every other
  station's input constant. E-131.

**Book precedence matters and is measured.** Manual price settings first (not a
price book at all), then the **offer's own flags**, then the station's
whitelist, then the host's kind. Flags must outrank the whitelist: 13 offers on
snapshot 71 are both `supplies`-flagged and `lockavgprice`-listed and all 13
price at the midpoint, not at `avg − 1` — booking the whitelist first puts them
in the wrong book by 0.5–0.75 band units.

The remaining books were re-admitted as candidates and re-tested on 2026-07-29
against the value cap; the old `narrow price span (output)` cohort
(computronicsubstrate / claytronics / siliconwafers, 114 offers) turned out
**not** to be a separate book — it is ordinary supplier pricing with the 5 M cap
binding, bin RMSE 0.2382 → 0.0136. The cap was explicitly rejected for yards
(bin RMSE 0.3355 → 0.6310 on the 202 offers where it would bind) and for
buy-only production inputs (0.1058 → 0.2078 on 147); the yard rejection stands
independently of E-131, which changes the yard's *curve*, not its denominator.

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

**Re-scored on snapshot 71 by `analysis/pricing.py` (2026-07-30).** Where these
supersede the save-70 figures above, they are the numbers to quote — same
discipline, current snapshot, and reproduced by an implementation rather than a
scratch script. `lockavgprice` and `supplies` are exact **to 1e-9 per offer**,
so they carry no error bar at all. The supplier population's binding cohort
reads bin RMSE 0.0059 at `(V, a) = (5.00 M, 0.048)` and 0.0089 at
`(5.05 M, 0.053)`; the 1,349 non-binding suppliers read 0.0127 and 0.0077
respectively; all 1,715 suppliers 0.0094 and 0.0078. Yards: 0.0054 on the
cosine against 0.1483 on the power. Two scoring rules the harness enforces and
that any re-run must too: **exclude `lockavgprice` pairs from the supplier
population** — leaving them in inflates the binding bin RMSE from 0.0145 to
0.43, which is what a careless run reports — and drop clamped offers
(`|s| ≥ 1`, 9 % of station-epochs), which sit on a band edge and carry no
information about the fill coordinate.

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
| the input offset as a per-module **reserve of units** | it is a fill fraction, not a stock of goods: NVF-801 shares one `a` across allocations differing 1,764×, 169 of 909 stations carry a positive offset, and it is flat to 0.006 over 13 epochs while stock moves 10–50 % (E-011) |
| the input offset as a reserve denominated in **hours of consumption** | **not refuted — and that is the point.** It is algebraically indistinguishable from the fill offset itself (the allocation is proportional to consumption rate), so it cannot be tested this way; it would still need a mechanism for the positive-`a` stations. Do not re-run the E-011 test expecting it to discriminate |
| yards priced off outstanding **build demand** (E-028's mechanism) | the demand was constructed and is a median 0 % / max 69 % of a yard's own allocation; on it, 10 of 16 bins degenerate to fill 1.000 spanning the whole band, bin RMSE 0.4355 against the proxy's 0.0792; and BOM swings at CV 0.511 across epochs while the allocation holds at CV 0.0107, with complete queue turnover in under 2,000 s |
| the yard book as a clamped power `1 − fill^k` (k ≈ 2.6) | a **shape artifact of unmodelled offsets**, not a family: once yard rations take +0.006 and yard sells +0.053, the ordinary cosine at `a = −0.202` beats it 27× on bin RMSE at equal parameter count and reproduces the 0.17 band floor the power form cannot (E-131) |
| the cap's scope as **net-position saturation** (cap only while net ≤ target) | ten falsifiers at fill 0.51–0.94 already past the capped target, all sitting at the band minimum where the allocation curve is off by up to a full half-spread: CAC-761, MBP-961, PAC-481, TFH-220, XXF-947, DRN-534, QFO-450, OHU-068, SZE-818, AOY-922 (E-133) |
| the cap's scope as a faction / design / sector / tide-phase property | every grouping contains both cohorts — scavenger IRD-672 caps while eight other scavengers do not, kaori BPR-268 caps while kaori DHI-588 does not, `station_gen_factory_base_01_macro` is the modal macro on both sides, cluster_500 holds four cappers and eight non-cappers; across 13 epochs the scavengers' prices move only with their own net, no periodicity |
| the "1.21–1.30× scavenger storage scale error" | **withdrawn, and by freeing `a`, not by changing the storage model.** KWC-232's allocation is player-verified at 1,833,000 against a modelled 1,833,247; corpus 2-parameter solves on the series with leverage return `T ≈ the modelled allocation` with a negative offset (NDE-080 1.014×, CGW-678 0.993×, NDE-080 scrap 1.000×). The 1.2–1.3× figures survive only where net varies 0–3 % and `T` and `a` are not separable |
| build-storage price as a cosine, warped cosine, clamped line, or the yard's power | on an **independent** module-BOM denominator: 0.3084 / 0.4261 / 0.2844 / 0.1629 against flat-then-line's 0.0725 (E-118). Same ordering on the self-referential denominator, which is what shows it was never an artifact of `amount` appearing on both sides |
| `u`-space least squares for the (V, a) solve | heteroscedastic near `s = ±1`: it manufactured `V ≈ 3.8–4.5 M` on the low-fill solar plants out of 0.06 Cr price deviations. Score in band units |
| `(V, a) = (5.00 M, 0.046)` as a save-wide rule | best on the capped cohort (0.0058) and one of the worst save-wide (0.0127 against a 0.0077 baseline) — it buys 344 offers by degrading the 1,349 that carry no cap at all. Over-fitting |

## Open questions

1. ~~**Is `V` exactly 5,000,000 Cr?**~~ **SETTLED 2026-07-31 (E-116
   CONFIRMED): V = 5,000,000 Cr.** The ridge was broken offline by an
   *uncapped same-ware control*: 26 uncapped energy-cell sellers (allocations
   250k–296k, seven factions, 329 station-epochs) pin the supplier offset at
   **a = +0.0483 (IQR 0.0480–0.0486)** against their known allocations, which
   excludes the pooled a = 0.052 behind the 5.05 M optimum (a composition
   artifact). With `a` pinned, the capped anchors return implied V =
   5,004,974 / 5,004,155 (13-epoch medians, IQR ≈ ±0.1 %) — 5.05 M refuted at
   ~10× the IQR; the +0.1 % residual is inside the V↔a coupling. No reading
   was needed (the old R6 is dissolved).
2. **What the per-station input offset physically is.** Confirmed as a station
   constant with a 0.78 h ceiling; **four** hypotheses now killed (staleness,
   recipe properties, `hacked=`, per-module unit reserve), and the
   hours-of-consumption form is untestable by the same route. This is the
   model's biggest unexplained parameter, and it is now load-bearing in three
   places: the consumer book, the yard constant (−0.202) and the
   self-consumption exemption.
3. **Whether the engine carries `m` or `a`.** They are interchangeable at a
   single fill, so only a cohort spanning several fills can separate them.
   Tidebreak is the open case: the cap says 200 units with no free parameters,
   E-018's two-parameter solve said 173.1 (E-117).
4. **Do non-producers cap?** Narrowed from a cohort to **DHI-588 alone** — two
   offers, on in-game-verified allocations, preferring the allocation over the
   cap by 0.255 and 0.141 half-spreads, with no self-consumption to explain it
   — against VOM-540, which caps. Recorded as register contradiction (8), not
   resolved.
5. **Where an exempted (self-consumed) supplier offer actually lands.** The
   split is exact; the price form is confirmed only where the station's input
   constant is observable (ULG-519), and the eight Avarice scavengers buy no
   inputs at all (E-132).
6. **What the 949 fully-built build storages are buying for.** The
   whole-installed-loadout replacement BOM tracks the proxy at r = 0.887 over
   898 offers (median ratio 1.61), which is a hypothesis and not a model — the
   *missing* loadout cannot be computed from the save alone because L-size
   `<upgrades><groups>` entries are not 1:1 with installed turrets (E-135).
7. **What sets a `shady` station's tier.** Unstaffed is necessary and not
   sufficient, and the tier is mutable state that the save gives no other
   handle on (E-134).

## One-pager

```
price      = avg + max(s,0)·(max − avg) + min(s,0)·(avg − min)
             ( = avg · (1 + spread·s) for the 1,851 symmetric-band wares )
s          = cos(π · clamp((fill/m + a) / 1.095, 0, 1))
fill       = (stock + inbound − outbound) / allocation

a  = +0.053  station posts a sell offer for the ware
     −0.039  buy-only production input   (a PER-STATION constant, 0…−0.8;
                                          −0.039 is only the population default)
     +0.006  buy-only ration
     −0.202  host carries a built buildmodule (yards; rations and sells on
                                          that host still take +0.006/+0.053)
m  = min(1, 5,000,000 Cr / (price_avg x allocation))     supplier side only
     ( = 1 almost always; 0.04 Tidebreak, 0.11 computronicsubstrate,
       0.32 the 992k-unit energy-cell solar design )
     V has NO per-station/ware/faction structure, but V and a trade off on a
     ridge: (5.00M, 0.048) and (5.05M, 0.053) are indistinguishable offline.

exemption: above the capped target, a ware the station ITSELF CONSUMES
     (own recipe input | build resource | ration of a race it employs)
     reverts to T = allocation with that station's own input constant,
     instead of clamping at the band minimum.   Below the target: no exemption.

then, at display time only:  × (1 − reputation tier% − event%)
and the panel rounds its percentages UP.

ALSO this model, as fixed points / offsets on the same cosine:
     supplies  s = +0.5 exactly   ( = (avg+max)/2, no parameters )
     yards     the ordinary cosine at a = −0.202  (NOT a clamped power)

NOT this model: lockavgprice (avg; but offer FLAGS outrank the whitelist),
shady (two mutable tiers: 1.042 × max, or 2.750 × avg — fixed ⇒ unstaffed),
build storages (no allocation at all; flat at band max to a knee ~0.4–0.6,
then falls — descriptive, not a law), player (manual),
deployables (recipe × buildpricefactor, no rep discount).

book precedence: manual price setting → offer flags → station whitelist
                 → host kind (buildstorage, yard) → main sequence
```
