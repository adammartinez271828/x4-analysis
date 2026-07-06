"""Reference game data: the CSVs written by `extract-gamedata`.

Faction handling: the analysis keys everything on the save's owner ids
("argon", "boron", ...). Display names and short codes come from the game
data; colours keep the R script's hand-picked palette for the original
factions (chosen for map readability) and fall back to game colours for
factions added since, then grey.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .textdb import TextDB

# R script palette (X4SaveGameAnalysis.R lines 117-132), keyed by owner id.
_R_COLOURS = {
    "player": "#33f23a", "argon": "#0450f2", "antigone": "#4c91d3",
    "teladi": "#a2b927", "ministry": "#8eb48c", "holyorder": "#f26ca5",
    "paranid": "#7a03f2", "alliance": "#aa37c2", "hatikvah": "#1beaf0",
    "scaleplate": "#7e7732", "split": "#fc691a", "freesplit": "#f19600",
    "fallensplit": "#ff4848", "xenon": "#c10200", "khaak": "#ffb6c1",
    "pioneers": "#39ad9b", "buccaneers": "#5500f4", "scavenger": "#5683a3",
    "terran": "#bdd2fb", "loanshark": "#988397", "yaki": "#fe8ffa",
    "ownerless": "#808080",
}
# R three-letter codes for owners whose game shortname differs or is absent
_R_SHORT = {"player": "PLA", "ownerless": "NIL"}

OTHER_FACTION = "OTH"
SHIP_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]


@dataclass
class RefData:
    factions: pd.DataFrame
    wares: pd.DataFrame
    clusters: pd.DataFrame
    sectors: pd.DataFrame
    ships: pd.DataFrame
    modules: pd.DataFrame    # production modules: macro, ware, method, ...
    recipes: pd.DataFrame    # ware production recipes (long: one row/input)
    modcaps: pd.DataFrame    # module housing/workers/cargo capacities
    textdb: TextDB

    # owner id -> short code / display name / colour
    faction_short: dict
    faction_name: dict
    faction_colour: dict
    ware_name: dict          # ware id -> display name
    economy_wares: list      # ordered commodity display names (factor levels)

    def short(self, owner: str) -> str:
        return self.faction_short.get(owner, OTHER_FACTION)

    def name_of_short(self, short: str) -> str:
        for owner, s in self.faction_short.items():
            if s == short:
                return self.faction_name.get(owner, short)
        return "Other"

    def colour_of_short(self, short: str) -> str:
        for owner, s in self.faction_short.items():
            if s == short:
                return self.faction_colour.get(owner, "#808080")
        return "#808080"

    def resolve_name(self, name: str) -> str:
        """Resolve {page,id} text refs in savegame names (custom names may
        embed them; story stations are entirely refs)."""
        if "{" in name:
            return self.textdb.resolve(name)
        return name


def load_refdata(data_dir: Path) -> RefData:
    """Load reference CSVs. Files in `data_dir` (the writable user data dir,
    populated by extract-gamedata) override the copies shipped inside the
    package, so uvx/wheel installs work out of the box."""
    from .config import PACKAGE_DATA

    def _path(name: str) -> Path:
        user = data_dir / name
        return user if user.exists() else PACKAGE_DATA / name

    factions = pd.read_csv(_path("factions.csv"), dtype=str).fillna("")
    wares = pd.read_csv(_path("wares.csv"), dtype=str).fillna("")
    clusters = pd.read_csv(_path("clusters.csv"))
    sectors = pd.read_csv(_path("sectors.csv"))
    ships = pd.read_csv(_path("ships.csv"))
    textdb = TextDB.from_csv(_path("textdb.csv.gz"))

    def _optional(name: str, cols: list[str]) -> pd.DataFrame:
        path = _path(name)
        if path.exists():
            return pd.read_csv(path)
        return pd.DataFrame(columns=cols)

    modules = _optional("modules.csv",
                        ["macro", "name", "ware", "method", "scale",
                         "workforce", "source"])
    recipes = _optional("recipes.csv",
                        ["ware", "method", "time", "amount", "input_ware",
                         "input_amount"])
    modcaps = _optional("modcaps.csv",
                        ["macro", "class", "housing", "workers", "cargo_max",
                         "cargo_tags"])

    faction_short: dict[str, str] = {}
    faction_name: dict[str, str] = {}
    faction_colour: dict[str, str] = {}
    for row in factions.itertuples():
        owner = row.id
        short = _R_SHORT.get(owner) or (row.shortname or owner[:3]).upper()
        faction_short[owner] = short
        faction_name[owner] = row.name or owner
        faction_colour[owner] = _R_COLOURS.get(owner) or row.colour or "#808080"
    # "ownerless" isn't in factions.xml but is a sector owner in saves
    faction_short.setdefault("ownerless", "NIL")
    faction_name.setdefault("ownerless", "Ownerless")
    faction_colour.setdefault("ownerless", "#808080")

    ware_name = dict(zip(wares["id"], wares["name"]))
    econ = wares[wares["tags"].str.contains("economy", na=False)]
    economy_wares = sorted(n for n in econ["name"] if n)

    ships = ships.copy()
    ships["macro"] = ships["macro"].str.lower()

    return RefData(
        factions=factions, wares=wares, clusters=clusters, sectors=sectors,
        ships=ships, modules=modules, recipes=recipes,
        modcaps=modcaps, textdb=textdb,
        faction_short=faction_short, faction_name=faction_name,
        faction_colour=faction_colour, ware_name=ware_name,
        economy_wares=economy_wares,
    )
