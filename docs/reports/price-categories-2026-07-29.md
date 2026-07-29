# Station price cohorts: what sets `m` — 2026-07-29

Research only; no `src/` change. Measured on DB `save_id` 70 (resolved from
`current_save`), 15,602 trade offers. Verification: `uv run pytest -q` →
**247 passed**; `uv run python tests/readings.py` → **49/50 in-game readings**
(unchanged — nothing under `src/` was touched).

Machine-readable companion:
[price-categories-2026-07-29.csv](price-categories-2026-07-29.csv), one row per
(station, ware, side) with the cohort label, both denominators, the fitted
parameters and a confidence flag.

Coordinates are the ones
[station-pricing-model.md](../models/station-pricing-model.md) defines:
`s = cos(π·clamp(u/S,0,1))`, `u = fill/m + a`, `S = 1.095`, `fill = (stock +
inbound − outbound)/allocation`. `S`, the supplier offset `a = +0.053`, the
production-input offset `a = −0.039` and the ration offset `a = +0.006` are
taken as settled and are not re-derived. The baseline reproduces the model
doc's fit table exactly (rations median |res| 0.0015, supplier 0.0125,
production inputs 0.0717), which is what licenses everything below.

---

## Headline: the low-`m` corridor is a 5-million-credit cap on the price target

**The price target is not `m × allocation` with a per-cohort `m`. It is the
allocation capped at a fixed credit value:**

```
target = min( allocation , V / ware.price_avg )        V = 5,000,000 Cr
       — applied only where the station posts a SELL offer for the ware
```

Equivalently, and more usefully: a supplier prices on whichever runs out
first, its storage or five million credits of that ware.

```
u = max( net/allocation , net × price_avg / 5,000,000 ) + a
```

`m` is then not a free parameter at all. It is
`m = min(1, V / (price_avg × allocation))` — determined entirely by the ware's
band average and the station's own allocation, both of which are already known
from the storage model. **The corridor has zero free parameters.**

### Which stations and wares are in the corridor

Every supplier offer whose allocation is worth more than 5 M Cr — **399
offers, 331 stations, 29 wares, 17 factions**. What they share is *not* a ware,
a faction, a sector or a design: 392 of the 399 sit on the single generic
`station_gen_factory_base_01_macro`, the commonest station design in the save.
What they share is that **allocation × band average exceeds 5 M Cr**, which
happens for two different reasons:

- *expensive wares in small quantities* — computronic substrate (8,280 Cr,
  allocation 5,338 ⇒ 44 M Cr of allocation, `m = 0.113`), Protectyon
  (25,000 Cr, `m = 0.040`), claytronics, silicon carbide;
- *cheap wares in enormous quantities* — energy cells at 16 Cr but 992,397
  units of allocation ⇒ 15.9 M Cr, `m = 0.315`.

Those two groups look nothing alike on a fill/`s` scatter until you multiply by
the band average, which is why the corridor read as a mixture of unrelated
cohorts.

| ware | offers | stations | band avg | median allocation | median alloc. value | cap (units) | implied `m` |
|---|---:|---:|---:|---:|---:|---:|---:|
| condensate (Protectyon) | 2 | 1 | 25,000 | 5,000 | 125.0 M | 200 | **0.040** |
| computronicsubstrate | 22 | 22 | 8,280 | 5,338 | 44.2 M | 604 | **0.113** |
| khaakalloy | 4 | 4 | 1,400 | 15,274 | 21.4 M | 3,571 | 0.234 |
| energycells | 59 | 55 | 16 | 992,397 | 15.9 M | 312,500 | 0.315 |
| scrapmetal | 21 | 11 | 375 | 30,000 | 11.3 M | 13,333 | 0.444 |
| siliconcarbide | 15 | 15 | 1,414 | 7,149 | 10.1 M | 3,536 | 0.495 |
| refinedmetals | 14 | 13 | 148 | 61,629 | 9.1 M | 33,784 | 0.549 |
| microchips | 40 | 35 | 948 | 9,322 | 8.8 M | 5,274 | 0.567 |
| claytronics | 43 | 42 | 2,040 | 4,292 | 8.8 M | 2,451 | 0.571 |
| siliconwafers | 30 | 27 | 299 | 28,528 | 8.5 M | 16,722 | 0.586 |
| plasmaconductors | 18 | 18 | 1,026 | 8,321 | 8.5 M | 4,873 | 0.594 |
| hullparts | 35 | 35 | 209 | 39,321 | 8.2 M | 23,923 | 0.608 |
| graphene | 13 | 13 | 166 | 48,091 | 8.0 M | 30,120 | 0.626 |
| advancedcomposites | 6 | 6 | 540 | 14,341 | 7.7 M | 9,259 | 0.646 |
| teladianium | 6 | 6 | 202 | 36,268 | 7.3 M | 24,752 | 0.689 |
| antimattercells | 7 | 7 | 202 | 33,835 | 6.8 M | 24,752 | 0.732 |
| quantumtubes | 4 | 4 | 300 | 21,747 | 6.5 M | 16,667 | 0.769 |
| fieldcoils | 4 | 4 | 412 | 15,501 | 6.4 M | 12,136 | 0.784 |
| advancedelectronics | 18 | 18 | 1,014 | 6,027 | 6.1 M | 4,931 | 0.818 |
| medicalsupplies | 17 | 17 | 66 | 79,270 | 5.2 M | 75,758 | 0.956 |

