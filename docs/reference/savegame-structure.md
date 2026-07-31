# X4: Foundations savegame XML structure (game v9.0)

A top-down map of the save-file tree as far as it is currently understood.
Assembled 2026-07-23 from direct inspection of a real v9.0 save plus the
format knowledge accumulated in this repo; every element and attribute shown
below was verified to occur in the reference save, and all XML snippets are
verbatim from it, except that they are re-indented for readability (the save
itself is unindented) and elisions are marked `<!-- … -->`. Semantics that go
beyond
what the XML itself shows (units, counters, id behavior) are reverse-engineered;
anything not validated is flagged **(unverified)**.

**Reference save:** `save_002.xml.gz`, 2026-07-22, 78 MB gzipped,
game `version="900" build="611726"`, guid `8E0C8E37-2192-49FD-BF4B-F535782A1C55`,
game time 72,813 s (≈ 20.2 h), 11.3 M XML elements.

**Caveats up front**

- The save is `modified="1"` and the game runs ~60 mods plus all official
  DLCs. Element *structure* has matched vanilla wherever cross-checked, but
  mods add wares/macros/factions and can skew counts and values. Any
  vanilla-only claim here should be re-verified against an unmodded save.
- This documents **save files only**. Game data files (`.cat`/`.dat` archives,
  `wares.xml`, macro XMLs, …) are out of scope.
- Regions the analysis has needed are documented in full; the rest of the tree
  is stubbed with a one-line description and an explicit *(not yet documented)*
  marker so this file can be extended in place.

## File container and global conventions

A save is a single gzip-compressed XML document (`.xml.gz`; uncompressed
`.xml` also loads). The XML is machine-written, one element per line, no
indentation. Root element: `<savegame>`.

Conventions that hold throughout the tree:

- **Runtime ids** look like `[0x2f96c]` (hex, bracketed). They are allocation
  order, unique within one session — and **remap on every load**. Never use
  them as stable identity across saves; within one save they are the join key
  for every cross-reference (`buyer=`, `component=`, `attacker=`,
  `<connected connection=…>`, …).
- **Codes** (`code="WYH-699"`) are the in-game display codes. They are
  recycled after an object dies (measured: 163 recycles in 21 game-minutes of
  NPC churn) and live cross-faction collisions exist in long saves — not a
  GUID either.
- **Names** are player/game-assigned display strings and change on rename.
  Many name-ish attributes hold **localization references** of the form
  `{page,id}` (e.g. `basename="{20102,1501}"`,
  `location="{20004,4050011}"`) which resolve via the game's text pages.
- **Money is stored in cents.** Verified for trade-offer `price`, economylog
  `price`, logbook `money`, `info/player@money` and faction `<account>`
  amounts: divide by 100 for credits. (The one observed exception:
  `<trade><prices><reference>` values are whole credits — see below.)
- **Times** (`time=`, `spawntime=`, `starttime=`, `attacktime=`, stat values
  prefixed `time_`) are game seconds since playthrough start, as floats. The
  exception is `info/save@date`, a Unix epoch timestamp.
- **Macros** (`macro="ship_arg_l_destroyer_02_a_macro"`) reference game-data
  asset macros. In this save every macro attribute is fully lowercase; the
  game *data files* use mixed case for some of the same names, so comparisons
  against game data must be case-insensitive.
