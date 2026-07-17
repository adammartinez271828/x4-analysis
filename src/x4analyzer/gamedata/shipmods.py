"""Ship / hull-mod extraction, the fourth equipmentmods section after
weapons, engines and shields. The <ship> section is the most heterogeneous:
~11 stat families across durability, mobility, sensors, stealth, loadout and
hazard resistance, so there is no single physics model - each mod is a direct
multiplier (or, for radarcloak, an additive signature reduction) on its stat.

Stat kinds and directions:
  maxhull, radarrange            -> MULTIPLIER, higher better (neutral 1)
  mass, drag                     -> MULTIPLIER, lower better  (neutral 1)
  radarcloak                     -> ADDITIVE signature reduction, more
                                    negative better (neutral 0)
  regiondamage                   -> ADDITIVE hazard-damage REDUCTION fraction,
                                    higher better (neutral 0; 1.0 = 100%
                                    reduction/immunity, -1.0 = double damage)
  *capacity                      -> ADDITIVE FLAT count (+N consumables, base
                                    ~8 on S ships to ~20 on L), higher better
  hidecargochance                -> ADDITIVE chance, higher better (neutral 0)
"""

from __future__ import annotations

import re

from lxml import etree

from .catalog import GameFiles
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)
_MOD_WARE = re.compile(r"^mod_ship_")

# multiplier stats where lower is better
LOWER_BETTER = {"mass", "drag"}
# additive stats (neutral 0, realized values SUM not multiply)
ADDITIVE = {"radarcloak", "hidecargochance", "regiondamage",
            "countermeasurecapacity", "deployablecapacity", "missilecapacity",
            "unitcapacity"}
# stats whose OPTIMAL roll is the low end (lower/more-negative is better)
OPTIMAL_MIN = LOWER_BETTER | {"radarcloak"}


def _f(el, attr, default=None):
    if el is None:
        return default
    v = el.get(attr)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def extract_ship_mods(gf: GameFiles, tdb: TextDB | None = None) -> list[dict]:
    """<ship>-section entries of libraries/equipmentmods.xml (base + diff
    patches). Same shape/rules as the other extract_*_mods."""
    names = _mod_ware_names(gf, tdb)
    mods: dict[str, dict] = {}
    paths = ["libraries/equipmentmods.xml"] + [
        f"extensions/{ext}/libraries/equipmentmods.xml" for ext in gf.extensions]
    for path in paths:
        if path not in gf:
            continue
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for el in root.iter(etree.Element):
            ware = el.get("ware") or ""
            if not _MOD_WARE.match(ware) or el.get("quality") is None:
                continue
            bonus = el.find("bonus")
            bonuses = []
            chance = _f(bonus, "chance", 0.0)
            bmax = int(_f(bonus, "max", 0) or 0)
            if bonus is not None:
                for b in bonus:
                    bonuses.append({"stat": b.tag, "min": _f(b, "min", 1.0),
                                    "max": _f(b, "max", 1.0),
                                    "weight": _f(b, "weight", 1.0)})
            forced = bool(bonuses) and chance >= 1.0 and len(bonuses) <= bmax
            mods[ware] = {
                "ware": ware, "name": names.get(ware, ware), "stat": el.tag,
                "quality": int(_f(el, "quality", 1) or 1),
                "min": _f(el, "min", 1.0), "max": _f(el, "max", 1.0),
                "bonus_chance": chance, "bonus_max": bmax,
                "forced": forced, "bonuses": bonuses,
            }
    return sorted(mods.values(), key=lambda m: (m["quality"], m["stat"], m["ware"]))


def _mod_ware_names(gf: GameFiles, tdb: TextDB | None) -> dict[str, str]:
    names: dict[str, str] = {}
    if tdb is None:
        return names
    paths = ["libraries/wares.xml"] + [
        f"extensions/{ext}/libraries/wares.xml" for ext in gf.extensions]
    for path in paths:
        if path not in gf:
            continue
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for w in root.iter("ware"):
            wid = w.get("id", "")
            if not wid.startswith("mod_ship_"):
                continue
            short = tdb.resolve(w.get("shortname", "")).strip()
            if not short:
                short = tdb.resolve(w.get("name", "")).split(" (")[0].strip()
            names[wid] = short or wid
    return names


def _pick(stat: str, lo: float, hi: float, roll: str) -> float:
    if roll == "min":
        return lo
    if roll == "max":
        return hi
    return lo if stat in OPTIMAL_MIN else hi     # optimal


def realized_mults(mod: dict, roll: str = "optimal") -> dict[str, float]:
    """stat -> realized value (primary + forced bonuses). Multipliers for most
    stats; radarcloak is an additive reduction (compounds by sum, not product)."""
    out = {mod["stat"]: _pick(mod["stat"], mod["min"], mod["max"], roll)}
    if mod["forced"]:
        for b in mod["bonuses"]:
            v = _pick(b["stat"], b["min"], b["max"], roll)
            if b["stat"] in ADDITIVE:
                out[b["stat"]] = out.get(b["stat"], 0.0) + v
            else:
                out[b["stat"]] = out.get(b["stat"], 1.0) * v
    return out


def goodness(stat: str, value: float) -> float:
    """A monotonic 'higher = better' scalar for a stat's realized value, so
    mods can be Pareto-compared."""
    if stat == "radarcloak":
        return -value                      # -0.5 signature -> 0.5 goodness
    if stat in ADDITIVE:
        return value                       # capacities / hidecargo: more = better
    if stat in LOWER_BETTER:
        return 1.0 / value if value else 1e9  # regiondamage 0 = total immunity
    return value


def goodness_vector(mod: dict, stats: list[str]) -> dict[str, float]:
    """goodness per stat in `stats` for a mod (neutral = 1.0 mult / 0.0 add)."""
    mults = realized_mults(mod, "optimal")
    out = {}
    for s in stats:
        default = 0.0 if s in ADDITIVE else 1.0
        out[s] = goodness(s, mults.get(s, default))
    return out
