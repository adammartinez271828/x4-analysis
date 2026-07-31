# The 5 M cap's scope, and the scavenger "storage scale error" — 2026-07-30

Plan item **P4** of [../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md)
plus the offline half of **E-059**. Everything below was derived on analysis-DB
snapshot **`save_id` 71** (`save_002`, game time 82,688; resolved from
`current_save`, not hardcoded) and on the 13-save archive corpus built in Phase 1
(game time 69,324–84,643). Nothing under `src/` or `tests/` was touched; no
register, reference or model doc was edited by this pass — the recommendations at
the end are for the Phase 4 docs-sync owner.

**Headline.** The 5 M credit cap (E-113/E-114) comes out of this *stronger*, not
weaker: it now has 13-epoch multi-fill confirmation on 60+ stations and, newly,
it is confirmed **above** the capped target, which kills the leading scope
candidate. The apparent counterexamples split into one clean, previously
unnoticed population — **a ware the station itself consumes never prices at the
band minimum** — and one residual station, DHI-588. And the reported
"1.21–1.30× scavenger storage scale error" is **withdrawn**: it was an artifact
of holding the offset `a` at +0.053, and the corpus 2-parameter solves plus
KWC-232's in-game-verified allocation put the storage model back in the clear.

---

## 0. Method and conventions

- Supplier-side offer = the station posts a `sell` for the ware, flags carry
  neither `supplies` nor `shady`, and the storage model has an allocation row
  (`station_storage`, `role != 'supply'`).
- Net position = `cargo + undelivered inbound − committed outbound`, with the
  per-pending remainder floored at zero. Two data traps were hit and fixed:
  a purged trade with `amount = 0, transferred = 5166` (DJQ-075) makes a naive
  `amount − transferred` *add* stock, and the **corpus stores every pending
  trade twice** (`source = 'order'` and `'reservation'`), so corpus nets are
  deduplicated on `trade_id` (warning relayed from the P2 agent; all corpus
  numbers here were produced after the fix).
- Predictions use the confirmed closed form, `u = net/T + a`,
  `s = cos(π·clamp(u/1.095, 0, 1))`, `a = +0.053`.
- **Scoring is in band units, not `u`.** Error = `(observed − predicted) /
  half-spread` on the observed side. The `u`-space residual is unusable near the
  clamps (a 4-cent price difference at the band minimum manufactures a residual
  of 2–5), and every "×5 off" figure in earlier triage notes is that artifact.
- Bin-median scoring per the plan's ground rules: 20 **rule-independent** bins on
  `fill = net/allocation` over [0, 1.2], median \|error\| per bin, RMS over bin
  medians, equal weight per bin. Rules are scored on the whole supplier book and
  on every sub-cohort, both reported.
- Player-owned stations are reported separately: 6 of them carry manual
  `ware_limit` rows and/or `price_setting` overrides (MXH-411 has both), so their
  offers are not evidence about the economy price book either way.

---

## 1. Census on snapshot 71

| population | n |
|---|---:|
| supplier-side offers with an allocation | 2,351 |
| … of which the (station, ware) is on the station's `lockavgprice` whitelist | **585** |
| main-book supplier offers | 1,766 |
| … with allocation value > 5 M Cr (the cap can bind) | **385** |
| … with net > 0 | 376 (363 NPC-owned) |
| … net **below** the capped target `V/price_avg` | 323 (314 NPC) |
| … net **above** the capped target ("saturated") | 53 (49 NPC) |

The 585 `lockavgprice` rows matter: they are pegged at band average (sell = avg,
buy = avg − 1, E-025) and they account for **every** "prices at exactly band
average, fits neither curve" row in the triage, RAN-388 included (§ 5). Leaving
them in the census is what made the anomaly look larger than it is.

### Classification of the 385

Resolution-aware (the two hypotheses must differ by more than 4 × the 0.0125
supplier MAD before an offer is allowed to vote):

| class | n | meaning |
|---|---:|---|
| capper | 217 | capped prediction wins, resolvably |
| capper (cap predicts the clamp, observed is clamped) | 31 | cap-consistent only |
| unresolved (the two predictions differ by < 0.05 in `u`) | 111 | no vote |
| non-capper, cap does not clamp | 3 | DHI-588 ×2 + ABR-398 (player) |
| **non-capper, cap predicts band min and the price is above it** | **22** | the anomaly |
| clamped low with no model support | 1 | RNJ-168 (§ 6) |

