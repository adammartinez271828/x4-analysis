"""Station storage-allocation model.

Reverse-engineered (session 2026-07, validated against GDR-378, PEJ-489,
UBX-812 across Terran/Paranid and all three transport pools): a producing
station sizes each ware's storage to hold a fixed number of *hours* of that
ware's throughput, per transport pool (container / liquid / solid), at full
workforce.

  jobs           = Sum of modcap.workers over the station's built modules
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

Not modeled (v1) -- these station types get only their workforce-food rows (or
nothing), because their main storage is driven by mechanisms this module does
not read:
  * wharfs / shipyards / equipment docks -- consume ship/equipment build inputs
    (hull parts, electronics, scanning arrays, ...) via BUILD modules, not
    production recipes, so that storage is absent.
  * pure trade stations -- no production; their target comes from trade config.
  * the separate ammunition/defence pool (drone energy, missile components,
    smart chips) on stations with drone/ammo production (e.g. PEJ-489 energy).
  * multi-stage internally-cycled wares (produced AND consumed on-site) use
    gross production, not net flow.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ..gamedata.refdata import RefData
from .frames import Frames

FOOD_HOURS = 4.0
WORKUNIT = "workunit_busy"

_COLS = ["station_id", "ware", "transport", "role",
         "throughput", "max_units", "max_volume"]


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

    wares = ref.wares.set_index("id")
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
            if time > 0:
                output[sid][ware] += amount / time * 3600.0 * units * (1 + work)
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

    # allocate per station per transport pool
    rows: list[dict] = []
    for sid in stations:
        caps = pool_cap.get(sid)
        if not caps:
            continue
        # role + throughput per ware: food > output > input
        role: dict[str, str] = {}
        thru: dict[str, float] = {}
        for ware, amt in food[sid].items():
            role[ware], thru[ware] = "food", amt
        for ware, amt in output[sid].items():
            if ware not in role:
                role[ware], thru[ware] = "output", amt
        for ware, amt in consume[sid].items():
            if ware not in role:
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
                "max_volume": mx * vol,
            })

    return pd.DataFrame(rows, columns=_COLS)
