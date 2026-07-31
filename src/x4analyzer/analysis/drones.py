"""Station munition & drone census.

A station's own ``<ammunition><available>`` block (parser -> ``save.ammunition``)
holds everything the station keeps ready to launch or deploy: its drones
(defence / repair / transport-cargo / build / mining), police craft, turret
munitions (missiles, countermeasures) and deployables (satellites, mines,
resource probes). We capture ALL of it, tagged with a ``category`` and an
``is_unit`` flag.

DRONES + POLICE are the ``is_unit`` rows: they share ONE pool -- the engine
property ``units.maxcount`` -- with no per-type sub-cap (verified in-game; any
mix counts against the single number, per the engine's lib.ammo.drones.xml
unitcategories transport/repair/build/defence/mining + police). Missiles,
countermeasures and deployables are separate inventories, captured here for
reference but never counted toward the drone pool.

CAPACITY: the pool's hard cap (``units.maxcount``) is readable -- dock / pier /
build / **defence** modules declare ``<storage unit="N">`` (modcaps.unit_storage;
defence discs/tubes = 15 each), and each built production module adds a flat 10
that appears in no module field. ``capacity`` = Sum module_cap.unit_storage +
10 x built production modules, validated in-game on two production-heavy NPC
stations to the unit (E-062, 2026-07-31: EWQ-469 273 + 23x10 = 503, DIS-888
141 + 22x10 = 361) on top of the floor-only validations (ABR-398 40, EBT-957
92, QJI-262 220). ``capacity_floor`` (the unit-storage sum alone) is kept as
the conservative persisted value. The build TARGET is persisted per product
ware in ``<supplies><orders>`` (E-063; parser ``station_supplies``); what is
not persisted is any per-category *desired* inside the ammunition block itself.
"""
from __future__ import annotations

import pandas as pd

from ..gamedata.refdata import RefData

_COLS = ["station_id", "macro", "category", "is_unit", "count",
         "capacity_floor", "capacity"]

# each built production module adds a flat 10 to units.maxcount (E-062)
_PRODUCTION_UNITS = 10.0

# macro fragment -> (category, is_unit). Order matters (first match wins).
# is_unit rows count toward the shared drone pool (units.maxcount); the rest are
# turret munitions / deployables kept in their own inventories.
_CATEGORY: tuple[tuple[str, str, int], ...] = (
    ("fightingdrone", "defence", 1),
    ("repairdrone", "repair", 1),
    ("cargodrone", "transport", 1),
    ("buildingdrone", "build", 1),
    ("builddrone", "build", 1),
    ("miningdrone", "mining", 1),
    ("_police_", "police", 1),
    ("countermeasure", "countermeasure", 0),
    ("missile", "missile", 0),
    ("satellite", "deployable", 0),
    ("resourceprobe", "deployable", 0),
    ("_mine_", "deployable", 0),
    ("lasertower", "deployable", 0),
    ("navbeacon", "deployable", 0),
)


def _classify(macro: str) -> tuple[str, int]:
    for frag, cat, unit in _CATEGORY:
        if frag in macro:
            return cat, unit
    return "other", 0


def station_munition(save, frames, ref: RefData) -> pd.DataFrame:
    """Per (station id, macro): count of every item in the station's own
    ammunition, with a category, an is_unit flag (counts toward the drone
    pool), and the station's readable drone-capacity floor."""
    items = getattr(save, "ammunition", None) or []
    if not items:
        return pd.DataFrame(columns=_COLS)

    # capacity floor per station: Sum module_cap.unit_storage over built modules;
    # full capacity adds a flat 10 per built production module (E-062).
    floor: dict[str, float] = {}
    prod_units: dict[str, float] = {}
    mc = ref.modcaps
    mods = frames.built_modules
    if (mc is not None and not mc.empty and "unit_storage" in mc.columns
            and mods is not None and not mods.empty):
        unit = (pd.to_numeric(mc.set_index("macro")["unit_storage"],
                              errors="coerce").fillna(0.0).to_dict())
        is_prod = (mc.set_index("macro")["class"] == "production").to_dict() \
            if "class" in mc.columns else {}
        for m in mods.itertuples():
            u = unit.get(m.macro, 0.0)
            if u:
                floor[m.id] = floor.get(m.id, 0.0) + u
            if is_prod.get(m.macro, False):
                prod_units[m.id] = prod_units.get(m.id, 0.0) + _PRODUCTION_UNITS

    counts: dict[tuple[str, str], float] = {}
    for sid, macro, amount in items:
        try:
            n = float(amount)
        except (TypeError, ValueError):
            continue
        counts[(sid, macro)] = counts.get((sid, macro), 0.0) + n

    rows = []
    for (sid, macro), n in counts.items():
        cat, is_unit = _classify(macro)
        rows.append({
            "station_id": sid, "macro": macro, "category": cat,
            "is_unit": is_unit, "count": n,
            "capacity_floor": floor.get(sid, 0.0),
            "capacity": floor.get(sid, 0.0) + prod_units.get(sid, 0.0),
        })
    return pd.DataFrame(rows, columns=_COLS)