Below the capped target the cap is in excellent shape: **7 of 323** offers miss
the capped curve by more than 5 % of the half-spread, and two of those seven are
DHI-588's.

---

## 2. The scope test — what survives

All rules scored on NPC-owned offers, bin-median RMS of \|error\| in half-spread
units (lower is better). `T` is the price-target denominator.

| rule | whole book (1,691) | > 5 M (363) | saturated (49) | saturated, self-consumed (19) | saturated, not (30) | below target (314) |
|---|---:|---:|---:|---:|---:|---:|
| R0 no cap, `T = allocation` | 0.0342 | 0.3270 | 0.4172 | 0.4730 | 0.4245 | 0.3047 |
| **R1 cap always (E-113)** | **0.0315** | 0.3595 | 0.6727 | 0.8772 | **0.0000** | **0.0144** |
| R2 cap only while net ≤ capped target | 0.0333 | 0.1497 | 0.4172 | 0.4730 | 0.4245 | 0.0144 |
| R3 cap except the scavenger faction | 0.0315 | 0.3379 | 0.6535 | 0.8506 | 0.0000 | 0.0145 |
| R4 cap except self-consumed wares (always) | 0.0315 | 0.1396 | 0.2305 | 0.4730 | 0.0000 | 0.0303 |
| **R5 cap, self-consumed reverts to `allocation` above the target** | **0.0315** | **0.1391** | **0.2305** | 0.4730 | **0.0000** | **0.0144** |

Readings:

- **The cap is confirmed above the target, not just below it.** On the 30
  saturated NPC offers that are *not* self-consumed the capped curve's bin-median
  error is **0.0000 in all seven bins** — all 30 sit at exactly the band minimum —
  while the allocation curve scores 0.4245.
- **Candidate (i), net-position saturation, is FALSIFIED.** Its falsifiers are
  the offers whose fill is only 0.51–0.94 while the net is already past the
  capped target: CAC-761 siliconwafers (fill 0.813, allocation curve says 204.72,
  observed **180.00** = band min), MBP-961 superfluidcoolant (0.639, says 125.77,
  observed 90.00), PAC-481 fieldcoils (0.512, says 403.92, observed 247.00),
  TFH-220 antimattercells (0.531, says 193.52, observed 121.00), XXF-947 (0.831,
  135.40 vs 121.00), DRN-534, QFO-450, OHU-068, SZE-818, AOY-922. Reverting to
  the allocation above the target is off by up to a full half-spread on these.
- **Faction (R3), station design/macro and sector are all falsified.** Every
  grouping contains both cohorts: scavenger IRD-672 caps cleanly while eight
  other scavengers do not; kaori BPR-268 caps while kaori DHI-588 does not;
  teladi, pioneers and split appear on both sides; `station_gen_factory_base_01_
  macro` is the modal macro on both sides; Avarice (cluster_500) holds four
  cappers (IRD-672, ANY-260, IDZ-231, AWU-079) and eight non-cappers.
- **Produces-vs-resells is falsified again**, and in the opposite direction from
  E-115's phrasing: what matters is not whether the station *makes* the ware but
  whether it *eats* it (§ 3).
- **Tide phase / game time is falsified.** Across the 13 corpus epochs
  (15,319 s of game time) the eight scavengers' energy-cell prices move only with
  their own net (CGW-678 11.33 → 11.54 → 11.40 as its net moves 1.089–1.128 M;
  NDE-080 17.80 → 14.08 monotonically as its net grows 528 k → 743 k). No
  periodicity, no epoch-keyed level shift.

---

## 3. What actually separates the two cohorts: **the station consumes the ware**

Define a ware as *self-consumed* by a station when any of the following holds:
it is an input to one of the station's own production recipes (`module_ref` →
`recipe`); the station has a built `buildmodule*` and the ware is a build
resource; or the ware is a ration of a race present in the station's workforce.

Among the 49 saturated NPC offers:

| | at exactly band min | above band min |
|---|---:|---:|
| **self-consumed** | **0** | **19** |
| not self-consumed | **30** | **0** |

A perfect split, with no tuned parameter. The 19: energy cells at CGW-678,
FXP-772, KWC-232, MDS-738, NDE-080, QIB-162, QTB-164, WIE-366 (scavenger),
YAC-593 (pioneers), PKM-304 (teladi); scrap metal at CGW-678, FXP-772, NDE-080,
PKM-304; silicon at AKE-218; hull parts at ULG-519 (consumed by its XL build
module); microchips at EWQ-469; teladianium at VNM-914; medical supplies at
DIS-888 (eaten by its own 1,991 argon workers). The two player exceptions,
MXH-411's computronic substrate and silicon carbide, are also self-consumed —
it runs a Terran ship-build module — and ABR-398's scrap metal is the one row
this rule does not cover (player-owned, manual `max` limits; see § 0).

