# Viz internals: dashboard, map, and analysis pages

How the visualization layer is built, page by page. Data semantics live in
[save-semantics.md](save-semantics.md); formats in
[savegame-structure.md](savegame-structure.md) /
[db-schema.md](db-schema.md) / [csv-reference.md](csv-reference.md).

## The dashboard shell (`viz/dashboard.py`, `viz/common.py`)

Each widget is written as its own HTML file under `output/files/` sharing
`lib/` assets (plotly + vendored jQuery/DataTables from
`src/x4analyzer/vendor/` — dashboards are fully offline), embedded in the
dashboard via iframes. The dashboard is **tabbed two-level** — Map; Trade:
Opportunities/Earnings/History/Charts/Starburst Charts (in that order —
opens on Opportunities); Empire: Audit/Station P&L/Fleet/Standings; Market:
Overview/Build Advisor; Universe: Overview/Contested/Relations — vanilla
JS, iframes lazy-load on first SUB-tab open, active view persists in
sessionStorage and the `#tab/sub` URL hash. It is **dark-themed**: theme
constants live in `viz/common.py` and `save_widget()` applies them to every
figure; keep new widgets dark (user preference). Tables use vendored
DataTables. Chart legends/stacks are ordered by volume, largest first.

## Trade history & market pages (`viz/history.py`, `viz/market.py`)

Self-contained interactive pages: trade data embedded as JSON, rendered
client-side with a selector (per-object trade history; global per-ware
market stats).

`build_market` also emits the **Trade → Opportunities** page (lanes +
per-ware "buy here / sell here" offer charts + top trading stations — the
actionable views, with the offer books moved OUT of the market payload; a
lane click jumps the charts to its ware), computed in
`analysis/opportunities.py`: pairwise sell×buy lanes per ware ranked by
spread/m³/jump (jumps via `sectorgraph`, same-sector = 1). Player endpoints
transact at 0 Cr — one rule that makes own-origin lanes pure profit and
drops NPC→player and player→player pairs on the positive-spread filter;
Quettanauts (`kaori`, barter-only) are flagged and UI-excluded by default;
depth (min of the two offer amounts) caps all totals since quoted prices
move against large trades; spoilers hide undiscovered endpoints. Ship
presets are the PLAYER's trade ships with loadout travel speed (save
engines × engines.csv thrust·travel_mult ÷ ships.csv drag_forward — the
in-game encyclopedia formula) and each lane carries its real route length
(station/gate positions along the BFS path, split plain vs
local-highway-sector km via sectors.csv `highway`), so Cr/h = trip profit /
time at 90% travel speed (log-validated) with S/M riding highways at an
assumed 10 km/s (one-way, no spool-up/docking). DataTables `ext.search`
filters on this page must guard on the table id — there are two tables.

## Build Advisor (`viz/advisor.py` + `analysis/sectorgraph.py`)

