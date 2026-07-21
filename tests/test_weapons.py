"""Weapon / bullet / equipment-mod extraction for the gamedata dashboard.

Uses synthetic .cat/.dat archives (see test_catalog.py) carrying real v9.0
XML: the ARG S Ion Blaster Mk2 in the base game (uppercase WeaponSystems/
weaponFx directories) and the TER S Electromagnetic Gun Mk1 in a lowercase
DLC, re-issued by a second DLC to prove the load-order override.
"""

from pathlib import Path

import pytest

from x4analyzer.config import Config
from x4analyzer.gamedata.catalog import GameFiles
from x4analyzer.gamedata.extract import load_textdb
from x4analyzer.gamedata.weapons import extract_weapon_mods, extract_weapons
from x4analyzer.viz.weaponmods import build_gamedata_dashboard


def make_cat(directory: Path, name: str, files: dict[str, bytes]) -> None:
    lines = []
    blob = b""
    for path, content in files.items():
        lines.append(f"{path} {len(content)} 1700000000 " + "0" * 32)
        blob += content
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.cat").write_text("\n".join(lines) + "\n")
    (directory / f"{name}.dat").write_bytes(blob)


ION_WEAPON = b"""<macros>
  <macro name="weapon_arg_s_ion_01_mk2_macro" class="weapon">
    <properties>
      <identification name="{20105,1194}" makerrace="argon" mk="2" />
      <bullet class="bullet_arg_s_ion_01_mk2_macro" />
      <heat overheat="10000" cooldelay="1.13" coolrate="2000" reenable="9500" />
      <rotationspeed max="150" />
    </properties>
  </macro>
</macros>"""

ION_BULLET = b"""<macros>
  <macro name="bullet_arg_s_ion_01_mk2_macro" class="bullet">
    <properties>
      <ammunition value="5" reload="5" />
      <bullet speed="2800" lifetime="1.45" amount="1" barrelamount="1" />
      <reload rate="1" />
      <damage value="84" shield="336" repair="0" />
    </properties>
  </macro>
</macros>"""

EM_WEAPON_TMPL = """<macros>
  <macro name="weapon_ter_s_laser_02_mk1_macro" class="weapon">
    <properties>
      <identification name="{{20105,1564}}" makerrace="terran" mk="1" />
      <bullet class="bullet_ter_s_laser_02_mk1_macro" />
      <heat overheat="10000" cooldelay="1" overheatcooldelay="{ohcd}"
            coolrate="2000" reenable="8000" />
      <rotationspeed max="100" />
    </properties>
  </macro>
</macros>"""

EM_BULLET = b"""<macros>
  <macro name="bullet_ter_s_laser_02_mk1_macro" class="bullet">
    <properties>
      <bullet speed="2800" lifetime="1" barrelamount="1" />
      <heat value="350" />
      <reload rate="1.4" />
      <damage value="110" hull="70" repair="0" />
    </properties>
  </macro>
</macros>"""

MORTAR_WEAPON = b"""<macros>
  <macro name="weapon_gen_s_cannon_01_mk1_macro" class="weapon">
    <properties>
      <identification name="S Blast Mortar Mk1" mk="1" />
      <bullet class="bullet_gen_s_cannon_01_mk1_macro" />
      <heat overheat="10000" cooldelay="4" overheatcooldelay="2"
            coolrate="580" reenable="7000" />
    </properties>
  </macro>
</macros>"""

# damage lives ONLY in <areadamage>; the <damage> element is absent
MORTAR_BULLET = b"""<macros>
  <macro name="bullet_gen_s_cannon_01_mk1_macro" class="bullet">
    <properties>
      <ammunition value="8" reload="12" />
      <bullet speed="3000" lifetime="1.25" amount="1" barrelamount="1" />
      <heat value="490" />
      <reload time="0.9" />
      <areadamage value="376" />
    </properties>
  </macro>
</macros>"""

# Paranid Mass Driver: the bullet stores per-shot heat as <heat initial=>
# with NO value attribute -- the parser must fall back to `initial` or the
# weapon reads as heatless (bug 2026-07)
RAILGUN_WEAPON = b"""<macros>
  <macro name="weapon_par_s_railgun_01_mk1_macro" class="weapon">
    <properties>
      <identification name="PAR S Mass Driver Mk1" makerrace="paranid" mk="1" />
      <bullet class="bullet_par_s_railgun_01_mk1_macro" />
      <heat overheat="10000" cooldelay="1.5" overheatcooldelay="4"
            coolrate="900" reenable="1000" />
    </properties>
  </macro>
</macros>"""

RAILGUN_BULLET = b"""<macros>
  <macro name="bullet_par_s_railgun_01_mk1_macro" class="bullet">
    <properties>
      <bullet speed="10000" lifetime="1.4" amount="1" barrelamount="1"
              chargetime="0.5" />
      <heat initial="8000" />
      <reload time="3.8" />
      <damage value="1122" repair="0" />
    </properties>
  </macro>
</macros>"""

