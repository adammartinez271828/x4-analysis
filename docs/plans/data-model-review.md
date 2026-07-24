# Adversarial review of the data-model documentation

Status: **findings + research backlog** (2026-07-23). Every document under
`docs/models/` and `docs/reference/`, plus
[db-model-improvements.md](db-model-improvements.md), was attacked by an
independent reviewer whose brief was to refute claims, find drift from
code/data, and find coverage gaps — not to summarize. Nothing reviewed was
edited; this file is the only output.

**Evidence base for tested findings.** Newest save
`~/.config/EgoSoft/X4/12073019/save/save_002.xml.gz` (81 MB gz, game time
72,813 s) and the 12 older dated saves/autosaves (57,508 s → 72,813 s) via
streaming `lxml.iterparse`; the two populated DBs opened read-only
(`file:...?mode=ro`): `~/.local/share/x4analyzer/x4_8E0C8E37-….sqlite`
("8E0C", current ~20 h playthrough, schema v10) and `x4_94062A45-….sqlite`
("9406", 559 h playthrough, schema v5); game files via
`x4analyzer.gamedata.catalog.GameFiles`; the committed CSVs; the source
tree and git history. Every finding is labeled **TESTED** (with the
check that reproduces it) or **UNTESTED** (desk reasoning). Severity:
**wrong** (claim refuted) / **unsupported** (asserted beyond its
evidence) / **stale** (code or data moved) / **gap** (in-scope but
missing). Blast radius names what inherits the error.

**Headline.** ~110 findings across ten documents. The structural docs are
in far better shape than the semantic ones: raw counts, element
inventories, DDL inventories, and code maps verified almost perfectly,
while a cluster of *interpretive* claims — several tagged [OBS] or
CONFIRMED — failed empirical re-testing outright. The five worst:

1. **Resource respawn relocates** (145 relocations vs 4 in-place across 12
   save transitions) — the model doc's [OBS]-overrides-DOC caveat was
   backwards, and its per-area tracking recipe is invalid.
2. **The wormhole direction rule is probably inverted** — the map's one
   asymmetric warp arrow likely points backwards, and the Avarice link is
   tide-cycled, not story-gated.
3. **The economylog is four typed ledgers, not one** — the "two flavors of
   type=trade" model mischaracterizes ~28 k entries and an undocumented
   `tradeentry` family pollutes `stock_event` (the `ware != ''` guard in
   `v_stock_delta` exists because of it, explained nowhere).
4. **The destroyed-object log wording changed in v9** — the reference save
   contains 6 destroyed events the parser regex cannot match, while two
   docs assert the playthrough has none.
5. **`save`/`meta` are dropped on every schema bump** — a premise error
   shared by db-schema.md and db-model-improvements.md that breaks the
   proposed trend layer (T4/T5) as designed.

---

## Findings by document

### docs/reference/savegame-structure.md

Verdict: **the census layer is excellent, the semantic layer around the
economylog and the "stub" regions is not.** All 17 top-level children,
subtree counts (11,293,635 elements), the component class table, the
economylog type-count table, money conventions, and dozens of
micro-claims (`assignmment` 2,251/0, flat-`<subordinate>` trap, person
roles, offer grouping) reproduced exactly.

- **F1. `<economylog>` structure wrong — four typed ledgers, not one.**
  Claim: "`<economylog><entries>` holding ~2.1 M `<log>` elements, plus a
  `<removed>` block." Attack: it is partitioned into `<entries
  type="cargo">` (1,271,845 logs), `type="tradeoffer"` (820,302),
  `type="trade"` (3,428), `type="money"` (4,666), with `<removed>` first
  in document order; the wrapper `type` is the primary semantic key the
  doc's "two flavors" heuristic re-derives from attributes. TESTED —
  iterparse depth-3 scan of economylog children of save_002; per-block log
  counts reconcile exactly with the doc's own type table. Severity:
  wrong. Blast: `parser.py` (collects `<log type="trade">` ignoring block
  context), `store._merge_trades`, and F2 below.
- **F2. "Two flavors" of `type="trade"` is really four; the `tradeentry`
  family pollutes `stock_event`.** The 380,490 "owner-only" entries split:
  owner+ware+v 352,663; owner+ware **without `v`** 26,581; an undocumented
  `tradeentry` family of 1,246 (`owner|partner|tradeentry[|v[|t2|v2]]`, no
  `ware`, `v` at money scale, living in the *money* block). TESTED —
  attribute-set census; DB check: `stock_event` has 1,219 `ware=''` rows,
  all `raw_attrs LIKE '%tradeentry%'`; `v_stock_delta` silently guards
  `WHERE ware != ''` — a code/data coupling no doc explains. Severity:
  wrong + gap. Blast: `store._merge_trades` (ingests tradeentry rows as
  fake stock snapshots; treats missing `v` as stock = 0 on an unbacked
  assumption), `stock_event`, `v_stock_delta`, `frames.global_trades`,
  trade time-series widgets.
- **F3. "Full transactions (buyer + seller + price — 3,252 here)"
  overstated.** 3,252 counts buyer+seller regardless of price; 3 lack
  `price` (silently dropped by store); only 965/3,252 carry the example's
  full `b/bmax/s/smax` shape (11 distinct attribute sets). TESTED.
  Severity: wrong (minor). Blast: store's tx criterion; db-schema.md
  § trade_tx cites this definition.
- **F4. Trade-block `transfer` entries are the missing 176 of
  `trades_executed`.** `transfer` (1,257) splits 269 cargo / 176 trade /
  812 money block. Trade block total = 3,252 + 176 = 3,428 = the save's
  `trades_executed` stat exactly — the game counts them as executed
  trades; the parser/DB ignore them. TESTED. Severity: gap. Blast:
  trade_tx completeness (player internal transfers absent), P&L views.
- **F5. Destroyed-object log wording is stale — and the save disproves it
  internally.** Doc gives the v5.10 form "`<object> in sector <sector>
  was destroyed by <killer>.`"; the reference save contains **6**
  destroyed entries in a new wording (title `"RS-PE (GDV-373) was
  destroyed."`, text `"Location: …\nDestroyed by: …"`, sometimes a
  `Commander:` line, plus undocumented `x/y/z` attrs). Zero old-style
  titles. `logparse.parse_destroyed` matches nothing → `event_destroyed`
  is empty despite matching events existing. TESTED — logbook line-scan;
  DB: `log_entry LIKE '%was destroyed by%'` = 0, `LIKE '%was
  destroyed.%'` = 6, `event_destroyed` = 0 rows. Severity: stale
  (effectively wrong). Blast: `parse_destroyed`, `event_destroyed`,
  destroyed dashboards; db-schema.md and save-semantics.md repeat the
  false "no such events" rationale (see X7).
- **F6. Logbook attr table omits `x`/`y`/`z`** (the 6 destroyed events).
  TESTED. Severity: gap (minor). Doc-only.
- **F7. `<shortage>` context claim false twice over.** Parents of
  `<ware>` under `<shortage>`: production/queue 1,066, workforces 391,
  `build/resources` 96 (the form the doc marks "(unverified in this
  save)" is present), queue/item 27; plus `<insufficient>` nested inside
  `<shortage>` under `<aborted>`. TESTED (grandparent census). Severity:
  wrong + stale. Blast: mostly doc; parser ingestion is guarded.
- **F8. `<insufficient>` contexts undocumented** (queue/item 16,
  aborted/shortage 10). TESTED. Severity: gap (minor).
- **F9. Station children list incomplete; station `<economylog>`
  mis-described.** A 200-station sample also shows `locked` (73),
  `subordinates` (34 — stations command fleets), `lastglobalanimation`
  (7), direct `build` (5), and `<commissions>` holding `<booster
  faction="player" amount="0.12" time delay decayrate>` — per-station
  player commission state, documented nowhere and load-bearing for the
  pricing model. The station `<economylog>` is a self-closing element
  *with attributes* `cargo="0" offer="0"`, not a structural variant of the
  top-level block. TESTED. Severity: gap + wrong-detail.
- **F10. `<booster>` has four contexts and three schemas, not two.**
  Parent census: relations 171, discounts 11, **tolerance 345** (NPC
  pilots: `value="-1" time delay="10" decayrate="0.05"` — police
  tolerance), **commissions 14** (stations). The `delay`/`decayrate`
  variants are undocumented — decay parameters *do* exist in the save,
  relevant to faction-relations-model.md. TESTED. Severity: gap.
