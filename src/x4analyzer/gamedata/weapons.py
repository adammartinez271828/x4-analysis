"""Weapon / turret / bullet / equipment-mod extraction from the game files.

Feeds the game-data dashboard (`x4-analyzer gamedata-dashboard`), NOT the
savegame pipeline. Three sources, all read through the GameFiles catalog view
(base + DLC, later wins, loose files override):

- weapon/turret macros (assets/**/macros/weapon_*|turret_*_macro.xml — the
  base game spells the directory `WeaponSystems`/`weaponFx`, DLCs lowercase
  it, and GameFiles.glob is case-sensitive, hence the [Ww] classes);
- their bullet macros (assets/fx/weaponFx/macros and DLC equivalents),
  which carry the fire-rate / heat-per-shot / clip / damage numbers;
- libraries/equipmentmods.xml `<weapon>` section: every mod's primary stat
  with its roll range plus `<bonus>` children. A bonus block whose child
  count fits within its `max` (at chance 1.0) is FORCED — every child always
  rolls; a larger weighted pool is optional and never guaranteed.

Only class="weapon"/"turret" macros are kept: missile launchers share the
file naming but their damage lives on missile ammunition, which this model
does not cover.
"""

from __future__ import annotations

import re

from lxml import etree

from .catalog import GameFiles
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)

WEAPON_GLOB = (r"(extensions/[^/]+/)?assets/.*/macros/"
               r"(weapon|turret)_[^/]*_macro\.xml$")
BULLET_GLOB = r"(extensions/[^/]+/)?assets/fx/[Ww]eapon[Ff]x/macros/[^/]*\.xml$"

_WEAPON_CLASSES = {"weapon", "turret"}
_SIZES = {"xs", "s", "m", "l", "xl"}


def _load_order(gf: GameFiles, paths: list[str]) -> list[str]:
    """Sort virtual paths base-first then extensions in load order, so a
    later duplicate macro name overrides an earlier one (timelines re-issues
    e.g. the Terran EM gun with new heat numbers)."""
    def key(path: str) -> tuple[int, str]:
        src = gf.source_of(path)
        if not src:
            return (0, path)
        try:
            return (1 + gf.extensions.index(src), path)
        except ValueError:
            return (len(gf.extensions) + 1, path)
    return sorted(paths, key=key)


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


def _parse_bullets(gf: GameFiles) -> dict[str, dict]:
    """bullet macro name -> firing properties (see keys below)."""
    bullets: dict[str, dict] = {}
    for path in _load_order(gf, gf.glob(BULLET_GLOB)):
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        for m in root.iter("macro"):
            name = (m.get("name") or "").lower()
            props = m.find("properties")
            if not name or props is None:
                continue
            b = props.find("bullet")
            dmg = props.find("damage")
            area = props.find("areadamage")
            # heat: `value` is the ongoing per-shot/-second heat; `initial` is
            # an instantaneous spike at each firing-cycle onset. Kept separate
            # (the sim applies initial as a one-time spike, or as the per-shot
            # heat for a mass driver that has only initial and no value). See
            # docs/weapon-heat-and-rate-bug-2026-07.md.
            heat_el = props.find("heat")
            bullets[name] = {
                "speed": _f(b, "speed"),
                "lifetime": _f(b, "lifetime"),
                "range": _f(b, "range"),
                "chargetime": _f(b, "chargetime"),
                "amount": _f(b, "amount", 1.0),
                "barrelamount": _f(b, "barrelamount", 1.0),
                "forcecooldown": _f(b, "forcecooldownaftershot", 0.0),
                "heat": _f(heat_el, "value", 0.0),
                "heat_initial": _f(heat_el, "initial", 0.0),
                "reload_rate": _f(props.find("reload"), "rate"),
                "reload_time": _f(props.find("reload"), "time"),
                "ammo_clip": _f(props.find("ammunition"), "value"),
                "ammo_reload": _f(props.find("ammunition"), "reload"),
                "dmg": _f(dmg, "value", 0.0),
                "dmg_shield": _f(dmg, "shield", 0.0),
                "dmg_hull": _f(dmg, "hull", 0.0),
                "dmg_repair": _f(dmg, "repair", 0.0),
                # explosive weapons (Blast Mortar, flak) keep their damage
                # in <areadamage>, sometimes with no <damage> at all
                "area_dmg": _f(area, "value", 0.0),
                "area_dmg_shield": _f(area, "shield", 0.0),
                "has_damage": dmg is not None or area is not None,
            }
    return bullets


