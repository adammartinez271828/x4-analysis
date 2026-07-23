# How X4 faction relations / diplomacy work (current understanding)

Reference for the Diplomacy feature. Assembled 2026-07-22 from a full sweep of
one 600h save's `<factions>` block and the game files
(`libraries/factions.xml`). Confidence tags: **[OBS]** observed in save data,
**[DOC]** stated in a game-file comment, **[INF]** inferred.

## The model in one paragraph

All faction relations live in the savegame under
`/savegame/universe/factions`, one `<faction id="…">` per faction. Each stores
its **own view** of the others as a **base** `<relation faction="Y"
relation="N"/>` (N ∈ −1..+1) plus additive **boosters** `<booster faction="Y"
relation="N" time="T"/>`. **Effective standing = clamp(base + Σ boosters,
−1, +1)** — and because the engine persists each booster at its *current
decayed* value, this equals the standing the game reported at save time (no
decay curve to reproduce). A pair neither faction lists defaults to **0.0
(neutral)**, and a real save has already materialized all its non-zero
relations, so the full picture is recoverable **from the save alone**.

## Storage [OBS]

Per `<faction>`:
- `<relations>` → `<relation faction= relation=>` (base) and `<booster faction=
  relation= time=>` (temporary standing modifier).
- `<discounts>` → `<booster faction= amount= time=>` — a *trade discount*
  fraction this faction grants the target (same tag as a relation booster,
  distinguished by its `<discounts>` parent and `amount=` vs `relation=`).
- `<account id= amount=>` — the faction's treasury.
- `<licences>` → `<licence type= factions="a b c"/>` — rep-gated unlocks
  (which factions a licence type is granted for).
- Also `<diplomacy>` (war-eligibility excludes), `<moods>` (ToA avarice) — not
  currently parsed.

## Directional, not symmetric [OBS]

Relations are stored per-faction and are *mostly* reciprocal but **not
guaranteed**: in the test save `argon→scaleplate = −0.32` while
`antigone→scaleplate = −0.1`. The relations matrix is therefore directional —
row = the faction whose view it is, column = the target. Read (and display)
both directions.

## Player standing is booster-driven [OBS]

The player has no base `<relation>` with the major trading factions — you start
neutral (0) and rep accrues entirely via boosters (missions, trade). Boosters
mirror exactly across the pair (argon↔player were both `0.240896 @ t=70164.839`).
Permanent hostiles (Xenon, Kha'ak = −1) and scripted allies (Alliance = +1) are
base relations.

## The −30..+30 rank value [DOC]

The in-game rep bar maps the −1..+1 relation to a −30..+30 UI value by a fixed
formula (documented in the `libraries/factions.xml` header comment; there is no
machine-readable table, so these are code constants in `viz/diplomacy.py`):

```
uiv = sign(r) · 10 · log10(|r| · 1000)        for |r| > 0.0032
uiv = r / 0.00064                             for |r| ≤ 0.0032  (linear band)
```
Anchors: `1.0=30, 0.5=27, 0.32=25, 0.1=20, 0.032=15, 0.01=10, 0.0032=5`
(negatives mirror). Standing-band labels used by the view — Ally ≥0.5,
Friend ≥0.1, Friendly ≥0.01, Neutral, Enemy, Hostile ≤−0.32, War =−1 — are a
single-label reduction of the game's overlapping behaviour bands
(self/ally/member/friend/neutral/enemy/killmilitary/kill/nemesis).

## What we deliberately don't do

- **Booster decay projection** — the decay curve (`delay`/`decay` params, e.g.
  `540s` then rate `0.02`) is engine-internal. We show the standing *as of the
  save*, which is exact; we do not predict future decay. [INF]
- **Game-file default relations** — unneeded: unlisted pair = 0.0 and the save
  is complete, so no `extract-gamedata` change and no reference CSV. [OBS]

## Where it lives in the code

- `save/parser.py` — `faction_id_stack` generalizes the old player-only
  `in_faction_player` handler; collects `faction_relations` / `faction_boosters`
  / `faction_discounts` / `faction_accounts` / `faction_licences`.
- `db/schema.py` + `db/store.py` — `faction_relation` (kind base|booster|
  discount), `faction_meta` (treasury), `faction_licence` world tables.
- `analysis/frames.py` — pivots kind → `frames.faction_relations`
  (faction, other, base, booster, **effective**), plus `faction_discounts` /
  `faction_meta` / `faction_licences`.
- `viz/diplomacy.py` + `diplomacy_page.js` — **Empire ▸ Standings** (player
  standings table, diverging bars, rank, discounts, licences, treasury) and
  **Universe ▸ Relations** (directional faction×faction heatmap). No spoiler
  handling: relations are global state, not exploration-gated.