- **F11. `<patches>` is not "one `<patch>` per DLC/mod".** The block holds
  exactly 9 entries (7 DLC + 2 `ws_*`) on a ~60-mod install — the save
  records only save-relevant extensions; the doc's own `<info>` subtree
  count (24) already made a 60-entry list impossible. TESTED (`zcat |
  head`). Severity: wrong. Blast: mod audits from `<patches>`.
- **F12. yieldid ware list overclaims `scrap`.** Census over all 3,246
  areas: no `scrap` token — under a preamble asserting everything occurs
  in the reference save. TESTED. Severity: wrong (minor).
- **F13. Fleet assignment values incomplete** — also `interception`,
  `salvage`. TESTED. Severity: gap (minor).
- **F14. Committed in-flight trades: stale hedge + missing load-bearing
  structure.** `trade/reservations` *is* present (2,602 elements — the
  "(not re-verified)" hedge is stale), and the committed-trade records
  under orders — 2,617 `<trade id buyer|seller partner ware price amount
  desired flags="sellermoneyvirtual|…">` children of `<order
  order="TradePerform" temp="1">` — are entirely undocumented although
  save-semantics.md's pricing model depends on exactly them ("Pending =
  committed outbound sales … verified exact in-game"). TESTED. Severity:
  stale + gap. Blast: any pricing implementation lacks a structural
  reference.
- **F15. Second `<component>` form undescribed.** 454 elements are pure
  cross-references `<component component="[0x…]"/>` (no class/id, inside
  recycling/dismantle `<components>` blocks); the "all optional except
  class/id in practice" claim and the class table miss them. TESTED.
  Severity: wrong (minor).
- **F16. `<god/>` is literally empty** — the stub implies undocumented
  content; there is none (likewise `uianchorhelper`, `cameraanchor`).
  TESTED. Severity: unsupported (minor).
- **F17. Stub-region contents (gap enumeration).** TESTED depth census of
  what the stubs hide: `universe/jobs` 1,245 `<job>` (~174 k lines, the
  largest undocumented region, incl. unspawned-ship subtrees);
  `universe/blacklists` — a *second* `<blacklist>` schema (id/owner/type +
  macro refs) distinct from the player-faction form the doc shows;
  `script` 324,653 `<ref>`; `md` 354 scripts / 978 cues; `aidirector`
  27,225 entities; `missions` `<thread>` nesting and `<bbs>` offers
  undescribed; player/NPC `<known>` blocks holding 42 typed `<entries
  type="…">` encyclopedia ledgers (an element-name collision with
  economylog `<entries>`), `<times><unlock>`, and
  `<modifiers><modifier object name type="commission|discount" amount
  time>` — the per-station economy-event records the pricing model needs
  (2 discount / 14 commission; `time` is future = expiry). Severity: gap.
- **F18. economylog `<removed>` attrs are a sparse union** — `offer`
  optional, undocumented `cargo` attr (value pattern supports the "looks
  like a game time" guess). TESTED. Severity: gap (minor).
- **F19. `distance_*` "km (unit unverified)" refuted by the doc's own
  numbers.** `distance_superhighways`/`time_superhighways` = 9,813 "km/s"
  — sensible only as metres (≈9.8 km/s); `distance_walked` 11,417
  absurd as km; `distance_space` sensible only as km. Units are mixed
  per-counter. TESTED (desk arithmetic on captured values). Severity:
  unsupported.
- **F20. Mission `reward` "presumably cents" — probably backwards.**
  Rewards 71,060–459,190 read as whole credits at guild-mission scale;
  as cents they'd be 710–4,592 Cr. UNTESTED (desk reasoning; no completed
  mission spans a checked save pair). Severity: unsupported.

### docs/reference/db-schema.md

Verdict: **inventory perfect, several semantic claims fail on the doc's
own reference DB.** The three-way inventory (doc = schema.py = live DB:
46 tables, 8 views, 11 indices), merge idempotency (same save imported
twice, zero duplicate E-rows), the ~40× overcount workaround's
qualitative claim, the zombie `station_drones` account, and all
enumerations verified exactly.

- **F1. `spawntime` "NULL = world creation" is wrong — it's 0.** NULL
  means the element carries no spawntime at all (clusters/sectors).
  TESTED — `entity`: 0 NULL spawntimes, 9,757 rows with spawntime = 0;
  `component`: 279 NULL = exactly the 127 clusters + 152 sectors.
  schema.py's own DDL comment and savegame-structure.md both say 0.
  Severity: wrong. Blast: any "original universe objects" bucketing by
  `spawntime IS NULL`; registry generation semantics (the "only a slot's
  first generation" claim is vacuous under the NULL reading, holds under
  the 0 reading).
- **F2. "Live collisions are cross-faction code reuse" — same-faction
  collisions exist.** TESTED — the 8E0C DB has two simultaneously-alive
  terran `ship_ter_s_fighter_01_a` both coded **XPU-790** in different
  sectors (entities 5318/11691, both open); 10 live same-slot
  (code,class) collisions total, 1 same-faction. The macro/owner tiebreak
  cannot disambiguate; event attribution falls to entity_id order.
  Severity: wrong (the parenthetical) + gap. Blast: entity_event
  attribution; falsifies the "codes safe among simultaneously-alive
  same-faction objects" rule in CLAUDE.md and save-semantics.md (X2).
- **F3. "`save` is the only record older imports happened" — routinely
  destroyed.** `save` is not in `EVENT_TABLES`, so every schema bump
  drops it. TESTED — entity.first_seen has 13 distinct values (13
  registry-updating imports) but `save` holds 2 rows, both from
  2026-07-23 with identical game_time. Severity: wrong / internal
  contradiction (the doc's own versioning section lists the drop).
  Blast: import provenance; shared premise with db-model-improvements.md
  (X13).
- **F4. Merging an older save silently destroys E history —
  undocumented.** `_merge_window` executes `DELETE FROM {table} WHERE
  time >= mintime` unconditionally; feeding an older save (`--save` is
  one keystroke away) wipes everything newer and replaces it with the
  shorter window. Only the entity registry has a high-water guard.
  UNTESTED destructively (read-only review); the code path is
  unconditional. Severity: gap — the highest-stakes omission in the doc.
  Blast: the entire value of the E tables; every history-consuming
  dashboard.
- **F5. "One deliberate `''` exception" is false — there are three.**
  `trade_tx.ware` and `stock_event.ware` also store `''` (`or ""` in
  store.py), per the doc's own column tables; the named exception
  (`trade_offer.object_id`) currently has zero instances. TESTED —
  `stock_event.ware=''` → 1,219; `trade_offer.object_id=''` → 0.
  Severity: internal contradiction. Blast: `IS NULL` predicates on event
  tables miss rows.
- **F6. "All views filter to the current snapshot" — `v_stock_delta`
  doesn't** (correctly; it's an E-table view). TESTED (view DDL).
  Severity: internal contradiction (minor).
- **F7. `idx_stock` "serves the v_stock_delta window scan" — it doesn't.**
  The view partitions on the synthesized text identity; `EXPLAIN QUERY
  PLAN` shows `SCAN stock_event` + temp B-tree. db-model-improvements.md
  already documents the opposite; db-schema.md didn't get the memo.
  TESTED. Severity: stale.
- **F8. The csv legacy-import narrative describes rows that don't
  exist.** Both DBs have `csv_caches_imported='1'` and cache files on
  disk, yet zero imported rows exist (csv-imported rows are identifiable
  by `raw_attrs IS NULL`; count = 0 in trade_tx and log_entry of both
  DBs) — the import ran and contributed nothing; the csv.gz files remain
  the *only* copy of pre-DB history, contrary to the doc's implication.
  TESTED. Severity: unsupported/misleading.
- **F9. The epoch machinery has never fired.** `MAX(epoch) = 0` in
  trade_tx and stock_event of both DBs — increment-on-gap, epoch-
  partitioned LAG, and gap semantics have zero empirical instances; the
  doc's "verified against the real populated database" framing overclaims
  them. TESTED. Severity: unsupported. Blast: v_stock_delta behavior
  across future gaps.
- **F10. "v9 wording unverified" for event_construction is stale** — the
  9406 DB contains one `event_construction` row (a v9 resupply event that
  parsed correctly). TESTED. Severity: stale (mild).
