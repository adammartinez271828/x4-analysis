# Changelog

## 1.3.0 — 2026-07-21

### New User Features

#### Trade Opportunities

- **New Opportunities view** — the Trade tab now opens on **Opportunities**: ranked buy-here → sell-here **lanes** per ware, with per-ware "buy here / sell here" offer charts and top trading stations. Click a lane to jump the charts to its ware.
- **Real trip economics from your own ships** — each lane's profit-per-hour is built from your player trade ships' **loadout travel speed** and the lane's **actual route length** (station and gate positions along the gate-graph path, split into plain vs local-highway km), plus dock time — not a flat estimate.
- **Controls, as cards** — ware filter, ship preset (its cargo hold and computed travel speed shown read-only), adjustable **travel drive ratio** and **average highway speed**, per-ship-size dock time, and a **sell-player-reserve-stock** mode. Sort by Cr/h; **Distance (km)**, **Time**, and depth-capped **Depth Cr** columns.
- **Documented assumptions** — the "what these lanes mean and caveats" note explains what each control does to the model.

#### Sector Map

- **Data-vault overlays** — regular vaults (cyan stars) and Erlking vaults (gold stars) at every zoom level, showing opened vs unopened state and, on hover, code / status / blueprint; legend labels carry opened/total counts.
- **Player station markers** — zoomed in, each player station shows a marker with a name/code tooltip.
- **Highways on the map** — **Superhighways** and local **ring Highways** as their own Base Map toggles, drawn along their true spline tracks; gate lines now attach at the actual gate positions rather than zone centres.
- **Resource overlay redesigned** — the whole-hex tint that washed out busy sectors is gone. Each selected resource now draws **percentile edge gauges**: **mineable-now** up the left hex edges and **max replenishment rate** up the right edges (a half-full gauge = the median sector), so "empty but replenishing fast" reads distinctly from "full but slow to come back". The sector detail panel lists **every resource field** in a collapsible dropdown — current / capacity, gatherspeed, and a respawn ETA for depleted fields — with respawned ("overdue") fields correctly shown as full. Resources render regardless of which factions are selected.
- **Defaults** — gate/superhighway/highway routes on by default; Kha'ak stations off.

#### Universe Charts

- **Total Sector max replenishment per Resource** — a new sunburst on the Universe → Overview tab, companion to "Total Sector resources per Resource": each resource ring is subdivided by each sector's share of that resource's theoretical maximum replenishment rate (Σ capacity ÷ respawndelay, units/h).

#### Dashboard Layout

- **Five question-shaped tabs** — the dashboard is reorganized into a two-level layout (Map / Trade / Empire / Market / Universe) with sub-tab pills; the active view and sub-view persist across reloads.

### Internal

- **Resource respawn model** — the parser now captures each resource area's respawn-eligibility clock (`starttime`, schema v7) alongside its yield/level/gatherspeed tokens, and `extract-gamedata` pulls `regionyields.xml` and gatherspeeds into new reference CSVs. The reverse-engineered v9 depletion/respawn mechanic — areas deplete under mining, respawn whole once past `respawndelay`, and the stored yield materializes on the next miner contact — is documented in `docs/resource-depletion-model.md`, validated by an in-game experiment.

### Bugfixes

- **Weapon sim: mass drivers read as heatless** — Paranid Mass Drivers store per-shot heat on `<heat initial>` rather than `<heat value>`, so they showed no overheat time or cooldown. Fixed, and the heat cycle is now **simulated discretely**: mass drivers overheat in 2 shots, and `initial`-spike + `value` beams (e.g. the Scalar Aperture) are modeled correctly — all validated against in-game behavior.
- **Weapon sim: clip weapons showed burst rate** — clip/burst weapons (Tau Accelerator, Bolt Repeater/Turret, Neutron Gatling, …) displayed the intra-clip burst rate instead of the **sustained** fire rate the in-game encyclopedia shows (S Tau Accelerator 3/s → ~1.06/s).

## 1.2.0 — 2026-07-20

### New User Features

#### Interactive Sector Map

- **Interactive sector map** — the map tab is rebuilt as a **self-contained interactive SVG page** (no plotly):
  - Pan/zoom about the cursor, with **zoom-adaptive labels** — cluster names when zoomed out, sub-sector names when zoomed in
  - Hover tooltips with **gate-connection highlighting**
  - **View-state persistence** across reloads
- **Sector detail panel** — click a sector for its stations, resource yields, sunlight, and gate connections; alphabetically sorted, facility stations listed first with facility badges; the panel takes layout space instead of covering the map.
- **Facility overlays** — faction HQs, shipyards, wharfs, equipment docks, trading stations, and Kha'ak installations shown as zoom-adaptive icons (one row per cluster zoomed out, true in-sector positions zoomed in), dimming with their owning faction.
- **Overlays and legend controls** — resource overlay (renormalized over visible factions), sunlight overlay, player-assets overlay, faction all/none toggles, collapsible legend groups, and sector search/jump-to.
- **Accurate geography** — gate/accelerator lines attach at the gates' approximate in-sector positions, and multi-sector cluster layouts (mirroring, sector order, Sol names) now match an in-game audit.

#### Analysis & Tools

- **Raw resource supply on the Audit tab** — per-station cards showing mining inflow shortfall per hold class in m³/h and the fix quoted as ships (*"+32 M or +12 L"*), using each miner pool's **measured** real delivery rate.
- **`find` subcommand** — locates objects in a save by macro regex and reports in-game map coordinates; defaults to the 5 Erlking data vaults and reports whether each vault's blueprint is still uncollected.
- **Game-data dashboard** (`gamedata-dashboard`) — a new savegame-independent analysis page comparing weapon mods per weapon at optimal rolls, backed by an in-game-validated fire/heat/reload simulation.

