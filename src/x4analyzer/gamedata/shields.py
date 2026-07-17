"""Shield + shield-mod extraction, the third equipmentmods section after
weapons.py and engines.py. Simpler than engines: a shield has one block,
`<recharge max rate delay/>` (capacity HP / recharge HP-per-s / delay in s
before recharge starts), and mods scale those three directly.

The one interaction worth modelling: capacity raises the buffer but SLOWS the
refill, because time-to-full ~= delay + capacity/rate. So a capacity mod
lengthens refill time while rate/delay mods shorten it - the shield analog of
the engine forward-thrust leak. `derive_stats` reports that composite for a
representative shield (mod-vs-mod ratios on capacity/rate/delay are
shield-independent; the composite depends mildly on the base delay:cap/rate
split, so it is quoted for one representative shield).
"""

from __future__ import annotations

import re

from lxml import etree

from .catalog import GameFiles
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)

SHIELD_GLOB = (r"(extensions/[^/]+/)?assets/props/[Ss]urface[Ee]lements/macros/"
               r"shield_[^/]*_macro\.xml$")
_SIZE_RE = re.compile(r"_(xs|s|m|l|xl)_")
_MOD_WARE = re.compile(r"^mod_shield_")
TIME_STATS = ("rechargedelay",)   # lower is better


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


def extract_shields(gf: GameFiles) -> list[dict]:
    """Every shield macro's recharge block: capacity (max), rate, delay."""
    out = []
    for path in gf.glob(SHIELD_GLOB):
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for m in root.iter("macro"):
            if not (m.get("class") or "").startswith("shield"):
                continue
            rc = m.find(".//recharge")
            if rc is None:
                continue
            sm = _SIZE_RE.search(m.get("name", ""))
            out.append({
                "macro": m.get("name", ""),
                "size": sm.group(1) if sm else None,
                "capacity": _f(rc, "max", 0.0),
                "rate": _f(rc, "rate", 0.0),
                "delay": _f(rc, "delay", 0.0),
            })
    return sorted(out, key=lambda s: (s["size"] or "", s["macro"]))


def representative_shield(shields: list[dict], size: str = "m") -> dict | None:
    """A mid-size standard shield for the composite refill-time number. Any
    consistent pick works for mod comparison; the standard M is the default."""
    pool = [s for s in shields if s["size"] == size]
    std = [s for s in pool if "standard" in s["macro"]]
    return (std or pool or shields or [None])[0]


def extract_shield_mods(gf: GameFiles, tdb: TextDB | None = None) -> list[dict]:
    """<shield>-section entries of libraries/equipmentmods.xml (base + diff
    patches). Same shape/rules as engines.extract_engine_mods."""
    names = _mod_ware_names(gf, tdb)
    mods: dict[str, dict] = {}
    paths = ["libraries/equipmentmods.xml"] + [
        f"extensions/{ext}/libraries/equipmentmods.xml" for ext in gf.extensions
    ]
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
            if not wid.startswith("mod_shield_"):
                continue
            short = tdb.resolve(w.get("shortname", "")).strip()
            if not short:
                short = tdb.resolve(w.get("name", "")).split(" (")[0].strip()
            names[wid] = short or wid
    return names


def realized_mults(mod: dict, roll: str = "optimal") -> dict[str, float]:
    """Collapse a mod (primary + forced bonuses) to a stat -> multiplier map.
    optimal = MAX for capacity/rate, MIN for rechargedelay (lower is better)."""
    def pick(stat, lo, hi):
        if roll == "min":
            return lo
        if roll == "max":
            return hi
        return lo if stat in TIME_STATS else hi
    out = {mod["stat"]: pick(mod["stat"], mod["min"], mod["max"])}
    if mod["forced"]:
        for b in mod["bonuses"]:
            out[b["stat"]] = out.get(b["stat"], 1.0) * pick(b["stat"], b["min"], b["max"])
    return out


def derive_stats(shield: dict, mults: dict[str, float] | None = None) -> dict:
    """Resulting shield stats under a mod. refill_time = delay + capacity/rate
    (seconds from shield-down to full) - the composite where capacity trades
    against recovery."""
    mults = mults or {}
    cap = shield["capacity"] * mults.get("capacity", 1.0)
    rate = shield["rate"] * mults.get("rechargerate", 1.0)
    delay = shield["delay"] * mults.get("rechargedelay", 1.0)
    return {
        "capacity": cap,
        "rechargerate": rate,
        "rechargedelay": delay,
        "refill_time": delay + (cap / rate if rate else 0.0),
    }
