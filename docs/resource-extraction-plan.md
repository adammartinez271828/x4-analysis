# Measured "maximum steady extraction rate" from save-history respawns

Plan on branch `resource-edge-gauge` (2026-07-21), extending the resource
edge-gauge work. Goal: replace the static, class-derived replenishment
gauge with an **empirically measured maximum steady extraction rate** per
sector-ware — the "you can mine this many ore/hour here forever" number —
derived by tracking resource-pool respawn events across the save history.

## Why (what the manual analysis established)

The static class estimate (`Σ area cap / respawndelay × gatherspeed`,
shipped as the right-edge gauge) is unreliable as a rate. Measured against
four ore fields plus the two Sol systems:

| field · ware | class formula | reality (measured) |
|---|---|---|
| Emperor's Pride VI ore | 45k/h | ~45k/h (matched) |
| Matrix #9 ore | 228k/h | ~37k/h (**6× over**) |
| Matrix #598 ore | 200k/h | ~28k/h (~7× over) |
| Saturn 2 silicon | 61k/h | **≥233k/h (4× under)** |

It is wrong in **both** directions because it ignores the one governing
variable: **depletion depth.** X4's regen is clearly `regen ∝ (cap −
current)` — a deeply depleted area (Saturn 2 silicon at 29% full) refills
fast and *overshoots* the class rate; a near-full area (Matrix #9's 60
lightly-tapped areas) barely regenerates and falls far short. The static
number is neither the realized rate nor a stable ceiling.

Established facts the plan relies on:

1. **Regen is real and measurable from saves.** Verified non-artefactually:
   Saturn 2's +969,919 silicon jump landed in the **same 6 areas** (identical
   classes/count) — a genuine refill, not scan discovery.
2. **Regen is bursty/discrete** — big respawn chunks gated by `respawndelay`,
   not a smooth trickle (Saturn 2 silicon +970k in 0.22 game-h; Emperor's
   Pride ore +15k blips).
3. **In a heavily-mined (depleted) sector, observed regen ≈ the maximum
   steady extraction rate** — the field is held below cap, so it regenerates
   near its ceiling, and what it regenerates is exactly what you can pull
   sustainably.
4. **Area runtime ids remap every load** — individual asteroid fields cannot
   be tracked across saves. Aggregate per **(sector, ware)** only.
5. **Frozen sectors exist** — unsimulated/unvisited sectors don't regen at
   all (Unknown System, and scrap everywhere); they must read as "no data,"
   not "zero rate."
6. **Only *distinct game-times* carry information** — this playthrough's DB
   has 46 runs but 2 distinct saves; the 13 save files on disk span
   game-hours 0.16 → 18.39. Density = how often distinct saves get analyzed.

## Blocker: the DB keeps only the newest snapshot

`store.py` deletes every world table (including `resource`) before each
snapshot write ("phase-5 retention" is unimplemented). There is no
cross-snapshot resource history in the DB today — the manual analysis
scanned the raw save files directly. The measurement needs history that
survives across runs, keyed by game-time. This is the aggregate-history
table proposed as P6 in [live-db-features.md](live-db-features.md), scoped
to resources.

## Architecture

Five pieces, mapped to the pipeline:

### 1. Retention — `resource_history` (new event-style table)

A tiny per-snapshot aggregate that **survives schema resets and merges
across runs** (add to `schema.EVENT_TABLES`). One row per
(game-time, sector, ware):

```
resource_history(
  game_time    REAL NOT NULL,   -- snapshot identity (see keying)
  save_date    TEXT,            -- tiebreak / display
  sector_macro TEXT NOT NULL,
  ware         TEXT NOT NULL,
  total_yield  REAL NOT NULL,   -- Σ area current pool
  total_cap    REAL NOT NULL,   -- Σ area capacity (fill = yield/cap)
  n_areas      INTEGER NOT NULL,-- discovery guard (see derivation)
  PRIMARY KEY (game_time, sector_macro, ware)
)
```

~455 sector-ware rows × distinct snapshots ≈ kilobytes; negligible next to
the 60 MB stock_event table. `total_cap`/`n_areas` come from the level
tokens already parsed (schema v6). Per-class detail is **not** stored —
aggregate totals are sufficient and keep the table small.

**Keying / idempotency.** `game_time` is the snapshot identity: re-analyzing
the same save (same game_time) `INSERT OR REPLACE`s the same rows (adds
nothing); a distinct game_time accumulates a new point. This mirrors the
"2 distinct saves regardless of 46 reruns" reality — reruns don't inflate
the history. (Edge case: two real saves at an identical game_time — vanishingly
rare; `save_date` breaks the tie if ever needed.)

### 2. Store — upsert on snapshot write

In `write_snapshot`, after the `resource` insert, aggregate the same rows
by (sector, ware) and upsert into `resource_history`. Because it keys on
game_time and the table is in `EVENT_TABLES`, it is idempotent and
history-preserving with zero extra parse cost.

### 3. Backfill — populate history from saves already on disk

The table starts empty; going forward it fills one point per analyzed save.
To get signal *now* from the 13 existing saves, a lightweight batch command:

```
x4-analyzer extract-history [saves...]   # default: all saves in the save dir
```

Runs the existing single-pass parser over each save and upserts **only**
`resource_history` (skips the full snapshot rebuild + dashboard). ~30–120 s
per save; one-time. Reuses `parser.parse_savegame` — no new parsing logic.

### 4. Derivation — `analysis/extraction.py`

Per (sector, ware), read `resource_history` ordered by game_time and
compute the measured rate:

- **Gross respawn** = Σ of *positive* `total_yield` deltas between
  consecutive snapshots, over elapsed game-time → observed regen (units/h).
- **Discovery guard**: if `n_areas` increases across an interval, that
  delta mixes real regen with newly-visible areas — **discount or drop**
  it (the verified discriminator). Only intervals with stable `n_areas`
  count as clean regen.
- **Lower-bound semantics**: mining masks regen (net delta < gross regen),
  so the measured value is a **floor** on true sustainable extraction —
  except where the pool is stable or rising under heavy mining, where it
  approaches the true maximum. Carry a flag for which regime applies.
- **Confidence** from: number of distinct game-times, total elapsed
  game-time spanned, and number of clean respawn events observed. No
  respawn events → **unobserved** (fall back / show nothing), not "0/h."

Returns per (sector, ware): `measured_rate`, `is_floor`, `n_events`,
`span_h`, `confidence`, plus current `fill` (for context).

### 5. Display — map gauge + detail panel

- Right-edge gauge switches to the **measured** rate when confidence
  clears a threshold; percentile ranking stays the visual encoding, now
  over a trustworthy quantity.
- Detail panel shows a real units/hour figure ("Ore: max steady
  extraction ≈ 45k/h, measured over N snapshots / M game-h"), with a
  `≥` prefix when it's a floor, and "insufficient history" when unobserved.
- Relabel from "replenish" to **"max steady extraction"** — the
  actionable, correctly-named quantity.
- Scrap wares stay excluded (no regen; established earlier).
- Static class estimate: either retired, or kept only as a greyed
  "capacity ceiling" fallback where no measurement exists (decision below).

## Phasing

1. **Retention + backfill** (foundational): `resource_history` table,
   store upsert, `extract-history` command. Ship behind nothing — it only
   adds a table and a command; the dashboard is unchanged.
2. **Derivation**: `analysis/extraction.py` + tests. Validate it
   reproduces the manual numbers (Emperor's Pride ~45k/h, Saturn 2 silicon
   ≥233k/h) from the 13 saves.
3. **Display**: gauge + detail-panel wiring; relabel.
4. **Polish**: confidence thresholds, floor/`≥` presentation, fallback
   behaviour.

Each phase is independently commit-able; 1 is useful on its own (it's the
history other resource features would reuse).

## Testing

- **Unit** (`analysis/extraction.py`): synthetic 3-snapshot history →
  known positive deltas → expected rate; area-count jump → discovery delta
  excluded; single snapshot → unobserved; monotone decline → floor flag;
  scrap → excluded.
- **Store**: upsert idempotency (same game_time twice → one row set);
  distinct game_times accumulate; survives a schema-version reset (E-table).
- **Regression**: freeze the manual findings as expected ranges —
  Emperor's Pride VI ore in [35k, 55k]/h; Saturn 2 silicon ≥ 200k/h;
  Unknown System / any scrap → unobserved.

## Decisions needed

1. **History source**: backfill from the 13 on-disk saves now (one-time
   scan), or accumulate going forward only? (Backfill gives immediate
   signal; recommended.)
2. **Fallback when unobserved**: show nothing, show the old class estimate
   greyed as a rough "capacity ceiling," or show "insufficient history"?
3. **Floor honesty**: prefix measured-but-mining-masked values with `≥`,
   or present a single best estimate?
4. **Confidence threshold** for promoting the gauge from class-estimate to
   measured — how many events / how much game-h span is "enough"?

## Non-goals / caveats

- **Not** tracking individual areas (ids remap) — aggregate per sector-ware.
- **Not** modelling the `(cap − current)` regen physics analytically —
  pure measurement sidesteps the unknown rate constant.
- **Not** full world-state retention (122 MB × N) — only the ~KB aggregate.
- Signal density is bounded by **distinct analyzed saves**; casual players
  with few saves get few/low-confidence measurements. This is the same
  argument for the analyzer parse→DB / watch-mode split (P7 in
  live-db-features.md): a denser save stream directly improves this feature.
- Measured rate is a **floor** in actively-mined-but-declining sectors; only
  stable/rising-under-load sectors reveal the true maximum. The UI must not
  present a floor as the exact ceiling.