### Internal

- **SQLite analysis database** — every parsed record now lands in a per-playthrough SQLite store: world state per snapshot, event history (trades, stock, log) merged idempotently across runs with save-stable identity and coverage epochs. The `csv.gz` cache layer is retired (existing history is imported once, files left as backup). Hardened against malformed/modded save data.
- **Entity registry** — surrogate GUIDs for ships and stations across snapshots (the game has no stable IDs: runtime ids remap, codes are recycled, names change), with capture/rename tracking; cross-run analysis keys on these where available.
- **Expanded game-data extraction** — ship cargo capacity (solid/liquid, from storage macros) into `ships.csv`, per-sector sunlight into `sectors.csv`, gate endpoint zone offsets and intra-cluster accelerator links into `gates.csv`, plus engine-, shield-, and ship/hull-mod models (`engines.py`, `shields.py`, `shipmods.py`).
- **Save-XML coverage inventory** — a ranked report of what the parser currently drops, as a roadmap for future extraction.
- **Package restructure** — pipeline-stage subpackages (`gamedata/` → `save/` → `db/` → `analysis/` → `viz/`); `frames.py` now reads from database views.

### Bugfixes

- **Weapon sim: beams understated ~3×** — beams are now modeled as sub-shot emitters.
- **Weapon sim: reload semantics** — corrected reload-rate vs reload-time handling and between-shot cooling; `<areadamage>` and interval-less clips (Blast Mortar, Boson Lance) are now parsed.
- **Ship mods** — `regiondamage` is a reduction fraction, not a multiplier; capacity mods are flat additive bonuses, not multipliers.
- **Weapon-mod qualities** are named Basic/Enhanced/Exceptional (were mislabeled Mk1–3).
- **Renamed ships no longer split their trade history** — tradelog display names are re-resolved per ship code.

## 1.1.1 — 2026-07-09

### Improved

- **Trade History browser** — the station/ship dropdown is now sorted alphabetically, and ships assigned to a commander (ship or station) are listed as `Commander (CODE) - Ship (CODE)`, so whole fleets group together under their commander. The "Executed by" tags use the same labels.

## 1.1.0 — 2026-07-09

### New Features

- **Map** — the legend was drawn inside the plot and covered the top-left sectors (Sol cluster area); it now lives in its own strip right of the map.
- **Fullscreen zoom button** on every chart widget — sunbursts, map, time-series redraw at full screen size; Esc returns.
- **Universe-tab sunbursts fully labeled** — every wedge shows its absolute value and % of the total, the center shows the grand total (modules / tonnes / ships; resource charts show per-resource total yields).
- **"Activity per faction"** (opaque mass-blend index) replaced by two concrete charts: station modules per faction per sector, and ships per faction per sector.
- **Ship resupply log entries** were unparseable on v9 saves — the game moved the details from the entry title into the text; both formats now parse.
- **Release workflow** — releases are drafted by hand with real patch notes; publishing triggers the build, which attaches binaries without overwriting the notes.

### Bugfixes

- **Crash (`LossySetitemError`)** analyzing fresh-playthrough saves where no trade party matched the removed-objects list.
- **Duplicate transactions in Trade History** — the cross-run trade cache deduped on exact rows, but component ids are reassigned between saves, so boundary trades gained one copy per analyzed save; dedup now uses save-stable identity and existing caches self-heal.
- **Market: overstated minable production** — production of minable wares (ore, silicon, …) was overstated ~20–40% by counting every trade hop; it now uses net deliveries, making actual balance agree with the stock trend by construction.
- **Market: phantom "construction" consumption for silicon/ore** — all recipes consuming them are Xenon-only, and Xenon (who harvest rather than trade) are excluded from market data; Xenon-only recipes no longer classify wares as build materials, and Xenon stock movements are excluded from the whole tab.

## 1.0.2 — 2026-07-08

### New Features

- **Market ware detail** — galaxy stock trend line overlaid on the deliveries chart (own right-hand axis), reconstructed from per-station post-trade stock snapshots — shows whether a ware is actually accumulating or draining.
- **Audit, idle ships** — shows each ship's standing order, and now also catches ships whose standing order is assigned but not running (previously invisible); pilot column dropped.
- **Escape pods** were listed as idle ships in the Audit tab and cluttered the Fleet Compositions sunburst; XS craft (not orderable) are now excluded from both, including pod-only sector stubs.
- **Log-text parsers** now dump samples of unrecognized log wording as console warnings, so localization/version drift is reportable instead of silently wrong.

### Bugfixes

- **Crash (`'str' object has no attribute 'str'`)** in ship construction/repair/resupply log parsing when the save's log wording differs from the expected English phrases; same latent crash class fixed in the transfers, pirates, and police parsers.

## 1.0.1 — 2026-07-08

### Improved

- **Windows exe** — when launched by double-click, the console stays open until Enter — final output and any errors are actually readable.

## 1.0.0 — 2026-07-08

Initial public release. Parses an X4: Foundations (v9.0) savegame and produces a static HTML dashboard: interactive sector map, trade/sales time-series, sunbursts, and sortable tables.

- **Standalone builds** for Windows (`x4-analyzer-windows.exe`) and Linux (`x4-analyzer-linux`) — no Python required; the newest savegame is found automatically and the dashboard opens in the browser. Running from source is supported via `uvx --from git+https://github.com/adammartinez271828/x4-analysis x4-analyzer`.

### Bugfixes

- **Release CI** — builds failed on newer setup-uv because `.venv` already existed (`uv venv --clear`).