(the remaining 9 wares hold 1–8 offers each: khaakscrapmetal, superfluidcoolant,
water, silicon, metallicmicrolattice, spaceweed, dronecomponents, sojahusk,
stimulants.)

### Claytronics — the bimodality is the cap turning on

Claytronics was the sharpest available test case precisely because the same
ware split into two clusters, so whatever separated them had to be a station
property. It is: **allocation**. Sorted by allocation, the 48 claytronics
sellers trace `m × allocation` at a dead-flat 2,480–2,525 units — that is
2,451 units = 5 M Cr / 2,040 Cr — for every station whose allocation exceeds
it, and `m → 1` for every station below it.

| station | allocation | implied `m` (m=1 basis) | `m × allocation` |
|---|---:|---:|---:|
| GOR-075 | 22,835 | 0.109 | 2,482 |
| VLJ-484 | 16,941 | 0.147 | 2,494 |
| RKK-403 | 16,306 | 0.152 | 2,479 |
| EOT-001 | 13,963 | 0.178 | 2,488 |
| IRD-672 | 8,592 | 0.289 | 2,481 |
| TNY-860 | 6,813 | 0.369 | 2,515 |
| NDE-080 | 4,421 | 0.560 | 2,478 |
| LIB-169 | 3,743 | 0.663 | 2,480 |
| JZK-994 | 3,263 | 0.760 | 2,480 |
| LDJ-359 | 2,796 | 0.887 | 2,481 |
| ZNW-776 | 2,706 | 0.917 | 2,481 |
| CGW-678 | 2,595 | 0.957 | 2,483 |
| *…below the cap:* WOK-167 | 1,757 | 1.214 | 2,133 |
| PKM-304 | 1,931 | 1.168 | 2,256 |

The per-(ware, role) dispersion of implied `m` for claytronics output falls
from **IQR/median 0.95 to 0.014** on the capped basis.

### The value of the cap

The sharpest single estimate comes from the Terran/Pioneer energy-cell solar
design — one design, allocation ~992,397 units confirmed in game (AXO-574
992,397, GUX-488 994,470 are among the 49 validated readings), 47 stations
spanning three decades of stock. Taking only the well-conditioned offers
(|s| < 0.7, where `arccos` is not flat) and the cohort's own established
`a = 0.048`:

> **per-offer implied V: median 5,002,645 Cr, IQR 5,001,555 … 5,007,379,
> n = 20.**

That is 5,000,000 Cr to 0.05 %. Solving two individual offers 1.14 M Cr of
stock apart (TFO-916 and GUB-861, same design, same sector group) for `(V, a)`
simultaneously gives **V = 5,006,800 Cr, a = 0.0482** — and `a = 0.048` is the
value [price-curve-2026-07-28.md](price-curve-2026-07-28.md) independently
reports for energy-cell sellers, so the two-parameter solve returns the known
offset rather than absorbing error into it.

Scanning V against the whole binding population with `a` fixed by the confirmed
rule:

| V | bin RMSE (16 bins) | median \|res\| | \|res\| > 0.25 |
|---:|---:|---:|---:|
| 4.00 M | 0.2228 | 0.2171 | 43.6 % |
| 4.50 M | 0.1087 | 0.1029 | 3.3 % |
| 4.75 M | 0.0594 | 0.0568 | 3.0 % |
| 4.90 M | 0.0331 | 0.0302 | 3.0 % |
| **5.00 M** | **0.0197** | **0.0146** | **3.0 %** |
| 5.10 M | 0.0172 | 0.0095 | 2.8 % |
| 5.25 M | 0.0339 | 0.0222 | 2.8 % |
| 5.50 M | 0.0692 | 0.0512 | 3.0 % |
| 6.00 M | 0.1291 | 0.0880 | 6.3 % |

The optimum on this population is 5.05–5.10 M rather than 5.00 M exactly. `V`
and `a` trade off (a 1 % rise in V is absorbed by ~0.001 of `a`), so this is
within the known scatter of the supplier offset (0.041–0.066 across 18 wares).
I report **V = 5,000,000 Cr** because that is what the one cohort with a
directly-validated allocation and a wide fill range returns, and because it is
a round number in a game whose other constants are round.

