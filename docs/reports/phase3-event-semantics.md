# Phase 3: event-stream semantics — B1, B18, T15 (v12 bump), B2, B15 re-run

Executed 2026-07-24 per [execution-roadmap.md](../plans/execution-roadmap.md)
Phase 3 (+ refinements R2/R3/R6), methods per
[data-model-review.md](../plans/data-model-review.md) backlog items 1, 18
and 2. The research outcome landed as a new plan item
([db-model-improvements.md](../plans/db-model-improvements.md) **T15**,
priority row H5) and shipped as schema **v12**. One commit per item, the
full suite (`uv run pytest -q`) green at every commit: **180 passed**.

| Item | Commit | What shipped |
|---|---|---|
| B1 + B18 + T15 | `a07cf5a` | ledger-typed economylog ingestion, `money_event`, `trade_tx.kind`, v12 migration, doc rewrites (economylog §, X18, R3 note) |
| B2 | `daacd65` | v9 destroyed-wording harvest, `parse_destroyed` rewrite, X7 doc fixes |
| B15 re-run + report | this commit | migration + revived parsers validated end-to-end on both real DBs |

## B1 — the economylog re-model

**Question.** The review (savegame-structure F1/F2) showed the economylog
is four wrapper-typed ledgers, with an undocumented `tradeentry` family
polluting `stock_event`. What do the money-block `tradeentry` records
index (cents? partner direction?), and do `v`-less owner rows mean
stock 0?

**Method.** Block-context iterparse sweeps of save_003 (game time
74,720) with replication on save_010 and the 559 h playthrough's newest
save (`~/Downloads/save_006.xml.gz`); money-block↔trade-block matching
first by shared `{owner,partner}` pair at nearby timestamps, then by
direct `tradeentry` indexing; same-save cross-check of cargo-ledger last
rows against the stations' own `<cargo>` amounts (via the package
parser). Scripts: session scratchpad `b1_sweep.py` / `b1_analyze.py` /
`b1_round2.py`.

**Evidence and verdicts.**

- **CONFIRMED — four wrapper-typed ledgers.** `<entries type="cargo">`
  (1,313,619 logs in save_003), `tradeoffer` (842,248), `trade` (3,656),
  `money` (4,773); the `<log type=…>` attribute is the mutation cause,
  not the record type. The current parser's block-blind
  `<log type="trade">` collection was picking up 390,156 cargo + 3,477
  trade + 1,295 money rows as one family.
- **CONFIRMED — `tradeentry` is a 1-based ordinal into the trade
  ledger.** For every money-block `type="trade"` row carrying the attr,
  `trade_block[tradeentry−1]`'s `{buyer, seller}` equals the row's
  `{owner, partner}`: **1,295/1,295** (save_003), **6,762/6,764**
  (559 h save; the 2 misses are consistent with removed/edge entries,
  and 283 rows there carry no `tradeentry` at all). Ids are near-unique
  and near-monotone with time; the trade ledger itself appears to grow
  from game start (row count = the save's `trades_executed` stat +
  transfers, exactly).
- **CONFIRMED — money-block `v` is cents.** Against the referenced
  trade's `price × amount`: 275 exact + 393 within 0.01% (sub-credit
  unit-price rounding) of 1,184 v-carrying rows in save_003 (e.g.
  `v=12,641,200` = 14,365 ¢ × 880 exactly). The ~40% remainder is
  ≥10% off and correlates with **amended/reused trade entries**
  (duplicate `tradeentry` ids both pointing at one entry, `t2`/`v2`
  second points whose `v2` matches the trade total; sample 5 in the
  sweep) — *hypothesis*: `v` accumulates actual payments across partial
  fills of an entry whose displayed amount is only its latest state.
  Not needed for ingestion; recorded as open.
- **CONFIRMED — the money block is the player's ledger.** Every owner
  resolvable in the current universe is player-faction: 2,497/2,497
  (save_003), 15,431/15,431 (559 h save); unresolvable owners are gone
  objects. Direction is carried by the owner's role in the referenced
  trade: seller-side rows carry `v` (1,160/1,161), buyer-side rows are
  mostly v-less (110/134) — *hypothesis*: buyer money moved at order
  time (escrow; `orderqueue_add` rows carry `v` ≈ price × amount).
- **CONFIRMED — cargo-ledger v-less rows mean stock 0.** For every
  (owner, ware) whose *last* cargo-ledger row (any type) is a v-less
  `type="trade"` row, the same save's `<cargo>` shows zero/absent:
  **2,591/2,591** (save_003; replicated 2,560/2,560 in save_010). The
  store's `absent v = 0` assumption is now evidence-backed. Control:
  v-carrying last rows match `<cargo>` exactly at 96–99% per type once
  the `t2`/`v2` amendment is honored (`v2` = latest level; the residue
  sits in in-flight `drop`/`construction` processes).

