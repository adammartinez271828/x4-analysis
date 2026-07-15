"""Weapon firing-cycle simulation with equipment mods.

The rules below were validated in-game (sessions of 2026-07) — keep them:

- Reload mods are RATE-semantic on EVERY weapon: a `<reload rate>` is
  multiplied by the mod (x2 = double fire rate), a `<reload time>` is
  DIVIDED by it (x1.2 = 20% faster). The optimal roll is always the
  range MAX. (Corrected 2026-07: S Plasma Cannon Mk1, reload time 2.6 s,
  fired 5 shots in ~10.4 s bare and ~8.7 s under reload x1.2 — the old
  literal-multiply rule mis-predicted a slowdown.) Damage and coolrate
  multiply directly; chargetime multiplies a duration (optimal = MIN).
- Heat weapons: each volley adds the bullet's `<heat value>`, and the
  weapon COOLS BETWEEN SHOTS once `cooldelay` has elapsed since the last
  one: net heat per shot = heat - coolrate * max(0, interval - cooldelay).
  Weapons whose net is <= 0 never overheat. (Validated 2026-07 on the
  S Plasma Cannon Mk1: 2600 heat, 1000/s coolrate, 1.8 s cooldelay ->
  net 1800/shot, sits at 9800/10000 after five bare shots without
  overheating, but overheats on the fifth shot under a +20% fire-rate
  mod because the shorter gap cools less.) Fast weapons whose interval
  never exceeds cooldelay reduce to the old no-cooling-while-firing
  model — reference numbers (TER S Electromagnetic Gun Mk1, interval
  0.71 s < cooldelay 1.0 s): 10000/350 = 28.57 volleys per heat bar,
  10000/(350*1.4) = 20.41 s cold time-to-overheat. At `overheat` the
  weapon goes offline for `overheatcooldelay`, then cools at `coolrate`
  and re-enables once heat reaches `reenable`.
- Clip weapons (`<ammunition value reload>`): the clip reload time is
  FIXED — reload mods only scale the shot interval inside the burst.
  The weapon also cools during the clip-reload pause (after cooldelay),
  so many clip weapons never overheat in practice.
- Charge/beam weapons: shot interval = reload time + charge time (a
  simplified model); stats that need heat stay None when there is none.
- Damage vs shields = value + shield attr, vs hull = value + hull attr,
  plus <areadamage> explosion damage (Blast Mortar/flak keep ALL damage
  there), each times projectile count (amount x barrelamount). Heat
  counts once per volley (Split shotguns: amount=4, one 170-heat charge).
- A clip with no <reload> element (Boson Lance Mk1's one-shot clip) makes
  the clip reload the entire firing cycle; reload mods have no field to
  multiply, so they do nothing.

The continuous-rate model treats every shot as occupying 1/rate seconds
and heat as accruing at the net rate (matching both the 20.41 s EM Gun
figure and the plasma-cannon shot counts) rather than simulating
discrete shot ticks.
"""

from __future__ import annotations

# mod stats that influence the simulated firing cycle; mods whose guaranteed
# effects touch none of these are left off the comparison table
SIM_STATS = ("damage", "cooling", "reload", "chargetime")

# order of the stat vector shipped to the dashboard page
STAT_KEYS = [
    "dmg_s", "dmg_h", "rate", "coolrate",
    "t_overheat", "t_cooldown", "t_cycle", "shots_cycle",
    "cyc_dmg_s", "cyc_dmg_h", "cyc_dps_s", "cyc_dps_h",
    "ss_fire", "ss_cool", "duty", "ss_dps_s", "ss_dps_h",
]


def reload_kind(weapon: dict) -> str | None:
    if weapon.get("reload_rate"):
        return "rate"
    if weapon.get("reload_time"):
        return "time"
    return None


def optimal_mult(stat: str, lo: float, hi: float,
                 rkind: str | None = None) -> float:
    """Best-for-player end of a mod roll range. Reload mods are
    rate-semantic on every weapon (verified in-game 2026-07), so reload —
    like damage and cooling — always wants the MAX; chargetime multiplies
    a duration and wants the MIN. A malus range (both ends < 1) picks its
    least-bad end the same way. `rkind` is kept for API compatibility but
    no longer changes the result."""
    if stat == "chargetime":
        return min(lo, hi)
    return max(lo, hi)


def guaranteed_stats(mod: dict) -> list[str]:
    """Stats the mod ALWAYS applies: the primary plus forced bonuses.
    Weighted optional pools are excluded (shown as detail only)."""
    stats = [mod["stat"]]
    if mod["forced"]:
        stats += [b["stat"] for b in mod["bonuses"]]
    return stats


def mod_multipliers(mod: dict, weapon: dict) -> dict[str, float]:
    """stat -> multiplier at the optimal roll for this weapon (primary +
    forced bonuses at their best-for-player value)."""
    rkind = reload_kind(weapon)
    mults = {mod["stat"]: optimal_mult(mod["stat"], mod["min"], mod["max"],
                                       rkind)}
    if mod["forced"]:
        for b in mod["bonuses"]:
            mults[b["stat"]] = optimal_mult(b["stat"], b["min"], b["max"],
                                            rkind)
    return mults


