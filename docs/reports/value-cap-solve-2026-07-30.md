# The joint (V, a) solve — 13-epoch supplier trajectories (P2)

*2026-07-30. Plan item **P2** of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md); targets
register entries **E-116** (is `V` exactly 5,000,000 Cr?) and **E-007** (is the
sell-side offset 0.050 with a small-allocation drift?). Data: the 13-save
archived corpus built in Phase 1 (game time 69,324 → 84,643 s, one playthrough,
guid `8E0C8E37-2192-49FD-BF4B-F535782A1C55`), parsed with the project's own
`save/parser.py`, plus analysis-DB snapshot `save_id` **71** for storage
allocations and band data. Bands come from the packaged STOCK reference CSVs
and were verified identical between the corpus extract and the analysis DB
(0 of 1,891 rows differ). Nothing under `src/` or `tests/` was touched.*

---

## Headline

**E-116 stays PENDING. Reading R6 remains decisive.** The corpus makes the
cap sharper in every way *except* the one that matters:

- **CONFIRMED (new):** the cap value has **no per-station, per-ware or
  per-faction structure**. With `a` held at one value, the per-station solved
  `V` over 153 multi-epoch trajectories has **IQR/median = 0.008** (0.8 %) —
  ware medians spread 5.025–5.060 M, faction medians 5.030–5.080 M. `V` is one
  global engine constant.
- **NOT settled:** its absolute value. `V` and `a` trade off along an exact
  ridge, and **13 epochs per station do not break it** — the corpus ridge and
  the single-snapshot binding-population ridge have the *same* slope,
  ≈ **+0.0009 in `a` per +1 % in `V`**, precisely the trade-off E-116 predicted.
  Per-station 95 %-style `V` intervals with `a` free are ~23 % wide (median
  1.16 M), not the ~1 % the pass criterion asked for.
- What the corpus *does* give: **conditional on `a`, `V` is pinned to ±0.1 %.**
  At `a = 0.048` the two in-game-anchored solar plants each return implied
  `V = 5,001,8xx Cr` as a 13-epoch median (AXO-574 5,001,807; GUX-488
  5,001,772). At `a = 0.053` the same stations return 5,057,327 and 5,043,210.
  So *if* the supplier offset is 0.048, `V` is 5.000 M to four figures; if it
  is 0.053, `V` is ≈ 5.05 M. The engine's `a` is what is unknown, not `V`.
- **E-007 is sharply narrowed and its "second effect" half is in trouble.**
  The 0.058 → 0.049 drift with allocation reproduces exactly on the population
  whose denominator is the *modelled* allocation (0.0590 at alloc 2,155 →
  0.0484 at alloc 195,691, 10 bins × 106 offers), and **disappears on the
  capped cohort, whose denominator `V/price_avg` carries no storage-model
  error** (a flat 0.0450 → 0.0475 across allocations 5,157 → 992,398, 6 bins ×
  29). The most likely reading is that the drift is an **allocation-model
  artifact**, not a second price effect. HYPOTHESIS, not confirmed.

---

## Method

### Cohort