**Below** the capped target the exemption does *not* apply: all 51 self-consumed
sub-target offers fit the **capped** curve (errors 0.008–0.019 of half-spread)
and are wildly wrong on the allocation curve (up to −0.94). That is why R4 (a
blanket exemption) degrades the below-target cohort from 0.0144 to 0.0303 while
R5 (exemption only above the target) is neutral everywhere else.

### The form the exempted offers take

They do **not** land on the allocation curve with `a = +0.053` either (R5's 0.4730
on that cohort). Solving each for its offset with `T = allocation` gives a
*negative* `a`: energy cells −0.108 to −0.153, scrap metal −0.015 to −0.071,
silicon −0.162, hull parts −0.208.

The one station where the answer is independently checkable settles it:
**ULG-519's** buy-only production inputs read a per-station input constant of
**−0.202, −0.203, −0.202** (antimatter converters, engine parts, missile
components — E-011's per-station constant), and its saturated hull-parts *sell*
offer reads **−0.208**. Predicting its price from `T = allocation`, `a = −0.203`
lands within **0.014** of the observation, against +0.348 (allocation, +0.053)
and +0.355 (capped). EWQ-469 (−0.015 with its measured input constant) and
VNM-914 (−0.080) point the same way; the eight scavengers have no production
inputs to buy, so their input constant is unobservable and the −0.11…−0.15 they
imply can only be called *consistent* with E-011's range (0 to ≈ −0.78 h of
consumption), not fitted.

**HYPOTHESIS (new).** *The supplier book applies until it would clamp the price
at the band minimum. If the station itself consumes the ware, the price does not
clamp: it falls onto the consumer book instead — target = the storage allocation,
offset = the station's own input constant.*
*Falsified by:* any self-consumed supplier offer sitting at exactly the band
minimum with net above the capped target, or any non-self-consumed one above the
band minimum in that region without a manual price/limit override. Neither
exists on snapshot 71 (0/19 and 0/30).
*Not yet a model:* the scavengers' input constants are unmeasured, so the rule
predicts *that* their price stays off the floor, not *where* it lands.

---

## 4. The scavenger "1.21–1.30× storage scale error" is withdrawn

The § 5 lead in [price-categories-2026-07-29.md](price-categories-2026-07-29.md)
and finding 2 of the triage read the eight stations' prices as implying a storage
allocation 1.21–1.30 × the modelled one. That inference assumed `a = +0.053`.
Three independent lines say the storage model is right and the offset is what
moved:

