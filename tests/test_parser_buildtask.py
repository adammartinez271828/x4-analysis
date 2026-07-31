"""Build tasks: the `<build>` elements carrying type=/order= (v29).

The save keeps ONE logical build order in two shapes — the order wrapper
under `<buildtasks><queue|inprogress>` of a station/build storage, and its
live progress on a `buildprocessor` component inside one of that host's
build/dock modules — sharing one id space (wrapper id= <-> processor
order=). The parser records both; the store keys them per host so the two
rows join, and `v_build_storage_station` exposes the build storage ->
station link the expand task carries.

Fixture geometry mirrors the real save (docs/reports/build-demand-2026-07-30
.md): a build storage expanding a station, a wharf with a queued and an
in-progress buildship order, and a station `<build method=>` CONFIG element
of the same tag name that must stay out of this table.
"""
from pathlib import Path

import pytest

from x4analyzer.config import Config
from x4analyzer.db import store
from x4analyzer.gamedata.refdata import load_refdata
from x4analyzer.save.parser import parse_savegame

FIXTURE = """<?xml version="1.0"?>
<savegame>
  <info>
    <save name="#002" date="1700000001"/>
    <game guid="BUILD-TASK" version="900" time="82000.0"/>
    <player name="Test Pilot" money="100"/>
  </info>
  <universe>
    <component class="galaxy" id="[0x1]" connection="space">
      <connections><connection connection="galaxy">
      <component class="cluster" macro="cluster_01_macro" id="[0x10]" connection="galaxy">
        <connections><connection connection="cluster">
        <component class="sector" macro="cluster_01_sector001_macro" id="[0x11]"
                   connection="cluster">
        <connections><connection connection="sector">
          <!-- the station being expanded -->
          <component class="station" macro="station_macro" id="[0xA0]"
                     owner="argon" code="ALP-001" connection="sector">
            <build method="closedloop"/>
            <construction><sequence>
              <entry id="[0x50]" index="1" macro="mod_a_macro"/>
            </sequence></construction>
          </component>
          <!-- its build storage: the expand task names the station -->
          <component class="buildstorage" macro="buildstorage_macro" id="[0xB9]"
                     owner="argon" code="BST-001" connection="sector">
            <buildtasks><inprogress>
              <build id="[0x99]" type="expand" preexisting="1" builder="[0xC1]"
                     component="[0xA0]" faction="argon" time="6206.4"
                     flags="nothing">
                <sequence>
                  <entry id="[0x50]" index="1" macro="mod_a_macro"/>
                </sequence>
                <paint inventory="0"/>
              </build>
            </inprogress></buildtasks>
            <connections><connection connection="modules">
              <component class="buildmodule" macro="buildmodule_macro" id="[0xBA]"
                         connection="modules">
                <connections><connection connection="processor">
                  <component class="buildprocessor" macro="proc_macro" id="[0xBB]"
                             connection="processor">
                    <build start="75593.2" step="1" steps="4" method="argon"
                           secondary="checkresources" constructionvesselrequired="1"
                           increasehull="1" type="build"
                           state="waitingforresources" sequenceindex="5"
                           order="[0x99]">
                      <resources>
                        <ware ware="claytronics" amount="12"/>
                        <insufficient>
                          <ware ware="claytronics" amount="75593"/>
                        </insufficient>
                      </resources>
                    </build>
                  </component>
                </connection></connections>
              </component>
            </connection></connections>
          </component>
          <!-- a wharf: one queued and one in-progress ship order -->
          <component class="station" macro="wharf_macro" id="[0xD0]"
                     owner="player" code="WHF-001" connection="sector">
            <buildtasks>
              <queue>
                <build id="[0x1a2]" type="buildship" preexisting="1"
                       builder="[0xD1]" component="[0xE1]" faction="player"
                       time="80511.5" flags="nothing">
                  <paint inventory="0"/>
                  <resources><insufficient>
                    <ware ware="hullparts" amount="80511"/>
                  </insufficient></resources>
                </build>
              </queue>
              <inprogress>
                <build id="[0x1a3]" type="buildship" builder="[0xD1]"
                       component="[0xE2]" faction="player" time="80600.0"
                       macro="SHIP_TER_M_TRANS_CONTAINER_01_A_MACRO"/>
              </inprogress>
            </buildtasks>
          </component>
          <!-- the ships those orders point at. The QUEUED one is a hull
               the yard holds: a real component with no @connection, so it
               never lands in the `component` table (as on save_002, where
               191 of 214 buildship targets are like this) -->
          <component class="ship_s" macro="ship_arg_s_scout_01_a_macro"
                     id="[0xE1]" owner="player" code="SHP-001"
                     spawntime="80511.5"/>
          <component class="ship_m" macro="ship_ter_m_trans_container_01_a_macro"
                     id="[0xE2]" owner="player" code="SHP-002"
                     spawntime="12.0" connection="sector"/>
        </connection></connections>
        </component>
        </connection></connections>
      </component>
      </connection></connections>
    </component>
  </universe>
</savegame>
"""

