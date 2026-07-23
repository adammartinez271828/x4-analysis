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

# ware name + yield level + gatherspeed embedded in a v9 resource-area
# yieldid: "sphere_large_ore_high_slow" -> ("ore", "high", "slow"); both
# suffix tokens are optional ("sphere_medium_silicon_low" has no speed)
_YIELD_WARE_RE = re.compile(
    r"_(ore|silicon|nividium|ice|hydrogen|helium|methane"
    r"|rawkhaakscrap|rawscrap|scrap)(?:_([a-z]+))?(?:_([a-z]+))?$"
)

# data vaults, matched on macro: the classes differ (regular vaults are
# class="datavault", Erlking vaults class="object")
_VAULT_RE = re.compile(r"^landmarks_(erlking_)?vault_\d+_macro$")

# wormholes / anomalies: every galaxy anomaly (the scannable lore swirls AND
# the story warp points) is class="anomaly", macro wormhole_v1(_standalone).
# Only some carry a <transition destination> (story warp) or a <connected>
# link to a partner wormhole (an active/paired warp) — see
# docs/models/wormhole-connection-model.md
_ANOMALY_CLASS = "anomaly"


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
    #  spawntime, cluster_id, cluster_macro, sector_id, sector_macro,
    #  basename, parent_id)
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
    # (sector_macro, ware, yield, level, speed, starttime); starttime is the
    # game-time secs at which a depleted area becomes respawn-eligible (0 on
    # live/never-depleted areas) — an empty area past its starttime reads
    # yield=0 but is actually full and mineable
    resources: list = field(default_factory=list)
    cargo: list = field(default_factory=list)          # (object_id, ware, amount)
    # station-level ammunition: (station_id, macro, amount) from the station's
    # own <ammunition><available> -- drones (defence/repair/transport/build/
    # mining, sharing one units.maxcount pool), police craft, turret munitions
    # (missiles, countermeasures) and deployables. Docked ships' ammunition is
    # excluded (nearest component must be the station itself). Classified in
    # analysis/drones.py. NB: drones/police are the units; the rest are
    # separate inventories.
    ammunition: list = field(default_factory=list)
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
    # data vaults (regular + Erlking), for the map overlay:
    # (id, macro, code, knownto, sector_macro, sx, sz, unlocked, loot,
    #  blueprints_csv). unlocked = <unlock state="unlocked"/> present;
    # loot = collectable child components still uncollected; blueprints =
    # blueprint macros still inside (Erlking; empty once collected)
    datavaults: list = field(default_factory=list)
    # wormholes / anomalies for the map overlay:
    # (id, macro, code, knownto, cluster_macro, sector_macro, sx, sz,
    #  source_entry, source_class, transition_dest). transition_dest is None
    # when the component has no <transition> (an inert lore anomaly), else the
    # destination-state string ("0" = a dormant/story warp not yet wired up)
    wormholes: list = field(default_factory=list)
    # directional links between paired wormholes, one row per <connection>:
    # (wormhole_id, own_conn_id, role, target_conn_id). role is "origin"
    # (this end is the entry) or "destination" (this end is the exit);
    # target_conn_id is the partner's connection id — resolve the partner by
    # matching it to another wormhole's own_conn_id (frames.wormhole_edges)
    wormhole_links: list = field(default_factory=list)
    # equipped engines: (ship_id, engine_macro) per engine component (all
    # ships; the store keeps player ships only — speed-from-loadout)
    ship_engines: list = field(default_factory=list)
    # faction diplomacy (universe/factions block). base relations, temporary
    # boosters (additive, decay toward base — the stored value is current as
    # of the save) and trade discounts, one row each:
    faction_relations: list = field(default_factory=list)  # (faction, other, relation)
    faction_boosters: list = field(default_factory=list)   # (faction, other, relation, time)
    faction_discounts: list = field(default_factory=list)  # (faction, other, amount, time)
    faction_accounts: list = field(default_factory=list)   # (faction, amount)
    faction_licences: list = field(default_factory=list)   # (faction, type, factions_csv)
    # False when the save was started with local (ring) highways
    # disabled: such saves contain no class="highway" components
    has_highways: bool = False


