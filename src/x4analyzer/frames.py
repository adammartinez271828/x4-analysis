"""Builds the analysis dataframes from a parsed savegame.

Faithful port of the df.* logic in X4SaveGameAnalysis.R (line references in
comments). Column names keep the R script's dotted style so anyone familiar
with the original finds their way around.

World-state and stock-delta frames read from the analysis database
(store.py writes it before this runs); SQL NULLs are normalized back to the
frames' historic empty-string convention so downstream code is unchanged.
The log/tradelog frames still come from the csv.gz caches while those are
dual-written (see caches.py).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from . import logparse
from .caches import merge_log_cache, merge_tradelog_cache
from .cli import log
from .config import Config
from .refdata import OTHER_FACTION, RefData, SHIP_SIZES
from .saveparser import SaveData


@dataclass
class Frames:
    universe: pd.DataFrame
    sectors: pd.DataFrame
    playerowned: pd.DataFrame
    wings: pd.DataFrame
    npcs: pd.DataFrame
    stations: pd.DataFrame
    ships: pd.DataFrame
    log: pd.DataFrame
    tradelog: pd.DataFrame
    sales: pd.DataFrame
    buys: pd.DataFrame
    destroyed: pd.DataFrame
    transfers: pd.DataFrame
    pirates: pd.DataFrame
    police: pd.DataFrame

    # all stations' construction entries: id, index, macro (market analysis)
    # NOTE: includes planned-but-unbuilt entries (station sequences list the
    # whole plan; build storages carry expansion plans) — use built_modules
    # for anything measuring existing capacity/value
    station_modules: pd.DataFrame = None
    # universe-wide economylog events (owner/ware/volume, all factions)
    global_trades: pd.DataFrame = None
    # per-object cargo, workforce and pending construction resources
    station_cargo: pd.DataFrame = None       # id, ware, amount
    workforce_all: pd.DataFrame = None       # id, race, amount
    build_demand: pd.DataFrame = None        # id, ware, amount, kind (missing)
    trade_offers: pd.DataFrame = None        # id, side, ware, amount, price
    orders: pd.DataFrame = None              # id, order, default, state
    built_refs: set = None                   # constructed sequence-entry ids
    module_upgrades: pd.DataFrame = None     # entry, macro (planned loadouts)

    @property
    def built_modules(self) -> pd.DataFrame:
        """station_modules restricted to entries whose module actually
        exists (a component references the entry and is out of
        construction); entries without ids are kept defensively. The flag
        is resolved at database load time (v_built_module semantics)."""
        m = self.station_modules
        return m[m["built"] == 1]
    floating_wares: pd.DataFrame = None      # sector.macro, ware, amount

    resource_cols: list = field(default_factory=list)
    faction_levels: list = field(default_factory=list)
    time_now: float = 0.0
    logged_hours: float = 0.0
    player_faction_name: str = "Player"


def _faction_levels(ref: RefData) -> list[str]:
    levels = ["PLA"]
    for short in ref.faction_short.values():
        if short not in levels:
            levels.append(short)
    levels.append(OTHER_FACTION)
    return levels


_CUR = "(SELECT MAX(save_id) FROM save)"


def _read(conn: sqlite3.Connection, sql: str,
          fill: list[str] = (), params=None) -> pd.DataFrame:
    """read_sql with SQL NULLs in `fill` columns normalized back to the
    frames' historic empty-string convention."""
    df = pd.read_sql(sql, conn, params=params)
    for col in fill:
        df[col] = df[col].fillna("")
    return df


