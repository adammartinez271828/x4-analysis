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
| `<economylog>` | rolling economy event window + removed-object list | 2,100,394 | documented |
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
- `<booster>` under `<relations>` is a temporary additive standing modifier;
  the stored `relation` is its **current decayed value** as of the save (the
  engine persists it mid-decay), with `time` the last-update game time.
  Effective standing = clamp(base + Σ boosters, −1, +1).
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
| `known` / `read` | encyclopedia/UI flags **(semantics unverified)** |
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

- `<listeners>` / `<events>` — event subscription/history bookkeeping.
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
  level>_<gatherspeed>` — both suffix tokens optional
  (`sphere_medium_silicon_low` has no speed token). Wares seen: ore,
  silicon, nividium, ice, hydrogen, helium, methane, rawscrap,
  rawkhaakscrap, scrap.
- `yield` is the currently mineable amount (units of the ware).
- `starttime` is the game time at which a depleted area becomes
  respawn-eligible; `0` on live/never-depleted areas. **Trap:** an area past
  its `starttime` still reads `yield="0"` in the save but is actually
  respawned and full in-game — the save is not updated until something
  interacts with it. (This v9 format replaced v5.10's per-ware `recharge`
  attributes; there is no resource "recharge" number in v9 saves.)

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
- `<economylog>` — per-station variant of the top-level block (empty here).
- `<buildtasks>` — in-progress build tasks (below, under build storages).
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

**Build plan, listed twice.** The same sequence entries (same `id`s!) appear
in TWO places: the station's own `<construction><sequence>` and — while a
build storage exists — the storage's
`<buildtasks><inprogress><build type="expand"><sequence>`. Consumers must
dedupe by entry id. The sequence includes *unbuilt* entries; a built module's
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
per queued order — meaningless to sum.

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
craft, turret munitions (missiles, countermeasures) and deployables; only
the *current* counts are stored — desired levels are not persisted.

**Trade block** — `<trade>` children observed:

- `<offers>` — open buy/sell offers (below).
- `<prices>` — configured reference prices (below).
- `<reservations>` — committed in-flight trades (below).
- `<restrictions>` — station-wide counterparty restrictions **(semantics
  unverified)**.
- `<source>`, `<active>`, `<settings>` — *(not yet documented)*.

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
  wanted total **(interpretation unverified)**; `flags` a `|`-joined set
  (`shady` marks illegal-ware offers, `restrictions` limits counterparties).
- Ships carry the same `<trade>` block; idle traders often have just
  `<offers settings="buyintermediates|sellintermediates|blockoffers"/>`.
- `<prices><reference>` holds the station's configured reference prices —
  in **whole credits**, unlike everything else (energycells `buy="21"` ≈ the
  16 Cr average, while offer prices are cents):

```xml
<prices>
  <reference>
    <ware ware="hullparts" buy="276" sell="0"/>
    <ware ware="energycells" buy="21" sell="0"/>
  </reference>
