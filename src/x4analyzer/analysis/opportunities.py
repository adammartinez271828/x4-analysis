"""Pairwise ware arbitrage from open trade offers (Market tab section).

For every ware with both open sell and buy offers, pair the cheapest asks
with the highest bids and quote the spread per unit, per m³ of cargo hold
(what a full trip earns — high per-unit profit on a bulky ware can trail a
cheap dense one) and per m³ per gate jump (the feasible proxy for trip
time; highways make it approximate and it is labeled as such).

Player-owned endpoints transact at 0 Cr: buying from an own station costs
the empire nothing (seller side — the full bid is profit), "selling" to an
own station earns nothing (buyer side). With that one rule NPC→player and
player→player pairs go non-positive and drop out on the spread filter,
matching the intended semantics without special cases.

Quoted prices are one point on the game's price curve — a large trade
moves the price against the trader — so every pair carries its depth
(min of the two offer amounts) and the client caps per-trip figures by
hold size and depth rather than extrapolating the quote.
"""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..gamedata.refdata import RefData
from .frames import Frames
from .sectorgraph import build_adjacency, bfs_distances

# Xenon neither buy nor sell on the market (harvest-only economy); same
# exclusion the rest of the Market tab applies
EXCLUDED_OWNERS = {"xenon"}

TOP_N = 15       # cheapest asks / highest bids considered per ware
MAX_PAIRS = 25   # pairs kept per ware, ranked by the per-m³-per-jump rate


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
    off["faction"] = fac
    off["label"] = (name.fillna(fac + " " + base)
                    + " (" + off["id"].map(endpoints["code"]).fillna("?")
                    + ")")
    off["sector"] = off["id"].map(endpoints["sector.macro"])
    off["secname"] = off["sector"].map(sec_name).fillna("?")
    off["bs"] = (off["id"].map(endpoints["class"]) == "buildstorage") \
        .astype(int)

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
    dist_cache: dict[str, dict[str, int]] = {}

    def jumps(a: str, b: str) -> int | None:
        if a not in dist_cache:
            dist_cache[a] = bfs_distances(adj, a)
        return dist_cache[a].get(b)

    def endpoint(r) -> dict:
        d = {"l": str(r["label"]), "f": str(r["faction"]),
             "sec": str(r["secname"]), "amt": float(r["amount"]),
             "price": round(float(r["price"]) , 2)}
        if r["player"]:
            d["p"] = 1
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
                    "du": du,
                    "dm3": round(du * vol, 1),
                    "total": round(du * spread, 0),
                })
        pairs.sort(key=lambda p: p["rate"], reverse=True)
        rows.extend(pairs[:MAX_PAIRS])
    rows.sort(key=lambda p: p["rate"], reverse=True)
    return rows


def ship_presets(ref: RefData) -> list[dict]:
    """Container-capable trade ships for the hold-size what-if control:
    one entry per model (largest cargo variant), sorted by hold size."""
    sh = ref.ships
    sh = sh[(pd.to_numeric(sh["cargo"], errors="coerce").fillna(0) > 0)
            & sh["cargo_tags"].fillna("").str.contains("container")]
    if sh.empty:
        return []
    sh = sh.assign(cargo=pd.to_numeric(sh["cargo"], errors="coerce"))
    sh = (sh.sort_values("cargo", ascending=False)
          .drop_duplicates(subset=["model"]))
    return [{"m": str(r["model"]), "cls": str(r["class"]),
             "cargo": float(r["cargo"])}
            for _, r in sh.iterrows()
            if str(r["model"]) not in ("", "nan")]
