"""The storage model against real in-game readings.

Every number here was read off the station UI in game by the player (or, where
marked `derived`, inferred from the station's own buy offers — a lower bound
only). The fixture carries each station's model INPUTS alongside, so this runs
without a savegame.

The point of this file is to make model changes measurable: a candidate that
fixes one station must not silently break another. Run
`python -m tests.readings` for the full scoreboard.
"""
import pytest

from readings import load, model_for, report, score

# Baseline as of 2026-07-28, after the <production><efficiency> work.
# RAISE THIS as the model improves; it must never fall.
BASELINE_INGAME = 27

# Stations the model reproduces exactly. These are regression locks — a change
# that breaks one of these is a real regression, not a trade-off.
EXACT_STATIONS = ("MAL-475", "TPF-229")


def test_fixture_is_self_consistent():
    doc = load()
    assert doc["observed"], "no readings recorded"
    for code in doc["observed"]:
        assert code in doc["stations"], f"{code} has readings but no inputs"
        assert doc["stations"][code]["modules"], f"{code} has no built modules"


@pytest.mark.parametrize("code", EXACT_STATIONS)
def test_stations_the_model_gets_right_stay_right(code):
    doc = load()
    got = model_for(doc, code)
    obs = doc["observed"][code]
    bad = []
    for kind, idx in (("alloc", 0), ("rate", 1)):
        for ware, (value, source, _note) in obs[kind].items():
            if source != "ingame":
                continue
            pair = got.get(ware)
            assert pair is not None, f"{code}: model produced no row for {ware}"
            err = pair[idx] / value - 1
            if abs(err) > 0.01:
                bad.append(f"{ware} {kind}: {pair[idx]:,.0f} vs {value:,.0f} "
                           f"({err:+.1%})")
    assert not bad, f"{code} regressed:\n  " + "\n  ".join(bad)


def test_overall_score_does_not_regress():
    _rows, s = score()
    assert s["ingame_pass"] >= BASELINE_INGAME, (
        f"in-game readings matched dropped to {s['ingame_pass']}/{s['ingame']} "
        f"(baseline {BASELINE_INGAME}). Full scoreboard:\n\n{report()}")


def test_derived_readings_are_treated_as_a_lower_bound():
    # MAL-475 is the counter-example: its consumers are still under
    # construction, so it bids far below its real allocation. A model value
    # ABOVE a derived reading must not count as an error.
    rows, _ = score()
    derived = [r for r in rows if r[4] == "derived"]
    assert derived, "fixture lost its derived readings"
    assert any(r[6] is not None and r[6] > 0.01 and r[7] for r in rows
               if r[4] == "derived") or all(
        r[7] or (r[6] is not None and r[6] < 0) for r in derived)
