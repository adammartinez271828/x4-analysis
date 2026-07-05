# Feasibility study: future analytics tools

Status: **idea catalogue, nothing implemented.** Companion to
`player-view-plan.md`. Feasibility ratings are grounded in what the save and
game data are known to contain (see CLAUDE.md "Market tab data semantics"
for the hard-won parsing knowledge these build on).

Design principle (user-confirmed): prescriptive tools produce **ranked
recommendations whose scores decompose into visible factors** — a top-10
list where every score can be expanded into profit / distance / danger /
etc., with tunable weights. Never an opaque oracle.

Priority guidance (user-confirmed): all four themes appeal; cross-run
history is constrained by the user *not* wanting to run the analyzer
habitually — see the watch-mode idea (#10) which removes that constraint.

---

## A. Prescriptive advisors

### 1. Trade route finder — feasibility: HIGH ⭐ recommended first

"Buy ware W at station A for P₁, haul N units (M m³) through K gates, sell
at station B for P₂ → profit/trip, profit/hour, profit/m³."

- **Data:** open buy/sell offers with prices, amounts, station sectors (all
  already parsed for the Market tab). Sector adjacency graph from gates:
  220 known gate components exist in the save with sector ancestry;
  gate-pair connections also derivable from game files
  (`galaxy.xml` connections) for unrevealed links.
- **Work:** build the sector graph once; BFS distances; enumerate
  (sell-offer × buy-offer) pairs per ware; score = spread × min(amounts)
  constrained by a configurable cargo size, discounted by gate distance.
- **Factors exposed:** spread, volume ceiling, cargo trips, gate count,
  sector danger (from #8's threat index), counterparty faction.
- **Risks:** none structural; needs the player-view caveat (omniscient
  offers) eventually.

### 2. Station build advisor — feasibility: MEDIUM-HIGH ⭐ the killer feature

Score "build a W factory in sector S": market gap (Market tab metrics) ×
input availability nearby (sell offers + mining yields within R gates) ×
demand proximity (understocked buyers within R gates) × danger × workforce
availability (habitat food supply chains nearby).

- **Data:** every factor already computed or parsed; needs the sector graph
  from #1 and a scoring model.
- **Work:** mostly the scoring model + a per-sector detail view justifying
  each recommendation ("claytronics fab in Segaris: 30M build demand within
  3 gates, silicon at 152 Cr 1 gate away, 0 hostile events logged").
- **Risks:** recommendation quality is judgement-laden; mitigate with the
  decomposable-factors principle and tunable weights.

### 3. Blueprint ROI calculator — feasibility: HIGH

For each buildable production module: build cost (module ware build recipes
— already in recipes.csv) + blueprint price (game data) vs revenue at
*current live prices* (best open buy offers) → payback hours, ranked.

- **Data:** all present. Needs blueprint prices extracted (wares.xml has
  module ware prices; blueprint licence costs live in game data too).
- **Work:** small; a table on the Market tab or its own tab section.
- **Nuance:** revenue should offer both "average price" (conservative) and
  "current best offers" (opportunistic) columns.

### 4. Mining site advisor — feasibility: HIGH

Best sectors per minable ware: resource yield (parsed for the map) ×
distance to paying buyers (graph from #1) × danger × current competition
(NPC miner density per sector — countable from universe ships with
purpose="mine" per sector).

- **Data:** all present including competitor density, which is a nice
  differentiator ("high yield but 40 NPC miners already work it").

---

## B. Own-empire operations

### 5. Empire bottleneck audit — feasibility: HIGH ⭐ highest value/effort

One page listing everything wrong with YOUR assets:

- production stalled waiting for inputs (own stations' `<build>`/queue
  states and `insufficient` blocks — richest data in the save);
- output storage saturated → production choking (cargo vs capacity; may
  need storage-capacity extraction from module macros);
- idle ships (no orders / default orders only — order queues are in the
  save, currently unparsed);
- understaffed stations (workforce vs `workforce max` per module);
- ships without engineers, low-skill pilots on high-value ships (already
  parsed for df.ships).

### 6. Station P&L statements — feasibility: HIGH

Per-station: revenue, input costs, net profit/h, trend; ROI ranking across
the empire. Extends the existing Trade History data (per-station trades are
already attributed); add module-based cost attribution for shared stations.
The cross-run cache already accumulates the needed history passively.

### 7. Fleet readiness report — feasibility: HIGH

Hull %, missing crew, engineer gaps, pilot skill distribution, equipment
tier audit (mk1 shame list — loadout components are in the save, currently
skipped), and ammo/missile/drone reserves vs capacity (the
`<supplies><wares>` blocks explicitly excluded from market stock are
exactly this data).

---

## C. Military / strategic

### 8. War dashboard + threat map — feasibility: MEDIUM-HIGH

- Hostile military mass per sector (universe ships × ship mass × owner
  relations — relations are in the save's faction data, unparsed);
- map overlay of Xenon pressure on border sectors;
- defence coverage: friendly defence platforms per border sector;
- station kills from the global log (all factions' losses, not just
  player's — `destroyed` entries exist for NPC stations too, worth
  verifying coverage).
- **Output:** a "front line report": sectors likely to flip, with the
  factors visible (hostile mass vs defence mass vs recent losses).

### 9. Loss heatmap — feasibility: HIGH (small)

Player ship losses on the map with killer attribution and time trend.
Mostly a presentation extension of the existing Destroyed table; danger
scores feed advisors #1/#2/#4.

---

## D. Cross-run history

### 10. Autosave watch mode — feasibility: MEDIUM ⭐ unlocks the theme

The user won't run the analyzer habitually — but X4 writes autosaves every
few minutes regardless. A `x4-analyzer --watch` daemon (or scheduled task)
that notices new autosaves and silently appends compact snapshots (prices,
stocks, ownership, player net worth) to the existing cache infrastructure
would build history with **zero user habit change**. Parsing is already
fast enough (~18 s) to run per autosave.

- **Risks:** long-running process UX; snapshot compaction so years of play
  stay small; autosave cadence varies.

### 11. History charts — feasibility: HIGH *once #10 exists*

Price history per ware, sector ownership timeline / war-progress animation,
player net-worth curve, market Fill %/backlog trends. All are simple charts
over #10's snapshots; without #10 they degrade to whatever sparse manual
runs exist (design must tolerate gaps).

### 12. Supply-chain Sankey — feasibility: MEDIUM (single-save, bonus)

Ware flow diagram (ore → refined → components → ships) per faction from the
capacity/delivery data; plotly has native sankey support. The work is
layout readability, not data.

---

## Suggested build order

1. **Sector graph** (shared infrastructure: gates → distances) — enables
   #1, #2, #4, #8.
2. **#1 Trade route finder** — highest immediate decision value, proves the
   graph.
3. **#5 Bottleneck audit** — best value/effort, no new infrastructure.
4. **#2 Build advisor** — the flagship, once #1's graph and the danger
   index from #9 exist.
5. **#9 → #8** military layer.
6. **#10 watch mode** when history features get pulled.

#3, #4, #7 are independent small wins to slot anywhere.