- **F11. `*_name` columns include synthesized fake names — undisclosed.**
  `store._identities` fabricates display names for nameless objects
  (`"<SHORT> <model|Station>"` etc.), indistinguishable from real names
  in the column. UNTESTED distribution-wise (unflagged — that's the
  point); code path unambiguous. Severity: gap.
- **F12. Registry domain "every ship/station/buildstorage ever observed"
  — only if it has a code.** `update_entity_registry` skips codeless
  components; currently 0 exist (TESTED) but modded saves are where they
  would appear. Severity: gap/untested assumption.
- **F13. Undocumented within-window log dedupe can drop real events.**
  `_merge_log` dedupes on the full natural row within one window — two
  genuinely identical entries (same second, same text) collapse
  permanently. UNTESTED; code unambiguous. Severity: gap.
- **F14. ER diagram PKs are truncated** — `save_id` is part of every
  W-table PK but the diagram omits it, with no disclaimer. Severity:
  stale (minor).
- **F15. Minor omissions** — `removed_object.raw_attrs` also carries
  `cargo`/`space`; the station_munition category list omits `mining`
  (which schema.py's comment includes — doc and code comment disagree
  with no data arbiter); `resource.level` ellipsis hides the middle
  values. Severity: gap (minor).

### docs/reference/save-semantics.md

Verdict: **the identity narrative and market mechanics mostly hold; the
pricing model's CONFIRMED banner does not survive contact with the full
offer book, and several quoted measurements are stale one-offs.**
Survived: the `assignmment` typo, yieldid parsing, `config_supply_*`
absence, workunit_busy recipe numbers (exact), DLC diff-patch story, rep
tier thresholds (exact), Layer-4 buy-side gap (2,725 of 13,005 buy offers
above band max), stock-snapshot semantics (qualitatively), proxy
attribution, understocked rule.

- **F1. The universal "6.105 h" target constant is contradicted by the
  project's own implemented model.** `analysis/storage.py` implements a
  **per-station** normalizer `T = (pool_capacity − Σfood)/Σ(throughput×
  volume)` with food fixed at 4.0 h; measured T values 7.55/5.71/~5.4 h
  across pools — 6.105 h was one station's value generalized. TESTED
  (storage.py docstring + constants; project memory concurs). Severity:
  wrong (as a universal constant under a CONFIRMED banner). Blast: any
  Layer-2 reproduction; station_storage semantics.
- **F2. "Workforce-adjusted throughput … base rates is the classic
  error" is only half true.** storage.py: work_effect applies to *output
  only*; input consumption stays at base (verified in-code against
  GDR-378). The doc's blanket prescription over-adjusts inputs. TESTED.
  Severity: wrong (imprecise).
- **F3. Layer 2 "linear confirmed" does not generalize.** Joining all
  1,518 banded sell offers against the DB's computed targets: 23% within
  1 Cr, 54% within 5% of band; 171 offers sit at stock ≥ target where the
  curve predicts ≈min yet 149 are priced well above min (energycells
  18.09 Cr at stock 511 k vs target 242 k). Either targets are wrong for
  those stations, pricing target ≠ storage max, or pending dominates —
  none demonstrated. TESTED (trade_offer × station_storage × cargo join
  on 8E0C). Severity: unsupported (single-ware observation generalized
  as CONFIRMED). Blast: pricing knowledge; any future pricing feature.
- **F4. The formula is unclamped but the game clamps.** 0 of 2,289
  checkable sell offers fall outside [min,max]. Clamping is real,
  load-bearing, undocumented. TESTED. Severity: gap.
- **F5. Transacted prices cross the band floor.** 12 of 3,133 trade_tx
  rows are below band min, down to exactly 0.500×min — consistent with
  tier+event discount stacking to 50%, which the doc neither bounds nor
  mentions. TESTED. Severity: gap. Blast: P&L interpretation.
- **F6. The code-fallback safety rule omits the class condition — live
  counterexamples exist.** RYJ-686 is simultaneously a xenon corvette
  and a xenon lasertower; PZZ-881 a station and its buildstorage; the
  registry's slot is code+**class** but the doc's rule says only
  "same-faction". And XPU-790 (see db-schema F2) is two alive
  same-faction same-class fighters — either the rule is dead or the
  registry double-minted (the `save` table's two rows for one file makes
  entity idempotency worth checking). TESTED. Severity: wrong (rule as
  worded) + possible bug. Blast: entity registry consumers, per-object
  views, CLAUDE.md's gotcha.
- **F7. "~40×" overcount factor is playthrough-specific** — measured
  26.0× (8E0C) and 65.7× (9406); the qualitative claim survives, the
  number doesn't (it is also duplicated into db-schema.md). TESTED.
  Severity: stale.
- **F8. "163 recycles in 21 game-minutes" is unreproducible** — both DBs
  now contain one distinct save each; the measurement survives only as
  prose in two docs. TESTED (save-table inspection). Severity:
  unsupported.
- **F9. "Log parsers unverified against v9; the test save contains no
  such events" is stale in both halves.** The 9406 DB's log_entry
  contains a v9 "Ship resupplied" row, and running
  `logparse.parse_ship_services` over the archived rows parses it
  correctly — resupply wording is v9-confirmed; meanwhile destroyed
  events *do* exist but in changed wording (savegame-structure F5).
  TESTED. Severity: stale. Blast: the event_* tables and their tabs.
- **F10. `capacity_floor` silently depends on modcap coverage.** 96
  built module macros in this modded save are absent from modcap; 21
  stations "exceed" their floor only because their (modded/Xenon)
  production macros are unmapped; a modded dock/pier macro would make the
  "exact" floor wrong with no warning. TESTED. Severity: gap. Blast:
  station_munition.capacity_floor, v_station_drones.
- **F11. MXH-411 listed as validation of the +10/production term is
  circular** — it is the fit point. Independent corroboration the doc
  lacks: ~12+ Xenon stations sit at exactly floor+10 with exactly one
  unmapped production module. TESTED. Severity: stale (miscalibrated in
  both directions).
- **F12. Reputation tiers are plain game data; the repo carries no band
  data.** The tiers are hardcoded in `md/notifications.xml`
  (`$DiscountMap`, verified verbatim) — not reverse-engineering; and
  min/max band values exist nowhere in the repo (wares.csv holds only
  `price_avg`), so every pricing layer is irreproducible without a game
  install — never stated. TESTED. Severity: gap.
- **F13. "Collisions exist in 600 h saves" understates** — 24 live
  cross-faction collisions in the ~20 h playthrough vs 15 in the 559 h
  one; collisions are immediate. TESTED. Severity: stale (minor).
- **F14. Internal tension unstated:** market capacity/Cr-h excludes the
  workforce bonus while the pricing section calls ignoring workforce "the
  classic error" — market Cr/h understates staffed producers by up to
  ~37–43% and no doc says so. TESTED (no work_effect in
  frames/opportunities/market). Severity: gap.

### docs/reference/csv-reference.md

Verdict: **inventory and spot values flawless; machinery and consumer
attributions have real errors.** All 14 files, headers, and row counts
match; committed vs user-dir copies are byte-identical; five values
re-derived from game XML match exactly (energycells, Bolo cargo,
regionyields veryhigh/ore, an engine, a hab module); the gates.csv
invariants and the single oneway row verified.

- **F1. "ownerless … absent from factions.xml" is wrong.** `ownerless`
  is a (hidden, nameless) faction in `libraries/factions.xml`; it is
  absent from the *CSV* because `extract_factions` silently drops any
  faction lacking `@name` (32 ids in XML → 31 rows). "One row per faction
  id" is therefore also wrong. TESTED (GameFiles parse). Severity: wrong
  + undocumented filter. Blast: cosmetic today (refdata `setdefault`s
  ownerless).
- **F2. "The map and Build Advisor read the full file" (gates.csv) —
  the Advisor doesn't.** It consumes gates only via
  `sectorgraph.build_adjacency` (endpoints only, undirected, plus a
  same-cluster full-mesh). Buried consequence: **sectorgraph ignores
  `oneway`**, so Advisor hop-distances treat Savage Spur I→II as two-way
  — recorded in no doc. TESTED. Severity: stale/wrong.
- **F3. engines.csv "and the gamedata dashboard" is false** — the
  dashboard imports weapons/weaponsim only; the sole engines.csv consumer
  is `opportunities.py`. TESTED (greps). Severity: stale.
