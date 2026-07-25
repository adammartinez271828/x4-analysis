# How X4 resource depletion & respawn works (current understanding)

Reference for the resource-extraction feature work. Assembled 2026-07-21
from the game files (`libraries/regionyields.xml` + its `.xsd`), an
empirical study of 13 saves, and a **live in-game experiment** (Pious Mists XI,
below) that settled the respawn trigger. **Revised 2026-07-24 (backlog
B5)**: a fresh 12-save sweep (11 consecutive transitions, game time
64,377–78,583 s) reversed the relocation/trackability story — depleted
areas *move* (the XSD's "at a random location" was right and our earlier
in-place override was wrong), on a measurable 20 km lattice — and the
respawn-on-contact trigger now rests on population-scale
reservation-join evidence, not just the n=1 experiment. Each claim is
tagged by confidence:

- **[DOC]** — stated in the game's own XSD documentation (authoritative).
- **[OBS]** — directly observed in save data (with the evidence).
- **[EXP]** — established by a controlled in-game experiment.
- **[INF]** — inferred/consistent-with, but not independently verified.

## The mechanic in one paragraph

A resource area holds a pool of one ware up to a fixed capacity. Mining
draws that pool down. **Partial areas do not refill** — there is no gradual
regeneration. When an area is fully **depleted**, its record **moves to a
new position in the sector** (a random multiple-of-20 km offset per axis —
the XSD's "at a random location") and is stored depleted with `starttime` =
now + `respawndelay` **minutes**. Past that time the area **respawns full at
its new position** — the ore is genuinely back and mineable (the
encyclopedia renders it at capacity). The subtlety is purely in the
**stored representation**: the save's `yield` field lazily keeps reading
**0** until a miner **actually mines the area**, at which point the stored
value materializes to reflect the ore that was already there and the miner
extracts from it. So a respawned-but-untouched area **is** full — the field
value just doesn't show it until touched. A sector's "replenishment" is
thus a series of discrete, whole-area respawns whose *stored* values catch
up on a miner's mining contact. No mining → no depletion, so the area never
enters this cycle (or moves) at all.

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
referencing `regionyields.xml`. **[DOC]**

**The XSD's "at a random location" is real — and it happens at
*depletion*, not respawn.** An earlier revision overrode the DOC wording
with an "in place" claim; that was wrong (it had only ever watched the
*materialization*, which is indeed in-place — relative to the record's
already-moved position). The B5 sweep (11 consecutive transitions, all
3,246 areas per save) caught the move itself, 123 times:

- At full depletion the `<area>` record **disappears from its position and
  reappears elsewhere in the sector, depleted, with a future
  `starttime`**: 123 count-preserving position changes vs **6** in-place
  live→depleted transitions; 0 creations, 0 destructions (3,246 areas in
  every save). The moved-in record's `starttime − respawndelay×60` falls
  inside the transition window in 120/121 cases — the move is stamped at
  depletion time. **[OBS]**
- **Displacements are steps on a 20 km lattice, per axis.** All 123
  paired moves have dx, dy, dz that are multiples of 20 km (two show one
  10 km component; a handful differ by float dust of ±0.01 m). Each
  coordinate's *fractional residue survives the move* (166244.016 →
  166244.016 or 146244.016…), and axes frequently step by 0 — which is
  why moves "share" 1–2 coordinates (y most often: per-sector y domains
  are tiny, median 4 values). Move distance: min 20, median 130,
  max 520 km. **[OBS]**
- The target is **not a fixed slot pool**: only 23/123 moved-to positions
  had ever been occupied by any area of that sector earlier in the
  window, and only 6/123 exactly re-landed on a previous position of the
  same (sector, yieldid) group. **[OBS]**

The physical `<fields>` (asteroid-region links) travel with the record;
depletion remains representational, not structural.

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
area keeps its `<fields>` (at its new, post-move position), just drops
`yield` and gains a `starttime`.

**Per-area `<reservations>` — a miner's live claim on the area.** **[OBS]**
An area being worked carries a `<reservations>` block between `<offset>`
and `<fields>`, one self-closing row per claiming ship:

```xml
<reservations>
  <reservation id="[0xa3f4]"/>
</reservations>
```

