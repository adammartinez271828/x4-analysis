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

Still not modeled: multi-stage internally-cycled wares (gross vs net flow); a
combined production+build station keeps the computed path only (its build
inputs are omitted). Proxy caveats: excess stock over-states, and a pure trade
station's *sold*-ware max is only a floor (the proxy reads the buy side).
"""
from __future__ import annotations

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
            # solar plants run at sector sunlight; nothing else does
            solar = sunlight.get(sid, 1.0) if ware == SOLAR_WARE else 1.0
            if time > 0:
                output[sid][ware] += (amount / time * 3600.0 * units
                                      * (1 + work) * solar)
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
    # ref.modules). Only these get the throughput x T model; wharfs / shipyards
    # / docks / trade stations build or trade instead and use the proxy below.
    producers = set(mods[mods["macro"].isin(set(modrows))]["id"]) & stations

    # allocate per producing station per transport pool
    rows: list[dict] = []
    for sid in producers:
        caps = pool_cap.get(sid)
        if not caps:
            continue
        # role + throughput per ware: food > output > input
        role: dict[str, str] = {}
        thru: dict[str, float] = {}
        for ware, amt in food[sid].items():
            role[ware], thru[ware] = "food", amt
        # a ware the station both makes and uses is sized by whichever flow
        # is LARGER — the buffer has to cover the bigger of the two. CONFIRMED
        # on KWC-232 (Avarice IV), which makes 208,708 energy cells/h and
        # feeds 372,000/h to its recyclers: the game allocates on the
        # consumption side (in-game 1,833,000 vs 1,832,362 predicted, with
        # hull parts and claytronics landing at the same 4.93 h). DLB-176
        # keeps its verified allocation because there production (42,643/h)
        # dwarfs consumption (2,100/h).
        for ware, amt in output[sid].items():
            if ware not in role:
                role[ware], thru[ware] = "output", amt
        for ware, amt in consume[sid].items():
            # non-economy feedstock (raw scrap) is never stocked -> no share
            if not economy_ware.get(ware, True):
                continue
            if ware not in role or amt > thru[ware]:
                role[ware], thru[ware] = "input", amt

        # food volume per pool, then split the remainder across production wares
        food_vol: dict[str, float] = defaultdict(float)
        for ware, r in role.items():
            if r == "food":
                food_vol[transport.get(ware, "")] += (
                    thru[ware] * FOOD_HOURS * volume.get(ware, 1.0))
        prod_sigma: dict[str, float] = defaultdict(float)
        for ware, r in role.items():
            if r != "food":
                prod_sigma[transport.get(ware, "")] += (
                    thru[ware] * volume.get(ware, 1.0))

        for ware, r in role.items():
            t = transport.get(ware, "")
            vol = volume.get(ware, 1.0)
            if r == "food":
                mx = thru[ware] * FOOD_HOURS
            else:
                remaining = caps.get(t, 0.0) - food_vol.get(t, 0.0)
                sigma = prod_sigma.get(t, 0.0)
                mx = thru[ware] * remaining / sigma if sigma > 0 else 0.0
            rows.append({
                "station_id": sid, "ware": ware, "transport": t, "role": r,
                "throughput": thru[ware], "max_units": mx,
                "max_volume": mx * vol, "source": "computed",
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
    # never part of the cargo-storage proxy, collected for every station
    has_flags = offers is not None and not offers.empty \
        and "flags" in offers.columns
    buy: dict[str, dict[str, float]] = defaultdict(dict)
    supply: dict[str, dict[str, float]] = defaultdict(dict)
    if offers is not None and not offers.empty:
        for o in offers.itertuples():
            if o.side != "buy" or o.id not in stations:
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
