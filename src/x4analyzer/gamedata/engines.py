"""Engine / thruster / ship-physics extraction and the engine-mod movement
model — the propulsion counterpart to weapons.py + weaponsim.py.

Feeds the engine-mod rebalance harness (pokeys-x4-mods
tools/engine-mod-rebalance/evaluate.py), NOT the savegame pipeline.

X4 movement physics (community-documented, cross-checked against the v9
game files; see docs in the mod repo). A ship's motion is set by three
components:

  - ENGINE macro (assets/props/Engines/macros/engine_*_macro.xml):
      <thrust forward reverse/>                    linear thrust
      <boost duration recharge thrust acceleration attack release coast/>
      <travel charge thrust attack release/>
    `boost/@thrust` and `travel/@thrust` are MULTIPLIERS of forward thrust,
    not raw thrust (boost ~x8, travel ~x14 on an S engine).
  - THRUSTER macro (thruster_*_macro.xml, one per size):
      <thrust strafe pitch yaw roll/>              strafe + rotation thrust
      <angular roll pitch/>
  - SHIP macro <physics>:
      mass; <inertia pitch yaw roll/>;
      <drag forward reverse horizontal vertical pitch yaw roll/>

The two documented formulas, applied per axis:

      max speed(axis)  = thrust(axis) / drag(axis)
      acceleration     = thrust      / mass          (linear)
      angular accel    = thrust      / inertia       (rotational)

So forward_speed = engine.forward / drag.forward, forward_accel =
engine.forward / mass, turn_rate(pitch) = thruster.pitch / drag.pitch, etc.
Boost/travel top speed = forward_speed x the boost/travel multiplier.

IMPORTANT for the rebalance: absolute boost/travel speeds computed this way
read low versus the in-game encyclopedia (there are extra global constants
this model omits), but an engine MOD scales the same base quantity for every
mod, so the CONSTANT CANCELS in mod-vs-mod comparison. Rankings and
best-at-a-stat verdicts are trustworthy; treat the absolute m/s as relative.

Engine-mod stat tags (libraries/equipmentmods.xml <engine> section) and the
base quantity each multiplies — this table is the semantic core:

    forwardthrust     -> engine.forward         (forward speed + accel)
    boostthrust       -> engine.boost.thrust    (boost speed)
    boostduration     -> engine.boost.duration  (boost time)
    boostacc          -> engine.boost.acceleration
    travelthrust      -> engine.travel.thrust   (travel speed)
    travelattacktime  -> engine.travel.attack   (spin-up, lower better)
    travelchargetime  -> engine.travel.charge   (charge, lower better)
    rotationthrust    -> thruster.pitch/yaw/roll (turn rate + accel)
    strafethrust      -> thruster.strafe        (strafe speed + accel)
    strafeacc         -> thruster.strafe        (strafe accel; see note)

Note: the vanilla `strafeacc` and `boostacc` tags are carried on wares
named travelreleasetime / travelstartthrust — Egosoft reused ware ids. The
stat TAG (element name) is what the engine reads, so the mapping keys off
the tag. `strafeacc` scaling strafe thrust is a best-effort read (there is
no separate strafe-accel field); flagged so the rebalance can avoid leaning
on it.
"""

from __future__ import annotations

import re

from lxml import etree

from .catalog import GameFiles
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)

ENGINE_GLOB = (r"(extensions/[^/]+/)?assets/props/[Ee]ngines/macros/"
               r"engine_[^/]*_macro\.xml$")
THRUSTER_GLOB = (r"(extensions/[^/]+/)?assets/props/[Ee]ngines/macros/"
                 r"thruster_[^/]*_macro\.xml$")
SHIP_GLOB = (r"(extensions/[^/]+/)?assets/units/[^/]+/macros/"
             r"ship_[^/]*_macro\.xml$")

_SIZES = ("xs", "s", "m", "l", "xl")
_SIZE_RE = re.compile(r"_(xs|s|m|l|xl)_")
_TYPE_RE = re.compile(r"_(allround|travel|combat)_")
_MK_RE = re.compile(r"_mk(\d)_")

