"""`x4-analyzer find` — print where matched objects are, with real names.

The community script this replaces hardcoded a sector-macro -> name table
(and shipped it with two sectors swapped). Here the names come from
sectors.csv / wares.csv, which extract-gamedata regenerates from the
installed game, so DLC and mod content resolve on their own.
"""

from __future__ import annotations

from ..config import Config
from ..gamedata.refdata import load_refdata
from .landmarks import ERLKING_VAULTS, find_landmarks


def run_find(cfg: Config, macro: str | None = None) -> int:
    save_file = cfg.find_savegame()
    print(f"save: {save_file}")

    hits = find_landmarks(save_file, macro or ERLKING_VAULTS)
    if not hits:
        print("no matching objects found")
        return 0

    ref = load_refdata(cfg.data_dir)
    sector_name = dict(zip(ref.sectors["macro"].str.lower(), ref.sectors["name"]))
    ware_name = dict(zip(ref.wares["id"], ref.wares["name"]))

    hits.sort(key=lambda h: (h.source_entry or h.macro))
    for h in hits:
        sector = sector_name.get(h.sector_macro, h.sector_macro or "?")
        x, y, z = h.km
        print(f"\n{sector}  ({h.code or h.id})")
        print(f"  position   x {x:9.1f} km   y {y:9.1f} km   z {z:9.1f} km")
        if h.source_entry:
            print(f"  entry      {h.source_entry}")
        if h.blueprints:
            names = ", ".join(ware_name.get(b, b) for b in h.blueprints)
            print(f"  contains   {names}")
        else:
            print("  contains   - (already collected)")
    print()
    return 0
