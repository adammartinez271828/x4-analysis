# Mixed-race rations, and what a trade station's storage really is

**2026-07-29.** Save `save_001.xml.gz` (db save_id 70, game time 82,130).
Started as "why does our model call water a ration on DHI-588", ended with the
non-producer path replaced: a trading station's allocation is not a proxy at
all, it is **capacity divided equally by volume among the wares it trades**.

Implemented in `analysis/storage.py`; claims registered as E-119…E-123 in
[../experiments/README.md](../experiments/README.md) § Storage allocation.

## The station

DHI-588 `[0x33296]`, *Pillars of Elysium*, Quettanauts (`kaori`), Mitsuno's
Sacrifice, `station_arg_tradestation_base_01_macro` — an Argon **design**, not
an Argon owner. No production module, so it took the `proxy` path
(`max = stock + open buy amount`). Three races in one workforce, which is the
whole point: **argon 179, paranid 33, teladi 39**.

The player read all 40 of its storage maxima off the Logical Station Overview.
They are now in `tests/data/station_readings.json` as `ingame` readings.

## Finding 1 — the readings are an exact arithmetic identity (E-119)

Every non-ration reading, multiplied by its ware's volume, is the **same
number** within its pool:

```
container  2,100,000 m³ − 4,635 m³ of rations = 2,095,365 / 30 traded wares = 69,845 m³
  energy cells      vol  1 → 69,845     smart chips    vol  2 → 34,922
  spices            vol  3 → 23,281     wheat          vol  4 → 17,461
  soja beans        vol  5 → 13,969     maja snails    vol  6 → 11,640
  hull parts        vol 12 →  5,820     scanning arrays vol 38 →  1,838     … 30 for 30

liquid     1,200,000 / 3 wares = 400,000 m³ → helium = hydrogen = methane = 66,666  (vol 6)
solid      1,700,000 / 3 wares = 566,666 m³ → ore = silicon 56,666 (vol 10), ice 70,833 (vol 8)
```

So a non-producer sizes storage exactly the way a **storage-only pool** is
sized (E-049, condensate): no recipes ⇒ no throughput ⇒ no hours to equalise ⇒
equal volume each. The trade list — the wares it posts a price for, bought or
sold — is the divisor.

This is not one station's coincidence. Over the save's 48 trading
non-producers, `derived = stock + inbound + open buy` per ware, times volume,
is constant within a pool at JDV-447, IWQ-591, RAN-388, SZM-264 and the rest;
the rule lands within 1 % of it on **601 of 634** (station, ware) pairs where
the station has an open buy, against **556** for the old stock+buy proxy — and
unlike the proxy it also sizes a ware the station holds none of and is not
currently bidding for.

