"""Regenerate reference data CSVs from the installed game (base + DLC).

Outputs into the data directory:
    factions.csv   id, shortname, name, primaryrace, colour, source
    wares.csv      id, name, group, transport, volume, tags, price_avg, source
    clusters.csv   macro, x, y, z, name, description, source
    sectors.csv    cluster, macro, x, y, z, name, sunlight, highway, source
    ships.csv      macro, model, class, race, purpose, hull, mass, cargo,
                   cargo_tags, crew, price, drag_forward, source
    engines.csv    macro, size, type, mk, forward, travel_thrust
    highways.csv   sector, points (local-highway spline "x z;x z;..." track)
    textdb.csv.gz  full page/id/text dump for resolving names in savegames
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from lxml import etree

from .catalog import GameFiles
from ..cli import log
from ..config import Config
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
        comp = w.find("component")
        rows[wid] = [
            wid,
            tdb.resolve(w.get("name", "")),
            w.get("group", ""),
            w.get("transport", ""),
            w.get("volume", ""),
            w.get("tags", ""),
            price.get("average", "") if price is not None else "",
            (comp.get("ref", "") if comp is not None else "").lower(),
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

    # per-sector sunlight multiplier from mapdefaults.xml (dataset
    # properties/area sunlight=...; base game first, DLC datasets later —
    # they only add their own sectors but let them win on overlap)
    sunlight: dict[str, float] = {}
    md_paths = sorted(gf.glob(r"(extensions/[^/]+/)?libraries/mapdefaults\.xml$"),
                      key=lambda p: p.startswith("extensions"))
    for path in md_paths:
        root = _parse(gf, path)
        if root is None:
            continue
        for ds in root.iter("dataset"):
            macro = (ds.get("macro") or "").lower()
            area = ds.find("properties/area")
            if macro and area is not None and area.get("sunlight"):
                try:
                    sunlight[macro] = float(area.get("sunlight"))
                except ValueError:
                    pass

    # local (ring) highways: the sector macro carries connections
    # ref="zonehighways" (superhighways between sectors are a different
    # ref and live in gates.csv). The macro they reference is defined in
    # zonehighways.xml with a splinetube boundary — the actual curved
    # track — in the macro's local frame; the connection's offset places
    # it in the sector (no rotations occur in any game/DLC file). Points
    # are packed as "x z;x z;..." per row. Fallback when a mod's macro
    # has no spline: the entrypoint/exitpoint ZONE positions from the
    # same sector macro give a straight two-point segment.
    splines: dict[str, list] = {}
    for path in gf.glob(r"(extensions/[^/]+/)?maps/xu_ep2_universe/"
                        r"[^/]*zonehighways\.xml$"):
        root = _parse(gf, path)
        if root is None:
            continue
        for m in root.iter("macro"):
            if m.get("class") != "highway" or not m.get("name"):
                continue
            ctrl = [(float(sp.get("x", 0)), float(sp.get("z", 0)),
                     float(sp.get("tx", 0)), float(sp.get("tz", 0)),
                     float(sp.get("inlength", 0)),
                     float(sp.get("outlength", 0)))
                    for sp in m.iter("splineposition")]
            if len(ctrl) >= 2:
                splines[m.get("name").lower()] = _sample_spline(ctrl)

    highway_secs: set[str] = set()
    highway_rows: list[list] = []
    for path in gf.glob(r"(extensions/[^/]+/)?maps/xu_ep2_universe/"
                        r"[^/]*sectors\.xml$"):
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for macro_el in root.iter("macro"):
            if macro_el.get("class") != "sector":
                continue
            smacro = (macro_el.get("name") or "").lower()
            zone_pos: dict[str, tuple] = {}
            for conn in macro_el.iter("connection"):
                if conn.get("ref") != "zones" or not conn.get("name"):
                    continue
                pos = conn.find("offset/position")
                if pos is not None:
                    zone_pos[conn.get("name")] = (
                        float(pos.get("x", 0)), float(pos.get("z", 0)))
            for conn in macro_el.iter("connection"):
                if conn.get("ref") != "zonehighways":
                    continue
                highway_secs.add(smacro)
                pos = conn.find("offset/position")
                ox = float(pos.get("x", 0)) if pos is not None else 0.0
                oz = float(pos.get("z", 0)) if pos is not None else 0.0
                ref_el = conn.find("macro")
                hmacro = (ref_el.get("ref") or "").lower() \
                    if ref_el is not None else ""
                pts = [(ox + x, oz + z) for x, z in splines.get(hmacro, ())]
                if not pts:
                    ep = {}
                    for c in conn.iter("connection"):
                        if c.get("ref") in ("entrypoint", "exitpoint"):
                            r2 = c.find("macro")
                            zname = (r2.get("path") or "").split("/")[-1] \
                                if r2 is not None else ""
                            ep[c.get("ref")] = zone_pos.get(zname)
                    if ep.get("entrypoint") and ep.get("exitpoint"):
                        pts = [ep["entrypoint"], ep["exitpoint"]]
                if pts:
                    highway_rows.append([smacro, ";".join(
                        f"{x:.1f} {z:.1f}" for x, z in pts), source])

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
                sun = sunlight.get(smacro, sunlight.get(cluster_macro, 1.0))
                sectors[smacro] = [cluster_macro, smacro, x, y, z, name, sun,
                                   int(smacro in highway_secs), source]

    return list(clusters.values()), list(sectors.values()), highway_rows


_SPLINE_SAMPLES = 16  # evaluated points per control-point span


def _sample_spline(ctrl: list[tuple]) -> list[tuple[float, float]]:
    """Evaluate the game's highway spline into a polyline. Each control
    point carries a unit tangent plus in/out lengths; the lengths run
    ~chord/3, which identifies them as BEZIER HANDLE lengths (a Hermite
    derivative would be ~the full chord): each span is the cubic Bezier
    P0, P0 + T0*outlength, P1 - T1*inlength, P1. Consecutive spans share
    the joint tangent, so the sampled track is smooth by construction;
    straight tracks stay straight."""
    out = [(ctrl[0][0], ctrl[0][1])]
    for (x0, z0, tx0, tz0, _il0, ol0), (x1, z1, tx1, tz1, il1, _ol1) \
            in zip(ctrl, ctrl[1:]):
        c1 = (x0 + tx0 * ol0, z0 + tz0 * ol0)
        c2 = (x1 - tx1 * il1, z1 - tz1 * il1)
        for i in range(1, _SPLINE_SAMPLES + 1):
            t = i / _SPLINE_SAMPLES
            u = 1 - t
            out.append((
                u**3 * x0 + 3 * u**2 * t * c1[0]
                + 3 * u * t**2 * c2[0] + t**3 * x1,
                u**3 * z0 + 3 * u**2 * t * c1[1]
                + 3 * u * t**2 * c2[1] + t**3 * z1,
            ))
    return out


_SECTOR_IN_PATH = re.compile(r"/([A-Za-z0-9_]*_Sector\d+)_connection/",
                             re.IGNORECASE)


def extract_gates(gf: GameFiles) -> list[list]:
    """Sector pairs joined by a jump gate or accelerator.

    Inter-cluster links come from galaxy.xml: its ref="destination"
    connections carry both endpoints' zone paths, which embed the sector
    connection names (Cluster_01_Sector001_connection ->
    cluster_01_sector001_macro). Intra-cluster links (trans-orbital
    accelerators, e.g. Earth <-> The Moon) are NOT in galaxy.xml: each
    cluster macro declares them as ref="sechighways" connections whose
    entrypoint/exitpoint zone paths embed the sector connection names the
    same way.

    The endpoint paths also name the gate ZONES: their sector-local
    offsets sit in the sector files, and the gate OBJECT's own offset
    within the zone in the zones files — zones span tens of km, so the
    zone centre alone can be 40 km off the spot the in-game map (and the
    highway tracks) use. Each row carries the summed position as
    ax/az/bx/bz (metres; 0/0 when the zone could not be resolved) so the
    map can draw connections where the gates actually sit."""

    # zone MACRO name -> {gate connection name -> (x, z) offset within
    # the zone; "" -> first found}. A single zone can host TWO gates
    # tens of km apart (Pontifex's Claim), so endpoints must match the
    # gate connection named in the galaxy/sechighway path. Jump gates
    # and accelerator props both hang off ref="gates" connections; be
    # liberal and also match props_gates_* macros.
    gate_off: dict[str, dict[str, tuple[float, float]]] = {}
    for path in gf.glob(
            r"(extensions/[^/]+/)?maps/xu_ep2_universe/[^/]*zones\.xml$"):
        root = _parse(gf, path)
        if root is None:
            continue
        for m in root.iter("macro"):
            zname = (m.get("name") or "").lower()
            if m.get("class") != "zone" or not zname:
                continue
            for conn in m.iter("connection"):
                ref_el = conn.find("macro")
                prop = (ref_el.get("ref") or "").lower() \
                    if ref_el is not None else ""
                if conn.get("ref") != "gates" \
                        and not prop.startswith("props_gates"):
                    continue
                pos = conn.find("offset/position")
                if pos is None:
                    continue
                off = (float(pos.get("x") or 0), float(pos.get("z") or 0))
                d = gate_off.setdefault(zname, {})
                d.setdefault("", off)
                if conn.get("name"):
                    d[conn.get("name").lower()] = off

    # zone-connection name -> (zone x, zone z, zone macro name)
    zone_pos: dict[str, tuple] = {}
    for path in gf.glob(
            r"(extensions/[^/]+/)?maps/xu_ep2_universe/[^/]*sectors\.xml$"):
        root = _parse(gf, path)
        if root is None:
            continue
        for conn in root.iter("connection"):
            if conn.get("ref") != "zones":
                continue
            name = (conn.get("name") or "").lower()
            if not name:
                continue
            pos = conn.find("offset/position")
            zx, zz = ((float(pos.get("x") or 0), float(pos.get("z") or 0))
                      if pos is not None else (0.0, 0.0))
            ref_el = conn.find("macro")
            zmacro = (ref_el.get("ref") or "").lower() \
                if ref_el is not None else ""
            zone_pos[name] = (zx, zz, zmacro)

    def sector_of(path: str) -> str:
        m = _SECTOR_IN_PATH.search(path or "")
        return f"{m.group(1).lower()}_macro" if m else ""

    def zone_of(path: str, gate_name: str = "") -> tuple[float, float]:
        """Gate position: zone offset + the named gate's offset inside
        the zone (path segments after the zone usually name the gate
        connection; `gate_name` is the sechighways fallback)."""
        segs = [s.lower() for s in (path or "").split("/")]
        for i, seg in enumerate(segs):
            zp = zone_pos.get(seg)
            if zp is None:
                continue
            zx, zz, zmacro = zp
            gates = gate_off.get(zmacro, {})
            g = None
            for cand in segs[i + 1:] + [gate_name.lower()]:
                if cand and cand in gates:
                    g = gates[cand]
                    break
            if g is None:
                g = gates.get("", (0.0, 0.0))
            return (zx + g[0], zz + g[1])
        return (0.0, 0.0)

    pairs: dict[tuple[str, str], list] = {}

    def add(a: str, b: str, pa: tuple[float, float],
            pb: tuple[float, float], source: str) -> None:
        if a and b and a != b:
            if b < a:
                a, b, pa, pb = b, a, pb, pa
            pairs.setdefault((a, b),
                             [a, b, pa[0], pa[1], pb[0], pb[1], source])

    for path in _variant_paths(gf, "maps/xu_ep2_universe/galaxy.xml"):
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for conn in root.iter("connection"):
            if conn.get("ref") != "destination":
                continue
            macro_el = conn.find("macro")
            if macro_el is None:
                continue
            add(sector_of(conn.get("path")), sector_of(macro_el.get("path")),
                zone_of(conn.get("path")), zone_of(macro_el.get("path")),
                source)

    for path in gf.glob(
            r"(extensions/[^/]+/)?maps/xu_ep2_universe/[^/]*clusters\.xml$"):
        root = _parse(gf, path)
        if root is None:
            continue
        source = gf.source_of(path)
        for conn in root.iter("connection"):
            if conn.get("ref") != "sechighways":
                continue
            ends = {"entrypoint": ("", (0.0, 0.0)),
                    "exitpoint": ("", (0.0, 0.0))}
            for sub in conn.iter("connection"):
                if sub.get("ref") in ends:
                    macro_el = sub.find("macro")
                    if macro_el is not None:
                        mp = macro_el.get("path")
                        ends[sub.get("ref")] = (
                            sector_of(mp),
                            zone_of(mp, macro_el.get("connection") or ""))
            add(ends["entrypoint"][0], ends["exitpoint"][0],
                ends["entrypoint"][1], ends["exitpoint"][1], source)

    return list(pairs.values())


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


def extract_modcaps(gf: GameFiles) -> list[list]:
    """Station module capacities: housing/needed workforce and storage."""
    rows = {}
    paths = gf.glob(
        r"(extensions/[^/]+/)?assets/structures/.*/macros/.*\.xml$"
    )
    for path in paths:
        root = _parse(gf, path)
        if root is None:
            continue
        for m in root.iter("macro"):
            macro = (m.get("name") or "").lower()
            if not macro:
                continue
            wf = m.find("properties/workforce")
            cargo = m.find("properties/cargo")
            if wf is None and cargo is None:
                continue
            rows[macro] = [
                macro,
                m.get("class", ""),
                wf.get("capacity", "") if wf is not None else "",  # housing
                wf.get("max", "") if wf is not None else "",       # workers used
                cargo.get("max", "") if cargo is not None else "",
                cargo.get("tags", "") if cargo is not None else "",
            ]
    return list(rows.values())


def _ship_storages(gf: GameFiles) -> dict[str, tuple[str, str]]:
    """Ship cargo hold macros -> (max, tags). A ship's cargo capacity lives
    on separate storage macros referenced from the ship macro's connections,
    not on the ship macro itself."""
    stores: dict[str, tuple[str, str]] = {}
    # ship hold macros sit next to the ship macros; some DLCs keep them
    # under props/StorageModules (base game casing) or storagemodules
    paths = gf.glob(
        r"(extensions/[^/]+/)?assets/(units/size_[a-z]+"
        r"|props/[Ss]torage[Mm]odules)/macros/storage_.*\.xml$"
    )
    for path in paths:
        root = _parse(gf, path)
        if root is None:
            continue
        for m in root.iter("macro"):
            macro = (m.get("name") or "").lower()
            cargo = m.find("properties/cargo")
            if macro and cargo is not None:
                stores[macro] = (cargo.get("max", ""), cargo.get("tags", ""))
    return stores


def extract_ships(gf: GameFiles, tdb: TextDB, prices: dict[str, str]) -> list[list]:
    rows = {}
    stores = _ship_storages(gf)
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
            if cargo is not None:
                cargo_max = cargo.get("max", "")
                cargo_tags = cargo.get("tags", "")
            else:
                # cargo capacity lives on the storage macros the ship links
                # via its connections; sum them (tags-united)
                holds = [stores[r] for r in (
                    (mm.get("ref") or "").lower()
                    for mm in m.findall("connections/connection/macro")
                ) if r in stores]
                cargo_max = str(sum(int(float(h[0] or 0)) for h in holds)) \
                    if holds else ""
                cargo_tags = " ".join(sorted(
                    {t for h in holds for t in h[1].split()}))
            drag = m.find("properties/physics/drag")
            rows[macro] = [
                macro,
                name or macro,
                _SIZE_BY_CLASS[cls],
                ident.get("makerrace", "") if ident is not None else "",
                purpose.get("primary", "") if purpose is not None else "",
                hull.get("max", "") if hull is not None else "",
                physics.get("mass", "") if physics is not None else "",
                cargo_max,
                cargo_tags,
                people.get("capacity", "") if people is not None else "",
                prices.get(macro.removesuffix("_macro"), ""),
                drag.get("forward", "") if drag is not None else "",
                source,
            ]
    return list(rows.values())


def extract_gamedata(cfg: Config, include_mods: bool = False) -> int:
    game_dir = cfg.resolve_game_dir()
    extensions = None
    if include_mods:
        ext_root = game_dir / "extensions"
        official = sorted(
            d.name for d in ext_root.iterdir()
            if d.is_dir() and d.name.startswith("ego_dlc_")
        )
        mods = sorted(
            d.name for d in ext_root.iterdir()
            if d.is_dir() and not d.name.startswith("ego_dlc_")
        )
        extensions = official + mods

    log("Indexing game catalogs:", game_dir)
    gf = GameFiles(game_dir, extensions)
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
        ["id", "name", "group", "transport", "volume", "tags", "price_avg", "component", "source"],
        ware_rows,
    )

    log("Extracting map (clusters, sectors, highways)")
    cluster_rows, sector_rows, highway_rows = extract_map(gf, tdb)
    _write_csv(
        cfg.data_dir / "clusters.csv",
        ["macro", "x", "y", "z", "name", "description", "source"],
        cluster_rows,
    )
    _write_csv(
        cfg.data_dir / "sectors.csv",
        ["cluster", "macro", "x", "y", "z", "name", "sunlight", "highway",
         "source"],
        sector_rows,
    )
    _write_csv(
        cfg.data_dir / "highways.csv",
        ["sector", "points", "source"],
        highway_rows,
    )

    log("Extracting gate connections")
    _write_csv(
        cfg.data_dir / "gates.csv",
        ["sector_a", "sector_b", "ax", "az", "bx", "bz", "source"],
        extract_gates(gf),
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

    log("Extracting module capacities")
    _write_csv(
        cfg.data_dir / "modcaps.csv",
        ["macro", "class", "housing", "workers", "cargo_max", "cargo_tags"],
        extract_modcaps(gf),
    )

    log("Extracting ship models")
    prices = {r[0]: r[6] for r in ware_rows}  # ware id -> price_avg
    _write_csv(
        cfg.data_dir / "ships.csv",
        ["macro", "model", "class", "race", "purpose", "hull", "mass",
         "cargo", "cargo_tags", "crew", "price", "drag_forward", "source"],
        extract_ships(gf, tdb, prices),
    )

    log("Extracting engines")
    from .engines import extract_engines
    _write_csv(
        cfg.data_dir / "engines.csv",
        ["macro", "size", "type", "mk", "forward", "travel_thrust"],
        [[e["macro"], e.get("size") or "", e.get("type") or "",
          e.get("mk") or "", e.get("forward") or 0,
          (e.get("travel") or {}).get("thrust", 0) or 0]
         for e in extract_engines(gf)],
    )

    log("Done.")
    return 0


def _ensure(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return True
