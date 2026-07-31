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
move against large trades — **except on `lockavgprice` endpoints**
(pricing Layer 6), which are pegged at band average whatever their stock,
tagged `lk` in the payload and badged *locked* in the table; a
`supplies`-flagged buy on a locked ware is exempt from the lock and stays
untagged (216 tagged endpoints in save_009). Spoilers hide undiscovered
endpoints. Ship
presets are the PLAYER's trade ships with loadout travel speed (save
engines × engines.csv thrust·travel_mult ÷ ships.csv drag_forward — the
in-game encyclopedia formula) and each lane carries its real route length
(station/gate positions along the BFS path, split plain vs
local-highway-sector km via sectors.csv `highway`), so Cr/h = trip profit /
time at 90% travel speed (log-validated) with S/M riding highways at an
assumed 10 km/s (one-way, no spool-up/docking). DataTables `ext.search`
filters on this page must guard on the table id — there are two tables.

## Sunbursts (`viz/sunbursts.py`, `common.Sunburst`)

`Sunburst.add()` accumulates (id, label, parent, value, colour) rows and
takes an OPTIONAL per-node `hover=` string; `figure()` emits plotly
`hovertext`/`hovertemplate` only when at least one node set one (nodes
without fall back to their label), so sunbursts that never pass `hover`
render byte-identically to before. **Fleet Compositions** uses it: the top
ring is the commander's sector, but a subordinate deep in a fleet can sit
in a DIFFERENT sector, so station/ship nodes hover as label + "Sector:
<their own sector>" (`"?"` when unresolved). Slice labels themselves stay
free of sector text.

## Sortable tables (`viz/tables.py`)

One DataTables page per table (`save_table`), dark-themed, height reported
to the dashboard via `parent.postMessage({x4h: …})` on every draw. Earnings
are aggregated by the pure `_earnings_table()` (Earnings/Trades/Items plus
the per-trade, per-item and per-hour rates) over `frames.sales`, which is
**external only** (seller PLA, buyer not PLA) — the rule everywhere else in
the dashboard (History, Charts, Sunbursts, P&L).

The two **Trade → Earnings** tables (per Seller, per Ware or Service) are the
one exception: they carry an "include internal trades" checkbox. Internal
= player→player rows pulled straight from `frames.tradelog`
(`internal_sales()`, same window and `money > 0` filter), attributed to the
save-time commander by the tradelog's existing "Executed by" redirect, so a
station miner's delivery earns for the station it supplies. Both aggregates
are computed up front (`earnings_variants()`) and both tables are rendered
into the same page by `save_table_variants()`; the checkbox only swaps which
one is visible (default OFF = today's external-only numbers) and re-posts the
iframe height. An empty internal set makes the two variants identical.
"Gross Earnings per Constructed Ship Type" and the non-earnings tables keep
plain `save_table()`.

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

**Logistics columns** (fleet sizing) reuse the Trade Opportunities
machinery rather than duplicating it: `opportunities._Router` for route
km and `opportunities.player_trade_ships` for the presets.

- **Haul m³/h** — the active-basis shortfall (demand − competition, so it
  follows the actual-flows checkbox) × the ware's `volume` from
  `wares.csv` (defensively 1 m³ when missing/unparseable — never 0).
- **≈ Traders** — haul ÷ what one ship of the selected preset moves per
  hour, rounded up. Presets are the player's real container ships (cargo
  m³ + loadout travel speed); ships whose engines don't resolve to a
  speed are dropped (they could never size a fleet), and a save with none
  left gets one clearly-labelled generic M freighter (8,000 m³ @ 3,000
  m/s) instead. The trip arithmetic mirrors the Opportunities page
  EXACTLY — plain km at 0.9 × travel speed, highway-sector km at 10 km/s
  for S/M only (L/XL fly everything at travel speed) — minus its dock-time
  overhead, so the count is a lower bound (said so on the page).
- **Distance** — per row, `route_km` from the candidate sector's CENTRE
  ((0,0) sector-local: the advisor scores a sector, not a plot, so there
  is no station position yet) to each in-radius sector with demand,
  averaged with that sector's share of the demand factor as the weight
  (hop-discounted consumption + backlog/24, capacity basis) — the
  numerator of `nd`. Demand in the build sector itself would be a
  degenerate 0 km centre-to-centre leg, so it is charged a flat
  `IN_SECTOR_KM` = 50 km one way (~100 km round trip, a typical
  intra-sector hop). km are computed once under S/M routing and reused at
  L/XL speeds client-side (the split is ship-independent). Rows whose
  demand is unreachable get null km and an em-dash trader count.

