"""Runtime mod patches: keep the bundled CSVs stock, fix the data per save.

The reference CSVs in `data/` are extracted from **base game + DLC only** and
are deliberately kept that way — they are committed, shared across saves, and
should describe vanilla X4. But this project's saves are heavily modded, and
some mods rewrite production recipes. Analysing such a save against stock
recipes silently produces wrong throughputs, and therefore wrong storage
allocations, prices and everything downstream.

So instead of baking mod values into the CSVs, we detect the mod **per save**
and apply its changes to the in-memory `RefData` for that run only. Nothing on
disk changes; a save without the mod is unaffected.

Detection has two routes, because X4 mods fall into two camps:

* **`save="true"` mods register in the savegame.** They appear as
  `<patches><patch extension="ws_..." version=".." name=".."/></patches>`, and
  `SaveData.extensions` carries them. Matching on the extension id is exact.
* **`save="false"` mods leave no trace in the save at all.** They are pure data
  overlays, so the game does not record them — `faction_fix_pack_econ_bal`
  (`ws_1668472321`) is one, and it is precisely the one that rewrites recipes.
  For these the only option is a **fingerprint**: a value in the save that is
  impossible under stock data.

The fingerprint used here is the production efficiency ceiling. A module
serialises `<production><efficiency product="X"/></production>`, and X is
`1 + work_effect x workforce_ratio` with the ratio in [0, 1] — so X can never
exceed `1 + work_effect` under stock data. When it does, that ware's work
effect is not the stock one and the recipe has been replaced.

Everything here is derived from reading the mod's own packed XML, not inferred
from arithmetic. See docs/reference/save-semantics.md § Mod-aware reference
data for the provenance and the measured effect.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

_EPS = 1e-6


@dataclass(frozen=True)
class RecipeOverride:
    """A full replacement for one (ware, method) production entry."""
    ware: str
    method: str
    time: float
    amount: float
    work_effect: float
    inputs: dict[str, float]


@dataclass(frozen=True)
class ModPatch:
    mod_id: str                 # extension id, for the save's <patch> list
    name: str
    source: str                 # where the values were read from
    recipes: tuple[RecipeOverride, ...] = ()
    # ware whose efficiency ceiling gives the mod away; None = detect by id
    fingerprint_ware: str | None = None
    note: str = ""


# --- the registry ---------------------------------------------------------
#
# faction_fix_pack_econ_bal ships `save="false"`, so it is invisible in the
# save's <patches> list — detected by fingerprint instead. Its wares.xml is a
# <diff> of three <replace> ops; the two production recipes are below (the
# third only changes a lasertower BUILD input, which storage does not use).
#
# NB `weaponcomponents` keeps work_effect 0.53, so it raises no fingerprint of
# its own. It is applied because it ships in the same file as the ware that
# does — one mod, one atomic change set.
_ECON_BAL = ModPatch(
    mod_id="ws_1668472321",
    name="Faction Enhancer - Econ Balance Module",
    source="faction_fix_pack_econ_bal/ext_01.cat -> libraries/wares.xml",
    fingerprint_ware="advancedelectronics",
    note=("save=\"false\", so it never appears in the save's <patches> list. "
          "Detected by advancedelectronics reporting an efficiency above the "
          "stock 1 + 0.36 ceiling (the mod raises the work effect to 0.40)."),
    recipes=(
        RecipeOverride(
            ware="advancedelectronics", method="default",
            time=720.0, amount=65.0, work_effect=0.40,
            inputs={"energycells": 150.0, "microchips": 49.0,
                    "quantumtubes": 36.0}),
        RecipeOverride(
            ware="weaponcomponents", method="default",
            time=1800.0, amount=204.0, work_effect=0.53,
            inputs={"energycells": 120.0, "hullparts": 25.0,
                    "plasmaconductors": 36.0}),
    ),
)

KNOWN_MODS: tuple[ModPatch, ...] = (_ECON_BAL,)


# --- detection ------------------------------------------------------------

def _ware_ceiling(recipes: pd.DataFrame, ware: str) -> float | None:
    """Highest stock `1 + work_effect` across that ware's methods."""
    rows = recipes[recipes["ware"] == ware]
    if rows.empty:
        return None
    we = pd.to_numeric(rows["work_effect"], errors="coerce").fillna(0.0)
    return 1.0 + float(we.max())


def detect(save, ref) -> list[ModPatch]:
    """Which known mods are active for this save.

    Defensive by convention: anything missing (no extensions list, no
    production data, an unknown ware) simply means "not detected".
    """
    found: list[ModPatch] = []
    ids = {str(e[0]) for e in (getattr(save, "extensions", None) or ())}
    prod = getattr(save, "module_production", None) or ()
    recipes = getattr(ref, "recipes", None)
    for mod in KNOWN_MODS:
        if mod.mod_id in ids:
            found.append(mod)
            continue
        ware = mod.fingerprint_ware
        if not ware or recipes is None or recipes.empty:
            continue
        ceiling = _ware_ceiling(recipes, ware)
        if ceiling is None:
            continue
        # rows are (host_id, macro, ware, efficiency, state)
        if any(len(r) > 3 and r[2] == ware and r[3] is not None
               and float(r[3]) > ceiling + _EPS for r in prod):
            found.append(mod)
    return found


# --- application ----------------------------------------------------------

_COLS = ["ware", "method", "time", "amount", "input_ware", "input_amount",
         "work_effect"]


def apply_recipes(ref, mods) -> object:
    """A copy of `ref` whose recipes carry the mods' overrides.

    The originals are dropped and replaced wholesale — these are `<replace>`
    ops on the whole `<production>` element, so a merge would be wrong: the
    mod can remove an input as well as change one.
    """
    overrides = [o for m in mods for o in m.recipes]
    if not overrides or getattr(ref, "recipes", None) is None:
        return ref
    rec = ref.recipes
    keys = {(o.ware, o.method) for o in overrides}
    kept = rec[~rec.apply(
        lambda r: (r["ware"], r["method"]) in keys, axis=1)] if not rec.empty else rec
    rows = []
    for o in overrides:
        if not o.inputs:
            rows.append([o.ware, o.method, o.time, o.amount, "", 0.0,
                         o.work_effect])
        for inw, amt in o.inputs.items():
            rows.append([o.ware, o.method, o.time, o.amount, inw, amt,
                         o.work_effect])
    patched = pd.concat([kept, pd.DataFrame(rows, columns=_COLS)],
                        ignore_index=True)
    return replace(ref, recipes=patched) if hasattr(ref, "__dataclass_fields__") \
        else _shallow_with_recipes(ref, patched)


def _shallow_with_recipes(ref, recipes):
    """Fallback for a hand-built namespace (tests)."""
    import copy
    out = copy.copy(ref)
    out.recipes = recipes
    return out


def patch_reference(save, ref, log=None):
    """Detect and apply in one step. Returns the (possibly patched) ref."""
    mods = detect(save, ref)
    if not mods:
        return ref
    for m in mods:
        if log:
            log(f"Mod detected: {m.name} ({m.mod_id}) — applying "
                f"{len(m.recipes)} recipe override(s) to this run only "
                f"(bundled CSVs stay stock). Source: {m.source}")
    return apply_recipes(ref, mods)
