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
- **A full station posts NO buy offer at all — CONFIRMED 2026-07-28**
  (player-observed on UDX-946, whose ore buy price sat at 0 for ~45 minutes
  because it was completely full, then appeared the moment it began drawing
  down). The offer is withdrawn, not priced at zero. Coverage across all
  computed input/ration rows in save_009's quicksave:

  | fill | rows | posting a buy offer |
  |---|---:|---:|
  | 0–90 % | 3,692 | 99.7 % |
  | 90–100 % | 1,225 | 92.7 % |
  | 100–110 % | 134 | **38.1 %** |
  | 110–120 % | 101 | **5.0 %** |

  Three consequences. A price-history chart reading 0 means *no offer*, never a
  zero price. The buy-side sample is **censored at the top of the fill range**,
  so the scarcity of buy points past 100 % fill in the fill-vs-price scatter is
  the game withdrawing offers, not evidence the allocation model is right
  there. And it corroborates the offer-derived allocation from the other
  direction: the bid disappears exactly as stock reaches the allocation.

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
  *Target_level* is NOT stored, and — **corrected 2026-07-27** — it is
  **not the storage allocation** either. The two were conflated: a
  station's allocation (`analysis/storage.py`, per-pool hours factor) is
  validated and matches the in-game UI exactly (player-read: VVT-308
  483k, FXT-179 435k, GUX-488 994k, AXO-574 992k), but the price curve
  runs over a much narrower span.

  Measured by *synthesising a curve from a cohort* — stations sharing
  ware, allocation and owner differ only in fill, so the cross-section IS
  the curve (the idea that cracked this; a single station gives one
  point). Fits are essentially exact, which also settles that the curve
  is linear:

  | cohort | n | R² | span | = hours of production | span / allocation |
  |---|---:|---:|---:|---:|---:|
  | energycells / terran (alloc 992,397) | 14 | 0.999 | 226,038 | 6.6 h | 0.23 |
  | energycells / teladi (alloc 98,618) | 12 | 0.996 | 78,515 | 5.2 h | 0.80 |
  | graphene / teladi (alloc 12,019) | 7 | 0.998 | 9,068 | 4.3 h | 0.75 |
  | computronicsubstrate / terran (alloc 5,376) | 6 | 0.982 | 626 | 1.0 h | 0.12 |
  | computronicsubstrate / pioneers (alloc 5,376) | 7 | 0.999 | 538 | 0.8 h | 0.10 |

  The Terran solar cohort resolves to: **band max up to ~43,000 units
  (4.4% of allocation), falling linearly to band min at ~269,000 (27.1%),
  flat at min above that** — three Mercury plants sitting at 100% fill and
  exactly 10.00 Cr anchor the tail. So `span/allocation` is not a
  constant, but `span` in *hours of production* is 4–7 h for the bulk
  wares, which is strikingly close to the early single-station fit of
  `≈ 6.105 h × throughput` that was retired when the allocation model
  landed. That fit was probably right about *this* quantity all along —
  it was measuring the price reference, not the storage allocation.

  Caveats before this becomes a feature: offer prices are player-facing,
  so a reputation discount scales the fitted slope (terran 15%, teladi 5%
  here) and inflates the measured span by 1/(1−d); the computronic
  substrate cohorts sit at ~1 h and fit no pattern yet; and the two knee
  positions have only been measured on one cohort.

  **Solar output scales with sector sunlight — CONFIRMED 2026-07-27
  (player-derived, now implemented).** `analysis/storage.py` rated energy
  cells at their recipe speed everywhere, inflating solar throughput by
  1/sunlight and skewing the equal-hours split on every station that makes
  energy cells alongside anything else. DLB-176 (Family Zhin,
  sunlight 0.71) produces 42,480 energy cells/h against a 42,000/h rated
  base — i.e. base x sunlight x the workforce bonus — and with that rate
  the existing split reproduces the in-game allocation exactly:

  | ware | model before | model after | in-game |
  |---|---:|---:|---:|
  | energy cells | 428,126 | **348,586** | ~348,000 |
  | graphene | 14,987 | **17,186** | 17,216 |
  | superfluid coolant | 15,135 | 17,357 | — |

  So the allocation RULE was right all along (equal hours over the pool
  net of the food buffer); only the throughput feeding it was wrong. The
  fix halved the population of stations holding more than their modelled
  allocation (37 output rows -> 29; the >5% cases 17 -> 7).

  **The ration buffer and the production share are ADDITIVE.** CONFIRMED
  2026-07-27 on JFV-172 (Tharka's Ravine XVI), which produces cheltmeat
  *and* feeds it to its own workers. The 4 h ration buffer comes off the
  pool first for **every** ration — including one the station makes — and
  a producer then takes a normal share of what is left, on top of its
  buffer: cheltmeat 12,757 + 306 = 13,063 against 13,062 read in-game,
  with spices landing on 20,051 exactly. Treating the roles as exclusive
  (food winning, as the model did) costs the producer its entire
  production claim and hands the surplus to the station's other wares —
  it put spices at 37,192 against a real 20,051.

  **Modules produce whole units per CYCLE — the engine truncates.**
  CONFIRMED 2026-07-27, 7/7 against player readings. The workforce bonus
  and sunlight scale the *cycle's amount*, which is then floored, and the
  hourly rate is that integer over the cycle time:
  `rate = floor(amount x (1 + work_effect) x sunlight) / time x 3600`.
  Order matters — DLB-176's energy cells only land on the observed 42,480/h
  if sunlight is folded in BEFORE the floor. It is truncation, not
  rounding: 97.92 -> 97 microchips, 195.91 -> 195 smart chips,
  141.55 -> 141 coolant. Multiplying at the hourly level instead leaves
  fractional units and always reads high, by a per-ware amount set by
  where the fraction falls (0.01%-0.9% observed) — which perturbs the
  RATIOS the pool split runs on, not merely the absolute rates.

  With all of the above in, the model reproduces **all 18 player-read
  allocations to within 0.20%** — nine of them exactly — across eight
  stations, six factions and both single- and multi-ware producers.

  **Production efficiency: the save states the multiplier — CONFIRMED
  2026-07-28.** Every production module carries
  `<production><efficiency product=>`, and that one number IS the whole
  multiplier on the recipe amount: workforce bonus, sector sunlight and any
  mod effect folded together. The rate is
  `floor(recipe.amount x product) / time x 3600` per module (truncated per
  CYCLE, as already established). EIJ-609 (Holy Order hull parts, True Sight)
  reads `product="1.12634"`: floor(294 x 1.12634) = 331 per 900 s x 3 modules
  = **3,972/h**, exactly the in-game logical overview, against 4,824/h from
  the reconstructed `work_effect`.

  This matters because the multiplier is **not reconstructible**: this
  playthrough runs Faction Fix Pack, which adds a per-faction "production
  efficiency from war pressure" term seen on ARG and ANT stations at
  *differing* percentages. Reading the field is the only mod-proof route.

  Scored against the **offer-derived** allocations (below) over 4,914
  (station, ware) pairs, the basis for OUTPUT storage is:

  | basis | median \|err\| | within 1% |
  |---|---:|---:|
  | save `efficiency`, outputs only | 0.0000 | **87.2%** |
  | reconstructed `work_effect` x sunlight | 0.0001 | 76.7% |
  | no multiplier | 0.0036 | 50.9% |
  | `efficiency` on outputs AND inputs | 0.0103 | 49.9% |

  So the model's SHAPE was right — outputs boosted, inputs at base — only the
  multiplier was reconstructed instead of read. Splitting by whether a
  station's efficiency equals `1 + work_effect` isolates the mod term and
  shows it genuinely enters the allocation:

  | station group | n | reconstructed | save `efficiency` |
  |---|---:|---:|---:|
  | efficiency == 1+work_effect (579 stations) | 2,790 | 92.9% | 92.9% |
  | efficiency modified (539 stations) | 2,124 | 55.5% | **79.7%** |

  Sunlight is already inside `efficiency`, so it must not be applied again.

  **A module with NO `<production>` block runs the bare recipe** (multiplier
  1.0), not the reconstructed `work_effect` — CONFIRMED on KRV-460, whose lone
  turret-components module reports no block and whose four inputs all come in
  at exactly 0.724 of the offer-derived truth; 1/0.724 recovers the 1.53
  `work_effect` the fallback was wrongly applying, and its true output rate is
  the base 340/h. 939 (station, macro) pairs are in this state. Treating them
  as 1.0 lifts them from 43.6% to 73.8% within 1% and the whole computed
  population from 82.9% to **86.2%**. `SOLAR_WARE` and `work_effect` now
  survive only for a save carrying no production data at all (a pre-v27
  database), where a missing row means "unknown" rather than "idle".
  Implemented v27 (`module_production`).

  **War-pressure bonuses do not count toward storage — player-confirmed
  2026-07-28.** EIJ-609 still reads 34,829 hull parts after the efficiency
  change, so its allocation follows a multiplier of 1.0 while its modules
  report 1.12634 and its production rate follows the full 1.12634. The mod's
  war term therefore enters the RATE but not the ALLOCATION, and the two have
  to be separated. `efficiency / (1 + work_effect)` is exactly 1.000 for the
  plurality of modules in every faction, so the vanilla part is recoverable in
  principle; the separation is not yet implemented. OPEN.

  **Superseded — EIJ-609 as a lag.** Its allocation implies efficiency exactly
  1.0 (in-game 34,829 hull parts; base model 34,829.1, and all three
  offer-derived inputs within 0.6 units, pool closing to exactly 1,000,000 m3)
  while its modules report 1.12634. HYPOTHESIS: the allocation is recomputed
  lazily and lags a recent efficiency change (its workforce is starving — zero
  medical supplies and zero soja husk — and the mod's war term looks recent).
  FALSIFIABLE: re-read the hull-parts allocation in-game later; the lag
  hypothesis predicts it drifts to ~37,228. If it stays at 34,829 the
  efficiency basis is wrong for war-modified stations specifically.

  **The offer-derived allocation is a LOWER BOUND, not an equality —
  CORRECTED 2026-07-28.** An open, unflagged buy offer's `amount` was briefly
  recorded here as exactly `allocation - stock - inbound pending`. It is not:
  a station bids only for what it can *use*. MAL-475 (player-owned, every
  allocation and rate confirmed correct in game) reads 157,810 derived against
  a true 1,498,962 energy cells because its consuming modules are still under
  construction; TPF-229 reads 4,470 derived helium against a true 10,654, and
  posts no buy offer at all for silicon, methane, silicon carbide or ore.
  Treat `stock + inbound + amount` as a floor: a model value BELOW it is a
  real error, a model value above it proves nothing. The 86%-within-1% figures
  quoted below were scored against this quantity as if it were truth and are
  therefore optimistic for the stations that are buying and uninformative for
  those that are not.

  The original claim held on EIJ-609 (graphene 2,466 + 426 inbound + 1,846 =
  4,738, putting all three inputs on an identical 9.872 h) and on most
  actively-trading stations, which is why it survived a sweep.
  Verified on EIJ-609 (graphene is its only ware with inbound: 2,466 + 426 +
  1,846 = 4,738, and only with the inbound term do all three inputs land on an
  identical 9.872 h), and save-wide the derived value matches the model at
  median ratio 1.0000. This turns allocation validation from 18 hand-read
  numbers into thousands of ground-truth points per save and should gate any
  future change to the model.

  **`<workforces><bonus busy=>` is NOT a bonus on/off switch** — busy=0 on
  1,132 of 1,244 workforce stations, including plainly bonused ones. It looks
  like a cycle phase. Do not use it as a gate.

  **A station can hold MORE than its allocated capacity.** MBI-471 reads
  14,330 energy cells against a 4,403 allocation *in the game's own menu*.
  Allocation is a trade/target level, not a physical cap — so "stock >
  allocation" is not evidence of a modelling error, and the 314 over-full
  input rows recorded as P5c are probably not a defect at all.

  **Dual-role wares are sized by the LARGER flow — CONFIRMED 2026-07-27**
  (player readings on KWC-232, Avarice IV). A station that both makes and
  uses a ware buffers the bigger of the two rates, not its output:
  KWC-232 makes 208,708 energy cells/h (1 solar module x 14.9 Avarice
  sunlight) and feeds 372,000/h to its four recyclers, and the game
  allocates on the consumption side. **Processing modules are outside the
  storage model entirely** — the scrap works' own 90,000 energy cells/h is
  excluded (counting it misses by 5% on energy cells and 15% on hull
  parts), matching the fact that its `rawscrap` feedstock is never stocked
  either. Its *output* (scrap metal) is stored normally.

  | ware | rate used | model | in-game |
  |---|---:|---:|---:|
  | energy cells | 372,000/h (recyclers) | 1,832,398 | 1,833,000 |
  | hull parts | 6,576/h (output) | 32,392 | 32,367 |
  | claytronics | 1,930/h (output) | 9,505 | 9,450 |

  All three land at the same 4.93 h, so equal-hours holds — only the rate
  feeding it was wrong. DLB-176 is unaffected (production 42,643/h dwarfs
  its 2,100/h consumption) and still matches at 348,586 vs ~348,000.

  **Scope note (2026-07-27, agreed with the player):** pricing work is
  currently confined to **basic production stations** — wharfs,
  shipyards, equipment docks, trade stations and pirate bases are
  excluded (they price by other rules: Layer 6, build price factor), as
  are player and Xenon stations, and `supplies`-flagged offers.
  **Workforce/food wares are tabled**: on habitats and trade hubs the
  model allots ~4 h of rations while the station stocks food as a trade
  good, so `station_storage` role='food' rows overshoot badly (219 rows
  over allocation, worst 110×) and are not usable as a fill measure.
  Multi-ware production stations ARE in scope, with the caveat that their
  pool split is approximate (351 input rows over allocation, mean 1.37×);
  single-output stations are clean (0 of 841 over-full).

  Within that scope, fill vs band position pools remarkably well across
  every ware — normalising price to `(price−min)/(max−min)` and fill to
  the modelled allocation, over 1,045 stations:

  | side | n | fit | R² |
  |---|---:|---|---:|
  | sell | 1,408 | band position = 1.001 − 0.0100 × fill% | 0.82 |
  | buy | 2,335 | band position = 1.060 − 0.0099 × fill% | 0.80 |

  A slope of −0.01 per % *is* `max − (max−min) × stock/allocation`, so the
  allocation-denominated curve is right for the bulk of stations — the
  cohort deviations above are the tail (oversized storage), not the rule.
  The buy side tracks fill on the same slope about 6% of a band higher,
  which is a stronger statement than Layer 4's "consumers price off need,
  not fill" and worth revisiting there.

- **The trade panel's decomposition — CONFIRMED 2026-07-28.** The station
  trade screen states the whole model outright: the price is the ware's
  **average** times one plus a sum of **additive modifiers, each expressed as a
  percentage of AVG**. Read off UDX-946 (ARG Ore Refinery I, The Reach):

  | ware | panel modifiers | panel price | check |
  |---|---|---:|---|
  | refined metals (selling) | High Supply −38.9 %, Prized Investor −9.1 %, **Total −48.0 %** | 76.82 | 148 × 0.520 = 76.96 |
  | ore (buying) | High Demand **+6.6 %** | 53.30 | 50 × 1.066 = **53.30 exact** |

  And the save's offer price carries the **supply/demand term alone**: its
  refined-metals sell offer is 90.72 = avg × 0.6130 = −38.70 %, against the
  panel's −38.9 %. The reputation discount is applied on top at display time,
  confirming Layer 3's split from the other direction.

  **The reference band IS that modifier's range.** `min = avg × (1 − spread)`
  and `max = avg × (1 + spread)` — symmetric for **1,851 of 1,891** wares
  (refined metals ±39.86 %, energy cells ±37.5 %). So for almost everything,
  "band position" and "modifier off avg" are the same quantity rescaled:
  `band = 0.5 + s / (2 × spread)`. The 40 exceptions are genuinely asymmetric
  — **ore is one** (−14 % / +16 %), as are food rations, graphene, engine parts
  and ice — and on those the band-position axis kinks at avg, so any curve fit
  should use `s = price/avg − 1` normalised by the appropriate half-width
  rather than `(price − min)/(max − min)`.

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
  so locked wares stay arbitrage-able with reputation. Re-confirmed on
  save_009: all 588 locked sell offers sit exactly at band average (zero
  variance), all 587 locked non-supply buys at exactly avg − 1 Cr, and
  the 13 supplies-flagged buys on locked wares price at 1.07–1.222× avg.
  **Consumers**: `frames.trade_settings` carries the whitelist and
  `analysis/opportunities.py` honours it (locked endpoints are exempt
  from the moves-against-you depth caveat, supplies-flagged offers
  excluded from the marking); any future storage-curve price model must
  skip locked (station, ware) pairs entirely. Their *unlocked*
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

## Mod-aware reference data (runtime patching, not CSV edits)

**Deliberate design decision, 2026-07-28.** The reference CSVs in
`src/x4analyzer/data/` are extracted from **base game + DLC only** and are kept
that way: they are committed, shared across every save and every user, and
should describe vanilla X4. Mods that rewrite game data are therefore applied
**per save, in memory, for that run only** — `gamedata/modpatch.py`, called
from `analyze.py` right after the parse. Nothing on disk changes and a
non-modded save is untouched.

Why it matters: analysing a modded save against stock recipes silently
produces wrong throughputs, and throughput feeds the storage allocation, which
feeds fill %, which feeds every price conclusion.

**Detection has two routes**, because mods fall into two camps:

- *`save="true"` mods register in the savegame* as
  `<patches><patch extension="ws_…" version=".." name=".."/></patches>`
  (`SaveData.extensions`, parsed since v27). Matching the extension id is exact.
  Habitat Capacity Boost (`ws_3737446888`) is one.
- *`save="false"` mods leave no trace at all.* They are pure data overlays, so
  the game records nothing — and that is exactly the camp the recipe-rewriting
  mod is in. For these the only option is a **fingerprint**: a value in the
  save impossible under stock data.

**The fingerprint used: the production efficiency ceiling.** A module
serialises `<production><efficiency product="X"/></production>` and
X = `1 + work_effect × workforce_ratio` with the ratio in [0, 1], so X can
never exceed `1 + work_effect` under stock data. When it does, that ware's work
effect is not the stock one. In this playthrough exactly one ware breaches it —
`advancedelectronics`, 59 of 101 modules, max ratio 1.0294 = 1.40/1.36 — and
nothing else in the save comes near its ceiling, so the signal is clean.

**What is registered** (read out of the mod's own packed XML with `GameFiles`,
not inferred): `faction_fix_pack_econ_bal` (`ws_1668472321`, "Faction Enhancer
– Econ Balance Module") ships a `libraries/wares.xml` `<diff>` of three
`<replace>` ops. Two are production recipes:

| ware | stock | modded |
|---|---|---|
| `advancedelectronics` | amount 54, work 0.36, in 60/44/20 | **amount 65, work 0.40, in 150/49/36** |
| `weaponcomponents` | amount 170, work 0.53, in 60/20/30 | **amount 204, work 0.53, in 120/25/36** |

(The third only changes a laser-tower *build* input, which storage never uses.)
`weaponcomponents` keeps its work effect and so raises no fingerprint of its
own; it is applied because it ships in the same file — one mod, one atomic
change set. Overrides **replace** the whole `<production>` entry rather than
merging, because a `<replace>` op can drop an input as well as change one.

**Measured effect** on the in-game readings fixture
(`tests/data/station_readings.json`, `uv run python tests/readings.py`):
**27/41 → 37/41** within 1%. IFO-957 goes from five failures to zero (all
within 0.4%, production rate exact at 450/h) and WRC-739 from four to zero
(all +0.0%).

**Not the catchup mod.** `faction_fix_pack_catchup` changes no recipes. Its
"Production efficiency from war pressure" (Holy Order +20%, Antigone +40%,
Argon +22%) is a post-hoc `<add_cargo>` of `floor(base_cycle_amount ×
ProdBonus)` on every production-finished event — **invisible in the save's
`<efficiency>` element and in the UI's Product/h**, and not a rate multiplier.
The percentage shown in the station menu is a separate UI row fed by
`$CatchupProdBonus` on the trade NPC blackboard. Do not model it as a
multiplier.

**Known gap, not yet registered:** `nd_habitat_cap_boost` (`ws_3737446888`,
which *does* appear in the save's patch list) replaces habitat workforce
capacity with S 2500 / M 5000 / L 10000 against a stock 333/666/999, a 7.5–10×
housing boost. `modcaps.csv` is stale for it, and `extract_modcaps` cannot read
it either — those are `<diff>` files with no `<macro>` element. Workforce
drives the ration buffer and the efficiency, so this is the next candidate for
the registry.

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