**Corollary for the pricing line (not edited here):** DHI-588 now has a
*computed* allocation, and it reproduces the two numbers the cap work quoted
from its bids — claytronics 2,910 and silicon 56,666 — to the unit. E-115's
open scope caveat ("all 330 capped stations are producers; the non-producers
do not cap") is therefore no longer confounded with "the non-producer number
is only a proxy". That is for that line of work to act on, not this one.

### The unit of division is the storage GROUP, not the transport tag (E-122)

JDV-447 is one 1,200,000 m³ `storage_arg_l_tradestation_01` whose `cargo_tags`
read `container liquid solid`. Summing it per tag gives all three pools
1,200,000 each; the readings say otherwise — its 20 container wares **and** its
one solid ware (nividium) all come out on `1,200,000 / 21 = 57,142.86 m³`. A
mixed-tag module is one shared space. `analysis/storage.py` now union-finds the
tags a station's storage modules name together and divides per connected group.

Five macros are mixed in this save (`storage_arg_l_tradestation_01`,
`landmarks_tel_tradestation_01[_ring]_storage_01`, `storage_gen_buildstorage_01`,
`xenon_small_station_01_storage_01`). Forty-two Xenon **producers** carry one,
and their pool capacities were being triple-counted; they post no trade offers,
so there is no ground truth for them and the change there is inference from the
rule, not a measurement.

## Finding 2 — the ration role is keyed on the races PRESENT (E-120)

The bug the player spotted: we emitted `role='food', max=10,390` for **water**.
Water is the *Boron* ration (`workunit_busy/boron`: bofu 15, water 27,
medicalsupplies 33 per 200 workers). No Boron work at DHI-588, and the game
treats water there as an ordinary traded ware — 11,640, exactly `69,845 / 6`,
sitting alongside maja snails, meat and swamp plant on the same volume share.

The old code keyed the food role on `food_wares` = *any* race's ration ware.
It is keyed on the station's own workforce races now. The four ration wares at
DHI-588 are exactly the ones its three races eat: foodrations (argon), sojahusk
(paranid), nostropoil (teladi), medicalsupplies (all three).

### The buffer is floored PER RACE, then summed

DCO-580 (argon 65 / boron 125 / paranid 63) settles the rounding order.
Its medical-supplies allocation, saturated in the save at **1,163**:

```
argon    4 h × 45/200 × 62  = 334.8 → 334      (boron's rate is 33, not 45,
boron    4 h × 33/200 × 125 = 495.0 → 495       so this cannot be done once
paranid  4 h × 45/200 × 62  = 334.8 → 334       on the total headcount)
                                       ----
                                       1,163    ✓  exact

one floor on the sum instead: floor(1,164.6) = 1,164  ✗
```

DHI-588 gives the same answer in game: 1,338 = 961 + 172 + 205 over
178/32/38 workers, where a single floor gives 1,339.

## Finding 3 — the basis is job slots, or the population (E-123)

For a **producer** the ration buffer is sized on Σ `module_cap.workers` over
built modules, *not* on the workers actually present. Over 1,065 single-race
producers with a saturated ration buy whose ration is not in their own recipes,
the implied headcount matches the job slots on **1,034** (median ratio 1.0000)
against **793** for the live workforce. GKM-488 staffs 2 of 540 job slots and
still allocates for 540. That was already the model's behaviour and it survives.

A trade station has no job slots at all and still eats, and there the basis is
the population itself. `storage.py` now takes `jobs` when the station has any
and the live workforce otherwise, splitting per race by the present mix.

## Finding 4 — the ration buffer lags the live workforce (E-121, PENDING)

This is the residual, and it is why 3 of the 40 DHI-588 readings miss.

|ware|read|model|err|
|---|---:|---:|---:|
|food rations|1,602|1,611|+0.6 %|
|medical supplies|1,338|1,354|+1.2 %|
|soja husk|184|190|+3.3 %|
|nostrop oil|173|177|+2.3 %|

All four readings are internally consistent with **one worker fewer per race**
than the save records — 178/32/38 against 179/33/39 — to the unit, on all four
wares at once. The save's own bids agree with the readings (foodrations
1,559 stock + 43 bid = 1,602 exactly), so this is not the player reading at a
different moment: the save state itself carries a ration buffer that does not
match the workforce written two elements away, under `<workforces
lasttime="81723.853">` against a save time of 82,130.

Save-wide, the implied ration headcount is:

- **equal to the saved workforce** on 13 of 31 single-race non-producers,
- **1–2 below** on 10 more (DCO-580's argon 65 → 62, paranid 63 → 62, while its
  boron 125 → 125 is exact),
- and **far above** on four starving teladi landmark trade stations, all four
  implying exactly **1,000** against saved workforces of 104, 231, 361 and 702.

Above and below, always by an integer, and largest where the workforce is
moving fastest. That is a lag, not a scale factor: no common ratio fits
DHI-588's three races (argon needs ≥ 0.9944, paranid ≤ 0.9733), and no
integer-workforce formula from the saved values reproduces them either.

