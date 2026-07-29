# Experiment register

Every falsifiable claim this repository's documentation has made about X4's
behaviour — settled and open — with its prediction, its status, and what would
(or did) settle it. An index, not a model: the models live in
`docs/reference/`, `docs/models/` and `docs/reports/`, and every entry links
back to the section that owns it.

Scope: **player-run experiments** (in-game readings, screenshots, deliberate
actions) and **save-derived tests** (measurements over a savegame or the DB).
Out of scope: code-level regressions already locked by unit tests. In-game
readings live in `tests/data/station_readings.json` (per-station `note` fields
carry the reasoning) and are replayed by `tests/readings.py`.

## Maintenance rule

- **Adding one.** Append to the end of the relevant subsystem block with the
  next free id — ids are stable, never reused, never renumbered. An entry needs
  all five fields: claim, status, prediction (numbers where the source gives
  them; `prediction not stated` otherwise — never invent one), what settles it,
  and a citation to a document *and* section that exists.
- **Changing a status.** Edit the entry in place, keep the evidence that moved
  it, and update the summary table. A killed hypothesis becomes **FALSIFIED**
  and *keeps the evidence that killed it* — this repo has re-tested dead
  hypotheses more than once. A claim replaced by a better statement of the same
  phenomenon becomes **SUPERSEDED** and names the id that replaced it; the
  replacement is a new entry, never an edit of the old one.
- **Never** record a result the sources do not state. If two documents
  disagree, record both and flag it rather than picking a winner (§ Contradictions).
- Status vocabulary is exactly `CONFIRMED`, `FALSIFIED`, `PENDING`, `SUPERSEDED`.

## Summary

| subsystem | CONFIRMED | FALSIFIED | PENDING | SUPERSEDED | total |
|---|---:|---:|---:|---:|---:|
| Pricing (E-001…E-036) | 13 | 10 | 11 | 2 | 36 |
| Storage allocation (E-037…E-063) | 14 | 6 | 6 | 1 | 27 |
| Parser / save format (E-064…E-080) | 9 | 4 | 4 | 0 | 17 |
| Faction / diplomacy (E-081…E-084) | 1 | 1 | 2 | 0 | 4 |
| Resources (E-085…E-097) | 6 | 3 | 4 | 0 | 13 |
| Other (E-098…E-111) | 5 | 5 | 4 | 0 | 14 |
| **total** | **48** | **29** | **31** | **3** | **111** |

Seven entries carry a documented disagreement between sources; they are flagged
in place and listed at the foot of the file.

---

## Pricing

**E-001 · CONFIRMED** — The buy-side price modifier is a cosine in storage fill.
*Predicts:* `s = cos(π × fill / 1.095)`, bin RMSE 0.0124 over 5,428 buy offers (40 bins). *Settled by:* bin-median fitting with equal weight per bin. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Layer 4.

**E-002 · FALSIFIED** — The buy curve is "near-linear with knees".
*Predicts:* n/a. *Killed by:* the knees were an artifact of scoring per-offer MAE across the crowded middle of the curve; explicitly retracted. Replaced by E-001. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Layer 4.

**E-003 · FALSIFIED** — A clamped linear supply curve fits the buy side.
*Killed by:* bin RMSE 0.1207 (S 0.600, k 2.438) against the cosine's 0.0124 — a 10× loss. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Layer 4.

**E-004 · SUPERSEDED** — The sell side is a *warped* cosine, `cos(π(f/S)^k)` at S 1.125 / k 0.86.
*Replaced by:* E-005. *Predicted:* bin RMSE 0.0352 over 1,569 offers / 26 bins. *Superseded by:* the one-parameter fill offset, which beats every two-parameter alternative. *Source:* [open-items-2026-07-28.md](../reports/open-items-2026-07-28.md) § A. The sell side needs its own curve.

**E-005 · CONFIRMED** — The sell side is the *same* cosine at the same span with an additive fill offset.
*Predicts:* `s = cos(π(fill + 0.053)/1.095)`; bin RMSE 0.0087 (1 param) vs power 0.0120, warped cosine 0.0144, pure cosine 0.1180. Shift, not scale: implied `a` flat to 4 s.f. over a 3× fill range while the scale moves 8 %. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § A / § Why the offset is additive and not a rescaled span.

