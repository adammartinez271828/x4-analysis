# High-value in-game readings — 2026-07-29

The player-side half of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md): every
open storage/pricing item that needs (or is materially accelerated by) an
in-game reading, ranked by information gained per reading. Every number below
was computed on the **current snapshot, `save_id` 71** (`save_002`, game time
82,688); nothing is carried over from the rotated save-70 figures. Prediction
arithmetic uses the confirmed closed form
`price = avg + s·(max−avg) [s ≥ 0] / avg + s·(avg−min) [s < 0]`,
`s = cos(π·clamp((net/target + a)/1.095, 0, 1))`, with the target and `a`
stated per hypothesis.

Each reading states whether it is the **ONLY ROUTE** to settle its claim, or
an **ACCELERATOR** for something the autonomous plan can also reach. Offer
prices in the save carry the supply/demand term only; the panel applies the
reputation discount on top and rounds percentages up (E-020/E-030) — where a
price is to be compared, read the **offer price**, not the panel percentage.

---

## R1 · VOM-540 (Tidebreak, Avarice I) — sell ~118 Protectyon, read the sell price — **ONLY ROUTE** (E-117, feeds contradiction 8)

**Why only-route:** VOM-540's condensate stock has never left the 1–22 range
in the DB's entire recorded history (19 stock events spanning game time
397–79,057; stock is 22 now, was 23 on save 70). At stock ≤ 22 the two live
hypotheses differ by only 20–30 Cr and the `a` trade-off absorbs that; no
archived save reaches the discriminating region. Only the player can move the
stock.

**Action:** sell ~118 Protectyon (stock → ~140), read the **sell** price
(current offers: sell 27,277.26, buy 27,276.26 — the buy = sell − 1 pair as
usual). Note the exact stock at the moment of reading.

**Predictions (snapshot-71 recomputation, band 22,500/25,000/27,500):**

| stock | 5 M cap: target 200, a = 0.048 | E-018: target 173.1, a = 0.021 | uncapped: alloc 5,000, a = 0.053 |
|---:|---:|---:|---:|
| 22 (now) | 27,247.51 | **27,277.71** ← observed 27,277.26 | 27,466.18 |
| 100 | 24,996.41 | 24,634.08 | 27,445.37 |
| **140** | **23,639.91** | **23,189.50** | **27,432.80** |
| 173 | 22,833.15 | 22,557.01 | 27,421.46 |

At stock 140 the cap and the fitted target are **450 Cr apart** — ~18× the
panel's ~25 Cr resolution — and the uncapped allocation is another 3,800 Cr
away (it is refuted by any material move at all). Note the honest state at
stock 22: the observed price currently sits on E-018's *fitted* two-parameter
solution, 30 Cr off the zero-parameter cap; that is exactly the m/`a`
degeneracy the mid-curve reading breaks.

**Settles:** whether the engine carries a credit-value cap (m) or a bespoke
target with its own offset (a) — the open question 3 of
[station-pricing-model.md](../models/station-pricing-model.md) — and adds the
second non-producer capper/non-capper datum to contradiction (8).

---

## R2 · NDE-080, CGW-678, KWC-232 (Avarice) — Logical Station Overview energy-cell storage maximum — **ONLY ROUTE for the storage half** of the scavenger anomaly (feeds contradiction 8)

Eight scavenger stations price their energy cells as if their allocation were
1.21–1.30× the modelled value, at net positions (0.68–1.79 M units) where the
5 M cap would clamp the price to band-min 10.00 — observed 11.27–15.10. The
allocation ground truth is not in the save; one LSO maximum per station splits
the anomaly:

| station | modelled allocation (H-B: model right) | price-implied target (H-A: storage input wrong) | observed price | cap prediction |
|---|---:|---:|---:|---:|
| NDE-080 | 960,935 | 1,244,154 (+29.5 %) | 15.10 | 10.00 |
| CGW-678 | 1,128,024 | 1,396,668 (+23.8 %) | 11.40 | 10.00 |
| KWC-232 | 1,833,247 | 2,212,257 (+20.7 %) | 11.27 | 10.00 |

The two hypotheses are 21–30 % apart — far beyond UI resolution. **Read any
one; read two to check the error is a constant scale** (the storage model's
own diagnostic: constant scale ⇒ capacity or throughput input, constant shift
⇒ pricing).