The row's ℹ detail gains a **Logistics** block: the weighted one-way
route, the preset's round-trip/m³-per-hour arithmetic, and the INPUT haul
(Σ recipe inputs/h × their volumes) — the latter stated **per production
module**, since the advisor sizes no station.

## Empire audit & station P&L (`viz/audit.py`, `viz/pnl.py`, `analysis/mining.py`)

Empire bottleneck audit: input starvation, raw resource supply, storage
saturation via modcaps.csv, waiting constructions, idle ships from parsed
order queues, staffing, crew gaps. Section order groups
the station findings first and the ship findings (idle ships, crew gaps)
last; the DataTables ids (`t1`…`t8`) are historical, do NOT follow the
displayed order, and are never renumbered — `t2` (the retired "output
piling up" section, folded into storage saturation) is simply unused.
Every section names the SECTOR: a station id → sector name
map (from `frames.stations['sector.id']` via the sectors frame, `"?"` when
unknown) feeds a Sector column right after Station in the starvation,
saturation and staffing tables and for the station rows of crew
gaps; ship rows (idle ships, crew gaps) resolve their own
`frames.ships['sector.id']`; the raw-supply cards carry it as muted fine
print in the card header (`_mining_cards(inflow, pools, st_name, st_sector,
wname)`). Per-station P&L: trade attribution by station code incl.
subordinate proxy; station value = module ware prices via wares.csv
`component` macro link. Its table is JS-driven — rows are positional JSON
arrays (`[label, sector, trades, …]`) and every `columnDefs` target is an
index into that array, so inserting a column means shifting them all; the
cumulative-net chart keeps plain station labels as series names (no sector)
to keep the legend readable.

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

A station with no ROOM for a ware also shows low inflow, so each ware
carries `stock` / `limit` / `want`: held units, its effective ceiling
(manual buy limit → manual max allocation → `station_storage.max_units`,
computed rows only — `source='proxy'` allocations are stock + inbound +
open buys and therefore circular), and its open buy-offer amount.
`mining.storage_blocked()` calls a ware space-limited ONLY when stock ≥
95% of a trusted ceiling (no ceiling ⇒ accepting). The buy offer is
display-only: its amount is allocation − stock − inbound, so in-flight
deliveries zero the bid on a half-empty draining station (MXH-411 read
"storage full" at 37% fill). A class whose consumed wares are ALL blocked
is headlined "⚠ storage full — inflow limited by space, not miners", drops
the "+N miners" advice, and is excluded from the section's finding count;
partially blocked classes keep the advice plus a warn line naming the
blocked wares. The per-ware fine print shows stock as `held / ceiling`.

Storage saturation flags any (station, cargo class) above
`STORAGE_FULL_PCT` = **80%** of built-module capacity and adds **Hours to
full**: `audit.hours_to_full(capacity, used, net_m3_h)` — remaining space
divided by the station's OWN net rate for that class, Σ over its wares of
(prod − cons) × ware volume from `_station_rates`. It returns `0.0` when
used ≥ capacity (rendered "full") and `None` when the net rate is ≤ 0
(rendered "—": not filling; external trade flows are deliberately NOT
counted, so a class fed only by purchases reads as not filling). Rows sort
soonest-to-fill first, non-filling last. This section subsumes the retired
"output piling up" table: a product stock that keeps growing is exactly a
class heading for full.

Constructions waiting for materials lists a Site and a Sector column. A
build plot has no name of its own, so the Site label is
`Likely {station name} (CODE)` for the first own station in the same
sector, falling back to `Build plot (CODE)` when the sector holds none;
the Sector comes from the build storage's `sector.macro`. A plot whose
offers are all at 0 units (or absent) gets the "site inactive" row ONLY if
`_remaining_construction` minus materials already delivered still leaves
something > 0.5 units — the remaining-materials estimate is computed first
and gates the whole site, so a finished-but-idle plot does not show up.

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
  "too unstable to be active" — save-specific census, B20 2026-07-24: 33
  of them across 30 sectors, up to 2 in one sector, so NOT one-per-sector
  as an earlier revision claimed — never script-activated); partners
  resolved by the connection-id ownership map. Direction: one arrow per
  `destination`-role link, drawn entry→exit — the role names the partner,
  so the enterable end is the one owning the `destination`-role connection
  (B4 re-derivation, 2026-07-24; the pre-B4 build had the one asymmetric
  arrow backwards). Links spoiler-dropped if either endpoint is
  undiscovered — see
  [../models/wormhole-connection-model.md](../models/wormhole-connection-model.md).
