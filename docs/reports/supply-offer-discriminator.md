# Supply-offer discriminator: `flags="supplies"` — CONFIRMED

Session 2026-07-26. Question: does X4 save data distinguish supply trade
offers (drone/ammunition component buys) from production-resource trade
offers? Testbed: player station ABR-398 ("Recycling Facility I", The
Reach) in save_007, whose in-game trade menu shows box-icon buy orders
for metallic microlattice and silicon carbide alongside a drone build
target of 50.

**Verdict: CONFIRMED.** An offer whose `flags` attribute contains the
token `supplies` is a station self-supply buy (an input for the
station's own drone/munition building); production-resource offers
never carry it. Confirmed universe-wide on two saves with zero
unexplained counterexamples, and quantitatively exact on ABR-398.
Shipped as schema v18 (commit `bd9a842`).

## Observation → structure

ABR-398's full subtree was extracted from save_007
(streaming `iterparse`, scratch script `extract_station.py`). Its
`<trade><offers><production>` block holds 9 offers; the two the game
box-icons are the only ones flagged:

```xml
<trade id="[0x8b44]" buyer="[0xa30d9]" ware="metallicmicrolattice" price="5350"
       amount="0" desired="2150" flags="supplies|invertfactionrestriction">
<trade id="[0x8b45]" buyer="[0xa30d9]" ware="siliconcarbide" price="152050"
       amount="0" desired="190" flags="supplies|invertfactionrestriction">
```

The other 7 (energycells/rawscrap/scrapmetal buys, claytronics/
hullparts/energycells/scrapmetal sells) have no `supplies` token. The
grouping element (`<production>`) and the `<source class="production"/>`
child are constant across ALL offers universe-wide (15,418/15,418) —
neither discriminates anything. The flag is the discriminator.

### Recipe verification (the wares cannot be production inputs)

ABR-398's modules: 3× `prod_gen_energycells` (2 built), 1×
`prod_gen_scrap_recycler`, 1× `proc_gen_scrapworks`. Their recipes
(packaged `recipes.csv`) consume only energycells, scrapmetal, rawscrap
(+ the recycling methods' energycells). `metallicmicrolattice` and
`siliconcarbide` appear in NO production-module recipe — only in
equipment/drone recipes.

### Quantitative closure — the numbers are exact

ABR-398's `<supplies><orders>` block: cargodrone 30, repairdrone 10,
fightingdrone 10 (Σ = 50 = the in-game build target). At the terran
drone-build method:

| input | 30 cargo | 10 repair | 10 fighting | total | save value |
|---|---|---|---|---|---|
| metallicmicrolattice | 30×51 | 10×33 | 10×29 | **2,150** | flagged offer `desired="2150"` |
| siliconcarbide | 30×4 | 10×4 | 10×3 | **190** | flagged offer `desired="190"` |
| energycells | 30×500 | 10×500 | 10×500 | **25,000** | `<supplies><wares>` on hand — no offer needed (station makes its own EC) |

Every number matches exactly. On flagged buys, `desired` = the
outstanding self-supply input need.

## Sweep evidence

Universe-wide collection (scratch `sweep_offers.py`: every offer with
all attributes + group tag + `<source>` class, plus per-station
`<supplies>` orders/wares, `<ammunition>` items, production/processing
modules; analysis joined against the packaged recipe/module CSVs).

### save_007 (primary)

- 15,418 open offers; **1,140 flagged `supplies`** — 1,140/1,140 are
  **buys**, 1,140/1,140 hosted on **stations** (no ships, no build
  storages), spanning **all 17 owner factions** (player: exactly
  ABR-398's 2 — matching the in-game observation that only those two
  show the box icon).
- Flagged ware set (9 wares) ⊂ the supply-recipe input family (inputs
  of `ship_*`/`missile_*` build recipes): smartchips 466,
  missilecomponents 352, dronecomponents 204, energycells 50,
  metallicmicrolattice 26, siliconcarbide 21, ore 10, silicon 10
  (xenon method), hullparts 1 (closedloop method). **Zero flagged wares
  outside the family; zero flagged sells.** The missilecomponents/
  smartchips counts show the mechanism covers **ammunition resupply**,
  not just drones.
- 25/7,700 in-flight `<reservation>` rows carry the flag too — supply
  purchases keep it through execution.

### Dual-role wares (both production input AND supply input)

16 flagged offers are for wares that are also production inputs of
their host (15× energycells, 1× metallicmicrolattice). 12 of the 16
hosts hold a **separate unflagged buy for the same ware** — the game
maintains the two demands as distinct offers on one station (the other
4 simply have no open production buy). Not counterexamples: they are
the discriminator working as designed.

### Candidate counterexamples, resolved

Unflagged station buys of supply-family wares, checked host by host:

- **ULG-519** (split, buys missilecomponents 258 + smartchips 2,188
  unflagged): carries `buildmodule_gen_ships_xl` — a **shipyard**. These
  are ship-construction resources (alongside engineparts,
  scanningarrays, khaakalloy…), a third demand class the game leaves
  unflagged.
- **MXH-411** (player, unflagged hullparts/turretcomponents/
  weaponcomponents/advancedcomposites buys with `desired` ≫ `amount`):
  carries `buildmodule_ter_ships_m` — wharf ship-building demand, same
  class. Its drone orders (30/10/10, same as ABR-398) generate **no**
  flagged offers because it **produces metallicmicrolattice and
  siliconcarbide itself** (27 production modules; it sells both) —
  internal sourcing needs no offers, exactly consistent.
- The remaining bulk (682 each of spaceweed/spacefuel/majadust/
  stimulants) are `shady`-flagged trade-station arbitrage buys, and
  JQR-498's energycells buy is HQ production trading (sell twin
  present).

**Zero unexplained counterexamples.**

### save_006 (replication control)

15,402 offers, **1,127 flagged** — same invariants: 100% buys, 100%
stations, same 9-ware family, zero outside it, zero flagged sells;
ABR-398 shows the identical 2 flagged offers with the identical
`desired` values.

## Bonus finding: drone build targets ARE persisted

`<supplies><orders>` (present on 21 stations in save_007, 40 ware-rows)
cross-checked against each host's `<ammunition>` counts: **37/40 rows
have on-hand exactly equal to the order amount, 0/40 exceed it**; the 3
short rows are ABR-398's (mid-gather, 0 drones on hand). With ABR-398's
in-game target of 50 = its orders sum, the block reads as the persisted
drone build **target** — contradicting save-semantics' earlier "desired
levels are not persisted anywhere" claim (that search used the wrong
needle, `$config_supply_*`). Caveat kept as hypothesis: only ~21
stations carry the block (absence ≠ no target), and
target-vs-outstanding-orders semantics need the play experiment below.
Docs corrected in the same commit.

