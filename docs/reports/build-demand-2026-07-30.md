# Yards, build storages and build stations: is there a bill-of-materials demand model? — 2026-07-30

Plan item **P8** of [../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md).
Targets: **E-028** (yard pricing denominator), **E-118** (build-storage curve
shape on an independent denominator), and the unmodelled **68 build-station
allocations**.

**Basis.** Analysis DB snapshot `save_id` **71** (`save_002.xml.gz`, game time
82,687.5) for prices, cargo, pending trades, build entries and reference data.
Two scratch `lxml` passes over `save_002.xml.gz` (and, for the epoch check,
over `autosave_01` at 69,324 s and `save_005` at 84,642 s) collected the build
task tree; the 13-save corpus built in Phase 1 supplied the time series.
**Nothing under `src/`, `tests/`, `docs/reference/`, `docs/models/` or
`docs/experiments/` was touched to produce this document** — scratch parsers
only, per the phase gate. Scratch lives in the job dir
(`$CLAUDE_JOB_DIR/tmp/p8/`).

Status discipline: every claim below is marked **[FINDING]** (measured on this
snapshot / corpus, not yet registered) or **[REJECTED]**. Register status
changes are *recommended*, not applied; Phase 4 owns the register.

---

## Headline

1. **The outstanding build bill of materials is far too small to be any
   station's storage target.** Summed over hull *and* every fitted piece of
   equipment, and counting each in-progress ship as if none of its materials
   had been consumed (a strict upper bound), the outstanding ship BOM is a
   **median 0.0 %** and a **maximum 69 %** of the yard's own offer-derived
   allocation `stock + amount`; on the ware that carries most of it,
   hullparts, the median is **7.1 %**.
2. **So E-028's mechanism is refuted, not merely unconfirmed.** On the demand
   denominator the yard curve collapses: 10 of 16 equal-count bins sit at fill
   exactly 1.000 with band medians spanning 0.02–1.00, bin RMSE **0.4355**
   against **0.0792** for the `stock + amount` proxy. The registered exponent
   **k = 2.60 reproduces (k = 2.62) — but on the proxy, not on demand.**
3. **The build-station allocation is a property of the DESIGN, not of the
   queue.** Same-build-module-signature station pairs agree at median Pearson
   **0.9986** on their derived per-ware allocation vector; over 15,319 s of
   corpus the derived allocation has median CV **0.0107** while the yard queues
   turn over **completely** (zero overlap of (yard, ship) tasks between any two
   epochs, even 1,955 s apart) and the outstanding BOM itself has median CV
   **0.511**.
4. **BOM-proportional allocation is rejected by the lower-bound rule**:
   **75.5 %** of scored (station, ware) cells fall *below* `stock + inbound +
   open buy`, median model/derived **0.104**. 24 of the 53 build stations with
   ≥ 4 buy offers have **no ship queue at all** and still hold a median
   **50.0 M Cr** of derived allocation.
