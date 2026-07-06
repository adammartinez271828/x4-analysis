# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Savegame analysis and visualization for X4: Foundations. The active implementation is a **Python package** (`src/x4analyzer/`, uv-managed) that parses an X4 savegame XML and produces a static HTML dashboard (interactive plotly sector map, trade/sales time-series, sunbursts, sortable tables). It targets game **v9.0** and was ported from the original R script.

The original R implementation (`X4SaveGameAnalysis/X4SaveGameAnalysis.R`, for game v5.10) was removed from the working tree but lives in git history (deleted in the commit "Remove the original R implementation…"); the Python code still cites its line numbers in comments as the porting reference — `git show da10a2f^:X4SaveGameAnalysis/X4SaveGameAnalysis.R` retrieves it.

## Commands

```bash
uv sync                                  # create .venv and install deps
uv run x4-analyzer                       # analyze newest save -> output/dashboard_<guid>.html
uv run x4-analyzer --save <file> --no-browser --spoilers-hide
uv run x4-analyzer extract-gamedata      # regenerate game data (user dir; add --data-dir src/x4analyzer/data to update the committed copies)
uv run pytest -q                         # run tests
uv run pytest tests/test_caches.py -q    # run one test file
```

Dependencies are deliberately slim: lxml, pandas, plotly (+pytest dev). Do not add heavier deps (kaleido, matplotlib, jupyter) without asking.

## Machine-specific paths (defaults in `config.py`)

- Savegames: `/home/adam/.config/EgoSoft/X4/12073019/save/` (found by the platform-aware search in `config.x4_user_dir_candidates()`)
- Game install: `/games/SteamLibrary/steamapps/common/X4 Foundations` (auto-detected from Steam `libraryfolders.vdf`; only needed for `extract-gamedata`; official DLCs installed, plus ~60 mods — saves are `modified="1"`)
- Reference CSVs live IN the package (`src/x4analyzer/data/`, committed) so wheels/uvx work; the per-user data dir (`~/.local/share/x4analyzer`, `platform-dependent via config.user_data_dir()`) holds caches and extract-gamedata output, which override packaged files. To refresh the COMMITTED data, run `uv run x4-analyzer extract-gamedata --data-dir src/x4analyzer/data`

## Architecture

Pipeline (`analyze.py`): savegame → `saveparser.py` → `frames.py` → `viz/*` + `dashboard.py`.

- **`saveparser.py`** — ONE streaming `lxml.iterparse` pass over the (gzipped) save collects every record type (~18 s / 270 MB peak for a 73 MB .gz save; the R version needed ~16 GB). Component ancestry (cluster/sector/parent object) is tracked via explicit stacks. If you need new data from the save, add a handler here, not a second pass.
- **`frames.py`** — builds pandas dataframes mirroring the R `df.*` objects (same dotted column names, e.g. `seller.proxy.id`). Faithful port; R line refs in comments. All joins against reference data are defensive (unknown macro/faction → fallback, never crash) because saves are modded.
- **`caches.py`** — the game's log/economylog are rolling windows; caches (tab-separated `.csv.gz` keyed by game GUID in the user data dir) preserve history across runs. Merge semantics ported from R: log = per-category min-time replacement; tradelog = min-time cutoff. Must stay idempotent (re-running on the same save adds nothing).
- **`logparse.py`** — regexes over English log text (`[\012]` = literal newline marker). Localization/version sensitive; every parser returns an empty frame when nothing matches and downstream skips.
- **`gamedata.py` + `catalog.py` + `textdb.py`** — `extract-gamedata` reads the game's `.cat/.dat` archives (base + `ego_dlc_*` in load order, later wins; loose files override) and regenerates the reference CSVs including a full localization dump (`textdb.csv.gz`) used to resolve `{page,id}` refs in save names. The v9.0+DLC copies are committed inside the package so analysis runs don't need the game install.
- **`viz/`** — each widget is written as its own HTML file under `output/files/` sharing `lib/` assets (plotly + vendored jQuery/DataTables from `src/x4analyzer/vendor/` — dashboards are fully offline), embedded in the dashboard via iframes. The dashboard is **tabbed** (Map / Trade / Trade Breakdown / Trade History / Station P&L / Market / Audit / Universe / Fleet / Tables; vanilla JS, iframes lazy-load on first tab open) and **dark-themed** — theme constants live in `viz/common.py` and `save_widget()` applies them to every figure; keep new widgets dark (user preference). Tables use vendored DataTables. Chart legends/stacks are ordered by volume, largest first.
- **`viz/history.py` / `viz/market.py`** — self-contained interactive pages: trade data embedded as JSON, rendered client-side with a selector (per-object trade history; global per-ware market stats).
- **`viz/advisor.py` + `sectorgraph.py`** — Build Advisor tab: scores "build ware W in sector S" for every producible economy ware × known sector. Sector adjacency = `gates.csv` (extracted from galaxy.xml `ref="destination"` connections, sector macros regexed out of the zone paths) + same-cluster pairs; factors (demand, competition, input supply incl. mining yields, hostile distance, workforce food) are BFS-hop-discounted (÷(1+hops), radius 4), normalized per ware, weighted client-side with sliders (never an opaque score — each row expands into its reasoning). Buy-offer backlog counts as amount/24 per hour next to capacity rates.
- **`viz/audit.py` / `viz/pnl.py`** — empire bottleneck audit (input starvation, output pile-up, storage saturation via modcaps.csv, waiting constructions, idle ships from parsed order queues, staffing, crew gaps) and per-station P&L (trade attribution by station code incl. subordinate proxy; station value = module ware prices via wares.csv `component` macro link).
- **`viz/map.py`** — map x/y = galaxy x/z. Multi-sector clusters use slot patterns (`_SLOTS`) derived from real in-cluster offsets instead of R's hardcoded per-name adjustment lists, so DLC sectors place automatically. Axis ranges are R's fixed 5.10 ranges auto-widened when DLC content falls outside.

