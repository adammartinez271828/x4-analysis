# Feasibility study: future analytics tools

Status: **idea catalogue, nothing implemented.** Companion to
`player-view-plan.md`. Feasibility ratings are grounded in what the save and
game data are known to contain (see CLAUDE.md "Market tab data semantics"
for the hard-won parsing knowledge these build on).

Design principle (user-confirmed): prescriptive tools produce **ranked
recommendations whose scores decompose into visible factors** — a top-10
list where every score can be expanded into profit / distance / danger /
etc., with tunable weights. Never an opaque oracle.

Priority guidance (user-confirmed): all four themes appeal; cross-run
history is constrained by the user *not* wanting to run the analyzer
habitually — see the watch-mode idea (#10) which removes that constraint.

---

## A. Prescriptive advisors

### 1. Trade route finder — feasibility: HIGH ⭐ recommended first

"Buy ware W at station A for P₁, haul N units (M m³) through K gates, sell
at station B for P₂ → profit/trip, profit/hour, profit/m³."

- **Data:** open buy/sell offers with prices, amounts, station sectors (all
  already parsed for the Market tab). Sector adjacency graph from gates:
  220 known gate components exist in the save with sector ancestry;
  gate-pair connections also derivable from game files
  (`galaxy.xml` connections) for unrevealed links.
- **Work:** build the sector graph once; BFS distances; enumerate
  (sell-offer × buy-offer) pairs per ware; score = spread × min(amounts)
  constrained by a configurable cargo size, discounted by gate distance.
- **Factors exposed:** spread, volume ceiling, cargo trips, gate count,
  sector danger (from #8's threat index), counterparty faction.
- **Risks:** none structural; needs the player-view caveat (omniscient
  offers) eventually.

### 2. Station build advisor — feasibility: MEDIUM-HIGH ⭐ **IMPLEMENTED** (Build Advisor tab)

Score "build a W factory in sector S": market gap (Market tab metrics) ×
input availability nearby (sell offers + mining yields within R gates) ×
demand proximity (understocked buyers within R gates) × danger × workforce
availability (habitat food supply chains nearby).

- **Data:** every factor already computed or parsed; needs the sector graph
  from #1 and a scoring model.
- **Work:** mostly the scoring model + a per-sector detail view justifying
  each recommendation ("claytronics fab in Segaris: 30M build demand within
  3 gates, silicon at 152 Cr 1 gate away, 0 hostile events logged").
- **Risks:** recommendation quality is judgement-laden; mitigate with the
  decomposable-factors principle and tunable weights.

### 3. Blueprint ROI calculator — feasibility: HIGH

For each buildable production module: build cost (module ware build recipes
— already in recipes.csv) + blueprint price (game data) vs revenue at
*current live prices* (best open buy offers) → payback hours, ranked.

- **Data:** all present. Needs blueprint prices extracted (wares.xml has
  module ware prices; blueprint licence costs live in game data too).
- **Work:** small; a table on the Market tab or its own tab section.
- **Nuance:** revenue should offer both "average price" (conservative) and
  "current best offers" (opportunistic) columns.

### 4. Mining site advisor — feasibility: HIGH

Best sectors per minable ware: resource yield (parsed for the map) ×
distance to paying buyers (graph from #1) × danger × current competition
(NPC miner density per sector — countable from universe ships with
purpose="mine" per sector).

- **Data:** all present including competitor density, which is a nice
  differentiator ("high yield but 40 NPC miners already work it").

---

## B. Own-empire operations

### 5. Empire bottleneck audit — feasibility: HIGH ⭐ **IMPLEMENTED** (Audit tab)

One page listing everything wrong with YOUR assets:

- production stalled waiting for inputs (own stations' `<build>`/queue
  states and `insufficient` blocks — richest data in the save);
- output storage saturated → production choking (cargo vs capacity; may
  need storage-capacity extraction from module macros);
- idle ships (no orders / default orders only — order queues are in the
  save, currently unparsed);
- understaffed stations (workforce vs `workforce max` per module);
- ships without engineers, low-skill pilots on high-value ships (already
  parsed for df.ships).

### 6. Station P&L statements — feasibility: HIGH — **IMPLEMENTED** (Station P&L tab)

Per-station: revenue, input costs, net profit/h, trend; ROI ranking across
the empire. Extends the existing Trade History data (per-station trades are
already attributed); add module-based cost attribution for shared stations.
The cross-run cache already accumulates the needed history passively.

### 7. Fleet readiness report — feasibility: HIGH

Hull %, missing crew, engineer gaps, pilot skill distribution, equipment
tier audit (mk1 shame list — loadout components are in the save, currently
skipped), and ammo/missile/drone reserves vs capacity (the
`<supplies><wares>` blocks explicitly excluded from market stock are
exactly this data).

---

## C. Military / strategic

### 8. War dashboard + threat map — feasibility: MEDIUM-HIGH

- Hostile military mass per sector (universe ships × ship mass × owner
  relations — relations are in the save's faction data, unparsed);
- map overlay of Xenon pressure on border sectors;
- defence coverage: friendly defence platforms per border sector;
- station kills from the global log (all factions' losses, not just
  player's — `destroyed` entries exist for NPC stations too, worth
  verifying coverage).
- **Output:** a "front line report": sectors likely to flip, with the
  factors visible (hostile mass vs defence mass vs recent losses).

### 9. Loss heatmap — feasibility: HIGH (small)

Player ship losses on the map with killer attribution and time trend.
Mostly a presentation extension of the existing Destroyed table; danger
scores feed advisors #1/#2/#4.

---

## D. Cross-run history

### 10. Autosave watch mode — feasibility: MEDIUM ⭐ unlocks the theme

The user won't run the analyzer habitually — but X4 writes autosaves every
few minutes regardless. A `x4-analyzer --watch` daemon (or scheduled task)
that notices new autosaves and silently appends compact snapshots (prices,
stocks, ownership, player net worth) to the existing cache infrastructure
would build history with **zero user habit change**. Parsing is already
fast enough (~18 s) to run per autosave.

- **Risks:** long-running process UX; snapshot compaction so years of play
  stay small; autosave cadence varies.

### 11. History charts — feasibility: HIGH *once #10 exists*

Price history per ware, sector ownership timeline / war-progress animation,
player net-worth curve, market Fill %/backlog trends. All are simple charts
over #10's snapshots; without #10 they degrade to whatever sparse manual
runs exist (design must tolerate gaps).

### 12. Supply-chain Sankey — feasibility: MEDIUM (single-save, bonus)

Ware flow diagram (ore → refined → components → ships) per faction from the
capacity/delivery data; plotly has native sankey support. The work is
layout readability, not data.

---

## Suggested build order

1. **Sector graph** (shared infrastructure: gates → distances) — enables
   #1, #2, #4, #8. **DONE** (`sectorgraph.py` + `gates.csv` from galaxy.xml).
2. **#1 Trade route finder** — highest immediate decision value, proves the
   graph.
3. **#5 Bottleneck audit** — best value/effort, no new infrastructure.
4. **#2 Build advisor** — the flagship, once #1's graph and the danger
   index from #9 exist.
5. **#9 → #8** military layer.
6. **#10 watch mode** when history features get pulled.

#3, #4, #7 are independent small wins to slot anywhere.

---

## E. Save-data extraction candidates (coverage-sweep backlog)

Folded in from the retired save-XML coverage inventory (2026-07-13, one
streaming sweep of `save_008` — 9.2 M elements, 2,311 distinct path keys;
the counts below are from that save). The structural documentation that
accompanied it now lives in `../reference/savegame-structure.md`; what
remains here is the backlog: save content **not yet extracted**, ranked by
analytics value ÷ (parse + storage cost). Candidate numbers (#1–#10) are
local to this section — they are unrelated to the idea numbers above.

Shipped since the sweep: candidate #6 (faction relations, boosters,
discounts, licences, accounts → the Standings/Relations views; moods and
diplomacy excludes remain uncaptured), and the station-level `ammunition`
part of #8 (the station-munition census). The rest is open.

Ranking = analytics value for existing tabs ÷ (parse + storage cost). All fit the
existing single pass: each is either a new `elif tag == …` branch keyed off
`tag_stack`/`comp_stack` (both already maintained), or a widening of an existing
branch. None needs a second pass.

### #1 Full economylog event stream (produce / consume / buyoffer / selloffer / collect / construction / …)

- **What:** the parser keeps only `type="trade"` (189k of 979k entries). The other
  ~790k entries are per-(owner, ware) snapshots of cumulative counters, in the same
  two-point encoding as the stock events: `v` at `time`, plus a second point `v2` at
  `t2`. Offer entries additionally carry `price` and `max` (target level).
- **Evidence (this save):**
  - `<log time="62.043" type="produce" owner="[0x206445f]" ware="energycells" v="829151" t2="3603.699" v2="926267"/>`
  - `<log time="0" type="buyoffer" owner="[0x202cfe9]" ware="advancedcomposites" price="53900" v="1528" max="3256" t2="571.576" v2="1689"/>`
  - `<log time="149.974" type="collect" owner="[0x201c5d2]" ware="ore" v="603"/>`
  - counts: buyoffer 294,870 · selloffer 120,126 · consume 114,748 · produce 88,579 · construction 59,925 · collect 24,598 · drop 13,611 · init 7,196 · surplus 5,382 · recycle 2,918 · transfer 446 · destruction 165 · ownerchange 7
- **Table sketch:** `econ_event(time REAL, type TEXT, owner_id TEXT, ware TEXT, v REAL, v2 REAL, t2 REAL, price_cr REAL, max REAL, owner_faction/code/name, epoch)` — merged with the same min-time-cutoff/epoch machinery as `stock_event`, per type.
- **Consumers:** Market tab gets *real* price history (buyoffer/selloffer price over
  time — today Cr/h is valued at static average price) and real produce/consume rates
  (today inferred from stock-delta `dv`); Raw-supply audit gets `collect` = measured
  mining yields per miner; Station P&L gets `construction` spend and `destruction`
  losses.
- **Cost:** parse — remove the `type=="trade"` filter in the existing branch and route
  by type (~+1–2 s for the extra dict copies). Storage — the big one: ~5× today's
  event rows; DB is 71 MB at 174k stock events, so expect roughly +100–250 MB per
  playthrough epoch. Mitigations: skip `time="0"` seeds, make buy/sell-offer capture
  opt-in or player/known-only, or store offers downsampled.
- **Caveat:** exact counter semantics (cumulative vs windowed, meaning of `t2/v2`)
  must be validated against in-game numbers before charting — same reverse-engineering
  discipline as the Market-tab `dv` work.

### #2 Subordinate group assignments (the `assignmment` attribute)

- **What:** the commander lists `<subordinates><group index="N" assignmment="mining|trade|defence|attack|supplyfleet|positiondefence|assist"/>`;
  each follower ship carries a flat `<subordinate group="N"/>`. Joining the existing
  `fleet_edge` with these two gives every subordinate's *role*. (CLAUDE.md's warning
  about flat `<subordinate>` elements refers to the job system's `jobs/job/waiting/subordinate`;
  the per-ship `<subordinate group>` element is the player-relevant group index.)
- **Evidence:** player station `MXH-411 [0x2035b27]`: `group index=2 assignmment="mining"`,
  `group index=3 assignmment="trade"`; follower `LEI-086 [0x204f810]` has
  `<subordinate group="1"/>`. Save-wide tally: defence 1,535 · mining 234 · trade 137 ·
  attack 119 · supplyfleet 21 · positiondefence 14 · assist 1. `ship_l` groups also
  carry `protectedsector`.
- **Counts:** 2,071 `group` defs + 9,616 follower elements.
- **Table sketch:** `subordinate_group(commander_id, idx INT, assignment TEXT, protected_sector TEXT)`; add `sub_group INT` to `component` (or a tiny `subordinate_of(ship_id, group_idx)` table).
- **Consumers:** Fleet tab (role labels on the hierarchy), Raw-supply audit (miners
  *assigned* vs miners *measured* — today the pool is inferred from trade rows only),
  Station P&L attribution sanity.
- **Cost:** trivial — one start-event branch for `subordinate` (like `person`), one
  end-event branch for `group` under a `subordinates` parent; ~12k rows.

### #3 Trade reservations (in-flight committed trades)

- **What:** `<trade><reservations><reservation …>` on stations: a signed trade that
  hasn't executed yet — reserver, partner, buyer/seller, ware, amount, `desired`,
  price, `escrow`/`transferred` flags.
- **Evidence:** `{'reserver': '[0x207d9c4]', 'id': '[0x84bbf]', 'buyer': '[0x2089a49]', 'ware': 'quantumtubes', 'price': '32500', 'amount': '61', 'desired': '61', 'flags': 'sellermoneyvirtual|buyermoneyvirtual|…|fixedprice'}` (price in cents like offers).
- **Count:** 2,175.
- **Table sketch:** `trade_reservation(host_id, res_id, side, partner_id, reserver_id, ware, amount, desired, price_cr, escrow, transferred, flags)`.
- **Consumers:** Audit input-starvation cards ("shortfall 4,000/h — but 3 deliveries
  totalling 2,400 already en route"), Market Satisfy(h), Build Advisor demand (demand
  already spoken-for is weaker demand).
- **Cost:** trivial — `elif tag == "reservation"` with `_nearest_host()`; 2k rows.

### #4 Station reference prices

- **What:** `<trade><prices><reference><ware ware=… buy=… sell=…/>` — the station's
  current reference buy/sell price per ware (0 = side disabled).
- **Evidence:** NPC station: `hullparts buy="276" sell="0"`, `energycells buy="21"`;
  player station `JQR-498`: `energycells buy="10"`. Values are whole credits (offers
  are cents — unit mismatch to respect; energycells avg ≈ 16 Cr).
- **Count:** 6,053 ware rows (~all trading stations incl. player trade ships).
- **Table sketch:** `station_price(object_id, ware, buy_cr REAL, sell_cr REAL)`.
- **Consumers:** Market tab (configured price vs open offers vs average), Build
  Advisor competition factor (who will undercut you), P&L (is a loss-making station
  simply mispriced).
- **Cost:** trivial — `ware` end-event with parent `reference`; guard against the
  other `ware` parents already dispatched.

### #5 Production-module cycle state

- **What:** each `production` module component carries `operationaltime` and a child
  `<production start=… end=… state=… cycle=… paused=…/>` — what the module is doing
  *right now* and when the batch lands.
- **Evidence:** `{'start': '35862.957', 'end': '37662.957', 'item': '0', 'cycle': '0', 'state': 'producing'}` (a 1,800 s cycle ending ~800 s after save time).
- **Count:** 2,630 (one per production module in the galaxy).
- **Table sketch:** `production_state(host_id, module_macro, start REAL, end REAL, state TEXT, paused REAL)` — host + macro from `comp_stack`.
- **Consumers:** Audit tab at module granularity: a "starved" station today is
  diagnosed from stock flows; `state != "producing"` / `paused` is the direct signal,
  and `end` gives next-output ETA. Market capacity utilization (capacity × fraction
  of modules actually producing).
- **Cost:** trivial — `elif tag == "production"` when `comp_stack[-1][0] == "production"`.

### #6 Faction relations, licences, boosters, moods, discounts

- **What:** the `universe/factions` block: pairwise `relation` values, temporary
  `booster` relations (with timestamps), per-faction `licences` (incl. everything the
  *player* holds), war/economy `moods`, price `discounts`, diplomacy `exclude`s.
- **Evidence:** player→argon booster `relation="0.0695385" time="36350.206"`; player
  licences incl. `militaryship: alliance pioneers terran argon antigone`; argon mood
  `avarice=high`; discounts `booster faction="player" amount="0.05"`; player↔terran
  relation `-2.32831e-10` (a hair below neutral).
- **Counts:** 972 relations + 18 boosters + 132 licences + 27 moods + 5 discounts across 132 factions.
- **Table sketch:** `faction_relation(faction, other, value REAL, locked)`, `faction_booster(faction, other, value, time)`, `faction_licence(faction, type, factions TEXT)`, `faction_mood(faction, type, level)`.
- **Consumers:** Map tab hostility overlay from *this save's* relations (mods shift
  them) instead of static faction reference; Build Advisor hostile-distance factor;
  a small Diplomacy widget (licences owned, relation trend across runs — relations
  merged per save give a time series).
- **Cost:** trivial volume; needs a "inside `universe/factions`, `comp_stack` empty"
  guard because `relations/booster` also appears under `npc`/`computer` components
  (198 + 133 seen).

### #7 Hull & shield damage state (+ under-attack attributes)

- **What:** any component below max hull carries `<hull value=… min=…/>`; charged
  shield groups carry `<shields><group group=… value=… time=…/>`. Components under
  fire carry `attacker`/`attacktime`/`attackership` attributes (currently dropped).
- **Evidence:** player ship `FII-436` hull `23333.205`; player station `MXH-411`
  production module hull `60000`; `PIE-222` shield `group_engines value="14900.518" time="33504.382"`;
  station `XNN-241` attrs `attacker="[0x2088dda]" attacktime="35029.075"`.
- **Counts:** 1,914 hull elements; 99,901 shield-group elements (most are
  context-only; `value` present when meaningful); attack attrs ride on components
  already visited.
- **Table sketch:** `damage(object_id, part_class TEXT, kind TEXT 'hull'|'shield', value REAL, min REAL, time REAL)`; plus `attacker_id`, `attack_time` columns on `component`.
- **Consumers:** Fleet tab "needs repair" list; Audit (damaged modules on player
  stations); Map ("under attack" markers with attacker faction). Caveat: hull *max*
  isn't in the save — percentages need macro reference data not currently in
  ships.csv/modcaps.csv.
- **Cost:** small — two end-event branches resolving the owning object via
  `_nearest_host()`; store player-owned (or `knownto`) only to keep rows down.

### #8 Mounted equipment loadouts (+ mods, ammunition)

- **What:** equipment is nested component elements inside ships: `engine`,
  `shieldgenerator`, `weapon`, `turret`, `missileturret` with `macro` — the *actual*
  fitted loadout (save-time truth, vs `module_upgrade` which is planned station
  loadouts). Plus `modification/{ship,weapon,engine,shield}` (installed mods with
  stat deltas) and `ammunition/available/item` (missiles/mines/drones aboard).
- **Evidence:** `<component class="engine" macro="engine_arg_m_combat_01_mk2_macro" connection="con_engine_01" id="[0x20903d2]">`,
  `<component class="weapon" macro="weapon_gen_m_laser_01_mk2_macro" … ammunition="4">`;
  mod: `{'ware': 'mod_ship_radarcloak_01_mk3', 'radarrange': '1.2', 'radarcloak': '-0.8'}`;
  ammo: `{'macro': 'weapon_gen_mine_01_macro', 'amount': '9'}`.
- **Counts:** engines 30,025 · weapons 25,531 · shieldgens 98,298 · turrets 124,439
  galaxy-wide; player-only is ~93 ships → a few hundred rows. Mods 13,533 (11,879 are
  paint), ammo 72,511.
- **Table sketch:** `equipment(object_id, clazz TEXT, macro TEXT)`; optional `equipment_mod(object_id, clazz, ware, attrs_json)`, `ammo(object_id, macro, amount)`.
- **Consumers:** Fleet tab loadout column + real travel-speed estimate (engine macro ×
  ship drag — the gamedata recipe already documented in memory), resupply planning
  (ammo), combat-strength scoring for the Audit's hostile-distance context.
- **Cost:** moderate if unfiltered (280k rows) — recommend capturing only when the
  nearest ship ancestor is player-owned (owner is on `comp_stack` entry push; needs
  the stack to also track owner). Handler is a start-event branch like the existing
  component push.

### #9 Money accounts, global stats, player inventory

- **What:** (a) `<account id=… amount=… own=…/>` on objects — stations with `own="1"`
  hold their operating budget; ships without one mirror the faction account;
  (b) `stats/stat` — 103 lifetime counters; (c) `component[player]/inventory/ware` —
  the player's personal inventory.
- **Evidence:** station `[0x258]` account `amount="1148" own="1"`; every player ship
  shows the faction account `[0x24c] amount="14858712"` (== `info/player@money`, so
  whole credits, unlike cent-priced trades); stats: `trades_executed=935`,
  `trade_value=89999704`, `ships_owned=93`, `trade_rank=15`, `fight_rank=14`;
  inventory: `inv_fluxcapacitor ×14`.
- **Counts:** 105 accounts + 103 stats + 102 inventory wares.
- **Table sketch:** `account(object_id, account_id, amount_cr, own)`; `stat(save_time REAL, id TEXT, value REAL)` (keep per-save history → playthrough time series across runs); `player_inventory(ware, amount)`.
- **Consumers:** Station P&L (budget vs earnings — a station bleeding its budget is
  the P&L headline), dashboard header (net worth, ranks), a progression sparkline
  from per-save stats history.
- **Cost:** trivial on all three.

### #10 Player blueprints & research

- **What:** `component[player]/blueprints/blueprint ware=…` (owned blueprints, incl.
  module/ship/equipment/paint wares) and `research/research ware=… method=…`
  (completed research).
- **Evidence:** `research_teleportation`, `research_module_venture`,
  `research_mod_shield_pre`; blueprints incl. `paintmod_0006` … (151 total).
- **Counts:** 151 + 25.
- **Table sketch:** `blueprint(ware TEXT)`, `research(ware TEXT, method TEXT)`.
- **Consumers:** Build Advisor — flag rows whose production module blueprint the
  player doesn't own (today it scores wares the player can't build); research gaps
  as an Audit card. Mod-flag: unknown `ws_*` blueprint wares must fall back to the
  ware id (existing defensive-join convention).
- **Cost:** trivial — two end-event branches guarded by `comp_stack` top being the
  `player` component.

### Honorable mentions (verified present, below the cut)

- **Missions & offers** (17 + 52): names, factions, `reward`/`rewardtext`, briefing
  objectives — e.g. plot "Return of the Hyperion". A Missions table is cheap but
  read-only info the game UI already shows well.
- **Ship `source` provenance** (36,626): `job=`, `mission=` — separates job-spawned
  NPC traffic from mission ships in universe views.
- **Per-ship blacklist refs** (3,094 `blacklists/blacklist type/ref`) + the 2
  universe blacklist definitions — which ships obey "Hostile Sector Travel Ban".
- **Shipyard order queue** (`buildtasks/queue/build`, 202, with `faction`, `time`,
  and sometimes `price`): who is buying ships where — NPC shipbuilding demand.
- **Player scan levels** (`memory/scan/item`, 7,652): scanned vs unscanned stations
  for a Map overlay.
- **Per-person crew skills** (115,279 `skills` elements galaxy-wide): today only
  role *counts* are stored; aggregating player crews' skill distribution would
  sharpen the Audit staffing card without an NPC-per-row explosion.
- **Deployables** (`satellite` 993, `mine` 758, `resourceprobe` present): sensor
  coverage overlay for the Map tab.
- **Mod/patch list** (`info/patches`, 18): store once per save for provenance of
  mod-skewed data.
- **Object positions** (`offset/position`, 1.4M): would enable in-sector detail
  maps, but is the one candidate that meaningfully raises parse cost; skip unless a
  sector-map feature is planned (then capture for universe-class components only,
  ~16k rows).

---

### Cost summary within the single pass

Parse-time: all candidates ride the existing start/end dispatch; the only measurable
additions are #1 (~790k extra attrib dicts, est. +1–2 s on the ~18 s pass) and #8 if
captured unfiltered (~280k rows; filter to player-owned to make it negligible).
Everything else is <15k elements total.

Storage: #1 dominates (est. +100–250 MB per playthrough at full fidelity — consider
opt-in offer capture); #7/#8 are bounded by filtering to player/known objects; the
rest are KB-scale. All event-like tables (#1) must reuse the epoch/min-time merge to
stay idempotent; snapshot-like tables (#2–#10) are world-state, rebuilt per save like
`component`.
