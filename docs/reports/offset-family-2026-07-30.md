# The offset family: rations, the input constant, and the storage-only case (P3)

*2026-07-30. Plan item **P3** of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md), covering
register entries **E-015** (rations vs the station constant), **E-011** (is the
input offset a per-module reserve?), **E-017** (is `+0.05` the default offset?)
and, incidentally, **E-009** (the constant is per-station) across time.*

*Data.* (a) and (c): the analysis DB snapshot resolved through
`current_save` — `save_id` **71**, `save_002`, game time 82,688.
(b): the 13-save archived corpus (game time 69,324 → 84,643 s, 15,319 s
span; adjacent saves as close as **5 s** and **177 s** apart, so the
"minutes timescale" is partly covered here as well as the hours one).
All offsets are inverted out of the confirmed closed form:

```
u   = 1.095 · acos(s_obs)/π ,   s_obs = (p−avg)/(max−avg)  or  (p−avg)/(avg−min)
a   = u − fill ,                fill  = (stock + inbound − outbound) / allocation
```

with `allocation` = `station_storage.max_units` (`role != 'supply'`). Offers
with `|s_obs| ≥ 1` are clamped and carry no information about `a`; they are
excluded everywhere. `supplies`- and `shady`-flagged offers are excluded, as
are (station, ware) pairs that also post a **sell** offer (those take the
supplier offset by E-016).

---

## (a) E-015 — rations do **not** track the station's input constant

### Result: the offset is keyed on the ware's role/predicate, not on the station

**Population.** 829 stations on snapshot 71 carry ≥ 1 unclamped ration buy
**and** ≥ 2 unclamped production-input buys: 1,500 ration offers and 2,632
input offers.

| population | median implied `a` | MAD | min | max |
|---|---:|---:|---:|---:|
| ration buys (`role = food`) | **+0.0066** | **0.0021** | −0.826 | +0.653 |
| production-input buys (same 829 stations) | −0.0525 | 0.0517 | −0.970 | +0.544 |

Per station, `ration_a − input_a` has median **+0.060** (min −0.218, max
+0.458). The rations sit still while the input constant ranges over the whole
population.

**The discriminating cohort.** 445 of the 829 stations have an input constant
further than 0.05 from +0.006 — these are the stations where the two
hypotheses make different predictions. On them:

| rule | median per-station |err| | bin-median |err| on the cohort | bin-median |err| save-wide |
|---|---:|---:|---:|
| rations sit at **+0.006** (role/predicate rule) | **0.0022** | **0.0045** | **0.0043** |
| rations take the **station's input constant** | 0.1041 | 0.1074 | 0.0647 |

*Bin-median scoring per the ground rules: fill deciles, equal weight per bin,
ten bins; reported both on the deriving cohort and on the whole 1,500-offer
ration population.* 401 of the 445 discriminating stations put their rations
within 0.02 of +0.006; only 179 of all 829 are within 0.02 of their own input
constant, and those are stations whose input constant happens to be near zero.

**The reference case named in the triage reproduces exactly.** CCN-497
(`[0x9edbf]`, holyorder): graphene −0.3884, refined metals −0.3995 — median
input constant −0.3940 — while medical supplies read **+0.0061** and soja husk
**+0.0060**. The station constant does not drag its rations with it.

### The residual, expressed in credits (the honest error bar)

`a` is a poor unit for ration wares: they are cheap, so one credit of price is
worth ~0.03 of `a`. Scoring in credits instead, against the prediction at
`a = +0.006`:

- median residual **−0.027 Cr** over 1,500 offers, MAD 0.068 Cr;
- **1,359 / 1,500 within ±0.50 Cr**, **1,407 / 1,500 within ±1.00 Cr**;
- of the 179 offers that look "off-rule" in `a` (|a − 0.006| > 0.02), 174 are
  within **2.5 Cr** and their median band average is 54 Cr — they are the
  price-rounding quantum, not a second offset;
