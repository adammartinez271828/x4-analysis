"""nd_habitat_cap_boost (E-061): diff reading + the runtime modcaps patch.

The mod is `save="true"`, so it is detected on its extension id alone — no
fingerprint, hence no way to fire on a save that does not run it. Its files
are `<diff>` documents with no `<macro>` element, which the extractor used to
skip outright; `macro_attr_diffs` reads them.
"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from lxml import etree

from x4analyzer.gamedata import modpatch
from x4analyzer.gamedata.extract import extract_modcaps, macro_attr_diffs

_CAP_COLS = ["macro", "class", "housing", "workers", "cargo_max",
             "cargo_tags", "unit_storage"]

# stock values, from the committed modcaps.csv
_STOCK = [
    ["hab_arg_s_01_macro", "habitation", 250.0, None, None, "", None],
    ["hab_par_l_01_macro", "habitation", 999.0, None, None, "", None],
    ["hab_ter_s_01_macro", "habitation", 100.0, None, None, "", None],
    ["landmarks_arg_antigonespire_01_macro", "habitation", 2000.0,
     None, None, "", None],
    # an untouched neighbour: a production module with a workforce DEMAND
    ["prod_gen_energycells_01_macro", "production", None, 200.0,
     None, "", None],
]


def _ref():
    return SimpleNamespace(
        recipes=pd.DataFrame(columns=["ware", "method", "time", "amount",
                                      "input_ware", "input_amount",
                                      "work_effect"]),
        modcaps=pd.DataFrame(_STOCK, columns=_CAP_COLS))


def _save(extensions=()):
    return SimpleNamespace(module_production=[], extensions=list(extensions))


_MOD = [("ws_3737446888", "100", "Habitat Capacity Boost")]


# --- reading the diffs ----------------------------------------------------

def test_macro_attr_diffs_reads_a_replace_with_no_macro_element():
    root = etree.fromstring(
        b'<diff><replace sel="/macros/macro/properties/workforce/@capacity">'
        b'2500</replace></diff>')
    assert macro_attr_diffs(root) == {("workforce", "capacity"): "2500"}


def test_macro_attr_diffs_ignores_non_diffs_and_unknown_ops():
    plain = etree.fromstring(b'<macros><macro name="x"/></macros>')
    assert macro_attr_diffs(plain) == {}
    weird = etree.fromstring(
        b'<diff><add sel="/macros/macro"><properties/></add>'
        b'<replace sel="//ware[@id=\'x\']/@price">1</replace>'
        b'<!--c--></diff>')
    assert macro_attr_diffs(weird) == {}
    assert macro_attr_diffs(None) == {}


def test_extract_modcaps_applies_a_diff_file(tmp_path: Path):
    """A `<diff>` for a known macro patches its row; one for an unknown macro
    is dropped rather than inventing a half-empty row."""
    class FakeGF:
        _files = {
            "assets/structures/habitat/macros/hab_arg_s_01_macro.xml":
                b'<macros><macro name="hab_arg_s_01_macro" class="habitation">'
                b'<properties><workforce capacity="250"/></properties>'
                b'</macro></macros>',
            "extensions/mod/assets/structures/habitat/macros/"
            "hab_arg_s_01_macro.xml":
                b'<diff><replace sel="/macros/macro/properties/workforce/'
                b'@capacity">2500</replace></diff>',
            "extensions/mod/extensions/ego_dlc_terran/assets/structures/"
            "habitat/macros/hab_nope_01_macro.xml":
                b'<diff><replace sel="/macros/macro/properties/workforce/'
                b'@capacity">2500</replace></diff>',
        }

        def glob(self, regex):
            import re
            return sorted(p for p in self._files if re.match(regex, p))

        def read_bytes(self, path):
            return self._files[path]

    rows = extract_modcaps(FakeGF())
    assert rows == [["hab_arg_s_01_macro", "habitation", "2500", "", "", "", ""]]


# --- detection ------------------------------------------------------------

def test_detected_only_when_the_save_records_the_extension():
    assert [m.mod_id for m in modpatch.detect(_save(_MOD), _ref())] \
        == ["ws_3737446888"]
    # no fingerprint route: an unmodded save cannot trip it
    assert modpatch.detect(_save(), _ref()) == []
    assert modpatch.detect(_save([("ws_999", "1", "other")]), _ref()) == []


def test_unmodded_save_keeps_stock_housing():
    ref = _ref()
    out = modpatch.patch_reference(_save(), ref)
    assert out is ref


# --- application ----------------------------------------------------------

def test_habitat_housing_is_boosted_and_nothing_else_moves():
    ref = _ref()
    out = modpatch.patch_reference(_save(_MOD), ref)
    caps = out.modcaps.set_index("macro")
    assert caps.loc["hab_arg_s_01_macro", "housing"] == 2500.0
    assert caps.loc["hab_par_l_01_macro", "housing"] == 10000.0
    assert caps.loc["hab_ter_s_01_macro", "housing"] == 2500.0
    assert caps.loc["landmarks_arg_antigonespire_01_macro", "housing"] == 20000.0
    # the mod touches CAPACITY only: the employment-target column (E-124) and
    # every non-habitat row are untouched
    assert caps.loc["prod_gen_energycells_01_macro", "workers"] == 200.0
    assert pd.isna(caps.loc["hab_arg_s_01_macro", "workers"])
    assert list(out.modcaps.columns) == _CAP_COLS
    assert len(out.modcaps) == len(_STOCK)


def test_patch_is_a_copy_leaving_the_bundled_data_untouched():
    ref = _ref()
    before = ref.modcaps.copy()
    modpatch.patch_reference(_save(_MOD), ref)
    pd.testing.assert_frame_equal(ref.modcaps, before)


def test_defensive_against_missing_modcaps():
    ref = SimpleNamespace(recipes=None)
    assert modpatch.apply_modcaps(ref, modpatch.KNOWN_MODS) is ref
    empty = SimpleNamespace(modcaps=pd.DataFrame(columns=_CAP_COLS))
    assert modpatch.apply_modcaps(empty, modpatch.KNOWN_MODS) is empty


# --- the registry against the installed mod -------------------------------

def _mod_dir():
    from x4analyzer.config import Config
    game = Config().game_dir
    if game is None:
        return None
    d = game / "extensions" / "nd_habitat_cap_boost"
    return d if d.is_dir() else None


@pytest.mark.skipif(_mod_dir() is None,
                    reason="nd_habitat_cap_boost not installed")
def test_registry_matches_the_installed_mod_files():
    """The hard-coded overrides equal what the mod's own XML says.

    This is the provenance check: modpatch's numbers were READ from the packed
    files, and this fails if the mod is updated with different values.
    """
    from x4analyzer.config import Config
    from x4analyzer.gamedata.catalog import GameFiles

    game = Config().game_dir
    dlcs = sorted(d.name for d in (game / "extensions").iterdir()
                  if d.name.startswith("ego_dlc_"))
    gf = GameFiles(game, dlcs + ["nd_habitat_cap_boost"])

    from_files = {}
    for path in gf.glob(r"extensions/nd_habitat_cap_boost/"):
        ops = macro_attr_diffs(etree.fromstring(gf.read_bytes(path)))
        cap = ops.get(("workforce", "capacity"))
        if cap is not None:
            from_files[path.rsplit("/", 1)[-1][:-4].lower()] = float(cap)

    mod = next(m for m in modpatch.KNOWN_MODS if m.mod_id == "ws_3737446888")
    registry = {o.macro: o.value for o in mod.modcaps if o.field == "housing"}
    assert registry == from_files