### Bin-by-bin, the headline population

399 supplier offers whose allocation value exceeds 5 M Cr, 16 equal-count bins,
ordered by stock value, equal weight per bin. `s_m=1` is the current published
model; `s_cap` is `min(allocation, 5 M/avg)` with the same `a`.

| stock value (Cr) | n | fill (alloc) | fill (cap) | s obs | s cap | s m=1 | res cap | res m=1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7,500 | 25 | 0.0004 | 0.0015 | +0.9995 | +0.9878 | +0.9883 | +0.0117 | +0.0112 |
| 148,320 | 25 | 0.0125 | 0.0297 | +0.9845 | +0.9720 | +0.9824 | +0.0125 | +0.0021 |
| 383,940 | 25 | 0.0329 | 0.0768 | +0.9415 | +0.9315 | +0.9698 | +0.0100 | −0.0283 |
| 761,514 | 25 | 0.0525 | 0.1523 | +0.8487 | +0.8315 | +0.9545 | +0.0172 | −0.1058 |
| 1,049,807 | 25 | 0.1246 | 0.2100 | +0.7449 | +0.7287 | +0.8729 | +0.0163 | −0.1280 |
| 1,354,692 | 25 | 0.1276 | 0.2709 | +0.6130 | +0.5983 | +0.8688 | +0.0147 | −0.2557 |
| 1,607,520 | 25 | 0.1401 | 0.3215 | +0.5135 | +0.4762 | +0.8504 | +0.0373 | −0.3369 |
| 1,777,032 | 25 | 0.2417 | 0.3554 | +0.3982 | +0.3886 | +0.6633 | +0.0096 | −0.2651 |
| 1,897,200 | 25 | 0.2651 | 0.3794 | +0.3381 | +0.3241 | +0.6116 | +0.0139 | −0.2736 |
| 2,039,493 | 25 | 0.2351 | 0.4079 | +0.2600 | +0.2459 | +0.6774 | +0.0141 | −0.4174 |
| 2,138,184 | 25 | 0.2739 | 0.4276 | +0.2054 | +0.1907 | +0.5915 | +0.0147 | −0.3861 |
| 2,346,836 | 25 | 0.2702 | 0.4694 | +0.0888 | +0.0720 | +0.6001 | +0.0168 | −0.5112 |
| 2,506,224 | 25 | 0.3041 | 0.5012 | −0.0050 | −0.0193 | +0.5195 | +0.0143 | −0.5245 |
| 3,911,250 | 25 | 0.4315 | 0.7822 | −0.6568 | −0.7349 | +0.1799 | +0.0781 | −0.8367 |
| 7,625,696 | 25 | 0.9717 | 1.5251 | −1.0000 | −1.0000 | −0.9797 | 0.0000 | −0.0203 |
| 14,803,304 | 24 | 0.9877 | 2.9607 | −0.9438 | −1.0000 | −0.9879 | +0.0562 | +0.0441 |

**bin RMSE 0.0285 against 0.3459 — a 12× improvement with zero free
parameters.** The residual is a small, uniform +0.014 bias, which is the
V/`a` trade-off discussed above and not a shape error: the model tracks `s`
from +1.00 to −1.00 through a monotone 5,000-fold sweep of stock value.

---

## Scoring against the whole population

The rule is scored against every main-sequence offer, not only the corridor.

| population | n | bin RMSE `m=1` | bin RMSE cap | median \|res\| `m=1` | median \|res\| cap | \|res\|>0.25 `m=1` | \|res\|>0.25 cap |
|---|---:|---:|---:|---:|---:|---:|---:|
| all main + narrow | 7,227 | 0.00630 | 0.00659 | 0.01433 | 0.01411 | 6.12 % | **4.03 %** |
| supplier side | 1,821 | 0.00717 | 0.00847 | 0.01285 | 0.01302 | 9.77 % | **1.48 %** |
| …where the cap binds | 399 | **0.28296** | **0.01924** | 0.17698 | 0.01457 | 40.85 % | 3.01 % |
| …where it does not | 1,422 | 0.00740 | 0.00740 | 0.01154 | 0.01154 | 1.05 % | 1.05 % |
| buy-only production input | 3,044 | 0.02209 | 0.02209 | 0.07171 | 0.07171 | 8.64 % | 8.64 % |
| rations | 2,372 | 0.00609 | 0.00609 | 0.00151 | 0.00151 | 0.04 % | 0.04 % |
| narrow-span cohort (the old separate book) | 114 | **0.23821** | **0.01359** | 0.17452 | 0.01412 | 41.23 % | **0.00 %** |

