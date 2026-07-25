# Phase 7 — research track P1 + trust-setter (B4, B5, B13)

Executed 2026-07-24 per
[execution-roadmap.md](../plans/execution-roadmap.md)'s research track.
Commits: B4 `9dd0f74`, B13 `35da463`, B5 `6307526`, this report +
ledger update (see `git log`). `uv run pytest -q` green at every commit
(205 passed). Real analysis DBs opened read-only throughout; SHA-256
checksums verified unchanged start → finish:

```
cf4ccf029250e02bb22733aac42d604634a545bf6436b446fa158e49e26d653a  x4_8E0C8E37-….sqlite
9a1911420401faebbcff7d99dfa1939ea1f0999657f4570e4572155cffc167a2  x4_94062A45-….sqlite
```

Working data: one combined streaming extractor
(`$CLAUDE_JOB_DIR/tmp/extract_combined.py`, ~4 s/save) ran once over all
13 archived saves, emitting per save: game time, all 3,246 resource
areas (with reservation counts), per-area reservation ids, all 41
anomalies, and every wormhole `<connection>` row. quicksave and
save_006 share game time 78,583.099 (same state saved twice) — analyses
use the 12 unique-time saves / 11 consecutive transitions.

---

## B4 — settle the wormhole arrow

**Question.** Does the `connection` role `origin` mark the enterable end
(the doc's rule) or is the rule inverted (review W1)? Is the Avarice
link tide-cycled (W2), and must map tiers be save-time-dependent?

**Method.** (1) Sweep all 13 saves for the WHT-407/IVC-752 link rows,
hoping for a 4-row tide-wave window; read role stability either way.
(2) Read the DLC's wiring script first-hand via `GameFiles`
(`extensions/ego_dlc_pirate/md/setup_dlc_pirate.xml`).

**Evidence.**

- Sweep: **every save holds exactly 6 link rows** — 2 for the Avarice
  pair, 4 for Freedom's Reach. The hoped-for 4-row wave window was
  never captured: all 13 saves are calm-phase. In all of them,
  byte-stable: WHT-407 (Dead End, `S2B_anomaly_01`, godobject) owns the
  `origin`-role connection; IVC-752 (Unknown System, `S3_anomaly_01`,
  godobject) owns the `destination`-role connection. Tier census 30
  inert / 7 dormant / 4 linked reproduces in every save.
- Script (decisive): the permanent link is wired at universe generation
  by `add_anomaly_destination anomaly=$AnomaliesS3toS2
  destination=$AnomaliesS2toS3` with comment *"exit from S3 into S2
  (not tied to the wave)"* (lines ~1928/1936/1944) — the `anomaly=`
  argument (IVC-752) is the **enterable** end. `TheWave_Anomaly_Activate`
  (line ~2520) adds only the **reverse** direction
  (`anomaly=$AnomaliesS2toS3`) and `TheWave_Anomaly_Deactivate`
  (~2531) removes exactly it.

**Verdict.** W1 settled — **the doc's rule was inverted**. The
`connection` role names the **partner**, not the owner: the entry owns
the `destination`-role connection (pointing at its exit), the exit owns
the `origin`-role back-pointer. Traversal is IVC-752 → WHT-407. W2
refined: only the *reverse* edge is tide-cycled; the permanent edge and
all tier assignments are stable, so **map tiers need not be
save-time-dependent** — a wave-window save would add one arrow, not
change the census. Grade: **[SCRIPT]+[OBS]** — decisive at the
script/save level; the agent sweep alone (no wave window) is only
suggestive, so the CONFIRMED tag waits on the play half (fly both ends,
play checklist below).

**Map fix (flagged).** `viz/map.py` drew the galaxy's one asymmetric
arrow **backwards** (edges were built from `origin`-role links). Fixed:
edges now derive from `destination`-role links, arrow entry → exit, and
only the entry end carries a "Warps to" destination
(`map.py` `_payload`, `map_page.js` comments, `test_map_prep.py`
pinned to the corrected semantics). Dashboard rebuilt end-to-end
against a scratch data dir (`XDG_DATA_HOME` override; real DBs
untouched) — build clean.

**Doc fixes applied (DF-2).** X5 (arrow direction) in
wormhole-connection-model.md, savegame-structure.md § Anomalies,
viz-internals.md; X6 (functional ≠ script-created — WHT-407/IVC-752 are
god-placed by the DLC's god.xml, only Freedom's Reach is
script-created) in the model doc. Plus the tide-cycle section and
census-stability note (W2's doc consequence).

---

## B5 — resource trackability / relocation model

**Question.** Do depleted areas relocate (review F1, against the doc's
"in place" [OBS-overrides-DOC] claim)? Is (position, yieldid) a valid
cross-save key (F2)? Can the n=1 contact-trigger experiment be replaced
with population-scale evidence (F6/F7)?

**Method.** Fresh extraction of all 13 saves (4 had rotated since the
review's 2026-07-23 TSVs); relocation census per (sector, yieldid)
group over 11 consecutive transitions; greedy nearest-pairing of
lost→gained positions into displacement vectors; lattice/axis/pool
tests; per-area `<reservations>` parsed and joined against lifecycle
transitions; reservation id resolved against the save's components.
Scripts: `$CLAUDE_JOB_DIR/tmp/b5_analysis.py`, `b5_analysis2.py`, plus
inline lattice/reservation-resolution snippets.

**Evidence.**

- **Relocation census**: 123 count-preserving position changes vs **6**
  in-place live→depleted; 0 creations, 0 destructions (3,246 areas in
  every save; all moves in-sector). Moved-away rows were live (120/126);
  moved-in rows depleted (124/129) with future starttimes.
  `starttime − respawndelay×60` lands inside the transition window for
  120/121 moved-in depleted rows — the move is stamped at depletion.
  (One outlier carries a stale pre-window starttime, matching the known
  stale-timer leftover behavior.)
- **Displacement clustering**: all 123 vectors are per-axis multiples
  of 20 km (2 with a 10 km component; residual "off" cases are float
  dust ≤ 0.01 m). Coordinates keep their fractional residues across
  moves. Axis-share rates (x/y/z kept: 18/47/21 of 123) sit ~1.5–2×
  above the chance baseline from per-sector coordinate domains (median
  domain sizes 13/4/13) — the "shares 1–2 coordinates" phenomenon is
  lattice steps of 0 plus tiny y domains. Distances 20–520 km, median
  130. Not a slot pool: 23/123 targets ever previously occupied by any
  area of the sector; 6/123 exact re-landings for the same group.
- **Reservations**: `<reservation id="[0x…]"/>` under `<area>` resolves
  to the claiming **miner ship's component id** (verified: `[0xa3f4]` →
  `ship_par_m_miner_liquid_01_a_macro` code FLF-530 in the same save).
  Newest save: 517 rows on 251 areas — 508 on live, 9 on
  depleted-eligible, 0 on depleted-pending.
- **Contact-trigger join** (stable-position areas, 11 transitions):
  materializations 103, of which 57 carried a reservation snapshot;
  eligible-but-stayed-0 transitions 1,383, of which 30 carried one;
  in-place depletions 6, of which 5 reserved. Reservation-carrying
  areas materialized at **66%** vs **3.3%** without (~20×).
- **Scrap**: 0 depletions/relocations in-window; **1 in-place
  materialization** of a depleted scrap area; 2 depleted scrap areas in
  the newest save (plus the review's recorded full tiny-rawscrap
  cycle).
- **New anomaly-grade oddity**: 4 depleted small-nividium records moved
  *again* with re-armed timers — indistinguishable between an invisible
  full cycle (materialize→strip→re-deplete a 500-cap area between
  saves) and an unclaimed re-roll. Recorded as open question 7,
  hypothesis only.

**Verdict.** F1 CONFIRMED at scale (the XSD's "at a random location"
was right; the doc's in-place override reversed). F2 settled:
position-keyed identity is valid only **between** depletions (89
duplicate keys / 196 areas in the newest save demand multiset
handling); coordinate residues mod 20 km survive moves and are recorded
as an untested re-linking recipe. F6 upgraded from n=1 [EXP] to
[EXP]+population-[OBS]. F7 discharged: reservations documented with
resolved semantics (parser support noted as an extraction-backlog
candidate, not implemented).

**Docs.** resource-depletion-model.md rewritten (header, one-paragraph
model, random-location/relocation section, lifecycle, trackability,
scrap, contact-trigger + reservation join, open questions 2/5/6/7,
Appendix B, one-line summary). Caveat refreshes: db-schema.md
`v_resource_area` row and db-model-improvements.md T9 bullet now cite
the settled verdict; csv-reference.md's `yield ÷ respawndelay` sentence
restated as the contact-cycled single-area ceiling (the B5-settled half
of X10).

---

## B13 — mod visibility end-to-end

**Question.** Why does `GameFiles` see 7 extensions on a ~60-mod
install; do mod capacity entries reach `module_cap` or hide behind
`capacity_floor`; what does this do to every "swept all game files"
claim?

**Evidence.**

- **Discovery**: `catalog.py` `GameFiles.__init__` defaults to folders
  matching `ego_dlc_*` — 7 of **74** installed extension folders (67
  mods). Workshop (`steamapps/workshop/content/392160`) and user-dir
  extension paths are **empty**; everything is in the game dir, so the
  name filter is the entire gap.
- **Identity & enablement**: folder name ≠ `content.xml` content id
  (folder `vro` = `ws_1696862840`). The per-playthrough enable list
  (`~/.config/EgoSoft/X4/12073019/content.xml`) disables 14 of the 67
  (including VRO). Nothing in the analyzer consults it — and
  `--include-mods` loads *all* non-DLC folders alphabetically,
  disabled ones included.
- **Save stamping**: the save's `<patches>` block holds 9 entries = 7
  DLCs + the 2 enabled mods whose `content.xml` lacks
  `save="0|false"` (Habitat Capacity Boost `ws_3737446888`,
  Respectable Terran Crews `ws_3566937504`). The other ~51 enabled mods
  are runtime-active but invisible in the save.
- **Cat vs loose**: 59 of 67 mods ship `ext_*.cat`; **8 are
  loose-file-only** (among them the four `*-mod-rebalance` dev mods) —
  invisible to the catalog index (and hence to `glob()`/sweeps) even
  with the name filter removed; `read_bytes` reaches them only via the
  game-dir loose fallback.
- **Diff opacity**: mod payloads are mostly attribute-level
  `<diff><replace sel="…/@attr">` patches. The tag-scanning extractors
  see no elements in them — even a mod-aware sweep would silently
  no-op on such changes without a diff-patch engine.
- **`module_cap` / capacity floor**: the DB's 96 built-module macros
  with no `module_cap` row were each checked against the vanilla+DLC
  files: **all 96 exist there and declare no workforce/cargo/storage
  properties at all** (landmarks, struct connectors, claim modules…).
  Queries: `SELECT count(DISTINCT macro) FROM v_built_module WHERE
  macro NOT IN (SELECT macro FROM module_cap)` → 96 (read-only
  connect); per-macro `properties/workforce|cargo|storage` parse → 0
  hits.
- **The live drift**: Habitat Capacity Boost (enabled AND save-stamped)
  replaces `workforce/@capacity` on 20 habitat macro files —
  `hab_arg_s_01_macro` 250 → **2,500** (mod payload read from its cat)
  — while `modcaps.csv`/`module_cap` carry vanilla values for the
  playthrough's **2,499 built habitat modules**.

**Verdict.** The "7 of ~60" mystery is fully explained (name filter;
nothing else). The review's csv F4 hypothesis — mod modcaps hiding
behind `capacity_floor` — is **refuted**: the 96 absences are benign,
capacity-less vanilla content; `capacity_floor` hides nothing. The real
mod effect on reference data is **value drift on rows the CSV already
has** (habitat housing ~5–10× understated for this playthrough).
Trust rule recorded: "swept all game files" = the cat-indexed
vanilla+DLC virtual filesystem, on saves that are `modified="1"`.

**Docs.** csv-reference.md: trust-scope section, load-order/`--include-
mods` corrections, modcaps coverage note. wormhole-connection-model.md:
W7 scope section — including the concrete case of `new_anomaly_sbh_toa`
(disabled), whose cat patches `wormhole_v1_macro.xml` itself.

**Follow-up items (recorded, not implemented).**

1. Enable-list-aware extension discovery (read the user
   `content.xml`, map content ids ↔ folders) for `GameFiles` /
   `--include-mods`.
2. Loose-file extension indexing (glob extension dirs when no
   `ext_*.cat` exists).
3. A `<diff>` patch applier for library/macro extraction (needed before
   any mod-aware modcaps/wares re-extraction; would fix the habitat
   drift).
4. `save/parser.py`: collect per-area `<reservations>` (B5's F7 data
   source) if a per-area mining feature lands.

---

## DF-2 disposition

**Applied this phase** (each names its settled gate):

- **X5** (gate B4 — settled at [SCRIPT]+[OBS] grade): arrow direction
  corrected in wormhole-connection-model.md, savegame-structure.md
  § Anomalies, viz-internals.md, and the code comment/behavior in
  viz/map.py.
- **X6** (gate B4): "functional warps are script-created" replaced with
  the two-provenance statement (god-placed DLC warps vs the
  script-created Freedom's Reach pair).
- **X10, B5 half** (gate B5): csv-reference.md's flat
  "max replenishment rate = yield ÷ respawndelay" restated as the
  contact-cycled single-area ceiling. The map/sunburst summed-rate
  code half remains with the gatherspeed question.

**Previously applied** (verified, for the ledger): X2 (gate B6) is
present in all three docs; X7/X18 shipped with Phase 3.

**Still gated:**

- **X3** — gate **B9** (play): booster decay, five-doc propagation
  (four remaining).
- **X8** — gate **B14**: commissions/modifiers vocabulary.
- **X9 + X10 remainder** — gate **B10**: gatherspeed semantics for
  solids (csv-reference row, frames.py comment, map speed labels /
  summed-rate gauge).
- **X14** — gate **B16**: stale recycle-rate numbers in
  save-semantics.md + db-schema.md.
- **X20** — gate **B21**: sectorgraph `oneway` handling.

---

## Play checklist (all open play items)

Save files go to the usual save dir
(`/home/adam/.config/EgoSoft/X4/12073019/save/`) — use **manual save
slots** (they persist; autosaves rotate) and note the slot names used.

1. **B4 — fly both ends of the Avarice warp** (upgrades the inverted
   arrow from [SCRIPT] to CONFIRMED).
   - In a **calm phase** (no tide wave running), fly to **Unknown
     System** (Avarice's neighbor, sector `cluster_504_sector001`) and
     enter the Stable Warp Anomaly **IVC-752**. Expected: you exit at
     **WHT-407** in Avarice V Dead End.
   - Then, still calm-phase, try to enter **WHT-407** from Dead End.
     Expected: not traversable (it's the exit end).
   - Optional bonus: during a tide wave, save once while the wave is
     active (any slot) — that save should show the pair with 4
     `<connection>` rows, capturing the never-yet-seen two-way state.
   - Evidence settled: entry/exit assignment; one save during a wave
     additionally pins W2's 4-row encoding.
2. **B9 — booster decay: observe or kill** (settles faction F1/F7,
   unblocks the X3 five-doc propagation).
   - Trigger a known reputation event (e.g. destroy a criminal ship
     near a faction's station or complete a mission with a rep reward),
     then **save immediately** (slot A).
   - Leave that faction completely untouched for **≥1 game hour**
     (fly elsewhere), then **save again** (slot B) without further rep
     events for that faction.
   - Also: for 3 factions, note the in-game rep bar value (screenshot
     or jot the number) right at one of the saves.
   - Evidence settled: byte-diff of the same booster keys between A/B
     shows decay or its absence; clamp(base+Σboosters) vs the noted rep
     bars validates (or kills) the standing formula.
3. ~~**B11 — nividium respawn amount**~~ — **DISCHARGED 2026-07-24,
   no flight needed.** The item's protocol (depleted nividium past
   eligibility, save before/after first pull) is exactly the Pious
   Mists XI experiment already performed (980 + 4,020 = 5,000 = cap),
   which the player confirms as that very test and definitive. F5
   resolved: materialize-to-full holds for nividium; the sweep's
   below-cap tail is drawdown between saves. The
   `'full'`-overstates-nividium caveat is retired in db-schema.md and
   plan T9.
4. **B10 (optional play half) — gatherspeed timing** (with the agent
   half, settles X9/X10-remainder).
   - Pick two areas of the **same ware and level** but different speed
     tokens (one `fast`, one `slow` — the map/`v_resource_area` lists
     `speed`). Park one identical miner on each, note game time, let
     both fill (or run a fixed interval), compare cargo gathered.
   - Evidence settled: whether the factor scales extraction rate for
     solids (vs per-asteroid yield as the XSD reads).
5. **B14 (optional play half) — pricing stacking bound**.
   - Find a station where you hold a **25% commission tier** and wait
     for/trigger an active discount event at it; check one ware's buy
     price against `0.5 × min price`.
   - Evidence settled: whether commission+event discounts clamp at
     0.5×min (the Layer-3 stacking bound).
6. **B17 (optional play half) — mission reward / distance units**.
   - Open the in-game **stats screen** and note total mission rewards
     and distance-travelled figures; save right after (any slot).
   - Evidence settled: the tie-breaker between the save's `reward` /
     `distance_*` candidate units and the game's own displayed totals.
7. **B19 (optional play halves) — station oddments semantics**.
   - `locked`: try to trade with / dock at a station whose save record
     carries `<locked>`; note the UI behavior.
   - NPC `<tolerance>` boosters: commit a minor crime (scan/theft) near
     a faction station, note the tolerance drop and how long until it
     recovers; save before/after (two slots).
   - Evidence settled: what `locked` gates in the UI; tolerance decay
     parameters for the faction model.
8. **B21 (optional play half) — Savage Spur hop validation**.
   - Fly the **Savage Spur I → II** accelerator, then attempt the
     reverse trip; note that the return needs a different route.
   - Evidence settled: the one-way `oneway` encoding in gates.csv
     matches in-game traversal (X20's ground truth).

No main-sequence or research-track work waits on any of these; each
upgrades its doc fix from "probable" to confirmed when done.