## v9.0 vs v5.10 divergences worth knowing

- Resource areas changed format: v5.10 had per-ware `recharge` attrs; v9 has `<area yieldid="sphere_large_ore_high_slow" yield="N">`. The ware is parsed out of the yieldid; "recharge" semantics became summed yield. There is consequently **no resource cache** anymore (`--force-refresh` is a no-op kept for compatibility).
- economylog `type="trade"` entries come in two flavors; only those with buyer+seller+price are real transactions (owner-only entries are ignored).
- `ship_xs` is a new component class (mapped to size XS, excluded from mass plots like R did).
- Fleet hierarchy: follower's `<connected connection="[X]">` ↔ commander's `<connection connection="subordinates" id="[X]">`. The flat `<subordinate>` elements in saves are the NPC job system — NOT player fleets.
- Ship construction/repair/resupply, destroyed-object, and surplus-transfer log parsing is ported verbatim from R but **unverified against v9 wording** (the test save contains no such events). If those dashboards stay empty on a save that should have them, check the actual log text first.
- Faction short codes come from game data (player is special-cased to `PLA`, ownerless to `NIL`, unknown/visitor factions bucket to `OTH`); colours keep the R palette for legacy factions, game colours for new ones.
- Subordinate→commander trade attribution (R's "proxy" logic) uses the fleet hierarchy **at save time** — the save has no historical assignments, so old trades can show under a commander the ship didn't have yet. The Trade History tab therefore tags such rows ("Executed by") and has a toggle to disable the redirect; keep that pattern in any new per-object views. (Fun fact: the save's group assignment attribute is spelled `assignmment`.)
- Market tab data semantics (all reverse-engineered, validated against this save):
  - The owner-only economylog `<log type="trade" owner ware v>` events record the station's **stock level after each trade**, NOT a trade amount — traded volume must be derived from positive deltas between consecutive snapshots per (owner, ware) (`frames.global_trades["dv"]`). Summing `v` directly overcounts ~40x.
  - Consumption capacity = module recipe inputs + population needs. Workforce upkeep is the game's per-race `workunit_busy` recipes in wares.xml (200 workers consume e.g. 75 foodrations + 45 medicalsupplies per 600 s). DLC adds race methods (terran/boron/split) via **diff patches inside existing wares** — `extract_recipes` must scan `<add sel="...ware[@id=...]">` blocks, not just `<ware>` elements (missing this overcounted Terran energy production 3.5x).
  - Build demand = the build storages' open **buy offers** (`<trade buyer= ware= amount=>` under `<offers>`). The `<insufficient>`/`<shortage>` amounts under `<build><resources>` are NOT per-ware quantities (in-game cross-checks disproved them — wrong amounts AND wares the build doesn't need); `build_resources` is still parsed but must not be used for demand. New-station constructions sit on **free-floating build storages with no station ancestor** — don't require an object ancestor when collecting.
  - Construction-plan estimating (Audit tab, for sites with no funded orders): the plan lives on the build storage under `<queue><build type="expand"><sequence><entry>`; an existing station's own `<construction><sequence>` repeats the SAME entry ids, so dedupe by entry id. A built module's component carries `construction="[entryid]"` — but `state="construction"` means still building and its materials still count (treating it as built made estimates come in low by exactly one module's recipe). Estimate = Σ default-method recipes of unbuilt entries (module ware found via wares.csv `component` == macro) + loadout equipment from `<shields>/<turrets>/<engines>` groups in entries, minus wares already in site cargo. Validated within ~1% (WJL-290 claytronics exact) against in-game "required" figures, which are gross of delivered cargo and pro-rate partially built modules.
  - Understocked = buyers (open `<trade buyer= amount=>` offers under `<offers>`, plus build hosts) holding < 25% of target level (stock + wanted). Fill % = buyer-side Σheld/Σ(held+wanted); Satisfy (h) = (buy+build demand)/production surplus, with a ≥gap/deliveries fallback when there is no surplus.
  - Capacity excludes workforce production bonuses; Cr/h values volume at average game price (universe events carry no prices).

## Gotchas

- pandas `itertuples()` mangles the dotted column names — use `iterrows()` or positional access when a loop touches columns like `sector.id`.
- Money in save files is in cents; divide by 100 (trade `price`, log `money`).
- Macros are lowercased at every boundary (save values vs game-file values differ in case).
- `spoilers_hide` must be honored by any new visualization (hides undiscovered sectors/objects and the resource sunbursts).
- Warnings in a run are fine; errors are not (same convention as the R original).