- Derelict-ship overlay (payload `derelicts`, default off): every
  `owner="ownerless"` ship component in a plotted sector (see
  [save-semantics.md](save-semantics.md) § Derelict ships), drawn at all zoom
  levels as amber (`#FF9F1C`) diamond-X markers — solid for a **bailed**
  derelict (`spawntime > 0`: it spawned mid-game and lost its crew, the kind
  worth flying out to claim), smaller dimmed hollow for a **pre-placed** one
  (`spawntime` 0/absent, the game-start hypothesis E-144). Records carry
  code, ship model (ref.ships `model` by macro, falling back to the macro for
  modded hulls), size (ref.ships `class`, falling back to the component
  class suffix), origin, spawntime and sector name; tooltip shows all of
  them (spawn time in game-hours), legend label counts bailed/total.
  Positions use the same shared per-sector normalization as gates, stations
  and vaults — the parser runs the station-style zone-offset walk for
  ownerless ships only (owned ships move constantly and stay position-less),
  so a snapshot taken before that change falls back to the hex centre.
  Spoiler-filtered like everything else (`knownto == "player"` only).
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
clamp(booster if the pair has one, else base, −1, 1) — the standing AS OF THE
SAVE, since the engine persists a booster at its current decayed value and the
booster *is* the standing, not an offset on the base (E-145; the earlier
additive `clamp(base + Σboosters)` is FALSIFIED, E-083). The page shows the raw
base and booster columns alongside; only `effective` composes them, and it
composes them in `frames.py` only — `viz/diplomacy.py` reads that column.

Two self-contained pages (map.py `_PAGE`+external-JS pattern,
`window.X4DIPLO`, `diplomacy_page.js` branches on `view`): Standings = a
DataTables table with diverging −30..+30 bars, rank band, discount, licence
count, treasury; Relations = a hand-SVG directional heatmap (diverging
red→grey→green by |uiv|/30, war/ally outlines, player row/col emphasized,
hover shows both directions). Relations are **stored per direction** —
which is why the heatmap is drawn directional — but in the analyzed save
every base pair is exactly reciprocal (0 of 486 pairs asymmetric, B20
re-check 2026-07-24; review X4 — an earlier revision claimed "NOT
symmetric" from an example that compared two *different* pairs,
argon→scaleplate vs antigone→scaleplate, which shows pair variance, not
asymmetry). An unlisted pair = 0.0 neutral, so the matrix comes from the
save alone (no extract-gamedata/reference CSV). The −30..+30 rank value is a fixed log
formula (`sign(r)·10·log10(|r|·1000)`, linear inside ±0.0032) kept as code
constants. NO spoiler handling — relations are global state, not
exploration-gated. Curated faction order/roster (`_ORDER`, real factions
only — excludes visitor###/civilian/ownerless).

## Weapon-mod dashboard (`viz/weaponmods.py` + `gamedata/weapons.py`/`weaponsim.py`)

The `gamedata-dashboard` subcommand: a static GAME-FILE analysis page (no
savegame involved), currently one tab comparing weapon mods per weapon at
optimal rolls. Fully self-contained HTML (inline CSS/vanilla JS, no
vendored libs). Simulation rules were validated in-game
(`tests/test_weaponsim.py` is the source of truth — review X17 corrected
this paragraph toward the tests): a reload mod always speeds fire up, in
whichever encoding the weapon stores — it multiplies a stored `reload
rate` and DIVIDES a stored `reload time` (S Plasma Cannon validation),
so the optimal roll is the range max either way; clip (`<ammunition>`)
reload time is never modified (cooling mods do nothing to it); cooling
happens between shots once `cooldelay` elapses — a fast weapon like the
EM Gun (0.71 s interval < 1.0 s cooldelay) never cools while firing, a
slow one like the Plasma Cannon does; the heat cycle is DISCRETE
(per-shot), which is why the EM Gun fires 29 shots per 10,000-heat bar
(the 29th tips it over; 28 intervals ≈ 20.0 s from cold), not the
continuous-rate 28.57/20.41 an earlier revision quoted; steady-state
cycle fires reenable→overheat. Weapon macros are deduped across DLCs in load order (timelines
re-issues terran weapons); `equipmentmods.xml` bonus blocks whose child
count fits `max` at chance 1.0 are forced (applied at least-bad value),
larger weighted pools are optional (detail-only).