**What it settles / what it can't:** max ≈ implied ⇒ a storage-input error
(Avarice capacity/throughput) *plus* a cap-scope hole; max ≈ modelled ⇒ the
allocations are right and the whole anomaly is pricing. **Either way the cap
fails on these eight** — even the implied targets exceed the 312,500-unit
capped target, so the reading cannot rescue the cap here; it directs the
autonomous P4 analysis. Sister station IRD-672 needs no reading: its
allocation is already in-game-verified (1,665,000) and its price sits on the
cap (implied target 315,619 vs 312,500, +1.0 %).

**ACCELERATOR for the pricing half** (P4 runs regardless), **ONLY ROUTE for
the allocation half**.

---

## R3 · EIJ-609 (Holy Order fab) — hull-parts storage maximum, third read — decides between two live hypotheses (E-051 vs E-053)

Its production rate follows the reported efficiency 1.12634 exactly while the
allocation read 34,829 twice — the model (efficiency basis) says **37,227.6**
on snapshot 71. Two competing explanations, directly separated by one number:

| reading | supports |
|---:|---|
| ~37,228 (drifted up) | E-051: allocation is recomputed lazily and has now caught up |
| 34,829 (unchanged) | E-053: war-pressure efficiency never enters the allocation (vanilla-basis 1.0) |

**ACCELERATOR with a conditional only-route:** plan item P6 checks the
archived corpus first — if EIJ-609's efficiency has been 1.12634 with a static
implied allocation across all 13 epochs (~20,000 s), the lag is falsified
offline and this reading merely confirms; if the corpus shows a recent
efficiency step, this third read becomes the only decisive route.

---

## R4 · CCN-497 (Holy Order, one station visit, two timed readings) — the input-offset mechanism (E-011) and the rations exception (E-015)

CCN-497 remains the extreme offset station on 71 and posts everything needed
in one place:

| ware | side | price now | fill now | implied `a` |
|---|---|---:|---:|---:|
| graphene | buy (input) | 186.58 | 0.827 | **−0.388** |
| refined metals | buy (input) | 202.95 | 0.529 | **−0.400** |
| medical supplies | buy (ration) | 64.35 | 0.566 | **+0.006** |
| soja husk | buy (ration) | 31.36 | 0.559 | **+0.006** |
| energy cells | buy (input) | 22.00 = band max | 0.127 | clamped, bound only |

**Action:** read graphene and medical-supplies buy prices *and their stocks*
twice, ~5 and ~30 minutes apart (LSO gives stock; trade panel gives price).

**E-011 (is the −0.039-family offset a per-module input reserve?):** a reserve
moves the price **continuously with stock**; a station constant holds the
implied `a` fixed while only fill moves it. Two (stock, price) pairs invert to
two implied `a` values: same to ±0.01 ⇒ reserve refuted at this timescale;
drifting with the stock drawn down ⇒ reserve supported. (Plan item P3 runs the
same test on hours-apart corpus epochs; this reading adds the fine timescale
the corpus cannot see.)

**E-015 (do rations escape the station constant?):** at medical supplies' fill
0.566, the station-constant hypothesis (a = −0.39 shared by all its buys)
predicts **86.12**; the role/predicate-keyed hypothesis predicts **64.38**;
observed **64.35** — a 22 Cr separation on a 23 Cr half-band. The save already
shows this same-snapshot (plan P3 settles it save-wide); the in-game read is
the belt-and-braces confirmation with a directly-read allocation.
**ACCELERATOR.**

---

## R5 · Player-built two-race station — the employment-target race split (E-128, contradiction 9) — **ONLY ROUTE**

DHI-588 (in game) demands the LIVE workforce mix; DCO-580 (save-derived,
re-verified on 71: derived bofu 225 > live-mix 221, water 405 > 398 —
lower-bound logic makes that an outright refutation) demands its HABITAT mix;
the save holds no third discriminating station, DCO-580 is not player-visible
(`knownto` NULL on 71), and no station in the corpus has a habitat race set
differing from its workforce race set. The implemented live-mix rule is
known-wrong at DCO-580.

