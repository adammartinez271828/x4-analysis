"""Station storage-allocation model.

Reverse-engineered (session 2026-07, validated against GDR-378, PEJ-489,
UBX-812 across Terran/Paranid and all three transport pools): a producing
station sizes each ware's storage to hold a fixed number of *hours* of that
ware's throughput, per transport pool (container / liquid / solid), at full
workforce.

  jobs           = Sum of module_cap.workers over the station's built modules
  output(ware)   = Sum (recipe.amount/time * 3600 * scale) * (1 + work_effect)
  input(ware)    = Sum (recipe.input_amount/time * 3600 * scale)   (no bonus)
  food(ware)     = per-race workunit_busy input * jobs             (fixed 4h)

Per transport pool, food wares get FOOD_HOURS of buffer and the remaining
capacity is divided across the production wares so each holds an equal number
of hours:

  T   = (pool_capacity - Sum food_volume) / Sum(throughput * ware.volume)
  max = throughput * T                    (food max = consumption * FOOD_HOURS)

Work_effect applies to output only; input consumption stays at base (verified:
GDR-378 energy consumption = base rate).

Non-producing stations (wharfs / shipyards / equipment docks / trade stations)
have no production recipes -- their storage is driven by ship/equipment
construction or arbitrage, not recipes. For these we use a PROXY: the allocated
max per ware ~= current stock + open buy-offer amount (source='proxy'), which we
verified is genuinely allocated storage (two same-faction Argon wharves matched
to Pearson r=0.9984 despite different fill). A full build bill-of-materials
model would be far costlier and not meaningfully more accurate. Producing
stations keep the exact throughput x T model (source='computed').

Supply offers (v18): buy offers whose save flags contain "supplies" are the
station's SELF-SUPPLY demand -- inputs for building its own drones/munitions,
delivered to the separate <supplies> inventory, not cargo storage (CONFIRMED
sweep-wide, docs/reports/supply-offer-discriminator.md). They are excluded
from the proxy's stock+buy max and emitted as separate role='supply' rows
(source='offer', max = outstanding need: desired when present, else amount)
for EVERY station, producing or not.

Shady offers (v26): buy offers flagged "shady" are the station's black-market
book, unlocked per station via its shadyguy post. They are a separate book as
well -- price-inelastic and backed by no stock -- so they are dropped from the
proxy entirely and get no storage row (docs/reports/fill-price-spread-*.md).

Still not modeled: multi-stage internally-cycled wares (gross vs net flow); a
combined production+build station keeps the computed path only (its build
inputs are omitted). Proxy caveats: excess stock over-states, and a pure trade
station's *sold*-ware max is only a floor (the proxy reads the buy side).
"""
from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

from ..gamedata.refdata import RefData
from .frames import Frames

FOOD_HOURS = 4.0
WORKUNIT = "workunit_busy"
# solar output scales with the SECTOR's sunlight multiplier (sectors.csv,
# from mapdefaults' area@sunlight). Only energy-cell production is solar;
# every other recipe runs at its rated speed wherever it sits. Player-
# verified 2026-07-27 on DLB-176 in Family Zhin (sunlight 0.71): the game
# produces 42,480 energy cells/h against a 42,000/h rated base, i.e.
# base x 0.71 x the workforce bonus - and with that rate the equal-hours
# split reproduces the in-game allocation (17,216 graphene, 348k energy
# cells) to 0.2%. Omitting it inflated solar throughput by 1/sunlight and
# skewed every multi-ware split on a station that makes energy cells.
SOLAR_WARE = "energycells"

_COLS = ["station_id", "ware", "transport", "role",
         "throughput", "max_units", "max_volume", "source"]


