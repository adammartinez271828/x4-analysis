# Weapon heat & fire-rate bugs (2026-07)

Two bugs in the game-data dashboard's weapon model (`gamedata-dashboard`),
found from a user report: "Mass drivers are treated as not having heat… S Tau
Accelerator shows a fire rate of 3/s, but it is 1.05/s." Both are confirmed and
fixed; the mass-driver bug turned out to require replacing the simulator's
continuous heat model with a discrete one. Neither touches the savegame
pipeline.

## Bug 1 — mass drivers read as heatless (and the deeper heat-model fix)

**Symptom.** Paranid Mass Drivers showed no overheat time or cooldown; in-game
they clearly overheat (two shots, then offline).

**Root cause (parse).** Per-shot heat lives on the *bullet* macro. Almost every
bullet spells it `<heat value="…">`, but the four Paranid railgun bullets spell
it `<heat initial="8000">` with **no `value` attribute**. `_parse_bullets` read
only `value` (defaulting to `0.0`), so heat-per-shot came out `0`, the heat
guard in the simulator never engaged, and the weapon was modelled as a
continuous, never-overheating gun at 100 % duty.

**Root cause (model).** Fixing the parse exposed a second, deeper problem: the
two heat attributes have **different meanings**, and the simulator's
*continuous-rate* heat model couldn't represent either the mass driver or the
`initial`+`value` beams:

- **`value`** is the ongoing heat — per shot for a bullet, per second for a beam.
- **`initial`** is an *instantaneous spike* at the onset of a firing cycle / beam
  re-activation. For a discrete charge weapon that has only `initial` (the mass
  drivers), that spike is deposited on **every shot**.

The continuous model amortised a large per-shot spike into a smooth trickle, so
the mass driver came out at ~1.7 shots / ~7 s instead of the real **2 shots /
~4.3 s**, and beams ignored the `initial` spike entirely.

**Why it slipped.** `value` is the near-universal spelling — 66 of the 83
heat-bearing bullets. `initial`-only is a four-weapon edge case, and the 13
beam/burst "both" carriers parsed fine on `value`, masking the gap. The in-game
validation set (EM Gun, Plasma Cannon, Blast Mortar) all use `value` and are
fast enough that continuous ≈ discrete, so the model's blind spot never showed.

**Impact.** 4 mass-driver weapons went from "heatless" to overheating in 2
shots. The heat cycle is now **simulated discretely** (shot-by-shot for bullets,
activation-by-activation for beams), which also shifts every heat weapon's
overheat/duty numbers slightly — validated against four in-game observations:

| weapon | model | in-game |
|---|---|---|
| Mass Driver (initial 8000, no value) | 2 shots, overheat ~4.3 s | 2 shots ✓ |
| M Scalar Aperture beam (initial 2000 + value 1333/s) | full 4 s beam → 73 %, then a 0.5 s beam → overheat | "sustains ~70 %, then a shortened beam" ✓ |
| Plasma Cannon (value 2600) | 5 safe shots, 6th overheats | ✓ |
| EM Gun (value 350) | ~29 shots / ~20 s | 20.4 s (continuous formula; 2 % shift) |

**Fix.** Parse `value` and `initial` as separate fields
(`gamedata/weapons.py`), and replace the continuous heat math in
`gamedata/weaponsim.py::simulate` with a discrete firing-cycle simulation
(`_bullet_heat_cycle` for bullets, an inline activation loop for beams) that
deposits `initial` at each cycle onset and `value` per shot/second.

## Bug 2 — burst rate shown instead of sustained

**Symptom.** The S Tau Accelerator's fire rate read 3/s; the in-game
encyclopedia shows ~1.05/s.

**Root cause.** Clip/burst weapons store two numbers: a fast intra-clip
`<reload rate>` (e.g. 3/s) and a separate `<ammunition value="6" reload="4">`
(clip size + a **fixed** reload). The simulator displayed `1/interval` — the
intra-clip **burst** rate — whereas the encyclopedia reports the **sustained**
rate across the whole clip cycle (fire the clip, then reload).

A second, smaller error: the cycle span was computed as `clip·interval +
reload`. The correct span is `(clip−1)·interval + reload` — N shots have N−1
gaps between them, then the reload. This is what makes the number match:
S Tau Mk2 = `6 / ((6−1)/3 + 4) = 1.06/s`.

**Impact.** 122 clip weapons displayed the burst rate instead of sustained —
some dramatically off (SPL Neutron Gatling Turret 18 → 6.5/s; M Bolt Turret
16 → 3.6/s; S Tau 3 → 1.06/s). The cycle/duty/DPS figures for every clip weapon
also shifted slightly with the N→N−1 correction. Non-clip weapons (EM Gun,
Plasma Cannon, beams, charge weapons) are unchanged — for them sustained ==
burst.

**Fix.** Report the sustained rate on every weapon (it equals the plain rate
when there is no clip), and use the `(clip−1)`-gap cycle throughout
(`gamedata/weaponsim.py`). Boson Lance (a one-shot clip) is unaffected: with
`clip = 1` there are no intra-burst gaps, so the reload *is* the cycle.

## How these happened / guardrails added

All three are the same shape of bug: a near-universal encoding (`value`; a
single-shot fire rate; smooth-enough heat) quietly hid a minority one
(`initial`; a clipped burst; a big per-shot spike), and the in-game validation
set was anchored on a few "hero" weapons (EM Gun, Plasma Cannon, Beam Turret)
that didn't exercise the minority case. The continuous heat model in particular
looked correct precisely *because* every validated weapon was fast enough that
continuous ≈ discrete.

Regression tests added:
- `test_weapons.py` — a railgun bullet with `<heat initial>` only; asserts the
  parser keeps `heat=0` / `heat_initial=8000` separately.
- `test_weaponsim.py` — the mass driver fires 2 shots / ~4.3 s; the M Scalar
  Aperture beam does one full 4 s activation then a shortened one before
  overheating; the S Tau reports ~1.06/s sustained, not 3/s; the EM Gun /
  Plasma Cannon / clip-cycle numbers updated to the discrete `(N−1)`-gap values.

Suggested future guard: when refreshing game data, spot-check simulated
fire-rate and overheat against actual in-game behaviour for one weapon of each
archetype — continuous, clip/burst, charge, railgun, beam — so a new minority
encoding or timing regime can't pass unnoticed.