The `id` is the **reserving mining ship's component id** (verified:
`[0xa3f4]` resolves to `ship_par_m_miner_liquid_01_a_macro`, code
FLF-530, a Paranid liquid miner, in the same save). The newest save holds
517 reservation rows on 251 areas (of 3,246): **508 rows sit on live
areas, 9 on depleted-*eligible* areas** (miners en route to a respawn
about to be triggered), **0 on depleted-pending areas** — miners never
claim an area whose timer hasn't run out. Counts per save in the window:
446–522. (These rows are the review's F7 data source; `save/parser.py`
still does not collect them — a candidate for the extraction backlog.)

### `starttime` = the respawn-*eligibility* time (not the depletion time, not when it fires)

Confirmed by the strongest available test: **every** depleted area whose
`starttime` is in the *future* is empty (42/42, across all wares), and no
depleted area has `starttime=0`. A depletion timestamp could never be in the
future, so `starttime` is the game-time at which this depleted area becomes
**eligible** to respawn (= depletion + `respawndelay`). **[OBS]** But
`starttime` is *not* when the respawn happens — an eligible area sits at zero
until a miner mines it (see the trigger section). An earlier draft read it as
the depletion time; that was wrong, and any "overdue" arithmetic built on
`now − respawndelay` with it is void. "Past-due / eligible" is simply
`starttime < game_time`; "not yet eligible" is `starttime > game_time`.

## Life cycle of an area

1. Area sits at some current `yield` ≤ capacity. **[DOC/OBS]**
2. Miners extract; gatherspeed `factor` scales extraction speed. Current
   `yield` falls. **[DOC]** (gatherspeed's exact effect on rate is [INF].)
3. A partially-mined area **does not refill** — no gradual regeneration.
   **[OBS]** Directly observed: Saturn 2's two mined-down `huge_silicon` areas
   stayed byte-identical while a depleted neighbour materialized full, and the
   partial nividium areas at Avarice / Third Redemption (381, 402) held fixed
   values across 4+ saves. (The XSD's "after it was **depleted**" wording
   independently implies it: a pool only comes back via whole-area respawn on
   *full* depletion, never partially.)
4. On full depletion the area drops its `yield`, is stamped with a
   `starttime` = **now + `respawndelay` minutes** (its respawn-eligibility
   time), and **moves to a new position in the sector** (per-axis
   multiple-of-20 km offset — 123 observed moves vs 6 in-place
   depletions; see the relocation section). It keeps its `<fields>`.
   **[OBS]**
5. Past `starttime` the area is **respawned** — the ore is back, full, and
   mineable (the encyclopedia shows it at capacity). But its *stored* `yield`
   lazily stays at 0 until a miner **actually mines it**, at which point the
   value materializes to full and the miner extracts. **[EXP]** — the Pious
   Mists XI experiment (below) caught exactly this: an area 1 h past `starttime`
   read 0 in the save until a Drill reached it, then materialized to its full
   5,000 cap with the miner pulling 980 out in the same instant. Saturn 2's
   `0 → 998,453` silicon materialization is the same event from the NPC-miner
   side.
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

### Trackability: stable between depletions, broken by each one

The area `id` (`[0x…]`) is a runtime id and remaps on every load, so it is
**not** a stable key. The area's `<offset><position>` is stable **through
mining and through materialization** — but it **changes at ~95% of full
depletions** (123 moves vs 6 in-place across 11 transitions), so
**(position, yieldid) is a valid key only between depletions**. An earlier
revision claimed position-keyed tracking survives the full cycle; it does
not — that revision had only ever watched areas that never fully depleted
in-window (the Asteroid Belt's two permanently-0 areas, idle nividium
spots) or the in-place *materialization* step (Pious Mists XI), never a
depletion itself. **[OBS]**

What the key is good for, precisely:

- **Between depletions** (live areas being mined down, and
  depleted/eligible areas waiting at their post-move spot): (sector,
  yieldid, position) is stable and unique enough — but note **89
  duplicate keys covering 196 areas** exist galaxy-wide (stacked areas,
  including three depleted areas at one position with three starttimes),
  so a tracker must tolerate multisets. **[OBS]**
- **Across a depletion**: the position breaks, but the move preserves
  each coordinate's **fractional residue mod 20 km** (all 123 observed
  moves). For the ~24% of areas with fractional coordinates, (sector,
  yieldid, residue triple) is a plausible cross-depletion identity;
  grid-aligned areas (residue 0, ~76%) are indistinguishable from
  same-group siblings this way. Residue tracking is an [OBS]-derived
  *recipe*, but its uniqueness in practice is **[INF]** — untested at
  population scale.