**E-006 · FALSIFIED** — The output/sell curve is a power law reaching the floor at fill ≈ 0.79–0.85.
*Predicted:* `1 − (u/0.766)^1.55`, MAD 0.0076 on 1,331 offers. *Killed by:* the 0.55–0.98 fill region, previously empty at the bin thresholds used; at `minn = 8` it holds 135 offers and only 8 are at the floor (0.80 → −0.79, 0.95 → −0.98). Wrong by a full 0.2 of a band through that stretch. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § The power law is falsified; original in [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Addendum 3.

**E-007 · PENDING** — The sell-side offset is exactly 0.050 and the drift to 0.058 at small allocations is a second, smaller effect.
*Predicts:* offset 0.0578 at alloc ≈ 2,500 down to 0.0487 at alloc ≈ 250,000; worth ~0.01 of a band. *Falsified by:* any single cohort at small allocation reading a stable 0.050. *Needs:* two producers of the same ware with allocations an order of magnitude apart, both read in game. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § A / § CONFIRMED vs hypothesis.

**E-008 · FALSIFIED** — There is a per-ware sell-side offset (shieldcomponents −0.158, fieldcoils −0.143, weaponcomponents −0.136, turretcomponents −0.130, advancedelectronics −0.064).
*Killed by:* on the shifted coordinate the per-ware implied `a` collapses to 0.041–0.066 across 18 wares with n ≥ 20, ordered simply by the wares' median fill (corr +0.37). Composition artifact. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § The per-ware sell offsets are a composition artifact.

**E-009 · CONFIRMED** — The production-input price offset is one constant *per station*, shared by all its inputs.
*Predicts:* within-station sd 0.0114 against between-station 0.0542 over 547 stations; CCN-497 −0.3896 (sd 0.0014), FSL-235 −0.3385, NRD-991 −0.1736, JQZ-281 −0.2511. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § B. Production inputs.

**E-010 · FALSIFIED** — The per-station input offset is price *staleness* against a per-station update timer.
*Killed by:* the timer exists — `<event event="updatetradeoffers">`, 3,555 events over 1,804 stations, period ~65 s — and does not explain it: `corr(offset, time since last update) = −0.08`, `corr(|offset|, …) = +0.04`, medians flat at −0.031…−0.053 across dt buckets, and 65 s cannot accumulate the ~0.78 h of throughput the largest offsets need (off by two orders of magnitude). Also unexplained by it: rations carry `a ≈ +0.006`. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 2 / § The price-update timer.

**E-011 · PENDING** — The input offset is a per-module input reserve, so `a ∝ 1/n_modules`.
*Predicts:* `a` = −0.083 / −0.043 at 1 and 2 modules is an exact halving. *Against:* the 1/n law predicts −0.028 at n ≥ 3 where −0.017 is observed, and `a` turns positive at n ≥ 5, which a reserve cannot do; `reserve / one module's cycle input × cycle time` spans 1,100–2,500 s over 20 wares. *Needs:* CCN-497 (1.15 h allocation, offset ~0.39 of a band) read twice, ~5 and ~30 min apart, with stock noted both times — a reserve moves the price continuously with stock. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § B / § CONFIRMED vs hypothesis.

**E-012 · FALSIFIED** — The `hacked=` station flag explains the positive-offset population.
*Predicted:* the 14 flagged stations should sit off the rest. *Killed by:* 11 with ≥ 2 unclamped input offers give median offset −0.010 against −0.042 for the other 891 and 45 % positive against 20 % — but the group spans −0.076 (IAZ-139) to +0.117 (JUK-948) at n = 11. Recorded as tested and weak, not an explanation. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § The hacked-station test.

**E-013 · FALSIFIED** — The input offset is driven by a recipe-level property.
*Killed by:* rank correlations over n = 2,696–3,085 — recipe cycle time +0.134, number of inputs +0.170, input's share of recipe input value +0.199, chain tier +0.105, inbound pending +0.017, workforce −0.061, efficiency +0.118, fill −0.001. All ≤ 0.20 and all ware-level, which cannot in principle explain a station constant. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § What it is *not* — tested and rejected here.

**E-014 · FALSIFIED** — The offset can be shipped as a lookup by production module count.
*Killed by (as a shippable law):* it improves per-offer MAD (0.0723 → 0.0560) but degrades the bin-median fit 3× (0.0213 → 0.0649). A real description of where the offset comes from, not a calibrated law. The underlying monotone relation with module count is CONFIRMED (see E-015 note; −0.083 at 1 module to +0.013 at 7+). *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Scoring the module-count rule.

**E-015 · PENDING** — The rations exception: rations sit at `a ≈ +0.006` while the same stations' production inputs sit at a station-wide negative offset.
*Predicts:* prediction not stated beyond the two offsets. *Settles it:* one habitat's ration buy price and one production input's buy price read from the same station at the same moment — same offset ⇒ the station-constant rule is universal and the ration measurement is a sampling artifact; different ⇒ the offset is keyed on ware role. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Ranked remaining leads, item 3.

**E-016 · CONFIRMED** — The +0.053 offset is keyed on *whether the station posts a sell offer* for the ware, not on ware role.
*Predicts:* input/buy-only −0.040 (n 2,763), input/buy-and-sell **+0.049** (n 94), output/sell-only +0.053 (n 1,388), food/buy-only +0.007 (n 1,837). Scored on the 117 offers where the two rules disagree: MAD 0.0156 vs 0.1800. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 3 / § A better discriminator for the § A offset.

**E-017 · PENDING** — `a = +0.05` (supplier) is the default offset and the −0.039 production-input offset is the special case.
*Predicts:* 14 condensate offers on one station design give a = +0.048, MAD 0.0053, against 0.1019 at a = 0 and 0.1896 at a = −0.039. *Falsified by:* any storage-only ware, on any station, reading the consumer offset. Evidence is thin — 14 offers, three fills quantised to fifths, one faction. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 5 / § Condensate prices on the SUPPLIER curve.

**E-018 · PENDING** — The price denominator is a per-(station, ware) *price target* distinct from the storage allocation.
*Predicts:* at Tidebreak (VOM-540) two readings one unit apart moved the price +17.41 Cr; the 5,000-unit storage allocation permits 0.67 Cr/unit and a 173-unit target predicts 19.28 Cr/unit. Solving both points exactly gives target 173.1 units, offset a = +0.021, span = 3.5 % of allocation. *Settles it:* sell ~150 Protectyon at Tidebreak — the 173-unit target predicts a collapse to the band floor at **22,500 Cr**; the 5,000-unit allocation predicts a ~100 Cr move, 27,277 → ~**27,180 Cr**. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 6.

**E-019 · FALSIFIED** — Tidebreak runs a separate price book (`shady` / `lockavgprice` / build-storage).
*Killed by:* the trade panel reads "Low Supply +9.2 %", a named supply/demand modifier of the family already confirmed on UDX-946 — it prices through the normal model. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 6 / § Two corrections to Addendum 5.

**E-020 · CONFIRMED** — The trade panel rounds the price modifier UP.
*Predicts:* panel +9.2 % where `price/avg − 1` is +9.109 % — a panel percentage is a ceiling on the true modifier, good to 0.1 pp; fit the offer price, not the panel figure. *Settled by:* player reading, 2026-07-29. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 6 / Secondary check.

**E-021 · CONFIRMED** — Ration wares follow the same cosine at the same span.
*Predicts:* `band = (1 + cos(π·net/(1.085 × allocation)))/2`, MAD 0.00163 pooled over 2,369 offers; 8 of 9 cohorts land on S 1.068–1.100; decile median residual never exceeds 0.0038. *Falsified by:* a habitat ration reading more than ~0.005 band off the cosine at a directly-read allocation. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Addendum 3 / § The ration cosine is exact.

**E-022 · CONFIRMED** — There is one price per (station, ware): `buy = sell − 1.00 Cr`.
*Predicts:* 704 of 706 pairs posting both sides, exactly; the two exceptions are player-owned. *Falsified by:* any non-player (station, ware) pair with both sides and a delta ≠ 1. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Main sequence / § Rebutting the `a` non-goal, follow-up 4.

**E-023 · CONFIRMED** — Stations price off their *net position* (`stock + inbound − committed outbound`), not their cargo.
*Predicts:* MAD 0.0527 → 0.0448 save-wide; on the 1,287 offers carrying pending, 0.0832 → 0.0411; the 43 "near-empty pricing as full" offers are 81 % inbound-pending and their median residual goes −0.502 → +0.013. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Addendum (same day): pending.

**E-024 · PENDING** — The price reference span is `m(ware, role) × allocation` with m a game constant.
*Predicts:* computronicsubstrate 0.194, claytronics 0.797, siliconwafers 0.823 against ~0.99–1.16 for the pack; GDR-378 reads 0.144 on computronicsubstrate while its five same-pool inputs sit at 1.02–1.12. *Falsified by:* a single station's m moving between saves at constant allocation, or an in-game read of a computronic-substrate producer's storage max coming back near 1,000 rather than ~5,300. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Addendum 2: the steep low-fill branch.

**E-025 · CONFIRMED** — `lockavgprice` wares are pegged at band average regardless of stock.
*Predicts:* sell = avg exactly (588/588 offers, zero variance), buy = avg − 1 Cr; corr(fill, band) = −0.04 over 1,175 offers; Layer-3 discounts still stack (EBT-957 microlattice 46.75 = 50 × (1 − 2.0 % − 4.5 %)). *Settled by:* save sweep + in-game read, 2026-07-27. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Layer 6.

**E-026 · CONFIRMED** — `shady` offers are a separate, price-inelastic black-market book.
*Predicts:* median 1.055 × band max, identical to three decimals across stimulants/spacefuel/spaceweed/majadust; corr(amount, price) = −0.08; 823 shadyguy posts ↔ exactly 823 stations posting shady offers. **Contradiction:** open-items-2026-07-27 § P6 reports the same population at "~1.77× the ceiling" with per-ware absolute prices (spaceweed 456.20, spacefuel 366.60, stimulants 935.00, majadust 572.60). Both recorded; not reconciled. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Black market (`shady`); [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P6.

**E-027 · PENDING** — The self-supply (`supplies`) buy price is a fixed per-ware multiple of band average.
*Predicts:* 10 distinct price/avg values over 1,207 offers — smartchips 1.1053, missilecomponents 1.2222, dronecomponents 1.1247, energycells 1.1875, metallicmicrolattice 1.0700, siliconcarbide 1.0753, silicon 1.0769, ore 1.0800, hullparts 1.1507, claytronics 1.0750 — independent of station, stock and faction. Source of the constants unidentified; it is **not** the recipe input value (0.72–0.95 computed vs 1.07–1.22 observed). *Settles it:* an extract-gamedata sweep for a per-ware field near 1.07–1.22. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Self-supply (`supplies`).

**E-028 · PENDING** — Yards/wharfs/docks price off outstanding build demand, not stock, on the same clamped form.
*Predicts:* fitting `band = clamp(1 − fill^k)` on the net position gives k = 2.60, MAD 0.0382 (exact denominator: 2.60 / 0.0367), against 0.1705 at k = 1.00; yards run much fuller (median fill 76 % vs 54 %). *Falsified by:* k staying ≈ 2.38 with a demand denominator. *Needs:* an NPC wharf with a known order queue; compare `stock + amount` against Σ recipe of its queued ships. **Note:** the same report's earlier text quotes k ≈ 2.38, corrected to 2.60 in its addendum. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Yards / wharfs / docks + § Addendum (same day).

**E-029 · CONFIRMED** — Construction buyers do not price off stock at all.
*Predicts:* median band position exactly 1.000 and median price/max exactly 1.000 over 1,788 build-storage offers; 189 above band max; they hold no allocation. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Build-storage demand.

**E-030 · CONFIRMED** — The trade panel's price decomposition is `avg × (1 + Σ additive modifiers)`, and the save's offer price carries the supply/demand term alone.
*Predicts:* UDX-946 ore (buying) "High Demand +6.6 %" → 50 × 1.066 = 53.30 exact; refined metals sell offer 90.72 = avg × 0.6130 = −38.70 % against the panel's −38.9 % (rep discount applied at display). *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, The trade panel's decomposition.

**E-031 · PENDING** — Commission + event discounts clamp at 0.5 × min price (the Layer-3 stacking bound).
*Settles it:* find a station where you hold a 25 % commission tier, wait for or trigger an active discount event there, and check one ware's buy price against `0.5 × min price`. *Source:* [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B14.

**E-032 · CONFIRMED** — The deployable price multiplier M is the save's `<trade><prices buildpricefactor>`.
*Predicts:* all four cross-station ratio constraints reproduced to ≤ 0.30 % with zero free parameters; NPC values clamp to [0.9, 1.15], pile at the bounds (50 of 67), and drift (12 of 67 changed between save_006 and save_008) — read per save. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Deployables.

**E-033 · FALSIFIED** — M is a per-station-type constant (wharf 1.15 / shipyard 1.067 / dock 0.90), or is calibratable once per station.
*Killed by:* a shipyard at 0.9 exists (sampling coincidence), and the observed re-rolls. Both routes explicitly closed. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Deployables; [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § 3. Explicitly closed.

**E-034 · PENDING** — The deployable valuation vector E is a sampled, time-varying engine statistic.
*Predicts:* every offline candidate already failed proportionality (own curve, own buys, `<prices><reference>`, band avg, offer-book aggregates at every scope, executed-trade averages — all > 5 % spread against the < 1 % required); three vectors observed, E_A shared by QJI-262+HLA-335+RLP-496 to 0.1 % across 3 sectors and 2 factions. *Settles it:* re-read QJI-262's nine deployable quotes a few game-hours later, paused — drift ⇒ time-varying; frozen ⇒ static and the cross-map sharing needs a different theory. *Source:* [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P1 — The E vector.

**E-035 · PENDING** — `buildpricefactor` re-rolls on an interval, and the walk correlates with the previous value.
*Predicts:* 12 of 67 changed between save_006 and save_008, some small steps 0.9→1.02, some jumps 0.9→1.15. *Settles it:* sweep the archived save series (seed-trends corpus) — offline, no play needed. Also open: confirm in game that MXH-411's stored 1.5 is its price-slider setting. *Source:* [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P2 — `buildpricefactor` dynamics.

**E-036 · SUPERSEDED** — Layer 2's economy price is linear in stock over a `target_level` much narrower than the allocation.
*Replaced by:* E-001, partly reinstated by E-018. *Predicted:* `economy_price = max − (max−min)(stock − pending)/target_level`; cohort fits R² 0.982–0.999, span 4–7 h of production for bulk wares, Terran solar band max to ~43,000 units falling to band min at ~269,000 against a 992,397 allocation. *Superseded by:* the fill/allocation cosine. *Reinstated in part:* Addendum 6 finds the denominator *is* sometimes a narrower price target (E-018), so the two are recorded as both true. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Layer 2.

## Storage allocation

**E-037 · CONFIRMED** — A station allocates each ware an equal number of *hours* of throughput out of its transport pool, with rations taking a fixed 4 h buffer off the top.
*Predicts:* `T = (pool_capacity − Σ ration_volume) / Σ(throughput × ware.volume)`; reproduces all 18 player-read allocations to within 0.20 %, nine exactly, across eight stations and six factions. *Source:* [handoff-storage-price-2026-07-28.md](../plans/handoff-storage-price-2026-07-28.md) § Confirmed model / Allocation.

**E-038 · CONFIRMED** — Modules produce whole units per CYCLE; the engine truncates before the hourly rate.
*Predicts:* `rate = floor(amount × (1 + work_effect) × sunlight)/time × 3600`; 7/7 against player readings; 97.92 → 97 microchips, 195.91 → 195 smart chips, 141.55 → 141 coolant. Order matters: DLB-176's 42,480/h only lands if sunlight is folded in before the floor. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Modules produce whole units per CYCLE.

**E-039 · CONFIRMED** — Solar output scales with sector sunlight.
*Predicts:* DLB-176 (Family Zhin, sunlight 0.71) 42,480 energy cells/h against a 42,000/h rated base; with it, energy cells 428,126 → 348,586 against ~348,000 in game and graphene 14,987 → 17,186 against 17,216. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Solar output scales with sector sunlight.

**E-040 · CONFIRMED** — `<production><efficiency product=>` is the complete multiplier, and the allocation applies it to outputs only.
*Predicts:* EIJ-609 floor(294 × 1.12634) = 331 per 900 s × 3 = 3,972/h, exactly the in-game overview against 4,824/h reconstructed. Scored over 4,914 pairs: efficiency on outputs only 87.2 % within 1 %, reconstructed work_effect × sunlight 76.7 %, no multiplier 50.9 %. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Production efficiency.

**E-041 · FALSIFIED** — The allocation ignores the efficiency multiplier entirely (fitted on EIJ-609's six wares).
*Killed by:* the 281 differential-efficiency stations; a no-multiplier basis scores 50.9 % within 1 % against 87.2 %. Marked SUPERSEDED in its own plan. *Source:* [storage-production-model-2026-07-28.md](../plans/storage-production-model-2026-07-28.md) § C3.

**E-042 · FALSIFIED** — Inputs are scaled by efficiency like outputs.
*Killed by:* it breaks IFO-957 by +23 % and TPF-229 by +16 %, and scores 49.9 % within 1 % against 87.2 % for outputs-only. *Source:* [handoff-storage-price-2026-07-28.md](../plans/handoff-storage-price-2026-07-28.md) § Confirmed model / Allocation.

**E-043 · CONFIRMED** — A module with no `<production>` block is idle and runs the bare recipe (multiplier 1.0).
*Predicts:* KRV-460's four inputs come in at exactly 0.724 of the offer-derived truth; 1/0.724 recovers the 1.53 work_effect wrongly applied. 939 (station, macro) pairs affected; 43.6 % → 73.8 % within 1 %, whole computed population 82.9 % → 86.2 %. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, A module with NO `<production>` block.

**E-044 · CONFIRMED** — A dual-role ware is sized by the LARGER of production and consumption.
*Predicts:* KWC-232 energy cells on 372,000/h consumption → 1,832,398 model vs 1,833,000 in game; hull parts 32,392 / 32,367; claytronics 9,505 / 9,450 — all at the same 4.93 h. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Dual-role wares.

**E-045 · CONFIRMED** — Processing modules (scrap works) are outside the storage model; their output is stored normally and their feedstock never is.
*Predicts:* counting the scrap works' 90,000 energy cells/h misses by 5 % on energy cells and 15 % on hull parts (KWC-232); reproduced on IRD-672 — scrap metal 40,000 exact, raw scrap no allocation and no row, and the UI itself keeps raw scrap distinct from ware storage. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Dual-role wares; [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 3.

**E-046 · CONFIRMED** — A multi-queue module's alternation *split* cancels out of the equal-hours division.
*Predicts:* IRD-672's three recyclers modelled as 3 × (144,000 + 42,000)/2 = 279,000 energy cells/h → 1,664,647 against 1,665,000 read in game (−0.02 %); food rations, medical supplies and scrap metal exact; claytronics +0.17 %, hull parts +0.16 %. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 3: IRD-672 as a test case.

**E-047 · FALSIFIED** — The engine sizes storage on the recipe *currently queued* rather than the average of the alternation.
*Killed by:* E-046's IRD-672 readings. The prices had implied an energy throughput near 52,600/h, a fifth of the modelled figure; the allocation reading came back exact on the averaged model, so the deviation is price, not allocation. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 2 (raised) / § Addendum 3 (killed).

**E-048 · CONFIRMED** — The ration buffer and the production share are ADDITIVE for a ware the station both makes and eats.
*Predicts:* JFV-172 cheltmeat 12,757 + 306 = 13,063 against 13,062 in game, spices 20,051 exactly; treating the roles as exclusive puts spices at 37,192. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, The ration buffer and the production share are ADDITIVE.

**E-049 · CONFIRMED** — Condensate ("Protectyon") is a fourth transport pool with no throughput: allocation = pool capacity / ware.volume.
*Predicts:* IRD-672's one `storage_pir_l_condensate_01` (50 m³) ÷ 10 m³ = 5 Protectyon, matching the station UI. 18 stations qualify; three price populations unchanged to four decimals after the fix, only +11 offers move. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, A fourth transport pool.

**E-050 · CONFIRMED** — VOM-540's `landmarks_gen_piratestation_01_ring_01` allocates 5,000 Protectyon (50,000 m³ ÷ 10).
*Predicts:* offer-derived floor closes twice — `23 + 4,977 = 5,000` in the save and `22 + 4,978 = 5,000` on the panel. Retracts Addendum 5's "extrapolation, not a confirmed number" caveat. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 6 / § Two corrections to Addendum 5.

**E-051 · PENDING** — EIJ-609's allocation is recomputed lazily and lags a recent efficiency change.
*Predicts:* re-reading the hull-parts allocation in game later should show a drift from 34,829 to ~37,228. If it stays at 34,829 the efficiency basis is wrong for war-modified stations specifically. Its rate follows 1.12634 exactly (3,972/h) while its allocation follows 1.0; read in game twice already. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, Superseded — EIJ-609 as a lag; [open-items-2026-07-28.md](../reports/open-items-2026-07-28.md) § F.

**E-052 · FALSIFIED** — A starving-workforce gate on the allocation (fitted to EIJ-609).
*Killed by:* it reproduced EIJ-609's six wares exactly and was worse than no gate save-wide under every definition tried, 93.8 % → 83.6–91.6 %. The register's standing lesson: do not fit a rule to one station. *Source:* [handoff-storage-price-2026-07-28.md](../plans/handoff-storage-price-2026-07-28.md) § Methodological lessons, item 2.

**E-053 · PENDING** — The mod's war-pressure efficiency term enters the production RATE but not the ALLOCATION.
*Predicts:* EIJ-609 reads 34,829 hull parts (multiplier 1.0 for allocation) while its modules report 1.12634 and the rate follows it; `efficiency / (1 + work_effect)` is exactly 1.000 for the plurality of modules in every faction, so the vanilla part is recoverable in principle. Separation not implemented. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, War-pressure bonuses do not count toward storage.

**E-054 · CONFIRMED** — `allocation = stock + inbound + open buy amount` is a LOWER BOUND, not an equality. **Documents disagree — see § Contradictions.**
*As an equality:* FALSIFIED — a station bids only for what it can use; MAL-475 reads 157,810 derived against a true 1,498,962, TPF-229 4,470 against 10,654. Treat as a LOWER BOUND. *As a save-derived check:* CONFIRMED at median ratio 1.0000 over 5,334 main-sequence buys (72.6 % within 5 %), and for production inputs that post a buy offer it is **saturated, not merely bounded** — median ratio 0.99992–0.99995 in every module-count bucket. Both statements stand; the disagreement is about the population, and the docs do not reconcile the wording. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, The offer-derived allocation is a LOWER BOUND; [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Rebutting the `a` non-goal; [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Recorded, not pursued.

**E-055 · CONFIRMED** — A full station withdraws its buy offer entirely rather than pricing it at zero.
*Predicts:* offer coverage 99.7 % below 90 % fill, 92.7 % at 90–100 %, 38.1 % at 100–110 %, 5.0 % at 110–120 %. *Settled by:* player observation on UDX-946 — ore buy price sat at 0 for ~45 minutes while completely full, then reappeared the moment it drew down. *Source:* [save-semantics.md](../reference/save-semantics.md) § Market data semantics.

**E-056 · CONFIRMED** — A station can hold MORE than its allocated capacity; allocation is a trade/target level, not a physical cap.
*Predicts:* MBI-471 reads 14,330 energy cells against a 4,403 allocation in the game's own menu. Consequence: "stock > allocation" is not evidence of a modelling error. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model, A station can hold MORE.

**E-057 · SUPERSEDED** — The high-ratio over-full rows are a defect keyed on `prod_gen_scrap_recycler` modules.
*Replaced by:* E-044 and E-045. *Predicted:* 13 of 17 genuine over-fill rows sit on nine recycler stations; QIB-162 and MDS-738 modelled 241,536 against 960,000 in game (×3.97), KWC-232 262,234 against 1,833,000 (×6.99). *Superseded by:* the dual-role and processing-module rules, which took output-side over-fills from 17 to 1. *Source:* [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P5c / § P5b.

**E-058 · FALSIFIED** — The pool split under-allocates hull parts by ~17 % (ratio 1.171, the only ware-level error above 6 %).
*Killed by:* on the current import `(stock + buy amount)/allocation` for hull parts is 0.9986 over 66 offers, and every ware with n ≥ 40 sits within 0.8 % of 1.000 (worst: ice 0.992). The efficiency, idle-module and multi-queue fixes closed it. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 4, Also closed; original in [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Proposed follow-up models, item 3.

**E-059 · PENDING** — Hybrid production+build stations belong on the computed path, not the storage proxy.
*Predicts:* prediction not stated. *Needs:* an NPC station with both a production and a build module — ULG-519 is the candidate — plus an in-game read of one production ware's max. Falsified if the computed path matches within a few percent. MXH-411 cannot settle it: it carries player-set `ware_limit` rows (max energycells 739,800 vs a proxy of 493,552), so it shows the player's configuration, not the engine's. *Source:* [fill-price-spread-2026-07-28.md](../reports/fill-price-spread-2026-07-28.md) § Proposed follow-up models, item 6.

**E-060 · FALSIFIED** — `<workforces><bonus busy=>` is a bonus on/off switch.
*Killed by:* busy=0 on 1,132 of 1,244 workforce stations, including plainly bonused ones. Looks like a cycle phase; do not use it as a gate. *Source:* [save-semantics.md](../reference/save-semantics.md) § Ware pricing model.

**E-061 · PENDING** — `nd_habitat_cap_boost` (S 2500 / M 5000 / L 10000 against stock 333/666/999) is a known-wrong input to the ration buffer and the efficiency.
*Predicts:* a 7.5–10× housing boost affecting 2,499 built habitat modules; `hab_arg_s_01_macro` 250 → 2,500. *Blocked on:* `extract_modcaps` cannot read `<diff>` files with no `<macro>` element, and `extract_wares` handles only `<add sel=…>`, never `<replace>`. *Source:* [open-items-2026-07-28.md](../reports/open-items-2026-07-28.md) § G. Reference-data gaps.

**E-062 · PENDING** — Station drone-pool capacity = Σ `module_cap.unit_storage` + 10 per built production module.
*Predicts:* the +10 term is FIT from a single point (MXH-411: floor 40 vs true cap 310) and is a one-point hypothesis, not a validation. The floor alone is validated in game on ABR-398 40, EBT-957 92, QJI-262 220. *Settles it:* any in-game `units.maxcount` reading on a second production-heavy station. *Source:* [save-semantics.md](../reference/save-semantics.md) § Station drone/unit pool.

**E-063 · PENDING** — `<supplies><orders>` persists the drone build TARGET, not outstanding orders.
*Predicts:* 37/40 order rows across 21 stations exactly equal the station's current drone count, 0/40 exceed it; five full, idle player stations carry rows equal to their counts (JQR-498/MXH-411 30-10-10, QNF-337/TIH-455 15-5-5, MAL-475 30-10-9), which an outstanding-orders reading would put at 0. *Settles it:* on a full station raise the target 30 → 40 and save — reads 40 ⇒ target, 10 ⇒ outstanding; then lower it below stock and see whether the block shrinks without scrapping drones. *Source:* [supply-offer-discriminator.md](../reports/supply-offer-discriminator.md) § Play checklist (open ends, each with the evidence it would produce).

## Parser / save format

**E-064 · CONFIRMED** — `built_refs` keyed on the bare entry id lets one station's finished module mark another station's unbuilt entry built.
*Predicts:* entry ids are unique only per station (2,235 of 22,562 shared, up to 33 stations on one id); 335 (station, entry) pairs in progress with no finished twin, of which 14 across 11 stations were wrongly marked built. JAR-041 gained 250,000 m³ of phantom container capacity → every allocation at 2×. Fixed by keying on `(host_id, entry_id)`; energy cells 42,516 → 21,002 against 21,001 in game. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 2 (JAR-041) / § Addendum 4.

**E-065 · CONFIRMED** — JAR-041's price residuals predict an allocation denominator error of exactly 2×, from prices alone.
*Predicted:* scale 1.998 / 1.994 / 2.037 / 1.984 on four wares; energy-cell max should read 21,258, not the modelled 42,516. *Settled by:* the player read 21,001 and diagnosed the second storage module as still under construction; after the parser fix the station prices on the curve (shift +0.323 sd 0.108 → −0.002 sd 0.023, output +0.050 against the § A constant +0.053). A complete round trip, each step measured independently. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum (same day): lead 5 / § Addendum 4.

**E-066 · FALSIFIED** — JUK-948's deviation is a ~1.37× allocation error.
*Killed by:* in game 18,957 energy cells against a modelled 19,089, −0.7 %. The allocation is right and the entire deviation is price — it becomes the first identified positive-offset station (+0.10 to +0.23 of a band). *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 2 / JUK-948.

**E-067 · FALSIFIED** — IRD-672 runs six scrap recyclers.
*Killed by:* the player reports three, each listed twice in the Logical Station Overview because each carries two products; `build_entry` agrees at 3. The "6" was a join artifact against `module_ref`, which holds one row per product. *Source:* [price-curve-2026-07-28.md](../reports/price-curve-2026-07-28.md) § Addendum 2 / IRD-672.

**E-068 · FALSIFIED** — `<insufficient>`/`<shortage>` amounts under `<build><resources>` are per-ware quantities.
*Killed by:* in-game cross-checks — wrong amounts AND wares the build doesn't need; one `<ware ware="claytronics" amount="62915"/>` matches the build's own `start="62915.848"`. Build demand comes from the build storages' open buy offers instead. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § Stations.

**E-069 · CONFIRMED** — `flags="supplies"` marks station self-supply buys and nothing else.
*Predicts:* save_007 — 1,140 of 15,418 offers flagged; 1,140/1,140 buys, 1,140/1,140 station-hosted, all 17 factions, 9-ware family, zero flagged sells, zero wares outside the family; `desired` = the outstanding input need, exact against ABR-398's orders × terran drone recipe (metallicmicrolattice 2,150, siliconcarbide 190, energycells 25,000 already on hand). Replicated on save_006 (1,127 flagged, identical invariants). All candidate counterexamples resolved. *Source:* [supply-offer-discriminator.md](../reports/supply-offer-discriminator.md) § Sweep evidence.

**E-070 · CONFIRMED** — `<overrides>` are the station-config manual per-ware limits, exact against live offers.
*Predicts:* MXH-411 buy limit 739,800 − stock 488,215 = 251,585 = the live offer's `desired`, exactly; sell side 83,773 − 34,200 = 49,573 microlattice, 3,867 − 2,646 = 1,221 computronic substrate, 9,814 − 5,184 = 4,630 silicon carbide — all exact. A `<ware>` with no `amount` means 1 (the UI's floor), not 0. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § Stations.

**E-071 · CONFIRMED** — The player-subscription duration is a constant 18,000 s (5 game-hours), and expired rows are retained.
*Predicts:* `parameters.xml <subscriptiondurations base="18000" tradecompleted="18000"/>`; zero of 10,694 timed rows exceed game_time + 18,000; 28.7 % of rows in save_008 are already expired. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § The player component.

**E-072 · FALSIFIED** — A satellite in a sector implies a live subscription on its stations.
*Killed by:* at sector granularity, covered sectors show a *lower* live rate. *Replacement (PENDING):* per-object radar radius + `tradecompleted` refresh — settled by parking a satellite next to one station, saving twice and checking its `remaining_s` ≈ 18,000 both times. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § The player component; [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P4.

**E-073 · CONFIRMED** — Permanent (`time`-less) subscriptions come from scanning a station's data leak.
*Predicts:* 11 such rows in save_008, all stations. *Settled by:* player confirmation on FEL-543, 2026-07-27. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § The player component.

**E-074 · PENDING** — `component@known` marks "visited" rather than merely map-known.
*Predicts:* among kept classes it marks 133 stations + 108 sectors + 103 clusters, 343 of 344 also `knownto`. *Settles it:* check a station you have definitely never visited but can see on the map. *Source:* [open-items-2026-07-27.md](../reports/open-items-2026-07-27.md) § P4 — Smaller semantic gaps.

**E-075 · CONFIRMED** — Build method follows the *builder faction's* rule, with a per-station override.
*Predicts:* `build@method` constant per builder faction over all 499 in-flight build tasks in save_008, never tracking module race (player 12/12 terran); the lone `alliance`→closedloop exception lands exactly on the two alliance stations carrying an override. *Settled by:* a controlled in-game change — ABR-398 had no element while inheriting `terran` and gained `<build method="closedloop"/>` the moment it was set to Closed Loop. *Source:* [save-semantics.md](../reference/save-semantics.md) § Build method.

**E-076 · CONFIRMED** — Object codes are recycled and live collisions exist even among simultaneously-alive same-faction same-class ships.
*Predicts:* 163 recycles in 21 game-minutes of NPC churn; save_001 holds two live terran `ship_ter_s_fighter_01_a` both coded XPU-790 (verified as two physical components), and RYJ-686 is at once a xenon corvette and a xenon lasertower. *Source:* [save-semantics.md](../reference/save-semantics.md) § Identity: nothing in the save is a GUID.

**E-077 · PENDING** — The money ledger's `v` accumulates actual payments across partial fills while the trade entry shows only its latest state; buyer-side rows are v-less because payment was escrowed at order time.
*Predicts:* `v` is `price × amount` or within 0.01 % except on amended/reused trade entries. *Settles it:* prediction not stated. *Source:* [savegame-structure.md](../reference/savegame-structure.md) § The money ledger.

**E-078 · PENDING** — The v5.10-ported log wordings for ship construction, repair and station-manager surplus transfers still parse on v9.
*Predicts:* zero archived instances anywhere in either playthrough, so unverifiable from history; destroyed-object, resupply and pirate/police wordings are v9-verified (323/323 archived destroyed rows). *Settles it:* a save that should contain such events — if those dashboards stay empty, check the actual log text first. *Source:* [architecture.md](../reference/architecture.md) § save/logparse.py.

**E-079 · CONFIRMED** — Cross-run event coverage epochs prevent phantom deltas across import gaps.
*Predicts:* synthetic probe, 2026-07-23 — `dv = NULL` for the first row of a new epoch; the same query without the epoch term reported a 150-unit phantom. Caveat kept: no real import has fired it (both populated DBs hold `MAX(epoch) = 0`), so gap behaviour is unexercised in production. *Source:* [db-schema.md](../reference/db-schema.md) § Merge semantics and idempotency.

**E-080 · PENDING** — `<stats>` `distance_*` are km and mission `reward` is cents.
*Predicts:* prediction not stated; both flagged unverified. *Settles it:* open the in-game stats screen and compare total mission rewards and distance travelled against the save's figures. *Source:* [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B17.

## Faction / diplomacy

**E-081 · FALSIFIED** — Faction relations are directional and not symmetric. **Documents disagree — see § Contradictions.**
*Claimed:* `argon→scaleplate = −0.32` while `antigone→scaleplate = −0.1`. *Contradicted by:* the B20 refresh — that example compares two *different* pairs, and 0 of 486 base pairs in the measured save are asymmetric. Restated there as stored-per-direction / measured-reciprocal. Both documents still stand as written. *Source:* [faction-relations-model.md](../models/faction-relations-model.md) § Directional, not symmetric [OBS]; [b20-number-refresh.md](../reports/b20-number-refresh.md) § Measurement table, row 12; [db-schema.md](../reference/db-schema.md) § faction_relation / faction_meta / faction_licence.

**E-082 · CONFIRMED** — Player standing is booster-driven: no base `<relation>` with major trading factions, permanent hostiles/allies are base relations.
*Predicts:* argon↔player both `0.240896 @ t=70164.839`; Xenon and Kha'ak at −1, Alliance at +1. *Source:* [faction-relations-model.md](../models/faction-relations-model.md) § Player standing is booster-driven [OBS].

**E-083 · PENDING** — Effective standing = `clamp(base + Σ boosters, −1, +1)`, and the rep bar is a fixed log transform of it.
*Predicts:* `uiv = sign(r)·10·log10(|r|·1000)` for `|r| > 0.0032`, `uiv = r/0.00064` below; anchors 1.0=30, 0.5=27, 0.32=25, 0.1=20, 0.032=15, 0.01=10, 0.0032=5. *Settles it:* play item B9 — note the in-game rep bar for 3 factions and check `clamp(base + Σ boosters)` against it. *Source:* [faction-relations-model.md](../models/faction-relations-model.md) § The −30..+30 rank value [DOC]; [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B9.

**E-084 · PENDING** — Boosters decay in place, and the save persists them at their current decayed value.
*Predicts:* `delay`/`decay` params, e.g. 540 s then rate 0.02; the decay curve is deliberately not projected. *Settles it:* B9 — save (slot A), leave one faction completely untouched for ≥ 1 game hour, save again (slot B), byte-diff the same booster keys. *Source:* [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B9.

## Resources

**E-085 · CONFIRMED** — A fully depleted resource area MOVES to a new random in-sector position; it does not respawn in place.
*Predicts:* 123 count-preserving position changes against 6 in-place live→depleted transitions; 0 creations, 0 destructions, 3,246 areas in every save, all moves in-sector; `starttime − respawndelay×60` lands inside the transition window for 120/121 moved-in rows. Supersedes the doc's earlier in-place claim; the XSD's "at a random location" was right. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Trackability; [phase7-research-p1.md](../reports/phase7-research-p1.md) § B5.

**E-086 · CONFIRMED** — Displacements are per-axis multiples of 20 km, and fractional coordinate residues survive the move.
*Predicts:* all 123 vectors are 20 km multiples (two with one 10 km component; ±0.01 m float dust); distances 20–520 km, median 130. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Trackability.

**E-087 · FALSIFIED** — Relocation targets come from a fixed slot pool.
*Killed by:* only 23 of 123 moved-to positions had ever been occupied by any area of that sector in the window, and only 6 of 123 exactly re-landed on a previous position of the same (sector, yieldid) group. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Trackability.

**E-088 · CONFIRMED** — A depleted area's stored yield materializes when a miner makes mining contact with it, not on a timer.
*Predicts:* reservation join — 103 materializations of which 57 carried a reservation, against 1,383 eligible-but-stayed-0 of which 30 did: 66 % vs 3.3 %, a ~20× enrichment. Player experiment at Pious Mists XI: 4,020 stored + 980 in the Drill's hold = 5,000 = cap. *Caveat kept:* the two surviving saves cannot distinguish contact-on-mining from on-approach/targeting. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § The stored yield materializes when a miner mines the area.

**E-089 · FALSIFIED** — Respawn needs high attention / a background timer / a rate-limited queue.
*Killed by:* Saturn 2 materialized with no player near while Third Redemption stayed at 0 with the player in-sector; an area sat 1 h+ past eligibility storing 0 until a miner touched it; at 18.52 h there were 145 eligible areas storing 0, and clearing happens one area at a time on contact. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § The stored yield materializes when a miner mines the area.

**E-090 · CONFIRMED** — A respawn restores full capacity, nividium included.
*Predicts:* Saturn 2 silicon 0 → 998,453 (99.8 %). *Reopened* by review F5 (of 117 sweep materializations only 18 reappeared ≥ 99.5 % of cap, the low tail exclusively nividium, min 4.4 %) and *resolved again*: the tail is post-materialization drawdown between saves, and the 980 + 4,020 = 5,000 experiment is definitive. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Open questions (unverified), Q1.

**E-091 · CONFIRMED** — Partial areas never refill; only a full depletion arms the cycle, and unmined sectors are frozen.
*Predicts:* Saturn 2's two mined-down `huge_silicon` areas stayed byte-identical; partial nividium areas held fixed values across 4+ saves; The Unknown System held its ore pools byte-identical across 11 saves over 4.6 game-hours at 32–70 % of capacity. Across all 3,306 areas, zero nonzero-yield areas carry a future `starttime`. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Life cycle of an area / § Unmined sectors are frozen.

**E-092 · CONFIRMED** — `starttime` is the respawn-*eligibility* time, not the depletion time.
*Predicts:* every depleted area whose `starttime` is in the future is empty, 42/42 across all wares; no depleted area has `starttime = 0`. Any "overdue" arithmetic on `now − respawndelay` is void. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § `starttime` = the respawn-*eligibility* time.

**E-093 · PENDING** — `gatherspeed` scales the mining extraction rate for solids, not the respawn amount or per-asteroid yield.
*Predicts:* factors 0.2 / 0.5 / 1.0 / 2.0 / 5.0 with ratings 3 / 6 / 9 / 12 / 15; currently assumed extraction-rate-only [INF]. *Settles it:* play item B10 — mine two areas of the same ware and level but different speed tokens (one `fast`, one `slow`) and time them. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Open questions (unverified), Q3; [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B10.

**E-094 · PENDING** — Depleted areas re-roll their position and timer if left unclaimed past eligibility.
*Predicts:* four depleted small-nividium records moved again in-window with freshly re-armed `starttime`s; indistinguishable from an invisible full cycle on a 500-cap area between saves. All four are nividium `verylow`; no other ware showed it. Recorded as hypothesis only. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Open questions (unverified), Q7.

**E-095 · PENDING** — What decides which areas a miner AI touches.
*Ruled out:* gatherspeed — the two permanently-0 Asteroid Belt areas are `medium/fast` and `high/average`, better than two `veryhigh/slow` areas that cycle fine; both sit at the sector periphery (km(−250,−50) and (−130,230)), so the driver looks like position/pathing. Selection logic is engine-side and unquantified; `<reservations>` is the direct observable of the outcome. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Open questions (unverified), Q6.

**E-096 · PENDING** — Coordinate residues mod 20 km can re-link an area's identity across a depletion.
*Predicts:* ~24 % of areas carry fractional coordinates; ~76 % are grid-aligned (residue 0) and cannot be told apart this way. Recorded as an untested recipe. *Settles it:* a uniqueness test at population scale. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Trackability.

**E-097 · FALSIFIED** — `cap / respawndelay` is a continuous field regeneration rate.
*Killed by:* it is dimensionally meaningless — respawn refills to capacity in one step, is contact-triggered, and the record relocates at each depletion. `yield ÷ respawndelay` is a single-area throughput *ceiling* only. The map gauge that computed it was reworked and the measured-rate plan shelved. *Source:* [resource-depletion-model.md](../models/resource-depletion-model.md) § Rates and "extraction"; [csv-reference.md](../reference/csv-reference.md) § regionyields.csv.

## Other

**E-098 · FALSIFIED** — The `origin`-role connection marks a wormhole's *entry* end.
*Killed by:* `setup_dlc_pirate.xml`'s `add_anomaly_destination anomaly=<IVC-752> destination=<WHT-407>` with the comment "exit from S3 into S2 (not tied to the wave)" — the `anomaly=` argument is the enterable end, so the roles are inverted. The old rule had been calibrated on zero discriminating cases, and `viz/map.py` drew the galaxy's one asymmetric arrow backwards. *Source:* [phase7-research-p1.md](../reports/phase7-research-p1.md) § B4 — settle the wormhole arrow.

**E-099 · PENDING** — Traversal runs IVC-752 → WHT-407, and WHT-407 is not enterable from Dead End.
*Predicts:* enter the Stable Warp Anomaly IVC-752 in Unknown System (`cluster_504_sector001`) and you exit at WHT-407 in Avarice V Dead End; the reverse is not traversable. Byte-stable across 13/13 saves at [SCRIPT]+[OBS] grade; the CONFIRMED tag waits on the play half. *Source:* [wormhole-connection-model.md](../models/wormhole-connection-model.md) § The prediction rule [OBS]; [phase7-research-p1.md](../reports/phase7-research-p1.md) § Play checklist, B4.

**E-100 · PENDING** — During an Avarice tide wave the pair temporarily gains the reverse link.
*Predicts:* 4 `<connection>` rows instead of 2; every save holds exactly 6 link rows (2 Avarice + 4 Freedom's Reach) and all 13 archived saves are calm-phase. A wave-window save would add one arrow, not change the 30/7/4 tier census. *Settles it:* save once while a wave is active. *Source:* [wormhole-connection-model.md](../models/wormhole-connection-model.md) § The Avarice link is tide-cycled [SCRIPT].

**E-101 · FALSIFIED** — Every functional warp is script-created.
*Killed by:* two provenances among the 11 functional warps — 9 are god-placed by DLC `god.xml` (8 Avarice `S2A_/S2B_/S2C_` including WHT-407, plus IVC-752 `S3_anomaly_01`); only the Freedom's Reach pair is `<source class="script">`. *Source:* [wormhole-connection-model.md](../models/wormhole-connection-model.md) § What the inert tier actually is [OBS].

**E-102 · FALSIFIED** — The inert anomaly tier is 30 anomalies, one per base-game sector. **Documents disagree — see § Contradictions.**
*Killed by:* the B20 refresh — 33 across 30 sectors, max 2 per sector; one-per-sector refuted. The wormhole model still states 30 / one per base-game sector. Both recorded. *Source:* [b20-number-refresh.md](../reports/b20-number-refresh.md) § Measurement table, row 11; [wormhole-connection-model.md](../models/wormhole-connection-model.md) § What the inert tier actually is [OBS].

**E-103 · CONFIRMED** — Savage Spur I → II is genuinely one-way.
*Settled by:* player confirmation, 2026-07-24 — the reverse traversal is impossible and intentionally so (a story element relies on it). `gates.csv`'s `oneway` encoding is ground-truth-correct; `sectorgraph.py`'s undirected graph is confirmed wrong for this edge, so advisor routes may include the impossible reverse hop. *Source:* [csv-reference.md](../reference/csv-reference.md) § gates.csv.

**E-104 · CONFIRMED** — Ship speed from game files: `max = Σ engine thrust.forward ÷ hull drag.forward`, `travel = max × engine travel@thrust`.
*Settled by:* validation against the in-game encyclopedia. L/XL engines only come in mk1, so thrust scales purely with mount count. *Source:* [architecture.md](../reference/architecture.md) § gamedata/ — game-file extraction.

**E-105 · CONFIRMED** — A `save="false"` mod can be fingerprinted by production efficiency breaching the stock `1 + work_effect` ceiling.
*Predicts:* exactly one ware breaches in this playthrough — `advancedelectronics`, 59 of 101 modules, max ratio 1.0294 = 1.40/1.36 — and nothing else comes near its ceiling. Registering `faction_fix_pack_econ_bal` moves the readings fixture 27/41 → 37/41 within 1 %. *Source:* [save-semantics.md](../reference/save-semantics.md) § Mod-aware reference data.

**E-106 · FALSIFIED** — Faction Fix Pack's catch-up "production efficiency from war pressure" is a rate multiplier.
*Killed by:* it is a post-hoc `<add_cargo>` of `floor(base_cycle_amount × ProdBonus)` on every production-finished event — invisible in the save's `<efficiency>` and in the UI's Product/h; the station-menu percentage is a separate UI row fed by `$CatchupProdBonus`. Do not model it as a multiplier. *Source:* [save-semantics.md](../reference/save-semantics.md) § Mod-aware reference data.

**E-107 · FALSIFIED** — The 96 built-module macros with no `module_cap` row are mod content hidden from extraction (csv F4).
*Killed by:* all 96 exist in the vanilla+DLC files and declare no workforce/cargo/storage properties at all; per-macro property parse → 0 hits. `capacity_floor` hides nothing. *Source:* [csv-reference.md](../reference/csv-reference.md) § modcaps.csv; [phase7-research-p1.md](../reports/phase7-research-p1.md) § B13.

**E-108 · CONFIRMED** — A save under-reports its own active mods.
*Predicts:* `GameFiles`' default discovery loads 7 of 74 installed extension folders; the save's `<patches>` holds 9 entries = 7 DLCs + 2 mods, leaving ~51 enabled mods runtime-active but unstamped; 8 of 67 mods ship loose files only; mod payloads are mostly attribute-level `<diff><replace sel="…/@attr">` patches that tag-scanning extractors read as empty. *Source:* [csv-reference.md](../reference/csv-reference.md) § Extraction and override machinery; [phase7-research-p1.md](../reports/phase7-research-p1.md) § B13.

**E-109 · PENDING** — Estimator B (yard draw) measures construction consumption once co-located production is subtracted.
*Predicts:* raw draw energycells 1.01M/h, hullparts 128k/h, microlattice 96k/h, smartchips 38k/h, weaponcomponents 15k/h, engineparts 12k/h; the energy-cell figure far exceeds estimator C's 292k/h, which is the contamination showing. *Settles it:* subtract each station's known module consumption rate — "without it, do not present B at all". *Source:* [continuous-construction-demand.md](../plans/continuous-construction-demand.md) § B. Yard draw.

**E-110 · PENDING** — The spawn-mechanistic estimator C is an upper bound on material demand because the job system respawns ships free.
*Predicts:* C says hullparts 395k/h recipe-equivalent against an observed yard draw of 128k/h. Well-supported inference, "not provable from the save alone"; survivorship bias means older windows undercount, so use 2–6 h windows. *Source:* [continuous-construction-demand.md](../plans/continuous-construction-demand.md) § C. Spawn-mechanistic + § Risks / caveats.

**E-111 · CONFIRMED** — Build storages emit no stock events, so station-side construction draw is not directly observable.
*Predicts:* verified — no buildstorage owners in the economylog; the workaround is construction-only wares (claytronics), measured at 15,585/h against a delivery-based 37.3k/h that double-counts production accumulation. *Source:* [continuous-construction-demand.md](../plans/continuous-construction-demand.md) § D. Station-side construction.

---

## Contradictions between documents — recorded, not resolved

1. **Offer-derived allocation** (E-054) — save-semantics.md demotes it to a lower bound on the strength of MAL-475 and TPF-229; fill-price-spread and price-curve report it as an equality at median ratio 1.0000 and as *saturated* for input buyers. Different populations, incompatible wording.
2. **`shady` price level** (E-026) — "~1.055 × band max" (fill-price-spread) against "~1.77× the ceiling" (open-items-2026-07-27), on populations of the same size and description.
3. **Faction relation symmetry** (E-081) — "directional, not symmetric" with a worked example against "0 of 486 base pairs asymmetric", the B20 refresh noting the example compared two different pairs.
4. **Inert anomaly census** (E-102) — 30, one per base-game sector, against 33 across 30 sectors with max 2 per sector.
5. **Sell-side curve** (E-004 vs E-005) — save-semantics.md § Layer 4 still carries the warped cosine at S 1.125 / k 0.86 for the sell side; price-curve.md replaces it with the shifted cosine. The reference doc is stale rather than wrong-headed, but a reader hitting Layer 4 first gets the superseded law.
6. **Price denominator** (E-036 vs E-018) — "target_level is NOT the storage allocation" against the fill/allocation cosine. Addendum 6 holds both: the cosine and its span stand, and the denominator is a price target that usually equals the allocation and sometimes does not.
7. **Yard exponent** (E-028) — k ≈ 2.38 in the body of fill-price-spread, k = 2.60 in its own addendum after the pending-correction; the body text was not updated.
