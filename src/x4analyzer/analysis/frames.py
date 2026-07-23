"""Builds the analysis dataframes from a parsed savegame.

Faithful port of the df.* logic in X4SaveGameAnalysis.R (line references in
comments). Column names keep the R script's dotted style so anyone familiar
with the original finds their way around.

Everything reads from the analysis database (store.py writes and merges it
before this runs) — world state from the current snapshot, log/trade
history from the merged event tables; SQL NULLs are normalized back to the
frames' historic empty-string convention so downstream code is unchanged.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from ..save import logparse
from ..cli import log
from ..gamedata.refdata import OTHER_FACTION, RefData, SHIP_SIZES
from ..save.parser import SaveData


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

    # entity registry: one row per physical ship/station/buildstorage ever
    # observed, surrogate entity_id (codes recycle, ids remap, names/owners
    # mutate — the registry is the durable identity)
    entities: pd.DataFrame = None

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
    # data vaults (regular + Erlking): id, macro, code, knownto,
    # sector.macro, sx, sz, unlocked, loot, blueprints
    datavaults: pd.DataFrame = None
    # wormholes / anomalies: id, macro, code, knownto, cluster.macro,
    # sector.macro, sx, sz, source_entry, source_class, transition_dest
    wormholes: pd.DataFrame = None
    # directional warp links: id, own_conn, role, target_conn
    wormhole_links: pd.DataFrame = None
    # player ships' equipped engines: id, macro, n (mounted count)
    ship_engines: pd.DataFrame = None
    # faction diplomacy (universe/factions):
    #   faction_relations: faction, other, base, booster, effective (clamped)
    #   faction_discounts: faction, other, discount (trade discount fraction)
    #   faction_meta: faction, account (treasury)
    #   faction_licences: faction, type, factions (rep-gated unlocks)
    faction_relations: pd.DataFrame = None
    faction_discounts: pd.DataFrame = None
    faction_meta: pd.DataFrame = None
    faction_licences: pd.DataFrame = None

    # storage-allocation model (analysis/storage.py): per (station id, ware)
    # max_units / max_volume / throughput / transport / role. Computed after
    # the frames are built (analyze.py) and attached for the viz layer.
    station_storage: pd.DataFrame = None
    # station munition census: station_id / macro / category / is_unit / count
    # / capacity_floor. Attached after the frames are built (analyze.py).
    station_munition: pd.DataFrame = None

    resource_cols: list = field(default_factory=list)
    faction_levels: list = field(default_factory=list)
    # per-area resource status for the map detail panel, keyed
    # sector.macro -> ware -> [ {status, cap, now, eta_min} ], one record per
    # area (status in live|full|respawning|never|unknown)
    resource_areas: dict = field(default_factory=dict)
    time_now: float = 0.0
    logged_hours: float = 0.0
    player_faction_name: str = "Player"
    # ring highways exist in this save (custom starts can disable them)
    has_highways: bool = True


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


def station_types(universe: pd.DataFrame, module_list: pd.DataFrame,
                  ref: RefData) -> pd.Series:
    """Display type per object id for unnamed stations: basename attr when
    present, else synthesized like the game does — build modules make it a
    Shipyard/Wharf/Equipment Dock, otherwise the dominant production
    module's product ("Energy Cell Factory"); build storages are plots.
    `universe` needs id/class/basename, `module_list` id/macro."""
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
    by_id = universe.set_index("id")
    stype = (by_id["basename"].replace("", pd.NA)
             .fillna(yard).fillna(factory).fillna("Station"))
    stype[by_id["class"] == "buildstorage"] = "Build plot"
    return stype


def station_types_from_db(conn: sqlite3.Connection, ref: RefData) -> dict:
    """station_types over the current snapshot, for callers that run before
    build_frames (store.merge_events resolves trade-party display names)."""
    universe = _read(conn, f"""
        SELECT id, class, basename FROM component
        WHERE save_id = {_CUR}""", fill=["basename"])
    module_list = _read(conn, f"""
        SELECT host_id AS id, macro FROM module
        WHERE save_id = {_CUR}""", fill=["macro"])
    return dict(station_types(universe, module_list, ref))


def build_frames(save: SaveData, ref: RefData,
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
               parent_id AS "parent.id", sx, sz, faction_hq
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
    resource_areas: dict = {}
    res = _read(conn, f"""
        SELECT sector_macro AS macro, ware, yield, level, speed, starttime
        FROM resource WHERE save_id = {_CUR} ORDER BY rowid""")
    if not res.empty:
        # Per-area status from the confirmed respawn model
        # (docs/models/resource-depletion-model.md). An area's stored yield reads 0
        # once depleted and only "materializes" back to full when a miner
        # mines it, but availability itself is timer-driven: an empty area is
        # already respawned & full once past its starttime (respawn-eligibility
        # clock). So mineable-now = live yield, OR full capacity for an
        # eligible-empty area, OR 0 while still on the respawn cooldown. The
        # replenishment CEILING is Σ capacity/respawndelay (per hour) — the
        # rate if every area were held depleted; gatherspeed is an EXTRACTION
        # term, not a respawn term, so it is deliberately absent here.
        now_t = float(save.game_time)

        def _classify(ware, level, yld, start):
            cap, delay = ref.region_yields.get(
                (str(level), str(ware)), (0.0, 0.0))
            if yld > 0:
                status, mineable = "live", yld
            elif not cap:                       # no reference entry
                status, mineable = "unknown", 0.0
            elif delay < 0:                     # -1 = never respawns
                status, mineable = "never", 0.0
            elif start == 0 or start <= now_t:  # respawned & full (reads 0)
                status, mineable = "full", cap
            else:
                status, mineable = "respawning", 0.0
            rate = cap / delay * 60.0 if delay and delay > 0 else 0.0
            eta = (start - now_t) / 60.0 if status == "respawning" else None
            return status, float(mineable), float(cap), rate, eta

        # (status, mineable, cap, rate, eta) per area, aligned with res rows.
        # Only the pure-float mineable/rate go back into res (for pivots);
        # status/cap/eta feed the breakdown directly from cls to avoid pandas
        # coercing the None etas to NaN
        cls = [_classify(w, lv, y, st) for w, lv, y, st in zip(
            res["ware"], res["level"], res["yield"], res["starttime"])]
        res["mineable"] = [c[1] for c in cls]
        res["rate"] = [c[3] for c in cls]

        # left gauge / panel headline: mineable-now (the encyclopedia number)
        pivot = res.pivot_table(index="macro", columns="ware",
                                values="mineable", aggfunc="sum",
                                fill_value=0.0).reset_index()
        resource_cols = [c for c in pivot.columns if c != "macro"]
        sectors = sectors.merge(pivot, on="macro", how="left")
        sectors[resource_cols] = sectors[resource_cols].fillna(0.0)

        # right gauge: theoretical max replenishment rate (units/h). Zero when
        # the reference CSVs predate the extract, so the gauge simply doesn't
        # draw
        rep = res.pivot_table(index="macro", columns="ware", values="rate",
                              aggfunc="sum", fill_value=0.0).reset_index()
        rep.columns = ["macro"] + [f"rep.{c}" for c in rep.columns[1:]]
        sectors = sectors.merge(rep, on="macro", how="left")
        rep_cols = [c for c in sectors.columns if c.startswith("rep.")]
        sectors[rep_cols] = sectors[rep_cols].fillna(0.0)

        # per-area breakdown for the detail dropdown, one record per area,
        # carrying the yieldid's gatherspeed token
        for macro, ware, speed, (status, now_v, cap_v, _rate, eta_v) in zip(
                res["macro"], res["ware"], res["speed"], cls):
            rec = {"status": status, "cap": round(cap_v), "now": round(now_v),
                   "speed": "" if pd.isna(speed) else str(speed),
                   "eta_min": None if eta_v is None else round(eta_v)}
            resource_areas.setdefault(macro, {}).setdefault(ware, []).append(rec)
        # most-available fields first (current mineable volume, then capacity)
        for ware_map in resource_areas.values():
            for recs in ware_map.values():
                recs.sort(key=lambda r: (-r["now"], -r["cap"]))

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

    universe["stype"] = universe["id"].map(
        station_types(universe, module_list, ref)).values

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
    # the merged event history (all runs); money back to the save's cents
    # so the logparse consumers' /100 stays untouched
    log("Preparing log entries -> log")
    df_log = _read(conn, """
        SELECT time, category, title, text, money_cr * 100.0 AS money,
               component_id AS component
        FROM log_entry ORDER BY time""", fill=["category"])
    df_log = df_log[
        (df_log["category"] == "")
        | ((df_log["category"] == "upkeep") & (df_log["title"] != "Trade Completed"))
    ]
    df_log = df_log.drop_duplicates().reset_index(drop=True)

    # ---- entity registry (surrogate identity across snapshots) -----------------
    log("Preparing entity registry -> entities")
    entities = _read(conn, """
        SELECT entity_id, code, class, macro, spawntime, owner, name,
               first_seen, last_seen, gone_time, gone_reason
        FROM entity ORDER BY entity_id""")

    # ---- tradelog (R 559-647) -------------------------------------------------
    # the merged trade_tx history; parties were resolved to display-ready
    # identities at merge time (the only moment their runtime ids are
    # unambiguous), commander attribution included — reassemble the R-era
    # dotted columns: main = commander when a subordinate executed the
    # trade, proxy.* = the executing ship ("Executed by" in Trade History)
    log("Preparing economylog -> tradelog")
    tl = _read(conn, """
        SELECT time, ware, price_cr, amount,
               buyer_id, buyer_faction, buyer_code, buyer_name,
               buyer_cmdr_id, buyer_cmdr_name, buyer_cmdr_code,
               seller_id, seller_faction, seller_code, seller_name,
               seller_cmdr_id, seller_cmdr_name, seller_cmdr_code,
               buyer_entity, seller_entity,
               buyer_cmdr_entity, seller_cmdr_entity
        FROM trade_tx ORDER BY time""")
    # A rename must not split an object's history: names are display-only
    # and trade_tx keeps whatever name each row was merged under.
    # Re-resolve display names, best evidence first: the entity registry's
    # current name (exact surrogate identity), else per code — the current
    # save's name when the object still exists, otherwise the latest name
    # the history recorded for that code (codes are unique among the
    # living but recycled after death; entity ids never are).
    if not tl.empty:
        ent_name = entities.dropna(subset=["name"]) \
            .set_index("entity_id")["name"]
        seen = pd.concat(
            [tl[["time", f"{side}{k}_code", f"{side}{k}_name"]]
             .set_axis(["time", "code", "name"], axis=1)
             for side in ("buyer", "seller") for k in ("", "_cmdr")],
            ignore_index=True).dropna(subset=["code", "name"])
        seen = seen[(seen["code"] != "") & (seen["name"] != "")]
        seen = seen.sort_values("time", kind="stable")
        name_by_code = dict(zip(seen["code"], seen["name"]))
        alive = universe[(universe["code"] != "") & (universe["name"] != "")]
        name_by_code.update(zip(alive["code"], alive["name"]))
        for col in ("buyer_name", "seller_name",
                    "buyer_cmdr_name", "seller_cmdr_name"):
            codes = tl[col.replace("_name", "_code")]
            eids = tl[col.replace("_name", "_entity")]
            tl[col] = (eids.map(ent_name)
                       .fillna(codes.map(name_by_code))
                       .fillna(tl[col]))
    tradelog = pd.DataFrame({
        "time": tl["time"],
        "commodity": tl["ware"].map(ref.ware_name).fillna(tl["ware"]),
        "price": tl["price_cr"],
        "amount": tl["amount"].astype("Int64"),
    })
    tradelog["money"] = (tradelog["price"] * tradelog["amount"]).astype("Int64")
    for side in ("seller", "buyer"):
        fac = (tl[f"{side}_faction"].map(ref.faction_short)
               .fillna(OTHER_FACTION))
        # safety net for rows merged before display names were stored
        name = tl[f"{side}_name"].fillna(fac + " Station")
        proxied = tl[f"{side}_cmdr_id"].notna()
        tradelog[f"{side}.faction"] = fac
        tradelog[f"{side}.id"] = tl[f"{side}_id"].where(
            ~proxied, tl[f"{side}_cmdr_id"])
        tradelog[f"{side}.name"] = name.where(
            ~proxied, tl[f"{side}_cmdr_name"])
        tradelog[f"{side}.code"] = tl[f"{side}_code"].where(
            ~proxied, tl[f"{side}_cmdr_code"])
        tradelog[f"{side}.proxy.id"] = tl[f"{side}_id"].where(proxied)
        tradelog[f"{side}.proxy.name"] = tl[f"{side}_name"].where(proxied)
        tradelog[f"{side}.proxy.code"] = tl[f"{side}_code"].where(proxied)
        tradelog[f"{side}.entity"] = tl[f"{side}_entity"].where(
            ~proxied, tl[f"{side}_cmdr_entity"]).astype("Int64")
        tradelog[f"{side}.proxy.entity"] = \
            tl[f"{side}_entity"].where(proxied).astype("Int64")
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

    # ---- faction diplomacy: pivot base/booster into effective standing -----
    frel_raw = _read(conn, f"""
        SELECT faction, other, kind, value FROM faction_relation
        WHERE save_id = {_CUR} ORDER BY rowid""")
    if not frel_raw.empty:
        base = (frel_raw[frel_raw["kind"] == "base"]
                .groupby(["faction", "other"])["value"].sum())
        boost = (frel_raw[frel_raw["kind"] == "booster"]
                 .groupby(["faction", "other"])["value"].sum())
        keys = base.index.union(boost.index)
        faction_relations = pd.DataFrame(index=keys)
        faction_relations["base"] = base.reindex(keys).fillna(0.0)
        faction_relations["booster"] = boost.reindex(keys).fillna(0.0)
        # effective standing as of the save (boosters are stored at their
        # current decayed value) = base + boosters, clamped to [-1, 1]
        faction_relations["effective"] = (
            faction_relations["base"] + faction_relations["booster"]
        ).clip(-1.0, 1.0)
        faction_relations = faction_relations.reset_index()
        faction_discounts = (frel_raw[frel_raw["kind"] == "discount"]
                             [["faction", "other", "value"]]
                             .rename(columns={"value": "discount"})
                             .reset_index(drop=True))
    else:
        faction_relations = pd.DataFrame(
            columns=["faction", "other", "base", "booster", "effective"])
        faction_discounts = pd.DataFrame(
            columns=["faction", "other", "discount"])

    return Frames(
        universe=universe, sectors=sectors, playerowned=playerowned,
        wings=wings, npcs=npcs, stations=stations, ships=ships, log=df_log,
        tradelog=tradelog, sales=sales, buys=buys, destroyed=destroyed,
        transfers=transfers, pirates=pirates, police=police,
        entities=entities,
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
        has_highways=save.has_highways,
        module_upgrades=_read(conn, f"""
            SELECT entry_id AS entry, equipment_macro AS macro
            FROM module_upgrade WHERE save_id = {_CUR} ORDER BY rowid"""),
        floating_wares=_read(conn, f"""
            SELECT sector_macro AS "sector.macro", ware, amount
            FROM floating_ware WHERE save_id = {_CUR} ORDER BY rowid""",
            fill=["sector.macro"]),
        datavaults=_read(conn, f"""
            SELECT object_id AS id, macro, code, knownto,
                   sector_macro AS "sector.macro", sx, sz,
                   unlocked, loot, blueprints
            FROM datavault WHERE save_id = {_CUR} ORDER BY rowid""",
            fill=["code", "knownto", "sector.macro", "blueprints"]),
        wormholes=_read(conn, f"""
            SELECT object_id AS id, macro, code, knownto,
                   cluster_macro AS "cluster.macro",
                   sector_macro AS "sector.macro", sx, sz,
                   source_entry, source_class, transition_dest
            FROM wormhole WHERE save_id = {_CUR} ORDER BY rowid""",
            fill=["code", "knownto", "cluster.macro", "sector.macro",
                  "source_entry", "source_class"]),
        wormhole_links=_read(conn, f"""
            SELECT object_id AS id, own_conn, role, target_conn
            FROM wormhole_link WHERE save_id = {_CUR} ORDER BY rowid""",
            fill=["role"]),
        ship_engines=_read(conn, f"""
            SELECT object_id AS id, macro, n
            FROM ship_engine WHERE save_id = {_CUR} ORDER BY rowid"""),
        faction_relations=faction_relations, faction_discounts=faction_discounts,
        faction_meta=_read(conn, f"""
            SELECT faction, account FROM faction_meta
            WHERE save_id = {_CUR} ORDER BY rowid"""),
        faction_licences=_read(conn, f"""
            SELECT faction, type, factions FROM faction_licence
            WHERE save_id = {_CUR} ORDER BY rowid""", fill=["factions"]),
        resource_cols=resource_cols, faction_levels=faction_levels,
        resource_areas=resource_areas,
        time_now=time_now, logged_hours=logged_hours,
        player_faction_name=player_faction_name,
    )
