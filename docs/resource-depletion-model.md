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

### Save files — the `<resourceareas>` block

At runtime the areas live in a flat `<resourceareas>` block **directly under
the sector component** (not a separate region object). **[OBS]** A live solid
area is richer than the game-file template — it carries a position and links
to the physical asteroids:

```xml
<component class="sector" macro="cluster_500_sector002_macro">
  …
  <resourceareas>
    <area id="[0x301a0]" yieldid="sphere_medium_nividium_verylow_veryfast"
          yield="381" starttime="0">
      <offset><position x="-30000" y="-10000" z="-130000"/></offset>
      <fields>
        <field region="[0x2ebaa]" macro="env_ast_niv_l_01_macro" weight="3076"/>
        <field region="[0x2ebb2]" macro="env_ast_niv_l_01_macro" weight="279485"/>
        …
      </fields>
    </area>
    …
  </resourceareas>
```

Attributes / children (all **[OBS]**):

- `yieldid` = `sphere_<boundary>_<ware>_<level>_<gatherspeed>`, e.g.
  `sphere_large_ore_high_slow` → boundary `large`, ware `ore`, level `high`,
  gatherspeed `slow`. Parse by structure, not a regex over the middle: the
  **boundary** token `medium` collides with the **level** token `medium`.
- `yield` = the area's **current** pool (depletes with mining). **Absent
  entirely when the area is depleted** — not `yield="0"`.
- `starttime` = `0` while the area holds resource; once depleted it becomes
  the **scheduled respawn time** (game-time seconds). See "starttime" below.
- `<offset><position>` = the area's real 3D location in the sector (metres).
  Present on **every** area, including depleted ones.
- `id` is a **runtime** id that remaps on every load — not a stable identity.
- No `respawndelay` attribute exists on save areas; the delay is resolved
  from the `yieldid`'s level via `regionyields.xml`.

**Gases vs solids differ structurally.** **[OBS]**

- **Gases** (helium, hydrogen, methane): position + yield only, **no
  `<fields>`** — they are gas clouds, no rocks to reference.
- **Solids** (ore, silicon, ice, nividium): a `<fields>` list linking the
  abstract deposit to the physical asteroid environment macros that render
  and get mined — `env_ast_ore_*`, `env_ast_crystal_*` (silicon is mined
  from *crystal* asteroids), `env_ast_ice_*`, `env_ast_niv_*`. Each `<field>`
  carries a `region="[0x…]"` (runtime id of the physical asteroid-field
  region) and a `weight`.

Two structural facts: **areas share physical regions** (one `region` id such
as `[0x2ebb2]` appears in the `<fields>` of ore, silicon, ice *and* nividium
areas — the `<area>` layer is accounting, the `region`/`macro` layer is the
rocks), and **depletion is representational, not structural** — a mined-out
area keeps its `<offset>` and `<fields>`, just drops `yield` and gains a
`starttime`.

### `starttime` = the scheduled respawn time (not the depletion time)

Confirmed by the strongest available test: **every** depleted area whose
`starttime` is in the *future* is empty (42/42, across all wares), and no
depleted area has `starttime=0`. A depletion timestamp could never be in the
future, so `starttime` is the **game-time at which this depleted area is
scheduled to respawn**. **[OBS]** (An earlier draft read it as the depletion
time; that was wrong, and any "overdue" arithmetic built on `now −
respawndelay` with it is void. The correct "past-due" test is simply
`starttime < game_time`.)

## Life cycle of an area