Scores "build ware W in sector S" for every producible economy ware ×
known sector. Sector adjacency = `gates.csv` (see
[csv-reference.md](csv-reference.md) for how the pairs and endpoint gate
positions are extracted) + same-cluster pairs; factors (demand,
competition, input supply incl. mining yields, hostile distance, workforce
food) are BFS-hop-discounted (÷(1+hops), radius 4), normalized per ware,
weighted client-side with sliders (never an opaque score — each row expands
into its reasoning). Buy-offer backlog counts as amount/24 per hour next to
capacity rates. An "estimated actual flows" checkbox (mirroring the Market
tab's) swaps demand/competition/shortfall/untapped and the balance table
between capacity and stock-flow actuals (`market.actual_flows`); input
ratios ALWAYS use actual net flow (production − existing consumption
nearby) — capacity-based input ratios would count starved producers' output
that cannot be bought.

## Empire audit & station P&L (`viz/audit.py`, `viz/pnl.py`, `analysis/mining.py`)

Empire bottleneck audit: input starvation, raw resource supply, output
pile-up, storage saturation via modcaps.csv, waiting constructions, idle
ships from parsed order queues, staffing, crew gaps. Per-station P&L: trade
attribution by station code incl. subordinate proxy; station value = module
ware prices via wares.csv `component` macro link.

Raw resource supply (`analysis/mining.py`) renders per-station cards: per
hold class (solid/liquid — one shared miner pool each) the overall
shortfall in m³/h (recipe consumption − observed inflow; miner deliveries
ARE regular intra-empire trade_tx rows: seller = miner, seller commander =
the station) and how many miners close it, quoted per ship size ("+32 M or
+12 L") — miner pools are per (hold class, size), each at its MEASURED
full-load rate (own deliveries m³/h ÷ pool hold m³; fallback: empire median
for that size, then per-size ASSUMED_TRIPS_PER_H). Ship cargo capacity
lives on storage macros linked from the ship macro's connections —
extract-gamedata resolves it into ships.csv `cargo`/`cargo_tags` (solid vs
liquid identifies miner type); `cargo` is hold VOLUME in m³, not units.

## The sector map (`viz/map.py` + `viz/map_page.js`)

A self-contained interactive SVG page (no plotly, no lib/ assets):
`_payload()` emits all map content as JSON records in **reference-pixel
space** (y-down, one unit = one px at the R-tuned 1536×864 density; the
anisotropic data→px transform stays on the Python side so hexes are regular
polygons and zoom is a uniform viewBox scale), and the `map_page.js`
template (inlined at build time, tokens substituted via `str.replace` —
never f-strings) renders it client-side. Map x/y = galaxy x/z; R's fixed
5.10 ranges auto-widen for DLC content and define the scene extents.
Multi-sector clusters use slot patterns (`_SLOTS`) derived from real
in-cluster offsets, so DLC sectors place automatically. Symbol geometry
(flat-top `hexagon2`, `star`, `star-triangle-down`, `diamond-x`) is ported
verbatim from plotly.js symbol defs — marker "size" = point-to-point width.

Interactivity:

- viewBox pan/zoom (wheel about cursor 1×–10×, drag, reset, keys; the
  dashboard iframe just fills the viewport, `build_map`'s returned w/h are
  advisory), zoom-tiered counter-scaled labels.
- HTML legend: faction all/none; single-select **resource overlay** drawn
  as percentile gauges on the hex edges independent of faction selection —
  **mineable-now** solid up the two LEFT edges, **max replenishment rate**
  dashed up the two RIGHT edges, rank among non-zero sectors only, median =
  full bottom edge of its side (so short-left/tall-right =
  empty-but-replenishing, tall-left/short-right = full-but-slow).
  Mineable-now = Σ over areas of live yield OR full capacity for an
  eligible-empty ("overdue") area (past its respawn `starttime`; reads
  yield=0 in the save but is respawned & full — the encyclopedia number) OR
  0 while still on the respawn cooldown — see
  [../models/resource-depletion-model.md](../models/resource-depletion-model.md).
  Max replenishment rate = Σ capacity/respawndelay (units/h,
  regionyields.csv), the ceiling if every area were held depleted;
  **gatherspeed is deliberately excluded** (it governs extraction, not
  respawn). The detail panel headline shows mineable-now, with a
  collapsed-by-default `<details>` dropdown per resource listing each
  actual field's now/cap and status (live / full (respawned) / respawns in
  ~Xm / depleted / capacity unknown) from `frames.resource_areas` (payload
  `area_status`, spoiler-safe).
- Hover tooltips + gate-connection highlight; click → sector detail panel
  (stations/yields/connections). The stations payload for the detail panel
  is spoiler-filtered like everything else — no hidden names may reach the
  page.
- Player-assets overlay (dashed ring + count badge per sector; zoomed in
  also per-station diamond markers with name/code tooltips, in a group
  above the hit hexes so they're hoverable).
- Data-vault overlays (regular = cyan stars, Erlking = gold stars, all zoom
  levels; larger solid = unopened vs smaller dimmed hollow = opened, legend
  labels carry opened/total counts, tooltips give code/status/blueprint).
- Wormhole/anomaly overlay (default off): every `class="anomaly"` in the
  galaxy tiered as **linked** = violet solid ring + core with a dashed
  arrowed link to its partner, **dormant** = violet dashed ring (a story
  `<transition>` whose exit is assigned in-mission, not in the save),
  **inert** = dim dot (a god-placed "Unstable Warp Anomaly", permanently
  "too unstable to be active" — 30 of them, one per base-game sector, never
  script-activated); partners resolved by the connection-id ownership map,
  direction origin→destination, links spoiler-dropped if either endpoint is
  undiscovered — see
  [../models/wormhole-connection-model.md](../models/wormhole-connection-model.md).
- Search/jump; sessionStorage view persistence.

Gate lines attach at the gates' approximate in-sector positions (endpoint
zone offsets from gates.csv, scaled so the farthest sits at 75% of the hex
half-width); same-cluster gates.csv rows draw as a separate Superhighways
layer (dashed teal) — superhighways are DIRECTIONAL tubes, so gates.csv
carries a `oneway` column (the exit sector macro, empty for two-way; the
galaxy's only case is Savage Spur I→II, `cluster_112`) and the payload gate
record's 7th field encodes it (0 two-way / 1 flows-to-b / 2 flows-to-a),
drawn as a midpoint arrowhead toward the exit; galaxy.xml jump gates are
stored once and inherently two-way, so the one-way test is sechighways-only.
Local ring-highway segments (highways.csv, zone-to-zone endpoints from the
sector macros' zonehighways connections) draw as an amber Highways layer —
three independent Base Map toggles. Deselected factions dim to 0.15 instead
of hiding; stroke weights counter-scale with zoom (capped ~1.3× base screen
weight). Labels swap at the zoom threshold: one cluster name per
multi-sector cluster when zoomed out, sub-sector names when zoomed in with
the cluster name floating above the hex (below when a hex sits directly
above).

The in-cluster ARRANGEMENT of multi-sector clusters is NOT derivable from
any game data file — the in-game-audited tables in map.py (`_LEFT_HANDED`,
`_SWAP_ORDER`, `_NAME_BELOW`, `_CLUSTER_NAMES`) encode mirroring, sector
order, label placement and the Sol cluster display names; **extend them,
don't re-derive**.

Facility overlays (faction HQs, shipyards, wharfs, equipment docks, trading
stations; default on): classification is module-based from `built_modules`
(`buildmodule_*_ships_*` + l/xl → shipyard, without → wharf, `_equip_` →
equipment dock; display precedence shipyard > wharf > equipdock since
player yards can be all three) with trading from the basename label; zoomed
out each cluster shows one icon row at its hex bottom (kind union), zoomed
in icons sit at the stations' sector-local positions (shared normalization
with gate endpoints).

## Diplomacy views (`viz/diplomacy.py` + `viz/diplomacy_page.js`)

Faction diplomacy, split by whose perspective it answers: **Empire →
Standings** (player ↔ each faction) and **Universe → Relations** (the
directional faction×faction matrix). All from the save's
`universe/factions` block — parsing and storage in
[db-schema.md](db-schema.md), semantics in
[../models/faction-relations-model.md](../models/faction-relations-model.md).
Frames pivots to `faction_relations` with base/booster/**effective** =
clamp(base + Σboosters, −1, 1) — the standing AS OF THE SAVE, since the
engine persists boosters at their current decayed value.

Two self-contained pages (map.py `_PAGE`+external-JS pattern,
`window.X4DIPLO`, `diplomacy_page.js` branches on `view`): Standings = a
DataTables table with diverging −30..+30 bars, rank band, discount, licence
count, treasury; Relations = a hand-SVG directional heatmap (diverging
red→grey→green by |uiv|/30, war/ally outlines, player row/col emphasized,
hover shows both directions). Relations are **directional (NOT symmetric** —
argon→scaleplate −0.32 vs antigone→scaleplate −0.1) and an unlisted pair =
0.0 neutral, so the matrix comes from the save alone (no
extract-gamedata/reference CSV). The −30..+30 rank value is a fixed log
formula (`sign(r)·10·log10(|r|·1000)`, linear inside ±0.0032) kept as code
constants. NO spoiler handling — relations are global state, not
exploration-gated. Curated faction order/roster (`_ORDER`, real factions
only — excludes visitor###/civilian/ownerless).

## Weapon-mod dashboard (`viz/weaponmods.py` + `gamedata/weapons.py`/`weaponsim.py`)

The `gamedata-dashboard` subcommand: a static GAME-FILE analysis page (no
savegame involved), currently one tab comparing weapon mods per weapon at
optimal rolls. Fully self-contained HTML (inline CSS/vanilla JS, no
vendored libs). Simulation rules were validated in-game — a mod multiplies
the stat field EXACTLY as stored (`reload rate` ×2 = twice the fire rate,
so optimal roll is the range max; `reload time` would want the min), clip
(`<ammunition>`) reload time is never modified, no cooling happens while
firing, steady-state cycle fires reenable→overheat. Reference numbers in
`tests/test_weaponsim.py` (EM Gun: 28.57 shots per heat bar, 20.41 s cold
overheat). Weapon macros are deduped across DLCs in load order (timelines
re-issues terran weapons); `equipmentmods.xml` bonus blocks whose child
count fits `max` at chance 1.0 are forced (applied at least-bad value),
larger weighted pools are optional (detail-only).