- **Positions are parent-relative** down the component tree (galaxy → cluster
  → sector → zone → object), in metres; the in-game map shows km. Any link of
  the chain may be `<offset default="1"/>` (= at the parent's origin) and
  `<position>` omits zero axes (`y` missing = 0). An object's sector-local
  position is the sum of its own offset plus every interposed offset below
  the sector (typically the zone's).

## Top of the tree

Children of `<savegame>`, in document order as they occur in the reference
save; Count = size of the whole subtree (including the element itself)
in the reference save:

| Element | Contents | Count | Status |
|---|---|---:|---|
| `<info>` | save/game/player metadata, DLC+mod list | 24 | documented |
| `<universe>` | factions, the whole component tree, jobs, god, … | 5,869,811 | documented (core) |
| `<economylog>` | four typed economy ledgers (cargo/tradeoffer/trade/money) + removed-object list | 2,100,394 | documented |
| `<stats>` | lifetime playthrough counters | 104 | documented |
| `<log>` | player logbook (rolling window) | 3,952 | documented |
| `<messages>` | notification history | 72 | outlined |
| `<tickercache>` | recent ticker lines | 101 | stub |
| `<script>` | script-engine state | 1,367,360 | stub |
| `<md>` | mission-director cue state | 874,430 | stub |
| `<missions>` | active missions and mission offers | 1,405 | outlined |
| `<aidirector>` | AI director state | 1,075,865 | stub |
| `<operations>` | ventures/diplomacy operations state | 108 | stub |
| `<fleetmanager>` | fleet-manager state | 2 | stub |
| `<ventures>` | venture platform state | 1 | stub |
| `<notifications>` | pending UI notifications | 1 | stub |
| `<ui>` | UI state (map filters, etc.) | 3 | stub |
| `<signature>` | integrity signature blob | 1 | stub |

## `<info>`

Complete in the reference save (patch list truncated here; `<patches>` also
contains a `<history>` block repeating the same list — presumably the load
order at first creation **(unverified)**):

```xml
<info>
  <save name="#002" date="1784772579"/>
  <game id="X4" version="900" build="611726" modified="1" time="72813.204" code="3394980" original="900" originalbuild="611726" start="custom_creative" seed="2788852738" guid="8E0C8E37-2192-49FD-BF4B-F535782A1C55"/>
  <player name="Athena Seldon" location="{20004,4050011}" money="5904557"/>
  <patches>
    <patch extension="ego_dlc_split" version="900" name="Split Vendetta"/>
    <patch extension="ws_3737446888" version="100" name="Habitat Capacity Boost"/>
    <!-- … one <patch> per DLC/mod, then <history> repeating them … -->
  </patches>
</info>
```

| Attribute | Meaning |
|---|---|
| `save@name` | save-slot display name |
| `save@date` | wall-clock save time, Unix epoch seconds |
| `game@version` / `build` | game version (900 = v9.0) and build number |
| `game@original` / `originalbuild` | version the playthrough started on |
| `game@modified` | `"1"` when mods are/were active |
| `game@time` | game seconds since playthrough start |
| `game@start` | gamestart id (`custom_creative`, …) |
| `game@seed` | universe seed |
| `game@guid` | playthrough GUID — the only stable playthrough identity |
| `player@name` | player character name |
| `player@location` | `{page,id}` text ref of the current location name |
| `player@money` | player account balance, **cents** |
| `patch@extension` | DLC (`ego_dlc_*`) or workshop mod (`ws_*`) id |

## `<universe>`

Children in document order:

- `<blacklists>` — player-defined blacklist definitions, referenced by ships'
  `<blacklists><blacklist type=… ref=…/>`. *(not yet documented)*
- `<traderules>` / `<fightrules>` — global rule definitions. *(not yet
  documented)*
- `<factions>` — the diplomacy block (next section).
- `<jobs>` — NPC job-system state (`job` elements with `waiting`/`requested`
  ship templates; the full component subtrees of not-yet-spawned ships live
  here too). *(not yet documented)*
- `<god>` — god-engine state (station/object seeding). *(not yet
  documented)*
- `<diplomacy>` — envoy/agent operations (Envoy Pack DLC). *(not yet
  documented)*
- `<controltextures>` — engine state. *(not yet documented)*
- `<component class="galaxy">` — the entire physical universe (the rest of
  this chapter).
- `<cameras>`, `<physics>`, `<uianchorhelper>`, `<uianchorhelper_cutscene>`,
  `<cameraanchor>` — engine/render state. *(not yet documented)*

### `<factions>`

One `<faction id="…">` per faction (132 in this save, including
`visitor###` one-offs). Relations are **directional** (argon→scaleplate can
differ from scaleplate→argon) and an unlisted pair means 0.0 (neutral).
A faction that the player has interacted with, trimmed:

```xml
<faction id="argon">
  <relations>
    <relation faction="antigone" relation="0.67"/>
    <relation faction="scaleplate" relation="-0.32"/>
    <relation faction="xenon" relation="-1"/>
    <!-- … one <relation> per non-neutral counterpart … -->
    <booster faction="player" relation="0.264266" time="72806.6"/>
  </relations>
  <diplomacy active="1" events="1">
    <exclude faction="antigone" reason="dlc2_1"/>
  </diplomacy>
  <moods>
    <mood type="avarice" level="high"/>
  </moods>
  <discounts>
    <booster faction="player" amount="0.15" time="69376.571"/>
  </discounts>
  <licences>
    <licence type="capitalship" factions="antigone"/>
    <licence type="generaluseship" factions="antigone hatikvah"/>
  </licences>
</faction>
```

- `relation` is a float in −1…+1. The in-game −30…+30 scale is a log
  transform of this value, not stored in the save.
- `<booster>` under `<relations>` is a temporary standing modifier, and it is
  **not an offset on the base**: the stored `relation` is the pair's **current
  standing** at its decayed value as of the save (the engine persists it
  mid-decay), with `time` the last-update game time. Effective standing =
  clamp(booster if the pair has one, else base, −1, +1) — E-145. (The former
  additive reading, `clamp(base + Σ boosters, −1, +1)`, is **SUPERSEDED**: it
  mispredicted three in-game rep readings by up to 43 rank points and two signs
  — E-083, FALSIFIED. See
  [../models/faction-relations-model.md](../models/faction-relations-model.md)
  § Rejected alternatives.)
- `<booster>` under `<discounts>` is the same element name with different
  semantics: a trade discount fraction (`amount="0.15"` = 15 %).
- `<licence>` lists which *counterpart* factions granted this faction a
  licence of `type` (space-separated faction ids).

The `id="player"` faction additionally carries the player's global settings
and identity:

```xml
<faction id="player">
  <relations><!-- … --></relations>
  <blacklists>
    <blacklist type="sectortravel" civilian="2" military="2"/>
  </blacklists>
  <fightrules>
    <fightrule type="attack" fightrule="1"/>
  </fightrules>
  <buildrules method="terran"/>
  <licences>
    <licence type="militaryship" factions="alliance pioneers terran argon antigone hatikvah scavenger yaki holyorder"/>
    <!-- … -->
  </licences>
  <account id="[0x10c]" amount="5904557"/>
  <custom>
    <name name="Special Circumstances"/>
    <image file="assets\textures\ui\player_logos/playerlogo_10.tga"/>
  </custom>
</faction>
```

- **`<buildrules method="…"/>`** — the faction's preferred **build
  method**: which recipe variant its yards/stations use when building
  ships, deployables, drones and equipment (`terran`, `closedloop`,
  `default` = universal/commonwealth; the `recipes.csv` `method` column).
  On `id="player"` this is the UI's *Default preferred build method*
  (player-confirmed 2026-07-27: setting = Terran ⇔ `method="terran"`, and
  it is the only `<buildrules>` in the player's tree). Written only when
  a faction's rule differs from its library default — 3 elements in every
  archived save (`player` terran, `scavenger` and `loanshark` closedloop);
  factions without one build on their race's default method. CONFIRMED
  against every in-flight build order in save_008: `build@method` is
  constant per *builder faction* across all 499 tasks and never varies
  with the station's module race — player 12/12 `terran` (matching its
  `<buildrules>`), each NPC faction on its own race method. The lone
  exception, `alliance` building `closedloop` without a faction rule, is
  explained by the per-station override below: its two build tasks sit at
  exactly the two alliance stations that carry one. Parsed into
  `faction_meta.build_method` (v21).
- Per-**station** override (station configuration menu → *Preferred build
  method*, `SetContainerBuildMethod`; empty string = inherit the faction
  rule): serialized as `<build method="…"/>` directly under the station or
  `buildstorage` component — **CONFIRMED** by a controlled change, see
  § Stations. It is *not* a second `<buildrules>` element.
  Effective method per ware = the chosen method if that ware has a recipe
  under it, else `default` (the engine's own fallback, stated in
  `menu_station_configuration.lua`).
- `<account amount>` is the faction treasury in **cents**; the player's
  matches `info/player@money` exactly.
- `<custom><name name="…"/>` holds the player's custom faction name (only
  present when set). NPC factions use the same block with `{page,id}` refs
  and extra attributes (`shortname`, `prefixname`, `spacename`, …).
- `<booster>` elements also appear under `<relations>` of `npc`/`computer`
  *components* elsewhere in the tree — context (inside `universe/factions`)
  matters when scanning for them.

### The component tree

Everything physical is a recursive tree of `<component>` elements. A
component's children include a `<connections>` block whose `<connection>`
elements host the child components:

```
<component class="galaxy" …>
  <connections>
    <connection connection="…">
      <component class="cluster" …>
        <connections> … <component class="sector"> …
          <component class="zone"> … <component class="station"/ship_*/…>
```

The nesting continues *inside* objects: a station contains its modules as
components, a ship contains its engines, turrets, shield generators, crew
(`npc` components), docked ships, and so on. The chain from galaxy down to a
ship's turret is routinely 6–8 components deep.

Component classes present in the reference save (counts for scale):

| Class | Count | Class | Count | Class | Count |
|---|---:|---|---:|---|---:|
| `turret` | 125,796 | `room` | 2,219 | `collectableammo` | 121 |
| `shieldgenerator` | 107,874 | `pier` | 1,943 | `highwayentrygate` | 106 |
| `cargobay` | 71,106 | `buildmodule` | 1,931 | `highwayexitgate` | 106 |
| `dockingbay` | 70,088 | `habitation` | 1,865 | `highway` | 106 |
| `engine` | 33,497 | `station` | 1,775 | `signalleak` | 89 |
| `weapon` | 27,978 | `buildstorage` | 1,693 | `resourceprobe` | 74 |
| `computer` | 17,750 | `ship_l` | 1,126 | `effectobject` | 71 |
| `storage` | 16,879 | `satellite` | 1,079 | `navbeacon` | 66 |
| `cockpit` | 14,889 | `collectablewares` | 1,009 | `anomaly` | 41 |
| `npc` | 13,012 | `asteroid` | 973 | `datavault` | 30 |
| `missileturret` | 11,176 | `recyclable` | 727 | `welfaremodule` | 30 |
| `ship_s` | 8,398 | `mine` | 722 | `navcontext` | 23 |
| `connectionmodule` | 8,372 | `region` | 464 | `processingmodule` | 17 |
| `defencemodule` | 6,275 | `ship_xl` | 366 | `checkpoint` | 16 |
| `ship_m` | 4,653 | `ship_xs` | 346 | `dismantleprocessor` | 4 |
| `dockarea` | 3,686 | `gate` | 323 | `galaxy` | 1 |
| `destructible` | 3,557 | `adsign` | 177 | `player` | 1 |
| `controlroom` | 3,490 | `sector` | 152 | `scene` | 1 |
| `production` | 3,235 | `radar` | 133 | `positional` | 1 |
| `zone` | 2,662 | `object` | 130 | `forceemitter` | 1 |
| `buildprocessor` | 2,458 | `cluster` | 127 | | |
| `missilelauncher` | 2,456 | `celestialbody` | 127 | | |

(`lockbox` is a known class but absent from this save.) A save started with
local ring highways disabled contains no `class="highway"` components at
all.

Common component attributes (all optional except `class`/`id` in practice):

| Attribute | Meaning |
|---|---|
| `class` | component type (table above) |
| `id` | runtime id `[0x…]` — remaps every load |
| `macro` | game-data asset macro |
| `connection` | name of the parent connection slot it occupies |
| `code` | display code `ABC-123` (recycled after death) |
| `name` | custom display name (renames overwrite it) |
| `basename` | base display name, often a `{page,id}` ref |
| `owner` | owning faction id (`player`, `argon`, `ownerless`, …) |
| `knownto` | `"player"` when the player has discovered the object |
| `known` | discovery flag, always `"1"` when present (31,408 elements in save_008, mostly on zones/gates/modules the pipeline drops; among kept universe classes only stations 133 / sectors 108 / clusters 103, nearly all also `knownto` — a deeper "visited" tier, **semantics unverified**); captured on `component` since v20 |
| `read` | encyclopedia/UI flag **(semantics unverified)** |
| `contested` | `"1"` on contested sectors |
| `spawntime` | game time the object was created (0 = at universe creation); 18,357 components carry it here |
| `state` | e.g. `"wreck"`, `"construction"` (module still being built) |
| `construction` | id of the build-sequence `<entry>` this module was built from |
| `factionheadquarters` | `"1"` on the one station per faction where its representative sits |
| `nameindex`, `modulelevel`, `level`, `cover`, `variation`, `seed` | misc display/generation state **(semantics unverified)** |
| `attacker`, `attackership`, `attacktime`, `shipattacktime`, `intentionalattacktime`, `attackmethod` | under-attack bookkeeping (attacker's runtime id + times) |
| `thruster` (ships) | thruster macro (not a child component, unlike engines) |
| `money` (collectables) | credit value in **cents** |
| `blueprints` (vault pickups) | comma-separated blueprint ware ids still inside — **absent from this save** (all collected); known from earlier saves of the same playthrough |

Every component may carry its own `<offset>` right under itself:

```xml
<offset>
  <position x="7.395" y="-6.36" z="-18.909"/>
  <rotation roll="-179.99989"/>
</offset>
```

or the no-offset form `<offset default="1"/>` (178,450 occurrences here).
Positions are metres relative to the parent component (see conventions).

Other recurring child blocks of components, not detailed further:

- `<listeners>` / `<events>` — MD-script event plumbing (which cue is
  watching what). Investigated and **closed 2026-07-27: deliberately never
  captured** — ~186 k rows, no analysis value; not a parser candidate.
- `<movement>` — velocity + interpolation state.
- `<physics>`, `<gravidar>`, `<boost>` — engine/flight state.
- `<source>` — provenance: `class=` `godobject`/`script`/`job`/`drop`/
  `production` with `entry=`/`job=`/… refs.
- `<blackboard>` — script variables.
- `<shields>` / `<hull>` — damage state: `<hull value="88"/>`,
  `<shields><group group=… value=… time=…/>`.
- `<modification>` — installed equipment mods.
- `<supplies>` — ships' own ammo/drone ware reserves — **not** cargo.
- `<removed>` — connections whose child component is gone, e.g. collected
  vault pickups.

### Galaxy, cluster, sector, zone

```xml
<component class="galaxy" macro="xu_ep2_universe_macro" code="AWM-980" id="[0x55b5]">
  <component class="cluster" macro="cluster_409_macro" connection="galaxy" code="BDO-271" knownto="player" known="1" id="[0x55b6]">
    <component class="sector" macro="cluster_409_sector001_macro" connection="cluster" code="TVA-098" owner="freesplit" contested="1" knownto="player" known="1" id="[0x55b9]">
      <component class="zone" macro="zone004_cluster_409_sector001_macro" connection="sector" code="CFT-615" knownto="player" id="[0x55bb]">
```

Clusters also host `region` components (asteroid-field geometry),
`celestialbody`, and the inter-sector `highway` components
(`superhighway001_cluster_42_macro` etc.). Zones carry a `<masstraffic>`
block. Sector/cluster/zone `macro` names are the stable topology identity —
runtime ids are not.

### Sector resource areas

Each sector component carries a `<resourceareas>` block (110 sectors here);
one `<area>` per minable sphere:

```xml
<resourceareas>
  <area id="[0x6844]" yieldid="sphere_large_ore_high_slow" yield="53658" starttime="0">
    <offset>
      <position x="150000" y="10000" z="-250000"/>
    </offset>
    <fields>
      <field region="[0x6841]" macro="env_ast_ore_l_01_macro" weight="1075059"/>
      <!-- … more asteroid-model fields … -->
    </fields>
  </area>
  <!-- … more areas; some carry <reservations><reservation id=…/> (a miner
  working the area) … -->
</resourceareas>
```

- `yieldid` encodes the ware and levels: `sphere_<size>_<ware>_<yield
  level>_<gatherspeed>`. The grammar allows the suffix tokens to be
  optional, but **in both analyzed playthroughs every area carries both**
  (0 of ~6,000 areas lack a level or speed token — review X11; the
  earlier `sphere_medium_silicon_low` example is not from these saves).
  Wares seen in these playthroughs: ore, silicon, nividium, ice,
  hydrogen, helium, methane, rawscrap, rawkhaakscrap (`scrap` appears in
  the yieldid grammar but in no area of either save).
- `yield` is the currently mineable amount (units of the ware).
- `starttime` is the game time at which a depleted area becomes
  respawn-eligible; `0` on live/never-depleted areas. **Trap:** on a
  depleted area the `yield` attribute is **absent** (the game omits
  default attributes; the parser reads it as 0 — review X11 corrected
  an earlier claim that the save literally writes `yield="0"`), and an
  area past its `starttime` is actually respawned and full in-game even
  though its stored yield still reads as empty — the save is not updated
  until something interacts with it. (This v9 format replaced v5.10's
  per-ware `recharge` attributes; there is no resource "recharge" number
  in v9 saves.)

### Stations

Direct children of a `station` component, in observed order:

- `<listeners>`, `<events>`, `<offset>`, `<source>`, `<gravidar>`,
  `<shields>`, `<supplies>` — the common component blocks listed above.
- `<control>` — crew posts (below).
- `<construction>` — the build-plan sequence (below).
- `<ammunition>` — station drones & munitions (below).
- `<weapongroups>` — turret group assignments. *(not yet documented)*
- `<trade>` — offers, prices, reservations (below).
- `<workforces>` — workforce per race (below).
- `<production>` — station-level production block, distinct from the
  per-module cycle state. *(not yet documented)*
- `<economylog>` — self-closing per-station stub with attributes
  (`cargo="0" offer="0"`), not a structural variant of the top-level block.
- `<buildtasks>` — in-progress build tasks (below, under build storages).
- `<build>` — **three different elements share this tag name**, in ONE id
  space, and telling them apart is the whole trick (v29,
  [../reports/build-demand-2026-07-30.md](../reports/build-demand-2026-07-30.md)):
  1. the station's **build configuration**, directly under the station or
     `buildstorage` component (rare, `@method` + optional `<ship>` list —
     documented immediately below);
  2. the **order wrapper**, under `<buildtasks><queue>` or
     `<buildtasks><inprogress>`, carrying
     `id`/`type`/`component`/`builder`/`faction`/`time`/`flags`;
  3. the **processor progress**, on a `buildprocessor` component inside one of
     the host's build/dock modules, carrying `order=` (which joins the
     wrapper's `id` on the same host) plus
     `state`/`step`/`steps`/`start`/`method`/`sequenceindex`.

  Shapes 2 and 3 are one logical task in two rows; the join closed **618 of
  618** on save_002. Observed `@type` vocabulary on that save: `expand` (593
  inprogress + 11 queued, all on build storages), `buildship` (191 queued + 23
  inprogress, on stations), `build` (306 + 24), `restock` (19 queued),
  and a handful of `recycle` / `recycleship` / `recycleanchor`; 286 elements
  carry no `type` at all. Parsed into `build_task` + `v_build_task`
  (db-schema.md).
- The build-configuration form, written only when the station deviates from its
  faction defaults:
  `@method` = the per-station **build-method override**
  (savegame-structure § factions, save-semantics.md § Build method), and
  an optional `<ship absolute="…"/>` child lists the ship macros the yard
  offers. CONFIRMED 2026-07-27 by a controlled in-game change: ABR-398
  (player, faction rule `terran`) had no `<build>` element in save_008;
  after setting *Preferred build method → Closed Loop* on that station it
  saves as `<build method="closedloop"/>`, between `<buildtasks>` and
  `<overrides>`. Only 3 exist in save_009 — ABR-398 plus alliance's
  YZJ-839 (on the `buildstorage` component) and GFG-641 (station, with
  the `<ship>` list); absence = inherit the faction rule. Parsed into the
  `build_method` table (v21); the `<ship>` list is not captured.
- `<snapshot>` — repeats sequence-entry data. *(not yet documented)*
- `<buildplot>` — the station's build-plot definition. *(not yet
  documented)*
- `<connections>` — the modules and docked ships.

**Crew posts** — `<control>` holds one `<post>` per assigned officer,
pointing at the `npc` component filling it:

```xml
<control>
  <post id="shadyguy" component="[0x5686]"/>
  <post id="manager" component="[0x5685]"/>
  <post id="defence" component="[0x5683]"/>
  <post id="engineer" component="[0x5684]"/>
</control>
```

**Workforce** — `<workforces>` wraps one `<workforce>` per race; an
`<insufficient>` child lists wares whose lack is capping growth (amounts are
**not** per-ware quantities — see the build-resources warning below):

```xml
<workforce race="split" amount="227">
  <insufficient>
    <ware ware="cheltmeat" amount="72461"/>
    <ware ware="medicalsupplies" amount="72461"/>
    <ware ware="scruffinfruits" amount="72461"/>
  </insufficient>
</workforce>
```

**Production modules** — each carries its live state, and
`<efficiency product>` is the engine's **complete** multiplier on the recipe
amount (workforce bonus, sector sunlight and any mod effect, all folded into
one number). `<queue ware>` names what it is making:

```xml
<production start="81852.263" end="82752.263" item="0" cycle="0" state="producing">
  <efficiency product="1.12634"/>
  <queue ware="hullparts"/>
</production>
```

The rate is `floor(recipe.amount x product) / recipe.time x 3600` per module —
the engine truncates per CYCLE. Do not confuse this with the station-level
`<offers><production>`, which holds trade offers and no recipe at all.
Parsed since v27 (`module_production`).

**Build plan, listed twice.** The same sequence entries (same `id`s!) appear
in TWO places: the station's own `<construction><sequence>` and — while a
build storage exists — the storage's
`<buildtasks><inprogress><build type="expand"><sequence>` (a station also
repeats its plan a third time under `<snapshot>`). Consumers must dedupe by
entry id **per host** — and the storage's copy belongs to the station named
in `<build component=>`, not to the storage.

**The expand wrapper's `component=` IS the station it serves**, and it is the
direct build-storage → station link that used to have to be inferred from plot
geometry: **593 storages ↔ 593 distinct stations, 1:1**, on save_002
(`v_build_storage_station`). A storage whose station has no expand task in
flight emits no link — 181 of the 625 offer-posting storages on that save — and
11 storages carry both an inprogress and a queued expand for the same station.

**Entry ids are unique only PER STATION.** Every station running the same
station plan carries the same entry ids (2,235 of 22,562 ids in one save are
shared, up to 33 stations on one id), so any lookup keyed on the bare entry
id merges unrelated stations — that is how a finished module on one station
marked an unbuilt entry built on another (see db-schema.md v28).

The sequence includes *unbuilt* entries; a built module's
component elsewhere in the station carries `construction="[entryid]"`
(with `state="construction"` meaning still in progress — its materials still
count). Station side:

```xml
<construction>
  <sequence>
    <entry id="[0x1f64]" index="1" macro="pier_spl_harbor_03_macro">
      <offset>
        <position y="-828.706" z="-510.504"/>
        <rotation yaw="-90"/>
      </offset>
    </entry>
    <entry id="[0x1f67]" index="4" macro="defence_spl_disc_01_macro" connection="connectionsnap002">
      <predecessor index="2" connection="connectionsnap001"/>
      <offset>
        <position x="-0.000102" y="-828.706" z="389.496"/>
        <rotation yaw="-120"/>
      </offset>
      <upgrades>
        <groups>
          <shields macro="shield_spl_m_standard_02_mk2_macro" group="group02"/>
          <turrets macro="turret_spl_m_beam_02_mk1_macro" group="group02"/>
          <!-- … planned loadout: <shields>/<turrets>/<engines> per group … -->
        </groups>
      </upgrades>
    </entry>
    <!-- … -->
  </sequence>
</construction>
```

Build-storage side (same entry ids `[0x1f64]`…, wrapped in the build task;
here `<upgrades generated="1">`):

```xml
<buildtasks>
  <inprogress>
    <build id="[0x5]" type="expand" preexisting="1" builder="[0x55be]" component="[0x5680]" faction="split" time="6206.435" flags="nothing">
      <sequence>
        <entry id="[0x1f64]" index="1" macro="pier_spl_harbor_03_macro">
          <!-- … identical entries … -->
        </sequence>
        <paint inventory="0"/>
      </build>
    </inprogress>
  </buildtasks>
```

**Missing build materials** — `<build>` elements (on `buildprocessor`
components inside build/dock modules, and as bare
`<build method=… order=…>` task wrappers) carry a `<resources>` block; the
`<insufficient>` child lists wares the build lacks:

```xml
<build start="62915.848" step="1" steps="1" method="split" secondary="checkresources" constructionvesselrequired="1" increasehull="1" type="build" state="waitingforresources" sequenceindex="18" order="[0x42]">
  <resources>
    <ware ware="claytronics" amount="61"/>
    <ware ware="energycells" amount="121"/>
    <ware ware="hullparts" amount="222"/>
    <insufficient>
      <ware ware="claytronics" amount="62915"/>
    </insufficient>
  </resources>
</build>
```

**Warning:** the `<insufficient>`/`<shortage>` *amounts* are not per-ware
quantities (in-game cross-checks disproved them — wrong amounts AND wares
the build doesn't need; note the value above matching the build's *start
time*). Treat them as "this ware is lacking" flags only; real construction
demand is the build storage's open buy offers. A `<shortage>` variant exists
with the same `<ware>` children; in this save it appears only under
production-module `<queue>` elements (shown below), the
shipyard-ship-order form under `<build><resources>` is **(unverified in this
save)**. `type="buildship"` builds at wharfs repeat one wharf-wide aggregate
per queued order — meaningless to sum. **E-068 stands as written: those amounts
are not quantities.**

> **SUPERSEDED 2026-07-30 — the conclusion drawn from it, not the warning.**
> This section used to conclude: *"a per-order bill-of-materials model for
> wharf/shipyard construction demand is closed, not a gap: the save does not
> carry the quantities."* Right in outcome, wrong in premise. Only the
> **per-order quantities** are absent; **the target's component tree IS
> carried**. Each `<build type="buildship">` wrapper's `component=` resolves to
> a real ship component — 214 of 214 on save_002 (118 ship_s, 73 ship_m, 12
> ship_l, 11 ship_xl) — with its macro, spawntime and its full installed
> equipment tree, so a per-order BOM is computable from the packaged CSVs
> alone: hull recipe plus every fitted turret, shield, engine, weapon and
> launcher, each itself a ware with a recipe. It was computed. The model is
> closed because the resulting demand is **two orders of magnitude too small**
> to be any yard's storage target — median 0.0 % and maximum 69 % of the
> yard's own `stock + amount`, against a median energy-cell stock of 300,788
> units and a whole outstanding hull BOM of 703 — not because it is
> unreadable ([../reports/build-demand-2026-07-30.md](../reports/build-demand-2026-07-30.md)
> § What the save actually carries; E-028 FALSIFIED). The stock + buy-offer
> proxy (`station_metric.source = 'proxy'`) remains the right answer and is now
> known to be stable to ~1 % over 15,300 s.
>
> Two further facts about those targets, worth knowing before joining on them:
> a **queued** `buildship` target is usually a **connection-less** component —
> an unplaced hull the yard holds — which `component` filters out by design
> (191 of the 214 on save_002), which is why `build_task` denormalizes the
> target's class/macro/code at load. And only **71** of the 235
> buildship + restock tasks have `component@spawntime == build@time`, i.e. a
> hull created for this order; the other 164 point at ships that existed long
> before, because the same element also carries repair / refit / restock work.

**Production modules** — each `production` component carries live cycle
state, an efficiency factor, and its queue (with the shortage form above):

```xml
<production start="71248.835" end="72806.826" item="0" cycle="0" state="waitingforresources">
  <efficiency product="1.53"/>
  <queue ware="turretcomponents">
    <shortage>
      <ware ware="microchips" amount="58648"/>
    </shortage>
  </queue>
</production>
```

**Station drones & munitions** — the station's own `<ammunition>` block
(directly under the station component; docked ships have their own):

```xml
<ammunition>
  <available>
    <item macro="ship_gen_xs_repairdrone_01_a_macro" amount="2"/>
    <item macro="ship_gen_xs_cargodrone_empty_01_a_macro" amount="1"/>
    <item macro="ship_gen_s_fightingdrone_01_a_macro" amount="12"/>
  </available>
</ammunition>
```

This one pool mixes drones (defence/repair/transport/build/mining), police
craft, turret munitions (missiles, countermeasures) and deployables;
`<available>` holds the *current* counts.

**Supply state** — the station's `<supplies>` block (sibling of
`<ammunition>`) records the self-supply machinery behind those counts:

