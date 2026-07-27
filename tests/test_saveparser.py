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
        <buildrules method="terran"/>
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
            <area yieldid="sphere_large_ore_high_slow" yield="0" starttime="4000"/>
            <area yieldid="sphere_large_ore_high_slow" yield="0" starttime="9000"/>
          </resourceareas>
          <connections><connection connection="sector">
          <component class="zone" macro="zone001_macro" id="[0x15]" connection="sector">
          <offset><position x="1000" y="5" z="-2000"/></offset>
          <connections><connection connection="zone">
          <component class="station" macro="station_macro" id="[0x20]" owner="player"
                     code="STA-001" factionheadquarters="1" known="1"
                     connection="zone">
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
              <trade id="[0xT2]" buyer="[0x21]" ware="dronecomponents"
                     price="200" amount="0" desired="50"
                     flags="supplies|invertfactionrestriction"/>
            </production></offers>
            <prices buildpricefactor="1.07">
              <reference><ware ware="energycells" buy="12" sell="0"/></reference>
              <override>
                <ware ware="energycells" buy="21" sell="0"/>
                <ware ware="claytronics" buy="0" sell="1734"/>
              </override>
            </prices>
            <overrides>
              <max><ware ware="energycells" amount="739800"/>
                   <ware ware="weaponcomponents"/></max>
              <buy><ware ware="energycells" amount="739800"/></buy>
              <sell><ware ware="siliconcarbide" amount="5184"/></sell>
            </overrides>
            <settings>
              <setting name="buy" wares="spaceweed majadust"/>
              <setting name="lockavgprice" wares="spaceweed"/>
            </settings>
            <active>
              <trade id="[0xT3]" seller="[0x20]" buyer="[0x77]" partner="[0x77]"
                     ware="energycells" price="150" escrow="30000" amount="100"
                     transferred="40" desired="140" flags="fixedprice"/>
            </active>
            <reservations>
              <reservation reserver="[0x30]" id="[0xT3]" seller="[0x20]"
                     buyer="[0x77]" partner="[0x77]" ware="energycells"
                     price="150" escrow="30000" amount="100" transferred="40"
                     desired="140" flags="fixedprice"/>
              <reservation reserver="[0x30]" id="[0xT4]" buyer="[0x20]"
                     partner="[0x88]" ware="ore" price="5000" amount="60"
                     desired="60" time="9000.5" flags="fixedprice"/>
            </reservations></trade>
            <supplies>
              <wares><ware ware="metallicmicrolattice" amount="1200"/></wares>
              <orders>
                <ware ware="ship_gen_xs_repairdrone_01_a" amount="10"/>
              </orders>
            </supplies>
            <build><resources><insufficient>
              <ware ware="claytronics" amount="1000"/>
            </insufficient></resources></build>
            <build method="closedloop"/>
            <connections>
              <connection connection="subordinates" id="[0xC1]"/>
              <connection connection="build">
                <component class="buildprocessor" id="[0x25]" connection="build">
                  <build method="argon" order="[0x9]" type="build" state="inprogress">
                    <nextresources><ware ware="hullparts" amount="10"/></nextresources>
                  </build>
                </component>
              </connection>
              <connection connection="dock">
              <component class="ship_s" macro="ship_test_macro" id="[0x30]"
                         owner="player" code="SHP-001" connection="dock">
                <control><post id="aipilot" component="[0x99]"/></control>
                <supplies>
                  <wares><ware ware="missile_dumb_mk1" amount="8"/></wares>
                </supplies>
                <people>
                  <person macro="char_svc_macro" role="service"/>
                  <person macro="char_svc_macro" role="service"/>
                  <person macro="char_pax_macro" role="passenger"/>
                </people>
                <orders>
                  <order id="[0xA1]" default="1" order="Wait" state="started">
                    <trade id="[0xT3]" seller="[0x20]" buyer="[0x77]"
                           partner="[0x77]" ware="energycells" price="150"
                           escrow="30000" amount="100" transferred="40"
                           desired="140" flags="fixedprice"/>
                    <trade id="[0xT4]" buyer="[0x20]" partner="[0x88]"
                           ware="ore" price="5000" amount="60" desired="60"
                           flags="fixedprice"/>
                  </order>
                </orders>
                <connections>
                  <connection connection="commander" id="[0xC9]">
                    <connected connection="[0xC1]"/>
                  </connection>
                  <connection connection="con_engine01">
                    <component class="engine" connection="engine"
                        macro="engine_arg_s_travel_01_mk3_macro" id="[0x31]"/>
                  </connection>
                  <connection connection="con_engine02">
                    <component class="engine" connection="engine"
                        macro="engine_arg_s_travel_01_mk3_macro" id="[0x32]"/>
                  </connection>
                </connections>
                <component class="npc" macro="char_macro" id="[0x99]" owner="player"
                           name="Jane Doe" code="NPC-001" connection="crew">
                  <skills piloting="9" morale="7" engineering="3"/>
                </component>
                <component class="player" macro="character_player_macro"
                           id="[0x9A]" owner="player" name="Test Player"
                           connection="player">
                  <memory>
                    <subscriptions>
                      <item component="[0x20]" time="9000.5"/>
                      <item component="[0x30]" time="1000.0"/>
                      <item component="[0x40]"/>
                    </subscriptions>
                    <scan>
                      <item component="[0x20]" level="2"/>
                    </scan>
                  </memory>
                </component>
              </component>
              </connection>
            </connections>
          </component>
          <component class="highway" connection="zonehighways"
                     macro="highway01_cluster_01_macro" id="[0x99a]">
            <offset default="1"/>
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
    <entries type="cargo">
      <log time="11.0" type="trade" ware="ice" owner="[0x20]" v="50"/>
      <log time="11.5" type="produce" ware="ice" owner="[0x20]" v="60"/>
    </entries>
    <entries type="trade">
      <log time="10.5" type="trade" ware="energycells" buyer="[0x20]"
           seller="[0x77]" price="1600" v="100"/>
      <log time="12.0" type="transfer" ware="ice" buyer="[0x30]"
           seller="[0x20]" v="25" b="25" bmax="100"/>
    </entries>
    <entries type="money">
      <log time="10.7" type="trade" owner="[0x20]" partner="[0x77]"
           tradeentry="1" v="16000000"/>
    </entries>
    <removed>
      <object id="115" owner="teladi" name="TEL Trader" code="TDR-001"/>
    </removed>
  </economylog>
  <log>
    <entry time="100.0" category="upkeep" title="Test entry" text="text" interact="showlocation"/>
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
    assert station[19] == "1"      # known flag (v20)
    assert ship[19] == ""          # absent known -> ""
    # ships don't get positions
    assert (ship[16], ship[17]) == (None, None)
    sector = next(c for c in d.components if c[1] == "sector")
    assert sector[7] == "1"  # contested

    assert ("[0x20]", "manager", "[0x99]") in d.posts
    assert ("[0x30]", "aipilot", "[0x99]") in d.posts
    assert ("[0x20]", "argon", 50.0) in d.workforce
    # module count keeps max construction index; macro kept for market stats
    assert max(m[1] for m in d.modules if m[0] == "[0x20]") == 3
    assert ("[0x20]", 1, "mod_a_macro", "[0x50]") in d.modules

    # build method (v21). <build> is overloaded three ways and only one of
    # them is the per-station override: the fixture carries all three — the
    # station's construction-progress block (no attributes), a build TASK
    # under a buildprocessor (method= AND order=), and the override itself.
    # station self-supply (v22): build targets + set-aside inputs, stations
    # only — the identical block on the docked ship is its ammo reserve
    assert d.station_supplies == [
        ("[0x20]", "ware", "metallicmicrolattice", 1200.0),
        ("[0x20]", "order", "ship_gen_xs_repairdrone_01_a", 10.0),
    ]
    # configured prices: whole credits, 0 = that side unset. <reference>
    # and <override> are the same shape, told apart by kind
    assert d.price_settings == [
        ("[0x20]", "reference", "energycells", 12.0, 0.0),
        ("[0x20]", "override", "energycells", 21.0, 0.0),
        ("[0x20]", "override", "claytronics", 0.0, 1734.0),
    ]
    # manual per-ware limits; a ware with no amount= means 1, the floor the
    # station UI clamps all three limit kinds to (it cannot store 0)
    assert d.ware_limits == [
        ("[0x20]", "max", "energycells", 739800.0),
        ("[0x20]", "max", "weaponcomponents", 1.0),
        ("[0x20]", "buy", "energycells", 739800.0),
        ("[0x20]", "sell", "siliconcarbide", 5184.0),
    ]

    assert d.faction_build_rules == [("player", "terran")]
    assert d.station_build_methods == [("[0x20]", "closedloop")]

    assert len(d.npcs) == 1
    npc = d.npcs[0]
    assert npc[1] == "Jane Doe" and npc[4]["piloting"] == 9.0

    assert d.commander_links == [("[0x30]", "[0xC1]")]
    assert d.subordinate_conns == [("[0x20]", "[0xC1]")]

    # per-area rows carry starttime (respawn-eligibility clock); game_time is
    # 5000.5, so the starttime=4000 area is eligible (empty-but-full) and the
    # starttime=9000 one is still respawning
    assert d.resources == [
        ("cluster_01_sector001_macro", "ore", 1000.0, "high", "slow", 0.0),
        ("cluster_01_sector001_macro", "silicon", 200.0, "low", "", 0.0),
        ("cluster_01_sector001_macro", "ore", 0.0, "high", "slow", 4000.0),
        ("cluster_01_sector001_macro", "ore", 0.0, "high", "slow", 9000.0),
    ]

    assert d.people == {("[0x30]", "service"): 2, ("[0x30]", "passenger"): 1}

    # player trade-info subscriptions: absolute expiry, None = permanent
    assert d.player_subscriptions == [
        ("[0x20]", 9000.5), ("[0x30]", 1000.0), ("[0x40]", None)]
    # station build price factor from <trade><prices buildpricefactor=>
    assert d.build_price_factors == [("[0x20]", 1.07)]
    # player module scan levels from <memory><scan> (v20)
    assert d.player_scans == [("[0x20]", 2)]
    # trade-station ware whitelists, one row per ware (v20)
    assert d.trade_settings == [
        ("[0x20]", "buy", "spaceweed"), ("[0x20]", "buy", "majadust"),
        ("[0x20]", "lockavgprice", "spaceweed")]
    # committed in-flight trades (v26): the save keeps each in TWO places
    # (the ship's order and the station's reservation) and the parser takes
    # both, leaving the merge to the store. <active> contributes only ids.
    assert d.trade_active_ids == ["[0xT3]"]
    by_id = {}
    for row in d.trade_pending:
        by_id.setdefault(row[1], []).append(row)
    assert sorted(by_id) == ["[0xT3]", "[0xT4]"]
    assert {r[0] for r in by_id["[0xT3]"]} == {"order", "reservation"}
    # order rows are hosted by the ship, reservations by the station
    assert {r[2] for r in by_id["[0xT3]"]} == {"[0x30]", "[0x20]"}
    # buyer= present and seller= absent -> seller is `partner` (the rule
    # the pricing model's pending term depends on)
    ore = by_id["[0xT4]"][0]
    assert (ore[4], ore[5], ore[6]) == ("[0x20]", "[0x88]", "[0x88]")

    assert ("[0x20]", "buy", "energycells", 500.0, 1.0, "", 500.0) \
        in d.trade_offers
    # supplies-flagged self-supply buy: raw flags and desired captured
    assert ("[0x20]", "buy", "dronecomponents", 0.0, 2.0,
            "supplies|invertfactionrestriction", 50.0) in d.trade_offers
    assert ("[0x30]", "Wait", True, "started") in d.orders
    assert ("[0x20]", "claytronics", 1000.0, "insufficient") \
        in d.build_resources
    assert ("cluster_01_sector001_macro", "rawscrap", 1000.0) \
        in d.floating_wares

    assert d.has_highways is True

    # equipped engines attributed to the nearest ship ancestor
    assert d.ship_engines == [
        ("[0x30]", "engine_arg_s_travel_01_mk3_macro"),
        ("[0x30]", "engine_arg_s_travel_01_mk3_macro"),
    ]

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

    # the economylog collections are split by ledger block, not by the
    # log's type attr: the cargo-block produce row is not collected
    assert [t["type"] for t in d.trades] == ["trade", "transfer"]
    assert d.trades[0]["ware"] == "energycells"
    assert d.stock_logs == [{"time": "11.0", "type": "trade", "ware": "ice",
                             "owner": "[0x20]", "v": "50"}]
    assert d.money_logs == [{"time": "10.7", "type": "trade",
                             "owner": "[0x20]", "partner": "[0x77]",
                             "tradeentry": "1", "v": "16000000"}]
    assert d.removed_objects[0]["name"] == "TEL Trader"
    assert d.log_entries[0]["title"] == "Test entry"
