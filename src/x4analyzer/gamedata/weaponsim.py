"""Weapon firing-cycle simulation with equipment mods.

The rules below were validated in-game (sessions of 2026-07) — keep them:

- Reload mods are RATE-semantic on EVERY weapon: a `<reload rate>` is
  multiplied by the mod (x2 = double fire rate), a `<reload time>` is
  DIVIDED by it (x1.2 = 20% faster). The optimal roll is always the
  range MAX. (Corrected 2026-07: S Plasma Cannon Mk1, reload time 2.6 s,
  fired 5 shots in ~10.4 s bare and ~8.7 s under reload x1.2 — the old
  literal-multiply rule mis-predicted a slowdown.) Damage and coolrate
  multiply directly; chargetime multiplies a duration (optimal = MIN).
- Heat weapons: the heat cycle is simulated DISCRETELY, shot by shot. A
  bullet adds its `<heat value>` per shot; a `<heat initial>` is an
  instantaneous spike at the onset of a firing cycle (and it IS the per-shot
  heat for a charge weapon like the Paranid mass driver that has only
  `initial` and no `value`). Between shots the weapon cools once `cooldelay`
  has elapsed, so a slow weapon can shed most of a shot's heat before the
  next — weapons whose heat plateaus below `overheat` never overheat.
  Validated in-game 2026-07: the mass driver (initial 8000, no value) fires
  exactly TWO shots before overheating (8000 -> cool -> 8000 again crosses
  10000); the S Plasma Cannon Mk1 sits at 9800/10000 after five bare shots
  and overheats on the sixth (the +20% fire-rate mod moves that to the
  fifth). The old continuous net-rate model amortised a big per-shot spike
  into a trickle and badly overstated the time-to-overheat for such slow
  weapons. Fast weapons (TER S Electromagnetic Gun Mk1, interval 0.71 s <
  cooldelay 1.0 s, no between-shot cooling) reach 10000/350 = ~29 shots per
  bar / ~20 s cold. At `overheat` the weapon goes offline for
  `overheatcooldelay`, then cools at `coolrate` and re-enables at `reenable`.
- Clip weapons (`<ammunition value reload>`): the clip reload time is
  FIXED — reload mods only scale the shot interval inside the burst.
  The weapon also cools during the clip-reload pause (after cooldelay),
  so many clip weapons never overheat in practice.
- Beam weapons (hitscan, projectile speed = c): rendered as many sub-shots
  packed into a live window; `dmg_s` is the per-second intensity and the beam
  is live for `lifetime` of each `reload_time` cycle. Peak DPS = dmg_s x
  reload; sustained = peak x duty. Verified in-game 2026-07: ARG M Beam
  Turret, dmg_s 168, lifetime 3, reload_time 7 -> encyclopedia Weapon Output
  168 x 3/7 = 72 MW (structural duty when heatless). Reload is rate-semantic:
  it shortens the gap between sub-shots, so it RAISES the per-second intensity
  (peak and sustained both scale x reload -- S Beam Emitter burst 110 -> 134
  under reload x1.225), but does NOT change the on/off cycle. The heat cycle
  is simulated per activation: each adds the `<heat initial>` spike, then
  `<heat value>` per second while live, cooling in the off gaps. If the beam
  overheats within a single activation it fires continuously to the overheat
  (structural gaps don't apply), so its duty is purely heat-limited — e.g.
  the M Scalar Aperture (initial 2000, value 1333/s, lifetime 4) sustains one
  full 4 s beam to ~73% then a shortened ~0.5 s beam before overheating.
- Charge weapons: shot interval = reload time + charge time (a simplified
  model); stats that need heat stay None when there is none.
- Damage vs shields = value + shield attr, vs hull = value + hull attr,
  plus <areadamage> explosion damage (Blast Mortar/flak keep ALL damage
  there), each times projectile count (amount x barrelamount). Heat
  counts once per volley (Split shotguns: amount=4, one 170-heat charge).
- A clip with no <reload> element (Boson Lance Mk1's one-shot clip) makes
  the clip reload the entire firing cycle; reload mods have no field to
  multiply, so they do nothing.

The heat cycle is simulated as discrete shot/activation ticks (see
_bullet_heat_cycle and the beam block), which is required to model both
slow high-per-shot weapons (mass drivers) and the beam onset spike; the
non-heat firing rate stays a closed-form sustained figure.
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


# projectile speed of a beam bullet is the speed of light (hitscan); this is
# the reliable discriminator for beams, whose <damage> is a per-second rate.
SPEED_OF_LIGHT = 299792500.0


def is_beam(weapon: dict) -> bool:
    return (weapon.get("speed") or 0.0) >= SPEED_OF_LIGHT


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


def _bullet_heat_cycle(per_shot: float, onset: float, overheat: float,
                       coolrate: float, cooldelay: float, interval: float,
                       clip: float, clip_reload: float,
                       start: float) -> tuple[int | None, float]:
    """Discretely fire shots from `start` heat until the weapon overheats.
    `onset` is a one-time spike added at the first shot of the firing cycle
    (the `<heat initial>` of a weapon that also has an ongoing per-shot
    `value`). Cooling happens in each gap once `cooldelay` has elapsed; a clip
    reload replaces the gap after every `clip` shots. Returns (n_shots, t_fire)
    — the shot that tips it over and the time from the first shot to that shot
    ((n-1) gaps) — or (None, 0.0) if the heat plateaus below `overheat`."""
    heat = start + onset
    n = 0
    t = 0.0
    max_heat = -1.0
    since_max = 0
    clip_n = int(clip) if clip else 0
    while n < 5000:
        heat += per_shot
        n += 1
        if heat >= overheat:
            return n, t
        if heat > max_heat + 1e-9:      # still climbing -> keep going
            max_heat, since_max = heat, 0
        else:                           # peak stalled a full clip -> never
            since_max += 1
            if since_max > max(clip_n, 1) + 1:
                return None, 0.0
        gap = clip_reload if (clip_n and clip_reload > 0 and n % clip_n == 0) \
            else interval
        heat = max(0.0, heat - coolrate * max(0.0, gap - cooldelay))
        t += gap
    return None, 0.0


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

    # heat sources: `value` accrues per shot (bullet) / per second (beam);
    # `initial` is an INSTANTANEOUS spike at the onset of each firing cycle /
    # beam re-activation. A weapon with only `initial` (Paranid mass drivers)
    # deposits it on every discrete shot. (Model corrected 2026-07;
    # reference numbers in tests/test_weaponsim.py.)
    value_heat = weapon.get("heat") or 0.0
    init_heat = weapon.get("heat_initial") or 0.0
    overheat = weapon.get("overheat") or 0.0
    coolrate = (weapon.get("coolrate") or 0.0) * mc
    cooldelay = weapon.get("cooldelay") or 0.0
    ohcd = weapon.get("overheatcooldelay") or 0.0
    reenable = weapon.get("reenable") or 0.0

    if is_beam(weapon):
        # A beam is many sub-shots packed into its live window; `dmg_s` is the
        # per-second intensity, live for `lifetime` of each `reload_time`
        # cycle. Reload packs in more sub-shots -> higher peak intensity AND
        # heat rate (both scale x mr). Each activation adds the `initial` spike
        # instantly, then `value` per second; cooling happens in the off gap.
        life = weapon.get("lifetime") or 0.0
        rt = weapon.get("reload_time") or 0.0
        struct_duty = min(1.0, life / rt) if rt > 0 else 1.0
        out["rate"] = mr  # peak = dmg_s x mr (reload packs in more sub-shots)
        peak_s, peak_h = dmg_s * mr, dmg_h * mr
        heat_rate = value_heat * mr
        duty = struct_duty
        if value_heat > 0 and overheat > 0 and coolrate > 0:
            out["coolrate"] = coolrate
            gap = max(rt - life, 0.0)

            def beam_cycle(start: float) -> tuple[float | None, int]:
                heat = start
                fire = 0.0
                for a in range(5000):
                    heat += init_heat
                    to_over = (overheat - heat) / heat_rate \
                        if heat_rate > 0 else 1e18
                    live = min(life, max(to_over, 0.0))
                    fire += live
                    heat += heat_rate * live
                    if heat >= overheat:
                        return fire, a + 1
                    heat = max(0.0, heat - coolrate * max(0.0, gap - cooldelay))
                return None, 0

            ss_fire, _ = beam_cycle(reenable)
            if ss_fire is not None:
                ss_cool = ohcd + max(overheat - reenable, 0.0) / coolrate
                heat_duty = ss_fire / (ss_fire + ss_cool) \
                    if ss_fire + ss_cool > 0 else 0.0
                # if it overheats within one activation it fires continuously
                # to the overheat (no lifetime gaps), so structural duty does
                # not additionally apply
                duty = heat_duty if ss_fire <= life else struct_duty * heat_duty
                out.update(ss_fire=ss_fire, ss_cool=ss_cool)
                cold_fire, n_act = beam_cycle(0.0)
                if cold_fire is not None:
                    t_cool = ohcd + overheat / coolrate
                    out.update(t_overheat=cold_fire, t_cooldown=t_cool,
                               t_cycle=cold_fire + t_cool, shots_cycle=n_act)
        out.update(duty=duty, ss_dps_s=peak_s * duty, ss_dps_h=peak_h * duty)
        return out

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

    # Sustained volley rate. A clip of N shots spans (N-1) intra-burst gaps
    # from the first shot to the last, THEN the FIXED clip reload (never
    # modded). The in-game encyclopedia rate-of-fire is this sustained figure,
    # NOT the intra-clip burst rate (1/interval) -- e.g. the S Tau Accelerator
    # reads 3/s burst but ~1.06/s sustained. (Bug fix 2026-07,
    # validated against in-game figures.)
    if clip:
        clip_cycle = max(clip - 1.0, 0.0) * interval + clip_reload
        eff_rate = clip / clip_cycle if clip_cycle > 0 else rate
    else:
        eff_rate = rate
    # display the sustained rate on every weapon (== the plain rate when there
    # is no clip)
    out["rate"] = eff_rate

    # per-shot heat: the ongoing `value`, or the `initial` spike on every shot
    # for a discrete charge weapon that has no `value` (mass drivers)
    per_shot = value_heat if value_heat > 0 else init_heat
    onset = init_heat if value_heat > 0 else 0.0

    overheats = False
    if per_shot > 0 and overheat > 0 and coolrate > 0:
        out["coolrate"] = coolrate
        # cold cycle: fire from 0 until overheat, discretely (the continuous
        # net-rate model badly overstated the time for slow, high-per-shot
        # weapons like the mass driver: 2 shots / ~4.3 s, not ~1.7 / ~7 s)
        n_cold, fire_cold = _bullet_heat_cycle(
            per_shot, onset, overheat, coolrate, cooldelay,
            interval or 0.0, clip, clip_reload, 0.0)
        if n_cold is not None:
            overheats = True
            t_cool = ohcd + overheat / coolrate
            out.update(t_overheat=fire_cold, t_cooldown=t_cool,
                       t_cycle=fire_cold + t_cool, shots_cycle=n_cold,
                       cyc_dmg_s=n_cold * dmg_s, cyc_dmg_h=n_cold * dmg_h,
                       cyc_dps_s=n_cold * dmg_s / (fire_cold + t_cool),
                       cyc_dps_h=n_cold * dmg_h / (fire_cold + t_cool))
            # steady state: fire from reenable to overheat, cool back
            n_ss, fire_ss = _bullet_heat_cycle(
                per_shot, onset, overheat, coolrate, cooldelay,
                interval or 0.0, clip, clip_reload, reenable)
            ss_cool = ohcd + max(overheat - reenable, 0.0) / coolrate
            span = fire_ss + ss_cool
            duty = fire_ss / span if span > 0 else 0.0
            out.update(ss_fire=fire_ss, ss_cool=ss_cool, duty=duty,
                       ss_dps_s=(n_ss or 0) * dmg_s / span if span else 0.0,
                       ss_dps_h=(n_ss or 0) * dmg_h / span if span else 0.0)
    if overheats:
        return out

    if clip:
        # pure clip weapon (e.g. ARG S Ion Blaster): cycle = the burst span
        # ((clip-1) intra-burst gaps) + the fixed clip reload; overheat stats
        # never apply
        burst_span = max(clip - 1.0, 0.0) * interval
        cycle = burst_span + clip_reload
        duty = burst_span / cycle if cycle > 0 else 0.0
        out.update(t_cycle=cycle, shots_cycle=clip,
                   cyc_dmg_s=clip * dmg_s, cyc_dmg_h=clip * dmg_h,
                   cyc_dps_s=clip * dmg_s / cycle,
                   cyc_dps_h=clip * dmg_h / cycle,
                   ss_fire=burst_span, ss_cool=clip_reload, duty=duty,
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
