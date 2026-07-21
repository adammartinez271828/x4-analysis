# How X4 resource depletion & respawn works (current understanding)

Reference for the resource-extraction feature work. Assembled 2026-07-21
from the game files (`libraries/regionyields.xml` + its `.xsd`) and an
empirical study of 13 saves from one playthrough (game-hours 0.16 → 18.39).
Each claim below is tagged by confidence:

- **[DOC]** — stated in the game's own XSD documentation (authoritative).
- **[OBS]** — directly observed in save data (with the evidence).
- **[INF]** — inferred/consistent-with, but not independently verified.

## The mechanic in one paragraph

A resource area holds a pool of one ware up to a fixed capacity. Mining
draws that pool down. **Partial areas do not refill** — there is no gradual
regeneration. Only when an area is fully **depleted** does a timer start;
`respawndelay` **minutes** later the area **respawns, full, at a random
location within the same sector**. So the entire "replenishment" of a
sector is a series of discrete, whole-area respawn events, each triggered
by a prior depletion. No depletion → no respawn.

## Source data

### Game files — `libraries/regionyields.xml`

Defines the templates every resource area references:

- **Yield levels** `verylow · low · medium · high · veryhigh`, each giving a
  per-ware `yield` (the area's capacity) and a `respawndelay`. For ore:
  5,000 / 50,000 / 200,000 / 1,000,000 / 2,000,000 with respawndelay
  20 / 40 / 60 / 120 / 180. **[DOC]**
- **Gatherspeeds** `veryslow · slow · average · fast · veryfast` with
  `factor` 0.2 / 0.5 / 1.0 / 2.0 / 5.0 and a `rating` 3 / 6 / 9 / 12 / 15.
  **[DOC]**

The XSD documents the two key attributes verbatim:

- `yield`: *"The total amount of yield in this area"* — i.e. the capacity. **[DOC]**
- `respawndelay` (`xs:float`): *"The time after it was depleted **(in
  minutes)** before this resource area is respawned **at a random
  location**. Defaults to 0. Set to -1 to prevent respawning."* **[DOC]**

`region_definitions.xml` carries a 9.00 note: resource areas are now defined
per-**sector** in `mapdefaults.xml` under `<properties><resourceareas>`,
referencing `regionyields.xml`. So an area's respawn "random location" is
scoped to its own sector's field, not the galaxy. **[DOC]**

### Save files — the `<area>` element

Each live area appears as:

```
<area id="[0x7685]" yieldid="sphere_large_ore_high_slow" yield="53658" starttime="0">
```

- `yieldid` = `sphere_<size>_<ware>_<level>_<gatherspeed>`, e.g.
  `sphere_large_ore_high_slow` → boundary `large`, ware `ore`, level `high`,
  gatherspeed `slow`. The size/level/speed are optional trailing tokens. **[OBS]**
- `yield` = the area's **current** pool (depletes with mining). **[OBS]**
- `id` is a **runtime** id that remaps on every load — not a stable
  identity. **[OBS]**
- Save areas carry **no `respawndelay` attribute** (0 occurrences in the
  save); the delay is resolved purely from the `yieldid`'s level via
  `regionyields.xml`. **[OBS]**

## Life cycle of an area

