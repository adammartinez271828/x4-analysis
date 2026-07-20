"""Pairwise ware arbitrage from open trade offers (Market tab section).

For every ware with both open sell and buy offers, pair the cheapest asks
with the highest bids and quote the spread per unit, per m³ of cargo hold
(what a full trip earns — high per-unit profit on a bulky ware can trail a
cheap dense one) and per m³ per gate jump. Each lane also carries its real
route length in km — legs measured between the stations' sector-local
positions and the actual gate positions along the BFS path — split into
plain-space km and km inside local-highway sectors, so the client can turn
a ship's travel speed into a trip time (S/M ships ride highways at an
assumed average; L/XL fly everything).

Player-owned endpoints transact at 0 Cr: buying from an own station costs
the empire nothing (seller side — the full bid is profit), "selling" to an
own station earns nothing (buyer side). With that one rule NPC→player and
player→player pairs go non-positive and drop out on the spread filter,
matching the intended semantics without special cases. Quettanaut (kaori)
endpoints are flagged: they barter instead of trading credits, so their
lanes are excluded by default in the UI.

Quoted prices are one point on the game's price curve — a large trade
moves the price against the trader — so every pair carries its depth
(min of the two offer amounts) and the client caps per-trip figures by
hold size and depth rather than extrapolating the quote.
"""

from __future__ import annotations

import math

import pandas as pd

from ..config import Config
from ..gamedata.refdata import RefData
from .frames import Frames
from .sectorgraph import build_adjacency, bfs_distances

# Xenon neither buy nor sell on the market (harvest-only economy); same
# exclusion the rest of the Market tab applies
EXCLUDED_OWNERS = {"xenon"}
# barter-only faction (X4: Timelines): flagged per endpoint, UI-excluded
BARTER_OWNERS = {"kaori"}

TOP_N = 15       # cheapest asks / highest bids considered per ware
MAX_PAIRS = 25   # pairs kept per ware, ranked by the per-m³-per-jump rate


# highway-sector km cost this fraction of plain km when routing an S/M
# ship: ~10 km/s on the ring vs ~1 km/s effective travel speed. Only the
# RATIO steers the path choice, so one representative value covers all
# S/M ships and the km split stays ship-independent.
_SM_HW_COST = 0.1