**Design:** on a player production station (fixed employment target `T` = Σ
production-module `workforce max` — read "Employment target" in the Workforce
tab first), build habitats of **two races with different rations**, e.g.
`hab_arg_s` (250) + `hab_par_s` (333), and read the ration storage maxima
**while the habitats are still filling**, when live mix ≠ capacity mix. Leave
the ration wares on automatic limits (a manual `ware_limit` overrides the
allocation and voids the test — this is why MXH-411 can't be used as-is).

**Prediction formulas** (rates per head per hour: argon food rations 2.25,
medical 1.35; paranid soja husk 1.44, medical 1.35; boron bofu 0.45, water
0.81, medical 0.99 — from `workunit_busy`, amount per 200 workers per 600 s):

```
head[race] = floor(T × share[race])        share = live mix  |  habitat-capacity mix
max[ration] = Σ_races floor(rate × head[race] × 4 h)
```

Worked example at T = 1,000, argon/paranid habitats (250/333 capacity), read
when 200 argon / 50 paranid live aboard:

| ware | LIVE mix (heads 800/200) | HABITAT mix (heads 428/571) |
|---|---:|---:|
| food rations (argon) | **7,200** | **3,852** |
| soja husk (paranid) | **1,152** | **3,288** |
| medical supplies (both) | 5,400 | 5,394 |

Read the two race-specific rations — they separate by ~2–3×; medical supplies
barely discriminates and is only a consistency check. (If Boron space is ever
explored and DCO-580 becomes visible, its food-rations max — live 576 vs
habitat 558 — settles it in one look instead.)

---

## R6 · AXO-574 (Earth) or GUX-488 — energy-cell sell price + stock, twice — pin V and `a` exactly (E-116, E-007) — **ACCELERATOR**

Snapshot 71 already separates the hypotheses across the two stations of this
in-game-verified design (allocations 992,398 / 994,471, both capped at
5 M/16 = 312,500):

| station | net now | observed | V=5.00 M, a=.048 | V=5.10 M, a=.048 | V=5.00 M, a=.058 |
|---|---:|---:|---:|---:|---:|
| AXO-574 | 133,133 | **17.25** | **17.26** | 17.40 | 17.09 |
| GUX-488 | 205,740 | **13.36** | **13.36** | 13.56 | 13.21 |

Plan item P2 does the per-station multi-fill solve on the archived corpus
(AXO-574's stock has ranged 2,840–493,754 historically), so this reading is
expected to be confirmation only. If P2's V intervals straddle 5.0–5.1 M, two
paused readings at well-separated stocks (ideally near 150,000 and 300,000 —
predicted 16.34/10.19 at V = 5.00 M, a = 0.048 vs 16.50/10.27 at 5.10 M)
settle it with no cohort assumptions. Settling `a` here also closes E-007's
main branch.

---

## R7 · QJI-262 (Terran wharf) — re-read the nine deployable quotes a few game-hours later, paused — **ONLY ROUTE** (E-034)

Every offline candidate for the valuation vector E has already been tested and
failed proportionality (register E-034); the vector is not in the save. Two
outcomes: the quotes **drift** ⇒ E is a sampled, time-varying engine statistic
(as hypothesised); they are **frozen** ⇒ E is static and the observed 0.1 %
cross-map sharing (E_A on QJI-262 + HLA-335 + RLP-496) needs a different
theory. Remember `buildpricefactor` may re-roll between the two looks (E-032);
note it both times (it multiplies all nine quotes uniformly, so it divides
out).

---

## R8 · EWQ-469 or DIS-888 — drone/unit capacity (`units.maxcount`) in the Info panel — **ONLY ROUTE** (E-062)

The cap is not persisted in the save; the +10-per-production-module term was
fit from a single point (MXH-411). Two clean candidates on 71, both
player-known NPC stations with many production modules:

| station | prod modules | floor: Σ `unit_storage` | floor + 10/module |
|---|---:|---:|---:|
| EWQ-469 | 23 | **273** | **503** |
| DIS-888 | 22 | **141** | **361** |

One number read; 46–61 % separation. Trivial effort, settles a one-point
hypothesis.

---

## R9 · Any full, idle player station — raise the drone build target 30 → 40, save — **ONLY ROUTE** (E-063)

If the re-imported save's `<supplies><orders>` reads **40**, it persists the
TARGET; **10**, outstanding orders. Then lower it below current stock and
check the block shrinks without scrapping drones. Settles the last open
semantics of the supply block. (Import the new save and check; the DB side is
free.)

---

## R10 · MXH-411 — check the trade-rule price slider — trivial side-check (E-035's open half)

The save stores `buildpricefactor = 1.5` for MXH-411 on 71 (outside the NPC
[0.9, 1.15] clamp). Confirm in the station's trade settings that 1.5 is the
player's own price-slider value. One look; closes the interpretation while
plan item P5 measures the NPC dynamics offline.

---

## R11 · Opportunistic — commission-tier + discount-event clamp (E-031) — **ONLY ROUTE**, do not seek out

Needs a station where a 25 % commission tier is held *while* a discount event
is active; then one ware's buy price against `0.5 × min price`. Not worth
engineering; take it if the situation arises.

---

## Readings explicitly NOT worth taking

- **DHI-588** — already read (40 readings); its non-capping is re-verified on
  71 from the save alone (silicon observed 144.49 vs uncapped 144.18 vs capped
  139.40).
- **EOX-322, GMJ-316, MOP-635** — E-115's old "needs" list; on 71 none holds
  any ware above 5 M Cr of allocation, so they no longer discriminate.
- **RAN-388** — would discriminate (nividium 10.2 M Cr, claytronics 8.9 M Cr)
  but is not player-visible, and both wares sit at exactly band average —
  likely a different book (checked offline in P4).
- **TDF-832 / GMJ-316 supplies tabs** — E-127 is settled including the
  both-terms case; the zero-amount floor is a documented limitation, not an
  open reading.

## Ranking rationale (information per reading)

R1 settles a model-form question (does the engine carry a value cap) that
three register entries hang off, with a 450 Cr / 18σ separation — and cannot
be reached any other way. R2 is the largest off-model supplier block and
directs the biggest open analysis. R3 kills one of two live hypotheses
outright. R4 attacks the price model's biggest unexplained parameter (the
−0.039 family) at a timescale nothing offline can reach. R5 fixes a
known-wrong implemented rule but costs a station build. R6–R8 are cheap and
decisive but narrower; R9–R11 are housekeeping.

---

## Addendum, 2026-07-30 — re-ranking after the Phase 2–3 analyses

*Appended, not edited: everything above is the state of knowledge on
2026-07-29 and stays as written. The eight Phase-2 reports dated 2026-07-30 and
the Phase-3 implementation moved four of these eleven readings. Register
statuses are in
[../experiments/README.md](../experiments/README.md); the per-item outcomes are
summarised at the top of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md).*

