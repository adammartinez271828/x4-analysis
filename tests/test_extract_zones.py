"""zones.csv extraction (gamedata/extract.py:extract_zones).

A zone's sector-local offset lives ONLY in the map files: the save writes
`<offset default="1"/>` for every static zone (E-151). These tests pin the
reading of `maps/xu_ep2_universe/*sectors.xml` — including the two things
that bite here, extension load order and `<diff>` patches from mods.
"""
from pathlib import Path

from x4analyzer.gamedata.catalog import GameFiles
from x4analyzer.gamedata.extract import extract_zones

from test_catalog import make_cat

BASE_SECTORS = b"""<macros>
  <macro name="Cluster_01_Sector001_macro" class="sector">
    <connections>
      <connection name="Zone001_connection" ref="zones">
        <offset><position x="1000.5" z="-2000"/></offset>
        <macro ref="Zone001_Cluster_01_Sector001_macro" connection="sector"/>
      </connection>
      <connection name="Zone002_connection" ref="zones">
        <offset><position x="10" y="25" z="30"/></offset>
        <macro ref="Zone002_Cluster_01_Sector001_macro" connection="sector"/>
      </connection>
      <connection name="Highway_connection" ref="zonehighways">
        <offset><position x="7" z="8"/></offset>
        <macro ref="Highway01_macro" connection="cluster"/>
      </connection>
    </connections>
  </macro>
</macros>
"""

EXT_SECTORS = b"""<macros>
  <macro name="Cluster_99_Sector001_macro" class="sector">
    <connections>
      <connection name="Zone001_connection" ref="zones">
        <macro ref="Zone001_Cluster_99_Sector001_macro" connection="sector"/>
      </connection>
    </connections>
  </macro>
</macros>
"""

# a mod patching zones into an existing sector: one op names the sector it
# patches, the other does not
DIFF_SECTORS = b"""<diff>
  <add sel="//macro[@name='Cluster_01_Sector001_macro']/connections">
    <connection name="Zone900_connection" ref="zones">
      <offset><position x="500" z="600"/></offset>
      <macro ref="Zone900_modded_macro" connection="sector"/>
    </connection>
  </add>
  <add sel="//connections">
    <connection name="Zone901_connection" ref="zones">
      <offset><position x="1" z="2"/></offset>
      <macro ref="Zone901_modded_macro" connection="sector"/>
    </connection>
  </add>
</diff>
"""


def _rows(tmp_path: Path, **extras: bytes) -> dict[str, list]:
    make_cat(tmp_path, "01", {
        "maps/xu_ep2_universe/sectors.xml": BASE_SECTORS,
    })
    exts = []
    for name, files in extras.items():
        d = tmp_path / "extensions" / name
        d.mkdir(parents=True)
        make_cat(d, "ext_01", files)
        exts.append(name)
    gf = GameFiles(tmp_path, extensions=exts)
    return {r[1]: r for r in extract_zones(gf)}


def test_base_sector_zones(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    # the zonehighways connection is not a zone
    assert set(rows) == {"zone001_cluster_01_sector001_macro",
                         "zone002_cluster_01_sector001_macro"}
    # macros lowercased on both sides, metres kept as floats, a missing
    # axis is 0.0 (the y of a 2-D sector layout)
    assert rows["zone001_cluster_01_sector001_macro"] == [
        "cluster_01_sector001_macro", "zone001_cluster_01_sector001_macro",
        1000.5, 0.0, -2000.0, ""]
    assert rows["zone002_cluster_01_sector001_macro"][2:5] == [10.0, 25.0, 30.0]


def test_extension_sectors_are_included_with_their_source(
        tmp_path: Path) -> None:
    rows = _rows(tmp_path, ego_dlc_x={
        "maps/xu_ep2_universe/dlc_sectors.xml": EXT_SECTORS})
    row = rows["zone001_cluster_99_sector001_macro"]
    assert row[0] == "cluster_99_sector001_macro"
    assert row[5] == "ego_dlc_x"
    # a connection with no <offset> at all sits at the sector centre
    assert row[2:5] == [0.0, 0.0, 0.0]


def test_diff_patches_from_mods(tmp_path: Path) -> None:
    rows = _rows(tmp_path, somemod={
        "maps/xu_ep2_universe/mod_sectors.xml": DIFF_SECTORS})
    # sel= names the sector it patches
    assert rows["zone900_modded_macro"] == [
        "cluster_01_sector001_macro", "zone900_modded_macro",
        500.0, 0.0, 600.0, "somemod"]
    # sel= that cannot be resolved still yields a row: consumers key on the
    # zone macro, so the offset places objects either way
    assert rows["zone901_modded_macro"][0] == ""
    assert rows["zone901_modded_macro"][2:5] == [1.0, 0.0, 2.0]


def test_a_mod_overrides_the_base_game_not_the_other_way_round(
        tmp_path: Path) -> None:
    """gf.glob sorts lexically, so "extensions/..." comes BEFORE "maps/...":
    without the base-first reordering the base game would overwrite the
    extension's copy of a sector."""
    override = BASE_SECTORS.replace(b'x="1000.5" z="-2000"',
                                    b'x="77" z="88"')
    rows = _rows(tmp_path, somemod={
        "maps/xu_ep2_universe/sectors.xml": override})
    row = rows["zone001_cluster_01_sector001_macro"]
    assert row[2:5] == [77.0, 0.0, 88.0]
    assert row[5] == "somemod"


def test_an_emptied_mod_file_is_skipped(tmp_path: Path) -> None:
    rows = _rows(tmp_path, somemod={
        "maps/xu_ep2_universe/sectors.xml": b""})
    assert rows["zone001_cluster_01_sector001_macro"][2] == 1000.5


def test_rows_are_sorted(tmp_path: Path) -> None:
    make_cat(tmp_path, "01", {
        "maps/xu_ep2_universe/sectors.xml": BASE_SECTORS,
    })
    gf = GameFiles(tmp_path, extensions=[])
    rows = extract_zones(gf)
    assert rows == sorted(rows, key=lambda r: (r[0], r[1]))