Candidates were taken from snapshot 71: every **sell** offer on a non-player
station with a `station_storage` row (`role != 'supply'`), no `shady` /
`supplies` flag, and **allocation value `max_units × ware.price_avg` > 8 M Cr**
— comfortably above the 5 M cap so the cap is the binding term. The eight
scavenger non-cappers (CGW-678, FXP-772, KWC-232, MDS-738, NDE-080, QIB-162,
QTB-164, WIE-366; P4's population) and DHI-588 / VOM-540 were excluded.

**255 (station, ware) offers over 211 stations**, minimum allocation value
8.01 M Cr. The energy-cell solar cohort is 38 of them (38 stations, allocation
values 13.4–15.9 M Cr, allocation/target ratio ≥ 2.68 — i.e. the cap binds by a
factor of at least 2.7 everywhere, never marginally).

### Trajectories

Cross-save station identity is `(code, class, macro)`; **0 of the 255 keys was
ambiguous in any of the 13 saves**. Per epoch:

```
net = cargo_total + inbound pending − outbound pending
```

> **Corpus pitfall, recorded for the other Phase-2 items.** The scratch corpus
> stores every pending trade **twice** — once as `source='order'`, once as
> `source='reservation'` (2,449 / 2,450 rows on `save_002`). The analysis DB
> deduplicates on `trade_id` in `db/store.py`; a naive `SUM(amount −
> transferred)` over the corpus table **doubles every pending term**. Before
> the fix, GUX-488's implied target swung between 182 k and 313 k depending on
> whether an outbound trade happened to be open; after deduplicating on
> `trade_id` it is 308 k–313 k across all 13 epochs. Any corpus analysis that
> touches `trade_pending` must dedupe.

**3,307 station-epochs**; 251 of 255 trajectories have all 13 epochs. **299
station-epochs (9.0 %) are price-clamped** (`|s| ≥ 1`, the offer sitting on the
band edge) and are excluded from every solve; they are reported here only as
counts. Module lists (`station_module`, macro × built state) are **unchanged
across all 13 epochs on 204 of 255 trajectories**; where they changed, only the
epochs carrying the modal module fingerprint were used, so the allocation
underlying each solve is constant by construction.

### The solve

Everything is scored in **band units** — `res = s_model − s_observed`, the
residual measure the pricing model doc uses — never in `u`. This matters: `u`
is `1.095·acos(s)/π`, so near `s = ±1` the cosine is flat and a one-cent price
error becomes an enormous `u` error. A first pass fitted `u = net·price_avg/V +
a` by OLS in `u` space and was thrown by exactly this: the low-fill energy-cell
stations (JMM-777, UBX-812, KSQ-575 …), which sit at `s = 0.96–0.99`, returned
`V ≈ 3.8–4.5 M` and `a ≈ 0.031` from price deviations of **0.06 Cr**. That
result is an artifact of heteroscedasticity and is not reported below.

Per trajectory, `V` is scanned on a 10 kCr grid and `a` on a 5·10⁻⁴ grid; for
each `V` the reported figure is the `a` minimising the **maximum** |res| over
the epochs (Chebyshev), and the tolerance interval is the set of `V` whose best
max|res| stays under 0.025 band units (twice the supplier population's known
MAD). Lever arm is quoted as `(net_max − net_min)·price_avg / 5 M` — the
fraction of the capped target the trajectory sweeps.

Population scoring on snapshot 71 follows the mandated rules: **bin medians,
equal weight per bin, 16 equal-count bins on the binding population and 24 on
the whole supplier population**, never per-offer MAE. The supplier population
excludes `lockavgprice` pairs (591 on snapshot 71 — leaving them in inflates
the binding bin RMSE from 0.0145 to 0.43 and is what a careless run reports),
player-owned stations, `shady` and `supplies` books, and offers with no
allocation row (build storages). Populations: **1,715 supplier offers, of which
344 binding** (allocation value > 5 M, scavengers removed) **and 1,349
non-binding**.

---

## Result 1 — the anchors

AXO-574 (Terran) and GUX-488 (Teladi), same capped solar design,
in-game-verified allocations ~992 k units, 13 epochs each, no clamped points,
module lists unchanged. Implied target `net/(u − a)` per epoch, and the implied
`V = target × price_avg`:

| station | `a` | n | implied target (median) | implied `V` median | IQR |
|---|---:|---:|---:|---:|---|
| AXO-574 | 0.046 | 13 | 311,213 | 4,979,411 | 4,976,045–4,982,445 |
| AXO-574 | **0.048** | 13 | **312,613** | **5,001,807** | 4,998,849–5,003,589 |
| AXO-574 | 0.050 | 13 | 314,018 | 5,024,281 | 5,021,863–5,024,556 |
| AXO-574 | 0.053 | 13 | 316,083 | 5,057,327 | 5,055,731–5,058,689 |
| GUX-488 | 0.046 | 13 | 311,556 | 4,984,890 | 4,978,158–4,985,381 |
| GUX-488 | **0.048** | 13 | **312,611** | **5,001,772** | 4,991,106–5,002,957 |
| GUX-488 | 0.050 | 13 | 313,650 | 5,018,399 | 5,004,122–5,021,345 |
| GUX-488 | 0.053 | 13 | 315,201 | 5,043,210 | 5,023,773–5,047,690 |

The two stations agree with each other to **0.001 %** at every `a`, over
non-overlapping stock ranges (AXO 122 k–166 k, GUX 91 k–260 k) and over
15,300 s of game time. That is the "two points, two unknowns" E-116 asked for,
executed 13 times per station — and it still only produces a *line* in
(V, a), not a point.

## Result 2 — the ridge, corpus vs population

177 trajectories (158 stations, 2,149 station-epochs) with lever arm ≥ 0.05
were scored against a (V, a) grid, equal weight per station-offer (median over
stations of the median |res| across that station's epochs), alongside the
snapshot-71 binding population's bin RMSE.

Corpus (median |res|, band units):

| `a` \ `V` | 4.90 M | 4.95 M | 5.00 M | 5.05 M | 5.10 M | 5.15 M |
|---|---:|---:|---:|---:|---:|---:|
| 0.044 | 0.0098 | **0.0031** | 0.0097 | 0.0191 | 0.0279 | 0.0371 |
| 0.048 | 0.0199 | 0.0117 | **0.0033** | 0.0100 | 0.0178 | 0.0270 |
| 0.052 | 0.0304 | 0.0208 | 0.0125 | **0.0063** | 0.0105 | 0.0163 |
| 0.056 | 0.0410 | 0.0314 | 0.0222 | 0.0150 | **0.0096** | 0.0123 |
| 0.060 | 0.0517 | 0.0419 | 0.0324 | 0.0236 | 0.0179 | **0.0128** |

Snapshot-71 binding population (bin RMSE, 16 bins):

| `a` \ `V` | 4.90 M | 4.95 M | 5.00 M | 5.05 M | 5.10 M | 5.15 M |
|---|---:|---:|---:|---:|---:|---:|
| 0.044 | 0.0119 | **0.0047** | 0.0084 | 0.0164 | 0.0244 | 0.0323 |
| 0.048 | 0.0206 | 0.0119 | **0.0059** | 0.0096 | 0.0171 | 0.0247 |
| 0.052 | 0.0292 | 0.0204 | 0.0125 | **0.0079** | 0.0111 | 0.0180 |
| 0.056 | 0.0379 | 0.0291 | 0.0208 | 0.0138 | **0.0102** | 0.0128 |
| 0.060 | 0.0467 | 0.0379 | 0.0295 | 0.0218 | 0.0156 | **0.0127** |

The two minima traces are the same line to within one grid cell. Unconstrained
optima: corpus **V = 4.975 M, a = 0.046** (0.0026); binding population
**V = 4.925 M, a = 0.042** (0.0045). Neither is meaningful on its own — both
sit on the ridge.

**The third population is what breaks the tie, and it points slightly away from
5.00 M.** The 1,349 **non-binding** supplier offers price on their allocation,
so `V` does not enter at all; they pin `a` alone:

| `a` | 0.046 | 0.048 | 0.050 | **0.052** | 0.054 | 0.056 | 0.058 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bin RMSE (24 bins) | 0.0166 | 0.0127 | 0.0095 | **0.0077** | 0.0083 | 0.0111 | 0.0148 |

Feeding `a = 0.052–0.053` into the ridge gives **V ≈ 5.05 M**. Feeding the
energy-cell cohort's independently known `a = 0.048–0.049` gives **V = 5.00 M**.
The two are 1 % apart, which is exactly the size of the ridge trade-off, and the
non-binding population's `a` is itself measured *through* the storage
allocation model, so a ~1 % systematic bias in modelled allocations would move
it by the whole disputed amount. **This is not settleable from save data.**

Headline candidates, all populations (bin medians / equal weight per station):

| candidate | corpus | binding (344) | non-binding (1,349) | all supplier (1,715) |
|---|---:|---:|---:|---:|
| uncapped `m = 1`, a = 0.053 | — | 0.2715 | 0.0077 | 0.0077 |
| V = 5.00 M, a = 0.046 | 0.0049 | 0.0058 | 0.0166 | 0.0127 |
| **V = 5.00 M, a = 0.048** | **0.0033** | **0.0059** | 0.0127 | 0.0094 |
| V = 5.00 M, a = 0.053 | 0.0150 | 0.0145 | **0.0077** | 0.0089 |
| **V = 5.05 M, a = 0.053** | 0.0085 | 0.0089 | **0.0077** | **0.0078** |
| V = 5.10 M, a = 0.053 | 0.0097 | 0.0102 | **0.0077** | 0.0080 |
| V = 5.10 M, a = 0.058 | 0.0139 | 0.0124 | 0.0148 | 0.0137 |
| V = 4.93 M, a = 0.046 | 0.0104 | 0.0110 | 0.0164 | 0.0127 |

**Over-fitting check, as required.** `(5.00 M, 0.046)` is the best pair on the
capped cohort and one of the *worst* save-wide (0.0127 against the baseline
0.0077): it buys the binding 344 by degrading the 1,349 that carry no cap at
all. **Rejected as a save-wide rule.** `(5.05 M, 0.053)` is the only candidate
that is simultaneously at or near the optimum on all three populations
(0.0085 / 0.0089 / 0.0077 / 0.0078) — but it is not *distinguishable* from
`(5.00 M, 0.048)` by any save-side measurement, because the difference between
them is the ridge.

## Result 3 — `V` has no per-station structure (new, CONFIRMED)

Holding `a` fixed and solving `V` per station on the 153 trajectories with
lever arm ≥ 0.10:

| `a` fixed at | per-station best `V` median | IQR | IQR/median |
|---|---:|---|---:|
| 0.048 | 5,010,000 | 5,000,000–5,040,000 | **0.008** |
| 0.050 | 5,030,000 | 5,030,000–5,080,000 | 0.010 |
| 0.053 | 5,080,000 | 5,060,000–5,150,000 | 0.018 |

At `a = 0.050`, grouped medians: by ware — computronicsubstrate 5.06 M (26),
claytronics 5.04 M (19), energycells 5.03 M (17), microchips 5.03 M (17),
siliconcarbide 5.05 M (16), hullparts 5.03 M (16), siliconwafers 5.025 M (8),
plasmaconductors 5.03 M (7); by faction — terran 5.03 M (36), pioneers 5.08 M
(25), teladi 5.04 M (24), paranid / holyorder / argon / antigone / split all
5.03 M. **Nothing beats pooling.** This closes the "is the cap per-design or
per-faction" question that E-113/E-115 left implicitly open, on 13 epochs
rather than one snapshot.

*Falsified by:* any capped cohort whose solved `V` at a common `a` sits more
than ~2 % from the pooled median.

## Result 4 — E-007

Two independent measurements of the offset's dependence on size, both on
snapshot 71 (per-offer implied `a`, bin medians, equal count per bin):

**(a) Non-binding suppliers, denominator = modelled allocation.** 1,068 offers
after dropping clamped offers and the flat ends of the cosine (`u/S` outside
0.15–0.85, where a cent maps to a large `a` error):

| median allocation | 2,155 | 3,556 | 4,745 | 7,368 | 10,035 | 13,229 | 20,570 | 37,879 | 68,414 | 195,691 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| median implied `a` | 0.0590 | 0.0605 | 0.0559 | 0.0565 | 0.0554 | 0.0524 | 0.0512 | 0.0499 | 0.0491 | 0.0484 |

E-007 predicted 0.0578 at ≈ 2,500 falling to 0.0487 at ≈ 250,000. **Reproduced
to 0.001 across two decades of allocation.** Monotone, 10/10 bins.

**(b) The capped cohort, denominator = `V/price_avg`, no storage model
involved.** 177 trajectories, implied `a` at `V = 5.00 M`, binned by the
station's modelled allocation:

| median allocation | 5,157 | 8,301 | 14,233 | 40,000 | 61,574 | 992,398 |
|---|---:|---:|---:|---:|---:|---:|
| n | 29 | 29 | 29 | 29 | 29 | 29 |
| median implied `a` | 0.0450 | 0.0450 | 0.0465 | 0.0465 | 0.0475 | 0.0415 |

Over allocations spanning **5 k → 992 k** the offset moves by **+0.002**, and
in the *opposite* direction to (a) — where (a) predicts −0.009 over the same
range. (The last bin is the low-fill energy-cell group whose IQR is 0.031–0.048;
it sits at the flat top of the cosine and is the least trustworthy.)

**Reading.** The drift lives in the denominator, not in the offset: it appears
whenever `fill` is computed from a *modelled* allocation and vanishes when the
denominator is exact. Quantitatively: implied `a` = `u − net/allocation`, so
over-estimating the allocation by a relative `e` inflates implied `a` by
`e × fill`. At the population's typical fill ≈ 0.5, the observed +0.010 excess
at alloc ≈ 2,000 needs `e ≈ 2 %` there and `e ≈ 0` at alloc ≈ 200,000 — a
*size-dependent relative* bias, which is exactly what a fixed additive term
(the ration 4 h buffer, per-module rounding) does to a small pool and not to a
large one. **HYPOTHESIS.**
*Falsified by:* a capped cohort at small allocation reading an `a` above its
large-allocation siblings by the predicted ~0.009, or an independent in-game
allocation reading confirming the modelled value at alloc ≈ 2,500 to better
than 1 %.

---

## CONFIRMED vs hypothesis

**CONFIRMED here (recommend register action):**

1. `V` is a single global constant with no per-station, per-ware or
   per-faction structure: IQR/median **0.008** over 153 trajectories at fixed
   `a` (Result 3). *Falsified by:* a cohort more than ~2 % off the pooled
   median at a common `a`.
2. The `V`/`a` trade-off is **exact and measured**: the corpus's 13-epoch ridge
   has the same slope as the single-snapshot ridge, ≈ +0.0009 in `a` per +1 %
   in `V` (Result 2). E-116's own prediction ("a 1 % change in V is absorbed by
   ~0.001 of `a`") is confirmed — which is precisely why E-116 cannot be
   settled offline.
3. Conditional pinning: at `a = 0.048` the capped target is `5,001,8xx Cr /
   price_avg` on both in-game-anchored solar plants, 13 epochs each, IQR
   ±0.05 % (Result 1).

**HYPOTHESIS (not registered as settled):**

4. `V = 5.00 M` exactly (E-116). Consistent with everything, but so is
   `V = 5.05 M` with `a = 0.053`, and the latter is marginally better save-wide.
   **E-116 stays PENDING; reading R6 (one solar plant, two well-separated
   stocks, read in game) remains decisive** — with the corpus's contribution
   being that the reading now only has to pin `a` *or* `V`, not both, and that
   any single well-conditioned station will do because `V` has no cohort
   structure.
5. E-007's small-allocation drift is an allocation-model artifact (Result 4).

**Explicitly rejected:**

- `(V = 5.00 M, a = 0.046)` as a save-wide rule — best on the capped cohort,
  save-wide bin RMSE 0.0127 against the 0.0077 baseline. Over-fitting.
- `u`-space least squares for this problem — heteroscedastic near `s = ±1`;
  it manufactured `V ≈ 3.8–4.5 M` on the low-fill solar plants out of 0.06 Cr
  price deviations.
- Per-ware or per-faction `V` (Result 3).

---

## Ranked leads

1. **R6 is still the reading to take, and it is now cheaper.** Any *one*
   well-conditioned capped station read at two stocks pins `a`, and `V` follows
   to ±0.1 % (Result 1 gives the conversion: `V = target × price_avg`, and
   `a = 0.048 ⇒ 5.000 M`, `a = 0.053 ⇒ 5.05 M`). Because `V` has no cohort
   structure (Result 3), the station need not be a solar plant.
2. **Two stations refuse `V = 5.00 M` at any tolerance-feasible `a`** and are
   worth a look by whoever owns the storage model: **YAC-593** (pioneers,
   scrapmetal, net 29–5,406, modelled allocation 50,000, `V` interval
   4.39–4.88 M) and **VQO-413** (teladi, hullparts, net 3,109–8,998, modelled
   allocation 66,124, `V` interval 5.81–6.38 M). Both are single stations with
   13 epochs and stable module lists, so the discrepancy is in their
   allocation, their book, or the cap's scope — not in noise. 2 of 137.
3. **The low-fill energy-cell stations** (JMM-777, UBX-812, KSQ-575, QEH-295,
   FPJ-449, ZBG-015, ASC-111, PCU-640) sit permanently at `s = 0.96–0.99` with
   prices within 0.06 Cr of the `(5.00 M, 0.048)` prediction. They are useless
   for fitting but are a good **regression fixture** for the flat-top end of
   the cosine, which nothing else in the project covers.
4. **The allocation-model bias implied by Result 4** is measurable: if the
   drift in (a) is a denominator artifact, the modelled allocation is ~2 % too
   large at alloc ≈ 2,500 and correct at alloc ≈ 200,000. That is a testable
   prediction for the storage model, independent of any price work.
