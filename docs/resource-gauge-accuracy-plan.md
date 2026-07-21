# Accurate resource edge gauges + per-field status dropdown

Plan on branch `resource-edge-gauge` (2026-07-21). Rework the sector-map
resource overlay and the sector detail panel to reflect the **confirmed**
respawn model (see `resource-depletion-model.md`), replacing two quantities
that the investigation showed are wrong:

- the **left** edge gauge ranks summed *stored* `yield` — which **understates**
  mineability, because an eligible-empty ("overdue") area reads `0` in the save
  yet is actually **full and mineable** (the encyclopedia shows it at capacity);
- the **right** edge gauge ranks an ordinal index `Σ cap/respawndelay ×
  gatherspeed` — the gatherspeed factor (0.2–5.0×) is an **extraction**-speed
  token, not a respawn term, so it distorts a "replenishment rate" by up to 25×.

The two gauges become a clean two-axis read of a sector, exactly as intended:

```
 LEFT edge  = mineable NOW        (live yields + full "overdue" areas)
 RIGHT edge = max replenishment   (Σ capacity / respawndelay, per hour)

 short-left / tall-right  = empty but replenishing fast
 tall-left / short-right  = full but slow to come back
```

Both stay **percentile-ranked among non-zero sectors**, so a half-full gauge =
the **median** sector (P50), unchanged rendering (`edgeGauge`/`pctile`).

## The model, as it maps to numbers

Per resource **area** in a sector (`<area yieldid yield starttime>`):

- **capacity** = the level's max yield, `regionyields.csv[(level, ware)].yield`
  (e.g. `verylow ore` → 5000). This is what an area holds when fully respawned.
- **respawndelay** = `regionyields.csv[(level, ware)].respawndelay`, in **minutes**
  (20–480 in current data). `-1` = never respawns (guard even though none appear
  in this dataset).
- **mineable now** (matches the encyclopedia):
  - `yield > 0` → `yield` (live pool)
  - `yield == 0` and eligible (`starttime == 0` or `starttime ≤ game_time`) and
    `respawndelay != -1` → **`capacity`** (respawned & full; the save just reads 0)
  - `yield == 0` and not-yet-eligible (`starttime > game_time`) → `0` (respawning)
  - `yield == 0` and `respawndelay == -1` → `0` (never respawns)
- **max replenishment rate** = `capacity / respawndelay` per area, summed over the
  sector's areas of that ware, expressed **per hour** (`× 60 / respawndelay_min`).
  Never-respawn areas contribute 0. **No gatherspeed factor.** This is the
  *theoretical maximum* — the ceiling if every area were kept fully depleted, so
  each refills its capacity once per cooldown. (It is a ceiling, not a realized
  rate; `resource-extraction-plan.md` covers measuring the realized rate from
  save history — a separate, larger feature.)

Sector-ware aggregates the gauges consume:

- `mineable_now = Σ area mineable-now`  → **left** gauge + panel headline number
- `replenish_rate = Σ area (capacity / respawndelay) × 60`  → **right** gauge
- plus a per-area **status breakdown** for the detail dropdown (below)

## Changes by pipeline stage

### 1. Parser — capture per-area `starttime`  (`save/parser.py`)

The `<area>` handler already parses `yieldid` into `(ware, level, speed)` and
reads `yield`; add `starttime`. The resources tuple becomes:

```
(sector_macro, ware, yield, level, speed, starttime)   # was 5-tuple
```

`starttime` is game-time seconds (same clock as `game_time`); absent/`0` on
live and never-depleted areas. One extra `elem.get("starttime")`; no new pass.

### 2. Schema + store — persist it  (`db/schema.py`, `db/store.py`)

- `resource` table gains `starttime REAL`. Bump `SCHEMA_VERSION` **6 → 7**
  (world tables are replaced wholesale per snapshot, so the bump just requires
  re-analyzing the current save — no history to migrate; the DB backup at
  `backup-2026-07-21-pre-replenish/` already covers the earlier v6 change).
- `store.write_snapshot` writes `starttime` alongside `level`/`speed`.

Capacity/respawndelay are **not** stored — they're reference data, resolved at
frames time from `ref.region_yields` (already loaded). Keeps the row small and
avoids a second source of truth for capacity.

### 3. Frames — compute the two aggregates + breakdown  (`analysis/frames.py`)

Replace the current `_rate` block (which multiplies in gatherspeed and ranks
raw stored yield). Reading the `resource` rows for the current save, per row
resolve `(cap, delay) = ref.region_yields.get((level, ware), (0, 0))` and derive:

- `mineable = yield if yield>0 else (cap if _eligible(starttime, game_time, delay) else 0)`
- `rate_per_h = (cap/delay*60) if delay>0 else 0`

where `_eligible = delay > 0 and (starttime == 0 or starttime <= game_time)`.

Then:

- pivot **`mineable`** → the existing per-ware `<ware>` columns (rename intent:
  these now carry mineable-now, not stored yield). `resource_cols` unchanged.
- pivot **`rate_per_h`** → `rep.<ware>` columns (same names the payload already
  reads; just an accurate quantity now).
