"""Sunburst plots (R lines 1213-1497)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..cli import log
from ..config import Config
from ..frames import Frames
from ..refdata import RefData
from .charts import SHIP_SERVICES
from .common import Sunburst, save_widget, with_alpha


def _faction_colour(ref: RefData, short: str, level: int) -> str:
    return with_alpha(ref.colour_of_short(str(short)), 255 - (level - 1) * 48)


def _owner_colour(ref: RefData, owner: str, level: int) -> str:
    return with_alpha(ref.faction_colour.get(str(owner), "#808080"),
                      255 - (level - 1) * 32)


def _money_sunburst(df: pd.DataFrame, levels: list[tuple[list[str], str]],
                    title: str, window_hours: float,
                    colour_fn=None) -> "pd.DataFrame":
    """Generic builder: `levels` is a list of (groupby columns, label column);
    each level nests inside the previous one. Values are summed money."""
    sb = Sunburst()
    total = float(df["money"].sum())
    sb.add_root("Total", total)
    for depth, (cols, label_col) in enumerate(levels, start=1):
        agg = df.groupby(cols, observed=True)["money"].sum().reset_index()
        if "amount" in df.columns and label_col == "__ships__":
            amounts = df.groupby(cols, observed=True)["amount"].sum().reset_index()
            agg = agg.merge(amounts, on=cols)
        for _, d in agg.iterrows():
            id_ = ">>".join(str(d[c]) for c in cols)
            parent = ">>".join(str(d[c]) for c in cols[:-1]) or "total"
            if label_col == "__ships__":
                label = f"{d['amount']} x<br>{d[cols[-1]]}"
            else:
                label = str(d[label_col])
            colour = colour_fn(d, depth) if colour_fn else None
            if d["money"] > 0:
                sb.add(id_, label, parent, float(d["money"]), colour)
    sb.annotate_money(total, window_hours)
    return sb.figure(title)


def build_sunbursts(frames: Frames, ref: RefData, cfg: Config,
                    files_dir: Path, guid: str) -> list[str]:
    out: list[str] = []
    time_limit = frames.time_now - 3600 * cfg.history_hours
    window = (frames.time_now - time_limit) / 3600.0
    hh = f"{cfg.history_hours:g}h"
    station_codes = set(frames.stations["code"]) if not frames.stations.empty \
        else set()

    def emit(fig, title):
        out.append(save_widget(fig, files_dir, title, guid))

    sales, buys = frames.sales, frames.buys

    # -- ship sales (R 1222-1258) -------------------------------------------
    df = sales[(sales["time"] > time_limit) & (sales["money"] > 0)
               & (sales["commodity"] == "Ship construction")].copy()
    if not df.empty:
        df["buyer.faction"] = df["buyer.faction"].astype(str)
        title = f"{hh} Ship Sales per Wharf"
        log("->", title)
        emit(_money_sunburst(
            df, [(["seller.name"], "seller.name"),
                 (["seller.name", "buyer.faction"], "buyer.faction"),
                 (["seller.name", "buyer.faction", "buyer.name"], "__ships__")],
            title, window,
            colour_fn=lambda d, lvl: None if lvl == 1
            else _faction_colour(ref, d["buyer.faction"], lvl - 1)), title)

        title = f"{hh} Ship Sales per Faction"
        log("->", title)
        emit(_money_sunburst(
            df, [(["buyer.faction"], "buyer.faction"),
                 (["buyer.faction", "buyer.name"], "__ships__")],
            title, window,
            colour_fn=lambda d, lvl: _faction_colour(
                ref, d["buyer.faction"], lvl)), title)

    # -- commodity sales (R 1260-1299) ---------------------------------------
    df = sales[(sales["time"] > time_limit) & (sales["money"] > 0)
               & ~sales["commodity"].isin(SHIP_SERVICES)].copy()
    if not df.empty:
        df["buyer.faction"] = df["buyer.faction"].astype(str)
        name = df["seller.name"].astype(str)
        outside = ~df["seller.code"].isin(station_codes)
        df["seller.name"] = name.where(~outside,
                                       name + " (" + df["seller.code"].astype(str)
                                       + ")")
        title1 = f"{hh} Commodity Sales by Faction"
        log("->", title1)
        emit(_money_sunburst(
            df, [(["buyer.faction"], "buyer.faction"),
                 (["buyer.faction", "seller.name"], "seller.name"),
                 (["buyer.faction", "seller.name", "commodity"], "commodity")],
            title1, window,
            colour_fn=lambda d, lvl: _faction_colour(
                ref, d["buyer.faction"], lvl)), title1)

        title2 = f"{hh} Commodity Sales by Commodity"
        log("->", title2)
        emit(_money_sunburst(
            df, [(["commodity"], "commodity"),
                 (["commodity", "seller.name"], "seller.name"),
                 (["commodity", "seller.name", "buyer.faction"],
                  "buyer.faction")],
            title2, window), title2)

    # -- commodity buys (R 1302-1345) ----------------------------------------
    df = buys[(buys["time"] > time_limit) & (buys["money"] < 0)].copy()
    if not df.empty:
        df["money"] = -df["money"]
        df["seller.faction"] = df["seller.faction"].astype(str)
        name = df["buyer.name"].astype(str)
        outside = ~df["buyer.code"].isin(station_codes)
        df["buyer.name"] = name.where(~outside,
                                      name + " (" + df["buyer.code"].astype(str)
                                      + ")")
        title = f"{hh} Commodity Buys by Commodity"
        log("->", title)
        emit(_money_sunburst(
            df, [(["commodity"], "commodity"),
                 (["commodity", "buyer.name"], "buyer.name"),
                 (["commodity", "buyer.name", "seller.faction"],
                  "seller.faction")],
            title, window), title)

        title = f"{hh} Commodity Buys by Buyer"
        log("->", title)
        emit(_money_sunburst(
            df, [(["buyer.name"], "buyer.name"),
                 (["buyer.name", "commodity"], "commodity"),
                 (["buyer.name", "commodity", "seller.faction"],
                  "seller.faction")],
            title, window), title)

    # -- sector resources (R 1353-1385), spoiler-gated ------------------------
    if not cfg.spoilers_hide and frames.resource_cols:
        melted = frames.sectors.melt(
            id_vars=["id", "owner", "name"], value_vars=frames.resource_cols,
            var_name="resource", value_name="value").dropna(subset=["value"])
        melted = melted[melted["value"] > 0]
        totals = melted.groupby("resource")["value"].sum()
        melted["percentage"] = (10000.0 * melted["value"]
                                / melted["resource"].map(totals)).round()
        melted = melted[melted["percentage"] > 0]

        title = "Total Sector resources per Resource"
        log("->", title)
        sb = Sunburst()
        res_tot = melted.groupby("resource")["percentage"].sum()
        sb.add_root("Mining<br>Resources", float(res_tot.sum()), id_="root")
        for resource, val in res_tot.items():
            sb.add(str(resource), ref.ware_name.get(str(resource), str(resource)),
                   "root", float(val))
        for row in melted.itertuples(index=False):
            sb.add(f"{row.resource}>>{row.id}",
                   f"{row.name}<br>{0.01 * row.percentage:g} %",
                   str(row.resource), float(row.percentage))
        emit(sb.figure(title), title)

        title = "Resource availability per Sector"
        log("->", title)
        sb = Sunburst()
        sb.add_root("Resource availability<br>by Sector owner",
                    float(melted["percentage"].sum()), id_="root")
        by_owner = melted.groupby("owner")["percentage"].sum()
        for owner, val in by_owner.items():
            sb.add(str(owner), ref.faction_short.get(str(owner), "OTH"),
                   "root", float(val), _owner_colour(ref, owner, 1))
        by_sector = melted.groupby(["owner", "id", "name"]
                                   )["percentage"].sum().reset_index()
        for row in by_sector.itertuples(index=False):
            sb.add(str(row.id), str(row.name), str(row.owner),
                   float(row.percentage), _owner_colour(ref, row.owner, 2))
        for row in melted.itertuples(index=False):
            sb.add(f"{row.id}>>{row.resource}",
                   f"{ref.ware_name.get(str(row.resource), row.resource)}"
                   f"<br>{0.01 * row.percentage:g} %",
                   str(row.id), float(row.percentage),
                   _owner_colour(ref, row.owner, 3))
        emit(sb.figure(title), title)

    # -- universe composition (R 1387-1460) -----------------------------------
    sec = frames.sectors.set_index("macro")
    known_sectors = set(
        frames.sectors.loc[frames.sectors["knownto"] == "player", "macro"])

    def universe_subset(mask):
        df = frames.universe[mask].copy()
        if cfg.spoilers_hide:
            df = df[(df["knownto"] == "player")
                    & df["sector.macro"].isin(known_sectors)]
        df["faction"] = df["owner"].map(ref.faction_short).fillna("OTH")
        df["sector.name"] = df["sector.macro"].map(sec["name"])
        df["sector.owner"] = (df["sector.macro"].map(sec["owner"])
                              .map(ref.faction_short).fillna("OTH"))
        return df.dropna(subset=["sector.name"])

    def composition_sunburst(df, value_col, title, root_label,
                             by_faction_first=False, with_size=False):
        sb = Sunburst()
        sb.add_root(root_label, float(df[value_col].sum()), id_="root")
        first = "faction" if by_faction_first else "sector.owner"
        lvl1 = df.groupby(first, observed=True)[value_col].sum()
        for key, val in lvl1.items():
            sb.add(str(key), str(key), "root", float(val),
                   _faction_colour(ref, key, 1))
        group2 = [first, "sector.name"]
        lvl2 = df.groupby(group2, observed=True).agg(
            value=(value_col, "sum"),
            colour_key=("sector.owner", "first")).reset_index()
        for row in lvl2.itertuples(index=False):
            sb.add(f"{row[0]} {row[1]}", str(row[1]), str(row[0]),
                   float(row.value), _faction_colour(ref, row.colour_key, 1))
        group3 = group2 + (["faction"] if not by_faction_first else ["size"])
        lvl3 = df.groupby(group3, observed=True)[value_col].sum().reset_index()
        for row in lvl3.itertuples(index=False):
            sb.add(f"{row[2]} {row[0]} {row[1]}", str(row[2]),
                   f"{row[0]} {row[1]}", float(row[3]),
                   _faction_colour(ref, row[2] if not by_faction_first
                                   else row[0], 1))
        if with_size and not by_faction_first:
            group4 = group3 + ["size"]
            lvl4 = df.groupby(group4, observed=True)[value_col].sum().reset_index()
            for row in lvl4.itertuples(index=False):
                sb.add(f"{row[3]} {row[2]} {row[0]} {row[1]}", str(row[3]),
                       f"{row[2]} {row[0]} {row[1]}", float(row[4]),
                       _faction_colour(ref, row[2], 1))
        return sb.figure(title)

    title = "Station modules per sector"
    log("->", title)
    st = universe_subset(frames.universe["class"] == "station")
    st["modules"] = pd.to_numeric(st["modules"], errors="coerce").fillna(1)
    emit(composition_sunburst(st, "modules", title,
                              "Station modules<br>per sector"), title)

    title = "Ship hull mass per sector"
    log("->", title)
    sh = universe_subset(frames.universe["class"].str.contains("ship"))
    sh["size"] = sh["class"].str.replace("ship_", "").str.upper()
    sh = sh[sh["size"] != "XS"]
    mass_map = dict(zip(ref.ships["macro"], ref.ships["mass"]))
    sh["value"] = pd.to_numeric(sh["macro"].map(mass_map),
                                errors="coerce").fillna(1.0)
    emit(composition_sunburst(sh, "value", title,
                              "Ship hull mass<br>per sector", with_size=True),
         title)

    title = "Activity per faction"
    log("->", title)
    act = universe_subset(
        (frames.universe["class"] == "station")
        | frames.universe["class"].str.contains("ship"))
    act["size"] = (act["class"].str.replace("ship_", "").str.upper()
                   .where(act["class"] != "station", "STATION"))
    act = act[act["size"] != "XS"]
    act["value"] = pd.to_numeric(act["macro"].map(mass_map), errors="coerce")
    station_mass = pd.to_numeric(act["mass"], errors="coerce") / 10.0
    act.loc[act["size"] == "STATION", "value"] = station_mass
    act["value"] = act["value"].fillna(1.0)
    emit(composition_sunburst(act, "value", title, "Activity<br>per faction",
                              by_faction_first=True), title)

    # -- fleet composition (R 1462-1497) --------------------------------------
    if not frames.wings.empty:
        title = "Fleet Compositions"
        log("->", title)
        emit(_fleet_sunburst(frames, ref, title), title)
    return out


def _fleet_sunburst(frames: Frames, ref: RefData, title: str):
    sectors = frames.sectors.set_index("id")
    wings, ships, stations = frames.wings, frames.ships, frames.stations
    sb = Sunburst()

    def sector_colour(sector_id, level):
        owner = sectors["owner"].get(sector_id, "")
        return _owner_colour(ref, owner, level)

    used_sectors = frames.playerowned["sector.id"].unique()
    for sid in used_sectors:
        name = sectors["name"].get(sid)
        owner = sectors["owner"].get(sid, "")
        if pd.isna(name):
            label = f"{owner} owned" if owner and owner != "ownerless" \
                else "unowned"
        else:
            label = str(name)
        if sectors["contested"].get(sid, 0) == 1:
            label += "<br><b>CONTESTED</b>"
        sb.add(str(sid), label, "", 0, sector_colour(sid, 1))

    leaders = set(wings["leader"])
    followers = set(wings["follower"])

    tops = []
    for df, unnamed in ((stations, "Unnamed Station"), (ships, None)):
        if df.empty:
            continue
        top = df[df["id"].isin(leaders) & ~df["id"].isin(followers)]
        for _, d in top.iterrows():
            name = d["name"] if pd.notna(d["name"]) else (unnamed or d["macro"])
            sb.add(str(d["id"]), f"{name}<br>{d['code']}", str(d["sector.id"]),
                   0, sector_colour(d["sector.id"], 2))
            tops.append(d["id"])

    # walk down the hierarchy
    ships_by_id = ships.set_index("id")
    frontier = list(tops)
    level = 3
    while frontier:
        nxt = []
        for _, w in wings[wings["leader"].isin(frontier)].iterrows():
            fid = w["follower"]
            if fid not in ships_by_id.index:
                continue
            srow = ships_by_id.loc[fid]
            sb.add(str(fid), f"{srow['name']}<br>{srow['code']}",
                   str(w["leader"]), 0,
                   sector_colour(srow["sector.id"], min(level, 6)))
            nxt.append(fid)
        frontier = nxt
        level += 1
        if level > 12:
            break

    # ships outside any fleet hang directly under their sector
    solo = ships[~ships["id"].isin(leaders) & ~ships["id"].isin(followers)]
    for _, d in solo.iterrows():
        sb.add(str(d["id"]), f"{d['name']}<br>{d['code']}", str(d["sector.id"]),
               0, sector_colour(d["sector.id"], 2))

    return sb.figure(title, maxdepth=3, values=False)
