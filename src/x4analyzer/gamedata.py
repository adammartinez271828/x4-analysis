"""Regenerate reference data CSVs from the installed game (base + DLC).

Outputs into the data directory:
    factions.csv   id, shortname, name, primaryrace, colour, source
    wares.csv      id, name, group, transport, volume, tags, price_avg, source
    clusters.csv   macro, x, y, z, name, description, source
    sectors.csv    cluster, macro, x, y, z, name, source
    ships.csv      macro, model, class, race, purpose, hull, mass, cargo,
                   crew, price, source
    textdb.csv.gz  full page/id/text dump for resolving names in savegames
"""

from __future__ import annotations

import csv
from pathlib import Path

from lxml import etree

from .catalog import GameFiles
from .cli import log
from .config import Config
from .textdb import TextDB

_PARSER = etree.XMLParser(recover=True, huge_tree=True)


def _parse(gf: GameFiles, path: str) -> etree._Element | None:
    try:
        return etree.fromstring(gf.read_bytes(path), _PARSER)
    except FileNotFoundError:
        return None


def _variant_paths(gf: GameFiles, relpath: str) -> list[str]:
    """A base-game file plus each extension's version of it, in load order."""
    paths = [relpath] if relpath in gf else []
    for ext in gf.extensions:
        p = f"extensions/{ext}/{relpath}"
        if p in gf:
            paths.append(p)
    return paths


def _iter_merged(gf: GameFiles, relpath: str, tag: str):
    """Yield (element, source_extension) for `tag` across base + extension
    versions of a library file. Extension files are usually `<diff>` patches;
    scanning descendants for the tag handles both forms."""
    for path in _variant_paths(gf, relpath):
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for elem in root.iter(tag):
            yield elem, source


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    log(f"  wrote {path.name}: {len(rows)} rows")


# --------------------------------------------------------------------------

def load_textdb(gf: GameFiles) -> TextDB:
    db = TextDB()
    for path in _variant_paths(gf, "t/0001-l044.xml"):
        db.load_xml(gf.read_bytes(path))
    return db


def extract_factions(gf: GameFiles, tdb: TextDB) -> list[list]:
    # colour chain: faction <color ref=X> -> colors.xml <mapping id=X ref=Y>
    # -> <color id=Y r= g= b=>
    colours: dict[str, str] = {}
    mappings: dict[str, str] = {}
    for elem, _ in _iter_merged(gf, "libraries/colors.xml", "color"):
        cid = elem.get("id")
        if cid and elem.get("r") is not None:
            r, g, b = (round(float(elem.get(c, "0"))) for c in "rgb")
            colours[cid] = f"#{r:02x}{g:02x}{b:02x}"
    for elem, _ in _iter_merged(gf, "libraries/colors.xml", "mapping"):
        if elem.get("id") and elem.get("ref"):
            mappings[elem.get("id")] = elem.get("ref")

    rows = {}
    for f, source in _iter_merged(gf, "libraries/factions.xml", "faction"):
        fid = f.get("id")
        if not fid or f.get("name") is None:
            continue
        colour_ref = None
        c = f.find("color")
        if c is not None:
            colour_ref = c.get("ref")
        colour = colours.get(mappings.get(colour_ref, ""), "")
        rows[fid] = [
            fid,
            tdb.resolve(f.get("shortname", "")),
            tdb.resolve(f.get("name", "")),
            f.get("primaryrace", ""),
            colour,
            source,
        ]
    return list(rows.values())


def extract_wares(gf: GameFiles, tdb: TextDB) -> list[list]:
    rows = {}
    for w, source in _iter_merged(gf, "libraries/wares.xml", "ware"):
        wid = w.get("id")
        if not wid or w.getparent() is None:
            continue
        price = w.find("price")
        rows[wid] = [
            wid,
            tdb.resolve(w.get("name", "")),
            w.get("group", ""),
            w.get("transport", ""),
            w.get("volume", ""),
            w.get("tags", ""),
            price.get("average", "") if price is not None else "",
            source,
        ]
    return list(rows.values())


def _map_names(gf: GameFiles, tdb: TextDB) -> dict[str, tuple[str, str]]:
    """macro (lowercased) -> (name, description) from mapdefaults datasets."""
    names: dict[str, tuple[str, str]] = {}
    for ds, _ in _iter_merged(gf, "libraries/mapdefaults.xml", "dataset"):
        macro = (ds.get("macro") or "").lower()
        ident = ds.find("properties/identification")
        if not macro or ident is None:
            continue
        names[macro] = (
            tdb.resolve(ident.get("name", "")),
            tdb.resolve(ident.get("description", "")),
        )
    return names


