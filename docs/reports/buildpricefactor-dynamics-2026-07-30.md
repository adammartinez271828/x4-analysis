# `buildpricefactor` dynamics — the 13-save sweep (P5)

*2026-07-30. Plan item **P5** of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md); settles
the offline half of register entry **E-035** and re-establishes the drift
evidence cited by **E-032**. Data: the 13-save archived corpus built in Phase 1
(game time 69,324 → 84,643 s = 4.26 game-hours, one playthrough, guid
`8E0C8E37-2192-49FD-BF4B-F535782A1C55`), parsed with the project's own
`save/parser.py`. Nothing under `src/` or `tests/` was touched.*

**Provenance caveat, recorded deliberately.** E-032 and E-035 cite a
`save_006` ↔ `save_008` comparison from the ~61,949 s era ("12 of 67 changed").
Those save *files* have since been overwritten by the playthrough; the versions
that produced the original numbers no longer exist on disk. **This sweep is the
new evidence base.** It is not a re-verification of the old measurement — but,
noted below, the new files reproduce "12 of 67" exactly, which is a pleasing
coincidence and not a proof of anything.

---

## Population

`build_price_factor` is parsed per save but only snapshot-retained in the
analysis DB, so the corpus re-parse is the only place the series exists.

- **880 station-epoch rows**, 100 % resolvable to a `component` row.
- **68 distinct stations** by `(code, class, macro)`; **67 present in all 13
  epochs**, one (MXH-411, player) appearing from `save_008` onward (9 epochs).
- **812 consecutive-epoch transitions**, 804 of them NPC.
- Epoch spacing runs from **5 s** (`save_010` → `save_001`) to **7,187 s**
  (`autosave_01` → `autosave_02`), which is what makes a rate estimate possible
  at all.

---

## Result 1 — the clamp is real, and it is sticky

On the last epoch (`save_005`, game time 84,643): 68 values, **25 at exactly
0.900**, **22 at exactly 1.150**, i.e. **69 % sitting on a bound**. Pooled over
all 871 NPC station-epochs: **345 at 0.900, 315 at 1.150, 211 interior**
(75.8 % on a bound).

**No NPC value ever leaves [0.90, 1.15]** in 871 observations. The single
exception is **MXH-411**, player-owned (`Fabrication Complex TI`), which holds
**1.500 constant across all 9 epochs it exists for** — never re-rolling, never
clamped. That is consistent with it being a player price-slider setting rather
than an engine roll, but the save cannot distinguish "player setting" from
"NPC rule that does not apply to player stations"; **confirming 1.5 = the
slider stays a player item (R10)**.

The bounds are not merely absorbing, they are **sticky**:

| origin | P(value changes to the next epoch) |
|---|---|
| at 0.900 | 35/320 = **0.11** |
| interior | 96/191 = **0.50** |
| at 1.150 | 44/293 = **0.15** |

## Result 2 — re-roll rate

Change fraction per transition, by epoch gap (n = 67–68 stations per row):

| gap | 5 s | 177 s | 338 s | 360 s | 557 s | 656 s | 850 s | 954 s | 962 s | 1,201 s | 2,072 s | 7,187 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| changed | 1 | 7 | 13 | 10 | 16 | 22 | 15 | 16 | 20 | 16 | 19 | 20 |
| fraction | 0.015 | 0.103 | 0.191 | 0.147 | 0.235 | 0.324 | 0.224 | 0.239 | 0.294 | 0.235 | 0.284 | 0.299 |

The fraction rises with the gap up to roughly **600 s** and then **saturates at
~0.25–0.30** — it does *not* keep climbing toward 1 even at a two-hour gap.
Two consequences:

- The re-roll **is** time-driven on a scale of order **5–10 minutes** of game
  time (the 5 s gap shows 1 change; the 338 s gap already shows 13).
- The value is far more persistent than an independent redraw would be. An
  independent draw from the observed value distribution would differ ~75 % of
  the time; at a 2 h gap only 30 % differ. **The process is not memoryless.**

Over the whole 4.26 h window: **175 changes over 67 stations = 0.61 changes per
station per game-hour** (mean observed interval 1.63 h) — a **lower bound**, as
13 samples cannot see a re-roll that returned to the same value or two
re-rolls inside one gap. Per-station change counts are strongly heterogeneous:
**21 of 67 stations never changed at all** in 4.26 h, while the busiest changed
**9 times** (counts 0:21, 1:6, 2:13, 3:4, 4:7, 5:4, 6:6, 7:3, 8:1, 9:2).

Direct `save_006` → `save_008` (gap 1,804 s): **12 of 67 changed** — the
register's original figure, reproduced on the re-parsed files.

## Result 3 — the walk correlates with the previous value (E-035's second half)

- **corr(new, previous) = +0.888** over all 804 NPC transitions.
- Restricted to the 175 transitions that actually changed, **+0.273** — the
  residual correlation after conditioning on "it moved".

Step sizes on the 175 changed NPC transitions: median **−0.0210**, median
|step| **0.0870**, range **−0.250 … +0.250**, **86 up / 89 down** (no drift).
The |step| histogram is *discrete*, not continuous: 0.02 (12), 0.03 (40),
0.04 (1), 0.05 (1), 0.06 (11), 0.07 (1), 0.08 (17), 0.09 (33), 0.12 (17),
0.13 (15), 0.16 (4), 0.17 (4), 0.19 (3), 0.25 (16).

