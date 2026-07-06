# Feasibility study: continuous ship & station construction demand

Status: **partially implemented** — the Market tab's "Constr/h (est.)"
column and the Build Advisor's demand factor use estimators A and D
(`market.construction_rates`): construction-only wares get producer
outflow (≈), dual-use wares get yard intake as a lower bound (≥).
Estimator B' (draw minus module consumption) and the C spawn analysis /
construction tab remain unimplemented.

Corrections since first written (see CLAUDE.md "Market tab data
semantics" for the authoritative versions):

- The "Build demand = materials missing right now" premise referenced
  below was **wrong** — the save's `<insufficient>` amounts are not
  per-ware quantities. Build demand is now the build storages' open buy
  offers, and the "30.0M-unit claytronics backlog" figure below came
  from the disproven data; the flow-based rates were re-validated
  against offer-based demand and stand.
- Satisfy (h) already handles the no-surplus case with a
  backlog-in-hours fallback, which supersedes the "374 h" criticism.
Question: can we estimate construction demand as a *rate* (units/hour,
ongoing) instead of the current snapshot metrics (Build demand = materials
missing right now; shipyard order backlogs excluded as unmeasurable)?

**Verdict: yes — via an ensemble of three independent estimators, each
measurable from a single save, each with a known bias. Validated against the
reference save on 2026-07-05.**

## The two unexploited data assets

1. **Every ship has a `spawntime`** (14,420/14,420 NPC ships in the
   reference save). A single save therefore contains the *entire campaign's*
   fleet-production timeline. Recent window: 1,093 ships/h spawned over the
   last 5 h (3,330 S / 1,452 M / 216 L / 55 XL; Xenon 2,814, Kha'ak 461,
   then argon/teladi/boron/holyorder ~250–320 each).
2. **The negative half of the stock-delta stream.** The Market tab's
   traded-volume estimate uses only positive deltas (deliveries); negative
   deltas at a station = stock leaving it (consumption, construction draw,
   or sales).

Ship build recipes (exact material lists per ship) are already extracted in
`recipes.csv`; 5,019 of 5,495 recent spawns matched a recipe (unmatched are
mostly mod/special macros).

## The estimators and what validation showed

### A. Yard intake — "what construction buys from the market" (primary)

Positive stock deltas at stations with build modules = sustained purchasing
rate of construction materials. **This is the decision-relevant number for a
trader**: what shipyards/wharves continuously absorb, per ware, per hour.
Cleanly measurable today; ~19.5 h observation window in the reference save.

### B. Yard draw — "what construction consumes" (needs one refinement)

Negative deltas at yard stations. Measured (commonwealth yards):
energycells 1.01M/h, hullparts 128k/h, microlattice 96k/h, smartchips
38k/h, weaponcomponents 15k/h, engineparts 12k/h.

**Known contamination:** yards also host ordinary production modules and
resell wares, so draw ≠ construction alone (energy cells especially).
Refinement: subtract the station's *known module consumption rate* (already
computed per station for the Market tab) from its draw. Residual ≈
construction + resale.

### C. Spawn-mechanistic — composition, trend, and cross-check

Ships spawned per window × their build recipes → demand by ware, faction,
and ship size. Measured (last 5 h, excl. Xenon/Kha'ak): hullparts 395k/h,
energycells 292k/h, water 23k/h, microlattice 12k/h.

**The disagreement with A/B is informative, not fatal:**

- hullparts: C says 395k/h "recipe-equivalent", observed yard draw is only
  128k/h → a large fraction of NPC ship spawns are **job-system respawns
  that don't consume market materials** (the game spawns replacement ships
  administratively). C is therefore an upper bound on material demand but
  the *right* measure of fleet-replenishment tempo; A/B measure what the
  economy actually pays for.
- energycells: observed draw (1.01M/h) far exceeds C (292k/h) → confirms
  B's contamination by co-located modules/resale; the refinement in B is
  required before quoting per-ware construction consumption.
- Ratios by ware also differ because ship mix ≠ recipe mix (Xenon build
  from ore/silicon: their spawn demand of 52k ore + 44k silicon /h explains
  most of the ore/silicon draw seen at all-faction yards).

### D. Station-side construction (no spawn analogue for modules)

Build storages do **not** emit stock events (verified: no buildstorage
owners in the economylog), so station-construction draw isn't directly
observable. Two workable proxies:

- **Construction-only wares (claytronics):** producer outflow (negative
  deltas at producing stations) = absorption by construction, since nothing
  else consumes it. Measured: **15,585/h** — notably cleaner than the
  delivery-based 37.3k/h (which double-counts production accumulation).
  Against the 30.0M-unit backlog this gives a *flow-based* satisfy horizon
  of ~1,900 h — far more honest than the current surplus-based 374 h.
- **Dual-use wares (hullparts, energycells):** station share ≈ producer
  outflow − yard intake (A). Wider error bars; label accordingly.
- New-station tempo: stations also carry `spawntime` → new stations/h by
  faction as a trend indicator (module expansions remain invisible).

## What this would look like in the Market tab

- New column **"Constr. demand/h"** per ware = yard intake (A) + station
  absorption (D), with the info panel documenting the estimator per ware
  class (construction-only vs dual-use).
- **Satisfy (h) upgrade:** for construction wares, use flow-based absorption
  instead of production surplus (fixes claytronics' misleading 374 h).
- New **Construction section/tab**: shipbuilding tempo chart (spawn
  histogram over the whole campaign — one save gives the full curve),
  demand by faction and ship size (from C), yard intake vs draw per ware,
  new-station rate.
- Player-relevant framing: "yards are absorbing X/h of hullparts and are
  understocked at N of M — selling into this is sustainable at ~X/h."

## Implementation sketch (if/when built)

1. `frames.global_trades`: add negative-delta column (`dv_neg`) alongside
   `dv` (one-line change to the existing diff).
2. Classify stations: yard (has buildmodule — already derivable from
   `station_modules`), producer-of-ware (from module map).
3. Estimator table per ware: intake(A), draw−modulecons(B'), spawn-recipe
   (C, windowed, faction/size cube), producer-outflow (D where applicable).
4. Reconciliation + display rules per ware class; info-panel methodology.
5. Spawn histogram figure (campaign-long tempo, by faction/size).
6. Tests: synthetic economylog fixtures for A/B/D; recipe-join test for C.

## Risks / caveats

- Survivorship bias in C: destroyed ships leave the save, so older windows
  undercount; use recent windows (2–6 h) and say so.
- The economylog observation window (~19.5 h here) sets the floor on how
  "continuous" the rates are; early-campaign saves will be noisy.
- B' requires the module-consumption subtraction to be per-station (data
  exists) — without it, do not present B at all.
- Job-system spawn mechanics are reverse-engineered inference; the C-vs-A
  gap attribution (free respawns) is well-supported but not provable from
  the save alone.
- Player-view mode (see player-view-plan.md) interacts: all estimators are
  omniscient; under player-view they need the same masking treatment as
  traded volume.