**HYPOTHESIS (E-121):** the ration buffer is recomputed on a slower cadence
than the workforce itself, so it reflects the headcount at the last recompute.
Same family as E-051 (EIJ-609's lagging efficiency).
**Falsifiable by** re-reading DHI-588's four ration maxima after playing
forward: the lag predicts they walk up to 1,611 / 1,354 / 190 / 177 and then
track the workforce again, while a fixed offset predicts they stay one worker
per race behind for ever.

**Not done, deliberately:** subtracting a worker per race would fit all four
readings and IRD-672 would still pass (−0.03 %). It is a fudge factor with one
station behind it and the population says the saved workforce is the best
single choice (13 exact against 4 at −1), so the model keeps the saved value
and carries the error.

## Scores

`uv run python tests/readings.py`

| | before | after |
|---|---|---|
| in-game readings within 1 % | 49 / 50 | **86 / 90** |
| all readings (derived as a lower bound) | 51 / 55 | 88 / 95 |

The 40 DHI-588 readings enter as 37 pass / 3 fail: **36 of 36 non-ration wares
to the unit**, food rations at +0.6 %, and the three ration misses of E-121.
The pre-existing failure (EIJ-609 hull parts, E-051) is unchanged. `uv run
pytest -q`: 247 → 254 passing.

Against the save's own lower bound on save 70 (`stock + inbound + open buy`,
6,578 pairs with an open buy offer): 86.3 % → **89.1 %** within 1 % overall.
Read that number with care: the trading population went 87.7 % → 94.8 % on a
genuine prediction, but the *build*-station rows went 84 % → 100 % only because
the proxy is now computed from the same three terms the bound is — that part is
circular and is not evidence of anything except internal consistency.

## Addendum — the parallel read-only investigation

A second agent worked the same station concurrently, read-only, and reached the
equal-volume rule independently:
[trade-station-allocations-2026-07-29.md](trade-station-allocations-2026-07-29.md).
Its report is not edited here. Everything below was re-measured against my own
code before being adopted.

Adopted, verified:

- **The inbound term was missing from the proxy.** `save-semantics.md` has
  always specified `stock + inbound + open buy amount`; `analysis/storage.py`
  computed `stock + amount`. Now fixed from `trade_pending`
  (`Σ amount − transferred`, `buyer_id` = the station). It no longer changes a
  trade station — those left the proxy entirely — but it is the correct
  definition for the build stations that remain on it, and it was a live
  code/doc contradiction.
- **Cargo with no offer is loot** and gets no allocation. Verified on KPU-277
  (63 teladianium, 18 hull parts, 4 graphene, 21 missile components, none
  offered, all outside its 3-ware division). Such rows are no longer emitted
  for stations on the split path.
- **A station with no workforce takes no ration reserve.** Verified on JJX-981:
  terran MREs and medical supplies come out at a full 125,000-unit share.
  Falls out of keying rations on the races present; no extra code.
- **Build stations must be classified by a built `buildmodule*` entry, not by
  station macro** (52 wear `station_gen_factory_base_01_macro`), and the
  equal-volume rule is FALSE for them — 33 % of their wares exceed the equal
  share. `storage.py` already classified by module and keeps them on the proxy.
- **Its H1 is my E-121**, with a second population I had not measured: four
  Teladi landmark trade stations carrying an *identical* 5,400 / 4,560 reserve
  — a flat 1,000-worker basis — against live workforces of 104 / 231 / 361 /
  702, and module housing of 6,000, so it is neither the live workforce nor the
  housing cap. Cited in the register entry.

Recorded, not adopted:

- **`floor(share / volume)` as the engine's own truncation** (exact 537 of 561
  against `round`'s 243). The direction is certainly right — the in-game
  readings are floors (advanced composites 2,182.67 reads 2,182) — but the
  save-side score cannot distinguish it from a float allocation, because the
  ground truth is `stock + inbound + buy` and stock is integral, so a saturated
  station can only ever reach `floor(allocation)`. `storage.py` keeps the
  unrounded value, exactly as it does on the producer path, and the doc records
  that the UI shows the floor.
