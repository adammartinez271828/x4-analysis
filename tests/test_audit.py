"""Empire audit helpers."""

from x4analyzer.viz.audit import hours_to_full


def test_hours_to_full_filling():
    # 1000 m³ capacity, 800 used, +100 m³/h net -> 2h of room left
    assert hours_to_full(1000.0, 800.0, 100.0) == 2.0


def test_hours_to_full_not_filling():
    # net production zero or negative: the class is not filling
    assert hours_to_full(1000.0, 900.0, 0.0) is None
    assert hours_to_full(1000.0, 900.0, -50.0) is None


def test_hours_to_full_already_full():
    assert hours_to_full(1000.0, 1000.0, 100.0) == 0.0
    assert hours_to_full(1000.0, 1200.0, 100.0) == 0.0
    # full wins over "not filling" — no room left either way
    assert hours_to_full(1000.0, 1000.0, -5.0) == 0.0
