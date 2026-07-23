# x4analyzer reference CSVs

The full reference for the game-data CSVs that `extract-gamedata` writes and
the analysis consumes. Third companion in the chain: game files → **reference
CSVs** (this document) → database ([db-schema.md](db-schema.md)) — with the
save side covered by [savegame-structure.md](savegame-structure.md). Where
db-schema.md says a DB table is loaded from a CSV, this document is the
authority on that CSV.

The extractor is `gamedata/extract.py` (with `catalog.py` for the archive
reader, `textdb.py` for localization, `engines.py` for engine stats); the
loader is `gamedata/refdata.py`. Everything below was verified against the
committed CSVs in `src/x4analyzer/data/` (headers diffed programmatically,
row counts from the files, checked 2026-07-23). The committed copies were
extracted from **game v9.0 + all official DLCs, no mods**. Out of scope: the
retired legacy csv.gz caches, save-file structure, and the DB schema.

## Extraction and override machinery

Stated once here, not repeated per file:

- **Archives.** Game data lives in `.cat`/`.dat` pairs: the `.cat` is a text
  index (`<path> <size> <mtime> <md5>` per line), the `.dat` holds the
  payloads concatenated in index order, so each entry's offset is the
  running sum of the sizes before it.
- **Load order, later wins.** Base-game numbered cats (`01.cat`, `02.cat`,
  …) in order, then each extension's `ext_*.cat` — official DLCs
  (`ego_dlc_*`, sorted) by default; `extract-gamedata --include-mods`
  appends workshop mods after them. A later archive's copy of a path
  replaces an earlier one, and **loose files on disk override everything**
  (X4's own precedence rules).
- **Library merging.** For a library file (e.g. `libraries/wares.xml`) the
  extractor reads the base version plus each extension's version in load
  order. Extension versions are usually `<diff>` patches; scanning
  descendants by tag handles both full files and patches. Each extracted
  row's `source` column records the contributing extension (empty = base
  game).
- **Diff patches inside existing elements.** DLCs also *modify* existing
  library elements via `<add sel="//ware[@id='…']">` blocks — e.g. Boron
  adds a `boron` production method inside the existing `workunit_busy`
  ware. Recipe extraction scans these `add` blocks explicitly; missing
  them once overcounted Terran energy production 3.5×.
- **Localization.** Display strings in game files are `{page,id}`
  references into the language t-files (`t/0001-l044.xml` = English, plus
  extension t-files, merged). The extractor resolves them at extraction
  time — recursively (nested refs), stripping `(comments)` and unescaping
  `\(` `\)` — so every `name`/`description` column below holds plain text.
- **Casing.** Macro names are lowercased at extraction boundaries (game
  files use mixed case; savegames are lowercase) — every `macro` column
  below is lowercase, and consumers compare case-insensitively.
- **Override resolution at load.** `refdata.py` loads each CSV from the
  per-user data dir (`~/.local/share/x4analyzer/`) if present, else from
  the packaged copy (`src/x4analyzer/data/`, committed so wheel/uvx
  installs work without a game install). Optional CSVs missing in both
  places load as empty frames; a few back-compat shims patch older user-dir
  extracts (pre-spline `highways.csv` endpoint columns are converted to
  `points`; missing `sectors.highway` defaults to 0, missing
  `ships.drag_forward` to NA). Regenerate the user copies with
  `uv run x4-analyzer extract-gamedata`, the committed ones by adding
  `--data-dir src/x4analyzer/data`.

Files and row counts (committed copies): `clusters.csv` 127 ·
`engines.csv` 177 · `factions.csv` 31 · `gates.csv` 179 ·
`gatherspeeds.csv` 5 · `highways.csv` 55 · `modcaps.csv` 240 ·
`modules.csv` 68 · `recipes.csv` 5,171 · `regionyields.csv` 45 ·
`sectors.csv` 152 · `ships.csv` 358 · `wares.csv` 1,915 ·
`textdb.csv.gz` 71,508.

## factions.csv

Faction catalog. One row per faction id; key `id`. Feeds the DB `faction`
table.

| Column | Meaning | Provenance |
|---|---|---|
| `id` | faction id as savegames use it (`argon`, `xenon`, …) | `libraries/factions.xml` `faction@id` |
| `shortname` | short display code (`ARG`) | `faction@shortname`, text ref resolved |
| `name` | display name | `faction@name`, text ref resolved |
| `primaryrace` | primary race id | `faction@primaryrace` |
| `colour` | `#rrggbb` map colour | derived: `faction/color@ref` → `libraries/colors.xml` `mapping@id/@ref` → `color@r/@g/@b` |
| `source` | contributing extension (empty = base) | derived: archive source |

