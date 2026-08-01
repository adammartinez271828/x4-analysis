"""Reference-CSV loading (gamedata/refdata.py) — the user-dir override rules.

A file in the user data dir (written by extract-gamedata) overrides the copy
bundled in the package. An override written by an OLDER release can be missing
columns this version needs; it is then ignored with a warning rather than
served (a stale recipes.csv without `work_effect` crashed 1.4.0 at startup).
"""
import shutil

import pandas as pd

from x4analyzer.config import PACKAGE_DATA
from x4analyzer.gamedata.refdata import load_refdata


def _user_dir(tmp_path, name, frame):
    """A user data dir holding one override CSV plus the files the loader
    always needs (copied from the packaged set)."""
    d = tmp_path / "userdata"
    d.mkdir()
    frame.to_csv(d / name, index=False)
    return d


def _packaged(name):
    return pd.read_csv(PACKAGE_DATA / name)


def test_stale_override_missing_a_column_loses_to_the_packaged_copy(tmp_path):
    stale = _packaged("recipes.csv").drop(columns=["work_effect"]).head(3)
    d = _user_dir(tmp_path, "recipes.csv", stale)
    msgs = []
    ref = load_refdata(d, log=lambda *p: msgs.append(" ".join(map(str, p))))

    assert "work_effect" in ref.recipes.columns
    assert len(ref.recipes) == len(_packaged("recipes.csv"))    # packaged won
    assert any("recipes.csv" in m and "work_effect" in m
               and "extract-gamedata" in m for m in msgs), msgs


def test_stale_wares_override_also_loses(tmp_path):
    # wares.csv gained price_min/price_max in the same release cycle
    stale = _packaged("wares.csv").drop(columns=["price_min", "price_max"])
    d = _user_dir(tmp_path, "wares.csv", stale.head(5))
    msgs = []
    ref = load_refdata(d, log=lambda *p: msgs.append(" ".join(map(str, p))))

    assert {"price_min", "price_max"} <= set(ref.wares.columns)
    assert len(ref.wares) == len(_packaged("wares.csv"))
    assert any("wares.csv" in m for m in msgs), msgs


def test_a_current_override_still_wins(tmp_path):
    mine = _packaged("recipes.csv").head(4)
    d = _user_dir(tmp_path, "recipes.csv", mine)
    msgs = []
    ref = load_refdata(d, log=lambda *p: msgs.append(" ".join(map(str, p))))

    assert len(ref.recipes) == 4
    assert msgs == []


def test_extra_columns_in_the_override_are_fine(tmp_path):
    mine = _packaged("recipes.csv").head(4)
    mine["future_column"] = 1
    d = _user_dir(tmp_path, "recipes.csv", mine)
    msgs = []
    ref = load_refdata(d, log=lambda *p: msgs.append(" ".join(map(str, p))))

    assert len(ref.recipes) == 4
    assert "future_column" in ref.recipes.columns
    assert msgs == []


def test_a_gzipped_override_is_header_checked_too(tmp_path):
    d = tmp_path / "userdata"
    d.mkdir()
    shutil.copy(PACKAGE_DATA / "textdb.csv.gz", d / "textdb.csv.gz")
    msgs = []
    load_refdata(d, log=lambda *p: msgs.append(" ".join(map(str, p))))
    assert msgs == []       # an identical copy is not stale
