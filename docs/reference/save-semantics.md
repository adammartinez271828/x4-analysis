# Save-data semantics: what the numbers mean

Reverse-engineered *meanings* — one level above raw structure
([savegame-structure.md](savegame-structure.md)) and storage
([db-schema.md](db-schema.md)). Everything here was validated against this
project's real playthroughs; claims are separated into confirmed vs
hypothesis per the project convention, and the game-version provenance
(v9.0, mostly ported/upgraded from a v5.10-era R implementation) is noted
where it still matters.

## v9 save behavior (and where it diverged from v5.10)

- **Resource areas**: v9 stores `<area yieldid="sphere_large_ore_high_slow"
  yield="N">`; the ware is parsed out of the yieldid and "recharge"
  semantics became summed yield. (v5.10 had per-ware `recharge` attributes;
  the R script kept a resource cache — there is consequently **no resource
  cache** anymore.) Depletion/respawn behavior:
  [../models/resource-depletion-model.md](../models/resource-depletion-model.md).
- **The economylog is four typed ledgers**, keyed by the wrapper
  `<entries type="cargo|tradeoffer|trade|money">` — a `<log>`'s own
  `type` attr names the mutation cause, not the record type. Trade-block
  rows are real transactions (+ player-internal transfers); cargo-block
  `type="trade"` rows are stock snapshots (see Market semantics below);
  money-block rows are the player's money ledger (`v` in cents,
  `tradeentry` = ordinal into the trade ledger). Full model:
  savegame-structure.md § `<economylog>`.
- **`ship_xs`** is a component class (drones, pods), mapped to size XS and
  excluded from mass plots.
- **Fleet hierarchy**: a follower's `<connected connection="[X]">` ↔ the
  commander's `<connection connection="subordinates" id="[X]">`. The flat
  `<subordinate>` elements in saves are the NPC job system — NOT player
  fleets. (Structure: savegame-structure.md § Fleet hierarchy.)