COLS = ("host_id", "comp_id", "kind", "task_id", "ctx", "type", "target_id",
        "builder", "faction", "time", "flags", "preexisting", "method",
        "state", "step", "steps", "start", "end", "sequence_index", "macro")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    p = tmp_path_factory.mktemp("bt") / "save.xml"
    p.write_text(FIXTURE)
    return parse_savegame(p)


def _row(data, task_id, kind):
    rows = [dict(zip(COLS, r)) for r in data.build_tasks
            if r[3] == task_id and r[2] == kind]
    assert len(rows) == 1, (task_id, kind)
    return rows[0]


# ---- parser ---------------------------------------------------------------

def test_all_type_or_order_builds_collected(data):
    assert len(data.build_tasks) == 4
    assert sorted((r[2], r[3]) for r in data.build_tasks) == [
        ("progress", "[0x99]"), ("task", "[0x1a2]"), ("task", "[0x1a3]"),
        ("task", "[0x99]")]


def test_expand_task_carries_the_station(data):
    r = _row(data, "[0x99]", "task")
    assert r["host_id"] == "[0xB9]"       # the build storage
    assert r["comp_id"] == "[0xB9]"
    assert r["target_id"] == "[0xA0]"     # the station it is building
    assert (r["ctx"], r["type"]) == ("inprogress", "expand")
    assert (r["builder"], r["faction"]) == ("[0xC1]", "argon")
    assert (r["time"], r["flags"], r["preexisting"]) == ("6206.4", "nothing",
                                                         "1")


def test_progress_row_attributes_to_the_host_not_the_processor(data):
    r = _row(data, "[0x99]", "progress")
    # nearest station/buildstorage ancestor, not the buildmodule the
    # processor sits in
    assert r["host_id"] == "[0xB9]"
    assert r["comp_id"] == "[0xBB]"
    assert r["ctx"] == "processor"
    assert (r["type"], r["state"]) == ("build", "waitingforresources")
    assert (r["step"], r["steps"], r["sequence_index"]) == ("1", "4", "5")
    assert (r["method"], r["start"]) == ("argon", "75593.2")
    assert r["target_id"] == ""           # progress names no target


def test_progress_joins_its_task_on_host_and_id(data):
    task = _row(data, "[0x99]", "task")
    prog = _row(data, "[0x99]", "progress")
    assert (prog["host_id"], prog["task_id"]) == (task["host_id"],
                                                  task["task_id"])


def test_buildship_orders(data):
    queued = _row(data, "[0x1a2]", "task")
    assert (queued["host_id"], queued["ctx"]) == ("[0xD0]", "queue")
    assert (queued["type"], queued["target_id"]) == ("buildship", "[0xE1]")
    live = _row(data, "[0x1a3]", "task")
    assert (live["ctx"], live["target_id"]) == ("inprogress", "[0xE2]")
    assert live["macro"] == "SHIP_TER_M_TRANS_CONTAINER_01_A_MACRO"


def test_build_config_element_is_not_a_task(data):
    """`<build method=>` under a station is the build-method OVERRIDE (v21),
    the same tag name with neither type= nor order=. It must stay in
    station_build_methods and out of build_tasks."""
    assert data.station_build_methods == [("[0xA0]", "closedloop")]
    assert not [r for r in data.build_tasks if r[0] == "[0xA0]"]


def test_insufficient_amounts_are_not_read_as_quantities(data):
    """E-068: the <insufficient>/<shortage> amounts are NOT per-ware
    quantities. The build_task handler reads no ware amounts at all — the
    ware NAMES keep going to build_resource, unchanged — and the wharf's
    buildship aggregate stays excluded there, as before."""
    assert all(len(r) == len(COLS) for r in data.build_tasks)
    assert {(host, ware, kind) for (host, ware, _amt, kind)
            in data.build_resources} == {
        ("[0xB9]", "claytronics", "insufficient")}


def test_unknown_task_type_does_not_crash(tmp_path: Path):
    """A modded/unknown task type is data, not an error."""
    p = tmp_path / "save.xml"
    p.write_text(FIXTURE.replace('type="buildship"', 'type="modthing"'))
    d = parse_savegame(p)
    assert sorted(r[5] for r in d.build_tasks) == [
        "build", "expand", "modthing", "modthing"]


# ---- store ----------------------------------------------------------------

@pytest.fixture(scope="module")
def ref():
    return load_refdata(Path("/nonexistent"))   # packaged reference CSVs