**Be honest about the first row.** The save-wide *bin-median* statistic goes
very slightly the wrong way, 0.00630 → 0.00659. It is not a real degradation:
bin medians over 7,227 offers in 24 bins of ~300 cannot see 399 offers however
wrong they are, and the same insensitivity is why `m=1` scores 0.0063 there
while scoring 0.283 on the offers it actually gets wrong. The two statistics
that can see the change both improve — the fraction beyond a quarter band goes
**6.12 % → 4.03 %** save-wide and **9.77 % → 1.48 %** on the supplier side, and
per-offer median |res| improves. Nothing outside the binding set moves at all,
by construction.

### The cap applies to the supplier side only

Tested by applying it everywhere and scoring, on the offers where it would
bind:

| population, restricted to alloc. value > 5 M | n | bin RMSE no cap | bin RMSE with cap |
|---|---:|---:|---:|
| station posts a sell offer | 399 | 0.2830 | **0.0192** |
| buy-only production input | 147 | **0.1058** | 0.2078 |

Applying it to buy-only inputs doubles their error, so it is rejected there.
Independently, the raw data shows no knee: bucketing buy-only inputs by
allocation value, implied-target ÷ allocation-value sits at 0.94–1.09 all the
way to 13 M Cr of allocation, whereas the supplier side breaks from 1.01 to
0.67 at 4–7.6 M and to 0.046 at 125 M.

**The discriminator is the same one E-016 already established for the offset
`a`** — *whether the station posts a sell offer for that ware*, not the ware's
role and not the side of the individual offer. That is a second, independent
phenomenon selecting on the same predicate, which is itself evidence the
predicate is real.

Rations never reach 5 M Cr of allocation anywhere in the save (largest 2.0 M),
so they are untested, not exempt.

---

## Cohort census and per-cohort fits

Joint `(m, a)` grid fits on bin medians, equal weight per bin. `n distinct
fills` is the identifiability guard: a two-parameter fit needs at least three.

| cohort | offers | stations | wares | distinct fills | joint fit `m` | joint fit `a` | bin RMSE (joint) | bin RMSE (`m`=1) | bin RMSE (model) | identifiable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| main / ration | 2,362 | 1,150 | 9 | 1,556 | 0.995 | +0.006 | 0.0068 | 0.0094 | 0.0094 | yes |
| main / production-input | 3,132 | 1,094 | 44 | 2,372 | 1.000 | −0.040 | 0.0231 | 0.0232 | 0.0232 | yes |
| main / supplier / allocation | 1,426 | 991 | 55 | 1,150 | 0.995 | +0.052 | 0.0067 | 0.0067 | 0.0067 | yes |
| main / supplier / **value-capped** | 399 | 331 | 29 | 341 | 1.050 | +0.190 | 0.1516 | 0.2880 | **0.0229** | yes |
| yard / build-demand | 701 | 67 | 43 | 626 | 1.050 | −0.148 | 0.0917 | 0.2964 | 0.2964 | yes |
| lockavgprice / pegged-at-avg | 1,175 | 47 | 47 | 197 | 2.180 | +0.250 | 0.6885 | 0.9179 | 0.9179 | yes (meaningless) |
| supplies / per-ware-constant | 1,305 | 794 | 9 | 8 | 2.995 | +0.250 | 0.2326 | 0.5565 | 0.5565 | **no** (8 fills, 30 rows with an allocation at all) |
| player / manual | 58 | 10 | 28 | 23 | 2.995 | −0.192 | 0.2242 | 1.0853 | 1.0853 | **no** (grid edge, off-model by design) |
| shady / common (1.04× max) | 2,901 | 728 | 4 | 0 | — | — | — | — | — | **no coordinate** |
| shady / fixed (2.75× avg) | 372 | 95 | 4 | 0 | — | — | — | — | — | **no coordinate** |
| buildstorage / demand-curve | 1,771 | 630 | 15 | 0 | — | — | — | — | — | **no allocation** |

The three fits that hit a grid edge (`m = 2.995`, `a = ±0.250`) are reported as
**unusable, not as parameters** — they are the optimiser saying "this is not a
cosine in this coordinate". The `main/supplier/value-capped` row makes the
central point: a *single* `(m, a)` pair fitted freely to that cohort scores
0.1516, while the value cap — which assigns each offer its own `m` from
quantities already known — scores **0.0229 with no free parameters at all**.
The corridor is not a cohort with a low `m`; it is a population whose `m`
varies station by station in a way the cap predicts.

### Which grouping makes `m` tightest

Mean within-group IQR of implied `m` over the supplier side, groups of ≥ 8
offers, weighted by group size. Lower is tighter. The pooled row is the
reference: a grouping only earns its keep by beating it.

