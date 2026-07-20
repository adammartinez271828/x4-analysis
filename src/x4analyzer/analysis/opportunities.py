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


class _Router:
    """Route lengths between stations: BFS shortest-hop path over the
    sector graph, legs measured through the actual gate positions
    (gates.csv endpoint offsets; same-cluster superhighway links without
    a gates row fall back to sector centres). Returns (km_plain, km_hw)
    with each leg attributed by its sector's local-highway flag."""

    def __init__(self, ref: RefData):
        self.adj = build_adjacency(ref)
        self.edge_pos: dict[tuple, tuple] = {}
        has_pts = {"ax", "az", "bx", "bz"} <= set(ref.gates.columns)
        for r in ref.gates.itertuples(index=False):
            a, b = str(r.sector_a), str(r.sector_b)
            pa = (float(r.ax), float(r.az)) if has_pts else (0.0, 0.0)
            pb = (float(r.bx), float(r.bz)) if has_pts else (0.0, 0.0)
            self.edge_pos.setdefault((a, b), (pa, pb))
            self.edge_pos.setdefault((b, a), (pb, pa))
        self.hw = dict(zip(ref.sectors["macro"],
                           ref.sectors.get("highway", 0)))
        self._paths: dict[str, dict] = {}

    def _prev(self, start: str) -> dict:
        if start not in self._paths:
            prev: dict[str, str | None] = {start: None}
            queue = [start]
            while queue:
                cur = queue.pop(0)
                for nxt in self.adj.get(cur, ()):
                    if nxt not in prev:
                        prev[nxt] = cur
                        queue.append(nxt)
            self._paths[start] = prev
        return self._paths[start]

    def _gate(self, a: str, b: str) -> tuple:
        return self.edge_pos.get((a, b), ((0.0, 0.0), (0.0, 0.0)))

    def legs_km(self, sa: str, pa: tuple, sb: str,
                pb: tuple) -> tuple[float, float] | None:
        """(km_plain, km_hw) from station at `pa` in sector `sa` to
        station at `pb` in `sb`; None when unreachable."""
        def dist(p, q):
            return math.hypot(p[0] - q[0], p[1] - q[1]) / 1000.0

        def add(acc, sector, p, q):
            acc[1 if self.hw.get(sector) else 0] += dist(p, q)

        acc = [0.0, 0.0]
        if sa == sb:
            add(acc, sa, pa, pb)
            return acc[0], acc[1]
        prev = self._prev(sa)
        if sb not in prev:
            return None
        path = [sb]
        while path[-1] != sa:
            path.append(prev[path[-1]])
        path.reverse()
        # first leg: station -> exit gate; middle: entry -> exit gate;
        # last: entry gate -> station
        add(acc, sa, pa, self._gate(path[0], path[1])[0])
        for i in range(1, len(path) - 1):
            add(acc, path[i], self._gate(path[i - 1], path[i])[1],
                self._gate(path[i], path[i + 1])[0])
        add(acc, sb, self._gate(path[-2], path[-1])[1], pb)
        return acc[0], acc[1]


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
                km = router.legs_km(str(s["sector"]), (s["sx"], s["sz"]),
                                    str(b["sector"]), (b["sx"], b["sz"]))
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
                    # route length, plain-space vs local-highway sectors
                    "kp": round(km[0], 1) if km else None,
                    "kh": round(km[1], 1) if km else None,
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

    out: list[dict] = []
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
        out.append({
            "l": label + (" (" + code + ")" if code else ""),
            "model": str(m["model"]), "cls": str(m["class"]),
            "cargo": float(cargo), "speed": speed,
        })
    out.sort(key=lambda s: s["l"].lower())
    return out
