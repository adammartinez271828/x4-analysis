# Save-XML coverage inventory & extraction candidates

**Save analyzed:** `save_008.xml.gz` (2026-07-13, 58 MB gz, game v9.0 build 611726,
`modified="1"`, guid `8E0C8E37-…`, game time 36,853 s ≈ 10.2 h).
**Method:** one streaming `lxml.iterparse` pass (same discipline as `save/parser.py`)
counting every element by *path key* = tag stack relative to the nearest enclosing
`<component class=…>` (components are the recursive unit of the save), collecting
attribute-name frequencies and up to 3 sample attribute dicts per path.
Result: **9,221,265 elements, 2,311 distinct path keys**. Every claim below is backed
by sampled values from this save; targeted `zcat|grep` and filtered iterparse passes
pulled the example subtrees. Peak memory stayed in the tens of MB.

Current DB for this playthrough (`x4_8E0C8E37….sqlite`, 71 MB after multiple runs):
trade_tx 728, stock_event 173,577, log_entry 1,744, component 15,987, trade_offer 14,172.

---

## 1. Coverage inventory

"Captured" = lands in a SQLite table via `save/parser.py` + `db/store.py`.
Counts are element counts in this save.

### 1.1 Save/universe metadata

| Path | Count | Captured | Notes |
|---|---:|---|---|
| `info/game`, `info/save`, `info/player` | 3 | **yes** → `save` | guid, version, time, date, name, money, modified |
| `info/patches/patch` (+`history/`) | 18 | no | DLC/mod load list (`ws_3737446888` Habitat Capacity Boost, `ws_3566937504` Respectable Terran Crews) — provenance for mod-sensitive analyses |
| `universe/factions/faction` (132) with `relations/relation` (972), `relations/booster` (18), `licences/licence` (132), `moods/mood` (27), `discounts/booster` (5), `diplomacy/exclude`, `traderules/traderule` | ~1,400 | no | **Candidate #6** |
| `universe/blacklists/blacklist` | 2 | no | player blacklist definitions; referenced by ships (see 1.4) |
| `universe/jobs/job` (+`waiting`, `requested`) | ~3,700 | no | NPC job-system state; low analytics value |
| `universe/diplomacy/actions/action`, `operations/diplomacy/…` | ~30 | no | envoy/agent operations (DLC mini_02); tiny |
| `universe/physics/…`, `controltextures` | ~1,800 | no | engine state — skip |
| `stats/stat` | 103 | no | global playthrough counters — **candidate #9** |
| `missions/mission` (17), `missions/offer` (52) | ~600 | no | active missions + offers incl. rewards — honorable mention |
| `messages/entry` (32), `tickercache/entry` (100) | 132 | no | GalNet/notification history — honorable mention |
| `log/entry` | 1,998 | **yes** → `log_entry` | all attrs kept (incl. `raw_attrs`) |

### 1.2 economylog

| Entry type | Count | Captured | Notes |
|---|---:|---|---|
| `type="trade"` | 189,169 | **yes** → `trade_tx` / `stock_event` | two flavors handled; `price`/`max` of stock snapshots survive only inside `raw_attrs` JSON |
| `buyoffer` / `selloffer` | 294,870 / 120,126 | **no** | per-(owner,ware) offer snapshots **with `price` and `max`** — price history! |
| `consume` / `produce` | 114,748 / 88,579 | **no** | cumulative production/consumption counters |
| `construction` | 59,925 | **no** | wares consumed by construction |
| `collect` / `drop` | 24,598 / 13,611 | **no** | mining/salvage gathered; cargo dropped |
| `init`, `surplus`, `recycle`, `transfer`, `destruction`, `ownerchange`, `debug` | ~16,100 | **no** | |
| `economylog/removed/object` | (per save) | **yes** → `removed_object` | |

→ **Candidate #1**: ~790k dropped events per save, the single biggest gap.

### 1.3 Components that become universe rows