def extract_map(gf: GameFiles, tdb: TextDB) -> tuple[list[list], list[list]]:
    names = _map_names(gf, tdb)

    # cluster galaxy positions: base galaxy.xml + DLC diff patches
    clusters: dict[str, list] = {}
    for path in _variant_paths(gf, "maps/xu_ep2_universe/galaxy.xml"):
        root = _parse(gf, path)
        source = gf.source_of(path)
        for conn in root.iter("connection"):
            if conn.get("ref") != "clusters":
                continue
            macro_el = conn.find("macro")
            if macro_el is None or not macro_el.get("ref"):
                continue
            macro = macro_el.get("ref").lower()
            pos = conn.find("offset/position")
            x = float(pos.get("x", 0)) if pos is not None else 0.0
            y = float(pos.get("y", 0)) if pos is not None else 0.0
            z = float(pos.get("z", 0)) if pos is not None else 0.0
            name, descr = names.get(macro, (macro, ""))
            clusters[macro] = [macro, x, y, z, name, descr, source]

    # sector membership + in-cluster offsets: clusters.xml variants
    sectors: dict[str, list] = {}
    cluster_files = [
        p for p in gf.glob(
            r"(extensions/[^/]+/)?maps/xu_ep2_universe/[^/]*clusters\.xml$"
        )
    ]
    for path in cluster_files:
        root = _parse(gf, path)
        source = gf.source_of(path)
        for macro_el in root.iter("macro"):
            if macro_el.get("class") != "cluster":
                continue
            cluster_macro = (macro_el.get("name") or "").lower()
            for conn in macro_el.iter("connection"):
                if conn.get("ref") != "sectors":
                    continue
                sec = conn.find("macro")
                if sec is None or not sec.get("ref"):
                    continue
                smacro = sec.get("ref").lower()
                pos = conn.find("offset/position")
                x = float(pos.get("x", 0)) if pos is not None else 0.0
                y = float(pos.get("y", 0)) if pos is not None else 0.0
                z = float(pos.get("z", 0)) if pos is not None else 0.0
                name, _descr = names.get(smacro, (smacro, ""))
                sectors[smacro] = [cluster_macro, smacro, x, y, z, name, source]

    return list(clusters.values()), list(sectors.values())


_SIZE_BY_CLASS = {
    "ship_xs": "XS", "ship_s": "S", "ship_m": "M",
    "ship_l": "L", "ship_xl": "XL",
}


def extract_modules(gf: GameFiles, tdb: TextDB) -> list[list]:
    """Production/processing station modules, one row per (macro, ware,
    method) the module can run.

    Queue forms: `<queue ware= method=/>` (single) or `<queue><item ware=
    method=/>...</queue>` (multi-ware, e.g. Scrap Recyclers). Processing
    modules (Scrap Processors) instead declare `<products><ware ware=
    amount=/>` and run the ware's "processing" recipe scaled by amount.
    """
    rows: list[list] = []
    seen: set[tuple] = set()
    paths = gf.glob(
        r"(extensions/[^/]+/)?assets/structures/.*/macros/.*\.xml$"
    )
    for path in paths:
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for m in root.iter("macro"):
            macro = (m.get("name") or "").lower()
            if not macro:
                continue
            prod = m.find("properties/production")
            products = m.find("properties/products")

            entries: list[tuple[str, str, float]] = []  # (ware, method, scale)
            if prod is not None:
                for q in prod.findall("queue"):
                    if q.get("ware"):
                        entries.append((q.get("ware"),
                                        q.get("method", "default"), 1.0))
                    for item in q.findall("item"):
                        if item.get("ware"):
                            entries.append((item.get("ware"),
                                            item.get("method", "default"), 1.0))
                if not entries and prod.get("wares"):
                    entries = [(w, "default", 1.0)
                               for w in prod.get("wares", "").split()]
            elif products is not None:
                for pw in products.findall("ware"):
                    if pw.get("ware"):
                        entries.append((pw.get("ware"), "processing",
                                        float(pw.get("amount", 1) or 1)))
            if not entries:
                continue

            ident = m.find("properties/identification")
            wf = m.find("properties/workforce")
            name = tdb.resolve(ident.get("name", "")) if ident is not None \
                else macro
            for ware, method, scale in entries:
                key = (macro, ware, method)
                if key in seen:
                    continue
                seen.add(key)
                rows.append([macro, name or macro, ware, method, scale,
                             wf.get("max", "") if wf is not None else "",
                             source])
    return rows