class _Router:
    """Route lengths between stations over a gate graph: nodes are the
    actual gate endpoints (gates.csv offsets; same-cluster superhighway
    links without a gates row get synthetic portals at the sector
    centres), in-sector edges join every gate pair, portal transits are
    free. Dijkstra minimizes TIME, not hops — validated against player
    trader logs, where shortest-hop paths through the dense core ran
    ~15-20%% long — with highway-sector km discounted for S/M routing.
    Returns (km_plain, km_hw), each leg attributed by its sector's
    local-highway flag."""

    def __init__(self, ref: RefData):
        self.hw = dict(zip(ref.sectors["macro"],
                           ref.sectors.get("highway", 0)))
        self.sector: list[str] = []     # node -> sector macro
        self.pos: list[tuple] = []      # node -> (x, z) metres
        self.by_sector: dict[str, list[int]] = {}
        self.portals: list[tuple] = []  # (node_i, node_j) free transits

        def node(sector: str, p: tuple) -> int:
            i = len(self.sector)
            self.sector.append(sector)
            self.pos.append(p)
            self.by_sector.setdefault(sector, []).append(i)
            return i

        has_pts = {"ax", "az", "bx", "bz"} <= set(ref.gates.columns)
        linked: set[tuple] = set()
        for r in ref.gates.itertuples(index=False):
            a, b = str(r.sector_a), str(r.sector_b)
            pa = (float(r.ax), float(r.az)) if has_pts else (0.0, 0.0)
            pb = (float(r.bx), float(r.bz)) if has_pts else (0.0, 0.0)
            self.portals.append((node(a, pa), node(b, pb)))
            linked.update([(a, b), (b, a)])
        # belt-and-braces like build_adjacency: same-cluster pairs are
        # mutually reachable even without an extracted sechighway row
        for _cl, grp in ref.sectors.groupby("cluster"):
            macros = list(grp["macro"])
            for i, a in enumerate(macros):
                for b in macros[i + 1:]:
                    if (a, b) not in linked:
                        self.portals.append(
                            (node(a, (0.0, 0.0)), node(b, (0.0, 0.0))))
        self.portal_of: dict[int, list[int]] = {}
        for i, j in self.portals:
            self.portal_of.setdefault(i, []).append(j)
            self.portal_of.setdefault(j, []).append(i)
        self._cache: dict[tuple, tuple | None] = {}

    def _w(self, sector: str, sm: bool) -> float:
        return _SM_HW_COST if sm and self.hw.get(sector) else 1.0

    @staticmethod
    def _dist(p, q) -> float:
        return math.hypot(p[0] - q[0], p[1] - q[1]) / 1000.0

    def route_km(self, sa: str, pa: tuple, sb: str, pb: tuple,
                 sm: bool) -> tuple[float, float] | None:
        """(km_plain, km_hw) of the time-optimal route from station `pa`
        in sector `sa` to station `pb` in `sb` under S/M (`sm`) or L/XL
        cost weights; None when unreachable."""
        if sa == sb:
            d = self._dist(pa, pb)
            return (0.0, d) if self.hw.get(sa) else (d, 0.0)
        key = (sa, pa, sm)
        if key not in self._cache:
            self._cache[key] = self._dijkstra_all(sa, pa, sm)
        best, split = self._cache[key]
        goal = None
        for n in self.by_sector.get(sb, ()):
            if n not in best:
                continue
            d = self._dist(self.pos[n], pb)
            total = best[n] + d * self._w(sb, sm)
            if goal is None or total < goal[0]:
                kp, kh = split[n]
                if self.hw.get(sb):
                    kh += d
                else:
                    kp += d
                goal = (total, kp, kh)
        if goal is None:
            return None
        return round(goal[1], 4), round(goal[2], 4)

    def _dijkstra_all(self, sa: str, pa: tuple, sm: bool) -> tuple:
        """Single-source relaxation over the whole gate graph: node ->
        (cost, (km_plain, km_hw)) along the cheapest route. One run per
        distinct seller station serves every buyer."""
        import heapq
        best: dict[int, float] = {}
        split: dict[int, tuple] = {}
        heap = []
        for n in self.by_sector.get(sa, ()):
            d = self._dist(pa, self.pos[n])
            sp = (0.0, d) if self.hw.get(sa) else (d, 0.0)
            heapq.heappush(heap, (d * self._w(sa, sm), n, sp))
        while heap:
            cost, n, sp = heapq.heappop(heap)
            if n in best and best[n] <= cost:
                continue
            best[n] = cost
            split[n] = sp
            # free portal transit to the twin endpoint(s), then in-sector
            # hops from there to every gate of the arrival sector
            for m in self.portal_of.get(n, ()):
                msec = self.sector[m]
                for k in self.by_sector[msec]:
                    d = self._dist(self.pos[m], self.pos[k]) if k != m \
                        else 0.0
                    c2 = cost + d * self._w(msec, sm)
                    if k in best and best[k] <= c2:
                        continue
                    kp, kh = sp
                    if self.hw.get(msec):
                        kh += d
                    else:
                        kp += d
                    heapq.heappush(heap, (c2, k, (kp, kh)))
        return best, split