# mod stat tag -> (component, dotted attribute path). "engine"/"thruster".
MOD_STAT_TARGET = {
    "forwardthrust": ("engine", "forward"),
    "boostthrust": ("engine", "boost.thrust"),
    "boostduration": ("engine", "boost.duration"),
    "boostacc": ("engine", "boost.acceleration"),
    "travelthrust": ("engine", "travel.thrust"),
    "travelattacktime": ("engine", "travel.attack"),
    "travelchargetime": ("engine", "travel.charge"),
    "rotationthrust": ("thruster", "rotation"),   # pitch+yaw+roll together
    "strafethrust": ("thruster", "strafe"),
    # strafeacc scales only the strafe ACCELERATION, not top strafe speed, so
    # it stays distinct from strafethrust (which scales strafe thrust => both
    # speed and accel). Applied as a post-multiplier on the derived stat.
    "strafeacc": ("derived", "strafe_accel"),
}


_MOD_WARE = re.compile(r"^mod_engine_")


def extract_engine_mods(gf: GameFiles, tdb: TextDB | None = None) -> list[dict]:
    """<engine>-section entries of libraries/equipmentmods.xml (base + any
    extension diff patches). Same shape as weapons.extract_weapon_mods: the
    element tag is the primary stat multiplied; a <bonus> whose child count
    fits its @max at chance 1.0 is FORCED (all children always apply)."""
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
                    bonuses.append({
                        "stat": b.tag,
                        "min": _f(b, "min", 1.0),
                        "max": _f(b, "max", 1.0),
                        "weight": _f(b, "weight", 1.0),
                    })
            forced = bool(bonuses) and chance >= 1.0 and len(bonuses) <= bmax
            mods[ware] = {
                "ware": ware,
                "name": names.get(ware, ware),
                "stat": el.tag,
                "quality": int(_f(el, "quality", 1) or 1),
                "min": _f(el, "min", 1.0),
                "max": _f(el, "max", 1.0),
                "bonus_chance": chance,
                "bonus_max": bmax,
                "forced": forced,
                "bonuses": bonuses,
            }
    return sorted(mods.values(), key=lambda m: (m["quality"], m["stat"], m["ware"]))


def _mod_ware_names(gf: GameFiles, tdb: TextDB | None) -> dict[str, str]:
    """mod ware id -> display name (wares.xml shortname; falls back to id)."""
    names: dict[str, str] = {}
    if tdb is None:
        return names
    paths = ["libraries/wares.xml"] + [
        f"extensions/{ext}/libraries/wares.xml" for ext in gf.extensions
    ]
    for path in paths:
        if path not in gf:
            continue
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for w in root.iter("ware"):
            wid = w.get("id", "")
            if not wid.startswith("mod_engine_"):
                continue
            short = tdb.resolve(w.get("shortname", "")).strip()
            if not short:
                short = tdb.resolve(w.get("name", "")).split(" (")[0].strip()
            names[wid] = short or wid
    return names


def realized_mults(mod: dict, roll: str = "optimal") -> dict[str, float]:
    """Collapse a mod (primary + forced bonuses) to one stat -> multiplier
    vector at the given roll. roll='optimal' takes the best end of each range
    (MAX for buffs/thrust, MIN for the *time* stats where lower is better);
    roll='min'/'max' take that literal end. Optional (non-forced) pool
    bonuses are excluded — they are engine-side RNG, not guaranteed."""
    time_stats = {"travelattacktime", "travelchargetime"}

    def pick(stat: str, lo: float, hi: float) -> float:
        if roll == "min":
            return lo
        if roll == "max":
            return hi
        return lo if stat in time_stats else hi   # optimal

    out: dict[str, float] = {mod["stat"]: pick(mod["stat"], mod["min"], mod["max"])}
    if mod["forced"]:
        for b in mod["bonuses"]:
            # multiple forced children of the same stat compound
            m = pick(b["stat"], b["min"], b["max"])
            out[b["stat"]] = out.get(b["stat"], 1.0) * m
    return out


def _f(el: etree._Element | None, attr: str, default=None):
    if el is None:
        return default
    v = el.get(attr)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _tag(name: str) -> str | None:
    m = _SIZE_RE.search(name)
    return m.group(1) if m else None