1. Area sits at some current `yield` ≤ capacity. **[DOC/OBS]**
2. Miners extract; gatherspeed `factor` scales extraction speed. Current
   `yield` falls. **[DOC]** (gatherspeed's exact effect on rate is [INF].)
3. A partially-mined area **does not refill**. **[INF — strongly implied by
   XSD wording ("after it was depleted") and by the smooth multi-hour
   declines with no partial recovery we observed].**
4. On full depletion, a `respawndelay`-minute cooldown begins. **[DOC]**
5. After the cooldown, a fresh **full** area respawns at a random spot in
   the sector. **[DOC]** (That the respawn restores *full* capacity is
   **[INF]** — see open questions.)
6. `respawndelay = -1` disables respawn entirely. **[DOC]**

## What this predicts, and what we observed

### Unmined sectors are frozen — confirmed

No mining → nothing depletes → no respawn timer → the field never changes.
**[OBS]** The Unknown System (no miners, one construction site) held its ore
pools byte-identical across 11 saves spanning 4.6 game-hours, sitting at
32–70% of capacity the whole time (so not "frozen because full").

### Hard-mined ore fields show discrete respawn jumps — observed

Sectors mined hard enough to deplete small areas show a smooth
partial-depletion decline punctuated by discrete up-jumps (respawns).
**[OBS]** Clean in-window examples:

- Emperor's Pride VI ore: steady decline with a +15,151 jump (17.21→17.80h).
- Matrix #598 ore: decline with a +8,649 jump.
- Saturn 2 silicon: +969,919 in 0.22h, verified to land in the **same 6
  areas** (identical count and class mix) — a genuine refill/respawn, not
  newly-scanned areas.
- cluster_29 ore: 185,904 → 1,164,322 in 0.8h.

The respawn cadence — sparse, large jumps hours apart — is itself evidence
that `respawndelay` is **minutes, not seconds**: second-scale delays would
make fields refill almost continuously, which is not what we see. **[OBS]**

### Aggregate-per-sector is the only trackable unit — established

Because areas both remap ids **and** respawn at new locations, individual
fields cannot be followed across saves. Only the **(sector, ware) total**
is stable enough to track. **[INF from DOC + OBS.]**

### Scrap looks frozen for the same reason as unmined sectors — reframed

`rawscrap` and `rawkhaakscrap` have the **same** respawndelay values as ore
(20–180 min), **not** -1, and no per-area override exists in the save. **[OBS]**
Across all 13 saves, scrap was never observed to respawn — but scrap was
also **never observed to deplete**: the big scrap fields never fell below
66–78% of their own max, and even the most-drawn-down (Silent Witness XII
khaak scrap at ~4% of cap) sat flat without hitting zero. **[OBS]**

So scrap's flatness is consistent with the general rule (slow collection →
no full depletion → no respawn), but whether scrap actually respawns when
depleted is **[UNVERIFIED]** — we have zero observations of the triggering
condition. Its other source, combat debris from destroyed ships, is a
separate mechanic and was minor in this playthrough (one +799 event in the
HQ combat sector). **[OBS]**

## Rates and "extraction" — what the numbers do and don't mean

- `cap / respawndelay` is **not** a continuous regeneration rate.
  `respawndelay` is a post-depletion cooldown (in minutes), not a rate
  denominator, so any per-hour figure built from it is dimensionally
  meaningless. **[DOC-derived]** (An earlier version of the map gauge
  computed exactly this; it is being reworked — see
  [resource-extraction-plan.md](resource-extraction-plan.md).)
- The **respawn-throughput ceiling** (whole areas returning every
  respawndelay) is enormous — far above any real mining fleet. In every
  sector studied the binding limit on sustainable extraction was the
  **mining fleet**, not respawn. **[INF from OBS].**
- Realized replenishment is only visible as **respawn events**, and
  concurrent mining masks much of it, so any measured rate from save
  history is a **lower bound** on true sustainable extraction — except in
  sectors stable or rising under heavy load, where it approaches the true
  maximum. **[OBS/INF].**

Measured fields (mining ≈ fleet-limited, replenish ≈ observed respawns):

| field · ware | fill | net decline | notes |
|---|---|---|---|
| Emperor's Pride VI ore | 32% | −36k/h | 31 miners; +15k respawn blip; est. replenish ~45k/h |
| Matrix #451 ore | 55% | −16.7k/h | 5 miners; replenish ~0–3k/h |
| Matrix #9 ore | 45% | −42.8k/h | 60 areas, 25 miners; replenish ~37k/h |
| Matrix #598 ore | 42% | −48.8k/h | 60 areas, 24 miners; +8.6k blip; replenish ~28k/h |
| Asteroid Belt silicon | 66% | −71k/h | 60 miners; declines faster than any static ceiling |
| Saturn 2 silicon | 29% | **+145k/h** | 71 miners; ≥233k/h gross respawn (rising under load) |

(Replenish estimates use an imported ~3,200 ore/h-per-M-miner rate,
calibrated at Emperor's Pride and cross-checked against the respawn blips;
they are estimates, not direct measurements.)

## Open questions (unverified)

1. **Does a respawn restore full capacity?** Saturn 2's huge silicon areas
   gained ~485k against a 2M cap in one event — consistent with either a
   partial respawn or an area that wasn't fully depleted. Unresolved.