- **F4. The library-merge + `source`-column machinery story is
  overbroad.** `extract_regionyields` reads the *base* file only (no
  `_variant_paths` merge, non-recovering parser) — harmless today (no
  DLC regionyields exists) but silently ignores mod patches under
  `--include-mods`; and five files (recipes, modcaps, engines,
  regionyields, gatherspeeds) have **no `source` column**, with modcaps
  last-writer-wins — mod overrides would be provenance-invisible.
  TESTED. Severity: internal contradiction / overconfident. Blast: mod
  contamination audits of the two most model-critical files.
- **F5. Loose-file override claim fails for discovery.** `GameFiles.glob`
  excludes loose files, and most extraction is glob-driven — loose files
  override content of indexed paths but loose-only files are never found;
  catalog.py's "both bare and namespaced" comment is also wrong. TESTED
  (code); latent (no loose dirs installed). Severity: unsupported nuance.
- **F6. modules.method → recipes join breaks for 19% of rows,
  undocumented.** 13 of 68 module rows name (ware, method) pairs with no
  recipe row; `storage.py:129` silently falls back to `(ware,
  "default")` — a load-bearing convention absent from the doc. TESTED
  (pandas anti-join). Severity: gap. Blast: storage model, Advisor
  throughputs.
- **F7. recipes "Key (ware, method, input_ware)" is a data property, not
  an invariant** — extraction dedups byte-identical rows only and the DB
  table has no PK; a mod duplicate would silently double station_storage
  throughput (storage.py takes `iloc[0]`). TESTED: 0 duplicates today.
  Severity: unsupported (fragile under `--include-mods`).
- **F8. "v9.0 + all official DLCs" is unverifiable** — `source` values
  show base + the 7 installed `ego_dlc_*`; nothing records game version
  or asserts DLC-set completeness. TESTED. Severity: untested assumption.
- **F9. "Lowercased at extraction boundaries" untrue for engines.csv** —
  lowercasing happens at *load*; the CSV is lowercase by luck of vanilla
  naming. TESTED (0 non-lowercase committed). Severity: minor.
- **F10. modules.csv provenance omits the `production@wares` attribute
  fallback** (extract.py; fires 0 times today). TESTED. Severity: trivial
  gap.

### docs/reference/architecture.md

Verdict: **mostly survives; one internal contradiction and one wrong
module list.** The GameFiles recipe, csv-cache flag, view lifecycle,
vault/collectable handling, and entity-registry description verified.

- **F1. §find contradicts §parser (and the code) on zones/positions.**
  §find says "parser.py deliberately drops both zones and positions";
  §parser (correctly) says offsets/zone chains are folded into the single
  pass, and `parser.py` keeps `<offset><position>` on the ancestry stack
  and sums zone offsets. The stale rationale was copied from
  `landmarks.py`'s docstring — which is itself stale. TESTED (grep/read).
  Severity: wrong + internal contradiction. Blast: invites a needless
  second sweep; the real justification for landmarks.py (generic macro
  lookup at arbitrary depth) goes unstated.
- **F2. gamedata module attribution wrong.** The gamedata dashboard calls
  only weapons.py + weaponsim.py; `engines.py`'s docstring says it feeds
  an external harness, and `shields.py`/`shipmods.py` are imported by
  nothing in src/ or tests/. TESTED (package-wide greps). Severity:
  wrong. Contradicts viz-internals' correct "one tab" claim (X16).
- **F3. Pipeline picture omits write-back and post-frames stages** —
  actual order includes `import_legacy_caches`, `write_derived`, and the
  storage/drones analyses persisted after frames. TESTED (analyze.py).
  Severity: gap.
- **F4. analysis/ coverage stops at frames.py** — `drones.py` and
  `storage.py` appear in no reference doc. TESTED. Severity: gap.
- **F5. logparse inventory omits the two v9-validated parsers**
  (`parse_pirates`, `parse_police`) that feed map overlays. TESTED.
  Severity: gap (minor).
- **F6. Performance numbers ("~18 s / 270 MB", "~17 s find") unverified**
  on current code. UNTESTED. Severity: unsupported.
- **F7. "tradelog" naming drift vs db-schema.md's `trade_tx`/`stock_event`
  merge description** (semantics match). TESTED. Severity: stale (minor).

### docs/reference/viz-internals.md

Verdict: **the map/diplomacy/opportunities/advisor core is remarkably
accurate** (tab tree, templating, gauge semantics, facility precedence,
rank formula, kaori/advisor/audit constants all verified exactly) —
**but the weapon-sim paragraph is flatly wrong three times over.**

- **F1. Weapon-sim paragraph contradicts the current sim and its own
  cited tests.** (a) "no cooling happens while firing" — refuted by
  `test_plasma_cannon_between_shot_cooling_matches_ingame`; (b) the
  reload-rate/time semantics — refuted by
  `test_reload_mod_is_rate_semantic_on_both_storage_forms` (stored times
  are divided; `optimal_mult(...) == 2.0` is max, not min; in-game
  validated); (c) "EM Gun: 28.57 shots per heat bar, 20.41 s" — the
  tests assert 29 shots (discrete model) and ≈20.0 s. The sim was
  rewritten (commits b6b7289, b038647) before the doc was extracted from
  CLAUDE.md; the text carried the retired model. TESTED (test file read;
  `uv run pytest -q` → 159 passed). Severity: wrong ×3. Blast: HIGH —
  CLAUDE.md directs revalidation against exactly these tests; a reader
  could "correct" the tests toward the doc.
- **F2. Superhighways are not dashed** — `#ly-shighways` renders solid
  lines; no `stroke-dasharray` on that layer. TESTED (grep both files).
  Severity: wrong (minor visual).
- **F3. highways.csv format description is the pre-spline legacy shape**
  — the CSV is `sector,points,source` spline polylines;
  csv-reference.md says so; the doc kept the endpoint-era description.
  TESTED. Severity: stale.
- **F4. Map overlay inventory incomplete** — contested overlay,
  police/pirate incident markers (fed by the undocumented parsers,
  windowed by `cfg.overlay_hours`), and the Khaak facility kind are all
  undocumented. TESTED. Severity: gap.
- **F5. Three of thirteen viz modules have no section** — `charts.py`,
  `sunbursts.py`, `tables.py`, including the fragile filename-based
  sub-tab routing (`_categorize_sunburst`, `"contested" in src`) that is
  exactly the trap a "page by page" doc should record. TESTED. Severity:
  gap.
- **F6. "90% travel speed (log-validated)"** is a user-editable input
  presented as a constant. TESTED. Severity: minor.
- **F7. Save-specific examples presented as facts** — "30 inert
  anomalies, one per base-game sector" (see wormhole W4: the
  one-per-sector half is false) and the argon/antigone diplomacy numbers
  (see faction F3: the example doesn't show what it claims). Severity:
  unsupported here.

### docs/models/resource-depletion-model.md

Verdict: **the [DOC] layer and the timer algebra are solid — the sweep
*confirmed* starttime = depletion + respawndelay×60 (149/151 events),
arm-at-true-zero, no partial refills, and eligibility gating — but two
headline [OBS] claims are refuted and one [INF] is contradicted by the
XSD the doc itself cites.** Method for the tested findings below: every
`<area>` (3,246/save) extracted with position from all 13 saves and
tracked across 12 consecutive-save transitions
(`/tmp/claude-1000/scratch-resource/` scripts).

- **F1. Respawn relocation is real — the doc wrongly overrode the XSD.**
  Claim: "'at a random location' is not what we observe … respawn is in
  place [OBS overrides DOC]". The sweep found **145 relocations vs 4
  in-place depletions**: at full depletion the record *moves* 20–539 km
  (median 120 km) and is stored depleted with a future starttime; zero
  creations/destructions — pure moves. The doc never observed a
  live→depleted transition at a tracked position; its "in place"
  evidence is the later materialization, which is in-place relative to
  the already-moved record. TESTED. Severity: wrong (~97% of depletions
  relocate). Blast: the trackability section, Appendix B; any per-area
  tracking or mining-advisor plan. Current frames (sector-level pivot)
  are immune.
- **F2. "Individual areas ARE trackable across saves by (position,
  yieldid)" is wrong.** Position breaks at every depletion (F1), and the
  key is not unique: 88 duplicate (sector, yieldid, position) keys
  covering 193 areas, including three depleted areas stacked at one
  position with three starttimes. The superseded "(sector, ware) totals
  only" guidance was safer. TESTED. Severity: wrong.