def _num(series, fill=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(fill)


def station_storage(frames: Frames, ref: RefData) -> pd.DataFrame:
    """Per (station id, ware): the max storage the game allocates, with the
    throughput driving it and its transport pool / role."""
    mods = frames.built_modules
    if (mods is None or mods.empty or ref.modules.empty
            or ref.recipes.empty or ref.modcaps.empty):
        return pd.DataFrame(columns=_COLS)

    uni = frames.universe.set_index("id")
    stations = set(uni.index[uni["class"] == "station"])
    # station -> sector sunlight. Defensive by convention: reference data
    # predating the sectors.csv sunlight column, or a hand-built frame
    # without sector ancestry, simply means no scaling (1.0).
    sec_ref = getattr(ref, "sectors", None)
    sun_by_sector = {}
    if sec_ref is not None and "sunlight" in getattr(sec_ref, "columns", []):
        sun_by_sector = dict(zip(sec_ref["macro"],
                                 _num(sec_ref["sunlight"], 1.0)))
    sunlight = ({sid: float(sun_by_sector.get(mac, 1.0) or 1.0)
                 for sid, mac in uni["sector.macro"].items()}
                if sun_by_sector and "sector.macro" in uni.columns else {})

    wares = ref.wares.set_index("id")
    # only TRADEABLE (economy-tagged) wares are stocked. The exceptions are
    # the processor feedstocks rawscrap / rawkhaakscrap (tags "processed
    # recycling solid"): scrapers deliver them straight into the processing
    # module, so the station never holds any — player-confirmed, and every
    # one of the 16 stations carrying such an input holds exactly 0. Giving
    # them a share of the solid pool halved what scrap metal should get
    # (CGW-678: 15,000 modelled vs 30,000 in-game, the full 300,000 m³ pool
    # at 10 m³/unit).
    economy_ware = {w: ("economy" in str(t)) for w, t in
                    zip(ref.wares["id"], ref.wares.get("tags", ""))}
    transport = wares["transport"].to_dict()
    volume = _num(wares["volume"], 1.0).replace(0, 1.0).to_dict()

    # recipe lookup: (ware, method) -> (time, amount, work_effect, [(inw, ina)])
    # work_effect is absent from recipes.csv extracted before v8 (and blank for
    # recipes without a workforce bonus) -> coerce to 0 rather than crash.
    rec = ref.recipes.copy()
    if "work_effect" not in rec.columns:
        rec["work_effect"] = 0.0
    rec["work_effect"] = _num(rec["work_effect"])
    recipes: dict[tuple[str, str], tuple] = {}
    for (ware, method), grp in rec.groupby(["ware", "method"]):
        first = grp.iloc[0]
        inputs = [(r.input_ware, float(r.input_amount))
                  for r in grp.itertuples()
                  if isinstance(r.input_ware, str) and r.input_ware]
        recipes[(ware, method)] = (
            float(first["time"]), float(first["amount"]),
            float(first["work_effect"]), inputs)
    methods = set(recipes)
    # wares any race's workforce eats (inputs of the workunit_busy recipes) --
    # they get the fixed 4h food buffer on the proxy path too.
    food_wares = {inw for (w, _m), (_t, _a, _e, ins) in recipes.items()
                  if w == WORKUNIT for inw, _ in ins}

    # module_ref: macro -> [(ware, method, scale, weight)]; weight splits a
    # multi-queue module (one recipe at a time) evenly across its options.
    mref = ref.modules[ref.modules["ware"].astype(str) != ""].copy()
    mref["scale"] = _num(mref["scale"], 1.0)
    counts = mref.groupby("macro")["macro"].transform("count")
    mref["weight"] = 1.0 / counts
    modrows: dict[str, list] = defaultdict(list)
    for r in mref.itertuples():
        modrows[r.macro].append((r.ware, r.method, r.scale, r.weight))

    # (station, module macro, ware) -> the engine's own production multiplier.
    #
    # CONFIRMED 2026-07-28. Each production module carries
    # `<production><efficiency product=>`, and that single number IS the whole
    # multiplier on the recipe amount: workforce bonus, sector sunlight and any
    # mod effect folded together (this playthrough's Faction Fix Pack adds a
    # per-faction war-pressure term, seen on ARG/ANT at differing percentages —
    # no static game-file model can reproduce that). EIJ-609 reads
    # `product="1.12634"`: floor(294 x 1.12634) = 331 per 900 s cycle x 3
    # modules = 3,972/h, exactly the in-game figure, against 4,824/h from the
    # reconstructed work_effect.
    #
    # Scored against the offer-derived allocations (allocation = stock +
    # inbound + open buy amount, exact) over 4,914 (station, ware) pairs:
    #
    #   basis                                   median |err|   within 1%
    #   this (efficiency, outputs only)             0.0000       87.2%
    #   reconstructed work_effect x sunlight        0.0001       76.7%
    #   no multiplier at all                        0.0036       50.9%
    #   efficiency on outputs AND inputs            0.0103       49.9%
    #
    # So the model's SHAPE was right — outputs are boosted, inputs are not —
    # only the multiplier was reconstructed instead of read. Sunlight is
    # already inside `efficiency`, so it must NOT be applied again here.
    #
    # A module with NO `<production>` block at all is running the bare recipe:
    # its multiplier is 1.0, not the reconstructed work_effect. CONFIRMED on
    # KRV-460, whose single turret-components module reports no block — all
    # four of its inputs come in at exactly 0.724 of the offer-derived truth,
    # and 1/0.724 recovers the 1.53 work_effect the fallback was wrongly
    # applying (its true output rate is the base 340/h). 939 (station, macro)
    # pairs are in this state; treating them as 1.0 lifts them from 43.6% to
    # 73.8% within 1%, and the whole computed population from 82.9% to 86.3%.
    #
    # The reconstruction survives only when the save carried no production
    # data at all (a pre-v27 database, or a hand-built frame) — there, a
    # missing row means "unknown", not "idle".
    prod_eff: dict[tuple[str, str, str], float] = {}
    mp = getattr(frames, "module_production", None)
    have_production = mp is not None and not mp.empty
    if have_production:
        for r in mp.itertuples():
            eff = getattr(r, "efficiency", None)
            if eff is None or pd.isna(eff) or float(eff) <= 0:
                continue
            prod_eff[(r.id, str(r.macro), str(r.ware))] = float(eff)

    mc = ref.modcaps.set_index("macro")
    workers = _num(mc["workers"]).to_dict()
    cargo_max = _num(mc["cargo_max"]).to_dict()
    cargo_tags = mc["cargo_tags"].fillna("").to_dict()

    # per station accumulators
    jobs: dict[str, float] = defaultdict(float)
    pool_cap: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    output: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    consume: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for m in mods.itertuples():
        sid, macro = m.id, m.macro
        if sid not in stations:
            continue
        jobs[sid] += workers.get(macro, 0.0)
        cap, tags = cargo_max.get(macro, 0.0), cargo_tags.get(macro, "")
        if cap:
            for t in ("container", "liquid", "solid"):
                if t in tags:
                    pool_cap[sid][t] += cap
        for ware, method, scale, weight in modrows.get(macro, ()):
            key = (ware, method) if (ware, method) in methods else (ware, "default")
            recipe = recipes.get(key)
            if not recipe:
                continue
            time, amount, work, inputs = recipe
            units = scale * weight
            # The save's own multiplier when the module reports one; otherwise
            # fall back to reconstructing it (workforce bonus x sunlight), which
            # is all we have for an idle module or a hand-built frame.
            eff = prod_eff.get((sid, macro, ware))
            if eff is None:
                if have_production:
                    eff = 1.0          # no <production> block: bare recipe
                else:
                    solar = (sunlight.get(sid, 1.0)
                             if ware == SOLAR_WARE else 1.0)
                    eff = (1 + work) * solar
            # A module produces whole units per CYCLE, not fractions per
            # hour: the multiplier scales the cycle's amount and the engine
            # TRUNCATES it (player-verified 7/7 — 97.92 -> 97 microchips,
            # 195.91 -> 195 smart chips, 141.55 -> 141 coolant, so floor and
            # not rounding, and EIJ-609's 294 x 1.12634 -> 331). Doing the
            # multiply at the hourly level instead leaves fractional units
            # and always reads high, by a per-ware amount that depends on
            # where the fraction falls (0.01%-0.9% here) — which perturbs
            # the RATIOS the pool split is computed from, not just the
            # absolute rates.
            per_cycle = math.floor(amount * eff)
            if time > 0:
                output[sid][ware] += per_cycle / time * 3600.0 * units
                # PROCESSING modules (scrap works) are outside the storage
                # model: their feedstock arrives from space and their inputs
                # get no buffer. Player-confirmed on KWC-232 — counting the
                # scrap works' 90,000 energy cells/h alongside the recyclers'
                # 372,000 misses the in-game allocation by 5% on energy cells
                # and 15% on hull parts; excluding it lands within 0.6% on
                # all three wares. Their OUTPUT (scrap metal) is stored
                # normally.
                if key[1] != "processing":
                    for inw, ina in inputs:
                        consume[sid][inw] += ina / time * 3600.0 * units

    # workforce food: full-workforce (jobs) consumption of the race ration,
    # split by the present-workforce race mix (single race -> all of jobs).
    food: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wf = frames.workforce_all
    if wf is not None and not wf.empty:
        totals = wf.groupby("id")["amount"].sum().to_dict()
        for w in wf.itertuples():
            sid = w.id
            if sid not in stations or jobs.get(sid, 0) <= 0:
                continue
            total = totals.get(sid, 0) or 0
            frac = (w.amount / total) if total else 0.0
            method = w.race if (WORKUNIT, w.race) in methods else "default"
            recipe = recipes.get((WORKUNIT, method))
            if not recipe:
                continue
            wtime, wamount, _work, winputs = recipe
            if wamount <= 0 or wtime <= 0:
                continue
            for inw, ina in winputs:
                food[sid][inw] += (ina / wamount / wtime * 3600.0
                                   * jobs[sid] * frac)

    # producers = stations with a real production module (macro known to
    # ref.modules) AND no build module. Only these get the throughput x T
    # model; wharfs / shipyards / equipment docks / trade stations build or
    # trade instead and use the proxy below.
    #
    # The build-module exclusion matters for HYBRIDS — a yard that also runs
    # production modules (3 in save_009: ULG-519 and the player's MXH-411,
    # plus one with no storage rows). They used to qualify as producers on
    # "has any production module", but their real buffers also feed the build
    # module, which the throughput model cannot see: ULG-519 modelled 45,044
    # hull parts against 61,494 actually held. The proxy (stock + open buy
    # offers) is what the yard path is for.
    yards = set(mods[mods["macro"].astype(str)
                     .str.startswith("buildmodule")]["id"])
    producers = (set(mods[mods["macro"].isin(set(modrows))]["id"])
                 & stations) - yards

    # allocate per producing station per transport pool
    rows: list[dict] = []
    for sid in producers:
        caps = pool_cap.get(sid)
        if not caps:
            continue
        # The workforce food buffer and the production share are ADDITIVE,
        # not exclusive. CONFIRMED on JFV-172 (Tharka's Ravine XVI), which
        # PRODUCES cheltmeat and also feeds it to its own workers: the game
        # reserves the 4 h ration buffer off the top for every ration — the
        # ones it makes included — and then hands the producer a normal
        # share of what is left, so cheltmeat gets 12,757 + 306 = 13,063
        # against 13,062 read in-game, and spices lands on 20,051 exactly.
        # Treating the roles as exclusive (food winning) cost cheltmeat its
        # entire production claim and handed the surplus to spices: 37,192
        # modelled against 20,051.
        food_rate: dict[str, float] = dict(food[sid])
        food_units = {w: amt * FOOD_HOURS for w, amt in food_rate.items()}
        # a ware the station both makes and uses is sized by whichever flow
        # is LARGER — the buffer has to cover the bigger of the two. CONFIRMED
        # on KWC-232 (Avarice IV), which makes 208,708 energy cells/h and
        # feeds 372,000/h to its recyclers: the game allocates on the
        # consumption side (in-game 1,833,000 vs 1,832,362 predicted, with
        # hull parts and claytronics landing at the same 4.93 h). DLB-176
        # keeps its verified allocation because there production (42,643/h)
        # dwarfs consumption (2,100/h).
        role: dict[str, str] = {}
        thru: dict[str, float] = {}
        for ware, amt in output[sid].items():
            role[ware], thru[ware] = "output", amt
        for ware, amt in consume[sid].items():
            # non-economy feedstock (raw scrap) is never stocked -> no share
            if not economy_ware.get(ware, True):
                continue
            if ware not in role or amt > thru[ware]:
                role[ware], thru[ware] = "input", amt

        # the ration buffer comes off the pool first, for every ration
        food_vol: dict[str, float] = defaultdict(float)
        for ware, units in food_units.items():
            food_vol[transport.get(ware, "")] += units * volume.get(ware, 1.0)
        prod_sigma: dict[str, float] = defaultdict(float)
        for ware in role:
            prod_sigma[transport.get(ware, "")] += (
                thru[ware] * volume.get(ware, 1.0))

        for ware in set(role) | set(food_units):
            t = transport.get(ware, "")
            vol = volume.get(ware, 1.0)
            buffer_units = food_units.get(ware, 0.0)
            share = 0.0
            if ware in role:
                remaining = caps.get(t, 0.0) - food_vol.get(t, 0.0)
                sigma = prod_sigma.get(t, 0.0)
                share = thru[ware] * remaining / sigma if sigma > 0 else 0.0
            mx = share + buffer_units
            r = role.get(ware, "food")
            rows.append({
                "station_id": sid, "ware": ware, "transport": t, "role": r,
                "throughput": thru.get(ware, food_rate.get(ware, 0.0)),
                "max_units": mx, "max_volume": mx * vol,
                "source": "computed",
            })

    # proxy path: non-producing stations (wharfs / shipyards / docks / trade).
    # The game's allocated max per ware is well-approximated by what the station
    # holds plus what it still bids to buy (proven ~allocated: two same-faction
    # wharves match to r=0.9984). throughput is unknown here -> left NULL.
    cargo = frames.station_cargo
    offers = frames.trade_offers
    stock: dict[str, dict[str, float]] = defaultdict(dict)
    if cargo is not None and not cargo.empty:
        for c in cargo.itertuples():
            if c.id not in producers and c.id in stations:
                stock[c.id][c.ware] = stock[c.id].get(c.ware, 0.0) + c.amount
    # supplies-flagged buys are self-supply (drone/munition build) demand:
    # never part of the cargo-storage proxy, collected for every station.
    # shady-flagged buys are the station's BLACK-MARKET book, unlocked per
    # station by its shadyguy (823 shadyguy posts <-> exactly the 823 stations
    # posting shady offers in save_009). It is a separate book too: the offers
    # are price-inelastic (~1.06x band max, no dependence on what the station
    # holds) and the station stocks none of the ware. Letting them into the
    # proxy minted 546 phantom (station, ware) allocations across 143
    # non-producing stations -- every one of them 100% shady-sourced, all four
    # of them illegal wares (stimulants / spacefuel / spaceweed / majadust).
    # Unlike supplies they get no row at all: nothing is allocated for them.
    has_flags = offers is not None and not offers.empty \
        and "flags" in offers.columns
    buy: dict[str, dict[str, float]] = defaultdict(dict)
    supply: dict[str, dict[str, float]] = defaultdict(dict)
    if offers is not None and not offers.empty:
        for o in offers.itertuples():
            if o.side != "buy" or o.id not in stations:
                continue
            if has_flags and isinstance(o.flags, str) and "shady" in o.flags:
                continue
            if has_flags and isinstance(o.flags, str) \
                    and "supplies" in o.flags:
                need = o.desired if getattr(o, "desired", None) is not None \
                    and pd.notna(o.desired) else o.amount
                supply[o.id][o.ware] = supply[o.id].get(o.ware, 0.0) + need
            elif o.id not in producers:
                buy[o.id][o.ware] = buy[o.id].get(o.ware, 0.0) + o.amount
    for sid in set(stock) | set(buy):
        for ware in set(stock.get(sid, {})) | set(buy.get(sid, {})):
            mx = stock.get(sid, {}).get(ware, 0.0) + buy.get(sid, {}).get(ware, 0.0)
            rows.append({
                "station_id": sid, "ware": ware,
                "transport": transport.get(ware, ""),
                "role": "food" if ware in food_wares else "input",
                "throughput": None, "max_units": mx,
                "max_volume": mx * volume.get(ware, 1.0), "source": "proxy",
            })

    # supply rows: open self-supply demand, read straight off the flagged
    # offers -- outstanding drone/munition build inputs, not storage
    for sid, wares_ in supply.items():
        for ware, need in wares_.items():
            rows.append({
                "station_id": sid, "ware": ware,
                "transport": transport.get(ware, ""), "role": "supply",
                "throughput": None, "max_units": need,
                "max_volume": need * volume.get(ware, 1.0),
                "source": "offer",
            })

    return pd.DataFrame(rows, columns=_COLS)