Consumer note: the analysis overrides `colour` with the R-era palette for
the original factions and special-cases the short codes for `player`
(`PLA`) and the synthetic `ownerless` (`NIL`), which is a sector owner in
saves but absent from `factions.xml`.

## wares.csv

Ware catalog — every ware the game defines, not just tradeables (includes
modules, ships, equipment, inventory items). One row per ware id; key `id`.
Feeds the DB `ware` table.

| Column | Meaning | Provenance |
|---|---|---|
| `id` | ware id as saves and recipes use it | `libraries/wares.xml` `ware@id` |
| `name` | display name | `ware@name`, text ref resolved |
| `group` | ware group (`hightech`, `foodstuffs`, …) | `ware@group` |
| `transport` | storage class (`container`/`liquid`/`solid`/`inventory`/…) | `ware@transport` |
| `volume` | m³ per unit | `ware@volume` |
| `tags` | space-separated tags (`economy` marks economy wares) | `ware@tags` |
| `price_avg` | average price, **credits** (saves store cents; game files don't) | `ware/price@average` |
| `component` | macro built from this ware, lowercased — the ware ↔ module/ship link | `ware/component@ref` |
| `source` | contributing extension | derived: archive source |

## clusters.csv

Cluster positions and lore. One row per cluster macro; key `macro`. Feeds
the DB `cluster_ref` table.

| Column | Meaning | Provenance |
|---|---|---|
| `macro` | cluster macro, lowercased | `maps/xu_ep2_universe/galaxy.xml` `connection[@ref="clusters"]/macro@ref` |
| `x`, `y`, `z` | galaxy position, metres | same connection's `offset/position` |
| `name` | display name | `libraries/mapdefaults.xml` `dataset/properties/identification@name`, resolved |
| `description` | lore text | same element `@description`, resolved |
| `source` | contributing extension | derived: archive source |

## sectors.csv

Sector membership and in-cluster placement. One row per sector macro; key
`macro`. Feeds the DB `sector_ref` table (which omits `sunlight` and
`highway`).

| Column | Meaning | Provenance |
|---|---|---|
| `cluster` | owning cluster macro | `maps/xu_ep2_universe/*clusters.xml` cluster macro |
| `macro` | sector macro, lowercased | cluster macro's `connection[@ref="sectors"]/macro@ref` |
| `x`, `y`, `z` | in-cluster offset, metres | same connection's `offset/position` |
| `name` | display name | `libraries/mapdefaults.xml` identification, resolved |
| `sunlight` | sunlight multiplier (solar-panel output scale; sector value, falling back to cluster, default 1.0) | `mapdefaults.xml` `dataset/properties/area@sunlight` |
| `highway` | 1 = the sector has a local ring highway (used to split trade-route km into highway-capable legs) | derived: sector macro declares a `zonehighways` connection |
| `source` | contributing extension | derived: archive source |

## gates.csv

Sector adjacency: one row per jump-gate or accelerator **pair**, endpoints
sorted so `sector_a < sector_b` lexically. Feeds the DB `gate` table (which
loads only `sector_a`/`sector_b`/`source`); the map and Build Advisor read
the full file.

| Column | Meaning | Provenance |
|---|---|---|
| `sector_a`, `sector_b` | the joined sector macros | inter-cluster: `galaxy.xml` `connection[@ref="destination"]` — both endpoints' zone paths embed the sector connection names; intra-cluster accelerators: cluster macros' `sechighways` connections (entrypoint/exitpoint paths, same trick) |
| `ax`, `az` / `bx`, `bz` | each gate's sector-local position, metres (0/0 when unresolved) | derived: zone offset (sector macro's `zones` connection) **plus** the gate object's offset inside the zone (`*zones.xml`, matched by gate connection name — one zone can host two gates tens of km apart, and zone centres alone sat up to 77 km off) |
| `source` | contributing extension | derived: archive source |
| `oneway` | empty = two-way; else the sector macro traffic flows **to** | derived: `sechighways` connections are directional (one per direction); a pair is one-way when its reverse connection is absent. Galaxy jump gates are stored once and inherently two-way, so the test applies to accelerators only. The galaxy's sole case: Savage Spur I → II (`cluster_112`) |

## highways.csv

Local (ring) highway tracks for the map's Highways layer. One row per
`zonehighways` connection of a sector. Not loaded into the DB.