- **F3. Gatherspeed [INF] is contradicted by the XSD the doc cites.**
  `regionyields.xsd`: the factor applies to "the yield contained in each
  object (for solid resources) or gather speed (for liquid resources)" —
  for solids it scales per-asteroid yield, not extraction rate. The
  frames comment and csv-reference.md both hardened the wrong reading.
  TESTED (XSD re-read). Severity: wrong/overconfident ([INF] treated as
  settled downstream). Blast: map speed labels, any future rate model,
  csv-reference row.
- **F4. "Scrap was never observed to deplete" refuted; open Q5 already
  settled by the save set.** save_003 (predating the doc) holds depleted
  rawscrap; one tiny_rawscrap area shows a full cycle inside the window
  (depleted → re-armed at depletion+20 min → live → re-depleted ×3).
  TESTED. Severity: wrong/stale.
- **F5. "Respawn brings a fresh full area — RESOLVED" overgeneralized
  from n=2.** Of 117 depleted→nonzero materializations, only 18
  reappeared ≥99.5% cap; the low tail is exclusively nividium (min 4.4%
  of cap). Consistent with materialize-full-then-mined-down but that
  requires stripping 95%+ between saves; an amount-scaling term is not
  excluded for nividium. TESTED (mean 0.88, median 0.97). Severity:
  unsupported. Blast: the map's "mineable now" may overstate nividium.
