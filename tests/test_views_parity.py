"""Real-database parity tests for the domain read layer (plan T6/T8/T9).

Each view that replaced a frames/pandas block must reproduce the output
of the code it retired, proven on the real 8E0C analysis database. The
retired pandas logic is reimplemented VERBATIM inside this module (that
is the point: the equivalence stays pinned after the production copy is
gone), and where the plan documents a known theoretical divergence the
test asserts the CURRENT equivalence explicitly so future divergence
fails loudly instead of drifting silently.

Read-only by construction: the real DB is opened ``mode=ro`` and the
checked-out code's view definitions are instantiated as TEMP views
(shadowing whatever view versions the file stores), so these tests
never write to the real database and always test the current DDL.
Skipped entirely on machines without the real DB.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from x4analyzer.analysis.frames import _faction_levels, tradelog_frame
from x4analyzer.config import Config
from x4analyzer.db import schema
from x4analyzer.gamedata.refdata import OTHER_FACTION, load_refdata

REAL_DB = (Path.home() / ".local/share/x4analyzer"
           / "x4_8E0C8E37-2192-49FD-BF4B-F535782A1C55.sqlite")

pytestmark = pytest.mark.skipif(
    not REAL_DB.exists(), reason="real 8E0C analysis DB not present")


@pytest.fixture(scope="module")
def conn():
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    # current code's views as TEMP clones (name resolution prefers temp,
    # so stored main-db views of any vintage are shadowed)
    for name, ddl in schema.VIEWS.items():
        body = ddl.split(" AS\n", 1)[1] if " AS\n" in ddl \
            else ddl.split(" AS ", 1)[1]
        conn.execute(f"CREATE TEMP VIEW {name} AS {body}")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def ref():
    # the same reference data the real pipeline uses (user data dir,
    # falling back to the packaged CSVs)
    return load_refdata(Config().data_dir)


def _eq(a: pd.Series, b: pd.Series) -> pd.Series:
    """NaN-tolerant elementwise equality."""
    return (a == b) | (a.isna() & b.isna())


# ---- v_trade vs the retired frames.tradelog assembly (T6 / M2) --------------

def _retired_tradelog(conn, ref, faction_levels) -> pd.DataFrame:
    """Verbatim reimplementation of the pandas tradelog assembly that
    lived in frames.build_frames before v_trade replaced it."""
    entities = pd.read_sql(
        "SELECT entity_id, name FROM entity ORDER BY entity_id", conn)
    universe = pd.read_sql(
        "SELECT code, name FROM component"
        " WHERE save_id = (SELECT MAX(save_id) FROM save)"
        " ORDER BY rowid", conn)
    for col in ("code", "name"):
        universe[col] = universe[col].fillna("")
    tl = pd.read_sql("""
        SELECT time, ware, price_cr, amount,
               buyer_id, buyer_faction, buyer_code, buyer_name,
               buyer_cmdr_id, buyer_cmdr_name, buyer_cmdr_code,
               seller_id, seller_faction, seller_code, seller_name,
               seller_cmdr_id, seller_cmdr_name, seller_cmdr_code,
               buyer_entity, seller_entity,
               buyer_cmdr_entity, seller_cmdr_entity
        FROM trade_tx
        WHERE (kind IS NULL OR kind = 'trade') AND price_cr IS NOT NULL
        ORDER BY time""", conn)
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
    return tradelog


def test_v_trade_reproduces_retired_tradelog(conn, ref):
    levels = _faction_levels(ref)
    new = tradelog_frame(conn, ref, levels)
    old = _retired_tradelog(conn, ref, levels)

    n_source = conn.execute(
        "SELECT COUNT(*) FROM trade_tx"
        " WHERE (kind IS NULL OR kind = 'trade')"
        " AND price_cr IS NOT NULL").fetchone()[0]
    assert len(new) == len(old) == n_source > 1000
    assert list(new.columns) == list(old.columns)

    ent_name = pd.read_sql(
        "SELECT entity_id, name FROM entity WHERE name IS NOT NULL",
        conn).set_index("entity_id")["name"]
    for col in new.columns:
        a, b = new[col], old[col]
        if col.endswith(".faction"):
            a, b = a.astype(str), b.astype(str)
        ok = _eq(a, b)
        if col.endswith(".name"):
            # the ONE sanctioned divergence (plan T6 / review plan-F4):
            # the retired latest-name-per-code fallback is gone — rows
            # whose (redirected) party has no registry name may degrade
            # to the stored merge-time name. Nothing else may differ.
            eid = new[col.replace(".name", ".entity")]
            allowed = eid.map(ent_name).isna()
            bad = ~ok & ~allowed
            assert bad.sum() == 0, \
                f"{col}: {bad.sum()} rows diverge outside the sanctioned set"
        else:
            assert ok.all(), f"{col}: {(~ok).sum()} rows differ"

    # proxied flags: view rule (cmdr_id) matches frames' rule row-for-row
    n_proxied_sql = conn.execute(
        "SELECT SUM(buyer_proxied), SUM(seller_proxied) FROM v_trade"
        " WHERE (kind IS NULL OR kind = 'trade')"
        " AND price_cr IS NOT NULL").fetchone()
    assert n_proxied_sql == (int(new["buyer.proxy.id"].notna().sum()),
                             int(new["seller.proxy.id"].notna().sum()))


# ---- v_stock_flow vs the retired v_stock_delta semantics (T6 / M2) ----------

_KEY = ("COALESCE('e' || owner_entity,"
        " owner_faction || '|' || owner_code, owner_id)")


def test_v_stock_flow_matches_pandas_recompute(conn):
    """Per-series inflow/outflow sums of the view equal a full pandas
    recomputation of the LAG deltas over stock_event."""
    se = pd.read_sql(
        f"SELECT rowid AS rid, {_KEY} AS k, ware, epoch, time, level"
        " FROM stock_event", conn)
    assert len(se) > 100_000
    se = se.sort_values(["k", "ware", "epoch", "time", "rid"],
                        kind="stable")
    lag = se.groupby(["k", "ware", "epoch"], sort=False)["level"].shift()
    se["inflow"] = (se["level"] - lag).clip(lower=0.0)
    se["outflow"] = (lag - se["level"]).clip(lower=0.0)
    mine = se.groupby(["k", "ware", "epoch"]).agg(
        n=("rid", "size"), si=("inflow", "sum"), so=("outflow", "sum"),
        nn=("inflow", lambda s: int(s.isna().sum())))

    view = pd.read_sql(
        f"SELECT {_KEY} AS k, ware, epoch, COUNT(*) AS n,"
        " SUM(inflow) AS si, SUM(outflow) AS so,"
        " SUM(inflow IS NULL) AS nn"
        " FROM v_stock_flow GROUP BY 1, 2, 3", conn) \
        .set_index(["k", "ware", "epoch"]).sort_index()
    mine = mine.sort_index()
    assert len(mine) == len(view)
    assert (mine["n"] == view["n"]).all()
    assert (mine["nn"] == view["nn"]).all()
    for col in ("si", "so"):
        diff = (mine[col].fillna(0) - view[col].fillna(0)).abs()
        assert diff.max() < 1e-6


def test_v_stock_flow_entity_partition_still_equals_text_partition(conn):
    """Pinned equivalence (plan T6 / C5): entity-first partitioning is
    delta-identical to the retired text-first partitioning on the real
    DB today. If this ever fails, the entity spine started healing (or
    splitting) series the text identity got wrong — that is the view
    working as designed, but it must be noticed, re-verified and this
    assertion re-scoped, not silently absorbed."""
    n = conn.execute("""
        WITH old AS (SELECT rowid AS rid,
               MAX(level - LAG(level) OVER w, 0) AS dv,
               MAX(LAG(level) OVER w - level, 0) AS dv_neg
             FROM stock_event
             WINDOW w AS (PARTITION BY
                 COALESCE(owner_faction || '|' || owner_code, owner_id),
                 ware, epoch ORDER BY time, rowid)),
        new AS (SELECT rowid AS rid,
               MAX(level - LAG(level) OVER w, 0) AS dv,
               MAX(LAG(level) OVER w - level, 0) AS dv_neg
             FROM stock_event
             WINDOW w AS (PARTITION BY
                 COALESCE('e' || owner_entity,
                          owner_faction || '|' || owner_code, owner_id),
                 ware, epoch ORDER BY time, rowid))
        SELECT COUNT(*) FROM old JOIN new USING (rid)
        WHERE old.dv IS NOT new.dv OR old.dv_neg IS NOT new.dv_neg
    """).fetchone()[0]
    assert n == 0


def test_v_stock_delta_alias_matches_flow(conn):
    tot = conn.execute(
        "SELECT COUNT(*), SUM(inflow), SUM(outflow) FROM v_stock_flow"
    ).fetchone()
    alias = conn.execute(
        "SELECT COUNT(*), SUM(dv), SUM(dv_neg) FROM v_stock_delta"
    ).fetchone()
    assert tot == alias
    assert tot[0] == conn.execute(
        "SELECT COUNT(*) FROM stock_event").fetchone()[0]


# ---- v_entity_life vs the entity table (T6 / M2) ----------------------------

def test_v_entity_life_matches_entity_and_snapshot(conn):
    ent = pd.read_sql(
        "SELECT entity_id, first_seen, gone_time FROM entity", conn)
    comp = pd.read_sql(
        "SELECT entity_id, id AS component_id, sector_macro FROM component"
        " WHERE save_id = (SELECT MAX(save_id) FROM save)"
        " AND entity_id IS NOT NULL", conn)
    now = conn.execute(
        "SELECT game_time FROM save"
        " WHERE save_id = (SELECT MAX(save_id) FROM save)").fetchone()[0]
    view = pd.read_sql(
        "SELECT entity_id, observed_span_s, alive, component_id,"
        " sector_macro FROM v_entity_life", conn)

    assert len(view) == len(ent) > 10_000
    merged = view.merge(ent, on="entity_id", validate="one_to_one")
    assert (merged["alive"] == merged["gone_time"].isna()).all()
    span = merged["gone_time"].fillna(now) - merged["first_seen"]
    assert (merged["observed_span_s"] - span).abs().max() < 1e-9

    expect = ent.merge(comp, on="entity_id", how="left",
                       validate="one_to_one")
    got = merged.set_index("entity_id")
    exp = expect.set_index("entity_id").reindex(got.index)
    assert _eq(got["component_id"], exp["component_id"]).all()
    assert _eq(got["sector_macro"], exp["sector_macro"]).all()
    # the join is live: a healthy chunk of entities is on the map now
    assert view["component_id"].notna().sum() > 1000


# ---- v_station vs the retired pandas rollups (T8 / M3) ----------------------

_CUR = "(SELECT MAX(save_id) FROM save)"


def test_v_station_matches_pandas_rollups(conn):
    view = pd.read_sql(
        "SELECT id, modules_built, workforce, cargo_volume_m3"
        " FROM v_station", conn).set_index("id").sort_index()
    stations = pd.read_sql(
        f"SELECT id FROM component WHERE class = 'station'"
        f" AND save_id = {_CUR}", conn)
    assert len(view) == len(stations) > 1000

    built = pd.read_sql(
        f"SELECT host_id FROM module WHERE built = 1"
        f" AND save_id = {_CUR}", conn) \
        .groupby("host_id").size().reindex(view.index).fillna(0)
    assert (view["modules_built"] == built).all()

    wf = pd.read_sql(
        f"SELECT station_id, amount FROM workforce"
        f" WHERE save_id = {_CUR}", conn) \
        .groupby("station_id")["amount"].sum().reindex(view.index)
    assert _eq(view["workforce"], wf).all()

    cargo = pd.read_sql(
        f"SELECT cg.object_id, cg.amount * COALESCE(w.volume, 0) AS vol"
        f" FROM cargo cg LEFT JOIN ware w ON w.id = cg.ware"
        f" WHERE cg.save_id = {_CUR}", conn) \
        .groupby("object_id")["vol"].sum().reindex(view.index)
    diff = (view["cargo_volume_m3"] - cargo).abs()
    assert _eq(view["cargo_volume_m3"], cargo).all() or diff.max() < 1e-6


# ---- v_player_fleet vs the retired resolutions (T8 / M3) --------------------

def test_v_player_fleet_matches_retired_wings_filter(conn):
    """The view must reproduce the retired pandas re-filter (player-owned
    station/ship on both sides) edge-for-edge."""
    fe = pd.read_sql(
        f"SELECT follower_id, commander_id FROM fleet_edge"
        f" WHERE save_id = {_CUR}", conn)
    uni = pd.read_sql(
        f"SELECT id, owner, class FROM component WHERE save_id = {_CUR}",
        conn)
    owned = set(uni[(uni["owner"] == "player")
                    & ((uni["class"] == "station")
                       | uni["class"].str.startswith("ship_"))]["id"])
    old = fe[fe["follower_id"].isin(owned) & fe["commander_id"].isin(owned)]
    view = pd.read_sql(
        "SELECT follower_id, follower_entity, commander_id,"
        " commander_entity FROM v_player_fleet", conn)
    assert len(view) > 50
    assert set(map(tuple, old.values)) \
        == set(map(tuple, view[["follower_id", "commander_id"]].values))
    # both sides are registry-resolvable ships/stations
    assert view["follower_entity"].notna().all()
    assert view["commander_entity"].notna().all()


def _retired_classify(ware, level, yld, start, region_yields, now_t):
    """Verbatim status half of the retired frames._classify closure."""
    cap, delay = region_yields.get((str(level), str(ware)), (0.0, 0.0))
    if yld > 0:
        return "live"
    if not cap:
        return "unknown"
    if delay < 0:
        return "never"
    if start == 0 or start <= now_t:
        return "full"
    return "respawning"


def test_v_resource_area_matches_retired_classify(conn, ref):
    """The plan's scripted 0-mismatch check (T9): the view's status CASE
    reproduces frames' retired classification on every area of the real
    DB. Re-run this whenever B21 changes the regionyields extraction
    (roadmap R5)."""
    # self-contained reference data: a TEMP region_yield shadows the main
    # table, so the check tests the checked-out CSV + view DDL even
    # against a DB whose R tables predate the region_yield load
    conn.execute("DROP TABLE IF EXISTS temp.region_yield")
    conn.execute("CREATE TEMP TABLE region_yield"
                 " (level TEXT, ware TEXT, capacity REAL, respawn_min REAL,"
                 "  PRIMARY KEY (level, ware))")
    conn.executemany(
        "INSERT INTO temp.region_yield VALUES (?,?,?,?)",
        [(level, w, c, d) for (level, w), (c, d)
         in sorted(ref.region_yields.items())])
    res = pd.read_sql(
        "SELECT sector_macro, ware, yield, level, starttime, status"
        " FROM v_resource_area", conn)
    now_t = conn.execute(
        "SELECT game_time FROM save"
        " WHERE save_id = (SELECT MAX(save_id) FROM save)").fetchone()[0]
    assert len(res) > 3000
    expect = [
        _retired_classify(w, lv, y, st, ref.region_yields, now_t)
        for w, lv, y, st in zip(res["ware"], res["level"], res["yield"],
                                res["starttime"])]
    mismatches = int((res["status"] != pd.Series(expect)).sum())
    assert mismatches == 0
    # all the load-bearing states occur in a real save
    assert {"live", "full", "respawning"} <= set(res["status"])


def test_region_yield_table_matches_csv(conn, ref):
    have = conn.execute(
        "SELECT 1 FROM main.sqlite_master"
        " WHERE type = 'table' AND name = 'region_yield'").fetchone()
    rows = {(level, w): (c, d) for level, w, c, d in conn.execute(
        "SELECT level, ware, capacity, respawn_min FROM main.region_yield")
    } if have else {}
    if not rows:
        pytest.skip("region_yield not yet loaded into this DB")
    assert rows == ref.region_yields
    # the unit sentinel: minutes, straight from the CSV
    assert rows[("verylow", "ore")][1] == 20.0


def test_v_player_fleet_no_connectionless_fleet_members(conn):
    """Pinned equivalence (plan-F10): the retired _player_edges resolved
    owners over ALL parsed components, the view joins `component`, which
    excludes connectionless ones — the two differ iff a fleet edge
    touches a connectionless object. Assert none does today; if this
    ever fails, a fleet edge lost commander attribution at merge and the
    divergence must be re-examined, not silently absorbed."""
    n = conn.execute(f"""
        SELECT COUNT(*) FROM fleet_edge fe
        WHERE fe.save_id = {_CUR}
          AND (NOT EXISTS (SELECT 1 FROM component c
                 WHERE c.save_id = fe.save_id AND c.id = fe.follower_id)
            OR NOT EXISTS (SELECT 1 FROM component c
                 WHERE c.save_id = fe.save_id AND c.id = fe.commander_id))
    """).fetchone()[0]
    assert n == 0
