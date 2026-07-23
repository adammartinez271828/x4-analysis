# Architecture: pipeline and subsystem internals

The deep-dive companion to CLAUDE.md's overview: how the parsing, analysis
and data layers work internally. Formats live in their own references —
[savegame-structure.md](savegame-structure.md) (save XML),
[db-schema.md](db-schema.md) (database), [csv-reference.md](csv-reference.md)
(extracted game data); reverse-engineered meanings in
[save-semantics.md](save-semantics.md); rendering in
[viz-internals.md](viz-internals.md).

Pipeline (`analyze.py`): savegame → `save/parser.py` → `db/store.py` →
`analysis/frames.py` → `viz/*` + `viz/dashboard.py`. Subpackages mirror the
stages: `gamedata/` (game-file extraction + reference data) → `save/`
(parsing) → `db/` (SQLite store) → `analysis/` (dataframes) → `viz/`
(widgets + dashboard); `cli.py`/`config.py`/`analyze.py` stay top-level.

## save/parser.py — the single streaming pass

ONE streaming `lxml.iterparse` pass over the (gzipped) save collects every
record type (~18 s / 270 MB peak for a 73 MB .gz save). Component ancestry
(cluster/sector/parent object) is tracked via explicit stacks; each stack
frame also keeps the component's own `<offset><position>`, so stations and
build plots get sector-local sx/sz (interposed zone offsets summed in — the
landmarks.py chain, folded into the single pass). The station attribute
`factionheadquarters="1"` (one station per faction, where its representative
sits) is captured.

Data vaults are collected in the same pass, matched on macro
`landmarks_(erlking_)?vault_*` — the classes differ: regular vaults are
`datavault`, Erlking ones `object`. Opened = child
`<unlock state="unlocked"/>`; uncollected loot = collectablewares /
collectableblueprints child components, whose `blueprints=` values are ware
ids. Wormholes/anomalies are likewise collected here (every
`class="anomaly"` plus its warp links — see
[../models/wormhole-connection-model.md](../models/wormhole-connection-model.md)).

If you need new data from the save, add a handler here, not a second pass
(the Conventions rule in CLAUDE.md).

## save/landmarks.py + save/find.py — the `find` subcommand

A small SEPARATE iterparse sweep (~17 s) that locates components by macro
regex and reports sector-relative km coordinates — a reimplementation of the
community "Erlking data vault locator" batch script (forum p5116566). It
keeps its own offset chain because positions in a save are parent-relative
(galaxy → cluster → sector → zone → object, any link possibly
`<offset default="1"/>` = zero) and summing from the sector down gives the
coordinates the in-game map shows — `parser.py` deliberately drops both
zones and positions, so this stays out of the hot path.

Pickup contents (`blueprints=` on child components) are captured at the
CHILD's end event, before the parent's end clears them; a vault whose
blueprint is already collected simply has no such child. Sector/ware names
come from sectors.csv / wares.csv, not a hardcoded table (the forum
script's table shipped with two Avarice sectors swapped).

## save/logparse.py — log-text parsers

Regexes over English log text (`[\012]` = the literal newline marker).
Localization/version sensitive; every parser returns an empty frame when
nothing matches and downstream skips. Rows whose title matches a parser but
whose text does not fit the expected wording are skipped with a warning
that dumps sample strings — report those so the parser can be fixed. The
ship construction/repair/resupply, destroyed-object, and surplus-transfer
parsers are ported verbatim from R but **unverified against v9 wording**
(see [save-semantics.md](save-semantics.md)).

## analysis/frames.py — the dataframe layer

Builds pandas dataframes mirroring the R `df.*` objects (same dotted column
names, e.g. `seller.proxy.id`). Faithful port; R line refs in comments are
the porting reference. All joins against reference data are defensive
(unknown macro/faction → fallback, never crash) because saves are modded.

## db/ — SQLite store

Every parsed record also lands in `x4_<guid>.sqlite` (user data dir): world
state rebuilt per snapshot, reference data replaced wholesale, event
history (trade_tx / stock_event / log_entry / removed_object) merged across
runs with save-stable identity and coverage epochs, plus the entity
registry. Views (`v_universe`, `v_fleet`, `v_stock_delta`, …) are recreated
at every connect. [db-schema.md](db-schema.md) is the complete reference —
tables, columns, the merge semantics (log = per-category min-time
replacement; tradelog = min-time cutoff — ported from R and still the
spec), idempotency, the entity identity model, and the retired csv.gz
caches (imported once per database via the `csv_caches_imported` meta flag;
files left on disk as backup, never read or written again).

## gamedata/ — game-file extraction

`extract.py` + `catalog.py` + `textdb.py` (+ `engines.py`, `weapons.py`,
`weaponsim.py`, `shields.py`, `shipmods.py` for the gamedata dashboard);
`refdata.py` loads the CSVs. `extract-gamedata` reads the game's
`.cat/.dat` archives (base + `ego_dlc_*` in load order, later wins; loose
files override) and regenerates the reference CSVs including the full
localization dump (`textdb.csv.gz`) used to resolve `{page,id}` refs in
save names. The v9.0+DLC copies are committed inside the package so
analysis runs don't need the game install.
[csv-reference.md](csv-reference.md) documents every file and the
extraction machinery.

### Reading game files directly (ad-hoc analysis recipe)

For questions the CSVs don't answer, use the archive reader straight:

```python
from x4analyzer.gamedata.catalog import GameFiles
gf = GameFiles(Path("/games/SteamLibrary/steamapps/common/X4 Foundations"))
gf.glob(r"regex over virtual paths")   # loose files not included
gf.read_bytes(path); gf.source_of(path)  # "" = base, else extension name
```

Where things live (DLC content is prefixed `extensions/ego_dlc_*/…`, casing
varies — always glob case-tolerantly):

- Ship **macros** (stats): `assets/units/size_l/macros/ship_<race>_l_trans_container_*_macro.xml`
  (same pattern for size_s/m/xl; purposes `trans_container|trans_solid|trans_liquid|destroyer|…`).
- Ship **components** (geometry = equipment mounts): same dir minus
  `/macros/`; count `<connection tags="engine large …">` elements for
  engine/shield/turret slot counts. Macro links to component via
  `<component ref=…>`.
- Storage macros are scattered (`assets/props/StorageModules/macros/`,
  `assets/units/size_*/macros/`, lowercase `storagemodules` in DLCs) —
  glob `.*/storage_.*_macro\.xml$`, don't assume one dir. A ship macro
  references its hold via `<connection ref="con_storage01"><macro ref=…>`.
- Engine macros: `.*/engine_<race>_l_.*_macro\.xml` — `<thrust forward>`,
  `<boost thrust>`, `<travel thrust charge attack>`.

Speed math (validated against the in-game encyclopedia): max speed =
Σ engine `thrust.forward` ÷ hull `physics/drag@forward`; travel speed =
max speed × engine `travel@thrust`; boost = × `boost@thrust`. L/XL engines
only come in mk1 — no upgrade path, thrust scales purely with mount count.
A useful freighter metric is cargo × travel speed (travel mode dominates
transit time).