def extract_recipes(gf: GameFiles) -> list[list]:
    """Ware production recipes, one row per (ware, method, input)."""
    import re as _re

    rows: list[tuple] = []

    def add_production(wid: str, prod) -> None:
        time = prod.get("time", "")
        amount = prod.get("amount", "")
        method = prod.get("method", "default")
        inputs = prod.findall("primary/ware")
        if not inputs:
            rows.append((wid, method, time, amount, "", ""))
        for inp in inputs:
            rows.append((wid, method, time, amount,
                         inp.get("ware", ""), inp.get("amount", "")))

    for w, _source in _iter_merged(gf, "libraries/wares.xml", "ware"):
        wid = w.get("id")
        if wid and w.getparent() is not None and w.getparent().tag != "primary":
            for prod in w.findall("production"):
                add_production(wid, prod)

    # DLC diffs also add production methods INSIDE existing wares, e.g.
    # <add sel="//ware[@id='workunit_busy']"><production method="boron">...
    ware_sel = _re.compile(r"ware\[@id='([^']+)'\]")
    for path in _variant_paths(gf, "libraries/wares.xml"):
        if "extensions/" not in path:
            continue
        root = _parse(gf, path)
        if root is None:
            continue
        for add in root.iter("add"):
            m = ware_sel.search(add.get("sel", ""))
            if not m:
                continue
            for prod in add.iter("production"):
                add_production(m.group(1), prod)

    return [list(r) for r in dict.fromkeys(rows)]


def extract_ships(gf: GameFiles, tdb: TextDB, prices: dict[str, str]) -> list[list]:
    rows = {}
    paths = gf.glob(
        r"(extensions/[^/]+/)?assets/units/size_[a-z]+/macros/ship_.*\.xml$"
    )
    for path in paths:
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for m in root.iter("macro"):
            cls = m.get("class", "")
            macro = (m.get("name") or "").lower()
            if cls not in _SIZE_BY_CLASS or not macro:
                continue
            ident = m.find("properties/identification")
            hull = m.find("properties/hull")
            physics = m.find("properties/physics")
            cargo = m.find("properties/cargo")
            people = m.find("properties/people")
            purpose = m.find("properties/purpose")
            name = tdb.resolve(ident.get("name", "")) if ident is not None else macro
            rows[macro] = [
                macro,
                name or macro,
                _SIZE_BY_CLASS[cls],
                ident.get("makerrace", "") if ident is not None else "",
                purpose.get("primary", "") if purpose is not None else "",
                hull.get("max", "") if hull is not None else "",
                physics.get("mass", "") if physics is not None else "",
                cargo.get("max", "") if cargo is not None else "",
                people.get("capacity", "") if people is not None else "",
                prices.get(macro.removesuffix("_macro"), ""),
                source,
            ]
    return list(rows.values())


def extract_gamedata(cfg: Config, include_mods: bool = False) -> int:
    extensions = None
    if include_mods:
        ext_root = cfg.game_dir / "extensions"
        official = sorted(
            d.name for d in ext_root.iterdir()
            if d.is_dir() and d.name.startswith("ego_dlc_")
        )
        mods = sorted(
            d.name for d in ext_root.iterdir()
            if d.is_dir() and not d.name.startswith("ego_dlc_")
        )
        extensions = official + mods

    log("Indexing game catalogs:", cfg.game_dir)
    gf = GameFiles(cfg.game_dir, extensions)
    log(f"  {len(gf._index)} files, extensions: {', '.join(gf.extensions)}")

    log("Loading localization (t-files)")
    tdb = load_textdb(gf)
    n = tdb.dump_csv(cfg.data_dir / "textdb.csv.gz") if _ensure(cfg.data_dir) else 0
    log(f"  wrote textdb.csv.gz: {n} entries")

    log("Extracting factions")
    _write_csv(
        cfg.data_dir / "factions.csv",
        ["id", "shortname", "name", "primaryrace", "colour", "source"],
        extract_factions(gf, tdb),
    )

    log("Extracting wares")
    ware_rows = extract_wares(gf, tdb)
    _write_csv(
        cfg.data_dir / "wares.csv",
        ["id", "name", "group", "transport", "volume", "tags", "price_avg", "source"],
        ware_rows,
    )

    log("Extracting map (clusters, sectors)")
    cluster_rows, sector_rows = extract_map(gf, tdb)
    _write_csv(
        cfg.data_dir / "clusters.csv",
        ["macro", "x", "y", "z", "name", "description", "source"],
        cluster_rows,
    )
    _write_csv(
        cfg.data_dir / "sectors.csv",
        ["cluster", "macro", "x", "y", "z", "name", "source"],
        sector_rows,
    )

    log("Extracting production modules")
    _write_csv(
        cfg.data_dir / "modules.csv",
        ["macro", "name", "ware", "method", "scale", "workforce", "source"],
        extract_modules(gf, tdb),
    )

    log("Extracting production recipes")
    _write_csv(
        cfg.data_dir / "recipes.csv",
        ["ware", "method", "time", "amount", "input_ware", "input_amount"],
        extract_recipes(gf),
    )

    log("Extracting ship models")
    prices = {r[0]: r[6] for r in ware_rows}  # ware id -> price_avg
    _write_csv(
        cfg.data_dir / "ships.csv",
        ["macro", "model", "class", "race", "purpose", "hull", "mass",
         "cargo", "crew", "price", "source"],
        extract_ships(gf, tdb, prices),
    )

    log("Done.")
    return 0


def _ensure(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return True