5. **E-118's shape survives an independent denominator.** Re-tested against the
   outstanding module-build BOM (432 offers with a nonzero independent
   denominator), the build-storage price is still flat at band 1.000 to a knee
   and then falls: free flat-then-line fits **knee 0.57, bin RMSE 0.0725**;
   the cosine scores 0.3084 and the clamped line 0.2844. The caveat recorded in
   E-118 ("the denominator uses the offer's own `amount`, so the correlation is
   partly definitional") is **discharged for the sub-population where an
   independent denominator exists**.
6. **New, unmodelled: build storages fund module LOADOUT replacement.** 949 of
   1,381 build-storage buy offers sit on stations whose module plan is fully
   built — they are buying turret/shield/engine inputs to replace destroyed
   equipment. The replacement BOM of the station's whole *installed* loadout
   correlates with the offer-derived proxy at **r = 0.887** over 898 offers
   (median ratio 1.61). This is the missing half of build-storage demand and it
   is not in any model.

---

## What the save actually carries

### `type="buildship"` tasks name a ship COMPONENT [FINDING]

`savegame-structure.md` § Stations records that the `<insufficient>`/
`<shortage>` amounts under `<build><resources>` are not quantities (E-068,
FALSIFIED) and concludes that "a per-order bill-of-materials model for
wharf/shipyard construction demand is **closed, not a gap**: the save does not
carry the quantities". That conclusion is **right in outcome but wrong in
premise**, and the premise matters:

- Each `<buildtasks><queue|inprogress><build type="buildship" …>` element
  carries `component="[0x….]"`, and **that id resolves to a real ship
  component elsewhere in the save**, with its macro, code, spawntime and its
  full installed equipment tree. 214 buildship tasks on 71, **214/214
  resolvable** (118 ship_s, 73 ship_m, 12 ship_l, 11 ship_xl).
- So a per-order BOM *is* computable — hull recipe from `recipes.csv` plus
  every fitted turret / shield / engine / weapon / launcher, each of which is
  itself a ware with a recipe. No game-file parsing beyond the packaged CSVs
  was needed.
- The reason the model still fails is not missing data. It is that the demand
  is **two orders of magnitude too small** (below).

Task census on 71 (all `<build>` elements carrying `type` or `order`):

| type | context | host class | n |
|---|---|---|---:|
| expand | inprogress | buildstorage | 593 |
| build | — | buildstorage | 306 |
| (none) | — | buildstorage | 286 |
| **buildship** | queue | station | **191** |
| build | — | station | 24 |
| **buildship** | inprogress | station | **23** |
| restock | queue | station | 19 |
| expand | queue | buildstorage | 11 |
| other (recycle / recycleship / recycleanchor / restock-inprogress) | | | 4 |

Of the 235 buildship + restock tasks, only **71** have
`component@spawntime == build@time` (a hull created for this order); **164**
point at ships that existed long before the task — the same element type also
carries **repair / refit / restock** work. Either way the ship's equipment tree
is present, so the BOM is computable for both.

### Build-storage ↔ station link

The `expand` task on a build storage names its station in `@component`: **593**
storages linked to **593** distinct stations, 1:1. 625 storages post buy
offers, of which 444 carry an expand task (the other 181 carry **no build task
at all** and still buy — see § loadout below).

---

## (a) E-028 — the yard denominator

### Definitions used

For a yard buy offer on ware *w*:

- `stock` — the station's own `<cargo>` for *w*.
- `inbound` / `outbound` — Σ of `amount − transferred` over active
  `trade_pending` rows where the yard is buyer / seller.
- `net` — `stock + inbound − outbound` (the pending-corrected net position,
  as in fill-price-spread's Addendum 1).
- **`bom`** — Σ over the yard's outstanding `buildship`/`restock` tasks of the
  target ship's per-unit recipe under the yard's resolved build method
  (`v_build_method`), **plus** the recipe of every `turret`,
  `shieldgenerator`, `missileturret`, `missilelauncher`, `weapon` and `engine`
  component in that ship's tree. Unbuilt-module BOM is added where it exists
  (it exists on **2 of 68** build stations; see below). No credit is taken for
  materials already consumed by an in-progress build, so `bom` is an **upper
  bound** on outstanding demand.
- **`demand = stock + inbound + bom`** — the denominator P8 specifies.
- `band` — `(price_cr − price_min)/(price_max − price_min)` on the ware's band.

Population: the **68** stations carrying a built `buildmodule*` entry (the
storage model's classification rule, *not* the station macro), buy side, minus
player-owned and `shady`/`supplies`-flagged offers, minus wares with a
degenerate band: **678 offers**, 241 of them with a nonzero BOM. Median band
position 0.448; 20.1 % clamped at band max; none at band min.

### The BOM is negligible against the proxy [FINDING]

`bom / (stock + amount)` over the 678 offers: **median 0.0000**, p90 0.0702,
**max 0.6945**, and **0 offers** reach 1.0.

| ware | n | median `bom/(stock+amount)` | max |
|---|---:|---:|---:|
| hullparts | 37 | 0.0711 | 0.6945 |
| weaponcomponents | 27 | 0.0702 | 0.2022 |
| shieldcomponents | 32 | 0.0297 | 0.3665 |
| energycells | 55 | 0.0213 | 0.1755 |
| advancedelectronics | 36 | 0.0189 | 0.2772 |
| turretcomponents | 35 | 0.0072 | 0.4575 |
| engineparts | 36 | 0.0066 | 0.2664 |

A yard's median energy-cell stock alone is **300,788** units against a whole
outstanding hull BOM of **703**.

### The refit [FINDING / REJECTED]

`band = clamp(1 − fill^k)`, `fill = net / denominator`, k scanned 0.01–6.00 on
per-offer median |residual|; scoring reported on **16 equal-count bin medians,
equal weight per bin**, per the ground rules.

| denominator | n | best k | MAD | MAD @ k=1 | **bin RMSE** | bin RMSE @ k=1 | median fill |
|---|---:|---:|---:|---:|---:|---:|---:|
| **E-028 proxy `stock + amount`** | 677 | **2.62** | 0.0399 | 0.1696 | **0.0792** | 0.1817 | 0.747 |
| proxy, net numerator (`net + amount`) | 677 | 2.51 | 0.0399 | 0.1696 | 0.0765 | 0.1817 | 0.747 |
| **`demand = stock + inbound + bom`** | 653 | 5.87 | 0.2481 | 0.3448 | **0.4355** | 0.5045 | **1.000** |
| `bom` alone | 241 | 4.01 | 0.4315 | 0.4501 | 0.5887 | 0.5981 | 3.000 (clipped) |
| `bom + stock` | 653 | 6.00 | 0.2501 | 0.3448 | 0.4381 | 0.5050 | 1.000 |
| `amount + bom` | 652 | 5.95 | 0.1882 | 0.2465 | 0.2834 | 0.3444 | 2.566 |

**E-028's registered prediction reproduces on 71 — k = 2.62 against the
registered 2.60, MAD 0.0399 against 0.0382 — but only on the `stock + amount`
proxy.** On the demand denominator the fill coordinate degenerates: ten of the
sixteen bins have median fill 1.000 and band medians running 0.021, 0.129,
0.178, 0.217, 0.277, 0.347, 0.457, 0.607, 0.938, 1.000 — the entire price range
at one x-value. No exponent can fit that; the 5.87 "best k" is the fitter
running to the edge of a hopeless grid.

Bin medians, proxy basis (k = 2.62), for the record:

| fill | 0.000 | 0.083 | 0.181 | 0.346 | 0.494 | 0.641 | 0.769 | 0.865 | 0.945 | 0.990 | 1.000 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| band obs | 1.000 | 1.000 | 0.999 | 0.931 | 0.766 | 0.560 | 0.457 | 0.325 | 0.218 | 0.176 | 0.167 |
| band pred | 1.000 | 0.999 | 0.989 | 0.938 | 0.843 | 0.688 | 0.497 | 0.317 | 0.137 | 0.027 | 0.000 |

(The residual structure at the full end — an observed floor near 0.17 where the
power curve goes to 0 — is real and unexplained; it is the same "yards read
high" hump fill-price-spread reported, and it is *not* addressed by any
denominator tried here.)

**Save-wide side effects.** None, in either direction: the yard book is
disjoint from the main sequence, from `lockavgprice`, from `supplies` and from
the build storages, so changing the yard denominator moves no other offer. That
is also why the demand basis cannot be defended as "worse here, better
elsewhere" — there is no elsewhere. Scored against the whole yard population
(all 678 offers, not the 241 that carry a queue), the demand basis is **5.5×
worse on bin RMSE** than the basis it replaces.

### The corpus kills the mechanism outright [FINDING]

Three epochs parsed for build tasks (69,324 / 82,688 / 84,643 s) and all 13
for offers and cargo:

- **Yard queues turn over completely.** (yard, ship-component) task pairs:
  197 at 69,324 s, 234 at 82,688 s, 209 at 84,643 s — **overlap 0** between
  *every* pair of epochs, including the two only 1,955 s apart.
- Outstanding BOM per (yard, ware): **415 series, median CV 0.511**
  (p25 0.230, p75 0.881). Universe-wide outstanding BOM: 1.26 M → 1.11 M →
  1.55 M units.
- Derived allocation `stock + amount` per (build-station code, ware), 697
  series present in ≥ 8 of the 13 epochs: **median CV 0.0107**, p25 0.0000,
  p75 0.0494, **75 % below CV 0.05** — against median CV 0.0669 (p75 0.322)
  for raw stock on the same series.

A quantity that swings by ±50 % cannot be the denominator of a quantity that
holds to ~1 %. **E-028's "yards price off outstanding build demand" is
falsified as a mechanism.** What survives is the *shape* result it was carrying:
the yard book is the same clamped-power family with a steeper exponent,
k ≈ 2.6, on an ordinary storage-like target.

*Falsifier for the replacement claim:* a yard whose derived allocation moves
with its queue — i.e. any (yard, ware) series whose `stock + amount` tracks its
outstanding BOM across epochs at |r| > 0.8. None of the 415 series does.

---

## (b) E-118 — build-storage curve on an independent denominator

Denominator: **outstanding module-build BOM** — Σ over the linked station's
**unbuilt** `build_entry` rows (which include in-progress modules, since the
parser only marks an entry built when a *finished* component references it) of
the module ware's recipe under the station's resolved build method. All 4,118
unbuilt entries on 71 resolve to a ware and a recipe; no fallbacks were needed.
`fill = (stock + inbound) / bom`, clipped at 3.0; band clipped at 1.0 (14 % of
build-storage offers price *above* band max, as E-029/E-118 record).

Population: 1,381 build-storage buy offers whose storage links to a station;
**432** have a nonzero independent denominator. 12 equal-count bins.

| shape | bin RMSE, **independent** module-BOM (n=432) | bin RMSE, self-referential `stock+amount` (n=1,352) |
|---|---:|---:|
| **free flat-then-line** (knee, width free) | **0.0725** (knee 0.57, width 0.64) | **0.0281** (knee 0.50, width 0.65) |
| free power `1 − u^k` | 0.1133 (k = 5.92) | 0.0886 (k = 3.64) |
| power k = 2.60 (the yard exponent) | 0.1629 | 0.1030 |
| flat-then-fall as E-118 measured it (knee 0.41) | 0.1897 | 0.1184 |
| clamped line `1 − u` | 0.2844 | 0.2238 |
| cosine `(1+cos πu)/2` | 0.3084 | 0.2398 |
| constant 1.0 | 0.3335 | 0.2983 |
| warped cosine `cos(π(u+0.053)/1.095)` | 0.4261 | 0.3818 |

Bin medians on the independent denominator (fill/band):
0.00/1.00 · 0.00/1.00 · 0.00/1.00 · 0.00/1.00 · 0.00/1.00 · 0.08/1.00 ·
0.31/1.00 · 0.57/1.00 · 0.75/0.72 · 0.90/0.42 · 0.98/0.41 · 3.00/0.24.

**[FINDING] E-118's shape claim survives the denominator change.** The price is
flat at band ceiling to a knee and then falls; the knee reads 0.57 on the
independent basis and 0.50 on the self-referential one (E-118 measured 0.41 on
save 70). The cosine family — both the plain and the warped-with-`a` form that
fits the ration book to 0.0016 — is **rejected on both bases**, by a factor of
4 and 8 respectively against the free flat-then-line. The clamped line is
rejected too. The ordering of shapes is identical on the two denominators,
which is the point: it was not an artifact of `amount` appearing on both sides.

**[FINDING] but the denominator is incomplete.** 949 of the 1,381 offers sit on
stations whose module plan is **fully built** — zero unbuilt entries — and they
are still buying. See the next section; those offers cannot be scored at all on
a module-BOM basis, and the 432 that can are a biased sub-population (stations
mid-expansion).

*Falsifier:* a build storage whose price sits materially below band max at a
fill below its knee on an independently measured denominator, or a cosine that
beats flat-then-line on bin medians on any denominator.

---

## The missing half: build storages fund module LOADOUT replacement [FINDING]

This was not in the plan and is new.

BHF-032 (teladi, station `[0x73ac]`, storage `[0x7137]`) has **16 of 16** plan
entries built, no unbuilt module, and its storage buys advancedelectronics 231,
fieldcoils 737, shieldcomponents 619, turretcomponents 1,135. Those are exactly
the recipe inputs of station **turrets and shields**. Its plan entries carry
`<upgrades><groups><shields macro=…/><turrets macro=…/></groups>`; comparing
the planned groups with the components actually installed under the station:

| macro | planned groups | installed |
|---|---:|---:|
| shield_tel_m_standard_02_mk2 | 38 | 38 |
| turret_tel_m_plasma_02_mk1 | 24 | 22 |
| turret_tel_m_shotgun_02_mk1 | 12 | 10 |
| turret_tel_m_gatling_02_mk1 | 4 | 4 |
| turret_tel_m_guided_02_mk1 | 2 | 2 |
| turret_tel_l_dumbfire_01_mk1 | 2 | 0 |
| shield_tel_l_standard_01_mk2 | 3 | 6 |
| turret_tel_l_plasma_01_mk1 | 3 | 18 |

M-size groups are 1:1 with installed components; L-size groups are not (one
group covers several turrets), so a *planned − installed* difference cannot be
computed exactly from the save alone without the per-module slot counts from
the game files. Measured anyway, over all 1,381 build-storage buy offers:

| candidate | offers with a nonzero value | Pearson vs `stock+amount` | log-Pearson | median ratio |
|---|---:|---:|---:|---:|
| unbuilt-module BOM | 415 | 0.158 | 0.740 | 1.000 |
| **whole installed loadout, replacement BOM** | **898** | **0.887** | 0.716 | 1.61 |
| planned − installed ("missing") loadout BOM | 209 | 0.352 | 0.519 | 0.092 |
| module BOM + missing loadout | 610 | 0.190 | 0.594 | — |

The whole-loadout replacement value is the only candidate that covers most of
the book and it tracks the proxy strongly. **Hypothesis, not confirmed:** a
build storage's target for equipment wares is proportional to the replacement
BOM of its station's installed turret/shield/engine loadout, with a coefficient
near 1/1.6 ≈ 0.62. *Falsifier:* a station whose loadout is destroyed and
rebuilt without its storage's derived allocation moving proportionally; or a
per-module slot-count extraction showing the missing-loadout BOM (not the whole
loadout) is what the amounts equal.

Note also the 181 storages that post buy offers with **no build task at all** —
consistent with the same standing-buffer reading.

---

## (c) The 68 build stations' allocation

Population: the 68 stations with a built `buildmodule*` entry; 53 post ≥ 4 buy
offers; 29 of those have a ship queue.

### BOM-proportional allocation — **REJECTED**

Model: allocate the station's total derived *volume* across wares in proportion
to the outstanding ship-BOM volume, i.e.
`model_w = (Σ_v derived_v·vol_v) · (bom_w·vol_w / Σ_v bom_v·vol_v) / vol_w`.
Scale is therefore free and generous — it is handed the true total.

| metric | value |
|---|---|
| (station, ware) cells scored | 416 |
| **model BELOW the offer-derived lower bound** | **314 (75.5 %)** |
| model/derived | median **0.104**, p10 0.000, p90 1.904 |

Under the standing rule (`stock + inbound + open buy` is a **lower bound**; a
model value below it is a real error, above it proves nothing) this is a
straightforward refutation, and it is not a scale problem: the scale was fitted.

Per-station Pearson(derived, BOM) across wares looks deceptively good — median
**0.960**, IQR 0.827–0.988 over the 29 queued stations — because both vectors
span four decades and are dominated by energycells and hullparts. It is
**below** the 0.9984 that the plain proxy achieves cross-station, and the
volume-basis correlation drops to median 0.732 (IQR 0.388–0.871). Correlation
is not the discriminator here; the lower-bound rule is. Recorded so the same
0.96 is not mistaken for support later.

Two further refutations that need no fitting at all:

- **24 of the 53** build stations with ≥ 4 buy offers have **no ship queue**,
  hence BOM ≡ 0, and hold a median **50.0 M Cr** of derived allocation
  (queued ones: 86.1 M Cr). A proportional model predicts zero.
- The corpus stability/turnover result of § (a): allocation CV 0.0107, BOM CV
  0.511, queue overlap 0.

### What the allocations DO look like [FINDING]

- **Design-determined and highly reproducible.** Cross-station Pearson of the
  derived per-ware allocation vector (≥ 6 shared wares):

  | pair type | n pairs | median r | p25 | p75 | frac r > 0.99 |
  |---|---:|---:|---:|---:|---:|
  | same built-`buildmodule` signature | 134 | **0.9986** | 0.9857 | 0.9996 | 0.664 |
  | different signature | 531 | 0.9598 | 0.8562 | 0.9827 | 0.121 |

  The 0.9986 reproduces the storage model's recorded 0.9984 on two Argon
  wharves and generalizes it to 134 pairs across the save.

- **Approximately separable** into a per-station scale and a per-ware constant.
  Fitting `log alloc(s,w) = A_s + B_w` (alternating means, 647 cells,
  53 stations, 45 wares) gives residual sd **0.602** against a total sd of
  1.836 — **R² 0.892**, median |residual| 0.379, i.e. a typical **1.46×** miss.
  Good enough to say the structure is mostly multiplicative, nowhere near the
  trade-station equal-hours law (which reproduces player readings to 0.20 %).

- **Not equal-share on any obvious axis.** CV across wares of the derived
  allocation, per station: **units 1.940**, **volume 1.195**, **credit value
  1.404** (medians) — against a trade station's 0.00004 in volume. The
  per-ware factor `B_w` is likewise not flat in any unit: CV of `B_w` 1.883,
  of `B_w × volume` **1.160**, of `B_w × price_avg` 2.573. Volume is the least
  dispersed of the three, so whatever the rule is, it is closer to a
  volume-share than to a value- or unit-share — but it is not one.

- **The station scale `A_s` is not explained by size.** corr(A_s, log built
  modules) = **−0.122**; log build modules **0.264**; log workforce **0.198**;
  log queued BOM units **0.288** (n = 29). Nothing tried accounts for it.

*Negative result recorded precisely, per the plan's own pass criterion.* The
proxy `max ≈ stock + inbound + open buy` stays the right answer for build
stations, and it is now known to be **stable to ~1 % over 15,300 s**, which is
a materially stronger warrant than it had.

---

## Rejected candidates

| candidate | population | why rejected |
|---|---|---|
| yard denominator = `stock + inbound + outstanding BOM` (E-028) | 653 yard buys | bin RMSE 0.4355 vs 0.0792 for the proxy; 10 of 16 bins degenerate to fill 1.000 spanning the whole band |
| yard denominator = outstanding BOM alone | 241 | bin RMSE 0.5887; median fill 3.0 (clipped) |
| yard denominator = `bom + stock` | 653 | 0.4381 |
| yard denominator = `amount + bom` | 652 | 0.2834 |
| BOM-proportional build-station allocation | 416 cells | 75.5 % of cells below the offer-derived lower bound; median model/derived 0.104; 24 of 53 stations have no queue at all |
| build-storage curve = cosine, on the independent denominator | 432 | bin RMSE 0.3084 vs 0.0725 for flat-then-line |
| build-storage curve = warped cosine `cos(π(u+0.053)/1.095)` | 432 | 0.4261 |
| build-storage curve = clamped line | 432 | 0.2844 |
| build-storage curve = the yard's power k=2.60 | 432 | 0.1629 |
| build-storage demand = unbuilt-module BOM alone | 1,381 | covers only 432 offers; 949 sit on fully-built stations |
| build-storage demand = *missing* (planned − installed) loadout BOM | 209 | median 0.092 of the proxy; L-size groups are not 1:1 with turrets, so the difference is not computable from the save alone |

---

## Recommendations for the Phase 4 docs-sync agent

Register edits are **not** applied here. Recommended:

1. **E-028 → FALSIFIED**, with a NEW entry taking over the surviving half.
   The killer: the outstanding BOM is ≤ 69 % (median 0 %) of the offer-derived
   allocation and swings at CV 0.511 across epochs while the allocation holds
   at CV 0.0107 with total queue turnover. The new entry should read
   approximately: *"The yard book is the same clamped-power family on the
   ordinary `stock + amount` target, with exponent k ≈ 2.6 — not on build
   demand"*, predicting k = 2.62 / MAD 0.0399 / bin RMSE 0.0792 on 677 offers
   on save 71, and noting the unexplained ~0.17 band floor at full.
2. **E-068 stands, but `savegame-structure.md` § Stations needs a correction**:
   its conclusion "a per-order bill-of-materials model for wharf/shipyard
   construction demand is closed, not a gap — the save does not carry the
   quantities" is wrong on the premise. `<build type="buildship" component=>`
   resolves to a real ship component (214/214 on save 71) with its full
   equipment tree, so the BOM *is* computable; it is closed because the demand
   is two orders of magnitude too small, not because it is unreadable. Suggest
   marking the old sentence SUPERSEDED and citing this report.
3. **E-118 → keep CONFIRMED and drop the denominator caveat**, or supersede
   with a sharper entry: the flat-then-fall shape and the cosine's rejection
   reproduce on an *independent* module-BOM denominator (knee 0.57, bin RMSE
   0.0725 vs cosine 0.3084). Add the knee's spread (0.41 on save 70, 0.50 on
   save 71 self-referential, 0.57 independent) rather than a single value.
4. **New entry (PENDING)** for the loadout hypothesis of § "The missing half":
   build storages fund module turret/shield replacement; whole-installed-loadout
   replacement BOM vs proxy r = 0.887 over 898 offers, median ratio 1.61.
5. **`models/station-storage-model.md` § Build stations keep the proxy** —
   the sentence *"Their real driver is presumably the build bill of materials;
   that model does not exist yet"* should be replaced: the BOM is now measured
   and **rejected**. Add the two new positives (same-signature cross-station
   r = 0.9986 over 134 pairs; corpus CV 0.0107 over 15,319 s) and the rejected
   table rows above.
6. **`models/station-pricing-model.md` § Populations that do NOT use this
   model** — the yard row's "same family, different exponent (k ≈ 2.6)" is
   confirmed on 71; the build-storage row's "not on the cosine (bin RMSE
   0.44–0.50)" should gain the independent-denominator numbers.
7. Contradictions section: nothing here touches (8) or (9).

---

## Should a parser handler be promoted (Phase 3)?

**Recommendation: a narrow YES, and not the one P8 was aimed at.**

- **Do not** promote a ship-BOM handler for pricing. It is measurably useless
  as a denominator, and the demand it computes is a rounding error against the
  allocations it would explain.
- **Do** consider promoting the build-task tree itself, which is cheap and
  currently thrown away:
  - `build_task(save_id, host_id, build_id, type, ctx, target_component,
    builder, faction, time, state, step, steps, method, sequence_index,
    order_id)` — ~1,458 rows on save 71, from `<build>` elements that carry
    `type`/`order`. Cost: one `elif` on the existing element dispatch, no
    second sweep. It yields, for the first time, **the build-storage → station
    link** (593 exact pairs via `type="expand"` `@component`), which today has
    to be inferred, and per-yard order books for the shipyard/wharf views.
  - `build_task_target` — resolving `@component` against the component table
    gives the queued/repairing ship's macro and code with no extra parsing.
  - **`module_loadout_plan(save_id, host_id, entry_id, kind, macro, group)`** —
    the `<entry><upgrades><groups>` rows, ~330 k in the save but ~110 k after
    the three-way plan dedup (`construction` / `buildtasks` / `snapshot`), and
    the only route to the loadout hypothesis in § "The missing half". This one
    is the largest and should be weighed against its value; a per-host
    aggregate (counts per macro) would be 1/50th the rows and enough.
  - Both need the existing per-host dedup discipline (a plan is listed up to
    three times, entry ids are unique only per station).
- Anything promoted must keep the single-pass rule and stay defensive: on 71
  every macro resolved, but a mod adding a ship or module macro absent from the
  packaged CSVs must fall through to NULL, not raise.

---

## Notes for other Phase 2 items

- **`v_build_method` is live and correct** on the current DB; method resolution
  mattered here only for `turret_tel_m_shotgun_02_mk1` and similar wares that
  have a `closedloop` variant, but the fallback path (`method → default → any`)
  should be reused rather than reinvented.
- **The corpus's build-station series are stable to ~1 %** (§ (c)). Anyone
  using build stations as a control population can treat their allocations as
  constant over the corpus span; anyone using them as a *time-varying* signal
  cannot.
- **Yard queues turn over completely in under 2,000 s.** Any claim keyed on a
  specific queued ship must be re-derived per epoch; there is no cross-save
  identity to hang on.
- **P4 / cap scope:** 20.1 % of yard buy offers are clamped at band max and
  none at band min; if the 5 M cap is re-tested on yards, note that
  fill-price-spread already rejected it there (bin RMSE 0.3355 → 0.6310) and
  nothing here changes that.
- **The `<build><resources><insufficient>` trap (E-068) is live in this data**:
  747 `build_resource` rows in the DB on save 71 (634 `insufficient`,
  113 `shortage`). They were not used for anything in this report and should
  not be.