def extract_engines(gf: GameFiles, tdb: TextDB | None = None) -> list[dict]:
    """Every real engine macro's thrust/boost/travel block (skips fx and the
    _video preview macros). type = allround|travel|combat; size in _SIZES."""
    out: list[dict] = []
    for path in gf.glob(ENGINE_GLOB):
        if "video" in path:
            continue
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for m in root.iter("macro"):
            if m.get("class") != "engine":
                continue
            p = m.find("properties")
            if p is None:
                continue
            thr, boost, trav = p.find("thrust"), p.find("boost"), p.find("travel")
            if thr is None:
                continue
            name = m.get("name", "")
            sm, tm, mk = _SIZE_RE.search(name), _TYPE_RE.search(name), _MK_RE.search(name)
            out.append({
                "macro": name,
                "size": sm.group(1) if sm else None,
                "type": tm.group(1) if tm else None,
                "mk": int(mk.group(1)) if mk else 1,
                "forward": _f(thr, "forward", 0.0),
                "reverse": _f(thr, "reverse", 0.0),
                "boost": {
                    "duration": _f(boost, "duration", 0.0),
                    "recharge": _f(boost, "recharge", 0.0),
                    "thrust": _f(boost, "thrust", 0.0),
                    "acceleration": _f(boost, "acceleration", 0.0),
                    "attack": _f(boost, "attack", 0.0),
                    "release": _f(boost, "release", 0.0),
                },
                "travel": {
                    "charge": _f(trav, "charge", 0.0),
                    "thrust": _f(trav, "thrust", 0.0),
                    "attack": _f(trav, "attack", 0.0),
                    "release": _f(trav, "release", 0.0),
                },
            })
    return sorted(out, key=lambda e: (e["size"] or "", e["type"] or "", e["mk"]))


def extract_thrusters(gf: GameFiles) -> dict[str, dict]:
    """size -> strafe/pitch/yaw/roll thrust. Ships pick a thruster by their
    <thruster tags=".."> size class; the generic gen_<size> allround is the
    canonical one, so we key by size and keep the first per size."""
    by_size: dict[str, dict] = {}
    for path in gf.glob(THRUSTER_GLOB):
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for m in root.iter("macro"):
            p = m.find("properties")
            if p is None:
                continue
            thr = p.find("thrust")
            if thr is None:
                continue
            size = _tag(m.get("name", ""))
            if size is None or size in by_size:
                continue
            by_size[size] = {
                "strafe": _f(thr, "strafe", 0.0),
                "pitch": _f(thr, "pitch", 0.0),
                "yaw": _f(thr, "yaw", 0.0),
                "roll": _f(thr, "roll", 0.0),
            }
    return by_size


def extract_ships(gf: GameFiles, tdb: TextDB | None = None) -> list[dict]:
    """Ship macros with a <physics> block: mass, inertia, drag, size class,
    purpose. Skips ships without physics (e.g. some scenario props)."""
    out: list[dict] = []
    for path in gf.glob(SHIP_GLOB):
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for m in root.iter("macro"):
            cls = m.get("class", "")
            if not cls.startswith("ship_"):
                continue
            p = m.find("properties")
            if p is None:
                continue
            phys = p.find("physics")
            if phys is None:
                continue
            drag = phys.find("drag")
            inertia = phys.find("inertia")
            if drag is None:
                continue
            ident = p.find("identification")
            purpose = p.find("purpose")
            name = ""
            if tdb is not None and ident is not None:
                name = tdb.resolve(ident.get("name", "")).strip()
            out.append({
                "macro": m.get("name", ""),
                "name": name or m.get("name", ""),
                "size": cls.split("_", 1)[1],   # ship_s -> s
                "purpose": (purpose.get("primary") if purpose is not None else None),
                "mass": _f(phys, "mass", 1.0),
                "inertia": {
                    "pitch": _f(inertia, "pitch", 1.0),
                    "yaw": _f(inertia, "yaw", 1.0),
                    "roll": _f(inertia, "roll", 1.0),
                },
                "drag": {
                    "forward": _f(drag, "forward", 1.0),
                    "reverse": _f(drag, "reverse", 1.0),
                    "horizontal": _f(drag, "horizontal", 1.0),
                    "vertical": _f(drag, "vertical", 1.0),
                    "pitch": _f(drag, "pitch", 1.0),
                    "yaw": _f(drag, "yaw", 1.0),
                    "roll": _f(drag, "roll", 1.0),
                },
            })
    return sorted(out, key=lambda s: (s["size"], s["macro"]))


