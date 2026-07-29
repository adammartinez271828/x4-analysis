# Trade stations allocate storage by equal VOLUME, not equal hours

**2026-07-29.** Save `8E0C8E37-2192-49FD-BF4B-F535782A1C55`, snapshot
`save_id = 70`. Prompted by the player's full in-game reading of DHI-588
(`[0x33296]`, Quettanauts / `kaori`, `station_arg_tradestation_base_01_macro`,
Mitsuno's Sacrifice), which the proxy reproduced 34 of 38 times.

Append-only, per CLAUDE.md. Nothing in `src/`, `docs/reference/`,
`docs/models/` or `docs/experiments/` was touched; proposed register entries are
quoted at the end for someone else to apply.

---

## Summary

1. **A non-producing station that is not also a build station divides each
   storage pool into EQUAL VOLUME shares, one per traded ware**, after the
   workforce ration reserve has come off the top. The share is
   `(pool_capacity − Σ ration_volume) / N`, and each ware's allocation is
   `floor(share / ware.volume)`. This is why the readings pair up: two wares of
   the same `ware.volume` get the same number of units, necessarily.
   **CONFIRMED** — every one of DHI-588's in-game readings reproduced to the
   unit (36 traded wares + 4 rations), and 95.7 % of 561 (station, ware) pairs
   across 49 stations exactly, with **zero cases anywhere in the population
   that exceed the predicted share**.
2. **This is not a new mechanic — it is the existing model's degenerate case.**
   `station-storage-model.md` already says a pool that no recipe touches gets
   `capacity / count(wares) / volume` (the condensate rule). A trade station is
   a station where *every* pool is in that state. The equal-hours split and the
   equal-volume split are the same rule; with zero throughput there are no
   hours to equalise, so the pool is shared by head count.
3. **The proxy's entire error is one missing term: inbound reservations.**
   `stock + open buy amount` omits goods already contracted and in flight.
   Adding `trade_pending` (buyer_id = station, `amount − transferred`) closes
   all four DHI-588 misses *exactly* and lifts the population from 82.9 % to
   97.3 % exact. `save-semantics.md` already names the correct quantity —
   `stock + inbound + amount` — but `analysis/storage.py` does not compute it.
4. **Wharfs, shipyards and equipment docks are NOT governed by this rule** and
   must not be folded into it. Median coefficient of variation of
   allocation-volume across a group's wares: **0.00004** for trade stations,
   **0.80** for build stations. 33 % of build-station wares exceed the equal
   share, some by 8×.

---

## 1. The rule

Per station, per **storage pool group**:

```
share = (pool_capacity − Σ ration_reserve_volume) / N
max(ware) = floor(share / ware.volume)
```

- **`N`** = the number of wares the station *trades* in that pool group:
  every ware carrying an open `trade_offer` (either side, including a sell
  offer with `amount = 0`), **excluding** offers flagged `shady` or
  `supplies`, and **excluding** wares that are `workunit_busy` inputs for a
  race present in the station's workforce.
- A ware sitting in cargo with **no offer is loot and gets no allocation.**
  KPU-277 holds 63 teladianium, 18 hull parts, 4 graphene and 21 missile
  components with no offer against any of them; including them would have put
  `N` at 7 instead of the true 3 and broken the fit by a factor of 2.3.
- **Rations get the ration reserve and nothing else** — they are outside the
  split, exactly as in the producer model, and for the same reason (their
  "production share" is zero).
- **A station with no workforce has no ration reserve, and its ration wares
  become ordinary trade goods with a full share.** JJX-981 (Terran trade
  station, zero workforce) allocates terran MREs and medical supplies
  125,000 units each — the same 250,000 m³ every other ware gets.

### Pool groups, not pools

`module_cap.cargo_tags` is sometimes `"container liquid solid"` — one bay
serving all three transports. Five macros do this, including
`storage_arg_l_tradestation_01_macro`, both Teladi trade-station landmark
storages and `xenon_small_station_01_storage_01_macro`. When a station's
storage is tagged that way, **the three transport pools share one budget and
one head count**, and the division runs over the union.

GMJ-316 (Argon trade station, Ianamus Zura) is the clean demonstration:
1,200,000 m³, no workforce, 20 container wares plus one solid ware
(`nividium`). `1,200,000 / 21 = 57,142.9 m³` — and every one of its 21 wares,
across two transport pools, lands on it. Treating the pools separately
(1,200,000 each) gives 1,200,000/20 and 1,200,000/1 and is wrong twice.

Four Argon/Antigone/Hatikvah stations and four Teladi landmark trade stations
sit in this group; all eight fit only with the pools merged.

---

## 2. DHI-588, end to end

Built storage: 1 × `storage_par_l_container` (1,000,000) + 1 ×
`storage_par_m_container` + 3 × `storage_tel_m_container` (250,000 each) +
2 × `storage_tel_s_container` (50,000) = **2,100,000 m³ container**;
1 × `storage_par_m_liquid` + 1 × `storage_tel_m_liquid` (500,000 each) +
2 × `storage_tel_s_liquid` (100,000) = **1,200,000 m³ liquid**;
2 × `storage_par_m_solid` + 1 × `storage_tel_m_solid` (500,000 each) +
2 × `storage_tel_s_solid` (100,000) = **1,700,000 m³ solid**.
All single-tag, so three independent pools.

Workforce 179 Argon / 33 Paranid / 39 Teladi, giving four ration wares:
food rations + medical supplies (Argon), soja husk (Paranid), nostrop oil
(Teladi). Reserve read in game: 1,602 / 1,338 / 184 / 173 units
= 1,602 + 2,676 + 184 + 173 = **4,635 m³**, all container.

```
container:  (2,100,000 − 4,635) / 30 traded wares  =  69,845.5 m³ each
liquid:      1,200,000          /  3               = 400,000.0 m³ each
solid:       1,700,000          /  3               = 566,666.7 m³ each
```

| ware | vol | share ÷ vol | model | **read in game** |
|---|---:|---:|---:|---:|
| energy cells, missile components | 1 | 69,845.5 | 69,845 | **69,845** |
| smart chips | 2 | 34,922.75 | 34,922 | **34,922** |
| spices | 3 | 23,281.8 | 23,281 | **23,281** |
| wheat | 4 | 17,461.4 | 17,461 | **17,461** |
| soja beans, sunrise flowers | 5 | 13,969.1 | 13,969 | **13,969** |
| maja snails, meat, swamp plant, water | 6 | 11,640.9 | 11,640 | **11,640** |
| antimatter converters, shield comp. | 10 | 6,984.6 | 6,984 | **6,984** |
| hull parts | 12 | 5,820.5 | 5,820 | **5,820** |
| refined metals | 14 | 4,989.0 | 4,988 | **4,988** |
| engine parts, field coils | 15 | 4,656.4 | 4,656 | **4,656** |
| superfluid coolant | 16 | 4,365.3 | 4,365 | **4,365** |
| antimatter cells, silicon wafers | 18 | 3,880.3 | 3,880 | **3,880** |
| graphene, weapon components | 20 | 3,492.3 | 3,492 | **3,492** |
| microchips, quantum tubes | 22 | 3,174.8 | 3,174 | **3,174** |
| claytronics | 24 | 2,910.2 | 2,910 | **2,910** |
| adv. electronics, drone comp. | 30 | 2,328.2 | 2,328 | **2,328** |
| adv. composites, plasma conductors | 32 | 2,182.7 | 2,182 | **2,182** |
| scanning arrays | 38 | 1,838.0 | 1,838 | **1,838** |
| helium, hydrogen, methane | 6 (liquid) | 66,666.7 | 66,666 | **66,666** |
| ice | 8 (solid) | 70,833.3 | 70,833 | **70,833** |
| ore, silicon | 10 (solid) | 56,666.7 | 56,666 | **56,666** |

**36 traded wares, 36 exact** — the 35 the player enumerated plus water, which
the message's pairing note places at 11,640 alongside maja snails / meat /
swamp plant. With the four rations that is the station's complete 40-row
allocation table. The whole "striking structure" in the readings is one number
per pool divided by `ware.volume`.

### The truncation is a floor, not a rounding

Across the 561 trade-station pairs, `floor(share / volume)` is exact **537
times**, `round` 243, `ceil` 45. Scanning arrays is the decisive case at
DHI-588: `69,845.5 / 38 = 1,838.04`, and 1,838 is read — but advanced
composites is `2,182.67` and reads **2,182**, not 2,183. Same floor as the
production model's per-cycle truncation (E-038).

---

## 3. How it scores save-wide

Population: the 115 stations with at least one `source='proxy'` storage row and
no `source='computed'` row. Split by module content, because the station macro
lies — 52 of them wear `station_gen_factory_base_01_macro` and are actually
wharfs and equipment docks:

- **trade-kind** (no `buildmodule`): 49 stations, 65 pool groups, 561 pairs.
  Trade stations, pirate bases, Xenon/Teladi/Terran/Split/Boron trade posts.
- **build-kind** (≥1 `buildmodule`): 66 stations, 72 pool groups, 580 pairs.
  Wharfs, shipyards, equipment docks.

Ground truth is the saturated proxy `stock + inbound + open buy amount`, which
is a **lower bound** — under-shooting proves nothing, over-shooting kills the
rule.

| | trade-kind | build-kind |
|---|---:|---:|
| pairs exactly `floor(share/volume)` | **537 / 561 (95.7 %)** | 11 / 580 (1.9 %) |
| pairs **exceeding** the predicted share | **6 (1.1 %)** | 193 (33.3 %) |
| median CV of allocation-volume across a group's wares | **0.00004** | 0.80 |
| p90 CV | 0.0002 | 1.40 |
| median share of a group's wares sitting on the plateau | **100 %** | 20 % |

A CV of 0.00004 is not "approximately equal" — it is the same number to five
significant figures, with the residual coming from unit truncation.

### Where the trade-kind fit is not exact

24 of 561 pairs. All but six are **under** the prediction, i.e. the station has
not saturated its allocation, which the lower-bound rule permits:

| station | wares | ratio | reading |
|---|---|---:|---|
| VYB-172 (buccaneers) | spacefuel / spaceweed / majadust | 0.72–0.78 | not saturated; 151 Paranid workers, small base |
| FYX-977, UYA-515, MMU-256 (buccaneers) | same three | 0.976–0.993 | not saturated |
| VTG-911 (teladi) | advanced composites | 0.915 | single unsaturated ware |
| PGI-932 (paranid) | helium | 0.989 | single unsaturated ware |

The six that sit **above** the predicted share do so by 0.02 %–0.2 % (e.g.
LJS-520 drone components 1,908 against 1,904) and are attributable to the
ration-reserve term, which I take from the proxy and which is itself a lower
bound. No case anywhere approaches a structural over-run.

### Build stations: the rule is false there, with numbers

QJI-262 (Terran wharf, 5,000,000 m³ single container pool, 7 wares — equal
volume would give 714,286 m³ each):

| ware | vol | alloc | alloc × vol |
|---|---:|---:|---:|
| energy cells | 1 | 2,005,796 | 2,005,796 |
| computronic substrate | 50 | 32,654 | 1,632,700 |
| silicon carbide | 20 | 40,497 | 809,940 |
| metallic microlattice | 1 | 419,537 | 419,537 |
| medical supplies | 2 | 9,180 | 18,360 |
| terran MRE | 2 | 8,772 | 17,544 |
| khaak alloy | 20 | 489 | 9,780 |

A 205× spread. Build-station allocation is presumably driven by the build
bill-of-materials, as `station-storage-model.md` already assumes; nothing here
changes that, and the proxy remains the right treatment for them. **The single
most useful thing this report does for build stations is prove they are a
separate population**, so a future model of them can be scored on its own
without the trade stations flattering it.

---

## 4. The proxy's error profile

Scored over the 561 trade-station pairs against the rule's prediction:

| proxy definition | exact | within 1 % | median | mean | p10 |
|---|---:|---:|---:|---:|---:|
| `stock + buy` (what `analysis/storage.py` computes) | 82.9 % | 84.3 % | 1.0000 | 0.9740 | 0.921 |
| `stock + inbound + buy` | **97.3 %** | **98.0 %** | 1.0000 | 0.9982 | 1.000 |

The error is **entirely one-sided (under)**, exactly as the lower-bound rule
predicts: 96 of 561 pairs under-report, none over-report. Of those 96, the
median shortfall is 11.2 % and the worst is 74.8 %.

**84 of the 96 under-reporting pairs have an open inbound reservation**, and
adding it closes them. DHI-588's four known misses close to the unit:

| ware | proxy | + inbound | = | read in game |
|---|---:|---:|---:|---:|
| advanced composites | 1,214 | 968 | 2,182 | **2,182** |
| drone components | 1,795 | 533 | 2,328 | **2,328** |
| engine parts | 3,650 | 1,006 | 4,656 | **4,656** |
| graphene | 2,737 | 755 | 3,492 | **3,492** |
| water (also missed) | 10,390 | 1,250 | 11,640 | **11,640** |

The data is already in the database: `trade_pending`, `buyer_id` = the station,
term = `Σ (amount − transferred)`. `save-semantics.md` § *The offer-derived
allocation is a LOWER BOUND* names `stock + inbound + amount` as the right
quantity; `analysis/storage.py`'s docstring says `stock + open buy-offer
amount`. **That is a live inconsistency between the reference doc and the
code**, and the code is the one that is wrong. It also affects producer
stations, where the same quantity is the validation denominator — the 87.2 %
figures in the model doc were scored against the two-term version.

---

## 5. CONFIRMED vs HYPOTHESIS

**CONFIRMED.**

- Trade-station allocation is `floor(((pool_capacity − ration_reserve) / N) /
  ware.volume)` with `N` the traded-ware count. Every DHI-588 in-game reading
  exact (36 traded + 4 rations); 95.7 % of 561 save-wide pairs exact; zero
  over-runs in 561 pairs.
- Truncation is `floor`, not round (537 vs 243).
- Multi-transport storage modules pool their capacity and their head count
  across all the transports they are tagged for. 8 stations, exact.
- Wares held in cargo without a trade offer receive no allocation (KPU-277).
- A station with no workforce takes no ration reserve and treats ration wares
  as ordinary trade goods (JJX-981, UFH-627, EBT-957, JBE-269, QIL-939, CCW-202
  — six Terran/Pioneer trade stations, all exact).
- The proxy's shortfall against this rule is the missing inbound term.
- The rule does **not** describe wharfs / shipyards / equipment docks.

**HYPOTHESIS — not settled by save data.**

- **H1. The ration reserve on a trade station uses a workforce basis that can
  differ from the current workforce.** For 67 of 85 (station, ration) pairs the
  reserve is within 2 % of `floor(current_workforce × rate × 4 h)`. The
  exceptions are systematic and point one way:

  | station | workforce | observed reserve | reserve ÷ rate ÷ 4 h |
  |---|---:|---|---:|
  | PTW-627 (teladi) | 104 | medical 5,400 / nostrop 4,560 | 1,000 |
  | MRZ-989 (teladi) | 231 | medical 5,400 / nostrop 4,560 | 1,000 |
  | IWQ-591 (teladi) | 361 | medical 5,400 / nostrop 4,560 | 1,000 |
  | VTG-911 (teladi) | 702 | medical 5,400 / nostrop 4,560 | 1,000 |
  | DHI-588 (kaori) | 179 / 33 / 39 | 1,602 / 184 / 173 | 178 / 32 / 38 |

  All four Teladi landmark trade stations carry an **identical** reserve while
  their live workforces differ 7×, so the reserve is not a function of the
  current workforce there. A fixed 1,000-worker basis fits all four; their
  module housing is 6,000, so it is not module capacity either. DHI-588
  meanwhile sits one worker per race *below* current. Both observations fit
  "the allocation is recomputed lazily and the reserve is frozen at the
  workforce level of the last recompute" — the same lag hypothesised for
  EIJ-609 (E-051). **It is a hypothesis, not a finding.** Note the split itself
  is exact once the *observed* reserve is used, so reserve and split were
  computed at the same moment.
- **H2. `N` is the traded-ware count as the save states it.** I derive `N` from
  the save's own offer list, so on any station where the game's internal trade
  list differs from its posted offers, the rule would look right for the wrong
  reason. Every station where all wares saturate confirms `N` independently
  (the plateau count equals `N`), and that is 100 % of groups at the median —
  but a station that trades a ware it currently posts no offer for would break
  it, and I have no example either way.
- **H3. The `supplies`/`shady` exclusions carry over unchanged.** I inherited
  them from `analysis/storage.py`. They are consistent with every fit here
  (PTW-627 and JJX-981 both post `shady` books that must be excluded for the
  split to land), but this report did not re-test them.

**Explicitly not claimed.** That the share is stable across saves; that the
player's own trade stations follow it (this save has none — MXH-411 is
build-kind); that anything here applies to build stations.

---

## 6. In-game readings that would settle the open parts

Ranked by how much each one decides. Each names the station, the wares, and
what each possible answer means.

**1. PTW-627 — Teladi trade station, Ianamus Zura IV (`landmarks_tel_tradestation_01_macro`).**
*Settles H1, the ration-reserve basis.* Read **medical supplies** and
**nostrop oil**.
- 5,400 / 4,560 ⇒ the reserve is frozen at a 1,000-worker basis while the
  station runs 104 workers ⇒ lazy recompute (or a fixed capacity basis).
- 561 / 474 ⇒ the reserve tracks the live workforce and the *split* is being
  computed against something else — which would also break the 19-ware share
  and would be the single most damaging reading available.
While there, read **missile components** (predict 93,928), **hull parts**
(7,827) and **scanning arrays** (2,471) to confirm the merged
container+liquid+solid pool on a second faction.

**2. KPU-277 — buccaneer pirate base, Windfall III / cluster_43.**
*Settles the loot-exclusion rule.* Read **space fuel** (predict 41,252),
**space weed** (27,501), **maja dust** (13,750) — and then **teladianium**,
**hull parts**, **graphene**, **missile components**, which it physically holds
(63 / 18 / 4 / 21 units) but posts no offer for.
- The four loot wares show **no allocation row / no storage entry** ⇒ `N = 3`
  confirmed, ware set = offers.
- They show an allocation ⇒ `N = 7`, the share drops to 35,359 m³, and every
  number in this report is refit.

**3. GMJ-316 — Argon trade station, Ianamus Zura (`station_arg_tradestation_base_01_macro`).**
*Settles the pool-merge rule on a workforce-free station.* Read **food
rations** (predict 57,142), **nividium** (5,714 — the only solid ware) and
**scanning arrays** (1,503). If nividium reads 120,000 (= 1,200,000 / 10) the
pools are separate and the merge is wrong. JDV-447, LJS-520, ERG-523 and
EOX-322 are identical twins if a second point is wanted.

**4. JJX-981 or UFH-627 — Terran trade station (`station_ter_tradestation_base_01_macro`), zero workforce.**
*Settles "no workforce ⇒ rations are ordinary trade goods".* Read **terran
MREs** and **medical supplies** (predict 125,000 each), **metallic
microlattice** (250,000), **computronic substrate** (5,000).
- 125,000 ⇒ confirmed.
- Anything much smaller ⇒ ration wares are always reserved, and the reserve has
  a floor independent of workforce.

**5. VYB-172 — buccaneer pirate base, cluster_37.** *Settles the largest
remaining gap between proxy and rule.* Read **space fuel** (predict 40,829,
proxy says 31,803), **space weed** (27,219 vs 19,644), **maja dust** (13,609 vs
10,048). Confirms the lower-bound reading of the residual; a reading equal to
the proxy would mean `N` or the reserve is wrong on small pirate bases.

**6. QJI-262 — Terran wharf, or AKY-534 — Argon equipment dock.** *Not a test
of this rule; the input for the next one.* The full allocation table for a
build station is the only thing that would let anyone model build-kind storage,
which is 66 stations and 580 (station, ware) pairs of the current save with no
model at all.

**7. Any trade station, before and after its trade list changes.** The rule
predicts that adding one ware to an `N = 6` station shrinks *every other ware's
allocation by 1/7*. That is a strong, cheap falsifier if the player can watch a
station pick up or drop a ware — e.g. QIL-939 (Terran, `N = 5`, share 185,714).

---

## 7. What I recommend changing (for whoever holds the pen)

I am read-only on the repo; these are proposals, not edits.

1. **`analysis/storage.py`** — non-producers without a `buildmodule` should take
   the computed path: `floor(((cap − ration_volume) / N) / volume)` with the
   pool-group merge, `source='computed'`, instead of the proxy. Build stations
   keep the proxy.
2. **The proxy, wherever it survives**, should add the inbound term from
   `trade_pending` (`buyer_id = station`, `Σ amount − transferred`). This also
   corrects the validation denominator for *producing* stations.
3. **`station-storage-model.md` § Non-producing stations use a proxy** is now
   only right for build stations; § Pools' "a pool no recipe touches" rule
   should be generalised to state that it is the same rule the trade stations
   obey.
4. **`analysis/storage.py`'s `role='food'` marking is wrong on trade stations**
   — it flags a ware as food by identity, so RAN-388 (Boron) shows food rations
   at 104,808 units and DHI-588 shows water as food. The role should depend on
   whether the ware is a `workunit_busy` input for a race actually in the
   station's workforce.

---

## Proposed experiment-register entries

To be appended to `docs/experiments/README.md` § Storage allocation at the next
free ids (E-064 onward is the Parser block, so these belong at the end of the
Storage block with whatever ids are free at the time of writing — the ids below
are placeholders and must be renumbered by whoever applies them). The summary
table row for Storage allocation would move from 14/6/6/1 (27) by +4 CONFIRMED
and +1 PENDING.

> **E-0xx · CONFIRMED** — A non-producing, non-building station divides each
> storage pool into equal *volume* shares, one per traded ware, after the
> ration reserve.
> *Predicts:* `max = floor(((pool_capacity − Σ ration_volume) / N) /
> ware.volume)` where `N` counts wares with an open non-`shady`,
> non-`supplies` trade offer, excluding the workforce's ration wares.
> Reproduces DHI-588's complete 40-row in-game table to the unit (container
> share 69,845.5 m³ over 30 wares, liquid 400,000 over 3, solid 566,666.7 over
> 3); 537 of 561 (station, ware) pairs exact across 49 stations, and 0 of 561
> exceed the predicted share. Median CV of allocation-volume within a pool
> group 0.00004 against 0.80 for build stations. It is the same rule as the
> equal-hours split with zero throughput. *Source:*
> [trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md) § 1–3.

> **E-0xx · CONFIRMED** — The offer-derived proxy's shortfall against the true
> allocation is the omitted inbound-reservation term.
> *Predicts:* adding `Σ (trade_pending.amount − transferred)` for
> `buyer_id = station` lifts trade-station agreement from 82.9 % to 97.3 %
> exact and mean 0.9740 → 0.9982; it closes DHI-588's four known misses
> exactly (advanced composites 1,214 + 968 = 2,182; drone components
> 1,795 + 533 = 2,328; engine parts 3,650 + 1,006 = 4,656; graphene
> 2,737 + 755 = 3,492) plus water 10,390 + 1,250 = 11,640. 84 of the 96
> under-reporting pairs carry an inbound reservation. `save-semantics.md`
> already specifies `stock + inbound + amount`; `analysis/storage.py` computes
> `stock + amount`. *Source:*
> [trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md) § 4.

> **E-0xx · CONFIRMED** — A storage module tagged for several transports pools
> its capacity *and its ware head count* across all of them.
> *Predicts:* GMJ-316 (`storage_arg_l_tradestation_01_macro`, 1,200,000 m³, no
> workforce) puts all 21 wares — 20 container plus solid nividium — on
> 1,200,000/21 = 57,142.9 m³, and every one lands. Holds on 8 stations across
> Argon/Antigone/Hatikvah and the four Teladi landmark trade stations; treating
> the pools separately fails all 8. *Source:*
> [trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md) § 1.

> **E-0xx · CONFIRMED** — Wharfs, shipyards and equipment docks do not follow
> the equal-volume rule and are a separate population.
> *Predicts:* 11 of 580 pairs exact against 537 of 561 for trade stations;
> 33.3 % of build-station wares exceed the equal share; median CV 0.80 against
> 0.00004. QJI-262 spans 9,780 m³ (khaak alloy) to 2,005,796 m³ (energy cells)
> in one pool. Classify by built `buildmodule` presence, not by station macro —
> 52 build stations wear `station_gen_factory_base_01_macro`. *Source:*
> [trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md) § 3.

> **E-0xx · PENDING** — The ration reserve is frozen at the workforce level of
> the last allocation recompute, not the current workforce.
> *Predicts:* all four Teladi landmark trade stations (PTW-627, MRZ-989,
> IWQ-591, VTG-911) carry an identical reserve of 5,400 medical supplies /
> 4,560 nostrop oil — a 1,000-worker basis — while their live workforces are
> 104 / 231 / 361 / 702; DHI-588 reads one worker per race *below* current
> (178/32/38 against 179/33/39). Module housing on the Teladi stations is
> 6,000, so it is not a capacity basis. 67 of 85 (station, ration) pairs are
> within 2 % of the live-workforce formula. *Settles it:* read PTW-627's
> medical supplies and nostrop oil in game — 5,400/4,560 ⇒ frozen basis,
> 561/474 ⇒ live workforce and the split needs re-deriving. Same lag mechanism
> hypothesised for EIJ-609. *Source:*
> [trade-station-allocations-2026-07-29.md](../reports/trade-station-allocations-2026-07-29.md) § 5, H1.