def build_frames(save: SaveData, ref: RefData, cfg: Config,
                 conn: sqlite3.Connection) -> Frames:
    faction_levels = _faction_levels(ref)

    # ---- universe (R 353-369) ---------------------------------------------
    log("Preparing universe components -> universe")
    # macros lowercased, {page,id} name refs resolved, and non-universe
    # components (no @connection) filtered at database load time
    universe = _read(conn, f"""
        SELECT id, class, macro, name, code, owner, knownto, contested,
               spawntime, cluster_id AS "cluster.id",
               cluster_macro AS "cluster.macro", sector_id AS "sector.id",
               sector_macro AS "sector.macro", basename,
               parent_id AS "parent.id"
        FROM component WHERE save_id = {_CUR} ORDER BY rowid""",
        fill=["macro", "name", "code", "owner", "knownto", "cluster.id",
              "cluster.macro", "sector.id", "sector.macro", "basename",
              "parent.id"])

    # ---- sectors + resources (R 371-415, adapted to the v9 save format) ---
    log("Preparing sector info -> sectors")
    sectors = universe[universe["class"] == "sector"].copy()
    sectors = sectors.merge(
        ref.sectors[["macro", "name"]].rename(columns={"name": "sector.name"}),
        on="macro", how="left",
    )
    sectors["name"] = sectors["sector.name"].fillna(sectors["macro"])
    sectors = sectors.drop(columns=["sector.name"])
    sectors["contested"] = pd.to_numeric(sectors["contested"], errors="coerce"
                                         ).fillna(0).astype(int)

    resource_cols: list[str] = []
    res = _read(conn, f"""
        SELECT sector_macro AS macro, ware, yield FROM resource
        WHERE save_id = {_CUR} ORDER BY rowid""")
    if not res.empty:
        pivot = res.pivot_table(index="macro", columns="ware", values="yield",
                                aggfunc="sum", fill_value=0.0).reset_index()
        resource_cols = [c for c in pivot.columns if c != "macro"]
        sectors = sectors.merge(pivot, on="macro", how="left")
        sectors[resource_cols] = sectors[resource_cols].fillna(0.0)

    # ---- player-owned objects (R 417-420) ---------------------------------
    log("Preparing player owned objects -> playerowned")
    playerowned = universe[
        (universe["owner"] == "player")
        & ((universe["class"] == "station")
           | universe["class"].str.startswith("ship_"))
    ].copy()

    # ---- fleet hierarchy (R 422-436) --------------------------------------
    log("Preparing fleet hierarchies -> wings")
    wings = _read(conn, f"""
        SELECT commander_id AS leader, follower_id AS follower
        FROM fleet_edge WHERE save_id = {_CUR} ORDER BY rowid""")
    owned = set(playerowned["id"])
    wings = wings[wings["follower"].isin(owned) & wings["leader"].isin(owned)]
    wings = wings[["leader", "follower"]].reset_index(drop=True)

    # ---- NPCs (R 438-454) --------------------------------------------------
    log("Preparing player employed NPCs -> npcs")
    npcs = _read(conn, """
        SELECT id, name, code, piloting, engineering, boarding, management,
               morale
        FROM v_npc""", fill=["name", "code"])
    npcs["role"] = pd.NA

    # ---- posts / workforce / modules lookups ------------------------------
    posts = _read(conn, f"""
        SELECT object_id AS "object.id", post, npc_id AS "npc.id"
        FROM post WHERE save_id = {_CUR} ORDER BY rowid""")
    posts = posts.drop_duplicates(["object.id", "post"])
    post_pivot = posts.pivot(index="object.id", columns="post", values="npc.id")

    # build-plan entries were deduped per (host, entry) at database load
    # (stations list their plan twice: construction sequence + expand queue)
    module_list = _read(conn, f"""
        SELECT host_id AS id, idx AS "index", macro, entry_id AS entry,
               build_method AS method, built
        FROM module WHERE save_id = {_CUR} ORDER BY rowid""",
        fill=["macro", "entry", "method"])
    modules = module_list.groupby("id", as_index=False)["index"].max()
    modules = modules.rename(columns={"index": "modules"})

    # display type for unnamed NPC stations: basename attr when present,
    # else synthesized like the game does — build modules make it a
    # Shipyard/Wharf/Equipment Dock, otherwise the dominant production
    # module's product ("Energy Cell Factory")
    def _yard_type(macros: pd.Series) -> str:
        ships = macros[macros.str.contains("_ships_", na=False)]
        if not ships.empty:
            return "Shipyard" if ships.str.contains("_l_|_xl_", na=False).any() \
                else "Wharf"
        return "Equipment Dock"

    bm = module_list[module_list["macro"].str.contains("buildmodule",
                                                       na=False)]
    yard = bm.groupby("id")["macro"].agg(_yard_type)
    prod = module_list.merge(
        ref.modules[ref.modules["ware"] != ""][["macro", "ware"]]
        .drop_duplicates("macro"), on="macro")
    main_ware = prod.groupby("id")["ware"].agg(
        lambda x: x.value_counts().idxmax())
    factory = (main_ware.map(ref.ware_name).fillna(main_ware) + " Factory")
    universe["stype"] = (universe["basename"].replace("", pd.NA)
                         .fillna(universe["id"].map(yard))
                         .fillna(universe["id"].map(factory))
                         .fillna("Station"))
    universe.loc[universe["class"] == "buildstorage", "stype"] = "Build plot"

    # station mass estimates onto the whole universe (R 520-524)
    universe = universe.merge(modules, on="id", how="left")
    is_station = universe["class"] == "station"
    universe.loc[is_station, "hull"] = universe.loc[is_station, "modules"] * 250_000
    universe.loc[is_station, "mass"] = universe.loc[is_station, "hull"] / 300

    # ---- stations (R 483-527) ----------------------------------------------
    log("Preparing player owned stations -> stations")
    stations = playerowned[playerowned["class"] == "station"].copy()
    stations = stations.drop(columns=["spawntime"])
    workforce_all = _read(conn, f"""
        SELECT station_id AS id, race, amount FROM workforce
        WHERE save_id = {_CUR} ORDER BY rowid""")
    if not stations.empty:
        for post in ("manager", "engineer", "shiptrader"):
            if post in post_pivot.columns:
                stations = stations.merge(
                    post_pivot[[post]].rename(columns={post: f"{post}.id"}),
                    left_on="id", right_index=True, how="left",
                )
            else:
                stations[f"{post}.id"] = pd.NA
        if not workforce_all.empty:
            wf = workforce_all.pivot_table(index="id", columns="race",
                                           values="amount", aggfunc="sum",
                                           fill_value=0)
            wf.columns = [f"workforce.{race}" for race in wf.columns]
            stations = stations.merge(wf, left_on="id", right_index=True,
                                      how="left")
        stations = stations.merge(modules, on="id", how="left")
        stations["hull"] = stations["modules"] * 250_000
        stations["mass"] = stations["hull"] / 300
    else:
        log("-> No player owned stations found")
        for col in ("manager.id", "engineer.id", "shiptrader.id",
                    "modules", "hull", "mass"):
            stations[col] = pd.Series(dtype=object)

    # ---- ships (R 529-551) --------------------------------------------------
    log("Preparing player owned ships -> ships")
    ships = playerowned[playerowned["class"] != "station"].copy()
    ships["size"] = pd.Categorical(
        ships["class"].str.replace("ship_", "", regex=False).str.upper(),
        categories=SHIP_SIZES, ordered=True,
    )
    model_map = dict(zip(ref.ships["macro"], ref.ships["model"]))
    ships["model"] = ships["macro"].map(model_map)
    ships["name"] = (ships["name"].replace("", pd.NA)
                     .fillna(ships["model"]).fillna(ships["macro"]))
    # crew complement: service crew + marines aboard vs the model's capacity
    people = _read(conn, f"""
        SELECT object_id, role, count FROM people WHERE save_id = {_CUR} ORDER BY rowid""")
    crew_counts = (people[people["role"].isin(("service", "marine"))]
                   .groupby("object_id")["count"].sum())
    ships["crew.have"] = (ships["id"].map(crew_counts)
                          .fillna(0).astype(int))
    crew_map = dict(zip(ref.ships["macro"],
                        pd.to_numeric(ref.ships["crew"], errors="coerce")))
    ships["crew.max"] = ships["macro"].map(crew_map)
    for post in ("aipilot", "engineer"):
        if post in post_pivot.columns:
            ships = ships.merge(
                post_pivot[[post]], left_on="id", right_index=True, how="left")
        else:
            ships[post] = pd.NA
    if not npcs.empty:
        pilot = npcs[["id", "name", "piloting"]].rename(columns={
            "id": "aipilot", "name": "pilot.name", "piloting": "pilot.skill"})
        ships = ships.merge(pilot, on="aipilot", how="left")
        # NPC employment info (R 546-550)
        npcs.loc[npcs["id"].isin(ships["aipilot"]), "role"] = "pilot (ship)"
        npcs.loc[npcs["id"].isin(ships["engineer"]), "role"] = "engineer (ship)"
        if not stations.empty:
            npcs.loc[npcs["id"].isin(stations["manager.id"]), "role"] = \
                "manager (station)"
            npcs.loc[npcs["id"].isin(stations["engineer.id"]), "role"] = \
                "engineer (station)"
            npcs.loc[npcs["id"].isin(stations["shiptrader.id"]), "role"] = \
                "shiptrader (station)"
    else:
        ships["pilot.name"] = pd.NA
        ships["pilot.skill"] = pd.NA

    # ship model as fallback display name in playerowned too (R 553-557)
    unnamed = (playerowned["class"] != "station") & \
        (playerowned["name"].replace("", pd.NA).isna())
    playerowned.loc[unnamed, "name"] = playerowned.loc[unnamed, "macro"].map(
        model_map).fillna(playerowned.loc[unnamed, "macro"])

    # ---- log (R 456-481) -----------------------------------------------------
    log("Preparing log entries -> log")
    df_log = pd.DataFrame(save.log_entries)
    for col in ("time", "category", "title", "text", "money", "component"):
        if col not in df_log.columns:
            df_log[col] = pd.NA
    df_log["category"] = df_log["category"].fillna("")
    df_log = df_log[
        (df_log["category"] == "")
        | ((df_log["category"] == "upkeep") & (df_log["title"] != "Trade Completed"))
    ]
    df_log["time"] = pd.to_numeric(df_log["time"], errors="coerce")
    df_log["money"] = pd.to_numeric(df_log["money"], errors="coerce")
    df_log = (df_log[["time", "category", "title", "text", "money", "component"]]
              .drop_duplicates().reset_index(drop=True))
    log("Loading and merging log cache")
    df_log = merge_log_cache(cfg, save.guid, df_log)

    # ---- tradelog (R 559-647) -------------------------------------------------
    log("Preparing economylog -> tradelog")
    tradelog = _build_tradelog(save, ref, universe, playerowned, wings,
                               faction_levels)
    log("Loading and merging tradelog cache")
    tradelog = merge_tradelog_cache(cfg, save.guid, tradelog)
    tradelog["seller.faction"] = pd.Categorical(
        tradelog["seller.faction"], categories=faction_levels, ordered=True)
    tradelog["buyer.faction"] = pd.Categorical(
        tradelog["buyer.faction"], categories=faction_levels, ordered=True)

    # ---- sales & buys (R 650-727) ----------------------------------------------
    log("Gathering sales -> sales; buys -> buys")
    sales = tradelog[
        (tradelog["seller.faction"] == "PLA") & (tradelog["buyer.faction"] != "PLA")
    ][logparse.SALE_COLS].copy()
    for title, split_text, commodity in (
        ("Ship constructed", " finished construction at station: ",
         "Ship construction"),
        ("Ship repaired", " finished repairing at station: ", "Ship repair"),
        ("Ship resupplied", " finished resupplying at station: ",
         "Ship resupply"),
    ):
        extra = logparse.parse_ship_services(df_log, title, split_text, commodity)
        if not extra.empty:
            sales = pd.concat([sales, extra], ignore_index=True)
    sales = sales.sort_values("time", ascending=False, ignore_index=True)

    buys = tradelog[
        (tradelog["seller.faction"] != "PLA") & (tradelog["buyer.faction"] == "PLA")
    ][["time", "money", "buyer.name", "buyer.code", "amount", "commodity",
       "seller.faction", "seller.name", "seller.code"]].copy()
    buys["money"] = -buys["money"]

    # ---- log-derived frames (R 729-790) -----------------------------------------
    log("Parsing destroyed/transfers/pirates/police from log")
    destroyed = logparse.parse_destroyed(df_log)
    transfers = logparse.parse_transfers(df_log, npcs, stations)
    sectors_for_join = sectors[["name", "sector.macro"]]
    pirates = logparse.parse_pirates(df_log, sectors_for_join)
    name_to_short = {ref.faction_name[o]: s for o, s in ref.faction_short.items()}
    police = logparse.parse_police(df_log, sectors_for_join, name_to_short)

    time_now = float(df_log["time"].max()) if not df_log.empty else save.game_time
    logged_hours = (
        (time_now - float(df_log["time"].min())) / 3600.0 if not df_log.empty else 0.0
    )
    if not destroyed.empty:
        destroyed["HoursAgo"] = (time_now - destroyed["time"]) / 3600.0

    player_faction_name = ref.resolve_name(save.player_faction_name) or "Player"

    # universe-wide trade events: owner-only economylog entries (volume
    # only; every faction). v is the station's stock level logged after
    # each trade, NOT a trade amount; delivered volume = positive stock
    # increases between consecutive snapshots (v_stock_delta), an upper-ish
    # estimate of traded volume. dv_neg = stock leaving the station
    # (consumption, construction draw, sales). Only the CURRENT save's
    # window feeds the dashboards — its ids resolve against this universe
    # and the Market rate denominators keep their meaning; the merged
    # multi-session history stays queryable in stock_event/v_stock_delta,
    # keyed by the save-stable identity resolved at merge time.
    row = conn.execute("SELECT value FROM meta"
                       " WHERE key = 'stock_event_window_start'").fetchone()
    gt = _read(conn, """
        SELECT owner_id AS owner, ware, time, level AS v, dv, dv_neg
        FROM v_stock_delta WHERE time >= ? ORDER BY time""",
        params=(float(row[0]) if row else 0.0,))
    if not gt.empty:
        gt[["dv", "dv_neg"]] = gt[["dv", "dv_neg"]].fillna(0.0)
        uni_idx = universe.set_index("id")
        gt["faction"] = (gt["owner"].map(uni_idx["owner"])
                         .map(ref.faction_short).fillna(OTHER_FACTION))
        gt["station"] = gt["owner"].map(uni_idx["name"])
        gt["station.code"] = gt["owner"].map(uni_idx["code"])
        gt["sector.macro"] = gt["owner"].map(uni_idx["sector.macro"])
        # stations destroyed since the trades happened are gone from the
        # universe tree, but the economylog <removed> catalog keeps their
        # identity — resolve them and mark with a dagger (the merged table
        # covers owners the current save's window no longer mentions)
        rem = _read(conn, "SELECT id, name, code, owner FROM removed_object")
        gt["destroyed"] = False
        if not rem.empty and "id" in rem.columns:
            rem = rem.drop_duplicates("id").set_index("id")
            miss = ~gt["owner"].isin(uni_idx.index) \
                & gt["owner"].isin(rem.index)
            gt.loc[miss, "faction"] = (gt.loc[miss, "owner"].map(rem["owner"])
                                       .map(ref.faction_short)
                                       .fillna(OTHER_FACTION))
            gt.loc[miss, "station"] = gt.loc[miss, "owner"].map(rem["name"])
            gt.loc[miss, "station.code"] = gt.loc[miss, "owner"].map(
                rem["code"])
            gt.loc[miss, "destroyed"] = True
        # anything still unresolved (gone from the universe AND the removed
        # catalog) keeps its object id as the code so distinct unknown
        # objects can never merge into one aggregate bar
        unknown = ~gt["owner"].isin(uni_idx.index) & gt["station"].isna()
        gt.loc[unknown, "station.code"] = gt.loc[unknown, "owner"]
        gt.loc[unknown, "destroyed"] = True
        # most NPC stations are unnamed: "<FAC> <type> (CODE)" fallback,
        # using the station's basename text ref ("Solar Power Plant" etc.)
        base = (gt["owner"].map(uni_idx["stype"]).replace("", pd.NA)
                .fillna("Station"))
        unnamed = gt["station"].replace("", pd.NA).isna()
        gt.loc[unnamed, "station"] = (gt.loc[unnamed, "faction"] + " "
                                      + base[unnamed])
        gt["label"] = (gt["station"]
                       + " (" + gt["station.code"].fillna("?") + ")")
        gt.loc[gt["destroyed"], "label"] += " †"
    else:
        gt = pd.DataFrame(columns=["time", "owner", "ware", "v", "dv",
                                   "dv_neg", "faction", "station",
                                   "station.code", "sector.macro", "label"])

    orders = _read(conn, f"""
        SELECT object_id AS id, order_name AS "order",
               is_default AS "default", state
        FROM ship_order WHERE save_id = {_CUR} ORDER BY rowid""", fill=["state"])
    orders["default"] = orders["default"].astype(bool)

    return Frames(
        universe=universe, sectors=sectors, playerowned=playerowned,
        wings=wings, npcs=npcs, stations=stations, ships=ships, log=df_log,
        tradelog=tradelog, sales=sales, buys=buys, destroyed=destroyed,
        transfers=transfers, pirates=pirates, police=police,
        station_modules=module_list, global_trades=gt,
        station_cargo=_read(conn, f"""
            SELECT object_id AS id, ware, amount FROM cargo
            WHERE save_id = {_CUR} ORDER BY rowid"""),
        workforce_all=workforce_all,
        build_demand=_read(conn, f"""
            SELECT host_id AS id, ware, amount, kind FROM build_resource
            WHERE save_id = {_CUR} ORDER BY rowid""", fill=["id"]),
        trade_offers=_read(conn, f"""
            SELECT object_id AS id, side, ware, amount, price_cr AS price
            FROM trade_offer WHERE save_id = {_CUR} ORDER BY rowid"""),
        orders=orders,
        built_refs=set(save.built_refs),
        module_upgrades=_read(conn, f"""
            SELECT entry_id AS entry, equipment_macro AS macro
            FROM module_upgrade WHERE save_id = {_CUR} ORDER BY rowid"""),
        floating_wares=_read(conn, f"""
            SELECT sector_macro AS "sector.macro", ware, amount
            FROM floating_ware WHERE save_id = {_CUR} ORDER BY rowid""",
            fill=["sector.macro"]),
        resource_cols=resource_cols, faction_levels=faction_levels,
        time_now=time_now, logged_hours=logged_hours,
        player_faction_name=player_faction_name,
    )