- **F6. Pious Mists [EXP]: valid n=1, framing outruns the recorded
  evidence.** The load-bearing observations (stored 0 "for the whole
  flight"; encyclopedia 5,000) are unrecorded in-game readings; the two
  surviving saves (0.21 h apart) cannot distinguish
  materialize-on-mining-contact from on-approach/targeting; the control
  controls eligibility, not contact. The 4,020+980=5,000 arithmetic does
  exclude third-party mining and pin materialize-to-full for that area
  (and the partner later materialized to 4,020 — another exactly-980
  pull). TESTED (save-side numbers reproduce exactly). Severity:
  overconfident tag; conclusion probably right.
- **F7. Per-area `<reservations>` (743 in the newest save) absent from
  the model doc and the parser** — direct per-area miner-contact
  evidence; the doc's own open Q6 data source. TESTED. Severity: gap.
- **F8. Internal contradiction on cap/respawndelay.** The doc calls
  per-hour figures from it "dimensionally meaningless", then derives the
  single-area ceiling from it — and frames still ships `rate =
  cap/delay×60` summed over **all** areas as the map's right gauge and
  the sunburst rep view, citing this doc; the "has since been reworked"
  note describes a rename, not a rework. TESTED (frames.py:241,262–270;
  viz/map.py:785–807; sunbursts.py:178–188). Severity:
  contradiction/stale. Blast: map rep gauge, sunbursts.
- **F9. Non-reproducible evidence base.** The doc's 3,306-area count is
  3,246 in every surviving save; its 42/204 counts are 41/226 today; part
  of its 13-save set has rotated out, so several [OBS] claims can no
  longer be re-checked. TESTED. Severity: stale (minor).
- **F10. The imported "~3,200 ore/h per M-miner" rate is uncited and
  unvalidated** yet drives every "replenish" figure in the measured
  table. UNTESTED (no source to test). Severity: unsupported.
- **F11. `<position>` omits zero-valued axes** (89 areas) — any tracker
  written from the doc's examples mis-parses ~3%. TESTED. Severity: gap.
- **F12. Gas asymmetry unexamined** — gases fully participate in the
  lifecycle (34/117 materializations) and the XSD gives gatherspeed a
  *different* meaning for liquids; the doc never surfaces either.
  TESTED. Severity: gap.

### docs/models/faction-relations-model.md

Verdict: **storage layout, completeness ("unlisted pair = 0", all 232
vanilla gamestart pairs present with matching values), and the code map
survive; the decay story, the player-rep story, and the directionality
evidence do not.**

- **F1. "Persisted at its current decayed value" is untested inference
  dressed as [OBS].** Across 4 saves spanning 7.9 game-hours, all 11
  booster keys sharing identical (faction, other, time=) are
  byte-identical — zero decay observed anywhere; and the doc's decay
  parameters ("540 s then 0.02") come from `set_relation_boost` calls
  that are **object-level** (`object=$ship`), not faction↔faction — of
  93 boost call sites audited, none creates a decaying faction-pair
  booster. The data is equally consistent with "player-rep boosters never
  decay" or "decayed at load". TESTED. Severity: unsupported. Blast: the
  claim is propagated as fact into savegame-structure.md, db-schema.md,
  viz-internals.md, and db-model-improvements.md T7 (X3); frames'
  numbers are unaffected either way.
- **F2. "Player starts neutral; rep accrues entirely via boosters" is
  wrong for Split/Terran/Yaki.** DLC factions.xml defaults:
  split→player −0.032, terran→player −0.032, yaki→player −0.32; the save
  carries them as base rows, and terran's −2.3e-10 residue shows the
  *base* relation is runtime-mutated (108 player-involving
  `add_faction_relation` call sites in md/). TESTED. Severity: wrong.
  Blast: any base=scripted/booster=earned decomposition.
- **F3. "Directional, not symmetric" — bogus evidence, empirically
  symmetric.** The doc's example compares two different *observers* of
  scaleplate, which says nothing about direction; the actual test — all
  486 base pairs in save_002 — is perfectly reciprocal (0 mismatches, 0
  one-sided), boosters included. TESTED. Severity: wrong (as evidenced);
  the directional display is harmless. db-schema.md repeats it (X4).
- **F4. Locked relations ignored end-to-end.** Nine factions carry
  `<relations locked="1">` (xenon, khaak, scaleplate, …); the parser
  drops the attribute and no doc mentions it — the diplomacy view cannot
  distinguish locked −1 from earnable −1. Also `<faction active="0">`
  uncaptured. TESTED. Severity: gap.
- **F5. The −30..+30 formula is "Approximate" per the game's own header**
  — the authoritative spec is the anchor table with interpolation;
  `_uivalue` gives 25.05 where the game pins 25. TESTED. Severity:
  stale/overconfident (cosmetic).
- **F6. Mod/visitor faction blindness.** 132 factions in the save; 100
  are `visitor001–100` noise rows; the hardcoded roster in
  viz/diplomacy.py that excludes them is a load-bearing decision recorded
  only in code. TESTED. Severity: gap.
- **F7. The clamp and "equals in-game standing" are unvalidated** — no
  in-save pair exceeds |1| (the clip has never fired on real data) and no
  save field stores the game's own effective standing; the equality has
  never been checked against the rep bar. TESTED (clamp scan) /
  UNTESTED (in-game half). Severity: unsupported (should be [INF]).

### docs/models/wormhole-connection-model.md

Verdict: **the link-resolution mechanics are exact (ownership map,
bidirectional mirror, macro facts, 41/30/7/4 counts all reproduce) — but
the interpretive layer above them is largely wrong.**

- **W1. The direction rule ("origin = entry, destination = exit") is
  probably inverted.** The galaxy's only asymmetric linked pair is wired
  by `setup_dlc_pirate.xml`: `add_anomaly_destination
  anomaly=<IVC-752> destination=<WHT-407>`, comment "exit from S3 into
  S2 (not tied to the wave)" — the permanent traversal is **enter
  IVC-752 → exit WHT-407**, opposite to the doc's arrow; in the save the
  *enterable* end owns the `destination`-role connection (the role names
  the partner relationship, not the owner's). Freedom's Reach is
  symmetric, so the doc calibrated its rule on zero discriminating
  cases. TESTED (script + save roles + DB wormhole_link). Severity:
  wrong (probable). Blast: `viz/map.py` draws the warp arrow from
  origin-role links — the map's one asymmetric arrow likely points
  backwards.
- **W2. The Avarice link is tide-cycled, not story-gated.** The S3↔S2B
  pairing is wired at universe generation (no story condition), and the
  reverse direction is added/removed by `TheWave_Anomaly_Activate`/
  `_Deactivate` with each tide — links appear and disappear per cycle,
  so the 30/7/4 census and "Freedom's Reach is the only two-way" are
  snapshots of a time-varying system; a wave-window save would show the
  pair as two-way. TESTED (script cues read in full). Severity: wrong
  (mechanism) + gap. Blast: map tiers/arrows silently change between
  saves with no warning anywhere.
- **W3. "God-placed and script-placed never overlap / every functional
  warp is script-created" contradicts the doc's own examples.** The
  linked WHT-407/IVC-752 are god-placed by the DLC's god.xml and marked
  `class="godobject"` in the doc's own XML excerpts; only Freedom's
  Reach is `class="script"`. TESTED. Severity: wrong + internal
  contradiction. Blast: any tier heuristic keyed on source class would
  misclassify all 8 Avarice warps.
- **W4. "One per base-game sector, each `<sector>_anomaly_01`" is
  false.** god.xml has three `_02` ids; two sectors host two anomalies;
  one entry is placed in a different sector than its name says; ~27
  distinct sectors cover the 30. "Exactly 30" survives; the distribution
  claim doesn't. TESTED. Severity: wrong (low blast).
- **W5. The `<transition destination>` interpretation is shaky.** The
  *linked, active* WHT-407 still carries `destination="0"` (the doc's own
  excerpt), so N does not change on activation and N≠0 has never been
  observed; a DLC god.xml comment suggests it is a boolean eligibility
  flag in an undocumented random-destination mechanic. TESTED. Severity:
  unsupported ([OBS] covers the attribute, not the interpretation).
- **W6. Activator inventory incomplete; Timelines claim dubious.**
  `add_anomaly_destination` is also called from two scripts the doc
  omits; the Timelines usage is in scenario maps (separate galaxies).
  TESTED (full call-site sweep). Severity: gap.
- **W7. Scope gaps: connection taxonomy and mod blindness.** The doc
  never situates wormholes against gates/accelerators/superhighways; and
  `GameFiles` indexes only the 7 official DLC extensions on this ~60-mod
  install — every "swept all 9,215 game XML files" claim in these docs is
  really vanilla+DLC only, on a save that is `modified="1"`. TESTED
  (extension enumeration). Severity: gap. Blast: the trust level of every
  game-file sweep in docs/models/.

### docs/plans/db-model-improvements.md

Verdict: **the critique layer is unusually accurate (all ~35 line
citations resolve; every DB data claim verified on both DBs; all 13 DDL
sketches parse and execute on SQLite 3.53) — but one shared false
premise breaks the trend-layer design, and the migration mechanics are
less "designed path" than claimed.**

- **F1. `save`/`meta` are dropped on every schema bump — the proposal's
  provenance/trend spine doesn't exist.** C1/C8/T5 treat `save` as an
  accumulating import log; store.py drops every non-E table (including
  `save` and `meta`) on a version bump, resetting save_ids. TESTED — the
  8E0C DB the spike measured at 46 save rows on 2026-07-21 now holds 2.
  Consequence: T4's A-tables ("never dropped") would key `save_id` into
  a resettable table — `join save.game_time` silently wrong after a
  bump, T5's rerun guard sees an empty table and re-appends, T3's
  `updated_save_id`/T13's `first_save_id` point into recycled ids, and
  T13's `managed_tables` meta key is dropped by the code path that would
  read it. No proposal promotes `save`/`meta` to never-dropped — a
  required precondition for half the design. Severity: wrong (premise) +
  gap. Blast: T3, T4, T5, T13. **Disposition (2026-07-23): addressed in
  plan** — new critique C12 + new item T0 promote `save`/`meta` to a
  never-dropped P class; T3/T4/T5/T13 declare the T0 dependency; §4
  sequences it first (H0).
- **F2. The EVENT_MIGRATIONS chain has holes and a real DB sits
  off-chain.** `NEXT_VERSION` maps only 1→2→3→4; the 9406 DB is at
  schema v5 (TESTED), so a migration keyed at the current version never
  runs for it — T3's backfill, T12's UPDATE, and T13's ALTER would
  silently skip, then explicit-column INSERTs would crash. Severity:
  unsupported (migration mechanics). Blast: T2 (index half), T3, T12,
  T13. **Disposition (2026-07-23): addressed in plan** — T0 part 2
  completes the version chain (empty tuples for E-quiet versions) with a
  regression test against an off-chain DB; T2's E-indices are rerouted to
  the idempotent `INDEXES` path, off the chain entirely; T3/T12/T13 note
  the T0 dependency.
- **F3. T6's `v_trade` drops executor display columns the dashboard
  consumes.** viz/history.py renders `{side}.proxy.name/.code`; the view
  exposes only executor *entity ids*, unrecoverable for NULL-entity rows;
  and `buyer_proxied = buyer_cmdr_entity IS NOT NULL` diverges from
  frames' `cmdr_id.notna()` (the csv-import path writes cmdr ids with
  NULL entities). TESTED (view executes; 0 divergent rows today).
  Severity: gap (DDL incomplete for its stated consumers).
  **Disposition (2026-07-23): addressed in plan** — T6's `v_trade` gains
  `{side}_exec_name`/`_exec_code` columns and keys both them and the
  proxied flags on `cmdr_id`; re-verified on a copy of the 8E0C DB
  (flags match frames' rule 261/2,038 exactly; exec columns populated
  for every proxied row).
- **F4. "Only ever applied to rows merged before schema v4 … a shrinking
  set" is wrong** — NULL-entity parties are minted at every merge
  (removed-object-resolved and registry-missed parties). TESTED (code
  paths). Severity: wrong (minor). **Disposition (2026-07-23): addressed
  in plan** — T6 restates the claim: the degradation is permanent, not
  transitional, and acceptable because those parties have no registry
  identity to resolve against (with the confirming query noted inline).
- **F5. "Eight occurrences of MAX(save_id)" is seven; "every view
  filters" is false** (two E-views correctly don't). TESTED (grep).
  Severity: stale (trivial). **Disposition (2026-07-23): addressed in
  plan** — C2 corrected to "seven occurrences across six of the eight
  views", grep re-run to confirm.
- **F6. T4's primary keys are decorative for NULL key columns.** SQLite
  permits duplicate rows when a PK column is NULL; NULL `sector_macro`
  occurs in practice. TESTED (duplicate insert succeeds on the sketched
  DDL). Uniqueness then rests entirely on the T5 guard — defeated
  post-bump by F1. Severity: unsupported. **Disposition (2026-07-23):
  addressed in plan** — T4's textual key columns are now `NOT NULL
  DEFAULT ''` with `COALESCE(x,'')` at insert; re-verified on a copy of
  the 8E0C DB (duplicate append now fails with `UNIQUE constraint
  failed`; the old DDL's duplicate acceptance reproduced first).
- **F7. "30 ms/station by durable identity" misquotes the spike** — the
  measurement was by owner_code (the text fallback). TESTED (branch doc).
  Severity: stale (trivial). **Disposition (2026-07-23): addressed in
  plan** — C5 restated: measured via the `owner_code` fallback, the
  durable-identity variant never separately timed.
- **F8. Missed critique: stale-save merges destroy E history** — the
  exact failure a live-mode watcher invites (out-of-order autosaves), and
  the doc's "no change below loses history" framing never notices the
  *current* model can lose history; no T-item adds a merge guard.
  UNTESTED (unambiguous code path; same finding as db-schema F4).
  Severity: gap (high for goal 1). **Disposition (2026-07-23): addressed
  in plan** — new critique C13 + new item T14: a high-water guard
  mirroring the registry's (skip-with-warning), sequenced into the first
  bump (§4 H4); the plan's history-loss statement now admits the current
  model's exposure. Backlog item 3 (proof-of-destruction) remains open
  as the pre-implementation test.
- **F9. Missed critique: `write_reference` rewrites every R table + full
  textdb on every run** — heavy write churn per autosave under a
  watcher. TESTED (code). Severity: gap (minor). **Disposition
  (2026-07-23): addressed in plan** — new critique C14; fix folded into
  T10 as a `meta('reference_digest')` skip-when-unchanged guard.
- **F10. T8's `v_player_fleet` ≠ `_player_edges` in theory** — the view
  JOINs `component` (excludes connectionless components); currently
  equivalent (0 divergent rows, TESTED) but the equivalence assumption is
  unstated. Severity: unsupported (low). **Disposition (2026-07-23):
  addressed in plan** — T8 states the assumption and requires either an
  equivalence test before `_player_edges` is deleted or resolving edges
  pre-filter in `write_snapshot`.
- **F11. T7 "verbatim" is off by one edge** — the view emits rows for
  discount-only pairs that frames excludes. TESTED. Severity: trivial.
  **Disposition (2026-07-23): addressed in plan** — T7 adds
  `AND kind IN ('base','booster')`; re-verified on the 8E0C copy (992
  pairs, exactly frames' base∪booster key set).

Also verified for this doc: `faction_meta.account` raw-cents exactly
(80,545,951 = 100 × 805,459.51), owner_entity coverage 99.24%/99.28%,
spike numbers quoted faithfully, `v_stock_flow`'s `MAX(a,b)`/WINDOW SQL
correct on probe data, T9's CASE reproduces `frames._classify` on every
probe state — but note X21: T9's `respawn_s` column would load *minutes*
from regionyields.csv under a name that says seconds.

---

## Cross-document contradictions

- **X1. `spawntime` NULL vs 0.** db-schema.md says "NULL = world
  creation"; savegame-structure.md and schema.py's own comment say 0.
  Data sides against db-schema.md (0 NULL spawntimes in `entity`).
- **X2. The code-fallback safety rule.** CLAUDE.md, save-semantics.md,
  and db-schema.md all state "codes safe among simultaneously-alive
  same-faction objects", omitting the class condition — refuted by
  RYJ-686 (ship+lasertower), PZZ-881 (station+buildstorage), and the
  XPU-790 same-faction same-class pair. Three docs need the same fix.
- **X3. "Boosters stored pre-decayed"** is asserted as fact in five
  files (faction model, savegame-structure.md, db-schema.md,
  viz-internals.md, db-model-improvements.md T7) and rests entirely on
  the faction model's unsupported F1. One correction must propagate to
  five places. **Disposition (2026-07-23): addressed in plan for the
  db-model-improvements.md instance** — T7 no longer asserts the claim;
  it states the decay question as unconfirmed (pointing at backlog
  item 9) and notes the view is correct under any resolution. The other
  four documents are out of this revision's scope and still carry the
  claim.
- **X4. "Relations are directional"** (faction model, db-schema.md) vs
  perfect reciprocity of all 486 pairs in the save.
- **X5. Wormhole arrow direction.** The model doc, savegame-structure.md
  § Anomalies, and viz/map.py's comment all encode origin=entry — the
  DLC script comment implies the opposite.
- **X6. "Functional warps are script-created"** (wormhole model prose)
  vs `class="godobject"` in the same doc's excerpts and in
  savegame-structure.md.
- **X7. "No destroyed events in this playthrough"** (db-schema.md
  never-populated section, save-semantics.md) vs 6 destroyed events in
  the save in new v9 wording — "no matching entries" conflated
  regex-mismatch with absence.
- **X8. Economy-event vocabulary.** save-semantics.md Layer 3 speaks of
  `<modifier type="discount">`; the save's population is predominantly
  `type="commission"` plus per-station `<commissions><booster>` blocks —
  and savegame-structure.md documents none of them, so the two docs
  describe the same mechanism with disjoint vocabulary.
- **X9. Gatherspeed semantics.** Model doc [INF], frames.py comment, and
  csv-reference.md all say extraction-rate; the XSD says per-object yield
  for solids / gather speed for liquids.
- **X10. cap/respawndelay rates.** Model doc: "dimensionally
  meaningless"; csv-reference.md states "max replenishment rate = yield ÷
  respawndelay" flatly; frames/map/sunbursts ship the summed rate citing
  the model doc.
- **X11. Depleted-area encoding + yieldid grammar.** savegame-structure
  says a past-starttime area "still reads yield=0" (actually the
  attribute is absent — model doc is right) and lists ware `scrap` /
  optional speed token (absent from every area of this playthrough;
  neither doc scopes its claim to a playthrough).
- **X12. `idx_stock`.** db-schema.md claims it serves the v_stock_delta
  scan; db-model-improvements.md documents (correctly) that it can't.
  **Disposition (2026-07-23): plan side already correct; strengthened**
  — the plan's C5 additionally corrects its own "serves the merge" half
  (`EXPLAIN QUERY PLAN` shows the merge's time-keyed queries SCAN too).
  The db-schema.md half is out of this revision's scope.
- **X13. `save` as accumulating provenance.** db-schema.md and
  db-model-improvements.md share the false premise; schema bumps drop it.
  **Disposition (2026-07-23): addressed in plan for the
  db-model-improvements.md instance** — see plan F1: C1/C8/§2 restated,
  T0 makes the premise true going forward. The db-schema.md instance is
  out of this revision's scope.
- **X14. Stale one-off numbers duplicated across docs.** "~40×"
  (measured 26×/66×) and "163 recycles / 21 min" (unreproducible) appear
  in both save-semantics.md and db-schema.md.
- **X15. The 6.105 h "constant"** (save-semantics.md) vs
  analysis/storage.py's per-station normalizer with FOOD_HOURS = 4.0.
- **X16. Gamedata dashboard modules.** architecture.md lists five
  modules; viz-internals.md correctly says one tab (weapons only);
  engines.py's docstring sides with viz-internals.
- **X17. Weapon-sim model.** viz-internals.md vs tests/test_weaponsim.py
  — the doc contradicts the tests CLAUDE.md designates as the source of
  truth.
- **X18. trade_tx "full flavor" definition.** db-schema.md cites
  savegame-structure's two-flavor model, which is incomplete (four
  ledgers, tradeentry family, price-less rows) and neither doc explains
  `v_stock_delta`'s `ware != ''` guard.
- **X19. MXH-411 circularity drift.** test_drones.py's docstring frames
  it as "floor 40 vs true 310"; save-semantics.md lists "MXH-411 310"
  under in-game validation of the formula it was fitted to.
- **X20. Advisor gate handling.** csv-reference.md's oneway
  documentation vs sectorgraph.py's undirected + same-cluster-full-mesh
  graph — the discrepancy lives in no doc.
- **X21. Resource-status units.** db-model-improvements.md T9 names the
  column `respawn_s` but its load source (regionyields.csv) is minutes —
  any SQL eta arithmetic against `starttime` (seconds) inherits a 60×
  bug; T9 also freezes the status model pre-relocation/nividium
  corrections. **Disposition (2026-07-23): addressed in plan** — T9's
  column is now `respawn_min` (kept in source units, conversion duty
  named), and T9 carries the nividium partial-refill and relocation
  caveats with pointers to backlog items 5/11; the revised view was
  re-verified against `frames._classify` on all 3,246 areas (0
  mismatches).

---

## Prioritized research backlog

Each item: the open question, method, executor (**agent** = runnable
in-session; **play** = requires in-game action), the evidence it settles,
and the documents it upgrades. Ordering: P1 = corrects data currently
feeding features or protects irreplaceable history; P2 = converts
load-bearing hypotheses into confirmed models; P3 = cleanups and
unit/provenance questions.

### P1 — corrects live errors / protects data

1. **Re-model the economylog as four typed ledgers.** What do the
   `money`-block `tradeentry` records index (money always cents? partner
   direction?), and do `v`-less owner rows really mean stock 0? Method:
   save sweep matching money-block records to trade-block transactions at
   shared timestamps, plus same-save cross-check of a station's `<cargo>`
   vs a v-less row. Executor: agent. Settles: correct `_merge_trades`
   ingestion (stop shunting tradeentry into `stock_event`; validate or
   drop the stock=0 assumption behind LAG deltas). Upgrades:
   savegame-structure.md § economylog, db-schema.md § stock_event/trade_tx.
2. **Harvest actual v9 log wordings and rewrite the logparse regexes.**
   Destroyed wording is known-changed (6 unparsed events in the save);
   resupply is v9-confirmed via the 559 h DB; construction/repair/
   transfer/surplus unknown. Method: scan all 13 saves' logbooks (and
   `cache_log_*.csv.gz`) for title/text patterns; re-run parsers over
   archived `log_entry` rows. Executor: agent. Settles: revives
   `event_destroyed`/`event_construction`/`event_transfer` and their
   dashboard tabs. Upgrades: savegame-structure.md, save-semantics.md,
   db-schema.md, architecture.md.
3. **Prove and guard the older-save merge destruction.** Method: copy a
   DB to scratch, merge an older save of the same playthrough, diff
   E-table extents — then decide the guard (mirror the registry's
   high-water check in `merge_events`). Executor: agent. Settles: whether
   one wrong `--save` (or an out-of-order autosave in watch mode) wipes
   history. Upgrades: db-schema.md § merge semantics,
   db-model-improvements.md (new T-item).
4. **Settle the wormhole arrow.** Method (agent): sweep archived saves
   for a tide-wave window where WHT-407/IVC-752 hold 4 link rows — the
   2-row direction that persists after deactivation is the permanent
   link; re-read the role semantics from that. Method (play, definitive):
   fly to Avarice V Dead End / Unknown System in a calm phase and try
   both ends. Settles: W1 + W2 (and whether map tiers must be
   save-time-dependent). Upgrades: wormhole-connection-model.md,
   savegame-structure.md § Anomalies, viz-internals.md.
5. **Rewrite the resource trackability/relocation model.** Method:
   extend the 12-transition sweep (displacement-vector clustering; why
   moves share 1–2 coordinates; scrap re-landing) and parse per-area
   `<reservations>` (743 rows) to join miner contact against
   depletion/materialization events — population-scale evidence for the
   contact trigger that replaces the n=1 experiment's gap. Executor:
   agent. Settles: F1/F2/F6/F7 of the resource model in one campaign.
   Upgrades: resource-depletion-model.md (trackability, random-location,
   contact-trigger sections), db-model-improvements.md T9.
6. **XPU-790 forensics + registry idempotency.** Method: sweep
   save_001/save_002 for code XPU-790 — one physical ship means a
   duplicate-mint/idempotency bug in `update_entity_registry` (the
   double `save` row for one file is the suspect path); two ships means
   a live same-faction same-class collision, killing the fallback rule
   in-game. Either way, add the class condition to the rule in three
   docs. Executor: agent. Settles: db-schema F2 / save-semantics F6 / X2.
   Upgrades: db-schema.md, save-semantics.md, CLAUDE.md.
7. **Make the improvement plan's spine real before building on it.**
   Method: promote `save`+`meta` to never-dropped (E-class or successor
   run-log) with a regression test that a SCHEMA_VERSION bump preserves
   them; fill the `NEXT_VERSION` chain 4→10 (the 9406 DB at v5 is live
   evidence); enumerate the tradelog columns viz consumes before T6.
   Executor: agent. Settles: db-model-improvements F1/F2/F3. Upgrades:
   db-model-improvements.md (amended T-items).

### P2 — converts hypotheses into models

8. **Full-galaxy Layer-2 pricing fit with pending.** Method: sweep the
   newest save for committed `<trade partner=…>` records under `<order>`
   containers (2,617 exist — structure now located), join
   stock/offers/computed targets, fit the curve across all wares; test
   clamping and whether the pricing target equals the storage-model
   target at all. Executor: agent. Settles: save-semantics F1/F3/F4
   (6.105 h vs per-station T; linearity beyond energy; clamp bounds).
   Upgrades: save-semantics.md § pricing, x4-pricing-model memory.
9. **Booster decay: observe or kill.** Method (agent): diff all future
   dated saves for any (pair, time=)-stable booster whose value drops.
   Method (play): trigger a known rep event, save twice ≥1 game-hour
   apart untouched. Also (play): compare clamp(base+Σboosters) to the
   in-game rep bar for 3 factions. Settles: faction F1/F7 and the
   five-document X3 propagation. Upgrades: faction-relations-model.md +
   four downstream docs.
10. **Gatherspeed semantics for solids.** Method (agent): game-file
    analysis of how the factor enters asteroid spawning; Method (play):
    time identical miners on same-level fast vs slow areas. Settles:
    resource F3 / X9. Upgrades: resource-depletion-model.md,
    csv-reference.md, frames.py comment.
11. **Nividium respawn amount.** Method (play): park one miner at a
    depleted nividium area past eligibility, save before/after first
    pull; first-pull + stored should equal cap if materialize-to-full
    holds. Settles: resource F5 (the one materialization family below
    cap). Upgrades: resource-depletion-model.md.
12. **Fire the epoch machinery once.** Method: scratch-DB copy, merge two
    synthetic disjoint windows via `store._merge_window`, verify epoch
    increment and `v_stock_delta` gap isolation. Executor: agent.
    Settles: db-schema F9 (epoch semantics from hypothesis to
    CONFIRMED). Upgrades: db-schema.md.
13. **Mod visibility end-to-end.** Method: establish why `GameFiles`
    sees 7 extensions on a ~60-mod install (game-dir vs user-dir vs
    workshop paths); check `content.xml` `save=` flags against the
    9-entry `<patches>` block; extract mod modcaps to close the 96
    missing macros behind `capacity_floor`. Executor: agent. Settles:
    wormhole W7, savegame-structure F11, save-semantics F10, csv F4/F7
    fragility — and the trust level of every "swept all game files"
    claim. Upgrades: csv-reference.md, wormhole model, save-semantics.md.
14. **Pricing Layer-3 structures: commissions and modifiers.** Method:
    document `<commissions><booster>` (stations) and
    `<known>…<modifiers><modifier type="commission|discount">` from the
    save; correlate active discounts in offers with modifier records;
    play-half for the stacking bound (a 25%-tier station with an active
    event should hit 0.5×min). Executor: agent + play. Settles:
    savegame-structure F9/F17, save-semantics F5, X8. Upgrades: both
    docs.
15. **Re-import the 559 h playthrough with the current pipeline.**
    Method: run analyze on the old playthrough's newest save (its DB is
    at schema v5 — also a live migration test); confirms `write_derived`
    populates event_construction end-to-end and exercises item 7's chain
    fix. Executor: agent. Settles: db-schema F10, save-semantics F9,
    db-model-improvements F2. Upgrades: db-schema.md.

### P3 — cleanups, units, provenance

16. **Re-measure the recycle rate.** Import save_008 + save_009 (24 min
    apart) into a scratch DB, count recycles per game-minute — replaces
    the unpinned "163/21 min" in two docs. Agent. Upgrades:
    save-semantics.md, db-schema.md.
17. **Mission `reward` and `distance_*` units.** Multi-save pair with a
    completed mission in between (reward vs logbook `money`);
    consecutive-save distance deltas vs known travel; in-game stats
    screen as the tie-breaker. Agent (bounds) + play (confirmation).
    Upgrades: savegame-structure.md.
18. **Trade-block `transfer` entries (176).** Attribute census +
    logbook cross-ref: do they belong in trade_tx (player internal
    transfers = the missing slice of `trades_executed`)? Agent.
    Upgrades: savegame-structure.md, db-schema.md.
19. **Station oddments.** `<locked>` (73), station `<subordinates>`
    (34), `<economylog cargo= offer=>` attrs, NPC `<tolerance>` boosters
    (345) — correlate across saves for meaning. Agent (structure) +
    play (semantics). Upgrades: savegame-structure.md,
    faction-relations-model.md (tolerance decay params).
20. **Perf + census refresh.** Re-time the parse ("~18 s / 270 MB") and
    the find sweep on current code; census inert anomalies per sector
    (viz F7); relabel the save-specific diplomacy example. Agent.
    Upgrades: architecture.md, CLAUDE.md, viz-internals.md.
21. **Reference-data provenance.** Record game version + DLC list at
    extraction time; add `source` to recipes/modcaps and route
    regionyields through `_variant_paths`; decide sectorgraph's `oneway`
    handling (X20). Agent (the in-game route-hop validation for
    Savage Spur is play). Upgrades: csv-reference.md.
22. **Encyclopedia `<known>` ledgers.** Document the 42 typed `<entries>`
    blocks and `read=` flags — would also settle the component
    `known`/`read` attrs marked "(semantics unverified)". Agent.
    Upgrades: savegame-structure.md.

---

## Review-constraint verification

- Every in-scope document has a findings section above; none received a
  clean "survived review" verdict, though the per-document verdict lines
  state what did survive (the census/inventory layers were near-perfect
  everywhere).
- Tested findings carry their reproduction (query, sweep, or file read)
  inline; agent working scripts live under `/tmp/claude-1000/scratch-*/`
  (session-temporary, not part of the repo).
- No reviewed document was modified: the review ran read-only against the
  repo, the saves, and the DBs (opened `mode=ro`); this file is the only
  addition to the working tree.
