# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Savegame analysis and visualization for X4: Foundations, game **v9.0**: a Python package (`src/x4analyzer/`, uv-managed) that parses an X4 savegame XML into a per-playthrough SQLite database and a static HTML dashboard (interactive sector map, trade time-series, sunbursts, sortable tables). Ported from an R script (game v5.10 era); the original was removed from the working tree but lives in git history — `git show da10a2f^:X4SaveGameAnalysis/X4SaveGameAnalysis.R` retrieves it — and the Python code still cites its line numbers in comments as the porting reference.

## Commands

```bash
uv sync                                  # create .venv and install deps
uv run x4-analyzer                       # analyze newest save -> output/dashboard_<guid>.html
uv run x4-analyzer --save <file> --no-browser --spoilers-hide
uv run x4-analyzer extract-gamedata      # regenerate game data (user dir; add --data-dir src/x4analyzer/data to update the committed copies)
uv run x4-analyzer gamedata-dashboard    # game-file analysis (no savegame) -> output/gamedata_dashboard.html
uv run x4-analyzer find                  # locate objects in a save (default: the 5 Erlking data vaults)
uv run x4-analyzer find --macro '^landmarks_'   # any macro regex
uv run pytest -q                         # run tests
uv run pytest tests/test_store.py -q     # run one test file
```

## Machine-specific paths (defaults in `config.py`)

- Savegames: `/home/adam/.config/EgoSoft/X4/12073019/save/` (found by the platform-aware search in `config.x4_user_dir_candidates()`; note the capital-S `EgoSoft` — naive lowercase-`Egosoft` matching misses it).
- Game install: `/games/SteamLibrary/steamapps/common/X4 Foundations` (auto-detected from Steam `libraryfolders.vdf`; only needed for `extract-gamedata`; official DLCs installed, plus ~60 mods — saves are `modified="1"`).
- Reference CSVs live IN the package (`src/x4analyzer/data/`, committed) so wheels/uvx work; the per-user data dir (`~/.local/share/x4analyzer`, platform-dependent via `config.user_data_dir()`) holds the analysis database (`x4_<guid>.sqlite`) and extract-gamedata output, which override packaged files.

## Architecture

Pipeline (`analyze.py`): savegame → `save/parser.py` → `db/store.py` → `analysis/frames.py` → `viz/*` + `viz/dashboard.py`. Subpackages mirror the stages: `gamedata/` → `save/` → `db/` → `analysis/` → `viz/`; `cli.py`/`config.py`/`analyze.py` stay top-level.

- **`save/parser.py`** — ONE streaming `lxml.iterparse` pass collects every record type (~18 s for a 73 MB .gz save), tracking ancestry with explicit stacks. New save data means a new handler here (see Conventions).
- **`save/landmarks.py` + `save/find.py`** — the `find` subcommand: a small separate sweep that keeps the zone offset chain the main parser deliberately drops.
- **`save/logparse.py`** — regexes over English log text; localization/version sensitive, empty frame when nothing matches.
- **`db/`** — world snapshot + reference data + cross-run event history and the entity registry in `x4_<guid>.sqlite`; views recreated at connect.
- **`analysis/frames.py`** — pandas frames mirroring the R `df.*` objects (same dotted column names); defensive joins throughout.
- **`gamedata/`** — `.cat/.dat` extraction into the committed reference CSVs + the weapon/gamedata dashboard models.
- **`viz/`** — per-widget HTML files in iframes under a dark, two-level tabbed dashboard; the sector map and diplomacy views are self-contained SVG/JS pages.

**Doc map** — `docs/reference/` is the source of truth; read the relevant page before working on a subsystem:

