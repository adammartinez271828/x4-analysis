"""Replay the in-game station readings through the storage model.

`tests/data/station_readings.json` holds, per station, everything
`analysis.storage.station_storage()` needs (built modules, live production
efficiency, workforce, cargo, offers) plus the reference rows those stations
touch — captured once from a real save — and alongside it the values the player
read **in game**. So the readings can be replayed as a fast unit test with no
savegame present, and a candidate model can be scored against all of them at
once instead of one station at a time.

Reading sources, and why the distinction matters:

* ``ingame``  — read off the station UI. Authoritative.
* ``derived`` — ``allocation = stock + inbound + open buy amount``. This is a
  **lower bound, not an equality**. A station bids only for what it can use, so
  one whose consuming modules are still under construction (MAL-475) or which
  simply is not buying a ware (TPF-229 helium/ore) reads far below its true
  allocation. Scoring must not treat a model value *above* a derived reading as
  an error.

Run ``uv run python tests/readings.py`` for the full scoreboard.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from x4analyzer.analysis.storage import station_storage

DATA = Path(__file__).parent / "data" / "station_readings.json"


def load() -> dict:
    return json.loads(DATA.read_text())


def _ref(doc: dict) -> SimpleNamespace:
    r = doc["reference"]
    return SimpleNamespace(
        wares=pd.DataFrame(r["ware"], columns=["id", "transport", "volume", "tags"]),
        recipes=pd.DataFrame(r["recipe"], columns=[
            "ware", "method", "time", "amount", "input_ware", "input_amount",
            "work_effect"]),
        modules=pd.DataFrame(r["module_ref"],
                             columns=["macro", "ware", "method", "scale"]),
        modcaps=pd.DataFrame(r["module_cap"], columns=[
            "macro", "class", "housing", "workers", "cargo_max", "cargo_tags"]),
        sectors=pd.DataFrame(r["sector_ref"], columns=["macro", "sunlight"]),
    )


def frames_for(doc: dict, codes=None) -> SimpleNamespace:
    """A Frames-alike covering ALL fixture stations at once.

    Deliberately one frame for every station, not one per station: the model
    asks whether *the save* carried `<production>` data at all, so a station
    that happens to have no production blocks (WRC-739) must not look like a
    pre-v27 database. Building it per station made WRC-739 fall back to the
    reconstructed work_effect and miss by 17%.
    """
    codes = list(codes or doc["stations"])
    built, uni, wf, cargo, offers, prod = [], [], [], [], [], []
    for code in codes:
        s = doc["stations"][code]
        sid = s["id"]
        built += [[sid, macro, 1] for macro, n in s["modules"] for _ in range(int(n))]
        uni.append([sid, "station", s["sector_macro"]])
        wf += [[sid, race, amt] for race, amt in s["workforce"]]
        cargo += [[sid, w, a] for w, a in s["cargo"]]
        offers += [[sid, side, w, a, 0.0, fl, None]
                   for side, w, a, fl in s["offers"]]
        prod += [[sid, macro, ware, eff, state, n]
                 for macro, ware, eff, state, n in s["production"]]
    return SimpleNamespace(
        built_modules=pd.DataFrame(built, columns=["id", "macro", "built"]),
        universe=pd.DataFrame(uni, columns=["id", "class", "sector.macro"]),
        workforce_all=pd.DataFrame(wf, columns=["id", "race", "amount"]),
        station_cargo=pd.DataFrame(cargo, columns=["id", "ware", "amount"]),
        trade_offers=pd.DataFrame(offers, columns=[
            "id", "side", "ware", "amount", "price", "flags", "desired"]),
        module_production=pd.DataFrame(prod, columns=[
            "id", "macro", "ware", "efficiency", "state", "n_modules"]),
    )


def model_all(doc: dict, storage_fn=station_storage) -> dict:
    """{station code: {ware: (allocation, throughput)}} in one model run."""
    df = storage_fn(frames_for(doc), _ref(doc))
    by_id = {}
    for r in df.itertuples():
        if r.role in ("output", "input", "food"):
            by_id.setdefault(r.station_id, {})[r.ware] = (r.max_units, r.throughput)
    return {code: by_id.get(s["id"], {}) for code, s in doc["stations"].items()}


def model_for(doc: dict, code: str, storage_fn=station_storage) -> dict:
    """{ware: (allocation, throughput)} as the model computes it."""
    return model_all(doc, storage_fn)[code]


def score(doc: dict | None = None, storage_fn=station_storage, tol: float = 0.01):
    """Compare model to every reading. Returns (rows, summary).

    A ``derived`` allocation reading is a lower bound: the model is only wrong
    if it comes in BELOW it.
    """
    doc = doc or load()
    allm = model_all(doc, storage_fn)
    rows = []
    for code, obs in sorted(doc["observed"].items()):
        got = allm[code]
        for kind in ("alloc", "rate"):
            for ware, (value, source, note) in sorted(obs[kind].items()):
                pair = got.get(ware)
                got_v = None if pair is None else pair[0 if kind == "alloc" else 1]
                if got_v is None:
                    rows.append((code, kind, ware, value, source, None, None, False))
                    continue
                err = got_v / value - 1 if value else float("inf")
                ok = (abs(err) <= tol if source == "ingame"
                      else err >= -tol)          # derived = lower bound
                rows.append((code, kind, ware, value, source, got_v, err, ok))
    ing = [r for r in rows if r[4] == "ingame"]
    summary = {
        "total": len(rows), "pass": sum(1 for r in rows if r[7]),
        "ingame": len(ing), "ingame_pass": sum(1 for r in ing if r[7]),
    }
    return rows, summary


def report(storage_fn=station_storage, tol: float = 0.01) -> str:
    rows, s = score(storage_fn=storage_fn, tol=tol)
    out = [f"{'station':9s} {'kind':5s} {'ware':22s} {'observed':>12} "
           f"{'model':>12} {'err':>8}  src"]
    last = None
    for code, kind, ware, val, src, got, err, ok in rows:
        if code != last:
            out.append("")
            last = code
        mark = "  " if ok else "!!"
        out.append(f"{mark}{code:7s} {kind:5s} {ware[:22]:22s} {val:12,.0f} "
                   f"{(f'{got:,.0f}' if got is not None else '-'):>12} "
                   f"{(f'{err:+.1%}' if err is not None else '-'):>8}  {src}")
    out.append("")
    out.append(f"in-game readings matched within {tol:.0%}: "
               f"{s['ingame_pass']}/{s['ingame']}   "
               f"all readings (derived scored as a lower bound): "
               f"{s['pass']}/{s['total']}")
    return "\n".join(out)


if __name__ == "__main__":  # pragma: no cover
    print(report())
