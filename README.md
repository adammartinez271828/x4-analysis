# X4 Analyzer

Savegame analysis and visualization for **X4: Foundations** (game v9.0). Point
it at your save and get a dark, tabbed HTML dashboard: an interactive sector
map, trade and income analytics for your empire, and a universe-wide market
analysis built to find and exploit gaps in the NPC economy.

Python port and major extension of Beamer Miasma's
[X4SaveGameAnalysis](https://www.reddit.com/r/X4Foundations/comments/11bkwbh/my_friends_say_i_take_the_game_too_seriously/)
R script (the original lives in this repo's git history). Where the R version
needed ~16 GB of RAM and several minutes, this parses a 1 GB savegame in one
streaming pass — seconds, a few hundred MB.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (one-command install, brings its
own Python). Then, without cloning anything:

```bash
uvx --from git+https://github.com/<your-account>/x4-analyzer x4-analyzer
```

Or from a clone (for development):

```bash
git clone <this repo> && cd x4-analyzer
uv sync
uv run x4-analyzer
```

Either way it finds your most recent savegame (Linux and Windows save
locations are auto-detected), analyzes it, writes
`output/dashboard_<guid>.html` in the current directory and opens it in
your browser. Dashboards are fully offline — no CDN dependencies. Useful flags:

```bash
uv run x4-analyzer --save ~/.config/EgoSoft/X4/<id>/save/quicksave.xml.gz
uv run x4-analyzer --spoilers-hide      # hide undiscovered sectors/objects
uv run x4-analyzer --no-browser
uv run x4-analyzer --x4-user-dir <dir>  # if your saves aren't auto-detected
```

Save locations: `~/.config/EgoSoft/X4/<player-id>/save/` on Linux,
`Documents\Egosoft\X4\<player-id>\save\` on Windows.

## The dashboard

| Tab | What's in it |
|---|---|
| **Map** | Interactive hex map of the galaxy: faction ownership, contested sectors, police/pirate activity overlays, per-sector resource ratings in tooltips. Handles all DLC sectors automatically. |
| **Trade** | Your empire's income/expenses over time: sales and buys by faction/seller/buyer, costs vs profits, station account transfers (hourly + cumulative). |
| **Trade Breakdown** | Sunbursts of recent sales and buys by commodity, station, and counterparty faction. |
| **Trade History** | Pick any of your stations or ships and browse its complete purchase/sale history — hourly volumes, per-commodity totals, and a searchable trade table with counterparties. |
| **Market** | Universe-wide per-ware economics: production/consumption capacity (including population food/meds upkeep), stock and cover, open buy demand in units and credits, construction material shortfalls, understocked-buyer counts, buyer-side Fill %, time-to-satisfaction/backlog depth, and best open prices. Ware detail shows exactly which stations to sell to or buy from (with prices, volumes and cargo m³), unmet demand by sector, and delivery trends — with a minimum-volume slider to skip dust-sized offers. |
| **Universe** | Sunbursts of the whole universe: station modules, ship hull mass, and faction activity per sector; sector resource distribution. |
| **Fleet** | Your fleet hierarchy as a drill-down sunburst. |
| **Tables** | Sortable earnings tables (per seller / per ware), recent losses, contested sectors. |

Numbers are reverse-engineered from the savegame; each analytical tab includes
a "how these numbers are computed & caveats" panel. Trade history accumulates
across runs in per-user cache files, preserving log data the game itself
discards — run the analyzer regularly to build long histories.

## Game data

The analysis needs reference data extracted from the game files (ships,
sectors, wares, recipes, localization). Data for **v9.0 + all official
DLC** ships inside the package, so you don't need anything besides your
savegame. After a game update, or to pick up mod-added ships, regenerate it
— the X4 installation is auto-detected via your Steam library:

```bash
x4-analyzer extract-gamedata                  # writes to your user data dir
x4-analyzer extract-gamedata --include-mods   # also scan mod extensions
```

Regenerated files (and the trade-history caches) live in a per-user data
directory (`~/.local/share/x4analyzer` on Linux, `%LOCALAPPDATA%\x4analyzer`
on Windows) and override the packaged copies.

## Notes

- Modded saves work — unknown ships/factions degrade gracefully rather than
  breaking the analysis (regenerate game data with `--include-mods` for full
  ship names).
- Log-text parsing assumes the English localization.
- Xenon stations are excluded from the Market tab: they hoard and consume but
  never trade.
- Development notes live in `CLAUDE.md`; run tests with `uv run pytest`.

## Credits

Original concept, R implementation, and much of the reverse-engineering of
the savegame format: **Beamer Miasma** (X4SaveGameAnalysis, for game v5.10).
X4: Foundations is © Egosoft — this is a fan-made analysis tool.
