# Changelog

## Unreleased

### New User Features

- **Build advisor: a "Modules" column replaces the score** — the Score column and the five weight sliders are gone. The score was never the cross-ware ranking that the default sorted-by-score view made it look like: every factor behind it was normalized *per ware* — each sector divided by the best sector for that same ware — so a ware oversupplied in every sector you can reach still produced a 1.0 leader, and rows with a **negative** shortfall sat near the top of the page. Every row now carries **Modules** instead: the nearby shortfall divided by what one production module of that ware actually makes per hour, signed, to one decimal. +20.2 means the gap within 4 gates would keep twenty production modules busy (Computronic Substrate in Brennan's Triumph, on a live save); −0.1 means the neighbourhood already makes slightly more than it consumes. The table opens sorted by **Untapped Cr/h** descending — that column and Modules are in real units (credits, modules) and are therefore the two figures on the page that *can* be compared across wares; demand, competition and input supply are still per-ware readings, so pick a ware in the filter before reading those against each other. The **estimated actual flows** box now starts checked, so the page opens on what the economy is really doing rather than on nameplate capacity; untick it for the old capacity view. What it does not know: the yield is the ware's **default** recipe — not your faction's build method, not a closed-loop variant, not adjusted for workforce bonuses — so read Modules as the size of the gap rather than as a build order; and the actual-flow estimates under-read any station that is kept smoothly supplied, because the game only records a station's stock when a trade touches it. The ten most promising sectors per ware are still chosen server-side by the old fixed weights; what is gone is a number that invited comparing one ware against another when it could not.
- **Trade → Routing: how long from here to there, for any ship and any two stations** — a new sub-tab next to Trade Opportunities that answers the question the lane table cannot: pick one of your ships and an origin (a station, or the selected ship's current location) and every station in the save is listed with the gate **jumps**, the real one-way **route length** in km — measured through the actual station and gate positions along the time-optimal path, not hop-counted — and the estimated **voyage time** for that ship. Sorted by time, so the nearest destinations come first; the "To" selector narrows it to a single pair, and both selectors are grouped by sector with a filter box for finding a station by name. Every hull is pickable, not just the traders: fighters, miners and carriers all get their real loadout travel speed. No prices and no cargo — this is deliberately the travel half of Trade Opportunities, sharing the identical route graph and time model (same dock-time, travel-drive-ratio and highway controls, same defaults), so the two panes can never disagree about how long a run takes. What the model does not know is spelled out on the page: gate and superhighway transits count as zero time, one-way gates are treated as two-way, and a free-flying ship is only known to the save by its sector, so its position is approximated by the sector centre (a docked ship uses its host station's exact position).
- **Empire → Standings: your standing with every faction, over time** — a new chart under the standings table draws one step line per faction from the game log's own reputation entries. Every step is a hard reading, not a reconstruction: each "Reputation gained/lost" entry records the exact −30..+30 rank *after* the change, so the line is what the game showed you at that moment, and the legend lets you isolate the factions you care about (they start ordered by how strongly they feel about you). The subtitle states how far back the history reaches — the game's logbook is a rolling window, so early history exists only for the stretches the analyzer has already imported (run `seed-trends` over your archived saves to fill it in), and any gap in that coverage is spelled out rather than drawn through. There is deliberately no "which activity earned me this rank" breakdown: the game omits a number from most reputation entries, so any such split would be a guess rather than a measurement.
- **Empire audit: scrap-processing throughput** — the Raw resource supply section gains a **Scrap processing** card block for every station with a Scrap Processor (or any other processing module, including modded ones): how much feedstock actually arrives per hour against what the modules could eat, as a coverage bar — one live station reads 8,374 of 9,000 Raw Scrap/h, 93% of capacity — plus how many salvage ships are assigned, how much scrap is drifting in that sector, and whether the station makes the energy cells its processors need (90,000/h for one Scrap Processor). Capacity comes from the module's own batch scale and recipe, so it is right for any processing module. The card is explicit about what it can and cannot know: the game records no production events and no live state for processing modules and their output never leaves the station, so utilization is measured on the intake side only — deliveries in the trade log against recipe capacity.

### Fixes

- **Objects in the map's zones are finally where the game puts them** — reported by a user who found an Erlking data vault nowhere near the spot `x4-analyzer find` sent them to. Almost everything in a sector sits inside a *zone*, and a savegame never writes down where a fixed zone is: it says "no offset stored here" and leaves the real number in the game's own map files. The analyzer read that as "this zone is at the middle of its sector", so every station, data vault, derelict and wormhole in one was drawn as if its zone sat at the sector's centre — 100–190 km off for the Erlking vaults, and up to 675 km for a station on a live save — while the gates around them (which were already read from the game files) sat correctly. Three of the five Erlking vaults move: WZH-227 in Avarice IV from (−5.1, 17.4) to **(−120.9, −78.7) km**, BUZ-095 from (34.6, −17.9) to **(145.0, −10.6)**, FKU-105 in Avarice V Dead End from (25.3, −36.6) to **(−159.1, −40.0)**; the other two were already right, because the zones they sit in are the temporary kind, which *does* record its position in the save. The analyzer now reads the zone offsets straight out of the installed game (a new `zones.csv` alongside the other reference data, regenerated by `extract-gamedata`), so the sector map places stations, vaults, derelicts and wormholes against the gates correctly, and the distances that Trade → Routing and Trade → Opportunities quote — and the Build Advisor's "≈ Traders" counts, which are computed from them — are measured between the real positions. Nothing is cached: the next analysis of any save fixes itself. A zone the reference data has never heard of (a modded sector, or a game patch newer than your last `extract-gamedata`) still falls back to the sector centre, and now says so once per run instead of quietly misplacing things.
- **Raw resource supply: rates no longer count trades from the future** — the observed-inflow window had a start but no end, while the trade history spans every save ever imported. Analysing an older save after a newer one (or after `seed-trends` walked your archive) therefore counted deliveries that happen *later* than the save being looked at, inflating every raw-supply figure — one live run read raw scrap arriving at 148% of the station's processing capacity where the true, clamped answer is 84%. The window now ends at the loaded save's own game time, for both the rate and the window length.
- **Empire audit: "starving for inputs" now knows what the station makes itself** — the section measured hours of cover as stock ÷ gross consumption, so an input the station produces on site (energy cells at a solar-panel station, hull parts at a self-supplying wharf) was permanently listed as STALLED — it holds no stock because it is consumed as fast as it is made. Each row now shows **Produces/h** beside Consumes/h and a **Net status** that nets the two: self-supplied inputs are called out as such (worded carefully — the module producing them can still be starved in turn), and everything else reports the hours left against *net* demand. A new checkbox (off by default) hides the self-supplied rows. The listed rows and their order are unchanged. Wares the station never stores at all — processor feedstock such as raw scrap, which scrapers deliver straight into the processing module — are no longer listed, removing the permanent "raw scrap STALLED" noise on every scrap station.
- **Empire audit: the tables no longer hide most of their rows** — every table on the Empire audit page (idle ships, crew gaps, starving inputs, storage, constructions, staffing) was paginated at 10 rows while the section heading counted them all, so a heading reading "Idle ships (37)" over a ten-row table looked like the analyzer had capped the list. Tables now show 25 rows per page and carry a length selector (10 / 25 / 100 / All).
- **Trade charts: hover shows the full ship/station label** — the stacked bar/area charts under Trade → Charts (and the faction/station charts built from the same helpers) truncated the trace name in the tooltip at plotly's default 15 characters, cutting off exactly the in-game code appended to each seller/buyer name (`Fulmekron (…`). Name truncation is now disabled, so the whole `Name (CODE)` label is readable.
- **Trade → History: the hourly bars are readable again** — the cumulative-net line grows to hundreds of millions of credits while an hour's trading is a fraction of that, and both shared one y-axis, so the bars were flattened to nothing. The cumulative net now has its own right-hand axis and the hourly sales/buys bars scale to themselves.
- **Trade → History: no more missing commodity labels** — the "By commodity" chart had a fixed height, so for an object trading more than about eight wares plotly silently dropped every other label and you could not tell which bar was which. The chart now grows with the number of wares (and the panel grows with it), so every commodity is labelled.
- **Market → Overview: the "Ware detail" dropdown is alphabetical** — it used to inherit the Cr/hr ranking of the summary table above it, which made finding a specific ware a hunt. The dropdown now sorts case-insensitively by ware name; the table and charts keep their Cr/hr ordering, and the initially selected ware is still the top earner. The advisor page's ware filter was aligned to the same case-insensitive sort.

## 1.4.1 — 2026-08-02

### New User Features

- **`x4-analyzer --version`** — the analyzer can finally tell you which version it is, in every distribution form (standalone binaries, `uvx`, source). Useful when reporting a problem.
- **Versioned download names** — release files now carry the version in the filename (`x4-analyzer-1.4.1-windows.zip`, `x4-analyzer-1.4.1-linux`), so it's obvious which build a downloaded file is.

### Fixes

- **Windows download reworked to stop Defender's false "Trojan:Win32/Sabsik" alarm** — the 1.4.0 Windows EXE was flagged by Windows Defender's machine-learning classifier. The build was a single self-extracting EXE that unpacked tens of MB of libraries to a temp folder at every launch — mechanically the same behaviour the classifier is trained to score as a malware dropper, and a brand-new unsigned binary with no version metadata starts from a bad prior. The Windows build is now an app folder shipped as `x4-analyzer-1.4.1-windows.zip` (extract completely, then run `x4-analyzer.exe` inside — a README in the zip says so too): nothing self-extracts at runtime, and the bundled libraries are the same well-known files thousands of Python apps ship, each scanned on its own reputation. The EXE also carries a proper version-info resource, UPX compression is explicitly off, and the PyInstaller version is pinned so the bootloader bytes can't silently change between releases. The Linux single-file binary is unchanged. Only code signing can remove the separate SmartScreen "unknown publisher" prompt; if Defender still complains about a future build, it should be reported at https://www.microsoft.com/en-us/wdsi/filesubmission — that clears the verdict for everyone within days.
- **No more startup crash when older game-data files are lying around** — if you ran `x4-analyzer extract-gamedata` under an earlier version, its output in your data folder was still being used by 1.4.0, which needs columns that older extracts don't have; analyzing a modded save (most saves) died immediately with `KeyError: 'work_effect'`. Out-of-date files are now detected, ignored with a warning that names the file and tells you to re-run `x4-analyzer extract-gamedata`, and the analyzer falls back to the reference data bundled with it — so it runs correctly either way, and re-extracting picks your own data straight back up. Newer-than-expected files (extra columns) keep working as before.

## 1.4.0 — 2026-08-01

### Fixes

- **Database upgrades no longer strand or rebuild your history** — the analysis database now migrates in place along a complete version chain: the old hand-written migration map stopped at v4, so any real database (v5+) fell off the chain and a version bump meant rebuilding from scratch. The save index and settings are now never dropped, the cross-run event history (trades, log, stock movements, trends) survives every upgrade, and leftover tables from old versions are cleaned up on the way through. A 1.3.0-era database opens under 1.4.0 and walks the whole chain (v13 → v30) with its history intact.
- **Estimated actual flows were near-zero on multi-session databases** — the stock-event history is recorded under each save's runtime object ids, which the game reshuffles on every load; the analyzer joined them against the current snapshot's ids, so on a database built from many play sessions almost the entire history silently missed and the Build Advisor's / Market tab's "estimated actual flows" read ~0 production for everything. The stream is now resolved through the entity registry (the analyzer's durable ship/station identity), and a snapshot no longer sees flow events newer than itself when an older save is re-analyzed.
- **Linux binary: browser launch no longer crashes kde-open/xdg-open** — the one-file build exported PyInstaller's `LD_LIBRARY_PATH` (with the build machine's older libstdc++) into the browser-opener process, which aborted with `GLIBCXX` version errors on newer distros (reported on Bazzite). The original environment is now restored before the browser is launched.

### New User Features

- **Diplomacy views** — faction relations are now surfaced from the savegame, split by whose perspective they answer. **Empire → Standings**: your empire's standing with every faction as a sortable table — a diverging −30..+30 rep bar, the rank (Ally/Friend/Neutral/Enemy/War), the trade discount each faction grants you, how many licences you hold with them, and your treasury. **Universe → Relations**: the whole galaxy's diplomacy as a directional faction×faction heatmap (green = allied, red = hostile), with war/ally cells outlined, your row/column highlighted, and a hover that shows both directions (relations aren't always symmetric). Effective standing is the active booster when one exists (the game persists it at its current decayed value — it *replaces* the base relation, it is not added to it), else the base relation; the −30..+30 rank uses the game's own formula. The composition was validated against in-game readings after the additive first guess predicted −21 for a faction the game shows at +22. How it all decodes is written up in `docs/models/faction-relations-model.md`.
- **Wormholes on the map** — a new **Wormholes** overlay marks every anomaly in the galaxy. The save encodes each one's partner directly (a connection-id cross-link), so **active** warp points (violet ring) are drawn joined to their exit by an arrowed link showing which way you travel — including the two-way pair in Freedom's Reach and the Avarice V Dead End → Unknown System link. **Dormant** story warps (a dashed ring; the Tide of Avarice points whose destination the game only assigns mid-mission) and **random** wormholes (a dim dot — the common "Unstable Warp Anomaly": flying in drops you at another random wormhole, so the save has no destination to draw; player-verified) are distinguished. Spoiler mode hides undiscovered wormholes and any link that would reveal one. How the connections are decoded is written up in `docs/models/wormhole-connection-model.md`.
- **One-way superhighways on the map** — superhighways are directional tubes; a normal accelerator has one each way, but the galaxy has a single **one-way** superhighway (Savage Spur I → II). `gates.csv` now records superhighway direction (`oneway` column, set when a `sechighways` connection has no reverse), and the map draws a midpoint **arrowhead** pointing the way traffic flows. Two-way links and jump gates are unaffected.
- **Derelict ships on the map** — a new **Derelict Ships** overlay marks every ownerless (claimable) hull in the galaxy: amber diamond-X markers with a hover showing the ship model, code, size, sector, and origin — **crew bailed** (solid marker, with when it appeared) vs **pre-placed at game start** (dimmed hollow marker; confirmed against a fresh-start save — all 15 of its untouched pre-placed derelicts carry the game-start signature). The legend row carries bailed/total counts; spoiler mode hides derelicts you haven't discovered. The parser now records sector-local positions for ownerless ships so the markers sit where the wrecks actually drift.
- **Ship losses on the map** — a new **Ship Losses** overlay marks every sector where you've lost a ship, from the analyzer's full loss archive (which reaches further back than the game's own rolling log): one crimson X per sector, modestly sized by how many died there, with a hover showing the count, a killed-by-faction tally, and the most recent losses (ship, killer, hours ago). Default hidden, legend row carries the total.
- **Kills & losses (Empire → Combat)** — a new sub-tab answering "what has my empire killed, captured, and lost". The **personal combat record** reads the save's own lifetime counters (ships/capital/Xenon/Kha'ak kills, modules and turrets, boarding attempts/successes, ships claimed, pilots forced to bail, fight rank) — these count *your personal actions only*, not your fleet's (established during development: the fleet's bounty-paid kills alone exceed the ships-destroyed counter), and the page says so. **Losses** lists every ship you've ever lost (the analyzer's archive outlives the game's rolling log) with location, killer, and a losses-by-killer-faction summary — replacing the old "Last 50 Destroyed Objects" table under Trade. **Bounty-confirmed kills** attributes kills per ship the only way the game records them: faction bounty payouts credited to named ships (count, credits, paying factions) — unwitnessed kills exist only in the aggregate counters, and the page is honest about that. **Captures & claims** lists abandoned ships found/claimed and pilots your forces forced out of their cockpits.
- **Build advisor: trade-fleet sizing** — the advisor now answers "and how many traders will that station need". Each row carries **Haul m³/h** (the shortfall volume you'd have to move to capture the Untapped Cr/h — it follows the estimated-actual-flows checkbox) and **≈ Traders**: how many of a selected ship it takes, using your real haulers (loadout travel speed and hold) and the row's real demand-weighted route distance over the same router the Opportunities lanes use. The ℹ detail gains a Logistics block: average route km (plain vs highway), the per-ship math, and the input haul per production module for the supply side. Stated assumptions: routes measure from the sector centre, no docking overhead — treat the trader count as a floor.
- **Earnings: internal trades toggle** — the Trade → Earnings tables (per Seller, per Ware) count external trades only, by design; a new checkbox adds your empire's **internal** trades (station miners delivering to their own station, inter-station transfers) to see e.g. how much Silicon your empire really moves. Off by default, so the familiar numbers are unchanged; internal deliveries attribute to the supplying commander like everything else.
- **Sector names across the Empire tab** — every audit section, Station P&L, and the crew/idle tables now name the sector each station or ship is in (sortable column); the raw-resource-supply cards carry it in the card header, and the Fleet sunburst shows each ship's *current* sector on hover — subordinates deep in a fleet can sit far from their commander. Audit sections are also regrouped: station findings first, ship findings (idle ships, crew gaps) together at the end.
- **Empire audit refinements** —
  - **Storage-aware miner advice**: the raw-resource-supply cards no longer recommend "+N miners" when a station physically can't accept more — a pool whose consumed wares all sit at ≥95% of a trusted storage ceiling (manual buy limit, manual allocation, or the modelled allocation) is flagged "storage full" instead and doesn't count as a finding; the per-ware fine print shows stock against its ceiling. A zero buy offer alone is deliberately *not* treated as full — in-flight deliveries zero the bid on stations that are nowhere near full.
  - **Constructions waiting for materials**: sites get a Sector column and concise "Likely *station* (CODE)" labels; inactive sites whose build plan is already fully delivered are no longer listed.
  - **Storage saturated**: threshold lowered to 80%, and each row shows **Hours to full** at the station's own net production rate (soonest first). The separate "Output piling up" section is retired — a filling storage class covers it.

### Internal

- **Station storage & pricing reverse-engineered end to end** — the release's research arc: how a station sizes each ware's storage allocation (hours-of-throughput per transport pool, with the degenerate equal-volume split for non-producers) and how it prices wares (band average ± a cosine in storage fill, flat modifiers on top, reputation discount at display time). Both are implemented (`analysis/storage.py`, `analysis/pricing.py`), exposed as queryable tables/views, written up as model docs (`docs/models/station-storage-model.md`, `station-pricing-model.md`), and validated against hundreds of in-game readings.
- **Experiments register** — every reverse-engineered claim now lives in `docs/experiments/README.md` with a stable id, status (confirmed/falsified/pending/superseded) and the evidence that set it, enforced by a structural test. 1.4.0 ships with 149 entries.
- **Schema v13 → v30** — the database grew a trend layer (per-snapshot aggregate history), committed in-flight trades (the price curve's pending term), station self-supply bookkeeping, manual per-ware limits and reference prices, resolved build methods, the engine's own per-module production multipliers, build tasks, scan levels, trade whitelists, price bands in the reference data, and the lifetime player-stats block — with fixes along the way for an entry-id collision that double-counted shared station plans and a zombie-table cleanup. All of it migrates in place (see Fixes).

## 1.3.0 — 2026-07-21

### New User Features

#### Sector Map Updates

- **Data-vault overlays** — regular vaults (cyan stars) and Erlking vaults (gold stars) at every zoom level, showing opened vs unopened state and, on hover, code / status / blueprint; legend labels carry opened/total counts.
- **Player station markers** — zoomed in, each player station shows a marker with a name/code tooltip.
- **Highways on the map** — **Superhighways** and local **ring Highways** as their own Base Map toggles, drawn along their true spline tracks; gate lines now attach at the actual gate positions rather than zone centres.
- **Resource overlay redesigned** — the whole-hex tint that washed out busy sectors is gone. Each selected resource now draws **percentile edge gauges**: **mineable-now** up the left hex edges and **max replenishment rate** up the right edges (a half-full gauge = the median sector), so "empty but replenishing fast" reads distinctly from "full but slow to come back". The sector detail panel lists **every resource field** in a collapsible dropdown — current / capacity, gatherspeed, and a respawn ETA for depleted fields — with respawned ("overdue") fields correctly shown as full. Resources render regardless of which factions are selected.
- **Defaults** — gate/superhighway/highway routes on by default; Kha'ak stations off.

#### Trade Opportunities

- **New Opportunities view** — the Trade tab now opens on **Opportunities**: ranked buy-here → sell-here **lanes** per ware, with per-ware "buy here / sell here" offer charts and top trading stations. Click a lane to jump the charts to its ware.
- **Real trip economics from your own ships** — each lane's profit-per-hour is built from your player trade ships' **loadout travel speed** and the lane's **actual route length** (station and gate positions along the gate-graph path, split into plain vs local-highway km), plus dock time — not a flat estimate.
- **Controls, as cards** — ware filter, ship preset (its cargo hold and computed travel speed shown read-only), adjustable **travel drive ratio** and **average highway speed**, per-ship-size dock time, and a **sell-player-reserve-stock** mode. Sort by Cr/h; **Distance (km)**, **Time**, and depth-capped **Depth Cr** columns.
- **Documented assumptions** — the "what these lanes mean and caveats" note explains what each control does to the model.

#### Universe Charts

- **Total Sector max replenishment per Resource** — a new sunburst on the Universe → Overview tab, companion to "Total Sector resources per Resource": each resource ring is subdivided by each sector's share of that resource's theoretical maximum replenishment rate (Σ capacity ÷ respawndelay, units/h).

#### Dashboard Layout

- **Five question-shaped tabs** — the dashboard is reorganized into a two-level layout (Map / Trade / Empire / Market / Universe) with sub-tab pills; the active view and sub-view persist across reloads.

### Internal

- **Resource respawn model** — the parser now captures each resource area's respawn-eligibility clock (`starttime`, schema v7) alongside its yield/level/gatherspeed tokens, and `extract-gamedata` pulls `regionyields.xml` and gatherspeeds into new reference CSVs. The reverse-engineered v9 depletion/respawn mechanic — areas deplete under mining, respawn whole once past `respawndelay`, and the stored yield materializes on the next miner contact — is documented in `docs/models/resource-depletion-model.md`, validated by an in-game experiment.

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