- **Log-text parsers** (wording status per the 2026-07-24 harvest of both
  playthroughs' archived history): destroyed-object parsing uses the v9
  form — title `<name> (<CODE>) was destroyed.`, text
  `Location:`/`Commander:`/`Destroyed by:` lines — verified against all
  323 archived events (the earlier "no such events in this playthrough"
  claim conflated regex mismatch with absence; the events were there in
  the new wording all along). Resupply and pirate/police are v9-verified.
  Ship construction/repair and surplus-transfer have **zero archived
  instances** anywhere, so their v5.10-ported wording remains
  unverifiable — if those dashboards stay empty on a save that should
  have them, check the actual log text first.
- **Faction short codes** come from game data; player is special-cased to
  `PLA`, ownerless to `NIL`, unknown/visitor factions bucket to `OTH`.
  Colours keep the R palette for legacy factions, game colours for new
  ones (`gamedata/refdata.py`).
- **Subordinate→commander trade attribution** (R's "proxy" logic) uses the
  fleet hierarchy **at save time** — the save has no historical
  assignments, so old trades can show under a commander the ship didn't
  have yet. The Trade History tab therefore tags such rows ("Executed by")
  and has a toggle to disable the redirect; keep that pattern in any new
  per-object view (Conventions). (Fun fact: the save's group-assignment
  attribute is spelled `assignmment`.)

## Identity: nothing in the save is a GUID

None of the game's own fields identifies a ship/station across sessions:
runtime ids (`[0x..]`) remap on every load, names change on rename, owners
on capture, and codes (`ABC-123`) are recycled after death (measured: 163
recycles in 21 game-minutes of NPC churn). Live code collisions exist and
are not limited to cross-faction reuse: a code can be held simultaneously
by objects of different classes (RYJ-686 is at once a xenon corvette and a
xenon lasertower), and CONFIRMED even by two same-faction same-class ships
(save_001 holds two live terran `ship_ter_s_fighter_01_a` both coded
XPU-790 — verified as two physical components in the save XML). The
**entity registry** (db-schema.md § entity) mints surrogate `entity_id`s
from the evidence (code+class = slot, spawntime = generation,
capture/rename tracked in `entity_event`); trade rows carry `*_entity`
columns resolved at merge time. Key cross-run analysis on entity ids where
available; a code fallback needs at least the full (code, class) slot and
even then is only a heuristic — same-slot collisions among
simultaneously-alive same-faction objects are real. Names
are display-only, never keys: `frames` re-resolves tradelog display names
(entity name first, then per-code current-save/latest-history) so renamed
objects don't split in per-object views.

A practical corollary: a DB snapshot's runtime ids do NOT match a
*different* save file on disk — cross-referencing raw XML against DB rows
only works against the same save that produced them.

## Market data semantics (all reverse-engineered, validated in-game)

- The cargo-ledger `<log type="trade" owner ware v>` events record the
  station's **stock level after each trade**, NOT a trade amount —
  traded volume must be derived from positive deltas between consecutive
  snapshots per (owner, ware) (`frames.global_trades["dv"]`,
  `v_stock_delta`). Summing `v` directly overcounts ~40×. An absent `v`
  means stock 0, not unknown (CONFIRMED against same-save `<cargo>`,
  2,591/2,591 pairs).
- Consumption capacity = module recipe inputs + population needs.
  Workforce upkeep is the game's per-race `workunit_busy` recipes in
  wares.xml (200 workers consume e.g. 75 foodrations + 45 medicalsupplies
  per 600 s). DLC adds race methods (terran/boron/split) via **diff patches
  inside existing wares** — recipe extraction must scan
  `<add sel="…ware[@id=…]">` blocks, not just `<ware>` elements (missing
  this overcounted Terran energy production 3.5×).
- Build demand = the build storages' open **buy offers** (`<trade buyer=
  ware= amount=>` under `<offers>`). The `<insufficient>`/`<shortage>`
  amounts under `<build><resources>` are NOT per-ware quantities (in-game
  cross-checks disproved them — wrong amounts AND wares the build doesn't
  need); `build_resources` is still parsed but must not be used for
  demand. New-station constructions sit on **free-floating build storages
  with no station ancestor** — don't require an object ancestor when
  collecting.
- **Station buy offers split into distinguishable demand classes** (2026-07,
  CONFIRMED sweep-wide on save_007 + save_006,
  [../reports/supply-offer-discriminator.md](../reports/supply-offer-discriminator.md)):
  *production inputs* (plain offers), *construction* (build-storage
  hosts), *ship building* (wharf/shipyard hosts, plain), and
  *self-supply* — inputs for the station's own drone/munition builds,
  marked `flags="supplies|…"` (the trade menu's "box" icon). All 1,140
  flagged offers in save_007 are station-hosted buys of supply-recipe
  inputs; a station can hold a flagged and an unflagged buy for the same
  ware simultaneously. On flagged buys `desired` = the outstanding input
  need (exact against ABR-398's orders × terran drone recipe). Consumers
  measuring production demand must exclude `supplies`-flagged offers
  (`analysis/storage.py` does since v18; the market/advisor widgets still
  count them — known conflation, small: 1,140 of 15,418 offers).
- Construction-plan estimating (Audit tab, for sites with no funded
  orders): the plan lives on the build storage under
  `<queue><build type="expand"><sequence><entry>`; an existing station's
  own `<construction><sequence>` repeats the SAME entry ids, so dedupe by
  entry id. A built module's component carries `construction="[entryid]"` —
  but `state="construction"` means still building and its materials still
  count (treating it as built made estimates come in low by exactly one
  module's recipe). Estimate = Σ default-method recipes of unbuilt entries
  (module ware found via wares.csv `component` == macro) + loadout
  equipment from `<shields>/<turrets>/<engines>` groups in entries, minus
  wares already in site cargo. Validated within ~1% (WJL-290 claytronics
  exact) against in-game "required" figures, which are gross of delivered
  cargo and pro-rate partially built modules.
- Understocked = buyers (open `<trade buyer= amount=>` offers under
  `<offers>`, plus build hosts) holding < 25% of target level (stock +
  wanted). Fill % = buyer-side Σheld/Σ(held+wanted); Satisfy (h) =
  (buy+build demand)/production surplus, with a ≥gap/deliveries fallback
  when there is no surplus.
- Capacity excludes workforce production bonuses; Cr/h values volume at
  average game price (universe events carry no prices).

## Ware pricing model

Collaborative reverse-engineering (2026-07); CONFIRMED unless flagged.
Storage allocation — the sibling model — is implemented
(`analysis/storage.py`, db-schema.md § station_storage); pricing itself is
knowledge, not yet a feature.

- **Layer 1 — reference band.** Each ware has min/avg/max in
  `libraries/wares.xml` (energy cells 10/16/22). Bands come from base+DLC
  only — a modded save's mods are NOT diff-merged into the committed CSVs,
  so treat as approximate; floors verified against offers, but buy-side
  ceilings can exceed max.
- **Layer 2 — economy price** (the value in the save's sell offers), a
  linear supply curve:
  `economy_price = max − (max−min) × (stock − pending) / target_level`.
  Linear confirmed across 192 energy sell offers; exact on clean solar
  plants. *Pending* = committed outbound sales, summed from
  `<trade partner= ware= amount=>` under `<order>` containers (seller =
  `partner` when `buyer` is present) — verified exact in-game.
  *Target_level* is NOT stored — it is computed from throughput. An
  early single-station fit read it as a universal
  `≈ 6.105 h × throughput` constant; the validated model
  (`analysis/storage.py`, cross-checked against GDR-378 / PEJ-489 /
  UBX-812 over all three transport pools — review X15) has **no
  universal hour constant**: the hours factor `T` is **per station and
  per transport pool** — the pool's capacity net of food buffers,
  divided across the pool's production wares so each holds an equal
  number of hours (`T = (pool_capacity − Σ food_volume) /
  Σ(throughput × volume)`), with workforce food fixed at
  `FOOD_HOURS = 4.0` h of consumption. Throughput must be
  workforce-ADJUSTED — using base recipe rates is the classic error.
  Workforce bonus: `actual_rate = base × (1 + staffing_ratio × recipe
  work_effect)`, per-recipe, not per-station (output only; inputs stay
  at base).
- **Layer 3 — player-facing price** = `economy_price × (1 − tier% −
  event%)`. Reputation tier discounts: Known Associate 5% (relation
  ≥0.01), Prized Investor 15% (≥0.1), Partnership Agreement 25% (≥1.0);
  the UI shows the discount as a % of AVG, which makes the same tier look
  variable across stations. Per-station economy events add temporary
  `<modifier type="discount">` records.
- **Layer 4 — buy side: NOT modeled** (open gap). Consumers price off
  need, not fill, and run above the band ceiling.
- **Layer 5 — player-owned stations** use manual thresholds — off-model by
  design. The persisted inputs are now readable (v23): `price_setting`
  (kind `reference` = the configured reference price, near-universal;
  kind `override` = a hard per-ware price override, 6 hosts) and
  `ware_limit`, the station-UI per-ware limits — `max` (storage
  allocation), `buy` (buy up to this stock level) and `sell` (keep this
  much, sell the excess). The last two are arithmetically exact against
  live offers: on MXH-411, buy limit 739,800 − stock 488,215 = the offer's
  251,585, and stock − sell limit reproduces all three sell offers to the
  unit (savegame-structure.md § Stations).
- **Layer 6 — locked trade-station wares** (validated in-game 2026-07-27):
  wares in a trade station's / pirate base's `lockavgprice` whitelist
  (`station_trade_setting`, v20) are pegged at band average — sell = avg
  exactly (588/588 offers in save_008, zero variance), buy = avg − 1 Cr —
  regardless of stock; the supply curve does not apply. Layer-3 discounts
  still stack on top (EBT-957 microlattice: 46.75 = 50 × (1 − 2.0% − 4.5%)),
  so locked wares stay arbitrage-able with reputation. Their *unlocked*
  wares at the same stations price off need as usual (Layer 4), and so do
  `supplies`-flagged self-supply buys even ON locked wares (all 7 in
  save_008 at 1.105–1.222×avg, beside the locked regular pair — the v18
  discriminator composing with the lock; zero counterexamples).
- **Deployables** (satellites/mines/…) are not stocked; a facility builds
  them on demand at
  `base_price × (Σ recipe·E / Σ recipe·band_avg) × M` — and **no
  reputation discount** (confirmed twice). Revised 2026-07-27
  (six-station, 9-deployable study on save_008; the linear recipe model
  reproduces all quotes at 0.16–2.9% rms per station):
  - **M is `<trade><prices buildpricefactor>` in the save — CONFIRMED**
    (all four cross-station ratio constraints reproduced to ≤0.30% with
    zero free parameters; `build_price_factor` table, v19). It is the
    engine's price variation (`parameters.xml <building><prices>
    <variation min="0.9" max="1.15"/>`), piles at the clamp bounds
    (50 of 67 NPC stations), and **drifts** (12 of 67 changed between
    save_006 and save_008) — read it per save, never calibrate it once.
    The old "M ≈ wharf 1.15 / shipyard 1.067 / dock 0.90 type constants"
    were a sampling coincidence (a shipyard at 0.9 exists), and the old
    "M is unstable" anomaly was E varying, not M. Both of those routes —
    per-station-type constants and calibrating M once per station — are
    **closed**: use the per-save `build_price_factor` value. Player yards store the
    price slider here instead (up to 1.5, the `<factor>` bound).
  - **E — the per-ware valuation vector — is the open gap.** It is NOT
    persisted: not the station's own storage-curve prices, posted buy
    prices, or `<prices><reference>`; not band averages (one station
    matched exactly, others ±18%/ware); not offer-book or executed-trade
    averages at any scope (global/faction/cluster/sector, all >5%
    spread vs the required <1%). Stations share E vectors across sectors
    and factions (three stations to 0.1%) while a co-sectored pair
    differs — scope is provably not geographic or factional. NPC trade
    subscriptions do not exist in the save (player-only concept), so E
    is engine-runtime state; with E fitted from a handful of quotes,
    every other deployable at that station predicts to ~1–3%.

## Station drone/unit pool

Station drones (defence/repair/transport/build/mining) + police craft
share ONE pool — the engine property `units.maxcount`, no per-type caps
(confirmed in-game). Actual counts live in the station's own
`<ammunition><available>` block (which also holds turret munitions and
deployables — separate inventories, flagged `is_unit=0` in the census).
Capacity formula: `cap = Σ module_cap.unit_storage (dock/pier/build/
defence modules) + 10 × built production modules` — the `+10/production`
term is FIT from a single data point (MXH-411: floor 40 vs true cap
310), so only the readable floor (Σ `unit_storage`) is persisted
(`capacity_floor`). The floor is validated in-game on ABR-398 40,
EBT-957 92, QJI-262 220; MXH-411's 310 is the fit's source, **not** an
independent validation of the production term (review X19 — an earlier
revision listed it under "validated", which was circular; the term
remains a one-point hypothesis, matching tests/test_drones.py's
framing). **Desired levels**: the earlier claim that they are "not
persisted anywhere" was wrong — `$config_supply_*` was the wrong needle.
A station's `<supplies><orders>` block persists its drone build orders
by product ware, and the evidence says it IS the build target: in
save_007, 37/40 order rows across 21 stations exactly equal the
station's current drone count (zero exceed it), the 3 short rows are
ABR-398 mid-gather, and ABR-398's orders sum (50) matches its in-game
build target. Reinforced by the v22 import of save_009: five full, idle player
stations carry order rows exactly equal to their drone counts — an
*outstanding*-orders reading would put those at 0. Caveat: only ~21 of
the universe's stations carry the block, so absence ≠ no target; whether
the block survives a target change on a full station is a play-checklist
item
([../reports/supply-offer-discriminator.md](../reports/supply-offer-discriminator.md)).
The missing *inputs* for those orders surface as `supplies`-flagged buy
offers with exact recipe math (Market data above), and inputs already
set aside sit in `<supplies><wares>`. Both are parsed since v22
(`station_supply`, `v_station_supply`; stations/build storages only —
a ship's identical block is its own ammo reserve). Tables and views:
db-schema.md § station_munition, § station_supply; `tests/test_drones.py` carries the validation
numbers.

## Build method: which recipe variant a station builds with

**CONFIRMED 2026-07-27** (player-reported UI setting + save/game-file
cross-check; closes the old "does build method follow module race or
faction?" question).

Wares with several `recipes.csv` methods (drones, ships, equipment,
deployables — e.g. `ship_gen_xs_buildingdrone_01_a` has `default`,
`terran`, `closedloop`, `xenon`) are built with **the builder faction's
preferred build method**, not the station's module race and not the
customer's faction:

- The rule lives in `<faction><buildrules method="…"/>` (savegame-
  structure.md § factions). For `id="player"` it is the UI's *Default
  preferred build method* — Terran / Universal (= `default`, everything
  non-terran) / Closed Loop (= `closedloop`, claytronics + hull parts).
  Stable across all 13 archived saves here (`terran`).
- A per-station override (station configuration menu; unset = inherit the
  faction rule) serializes as `<build method="…"/>` directly under the
  station / `buildstorage` component — **CONFIRMED 2026-07-27** by a
  controlled change: ABR-398 carried no such element while inheriting the
  player's `terran` rule, and gained `<build method="closedloop"/>` the
  moment it was set to Closed Loop in-game (save_009). Three stations
  universe-wide have one. Resolution order for anything that builds:
  station override → faction `<buildrules>` → race default.
- Per ware, the effective method is the chosen one *if that ware has a
  recipe under it*, else `default` — the engine's own fallback, so a
  Terran player still builds `default`-only items (e.g. laser towers)
  from the default recipe.

This is why ABR-398's `supplies`-flagged drone buys matched the **terran**
drone recipe: the player faction's rule, not its terran storage modules.
Anything joining `recipe` for player-built items should select
`method = <player buildrules>` with a `default` fallback — the same
`(ware, method) → (ware, "default")` pattern `analysis/storage.py`
already uses on the production side. **Parsed since v21**:
`faction_meta.build_method` + the `build_method` table, resolved by
`v_build_method` / `frames.build_methods`, and `station_modules.method`
now carries the resolved value (it was always empty before, so module
build costs silently used the `default` recipe for every builder).