# not a weapon: same file naming, must be skipped by the class filter
LAUNCHER = b"""<macros>
  <macro name="weapon_arg_s_torpedolauncher_01_mk1_macro" class="missilelauncher">
    <properties>
      <identification name="Torpedo Launcher" mk="1" />
      <bullet class="missile_arg_s_torpedo_01_mk1_macro" />
    </properties>
  </macro>
</macros>"""

EQUIPMENTMODS = b"""<equipmentmods>
  <weapon>
    <damage ware="mod_weapon_damage_01_mk1" quality="1" min="1.05" max="1.2"/>
    <cooling ware="mod_weapon_cooling_01_mk1" quality="1" min="1.048" max="1.216"/>
    <reload ware="mod_weapon_reload_01_mk1" quality="1" min="0.682" max="2"/>
    <sticktime ware="mod_weapon_sticktime_01_mk1" quality="1" min="1.05" max="1.2"/>
    <damage ware="mod_weapon_damage_03_mk1" quality="1" min="1.338" max="1.503">
      <bonus chance="1.0" max="2">
        <cooling min="0.681" max="0.74"/>
        <reload min="0.682" max="2"/>
      </bonus>
    </damage>
    <damage ware="mod_weapon_damage_01_mk2" quality="2" min="1.062" max="1.244">
      <bonus chance="1.0" max="2">
        <reload min="0.682" max="2" weight="1"/>
        <chargetime min="0.8" max="0.9" weight="3"/>
        <mining min="1.01" max="6.22" weight="3"/>
        <rotationspeed min="1.1" max="1.2" weight="3"/>
      </bonus>
    </damage>
  </weapon>
  <engine>
    <forwardthrust ware="mod_engine_forwardthrust_01_mk1" quality="1" min="1.025" max="1.1"/>
  </engine>
</equipmentmods>"""

WARES = b"""<wares>
  <ware id="mod_weapon_damage_01_mk1" name="Piercer (Damage Mod)" shortname="Piercer"/>
  <ware id="mod_weapon_cooling_01_mk1" name="Tramontane (Cooling Mod)" shortname="Tramontane"/>
  <ware id="mod_weapon_reload_01_mk1" name="Cowboy (Reload Mod)" shortname="Cowboy"/>
  <ware id="mod_weapon_sticktime_01_mk1" name="Gum (Sticky Mod)" shortname="Gum"/>
  <ware id="mod_weapon_damage_03_mk1" name="Slasher (Damage Mod)" shortname="Slasher"/>
  <ware id="mod_weapon_damage_01_mk2" name="Assassin (Damage Mod - Enhanced Quality)" shortname=""/>
  <ware id="ore" name="Ore"/>
</wares>"""

TFILE = b"""<language id="44">
  <page id="20105">
    <t id="1194">ARG S Ion Blaster Mk2</t>
    <t id="1564">TER S Electromagnetic Gun Mk1</t>
  </page>
</language>"""


@pytest.fixture
def game_dir(tmp_path: Path) -> Path:
    make_cat(tmp_path, "01", {
        "assets/props/WeaponSystems/energy/macros/"
        "weapon_arg_s_ion_01_mk2_macro.xml": ION_WEAPON,
        "assets/props/WeaponSystems/torpedo/macros/"
        "weapon_arg_s_torpedolauncher_01_mk1_macro.xml": LAUNCHER,
        "assets/props/WeaponSystems/heavy/macros/"
        "weapon_gen_s_cannon_01_mk1_macro.xml": MORTAR_WEAPON,
        "assets/props/WeaponSystems/heavy/macros/"
        "weapon_par_s_railgun_01_mk1_macro.xml": RAILGUN_WEAPON,
        "assets/fx/weaponFx/macros/"
        "bullet_arg_s_ion_01_mk2_macro.xml": ION_BULLET,
        "assets/fx/weaponFx/macros/"
        "bullet_gen_s_cannon_01_mk1_macro.xml": MORTAR_BULLET,
        "assets/fx/weaponFx/macros/"
        "bullet_par_s_railgun_01_mk1_macro.xml": RAILGUN_BULLET,
        "libraries/equipmentmods.xml": EQUIPMENTMODS,
        "libraries/wares.xml": WARES,
        "t/0001-l044.xml": TFILE,
    })
    # DLC uses lowercase weaponsystems/weaponfx paths
    make_cat(tmp_path / "extensions" / "ego_dlc_terran", "ext_01", {
        "assets/props/weaponsystems/standard/macros/"
        "weapon_ter_s_laser_02_mk1_macro.xml":
            EM_WEAPON_TMPL.format(ohcd=2).encode(),
        "assets/fx/weaponfx/macros/"
        "bullet_ter_s_laser_02_mk1_macro.xml": EM_BULLET,
    })
    # a later DLC re-issues the same macro (timelines does this for real):
    # its overheatcooldelay=1 must win over the terran DLC's 2
    make_cat(tmp_path / "extensions" / "ego_dlc_timelines", "ext_01", {
        "assets/props/weaponsystems/standard/macros/"
        "weapon_ter_s_laser_02_mk1_macro.xml":
            EM_WEAPON_TMPL.format(ohcd=1).encode(),
    })
    return tmp_path