- Its 95.7 %-of-561-exact and my 94.8 %-of-634-within-1 % are the same
  measurement over slightly different populations and denominators (it scores
  `stock + inbound + buy` and counts exact matches; I score within 1 % over
  every pair with an open buy). I did not try to reconcile the two counts and
  neither figure depends on the other.

## What would falsify each claim

- **E-119** (equal-volume split): a trade station whose in-game maxima × volume
  are *not* constant within a pool, or a station where the divisor is
  demonstrably not the trade list — e.g. one that trades 20 wares and divides
  by 21 for a reason other than a shared storage group.
- **E-120** (races present, per-race floor): a station with Boron workers and
  no Boron ration allocation; or a multi-race medical-supplies reading that
  matches a single floor on the summed rate and not the per-race floors.
- **E-121** (lag): see above.
- **E-122** (shared group): a station with a mixed-tag storage module whose
  per-tag allocations sum to more than the module's capacity.
- **E-123** (job slots): an in-game ration reading on a heavily *understaffed*
  producer matching its live workforce rather than its job slots.

## Verified untouched

The parser and DB were checked end to end for multi-race workforce and are
correct: the save carries 1,241 single-race, one two-race and two three-race
`<workforces>` blocks, and the `workforce` table holds exactly that (PK
`(save_id, station_id, race)`, accumulated per race in `db/store.py`).
DHI-588's three rows match its XML to the unit. No parser change was needed.

---

## Addendum 2 — the ration basis is the Employment Target (E-124), and E-121 is dead

**2026-07-29, later the same day.** The player supplied full in-game allocation
tables for two more trade stations — **GMJ-316** (Argon, Ianamus Zura) and
**PTW-627** (Teladi landmark), the reading this report asked for first — and a
second investigation ran in parallel. Between them the E-121 lag hypothesis is
**falsified outright**, and the residual that the body of this report called
"the one thing the model knowingly gets wrong" is closed.

### What it actually is

```
employment target = Σ <workforce max> over the built PRODUCTION and BUILDMODULE
                    macros                                (module_cap.workers)
                  + the STATION macro's own <workforce max>, if it declares one

ration reserve    = 4 h × target, split across races by the LIVE mix,
                    floored per race
```

The game shows this number in the station's Workforce tab. The player read
**"Employment target 1000"** on PTW-627, which has **104** workers living in it
in the save.

Eight station-class macros declare one, and I re-derived every value from the
game files rather than taking them on trust:

| design | target | | design | target |
|---|---:|---|---|---:|
| `station_gen_piratebase_base_01` | 150 | | `station_par_tradestation_base_01` | 400 |
| `station_arg_tradestation_base_01` | 250 | | `station_tel_tradestation_base_01` | 1000 |
| `station_bor_tradestation_base_01` | 250 | | `landmarks_tel_tradestation_01` | 1000 |
| `station_{spl,ter}_tradestation_base_01` | 300 | | | |

**Every one of the 31 single-race non-producers with a saturated ration buy
lands on its design's declared target exactly**, with no free parameter — the
same 31 stations whose reserves I had described as "≈ the live workforce, with
a lag". They only looked like the workforce because a station's population
grows *toward* its target: the reserves were 150 / 250 / 300 / 400 / 1000 while
the live workforces were 150–152 / 250–252 / 300–302 / 400–401 / 1000.

**It is a sum, not a fallback.** MOP-635 (Argon trade-station macro 250,
carrying build modules worth 400) implies exactly **650**; TTV-091 is
3,000 + 150 = **3,150**. Scored save-wide against the ration-implied basis, the
sum has **median ratio 1.0000 for every station design** and 1,118 of 1,150
within 1 % — 1,066 `gen_factory` producers, 50 yards (**wharfs 800**,
shipyards up to 3,150, out of the same sum with no special case), and the seven
trade/pirate designs.

**Habitation `<workforce max>` is capacity, not demand** — it lands in
`module_cap.housing` and must not be summed in. I tested it: housing matches
the implied basis on **0 of 31** non-producers (UGL-363 houses 14,985 and
reserves for 150) and 4 of 1,066 producers.

