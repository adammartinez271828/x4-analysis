# The `supplies` buy price is the band midpoint — cross-save verification (P1)

*2026-07-30. Plan item **P1** of
[../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md); settles
register entry **E-027**. Data: the 13-save archived corpus built in Phase 1
(game time 69,324 → 84,643 s, one playthrough, guid
`8E0C8E37-2192-49FD-BF4B-F535782A1C55`), parsed with the project's own
`save/parser.py`. Bands come from the packaged STOCK reference CSVs.*

## Claim

**CONFIRMED.** Every `supplies`-flagged buy offer prices at exactly the
midpoint between the ware's band average and its band maximum:

```
price(supplies) = (price_avg + price_max) / 2         i.e.  s = +0.5 exactly
```

Equivalently, in the closed form of
[../models/station-pricing-model.md](../models/station-pricing-model.md),
`u = 1.095 · acos(0.5)/π = 0.3650`, independent of stock, station, faction and
game time. E-027's "ten unexplained per-ware constants" are one line: the
constant is `(avg + max)/(2·avg) = 1 + spread/2`, and it varies only with the
ware's band spread.

*Falsified by:* **any** `supplies` offer, in any save, whose price is not its
band midpoint to the cent.

## Population and result

15,345 `supplies`-flagged offers, all on the **buy** side, over **9,594
distinct (station, save) pairs**, **19 factions** (incl. `player`, `xenon`,
`scavenger`) and all **13 saves**. Deviation from the midpoint: **0.000000
credits on every offer** — maximum absolute deviation is exactly zero for
every one of the ten wares.

| ware | n | offers' price | band min / avg / max | midpoint | price/avg | 1 + spread/2 |
|---|---:|---:|---|---:|---:|---:|
| smartchips | 6,295 | 63.00 | 46 / 57 / 69 | 63.00 | 1.1053 | 1.1053 |
| missilecomponents | 4,636 | 11.00 | 6 / 9 / 13 | 11.00 | 1.2222 | 1.2222 |
| dronecomponents | 2,888 | 1,028.00 | 685 / 914 / 1,142 | 1,028.00 | 1.1247 | 1.1247 |
| energycells | 648 | 19.00 | 10 / 16 / 22 | 19.00 | 1.1875 | 1.1875 |
| metallicmicrolattice | 392 | 53.50 | 42 / 50 / 57 | 53.50 | 1.0700 | 1.0700 |
| siliconcarbide | 286 | 1,520.50 | 1,202 / 1,414 / 1,627 | 1,520.50 | 1.0753 | 1.0753 |
| silicon | 92 | 140.00 | 111 / 130 / 150 | 140.00 | 1.0769 | 1.0769 |
| ore | 87 | 54.00 | 43 / 50 / 58 | 54.00 | 1.0800 | 1.0800 |
| hullparts | 17 | 240.50 | 146 / 209 / 272 | 240.50 | 1.1507 | 1.1507 |
| claytronics | 4 | 2,193.00 | 1,734 / 2,040 / 2,346 | 2,193.00 | 1.0750 | 1.0750 |

Every ware posts **one** price across all 13 saves (min = max per ware), so
there is nothing left for stock, epoch or owner to explain. Note the
half-credit prices — `metallicmicrolattice` 53.5, `siliconcarbide` 1,520.5,
`hullparts` 240.5 — which only a *midpoint* rule produces; they are the
strongest single piece of evidence against any "rounded per-ware constant"
reading of E-027.

The four claytronics offers (4 saves) confirm the tenth constant that the
triage could only fit retroactively from save 70: 2,193 = (2,040 + 2,346)/2,
ratio 1.0750.

Per-save counts (ordered by game time): 1,055 / 1,117 / 1,127 / 1,140 / 1,138 /
1,202 / 1,207 / 1,317 / 1,309 / 1,166 / 1,152 / 1,208 / 1,207 = 15,345.

## Assumptions, and why they do not weaken the result

- **Bands are the packaged stock values.** `gamedata/modpatch.py` patches
  *recipes*, never bands, so the corpus scores every save against one stock
  band table (`ware_band`, sourced from `RefData`). Two of the ten wares come
  from `ego_dlc_terran`, the rest from the base game; none is mod-supplied.
- **Sanity check on that assumption.** If a mod had rewritten any of these ten
  bands, the observed price would *not* land on the stock midpoint — a shifted
  band moves the midpoint. All ten land exactly, so for these wares the
  engine's band equals the stock band, and no non-stock band is implied
  anywhere in the population. (This is a check on ten wares only; it says
  nothing about bands elsewhere in the economy.)
- **Zero-amount offers.** 819 of the 15,345 offers carry `amount = 0` (a
  satisfied station still posting the offer — the E-127 floor caveat). They
  price at the midpoint like every other offer, which is consistent with the
  price being independent of the position: it is a constant, not a curve
  evaluated at zero.

## What this changes

- The `supplies` book is a **fixed point on the ordinary cosine**, not a
  separate price book with per-ware constants. `s = +0.5` for every ware.
- It is stock-independent: the same station at the same ware posts the same
  price whatever its held/on-order position. This is consistent with E-127's
  finding that the self-supply position is `held + on_order` — the price does
  not read that position at all.
- For the price model that Phase 3 will implement, `supplies` needs one branch:
  detect the flag, return `avg + 0.5·(max − avg)`. No parameters.

## Register recommendation (for the Phase 4 docs-sync agent)

- **New entry (next free id, e.g. E-129) · CONFIRMED** — "The `supplies`
  self-supply buy price is the band midpoint, `s = +0.5` exactly."
  *Predicts:* `price = (price_avg + price_max)/2`; 15,345 offers over 13 saves,
  9,594 station-save pairs, 19 factions, 10 wares, maximum deviation 0.00 Cr;
  half-credit prices 53.5 / 240.5 / 1,520.5 fall out of the rule.
  *Falsified by:* any `supplies` offer ≠ its band midpoint.
  *Source:* this report.
- **E-027 → SUPERSEDED**, *Replaced by:* the new entry. Its ten constants are
  `1 + spread/2` and are not independent numbers. Keep the old id.
- **reference/save-semantics.md § Self-supply (`supplies`)** — replace the
  per-ware constant table with the midpoint rule (the table can stay as a
  worked example, relabelled as *derived* values).
- **models/station-pricing-model.md** — add `supplies` to the price-book list
  as a fixed `s = +0.5` branch of the same cosine, not a separate book.