def representative_engine(engines: list[dict], size: str,
                          etype: str = "allround", mk: int = 1) -> dict | None:
    """Pick a stand-in engine of a ship's size for mod comparison. Engine
    choice is the player's and cancels in mod ratios, so any consistent pick
    works; allround mk1 is the neutral default."""
    pool = [e for e in engines if e["size"] == size]
    if not pool:
        return None
    exact = [e for e in pool if e["type"] == etype and e["mk"] == mk]
    if exact:
        return exact[0]
    typed = [e for e in pool if e["type"] == etype]
    return (typed or pool)[0]


def derive_stats(ship: dict, engine: dict, thruster: dict,
                 post: dict[str, float] | None = None) -> dict:
    """Moddable stat vector for a ship+engine+thruster. Speeds in m/s
    (relative; see module note), accels in m/s^2 or rad/s^2, times in s.
    Bigger is better EXCEPT travel_charge/travel_attack (times). `post` is an
    optional map of derived-stat -> multiplier for tags that scale a derived
    quantity directly (e.g. strafeacc -> strafe_accel)."""
    mass = ship["mass"] or 1.0
    drag = ship["drag"]
    inertia = ship["inertia"]
    fwd = engine["forward"]
    b, t = engine["boost"], engine["travel"]
    # rotation thrust is per-axis on the thruster; use pitch/yaw mean as the
    # headline "turn" (roll matters less for aim), keep axes too.
    turn_thrust = (thruster["pitch"] + thruster["yaw"]) / 2.0
    stats = {
        "forward_speed": fwd / drag["forward"],
        "forward_accel": fwd / mass,
        "reverse_speed": engine["reverse"] / drag["reverse"],
        "strafe_speed": thruster["strafe"] / drag["horizontal"],
        "strafe_accel": thruster["strafe"] / mass,
        "boost_speed": fwd * b["thrust"] / drag["forward"],
        "boost_duration": b["duration"],
        "boost_accel": fwd * (b["acceleration"] or 1.0) / mass,
        "travel_speed": fwd * t["thrust"] / drag["forward"],
        "travel_charge": t["charge"],          # lower better
        "travel_attack": t["attack"],          # lower better
        "turn_rate": turn_thrust / ((drag["pitch"] + drag["yaw"]) / 2.0),
        "turn_accel": turn_thrust / ((inertia["pitch"] + inertia["yaw"]) / 2.0),
        "roll_rate": thruster["roll"] / drag["roll"],
    }
    for k, m in (post or {}).items():
        if k in stats and m:
            stats[k] = stats[k] * m
    return stats


def apply_mod(engine: dict, thruster: dict, mults: dict[str, float]
              ) -> tuple[dict, dict, dict]:
    """Return (engine', thruster', post) with a mod's per-stat multipliers
    applied to the base quantity each tag targets (MOD_STAT_TARGET). `mults`
    maps stat tag -> realized multiplier (already resolved to a single value,
    since the rebalance pins min=max). `post` carries multipliers for tags
    that target a derived stat directly (comp == "derived"); pass it to
    derive_stats."""
    e = {**engine, "boost": dict(engine["boost"]), "travel": dict(engine["travel"])}
    th = dict(thruster)
    post: dict[str, float] = {}
    for tag, mult in mults.items():
        target = MOD_STAT_TARGET.get(tag)
        if target is None or mult is None:
            continue
        comp, path = target
        if comp == "engine":
            if "." in path:
                grp, key = path.split(".")
                e[grp][key] = e[grp][key] * mult
            else:
                e[path] = e[path] * mult
        elif comp == "thruster":
            if path == "rotation":
                for ax in ("pitch", "yaw", "roll"):
                    th[ax] = th[ax] * mult
            else:
                th[path] = th[path] * mult
        else:  # derived post-multiplier
            post[path] = post.get(path, 1.0) * mult
    return e, th, post


def modded_stats(ship: dict, engine: dict, thruster: dict,
                 mults: dict[str, float]) -> dict:
    """Convenience: apply a mod's multipliers and return the derived stats."""
    e, th, post = apply_mod(engine, thruster, mults)
    return derive_stats(ship, e, th, post)
