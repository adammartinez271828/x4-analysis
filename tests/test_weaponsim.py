"""Cycle/DPS math for the weapon-mod comparison (gamedata dashboard).

The reference numbers were validated in-game: TER S Electromagnetic Gun Mk1
fires ~29 shots per 10000-heat bar and overheats from cold in ~20 s (its
0.71 s interval never exceeds its 1.0 s cooldelay, so it never cools while
firing); with an optimal-roll vanilla Slasher it fires at 2.8 shots/s and
overheats in ~10 s. S Plasma Cannon Mk1 (2026-07) validated the slow-weapon
physics: reload mods DIVIDE its stored 2.6 s reload time, and it cools
between shots once cooldelay elapses (five bare shots sit just under the
10000 heat bar, the sixth overheats; +20% fire rate moves that to the
fifth). ARG S Ion Blaster clip reload is fixed (cooling mods do nothing,
reload mods only speed up the burst). The heat cycle is simulated discretely
(see weaponsim._bullet_heat_cycle) so slow high-per-shot weapons like the
mass driver come out right (2 shots, not a continuous-rate ~1.7).
"""

import pytest

from x4analyzer.gamedata.weaponsim import (guaranteed_stats, mod_multipliers,
                                           optimal_mult, simulate)

# TER S Electromagnetic Gun Mk1 (timelines override of the terran macro)
EM_GUN = {
    "overheat": 10000.0, "overheatcooldelay": 1.0, "coolrate": 2000.0,
    "reenable": 8000.0, "heat": 350.0, "cooldelay": 1.0, "reload_rate": 1.4,
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
    # discrete cold cycle: the 29th shot (350*29 = 10150) tips it over, 28 gaps
    assert s["shots_cycle"] == 29
    assert s["t_overheat"] == pytest.approx(28 / 1.4)   # ~20.0 s
    assert s["rate"] == pytest.approx(1.4)
    assert s["dmg_s"] == pytest.approx(110.0)   # value + shield bonus
    assert s["dmg_h"] == pytest.approx(180.0)   # value + hull bonus
    assert s["t_cooldown"] == pytest.approx(1.0 + 10000 / 2000)
    # steady state: from reenable 8000 the 6th shot (10100) overheats -> 5 gaps
    assert s["ss_fire"] == pytest.approx(5 / 1.4)
    assert s["ss_cool"] == pytest.approx(1.0 + 2000 / 2000)


def test_em_gun_slasher_optimal_matches_ingame():
    mults = mod_multipliers(SLASHER, EM_GUN)
    # reload mods are rate-semantic, so the optimal roll is always the MAX;
    # the forced cooling malus applies at its least-bad end
    assert mults == {"damage": 1.503, "cooling": 0.74, "reload": 2.0}
    s = simulate(EM_GUN, mults)
    assert s["rate"] == pytest.approx(2.8)
    assert s["t_overheat"] == pytest.approx(28 / 2.8)   # ~10.0 s (twice as fast)
    assert s["dmg_s"] == pytest.approx(110 * 1.503)
    assert s["coolrate"] == pytest.approx(2000 * 0.74)
    # heat per shot is unchanged: same 29 shots per bar, reached twice as fast
    assert s["shots_cycle"] == 29


def test_reload_mod_is_rate_semantic_on_both_storage_forms():
    # verified in-game 2026-07 (S Plasma Cannon Mk1): a reload multiplier
    # means fire rate on EVERY weapon - stored rates are multiplied,
    # stored times are divided, so the optimal roll is always the max
    assert optimal_mult("reload", 0.682, 2.0, "rate") == 2.0
    assert optimal_mult("reload", 0.682, 2.0, "time") == 2.0
    # chargetime multiplies a duration: min is always best
    assert optimal_mult("chargetime", 0.8, 0.95, "rate") == 0.8
    # malus ranges pick the least-bad end
    assert optimal_mult("cooling", 0.681, 0.74, "rate") == 0.74

    w = {"reload_time": 3.8, "dmg": 100.0}
    assert simulate(w, {"reload": 1.2})["rate"] == pytest.approx(1.2 / 3.8)
    assert simulate(w, {"reload": 0.682})["rate"] == \
        pytest.approx(0.682 / 3.8)


def test_ion_blaster_clip_cycle():
    s = simulate(ION_BLASTER)
    # no per-shot heat -> the heat block never engages
    assert s["coolrate"] is None and s["t_overheat"] is None
    # cycle = the burst span (4 gaps between 5 shots @1/s) + the 5 s clip
    # reload; the reported rate is sustained (5/9), not the 1/s intra-clip burst
    assert s["t_cycle"] == pytest.approx(9.0)    # 4*1 + 5
    assert s["rate"] == pytest.approx(5.0 / 9.0)
    assert s["shots_cycle"] == pytest.approx(5.0)
    assert s["dmg_s"] == pytest.approx(420.0)    # 84 + 336
    assert s["cyc_dps_s"] == pytest.approx(5 * 420 / 9)
    assert s["duty"] == pytest.approx(4.0 / 9.0)


def test_mass_driver_initial_heat_two_shots():
    # PAR Mass Driver: <heat initial=8000> only (no value), a slow charge
    # weapon. Each discrete shot deposits the 8000 spike, so it fires exactly
    # two shots before overheating (validated in-game 2026-07) -- the old
    # continuous model gave ~1.7 shots / ~7 s.
    w = {"heat": 0.0, "heat_initial": 8000.0, "overheat": 10000.0,
         "cooldelay": 2.0, "overheatcooldelay": 4.0, "coolrate": 870.0,
         "reenable": 1000.0, "reload_time": 3.8, "chargetime": 0.5,
         "amount": 1.0, "barrelamount": 1.0, "dmg": 1122.0}
    s = simulate(w)
    assert s["shots_cycle"] == 2                    # shot 1 -> 8000, shot 2 over
    assert s["t_overheat"] == pytest.approx(4.3)    # 2nd shot at one interval
    assert s["t_cooldown"] is not None              # real cooldown, not heatless


# M Scalar Aperture beam: instant spike 2000 + 1333/s value, live 4 s of a 5 s
# cycle. Projectile speed = c marks it a beam.
SCALAR_APERTURE = {
    "speed": 299792500.0, "lifetime": 4.0, "reload_time": 5.0,
    "heat": 1333.0, "heat_initial": 2000.0, "overheat": 10000.0,
    "reenable": 5000.0, "coolrate": 850.0, "cooldelay": 1.0,
    "overheatcooldelay": 2.0, "amount": 1.0, "barrelamount": 1.0,
    "dmg": 130.0, "dmg_hull": 390.0,
}


def test_scalar_aperture_beam_initial_spike():
    # validated in-game 2026-07: hold the trigger and it fires one full 4 s
    # beam to ~73% (2000 spike + 1333*4 = 7332), then a shortened ~0.5 s beam
    # before overheating -> two activations
    s = simulate(SCALAR_APERTURE)
    assert s["shots_cycle"] == 2                     # two beam activations
    assert s["t_overheat"] == pytest.approx(4.5, abs=0.02)
    # steady re-activation from reenable 5000: +2000 spike then climb to 10000
    assert s["ss_fire"] == pytest.approx((10000 - 5000 - 2000) / 1333, abs=0.01)


def test_tau_accelerator_reports_sustained_not_burst_rate():
    # SPL S Tau Accelerator Mk2: clip 6 @ 3/s burst, 4 s reload. Its per-volley
    # heat (124) is shed by the clip pause, so it never overheats and the clip
    # cycle governs. The reported rate must be the SUSTAINED figure the
    # encyclopedia shows (~1.06/s), NOT the 3/s intra-clip burst (bug 2026-07).
    w = {"reload_rate": 3.0, "ammo_clip": 6.0, "ammo_reload": 4.0,
         "amount": 4.0, "barrelamount": 1.0, "dmg": 80.0,
         "heat": 124.0, "overheat": 10000.0, "cooldelay": 3.5,
         "overheatcooldelay": 2.0, "coolrate": 1800.0, "reenable": 8000.0}
    s = simulate(w)
    assert s["t_overheat"] is None                       # never overheats
    assert s["rate"] == pytest.approx(6 / (5 / 3 + 4))   # ~1.059, not 3.0
    assert s["t_cycle"] == pytest.approx(5 / 3 + 4)      # (6-1) gaps + reload


def test_cooling_mod_has_no_effect_on_clip_weapon():
    assert simulate(ION_BLASTER, {"cooling": 1.216}) == simulate(ION_BLASTER)


def test_reload_mod_never_touches_clip_reload():
    s = simulate(ION_BLASTER, {"reload": 2.0})
    # a reload mod halves the intra-burst gap (burst span 4 s -> 2 s), but the
    # 5 s clip reload is fixed, so the sustained rate rises from 5/9 to 5/7
    assert s["rate"] == pytest.approx(5.0 / 7.0)
    assert s["t_cycle"] == pytest.approx(7.0)
    assert s["ss_cool"] == pytest.approx(5.0)
    assert s["cyc_dps_s"] == pytest.approx(5 * 420 / 7.0)


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
    # heat per volley against a slow 580/s coolrate. With between-shot
    # cooling the 12 s clip pause sheds 580*(12-2) = 5800 heat vs 3920
    # gained per clip, so the mortar never overheats - the clip cycle IS
    # the firing cycle.
    w = {"overheat": 10000.0, "overheatcooldelay": 2.0, "coolrate": 580.0,
         "reenable": 7000.0, "heat": 490.0, "cooldelay": 2.0,
         "reload_time": 0.9, "ammo_clip": 8.0, "ammo_reload": 12.0,
         "amount": 1.0, "barrelamount": 1.0,
         "dmg": 0.0, "area_dmg": 376.0}
    s = simulate(w)
    assert s["dmg_s"] == pytest.approx(376.0)
    assert s["dmg_h"] == pytest.approx(376.0)
    assert s["t_overheat"] is None
    assert s["t_cycle"] == pytest.approx(7 * 0.9 + 12)   # (8-1) gaps + reload
    assert s["shots_cycle"] == pytest.approx(8.0)
    assert s["cyc_dps_s"] == pytest.approx(8 * 376 / 18.3)
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
    # (cooldelay = interval, so no between-shot cooling engages)
    w = {"overheat": 10000.0, "coolrate": 2000.0, "reenable": 8000.0,
         "heat": 124.0, "cooldelay": 1.0, "reload_rate": 1.0, "amount": 4.0,
         "barrelamount": 1.0, "dmg": 25.0}
    s = simulate(w)
    assert s["dmg_s"] == pytest.approx(100.0)
    assert s["shots_cycle"] == 81           # 124*81 = 10044 crosses the bar


def test_plasma_cannon_between_shot_cooling_matches_ingame():
    # S Plasma Cannon Mk1, measured in-game 2026-07: 5 shots in ~10.4 s
    # bare WITHOUT overheating (heat sits at 9800/10000: net 1800/shot),
    # 5 shots in ~8.7 s under reload x1.2 - and then it overheats,
    # because the shorter gap cools less (net ~2233/shot)
    w = {"overheat": 10000.0, "overheatcooldelay": 2.0, "coolrate": 1000.0,
         "reenable": 7000.0, "heat": 2600.0, "cooldelay": 1.8,
         "reload_time": 2.6, "amount": 1.0, "barrelamount": 1.0,
         "dmg": 491.0}
    s = simulate(w)
    assert s["rate"] == pytest.approx(1 / 2.6)
    # net 1800/shot: after 5 shots heat sits at 9800, the 6th overheats
    assert s["shots_cycle"] == 6

    f = simulate(w, {"reload": 1.2})
    assert f["rate"] == pytest.approx(1.2 / 2.6)
    # the shorter gap cools less, so it overheats one shot sooner (on the 5th)
    assert f["shots_cycle"] == 5
    assert f["shots_cycle"] < s["shots_cycle"]


# ARG M Beam Turret Mk1: hitscan beam (speed = c), heatless. Its <damage> is
# dealt per second while the beam is live (lifetime 3 s of every 7 s cycle).
BEAM_TURRET = {
    "speed": 299792500.0, "lifetime": 3.0, "reload_time": 7.0, "heat": 0.0,
    "amount": 1.0, "barrelamount": 1.0,
    "dmg": 126.0, "dmg_shield": 42.0, "dmg_hull": 0.0,
}


def test_beam_output_matches_ingame_encyclopedia():
    # verified 2026-07: encyclopedia shows damage-vs-shield 168 (= per-second
    # beam damage) and Weapon Output 72 = 168 x lifetime 3 / reload_time 7
    s = simulate(BEAM_TURRET)
    assert s["dmg_s"] == pytest.approx(168.0)          # per-second intensity
    assert s["dmg_s"] * s["rate"] == pytest.approx(168.0)  # peak/burst = dmg_s
    assert s["ss_dps_s"] == pytest.approx(72.0)         # sustained = peak x duty
    assert s["duty"] == pytest.approx(3.0 / 7.0)


def test_beam_reload_raises_intensity_and_sustained():
    # reload packs more sub-shots into the live beam -> higher peak AND higher
    # sustained (verified: S Beam Emitter burst 110 -> 134 under reload x1.225).
    # It does NOT change the beam's on/off cycle, so structural duty is fixed.
    s = simulate(BEAM_TURRET, {"reload": 1.225})
    assert s["dmg_s"] * s["rate"] == pytest.approx(168.0 * 1.225)  # peak scales
    assert s["ss_dps_s"] == pytest.approx(72.0 * 1.225)           # sustained too
    assert s["duty"] == pytest.approx(3.0 / 7.0)                  # cycle unchanged
    # a continuous beam (lifetime == reload) also gains: reload still raises the
    # sub-shot rate, so its sustained scales too (it is NOT reload-inert)
    cont = dict(BEAM_TURRET, lifetime=7.0)
    assert simulate(cont, {"reload": 2.0})["ss_dps_s"] == \
        pytest.approx(2.0 * simulate(cont)["ss_dps_s"])


def test_beam_cooling_is_inert_when_heatless():
    assert simulate(BEAM_TURRET, {"cooling": 1.9}) == simulate(BEAM_TURRET)


def test_guaranteed_stats():
    assert guaranteed_stats(SLASHER) == ["damage", "cooling", "reload"]
    pool_mod = dict(SLASHER, forced=False)
    assert guaranteed_stats(pool_mod) == ["damage"]