- exactly **two** offers are genuinely off: **MXH-411** (medical supplies,
  +42.4 Cr; the *player's* station, which carries manual `override` price
  settings and whose whole input set reads a pathological −0.847 at fill > 1,
  i.e. its modelled allocation is wrong) and **HPI-934** (terran, medical
  supplies, −33.3 Cr, unexplained). That is 0.13 % of the population.

### Recommendation

**E-015 · settle as CONFIRMED (role/predicate-keyed).** The offset does not
follow the station; ration buys sit at +0.006 while the same stations' inputs
range from −0.97 to +0.54.

*Honest caveat, to be carried into the register entry:* this test trusts the
**modelled ration allocation** (E-021/E-119's ration buffer — the tightest law
in the project, pooled MAD 0.00163). If those allocations were systematically
wrong, the ration `a` would absorb the error. The independent in-game reading
**R4** (one habitat ration price and one production-input price read at the
same station at the same moment) remains the belt-and-braces confirmation and
should stay listed as such rather than being deleted.

*Falsified by:* a station posting an unclamped ration buy at its own input
constant while that constant is more than ~0.05 from +0.006, at a
directly-read (in-game) ration allocation.

---

## (b) E-011 — the per-module input **reserve** is refuted

E-011 says the −0.039 input offset is a **per-module input reserve**, i.e. the
station holds back a quantity of the ware for its modules, giving `a ∝ 1/n`.
Two independent tests, one same-snapshot and one across epochs.

### Test 1 (decisive): a reserve in **units** cannot be shared across wares

If the offset were a physical reserve `R` (units of ware held back by the
modules), then `a = −R/allocation`, so **`R` would be the same number for every
input of a station** and `a` would scale as `1/allocation`. E-009 already
establishes the opposite — `a` is shared across a station's inputs — but only
now, over stations whose input allocations differ by orders of magnitude, does
that become a refutation.

Restricting to **non-yard production stations** (no built `buildmodule`; see
below for why that split matters), 388 stations have ≥ 2 unclamped input buys
with allocations at least 3× apart and a materially negative constant:

| quantity | median |
|---|---:|
| within-station spread of `a` | 0.0391 |
| allocation ratio (max/min within station) | 5.4 |
| implied reserve ratio `R_max/R_min` | **4.5** |
| relative gap between the two ratios | 0.256 |

`R` tracks the allocation ratio, not 1.0. On the large multi-input stations the
demonstration is stark — NVF-801 posts twelve inputs at `a` = −0.198…−0.214
while its allocations run from 210 units (advanced composites) to 366,112
(energy cells); the implied "reserve" would have to be **41.7 units of advanced
composites and 73,500 units of energy cells, from the same modules**, a factor
of 1,764. The offset is a **fill fraction**, not a stock of goods.

Two further facts a reserve cannot accommodate:

- **169 of 909** non-yard stations with ≥ 2 unclamped input buys have a
  **positive** median `a` (a reserve can only be negative);
- the offset is bounded and clusters (see the yard result below), where a
  per-module reserve would smear with module count.

*A caveat stated plainly:* because the storage allocation is itself
proportional to consumption rate, a reserve expressed as **a fixed number of
hours of consumption** is observationally identical to a fill offset and is
**not** refuted here — but that is not what E-011 claims, and it would still
need a mechanism for the positive-`a` stations.

### Test 2: the constant is flat across epochs while stock moves

> **Superseded in part — see the Addendum (2026-07-30, same day) at the end of
> this report.** The corpus `trade_pending` table stores every trade twice
> (`source='order'` and `source='reservation'`), which doubled the pending
> terms in the epoch series below. The corrected figures are in the addendum;
> the conclusion is unchanged and strengthened. Test 1 and section (a) are
> computed from the analysis DB and are **not** affected.

Twenty-four largest-|a| input stations of snapshot 71, traced through all 13
saves on cross-save identity `(code, class, macro)`. Snapshot-71 allocations
are held fixed, so epochs where the allocation demonstrably moved must be
dropped. 1,165 raw (station, ware, epoch) points; filters, in order:

