"""Single-pass streaming parser for X4 savegames (.xml or .xml.gz).

One lxml.iterparse sweep collects every record the analysis needs; elements
are cleared as soon as they close, so peak memory stays far below the DOM
approach the original R script used (which needed ~16 GB for large saves).

Component ancestry (which cluster/sector/station/ship an element sits in) is
tracked with an explicit stack instead of the R script's forward-fill trick.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from lxml import etree

# component classes that become df_universe rows (buildstorage: needed to
# attribute free-floating construction sites to an owner)
_UNIVERSE_CLASSES = ("cluster", "sector", "station", "buildstorage")
_SHIP_RE = re.compile(r"^ship_")

# ware name embedded in a v9 resource-area yieldid, e.g.
# "sphere_large_ore_high_slow" -> "ore"
_YIELD_WARE_RE = re.compile(
    r"_(ore|silicon|nividium|ice|hydrogen|helium|methane|rawscrap|scrap)(?:_|$)"
)


@dataclass
class SaveData:
    # /savegame/info
    guid: str = ""
    game_version: str = ""
    game_time: float = 0.0
    save_date: str = ""
    player_name: str = ""
    player_money: float = 0.0
    player_faction_name: str = ""    # custom name, if renamed
    modified: bool = False

    # record lists (tuples; column names live in frames.py)
    components: list = field(default_factory=list)
    # (id, clazz, macro, name, code, owner, knownto, contested, connection,
    #  spawntime, cluster_id, cluster_macro, sector_id, sector_macro)
    # fleet hierarchy: a follower's <connected connection="[X]"> points at the
    # commander's <connection connection="subordinates" id="[X]"> element
    commander_links: list = field(default_factory=list)   # (follower_id, conn_ref)
    subordinate_conns: list = field(default_factory=list)  # (leader_id, conn_id)
    posts: list = field(default_factory=list)          # (object_id, post, npc_ref)
    workforce: list = field(default_factory=list)      # (station_id, race, amount)
    modules: list = field(default_factory=list)
    # (host_id, index, macro, entry_id, build_method)
    # sequence-entry ids that have a constructed component (module built)
    built_refs: list = field(default_factory=list)
    # equipment in planned module loadouts: (entry_id, equipment_macro)
    module_upgrades: list = field(default_factory=list)
    npcs: list = field(default_factory=list)           # (id, name, code, owner, {skills})
    resources: list = field(default_factory=list)      # (sector_macro, ware, yield)
    cargo: list = field(default_factory=list)          # (object_id, ware, amount)
    # materials missing for builds (<insufficient>/<shortage> under
    # <build><resources>); host is "" for free-floating build storages.
    # kind: "insufficient" = station construction, "shortage" = shipyard
    # ship-order backlog
    build_resources: list = field(default_factory=list)  # (host, ware, amount, kind)
    # open trade offers: (object_id, side, ware, amount, price_cr)
    # side "buy" = station wants to buy `amount` at `price`; "sell" mirrors
    trade_offers: list = field(default_factory=list)
    # free-floating ware objects in space (scrap cubes, dropped cargo)
    floating_wares: list = field(default_factory=list)  # (sector_macro, ware, amount)
    # order queues of stations/ships: (object_id, order, is_default, state)
    orders: list = field(default_factory=list)
    log_entries: list = field(default_factory=list)    # dict per <entry>
    trades: list = field(default_factory=list)         # dict per economylog <log>
    removed_objects: list = field(default_factory=list)  # dict per <object>
    # aggregate crew aboard: (object_id, role) -> count of <person> elements
    # (roles: service, marine, passenger, prisoner; captain/engineer are
    # separate npc components tracked via posts)
    people: dict = field(default_factory=dict)


def _open_save(path: Path) -> IO[bytes]:
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _nearest_host(comp_stack: list) -> str:
    """Nearest trackable ancestor: station, build storage, or ship. Offers
    and cargo of a station plot's build storage attribute to the storage,
    cleanly separating construction demand from station operations."""
    for pcls, pid, _pm in reversed(comp_stack):
        if pcls in ("station", "buildstorage") or _SHIP_RE.match(pcls):
            return pid
    return ""


def parse_savegame(path: Path, progress=None) -> SaveData:
    data = SaveData()
    d = data  # short alias

    tag_stack: list[str] = []
    # ancestry of open <component> elements: (clazz, id, macro)
    comp_stack: list[tuple[str, str, str]] = []
    # nearest open station/ship component id, for posts/workforce/modules
    object_stack: list[str] = []
    npc_stack: list[list] = []       # open npc records awaiting <skills>
    entry_stack: list[str] = []      # open construction sequence entries
    build_type_stack: list[str] = []  # type attr of open <build> elements
    build_method_stack: list[str] = []  # method attr of open <build> elements
    sector_macro_stack: list[str] = []
    in_faction_player = 0
    n_elems = 0

    with _open_save(path) as fh:
        for event, elem in etree.iterparse(
            fh, events=("start", "end"), recover=True, huge_tree=True
        ):
            tag = elem.tag
            if event == "start":
                tag_stack.append(tag)
                if tag == "component":
                    clazz = elem.get("class", "")
                    cid = elem.get("id", "")
                    comp_stack.append((clazz, cid, elem.get("macro", "")))
                    if clazz == "station" or _SHIP_RE.match(clazz):
                        object_stack.append(cid)
                    elif clazz == "sector":
                        sector_macro_stack.append(elem.get("macro", ""))
                    elif clazz == "npc" and elem.get("owner") == "player":
                        npc_stack.append([
                            cid, elem.get("name", ""), elem.get("code", ""),
                            elem.get("owner", ""), {},
                        ])
                elif tag == "build":
                    build_type_stack.append(elem.get("type", ""))
                    build_method_stack.append(elem.get("method", ""))
                elif tag == "entry" and elem.get("index") \
                        and elem.get("macro"):
                    entry_stack.append(elem.get("id", ""))
                elif tag == "person":
                    if object_stack:
                        key = (object_stack[-1], elem.get("role", ""))
                        d.people[key] = d.people.get(key, 0) + 1
                elif tag == "faction" and elem.get("id") == "player":
                    in_faction_player += 1
                continue

            # ---- end events ----
            tag_stack.pop()
            n_elems += 1
            if progress and n_elems % 5_000_000 == 0:
                progress(f"  ...{n_elems / 1e6:.0f}M elements")

            if tag == "component":
                clazz, cid, macro = comp_stack.pop()
                if elem.get("construction") \
                        and elem.get("state") != "construction":
                    # in-progress modules carry state="construction"; their
                    # plan entry still needs materials, so only finished
                    # components mark an entry as built
                    d.built_refs.append(elem.get("construction"))
                if clazz == "station" or _SHIP_RE.match(clazz):
                    if object_stack and object_stack[-1] == cid:
                        object_stack.pop()
                elif clazz == "sector":
                    if sector_macro_stack and sector_macro_stack[-1] == macro:
                        sector_macro_stack.pop()
                elif clazz == "npc" and npc_stack and npc_stack[-1][0] == cid:
                    d.npcs.append(tuple(npc_stack.pop()))

                if clazz in _UNIVERSE_CLASSES or _SHIP_RE.match(clazz):
                    cluster_id = cluster_macro = sector_id = sector_macro = ""
                    for pcls, pid, pmacro in comp_stack:
                        if pcls == "cluster":
                            cluster_id, cluster_macro = pid, pmacro
                        elif pcls == "sector":
                            sector_id, sector_macro = pid, pmacro
                    if clazz == "cluster":
                        cluster_id, cluster_macro = cid, macro
                    elif clazz == "sector":
                        sector_id, sector_macro = cid, macro
                    d.components.append((
                        cid, clazz, macro, elem.get("name", ""),
                        elem.get("code", ""), elem.get("owner", ""),
                        elem.get("knownto", ""), elem.get("contested", ""),
                        elem.get("connection", ""), elem.get("spawntime", ""),
                        cluster_id, cluster_macro, sector_id, sector_macro,
                        elem.get("basename", ""),
                    ))

            elif tag == "connected":
                parent = elem.getparent()
                if (object_stack and parent is not None
                        and parent.tag == "connection"
                        and parent.get("connection") == "commander"):
                    d.commander_links.append(
                        (object_stack[-1], elem.get("connection", "")))

            elif tag == "connection":
                if object_stack and elem.get("connection") == "subordinates":
                    d.subordinate_conns.append(
                        (object_stack[-1], elem.get("id", "")))

            elif tag == "post":
                # crew assignments live at <control><post id=... component=.../>
                if object_stack and tag_stack and tag_stack[-1] == "control":
                    d.posts.append((
                        object_stack[-1], elem.get("id", ""),
                        elem.get("component", ""),
                    ))

            elif tag == "workforce":
                if object_stack and elem.get("race"):
                    d.workforce.append((
                        object_stack[-1], elem.get("race", ""),
                        float(elem.get("amount", 0) or 0),
                    ))

            elif tag == "entry":
                if "log" in tag_stack:
                    d.log_entries.append(dict(elem.attrib))
                elif elem.get("index") and elem.get("macro"):
                    # sequence entries live on stations (built + queued) and
                    # on build storages (expansion plans, type="expand")
                    host = _nearest_host(comp_stack)
                    if host:
                        try:
                            d.modules.append((
                                host, int(elem.get("index")),
                                elem.get("macro", "").lower(),
                                elem.get("id", ""),
                                build_method_stack[-1]
                                if build_method_stack else "",
                            ))
                        except ValueError:
                            pass
                    if entry_stack:
                        entry_stack.pop()

            elif tag == "skills":
                if npc_stack:
                    npc_stack[-1][4] = {k: float(v) for k, v in elem.attrib.items()}

            elif tag == "ware":
                parent = tag_stack[-1] if tag_stack else ""
                gparent = tag_stack[-2] if len(tag_stack) >= 2 else ""
                if parent == "cargo":
                    host = _nearest_host(comp_stack)
                    if host:
                        d.cargo.append((
                            host, elem.get("ware", ""),
                            float(elem.get("amount", 0) or 0),
                        ))
                elif parent == "wares":
                    # only genuinely collectable objects count as floating
                    # stock: scrap cubes (class recyclable) and dropped cargo.
                    # <supplies><wares> blocks are ships' ammo/drone reserves.
                    if comp_stack and comp_stack[-1][0] in (
                            "recyclable", "collectablewares", "lockbox"):
                        d.floating_wares.append((
                            sector_macro_stack[-1] if sector_macro_stack
                            else "",
                            elem.get("ware", ""),
                            float(elem.get("amount", 0) or 0),
                        ))
                elif parent in ("insufficient", "shortage") \
                        and gparent == "resources":
                    # station/module construction only. buildship entries are
                    # queued wharf ship orders whose "insufficient" amounts
                    # are a wharf-wide aggregate repeated per order/ware —
                    # meaningless to sum (their demand = their buy offers)
                    btype = build_type_stack[-1] if build_type_stack else ""
                    if btype in ("", "build"):
                        # host = nearest trackable ancestor (station, free
                        # build storage, or ship) — insufficient blocks often
                        # sit under buildprocessor components, which aren't
                        # universe objects and would break faction/sector
                        # attribution
                        host = _nearest_host(comp_stack)
                        d.build_resources.append((
                            host,
                            elem.get("ware", ""),
                            float(elem.get("amount", 0) or 0),
                            parent,
                        ))

            elif tag == "build":
                if build_type_stack:
                    build_type_stack.pop()
                if build_method_stack:
                    build_method_stack.pop()

            elif tag == "order":
                if object_stack and elem.get("order"):
                    d.orders.append((
                        object_stack[-1], elem.get("order", ""),
                        elem.get("default", "") == "1",
                        elem.get("state", ""),
                    ))

            elif tag in ("shields", "turrets", "engines"):
                if entry_stack and elem.get("macro") \
                        and tag_stack and tag_stack[-1] == "groups":
                    d.module_upgrades.append(
                        (entry_stack[-1], elem.get("macro", "").lower()))

            elif tag == "trade":
                if elem.get("ware") and "offers" in tag_stack \
                        and (elem.get("buyer") or elem.get("seller")):
                    d.trade_offers.append((
                        _nearest_host(comp_stack),
                        "buy" if elem.get("buyer") else "sell",
                        elem.get("ware", ""),
                        float(elem.get("amount", 0) or 0),
                        float(elem.get("price", 0) or 0) / 100.0,
                    ))

            elif tag == "area":
                if sector_macro_stack and elem.get("yieldid"):
                    m = _YIELD_WARE_RE.search(elem.get("yieldid", ""))
                    if m:
                        d.resources.append((
                            sector_macro_stack[-1], m.group(1),
                            float(elem.get("yield", 0) or 0),
                        ))

            elif tag == "log" and "economylog" in tag_stack:
                if elem.get("type") == "trade":
                    d.trades.append(dict(elem.attrib))

            elif tag == "object":
                if "economylog" in tag_stack and "removed" in tag_stack:
                    d.removed_objects.append(dict(elem.attrib))

            elif tag == "game":
                if tag_stack and tag_stack[-1] == "info":
                    d.guid = elem.get("guid", "")
                    d.game_version = elem.get("version", "")
                    d.game_time = float(elem.get("time", 0) or 0)
                    d.modified = elem.get("modified", "0") == "1"

            elif tag == "save":
                if tag_stack and tag_stack[-1] == "info":
                    d.save_date = elem.get("date", "")

            elif tag == "player":
                if tag_stack and tag_stack[-1] == "info":
                    d.player_name = elem.get("name", "")
                    d.player_money = float(elem.get("money", 0) or 0)

            elif tag == "name":
                if in_faction_player and tag_stack and tag_stack[-1] == "custom":
                    d.player_faction_name = elem.get("name", "")

            elif tag == "faction":
                if elem.get("id") == "player":
                    in_faction_player = max(0, in_faction_player - 1)

            # free memory: drop this element and any closed older siblings
            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                while elem.getprevious() is not None:
                    del parent[0]

    return data