```xml
<supplies>
  <wares>
    <ware ware="energycells" amount="25000"/>
  </wares>
  <orders>
    <ware ware="ship_gen_xs_cargodrone_empty_01_a" amount="30"/>
    <ware ware="ship_gen_xs_repairdrone_01_a" amount="10"/>
    <ware ware="ship_gen_s_fightingdrone_01_a" amount="10"/>
  </orders>
</supplies>
```

- `<orders>` — drone/munition build orders, by product ware. In save_007,
  37 of 40 order rows across 21 stations exactly equal the station's
  current `<ammunition>` count for that drone; the 3 short rows belong to
  ABR-398, which is still gathering inputs — and its orders sum (50)
  matches the drone build target shown in-game. So `<orders>` looks like
  the persisted build TARGET (contradicting the earlier "desired levels
  are not persisted" claim), but only ~21 stations universe-wide carry
  the block at all. **Stronger evidence for TARGET (save_009, v22
  import)**: five *full, idle* player stations carry order rows exactly
  equal to their current drone counts (JQR-498/MXH-411 30-10-10,
  QNF-337/TIH-455 15-5-5, MAL-475 30-10-9 with one fighting drone lost) —
  outstanding orders on a full station would read 0. The residual
  ambiguity is a station whose stock is zero (ABR-398 keeps a 50-drone
  block with no `<ammunition>` block at all, where target and outstanding
  coincide numerically), so the report's play check — raise the target on
  a FULL station, look for 40 vs 10 — still discriminates cleanly.
  Parsed into `station_supply` (kind `order`, v22).
- `<wares>` — supply inputs already set aside (ABR-398: exactly the
  25,000 energy cells its 50 drone builds need at the terran recipe).
  Missing inputs the station cannot source internally become
  `supplies`-flagged buy offers (above). Parsed into `station_supply`
  (kind `ware`, v22) — **stations and build storages only**: ships
  (carriers/auxiliaries) carry an identical `<supplies><wares>` block
  holding their own ammo/drone reserves, which is a different concept and
  is deliberately not loaded into that table.

**Trade block** — `<trade>` children observed:

- `<offers>` — open buy/sell offers (below).
- `<prices>` — configured reference prices + the build price factor (below).
- `<reservations>` — committed in-flight trades (below).
- `<restrictions factions="…">` — station-wide counterparty restrictions
  (3,508 rows in save_008, always `factions="player"` in this save; pairs
  with the `shady`/`invertfactionrestriction` offer flags).
- `<settings>` — ware whitelists of trade stations / pirate bases (58
  stations in save_008): `<setting name="buy|sell|lockavgprice"
  wares="…"/>`, duplicated by a `<trade wares="…">` attribute on the same
  element. **`lockavgprice` semantics VALIDATED** (save + in-game,
  2026-07-27): the *economy* price is pegged at the ware's band average —
  sell offers at exactly avg (588/588 in save_008, zero variance), buy
  offers at avg − 1 Cr — regardless of stock; the storage curve does not
  apply. The trade UI shows the ±1 Cr as tiny "Low/High Demand"
  percentages, and **player-facing reputation/event discounts still stack
  on top** (EBT-957 metallic microlattice: shown 46.75 = 50 × (1 − 2.0%
  demand − 4.5% discount), player-verified) — locked wares remain
  arbitrage-able with good rep. **`supplies`-flagged self-supply buys are
  exempt** from the lock: all 7 such offers on locked wares in save_008
  price off-average (1.105–1.222×, Layer-4 need pricing), sitting beside
  the station's locked regular pair for the same ware (GMJ-316
  smartchips: buy 56 / sell 57 locked + supply buy 63). Zero unexplained
  counterexamples. Parsed into `station_trade_setting` (v20).