| reading | was | now |
|---|---|---|
| **R1** VOM-540 Protectyon | ONLY ROUTE, ranked #1 | **unchanged, still #1** |
| **R2** Avarice LSO maxima | ONLY ROUTE (storage half) | **withdrawn as framed** — low-value confirmation only |
| **R3** EIJ-609 third read | decides E-051 vs E-053 | **obsolete** — both entries falsified offline |
| **R4** CCN-497 timed reads | E-011 + E-015 | **optional** — E-011 falsified, E-015 confirmed offline; keep as E-015's belt-and-braces |
| **R5** player-built two-race station | ONLY ROUTE | **unchanged**, and now the *only* remaining route (corpus re-check exhausted the alternatives) |
| **R6** AXO-574 / GUX-488 | ACCELERATOR | **decisive** for E-116, and cheaper |
| **R7–R11** | — | **unchanged**; R10 gains relative value |

**R1 — unchanged, and still the highest-value reading available.** Nothing in
Phase 2 touched VOM-540: its stock has still never left the 1–22 range, the two
hypotheses still differ by only 20–30 Cr there, and the m-vs-`a` degeneracy the
mid-curve reading breaks is now *measured* rather than suspected (the (V, a)
ridge, slope +0.0009 per 1 %, unbroken by 13 epochs). Contradiction (8) has
narrowed around it: the producer-side "counterexamples" were re-absorbed, so
VOM-540 and DHI-588 are once again the only two non-producers in the ledger and
they still disagree. Predictions in § R1 stand unmodified.

**R2 — withdrawn as framed.** The premise was that eight scavenger stations
imply an allocation 1.21–1.30× the modelled one, so an LSO maximum would split
"storage input wrong" from "pricing wrong". That inference **assumed
`a = +0.053`**, and freeing `a` dissolves it: KWC-232's energy-cell allocation
is already player-verified at 1,833,000 against a modelled 1,833,247 (so the
scale error cannot be storage *there*), and corpus 2-parameter solves on the
series with real leverage return `T ≈ the modelled allocation` with a negative
offset — NDE-080 974,648 vs 960,935 (1.014×) at `a = −0.099`; CGW-678 scrap
metal 29,804 vs 30,000; NDE-080 scrap metal 30,008 vs 30,000. The 1.2–1.3×
figures survive only on the series with no leverage, where `T` and `a` are not
separable. The eight stations are now the **self-consumption exemption**
population (E-132), which is a pricing rule with no storage component. An LSO
read of NDE-080 or CGW-678 would still *confirm* the storage model on two more
stations — worth taking if the player is passing — but it is a low-value
confirmation, not a discriminator, and it is no longer "ONLY ROUTE" for
anything. **What would be worth reading in Avarice instead:** any recycler's
energy-cell price *together with its production-input prices*, which would
expose that station's input constant and turn E-132 from a classification into
a closed form.