| grouping | on the `m = 1` basis | on the value-cap basis |
|---|---:|---:|
| **(pooled — no grouping)** | 0.0476 | **0.0281** |
| station class | 0.0476 | 0.0281 |
| offer side | 0.0477 | 0.0284 |
| station macro / design | 0.0482 | 0.0284 |
| storage source (computed/proxy) | 0.0475 | 0.0286 |
| allocation in hours of throughput | 0.0833 | 0.0290 |
| ware role | 0.0478 | 0.0301 |
| station also produces the ware | 0.0480 | 0.0308 |
| production module count | 0.0604 | 0.0324 |
| total module count | 0.0723 | 0.0326 |
| allocation value (octiles) | 0.0806 | 0.0347 |
| transport pool | 0.0529 | 0.0478 |
| ware | 0.1166 | 0.0590 |
| owner faction | 0.0993 | 0.0800 |
| sector | 0.1286 | 0.1104 |

**No grouping beats pooling.** That is the answer to "which cohort definition
makes `m` tightest": after the value cap there is no residual cohort structure
in `m` at all — it is 1 everywhere, and the whole 41 % tightening (0.0476 →
0.0281) comes from the cap rather than from any partition. Every grouping that
appeared to explain something on the `m = 1` basis (ware 0.117, owner 0.099,
sector 0.129) is worse than pooling even there; those were small-group noise,
and the per-(ware, role) medians in the model doc were reading a mixture of
capped and uncapped stations.

### Per-(ware, role) implied `m`, before and after

| ware | role | n | stations | `m` (m=1 basis) | IQR/med | `m` (cap basis) | IQR/med |
|---|---|---:|---:|---:|---:|---:|---:|
| computronicsubstrate | output | 18 | 18 | 0.119 | 0.082 | **1.031** | 0.037 |
| siliconcarbide | output | 16 | 16 | 0.576 | 0.763 | **1.028** | 0.140 |
| claytronics | output | 48 | 48 | 0.691 | **0.952** | **1.015** | **0.014** |
| siliconwafers | output | 31 | 30 | 0.828 | 0.504 | **1.011** | **0.009** |
| microchips | output | 62 | 59 | 0.969 | 0.560 | **1.013** | 0.034 |
| hullparts | output | 112 | 112 | 0.976 | 0.208 | **1.006** | 0.042 |
| plasmaconductors | output | 64 | 59 | 0.982 | 0.062 | 0.999 | 0.043 |
| weaponcomponents | output | 59 | 59 | 0.960 | 0.057 | 0.960 | 0.057 |
| turretcomponents | output | 46 | 46 | 0.968 | 0.045 | 0.968 | 0.045 |
| energycells | input | 906 | 903 | 0.983 | 0.098 | 0.983 | 0.098 |
| water | input | 174 | 174 | 0.969 | 0.095 | 0.969 | 0.095 |
| scruffinfruits | food | 165 | 165 | 0.986 | 0.005 | 0.986 | 0.005 |

Every cohort the model doc listed as low-`m` collapses to 1.00–1.03, and does
so **more tightly than the uncapped pack**: claytronics and siliconwafers end
at IQR/median 0.014 and 0.009 against the pack's 0.045–0.098. Cohorts the cap
does not touch are byte-identical, as they must be.

---

## The six separate books, re-admitted and re-tested

Each was re-scored from scratch, including the possibility that it is on the
cosine after all.

### `narrow price span (output)` — **DISSOLVED, no longer a separate book**

computronicsubstrate / claytronics / siliconwafers outputs, 114 offers, carved
out in [fill-price-spread-2026-07-28.md](fill-price-spread-2026-07-28.md)
Addendum 2 as a cohort with a per-(ware, role) span constant of 0.19–0.82. It
is not a separate book and there is no per-ware span constant: it is ordinary
supplier pricing with the 5 M cap binding. **bin RMSE 0.2382 → 0.0136, median
|res| 0.1745 → 0.0141, offers beyond a quarter band 41.23 % → 0.00 %.** The
apparent per-ware constants were `5 M / (price_avg × the design's allocation)`,
which is constant within a ware only because those wares are made on one
station design.

### `shady` (black market) — **separate book CONFIRMED, unchanged**

3,273 offers over 823 stations, **no allocation at all**, so no fill
coordinate exists and the cap cannot apply. E-112's two tiers reproduce exactly
on save 70: a fixed tier of **372 offers over 95 stations at 2.7514 × band
average** and a common tier of **2,901 offers over 728 stations at 1.0441 ×
band max**, with **zero station overlap**. What sets a station's tier remains
open; it is not allocation value, since neither tier has an allocation.

### `lockavgprice` — **separate book CONFIRMED, unchanged**

1,175 offers, median price/avg exactly **1.0000** (sd 0.0165), corr(fill, s) =
−0.015. Pegged regardless of stock; the cap changes nothing (bin RMSE 0.9191 →
0.9136, i.e. both meaningless). No re-admission.