1. Area sits at some current `yield` ≤ capacity. **[DOC/OBS]**
2. Miners extract; gatherspeed `factor` scales extraction speed. Current
   `yield` falls. **[DOC]** (gatherspeed's exact effect on rate is [INF].)
3. A partially-mined area **does not refill**. **[INF — strongly implied by
   XSD wording ("after it was depleted") and by the smooth multi-hour
   declines with no partial recovery we observed].**
4. On full depletion the area drops its `yield` and is stamped with a
   `starttime` = **now + `respawndelay` minutes**, the scheduled respawn
   time. It keeps its position and `<fields>`. **[OBS]**
5. When that scheduled time arrives *and the region is being processed*, a
   fresh **full** area respawns at a random spot in the sector. **[DOC +
   OBS]** — directly observed: a Saturn 2 `large_silicon_high_average` area
   went from **0 → 998,453** (99.8% of its 1 M cap) in one interval, while
   unmined areas nearby stayed byte-identical and another depleted area
   (not yet due) stayed at 0. The "*being processed*" qualifier is the open
   part — see the attention/backlog section.
6. `respawndelay = -1` disables respawn entirely. **[DOC]**

## What this predicts, and what we observed

### Unmined sectors are frozen — confirmed

No mining → nothing depletes → no respawn is ever scheduled → the field never
changes. **[OBS]** The Unknown System (no miners, one construction site) held
its ore pools byte-identical across 11 saves spanning 4.6 game-hours, sitting
at 32–70% of capacity the whole time (so not "frozen because full"). This is
about *mining*, not attention (below): with nothing depleting the areas,
there is simply nothing to respawn.

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

### Respawn happens at low attention, but execution looks rate-limited

X4 simulates every sector continuously at **low attention**; **high
attention** (full detail) applies only within ~100 km of the player.
Depletion and respawn *both* happen at low attention: NPC fleets deplete
distant sectors, and Saturn 2's silicon respawned while the player was
**never** present there (only remote scouts). **[OBS, user-confirmed]** So
"only changes while the player is near" is wrong — proximity is not required.

But respawns do **not** all fire on schedule. At game-time 18.52h the save
holds 187 scheduled respawns: **42 pending** (respawn time in the future,
all empty) and **145 overdue** (scheduled time already passed, still empty).
Crucially, **135 of the 145 overdue are in actively-mined sectors** — the
backlog is not "no activity." Saturn 2 fired its silicon respawn yet still
carries 4 overdue (hydrogen); Matrix #598 carries 14 overdue ore, Matrix #9
seven, Emperor's Pride VI two. Sectors clear *some* due respawns while others
in the same sector stay overdue. **[OBS]**

That is the signature of **rate-limited / periodic execution**: each respawn
is *scheduled* cleanly (`starttime` = depletion + `respawndelay`, and the
pending times are arbitrarily spaced — no throttle in the scheduling), but
the engine *executes* due respawns at a limited rate, leaving a persistent
backlog that is largest where depletion is fastest. **[INF — strong].** No
explicit throttle exists in the game files (`regionyields.xsd` documents only
`respawndelay`); the limiting is engine-side. The unknown is the execution
budget (per region? per tick? universe-wide?) and firing order.

This **supersedes** two earlier guesses in this investigation, both now
falsified: that respawn needs high attention (Saturn 2 respawned with no
player near), and that it needs active mining (active sectors carry the bulk
of the backlog).

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

1. ~~Does a respawn restore full capacity?~~ **RESOLVED — yes.** A depleted
   Saturn 2 `large_silicon_high_average` area respawned at 998,453 / 1,000,000
   (99.8%) in one interval. Respawn brings a fresh, essentially full area;
   partially-mined areas nearby did not change. (The earlier "+485k per huge
   area" reading was a misattribution — the jump was one *large* area
   respawning full, not the *huge* areas partially refilling.)
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
6. **What is the respawn-execution budget?** Execution is rate-limited (145
   overdue scheduled respawns, 135 of them in actively-mined sectors), but
   whether the limit is per-region, per-tick, or universe-wide — and the
   firing order — is unknown.
7. **Do overdue respawns ever fire without the player, or only when he
   visits?** Avarice V stayed empty ~8 min after the player entered (far
   too short to conclude). The idle-field temporal test (leave a mined-out
   field, save hours later) would settle whether overdue respawns clear on
   their own.

## Appendix A — a complete ore-field definition, end to end

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

At runtime the sector's areas live in a flat `<resourceareas>` block under the
sector component. Each is an `<area>` with a remapped runtime id, a current
`yield`, a 3D `<offset><position>`, and — for solids — a `<fields>` list
linking to the physical asteroid macros that render and get mined:

```xml
<area id="[0x3018d]" yieldid="sphere_large_ore_high_slow" yield="53658" starttime="0">
  <offset><position x="-50000" y="-10000" z="-270000"/></offset>
  <fields>
    <field region="[0x2ebb2]" macro="env_ast_ore_xl_01_macro" weight="1190732"/>
    …
  </fields>
</area>
```

Here a `large/high/slow` area (1 M capacity) is nearly mined out at 53,658.
The save stores per area only the current `yield`, the `yieldid`, the
position, and the asteroid-field links; capacity, respawndelay, radius and
gather factor are all resolved back through `regionyields.xml`.

When it hits zero the `yield` attribute **disappears** and `starttime` is set
to the scheduled respawn time (depletion + 120 min). The `<offset>` and
`<fields>` stay — depletion is representational, not structural. It then
respawns full at a random spot in the sector, subject to the engine's
rate-limited respawn execution (see the low-attention/rate-limit section).

Gases (helium/hydrogen/methane) have **no `<fields>`** — just position and
yield — because there are no rocks; silicon's fields point at `env_ast_crystal_*`
(crystal asteroids), ice at `env_ast_ice_*`, nividium at `env_ast_niv_*`.
One physical `region` id is shared across the ore/silicon/ice/nividium areas
that coexist in the same field.

## Appendix B — one-pager

**The rule:** resources deplete continuously under mining but never refill
gradually. An area only comes back by **respawning whole and full** — and
only *after* it has been mined to exactly **0**.

**Life cycle of one area**

```
full ──mining──► partial ──mining──► EMPTY(0) ──schedule respawn at now+delay──► respawns FULL
                    │                            (delay = respawndelay minutes)   (random spot,
                    └── sits here forever if mining stops ─────────────────────    same sector,
                                                       execution is rate-limited)  full capacity)
```

On depletion the area drops its `yield` and stores `starttime` = the scheduled
respawn time; execution of due respawns is **rate-limited** by the engine, so
a backlog builds (145 overdue vs 42 pending in the studied save).

**A "field" is a bag of independent areas.** A sector's ore is ~12
separate asteroid areas of mixed size/level/speed, each with its own pool,
position, depletion, and respawn schedule. Nothing is per-sector; everything
is per-area. In the save each is an `<area>` with `yieldid`, `yield` (absent
when empty), `starttime`, an `<offset><position>`, and — for solids only — a
`<fields>` list linking to the physical asteroid macros (gases have none).

**The numbers** (`regionyields.xml`, per area):

| level | capacity (ore) | respawndelay |
|---|---:|---:|
| verylow | 5,000 | 20 min |
| low | 50,000 | 40 min |
| medium | 200,000 | 60 min |
| high | 1,000,000 | 120 min |
| veryhigh | 2,000,000 | 180 min |

Gatherspeed scales *mining* rate: veryslow ×0.2 · slow ×0.5 · average ×1.0
· fast ×2.0 · veryfast ×5.0. `respawndelay = -1` means never respawns.

**What follows from the rule**

- **Unmined sector → frozen forever.** No depletion, no respawn trigger.
- **Slowly-mined resource (e.g. scrap) → looks frozen too.** Areas never
  hit 0, so they never respawn. (Not because scrap *can't* — we've just
  never seen one depleted.)
- **Hard-mined field → smooth decline + discrete full-area pop-ups.** The
  decline is partial areas draining; the jumps are depleted areas
  respawning full.
- **Respawn = fresh full area at a random in-sector location.** Observed:
  0 → 998,453 / 1,000,000 in one interval.
- **Respawn works at low attention** (no player needed): a field respawned
  while the player only remote-scouted the sector. But **execution is
  rate-limited** — due respawns pile up even in busy sectors (Saturn 2 fired
  its silicon but kept 4 other respawns overdue).
- **Only the per-(sector, ware) total is trackable across saves** — area
  ids remap *and* areas relocate on respawn, so individual fields can't be
  followed.

**Consequences for measuring "extraction"**

- `cap ÷ respawndelay` is **not** a rate (respawndelay is a post-depletion
  cooldown in minutes, not a rate denominator).
- Real replenishment is only visible as respawn events; concurrent mining
  hides most of it, so any save-history measurement is a **lower bound**.
- In practice the ceiling on sustainable extraction is the **mining
  fleet**, not respawn throughput.

**Still unknown:** whether scrap respawns (never seen one depleted); exactly
what "depleted" threshold arms the timer; whether gatherspeed touches
respawn as well as mining.

## One-line summary

Resources deplete continuously under mining but only **respawn as whole
fresh areas after full depletion**, `respawndelay` **minutes** later, at a
random spot in the same sector — so replenishment is bursty and
depletion-gated, untouched fields never change, and the only reliably
trackable quantity is the per-sector-ware total across saves.
