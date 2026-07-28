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

Spread is measured as Σ|band_position − clamp(1 − fill/100)| over the offers
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

Real behavior. Median residual **+0.167** — they pay a systematic premium over
the stock-driven price — and the curve shape genuinely differs: the implied
exponent on `1 − band = fill^k` is **k ≈ 2.38** against 1.00 everywhere else.
This is the only category where the *shape*, not just the level, is different.
The proxy allocation is not the cause: `stock + buy_amount` reproduces the
proxy exactly by construction (100 % within 5 %), so the x-axis is not in
question here.

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
`1 − band = a × fill^k`. The evidence says `a` is not a free parameter at all,
so the non-goal is moot rather than deferred, and saying so changes the model.

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

With that exact denominator, fitting `1 − band = fill^k` over the main-sequence
buys gives **k = 1.00** as the MAD-minimising exponent (MAD 0.0414; searched
k = 0.60…2.98 in steps of 0.02 — an interior minimum, with 0.0537 at k = 0.90
and 0.0554 at k = 1.50), and
`a = 1.000` — the floor arrives at 100 % fill, not somewhere between 8.6 % and
82.3 %. The at-floor population (band < 0.02, n = 334) sits at a median fill of
**97.4 %**; the at-ceiling population (band > 0.98, n = 1,092) at **0.0 %**.

So the reported k ≈ 1.53–1.64 and the wandering `a` are artifacts of two
things: fitting through clamped points (a cohort that saturates at both ends
flattens the fitted slope arbitrarily), and using the *modelled* allocation,
whose pool-split error on multi-ware stations is the dispersion being read as
"scale". `a` is therefore **not a category discriminator** — with one
exception, which is worth the whole exercise: the yard category really does
have k ≈ 2.38, and that is now the sharpest available discriminator for it.

Residual claim after all this: main-sequence buys still sit **+0.026 band**
above the linear law with the exact denominator (MAD 0.041), and the excess is
hump-shaped in fill: +0.000 at 0–10 %, **+0.114 at 10–25 %**, +0.106 at
25–50 %, +0.029 at 50–75 %, −0.001 above 75 % (n = 920 / 344 / 761 / 1,450 /
1,859). Rations show the same hump on their own. This is real curvature in the
engine's price function, not an allocation artifact.

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
2. **Yard pricing (k ≈ 2.38, +0.167 level).** Yards likely price off outstanding
   build demand rather than stock, on the same clamped form but with the
   denominator being the funded order bill of materials rather than the
   allocation. *Validates:* an NPC wharf with a known order queue; compare
   `stock + amount` against Σ recipe of its queued ships. Falsified if k stays
   ≈ 2.38 with a demand denominator.
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
