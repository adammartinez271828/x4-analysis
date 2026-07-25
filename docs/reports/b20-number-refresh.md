# B20: perf + census number refresh

Executed 2026-07-24 as the post-Phase-6 close-out, per
[data-model-review.md](../plans/data-model-review.md) backlog item 20
(re-time the parse and the `find` sweep, census inert anomalies —
viz F7 — and relabel the save-specific diplomacy example). Machine:
the usual dev box; save = the analyzer's default pick, current
playthrough (8E0C). Numbers were replaced only where re-measured; each
row lists the command that produced it. The real DBs were read-only
throughout (`?mode=ro` URIs); the timing runs parse the save file
directly and import nothing.

**Measured subject.** `save_006.xml.gz`, 85,145,635 bytes (81.2 MiB),
game time 78,583.099 — the same snapshot the DB's newest import holds
(the quicksave written one minute earlier is the same save state), so
the DB census and the parse census describe one world state.

## Measurement table

| # | Number | Command | Old → New | Doc(s) updated |
|---|---|---|---|---|
| 1 | Full parse wall time | `uv run python -c "…parse_savegame(save_006.xml.gz)"` wrapped in `time.perf_counter()` | ~18 s → **22.0 s** (stated ~22 s) | architecture.md § save/, CLAUDE.md parser bullet |
| 2 | Parse peak memory | same run, `resource.getrusage(RUSAGE_SELF).ru_maxrss` | 270 MB → **403 MiB** (stated ~400 MB) | architecture.md § save/ |
| 3 | Save size the timing describes | `ls -l`, `peek_save_info` | 73 MB → **85 MB** (81.2 MiB gz) | architecture.md, CLAUDE.md |
| 4 | `find` sweep wall time | `time uv run x4-analyzer find` (default: the 5 Erlking vaults, newest save) | ~17 s → **17.8 s** (stated ~18 s) | architecture.md § find |
| 5 | DB file size | `ls -l ~/.local/share/x4analyzer/x4_8E0C….sqlite` | 145 MB → **167 MB** | db-schema.md header |
| 6 | Schema version | `SELECT value FROM meta WHERE key='schema_version'` | 11 → **17** | db-schema.md header |
| 7 | Current-snapshot components | `SELECT COUNT(*) FROM component WHERE save_id=(SELECT MAX(save_id) FROM save)` | 17,543 → **17,470** | db-schema.md header |
| 8 | Raw parsed components (incl. connectionless) | the run in #1, `len(d.components)` | (unstated) → **18,729** — 1,259 connectionless components are skipped at load, hence < #7's parse-side count | report only (context for #7) |
| 9 | stock_event rows | `SELECT COUNT(*) FROM stock_event` | 383,778 → **412,385** | db-schema.md header |
| 10 | entity rows | `SELECT COUNT(*) FROM entity` | 36,825 → **41,507** | db-schema.md header |
| 11 | Inert-anomaly census (viz F7) | `SELECT COUNT(*), COUNT(DISTINCT sector_macro), MAX(per-sector n) FROM wormhole WHERE transition_dest IS NULL AND save_id=current` | "30, one per base-game sector" → **33 across 30 sectors, max 2 per sector** (one-per-sector refuted, matching wormhole W4) | viz-internals.md § map overlays |
| 12 | Diplomacy reciprocity (the mislabeled example) | `SELECT COUNT(*) FROM faction_relation a WHERE kind='base' AND NOT EXISTS (mirror row with equal value)` at the current snapshot | "directional (NOT symmetric)" via an example comparing two different pairs → **0 of 486 base pairs asymmetric** in this save; claim restated as stored-per-direction / measured-reciprocal (review X4/F7) | viz-internals.md § diplomacy |

Notes on the timing deltas: the save file grew ~17 % since the original
measurements (73 → 85 MB) — the parse-time and peak-memory growth is
proportionate, not a regression; the `find` sweep is size-insensitive
enough that its number barely moved. All figures are single runs on the
dev box, same as the originals — treat them as the usual ±1 s /
±tens-of-MB ballpark, not benchmarks.

Save-specific labels: rows 7–12 describe **this playthrough's current
snapshot** (game time 78,583); the two viz-internals passages now carry
that scoping inline, which is the relabeling half of the backlog item.

Out of scope, unchanged: the "30 ms/station" spike misquote (a
db-model-improvements.md plan-review finding, not a reference doc),
csv-reference provenance numbers (B21), and every DF-2 item.