@pytest.fixture(scope="module")
def conn(tmp_path_factory, data, ref):
    cfg = Config()
    cfg.data_dir = tmp_path_factory.mktemp("db")
    conn = store.open_db(cfg, data.guid)
    store.write_reference(conn, ref)
    store.write_snapshot(conn, data, ref, "save.xml")
    yield conn
    conn.close()


def test_store_round_trip(conn):
    rows = conn.execute(
        "SELECT host_id, comp_id, kind, task_id, ctx, type, target_id,"
        " target_class, target_macro, target_code,"
        " builder, faction, time, flags, preexisting, method, state, step,"
        " steps, start_time, end_time, sequence_index, macro"
        " FROM build_task ORDER BY kind, task_id").fetchall()
    assert rows == [
        ("[0xB9]", "[0xBB]", "progress", "[0x99]", "processor", "build",
         None, None, None, None,
         None, None, None, None, None, "argon", "waitingforresources",
         1, 4, 75593.2, None, 5, None),
        ("[0xD0]", "[0xD0]", "task", "[0x1a2]", "queue", "buildship",
         "[0xE1]", "ship_s", "ship_arg_s_scout_01_a_macro", "SHP-001",
         "[0xD1]", "player", 80511.5, "nothing", 1, None, None,
         None, None, None, None, None, None),
        ("[0xD0]", "[0xD0]", "task", "[0x1a3]", "inprogress", "buildship",
         "[0xE2]", "ship_m", "ship_ter_m_trans_container_01_a_macro",
         "SHP-002",
         "[0xD1]", "player", 80600.0, None, None, None, None,
         None, None, None, None, None,
         "ship_ter_m_trans_container_01_a_macro"),   # lowercased
        ("[0xB9]", "[0xB9]", "task", "[0x99]", "inprogress", "expand",
         "[0xA0]", "station", "station_macro", "ALP-001",
         "[0xC1]", "argon", 6206.4, "nothing", 1, None, None,
         None, None, None, None, None, None),
    ]


def test_reimport_adds_nothing(conn, data, ref):
    before = conn.execute("SELECT COUNT(*) FROM build_task").fetchone()[0]
    store.write_snapshot(conn, data, ref, "save.xml")
    after = conn.execute("SELECT COUNT(*) FROM build_task").fetchone()[0]
    assert (before, after) == (4, 4)
    # world rows belong to the newest snapshot only (W-table rotation)
    assert conn.execute(
        "SELECT COUNT(DISTINCT save_id) FROM build_task").fetchone()[0] == 1


def test_unresolvable_target_loads_as_null(tmp_path, ref):
    """A target the save's component index does not carry (a removed or
    mod-owned object) must load as NULLs, never fail the import."""
    p = tmp_path / "save.xml"
    p.write_text(FIXTURE.replace('component="[0xE1]"',
                                 'component="[0xDEAD]"'))
    data = parse_savegame(p)
    cfg = Config()
    cfg.data_dir = tmp_path
    conn = store.open_db(cfg, data.guid)
    try:
        store.write_reference(conn, ref)
        store.write_snapshot(conn, data, ref, "save.xml")
        assert conn.execute(
            "SELECT target_id, target_class, target_macro, target_code"
            " FROM build_task WHERE task_id = '[0x1a2]'").fetchall() == [
            ("[0xDEAD]", None, None, None)]
    finally:
        conn.close()


def test_v_build_storage_station(conn):
    assert conn.execute(
        "SELECT storage_id, storage_code, station_id, station_code,"
        " station_macro, ctx, n_tasks"
        " FROM v_build_storage_station").fetchall() == [
        ("[0xB9]", "BST-001", "[0xA0]", "ALP-001", "station_macro",
         "inprogress", 1)]


def test_v_build_task_resolves_target_and_progress(conn):
    rows = {r[0]: r for r in conn.execute(
        "SELECT task_id, host_code, type, target_code, target_macro,"
        " target_spawntime, state, step, steps FROM v_build_task")}
    assert rows["[0x99]"] == ("[0x99]", "BST-001", "expand", "ALP-001",
                              "station_macro", None,
                              "waitingforresources", 1, 4)
    # a queued ship order resolves its ship from the DENORMALIZED columns
    # even though the unplaced hull is absent from `component` (so the
    # component-sourced spawntime is NULL); nothing is working it yet
    assert conn.execute(
        "SELECT COUNT(*) FROM component WHERE id = '[0xE1]'"
    ).fetchone() == (0,)
    assert rows["[0x1a2]"] == ("[0x1a2]", "WHF-001", "buildship", "SHP-001",
                               "ship_arg_s_scout_01_a_macro", None,
                               None, None, None)