</prices>
```

- `<trade><reservations>` holds committed in-flight trades (reserver,
  partner, ware, amount, price in cents) **(present in earlier saves of this
  playthrough; not re-verified in this one)**. Note the *same element name*
  `<reservations>` appears directly under components with spatial content
  (`zone=`, `expiration=`, a position — a reserved build/dock spot) and
  under resource `<area>` elements; context disambiguates.

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
resolve pairs; `origin` is the entry, `destination` the exit):

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
(incl. per-object scan levels), `discovered` (fog-of-war quadtrees),
`theme`, `spacesuit`, and more. *(Contents not yet documented.)*

## `<economylog>`

Structure: `<economylog><entries>` holding ~2.1 M `<log>` elements, plus a
`<removed>` block. This is a **rolling window** — the game prunes old
entries, so history older than a few game-hours is gone from any single
save. Stations also embed their own (empty here) `<economylog>` element.

Entry types and counts in the reference save:

| Type | Count | Type | Count |
|---|---:|---|---:|
| `buyoffer` | 573,968 | `init` | 7,196 |
| `trade` | 383,742 | `recycle` | 5,428 |
| `produce` | 246,575 | `script_remove` | 2,123 |
| `selloffer` | 246,334 | `transfer` | 1,257 |
| `consume` | 236,125 | `orderqueue_remove` | 1,124 |
| `script_add` | 201,672 | `orderqueue_add` | 288 |
| `construction` | 108,682 | `destruction` | 254 |
| `collect` | 44,450 | `ownerchange` | 9 |
| `drop` | 28,536 | `debug` | 6 |
| `surplus` | 12,471 | `sellship` | 1 |

### `type="trade"` — two flavors

**Full transactions** (buyer + seller + price — 3,252 here) are real trades:

```xml
<log time="961.477" type="trade" ware="stimulants" buyer="[0x399c7]" seller="[0x5425f]" price="33777" v="891" b="891" bmax="0" s="3283" smax="7450"/>
```

`price` is cents/unit, `v` the traded amount; `b`/`s` appear to be the
buyer's/seller's stock and `bmax`/`smax` capacity or target levels
**(b/bmax/s/smax semantics unverified)**.

**Owner-only entries** (380,490 here) are NOT transactions:

```xml
<log time="83.3" type="trade" owner="[0x3e15f]" ware="ice" v="7611"/>
```

`v` records the owner's **stock level after a trade touched that ware** —
a snapshot, not an amount. Traded volume must be derived from positive
deltas between consecutive snapshots per (owner, ware); summing `v`
directly overcounts ~40×. (Reverse-engineered, validated in-game.)

### Other entry types

Per-(owner, ware) counter snapshots in a two-point encoding — value `v` at
`time`, optionally a second point `v2` at `t2`; offer types add `price` and
`max` (target level). Exact counter semantics (cumulative vs windowed)
**(unverified)**:

```xml
<log time="62.043" type="produce" owner="[0x25d7b]" ware="energycells" v="829151" t2="3603.699" v2="926267"/>
<log time="0" type="selloffer" owner="[0x583a4]" ware="advancedcomposites" price="54000" v="1728" max="3256"/>
<log time="0" type="buyoffer" owner="[0xa49ee]" ware="dronecomponents" price="102800" v="80"/>
<log time="149.974" type="collect" owner="[0x2e6b8]" ware="condensate" v="2"/>
<log time="71761.462" type="sellship" owner="[0x61bc0]" v="8189639800" partner="[0x18950]"/>
```

The `orderqueue_add`/`orderqueue_remove`/`debug`/`sellship` types carry
money-like `v` values (cents) and a `partner` id.

### `<removed>`

One `<object>` per economy actor that no longer exists, letting old log
entries still resolve to a name (`offer` looks like a game time —
**semantics unverified**):

```xml
<object id="1" space="[0x55b5]" owner="pioneers" name="Oberth" code="AZW-146" offer="27826.302"/>
```

## `<stats>`

Flat list of lifetime playthrough counters (~100):

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
seconds; `distance_*` km **(unit unverified)**.

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
| `interact` | UI action hint (`showonmap`, …) |
| `highlighted` | `"1"` on emphasized entries (e.g. under-attack alerts) |

```xml
<entry time="21.4454" category="upkeep" title="Assigned Individual Charles Antonov to Falx." interact="showonmap" component="[0x39aa0]"/>
<entry time="2032.689" category="missions" title="Stocking Up Reserves" text="Mission completed." entity="Anastasia Kelly" money="22567000"/>
<entry time="208.243" category="missions" title="Stocking Up Reserves" text="Mission accepted." entity="Anastasia Kelly" faction="{20203,2901}"/>
```

### Log text formats

`text` embeds newlines as the **literal five-character sequence `[\012]`**
(and color codes as `[\033]#RRGGBBAA#…[\033]X`). Titles/texts are
localization-dependent; the wordings below are the English v9 forms that
carry machine-readable data (v9-verified only where the save contains such
events — construction/repair/resupply/destroyed/surplus wording is ported
from v5.10 observations and **(unverified against v9)**):

- Ship construction / repair / resupply (`category="upkeep"`):
  `<FAC> <ship> (<CODE>) finished <verb> at station: <station> (<CODE>).
  They have paid <N> Cr.` — details moved from `title` to `text` in v9 for
  resupply.
- Destroyed objects (`category="upkeep"`, title):
  `<object> in sector <sector> was destroyed by <killer>.`
- Station manager surplus transfers (`category="upkeep"`, two wordings,
  changed ~v4→v5): `Received surplus of <N> Credits from <manager>` /
  `Received surplus from <station> in <sector>`.
- Pirate harassment (title `Pirate Harassment`, text):
  `<ship> <CODE> in <sector>[\012]Accosted by <faction> pirate ship
  [\012]<FAC> <pirate> <CODE>.[\012]Response: <response>`
- Police interdiction (title `Police Interdiction`, text):
  `<ship> <CODE> in <sector>[\012]Ordered by <faction> police to stop
  …[\012]Response: <response>`

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
