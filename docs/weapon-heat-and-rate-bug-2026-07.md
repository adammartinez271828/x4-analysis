# Weapon heat & fire-rate bugs (2026-07)

Two data-interpretation bugs in the game-data dashboard's weapon model
(`gamedata-dashboard`), found from a user report: "Mass drivers are treated as
not having heat… S Tau Accelerator shows a fire rate of 3/s, but it is 1.05/s."
Both are confirmed and fixed. Neither touches the savegame pipeline.

## Bug 1 — mass drivers read as heatless

**Symptom.** Paranid Mass Drivers showed no overheat time or cooldown; in-game
they clearly overheat.

**Root cause.** Per-shot heat lives on the *bullet* macro. Almost every bullet
spells it `<heat value="…">`, but the four Paranid railgun bullets spell it
`<heat initial="8000">` with **no `value` attribute**. `_parse_bullets` read
only `value` (defaulting to `0.0`), so heat-per-shot came out `0`, the
`heat > 0` guard in the simulator never engaged, and the weapon was modelled as
a continuous, never-overheating gun at 100 % duty.

**Why it slipped.** `value` is the near-universal spelling — 66 of the 83
heat-bearing bullets. `initial` *alone* is a four-weapon edge case. The 13
beam/burst bullets that carry **both** `initial` and `value` parsed correctly on
`value` (there `value` is the real per-shot/-second heat and `initial` is a
one-off activation spike), which masked the gap. The in-game validation set
(EM Gun, Plasma Cannon, Blast Mortar) happened to use `value`.

**Impact.** 4 weapons — S/M Mass Driver Mk1 & Mk2. Their overheat/cooldown
columns were blank and their sustained DPS was overstated (no heat-duty
throttle). After the fix: heat 8000/shot → overheat in ~6–8 s, ~14–15 s
cooldown, duty ≈ 0.3.

**Fix.** Fall back to `initial` when `value` is absent
(`gamedata/weapons.py::_parse_bullets`). The 13 both-carriers keep using
`value`; their `initial` spike is intentionally ignored by the steady-state
model.

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

Both are the same shape of bug: a near-universal encoding (`value`; a
single-shot fire rate) quietly hid a minority one (`initial`; a clipped burst),
and the in-game validation set was anchored on a few "hero" weapons that didn't
exercise the minority case.

Regression tests added:
- `test_weapons.py` — a railgun bullet with `<heat initial>` only; asserts the
  parser reads 8000, not 0.
- `test_weaponsim.py` — the S Tau reports its ~1.06/s sustained rate, not 3/s;
  the Ion Blaster / Blast Mortar clip-cycle numbers updated to the `(N−1)`-gap
  convention.

Suggested future guard: when refreshing game data, spot-check simulated
fire-rate and overheat against the in-game encyclopedia for one weapon of each
archetype — continuous, clip/burst, charge, railgun, beam — so a new minority
encoding can't pass unnoticed.
