# How X4 station storage allocation works (generalized form)

Reference for the storage/market work, and the sibling of
[station-pricing-model.md](station-pricing-model.md) — the allocation computed
here is the denominator the price curve runs over. Assembled 2026-07-29 from
three sessions of reverse engineering against `save_001` plus in-game readings
taken by the player from the Logical Station Overview. Implemented in
`analysis/storage.py`; the rule-by-rule notes are in
[../reference/save-semantics.md](../reference/save-semantics.md) § Market data
semantics, the derivations in
[../plans/handoff-storage-price-2026-07-28.md](../plans/handoff-storage-price-2026-07-28.md),
and every claim's status in
[../experiments/README.md](../experiments/README.md) § Storage allocation.

Claims are tagged by confidence:

- **[UI]** — the game states it outright in the Logical Station Overview.
- **[OBS]** — measured in save data, with the population size given.
- **[EXP]** — established by an in-game reading or controlled action.
- **[INF]** — inferred, consistent with the data, not independently verified.

**This model is the best-validated thing in the project: 131 of 132 in-game
readings within 1 %** (`uv run python tests/readings.py`), across **thirteen
stations and eight factions**, single- and multi-ware producers, three trade
stations (one of them multi-species), and all four transport pools. The single
failure is EIJ-609's hull parts, below.

## The mechanic in one paragraph

A station does not size storage per ware in units — it sizes it in **hours**.
Each transport pool (container / liquid / solid / condensate) is divided so
that **every production ware in it holds the same number of hours of its own
throughput**, after rations have taken a fixed 4-hour buffer off the top. So a
ware that moves fast gets a big allocation and a ware that trickles gets a
small one, and they all run dry at the same moment. A station with no
throughput at all — a trade station, or a pool nothing touches — divides the
same space by head count instead, one equal *volume* share per ware it trades.
The only hard parts are computing each ware's throughput correctly — which the
savegame mostly states outright — and remembering that the pool, not the
station, is the unit of division (and that a mixed-tag storage module makes one
pool out of several transports).

## The derivation, as pseudocode

```
FOOD_HOURS = 4

for each station:

    # ---- pools are GROUPS of transport tags, not tags ----------------------
    # a storage module whose cargo_tags name several pools holds ONE shared
    # space, so union the tags such a module links and divide per group.
    groups = connected components of {module.cargo_tags} over built modules
    group_cap[g] = Σ m.cargo_max over modules serving g

    # ---- rations, for the races PRESENT in the workforce -------------------
    # the EMPLOYMENT TARGET, never the live population
    basis = Σ m.workers over built modules      # production + buildmodule
          + station.macro.workers               # the design's own target
    if basis == 0: basis = Σ workforce.amount   # no design declares neither
    if no workforce at all: no ration reserve
    for each race r present, with share f of the live workforce:
        head = floor(basis × f)                 # floored PER RACE
        for each input i of workunit_busy/r:
            ration_units[i] += floor(i.amount/200/i.time × 3600 × head × FOOD_HOURS)

    # ---- non-producers: equal VOLUME, and stop here ------------------------
    if station has no production module (and no build module):
        for each group g:
            W = wares traded (buy or sell, NOT flagged supplies|shady) in g
            share = (group_cap[g] − Σ ration_volume in W) / |W − rations|
            max[w] = ration_units[w] if w is a ration else share / w.volume
        continue                                          # yards: proxy below

    # ---- 1. pool capacities, from BUILT modules only ------------------------
    for m in station.modules where m.built:
        for tag in m.cargo_tags:            # container / liquid / solid / condensate
            pool_cap[tag] += m.cargo_max    # absent module_cap row ⇒ contributes 0

    # ---- 2. hourly flows ---------------------------------------------------
    for m in station.modules where m.built and m has a recipe:
        eff = m.<production><efficiency product=>        # the save's own number …
        if m has no <production> block: eff = 1.0        # … idle: bare recipe, not a guess
        if m is multi-queue (efficiency with no <queue ware>):
            rescale eff per recipe via that module's smallest work_effect
        for each product p of m:
            out[p] += floor(p.amount × eff) / p.time × 3600      # FLOOR PER CYCLE
        for each input i of m's recipe:
            inp[i] += i.amount / i.time × 3600                   # base rate, NO eff
        # a module running two products alternately contributes half of each

    flow[w] = max(out[w], inp[w])           # dual-role ⇒ the LARGER, not the output
    # processing modules (scrap works) contribute their OUTPUT only; their own
    # inputs never enter flow[]. Non-economy feedstock (rawscrap) is never stocked.

    # ---- 3. split each pool, equal hours ------------------------------------
    for pool, capacity in group_cap:
        wares = { w : group_of(w.transport) == pool }

        if no recipe anywhere produces or consumes any of `wares`:
            # storage-only pool (condensate). No throughput ⇒ no hours to equalise.
            for w in wares: max[w] = capacity / count(wares) / w.volume
            continue

        food_volume = Σ over rations r in wares of  ration_units[r] × r.volume
        Σflow       = Σ over w in wares of          flow[w] × w.volume

        T = (capacity − food_volume) / Σflow          # the pool's equal-hours factor

        for w in wares:
            max[w]  = flow[w] × T                     # production share
            if w is a ration:
                max[w] += food[w] × FOOD_HOURS        # ADDITIVE, not exclusive
```

