"""Ship / hull-mod extraction, the fourth equipmentmods section after
weapons, engines and shields. The <ship> section is the most heterogeneous:
~11 stat families across durability, mobility, sensors, stealth, loadout and
hazard resistance, so there is no single physics model - each mod is a direct
multiplier (or, for radarcloak, an additive signature reduction) on its stat.

Stat directions (whether higher is better):
  maxhull, radarrange, *capacity, hidecargochance   -> higher better
  mass, drag, regiondamage                          -> lower better
  radarcloak                                        -> additive, MORE NEGATIVE
                                                       (bigger reduction) better
"""

from __future__ import annotations

import re

from lxml import etree

from .catalog import GameFiles
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)
_MOD_WARE = re.compile(r"^mod_ship_")

# higher-is-better by default; these are the exceptions (lower is better)
LOWER_BETTER = {"mass", "drag", "regiondamage"}
# additive signature reduction (default 0, more negative = stealthier)
ADDITIVE = {"radarcloak"}


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
    # optimal: additive & lower-better want the MIN, higher-better wants MAX
    if stat in ADDITIVE or stat in LOWER_BETTER:
        return lo
    return hi


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
    mods can be Pareto-compared. Multiplier stats: value or 1/value; radarcloak
    (additive, default 0): the size of the reduction."""
    if stat in ADDITIVE:
        return -value                      # -0.5 signature -> 0.5 goodness
    if stat in LOWER_BETTER:
        return 1.0 / value if value else 1.0
    return value


def goodness_vector(mod: dict, stats: list[str]) -> dict[str, float]:
    """goodness per stat in `stats` for a mod (neutral = 1.0 mult / 0.0 add)."""
    mults = realized_mults(mod, "optimal")
    out = {}
    for s in stats:
        default = 0.0 if s in ADDITIVE else 1.0
        out[s] = goodness(s, mults.get(s, default))
    return out
