# Plan: Player-View Mode (reveal masking + live/stale coverage flag)

Status: **planned, not implemented**. This document is the design; nothing in
it has been built yet.

## Goal

An opt-in `--player-view` mode that restricts every view to information the
player character could actually possess, instead of the save's omniscient
global state:

1. **Reveal masking (exact):** objects the player has never revealed
   (`knownto != "player"`) disappear from all views entirely.
2. **Coverage flag (approximation):** known stations are classified **live**
   (player currently has intel coverage → prices/offers trustworthy) or
   **stale** (revealed in the past, no current coverage → values flagged as
   unreliable). The save does not store last-seen snapshots, so stale
   stations show *current* values visibly marked as "not what the player
   would see" — masking trust, not reconstructing history.

## What the save provides (feasibility findings, 2026-07-05)

- `knownto="player"` / `known` attributes are the **only** persisted player
  knowledge. In the reference save: 1,342/1,736 stations, 125/152 sectors,
  8,090/14,420 NPC ships revealed.
- **No** per-offer timestamps, price snapshots, station scan state, or any
  staleness data exist anywhere in the save (verified by attribute sweep).
- Player intel sources are reconstructible: 343 deployed player satellites
  (`class="satellite" owner="player"`), player ships/stations (positions and
  sector ancestry stored), and faction trade subscriptions via the player
  faction's `<licences>` block.

## Scope

**In scope:** reveal masking everywhere; sector-granular coverage model;
live/stale marking in the Market tab; player-view treatment of omniscient
columns (minimal version, see step 6).

**Out of scope (deferred):** radius-accurate satellite coverage (phase 2,
sketched at the end); any attempt at historical/stale *values*; Tier-3
redesign of capacity columns (kept with a caveat banner for now).

## Implementation steps

### 1. CLI / config

- `Config.player_view: bool = False`; CLI flag `--player-view`.
- `player_view` implies `spoilers_hide` (it is a strict superset — assert
  this relationship in one place, e.g. `Config.__post_init__` or where the
  CLI builds the config).

### 2. saveparser: two new collections

- **Satellites:** on component start, `class == "satellite"` and
  `owner == "player"` → record `(id, sector_macro)` into
  `SaveData.player_satellites`. (Positions deliberately ignored in phase 1.)
- **Player licences:** inside `<faction id="player">`, collect
  `<licence type=... factions=...>` rows into `SaveData.player_licences`
  as `(type, factions_string)`. The `in_faction_player` depth counter that
  already exists for the custom faction name can gate this.
- Fixture test additions: one satellite component, one licence element;
  assert both collections.

**Verification task:** confirm the licence `type` string the game uses for
trade subscriptions (expected something like `tradesubscription`; the
reference save's player has no such licence yet, so check
`libraries/factions.xml` licence definitions or a save where the
subscription rank has been reached). Until confirmed, treat the
subscription set as possibly empty — the model degrades gracefully.

### 3. frames: visibility classification

New dataframe `Frames.station_visibility` (`id`, `known: bool`,
`live: bool`), built as:

- `known` = station `knownto == "player"`.
- `covered_sectors` = set of `sector.macro` containing ANY of: player ships,
  player stations (from `playerowned`), or player satellites.
- `subscribed_factions` = owner ids whose faction appears in a
  trade-subscription licence.
- `live` = `known and (sector in covered_sectors or owner in
  subscribed_factions)`.

Also expose `Frames.visibility_counts` (known/live/stale/hidden totals) for
logging and the dashboard header.

### 4. Reveal masking (applies only when `player_view`)

Filter at the *input* level so every downstream metric inherits the mask:

- `viz/market.py`: `stations` set additionally requires `known`. This
  automatically masks: capacity rates, stock, buy/sell offer books, build
  hosts, buyers/understocked/fill, top-buyer/seller charts, sector demand.
- `frames.global_trades`: drop events whose owner station is not known
  (traded volume / Cr/h become "trades at stations you know of" —
  approximation, noted in the info panel).
- `viz/sunbursts.py` and `viz/map.py`: already gated via `spoilers_hide`,
  which `player_view` implies. Verify the universe sunbursts also drop
  unknown ships (`knownto` filter exists) — audit, don't assume.
- Trade/Trade History/Fleet/Tables: player-owned data, inherently known —
  explicitly no change (document this in the plan-of-record comment).

### 5. Live/stale marking (Market tab)

- Offer books (`d.bo`/`d.so` triples) gain a 4th element: `live` (0/1).
- "Sell here / Buy here" charts: stale offers render dimmed (reduced
  opacity) with a `(stale)` suffix in the bar text; tooltip explains.
- Summary-table metrics that rank opportunities (`Best sell`, `Demand (Cr)`)
  compute from **live offers only**; a secondary "incl. stale" value is NOT
  shown (keep it simple; revisit if it feels too aggressive).
- Fill %/Understocked/Buyers: computed over known stations, with stale
  stations included (their *offer amounts* are as unknowable as their
  prices, but excluding them entirely would make the metrics jumpy —
  document this compromise in the info panel).
- Dashboard header (or Market note) shows the visibility counts, e.g.
  "player view: 1,342 stations known (890 live / 452 stale), 394 hidden".

### 6. Omniscient-column treatment (minimal version)

When `player_view` is on:

- Info panel gains a "Player view" section listing the approximations:
  capacity assumes full station knowledge (scan state is not saved), stock
  includes cargo the player cannot see, traded volume covers known stations
  only.
- Add a `.warn`-styled banner line above the table: "Player view:
  reveal-masked; capacity/stock columns still assume scanned stations".
- No column removal in this phase (deferred decision).

### 7. Tests & verification

- Unit: coverage model on synthetic frames (station in covered sector →
  live; known outside coverage → stale; unknown → absent).
- Fixture parser test for satellites + licences (step 2).
- Real-save checks: visibility counts are plausible (343 satellites should
  make most Terran/Pioneer space live for this save); Market row deltas vs
  omniscient mode; screenshot pass of dimmed stale offers.
- Idempotence: caches are unaffected (mask is applied at build time, never
  written into caches — assert cache files byte-identical between a masked
  and unmasked run).

### 8. Docs

- README: one paragraph + flag mention.
- CLAUDE.md: visibility-model semantics bullet (knownto-only persistence,
  coverage approximation, subscription licence caveat).
- Market info panel: as in steps 5/6.

## Phase 2 sketch (not in this plan's scope)

Radius-accurate coverage: collect satellite/station positions (already in
the save as sector-relative offsets), radar ranges from game data (satellite
vs advanced satellite differ), and classify stations by distance instead of
sector membership. Strictly better fidelity; meaningful extra parsing and a
range table to maintain. Only worth it if sector-level classification proves
too coarse in practice.

## Risks / open questions

- Trade-subscription licence type string unverified (step 2 note).
- Sector-level coverage overstates vision in huge sectors (a satellite at
  one gate "covers" the whole sector) — acceptable for phase 1, motivates
  phase 2.
- Masking `global_trades` by known owner changes Traded/h and Cr/h meaning;
  the delivered-volume production estimate for minables inherits this and
  will read lower than omniscient mode. This is correct for the mode's
  purpose but must be labelled to avoid "why did production drop" confusion.
- `known=` (without `knownto`) appears on gates/sectors/clusters with
  slightly different semantics than `knownto="player"` — use `knownto`
  exclusively; do not mix.