Two places this is easy to get wrong, both of which cost real time:
`floor()` sits inside the cycle and not on the hourly rate, and `eff` multiplies
outputs only. Section [Throughput](#throughput--the-part-that-is-easy-to-get-wrong)
gives the numbers for both.

## The generalized form

Per station, per transport pool:

```
T   = (pool_capacity − Σ ration_volume) / Σ (throughput × ware.volume)

max(production ware) = throughput × T
max(ration)          = consumption × FOOD_HOURS          FOOD_HOURS = 4
```

- `pool_capacity` = Σ `module_cap.cargo_max` over the station's **built**
  modules whose `cargo_tags` name that pool.
- `T` is the pool's **equal-hours factor**, typically 4–9 h.
- The two terms are **additive, not exclusive** [EXP]: the ration buffer comes
  off the pool for *every* ration, including one the station makes itself, and
  a producer then takes a normal production share **on top**. Confirmed on
  JFV-172, which makes cheltmeat and feeds it to its own workers:
  12,757 + 306 = 13,063 against 13,062 read in game, with spices landing on
  20,051 exactly. Treating the roles as exclusive put spices at 37,192.

### Throughput — the part that is easy to get wrong

```
output(ware) = Σ over modules  floor(recipe.amount × efficiency) / recipe.time × 3600
input(ware)  = Σ over modules  recipe.input_amount / recipe.time × 3600     (base, no bonus)
ration(ware) = per-race workunit_busy input × jobs
```

**`efficiency` is stated in the savegame — do not reconstruct it [OBS].** Every
production module carries `<production><efficiency product=>`, and that single
number is the *complete* multiplier: workforce bonus × sector sunlight × mod
effects, already combined. Scored against offer-derived allocations over 4,914
(station, ware) pairs:

| basis for output throughput | within 1 % |
|---|---:|
| **save `efficiency`, outputs only** | **87.2 %** |
| reconstructed `work_effect` × sunlight | 76.7 % |
| no multiplier at all | 50.9 % |
| `efficiency` on outputs **and** inputs | 49.9 % |

The gap is entirely on modded stations: where `efficiency == 1 + work_effect`
(579 stations) both bases score 92.9 %, but on the 539 stations the mod touches,
reading the field scores 79.7 % against 55.5 % reconstructed. On a modded save,
reading the field is the only mod-proof route.

**Inputs are NOT scaled by efficiency [OBS].** Consumption stays at the base
recipe rate. Scaling it breaks IFO-957 by +23 % and TPF-229 by +16 %.

**The engine truncates per CYCLE, not per hour [EXP].** `floor()` applies to the
cycle's amount before the hourly rate is derived: 97.92 → 97 microchips,
195.91 → 195 smart chips, 141.55 → 141 coolant, 7/7 against player readings.
Order matters — DLB-176's observed 42,480 energy cells/h only lands if sunlight
is folded in *before* the floor. Multiplying at the hourly level leaves
fractional units, reads high by 0.01–0.9 %, and perturbs the *ratios* the pool
split runs on, not merely the absolute rates.

### Module-level rules

- **A module with no `<production>` block is idle and runs the bare recipe**
  (multiplier 1.0), not a reconstructed work effect [OBS]. 939 (station, macro)
  pairs are in this state. Confirmed on KRV-460, whose four inputs all came in
  at exactly 0.724 of truth — `1/0.724` recovers the 1.53 work effect the
  fallback was wrongly applying. Treating them as 1.0 lifted this group from
  43.6 % to 73.8 % within 1 %, and the whole computed population from 82.9 % to
  86.2 %.
- **A multi-queue module reports one efficiency with no `<queue ware>`** [OBS].
  It belongs to one of the module's recipes, which can have different work
  effects, so recover the workforce ratio against the module's smallest work
  effect and re-apply each recipe's own. Key on `(station, macro)` as well as
  `(station, macro, ware)`.
- **The alternation split cancels out [EXP].** A module alternating between two
  products is modelled at 50/50 of each, and that is right: IRD-672's three
  recyclers give `3 × (144,000 + 42,000)/2 = 279,000` energy cells/h, which
  reproduces its in-game 1,665,000-unit allocation. The split scales every rate
  on the module equally and cancels out of the equal-hours division.
- **Dual-role wares are sized by the LARGER flow** [EXP], not by the output.
  KWC-232 makes 208,708 energy cells/h and feeds 372,000/h to its recyclers;
  the game allocates on the consumption side.
- **Processing modules are outside the split entirely** [OBS]. A scrap works'
  recipe is quoted per unit of scrap, not per timed cycle, so it has no hourly
  rate to contribute. Its *output* is stored normally — IRD-672's scrap metal
  reads 40,000 exactly. Its `rawscrap` feedstock is never stocked at all, and
  the player confirms the game's own UI keeps raw scrap separate from ware
  storage [EXP].
- **Solar output scales with sector sunlight** [EXP], already inside
  `efficiency`, so it must not be applied twice.

### Pools

The pool list is **read from the data** — the distinct `ware.transport` values,
matched word-for-word against `module_cap.cargo_tags` — not hardcoded. Four
exist: `container`, `liquid`, `solid`, `condensate`.

**A pool no recipe touches has no throughput and no equal-hours split** [EXP].
Its allocation is simply capacity ÷ ware volume. Only condensate ("Protectyon",
Pirate DLC) qualifies; container/liquid/solid always have recipes. Confirmed on
IRD-672: one 50 m³ module ÷ volume 10 = **5 Protectyon**, read in game.

## Non-producing stations: the same rule, degenerate

A station with no recipes has no throughput, so there are no hours to
equalise — and the split falls back to **equal volume per traded ware**, which
is exactly the storage-only-pool rule above applied to every one of its pools:

```
share  = (group_capacity − Σ ration_volume) / n_traded
max[w] = share / w.volume                      rations: the 4 h buffer, as usual
```

- **`n_traded` is the station's TRADE LIST** [OBS] — every ware it posts an
  offer for, either side (a sell offer with `amount = 0` counts), excluding
  `supplies` and `shady`. A ware sitting in cargo with **no offer is loot and
  gets no allocation** (KPU-277 holds four such wares outside its 3-ware
  division).
- **A station with no workforce takes no ration reserve** and its ration wares
  become ordinary traded wares with a full share [OBS] — six Terran trade
  stations, JJX-981 among them, all exact.
- **The UI shows the floor** of `share / volume`: DHI-588's advanced composites
  are `2,182.67` and read **2,182**, its scanning arrays `1,838.04` → 1,838.
  Across 561 trade-station pairs `floor` is exact 537 times against `round`'s
  243. (`analysis/storage.py` keeps the unrounded value, as it does on the
  producer path.)

CONFIRMED 2026-07-29 on **DHI-588** — 40 in-game readings, three pools, three
races — and save-wide against `stock + inbound + open buy` on 601/634 pairs
within 1 % (the old proxy: 556). Worked in full in
[../reports/mixed-race-rations-2026-07-29.md](../reports/mixed-race-rations-2026-07-29.md)
and, independently and concurrently, in
[../reports/trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md),
which scores 537/561 pairs exact with **zero** over-runs and puts the median
coefficient of variation of allocation-volume across a group's wares at
**0.00004**.

### Build stations keep the proxy

Wharfs, shipyards and equipment docks are a different population and this rule
is **false** for them: 33 % of their wares exceed the equal share, QJI-262
spans 205× across seven wares, median CV 0.80 against a trade station's
0.00004. Classify by a built `buildmodule*` entry, **not by station macro** —
52 build stations wear `station_gen_factory_base_01_macro`. For them
`max ≈ stock + inbound + open buy amount` (`source='proxy'`) stands, verified
genuinely allocated storage (two same-faction Argon wharves at Pearson
**r = 0.9984** despite different fill). Their real driver is presumably the
build bill of materials; that model does not exist yet.

Excluded from both paths: **`supplies`-flagged** buys (self-supply for the
station's own drones/munitions, delivered to a separate inventory — emitted as
`role='supply'` rows instead) and **`shady`-flagged** buys (a black-market book
backed by no stock; they were minting 546 phantom allocation rows across 143
non-producing stations before being dropped).

### Rations across several races

The ration buffer is keyed on the races **actually present** in the workforce,
not on the ware being some race's ration [EXP]: DHI-588 has argon, paranid and
teladi workers, and **water** — the Boron ration — is an ordinary traded ware
there at 11,640 = 69,845/6, alongside maja snails, meat and swamp plant.

The buffer is **floored per race, then summed** [EXP]. DCO-580 (argon 65 /
boron 125 / paranid 63) allocates 1,163 medical supplies = 334 + 495 + 334;
boron's rate is 33 per 200 workers against the others' 45, and one floor on the
summed rate gives 1,164. DHI-588 repeats it in game: 1,338 = 961 + 172 + 205.

### The basis is the EMPLOYMENT TARGET, not the population [EXP]

```
target = Σ module_cap.workers over built production + buildmodule modules
       + module_cap.workers on the STATION's own macro, if it declares one
```

The game shows this number in the station's Workforce tab. It is a property of
the design and its build, not of who lives there: **PTW-627 reserves 4 h for
1,000 workers while 104 live in it**, and the player reads "Employment target
1000" in its UI. The eight station-class macros declare

| design | target | | design | target |
|---|---:|---|---|---:|
| `station_gen_piratebase_base_01` | 150 | | `station_par_tradestation_base_01` | 400 |
| `station_arg_tradestation_base_01` | 250 | | `station_tel_tradestation_base_01` | 1000 |
| `station_bor_tradestation_base_01` | 250 | | `landmarks_tel_tradestation_01` | 1000 |
| `station_{spl,ter}_tradestation_base_01` | 300 | | | |

and all eight match the reserve the save's own ration offers imply, exactly.

- **It is a SUM, not a fallback** [OBS]: MOP-635 (Argon trade-station macro 250
  + build modules 400) implies exactly 650, TTV-091 3,000 + 150 = 3,150.
- **Habitation `<workforce max>` is CAPACITY, not demand** [OBS] — it lands in
  `module_cap.housing` and must not be summed in. Housing matches the implied
  basis on 0 of 31 non-producers and 4 of 1,066 producers.
- Scored save-wide against the ration-implied basis, the sum has **median ratio
  1.0000 for every station design** and 1,118 of 1,150 within 1 %: 1,066
  gen_factory producers, 50 yards (wharfs 800, shipyards to 3,150, out of the
  same sum with no special case) and the seven trade/pirate designs.
- **No workers ⇒ no reserve**, whatever the design declares (GMJ-316: target
  250, no habitat module, food rations take a full 57,142 trading share).
- The target is split across races by the **live** mix and the headcount is
  **floored per race**: DHI-588's 250 over 179/33/39 → 178/32/38, and its four
  in-game ration maxima all land to the unit. DCO-580 disagrees and wants its
  *habitat* mix instead — recorded as contradiction (9) in the register.

This replaces the "the buffer lags the live workforce" reading (E-121,
FALSIFIED): nothing lags. DHI-588 holds 179/33/39 in three snapshots 20,000 s
apart with the same reserve throughout, and PTW-627's reserve sat at 1,000
while its workforce went 376 → 546 → 104 → 160.

## Validating it

**Against in-game readings** — the authoritative source.
`tests/data/station_readings.json` holds each station's model inputs alongside
the values the player read, and `tests/readings.py` replays them without a
savegame. Currently **86/90**. DHI-588 is now the broadest single check — 40
readings, three pools, three races, 37 within 1 % (36 of 36 non-ration wares to
the unit; the three misses are E-121's ration lag) — with IRD-672 the broadest
on the producer path at six wares across two pools, every one within 0.2 %.

**Against the save itself** — `stock + inbound + open buy amount` is the
station's own statement of what it can hold. It is a **LOWER BOUND, not an
equality** [OBS]: a station bids only for what it can *use*, so MAL-475 reads
157,810 derived against a true 1,498,962 because its consumers are unbuilt. A
model value *below* it is a real error; a model value *above* it proves
nothing. It **is** saturated — equal to the allocation at median ratio
**0.9999** — for production inputs that actually post a buy offer, which turns
validation from 18 hand-read numbers into thousands of ground-truth points per
save.

**A full station withdraws its buy offer entirely** [EXP] rather than pricing
it at zero, so the derived quantity vanishes exactly as stock reaches the
allocation. Coverage is 99.7 % below 90 % fill, 38 % at 100–110 %, 5 % above.

**Allocation is a trade/target level, not a physical cap** [UI]. MBI-471 holds
14,330 energy cells against a 4,403 allocation *in the game's own menu*, so
"stock > allocation" is not evidence of a modelling error.

## Rejected — do not re-test without new evidence

| candidate | how it died |
|---|---|
| a non-producer's allocation is `stock + open buy` and nothing better | it is `(capacity − rations)/n_traded/volume`, exact: DHI-588 36/36 non-ration readings, 601/634 save-wide against 556. The proxy was a *fill-dependent* reading of an allocation that does not depend on fill |
| the ration reserve is sized on the live workforce | it is sized on the design's EMPLOYMENT TARGET. PTW-627 reserves for 1,000 with 104 present; 31 of 31 single-race non-producers match their declared target exactly |
| the ration reserve lags the workforce (E-121) | nothing lags — DHI-588 is static across 20,000 s and still 1 worker per race "behind", which is the 250 target scaled to its 251 live workers |
| the ration basis is the station's habitat CAPACITY | 0 of 31 non-producers, 4 of 1,066 producers. Housing is capacity, not demand |
| the ration role belongs to a ware because some race eats it | put `role='food', max=10,390` on DHI-588's water, which the game allocates as an ordinary traded ware at 11,640. It is keyed on the races present |
| a mixed-tag storage module gives each of its tags the full capacity | triple-counts: JDV-447's 21 wares across two transports share one 1,200,000 m³ bay |
| `stock + open buy` is the offer-derived allocation | the inbound term is not optional — `stock + inbound + open buy`. Omitting it read low on 96 of 561 trade-station pairs, one-sided, and closed every DHI-588 miss exactly |
| the price curve's target level is the storage allocation | true for the bulk, false in general — Tidebreak prices over 173 units against a 5,000 allocation. See [station-pricing-model.md](station-pricing-model.md) |
| a starving workforce drops out of the allocation basis | fits EIJ-609's six wares exactly, and is worse save-wide under **every** definition tried: 93.8 % → 83.6–91.6 % within 1 % |
| reconstructing the multiplier from `work_effect` × sunlight | 76.7 % against the save field's 87.2 %, and it cannot work on a modded save |
| applying `efficiency` to inputs as well as outputs | 49.9 %, worse than applying no multiplier at all |
| rating energy cells at recipe speed everywhere | ignores sunlight; inflated solar throughput by 1/sunlight and skewed every station making energy cells alongside anything else |
| food and production roles as mutually exclusive | put JFV-172's spices at 37,192 against a real 20,051 |
| counting a scrap works' own energy draw in the split | misses by 5 % on energy cells and 15 % on hull parts |
| "the engine sizes on the currently queued recipe" | killed by IRD-672's readings — the 50/50 alternation split reproduces them |
| `<workforces><bonus busy=>` as a bonus on/off switch | `busy=0` on 1,132 of 1,244 workforce stations, including plainly bonused ones; it looks like a cycle phase |

## Known exceptions and open questions

1. **EIJ-609** — its production *rate* follows the reported efficiency 1.12634
   exactly (3,972/h) but its *allocation* follows a multiplier of 1.0: 34,829
   hull parts read in game, twice, against a modelled 37,228. **HYPOTHESIS**:
   the allocation is recomputed lazily and lags a recent efficiency change.
   *Falsifiable* by re-reading after playing forward — the lag predicts a drift
   to ~37,228. This is the one reading the model cannot reproduce.
2. **War-pressure bonuses enter the rate but not the allocation** [EXP], so the
   two must be separated. `efficiency / (1 + work_effect)` is exactly 1.000 for
   the plurality of modules in every faction, so the vanilla part is
   recoverable in principle. **Not yet implemented.**
3. **`nd_habitat_cap_boost` is not registered** in `gamedata/modpatch.py`. It
   replaces habitat workforce capacity with S 2500 / M 5000 / L 10000 against a
   stock 333/666/999. Workforce drives both the ration buffer and the
   efficiency, so this is a known-wrong input rather than an unknown rule.
4. **Hybrid production + build stations** keep the computed path only; their
   build inputs are omitted. MXH-411 cannot settle whether that is right
   because it carries player-set `ware_limit` rows. *Needs* an NPC station with
   both a production and a build module.
5. **Multi-stage internally-cycled wares** (gross vs net flow) are not modelled.
6. **How the employment target splits across races is unsettled.** DHI-588
   (in game) needs the LIVE race mix; DCO-580 (save-derived) needs its HABITAT
   capacity mix; EMY-219 cannot tell them apart. The model uses the live mix.
   ±3 workers on a 250-worker reserve. *Settles it:* a third multi-race station
   read in game. Register contradiction (9).
7. **Build-station allocation** (wharfs / shipyards / equipment docks) has no
   model at all — only the `stock + inbound + open buy` lower bound. The
   equal-volume rule is *false* there. QJI-262's seven wares span 205× in
   allocation-volume; a bill-of-materials model is the obvious candidate.

## A note on inputs versus rules

The one model failure large enough to notice in three sessions was **not a
model failure**. JAR-041 read 42,516 energy cells against 21,001 in game — a
clean factor of two — because the parser marked an unbuilt storage module as
built, doubling the pool capacity. The rule was right and its input was wrong.
When a station is off by a suspiciously round factor, check the inputs before
touching the model: a *constant scale* error across all of a station's wares
points at capacity or throughput, whereas a *constant shift* points at pricing.

## A worked example, end to end — WRC-739

ARG Advanced Electronics Factory, Argon. Chosen because it is the simplest
station in the fixture that still exercises three rules people get wrong, and
because all four of its allocations were read in game.

**The station.** 2 × `prod_gen_advancedelectronics` (540 workers each),
1 × `storage_arg_m_container` (250,000 m³), plus structure and defence. Two
details matter:

- **Its workforce is empty and neither production module carries a
  `<production>` block.** So `eff = 1.0` — the bare recipe — not a
  reconstructed work effect. Getting this wrong is what put KRV-460 out by a
  factor of 0.724.
- **No workforce means no rations, so no 4 h buffer comes off the pool.** This
  is the clean case: `T` is just capacity ÷ Σflow.

### Step 1 — the recipe (mod-patched)

This save runs Faction Fix Pack, which rewrites `advancedelectronics`. The
values below are the patched ones applied at runtime by
`gamedata/modpatch.py`; the **stock** recipe is amount 54 / inputs 60, 44, 20 /
work_effect 0.36 and would give the wrong answer here.

```
advancedelectronics/default:  time 720 s, amount 65
   inputs: energycells 150, microchips 49, quantumtubes 36
```

### Step 2 — hourly flows, ×2 modules, eff = 1.0

```
out  advancedelectronics = floor(65 × 1.0) / 720 × 3600 × 2 =   650 /h
inp  energycells         =            150  / 720 × 3600 × 2 = 1,500 /h
inp  microchips          =             49  / 720 × 3600 × 2 =   490 /h
inp  quantumtubes        =             36  / 720 × 3600 × 2 =   360 /h
```

### Step 3 — one pool, no food buffer

All four wares are `container`. With volumes 30 / 1 / 22 / 22:

```
Σflow = 650×30 + 1,500×1 + 490×22 + 360×22
      = 19,500 + 1,500 + 10,780 + 7,920      = 39,700 m³/h

T = (250,000 − 0) / 39,700 = 6.2972 h
```

### Step 4 — allocations, and the in-game check

```
max[ware] = flow × T
```

| ware | flow /h | × T | model | **read in game** |
|---|---:|---:|---:|---:|
| advanced electronics | 650 | 6.2972 | 4,093.20 | **4,093** |
| energy cells | 1,500 | 6.2972 | 9,445.84 | **9,445** |
| microchips | 490 | 6.2972 | 3,085.64 | **3,085** |
| quantum tubes | 360 | 6.2972 | 2,267.00 | **2,267** |

Four for four, each to the unit once truncated. Every ware sits on the same
**6.30 hours** — which is the whole model in one line.

### The same arithmetic where it gets hard — IRD-672

The scavenger recycler in Avarice I runs every awkward rule at once, and its
six allocations were also read in game. Two pools, and the container one
carries a ration buffer:

```
container: capacity 2,300,000 m³
  food_volume = 34,560×1 (rations) + 20,736×2 (medical)      =    76,032
  Σflow       = 279,000×1 + 1,440×24 + 4,932×12              =   372,744
  T           = (2,300,000 − 76,032) / 372,744               =  5.9664 h

solid:     capacity 400,000 m³
  Σflow       = 9,000 × 10 (scrap metal)                     =    90,000
  T           = 400,000 / 90,000                             =  4.4444 h

condensate: capacity 50 m³, no recipe touches it
  max         = 50 / 10                                      =  5 units
```

| ware | pool | model | read in game |
|---|---|---:|---:|
| energy cells | container | 1,664,647 | 1,665,000 |
| claytronics | container | 8,592 | 8,577 |
| hull parts | container | 29,427 | 29,379 |
| food rations | container | 34,560 | 34,560 |
| medical supplies | container | 20,736 | 20,736 |
| scrap metal | solid | 40,000 | 40,000 |
| condensate | condensate | 5 | 5 |
| raw scrap | — | *no row* | *no allocation* |

Its 279,000 energy cells/h is the interesting number. The station both makes
energy cells (one module at Avarice's 19.877 efficiency → 208,680/h) and feeds
them to three recyclers that alternate between claytronics and hull parts
(3 × (144,000 + 42,000)/2 = 279,000/h). The dual-role rule takes the **larger**,
so consumption wins; and the 50/50 alternation split is what makes the
1,665,000 reading come out right. Meanwhile the scrap works contributes its
*output* (scrap metal, 40,000 exact) while its own energy draw stays out of the
split, and `rawscrap` — 1,993 units of it in cargo — gets no allocation at all,
which the game's own UI corroborates by keeping raw scrap out of ware storage.

## One-pager

```
per station, per transport pool (container / liquid / solid / condensate):

  T   = (pool_capacity − Σ ration_volume) / Σ (throughput × ware.volume)
  max = throughput × T                    rations: consumption × 4 h  (additive)
  ration consumption runs on the EMPLOYMENT TARGET (Σ production/buildmodule
    workforce max + the station macro's own), split by the live race mix,
    floored per race. No workers ⇒ no reserve.

  output(ware) = Σ floor(recipe.amount × efficiency) / recipe.time × 3600
  input(ware)  = Σ recipe.input_amount / recipe.time × 3600      ← base, no bonus
  efficiency   = the module's own <production><efficiency product=>, complete
                 (workforce × sunlight × mods). Missing block ⇒ 1.0, not a guess.
  truncate PER CYCLE, before the hourly rate.
  dual-role ⇒ max(production, consumption).  processing modules ⇒ excluded.
  a pool no recipe touches ⇒ capacity / volume, no split.

non-producers that TRADE: equal VOLUME, the same rule with zero throughput
  max = (group_capacity − Σ ration_volume) / n_traded / ware.volume
  n_traded = the trade list (either side), minus `supplies` / `shady` /
  rations of the races present; cargo with no offer is loot, no allocation
build stations (a built buildmodule*): max ≈ stock + inbound + open buy amount

pools are GROUPS of transport tags: a module tagged "container liquid solid"
  is ONE shared space, so union the tags it links and divide once

validate against: tests/readings.py (131/132 in game), and
  stock + inbound + buy amount — a LOWER BOUND, saturated for input buyers
```