`cluster`/`sector`/`station`/`buildstorage`/`ship_*` → `component` table: **captured**
(id, class, macro, name, code, owner, knownto, contested, connection, spawntime,
cluster/sector ids, basename, parent). Attributes present in the save but dropped:
`state`, `cover`, `level`, `variation`, `attacker`, `attacktime`, `attackership`,
`description`, `nameindex`, `factionheadquarters`, `modulelevel`, `thruster`.
(`attacker`/`attacktime` = "under attack" signal — folded into candidate #7.)

Component classes never collected (not universe classes, not ships):

| Class | Count (components) | Notes |
|---|---:|---|
| `satellite` / `mine` / `resourceprobe` | 993 / 758 / present (`resourceprobe/hull` seen) | player + NPC deployables — honorable mention (map overlay) |
| `asteroid` (868), `gate` (323), `highway`, `adsign`, `destructible`, `object`, `room`, `zone`, … | ~6,000 | mostly scenery; gates already come from `gates.csv` |
| equipment classes nested in ships/stations: `turret` 114,024, `shieldgenerator` 98,298, `engine` 30,025, `weapon` 25,531, `missileturret` 10,415 | ~280k | mounted loadouts — **candidate #8** |

### 1.4 Sub-records of stations/ships

| Path (per 1.0 path-key) | Count | Captured | Notes |
|---|---:|---|---|
| `connections/connection[@connection=subordinates]` + follower `connected` | ~5k | **yes** → `fleet_edge` | |
| `subordinates/group` (`index`, **`assignmment`**, `protectedsector`) | 2,071 | **no** | commander-side group roles — **candidate #2** |
| `<subordinate group="N"/>` (flat, on follower) | 9,616 | **no** | follower→group index — **candidate #2** |
| `control/post` | ~27k | **yes** → `post` | |
| `workforce` | (per station) | **yes** → `workforce` | |
| `construction/sequence/entry`, `snapshot/entry`, buildstorage `buildtasks/inprogress/build/sequence/entry` + `upgrades/groups/{shields,turrets,engines}` | ~250k | **yes** → `module`, `module_upgrade`, built_refs | `upgrades/ammunition/unit` (14.9k) dropped |
| `people/person` (+`skills`, `npcseed`) | 259,698 | **partial** → `people` role counts | per-person `skills` (morale/piloting/…) and `macro` (race) dropped |
| `npc` components owner=player + `skills` | (93 ships' officers) | **yes** → `npc`, `npc_skill` | NPC `inventory/ware` (6,901), `blackboard` dropped |
| `cargo/ware` | ~13k | **yes** → `cargo` | |
| `trade/offers/**/trade` | 12,539 | **partial** → `trade_offer` | side/ware/amount/price kept; `desired`, `id`, `flags`, `restrictions@factions` (3,491) dropped |
| `trade/reservations/reservation` | 2,175 | **no** | committed in-flight trades — **candidate #3** |
| `trade/prices/reference/ware` | 6,053 | **no** | per-station reference buy/sell — **candidate #4** |
| `production/production` (cycle state) | 2,630 | **no** | **candidate #5** |
| `account` | 105 | **no** | object money accounts — **candidate #9** |
| `shields/group`, `…/hull` | 99,901 / 1,914 | **no** | damage state — **candidate #7** |
| `modification/{paint,ship,weapon,engine,shield}` | 13,533 | **no** | 11.9k are `paint`; real mods ~600 — part of #8 |
| `ammunition/available/item` | 72,511 | **no** | missiles/mines/drones aboard — part of #8 |
| `blacklists/blacklist` (`type`, `ref`) | 3,094 | **no** | per-ship blacklist assignment; honorable mention |
| `source` (`job`, `mission`, `commander`) | 36,626 | **no** | NPC job/mission provenance; honorable mention |
| `orders/order` | ~19k | **partial** → `ship_order` | `param` children (~390k), `syncpoint` dropped |
| `events/event` | 59,198 | no | mostly `updatetradeoffers`/`updateengineparameters` noise — skip |
| `supplies/wares/ware`, `units/unit` | ~2,100 | no | resupply reserves, drones under buildprocessor |
| `buildtasks/queue/build` (`faction`, `time`, `price`) | 202 | no | shipyard order queue w/ customer+price; honorable mention |
| `boost`, `gravidar`, `listeners`, `offset/position` etc. | ~1.6M | no | flight/engine state, geometry — skip |

### 1.5 Player component

| Path | Count | Captured | Notes |
|---|---:|---|---|
| `blueprints/blueprint` | 151 | no | **candidate #10** |
| `research/research` | 25 | no | **candidate #10** |
| `inventory/ware` | 102 | no | **candidate #9** |
| `memory/scan/item` (`component`, `level`) | 7,652 | no | scan level per known object; honorable mention |
| `discovered/sector/quadtree/**` | 64,825 | no | fog-of-war bitmap — skip |
| `known/entries`, `unlocks`, `platformtriggers`, `memory/subscriptions` | ~8k | no | minor |

### 1.6 Engine state (provably skippable)

| Group | Count | Verdict |
|---|---:|---|
| `//savegame/script/**` (script engine refs/vars) | 1,157,163 | skip |
| `//savegame/aidirector/**` | 996,302 | skip |
| `//savegame/md/**` (mission-director cues) | 809,425 | skip |
| `offset/position/rotation` under components | 1,403,798 | skip (see honorable mentions: in-sector maps) |
| `listeners/listener` | 222,067 | skip |

Together with economylog these account for ~4.6M of the 9.2M elements; the captured
record types cover most of the rest. The gaps listed above are the complete set of
plausibly-useful uncaptured data.

---

## 2. Ranked candidates

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

## 3. Cost summary within the single pass

Parse-time: all candidates ride the existing start/end dispatch; the only measurable
additions are #1 (~790k extra attrib dicts, est. +1–2 s on the ~18 s pass) and #8 if
captured unfiltered (~280k rows; filter to player-owned to make it negligible).
Everything else is <15k elements total.

Storage: #1 dominates (est. +100–250 MB per playthrough at full fidelity — consider
opt-in offer capture); #7/#8 are bounded by filtering to player/known objects; the
rest are KB-scale. All event-like tables (#1) must reuse the epoch/min-time merge to
stay idempotent; snapshot-like tables (#2–#10) are world-state, rebuilt per save like
`component`.
