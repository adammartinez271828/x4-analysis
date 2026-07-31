# How the storage and pricing models were found — a narrative

Written 2026-07-31. A story, not a reference: every claim cites the register
entry that owns it, and the rules live in [../models/](../models/).

---

## The plumbing came first

The project began as a port — an R script for X4 v5.10, rewritten in Python
for v9.0 and grown into a streaming parser, a SQLite database and a dashboard.
That made a new question askable: the market tab wanted to show how *full* a
station was, which meant knowing how much of each ware a station will hold.
The save does not say. The first answer was a proxy — stock, plus inbound,
plus open bids — which is a lower bound and behaved like one (E-054).

## Equal hours

The insight, when it came, was one line. **A station does not size storage in
units. It sizes it in hours.** Every ware in a transport pool holds the same
number of hours of its own throughput, after rations take a fixed 4-hour
buffer off the top — so a fast ware gets a big allocation, a trickle a small
one, and they all run dry at the same moment (E-037).

What made it stick was the loop: the player paused the game, opened a
station's Logical Station Overview and wrote down what it states outright, and
offline the model replayed those inputs without a savegame. WRC-739 came back
four for four to the unit — 4,093 / 9,445 / 3,085 / 2,267, every ware on the
same 6.30 hours. The fixture now stands at **137 of 138 readings within 1 %**
over fourteen stations.

The rule was never the hard part; the throughput was. The engine truncates per
*cycle*, not per hour (E-038), and the efficiency multiplier applies to
outputs only (E-040, E-042).

## One cosine

Pricing started worse. The first published curve was "near-linear with knees",
scored on per-offer error — which is dominated by the crowded middle of the
curve, where a line and a cosine are indistinguishable. Retracted (E-002).
Re-scored on bin medians, equal weight per bin, the answer is a
**cosine in storage fill, span 1.095**, beating a clamped line by 10× (E-001);
the sell side is the *same* cosine at the *same* span with one small additive
offset (E-005). Then the tails: some stations priced as though their storage
were tiny, others as though it were enormous, and it was one rule — a supplier
prices on whichever runs out first, its storage or **five million credits** of
that ware (E-113, E-114). Zero free parameters.

## The wrong turns that paid

**JAR-041** read 42,516 energy cells where the game said 21,001 — a clean
factor of two, and the *prices* had said so first: four wares implying a
denominator error of 1.998, 1.994, 2.037, 1.984, before anyone read the
station (E-065). The cause was a parser bug: module entry ids are unique only
per station, so one station's finished module marked another's unbuilt one
built (E-064). The rule was right and its input was wrong — a constant *scale*
error points at capacity, a constant *shift* at pricing.

**The Avarice scavengers** looked like a 1.21–1.30× storage error for days. It
was not a storage error but the price analysis holding the supplier offset
fixed at +0.053; freeing that parameter dissolved it, and the player later
read those allocations in game at the modelled values (E-115).

**EIJ-609** was carried as the one reading the model could not reproduce.
Thirteen archived saves settled it: its allocation stepped to a multiplier of
exactly 1.0, and by the next epoch it carried no `<production>` block at all —
where the model's own idle rule reproduces it exactly (E-051 FALSIFIED,
E-136). The failure was a snapshot of a transient.

## The campaign

By 2026-07-29 the open questions outnumbered the evenings, so they were
triaged: every open item in both subsystems, split by what could be settled
*without the player*. A corpus of 13 archived saves turned single-snapshot
fits into 15,300 s of trajectory, and parallel agents each took one item and
produced one dated report; then the price model went into `src/` for the first
time, and the docs were re-synced. Net: **25 items triaged, 8 statuses moved,
11 new register entries, no in-game reading consumed.**

## The last evening

What was left needed the player. At game time 84,968 they read two drone pools
(503 and 361, both exact — E-062), ran an experiment showing that
`<supplies><orders>` is a build *target* (E-063), and read three scavenger
panels — from which *they* proposed the mechanism the analysis had missed: the
Logical Station Overview omits the scrap processor's energy draw, so a station
the game shows as a net producer is an active buyer (E-140).

The reputation discount fell the same evening. A relation-scaled law was
proposed and falsified within hours (E-141); its replacement, the tier times
the *band width*, reproduced twelve panels to the cent and then met a station
it could not explain. A re-read gave the cap,
`discount = tier × min(price, band width)`, confirmed at full separation on a
deliberately chosen graphene-glut pair (E-142).

Then someone opened the game's own `libraries/parameters.xml` and found both
hard-won constants written down: `<economy><storage workforce="14400"/>` — the
4-hour ration buffer, in seconds — and `<economy><prices><product
factor="5000000"/>`, the cap, exactly (E-037, E-116).

## What the arc was made of

Predictions that named exact numbers before the reading: EWQ-469's 503 drones,
WRC-739's four allocations, JAR-041's factor of two. Falsification discipline:
39 register entries are FALSIFIED and keep the evidence that killed them, and
where two documents genuinely disagree the register records both rather than
picking a winner.