**Consequence.** Money-block rows in `stock_event` (`ware=''`, level =
cents!) were data corruption by mis-typing — exactly what
`v_stock_delta`'s `ware != ''` guard was silently hiding. That is T15.

## B18 — trade-block `transfer` entries

**Question.** Do the 176 (now 179) trade-block `transfer` rows belong in
`trade_tx` — the missing slice of `trades_executed`?

**Evidence.** Census over save_003 (179) and the 559 h save (115): all
resolvable (buyer, seller) pairs are **player↔player** (174/174 and
82/82; the rest have one party gone from the universe — consistent with
removed player build storages); classes are ship↔station/buildstorage;
wares are construction materials and consolidation cargo; every row has
`v` (amount), none has `price`. Trade-block total = trades + transfers =
the save's `trades_executed` stat exactly.

**Decision.** Ingest into `trade_tx` with a `kind` column
(`'trade'`/`'transfer'`), `price_cr` NULL — folded into T15's
implementation and migration, not a separate seam. The frames layer
filters to priced `kind='trade'` rows, so dashboards are unchanged;
completeness lives in the DB.

## T15 — implementation (schema v12)

Per the plan's new T15 section: the parser tracks the enclosing
`<entries type>` block (depth-1 economylog only — stations embed
self-closing stubs) and splits collection into `trades` / `stock_logs` /
`money_logs`; `_merge_trades` types rows by origin; the new E table
**`money_event`** carries owner/partner merge-time identity, `kind`,
`tradeentry`, `value_cr` (amended `v2` preferred, ÷100) and merges with
the same rolling-window + coverage semantics as its siblings
(stream `money_event`); `v_stock_delta` drops the `ware != ''` guard.

**Migration** `EVENT_MIGRATIONS["11"]` (v11→v12, stays in the chain
indefinitely): creates `money_event`; adds `trade_tx.kind` (existing
rows backfilled `'trade'` — the old ingestion criterion guaranteed it);
moves every `stock_event` row with `ware = ''` into `money_event`,
extracting partner/kind/tradeentry/value from `raw_attrs` JSON and
keeping epoch, merge-time identity and `owner_entity`; deletes the moved
rows. `ware = ''` is a complete criterion: money rows were the only
ware-less source (the csv legacy import never wrote stock rows).
Regression test `test_v11_database_retypes_money_rows` covers the moved
variants (v, v-less, `v2`-amended, `tradeentry`-less, csv-shaped
`raw_attrs IS NULL` rows untouched) and re-open idempotency.

## B2 — v9 log wordings and the parser revival

**Question.** What are the actual v9 wordings for the logparse families
(destroyed known-changed; construction/repair/transfer/surplus unknown)?

**Method.** Harvest over the merged `log_entry` history of both real DBs
plus the three `cache_log_*.csv.gz` files — 33,061 rows; the DBs stitch
every analyzed save's logbook window, and the not-yet-imported save_003
window was merged the same day, so the corpus covers the 13 saves.
Title-shape census + per-family sampling.

**Findings.**

| Family | Corpus instances | Verdict |
|---|---|---|
| destroyed | 323 (all `upkeep`) | **wording changed in v9** — title `<name> (<CODE>) was destroyed.` (323/323), text `Location: <sector>` + optional `Commander:` (246) + optional `Destroyed by: <killer> (<CODE>)` (311); zero old-form (`was destroyed by` in title) instances anywhere |
| resupply | 2 | v9 wording already handled (`paid the station` variant) — the 9406 DB's 1 `event_construction` row proves it |
| pirate / police | 169 / 9,140 | v9 texts match the existing regexes (D tables already populate: 3/436 and 79/4,202 pre-phase) |
| construction / repair | 0 | zero archived instances — wording unverifiable, parsers left as-is, documented |
| surplus transfers | 0 | zero archived instances — same |

`parse_destroyed` was rewritten for the v9 shape (commander line ignored,
killer optional — 12/323 rows have none) and validated read-only against
both DBs before shipping: **6** rows parse from the reference DB
(exactly the 6 known events), **157** from the 559 h DB, zero unparsed
warnings. The backfill needs no migration: `event_*` tables are D-class,
rebuilt every run from the full merged `log_entry` history, so the next
import *is* the idempotent backfill.

## B15 re-run — rehearsal and real-run evidence

### DB safety protocol

Backups taken before any real-DB write (WAL checkpointed first),
checksums recorded and re-verified afterwards (`sha256sum -c` → OK for
both):