| filter | dropped |
|---|---:|
| clamped (`\|s\| ≥ 1`) | 79 |
| built-module list differs from `save_002` | 30 |
| stale offer (price bit-identical to the previous epoch while net moved) | 32 |
| `net > snapshot-71 allocation` (allocation provably moved) | 141 |
| **kept** | **883** |

The stale filter is not cosmetic: the offer price is refreshed on the
`updatetradeoffers` timer (~65 s, E-010), so a save can catch a price that
belongs to an earlier stock. CCN-497's graphene, for example, reads exactly
−0.3885 on 8 of its 12 epochs and its three deviating epochs are precisely the
ones repeating a previous save's price (195.21 at both net 2,566 and net 1,714).

Restricting to **non-yard** production stations with ≥ 3 clean epochs and a
fill span ≥ 0.10 — 19 (station, ware) series:

- `a` spread across epochs: **median 0.0254**; ≤ 0.01 on 6/19, ≤ 0.02 on 8/19;
- **151 / 177 epochs are within 0.01 of their series median**;
- median fill span 0.212; median game-time span 14,663 s.

The clean end of that list is emphatic — the price moves along the cosine by
tens of percent while `a` does not move at all:

| station | ware | epochs | fill span | Δprice | median `a` | `a` spread |
|---|---|---:|---:|---:|---:|---:|
| PQZ-562 | energycells | 12 | 0.291 | 32.6 % | −0.2104 | **0.0008** |
| PQZ-562 | water | 10 | 0.129 | 16.4 % | −0.2104 | 0.0010 |
| JQZ-281 | energycells | 10 | 0.299 | 30.4 % | −0.2510 | 0.0017 |
| HTM-682 | energycells | 11 | 0.255 | 28.6 % | −0.1320 | 0.0031 |
| GYM-348 | ore | 7 | 0.184 | 6.1 % | −0.5294 | 0.0050 |
| JIC-579 | energycells | 11 | 0.212 | 22.7 % | +0.0015 | 0.0062 |
| UDX-946 | energycells | 12 | 0.184 | 18.3 % | −0.0348 | 0.0108 |
| CCN-497 | refinedmetals | 11 | 0.434 | 27.8 % (155.64 → 206.52) | −0.3906 | 0.0238 |

CCN-497 — the station E-011 asked the player to read twice — is covered here at
**11 epochs over 13,701 s**, with its net position running 1,005 → 1,960 units
(fill 0.457 → 0.891) and its price running 206.52 → 155.64, all at a constant
`a` of −0.389. The wider spreads in the remaining series are dominated by
epochs where the snapshot-71 allocation is stale rather than by movement in `a`
(the allocation is only measured at 71; per-epoch allocations are out of scope
of this item).

**E-009 across time.** Per station, per epoch, the median `a` over its inputs:
the within-epoch MAD across a station's own inputs is **0.0000–0.0009** on most
stations (IVE-441, SEE-945, XST-598, DBY-447, PQZ-562, JQZ-281, CCN-497), i.e.
the "one constant per station" rule holds at every epoch, not only on 71. The
epoch-to-epoch **range** of that constant is ≤ 0.01 on 6 of 22 stations and has
a median of 0.064 — but that range is measured against a fixed snapshot-71
allocation and so is an upper bound on real drift, not a measurement of it.
**Recommendation: do not upgrade or downgrade E-009 on this evidence** beyond
noting that the per-station-sharing half is now verified at 13 epochs.

### A finding that belongs to somebody else: the yard constant

The 24-station "largest |a|" list is dominated by a cluster at **exactly
−0.2026**, and every one of them is a yard/wharf:

- 41 stations sit within ±0.005 of −0.2026, and **all 41 carry a built
  `buildmodule`**;
- across all 61 non-player yards with ≥ 2 unclamped input buys, median `a` is
  **−0.2019 with MAD 0.0007**, within-station spread median 0.0082, over
  allocations that differ by a median factor of **385×**;
- the 909 non-yard production stations have median `a` −0.0435, MAD 0.0375.