1. **KWC-232's energy-cell allocation is player-verified in game at 1,833,000**
   (E-044's dual-role reading); the model gives **1,833,247** on snapshot 71 and
   its module set is unchanged across all 13 epochs. Its offers imply 2,212,257
   under `a = +0.053` — 1.207 × a number the player read off the Logical Station
   Overview. The scale error cannot be storage at KWC-232.
2. **Corpus 2-parameter solves.** Fitting `u = net/T + a` over the 13 epochs on
   the series with real leverage returns `T ≈ the modelled allocation` with a
   negative offset: NDE-080 energy cells `T = 974,648` vs modelled 960,935
   (**1.014×**), `a = −0.099`, rms(u) 0.0009 over a 528 k–743 k net range;
   PKM-304 energy cells `T = 852,643` vs 946,006 (0.90×), `a = −0.168`, rms
   0.0029 over 346 k–562 k; CGW-678 scrap metal `T = 29,804` vs 30,000
   (**0.993×**), `a = −0.039`; NDE-080 scrap metal `T = 30,008` vs 30,000
   (**1.000×**), `a = −0.034`; FXP-772 scrap metal `T = 20,248` vs 20,000
   (1.012×), `a = −0.060`. Neither series shows the stale-price repeats the P2
   agent warned about (prices move monotonically with net at every epoch).
   The 1.2–1.3× figures survive only on the series with *no* leverage (net
   varying by 0–3 % across 15,000 s), where `T` and `a` are not separable.
3. **The same stations' other wares are fine.** Their hull-parts and claytronics
   series fit the *capped* target across 13 epochs with `a` at the supplier value
   — claytronics `T` = 2,384 / 2,418 / 2,400 / 2,414 / 2,428 / 2,372 against the
   cap's 5 M/2,040 = **2,451**, hull parts 24,438 and 23,895 against 5 M/209 =
   **23,923**. If the Avarice sunlight, the recycler multi-queue split (E-046) or
   the storage-module tag grouping (E-122) were mis-modelled at these stations,
   those rows would be off too. They are not.

So the storage-side hypotheses the plan listed for the 1.21–1.30× scale
(Avarice sunlight, recycler multi-queue handling, storage macros/tag groups,
dual-role edge cases) are **not tested against a real target** — there is no
longer a scale to explain. No allocation change was proposed, so the
`tests/readings.py` constraint (≥ 131/132, IRD-672's six readings included) is
untouched by this item.

**And the two halves stay separate.** Even at 1.3 × the modelled allocation the
capped target for energy cells is 5 M/16 = 312,500 units, so at nets of
0.68–1.79 M the cap still demands the band minimum. **No allocation fix of any
size can explain a non-clamped price there** — that half is pricing, and § 3 is
where it lives.

---

## 5. RAN-388 — `lockavgprice`, not a cap counterexample

RAN-388 (Boron trade station, `station_bor_tradestation_base_01_macro`, not known
to the player) carries **all 23 of its traded wares on its `lockavgprice`
whitelist**, nividium and claytronics included. Its offers are the E-025 book to
the credit: nividium sell 510.00 / buy 509.00 against a band average of 510;
claytronics sell 2,040.00 / buy 2,039.00 against 2,040. It is not a discriminator
for the cap and never was, and the same applies to the whole "prices at exactly
band average" group the first census turned up (FEL-543, EBT-957, JBE-269,
TTV-091, ZAA-170, UVM-983, DAN-547, WSS-605 …) — all `lockavgprice`. Nothing
here is Boron-specific and one station would not have supported such a claim
anyway. This closes the last live item on E-115's stale "needs" list.

---

## 6. What is left open

- **DHI-588 remains the one clean below-target counterexample.** Silicon: net
  12,460 against a capped target of 45,045 and an allocation of 56,667 (in-game
  verified), observed **144.49**, capped predicts 139.40, allocation predicts
  144.18 — an error of +0.255 half-spreads against the cap and **+0.016** against
  the allocation. Claytronics: observed 2,223.59, capped 2,180.34, allocation
  2,219.07 (+0.141 vs +0.015). It consumes neither ware (no production modules;
  neither is a ration of its argon/paranid/teladi workforce), so § 3's rule does
  not reach it. Contradiction (8) stays open — but it is now **one station, two
  offers**, not a cohort, and the producer-side "counterexamples" that widened it
  in the triage have been re-absorbed.
- **Three below-target offers price *under* the capped curve** — PSB-706
  claytronics (−0.244 half-spreads), PTZ-931 hull parts (−0.201), WLC-614
  microchips (−0.136) — a different anomaly, unexplained, n = 3.
- **RNJ-168** (argon, energy cells) posts the band minimum at fill 0.143 with
  both curves predicting ≈ 21. Almost certainly a per-station price setting;
  worth one look by whoever implements the price model.
- **The consumer-book branch has no closed form** until per-station input
  constants (E-011) are modelled, because that is the offset it uses.

---

## 7. E-059 (offline half) — ULG-519

ULG-519 (split, Family Zhin) is confirmed hybrid on 71: `buildmodule_gen_ships_
xl_macro` + 10 production modules (4 × energy cells, 3 × hull parts, 2 × refined
metals, 1 × graphene), 2,500 workforce.

**It is not on the computed path today.** `analysis/storage.py` excludes any
station with a build module from the producer model, so all four of its produced
wares carry `source = 'proxy'` rows. The snapshot-71 comparison the plan asked
for is therefore vacuous by construction — the proxy *is* `stock + inbound +
open buy`, so `computed / derived = 1.000` for all four wares, and comparing a
snapshot-71 proxy against other epochs' bounds only measures stock drift.

The informative test is what the computed path *would* produce. Reconstructing
the equal-hours split from its module set (container pool 3,000,000 m³, ration
volume 104,100 m³, Σ flow×volume 373,008 m³/h ⇒ 7.764 h) gives **hull parts
37,452** against a derived lower bound of **61,494** — a bound that is identical
in all 13 corpus epochs, i.e. the station has been pinned full for 15,300 s. The
code's own note records the same comparison from save_009 with the production
model's exact number, **45,044 against 61,494**. Either way the computed value
is **below** the offer-derived lower bound, which by the lower-bound rule is a
**real error**. Energy cells (1,028,527 vs 214,606), graphene (20,030 vs 4,349)
and refined metals (72,668 vs 26,787) come out far above their bounds and prove
nothing, as expected.

**Conclusion for E-059:** the computed path *as currently formulated* is
**refuted** for hybrids — it cannot see the build module's draw, so the ware the
build module eats is under-allocated by ≥ 27 %. This does not refute "hybrids
belong on a computed path" in principle; it says the denominator must include
build demand before they can be moved onto one (the same missing quantity P8 is
constructing). The current proxy treatment is not wrong so much as
unfalsifiable, and it is right that the exclusion is deliberate rather than
accidental. An in-game reading of ULG-519's hull-parts maximum would still be
needed to *confirm* any replacement.

---

## 8. Recommendations for the docs-sync owner (Phase 4)

Nothing below has been applied; register ids are the next free ones as of this
writing.

1. **E-113 / E-114 — keep CONFIRMED, strengthen the evidence.** New: the cap is
   confirmed *above* the capped target (30/30 saturated non-self-consuming
   supplier offers sit at exactly the band minimum, bin-median error 0.0000,
   against 0.4245 for the allocation curve), and multi-fill corpus solves recover
   `T` within 1–3 % of `V/price_avg` on independent stations (IRD-672 305,810;
   GUX-488 308,456; AXO-574 303,182; claytronics 2,372–2,428 vs 2,451; hull parts
   23,895 / 24,438 vs 23,923 — implied `V` 4.85–5.05 M).
2. **New entry (proposed) — the self-consumption exemption**, status
   **PENDING (hypothesis, strong)**: *"A supplier offer for a ware the station
   itself consumes — as a production input, a build resource, or a ration for a
   race in its workforce — never clamps at the band minimum; above the capped
   target its price leaves the supplier book for the consumer book (target =
   allocation, offset = the station's input constant)."* Evidence: the 19/30
   split above; ULG-519's −0.208 sell offset against its own −0.202/−0.203 input
   constant, predicting its price to 0.014 half-spreads. *Settled by:* an
   in-game read of any Avarice recycler's energy-cell price together with its
   production-input prices, which would expose that station's input constant.
   *Falsified by:* the two counts above becoming non-zero.
3. **New entry (proposed) — net-position saturation, status FALSIFIED**, with the
   falsifier list from § 2 (CAC-761, MBP-961, PAC-481, TFH-220, XXF-947 …). This
   belongs in the station-pricing model's *rejected* table so it is not re-tested.
4. **E-115 — refine.** The selector is not only "the station posts a sell offer";
   the exemption in (2) is a second predicate. Its "needs" list is stale in full:
   EOX-322, GMJ-316 and MOP-635 no longer hold a qualifying ware, and RAN-388 is
   `lockavgprice` on both of its (§ 5) — that route is dead, not pending.
5. **Contradiction (8) — narrow, do not close.** The producer-side widening
   recorded in the triage is withdrawn (those stations are the § 3 population);
   what remains is DHI-588's two offers, still preferring the allocation over the
   cap by 0.24 / 0.13 half-spreads on in-game-verified allocations, with no
   self-consumption to explain it.
6. **Retire the "scavenger/Avarice allocation scale error"** from
   price-categories-2026-07-29.md § 5's open-questions list and from the plan's
   unmodelled-areas table, per § 4 — with the note that the withdrawal came from
   freeing `a`, not from any change to the storage model. `docs/reports/` is
   append-only, so this document is the retraction; the register and the models'
   rejected tables are where it should be recorded.
7. **E-059 — move from PENDING to a sharpened statement**, per § 7: the computed
   path is refuted for hybrids as currently formulated (computed 37,452–45,044
   below a 61,494 derived bound on ULG-519's hull parts), and the blocker is
   build demand in the denominator, which ties it to P8 rather than to a reading.
8. **E-025 / `lockavgprice`** — no change needed, but § 5 is worth citing as the
   reason a "prices at band average" observation is never evidence about the
   supply curve.

## Reproduction

Scratch scripts (job dir, not the repo): `census2.py` (census + classification),
`implied.py`, `refuters.py`, `fillbias.py`, `floor.py`, `dualrole.py`,
`score.py --npc` (the rule table), `traj.py` / `fits.py` (corpus trajectories and
the four-model fits), `offset.py` / `consumerbook.py` (the offset test),
`e059.py` / `ulg_computed.py` (E-059).