### `supplies` (self-supply) — **separate book CONFIRMED, unchanged**

1,305 offers, median price/avg **1.1247**. Only 30 of them have an allocation
row at all, and only 8 distinct fills among them, so **this cohort is
structurally unidentifiable for a two-parameter fit** and is reported as such.
The per-ware constants stand as the description.

### `yards / wharfs / docks` — **separate book CONFIRMED, cap REJECTED here**

701 offers, 67 stations. 202 of them have an allocation worth more than 5 M Cr,
so the cap is testable, and it fails: on that binding subset bin RMSE goes
**0.3355 → 0.6310** and median |res| **0.3283 → 0.5499**. Applying it to the
whole yard population also degrades it (0.3081 → 0.3653). The cap does not
extend to yards. E-028's `k ≈ 2.6` build-demand description stands.

### build storages — **off the main curve, with a defensible denominator**

1,771 offers over 630 hosts, and the requirement was to construct a denominator
or record them as off-curve with evidence. Both, in that order:

- **They hold no allocation** — 0 of 1,771 have a storage row — so `fill` does
  not exist for them and the storage model cannot supply one.
- **A defensible denominator exists**: the outstanding build demand implied by
  their own offer book, `stock + inbound + open buy amount`. It is carried in
  the CSV as `fill_model` for these rows.
- **On that denominator they are not price-inelastic.** corr(fill, s) =
  **−0.791** over 1,574 usable offers, and corr(stock, s) = −0.334 over the
  1,045 with stock. This **contradicts the plain reading of E-029**
  ("construction buyers do not price off stock at all"), although every number
  E-029 predicts still reproduces: median price/max exactly 1.0000, 63.1 % at
  band max to the cent, 187 offers (10.6 %) *above* band max.
- **But they are not on the cosine either.** The curve holds `s = +1.000` flat
  out to fill ≈ 0.41 and only then falls; against `cos(π(f+0.053)/1.095)` the
  bin RMSE is 0.4992, against `cos(πf/1.095)` 0.4369, and the best free
  `(m, a)` is `m = 1.05, a = −0.250` at bin RMSE 0.1353 — with `a` pinned at
  the grid edge, i.e. the fit wants an even larger negative offset.

| fill (demand) | n | s obs | cos(π(f+0.053)/1.095) |
|---:|---:|---:|---:|
| 0.0000 | 99 | +1.0000 | +0.9885 |
| 0.0064 | 98 | +1.0000 | +0.9855 |
| 0.0192 | 98 | +1.0000 | +0.9786 |
| 0.0723 | 98 | +1.0000 | +0.9360 |
| 0.2068 | 98 | +1.0000 | +0.7348 |
| 0.4109 | 98 | +1.0000 | +0.2376 |
| 0.5827 | 98 | +0.8545 | −0.2504 |
| 0.7441 | 98 | +0.1215 | −0.6564 |
| 0.8521 | 98 | −0.2251 | −0.8552 |
| 0.9453 | 98 | −0.4994 | −0.9617 |
| 1.0000 | 98 | −0.0479 | −0.9927 |

**Caveat, stated plainly:** the denominator is derived from the same offer's
own `amount`, so if the engine computes `amount = target − stock` then
`corr(fill, s)` is partly definitional. This is the "offer-derived allocation
is a lower bound" caveat in its strongest form. The monotone relationship is
real; its *shape* is only as trustworthy as that assumption, and the shape is
what refuses the cosine.

### player-owned — **off-model by design, unchanged**

58 offers, 10 stations, 23 distinct fills. Manual `price_setting` / `ware_limit`
thresholds. The free fit lands on the grid edge (`m = 2.995`). Not a cohort.

---

## CONFIRMED vs HYPOTHESIS

**CONFIRMED — the supplier-side price target is `min(allocation, V/price_avg)`.**
399 offers, 331 stations, 29 wares, 17 factions; bin RMSE 0.0285 against
0.3459 with zero free parameters; the fraction beyond a quarter band on the
supplier side goes 9.77 % → 1.48 % save-wide; nothing outside the binding set
moves. Independently, the implied-target/allocation ratio shows a sharp knee at
4–7.6 M Cr on the supplier side and no knee at all on buy-only inputs up to
13 M.
*Falsified by:* a supplier station with an in-game-verified allocation whose
allocation value exceeds 5 M Cr and whose price nonetheless tracks the full
allocation — e.g. any of the 55 energy-cell solar plants pricing as though its
target were 992,397 units rather than 312,500.