### Why E-121 was wrong, in its own terms

I raised the lag on the strength of DHI-588 reading one worker per race low and
four Teladi stations sharing a 1,000-worker reserve. Three checks kill it:

1. **DHI-588's workforce has not moved.** I pulled its `<workforces>` block out
   of save_006 (t = 61,949), save_008 (t = 66,773) and save_001 (t = 82,130):
   **179 / 33 / 39 in all three**, 20,000 s apart, with an identical reserve.
   Nothing was catching up with anything. The "−1 per race" is
   `floor(250 × race / 251)` — the target being *below* the live population.
2. **PTW-627's reserve is immovable.** Its workforce went 376 → 546 → 104 in
   the archived saves and reads 160 now; the reserve was 5,400 / 4,560 at every
   one of those points.
3. **The four Teladi stations share a macro**, `landmarks_tel_tradestation_01`,
   which declares 1000. Four stations landing on exactly 1,000 was a declared
   constant, not four independent decays to the same number.

E-121 is FALSIFIED with that evidence; E-123 (job slots, else live workforce)
is SUPERSEDED by E-124, its first half surviving as one term of the sum.
Whether a lag explains **EIJ-609** is untouched and stays open on E-051.

### The extraction gap (E-125)

`gamedata/extract.py` globbed `assets/structures/.*/macros/.*\.xml`, which
requires a directory between `structures` and `macros`. **Station** macros live
one level shallower, at `assets/structures/macros/*.xml`; only the Teladi
landmark (under `structures/landmarks/macros/`) matched, so `modcaps.csv` held
exactly one station row — by accident. Making the middle segment optional adds
**exactly 7 rows and changes nothing else** (247 rows, the same 240 module
rows), and the CSV stays stock base+DLC.

The user data dir's copy overrides the packaged one, so I regenerated
`~/.local/share/x4analyzer/modcaps.csv` too; a full `extract-gamedata` refresh
would do the same.

### The two new stations

**PTW-627** — the employment-target case. Reserve = 4 h at 1,000 =
5,400 medical supplies + 4,560 nostrop oil = 15,360 m³ off a shared
1,800,000 m³ pool (its storage modules are all tagged `container liquid solid`,
so container and solid divide together — nividium 9,392), leaving
`(1,800,000 − 15,360) / 19 = 93,928.42 m³` per traded ware. **21 of 21 exact.**
With the old live-workforce basis every trade ware read uniformly +0.78 % high
and both rations −89 %.

**GMJ-316** — the control. Same Argon design, so the same declared target of
250, but **no habitat module and no workforce**: no reserve at all, and its
food rations and medical supplies take full trading shares of 57,142 and
28,571. Its four `storage_arg_l_tradestation_01` modules are mixed-tag, so the
solid ware nividium reads 5,714 (= 57,142.86/10) and not 120,000 — E-122 again,
on a second design. **21 of 21 exact.** ("Allographyne" in the UI is our ware
id `khaakalloy`; a display-name mismatch, not missing data.)

Both disputed digits resolved before fixturing: the player re-read
**medicalsupplies 5,400** and **claytronics 3,913**, the save's own buy offers
carry `desired="5400"` and `desired="3913"`, and the 19-ware share arithmetic
independently requires 5,400. Nothing inferred was encoded as a reading.

PTW-627's readings come from a **later game state** than its model inputs (live
workforce 160 vs 104 in save_001). That is recorded in the fixture and does not
affect a single number, precisely because the basis is the target and not the
population — which is itself a small confirmation of E-124.

### `desired` on a buy offer is a free validation source

Where a station holds **zero stock** of a ware, its open buy offer's `desired`
(and `amount`) *is* the allocation: PTW-627's claytronics 3,913, medical
supplies 5,400, nostrop oil 4,560 and missile components 93,928 can all be read
straight out of the XML. This is the existing `stock + inbound + open buy`
lower bound at its saturated end, not a new field, but it means the
equal-volume split can be checked on far more stations than the three we have
in-game readings for. Worth a save-wide pass; not done here.

