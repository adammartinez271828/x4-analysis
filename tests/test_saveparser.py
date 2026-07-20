import gzip
from pathlib import Path

import pytest

from x4analyzer.save.parser import parse_savegame

FIXTURE = """<?xml version="1.0"?>
<savegame>
  <info>
    <save name="#001" date="1700000000"/>
    <game guid="ABCD-1234" version="900" time="5000.5" modified="1"/>
    <player name="Test Pilot" money="123456"/>
  </info>
  <universe>
    <factions>
      <faction id="player">
        <custom><name name="Testers"/></custom>
      </faction>
      <faction id="argon"/>
    </factions>
    <component class="galaxy" id="[0x1]" connection="space">
      <connections><connection connection="galaxy">
      <component class="cluster" macro="cluster_01_macro" id="[0x10]" connection="galaxy">
        <connections><connection connection="cluster">
        <component class="sector" macro="cluster_01_sector001_macro" id="[0x11]"
                   owner="argon" knownto="player" contested="1" connection="cluster">
          <component class="collectablewares" macro="sm_gen_scrap_cube_macro"
                     connection="sector" id="[0x60]">
            <wares><ware ware="rawscrap" amount="1000"/></wares>
          </component>
          <resourceareas>
            <area yieldid="sphere_large_ore_high_slow" yield="1000" starttime="0"/>
            <area yieldid="sphere_medium_silicon_low" yield="200" starttime="0"/>
          </resourceareas>
          <connections><connection connection="sector">
          <component class="zone" macro="zone001_macro" id="[0x15]" connection="sector">
          <offset><position x="1000" y="5" z="-2000"/></offset>
          <connections><connection connection="zone">
          <component class="station" macro="station_macro" id="[0x20]" owner="player"
                     code="STA-001" factionheadquarters="1" connection="zone">
            <offset><position x="500" y="0" z="250"/></offset>
            <control>
              <post id="manager" component="[0x99]"/>
            </control>
            <workforces lasttime="1.0"><workforce race="argon" amount="50"/></workforces>
            <construction><sequence>
              <entry id="[0x50]" index="1" macro="mod_a_macro"/>
              <entry id="[0x51]" index="3" macro="mod_b_macro"/>
            </sequence></construction>
            <trade><offers><production>
              <trade id="[0xT1]" buyer="[0x21]" ware="energycells"
                     price="100" amount="500" desired="500"/>
            </production></offers></trade>
            <build><resources><insufficient>
              <ware ware="claytronics" amount="1000"/>
            </insufficient></resources></build>
            <connections>
              <connection connection="subordinates" id="[0xC1]"/>
              <connection connection="dock">
              <component class="ship_s" macro="ship_test_macro" id="[0x30]"
                         owner="player" code="SHP-001" connection="dock">
                <control><post id="aipilot" component="[0x99]"/></control>
                <people>
                  <person macro="char_svc_macro" role="service"/>
                  <person macro="char_svc_macro" role="service"/>
                  <person macro="char_pax_macro" role="passenger"/>
                </people>
                <orders>
                  <order id="[0xA1]" default="1" order="Wait" state="started"/>
                </orders>
                <connections>
                  <connection connection="commander" id="[0xC9]">
                    <connected connection="[0xC1]"/>
                  </connection>
                </connections>
                <component class="npc" macro="char_macro" id="[0x99]" owner="player"
                           name="Jane Doe" code="NPC-001" connection="crew">
                  <skills piloting="9" morale="7" engineering="3"/>
                </component>
              </component>
              </connection>
            </connections>
          </component>
          <component class="datavault" macro="landmarks_vault_02_macro"
                     id="[0x70]" code="KBE-495" owner="ownerless"
                     knownto="player" connection="space">
            <offset><position x="-100" y="0" z="300"/></offset>
            <unlock state="unlocked"/>
            <connections/>
          </component>
          <component class="object" macro="landmarks_erlking_vault_04_macro"
                     id="[0x80]" code="WYH-699" owner="ownerless"
                     connection="space">
            <offset><position x="4000" y="0" z="-500"/></offset>
            <connections>
              <connection connection="connection_pickup">
                <component class="collectablewares" macro="sm_gen_wares_macro"
                           connection="connection01" id="[0x81]">
                  <offset default="1"/>
                  <wares><ware ware="inv_modulartrigger"/></wares>
                </component>
              </connection>
              <connection connection="connection_blueprint">
                <component class="collectableblueprints"
                           macro="props_sm_container_xs_erlking_bp_04_macro"
                           connection="connection01" code="WNG-368"
                           blueprints="turret_pir_l_battleship_01_laser_01_mk1"
                           id="[0x82]">
                  <offset default="1"/>
                </component>
              </connection>
            </connections>
          </component>
          </connection></connections>
          </component>
          </connection></connections>
        </component>
        </connection></connections>
      </component>
      </connection></connections>
    </component>
  </universe>
  <economylog>
    <entries type="trade">
      <log time="10.5" type="trade" ware="energycells" buyer="[0x20]"
           seller="[0x77]" price="1600" v="100"/>
      <log time="11.0" type="trade" ware="ice" owner="[0x20]" v="50"/>
    </entries>
    <removed>
      <object id="115" owner="teladi" name="TEL Trader" code="TDR-001"/>
    </removed>
  </economylog>
  <log>
    <entry time="100.0" category="upkeep" title="Test entry" text="text"/>
  </log>
</savegame>
"""