def test_extract_weapons(game_dir: Path):
    gf = GameFiles(game_dir)
    weapons = {w["macro"]: w for w in extract_weapons(gf, load_textdb(gf))}
    assert set(weapons) == {"weapon_arg_s_ion_01_mk2_macro",
                            "weapon_ter_s_laser_02_mk1_macro",
                            "weapon_gen_s_cannon_01_mk1_macro",
                            "weapon_par_s_railgun_01_mk1_macro"}

    # mass driver: heat comes from the bullet's <heat initial=> (no value),
    # so the weapon overheats rather than reading as heatless
    rg = weapons["weapon_par_s_railgun_01_mk1_macro"]
    assert rg["heat"] == 8000.0 and rg["overheat"] == 10000.0
    assert rg["chargetime"] == 0.5 and rg["reload_time"] == 3.8

    em = weapons["weapon_ter_s_laser_02_mk1_macro"]
    assert em["name"] == "TER S Electromagnetic Gun Mk1"
    assert em["size"] == "S" and em["wclass"] == "weapon"
    assert em["heat"] == 350.0 and em["reload_rate"] == 1.4
    assert em["overheat"] == 10000.0 and em["reenable"] == 8000.0
    assert em["dmg"] == 110.0 and em["dmg_hull"] == 70.0
    assert em["overheatcooldelay"] == 1.0   # timelines override wins
    assert em["source"] == "ego_dlc_timelines"

    mortar = weapons["weapon_gen_s_cannon_01_mk1_macro"]
    assert mortar["area_dmg"] == 376.0 and mortar["dmg"] == 0.0
    assert mortar["has_damage"]           # areadamage alone counts
    assert mortar["heat"] == 490.0 and mortar["ammo_clip"] == 8.0

    ion = weapons["weapon_arg_s_ion_01_mk2_macro"]
    assert ion["name"] == "ARG S Ion Blaster Mk2"
    assert ion["ammo_clip"] == 5.0 and ion["ammo_reload"] == 5.0
    assert ion["heat"] == 0.0
    assert ion["dmg"] == 84.0 and ion["dmg_shield"] == 336.0
    assert ion["mk"] == "2"


def test_extract_weapon_mods(game_dir: Path):
    gf = GameFiles(game_dir)
    mods = {m["ware"]: m for m in extract_weapon_mods(gf, load_textdb(gf))}
    # engine mods excluded, weapon mods (relevant or not) all present
    assert "mod_engine_forwardthrust_01_mk1" not in mods
    assert set(mods) == {
        "mod_weapon_damage_01_mk1", "mod_weapon_cooling_01_mk1",
        "mod_weapon_reload_01_mk1", "mod_weapon_sticktime_01_mk1",
        "mod_weapon_damage_03_mk1", "mod_weapon_damage_01_mk2",
    }

    slasher = mods["mod_weapon_damage_03_mk1"]
    assert slasher["name"] == "Slasher"
    assert slasher["stat"] == "damage" and slasher["quality"] == 1
    assert slasher["min"] == 1.338 and slasher["max"] == 1.503
    # two bonus children within max=2 at chance 1.0 -> both forced
    assert slasher["forced"]
    assert [(b["stat"], b["min"], b["max"]) for b in slasher["bonuses"]] \
        == [("cooling", 0.681, 0.74), ("reload", 0.682, 2.0)]

    assassin = mods["mod_weapon_damage_01_mk2"]
    # four weighted children for max=2 -> optional pool, nothing forced
    assert not assassin["forced"]
    assert len(assassin["bonuses"]) == 4
    # empty shortname falls back to the long name's leading words
    assert assassin["name"] == "Assassin"

    plain = mods["mod_weapon_damage_01_mk1"]
    assert plain["name"] == "Piercer" and not plain["bonuses"]


def test_build_gamedata_dashboard(game_dir: Path, tmp_path: Path):
    cfg = Config()
    cfg.game_dir = game_dir
    cfg.output_dir = tmp_path / "output"
    assert build_gamedata_dashboard(cfg) == 0
    html = (cfg.output_dir / "gamedata_dashboard.html").read_text()
    assert "TER S Electromagnetic Gun Mk1" in html
    assert "Slasher" in html
    # sticktime mod has no guaranteed effect on the firing cycle -> no column
    assert "mod_weapon_sticktime_01_mk1" not in html
    # self-contained: no external scripts or stylesheets
    assert "src=" not in html.split("<script>")[0]