## Implementation (schema v18, commit `bd9a842`)

- **Parser** (`save/parser.py`, same single pass): offer tuples gain
  the raw `flags` string and `desired`.
- **Schema v18** (`db/schema.py`): `trade_offer.flags`,
  `trade_offer.desired`; `station_storage` PK gains `role` (a ware can
  hold a production-side row and a supply row on the same station).
  W-table change — rides the drop-and-recreate bump, no
  EVENT_MIGRATIONS entry needed.
- **Storage model** (`analysis/storage.py`): `supplies`-flagged buys
  are excluded from the non-producer stock+buy proxy (they fill the
  separate `<supplies>` inventory, not cargo storage) and emitted as
  `role='supply'`, `source='offer'` rows for every station —
  `max_units` = outstanding need (`desired`, falling back to `amount`).
- **Left unchanged, deliberately**: the A-table aggregates
  (`station_metric.buy_open_cr`, `market_stat`) keep counting flagged
  offers — their accumulated history predates the flag and changing the
  computation would fork its semantics. The market/advisor widgets
  likewise still count them (1,140 of 15,418 offers; flags are now in
  `frames.trade_offers` for a future cleanup). The drone-pool
  capacity model is untouched (nothing here contradicts it — MXH-411's
  27 production modules × ~10 + floor 40 = 310 remains consistent).

### Tests (`uv run pytest -q`: **208 passed** at every commit)

- `test_saveparser`/`test_store`: fixture gains a supplies-flagged
  offer; round-trip of flags/desired through DB and frames asserted.
- `test_storage`: flagged buys excluded from the proxy max; supply rows
  emitted on proxy AND computed-path stations (`desired` fallback to
  `amount`); frames without the v18 columns still work. All pre-existing
  in-game-validated reference numbers (GDR-378-style throughput×T cases,
  proxy r=0.9984 fixture) re-run green unchanged.
- `test_drones`: reference numbers (ABR-398 40, EBT-957 92, QJI-262
  220 floors) re-run green unchanged.

### Real-DB safety protocol (per phase2-v11-bump.md)

Pre-change checksums (2026-07-26, before any write):

```
cf4ccf029250e02bb22733aac42d604634a545bf6436b446fa158e49e26d653a  x4_8E0C8E37-….sqlite
9a1911420401faebbcff7d99dfa1939ea1f0999657f4570e4572155cffc167a2  x4_94062A45-….sqlite
```

Backup: `backup/x4_8E0C8E37-….20260727T015238Z.pre-v18.sqlite`
(checksum recorded in `backup/checksums-20260727T015238Z-pre-v18.txt`,
byte-identical to the live pre-state).

Rehearsal (scratch copy + user-dir CSVs, `--data-dir`): v17→v18 walked
cleanly; save_007 imported (offers 15,418, flagged 1,140, supply rows
1,140; ABR-398 = MML 2,150 + SiC 190); second identical import added
**0 rows to every event table** (only the by-design `save` provenance
row); dashboard built both runs.

Real run (8E0C, the current playthrough): identical counts to the
rehearsal; second import again added 0 event rows; dashboards built.
Post-state: schema_version 18, checksum
`b65ee1e8ead85f93331488f0e0322192cae3ec28f6a17c7dda6611041a7e60ad`.
The 9406 DB was not written (post checksum identical to pre:
`9a191142…`); it walks to v18 on its own next import.

## Play checklist (open ends, each with the evidence it would produce)

1. **Target vs outstanding orders**: on a full station (e.g. MXH-411,
   50/50 drones), raise the drone build target (e.g. cargo 30→40),
   save. If `<supplies><orders>` cargo reads 40 → it's the target; if
   10 → outstanding orders. Lower it below current stock afterwards to
   see whether the block shrinks/vanishes without scrapping drones.
2. **Block lifetime**: on a station with no `<supplies>` block, set any
   build target, save, then let it complete and save again — does the
   block appear and then persist (supporting "target") or clear
   (supporting "orders")?
3. **Ammo targets**: set a missile stock level on a defence station,
   save — do missile wares appear in `<supplies><orders>` and their
   components as `supplies`-flagged buys (extending the 37/40 evidence
   from drones to munitions)?
4. **Method selection**: ABR-398 uses the terran drone recipe
   (terran-built modules). Order drones on a non-terran player station
   lacking the inputs and diff which component wares get flagged offers
   — pins whether build method follows module race, faction, or
   something else.

None of these gate the discriminator itself — it is CONFIRMED as
shipped; they close the remaining `<supplies>` semantics.
