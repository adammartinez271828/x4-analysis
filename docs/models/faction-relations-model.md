# How X4 faction relations / diplomacy work (current understanding)

Reference for the Diplomacy feature. Assembled 2026-07-22 from a full sweep of
one 600h save's `<factions>` block and the game files
(`libraries/factions.xml`); **composition revised 2026-07-31** after three
in-game rep readings killed the additive law (E-083 → E-145). Confidence tags:
**[OBS]** observed in save data, **[DOC]** stated in a game-file comment,
**[INF]** inferred.

## The model in one paragraph

All faction relations live in the savegame under
`/savegame/universe/factions`, one `<faction id="…">` per faction. Each stores
its **own view** of the others as a **base** `<relation faction="Y"
relation="N"/>` (N ∈ −1..+1) and, where one is live, a **booster** `<booster
faction="Y" relation="N" time="T"/>`. The booster is **not an offset**: it *is*
the current standing, persisted at its decayed value, and it **replaces** the
base for as long as it exists. **Effective standing = clamp(booster if the pair
has one, else base, −1, +1)** [OBS, E-145] — which equals the standing the game
reported at save time, so there is no decay curve to reproduce. A pair neither
faction lists defaults to **0.0 (neutral)**, and a real save has already
materialized all its non-zero relations, so the full picture is recoverable
**from the save alone**.

Observed saves carry at most one booster per direction per pair; the code sums
them if several ever appear (arbitrary but stable — see E-146).

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

Because a booster **replaces** the base, this has a consequence the additive
reading got backwards: for a faction that *does* carry a negative base towards
the player (the pirate and hostile-split factions, and story grants), the base
is the standing only **until** something creates a booster — after which the
booster alone is what the rep bar shows. Save 8E0C…/save_010 vs the game a few
hours later [OBS, E-145]:

| faction | base | booster | model rank | read in game |
|---|---:|---:|---:|---|
| yaki | −0.32 | +0.2 @ t=69408.744 | +23 | **+22, Ally** |
| split (ZYA) | −0.032 | −0.01004 @ t=78206.445 | −10 | **−6, Neutral** (decayed/traded since the save) |
| loanshark (VIG) | −0.0032 | +0.0026712 @ t=81940.398 | +4.17 | **+4** |
| scaleplate (SCA) | −0.0032 | — | −5 | negative, cannot be raised |
| buccaneers (BUC) | −0.032 | — | −15 | negative, cannot be raised |
| fallensplit (FAF) | −0.0032 | — | −5 | negative, cannot be raised |
| alliance (ALI) | +1 | — | +30 | **+30, ally** |

The yaki booster is exactly `0.2` and unchanged 3.7 game-hours later — a
permanent story grant, not a decaying one; `0.2` sits exactly on the rank-23
threshold (`10^2.3/1000 = 0.19953`), so a hair either way reads 22. The
booster-less rows reading their base are what rules out the mirror-image error
("only boosters count, base ignored").

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

## Rejected — do not re-test without new evidence

| candidate | how it died |
|---|---|
| **effective = clamp(base + Σ boosters, −1, +1)** — boosters are additive offsets on the base (E-083) | the three B9 readings of 2026-07-31. yaki: additive −0.12 ⇒ rank **−21**, read **+22** (43 rank points and a sign out). split: additive −0.042 ⇒ **−16**, read **−6**. loanshark: additive −0.00053 ⇒ **−0.8**, read **+4**. All three land on the transform once the booster replaces the base |
| only boosters count; the base is cosmetic | SCA/BUC/FAF read their negative base standings in game with no booster stored, and ALI reads +30 from base `1` |
| the rank transform is wrong (the other half of E-083) | not refuted — it is exact on loanshark (+4.17 ⇒ +4) and on yaki up to the rank-23 boundary. Only the composition moved |

Still **open**, not rejected (E-146): `max(base, booster)` fits every reading as
well as *replace* does, because every observed booster happens to be on the
better side of its base. The code implements *replace*; a pair whose booster is
worse than a non-zero base would separate them, and none exists in the
available saves. The booster's drift target (base vs 0) is unobserved for the
same reason.

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
  (faction, other, base, booster, **effective** = booster-if-present-else-base,
  clamped), plus `faction_discounts` / `faction_meta` / `faction_licences`.
  This is the ONE place the composition is computed; `db/schema.py`'s
  `v_faction_standing` mirrors it in SQL and the views are compared by
  `tests/test_views_parity.py`.
- `viz/diplomacy.py` + `diplomacy_page.js` — **Empire ▸ Standings** (player
  standings table, diverging bars, rank, discounts, licences, treasury) and
  **Universe ▸ Relations** (directional faction×faction heatmap). No spoiler
  handling: relations are global state, not exploration-gated.