def _build_tradelog(save: SaveData, ref: RefData, universe: pd.DataFrame,
                    playerowned: pd.DataFrame, wings: pd.DataFrame,
                    faction_levels: list) -> pd.DataFrame:
    cols = ["time", "commodity", "price", "amount", "money",
            "seller.faction", "seller.id", "seller.name", "seller.code",
            "seller.proxy.id", "seller.proxy.name", "seller.proxy.code",
            "buyer.faction", "buyer.id", "buyer.name", "buyer.code",
            "buyer.proxy.id", "buyer.proxy.name", "buyer.proxy.code"]
    trades = [t for t in save.trades
              if t.get("buyer") and t.get("seller") and t.get("price")]
    if not trades:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(trades)
    removed = pd.DataFrame(save.removed_objects)
    if removed.empty:
        removed = pd.DataFrame(columns=["id", "name", "code", "owner"])

    uni_by_id = universe.set_index("id")
    owned_by_id = playerowned.set_index("id")
    follower_to_leader = dict(zip(wings["follower"], wings["leader"]))
    removed_by_id = removed.set_index("id") if "id" in removed else removed
    model_map = dict(zip(ref.ships["macro"], ref.ships["model"]))
    macro_by_id = universe.set_index("id")["macro"]
    basename_by_id = universe.set_index("id")["stype"].replace("", pd.NA)

    def resolve_party(ids: pd.Series):
        """R 565-590: removed objects -> proxy redirect -> playerowned ->
        universe -> '<FAC> <model|Station>' fallback."""
        out = pd.DataFrame(index=ids.index)
        out["id"] = ids
        out["name"] = ids.map(removed_by_id["name"]) if "name" in removed_by_id \
            else pd.NA
        out["code"] = ids.map(removed_by_id["code"]) if "code" in removed_by_id \
            else pd.NA
        out["owner"] = ids.map(removed_by_id["owner"]) if "owner" in removed_by_id \
            else pd.NA
        # when no id matches, map() yields all-NaN float64 columns and
        # pandas then refuses to assign strings into them — pin to object
        for c in ("name", "code", "owner"):
            out[c] = out[c].astype("object")

        # subordinate traders act for their commander
        is_proxy = out["id"].isin(follower_to_leader)
        out["proxy.id"] = out["id"].where(is_proxy)
        out.loc[is_proxy, "id"] = out.loc[is_proxy, "id"].map(follower_to_leader)

        # player owned objects
        m = out["name"].isna() & out["id"].isin(owned_by_id.index)
        out.loc[m, "name"] = out.loc[m, "id"].map(owned_by_id["name"])
        out.loc[m, "code"] = out.loc[m, "id"].map(owned_by_id["code"])
        out.loc[m, "owner"] = "player"

        # anything else in the universe
        m = out["name"].replace("", pd.NA).isna()
        out.loc[m, "name"] = out.loc[m, "id"].map(uni_by_id["name"])
        out.loc[m, "code"] = out.loc[m, "code"].fillna(
            out.loc[m, "id"].map(uni_by_id["code"]))
        out.loc[m, "owner"] = out.loc[m, "owner"].fillna(
            out.loc[m, "id"].map(uni_by_id["owner"]))

        # nameless NPC objects: "<FAC> <ship model>" or the station's
        # basename type ("<FAC> Solar Power Plant")
        out["faction"] = out["owner"].map(ref.faction_short).fillna(OTHER_FACTION)
        m = out["name"].replace("", pd.NA).isna()
        fallback = (out.loc[m, "id"].map(macro_by_id).map(model_map)
                    .fillna(out.loc[m, "id"].map(basename_by_id))
                    .fillna("Station"))
        out.loc[m, "name"] = out.loc[m, "faction"] + " " + fallback

        # proxy name/code
        out["proxy.name"] = out["proxy.id"].map(owned_by_id["name"])
        out["proxy.code"] = out["proxy.id"].map(owned_by_id["code"])
        return out

    seller = resolve_party(df["seller"])
    buyer = resolve_party(df["buyer"])

    result = pd.DataFrame({
        "time": pd.to_numeric(df["time"], errors="coerce"),
        "commodity": df["ware"].map(ref.ware_name).fillna(df["ware"]),
        "price": pd.to_numeric(df["price"], errors="coerce") / 100.0,
        "amount": pd.to_numeric(df["v"], errors="coerce").astype("Int64"),
    })
    result["money"] = (result["price"] * result["amount"]).astype("Int64")
    for side, party in (("seller", seller), ("buyer", buyer)):
        result[f"{side}.faction"] = party["faction"]
        result[f"{side}.id"] = party["id"]
        result[f"{side}.name"] = party["name"]
        result[f"{side}.code"] = party["code"]
        result[f"{side}.proxy.id"] = party["proxy.id"]
        result[f"{side}.proxy.name"] = party["proxy.name"]
        result[f"{side}.proxy.code"] = party["proxy.code"]
    return result[cols]