- [architecture.md](docs/reference/architecture.md) — parser/frames/db/gamedata internals, the `find` sweep, log parsers, reading game files directly.
- [savegame-structure.md](docs/reference/savegame-structure.md) — the save XML format. [db-schema.md](docs/reference/db-schema.md) — every table/view, merge semantics, the entity identity model. [csv-reference.md](docs/reference/csv-reference.md) — the extracted CSVs and extraction machinery.
- [save-semantics.md](docs/reference/save-semantics.md) — reverse-engineered meanings: market data, identity/code recycling, the pricing model, the drone pool.
- [viz-internals.md](docs/reference/viz-internals.md) — dashboard shell, sector map, opportunities/advisor/audit/P&L, diplomacy, weapon sim.
- `docs/models/` — verified game-mechanics models (resource-depletion, faction-relations, wormhole-connection). `docs/plans/` — live plans and the extraction-candidates backlog.

## Conventions

- Dependencies stay slim: lxml, pandas, plotly (+pytest dev). Ask before adding heavier deps (kaleido, matplotlib, jupyter).
- Saves are modded — be defensive everywhere: joins against reference data fall back on unknown macro/faction/ware (never crash), the DB loads permissively ("" → NULL, no FK enforcement). Warnings in a run are fine; errors are not (same convention as the R original).
- New data from the save = a new handler in `parser.py`'s single pass — never a second sweep (`landmarks.py` is the one deliberate exception, kept out of the hot path).
- DB event merges must stay idempotent: re-running on the same save adds nothing.
- Every widget is dark-themed via the constants in `viz/common.py` (`save_widget()` applies them); keep new widgets dark (user preference — dark grey, not pure black).
- `spoilers_hide` must be honored by any new visualization (hides undiscovered sectors/objects); no hidden names may reach an emitted page.
- JS page templates (`viz/map_page.js`, `viz/diplomacy_page.js`) are inlined at build time with tokens substituted via `str.replace` — never f-strings.
- DataTables `ext.search` filters must guard on the table id — pages can host two tables.
- Per-object trade views keep the "Executed by" proxy-attribution pattern: subordinate trades redirect to the save-time commander, tagged, with a toggle to disable.
- Reverse-engineered claims separate CONFIRMED from hypothesis — never overclaim (e.g. don't assert per-station constants are stable across saves without proof). In-game-validated reference numbers live in the tests (`test_weaponsim.py`, `test_drones.py`, `test_storage.py`, `test_map_prep.py`); when touching a model, revalidate against them.
- New tracked docs go in a `docs/` subfolder (`reference/`, `models/`, `plans/`); loose `docs/*.md` files are gitignored scratch.
- Commit finished, verified work locally without asking; when a deliverable goes through interactive review, batch the whole revision round into one commit. Never `git push` (or push tags) until explicitly asked.

## Gotchas

- **Identity**: none of the game's own fields is a GUID — runtime ids (`[0x..]`) remap on every load, names change on rename, owners on capture, and codes (`ABC-123`) are recycled after death. The entity registry (`entity` table) mints surrogate `entity_id`s; key cross-run analysis on those, fall back to codes only among simultaneously-alive same-faction objects, and never key on names. Full model: [db-schema.md](docs/reference/db-schema.md), [save-semantics.md](docs/reference/save-semantics.md).
- Stations list their build plan TWICE in the save (construction sequence + expand queue repeat the same entry ids) and sequences include unbuilt entries: anything measuring existing capacity/storage/value must use `frames.built_modules` / `v_built_module`, never `station_modules` (pre-fix hull-parts "capacity" was nearly 2× reality).
- pandas `itertuples()` mangles the dotted column names — use `iterrows()` or positional access when a loop touches columns like `sector.id`.
- Money in save files is in cents; divide by 100 (trade `price`, log `money`, player money).
- Macros are lowercased at every boundary (save values vs game-file values differ in case).
- ships.csv `cargo` is hold VOLUME in m³, not units: divide by the ware's `volume` (ore = 10 m³ ⇒ an 8,800 m³ Bolo carries 880 ore).
- The game's log/economylog are rolling windows — history the game discarded survives only in the DB's event tables.