def simulate(weapon: dict, mults: dict[str, float] | None = None) -> dict:
    """Firing-cycle stats for a weapon with mod multipliers applied.
    Returns {key: float | None} over STAT_KEYS; None = not applicable
    (e.g. overheat stats on a weapon that never heats up)."""
    m = mults or {}
    md = m.get("damage", 1.0)
    mc = m.get("cooling", 1.0)
    mr = m.get("reload", 1.0)
    mct = m.get("chargetime", 1.0)

    proj = (weapon.get("amount") or 1.0) * (weapon.get("barrelamount") or 1.0)
    base = weapon.get("dmg") or 0.0
    # explosion damage (<areadamage>) hits the target on top of the direct
    # hit; explosive weapons like the Blast Mortar carry ALL damage there
    area = weapon.get("area_dmg") or 0.0
    dmg_s = (base + (weapon.get("dmg_shield") or 0.0) + area
             + (weapon.get("area_dmg_shield") or 0.0)) * md * proj
    dmg_h = (base + (weapon.get("dmg_hull") or 0.0) + area) * md * proj

    # volley interval: reload mods are rate-semantic on every weapon
    # (verified in-game 2026-07) - they multiply a stored rate and DIVIDE
    # a stored time
    interval = None
    if weapon.get("reload_rate"):
        r = weapon["reload_rate"] * mr
        interval = 1.0 / r if r > 0 else None
    elif weapon.get("reload_time"):
        interval = weapon["reload_time"] / mr if mr > 0 else None
    if weapon.get("chargetime"):
        interval = (interval or 0.0) + weapon["chargetime"] * mct

    out: dict[str, float | None] = {k: None for k in STAT_KEYS}
    out["dmg_s"], out["dmg_h"] = dmg_s, dmg_h

    clip = weapon.get("ammo_clip") or 0.0
    clip_reload = weapon.get("ammo_reload") or 0.0
    if interval is None and clip and clip_reload > 0:
        # no <reload> element at all (Boson Lance Mk1: a one-shot clip):
        # the clip reload IS the whole firing cycle, so reload mods have
        # nothing to multiply
        interval = 0.0
    if interval is None or interval < 0 or (interval == 0 and not clip):
        return out
    rate = 1.0 / interval if interval > 0 else None

    # sustained volley rate including the FIXED clip reload (never modded)
    eff_rate = clip / (clip * interval + clip_reload) if clip else rate
    # with no intra-burst interval the sustained rate is the only fire rate
    out["rate"] = rate if rate is not None else eff_rate

    heat = weapon.get("heat") or 0.0
    overheat = weapon.get("overheat") or 0.0
    coolrate = (weapon.get("coolrate") or 0.0) * mc
    net_heat = 0.0
    if heat > 0 and overheat > 0 and coolrate > 0:
        out["coolrate"] = coolrate
        # the weapon cools between shots once cooldelay has elapsed; slow
        # weapons therefore accrue less than <heat> per shot and may never
        # overheat at all (verified in-game 2026-07, S Plasma Cannon Mk1)
        cd = weapon.get("cooldelay") or 0.0
        cooled_shot = coolrate * max(0.0, (interval or 0.0) - cd)
        if clip and clip_reload > 0:
            cooled_shot += coolrate * max(0.0, clip_reload - cd) / clip
        net_heat = heat - cooled_shot
    if net_heat > 0 and eff_rate:
        ohcd = weapon.get("overheatcooldelay") or 0.0
        reenable = weapon.get("reenable") or 0.0
        heat_rate = net_heat * eff_rate

        # cold cycle: 0 -> overheat -> fully cooled
        t_over = overheat / heat_rate
        t_cool = ohcd + overheat / coolrate
        shots = overheat / net_heat
        out.update(t_overheat=t_over, t_cooldown=t_cool,
                   t_cycle=t_over + t_cool, shots_cycle=shots,
                   cyc_dmg_s=shots * dmg_s, cyc_dmg_h=shots * dmg_h,
                   cyc_dps_s=shots * dmg_s / (t_over + t_cool),
                   cyc_dps_h=shots * dmg_h / (t_over + t_cool))

        # steady state: fire reenable -> overheat, cool back to reenable
        band = max(overheat - reenable, 0.0)
        ss_fire = band / heat_rate
        ss_cool = ohcd + band / coolrate
        duty = ss_fire / (ss_fire + ss_cool) if ss_fire + ss_cool > 0 else 0.0
        out.update(ss_fire=ss_fire, ss_cool=ss_cool, duty=duty,
                   ss_dps_s=dmg_s * eff_rate * duty,
                   ss_dps_h=dmg_h * eff_rate * duty)
    elif clip:
        # pure clip weapon (e.g. ARG S Ion Blaster): cycle = empty the clip
        # + fixed clip reload; overheat stats never apply
        cycle = clip * interval + clip_reload
        duty = clip * interval / cycle if cycle > 0 else 0.0
        out.update(t_cycle=cycle, shots_cycle=clip,
                   cyc_dmg_s=clip * dmg_s, cyc_dmg_h=clip * dmg_h,
                   cyc_dps_s=clip * dmg_s / cycle,
                   cyc_dps_h=clip * dmg_h / cycle,
                   ss_fire=clip * interval, ss_cool=clip_reload, duty=duty,
                   ss_dps_s=clip * dmg_s / cycle,
                   ss_dps_h=clip * dmg_h / cycle)
    else:
        # no heat, no clip: fires forever
        out.update(duty=1.0, ss_dps_s=dmg_s * rate, ss_dps_h=dmg_h * rate)
    return out


def stat_vector(weapon: dict, mults: dict[str, float] | None = None
                ) -> list[float | None]:
    sim = simulate(weapon, mults)
    return [sim[k] for k in STAT_KEYS]