2. **What exactly does gatherspeed scale** — mining extraction rate,
   respawn amount, or both? Assumed extraction rate only. **[INF]**
3. **Does depletion require exactly 0**, or drop below some threshold, to
   arm the respawn timer? **[unknown]**
4. **Does scrap respawn at all when depleted?** Never observed depleted.
   Would be settled by deliberately mining one scrap field to zero and
   analyzing two saves across the respawndelay window.
5. **Quantitative respawn cadence vs `respawndelay`** — the minutes reading
   is confirmed qualitatively (hours-apart jumps), but we have not matched
   a specific event to a specific area's delay.

## Appendix — a complete ore-field definition, end to end

The full definition of a sector's ore is spread across three files that
reference each other. Worked example: **Cluster_01_Sector001** (the ore
part of its `<resourceareas>`).

### Step 1 — `mapdefaults.xml` places the areas in the sector

Under the sector macro's `<properties><resourceareas>`, each `<resourcearea>`
row says *how many* areas of a given template to spawn (`amount`) and *which*
template (`ref`):

```xml
<resourceareas>
  ...
  <resourcearea amount="4" ref="sphere_large_ore_high_slow" />
  <resourcearea amount="4" ref="sphere_small_ore_medium_average" />
  <resourcearea amount="4" ref="sphere_tiny_ore_low_fast" />
  ...
</resourceareas>
```

So this sector gets **12 ore areas**: four of each of three kinds.

### Step 2 — decode each `ref`

`ref = sphere_<boundary>_<ware>_<level>_<gatherspeed>`:

| ref | boundary | ware | level | gatherspeed |
|---|---|---|---|---|
| `sphere_large_ore_high_slow` | large | ore | high | slow |
| `sphere_small_ore_medium_average` | small | ore | medium | average |
| `sphere_tiny_ore_low_fast` | tiny | ore | low | fast |

### Step 3 — resolve the templates from `regionyields.xml`

Each token is a lookup into `regionyields.xml`:

- **boundary** → physical size (radius):
  `tiny r=20 km · small r=30 km · medium r=50 km · large r=100 km · huge r=200 km`
- **level** → per-ware capacity + respawndelay (from the `<yield>` blocks):
  `low` ore = 50,000 cap / 40 min · `medium` = 200,000 / 60 min ·
  `high` = 1,000,000 / 120 min
- **gatherspeed** → extraction-speed factor:
  `fast` = ×2.0 · `average` = ×1.0 · `slow` = ×0.5

### Step 4 — the resulting field

Putting it together, Cluster_01_Sector001's ore field is:

| kind | count | radius | capacity each | respawndelay | gather ×  | subtotal cap |
|---|---:|---|---:|---:|---:|---:|
| large / high / slow | 4 | 100 km | 1,000,000 | 120 min | 0.5 | 4,000,000 |
| small / medium / average | 4 | 30 km | 200,000 | 60 min | 1.0 | 800,000 |
| tiny / low / fast | 4 | 20 km | 50,000 | 40 min | 2.0 | 200,000 |
| **total** | **12** | | | | | **5,000,000** |

So "the ore in this sector" is 12 discrete asteroid areas totalling 5 M ore
at full capacity — a few big slow-to-respawn fields plus many small fast ones.

### Step 5 — how it looks live in a save

At runtime each of those 12 areas is instantiated as an `<area>` with a
current `yield` (its remaining pool) and a remapped runtime id, e.g.:

```xml
<area id="[0x7685]" yieldid="sphere_large_ore_high_slow" yield="53658" starttime="0"/>
```

Here a `large/high/slow` area (1 M capacity) is nearly mined out at 53,658 —
one of the four; when it hits zero it will respawn full, 120 minutes later,
at a random spot inside the same sector. The save stores **only** the current
`yield` and the `yieldid`; capacity, respawndelay, radius and gather factor
are all resolved back through `regionyields.xml`.

## One-line summary

Resources deplete continuously under mining but only **respawn as whole
fresh areas after full depletion**, `respawndelay` **minutes** later, at a
random spot in the same sector — so replenishment is bursty and
depletion-gated, untouched fields never change, and the only reliably
trackable quantity is the per-sector-ware total across saves.