**CONFIRMED — `V ≈ 5.0 M Cr`, and it is a *value*, not a volume or a unit
count.** Per-offer implied V on the energy-cell cohort: median 5,002,645,
IQR 5,001,555–5,007,379 (n = 20). Normalising by `price_min` or `price_max`
instead of `price_avg` gives a 3–6× looser fit (relative IQR 0.349 and 0.186
against 0.056). Normalising by ware volume gives no constant at all
(31,000–609,000 m³ across the same cohorts).
*Falsified by:* any tight capped cohort reading a V more than ~2 % from 5.0 M
once its `a` is independently pinned.

**CONFIRMED — the cap selects on "the station posts a sell offer for this
ware", not on ware role or offer side.** Applying it to buy-only inputs where
it would bind roughly doubles their error (bin RMSE 0.1058 → 0.2078). Same
predicate as E-016.
*Falsified by:* a buy-only production input with allocation value well above
5 M Cr pricing on the capped target.

**HYPOTHESIS — V is exactly 5,000,000 Cr rather than 5.05–5.10 M.** The
binding-population optimum is 5.05–5.10 M with `a` fixed at the rule value;
`V` and `a` trade off, so this cannot be settled from a population with a
scattered `a`.
*Falsified by:* one station read in game at two stock levels far enough apart
to pin `a` and `V` jointly (see the leads below).

**HYPOTHESIS — Tidebreak (E-018) is the same cap and not a bespoke target.**
VOM-540 carries condensate at band average 25,000 Cr against a 5,000-unit
allocation — 125 M Cr, the deepest point in the corridor in the entire save.
The cap predicts its target at **exactly 200.0 units with zero free
parameters**, against E-018's 173.1 fitted from two readings with two free
parameters. At the observed stock of 23 the cap model reproduces the save's
offer price to **28 Cr out of a 2,500 Cr band half-width (1.1 %)**, where the
uncapped allocation basis is off by **212 Cr (8.5 %)**. E-018's own derivative
constraint (+17.41 Cr per unit sold) implies 177 units and its level constraint
implies 216–226 depending on `a`; 200 sits between them, and the two-point
solve is too ill-conditioned to separate them from one station.
*Falsified by:* an in-game reading at Tidebreak that pins the target away from
200 — see leads.

**HYPOTHESIS — the cap is not a per-station or per-faction property.** The 331
capped stations span 17 factions and 4 designs with no grouping tightening `m`
below the pooled value. But 392 of 399 offers sit on one generic design, so a
design-level constant is not excluded by this save.
*Falsified by:* a capped supplier on a distinctly different design reading a
different V.

### The one counterexample in the save: DHI-588

Splitting the binding population by how its allocation was obtained separates
it cleanly, and the split is one station wide:

| allocation source | offers | stations | median \|res\| `m=1` | median \|res\| cap | bin RMSE `m=1` | bin RMSE cap |
|---|---:|---:|---:|---:|---:|---:|
| `computed` (production, equal-hours) | 395 | 330 | 0.1790 | **0.0145** | 0.2219 | **0.0191** |
| `proxy` (non-producer, stock + open buy) | 4 | 1 | **0.0152** | 0.1729 | **0.0121** | 0.1749 |

The four are **DHI-588** — a *Kaori*-owned station running the Argon
trade-station design `station_arg_tradestation_base_01_macro`, in Mitsuno's
Sacrifice — on claytronics and silicon, both sides. It fits **better uncapped**,
and this is not the proxy denominator marking its own homework:

| ware | stock | open buy amount | target from the offer book | target from the price | the cap says |
|---|---:|---:|---:|---:|---:|
| claytronics | 805 | 2,105 | **2,910** | 2,979 | 2,451 |
| silicon | 12,460 | 44,206 | **56,666** | 58,829 | 38,462 |

The station's own *bid quantity* and its *price* are independent observables.
They agree with each other to 2.4 % and 3.8 % and both disagree with the cap by
19 % and 53 %. A capped station would bid 1,646 claytronics, not 2,105. This is
a real breach, not a measurement artifact.

**So the discriminator is probably narrower than "posts a sell offer".** Every
one of the 330 capped stations is a *producer* with a computed, production-based
allocation; the one non-producer in the binding set ignores the cap — and so do
yards and wharfs, which are also non-producers and where the cap was rejected
independently (bin RMSE 0.3355 → 0.6310). That is a consistent story:
**non-producers do not cap.** It is also confounded in this save — every capped
producer posts a sell offer, so "producer" and "posts a sell offer" cannot be
separated on the 399 offers available, and one station is thin evidence for
either. The cap's *value* and *form* (E-113/E-114) do not depend on which way
this resolves; only its scope does.

*Falsified by:* a second non-producing station (trade station, dock) with an
allocation worth over 5 M Cr pricing on the capped target — which would make
DHI-588 an outlier rather than a rule.

---

## Ranked remaining leads, and the reading that settles each