| Column | Meaning | Provenance |
|---|---|---|
| `sector` | sector macro | sector macro's `connection[@ref="zonehighways"]` |
| `points` | the curved track as `"x z;x z;…"`, metres sector-local | derived: the referenced highway macro's `splineposition` control points (`*zonehighways.xml`) evaluated as cubic Béziers — each control point carries a unit tangent and in/out **handle lengths** (~chord/3, which identifies Bézier handles, not Hermite derivatives), 16 samples per span — then placed by the connection's offset. Fallback for spline-less macros: a straight entrypoint→exitpoint zone segment |
| `source` | contributing extension | derived: archive source |

## modules.csv

Production/processing station modules. One row per (macro, ware, method) a
module can run; key (`macro`, `ware`, `method`). Feeds the DB `module_ref`
table.

| Column | Meaning | Provenance |
|---|---|---|
| `macro` | module macro, lowercased | `assets/structures/**/macros/*.xml` `macro@name` |
| `name` | display name | `properties/identification@name`, resolved |
| `ware` | produced ware | `properties/production/queue@ware` (single), `queue/item@ware` (multi-ware, e.g. Scrap Recyclers), or `properties/products/ware@ware` (processing modules) |
| `method` | recipe method (`default`, race methods, `processing`) | same elements' `@method`; `processing` for products-form modules |
| `scale` | parallel recipe units (processing: `products/ware@amount`) | derived: 1.0 for queue-form modules |
| `workforce` | workforce the module uses at max | `properties/workforce@max` |
| `source` | contributing extension | derived: archive source |

## recipes.csv

Ware production recipes, long form: one row per (ware, method, input);
inputless recipes get a single row with empty `input_ware`. Key (`ware`,
`method`, `input_ware`). Feeds the DB `recipe` table. Workforce *upkeep* is
itself a recipe here (the per-race `workunit_busy` methods — DLC races
arrive via the `<add sel>` diff mechanism above).

| Column | Meaning | Provenance |
|---|---|---|
| `ware` | produced ware | `libraries/wares.xml` `ware@id` (production parent) |
| `method` | production method (`default`, `teladi`, `terran`, `boron`, `processing`, `recycling`, `closedloop`, …) | `ware/production@method` |
| `time` | seconds per cycle | `production@time` |
| `amount` | output units per cycle | `production@amount` |
| `input_ware` | one input ware | `production/primary/ware@ware` |
| `input_amount` | units of that input per cycle | `production/primary/ware@amount` |
| `work_effect` | max output multiplier bonus at full workforce (0 = none) | `production/effects/effect[@type="work"]@product` |

## modcaps.csv

Station-module capacities. One row per module macro that declares
workforce, cargo, or unit storage; key `macro`. Feeds the DB `modcap`
table.

| Column | Meaning | Provenance |
|---|---|---|
| `macro` | module macro, lowercased | `assets/structures/**/macros/*.xml` `macro@name` |
| `class` | module class (`habitation`, `storage`, `production`, …) | `macro@class` |
| `housing` | workforce the module houses | `properties/workforce@capacity` |
| `workers` | workforce the module needs | `properties/workforce@max` |
| `cargo_max` | storage volume, m³ | `properties/cargo@max` |
| `cargo_tags` | storage classes accepted (`container`, `liquid`, `solid`) | `properties/cargo@tags` |
| `unit_storage` | drone/unit slots the module adds | `properties/storage@unit` |

Gotcha: `unit_storage` is the readable **floor** of a station's shared
drone pool — only dock/pier/build/defence modules declare it; the engine's
`units.maxcount` adds an unexposed ~10 per production module, so summing
this under-counts big factories (the `capacity_floor` caveat in
db-schema.md § station_munition).

## ships.csv

Ship model catalog. One row per ship macro (classes `ship_xs`…`ship_xl`);
key `macro`. Feeds the DB `ship_ref` table (which omits `cargo_tags` and
`drag_forward` — both are consumed directly from the CSV).