- `<active>` — in-flight trades where the host is one side (49 hosts /
  54 rows in save_008), distinct from `<reservations>`: same `<trade>`
  shape plus `escrow` (cents already paid into escrow) and `transferred`
  (units already delivered, e.g. `transferred="138" desired="263"`).
  Parsed into `trade_active` (v20).
- `<source class="…"/>` — provenance tag on offers/trades
  (`class="production"` dominates; constant across all offers in this
  save, so it discriminates nothing).

Open offers sit under `<offers>`, wrapped in a grouping element (only
`<production>` observed, 2,139 occurrences — other group names
**(unverified)**). One
`<trade>` element per open offer; `buyer`/`seller` names the offering
object (which is how build storages' construction demand appears —
their buy offers):

```xml
<offers>
  <production>
    <trade id="[0x4c78]" buyer="[0x5680]" ware="energycells" price="1255" amount="120" desired="120" flags="invertfactionrestriction">
      <source class="production"/>
    </trade>
    <trade id="[0x4c7e]" seller="[0x5680]" ware="turretcomponents" price="29773" amount="1411" flags="invertfactionrestriction">
      <source class="production"/>
    </trade>
    <trade id="[0x4c81]" buyer="[0x5680]" ware="majadust" price="32866" amount="168" desired="168" flags="buyercargovirtual|buyermoneyvirtual|invertfactionrestriction|shady">
      <source class="production"/>
      <restrictions factions="player"/>
    </trade>
    <!-- … -->
  </production>
</offers>
```