@pytest.fixture(params=["plain", "gz"])
def save_file(tmp_path: Path, request) -> Path:
    if request.param == "gz":
        p = tmp_path / "save.xml.gz"
        with gzip.open(p, "wt") as fh:
            fh.write(FIXTURE)
    else:
        p = tmp_path / "save.xml"
        p.write_text(FIXTURE)
    return p


def test_fixture_parse(save_file: Path) -> None:
    d = parse_savegame(save_file)

    assert d.guid == "ABCD-1234"
    assert d.game_version == "900"
    assert d.game_time == 5000.5
    assert d.modified is True
    assert d.player_name == "Test Pilot"
    assert d.player_faction_name == "Testers"

    classes = {c[1] for c in d.components}
    assert classes == {"cluster", "sector", "station", "ship_s"}
    ship = next(c for c in d.components if c[1] == "ship_s")
    # ancestry: cluster and sector ids/macros propagated
    assert ship[10] == "[0x10]" and ship[12] == "[0x11]"
    # real containment via the nearest COLLECTED ancestor: the ship is
    # docked at the station; the station's enclosing zone (never a
    # component row) is skipped so its parent resolves to the sector
    assert ship[15] == "[0x20]"
    station = next(c for c in d.components if c[1] == "station")
    assert station[15] == "[0x11]"
    # sector-local position: the station's own offset summed with its
    # enclosing zone's offset (y dropped); faction HQ flag captured
    assert (station[16], station[17]) == (1500.0, -1750.0)
    assert station[18] == "1"
    # ships don't get positions
    assert (ship[16], ship[17]) == (None, None)
    sector = next(c for c in d.components if c[1] == "sector")
    assert sector[7] == "1"  # contested

    assert ("[0x20]", "manager", "[0x99]") in d.posts
    assert ("[0x30]", "aipilot", "[0x99]") in d.posts
    assert ("[0x20]", "argon", 50.0) in d.workforce
    # module count keeps max construction index; macro kept for market stats
    assert max(m[1] for m in d.modules if m[0] == "[0x20]") == 3
    assert ("[0x20]", 1, "mod_a_macro", "[0x50]", "") in d.modules

    assert len(d.npcs) == 1
    npc = d.npcs[0]
    assert npc[1] == "Jane Doe" and npc[4]["piloting"] == 9.0

    assert d.commander_links == [("[0x30]", "[0xC1]")]
    assert d.subordinate_conns == [("[0x20]", "[0xC1]")]

    assert d.resources == [
        ("cluster_01_sector001_macro", "ore", 1000.0),
        ("cluster_01_sector001_macro", "silicon", 200.0),
    ]

    assert d.people == {("[0x30]", "service"): 2, ("[0x30]", "passenger"): 1}

    assert ("[0x20]", "buy", "energycells", 500.0, 1.0) in d.trade_offers
    assert ("[0x30]", "Wait", True, "started") in d.orders
    assert ("[0x20]", "claytronics", 1000.0, "insufficient") \
        in d.build_resources
    assert ("cluster_01_sector001_macro", "rawscrap", 1000.0) \
        in d.floating_wares

    # data vaults: matched on macro (classes differ), sector-local
    # position summed over the zone offset like stations
    assert len(d.datavaults) == 2
    plain = next(v for v in d.datavaults if v[0] == "[0x70]")
    assert plain[1] == "landmarks_vault_02_macro"
    assert plain[2] == "KBE-495" and plain[3] == "player"
    assert plain[4] == "cluster_01_sector001_macro"
    assert (plain[5], plain[6]) == (900.0, -1700.0)
    assert plain[7] == 1 and plain[8] == 0 and plain[9] == ""  # opened, empty
    erl = next(v for v in d.datavaults if v[0] == "[0x80]")
    assert erl[1] == "landmarks_erlking_vault_04_macro"
    assert (erl[5], erl[6]) == (5000.0, -2500.0)
    assert erl[7] == 0 and erl[8] == 2  # locked; wares + blueprint inside
    assert erl[9] == "turret_pir_l_battleship_01_laser_01_mk1"

    assert len(d.trades) == 2  # frames layer filters the owner-only entry
    assert d.trades[0]["ware"] == "energycells"
    assert d.removed_objects[0]["name"] == "TEL Trader"
    assert d.log_entries[0]["title"] == "Test entry"