def _size_of(macro: str) -> str:
    for token in macro.split("_"):
        if token in _SIZES:
            return token.upper()
    return "?"


def extract_weapons(gf: GameFiles, tdb: TextDB) -> list[dict]:
    """One record per weapon/turret macro, bullet stats merged in. Weapons
    whose bullet macro cannot be found are dropped (one Kha'ak scenario
    beam in v9.0)."""
    bullets = _parse_bullets(gf)
    weapons: dict[str, dict] = {}
    for path in _load_order(gf, gf.glob(WEAPON_GLOB)):
        root = etree.fromstring(gf.read_bytes(path), _PARSER)
        if root is None:
            continue
        source = gf.source_of(path)
        for m in root.iter("macro"):
            macro = (m.get("name") or "").lower()
            if m.get("class") not in _WEAPON_CLASSES or not macro:
                continue
            props = m.find("properties")
            if props is None:
                continue
            ident = props.find("identification")
            bullet_el = props.find("bullet")
            bullet_ref = ((bullet_el.get("class") or "")
                          if bullet_el is not None else "").lower()
            bullet = bullets.get(bullet_ref)
            if bullet is None:
                continue
            heat = props.find("heat")
            name = tdb.resolve(ident.get("name", "")) if ident is not None \
                else ""
            weapons[macro] = {
                "macro": macro,
                "name": name or macro,
                "mk": (ident.get("mk", "") if ident is not None else ""),
                "race": (ident.get("makerrace", "")
                         if ident is not None else ""),
                "wclass": m.get("class"),
                "size": _size_of(macro),
                "source": source,
                "bullet": bullet_ref,
                "overheat": _f(heat, "overheat"),
                "cooldelay": _f(heat, "cooldelay"),
                "overheatcooldelay": _f(heat, "overheatcooldelay", 0.0),
                "coolrate": _f(heat, "coolrate"),
                "reenable": _f(heat, "reenable", 0.0),
                "rotation_speed": _f(props.find("rotationspeed"), "max"),
                **bullet,
            }
    return list(weapons.values())


_MOD_WARE = re.compile(r"^mod_weapon_")


def extract_weapon_mods(gf: GameFiles, tdb: TextDB) -> list[dict]:
    """Weapon-section entries of libraries/equipmentmods.xml (base +
    extension diff patches). Element tag = the primary stat the mod
    multiplies; ware id links to the purchasable ware."""
    names = _mod_ware_names(gf, tdb)
    mods: dict[str, dict] = {}
    paths = ["libraries/equipmentmods.xml"] + [
        f"extensions/{ext}/libraries/equipmentmods.xml"
        for ext in gf.extensions
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
            # every bonus child fits within max at chance 1 -> all forced
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
    return sorted(mods.values(),
                  key=lambda m: (m["quality"], m["stat"], m["ware"]))


def _mod_ware_names(gf: GameFiles, tdb: TextDB) -> dict[str, str]:
    """mod ware id -> display name (wares.xml shortname, e.g. 'Slasher';
    falls back to the long name's leading word group)."""
    names: dict[str, str] = {}
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
            if not wid.startswith("mod_"):
                continue
            short = tdb.resolve(w.get("shortname", "")).strip()
            if not short:
                short = tdb.resolve(w.get("name", "")).split(" (")[0].strip()
            names[wid] = short or wid
    return names
