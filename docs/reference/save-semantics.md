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
- **economylog `type="trade"` entries come in two flavors**; only those
  with buyer+seller+price are real transactions (owner-only entries are
  stock snapshots — see Market semantics below).
- **`ship_xs`** is a component class (drones, pods), mapped to size XS and
  excluded from mass plots.
- **Fleet hierarchy**: a follower's `<connected connection="[X]">` ↔ the
  commander's `<connection connection="subordinates" id="[X]">`. The flat
  `<subordinate>` elements in saves are the NPC job system — NOT player
  fleets. (Structure: savegame-structure.md § Fleet hierarchy.)
- **Log-text parsers**: ship construction/repair/resupply, destroyed-object
  and surplus-transfer parsing is ported verbatim from R but **unverified
  against v9 wording** (the test save contains no such events). If those
  dashboards stay empty on a save that should have them, check the actual
  log text first.
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

- The owner-only economylog `<log type="trade" owner ware v>` events record
  the station's **stock level after each trade**, NOT a trade amount —
  traded volume must be derived from positive deltas between consecutive
  snapshots per (owner, ware) (`frames.global_trades["dv"]`,
  `v_stock_delta`). Summing `v` directly overcounts ~40×.
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
  *Target_level* is NOT stored — it is computed:
  `target(ware) ≈ 6.105 h × workforce-ADJUSTED throughput (units/h)` for
  every ware the station produces or consumes (incl. workforce food and
  ammunition inputs); using base recipe rates instead of
  workforce-adjusted ones is the classic error. Workforce bonus:
  `actual_rate = base × (1 + staffing_ratio × recipe work_effect)`,
  per-recipe, not per-station.
- **Layer 3 — player-facing price** = `economy_price × (1 − tier% −
  event%)`. Reputation tier discounts: Known Associate 5% (relation
  ≥0.01), Prized Investor 15% (≥0.1), Partnership Agreement 25% (≥1.0);
  the UI shows the discount as a % of AVG, which makes the same tier look
  variable across stations. Per-station economy events add temporary
  `<modifier type="discount">` records.
- **Layer 4 — buy side: NOT modeled** (open gap). Consumers price off
  need, not fill, and run above the band ceiling.
- **Layer 5 — player-owned stations** use manual thresholds — off-model by
  design.
- **Deployables** (satellites/mines/…) are not stocked; a facility builds
  them on demand at
  `base_price × (Σ recipe·econ_price / Σ recipe·avg) × M_facility` with
  M ≈ wharf 1.15 / shipyard 1.067 / dock 0.90 — and **no reputation
  discount** (confirmed twice). *Hypothesis:* M is not a stable per-type
  constant (one wharf implies ≈0.92); likely an engine-side per-station
  term not derivable from saves — do not assume it is calibratable once.

## Station drone/unit pool

Station drones (defence/repair/transport/build/mining) + police craft
share ONE pool — the engine property `units.maxcount`, no per-type caps
(confirmed in-game). Actual counts live in the station's own
`<ammunition><available>` block (which also holds turret munitions and
deployables — separate inventories, flagged `is_unit=0` in the census).
Capacity formula: `cap = Σ modcap.unit_storage (dock/pier/build/defence
modules) + 10 × built production modules` — the `+10/production` term is
fit from one data point, so only the readable floor
(Σ `unit_storage`) is persisted (`capacity_floor`, exact for
non-production stations; validated in-game: ABR-398 40, EBT-957 92,
QJI-262 220, and MXH-411 310 incl. the production term). **Desired**
levels are not persisted anywhere in the save (the player auto-supply
config `$config_supply_*` has zero hits) — the model records observable
state only. Tables and views: db-schema.md § station_munition;
`tests/test_drones.py` carries the validation numbers.