- `price` is **cents** per unit; `amount` the open quantity; `desired` the
  wanted total (open + already-reserved portion); `flags` a `|`-joined set
  (`shady` marks illegal-ware offers, `restrictions` limits counterparties).
- **`flags="supplies|…"` marks station SELF-SUPPLY buys** — inputs for the
  station's own drone/munition building, as opposed to production
  resources. CONFIRMED sweep-wide (save_007: all 1,140 flagged offers of
  15,418 are station buys of supply-recipe inputs, across all 17 factions;
  replicated on save_006; zero counterexamples —
  [../reports/supply-offer-discriminator.md](../reports/supply-offer-discriminator.md)).
  On these buys `desired` is the outstanding input need for the station's
  supply build orders (validated exact against ABR-398's drone orders ×
  terran recipe: metallicmicrolattice 2,150, siliconcarbide 190). The same
  station can hold a flagged and an unflagged buy for the SAME ware
  (12 stations in save_007 do) — the two demands stay separate offers.
  This is the save-side marker behind the trade menu's "box" icon.
  Distinct third/fourth demand classes that are NOT flagged: build-storage
  construction buys and wharf/shipyard ship-building buys (equipment,
  missiles for ships under construction) — both plain offers.
  Observed token inventory across both sweeps: `supplies`, `shady`,
  `invertfactionrestriction`, `buyercargovirtual`, `buyermoneyvirtual`,
  `skipbuyerownaccount`.
- Ships carry the same `<trade>` block; idle traders often have just
  `<offers settings="buyintermediates|sellintermediates|blockoffers"/>`.
- `<prices><reference>` holds the station's configured reference prices —
  in **whole credits**, unlike everything else (energycells `buy="21"` ≈ the
  16 Cr average, while offer prices are cents). Near-universal: 21,997 ware
  rows over 4,433 hosts in save_009, i.e. essentially every trading object.
  Parsed into `price_setting` (kind `reference`, v23) — the persisted side
  of pricing Layer 5.

```xml
<prices buildpricefactor="1.07">
  <reference>
    <ware ware="hullparts" buy="276" sell="0"/>
    <ware ware="energycells" buy="21" sell="0"/>
  </reference>
</prices>
```

- **`prices@buildpricefactor`** — the per-station build price factor, the
  multiplier on everything the station builds and sells (ships,
  deployables — see save-semantics.md § deployable pricing). Present on
  exactly the ship/deployable-selling stations (68 of 4,429 price blocks
  in save_008: every wharf/shipyard/equipment dock). NPC values are the
  engine's price variation clamped to `[0.9, 1.15]`
  (`libraries/parameters.xml` `<building><prices><variation>`), pile at
  the clamp bounds (50 of 67), and **drift between saves** (12 of 67
  changed between save_006 and save_008) — always a snapshot, never a
  station constant. A player-owned yard stores the price slider instead
  (observed 1.5 = the `<factor max>` bound).

- **`<prices><override>`** holds manual per-ware price overrides —
  `<ware ware= buy= sell=>` in **whole credits** like `<reference>`, with
  `0` meaning "this side is not overridden". Rare and player-and-NPC
  alike: 22 ware rows over 6 hosts in save_009 (player MXH-411 buy 42
  microlattice / 22 energycells and JQR-498 buy 10 energycells; xenon
  DZQ-914 sells ore 43 / silicon 111; three NPC build storages sell their
  construction wares). Parsed into `price_override` (v22).
- **`<overrides>`** directly under the *component* (not under `<prices>`)
  is the station-config UI's **manual per-ware limits** — CONFIRMED
  2026-07-27, both by the engine's own API names
  (`GetContainerStockLimitOverrides`, `SetContainerBuyLimitOverride`,
  `SetContainerSellLimitOverride` in `menu_station_configuration.lua`) and
  arithmetically against live offers:

```xml
<overrides>
  <max><ware ware="energycells" amount="739800"/>
       <ware ware="weaponcomponents"/></max>
  <buy><ware ware="energycells" amount="739800"/>
       <ware ware="fieldcoils" amount="12"/></buy>
  <sell><ware ware="metallicmicrolattice" amount="34200"/></sell>
</overrides>
```

  - `<max>` — the **stock (storage allocation) limit** per ware: the
    amount the player set aside for that ware.
  - `<buy>` — **buy up to this stock level**. MXH-411 in save_009: limit
    739,800 − stock 488,215 = 251,585 = the live buy offer's `desired`,
    exactly; fieldcoils 12 − 0 = 12, exactly.
  - `<sell>` — **keep this much, sell the excess**. Same station:
    83,773 − 34,200 = 49,573 microlattice offered, 3,867 − 2,646 = 1,221
    computronic substrate, 9,814 − 5,184 = 4,630 silicon carbide — all
    exact. Two other stations offer *less* than stock − limit, which is
    consistent with in-flight reservations holding the rest back
    **(not separately verified)**.
  - A `<ware>` with **no `amount`** means **1**, not 0 — CONFIRMED
    2026-07-27 (player-reported "I can't set it to 0", then found in the
    UI code): every one of these limits is floored at 1 before it reaches
    the engine — `if value == 0 then value = 1` in the buy/sell slider
    handler, `SetContainerStockLimitOverride(container, ware,
    math.max(1, currentlimit))` for the storage level
    (`ui/addons/ego_detailmonitorhelper/helper.lua`) — so the save omits
    the minimum as its default. This also explains the 1-unit buy offers
    on those wares: limit 1 − stock 0 = 1, the same arithmetic as every
    other limit, not a separate mechanism. (The wares appear on the
    station's list at all because a build module needs them.)
  - Rare: 19 rows over 6 stations in save_009. Parsed into `ware_limit`
    (v23).

- **`<trade><reservations>`** holds committed in-flight trades
  (`reserver`, `buyer`/`seller`, `partner`, `ware`, `amount`, `desired`,
  `price` in cents, sometimes `escrow`/`transferred`/`time`) — 2,510 in
  save_009. Note the *same element name* `<reservations>` appears directly
  under components with spatial content (`zone=`, `expiration=`, a
  position — a reserved build/dock spot) and under resource `<area>`
  elements; the `<trade>` ancestry plus a `ware` attribute disambiguates.
  Parsed into `trade_pending` (v26).

  **Each committed trade is stored TWICE, attribute-identical**
  (2,510/2,510 in save_009): here, on the counterpart station, and on the
  executing ship as `<orders><order><trade>` — where the reservation's
  `@reserver` is exactly that ship. The 49 rows the save also lists under
  `<trade><active>` are a strict subset (escrow stage). Anything summing
  committed volume must therefore dedupe by trade `@id`, which is what the
  store's merge does.

  Exactly one of `buyer=`/`seller=` may be absent; `partner` names that
  missing side. This is the rule the pricing model's *pending* term
  depends on — pending outbound for a station = Σ `amount` of committed
  trades where that station is the seller (save-semantics.md § pricing).

**New-station construction sites** are free-floating `buildstorage`
components with **no station ancestor** (directly in a zone), holding the
`buildtasks` plan, their own `<cargo>` of delivered materials, and buy
offers:

```xml
<component class="buildstorage" macro="buildstorage_gen_base_01_macro" connection="space" code="ZNU-076" owner="split" knownto="player" transportdronemode="trade" pendingtransportdronemode="trade" usertransportdronemode="trade" spawntime="6206.422" id="[0x55be]">
```

Once the first modules exist, the storage's `<build component="[0x5680]">`
points at the now-created station component.

### Ships

Ship classes are `ship_xs` / `ship_s` / `ship_m` / `ship_l` / `ship_xl`
(`ship_xs` — drones, pods — was new in late versions). Typical attributes:

```xml
<component class="ship_l" macro="ship_arg_l_destroyer_02_a_macro" code="HVK-394" owner="antigone" spawntime="70460.822" thruster="thruster_gen_l_allround_01_mk1_macro" id="[0xc74]">
```

Notable children (all also seen on stations where marked):

- **`<cargo>`** — actual hold contents, on the ship (or a nested
  `cargobay`/`storage` component; attribute the wares to the nearest
  enclosing ship/station/buildstorage):

  ```xml
  <cargo>
    <ware ware="energycells" amount="7500"/>
  </cargo>
  ```

  `<ware>` elements appear in many other contexts (`<wares>` of floating
  objects, `<supplies><wares>` ammo reserves, `<insufficient>` lists,
  `<inventory>` of NPCs) — the parent element decides the meaning.

- **`<orders>`** — the order queue; `default="1"` marks the standing default
  order; `param` children carry the arguments:

  ```xml
  <orders>
    <order id="[0xba24]" default="1" order="DeployStaticDefenseStrategy">
      <param name="staticdefensestrategy"/>
      <param name="isminesonly" type="integer"/>
      <param name="debugchance" type="integer"/>
    </order>
  </orders>
  ```

  Orders may also carry `state=` (e.g. blocked/critical states) and
  `<syncpoint>` children *(not yet documented)*.

- **Equipment** is nested components: `engine`, `shieldgenerator`, `weapon`,
  `turret`, `missileturret`, `missilelauncher` (with `ammunition="4"` loaded
  counts and `lastshottime`), plus `storage`, `cockpit`, `dockingbay`, …

- **Crew**: officers are full `npc` components (name, code, owner, a
  `<traits role=…><skills …/></traits>` block); the rest of the crew are
  lightweight `<person>` elements under `<people>`:

  ```xml
  <person macro="character_yaki_female_cau_marine_01_macro" role="marine">
    <npcseed seed="8726040872602428135"/>
    <skills boarding="12" engineering="2" management="3" morale="11" piloting="5"/>
  </person>
  ```

  Roles seen: `service`, `marine`, `passenger`, `prisoner`. Skills are
  0–15 integers.

### Fleet hierarchy (player fleets)

A commander/subordinate pair is a mirrored connection link — the follower
owns a `commander` connection whose `<connected>` names the commander's
`subordinates` connection id, and vice versa:

```xml
<!-- on the follower -->
<connection connection="commander" id="[0x6684]">
  <connected connection="[0x66c0]"/>
</connection>

<!-- on the commander -->
<connection connection="subordinates" id="[0x66c0]">
  <connected connection="[0x6684]"/>
</connection>
```

The commander also lists its groups — note the game's own double-m spelling
`assignmment` (2,251 occurrences; there is no correctly-spelled variant):

```xml
<subordinates>
  <group index="1" assignmment="defence"/>
</subordinates>
```

Assignment values seen: `defence`, `mining`, `trade`, `attack`,
`supplyfleet`, `positiondefence`, `assist`. Position-defence groups add
`releaseassignmment="attack"` and `protectedsector="[0x672ed]"`. Each
follower ship carries a flat `<subordinate group="1"/>` element naming its
group index.

**Trap:** flat `<subordinate>` elements also appear under
`universe/jobs/job/waiting` with completely different attributes
(`<subordinate subordinate="[0x13ae]" commander="[0x493c9]"
job="teladi_fighter_escort_s_patrol"/>`) — that is the NPC job system, NOT
the fleet hierarchy.

### Data vaults

Regular data vaults are `class="datavault"`; the five Erlking vaults
(Timelines) are plain `class="object"` — both matched by macro
`landmarks_(erlking_)?vault_*`. An unopened vault holds `destructible`
repair-panel children; loot sits in pickup connections as
`collectablewares`/`collectableblueprints` components. An opened vault gains
`<unlock state="unlocked"/>`; collected pickups leave only a `<removed>`
marker. A regular vault, trimmed:

```xml
<component class="datavault" macro="landmarks_vault_01_macro" connection="space" code="KBE-495" owner="ownerless" id="[0x8aab]">
  <offset>
    <position x="-2087" y="300" z="2604"/>
  </offset>
  <source class="script"/>
  <connections>
    <connection connection="connection_trigger004" macro="connection_trigger004">
      <component class="destructible" macro="interactive_repairpanel_01_macro" connection="connection01" id="[0x8aac]">
        <offset default="1"/>
        <hull value="88"/>
      </component>
    </connection>
    <connection connection="connection_pickup" macro="connection_pickup">
      <component class="collectablewares" macro="sm_gen_wares_exploration_02_a_macro" connection="connection01" code="DYO-595" money="12117600" id="[0x8ab0]">
        <offset default="1"/>
        <wares>
          <ware ware="inv_modulartrigger"/>
          <ware ware="inv_hallucinogenics" amount="2"/>
          <!-- … -->
        </wares>
      </component>
    </connection>
    <connection connection="connection_info">
      <component class="signalleak" macro="dataleak_xs_vault_01_macro" connection="slotconnection" type="data" id="[0x8ab2]"/>
    </connection>
  </connections>
</component>
```

An Erlking vault whose blueprint has been collected (note `<removed>` —
the pickup connections are gone; an unlooted one instead has child
components carrying `blueprints="ware_id,…"`, **not present in this save**):

```xml
<component class="object" macro="landmarks_erlking_vault_04_macro" connection="space" code="WYH-699" owner="ownerless" knownto="player" id="[0x2f96c]">
  <removed>
    <connection macro="connection_pickup002"/>
    <connection macro="connection_pickup001"/>
  </removed>
  <offset>
    <position x="-10283.68" y="5808.466" z="-7077.066"/>
    <rotation yaw="-96.3538"/>
  </offset>
  <source entry="erlking_blueprint_4" seed="6554725687427950394" class="godobject"/>
  <!-- … destructible trigger panels … -->
</component>
```

`<source entry=…>` identifies which vault of the set this is.

### Anomalies / wormholes

Every galaxy anomaly — scannable lore swirls and story warps alike — is
`class="anomaly"`, macro `wormhole_v1_macro` or
`wormhole_v1_standalone_macro` (41 here). Three tiers, distinguished by two
optional children (see `docs/models/wormhole-connection-model.md` for the full
model):

Inert (no `<transition>`, no `<connections>` — permanent scenery, one per
base-game sector):

```xml
<component class="anomaly" macro="wormhole_v1_macro" connection="space" code="ICY-656" owner="ownerless" id="[0x6a52]">
  <offset>
    <position x="175" z="1369"/>
    <rotation yaw="178.1111" pitch="-9.55945"/>
  </offset>
  <source entry="nopileoslegacy_anomaly_01" seed="5044054990889015214" class="godobject"/>
</component>
```

Dormant story warp (`<transition destination="0"/>` — exit assigned by the
mission director at runtime, not resolvable from the save):

```xml
<component class="anomaly" macro="wormhole_v1_macro" connection="space" code="HJD-749" owner="ownerless" id="[0x2ee89]">
  <source entry="S2A_anomaly_01" seed="17252468560025069807" class="godobject"/>
  <transition destination="0"/>
</component>
```

Linked pair (a `<connections>` block; each end's `<connected>` names the
partner's connection id — build a connection-id → owning-anomaly map to
resolve pairs). The `connection` role names the **partner**, not the owner:
the **entry** end owns the `destination`-role connection (pointing at its
exit), the **exit** end owns the `origin`-role connection (pointing back at
its entry) — so this pair traverses IVC-752 → WHT-407 (B4 re-derivation
from `setup_dlc_pirate.xml`'s `add_anomaly_destination` wiring; in-game
confirmation pending). During an Avarice tide wave the pair temporarily
gains the reverse link (4 `<connection>` rows instead of 2); all archived
saves so far are calm-phase:

```xml
<component class="anomaly" macro="wormhole_v1_macro" connection="space" code="WHT-407" owner="ownerless" knownto="player" id="[0x2ff7b]">
  <source entry="S2B_anomaly_01" seed="782053128877211007" class="godobject"/>
  <transition destination="0"/>
  <connections>
    <connection connection="origin" id="[0x2ff7c]">
      <connected connection="[0x8a5e9]"/>
    </connection>
  </connections>
</component>

<component class="anomaly" macro="wormhole_v1_standalone_macro" connection="space" code="IVC-752" owner="ownerless" id="[0x8a5e8]">
  <source entry="S3_anomaly_01" seed="5297873152422558501" class="godobject"/>
  <connections>
    <connection connection="destination" id="[0x8a5e9]">
      <connected connection="[0x2ff7c]"/>
    </connection>
  </connections>
</component>
```

### Floating objects (drops, scrap, lockboxes)

Collectable stock in space is a component with a `<wares>` block:
`recyclable` (scrap cubes), `collectablewares` (dropped cargo / vault loot),
`collectableammo`, and `lockbox` (absent from this save). A scrap cube:

```xml
<component class="recyclable" macro="recyclable_gen_m_scrapcube_01_macro" connection="space" code="DZX-196" id="[0x12def]">
  <!-- … movement/offset … -->
  <wares>
    <ware ware="rawscrap" amount="1000"/>
  </wares>
</component>
```

`<ware>` here may omit `amount` (= 1). Do not confuse with ships'
`<supplies><wares>` blocks (ammo/drone reserves).

### The player component

A single `class="player"` component (the physical player character) sits
somewhere in the tree (in whatever they currently pilot/stand on). Children:
`inventory` (personal wares), `blueprints` (`<blueprint ware=…/>`),
`research` (`<research ware=… method=…/>`), `known`, `unlocks`, `memory`
(below), `discovered` (fog-of-war quadtrees), `theme`, `spacesuit`, and
more.

**`<memory>`** — the player's per-object knowledge state; exactly three
children in save_008 (2026-07 census):

```xml
<memory>
  <subscriptions>
    <item component="[0xe4a]" time="98321.118"/>
    <item component="[0x5c7d]" time="72067.216"/>  <!-- already expired -->
    <item component="[0x2f7b1]"/>                  <!-- no time = permanent -->
  </subscriptions>
  <scan>
    <item component="[0xe4c]" level="2"/>
  </scan>
  <longrangescan>
    <item object="[0x3b411]"/>
  </longrangescan>
</memory>
```

- **`<subscriptions>`** (10,705 items in save_008) — the player's
  trade-info subscriptions. `time` is an **absolute expiry** in game
  seconds; the duration constant is 18,000 s = 5 game-hours
  (`parameters.xml <subscriptiondurations base="18000"
  tradecompleted="18000"/>`; zero items exceed game_time + 18,000,
  CONFIRMED over all 10,694 timed rows). Expired rows are **retained**
  (28.7% in save_008) — consumers must filter `time > game_time`. Items
  without `time` never expire (11 in save_008, all stations —
  purchased/mission subscriptions, **hypothesis**). Subscription targets
  are always `knownto="player"` (7,622/7,622 live), but "known" is ~3×
  broader than subscribed. Satellite-in-sector does NOT imply a live
  subscription (falsified at sector granularity: covered sectors show a
  *lower* live rate). NPC stations/factions have **no** subscription
  state anywhere in the save — this block is the only one, and the
  concept is player-only, so reconstructing what NPC factions "know" from
  subscriptions is **closed: impossible, not pending**. Parsed into
  `player_subscription` (v19).
  The no-`time` permanent subscriptions come from **scanning a data
  leak** on the station (player-confirmed on FEL-543, 2026-07-27).
- **`<scan>`** (11,624 items) — permanent per-component module scan
  levels 0–3, overwhelmingly `class="storage"` modules (11,272); a
  different id set from subscriptions. Parsed into `player_scan` (v20).
- **`<longrangescan>`** — note it keys `object=`, not `component=`.

## `<economylog>`

Structure: **four typed ledgers** — `<entries type="cargo">`,
`<entries type="tradeoffer">`, `<entries type="trade">`,
`<entries type="money">`, each holding `<log>` elements (~2.1 M total),
plus a `<removed>` block (first in document order). The **wrapper block
is the primary semantic key**: a `<log>`'s own `type` attribute names the
*mutation cause* within its ledger, not the record type — the same
`type="trade"` means three different things in three different blocks.
The cargo/tradeoffer/money blocks are **rolling windows** (the game
prunes old entries); the trade block appears to grow from game start —
its row count exactly equals the save's own `trades_executed` +
internal-transfer total (verified in save_002 and save_003). Stations
also embed their own self-closing `<economylog cargo="0" offer="0"/>`
stub element — an attribute-carrying marker, not a nested ledger.

Per-block `<log type=…>` counts (save_003, game time 74,720):

| Block | Types (count) |
|---|---|
| `cargo` (1,313,619) | `trade` 390,156 · `produce` 256,198 · `consume` 242,666 · `script_add` 209,343 · `construction` 112,225 · `collect` 45,610 · `drop` 29,347 · `surplus` 12,493 · `init` 7,195 · `recycle` 5,634 · `script_remove` 2,193 · `destruction` 268 · `transfer` 272 · `ownerchange` 19 |
| `tradeoffer` (842,248) | `buyoffer` 588,854 · `selloffer` 253,394 |
| `trade` (3,656) | `trade` 3,477 · `transfer` 179 |
| `money` (4,773) | `trade` 1,295 · `script_add` 1,182 · `orderqueue_remove` 1,142 · `transfer` 848 · `orderqueue_add` 290 · `collect` 8 · `debug` 6 · `init` 1 · `sellship` 1 |

### The cargo ledger (`<entries type="cargo">`)

Per-(owner, ware) stock mutations. `v` is the **stock level after the
mutation** (CONFIRMED: for pairs whose last cargo-ledger row carries `v`,
it matches the same save's `<cargo>` amount — 96–99% per type, residue
explained by in-flight processes); continuous processes amend their row
in place with a second point `t2`/`v2` (`v2` = the latest level — using
it is what makes the `consume`/`produce` rows match `<cargo>`). An
**absent `v` means stock 0**, not unknown (CONFIRMED: 2,591/2,591 v-less
`type="trade"` rows correspond to zero/absent `<cargo>` in save_003;
replicated in save_010) — the game omits default attributes.

```xml
<log time="83.3" type="trade" owner="[0x3e15f]" ware="ice" v="7611"/>
<log time="62.043" type="produce" owner="[0x25d7b]" ware="energycells" v="829151" t2="3603.699" v2="926267"/>
```

Only the `type="trade"` rows (stock level after a trade touched that
ware) are ingested, into `stock_event`. Traded volume must be derived
from positive deltas between consecutive snapshots per (owner, ware);
summing `v` directly overcounts ~40×. (Reverse-engineered, validated
in-game.)

### The trade ledger (`<entries type="trade">`)

Real transactions (`type="trade"`; buyer AND seller, `price` cents/unit,
`v` the traded amount) and **player-internal transfers**
(`type="transfer"`; same shape minus `price`):

```xml
<log time="961.477" type="trade" ware="stimulants" buyer="[0x399c7]" seller="[0x5425f]" price="33777" v="891" b="891" bmax="0" s="3283" smax="7450"/>
<log time="5279.291" type="transfer" ware="claytronics" buyer="[0x3a7f5]" seller="[0x62c8d]" v="445" b="445" bmax="1132"/>
```

`b`/`s` appear to be the buyer's/seller's stock and `bmax`/`smax`
capacity or target levels **(b/bmax/s/smax semantics unverified)**. A
handful of `trade` rows lack `price` (3 in save_002). Transfer parties
are player↔player in every resolvable case (census over save_003 and
the 559 h playthrough; unresolvable parties are consistent with
later-removed player objects such as build storages) — the game's
`trades_executed` stat counts trades **and** transfers. Trade entries
between the same pair can be **amended/reused** across repeat deliveries
(duplicate `tradeentry` references from the money ledger point at one
entry; `b`/`bmax`/`s`/`smax` update in place).

### The money ledger (`<entries type="money">`)

The **player's** per-object money mutations (CONFIRMED: every owner
resolvable in the current universe is player-faction — 2,497/2,497 in
save_003, 15,431/15,431 in the 559 h playthrough's newest save). All
money values are cents. For `type="trade"` rows:

```xml
<log time="995.834" type="trade" owner="[0x4feb4]" v="12641200" partner="[0x7f389]" tradeentry="2"/>
```

- **`tradeentry` is a 1-based ordinal into the trade ledger** (CONFIRMED:
  the referenced entry's {buyer, seller} equals {owner, partner} for
  1,295/1,295 rows in save_003 and 6,762/6,764 in the 559 h save).
- `v` is the money amount for that trade in cents — exactly
  `price × amount` or within 0.01% (sub-credit unit-price rounding) for
  the unamended majority; rows referencing amended/reused trade entries
  diverge further (hypothesis: `v` accumulates actual payments across
  partial fills while the trade entry shows only its latest state).
  Like the cargo ledger, rows can be amended with `t2`/`v2`.
- Direction is carried by the owner's **role** in the referenced trade:
  seller-side rows almost always carry `v` (money in); buyer-side rows
  are mostly v-less (hypothesis: the payment was already escrowed at
  order time — see `orderqueue_add`, whose `v` ≈ price × amount at
  order placement).

The other types (`script_add`, `transfer`, `orderqueue_add/_remove`,
`collect`, `sellship`, `debug`, `init`) are non-trade money mutations
(mission income, surplus transfers, order-queue escrow, ship sales, …)
with `owner`, optional `partner` and money-scale `v`.

### The tradeoffer ledger (`<entries type="tradeoffer">`)

`buyoffer`/`selloffer` rows per (owner, ware) with `price`, optional
`price2`/`t2`/`v2` amendments and `max` (target level). Offer history —
large, derivable from snapshots, and not ingested.

### `<removed>`

One `<object>` per economy actor that no longer exists, letting old log
entries still resolve to a name (`offer` looks like a game time —
**semantics unverified**):

```xml
<object id="1" space="[0x55b5]" owner="pioneers" name="Oberth" code="AZW-146" offer="27826.302"/>
```

## `<stats>`

A flat list of lifetime playthrough counters (105 in the reference save),
**directly under `<savegame>`**, immediately after `</economylog>` and
before `<log>`. One `<stat id= value=>` per counter, values numeric
strings:

```xml
<stats>
  <stat id="time_total" value="72813.204"/>
  <stat id="sectors_discovered" value="132"/>
  <stat id="money_player" value="5904557"/>
  <stat id="trades_executed" value="3428"/>
  <stat id="trade_value" value="260914602"/>
  <stat id="ships_owned" value="150"/>
  <stat id="stations_owned" value="7"/>
  <!-- … distances, combat counters, ranks, … -->
</stats>
```

`money_player` matches `info/player@money` (cents); `time_*` are game
seconds; `distance_*` km **(unit unverified — E-080)**.

**`<stats>` is not a unique element name.** Planets carry their own
`<stats>` block nested deep in the component tree
(`…/planet/terraforming/stats/stat id="population"`) — two of them in the
reference save. A reader must key on the ancestor path, not the tag: only
`savegame/stats/stat` is the player block (`save/parser.py`'s handler
requires exactly that depth).

The combat-relevant ids, with the reference save's values:

| id | reference value | meaning |
|---|---:|---|
| `ships_destroyed` | 143 | ships killed |
| `capships_destroyed` | 0 | of which capital ships |
| `xenon_ships_destroyed` | 71 | of which Xenon |
| `khaak_ships_destroyed` | 8 | of which Kha'ak |
| `modules_destroyed` | 2 | station modules killed |
| `turrets_destroyed` | 146 | turrets killed |
| `adsigns_destroyed` | 0 | advertisement signs shot |
| `boarding_attempts` | 0 | boarding operations started |
| `ships_boarded` | 0 | boarding operations that succeeded |
| `ships_claimed` | 36 | ships claimed (abandoned or bailed) |
| `pilots_bailed` | 43 | pilots forced out of their ship |
| `fight_rank` / `fight_score` | 16 / 780 | combat rank and score |

**The combat counters are PERSONAL (E-148; E-147 falsified):** they count
the player's own actions, not the fleet's. Settled 2026-07-31: the
fleet's bounty-paid kills alone (259 Combat Reward entries crediting
ships the player was not flying) exceed `ships_destroyed` = 143, and the
fleet has destroyed capitals while `capships_destroyed` reads 0 — an
empire-wide counter allows neither. The block still mixes scopes overall
(`trades_executed` and `stations_owned` ARE empire-wide), so each row's
scope is an observation, not an inference; the exact boundary of
"personal" (turret kills with the player aboard, etc.) is unprobed.