- **Sector granularity is relocation-proof**: areas move within their
  sector (all 123 moves stayed in-sector), so per-(sector, ware) totals
  and the DB's `v_resource_area` view are unaffected by relocation.
  **[OBS]**

### Scrap participates in the cycle — just rarely

`rawscrap` and `rawkhaakscrap` have the **same** respawndelay values as ore
(20–180 min), **not** -1, and no per-area override exists in the save.
**[OBS]** An earlier revision claimed scrap "was never observed to deplete
or respawn"; the save set refutes both halves:

- The 2026-07-23 review found depleted rawscrap in save_003 and one
  `tiny_rawscrap` area completing a **full cycle** (depleted → re-armed at
  depletion+20 min → live → re-depleted, ×3) inside its window. **[OBS]**
- The current B5 window (11 transitions, 35 scrap groups) adds one
  **in-place scrap materialization** (a depleted scrap area coming back at
  its stable position) and holds 2 currently-depleted scrap areas in the
  newest save; 0 scrap depletions and 0 scrap relocations occurred
  in-window. **[OBS]**

So scrap follows the general lifecycle; its *flatness at scale* is still
real (big scrap fields hold 66–78% of max — collection is too slow to
fully deplete large areas, so the cycle fires only on tiny ones). Combat
debris from destroyed ships is a separate mechanic and was minor in this
playthrough (one +799 event in the HQ combat sector). **[OBS]**

### The stored yield materializes when a miner mines the area — experiment + population evidence

Past its `starttime` the area's ore is back and mineable (the encyclopedia
shows it at capacity), but the **stored `yield` stays 0** until a **miner
mines that specific area** — at which point the value materializes to full
and the miner extracts. It never materializes on a timer, at any attention
level. Two independent lines of evidence:

**1. Population scale: the reservation join** **[OBS]** — over the B5
window's 11 transitions, every stable-position area was classified per
transition and checked for miner reservations at either endpoint save:

| transition class | n | with a reservation snapshot |
|---|---:|---|
| depleted → live (materialization) | 103 | **57** (41 gained one at the later save, 14 at both, 2 at the earlier only) |
| eligible at both ends, stayed 0 | 1,383 | 30 |
| live → depleted in place | 6 | 5 |

An area seen with a reservation materialized in **66%** of cases
(57/87 reservation-carrying area-transitions, depletions excluded) vs
**3.3%** (46/1,399) without —
a ~20× enrichment. The 46 no-reservation materializations are expected:
saves are 20–40 min apart and a reservation exists only *while* a miner
works the area, so touch-and-go contacts fall between snapshots. The
9 reservations sitting on depleted-*eligible* areas in the newest save
are the trigger caught mid-flight: miners already claiming areas whose
stored value is still 0. This replaces the n=1 experiment as the primary
evidence base.

