"""Cycle/DPS math for the weapon-mod comparison (gamedata dashboard).

The reference numbers were validated in-game: TER S Electromagnetic Gun Mk1
fires 28.57 shots per 10000-heat bar and overheats from cold in 20.41 s;
with an optimal-roll Slasher (mod_weapon_damage_03_mk1) it fires at 2.8
shots/s and overheats in ~10.2 s. ARG S Ion Blaster clip reload is fixed
(cooling mods do nothing, reload mods only speed up the burst).
"""

import pytest

from x4analyzer.gamedata.weaponsim import (guaranteed_stats, mod_multipliers,
                                           optimal_mult, simulate)

# TER S Electromagnetic Gun Mk1 (timelines override of the terran macro)
EM_GUN = {
    "overheat": 10000.0, "overheatcooldelay": 1.0, "coolrate": 2000.0,
    "reenable": 8000.0, "heat": 350.0, "reload_rate": 1.4,
    "amount": 1.0, "barrelamount": 1.0,
    "dmg": 110.0, "dmg_shield": 0.0, "dmg_hull": 70.0,
}

# ARG S Ion Blaster Mk2: clip weapon, no per-shot heat
ION_BLASTER = {
    "overheat": 10000.0, "coolrate": 2000.0, "reenable": 9500.0,
    "heat": 0.0, "reload_rate": 1.0, "ammo_clip": 5.0, "ammo_reload": 5.0,
    "amount": 1.0, "barrelamount": 1.0,
    "dmg": 84.0, "dmg_shield": 336.0, "dmg_hull": 0.0,
}

SLASHER = {
    "ware": "mod_weapon_damage_03_mk1", "stat": "damage",
    "quality": 1, "min": 1.338, "max": 1.503, "forced": True,
    "bonuses": [
        {"stat": "cooling", "min": 0.681, "max": 0.74, "weight": 1.0},
        {"stat": "reload", "min": 0.682, "max": 2.0, "weight": 1.0},
    ],
}


def test_em_gun_bare_matches_ingame():
    s = simulate(EM_GUN)
    assert s["shots_cycle"] == pytest.approx(28.57, abs=0.01)
    assert s["t_overheat"] == pytest.approx(20.41, abs=0.01)
    assert s["rate"] == pytest.approx(1.4)
    assert s["dmg_s"] == pytest.approx(110.0)   # value + shield bonus
    assert s["dmg_h"] == pytest.approx(180.0)   # value + hull bonus
    assert s["t_cooldown"] == pytest.approx(1.0 + 10000 / 2000)
    # steady state: fire 8000->10000, cool back after the offline delay
    assert s["ss_fire"] == pytest.approx(2000 / (350 * 1.4))
    assert s["ss_cool"] == pytest.approx(1.0 + 2000 / 2000)


def test_em_gun_slasher_optimal_matches_ingame():
    mults = mod_multipliers(SLASHER, EM_GUN)
    # reload rate is multiplied literally, so the optimal roll is the MAX;
    # the forced cooling malus applies at its least-bad end
    assert mults == {"damage": 1.503, "cooling": 0.74, "reload": 2.0}
    s = simulate(EM_GUN, mults)
    assert s["rate"] == pytest.approx(2.8)
    assert s["t_overheat"] == pytest.approx(10.2, abs=0.01)
    assert s["dmg_s"] == pytest.approx(110 * 1.503)
    assert s["coolrate"] == pytest.approx(2000 * 0.74)
    # heat per shot is unchanged: same shots per bar, reached twice as fast
    assert s["shots_cycle"] == pytest.approx(28.57, abs=0.01)


def test_reload_mod_direction_flips_with_storage():
    # <reload rate>: bigger multiplier = faster -> optimal is max
    assert optimal_mult("reload", 0.682, 2.0, "rate") == 2.0
    # <reload time>: bigger multiplier = slower -> optimal is min
    assert optimal_mult("reload", 0.682, 2.0, "time") == 0.682
    # chargetime multiplies a duration: min is always best
    assert optimal_mult("chargetime", 0.8, 0.95, "rate") == 0.8
    # malus ranges pick the least-bad end
    assert optimal_mult("cooling", 0.681, 0.74, "rate") == 0.74

    w = {"reload_time": 3.8, "dmg": 100.0}
    s = simulate(w, {"reload": 0.682})
    assert s["rate"] == pytest.approx(1 / (3.8 * 0.682))


def test_ion_blaster_clip_cycle():
    s = simulate(ION_BLASTER)
    # no per-shot heat -> the heat block never engages
    assert s["coolrate"] is None and s["t_overheat"] is None
    assert s["t_cycle"] == pytest.approx(10.0)   # 5 shots @1/s + 5 s reload
    assert s["shots_cycle"] == pytest.approx(5.0)
    assert s["dmg_s"] == pytest.approx(420.0)    # 84 + 336
    assert s["cyc_dps_s"] == pytest.approx(210.0)
    assert s["duty"] == pytest.approx(0.5)