def build_opportunities(frames: Frames, ref: RefData,
                        cfg: Config) -> list[dict]:
    off = frames.trade_offers
    uni = frames.universe
    if off is None or off.empty or uni.empty:
        return []
    uni = uni.set_index("id")

    endpoints = uni[(uni["class"].isin(["station", "buildstorage"]))
                    & ~uni["owner"].isin(EXCLUDED_OWNERS)]
    if cfg.spoilers_hide:
        endpoints = endpoints[endpoints["knownto"] == "player"]

    off = off[off["id"].isin(endpoints.index) & (off["amount"] > 0)].copy()
    if off.empty:
        return []

    vol_map = dict(zip(
        ref.wares["id"],
        pd.to_numeric(ref.wares["volume"], errors="coerce").fillna(0.0)))
    sec_name = dict(zip(frames.sectors["macro"], frames.sectors["name"]))

    owner = off["id"].map(endpoints["owner"])
    fac = owner.map(ref.faction_short).fillna("OTH")
    fac = fac.where(owner != "player", "PLA")
    name = off["id"].map(endpoints["name"]).replace("", pd.NA)
    base = off["id"].map(endpoints["stype"]).replace("", pd.NA) \
        .fillna("Station")
    off["player"] = (owner == "player").astype(int)
    off["barter"] = owner.isin(BARTER_OWNERS).astype(int)
    off["faction"] = fac
    off["label"] = (name.fillna(fac + " " + base)
                    + " (" + off["id"].map(endpoints["code"]).fillna("?")
                    + ")")
    off["sector"] = off["id"].map(endpoints["sector.macro"])
    off["secname"] = off["sector"].map(sec_name).fillna("?")
    off["bs"] = (off["id"].map(endpoints["class"]) == "buildstorage") \
        .astype(int)
    for c in ("sx", "sz"):
        off[c] = pd.to_numeric(off["id"].map(endpoints[c]),
                               errors="coerce").fillna(0.0)

    # effective prices: player endpoints transact at 0 Cr (see module doc);
    # zero-priced NPC offers are junk rows, not free goods
    sells = off[(off["side"] == "sell") & (off["bs"] == 0)
                & ((off["price"] > 0) | (off["player"] == 1))].copy()
    buys = off[(off["side"] == "buy") & (off["price"] > 0)].copy()
    sells["eff"] = sells["price"].where(sells["player"] == 0, 0.0)
    buys["eff"] = buys["price"].where(buys["player"] == 0, 0.0)
    if sells.empty or buys.empty:
        return []

    adj = build_adjacency(ref)
    router = _Router(ref)
    dist_cache: dict[str, dict[str, int]] = {}

    def jumps(a: str, b: str) -> int | None:
        if a not in dist_cache:
            dist_cache[a] = bfs_distances(adj, a)
        return dist_cache[a].get(b)

    def endpoint(r) -> dict:
        d = {"l": str(r["label"]), "f": str(r["faction"]),
             "sec": str(r["secname"]), "amt": float(r["amount"]),
             "price": round(float(r["price"]), 2)}
        if r["player"]:
            d["p"] = 1
        if r["barter"]:
            d["qt"] = 1
        if r.get("bs"):
            d["c"] = 1   # construction site buyer
        return d

    rows: list[dict] = []
    for ware, sgrp in sells.groupby("ware"):
        vol = vol_map.get(ware, 0.0)
        if vol <= 0:
            continue
        bgrp = buys[buys["ware"] == ware]
        if bgrp.empty:
            continue
        sgrp = sgrp.nsmallest(TOP_N, "eff")
        bgrp = bgrp.nlargest(TOP_N, "eff")
        pairs: list[dict] = []
        for _, s in sgrp.iterrows():
            for _, b in bgrp.iterrows():
                spread = float(b["eff"]) - float(s["eff"])
                if spread <= 0:
                    continue
                j = jumps(str(s["sector"]), str(b["sector"]))
                if j is None:   # disconnected (modded galaxy): not flyable
                    continue
                km = router.route_km(str(s["sector"]), (s["sx"], s["sz"]),
                                     str(b["sector"]), (b["sx"], b["sz"]),
                                     sm=False)
                km_s = router.route_km(str(s["sector"]), (s["sx"], s["sz"]),
                                       str(b["sector"]), (b["sx"], b["sz"]),
                                       sm=True)
                du = min(float(s["amount"]), float(b["amount"]))
                pairs.append({
                    "w": ware,
                    "wn": ref.ware_name.get(ware, ware),
                    "vol": vol,
                    "s": endpoint(s), "b": endpoint(b),
                    "ask": round(float(s["eff"]), 2),
                    "bid": round(float(b["eff"]), 2),
                    "spread": round(spread, 2),
                    "pm3": round(spread / vol, 2),
                    "j": j,
                    # same-sector runs count as one hop: a trip still
                    # happens, and rate stays finite/sortable
                    "rate": round(spread / vol / max(1, j), 2),
                    # route length, plain-space vs local-highway sectors;
                    # kps/khs = the S/M-optimal route (highway km cheap)
                    # when it differs from the km-shortest L/XL one
                    "kp": round(km[0], 1) if km else None,
                    "kh": round(km[1], 1) if km else None,
                    **({"kps": round(km_s[0], 1),
                        "khs": round(km_s[1], 1)}
                       if km_s and km and
                       (abs(km_s[0] - km[0]) > 0.5
                        or abs(km_s[1] - km[1]) > 0.5) else {}),
                    "du": du,
                    "dm3": round(du * vol, 1),
                    "total": round(du * spread, 0),
                })
        pairs.sort(key=lambda p: p["rate"], reverse=True)
        rows.extend(pairs[:MAX_PAIRS])
    rows.sort(key=lambda p: p["rate"], reverse=True)
    return rows


