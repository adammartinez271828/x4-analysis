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

Two kinds of value are patched: production `recipes` (wholesale replacement of
a `(ware, method)` entry) and `modcaps` fields (one attribute of one macro's
capacity row, e.g. `nd_habitat_cap_boost` raising habitat housing). The
`modcaps` patch is field-level precisely because the mods that write it ship
attribute `<replace>` diffs; `gamedata/extract.py` reads the same diffs.

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
class ModCapOverride:
    """One field of one `modcaps` row (a station/module macro capacity)."""
    macro: str
    field: str                  # modcaps column: housing/workers/cargo_max/...
    value: float


@dataclass(frozen=True)
class ModPatch:
    mod_id: str                 # extension id, for the save's <patch> list
    name: str
    source: str                 # where the values were read from
    recipes: tuple[RecipeOverride, ...] = ()
    modcaps: tuple[ModCapOverride, ...] = ()
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

# nd_habitat_cap_boost ships `save="true"` -- the save records
# `<patch extension="ws_3737446888" version="100" name="Habitat Capacity
# Boost"/>`, so detection is exact on the id and NO fingerprint is used: a save
# without the mod never matches, and a save with it always does.
#
# Every one of its 26 files is a `<diff>` with a single
# `<replace sel="/macros/macro/properties/workforce/@capacity">`, i.e. it moves
# housing CAPACITY only. It does not touch `<workforce max>`, so the employment
# target of E-124 -- which sums production/build modules and the station macro,
# and deliberately excludes habitat housing -- is unaffected by construction.
#
# Stock housing is per race, not one triple: arg/bor/pir/spl/tel 250/500/1000,
# par 333/666/999, ter 100/250/500, Antigone pillar 1000 and spire 2000. The
# mod flattens them by SIZE (2500/5000/10000) and gives the two landmarks
# 15000/20000, so the boost ranges 7.5x (par L) to 25x (ter S).
#
# hab_par_{m_02,s_02,s_03}_macro are in the mod but in no installed content;
# they are kept verbatim and simply find no row to patch.
_HAB_S, _HAB_M, _HAB_L = 2500.0, 5000.0, 10000.0
_HAB_BOOST = ModPatch(
    mod_id="ws_3737446888",
    name="Habitat Capacity Boost",
    source=("nd_habitat_cap_boost/ext_01.cat -> assets/structures/habitat/"
            "macros/hab_*.xml (26 <diff><replace> files)"),
    note=("save=\"true\", so the save's <patches> list names it; detected by "
          "id only. Housing capacity is not an input to the ration reserve or "
          "the production rate (E-124) -- it feeds the audit staffing panel "
          "and module_cap.housing."),
    modcaps=tuple(
        ModCapOverride(macro=f"hab_{race}_{size}_{idx}_macro",
                       field="housing", value=cap)
        for race in ("arg", "bor", "par", "pir", "spl", "tel", "ter")
        for size, cap in (("s", _HAB_S), ("m", _HAB_M), ("l", _HAB_L))
        for idx in ("01",)
    ) + (
        ModCapOverride("hab_par_m_02_macro", "housing", _HAB_M),
        ModCapOverride("hab_par_s_02_macro", "housing", _HAB_S),
        ModCapOverride("hab_par_s_03_macro", "housing", _HAB_S),
        ModCapOverride("landmarks_arg_antigonepillar_01_macro", "housing",
                       15000.0),
        ModCapOverride("landmarks_arg_antigonespire_01_macro", "housing",
                       20000.0),
    ),
)

KNOWN_MODS: tuple[ModPatch, ...] = (_ECON_BAL, _HAB_BOOST)


# --- detection ------------------------------------------------------------

def _ware_ceiling(recipes: pd.DataFrame, ware: str) -> float | None:
    """Highest stock `1 + work_effect` across that ware's methods."""
    if recipes is None or "ware" not in getattr(recipes, "columns", ()):
        return None
    rows = recipes[recipes["ware"] == ware]
    if rows.empty or "work_effect" not in rows.columns:
        # a stale user-dir recipes.csv predates the work_effect column: we
        # cannot fingerprint. NOT a 0 default -- that would put the ceiling at
        # 1.0 and let any vanilla workforce bonus look like the mod.
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
    if rec.empty or not {"ware", "method"} <= set(rec.columns):
        # an unexpected (stale/partial) recipes frame: keep it as-is and just
        # append the overrides rather than dropping rows we cannot key
        kept = rec
    else:
        kept = rec[~rec.apply(
            lambda r: (r["ware"], r["method"]) in keys, axis=1)]
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
    return _with(ref, recipes=patched)


def apply_modcaps(ref, mods) -> object:
    """A copy of `ref` whose `modcaps` carry the mods' capacity overrides.

    Field-level, unlike the recipe patch: a mod's `<diff>` replaces ONE
    attribute of a macro, so everything else on the row must survive. Macros
    the reference data does not know are skipped (a mod may ship overrides for
    content that is not installed).
    """
    overrides = [o for m in mods for o in m.modcaps]
    caps = getattr(ref, "modcaps", None)
    if not overrides or caps is None or caps.empty \
            or "macro" not in caps.columns:
        return ref
    out = caps.copy()
    macro = out["macro"].astype(str).str.lower()
    for o in overrides:
        if o.field not in out.columns:
            continue
        hit = macro == o.macro.lower()
        if not hit.any():
            continue
        if out[o.field].dtype == object:
            out.loc[hit, o.field] = str(o.value)
        else:
            out.loc[hit, o.field] = o.value
    return _with(ref, modcaps=out)


def _with(ref, **fields):
    """`ref` with fields replaced -- dataclass or hand-built namespace (tests)."""
    if hasattr(ref, "__dataclass_fields__"):
        return replace(ref, **fields)
    import copy
    out = copy.copy(ref)
    for k, v in fields.items():
        setattr(out, k, v)
    return out


def patch_reference(save, ref, log=None):
    """Detect and apply in one step. Returns the (possibly patched) ref."""
    mods = detect(save, ref)
    if not mods:
        return ref
    for m in mods:
        if log:
            log(f"Mod detected: {m.name} ({m.mod_id}) — applying "
                f"{len(m.recipes)} recipe override(s) and {len(m.modcaps)} "
                f"module-capacity override(s) to this run only "
                f"(bundled CSVs stay stock). Source: {m.source}")
    return apply_modcaps(apply_recipes(ref, mods), mods)