**R3 — obsolete.** The reading was to decide between E-051 (lazy recompute) and
E-053 (war-pressure never enters the allocation). **Both are now FALSIFIED**,
and neither by this reading. E-053 lost its premise: there is no war-pressure
term inside `<efficiency>` to separate (0 of 1,630 modules exceed the ceiling
under mod-patched recipes; the mod's bonus is a post-hoc `<add_cargo>`,
E-106). E-051's prediction is contradicted by EIJ-609's own 13-epoch history —
the allocation did not drift up to ~37,228, it stepped **down** to a multiplier
of exactly 1.0 at 82,125 s and stayed there, and from 83,025 s the station
carries no `<production>` block at all, so the model's existing idle rule
reproduces 34,829 with no special case. The surviving claim (the allocation is
a *latched* snapshot, E-136) has **no reading that would settle it**: it is a
timing property, and one more number read at one more moment cannot
distinguish a latch from a coincidence. Do not spend a station visit on this.

**R4 — downgraded to optional.** Its E-011 half is spent: the reserve reading
is FALSIFIED on evidence the reading could not have produced (one `a` shared
across allocations differing 1,764×; 169 of 909 stations with a *positive*
offset), and the fine-timescale question it was designed for is answered by the
corpus, which holds CCN-497 at 11–12 clean epochs including adjacent saves
**177 s apart** with `a` flat to ±0.003. Its E-015 half is CONFIRMED offline
(bin-median 0.0045 against 0.1074 on 445 discriminating stations) — but that
test trusts the modelled ration allocation, so the reading keeps its value as
the belt-and-braces check at a *directly-read* allocation. Take it if
convenient; do not plan around it.

**R5 — unchanged, and now the last route standing.** The corpus re-check found
**zero** habitat-vs-workforce race-set mismatches in all 13 epochs across
~1,200 habitat-bearing stations, the multi-race population is still exactly
DHI-588 / DCO-580 / EMY-219, and DCO-580 is still player-unknown in the newest
save. `hab_pir_*` habitats were checked and cannot discriminate — all 78 of
them house single-race argon workforces. The design and prediction table in
§ R5 stand unmodified.

**R6 — promoted from accelerator to decisive, and cheaper than described.**
Thirteen epochs per station did *not* break the (V, a) ridge: the corpus ridge
and the single-snapshot ridge have the same slope, ≈ +0.0009 in `a` per +1 % in
`V`, and per-station V intervals with `a` free are ~23 % wide. Conditional on
`a` the answer is sharp (`a = 0.048 ⇒ V = 5.0018 M`; `a = 0.053 ⇒ ≈ 5.05 M`),
so **the reading only has to pin one of the two, not both** — and because `V`
has no per-station, per-ware or per-faction structure (E-130, IQR/median 0.008
over 153 trajectories), it need not be a solar plant: any well-conditioned
capped station read at two well-separated stocks will do. The § R6 predictions
remain correct. It settles E-007's main branch at the same time.

**R7–R9, R11 — unchanged.** Nothing in Phase 2 or 3 touched the deployable
valuation vector (E-034), the drone-pool cap (E-062), the drone-order semantics
(E-063) or the discount clamp (E-031).

**R10 — same cost, more value.** E-035's NPC half is now CONFIRMED on 871
observations, and MXH-411's stored **1.500** is the *single* value in the whole
corpus outside the [0.90, 1.15] clamp, constant across all 9 epochs it exists
for. The save cannot separate "the player's price-slider setting" from "the
clamp does not apply to player stations", and this one look closes the last
open clause of a now-confirmed entry.

**One reading not previously listed, worth noting as newly available.** E-138
(hybrid stations belong on a computed path once build demand enters the
denominator) would need an in-game read of **ULG-519's hull-parts maximum** to
*confirm* any replacement — the offer-derived 61,494 is a floor and can only
refute. It is not worth seeking out until a build-demand denominator exists to
test.