### Scores after Addendum 2

| | body of this report | now |
|---|---|---|
| in-game readings within 1 % | 86 / 90 | **131 / 132** |
| all readings (derived as a lower bound) | 88 / 95 | 133 / 137 |
| `pytest -q` | 254 | **259** |

All 40 DHI-588 readings are now exact (was 37/40 — the three ration misses were
the target), plus 21/21 GMJ-316 and 21/21 PTW-627. **The only remaining in-game
failure in the whole fixture is EIJ-609's hull parts (E-051).**

Against the save's own bound on save 70: 89.1 % → **89.4 %** within 1 %, and the
mixed-module trading stations 95.2 % → 99.5 %.

The producer path is unchanged by the target rule in this save — no producing
station carries a station macro that declares a target (0 of 1,254), so `jobs`
is the whole sum for all of them, and every producer reading is bit-identical
before and after.

### What is still open

- **The per-race split disagrees between two stations** (register contradiction
  9). DHI-588, read in game, needs the **live** race mix: 250 over 179/33/39 →
  178/32/38, all four ration maxima exact, while its habitat mix would give
  162/44/42 and miss every one. DCO-580, save-derived but saturated and stable
  across three snapshots, needs its **habitat** mix: 250 over a live 65/125/63
  wants 62/125/62, which is its 1:2:1 housing exactly, where the live mix gives
  64/123/62. EMY-219 cannot tell them apart. The model implements the live mix,
  on DHI-588's authority; the disagreement is ±3 workers on a 250-worker
  reserve. *Settles it:* a third multi-race station read in game.
- **The supplies model is wrong at GMJ-316** — the player reads a separate
  Supplies inventory of dronecomponents 6 / energycells 300 / smartchips 120,
  against the model's dronecomponents 1 and smartchips 130 and no energy-cell
  row at all. Recorded in the fixture's note; the supply path is a different
  model (`role='supply'`, read off flagged offers) and was not touched here.

---

# Addendum (same day): the GMJ-316 "supplies model is wrong" note is RETRACTED

Written by the coordinating session, not the author of the body above; the body
is left as published per the append-only rule.

The closing note claims *"the supplies model is wrong at GMJ-316 — the player
reads dronecomponents 6 / energycells 300 / smartchips 120 against the model's
dronecomponents 1 and smartchips 130 and no energy-cell row at all."* **That
comparison is invalid and the conclusion is withdrawn. Nothing is wrong.**

The two quantities are not the same thing:

- The in-game **Supplies** tab shows the station's supply position — what it
  **holds plus what it has on order**.
- `station_storage` `role='supply'` is defined in `db/schema.py` as the
  station's *open self-supply demand*: "outstanding drone/munition build
  inputs, **NOT** cargo-storage allocation". It is the **order only**, and it
  reports the order correctly.

On the current snapshot GMJ-316 reads, per ware:

| ware | held (`station_supply`) | on order (`supplies` offer) | `role='supply'` row | in game |
|---|---:|---:|---:|---:|
| smartchips | 0 | 120 | **120** | 120 |
| dronecomponents | **6** | 0 | *none* | 6 |
| energycells | **350** | 0 | *none* | 300 (earlier state) |

Smart chips agree exactly because the station holds none and has the lot on
order. The other two have no open order — a satisfied station posts none, the
same "a full station withdraws its buy offer entirely" rule that governs cargo —
so there is correctly no order row. The held side was never missing: it is
parsed into `station_supply` (kind `ware`), **2,471 rows over 1,033 stations**,
and exposed by `v_station_supply`.

**Nothing downstream consumes `role='supply'`** — no analysis module, no widget;
`v_station_supply` reads the raw held table. So no output in the project is
affected either way.

What is genuinely absent is a *supply allocation* — held + on order — which
nothing currently computes. Both terms are already in the DB. That is a missing
convenience, not a defect, and it carries the same lower-bound caveat as the
cargo proxy: with no open order the sum is only a floor on the target.

Recorded as **E-126**.
