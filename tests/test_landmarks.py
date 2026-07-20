from x4analyzer.save.landmarks import ERLKING_VAULTS, find_landmarks

# cluster -> sector -> zone -> vault, mirroring a real save: the vault itself
# carries no <offset> (so its position is entirely the zone's), while its
# sibling in a second zone carries both
FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<savegame>
<universe>
<component class="galaxy" macro="xu_ep2_universe_macro" id="[0x1]">
<offset><position x="1000000" y="0" z="1000000"/></offset>
<connections>
<connection connection="clusters">
<component class="cluster" macro="cluster_500_macro" id="[0x2]">
<offset><position x="5000" y="0" z="5000"/></offset>
<connections>
<connection connection="sectors">
<component class="sector" macro="cluster_500_sector003_macro" id="[0x3]">
<offset default="1"/>
<connections>
<connection connection="zones">
<component class="zone" macro="zone001_cluster_500_sector003_macro" id="[0x4]">
<offset><position x="-75000" y="1000" z="-41000"/></offset>
<connections>
<connection connection="objects">
<component class="object" macro="landmarks_erlking_vault_01_macro"
          code="GTJ-198" owner="ownerless" id="[0x5]">
<source entry="erlking_blueprint_1" class="godobject"/>
<connections>
<connection connection="connection_pickup001">
<component class="collectableblueprints" macro="props_xs_bp_01_macro"
           blueprints="engine_pir_xl_battleship_01_allround_01_mk1" id="[0x6]">
<offset default="1"/>
</component>
</connection>
</connections>
</component>
</connection>
</connections>
</component>
</connection>
<connection connection="zones">
<component class="zone" macro="zone004_cluster_500_sector003_macro" id="[0x7]">
<offset><position x="100" y="200" z="300"/></offset>
<connections>
<connection connection="objects">
<component class="object" macro="landmarks_erlking_vault_05_macro"
           code="MXH-976" owner="ownerless" id="[0x8]">
<offset><position x="14000" y="300" z="5500"/></offset>
<source entry="erlking_blueprint_5" class="godobject"/>
</component>
</connection>
</connections>
</component>
</connection>
</connections>
</component>
</connection>
</connections>
</component>
</connection>
</connections>
</component>
</universe>
</savegame>
"""


def _find(tmp_path, pattern=ERLKING_VAULTS):
    p = tmp_path / "save.xml"
    p.write_text(FIXTURE)
    return {h.code: h for h in find_landmarks(p, pattern)}


def test_finds_every_vault(tmp_path):
    hits = _find(tmp_path)
    assert set(hits) == {"GTJ-198", "MXH-976"}
    assert hits["GTJ-198"].source_entry == "erlking_blueprint_1"


def test_position_is_sector_relative(tmp_path):
    hits = _find(tmp_path)
    # galaxy/cluster offsets are excluded, the zone offset is not
    assert hits["GTJ-198"].km == (-75.0, 1.0, -41.0)
    # zone offset + the object's own offset
    assert hits["MXH-976"].km == (14.1, 0.5, 5.8)


def test_ancestry(tmp_path):
    h = _find(tmp_path)["GTJ-198"]
    assert h.cluster_macro == "cluster_500_macro"
    assert h.sector_macro == "cluster_500_sector003_macro"


def test_blueprints_attributed_to_the_vault(tmp_path):
    hits = _find(tmp_path)
    assert hits["GTJ-198"].blueprints == [
        "engine_pir_xl_battleship_01_allround_01_mk1"]
    # a looted vault has no pickup component left
    assert hits["MXH-976"].blueprints == []


def test_arbitrary_macro_pattern(tmp_path):
    hits = _find(tmp_path, r"^props_xs_bp")
    assert list(hits) == [""]          # the pickup has no code
    assert hits[""].macro == "props_xs_bp_01_macro"