The DB stores the block verbatim in the snapshot-scoped `player_stat`
table ([db-schema.md](db-schema.md) § player_stat).

## `<log>` — the player logbook

A **rolling window** of `<entry>` elements (3,951 here). Attributes are a
sparse union — each category uses what it needs:

| Attribute | Meaning |
|---|---|
| `time` | game seconds |
| `category` | `upkeep`, `missions`, `news`, `tips`, `alerts`, `diplomacy` — or absent |
| `title` / `text` | display strings (localized!) |
| `money` | credits involved, **cents** |
| `entity` / `faction` | actor display refs |
| `component` | runtime id of the subject object |
| `interact` | UI action hint (`showonmap`, `showlocationonmap`, …) |
| `highlighted` | `"1"` on emphasized entries (e.g. under-attack alerts) |
| `x` / `y` / `z` | event position (destroyed-object entries) |

```xml
<entry time="21.4454" category="upkeep" title="Assigned Individual Charles Antonov to Falx." interact="showonmap" component="[0x39aa0]"/>
<entry time="2032.689" category="missions" title="Stocking Up Reserves" text="Mission completed." entity="Anastasia Kelly" money="22567000"/>
<entry time="208.243" category="missions" title="Stocking Up Reserves" text="Mission accepted." entity="Anastasia Kelly" faction="{20203,2901}"/>
```