- build a **per-(sector, ware) field list** for the panel: **one record per
  actual area** — `{status, cap, now, eta_min}`, where `now` is the area's
  mineable-now, `cap` its capacity, and `eta_min = (starttime - game_time)/60`
  for respawning areas (else null). Status ∈ `live | full | respawning | never
  | unknown`. Sort by status priority (live, full, respawning, never) then `cap`
  desc, for a stable readable order. Carry it on `frames` as a new attribute
  (e.g. `resource_areas`: `{macro: {ware: [records]}}`). Not grouped — the
  dropdown lists the real fields (~3300 areas total across the save; each is one
  small record, and the panel only ever renders one sector at a time).

Fallback: `(level, ware)` missing from `regionyields.csv` (e.g. a gas area with
no level token) → `cap`/`delay` = 0; such an eligible-empty area contributes 0
to mineable-now (can't materialize a number) and 0 to the rate, and its
breakdown row is labelled `unknown`. Rare; note it rather than crash.

### 4. Payload — emit breakdown, keep gauge arrays  (`viz/map.py`)

`_payload` already emits `resources[].yields[i]` (→ now mineable-now) and
`resources[].rep[i]` (→ now the accurate rate). Add the per-sector field list so
the detail panel can render each field without a second lookup — a top-level
`area_status`: `{ sector_macro: { ware: [ {status, cap, now, eta_min} ] } }`,
one record per area, filtered by spoilers like everything else. The `rep` array is
still omitted only when the reference CSVs predate the extract (right gauge
simply doesn't draw), same guard as today.

### 5. Map JS — gauges unchanged, panel dropdown  (`viz/map_page.js`)

- **Gauges**: `renormalize()` / `edgeGauge` / `pctile` need **no change** — they
  already rank `yields` (left) and `rep` (right) with P50 = half. Only the
  underlying numbers changed. Update the two explaining comments (left =
  "mineable now incl. respawned-full areas"; right = "max replenishment rate,
  Σ cap/respawndelay per hour").
- **Detail panel** (`openPanel`, the `resInner` block): replace the inline
  `replenish P<n>` span. Each resource row shows:
  - headline: ware name + **mineable-now** amount (the encyclopedia number),
    and a small `replenish P<n>` percentile kept as a one-glance rank (optional;
    the dropdown carries the detail).
  - a native **`<details>`** (collapsed by default — no `open` attr, so it needs
    zero JS state) whose `<summary>` is e.g. "6 fields", and whose body lists
    **one row per actual field** from `area_status[macro][ware]`, each showing
    `now / cap` and its state:
    - `live` → "4,020 / 5,000 · live"
    - `full` → "5,000 / 5,000 · full (respawned)" ← the **"overdue = full"** fix,
      shown at capacity not 0
    - `respawning` → "0 / 5,000 · respawns in ~12m"
    - `never` → "0 / 500 · depleted (no respawn)"
    - `unknown` → "· capacity unknown" (missing regionyields entry)

  Using `<details>` keeps it self-contained; the panel's own section collapse
  state (`panelSec`) is untouched.

## Testing

- **`test_saveparser.py`**: extend the fixture areas with a `starttime`; assert
  the new 6-tuple shape, including one eligible-empty area (`yield=0`,
  `starttime` in the past) and one respawning (`starttime` in the future).
- **`test_store.py`**: `starttime` round-trips; schema is v7.
- **frames unit** (new small test or extend existing): synthetic resource rows
  → assert `mineable_now` counts an eligible-empty area at capacity and a
  respawning area at 0; `replenish_rate` excludes gatherspeed and never-respawn
  areas; `area_status` emits one record per area with correct `status`/`now`/
  `cap`/`eta_min` and the documented sort order.
- **regression sanity** (manual, not asserted): on the current save a sector
  with known overdue areas (e.g. Pious Mists XI nividium from the experiment)
  now reports mineable-now > 0 where it previously read 0.

## Flagged decisions

1. **Gatherspeed out of the replenishment rate** — recommended and assumed here
   (respawn is governed by `respawndelay` alone; gatherspeed is extraction
   speed). This changes the ranking vs today. If the earlier Emperor's Pride
   ~45k/h class match relied on gatherspeed≈1.0 there, dropping it is harmless;
   validate against a high-gatherspeed sector before finalizing.
2. **Left gauge → mineable-now** — follows directly from "overdue = full" and
   keeps the gauge, panel headline, and encyclopedia in agreement. Assumed.
3. **Keep the small `replenish P<n>` on the panel headline** or rely solely on
   the dropdown + right gauge? Minor; kept for one-glance rank, easy to drop.

## Non-goals

- Not measuring the *realized* extraction rate from save history — that's
  `resource-extraction-plan.md` (needs cross-snapshot retention). This plan is
  single-save-accurate: mineable-now and the theoretical replenishment ceiling.
- Not tracking individual areas across saves (ids remap) — aggregates + a
  point-in-time per-area status snapshot only.
- Scrap wares keep whatever the reference data says (no special-casing here).