def test_cooling_mod_has_no_effect_on_clip_weapon():
    assert simulate(ION_BLASTER, {"cooling": 1.216}) == simulate(ION_BLASTER)


def test_reload_mod_never_touches_clip_reload():
    s = simulate(ION_BLASTER, {"reload": 2.0})
    # burst shrinks from 5 s to 2.5 s; the 5 s clip reload is fixed
    assert s["rate"] == pytest.approx(2.0)
    assert s["t_cycle"] == pytest.approx(7.5)
    assert s["ss_cool"] == pytest.approx(5.0)
    assert s["cyc_dps_s"] == pytest.approx(5 * 420 / 7.5)


def test_continuous_weapon_without_heat_or_clip():
    w = {"reload_rate": 2.0, "dmg": 50.0, "dmg_hull": 10.0}
    s = simulate(w)
    assert s["t_cycle"] is None and s["shots_cycle"] is None
    assert s["duty"] == pytest.approx(1.0)
    assert s["ss_dps_s"] == pytest.approx(100.0)
    assert s["ss_dps_h"] == pytest.approx(120.0)


def test_charge_weapon_interval_includes_chargetime():
    w = {"reload_time": 3.8, "chargetime": 0.5, "dmg": 100.0}
    assert simulate(w)["rate"] == pytest.approx(1 / 4.3)
    s = simulate(w, {"chargetime": 0.8})
    assert s["rate"] == pytest.approx(1 / (3.8 + 0.4))


def test_blast_mortar_area_damage():
    # S Blast Mortar Mk1: ALL damage lives in <areadamage value="376">,
    # the <damage> element is empty; clip 8 @ 1/0.9s + 12 s reload, 490
    # heat per volley against a slow 580/s coolrate
    w = {"overheat": 10000.0, "overheatcooldelay": 2.0, "coolrate": 580.0,
         "reenable": 7000.0, "heat": 490.0, "reload_time": 0.9,
         "ammo_clip": 8.0, "ammo_reload": 12.0,
         "amount": 1.0, "barrelamount": 1.0,
         "dmg": 0.0, "area_dmg": 376.0}
    s = simulate(w)
    assert s["dmg_s"] == pytest.approx(376.0)
    assert s["dmg_h"] == pytest.approx(376.0)
    eff = 8 / (8 * 0.9 + 12)                   # sustained volleys/s
    assert s["t_overheat"] == pytest.approx(10000 / (490 * eff))
    assert s["shots_cycle"] == pytest.approx(10000 / 490)
    # direct-hit and explosion damage stack when both exist
    both = simulate(dict(w, dmg=100.0, area_dmg_shield=50.0))
    assert both["dmg_s"] == pytest.approx(526.0)
    assert both["dmg_h"] == pytest.approx(476.0)


def test_boson_lance_single_shot_clip():
    # SPL S Boson Lance Mk1: <ammunition value="1" reload="12.2"/> and NO
    # <reload> element — the clip reload is the entire firing cycle
    w = {"overheat": 10000.0, "coolrate": 2000.0, "reenable": 1000.0,
         "heat": 0.0, "ammo_clip": 1.0, "ammo_reload": 12.2,
         "amount": 1.0, "barrelamount": 1.0, "dmg": 750.0}
    s = simulate(w)
    assert s["rate"] == pytest.approx(1 / 12.2)   # sustained rate
    assert s["t_cycle"] == pytest.approx(12.2)
    assert s["shots_cycle"] == pytest.approx(1.0)
    assert s["cyc_dps_s"] == pytest.approx(750 / 12.2)
    assert s["ss_cool"] == pytest.approx(12.2)
    # nothing for a reload mod to multiply -> no effect
    assert simulate(w, {"reload": 2.0}) == s


def test_multi_projectile_volley():
    # Split shotgun pattern: 4 projectiles, one heat charge per volley
    w = {"overheat": 10000.0, "coolrate": 2000.0, "reenable": 8000.0,
         "heat": 124.0, "reload_rate": 1.0, "amount": 4.0,
         "barrelamount": 1.0, "dmg": 25.0}
    s = simulate(w)
    assert s["dmg_s"] == pytest.approx(100.0)
    assert s["shots_cycle"] == pytest.approx(10000 / 124)


def test_guaranteed_stats():
    assert guaranteed_stats(SLASHER) == ["damage", "cooling", "reload"]
    pool_mod = dict(SLASHER, forced=False)
    assert guaranteed_stats(pool_mod) == ["damage"]
