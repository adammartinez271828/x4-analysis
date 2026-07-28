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

### P5a — FIXED: solar output ignored sector sunlight

`analysis/storage.py` rated energy-cell production at recipe speed
regardless of where the station sits. Player-derived from DLB-176
(Family Zhin, sunlight 0.71): actual 42,480 ecells/h vs our 60,060, and
with the corrected rate the equal-hours split lands on the in-game
allocation (348,586 vs ~348,000 energy cells; 17,186 vs 17,216 graphene).
Over-full output rows fell 37 -> 29, and the >5% cases 17 -> 7.
The allocation *rule* was never wrong — only its input.

### P5b — FIXED: recyclers (dual-role wares + processing modules)

Two more rules, both player-derived from KWC-232 and both now implemented:
a ware the station makes AND uses is sized by `max(production,
consumption)`, and processing modules (scrap works) contribute neither
their feedstock nor their input demand to the allocation. Model vs
in-game after the fix: energy cells 1,832,398 / 1,833,000, hull parts
32,392 / 32,367, claytronics 9,505 / 9,450 — all at the same 4.93 h.

Output-side over-fills are now down to **1** (ULG-519, a shipyard on the
wrong code path) from 17 at the start of this thread.

### P5c — WITHDRAWN: "over-full" was never an error signal

Player-read allocations (2026-07-27) against `station_storage`:

| station | ware | modelled | actual (in-game) | factor |
|---|---|---:|---:|---:|
| QIB-162 (scavenger, Avarice IV) | energycells | 241,536 | 960,000 | ×3.97 |
| MDS-738 (scavenger, Avarice IV) | energycells | 241,536 | 960,000 | ×3.97 |
| KWC-232 (scavenger, Avarice IV) | energycells | 262,234 | 1,833,000 | ×6.99 |

Note the modelled figure is not merely low — the stations are holding
more than it (KWC-232 stocks 1,748,962), which is how this surfaced.
**Every high-ratio over-fill in the save shares one feature: a
`prod_gen_scrap_recycler` module.** 13 of the 17 genuine over-fill rows
sit on the nine recycler stations (Avarice I/IV/V plus teladi PKM-304 in
Bright Promise); the recycler's throughput or its role in the per-pool
hours factor is the obvious suspect, since a station that turns scrap
into energy cells has a production profile unlike anything the model was
validated against.

Tabled by agreement; revisit before any price model ships, since these
stations' fill percentage is meaningless until it is fixed.

The four non-recycler over-fills are mild and probably the multi-ware
pool split rather than a distinct defect: DLB-176 (split, Family Zhin)
graphene ×1.12 and superfluid coolant ×1.07, OOC-641 (boron, Reflected
Stars) energycells ×1.10, VDH-320 (holyorder, Cardinal's Redress)
antimatter cells ×1.05. Everything else in the list sits at ×1.00–1.02,
i.e. a full station the model gets right to within 0.1%.

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
- **NEW: pricing Layer 2's `target_level` is NOT the storage allocation.**
  Found while validating the v26 pending capture, and **corrected
  2026-07-27 by in-game readings** — an earlier revision of this entry
  blamed `analysis/storage.py` for over-allocating; that was wrong.
  Player-read allocations match the model exactly (VVT-308 483k,
  FXT-179 435k, GUX-488 994k, AXO-574 992k), so the storage model stands
  as validated.

  What the data does show: inverting the curve for `target_level`
  (`implied = (max−min)(stock−pending)/(max−price)`, restricted to the
  middle 70% of each band so the inversion is well-conditioned) gives
  implied/allocation ≈ **1.0 in the median over 500 station-wares** — but
  a systematic shortfall wherever a station has **large allocation and
  low fill**. The clearest cluster: Terran solar plants at ~15% fill
  (992k allocated) price at 16–17 Cr where the linear model says ~20 Cr,
  behaving as if their target were ~310k. Claytronics plants (implied
  2.3 h of throughput vs 6.9 h allocated) and big silicon-wafer plants
  show the same shape.

  Ruled out as causes, each with a measurement:
  - a units cap (~300k) — non-1 m³ wares saturate at wildly different
    unit counts (claytronics ~3k, refined metals ~34k, water uncapped);
  - an m³ cap (~300k) — implied×volume is not constant either
    (72k m³ claytronics … 620k m³ graphene), and QVL-220 holds 279k units
    of water = 1.67M m³;
  - an hours-of-throughput constant — implied hours vary 2.3–12.4 by ware;
  - reputation discounts (Layer 3) — implied/allocation medians are flat
    across all four discount tiers (1.03 / 1.01 / 1.00);
  - the quote reflecting the offer's volume rather than spot stock —
    an offer-midpoint price predicts *higher*, not lower.

  **Resolved 2026-07-27 by cohort synthesis** (player's idea: stations
  sharing ware + allocation + owner differ only in fill, so the
  cross-section is the curve). The curve is exactly linear (R² 0.982–
  0.999 across five cohorts) but spans far less than the allocation:
  Terran solar holds band max to ~43k units, falls to band min at ~269k,
  and is flat at min over the remaining 700k+ of allocation. Span in
  hours of production is 4–7 h for bulk wares (energy cells 6.6 h terran
  / 5.2 h teladi), matching the retired `≈6.105 h × throughput` fit —
  which was measuring the price reference, not the allocation. Details
  and caveats in save-semantics.md § pricing Layer 2. Remaining work:
  correct for the player-facing discount scaling the slope, explain the
  ~1 h computronic-substrate cohorts, and confirm the two knee positions
  on a second cohort.
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