| Column | Meaning | Provenance |
|---|---|---|
| `macro` | ship macro, lowercased | `assets/units/size_*/macros/ship_*.xml` `macro@name` |
| `model` | display name (`Behemoth Vanguard`) | `properties/identification@name`, resolved |
| `class` | size letter `XS`/`S`/`M`/`L`/`XL` | derived: from `macro@class` (`ship_s` → `S`, …) |
| `race` | maker race | `identification@makerrace` |
| `purpose` | primary role (`fight`, `trade`, `mine`, …) | `properties/purpose@primary` |
| `hull` | hull points | `properties/hull@max` |
| `mass` | tonnes | `properties/physics@mass` |
| `cargo` | hold **volume in m³ — not units** (divide by the ware's `volume`: an 8,800 m³ Bolo carries 880 ore at 10 m³ each) | `properties/cargo@max`, or derived: summed from the storage macros the ship links via `connections/connection/macro@ref` (`storage_*.xml` `properties/cargo@max`) — capital/miner holds live on those separate macros, not the ship macro |
| `cargo_tags` | hold storage classes, united across linked holds (`solid` vs `liquid` identifies miner type) | same elements' `@tags` |
| `crew` | crew capacity | `properties/people@capacity` |
| `price` | average price, credits | derived: `wares.csv` `price_avg` of the ware id = macro minus its `_macro` suffix |
| `drag_forward` | forward drag (the speed divisor) | `properties/physics/drag@forward` |
| `source` | contributing extension | derived: archive source |

## engines.csv

Engine thrust stats for loadout speed. One row per engine macro; key
`macro`. Not loaded into the DB — consumed directly (trade-opportunity
travel times from the player ships' actual mounted engines, and the
gamedata dashboard).

| Column | Meaning | Provenance |
|---|---|---|
| `macro` | engine macro, lowercased | engine macro files, `macro@name` (`class="engine"`; fx/`_video` preview macros skipped) |
| `size` | size letter (empty for odd macros like the spacesuit engine) | derived: regexed from the macro name |
| `type` | `allround` / `travel` / `combat` (empty when unclassifiable) | derived: regexed from the macro name |
| `mk` | mark number (default 1) | derived: regexed from the macro name |
| `forward` | forward thrust | `properties/thrust@forward` |
| `travel_thrust` | travel-mode thrust **multiplier** | `properties/travel@thrust` |

The in-game encyclopedia speed formula these feed: forward speed =
`forward ÷ ships.drag_forward`; **travel speed = `forward × travel_thrust
÷ ships.drag_forward`** (per mounted engine; the analysis multiplies by
the save's engine count).

## regionyields.csv

Resource-area replenishment parameters — quantifies the `yieldid` level
token of save resource areas (savegame-structure.md § Sector resource
areas; full model in docs/models/resource-depletion-model.md). One row per
(level, ware); key (`level`, `ware`). Not loaded into the DB.

| Column | Meaning | Provenance |
|---|---|---|
| `level` | yield tier (`verylow`…`veryhigh`), matching the save `yieldid`'s level token | `libraries/regionyields.xml` `yields/yield@id` |
| `ware` | resource ware | `yield/ware@id` |
| `yield` | the area's **capacity** — the amount a respawned area holds | `yield/ware@yield` |
| `respawndelay` | **minutes** after depletion until the area respawns (refills to capacity in one step) | `yield/ware@respawndelay` |

Max replenishment rate of an area = `yield ÷ respawndelay` — the ceiling
if it were held permanently depleted.

## gatherspeeds.csv

Extraction-speed tiers, matching the save `yieldid`'s *speed* token. One
row per tier; key `id`. Not loaded into the DB — and currently
**unconsumed**: `refdata.py` loads `id`→`factor` into `RefData` but nothing
reads it (`rating` is not even loaded). Kept deliberately: gatherspeed
governs *extraction* rate, not respawn, and the replenishment model
excludes it by design; the file is here for when an extraction-rate
feature needs it.

| Column | Meaning | Provenance |
|---|---|---|
| `id` | speed tier (`veryslow`…`veryfast`) | `libraries/regionyields.xml` `gatherspeeds/gatherspeed@id` |
| `factor` | extraction-speed multiplier | `gatherspeed@factor` |
| `rating` | UI rating value — **written but read by no code** | `gatherspeed@rating` |

## textdb.csv.gz

Full localization dump (gzip CSV, 1.6 MB, 71,508 rows), so analysis runs
can resolve names without the game install. Feeds the DB `text` table.
Format summary only — no page catalog here.

| Column | Meaning | Provenance |
|---|---|---|
| `page` | text page number | `t/0001-l044.xml` (+ DLC t-files) `page@id` |
| `id` | entry id within the page | `page/t@id` |
| `text` | the string, **unresolved** (may itself contain `{page,id}` refs and `(comments)`) | `t` element text |

The `{page,id}` reference scheme: game files and savegames embed display
strings as `{page,id}` (e.g. a save station `basename="{20102,1501}"`, a
player faction name `{20203,3401}`). Resolution substitutes the referenced
text, recurses into nested refs (depth-capped), strips `(comments)`, and
unescapes `\(` `\)`. The dump stores the *raw* strings, so resolution
happens at load time.