```
~/.local/share/x4analyzer/backup/
  x4_8E0C8E37-….20260724T130541Z.pre-phase3.sqlite
    0e481ff0a3af448c90c08b2f8be65c5fd2bb0bf5b4280525e92f1c2169b8d2c0
  x4_94062A45-….20260724T130541Z.pre-phase3.sqlite
    fb9f5591dbf5d16c27108eb2876f47c95c09a71f8c502a03303785c75e8717e1
    (byte-identical to the Phase-2 post-run checksum — nothing touched
    9406 in between)
  checksums-20260724T130541Z-pre-phase3.txt
```

8E0C's pre-phase3 state differed from the Phase-2 report: save_003 had
been imported at v11 on 2026-07-24T02:29Z (save_id 5), adding a fifth
window — and 76 more mis-typed money rows (1,295 `ware=''` total).

### Rehearsal (scratch copies, session scratchpad `b15/`)

Both real DBs + the user-dir reference CSVs copied to a scratch data dir,
real CLI run against it (`--data-dir`). Results identical in kind to the
real runs below; the third 9406 run confirmed counts frozen.

### Real run: 8E0C (current playthrough, v11 → v12)

Input: `save_005.xml.gz` (game time 75,210 — freshly saved this morning,
newer than the stored head 74,720; picked up automatically).

| table | pre (v11) | after run 1 | after run 2 |
|---|---|---|---|
| save | 5 | 6 | 7 (provenance row per import, by design) |
| trade_tx | 3,474 | 3,716 (3,537 trade + 179 transfer) | 3,716 |
| stock_event | 391,451 (1,295 `ware=''`) | 392,963 (**0** `ware=''`) | 392,963 |
| money_event | — | 4,795 | 4,795 |
| log_entry | 3,969 | 3,989 | 3,989 |
| removed_object | 1,222 | 1,331 | 1,331 |
| entity | 38,097 | 38,552 | 38,552 |
| entity_event | 65 | 69 | 69 |
| **event_destroyed** | **0** | **6** | **6** |
| event_pirate / event_police | 3 / 436 | 5 / 441 | 5 / 441 |
| schema_version | 11 | **12** | 12 |

### Real run: 9406 (the 559 h playthrough, v11 → v12)

Input: `/home/adam/Downloads/save_006.xml.gz` (the playthrough's newest
save, same head as stored — migration + idempotency proof).

| table | pre (v11) | after run 1 | after run 2 |
|---|---|---|---|
| save | 4 | 5 | 6 |
| trade_tx | 16,222 | 16,337 (16,222 trade + 115 transfer) | 16,337 |
| stock_event | 476,569 (7,047 `ware=''`) | 469,522 (**0** `ware=''`) | 469,522 |
| money_event | — | 16,408 | 16,408 |
| log_entry | 13,840 | 13,840 | 13,840 |
| removed_object | 863 | 863 | 863 |
| entity | 16,250 | 16,250 | 16,250 |
| **event_destroyed** | **0** | **157** | **157** |
| event_construction | 1 | 1 | 1 |
| event_pirate / event_police | 79 / 4,202 | 79 / 4,202 | 79 / 4,202 |
| schema_version | 11 | **12** | 12 |

Note 469,522 = 476,569 − 7,047: the migration moved every polluted row
(their re-typed copies live on in `money_event`; 16,408 > 7,047 because
the fresh money-ledger window is wider than what the old shunt kept).
Post-run `sha256sum` of both DBs recorded
(`fb800b05…` / `11417ce2…`); backup checksums re-verified OK.

## Verification summary

- `uv run pytest -q`: **180 passed** at every commit.
- Migration verified against a pre-Phase-3 v11 state twice over
  (scratch rehearsal + real run) and against synthetic v1/v5/v11 DBs in
  tests — old-state DBs correct on open; the v11→v12 step remains in
  the chain for any DB that shows up later.
- Re-running the same import adds 0 rows to every event table (both
  DBs, real runs).
- `event_destroyed` after backfill: 6 (8E0C, = the 6 known events) and
  157 (9406) — requirement ≥ 6 met.
- `stock_event.ware = ''` count is 0 in both DBs; `v_stock_delta` no
  longer needs (or has) the guard.
- Dashboards built without errors: 4 real runs + 5 rehearsal runs.
- Backups exist with recorded checksums; `sha256sum -c` verifies them.

## Open questions recorded (not blocking)

- Money-`v` composition for amended/reused trade entries (partial-fill
  accumulation hypothesis) — would need per-entry fill tracking across
  consecutive saves.
- `orderqueue_add` escrow semantics (its `tradeentry` pair-matches only
  ~46% by naive indexing).
- Ship construction/repair and surplus-transfer v9 wordings: zero
  archived instances anywhere; unverifiable until such an event occurs
  in a live playthrough.