## Result 4 — the factor lives on a tiny shared alphabet (new)

This is the sweep's real finding and it was not anticipated by E-035.

**Only 16 distinct values occur in all 880 station-epochs:**

| value | 0.900 | 0.921 | 0.923 | 0.925 | 0.931 | 0.962 | 0.975 | 0.983 | 0.994 | 1.020 | 1.060 | 1.070 | 1.090 | 1.120 | 1.150 | 1.500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n | 345 | 7 | 1 | 8 | 5 | 8 | 1 | 46 | 8 | 37 | 4 | 67 | 8 | 11 | 315 | 9 |

and **each station visits at most four of them** over 13 epochs (22 stations
use 1 value, 24 use 2, 17 use 3, 5 use 4). The per-station alphabets are
**shared across stations and across factions** — a handful of ladders recur
verbatim:

| ladder | stations using it | rung gaps |
|---|---|---|
| {0.900, 1.020, 1.150} | PIT-694, BTV-044, QCO-133, CML-479, EME-101, FKM-164 (all xenon) | 0.120, 0.130 |
| {0.983, 1.070, 1.150} | EDP-470 (paranid), EFF-568 (split), QJI-262 (terran), DXG-913 (teladi), XST-598 (antigone) | 0.087, 0.080 |
| {1.060, 1.090, 1.120, 1.150} | PDR-519 (pioneers), TXJ-676 (xenon), NUJ-928 (terran), AKY-534 (argon) | 0.030 ×3 |
| {0.900, 0.931, 0.962, 0.994} | HBK-285 (scavenger) | 0.031 ×3 |
| {0.900, 0.983, 1.070, 1.150} | URZ-485 (argon) | 0.083, 0.087, 0.080 |

Within a station's ladder, **141 of 175 moves are a single rung**; 34 skip.
The ladders look geometric rather than additive — successive ratios inside a
ladder agree to ~1 % (1.0885 / 1.0748; 1.1333 / 1.1275; 1.0275 / 1.0268) while
the additive gaps differ by up to 8 % — but the corpus cannot pin the generator
and this report does not claim one.

---

## Dynamics statement

**CONFIRMED (offline half of E-035):**

> NPC `buildpricefactor` is **clamped to [0.90, 1.15]** (871/871 NPC
> observations, zero escapes) and **piles up on the bounds** (75.8 % of
> station-epochs, 69 % of stations at any instant). It **re-rolls on a
> timescale of order 5–10 minutes of game time**, saturating at a ~25–30 %
> per-interval change rate; over 4.26 h it changes **0.61 times per station per
> game-hour** (lower bound), with strong per-station heterogeneity — 21 of 67
> stations never moved. The walk **correlates with its previous value**
> (corr = **+0.888** over 804 transitions, **+0.273** among the 175 that moved),
> because each station draws from a **small per-station ladder of 1–4 values**
> out of a **15-value** global NPC alphabet (16 counting the player's 1.500),
> and 141 of 175 moves are a single rung.
> Bound-sitting states are sticky: P(change) = 0.11 at 0.90 and 0.15 at 1.15
> against 0.50 in the interior.

*Falsified by:* any NPC `buildpricefactor` observed outside [0.90, 1.15]; any
NPC value off the 15-value alphabet above; a station whose per-epoch values
span more than four distinct levels within a few game-hours; or a change rate
that keeps rising toward 1.0 at gaps well beyond 600 s (which would restore the
"independent redraw" model).

**Still open / PLAYER only:** MXH-411's stored **1.500** is the one value
outside the NPC clamp and is constant over all 9 epochs it exists for.
Confirming that it is the station's **price-slider setting** needs an in-game
look (**R10**); the save alone cannot separate "player setting" from "the clamp
does not apply to player stations".

**Consequence for E-032 (deployable pricing).** E-032's operational advice —
*read `M` per save, never carry it across saves* — is reinforced: 21.6 % of
station-epoch pairs differ, with steps up to 0.25, i.e. up to a **28 % swing**
in a deployable's quoted price between two saves 6 minutes apart. E-032 itself
is unaffected; only the "drift" clause it cites now rests on this sweep.

---

## Ranked leads

1. **Find the generator of the 16-value alphabet.** Values are quantised to
   three decimals and cluster into per-station geometric ladders shared across
   unrelated factions; the ladders' common ratio varies by station
   (≈1.027, ≈1.08, ≈1.13). A per-station "volatility" parameter times a small
   integer state would produce exactly this. The obvious candidates to test
   against are station-level attributes already parsed (owner faction, station
   macro/design, sector) — none was tested here.
2. **21 of 67 stations never moved in 4.26 h.** If the frozen set is stable
   over a longer window it is a *property*, not a sampling accident, and it
   would separate "stations that re-roll" from "stations with a fixed factor" —
   worth one pass over a wider save series if one is ever archived.
3. **The saturation curve deserves a finer probe.** The change fraction is
   already 0.19 at a 338 s gap and flat by 600 s. A deliberate series of
   quicksaves 60/120/240 s apart would pin the re-roll period directly, and
   costs nothing but save-and-reload.
