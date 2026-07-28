"""Runtime mod detection and recipe patching (gamedata/modpatch.py).

The bundled CSVs stay stock; a mod that rewrites recipes is detected per save
and applied to that run's RefData only.
"""
from types import SimpleNamespace

import pandas as pd

from x4analyzer.gamedata import modpatch

_COLS = ["ware", "method", "time", "amount", "input_ware", "input_amount",
         "work_effect"]


def _ref():
    return SimpleNamespace(recipes=pd.DataFrame([
        # stock advancedelectronics: ceiling is 1 + 0.36
        ["advancedelectronics", "default", 720, 54, "energycells", 60, 0.36],
        ["advancedelectronics", "default", 720, 54, "microchips", 44, 0.36],
        ["advancedelectronics", "default", 720, 54, "quantumtubes", 20, 0.36],
        ["weaponcomponents", "default", 1800, 170, "energycells", 60, 0.53],
        ["hullparts", "default", 900, 294, "energycells", 80, 0.37],
    ], columns=_COLS))


def _save(prod=(), extensions=()):
    # module_production rows are (host, macro, ware, efficiency, state)
    return SimpleNamespace(module_production=list(prod),
                           extensions=list(extensions))


def test_stock_save_is_left_alone():
    save = _save(prod=[("s1", "m", "advancedelectronics", 1.36, "producing")])
    assert modpatch.detect(save, _ref()) == []


def test_efficiency_above_the_stock_ceiling_detects_the_mod():
    # 1.39556 > 1 + 0.36: impossible unless the work effect was replaced
    save = _save(prod=[("s1", "m", "advancedelectronics", 1.39556, "producing")])
    found = modpatch.detect(save, _ref())
    assert [m.mod_id for m in found] == ["ws_1668472321"]


def test_detection_by_extension_id_when_the_save_records_it():
    save = _save(extensions=[("ws_1668472321", "571", "Econ Balance")])
    assert [m.mod_id for m in modpatch.detect(save, _ref())] == ["ws_1668472321"]


def test_patch_replaces_the_recipe_wholesale():
    save = _save(prod=[("s1", "m", "advancedelectronics", 1.39556, "producing")])
    out = modpatch.patch_reference(save, _ref())
    ae = out.recipes[out.recipes["ware"] == "advancedelectronics"]
    assert set(ae["amount"]) == {65.0}
    assert set(ae["work_effect"]) == {0.40}
    assert dict(zip(ae["input_ware"], ae["input_amount"])) == {
        "energycells": 150.0, "microchips": 49.0, "quantumtubes": 36.0}
    # the sibling ware in the same mod file goes with it
    wc = out.recipes[out.recipes["ware"] == "weaponcomponents"]
    assert set(wc["amount"]) == {204.0}
    # untouched wares survive unchanged
    hp = out.recipes[out.recipes["ware"] == "hullparts"]
    assert set(hp["amount"]) == {294.0}


def test_patch_is_a_copy_leaving_the_bundled_data_untouched():
    ref = _ref()
    before = ref.recipes.copy()
    save = _save(prod=[("s1", "m", "advancedelectronics", 1.39556, "producing")])
    modpatch.patch_reference(save, ref)
    pd.testing.assert_frame_equal(ref.recipes, before)


def test_defensive_against_missing_or_junk_data():
    # no production data, no extensions, unknown ware, None efficiency
    assert modpatch.detect(SimpleNamespace(), _ref()) == []
    assert modpatch.detect(_save(), _ref()) == []
    assert modpatch.detect(
        _save(prod=[("s1", "m", "nosuchware", 99.0, "x"),
                    ("s1", "m", "advancedelectronics", None, "x")]), _ref()) == []
    empty = SimpleNamespace(recipes=pd.DataFrame(columns=_COLS))
    assert modpatch.detect(
        _save(prod=[("s1", "m", "advancedelectronics", 9.0, "x")]), empty) == []
    # patching with nothing detected returns the same object
    ref = _ref()
    assert modpatch.patch_reference(_save(), ref) is ref