And one lesson paid for: the 2026-07-27 deployable study committed its
conclusions but not its raw quotes, so on re-reading four game-days later the
question it existed to answer was **undecidable** (E-034). Record the raw data
— the derivation is cheap to redo, the reading is not.

---

## Appendix — the most interesting things this turned up about X4's economy

Each is CONFIRMED unless marked otherwise, with the register entry that owns
it.

- **Stations allocate storage in equal *hours*, not units.** Every ware in a
  transport pool holds the same hours of its own throughput, so they all run
  dry together. (E-037)
- **The 4-hour ration buffer is an engine constant, written down:**
  `libraries/parameters.xml` `<economy><storage workforce="14400"/>` — 14,400
  seconds. Measured for three sessions before it was found stated verbatim.
  (E-037)
- **Food reserves are sized on the station's *employment target*, not its
  population.** PTW-627 reserves 4 hours for 1,000 workers while 104 live
  there — and the target is a sum: the modules' declared workforce plus the
  station design's own. (E-124)
- **The ration buffer is floored per race, then summed.** DCO-580's 1,163
  medical supplies is 334 + 495 + 334; one floor on the summed rate gives
  1,164 and misses. (E-120)
- **It is keyed on the races actually present, not on who eats the ware.**
  Water — the Boron ration — is an ordinary traded ware at Argon/Paranid/Teladi
  DHI-588. (E-120)
- **Every price that moves with stock is one cosine**, span 1.095, from band
  minimum through average to maximum. A clamped line loses by 10×. (E-001,
  E-005)
- **A supplier's price target caps at five million credits of the ware** — it
  prices on whichever runs out first, its storage or 5 M Cr. The constant is
  the engine's own: `<economy><prices><product factor="5000000"/>`. (E-113,
  E-114, E-116)
- **There is one price per (station, ware): buy = sell − 1 Cr, always.** 704 of
  706 two-sided pairs exactly; both exceptions are player-owned. (E-022)
- **A station's self-supply buys sit at exactly the band midpoint**,
  `(avg + max)/2` — `s = +0.5` on the same cosine, no parameters, no stock
  dependence. 15,345 offers across 13 saves, maximum deviation 0.00 Cr; the
  half-credit prices (53.50, 240.50, 1,520.50) are the giveaway. A freshly
  minted offer is born on the rule rather than converging onto it. (E-129)
- **The black market has two disjoint tiers**, and the fixed 2.750 × band
  average one belongs to *unstaffed* stations — necessary, not sufficient, and
  the tier is mutable state the save gives no other handle on. (E-112, E-134)
- **Shipyards and wharfs are not a separate price family.** They are the
  ordinary cosine with one station constant, `a ≈ −0.202`, which also explains
  the ~0.17 band floor at full fill that the old power-law description left as
  an anomaly. (E-131)
- **A yard's `buildpricefactor` lives on a 15-value global alphabet** (0.900 …
  1.150), clamped for NPCs with *sticky* bounds — P(change) 0.11 at 0.900 and
  0.15 at 1.150 against 0.50 in the interior — and each station visits at most
  four of them. On a player yard it is simply the price slider. (E-035)
- **The Logical Station Overview omits the scrap processor's energy draw; the
  market side does not.** Scavengers the game shows as net energy producers are
  active buyers, because the processor-inclusive net is negative. (E-140)
- **A "missing" buy offer can be a zero-amount offer.** CCN-497 held 25 of
  1,375 allocated energy cells and showed no offer on the panel — because one
  pending trade carried 1,375 inbound, exactly the allocation. Stations price
  and bid on the *net position*, not on cargo. (E-023)
- **A full station withdraws its buy offer entirely** rather than pricing it at
  zero — so a price history reading 0 means *no offer*. (E-055)
- **Allocation is a trade target, not a physical cap.** MBI-471 holds 14,330
  energy cells against a 4,403 allocation, in the game's own menu. (E-056)
- **Station drone capacity = Σ module unit storage + 10 per built production
  module.** Predicted 503 and 361 on two NPC stations; read exactly. (E-062)
- **`<supplies><orders>` is the build TARGET, not outstanding orders** — and
  the self-supply demand follows the station's *resolved build method*, not its
  owner race's default. (E-063, E-075)
- **The reputation discount is `tier × min(offer price, band width)`**,
  displayed as a percentage of band average (which is why the shown percentage
  varies per ware). The tiers are real and stored — one md-created record per
  faction on the player component, 0.05 / 0.15 / 0.25. (E-142)
- **Build storages hold no storage allocation at all** — 0 of 1,771 — so no
  fill coordinate exists for them; they sit flat at band maximum to a knee and
  then fall, which is a description and not a law. (E-118)
- **Nothing in the save is a GUID.** Codes are recycled after death, and live
  collisions exist among simultaneously-alive same-faction same-class ships —
  two Terran fighters both coded XPU-790. (E-076)
- **A fully depleted resource field does not respawn in place — it moves**, to
  a random in-sector position, by per-axis multiples of 20 km. And the stored
  yield materializes when a miner makes contact, not on a timer. (E-085,
  E-086, E-088)
