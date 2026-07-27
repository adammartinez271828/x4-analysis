# Plan: Player-View Mode (reveal masking + live/stale coverage flag)

Status: **planned, not implemented**. This document is the design; nothing in
it has been built yet.

**Superseded assumption (2026-07-27):** the plan's "faction trade
subscriptions via the player faction's `<licences>` block" is wrong.
Subscriptions are *per object* in `<player><memory><subscriptions>` with an
absolute expiry (5 game-hours), player-only — NPC factions have no
subscription state at all — and they are already parsed into
`player_subscription` (v19), alongside `player_scan` (v20). Wherever this
document says "subscribed factions / subscription licence", read: join
`player_subscription` per station and filter `expires_at > game_time`. See
savegame-structure.md § The player component.

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

- `knownto="player"` / `known` attributes carry the reveal state. In the
  reference save: 1,342/1,736 stations, 125/152 sectors, 8,090/14,420 NPC
  ships revealed. **Revised 2026-07-27:** they are *not* the only persisted
  player knowledge — `<player><memory>` also holds per-object trade
  subscriptions with absolute expiry and per-object module scan levels
  (`player_subscription` v19, `player_scan` v20).
- **No** per-offer timestamps or price snapshots exist anywhere in the save
  (verified by attribute sweep), so no historical *values* are
  recoverable — but subscription expiry does give real per-station
  freshness, which is better than the sector-coverage approximation below.
- Player intel sources are reconstructible: 343 deployed player satellites
  (`class="satellite" owner="player"`), player ships/stations (positions and
  sector ancestry stored), and the subscription/scan tables above.

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

**Verification task — CLOSED (2026-07-27):** there is no trade-subscription
licence type. Subscriptions live per object in
`<player><memory><subscriptions>` and are already parsed
(`player_subscription`), so this step's licence collection is unnecessary;
the `<licences>` sweep only remains useful for other licence kinds.

### 3. frames: visibility classification

New dataframe `Frames.station_visibility` (`id`, `known: bool`,
`live: bool`), built as:

- `known` = station `knownto == "player"`.
- `covered_sectors` = set of `sector.macro` containing ANY of: player ships,
  player stations (from `playerowned`), or player satellites.
- `subscribed` = the station's id has an unexpired row in
  `player_subscription` (`expires_at IS NULL OR expires_at > game_time`) —
  revised 2026-07-27, replacing the falsified faction-licence set.
- `live` = `known and (sector in covered_sectors or subscribed)`.

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
- CLAUDE.md: visibility-model semantics bullet (reveal via `knownto`,
  freshness via `player_subscription`, coverage approximation caveat).
- Market info panel: as in steps 5/6.

## Phase 2 sketch (not in this plan's scope)

Radius-accurate coverage: collect satellite/station positions (already in
the save as sector-relative offsets), radar ranges from game data (satellite
vs advanced satellite differ), and classify stations by distance instead of
sector membership. Strictly better fidelity; meaningful extra parsing and a
range table to maintain. Only worth it if sector-level classification proves
too coarse in practice.

## Risks / open questions

- ~~Trade-subscription licence type string unverified~~ — closed
  2026-07-27: no such licence exists; use `player_subscription` (step 2/3).
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
