# Open questions & follow-ups — pricing / save-knowledge sessions (2026-07-26/27)

Status ledger after the supply-offer discriminator (v18, commit
`bd9a842`), the deployable-pricing study (six stations, nine deployables,
save_008), the subscription investigation, and the v19/v20 captures
(`6e4b0f1`, `6e7edd4`, `1bed0cc`). What follows is only what is still
OPEN — settled results live in
[supply-offer-discriminator.md](supply-offer-discriminator.md),
save-semantics.md (§ market data, § pricing incl. Layer 6, § drone pool),
savegame-structure.md, and db-schema.md.

Settled this session, for anchor: `supplies` offer flag = self-supply
demand (CONFIRMED, sweep-wide ×2 saves); deployable pricing
`quote = base × Σ(recipe·E)/Σ(recipe·avg) × M` with **M =
`buildpricefactor`, read from the save** (≤0.30% on all cross-station
constraints); `lockavgprice` = economy price pegged at band avg with
discounts stacking and supplies-buys exempt (7/7); permanent
subscriptions come from data-leak scans; drone build targets persist in
`<supplies><orders>` (37/40 exact).

---

## 1. Open research questions (need in-game readings or play experiments)

### P1 — The E vector (the last gap in deployable pricing)

E (per-ware valuation the resource factor prices against) is engine
runtime state: not persisted, and every offline candidate failed
proportionality (own curve / own buys / reference prices / band avg /
offer-book aggregates at every scope / executed-trade averages — all >5%
spread vs <1% required). Three vectors observed in save_008: E_A shared
by QJI-262+HLA-335+RLP-496 to 0.1% (3 sectors, 2 factions), E_B by
co-sectored PDR-519+XAP-684, E_C = band avg (NUJ-928).

- **Experiment (decisive, cheap): re-read QJI-262's nine deployable
  quotes a few game-hours after the last reading, paused.** Drift ⇒ E is
  a sampled time-varying statistic (the update-tick grouping — XAP/PDR
  6 s apart, QJI/RLP 3 s apart — becomes the explanation); frozen ⇒
  static and the cross-map sharing needs a different theory.
- **Second economy: same nine quotes at an Argon wharf + shipyard +
  equipment dock** (default recipes → different input wares). Tests
  whether the structure replicates outside the terran economy.
- Fallback framing if E stays opaque: fitting E from ~4 quotes predicts
  the station's remaining deployables to 1–3% — usable, just not
  save-only.

### P2 — `buildpricefactor` dynamics

It re-rolls (12/67 changed between save_006 and save_008, some small
steps 0.9→1.02, some jumps 0.9→1.15). Open: the re-roll interval, and
whether the walk correlates with the previous value. Answerable offline
by sweeping the archived save series (seed-trends corpus) — no play
needed, just a script pass. Also: confirm in-game that MXH-411's stored
1.5 equals its price-slider setting in the station UI.

### P3 — `<supplies>` semantics (play checklist from the v18 report)

1. **Target vs outstanding orders** — *mostly answered offline by the v22
   import*: five full, idle player stations show order rows exactly equal
   to their drone counts (JQR-498/MXH-411 30-10-10, QNF-337/TIH-455
   15-5-5, MAL-475 30-10-9), which an outstanding-orders reading would put
   at 0. Still worth the one-minute confirmation: on a full station raise
   the target (cargo 30→40), save — orders reads 40 ⇒ target; 10 ⇒
   outstanding. Then lower below stock: does the block shrink without
   scrapping drones?
2. **Block lifetime**: set a target on a station without the block, let
   it complete, save again — does the block persist (target) or clear
   (orders)?
3. **Ammo coverage**: set a missile stock level on a defence station —
   do missile wares appear in `<supplies><orders>` and their components
   as `supplies`-flagged buys?
4. ~~**Build method selection**~~ — **CLOSED 2026-07-27, no play
   experiment needed.** It is a *faction* setting, persisted as
   `<faction id="player"><buildrules method="terran"/>` = the UI's
   "Default preferred build method" (player-confirmed: Terran; the other
   options are Universal = `default` and Closed Loop = `closedloop`).
   Verified in the save: `build@method` is constant per builder faction
   over all 499 in-flight build tasks in save_008 and never tracks module
   race (player 12/12 terran); the element is byte-identical in all 13
   archived saves; NPC factions without one build on their own race rule
   (`alliance` → closedloop, which turned out to be per-station
   overrides, not a faction default). The per-station override was then
   settled the same day by a controlled in-game change: ABR-398 set to
   Closed Loop → save_009 gains `<build method="closedloop"/>` as a direct
   child of the station component (no such element while inheriting).
   Resolution order: station override → faction `<buildrules>` → race
   default. Per-ware fallback to `default` when the
   ware has no recipe under the chosen method is the engine's own rule.
   Written up in savegame-structure.md § factions and save-semantics.md
   § Build method.