1. **Pin `V` and `a` jointly on one station.** Read one energy-cell solar
   plant's sell price and stock twice, far apart in stock — ideally once near
   150,000 units (mid-curve, where `arccos` is steep) and once near 300,000.
   Two points, two unknowns, one station, no cohort scatter. This settles
   *whether V is 5,000,000 exactly* and simultaneously re-measures the supplier
   offset for E-007. Best targets: AXO-574 (Earth) and GUX-488, whose
   allocations are already in `tests/data/station_readings.json`.
   *Predicts:* `price = 16 × (1 + s × 0.375)` with `s = cos(π(stock/312,500 +
   0.048)/1.095)`.

2. **Tidebreak, to separate 200 from 173.** VOM-540 currently holds 23
   Protectyon at 27,259.85 Cr. Sell it **~117 more** (to a stock near 140) and
   read the price. The three live hypotheses are then furthest apart:

   | stock | cap, target 200 (`a` = 0.048) | E-018, target 173.1 (`a` = 0.021) | uncapped, allocation 5,000 |
   |---:|---:|---:|---:|
   | 23 (now) | 27,231.57 | 27,260.32 | 27,465.94 |
   | 100 | 24,996.41 | 24,634.08 | 27,445.37 |
   | **140** | **23,639.91** | **23,189.50** | **27,432.80** |
   | 173 | 22,833.15 | 22,557.01 | 27,421.46 |

   The uncapped allocation is refuted by any move at all — it predicts the
   price barely leaves 27,4xx across the whole range. Separating the cap from
   E-018's fitted target needs the mid-curve reading: **450 Cr at stock 140**,
   against a panel resolution of ~25 Cr (0.1 pp of the 25,000 Cr average). This
   is the highest-value single reading available.

3. **Does the cap apply to non-producers? DHI-588 says no.** See the
   counterexample section below — this is now the sharpest open question about
   the cap's scope, not a design-independence question. *Needs:* the Logical
   Station Overview storage maximum for claytronics and silicon on DHI-588
   (Mitsuno's Sacrifice), which would confirm or refute the 2,910 / 56,666
   targets its own offer book implies.

4. **Do rations cap?** No ration anywhere in the save reaches 5 M Cr of
   allocation (largest 2.0 M), so the question is untested rather than
   answered. *Needs:* a habitat with a very large medical-supplies or
   spaceweed allocation, or a player-built one.

5. **The scavenger (Avarice) allocation scale error.** Six scavenger stations
   price their energy cells as though their allocation were **1.25–1.37 ×** the
   modelled value — a *constant scale* error, which
   [station-storage-model.md](../models/station-storage-model.md) says points at
   capacity or throughput, not pricing. NDE-080 implies 1.316 M against a
   modelled 0.961 M; FXP-772 1.188 M against 0.904 M; CGW-678 1.448 M against
   1.128 M. This is a storage-model lead, not a pricing one, and it is the
   largest single block of `off-model` supplier rows in the CSV.
   *Needs:* the Logical Station Overview storage maximum for energy cells on
   any Avarice station (NDE-080, CGW-678, KWC-232).

6. **What sets a `shady` station's tier** (E-112, unchanged and still open).
   Neither tier has a fill coordinate, so no save-side measurement can settle
   it; it needs the shadyguy post's own state.

7. **The build-storage curve's true shape.** Only worth pursuing with a
   denominator that is *not* derived from the offer's own `amount` — i.e. the
   station's outstanding construction bill of materials, read from
   `build_resource` against `v_built_module`.

---

## Rejected here — do not re-test without new evidence

| candidate | how it died |
|---|---|
| `m` is a per-(ware, role) game constant (E-024) | claytronics reads 0.109 and 1.214 for the *same* ware and role on two stations; the split is by allocation, and `m × allocation` is flat to ±1 % |
| the corridor is a per-ware "price span" multiplier | the per-ware constants are `5 M / (avg × allocation)`; siliconwafers reading 0.823 as output and 1.184 as input is the same two designs, not two spans |
| the cap is a *volume* cap | `target × ware.volume` spans 31,000–609,000 m³ across cohorts that share a value cap to 1 % |
| the cap normalises on `price_min` or `price_max` | relative IQR of the implied cap 0.349 (min) and 0.186 (max) against 0.056 (avg) |
| the cap applies to buy-only production inputs | bin RMSE 0.1058 → 0.2078 on the 147 offers where it would bind; and no knee in the raw implied target up to 13 M Cr of allocation |
| the cap applies to yards/wharfs/docks | bin RMSE 0.3355 → 0.6310 on the 202 binding offers |
| the corridor is a faction, sector, design, module-count or transport-pool property | every one of those groupings has a *higher* within-group IQR of `m` than pooling, on both bases |
| a single `(m, a)` pair describes the capped cohort | free joint fit scores 0.1516 against the zero-parameter cap's 0.0229 |