**2. The Pious Mists XI experiment** **[EXP]** — the controlled n=1 that
originally settled the trigger. Honesty note (review F6): the two
load-bearing in-flight observations ("stored 0 for the whole flight", the
encyclopedia's 5,000) were in-game readings not captured in a save, and
the two surviving saves (0.21 h apart) cannot by themselves distinguish
materialize-on-mining-contact from on-approach/targeting — the
reservation join above is what carries the contact framing at scale. The
save-side arithmetic is exact and reproduces today:

- **Baseline** (save_008, 18.55h): the sector's two nividium areas both stored
  **0**. One at (30, 70) km was **eligible** — 0.9 h past its `starttime`; the
  other at (70, −50) km was **not yet eligible** (`starttime` ~0.5 h ahead).
  The encyclopedia showed **5,000** — i.e. only the eligible area's capacity
  (see the encyclopedia note), signalling the ore *was* there to be mined.
- **Action**: sent a player Drill on local automine for nividium; it flew in
  (the encyclopedia's live "mineable now" figure sent it there) and began
  mining. The eligible area's stored value stayed 0 for the whole flight —
  presence alone materialized nothing.
- **Result** (save_009, 18.76h): the **eligible** area (30, 70) now stored a
  live **4,020**, and the Drill's hold held **980** nividium. 4,020 + 980 =
  **5,000** = the medium nividium capacity: it materialized to full the instant
  the miner made contact, and the miner immediately pulled 980 out. The
  **not-yet-eligible** area (70, −50) stayed at 0 (correct — not yet respawned,
  and the miner wasn't on it).

So the stored value materializes on two conditions: the area past its
`starttime` (respawned/available) **and** a miner making mining contact.
Attention/presence is irrelevant except insofar as it lets a miner reach the
area. This is a **lazy, on-mining-contact** materialization, per area.

**This resolves the whole "why do saves show empty fields" backlog.** At
18.52h there were 145 eligible areas storing 0 — not stuck, not rate-limited;
their ore was available, the *stored* value just hadn't been materialized
because no miner had mined them since eligibility. Every earlier hypothesis
in this investigation was wrong and is superseded:

- ~~needs high attention~~ — Saturn 2 materialized with no player near (its NPC
  miners did it); Third Redemption stayed at 0 *with* the player in-sector.
- ~~needs a background timer / low-attention tick~~ — an area sat 1 h+ past
  eligibility storing 0 until a miner touched it.
- ~~rate-limited execution~~ — the "backlog" is areas no miner has mined; it
  clears one area at a time, on contact, not by a throttled queue.

It also explains the two **permanently-0** areas in the heavily-mined Asteroid
Belt (same fixed positions, stored 0 across 5 saves for 16 h while 11
neighbours cycled): the miner AI simply never paths to those two physical
spots, so nothing ever makes contact and their stored value never materializes.
Idle fields (Avarice, Third Redemption nividium) store 0 indefinitely for the
same reason — no miner works them.

### Aside: the encyclopedia is a live rendering of what's mineable NOW

The map/encyclopedia resource figures are not template capacities and not the
raw stored yields — they are a **live rendering of what is actually mineable
in the sector right now**, computed **per area**:

- a partially-mined area contributes its **live `yield`**;
- an **empty area past its respawn timer (eligible)** contributes its **full
  capacity** — because it *will* respawn to that the moment a miner touches it;
- an **empty area not yet eligible** contributes **0**.

**[OBS]** Verified: Third Redemption's ore 116k / ice 155k / methane 259k
matched the summed live yields to the digit (all partial areas), and its
overdue nividium showed 500 (one eligible-empty area at cap). The clincher is
Pious Mists XI — **two** empty medium nividium areas (5,000 cap each), yet the
encyclopedia showed **5,000, not 10,000**: only the **eligible** area was
counted at full; the not-yet-eligible one contributed **0**.

So the figure is exactly **"how much a miner could pull right now"** — live
resource plus eligible areas that respawn on contact — and it is **accurate**,
not a fudge. A genuinely-full area and an eligible-empty area are functionally
identical: both yield the full capacity when mined, which is why a mining ship
flies to either with equal confidence and succeeds (the eligible one respawns
on arrival — exactly what the Pious Mists XI Drill did). The distinction
matters only to **our** save-reading: an eligible-empty area is stored at
`yield`=0, so summing raw yields **understates** what's actually mineable. To
reproduce the game's honest "mineable now" figure, a tool must add each
empty-but-eligible area at its **full capacity**, not count it as 0.

## Rates and "extraction" — what the numbers do and don't mean

- `cap / respawndelay` is **not** a continuous regeneration rate.
  `respawndelay` is a post-depletion cooldown (in minutes), not a rate
  denominator, so any per-hour figure built from it is dimensionally
  meaningless. **[DOC-derived]** (An earlier version of the map gauge
  computed exactly this; it has since been
  reworked; the follow-up measured-rate plan was shelved.)
- The **respawn-throughput ceiling** (whole areas returning every
  respawndelay) is enormous — far above any real mining fleet. In every
  sector studied the binding limit on sustainable extraction was the
  **mining fleet**, not respawn. **[INF from OBS].**
- Because respawn is **on-mining-contact**, a field only *produces while a
  miner is actively on it*. A single continuously-mined area cycles at its
  own ceiling (mine to 0 → wait `respawndelay` → miner contact respawns it
  full → repeat = `cap / respawndelay`). A field's realized output is the sum
  over just the areas miners actually touch — which is why big fields never
  cycle all their areas (miners work a subset) and idle fields produce zero
  regardless of what they "contain." **[EXP-derived].**
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

1. ~~Does a respawn restore full capacity?~~ **RESOLVED — yes.** Saturn 2
   silicon 0 → 998,453 (99.8%); Pious Mists XI nividium respawned to its
   full 5,000 cap on miner contact. Respawn brings a fresh full area.
2. ~~Why do eligible areas not respawn — rate limit? attention?~~ **RESOLVED
   — respawn fires on a miner mining the area** (Pious Mists XI experiment,
   now backed at population scale by the reservation join: 66% of
   reservation-carrying eligible areas materialized between saves vs 3.3%
   of unreserved ones). Not a timer, not attention, not a throttle. The
   "overdue backlog" is just areas no miner has touched since becoming
   eligible.
3. **What exactly does gatherspeed scale** — mining extraction rate,
   respawn amount, or both? Assumed extraction rate only. **[INF]**
4. ~~Does depletion require exactly 0 to arm the timer?~~ **~Yes — arms at
   true empty.** **[INF, strongly supported]** Across all 3,306 areas in the
   save, **zero** nonzero-yield areas carry a *future* (actively counting-down)
   `starttime`; every active eligibility timer is on an **empty** area. The 204
   nonzero areas with a *past* `starttime` are stale leftovers (armed at a
   prior full depletion, re-materialized by mining, timer uncleared). A
   nonzero threshold would leave areas mid-countdown *with* resource — none
   exist. So the timer arms only when the area hits 0.
5. ~~Does scrap respawn when depleted?~~ **RESOLVED — yes.** The save set
   holds depleted rawscrap, one `tiny_rawscrap` full cycle (depleted →
   re-armed → live → re-depleted ×3, 2026-07-23 review), and one in-place
   scrap materialization in the B5 window. Only *large* scrap fields never
   deplete (collection too slow), so the cycle fires rarely.
6. **What decides which areas a miner AI touches?** This governs which areas
   ever respawn. **Not gatherspeed** **[OBS]**: the Asteroid Belt's two
   permanently-0 areas are `medium/fast` and `high/average` — *better* than
   the two `veryhigh/slow` areas that cycle fine there. Both dead areas sit at
   the sector's spatial **periphery** (km(−250, −50) far −x edge; (−130, 230)
   isolated corner), so the driver looks like **position / pathing** (proximity
   to stations and the miners' working cluster), not field quality. The
   per-area `<reservations>` rows are the direct observable of the
   selection's *outcome* (which areas miners claim); the selection logic
   itself is engine-side and unquantified.
7. **Do depleted areas re-roll if left unclaimed?** Four depleted small
   nividium records **moved again** in-window, arriving with a freshly
   re-armed `starttime` (arithmetic reads as a new depletion inside the
   transition). Two readings fit: an invisible full cycle between saves
   (materialize → strip a 500-cap area → re-deplete — plausible for
   nividium's tiny caps), or an eligible-unclaimed area re-rolling its
   position and timer. **[UNRESOLVED — hypothesis only.]** All four are
   nividium `verylow`; no other ware showed it.

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
to the respawn-eligibility time (depletion + 120 min). The `<offset>` and
`<fields>` stay — depletion is representational, not structural. After that
time it is *eligible* but stays empty until a **miner mines it**, at which
point it respawns full (see the respawn-trigger section).

Gases (helium/hydrogen/methane) have **no `<fields>`** — just position and
yield — because there are no rocks; silicon's fields point at `env_ast_crystal_*`
(crystal asteroids), ice at `env_ast_ice_*`, nividium at `env_ast_niv_*`.
One physical `region` id is shared across the ore/silicon/ice/nividium areas
that coexist in the same field.

## Appendix B — one-pager

**The rule:** resources deplete under mining and never refill gradually. A
fully depleted area **moves to a new spot in its sector** (per-axis random
multiple of 20 km) and **respawns whole and full there** `respawndelay`
minutes later — the ore is genuinely back and mineable then (the
encyclopedia shows it). But the save's *stored* `yield` lazily reads **0**
until a miner actually mines the area, which materializes the value. So a
respawned area **is** full; the field value just doesn't show it until
touched.

**Life cycle of one area**

```
full ──mining──► partial ──mining──► EMPTY: record MOVES ──wait respawndelay──► RESPAWNED at new spot
                    │                (new pos, starttime=now+delay)   (ore back & full; stored yield reads 0)
                    └── never refills on its own ──────────────────────────────►      │ miner mines it
                                                                                       ▼
                                                                            stored value materializes to
                                                                            FULL; miner extracts at once
```

The respawn (availability) happens on the `respawndelay` timer; only the
**stored `yield`** waits for a miner's contact to catch up. In the save a
respawned-but-untouched area has no `yield` attribute and a past `starttime`;
it sits at its post-move `<offset><position>` with its `<fields>`, and
materialization happens **in place at that new position**.

**A "field" is a bag of independent areas.** A sector's ore is ~12 separate
asteroid areas of mixed size/level/speed, each with its own pool, position,
and respawn state. Everything is per-area, and respawn is evaluated per-area
on contact — so a field only produces from the areas miners actually touch.

**The numbers** (`regionyields.xml`, per area; ore/silicon/ice share these):

| level | capacity | respawndelay |
|---|---:|---:|
| verylow | 5,000 | 20 min |
| low | 50,000 | 40 min |
| medium | 200,000 | 60 min |
| high | 1,000,000 | 120 min |
| veryhigh | 2,000,000 | 180 min |

(Nividium is far smaller: 500 → 50,000 cap, 90 → 480 min delay.) Gatherspeed
scales *mining* rate: veryslow ×0.2 · slow ×0.5 · average ×1.0 · fast ×2.0 ·
veryfast ×5.0. `respawndelay = -1` = never respawns.

**What follows from the rule**

- **No miner → the stored `yield` stays 0** (but the ore *did* respawn on the
  timer and is mineable — the encyclopedia shows it). Two distinct cases:
  areas that **never deplete** (unmined sectors, slowly-collected scrap) hold
  their stored value and never enter the cycle; areas **mined to 0** respawn on
  schedule but their stored value only **materializes when a miner mines them**.
  The Asteroid Belt has two ore areas *storing* 0 for 16 h+ while 11 neighbours
  cycle — the miner AI never paths to those two spots, so their value never
  materializes, though a miner sent there would find full ore.
- **Respawn works with no player present** — NPC miners trigger it (Saturn 2
  silicon respawned while the player only remote-scouted).
- **Confirmed by experiment**: an area 1 h past `starttime`, empty, respawned
  to its full 5,000 the instant a player Drill mined it — which took 980 in the
  same moment (4,020 left). Presence alone did nothing until mining contact.
- **The encyclopedia is a live rendering of what's *mineable now*** — live
  yields of partial areas + empty-but-eligible areas at full capacity (they
  respawn on contact); not-yet-eligible empty areas count 0. Pious Mists XI's
  two empty nividium areas showed **5,000, not 10,000** — only the eligible
  one counted. It's accurate: a full area and an eligible-empty area both mine
  out full. The implication runs the *other* way — summing raw save `yield`s
  **understates** mineability, so a "mineable now" tool must add
  empty-but-eligible areas at full capacity.
- **Position-keyed tracking works only between depletions** — the `<area>`
  `id` remaps on load, and the `<offset><position>` breaks at ~95% of full
  depletions (the record moves 20–520 km, a 20 km-lattice step per axis).
  Track live/waiting areas by (sector, yieldid, position), tolerate the
  ~90 stacked duplicate keys, and treat every depletion as an identity
  break (coordinate residues mod 20 km survive moves and *may* re-link
  fractional-coordinate areas — untested at scale). The per-(sector, ware)
  total is the relocation-proof granularity.

**Consequences for measuring "extraction"**

- `cap ÷ respawndelay` is **not** a live rate; it's the ceiling a *single
  continuously-mined* area could sustain (mine→wait→contact-respawn→repeat).
- A field's real output = sum over only the areas miners contact; big fields
  never cycle all areas, idle fields produce nothing regardless of contents.
- The binding limit on sustainable extraction is the **mining fleet** (which
  areas it touches and how fast), never respawn throughput.

**Mostly settled:** the timer arms at true empty (no nonzero area ever shows an
active countdown); scrap follows the same cycle (depleted rawscrap, one full
tiny-area cycle, one in-place materialization all observed — only large
fields never deplete); and which areas respawn is gated by **which areas a
miner paths to** — driven by position, *not* gatherspeed (the Asteroid
Belt's two dead areas are `fast`/`average`, better than the `slow` ones
that cycle), with per-area `<reservations>` as the direct observable of
miner claims. **Still open:** whether gatherspeed touches respawn *amount*,
the exact miner-AI area-selection logic, and whether unclaimed depleted
nividium areas re-roll (open question 7).

## One-line summary

Resources deplete under mining and never refill gradually; a fully depleted
area **moves to a new in-sector position** (20 km-lattice step per axis) and
**respawns whole and full there once past its `respawndelay`**, but the
save's stored `yield` **reads 0 until a miner mines that area and
materializes it** (population evidence: reserved areas materialize at ~20×
the rate of unreserved ones) — so availability is timer-driven, position
resets at depletion, and the stored value is contact-driven and per-area: a
save shows 0 for any respawned area no miner has touched, and a sector only
*produces* from the areas miners work.
