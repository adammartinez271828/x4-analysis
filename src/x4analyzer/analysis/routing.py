"""Routing payloads: the gate graph, the station list and reference
routes shipped to the Trade > Routing page.

The page answers "how long from here to there" for an arbitrary
(ship, origin) pair, which means the router has to run client-side —
1,800 stations × every origin is far too much to precompute. So the very
graph `opportunities._Router` walks is exported verbatim and transcribed
into JS (`viz/routing_page.js`).

To keep the two implementations honest, `build_gate_graph` is the single
constructor of that graph: `_Router` consumes it, `graph_payload`
serialises it, and `check_routes` embeds a handful of Python-computed
reference routes the page recomputes at load and warns about on
mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import Config
from ..gamedata.refdata import RefData
from .frames import Frames

# how many reference routes the page self-tests against at load
CHK_PAIRS = 16


@dataclass
class GateGraph:
    """Gate-endpoint graph: nodes are real gate positions (metres,
    sector-local), portals are the free transits between the two
    endpoints of one gate / superhighway link."""

    hw: dict[str, int] = field(default_factory=dict)
    sector: list[str] = field(default_factory=list)      # node -> macro
    pos: list[tuple] = field(default_factory=list)       # node -> (x, z)
    by_sector: dict[str, list[int]] = field(default_factory=dict)
    portals: list[tuple] = field(default_factory=list)   # (node_i, node_j)
    portal_of: dict[int, list[int]] = field(default_factory=dict)


def build_gate_graph(ref: RefData) -> GateGraph:
    """The one gate graph. Nodes come from gates.csv endpoint offsets;
    same-cluster sector pairs without a gates row get synthetic portals
    at the sector centres (belt-and-braces, mirroring
    `sectorgraph.build_adjacency`). One-way gates are treated as
    two-way, exactly as the BFS does."""
    g = GateGraph()
    g.hw = dict(zip(ref.sectors["macro"], ref.sectors.get("highway", 0)))

    def node(sector: str, p: tuple) -> int:
        i = len(g.sector)
        g.sector.append(sector)
        g.pos.append(p)
        g.by_sector.setdefault(sector, []).append(i)
        return i

    has_pts = {"ax", "az", "bx", "bz"} <= set(ref.gates.columns)
    linked: set[tuple] = set()
    for r in ref.gates.itertuples(index=False):
        a, b = str(r.sector_a), str(r.sector_b)
        pa = (float(r.ax), float(r.az)) if has_pts else (0.0, 0.0)
        pb = (float(r.bx), float(r.bz)) if has_pts else (0.0, 0.0)
        g.portals.append((node(a, pa), node(b, pb)))
        linked.update([(a, b), (b, a)])
    for _cl, grp in ref.sectors.groupby("cluster"):
        macros = list(grp["macro"])
        for i, a in enumerate(macros):
            for b in macros[i + 1:]:
                if (a, b) not in linked:
                    g.portals.append(
                        (node(a, (0.0, 0.0)), node(b, (0.0, 0.0))))
    for i, j in g.portals:
        g.portal_of.setdefault(i, []).append(j)
        g.portal_of.setdefault(j, []).append(i)
    return g


def graph_payload(ref: RefData) -> dict:
    """The gate graph as compact JSON for the page: sectors (macro +
    highway flag), nodes (sector index, x, z) in `_Router` node order,
    and portals as node index pairs. ~15 KB for the stock galaxy.

    Sector MACROS, never display names: under `spoilers_hide` the page
    must not carry the name of a sector the player has not discovered,
    and the graph is needed whole regardless of what is shown."""
    g = build_gate_graph(ref)
    macros: list[str] = []
    idx: dict[str, int] = {}
    for m in list(ref.sectors["macro"]) + g.sector:
        m = str(m)
        if m not in idx:
            idx[m] = len(macros)
            macros.append(m)
    return {
        "sec": [[m, int(bool(g.hw.get(m)))] for m in macros],
        "nodes": [[idx[s], round(p[0], 1), round(p[1], 1)]
                  for s, p in zip(g.sector, g.pos)],
        "portals": [[int(i), int(j)] for i, j in g.portals],
    }


def sector_index(ref: RefData) -> dict[str, int]:
    """macro -> index into `graph_payload()["sec"]`."""
    return {s[0]: i for i, s in enumerate(graph_payload(ref)["sec"])}


def routing_stations(frames: Frames, ref: RefData,
                     cfg: Config) -> tuple[list[list], dict[int, str]]:
    """Every station a route can end at, as compact rows
    `[label, factionShort, secIdx, sx, sz, flags]` (flags: 1 = player
    owned, 2 = construction site), plus the display names of the
    sectors they sit in, keyed by sector index.

    Player-owned build plots are included and tagged as sites (you fly
    resources to them); NPC build storage is not a destination anyone
    routes to and is dropped. Under `spoilers_hide` an undiscovered
    station is absent entirely — not listed as unreachable — and its
    sector name never reaches the page."""
    uni = frames.universe
    if uni is None or uni.empty:
        return [], {}
    st = uni[uni["class"].isin(["station", "buildstorage"])].copy()
    if st.empty:
        return [], {}
    st = st[(st["class"] == "station") | (st["owner"] == "player")]
    if cfg.spoilers_hide:
        st = st[st["knownto"] == "player"]
    if st.empty:
        return [], {}

    sidx = sector_index(ref)
    sec_name = dict(zip(frames.sectors["macro"], frames.sectors["name"]))
    rows: list[tuple] = []
    names: dict[int, str] = {}
    for _, r in st.iterrows():
        macro = str(r.get("sector.macro") or "")
        if macro not in sidx:
            continue                      # modded sector without game data
        owner = str(r.get("owner") or "")
        fac = ref.faction_short.get(owner, "OTH")
        if owner == "player":
            fac = "PLA"
        name = str(r.get("name") or "")
        base = str(r.get("stype") or "") or "Station"
        code = str(r.get("code") or "") or "?"
        label = (name or f"{fac} {base}") + f" ({code})"
        flags = (1 if owner == "player" else 0) \
            + (2 if str(r.get("class")) == "buildstorage" else 0)
        si = sidx[macro]
        sx = pd.to_numeric(r.get("sx"), errors="coerce")
        sz = pd.to_numeric(r.get("sz"), errors="coerce")
        names[si] = sec_name.get(macro, macro)
        rows.append((names[si], label, [label, fac, si,
                                        round(float(sx or 0.0), 1),
                                        round(float(sz or 0.0), 1),
                                        flags]))
    rows.sort(key=lambda t: (t[0].lower(), t[1].lower()))
    return [t[2] for t in rows], names


def check_routes(ref: RefData, stations: list[list]) -> list[list]:
    """Reference routes for the page's self-test: fixed station pairs
    with Python-computed (km_plain, km_highway), spread across the
    station list and alternating the S/M and L/XL cost weights.
    Entries are `[from, to, sm, kp, kh]` (station indices)."""
    from .opportunities import _Router

    n = len(stations)
    if n < 2:
        return []
    router = _Router(ref)
    macros = [s[0] for s in graph_payload(ref)["sec"]]
    step = max(1, n // (CHK_PAIRS + 1))
    out: list[list] = []
    for k in range(CHK_PAIRS):
        i = (k * step) % n
        j = (i + 1 + (n // 3)) % n
        if i == j:
            continue
        a, b = stations[i], stations[j]
        sm = k % 2
        km = router.route_km(macros[a[2]], (a[3], a[4]),
                             macros[b[2]], (b[3], b[4]), bool(sm))
        if km is None:
            continue
        out.append([i, j, sm, round(km[0], 3), round(km[1], 3)])
    return out