def _open_save(path: Path) -> IO[bytes]:
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _nearest_host(comp_stack: list) -> str:
    """Nearest trackable ancestor: station, build storage, or ship. Offers
    and cargo of a station plot's build storage attribute to the storage,
    cleanly separating construction demand from station operations."""
    for pcls, pid, _pm, _pp in reversed(comp_stack):
        if pcls in ("station", "buildstorage") or _SHIP_RE.match(pcls):
            return pid
    return ""


def parse_savegame(path: Path, progress=None) -> SaveData:
    data = SaveData()
    d = data  # short alias

    tag_stack: list[str] = []
    # ancestry of open <component> elements: [clazz, id, macro, offset].
    # offset is the component's own <offset><position> as (x, z), or None
    # (<offset default="1"/> = at the parent's origin) — kept so stations
    # get sector-local coordinates summed over the interposed zones
    comp_stack: list[list] = []
    # nearest open station/ship component id, for posts/workforce/modules
    object_stack: list[str] = []
    npc_stack: list[list] = []       # open npc records awaiting <skills>
    entry_stack: list[str] = []      # open construction sequence entries
    build_type_stack: list[str] = []  # type attr of open <build> elements
    build_method_stack: list[str] = []  # method attr of open <build> elements
    sector_macro_stack: list[str] = []
    # open data-vault components awaiting their loot/unlock children
    vault_stack: list[list] = []
    # open wormhole/anomaly components awaiting source/transition/connected
    # children: [comp_stack depth, record dict]
    wormhole_stack: list[list] = []
    # id of the open <faction> in the universe/factions block, so its
    # relation/booster/discount/account/licence children attribute correctly
    faction_id_stack: list[str] = []
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
                    comp_stack.append([clazz, cid, elem.get("macro", ""),
                                       None])
                    if clazz == "highway":
                        d.has_highways = True
                    if _VAULT_RE.match(elem.get("macro", "").lower()):
                        # [comp_stack depth, unlocked, loot, blueprints]
                        vault_stack.append([len(comp_stack), 0, 0, []])
                    elif clazz == _ANOMALY_CLASS:
                        wormhole_stack.append([len(comp_stack), {
                            "id": cid, "macro": elem.get("macro", "").lower(),
                            "code": elem.get("code", ""),
                            "knownto": elem.get("knownto", ""),
                            "source_entry": "", "source_class": "",
                            "transition_dest": None, "links": [],
                        }])
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
                elif tag == "faction":
                    # a faction in universe/factions (not a faction= attr
                    # elsewhere): track its id for the relations children
                    if "factions" in tag_stack:
                        faction_id_stack.append(elem.get("id", ""))
                    if elem.get("id") == "player":
                        in_faction_player += 1
                continue

            # ---- end events ----
            tag_stack.pop()
            n_elems += 1
            if progress and n_elems % 5_000_000 == 0:
                progress(f"  ...{n_elems / 1e6:.0f}M elements")

            if tag == "position":
                # a component's own offset: <component><offset><position/>
                # ("position" is already popped off tag_stack here)
                if comp_stack and tag_stack[-2:] == ["component", "offset"]:
                    try:
                        comp_stack[-1][3] = (float(elem.get("x", 0) or 0),
                                             float(elem.get("z", 0) or 0))
                    except ValueError:
                        pass

            elif tag == "unlock":
                # <unlock state="unlocked"/> directly under an open vault
                if vault_stack and len(comp_stack) == vault_stack[-1][0] \
                        and elem.get("state") == "unlocked":
                    vault_stack[-1][1] = 1

            elif tag == "source":
                # <source entry= class=> of an open wormhole
                if wormhole_stack and len(comp_stack) == wormhole_stack[-1][0]:
                    rec = wormhole_stack[-1][1]
                    rec["source_entry"] = elem.get("entry", "")
                    rec["source_class"] = elem.get("class", "")

            elif tag == "transition":
                # <transition destination="N"/> of an open wormhole; N=0 is a
                # dormant story warp (destination wired up in-mission)
                if wormhole_stack and len(comp_stack) == wormhole_stack[-1][0]:
                    wormhole_stack[-1][1]["transition_dest"] = \
                        elem.get("destination", "")

            elif tag == "item":
                # station-level <ammunition><available><item macro= amount=>:
                # the station's own drones. comp_stack[-1] is the enclosing
                # component, so requiring it to be a station drops the
                # ammunition of ships docked at the station.
                if (comp_stack and comp_stack[-1][0] == "station"
                        and tag_stack[-2:] == ["ammunition", "available"]):
                    amt = elem.get("amount", "")
                    macro = elem.get("macro", "").lower()
                    if macro and amt:
                        d.ammunition.append((comp_stack[-1][1], macro, amt))

            elif tag == "component":
                clazz, cid, macro, own_pos = comp_stack.pop()
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
                elif clazz == "engine" and object_stack:
                    d.ship_engines.append((object_stack[-1], macro))

                if clazz in _UNIVERSE_CLASSES or _SHIP_RE.match(clazz):
                    cluster_id = cluster_macro = sector_id = sector_macro = ""
                    sector_depth = -1
                    for i, (pcls, pid, pmacro, _pp) in enumerate(comp_stack):
                        if pcls == "cluster":
                            cluster_id, cluster_macro = pid, pmacro
                        elif pcls == "sector":
                            sector_id, sector_macro = pid, pmacro
                            sector_depth = i
                    if clazz == "cluster":
                        cluster_id, cluster_macro = cid, macro
                    elif clazz == "sector":
                        sector_id, sector_macro = cid, macro
                    # real containment (ship docked at station, station in
                    # sector), which the flattened cluster/sector columns
                    # can't express. Nearest COLLECTED ancestor, not the
                    # immediate XML parent: saves interpose zone/dockingbay
                    # components that never become rows, and a parent id
                    # must resolve within the table
                    parent_id = ""
                    for pcls, pid, _pm, _pp in reversed(comp_stack):
                        if pcls in _UNIVERSE_CLASSES or _SHIP_RE.match(pcls):
                            parent_id = pid
                            break
                    # sector-local position for stations/build plots: own
                    # offset plus any zone offsets between sector and here
                    # (landmarks.py does the same walk for the find cmd)
                    sx = sz = None
                    if clazz in ("station", "buildstorage") \
                            and sector_depth >= 0:
                        sx = own_pos[0] if own_pos else 0.0
                        sz = own_pos[1] if own_pos else 0.0
                        for _c, _i2, _m, p in comp_stack[sector_depth + 1:]:
                            if p:
                                sx += p[0]
                                sz += p[1]
                    d.components.append((
                        cid, clazz, macro, elem.get("name", ""),
                        elem.get("code", ""), elem.get("owner", ""),
                        elem.get("knownto", ""), elem.get("contested", ""),
                        elem.get("connection", ""), elem.get("spawntime", ""),
                        cluster_id, cluster_macro, sector_id, sector_macro,
                        elem.get("basename", ""), parent_id, sx, sz,
                        elem.get("factionheadquarters", ""),
                    ))

                if vault_stack:
                    v = vault_stack[-1]
                    if v[0] == len(comp_stack) + 1:
                        # this component IS the open vault: finalize with
                        # the sector-local position (same walk as stations)
                        vault_stack.pop()
                        vsector = ""
                        vsector_depth = -1
                        for i, (pcls, _pid, pmacro, _pp) in \
                                enumerate(comp_stack):
                            if pcls == "sector":
                                vsector, vsector_depth = pmacro, i
                        vx = own_pos[0] if own_pos else 0.0
                        vz = own_pos[1] if own_pos else 0.0
                        if vsector_depth >= 0:
                            for _c, _i2, _m, p in \
                                    comp_stack[vsector_depth + 1:]:
                                if p:
                                    vx += p[0]
                                    vz += p[1]
                        d.datavaults.append((
                            cid, macro, elem.get("code", ""),
                            elem.get("knownto", ""), vsector, vx, vz,
                            v[1], v[2], ",".join(v[3])))
                    elif v[0] <= len(comp_stack):
                        # a descendant of the open vault: uncollected loot
                        # (regular vaults hold collectablewares, Erlking
                        # ones also a collectableblueprints container)
                        bp = elem.get("blueprints", "")
                        if bp or clazz in ("collectablewares",
                                           "collectableblueprints"):
                            v[2] += 1
                            if bp:
                                v[3].extend(bp.split(","))

                if wormhole_stack and \
                        wormhole_stack[-1][0] == len(comp_stack) + 1:
                    # this component IS the open wormhole: finalize with its
                    # sector-local position (same offset walk as vaults)
                    rec = wormhole_stack.pop()[1]
                    wcluster = wsector = ""
                    wsector_depth = -1
                    for i, (pcls, _pid, pmacro, _pp) in enumerate(comp_stack):
                        if pcls == "cluster":
                            wcluster = pmacro
                        elif pcls == "sector":
                            wsector, wsector_depth = pmacro, i
                    wx = own_pos[0] if own_pos else 0.0
                    wz = own_pos[1] if own_pos else 0.0
                    if wsector_depth >= 0:
                        for _c, _i2, _m, p in comp_stack[wsector_depth + 1:]:
                            if p:
                                wx += p[0]
                                wz += p[1]
                    d.wormholes.append((
                        rec["id"], rec["macro"], rec["code"], rec["knownto"],
                        wcluster, wsector, wx, wz, rec["source_entry"],
                        rec["source_class"], rec["transition_dest"]))
                    for own_conn, role, target in rec["links"]:
                        d.wormhole_links.append(
                            (rec["id"], own_conn, role, target))

            elif tag == "connected":
                parent = elem.getparent()
                if (object_stack and parent is not None
                        and parent.tag == "connection"
                        and parent.get("connection") == "commander"):
                    d.commander_links.append(
                        (object_stack[-1], elem.get("connection", "")))
                # a wormhole's warp connection: <connection connection="origin"
                # id="[A]"><connected connection="[B]"/> — [B] is the partner
                # wormhole's connection id (resolved in frames)
                elif (wormhole_stack and parent is not None
                        and len(comp_stack) == wormhole_stack[-1][0]
                        and parent.tag == "connection"
                        and parent.get("connection") in ("origin",
                                                         "destination")):
                    wormhole_stack[-1][1]["links"].append((
                        parent.get("id", ""), parent.get("connection", ""),
                        elem.get("connection", "")))

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
                            m.group(2) or "", m.group(3) or "",
                            float(elem.get("starttime", 0) or 0),
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

            elif tag == "relation":
                # base <relation faction= relation=> under a faction's relations
                if faction_id_stack and elem.get("faction"):
                    d.faction_relations.append((
                        faction_id_stack[-1], elem.get("faction", ""),
                        float(elem.get("relation", 0) or 0)))

            elif tag == "booster":
                # <booster> appears under both <relations> (relation=, a
                # temporary standing modifier) and <discounts> (amount=, a
                # trade discount) — distinguished by the now-current parent
                if faction_id_stack and elem.get("faction"):
                    parent = tag_stack[-1] if tag_stack else ""
                    if parent == "relations":
                        d.faction_boosters.append((
                            faction_id_stack[-1], elem.get("faction", ""),
                            float(elem.get("relation", 0) or 0),
                            elem.get("time", "")))
                    elif parent == "discounts":
                        d.faction_discounts.append((
                            faction_id_stack[-1], elem.get("faction", ""),
                            float(elem.get("amount", 0) or 0),
                            elem.get("time", "")))

            elif tag == "licence":
                # rep-gated unlocks: <licence type= factions="a b c"/>
                if faction_id_stack and elem.get("type"):
                    d.faction_licences.append((
                        faction_id_stack[-1], elem.get("type", ""),
                        elem.get("factions", "")))

            elif tag == "account":
                # a faction's treasury: <account id= amount=>
                if faction_id_stack and elem.get("amount") is not None:
                    d.faction_accounts.append((
                        faction_id_stack[-1],
                        float(elem.get("amount", 0) or 0)))

            elif tag == "faction":
                if faction_id_stack and "factions" in tag_stack:
                    faction_id_stack.pop()
                if elem.get("id") == "player":
                    in_faction_player = max(0, in_faction_player - 1)

            # free memory: drop this element and any closed older siblings
            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                while elem.getprevious() is not None:
                    del parent[0]

    return data
