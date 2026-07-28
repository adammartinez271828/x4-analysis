# Handoff: station storage allocation and market pricing

Written 2026-07-28 at the end of a long session. Everything below is either
committed or measurable by running the commands given. Read
[open-items-2026-07-28.md](../reports/open-items-2026-07-28.md) alongside this
— that is the ranked list of what is left; this is the context needed to work
on it.

## The one-paragraph version

An X4 station allocates each ware a share of its transport pool so every
production ware holds an equal number of *hours* of throughput, with rations
taking a fixed 4 h buffer off the top. Throughput comes from the recipe scaled
by the module's own `<production><efficiency product=>` from the savegame.
Market prices are the ware's **average** times one plus an additive modifier
expressed as a percentage of that average, and the modifier is a **cosine in
storage fill**. The allocation model is done (40/41 in-game readings within
1 %); ration pricing is done (MAD 0.017); production-input and output pricing
are not.

## Confirmed model

### Allocation

Per station, per transport pool (container / liquid / solid):

```
T   = (pool_capacity - Σ ration_volume) / Σ (throughput × ware.volume)
max = throughput × T                    (rations: consumption × 4 h)
```

- `throughput(output) = floor(recipe.amount × efficiency) / recipe.time × 3600`
  per module, summed. The engine truncates **per cycle**, not per hour.
- `throughput(input)` is the recipe rate at **base** — inputs are not scaled by
  efficiency. Scaling them breaks IFO-957 by +23 % and TPF-229 by +16 %.
- `efficiency` is the module's own `<production><efficiency product=>`. It is
  the *complete* multiplier: workforce bonus × sector sunlight × mod effects,
  all in one number. Do not reconstruct it from `recipes.work_effect` and
  `sectors.sunlight` — that cannot work on a modded save.
- A module with **no `<production>` block** is idle and runs the bare recipe
  (multiplier 1.0), not the reconstructed work effect. 939 (station, macro)
  pairs are in this state.
- A **multi-queue** module caught between products reports an efficiency with
  no `<queue ware>`. Key on `(station, macro)` as well as
  `(station, macro, ware)`, and rescale: the reported figure belongs to one of
  its recipes, so recover the workforce ratio from it against the module's
  smallest work effect and re-apply each recipe's own. The alternation *split*
  does not matter — it scales every rate on the module equally and cancels out
  of the equal-hours division.
- Dual-role wares take `max(production, consumption)`. Processing modules
  (scrap works) are outside the model entirely: their recipe is quoted per unit
  of scrap, not per timed cycle, so they have no hourly rate to contribute.
  Non-`economy`-tagged feedstock (raw scrap) is never stocked.

### Price

```
price = ware.price_avg × (1 + Σ modifiers)
```

Modifiers are **additive percentages of avg**, exactly as the station trade
panel displays them ("High Supply −38.9 %", "Prized Investor −9.1 %",
"Total −48.0 %"). The savegame's offer price carries the **supply/demand term
alone**; the reputation discount is applied at display time.

The reference band *is* that modifier's range: `min = avg × (1 − spread)`,
`max = avg × (1 + spread)`, symmetric for 1,851 of 1,891 wares. **40 are
asymmetric** — ore (−14 %/+16 %), food rations, graphene, engine parts, ice —
so always work on the normalised coordinate

```
s = (price/avg − 1) / spread     # spread = the half-width on the relevant side
                                 # +1 = band max, −1 = band min
```

and never on `(price − min)/(max − min)`, which kinks at avg for those.

The buy-side curve:

```
s = cos(π × fill / 1.095)
```

Independently confirmed on rations at `(1 + cos(π u / 1.085))/2`, MAD 0.0016
over 2,369 offers — same law, same span, disjoint populations.

Other price books, all excluded from the main sequence: `shady` (≈1.055 × band
max, fill-independent), `supplies` (a fixed per-ware multiple of avg, 10
constants), `lockavgprice` (avg / avg − 1), build storages (band max), yards
(same family, `k ≈ 2.6`), player stations (manual).

### Two facts about offers