### Log text formats

`text` embeds newlines as the **literal five-character sequence `[\012]`**
(and color codes as `[\033]#RRGGBBAA#…[\033]X`). Titles/texts are
localization-dependent; the wordings below are the English v9 forms that
carry machine-readable data (verified against the 2026-07-24 harvest of
both playthroughs' archived history where events exist):

- Ship construction / repair / resupply (`category="upkeep"`):
  `<FAC> <ship> (<CODE>) finished <verb> at station: <station> (<CODE>).
  They have paid [the station] <N> Cr.` — details moved from `title` to
  `text` in v9 for resupply (v9-verified for resupply; construction and
  repair have zero archived instances, wording still v5.10-ported).
- Destroyed objects (`category="upkeep"`; v9-verified, 323/323 archived
  rows): title `<name> (<CODE>) was destroyed.`, text
  `Location: <sector>[\012]` + optional `Commander: <name> (<CODE>)[\012]`
  + optional `Destroyed by: <killer> (<CODE>)` (12/323 rows have no
  killer line); carries `x`/`y`/`z` position attrs and
  `interact="showlocationonmap"`. (The v5.10 one-line form
  `<object> in sector <sector> was destroyed by <killer>.` no longer
  occurs.)
- Station manager surplus transfers (`category="upkeep"`, two wordings,
  changed ~v4→v5): `Received surplus of <N> Credits from <manager>` /
  `Received surplus from <station> in <sector>` — zero archived
  instances in either playthrough; **(unverified against v9)**.
- Pirate harassment (title `Pirate Harassment`, text):
  `<ship> <CODE> in <sector>[\012]Accosted by <faction> pirate ship
  [\012]<FAC> <pirate> <CODE>.[\012]Response: <response>`
- Police interdiction (title `Police Interdiction`, text):
  `<ship> <CODE> in <sector>[\012]Ordered by <faction> police to stop
  …[\012]Response: <response>`
- Faction bounty payouts (title `Combat Reward`, **no category**;
  v9-verified 2026-07-31, 259/259 rows of the reference playthrough's
  merged history): text `Faction: <faction name>[\012]Station: <station>
  (<CODE>)[\012]Sector: <sector>[\012]Credited To: Ships: <name>
  (<CODE>)[, <name> (<CODE>)…]` — or `Credited To: Stations: <name>
  (<CODE>)` (6/259) — then the optional `[\012]Bounty: <N,NNN> Cr`
  (7/259 absent) and the optional `[\012]Reputation: +<N>`, which the
  game writes as `+<1` for a sub-unit gain (19/259 absent). The paying
  `Station:` may carry a role suffix, e.g.
  `HOP Paranid Wharf (THO-697) (Police Representative)`. The entry's
  `money` attribute (cents) is the exact bounty; the text is rounded.
  **This is the only per-ship kill attribution the log carries** — the
  game logs no general kill feed, so unwitnessed kills appear nowhere but
  the `<stats>` counters.
- Abandoned ships found (title `Found Abandoned Ship`, **no category**;
  39/39 + 21/21 rows across both playthroughs): text `<finder> <CODE> in
  <sector>[\012]Found abandoned ship <name> <CODE>.[\012]Response: Claim
  if possible`. It records the SIGHTING and the standing response, never
  the outcome — `<stats>`' `ships_claimed` is the only total of
  successful claims.
- Pilots forced to bail (`category="upkeep"` — **not** `alerts`; 45 + 64
  rows across both playthroughs): the whole record is the title,
  `Forced pilot to leave ship <ship> in sector <sector>.`, and the text
  is empty. No actor is recorded, so a bail cannot be attributed to one
  of your ships.

Object codes in log text match `[A-Z]{3}-[0-9]{3}`.

## `<messages>` and `<tickercache>`

`<messages>` holds notification-center entries:

```xml
<entry time="0" id="1" highpriority="1" title="Time Compression Research Component" text="An item has been acquired which, with the necessary research facility, can be used to research time compression technology." source="Betty"/>
```

`<tickercache>` caches recent ticker lines. *(Both otherwise not yet
documented.)*

## `<missions>`

Children: `listeners`, `offer` (open mission offers), `mission` (accepted
missions). Offers carry briefing objectives; missions carry
name/faction/type/reward:

```xml
<offer id="692082" actor="[0x61bc1]" name="14) Boarding Ships" description="Boarding large ships." faction="player" type="tutorial" level="trivial">
  <briefing>
    <objective step="1" type="custom" name="Training Marines"/>
    <!-- … -->
  </briefing>
</offer>

<mission name="Gathering Material" description="" faction="antigone" type="find" reward="459190" index="1"/>
```

`reward` is presumably cents **(unverified)**. *(Otherwise not yet
documented.)*

## Remaining top-level regions (stubs)

All *(not yet documented)*; subtree sizes are in the top-of-the-tree table —
the three engine-state blocks alone are ~3.3 M elements, which is what
justifies the skip:

- `<script>` — script-engine state: instance stacks, variables, object refs.
- `<md>` — mission-director cue state.
- `<aidirector>` — AI director state.
- `<operations>` — long-running operations (ventures, diplomacy agent
  missions).
- `<fleetmanager>` — fleet-manager bookkeeping.
- `<ventures>` — venture platform/online-feature state.
- `<notifications>` — pending UI notifications.
- `<ui>` — persisted UI state.
- `<signature>` — integrity signature blob (last element).