Read the sign carefully: on a yard the storage allocation is **not** the
denominator the engine uses (E-028: yards price off outstanding build demand),
so `−0.2026` is most likely the *denominator error* showing up as an offset —
`fill_true = fill_storage − 0.2026` would mean the demand denominator is a
near-constant function of the storage allocation across 41 yards of many
factions and designs. **This should be handed to the P8 / build-demand item**;
it is a strong constraint on E-028's denominator and it is not resolved here.
It also means every earlier statement about the "input offset" population is
contaminated by yards unless they were excluded — this report excludes them.

### Recommendation

**E-011 · FALSIFIED** as stated ("the input offset is a per-module input
reserve, so `a ∝ 1/n_modules`").
*Killed by:* the offset is shared as a **fill fraction** across a station's
inputs whose allocations differ by up to 1,764× (NVF-801: implied reserves of
41.7 and 73,500 units from the same modules), so it cannot be a stock of goods;
169/909 stations carry a positive offset, which no reserve can produce; and the
offset is flat to ≤ 0.01 across up to 13 epochs and 15,319 s while the net
position moves by 10–50 % of allocation, so it is not consumed and replenished
with stock.
*Not refuted by this work:* a reserve denominated in **hours of consumption**,
which is algebraically indistinguishable from the fill offset itself. Record
that in the model's rejected table so it is not re-tested as if new.
*Reading R4 (CCN-497 read 5 and 30 min apart)* can be **downgraded to
optional** — the corpus already supplies CCN-497 at 11 epochs including
adjacent saves 177 s apart. R4 retains value only as the belt-and-braces
confirmation for E-015 (see (a)).

---

## (c) E-017 — the storage-only population is nearly empty; evidence strengthened, not settled

E-017 asks whether `a = +0.05` (supplier) is the *default* offset, with the
−0.039 consumer offset the special case, and names "a storage-only ware read on
any station" as what settles it. On snapshot 71 the population that question
points at barely exists.

**Census.** 536 buy-**only** offers on stations with **no production module**;
407 unclamped and non-player, over 68 stations and 22 wares. But those 68
stations are almost entirely **wharfs, shipyards, pirate bases and trade
stations that carry a `buildmodule`** — 404 of the 407 offers. Their median
implied `a` is **−0.2019 (MAD 0.0010)**: the yard constant from (b), which
belongs to E-028's denominator problem, not to the offset family.

> **Superseded in part — see the Addendum.** The 37-point condensate series
> below shares the corpus pending-duplication defect; the census of 536/407/3
> offers is from the analysis DB and is unaffected.

**The genuine storage-only cohort is three stations.** CWW-066, AYQ-106 and
EWG-328 — scavenger, `station_gen_factory_base_01_macro`, no production and no
build module — each buying **condensate** against a 5-unit allocation. This is
the same design that produced E-017's original 14 offers. Across the 13-save
corpus they give **37 unclamped (station, epoch) points**:

| fill | n | median implied `a` |
|---:|---:|---:|
| 0.400 | 6 | +0.0478 |
| 0.600 | 15 | +0.0472 |
| 0.800 | 14 | +0.0509 |
| 0.000 | 1 | +0.2441 (allocation stale) |
| 1.200 | 1 | −0.5528 (net > allocation ⇒ allocation stale) |

Bin-median scoring over the three populated bins (equal weight per bin):

| candidate | bin-median \|err\| |
|---|---:|
| **supplier `a` = +0.050** | **0.0020** |
| +0.053 | 0.0044 |
| ration +0.006 | 0.0426 |
| consumer `a` = −0.039 | 0.0876 |

So every storage-only observation available in this playthrough reads the
**supplier** offset, at 35 clean points across 13 epochs and 3 stations rather
than E-017's original 14 — but it is still **one ware, one station design, one
faction, and three quantised fills** on a 5-unit allocation.

### Recommendation

**E-017 · stays PENDING**, evidence strengthened. Do **not** mark it CONFIRMED:
the population is not decisive and is not independent of the cohort the claim
was derived from. Update its *Predicts* to the 35-point, 13-epoch figure and
its *Needs* to reflect the census result — the reason no better save-side
evidence exists is structural: **non-producing stations in this save are
overwhelmingly yards, and yards price on a different denominator**, so the
"storage-only ware" population is 3 stations wide. Any future settlement needs
either a different playthrough with civilian trade stations or the in-game
reading.
*Falsified by:* any storage-only ware, on any station, reading the −0.039
consumer offset.

---

## Ground-rules compliance and known limits

- Every shape/parameter claim above is scored on **bin medians with equal
  weight per bin**, and reported on both the deriving cohort and the whole
  population ((a): 0.0045 cohort / 0.0043 save-wide; (c): three fill bins).
  Per-offer MAD is quoted only as a descriptive spread, never as the score.
- The **lower-bound rule** is respected: epochs where `net > allocation` are
  dropped as *allocation moved*, never re-fitted; they are counted (141 of
  1,165) rather than silently discarded.
- Cross-save identity is `(code, class, macro)` and is required to be unique
  in the target save; runtime ids are never carried across saves.
- Everything in (b) holds the **snapshot-71 allocation** fixed across epochs.
  Where the storage inputs (workforce, efficiency, module list) moved, the
  implied `a` absorbs it. Module-list changes are filtered; workforce and
  efficiency changes are not, and they are the most likely cause of the
  residual spread in the wider series. Recomputing per-epoch allocations is a
  storage-model job (P6) and is out of scope here.
- The save is modded; all joins fall back on unknown macro/faction/ware and
  nothing here writes to the analysis DB.

---

## Addendum, 2026-07-30 (same day): corpus pending-trade duplication

**Defect.** The Phase-1 scratch corpus (`corpus.sqlite`) stores every pending
trade **twice** — once with `source='order'` and once with
`source='reservation'` — on save_002, 4,899 rows over 2,450 distinct
`trade_id`s (2,449 order + 2,450 reservation), the pairs byte-identical (zero
`trade_id`s carry conflicting payloads). Found by the P2 agent. A plain
`SUM(amount − transferred)` over that table therefore **doubles every inbound
and outbound term** in the net position.

**Scope.** Only the corpus-derived series in this report are affected:
section (b) **Test 2** (the epoch trajectories) and the 37-point condensate
series in section (c). Everything else — all of section (a), section (b)
**Test 1**, the yard-constant census, and the 536 / 407 / 3-station census in
section (c) — is computed from the analysis DB, whose `trade_pending` has a
primary key on `trade_id` (2,450 rows / 2,450 ids on save 71) and is **not
duplicated**. Those figures stand as printed.

Everything below re-runs the affected computations with the pending terms
deduplicated per `trade_id`.

### Corrected filter counts (replaces the table in (b) Test 2)

| filter | as printed | **corrected** |
|---|---:|---:|
| clamped (`\|s\| ≥ 1`) | 79 | 79 |
| built-module list differs from `save_002` | 30 | 30 |
| stale offer (price identical to previous epoch while net moved) | 32 | **6** |
| `net > snapshot-71 allocation` | 141 | **26** |
| kept | 883 | **1,024** |

The two big drops are the point: the doubled inbound term was *manufacturing*
both artifacts. 115 of the 141 "allocation moved" epochs were simply net
positions inflated past the allocation by double-counting, and 26 of the 32
"stale" flags were epochs whose net only *appeared* to move.

### Corrected epoch stability (replaces the (b) Test 2 statistics)

Non-yard production stations, ≥ 3 clean epochs, fill span ≥ 0.10 — **20**
series (was 19):

| statistic | as printed | **corrected** |
|---|---:|---:|
| median `a` spread across epochs | 0.0254 | **0.0059** |
| spread ≤ 0.01 | 6/19 | **11/20** |
| spread ≤ 0.02 | 8/19 | **15/20** |
| epochs within 0.01 of series median | 151/177 | **227/241** |
| median fill span | 0.212 | **0.305** |
| median game-time span | 14,663 s | **15,319 s** |

Yards, same filters, 25 series: median spread **0.0042**, ≤ 0.01 on 15/25,
262/287 epochs within 0.01 of the series median.

Corrected worked examples:

| station | ware | epochs | fill span | median `a` | `a` spread |
|---|---|---:|---:|---:|---:|
| QHY-100 | water | 9 | 0.140 | −0.3097 | **0.0003** |
| JQZ-281 | antimattercells | 11 | 0.149 | −0.2503 | 0.0008 |
| HTM-682 | ore | 13 | 0.149 | −0.5283 | 0.0013 |
| PQZ-562 | energycells | 13 | 0.323 | −0.2104 | 0.0021 |
| JQZ-281 | energycells | 12 | 0.448 | −0.2510 | 0.0023 |
| CCN-497 | graphene | 12 | 0.315 | −0.3886 | 0.0027 |
| JQZ-281 | microchips | 13 | 0.658 | −0.2513 | 0.0198 |
| CCN-497 | refinedmetals | 11 | 0.434 | −0.3906 | 0.0238 |

**CCN-497, the station E-011 named, now reads clean on both inputs.** Graphene
holds `a` in −0.3884…−0.3911 on **all 12 unclamped epochs** (net 1,448 → 2,142,
price 233.00 → 158.98); refined metals holds −0.3884…−0.4122 on 11 epochs (net
1,005 → 1,960, price 206.52 → 155.64). Both across 15,319 s.

**One narrative correction.** The body cites CCN-497's graphene as an example
of a *stale* offer — "195.21 at both net 2,566 and net 1,714". That was the
duplication artifact: with dedup the net is genuinely **1,714 at all three of
save_009 / save_010 / save_001**, so the identical price is correct behaviour,
not staleness. Stale offers do exist (6 points survive the corrected filter,
and E-010's ~65 s `updatetradeoffers` timer is independently confirmed), but
they are **rare, not common**, and the warning issued to other Phase-2 agents
should be scaled down accordingly. Guarding against them remains cheap and
harmless.

### Corrected E-009-across-time figures

Per-station epoch-to-epoch **range** of the constant: median **0.0071** (was
0.064), ≤ 0.01 on **12 of 22** stations (was 6 of 22). Within-epoch MAD across
a station's own inputs remains 0.0000–0.0009 on most stations. The
recommendation is unchanged — **do not move E-009's status on this evidence**;
the range is still an upper bound measured against a fixed snapshot-71
allocation.

### Corrected condensate series (section (c))

37 unclamped (station, epoch) points over the same 3 stations. The `fill 1.200`
row disappears — it was an inflated net, not a stale allocation — leaving 36 of
37 points in three populated bins:

| fill | n | median implied `a` |
|---:|---:|---:|
| 0.400 | 6 | +0.0478 |
| 0.600 | **16** | +0.0472 |
| 0.800 | 14 | +0.0509 |
| 0.000 | 1 | +0.2441 (allocation stale) |

Bin-median |err| over the populated bins is **unchanged**: +0.050 supplier
**0.0020**, +0.053 0.0044, +0.006 ration 0.0426, −0.039 consumer 0.0876.

### Effect on the recommendations: none

- **E-011 · FALSIFIED — survives, strengthened.** Its decisive leg (Test 1,
  the reserve-in-units argument, NVF-801's 41.7-vs-73,500-unit contradiction,
  and the 169/909 positive-`a` stations) is analysis-DB only and untouched.
  The corroborating epoch leg got *better*: `a` is now flat to a median spread
  of 0.0059 with 227/241 epochs inside 0.01, over a larger median fill span.
- **E-015 · CONFIRMED (role/predicate-keyed) — survives untouched.** Section
  (a) uses no corpus data at all.
- **E-017 · stays PENDING** — same conclusion, same bin scores, one fewer
  spurious outlier.
- The **yard constant** finding (−0.2019, MAD 0.0007, 41/41 with a
  `buildmodule`) is analysis-DB derived and unaffected; the corrected yard
  epoch series (median spread 0.0042) reinforce it.