### P4 — Smaller semantic gaps

- **`component@known`**: among kept classes it marks 133 stations +
  sectors/clusters, nearly all also `knownto` — "visited"? "docked at"?
  Check a station you have definitely never visited but see on the map.
- **Subscription refresh trigger**: satellite-in-sector is falsified;
  hypothesis is per-object radar radius + `tradecompleted` refresh. Park
  a satellite next to one station, save twice, check its
  `remaining_s` ≈ 18,000 both times.
- **Drone-pool `+10/production` capacity term** (long-standing): still a
  one-point fit (MXH-411). Any in-game `units.maxcount` reading on a
  second production-heavy station would make it two.
- **Layer 4 buy-side curve**: first game-data anchor found —
  `parameters.xml <economy><prices><build min="0.25">` ("below 25%
  resources → pay max price"). A model of consumer buy prices vs fill
  around that threshold is unstarted.
- **Silent Witness XI vs XII**: my sector-name attribution for XVV-754
  disagreed with the in-game name by one sibling sector — likely an
  off-by-one in the report script's sector mapping, worth a quick check
  against `sectors.csv` (offline, minor; the committed data is
  unaffected).

## 2. Suggested implementation todos (code; one done — build method, v21)

- **`buildpricefactor` history (trend layer).** v20 stores it per
  snapshot in a W table — wiped on every import. Since it drifts, a
  "cheapest yard over time" view needs an A-table (station_metric-style
  append-once-per-snapshot). Small, and the seed-trends corpus would
  backfill it.
- **The map's knowledge layer** (original motivation): consume
  `player_subscription` (freshness/expiry per station, filter expired,
  sector roll-ups) + `player_scan` (scan levels) + `component.knownto`
  once station plotting lands.
- **Advisor/market widgets: exclude `supplies`-flagged offers from
  demand.** Known conflation left deliberately in v18 (1,140 of 15,418
  offers); flags are in `frames.trade_offers` now, so it's a filter.
- ~~**Price-prediction consumers: respect Layer 6.**~~ — **DONE
  (2026-07-27)**: `frames.trade_settings` exposes the whitelist and
  `analysis/opportunities.py` tags locked endpoints (`lk`), which the
  Trade Opportunities table badges *locked* and explains — their quote
  does not slide as the trade fills, so the depth/slippage caveat that
  governs every other lane does not apply. `supplies`-flagged buys are
  excluded from the marking (exempt from the lock). 216 tagged endpoints
  in save_009; pinned by `tests/test_opportunities.py`, including the
  no-whitelist case so the tag stays evidence rather than a default.
  Note there is still no storage-curve *predictor* in the code — when one
  ships it must skip locked pairs outright (recorded in save-semantics).
- **`spoilers_hide` at object granularity** using
  `component.knownto`/`known` instead of sector-level hiding.
- **Opportunities view: trade-station whitelists** — only the 58
  settings-stations trade arbitrary wares; the whitelist says which.
- **P&L/net-worth: include `trade_active` escrow** (6.9M Cr in save_008
  currently invisible between wallet and cargo).
- ~~**Pending capture** (the supply-curve numerator)~~ — **DONE (v26,
  2026-07-27)**: `trade_pending` + `v_trade_pending`. Both homes of a
  committed trade turned out to be the same record (order-embedded
  `<trade>` and station `<reservations>`, attribute-identical
  2,510/2,510, the reservation's `@reserver` being the order's ship), so
  the store merges by trade id rather than storing both; `trade_active`
  (v20) is superseded — its 49 rows are the escrow subset, now the
  `is_active` flag. Validated: on the 34 clean non-terran NPC solar
  plants with pending, the term cuts mean sell-price error 1.185 →
  0.515 Cr.
- **NEW: the storage model over-allocates once a station's storage is
  large — an absolute cap it does not implement.** Found while validating
  the v26 pending capture; diagnosed 2026-07-27 on save_009's clean
  single-output NPC energy plants by inverting the Layer-2 curve for the
  target level (`implied = (max−min)(stock−pending)/(max−price)`, taken
  only where 12 ≤ price ≤ 20 so the inversion is well-conditioned):

  | modeled allocation | n | implied/modeled |
  |---|---:|---:|
  | under 250,000 units | 69 | 1.05 |
  | 250,000–320,000 | ~7 | 1.00–1.05 |
  | 435,744 / 483,962 | 2 | 0.73 / 0.65 |
  | ~1,000,000 (an L container) | 15 | **0.32** |

  Every station modeled above ~320k units lands at an implied 296k–413k
  regardless of how much bigger its pool is, while everything below
  matches the model. **Not race-specific** — the first read called this a
  Terran defect, but a teladi plant (GUX-488, 1M pool) saturates
  identically at 0.30; Terran plants merely dominate the sample because
  they pair 8 production modules with a full 1M L container (28.9 h of
  storage vs 5–7 h elsewhere). The capacity data is not at fault
  (`storage_ter_l_container_01` = 1,000,000 m³, same as the Argon and
  Paranid L containers) and neither is throughput (the terran recipe's
  50/60 s is correctly picked over the default 175/60 s).

  So `analysis/storage.py`'s "a single-output station allocates its whole
  pool to that ware" is right only up to a ceiling of ~300–360k units.
  Open: whether the cap is denominated in units or m³ (energy cells are
  1 m³, so this sample cannot separate them), and its exact value.
  A second ware with a different volume would settle it. Until then any
  price prediction on a big-storage station is ~2 Cr out, and
  `station_storage.max_units` overstates those stations' allocation ~3×.
- ~~**wares.csv `price_min`/`price_max`**~~ — **DONE (v25, 2026-07-27)**:
  extraction captures the band, committed CSVs regenerated, `ware` gains
  `price_min`/`price_max`. Two vanilla DLC wares ship a broken `min`
  upstream (boron miner, split shield — both non-economy); kept verbatim
  with a warning rather than repaired, and pinned by
  `tests/test_catalog.py`. Load-side papercut fixed on the way: a stale
  user-dir CSV shadowing a newer packaged one used to load missing
  columns as silent NULLs — `write_reference` now warns.
- ~~**`<supplies><orders>`/`<wares>` + `<prices><override>` persistence**~~
  — **DONE (v22, 2026-07-27)**: `station_supply` (kind `order` = build
  target, `ware` = set-aside inputs; stations/build storages only, since
  a ship's identical block is its own ammo reserve) and `price_override`
  (whole credits, NULL = side not overridden), plus `v_station_supply`.
  save_009: 41 order rows / 2,444 ware rows over 1,048 stations, 22 price
  overrides over 6 hosts. Two side findings: the order rows equal the
  drone counts on five *full* player stations, which is hard to reconcile
  with an outstanding-orders reading (P3.1 above is now mostly answered —
  the raise-the-target check would close it); and a THIRD, previously
  unnoticed block, `<overrides>` directly under the station component
  (`<buy>`/`<sell>`/`<max>` ware lists with optional amounts, 6 stations)
  — documented as **unverified**, not parsed, with a discriminating
  in-game check noted in savegame-structure.md.
- ~~`<prices><reference>` + the `<overrides>` block~~ — **DONE (v23,
  2026-07-27)**: `price_setting` gains kind `reference` (21,997 rows /
  4,433 hosts — the persisted side of pricing Layer 5) and `ware_limit`
  captures the station-UI per-ware limits. The `<overrides>` semantics
  that v22 flagged unverified are now CONFIRMED, without a play
  experiment: the engine's own API names
  (`GetContainerStockLimitOverrides`, `Set(Buy|Sell)LimitOverride`) name
  them, and the arithmetic is exact against live offers (buy limit −
  stock = desired; stock − sell limit = offered). The v23 residual — a
  ware listed with no `amount` carrying a 1-unit buy offer — is resolved
  in v24: the omitted amount is **1**, the floor the UI clamps all three
  limits to (player-reported, then confirmed in `helper.lua`), so the
  1-unit offer is just limit − stock.
- **Deployable-pricing model doc** in `docs/models/` consolidating the
  formula, M, Layer 6, and the E gap (currently spread across
  save-semantics + this report + the subscription findings scratch file
  — the latter lives outside the repo and will not survive the session).

## 3. Explicitly closed / not worth pursuing

Each closure is now recorded at the place a future reader would look
(2026-07-27), so nothing here needs re-deriving:

- NPC trade subscriptions: do not exist in the save (1 block
  universe-wide, player-only) — no reconstruction possible.
  → savegame-structure.md § The player component.
- `<listeners>` capture: MD-script plumbing, 186k rows, no analysis
  value. → savegame-structure.md § The component tree (recurring child
  blocks).
- Full build bill-of-materials storage model for wharfs: rejected
  earlier (proxy is as accurate, far cheaper) — unchanged.
  → savegame-structure.md § Stations (buildship warning) +
  db-schema.md `station_metric.source`.
- Per-type M constants ("wharf 1.15 / shipyard 1.067 / dock 0.90"):
  retired; use `build_price_factor` per save. → save-semantics.md
  § pricing, Layer/deployables.
- "Calibrate M once per station": dead twice over (engine variation,
  observed re-rolls). → same place.

Also cleaned up outside `docs/reference/`: `docs/plans/player-view-plan.md`
carried the falsified "faction trade subscriptions via `<licences>`" model
(steps 2/3, feasibility findings, risks) — rewritten to use
`player_subscription`/`player_scan`.