- `allocation = stock + inbound + open buy amount` — but only as a **LOWER
  BOUND**. A station bids for what it can use, so one whose consumers are
  unbuilt (MAL-475: 157,810 derived against a true 1,498,962) or which simply
  is not buying reads far below its allocation. Never score a model as wrong
  for exceeding it.
- **A full station withdraws its buy offer entirely** rather than pricing it at
  zero. Offer coverage is 99.7 % below 90 % fill, 38 % at 100–110 %, 5 % above.
  So the buy sample is censored at the top of the fill range, and a price
  history reading 0 means *no offer*.

## How to work on this

### The test harness — use it for every change

```bash
uv run python tests/readings.py       # scoreboard, ~1 s, no savegame needed
uv run pytest -q                      # 234 tests
```

`tests/data/station_readings.json` holds, per station, everything
`station_storage()` needs plus the values the player read **in game**.
`tests/readings.py` replays them; `tests/test_readings.py` locks the exact
stations and guards the baseline (currently 40/41). A candidate model is scored
against every reading at once. Add new player readings to the fixture rather
than reasoning about one station at a time.

### Regenerating the data

```bash
uv run x4-analyzer --save <file> --no-browser     # parse → sqlite → dashboard
```

The DB is `~/.local/share/x4analyzer/x4_<guid>.sqlite`; `current_save` names
the active snapshot. `station_storage` holds the model output. Scratch scripts
belong in a temp dir, never in the repo.

### Mod handling — do not edit the CSVs

Reference CSVs in `src/x4analyzer/data/` stay **stock** (base + DLC). Mods that
rewrite game data are detected per save and patched into that run's `RefData`
in memory — `gamedata/modpatch.py`, called from `analyze.py`. Two detection
routes: extension id from the save's `<patches>` list, or a **fingerprint** for
`save="false"` mods that leave no trace (the current one is efficiency
exceeding the stock `1 + work_effect` ceiling). This playthrough runs Faction
Fix Pack; `faction_fix_pack_econ_bal` rewrites `advancedelectronics` and
`weaponcomponents`, worth 27/41 → 37/41 on the fixture.

## Methodological lessons — these cost real time today

1. **Weight the ends when fitting a shape.** Per-offer MAE is dominated by the
   crowded middle of the curve, where a straight line and a cosine are
   indistinguishable; it reported a clamped line as a good fit. Scoring **bin
   medians with equal weight per bin** put the cosine ahead by 10×. Fit shapes
   on binned data, not on raw offers.
2. **Do not fit a rule to one station.** A starving-workforce gate reproduced
   EIJ-609's six wares exactly and was worse than no gate save-wide under every
   definition tried (93.8 % → 83.6–91.6 %). Always score a candidate against
   the whole population before shipping it.
3. **Check the ground truth is ground truth.** The offer-derived allocation was
   asserted as an equality, used to score three commits, and then demoted to a
   lower bound by a single counter-example. In-game readings are authoritative;
   everything else is a proxy with a failure mode.
4. **Read the mod files rather than inferring.** A "modded recipe" was inferred
   from arithmetic that fit two numbers; the real recipe was in a *sibling*
   mod's packed XML and the arithmetic had been lucky. `GameFiles` from
   `gamedata/catalog.py` reads `.cat`/`.dat` directly.
5. The in-game **Logical Station Overview** and trade panel state most of this
   outright — production rate, efficiency, allocation, and the price
   decomposition by named modifier. Ask for a screenshot before deriving.

## Where things live

| what | where |
|---|---|
| allocation model | `src/x4analyzer/analysis/storage.py` |
| mod detection/patching | `src/x4analyzer/gamedata/modpatch.py` |
| production efficiency parse | `src/x4analyzer/save/parser.py` (`module_production`) |
| in-game readings fixture | `tests/data/station_readings.json` |
| scoreboard harness | `tests/readings.py`, `tests/test_readings.py` |
| the reverse-engineered rules | `docs/reference/save-semantics.md` |
| what is still open | `docs/reports/open-items-2026-07-28.md` |
| the spread taxonomy | `docs/reports/fill-price-spread-2026-07-28.md` |
| this session's plan | `docs/plans/storage-production-model-2026-07-28.md` |

Schema is v27. Conventions (dark widgets, spoiler handling, defensive joins,
commit locally and never push) are in `CLAUDE.md`.