def player_trade_ships(frames: Frames, ref: RefData) -> list[dict]:
    """The player's container-capable ships with their ACTUAL loadout
    travel speed: Σ(mounted engines × forward thrust × travel multiplier)
    ÷ the hull's forward drag (the in-game encyclopedia formula). Ships
    whose engines or hull aren't in the reference data get speed None."""
    uni = frames.universe
    engines = getattr(frames, "ship_engines", None)
    if uni is None or uni.empty:
        return []
    ships = uni[uni["class"].str.startswith("ship_")
                & (uni["class"] != "ship_xs")
                & (uni["owner"] == "player")]
    if ships.empty:
        return []

    ref_ships = ref.ships.set_index("macro")
    eng = ref.engines
    eng_travel = {}
    if eng is not None and not eng.empty:
        eng_travel = {
            r["macro"]: (float(r["forward"]) * float(r["travel_thrust"]))
            for _, r in eng.iterrows()
            if pd.notna(r["forward"]) and pd.notna(r["travel_thrust"])}
    mounts: dict[str, list] = {}
    if engines is not None and not engines.empty:
        for _, r in engines.iterrows():
            mounts.setdefault(str(r["id"]), []).append(
                (str(r["macro"]), int(r["n"])))

    # ships with identical model/size/hold/speed are interchangeable for
    # the what-if: roll them into one entry with a count instead of
    # listing every hull of a same-loadout freighter fleet
    groups: dict[tuple, dict] = {}
    for _, r in ships.iterrows():
        macro = str(r["macro"]).lower()
        if macro not in ref_ships.index:
            continue
        m = ref_ships.loc[macro]
        cargo = pd.to_numeric(m["cargo"], errors="coerce")
        tags = str(m["cargo_tags"] or "")
        if not (cargo > 0) or "container" not in tags:
            continue
        speed = None
        drag = pd.to_numeric(m.get("drag_forward"), errors="coerce")
        thrust = sum(eng_travel.get(em, 0.0) * n
                     for em, n in mounts.get(str(r["id"]), []))
        if thrust > 0 and pd.notna(drag) and drag > 0:
            speed = round(thrust / float(drag))
        label = str(r["name"]) or str(m["model"])
        code = str(r["code"] or "")
        key = (str(m["model"]), str(m["class"]), float(cargo), speed)
        g = groups.setdefault(key, {
            "l": (label + (" (" + code + ")" if code else "")
                  + " — " + key[0]),
            "model": key[0], "cls": key[1],
            "cargo": key[2], "speed": speed, "n": 0,
        })
        g["n"] += 1
    out = list(groups.values())
    for g in out:
        if g["n"] > 1:
            g["l"] = g["model"] + " ×" + str(g["n"])
    out.sort(key=lambda s: s["l"].lower())
    return out
