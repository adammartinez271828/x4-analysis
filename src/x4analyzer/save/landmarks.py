"""Locate individual objects in a savegame and report where to fly.

A reimplementation of the community batch/PowerShell "Erlking data vault
locator" (forum.egosoft.com p5116566), generalized: any component whose macro
matches a pattern is reported with its sector and its sector-relative
position, i.e. the km coordinates the in-game map shows.

Separate from `parser.py` on purpose. That parser makes ONE sweep collecting
everything the dashboard needs and deliberately drops zone components and
positions; this is a small standalone sweep for a targeted lookup, so it can
keep the offset chain (including the zones the analysis pipeline skips)
without complicating the hot path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .parser import _open_save

# the five Erlking data vaults (X4: Timelines); each holds one blueprint
ERLKING_VAULTS = r"^landmarks_erlking_vault_\d+_macro$"


@dataclass
class Landmark:
    macro: str
    id: str
    code: str = ""
    name: str = ""
    owner: str = ""
    cluster_macro: str = ""
    sector_macro: str = ""
    knownto: str = ""
    # position relative to the sector centre, in metres (game map shows km)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    # <source entry="erlking_blueprint_4"> — which of the set this is
    source_entry: str = ""
    # blueprints still sitting in the object's pickup connections; empty once
    # the player has collected them
    blueprints: list[str] = field(default_factory=list)

    @property
    def km(self) -> tuple[float, float, float]:
        return (self.x / 1000.0, self.y / 1000.0, self.z / 1000.0)


def _pos(elem) -> tuple[float, float, float]:
    def f(a: str) -> float:
        try:
            return float(elem.get(a, "0") or 0)
        except ValueError:
            return 0.0
    return (f("x"), f("y"), f("z"))


def find_landmarks(path: Path, pattern: str = ERLKING_VAULTS) -> list[Landmark]:
    """Stream the save, returning every component whose macro matches.

    Positions in a save are relative to the parent component, and the chain
    runs galaxy -> cluster -> sector -> zone -> object with any link possibly
    carrying `<offset default="1"/>` (= no offset). Summing from the sector
    down gives the sector-relative coordinates the game displays.
    """
    macro_re = re.compile(pattern, re.IGNORECASE)
    found: list[Landmark] = []

    tag_stack: list[str] = []
    # open <component> ancestry: [clazz, id, macro, (x, y, z)]
    comp_stack: list[list] = []
    # stack depths at which a matched component is currently open, so nested
    # pickups can be attributed to it
    open_hits: list[tuple[int, Landmark]] = []

    with _open_save(path) as fh:
        for event, elem in etree.iterparse(
            fh, events=("start", "end"), recover=True, huge_tree=True
        ):
            tag = elem.tag
            if event == "start":
                tag_stack.append(tag)
                if tag == "component":
                    macro = elem.get("macro", "").lower()
                    comp_stack.append([
                        elem.get("class", ""), elem.get("id", ""), macro,
                        (0.0, 0.0, 0.0),
                    ])
                    # matched on START: the pickups to attribute to it, and
                    # its own <offset>, are all still ahead of us
                    if macro_re.search(macro):
                        lm = Landmark(
                            macro=macro, id=elem.get("id", ""),
                            code=elem.get("code", ""),
                            name=elem.get("name", ""),
                            owner=elem.get("owner", ""),
                            knownto=elem.get("knownto", ""),
                        )
                        found.append(lm)
                        open_hits.append((len(comp_stack), lm))
                continue

            # ---- end events ----
            if tag == "position" and tag_stack[-3:] == [
                    "component", "offset", "position"]:
                if comp_stack:
                    comp_stack[-1][3] = _pos(elem)
            elif tag == "source" and open_hits and \
                    len(comp_stack) == open_hits[-1][0]:
                open_hits[-1][1].source_entry = elem.get("entry", "")
            elif tag == "component":
                bp = elem.get("blueprints")
                if bp and open_hits and len(comp_stack) > open_hits[-1][0]:
                    open_hits[-1][1].blueprints.extend(bp.split(","))

                _clazz, cid, _macro, _p = comp_stack[-1]
                if open_hits and open_hits[-1][0] == len(comp_stack) \
                        and open_hits[-1][1].id == cid:
                    lm = open_hits.pop()[1]
                    # sum offsets from the sector down to this component
                    start = 0
                    for i, (pcls, _i, _m, _pp) in enumerate(comp_stack):
                        if pcls in ("sector", "cluster"):
                            start = i + 1
                        if pcls == "cluster":
                            lm.cluster_macro = _m
                        elif pcls == "sector":
                            lm.sector_macro = _m
                    for _c, _i, _m, (x, y, z) in comp_stack[start:]:
                        lm.x += x
                        lm.y += y
                        lm.z += z
                comp_stack.pop()

            tag_stack.pop()

            # free memory: drop this element and any closed older siblings.
            # A matched component's children are read above, before its own
            # end event clears them.
            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                while elem.getprevious() is not None:
                    del parent[0]

    return found
