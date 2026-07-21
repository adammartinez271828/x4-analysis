"""Interactive hex sector map (R lines 802-1005).

Map x = galaxy x, map y = galaxy z. The R script hand-tuned offsets for every
multi-sector cluster by sector name; since extract-gamedata captures the real
in-cluster sector offsets, positions are derived from those instead (quantized
to the same grid steps the R script used), which covers DLC sectors
automatically.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from ..config import Config
from ..analysis.frames import Frames
from ..gamedata.refdata import RefData
from .common import DARK_BG, DARK_FG, fullscreen_button_html

X_DIV = 20_000_000
Y_DIV = 17_320_000
X_RANGE = (-230_000_000, 200_000_000)
Y_RANGE = (-86_600_000, 147_220_000)

# label wrapping: break on spaces except before roman numerals / short words
_WRAP = re.compile(
    r" (?![IVX]+ )(?![IVX]+$)(?!of )(?!to )(?!Sun$)(?!Plate )(?!First )(?!Dead )"
)
_SUFFIX = re.compile(r" [12IVX]+.*$")


# slot patterns for n sectors sharing one cluster hex, in (dx, dy) grid
# steps (8px, 14px at the fixed map density). Derived from the arrangements
# the R script hand-tuned per sector name (e.g. Grand Exchange), except the
# 2-slot pattern which R had mirrored versus the in-game map: the audited
# right-handed default is top-RIGHT + bottom-left, matching the 3-slot
# Grand Exchange shape (top and bottom sectors on the right).
_SLOTS = {
    1: [(0, 0)],
    2: [(1, 1), (-1, -1)],
    3: [(1, 1), (-2, 0), (1, -1)],
    4: [(-1, 1), (1, 1), (-1, -1), (1, -1)],
    5: [(-1, 1), (1, 1), (-2, 0), (-1, -1), (1, -1)],
    6: [(-1, 1), (1, 1), (-2, 0), (2, 0), (-1, -1), (1, -1)],
}

# multi-sector clusters the in-game map draws mirrored across the
# vertical axis ("left-handed", vs the right-handed _SLOTS defaults like
# Grand Exchange). The full vanilla+DLC list was audited in-game; no
# game data file predicts it — the in-cluster sector offsets, zone
# layouts and highway spline positions all fail to correlate (e.g.
# Black Hole Sun's offsets lean opposite to its in-game arrangement),
# so the lean lives in Egosoft's map code only. Unlisted clusters
# (future DLC, mods) default to right-handed.
_LEFT_HANDED = {
    "cluster_04_macro",    # Nopileos' Fortune
    "cluster_06_macro",    # Black Hole Sun
    "cluster_21_macro",    # Scale Plate Green
    "cluster_26_macro",    # Atiya's Misfortune
    "cluster_32_macro",    # Tharka's Cascade
    "cluster_42_macro",    # Hewa's Twin III/IV
    "cluster_50_macro",    # Turquoise Sea
    "cluster_104_macro",   # Earth / The Moon
    "cluster_108_macro",   # Saturn / Titan
    "cluster_408_macro",   # Thuruk's Demise
    "cluster_416_macro",   # Guiding Star
    "cluster_606_macro",   # Kingdom End
}

# clusters whose sectors the in-game map orders opposite to their
# in-cluster offsets (also audited in-game). Both are mostly-horizontal
# pairs where the z difference deciding "top" is a few Mm of noise; the
# game puts the data's "lower" sector on the top slot. Applied as a
# reversal of the offset-sorted sector order before slot assignment.
_SWAP_ORDER = {
    "cluster_15_macro",    # Ianamus Zura (VII top, IV bottom)
    "cluster_19_macro",    # Hewa's Twin (II top, I bottom)
}

# display-name overrides for cluster labels: the game names all three Sol
# clusters just "Sol", which is useless as a per-cluster label
_CLUSTER_NAMES = {
    "cluster_104_macro": "Earth",
    "cluster_108_macro": "Saturn",
}

# zoomed-in cluster-name placement overrides of the encroachment
# geometry (user preference): render BELOW despite a free top strip
_NAME_BELOW = {
    "cluster_19_macro",    # Hewa's Twin I/II (pairs with III/IV's label)
    "cluster_50_macro",    # Turquoise Sea (matches Scale Plate Green)
}


# The map page: a self-contained SVG renderer (no plotly, no lib/ assets).
# The client script lives in map_page.js next to this module and is inlined
# at build time; the payload is injected as window.X4MAP. Tokens are
# substituted with str.replace (not f-strings) to avoid CSS/JS brace
# escaping.
_PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Sector map</title>
<style>
html,body{height:100%;}
body{margin:0;background:__BG__;color:#b0b0b0;overflow:hidden;
font-family:'Open Sans',verdana,arial,sans-serif;}
#wrap{display:flex;height:100%;}
#map{flex:1 1 auto;width:100%;height:100%;display:block;overflow:hidden;
cursor:grab;--sw:1;}
#map.dragging{cursor:grabbing;}
/* stroke weights counter-scale with zoom (--sw set by the view
controller): they grow until ~1.3x their base screen weight, then hold */
#ly-factions polygon{stroke-width:calc(3px*var(--sw));}
#ly-clusters polygon{stroke-width:calc(2px*var(--sw));}
#ly-gates line{stroke-width:calc(1.5px*var(--sw));}
#ly-gates circle{r:calc(2px*var(--sw));}
#ly-shighways line{stroke-width:calc(1.5px*var(--sw));}
#ly-shighways circle{r:calc(2px*var(--sw));}
#ly-highways polyline{stroke-width:calc(1.5px*var(--sw));
stroke-linecap:round;stroke-linejoin:round;}
#ly-contested path,#ly-police path,#ly-pirates path{
stroke-width:calc(1px*var(--sw));}
#ly-resources path{stroke-width:calc(4px*var(--sw));
stroke-linecap:round;stroke-linejoin:round;}
.glhl-line,.glhl-hex{stroke-width:calc(2.5px*var(--sw));}
#ly-player polygon{stroke-width:calc(2px*var(--sw));}
.pulse{stroke-width:calc(4px*var(--sw));}
.seclabel{font-weight:bold;fill:rgba(240,240,96,0.63);}
#map.zoomed-out .k-suffix{display:none;}
#map.zoomed-out .k-basein{display:none;}
#map:not(.zoomed-out) .k-base{display:none;}
#ly-facilities{pointer-events:none;}
#map.zoomed-out #ly-plystations{display:none;}
#map.zoomed-out #fac-stations{display:none;}
#map:not(.zoomed-out) #fac-clusters{display:none;}
#map:not(.zoomed-out) #fac-stations g{pointer-events:auto;}
#ly-facilities.off-hq .fk-hq{display:none;}
#ly-facilities.off-shipyard .fk-shipyard{display:none;}
#ly-facilities.off-wharf .fk-wharf{display:none;}
#ly-facilities.off-equipdock .fk-equipdock{display:none;}
#ly-facilities.off-trading .fk-trading{display:none;}
#ly-facilities.off-khaak .fk-khaak{display:none;}
#ly-facilities .fdim{opacity:0.22;}
#ly-gates line{stroke:rgba(140,170,200,0.55);}
#ly-gates circle{fill:rgba(140,170,200,0.8);}
#ly-shighways line{stroke:rgba(110,220,190,0.6);}
#ly-shighways circle{fill:rgba(110,220,190,0.85);}
#ly-highways polyline{stroke:rgba(255,138,60,0.8);}
#ly-factions polygon{stroke-opacity:0.9;transition:stroke-opacity 0.15s;}
#ly-factions g.dim polygon{stroke-opacity:0.15;}
#ly-highlight *{pointer-events:none;}
.pbadge{font-size:9px;font-weight:bold;fill:#e8e8e8;}
.glhl-line{stroke:rgba(150,200,255,0.85);}
.glhl-hex{fill:none;stroke:rgba(150,200,255,0.7);}
#x4home{position:fixed;bottom:34px;right:10px;z-index:20;cursor:pointer;
font-size:22px;line-height:1;color:#b0b0b0;opacity:0.45;user-select:none;}
#x4home:hover{opacity:1;}
#searchwrap{position:fixed;top:8px;left:8px;z-index:15;display:flex;
align-items:center;gap:8px;}
#search{background:rgba(42,42,42,0.92);color:__FG__;border:1px solid #555;
border-radius:3px;padding:5px 9px;font-size:13px;width:170px;outline:none;}
#search:focus{border-color:#888;}
#search.nomatch{border-color:#c0504d;}
#searchinfo{color:#9a9a9a;font-size:12px;}
.pulse{fill:none;stroke:#ffe066;stroke-width:4;
animation:pulse 0.65s ease-out 3;}
@keyframes pulse{from{stroke-opacity:0.9;}to{stroke-opacity:0;}}
#panel{flex:none;width:0;height:100%;box-sizing:border-box;
overflow:hidden;background:rgba(28,28,28,0.97);
transition:width 0.22s ease-out;font-size:13px;color:__FG__;}
#panel.open{width:320px;border-left:1px solid #444;
border-right:1px solid #444;}
#panelbody{position:relative;width:320px;height:100%;box-sizing:border-box;
padding:14px 16px;overflow-y:auto;}
#panel h3{margin:0 30px 6px 0;font-size:16px;color:#f0f060;}
#panel h4{margin:14px 0 5px 0;font-size:13px;color:#b0b0b0;
border-bottom:1px solid #3a3a3a;padding-bottom:3px;cursor:pointer;
user-select:none;}
#panel h4:hover{color:#d8d8d8;}
.psec.collapsed .psbody{display:none;}
#panel .prow{color:#c8c8c8;margin:2px 0;}
#panelclose{position:absolute;top:8px;right:12px;cursor:pointer;
font-size:18px;color:#9a9a9a;}
#panelclose:hover{color:#fff;}
.plink{color:#8ab8e8;cursor:pointer;}
.plink:hover{text-decoration:underline;}
.pstat{margin:3px 0;color:#c8c8c8;}
.pstat small{color:#9a9a9a;}
.pfields{margin:0;}
.pfields>summary{cursor:pointer;list-style:none;outline:none;margin:3px 0;
display:flex;justify-content:space-between;align-items:baseline;gap:8px;
color:#c8c8c8;}
.pfields>summary::-webkit-details-marker{display:none;}
.pfields>summary::after{content:"\\25B8";color:#7a7a7a;flex:none;
font-size:11px;}
.pfields[open]>summary::after{content:"\\25BE";}
.pfields>summary:hover::after{color:#c8c8c8;}
.pfields>summary small{color:#9a9a9a;}
.pfhdr{margin:1px 0 3px 14px;color:#9a9a9a;font-size:11.5px;}
.pfhdr b{color:#c8a86a;font-weight:normal;}
.pfrow{margin:1px 0 1px 14px;color:#b8b8b8;font-size:11.5px;
font-variant-numeric:tabular-nums;}
.pfrow .fnum{color:#d8d8d8;}
.pfrow .fsp{color:#8a9a8a;}
.pf-respawning .fst{color:#c8a86a;}
.pf-never .fst,.pf-unknown .fst{color:#8a8a8a;}
.pfac{margin:9px 0 3px 0;color:#b0b0b0;font-weight:bold;font-size:12.5px;}
.pind{margin-left:12px;}
#legend{flex:none;width:__LEGW__px;box-sizing:border-box;height:100%;
overflow-y:auto;padding:24px 8px 12px 14px;font-size:13px;user-select:none;}
.lgroup{margin-bottom:16px;}
.ltitle{font-weight:bold;margin-bottom:5px;cursor:pointer;
user-select:none;}
.ltitle:hover{color:#d8d8d8;}
.lcaret{display:inline-block;width:13px;color:#8a8a8a;}
.lgroup.collapsed .lbody{display:none;}
.lgroup.collapsed{margin-bottom:8px;}
.litem{display:flex;align-items:center;gap:7px;cursor:pointer;
padding:1.5px 0;white-space:nowrap;}
.litem.off{opacity:0.45;}
.litem .sw{flex:none;width:18px;height:14px;display:flex;
align-items:center;justify-content:center;}
.lbtn{padding-left:25px;}
#tip{position:fixed;display:none;max-width:340px;z-index:10;
background:rgba(24,24,24,0.95);color:__FG__;border:1px solid #666;
border-radius:3px;padding:6px 9px;font-size:12.5px;line-height:1.4;
pointer-events:none;}
</style></head><body>
<div id='wrap'>
<svg id='map' xmlns='http://www.w3.org/2000/svg'></svg>
<div id='panel'><div id='panelbody'></div></div>
<div id='legend'></div>
</div>
<div id='searchwrap'><input id='search' type='text' placeholder='Find sector&#8230;'
autocomplete='off' spellcheck='false'><span id='searchinfo'></span></div>
<div id='tip'></div>
__FSBTN__
<script>window.X4MAP = __DATA__;</script>
<script>
__JS__
</script>
</body></html>
"""


# data units per px at the R-tuned density the plot area is scaled to keep
_UPX = (X_RANGE[1] - X_RANGE[0]) / 1536
_UPY = (Y_RANGE[1] - Y_RANGE[0]) / 864


def _slot_xy(dx: int, dy: int) -> tuple[float, float]:
    # 8px/14px per grid step. With 29px sub-sector hexes these are the
    # tightest arrangements that still work: the 2-slot diagonal pair and
    # the 3-slot vertical pair keep a ~2px gap, and every slot stays
    # inside the 65px cluster hex within stroke clearance (the bottom
    # corner of a (±1,∓1) slot lands exactly on the outline). 4+ hexes
    # cannot all fit disjointly; those keep R's waist overlaps.
    return dx * 8 * _UPX, dy * 14 * _UPY


def _layout_sectors(frames: Frames, ref: RefData, cfg: Config) -> pd.DataFrame:
    clusters = ref.clusters.set_index("macro")
    offsets = ref.sectors.set_index("macro")
    per_cluster = ref.sectors.groupby("cluster")["macro"].count()

    df = frames.sectors.copy()
    if cfg.spoilers_hide:
        df = df[df["knownto"] == "player"]

    recs = []
    for cluster_macro, group in df.groupby("cluster.macro"):
        if cluster_macro not in clusters.index:
            continue
        cx = float(clusters.loc[cluster_macro, "x"])
        cy = float(clusters.loc[cluster_macro, "z"])
        multi = per_cluster.get(cluster_macro, 1) > 1

        # order sectors by their real in-cluster position (top first, then
        # left) and assign them to the same-ordered display slots
        group = group.assign(
            _ox=group["macro"].map(offsets["x"]).fillna(0.0),
            _oz=group["macro"].map(offsets["z"]).fillna(0.0),
        ).sort_values(["_oz", "_ox"], ascending=[False, True])
        if cluster_macro in _SWAP_ORDER:
            group = group.iloc[::-1]
        n = len(group)
        slots = _SLOTS.get(n) if multi else _SLOTS[1]
        if slots is None:  # 7+ sectors: ring layout
            slots = [(-1, 1), (1, 1), (-2, 0), (2, 0), (-1, -1), (1, -1),
                     (0, 2), (0, -2)][:n]
        slots = sorted(slots, key=lambda s: (-s[1], s[0]))
        if multi and cluster_macro in _LEFT_HANDED:
            slots = sorted([(-dx, dy) for dx, dy in slots],
                           key=lambda s: (-s[1], s[0]))

        for (_, row), (dx, dy) in zip(group.iterrows(), slots):
            sx, sy = _slot_xy(dx, dy) if multi else (0.0, 0.0)
            recs.append({
                "x": cx + sx, "y": cy + sy, "cluster.x": cx, "cluster.y": cy,
                "cluster.macro": cluster_macro, "macro": row["macro"],
                "name": row["name"], "owner": row["owner"],
                "knownto": row["knownto"], "contested": row["contested"],
                "sizecat": "s" if multi else "b",
            })
    out = pd.DataFrame(recs)
    out["colour"] = out["owner"].map(ref.faction_colour).fillna("#808080")
    out["ownername"] = out["owner"].map(ref.faction_name).fillna(
        out["owner"].str.capitalize())
    out.loc[out["owner"] == "player", "ownername"] = "Player"
    return out


def _labels(plot_sectors: pd.DataFrame, ref: RefData) -> pd.DataFrame:
    """Sector labels. kind tags the visibility group: "single" (lone
    sector, always shown), "suffix" (per-sector label in a multi-sector
    cluster, zoomed-in only — the shared base prefix is stripped where the
    name has one, else the full name is used) or "base" (the cluster name,
    one per multi-sector cluster: zoomed-out, plus the zoomed-in companion
    above/below the hex). Multi-sector clusters therefore never show
    per-sector names at minimum zoom."""
    cluster_names = dict(zip(ref.clusters["macro"], ref.clusters["name"]))
    recs = []
    for cmacro, group in plot_sectors.groupby("cluster.macro"):
        if len(group) == 1:
            row = group.iloc[0]
            recs.append({"x": row["x"], "y": row["y"], "altname": row["name"],
                         "kind": "single", "big": row["sizecat"] == "b"})
            continue
        base = _CLUSTER_NAMES.get(cmacro) \
            or str(cluster_names.get(cmacro, "")) \
            or _SUFFIX.sub("", str(group.iloc[0]["name"]))
        for row in group.itertuples():
            name = str(row.name)
            if name.startswith(base + " ") and len(name) > len(base) + 1:
                name = name[len(base) + 1:]
            recs.append({"x": row.x, "y": row.y, "altname": name,
                         "kind": "suffix", "big": row.sizecat == "b"})
        recs.append({
            "x": float(group.iloc[0]["cluster.x"]),
            "y": float(group.iloc[0]["cluster.y"]),
            "altname": base,
            "kind": "base",
            "big": True,
            "cluster": cmacro,
        })
    return pd.DataFrame(recs).dropna(subset=["altname"])


def _overlay(events: pd.DataFrame, plot_sectors: pd.DataFrame,
             time_limit: float, count_name: str) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["x", "y", "sizecat", count_name, "scale",
                                     "name"])
    recent = events[events["time"] > time_limit]
    counts = (recent.groupby("sector.name").size()
              .rename(count_name).reset_index())
    merged = plot_sectors.merge(counts, left_on="name",
                                right_on="sector.name", how="inner")
    if merged.empty:
        return merged
    merged["scale"] = merged[count_name] / merged[count_name].max()
    return merged


def _resource_levels(plot_sectors: pd.DataFrame, sectors: pd.DataFrame,
                     resource_cols: list[str]) -> pd.DataFrame:
    """Quartile-bin each resource: 3=top quartile, 2=third, 1=any, 0=none."""
    res = plot_sectors.merge(
        sectors[["macro"] + resource_cols], on="macro", how="left")
    for col in resource_cols:
        vals = res[col].fillna(0.0)
        positive = vals[vals > 0]
        if positive.empty:
            res[col] = 0
            continue
        q50, q75 = positive.quantile(0.5), positive.quantile(0.75)
        # same binning as pd.cut([-1, 0, q50, q75, inf]) but robust to
        # duplicate edges (q50 == q75 when few sectors have the resource,
        # e.g. a barely-explored map under spoilers_hide)
        res[col] = ((vals > 0).astype(int) + (vals > q50).astype(int)
                    + (vals > q75).astype(int))
    return res


def _tooltips(res: pd.DataFrame, resource_cols: list[str], ref: RefData,
              overlay_hours: float) -> pd.Series:
    tips = []
    level_names = [(3, "High"), (2, "Medium"), (1, "Low")]
    for row in res.itertuples(index=False):
        d = row._asdict()
        parts = [f"<b>{d['name']}</b>"]
        owner = d["ownername"]
        parts.append(f"{owner} <b>(Contested)</b>" if d["contested"] == 1
                     else str(owner))
        if pd.notna(d.get("interdictions")):
            parts.append(f"{overlay_hours:.0f}h Police Interdictions: "
                         f"{int(d['interdictions'])}")
        if pd.notna(d.get("harassments")):
            parts.append(f"{overlay_hours:.0f}h Pirate Harassments: "
                         f"{int(d['harassments'])}")
        parts.append("<b>Resources</b>")
        for level, label in level_names:
            names = [ref.ware_name.get(c, c) for c in resource_cols
                     if d.get(c) == level]
            parts.append(f"{label}: " + (", ".join(names) if names else "None"))
        tips.append("<br>".join(parts))
    return pd.Series(tips, index=res.index)


def _payload(frames: Frames, ref: RefData, cfg: Config) -> dict:
    """All map content as plain records in reference-pixel space.

    Reference-px space: x right, y DOWN, one unit = one px at the R-tuned
    1536x864 density (map x = galaxy x, map y = galaxy z, so the R ranges
    still anchor the scale). The data->px transform is anisotropic (~3.4%),
    so it is applied here on the Python side; in px space hexes are regular
    polygons at the R-tuned px sizes and zoom is a uniform scale.
    """
    plot_sectors = _layout_sectors(frames, ref, cfg)
    plot_clusters = ref.clusters[
        ref.clusters["macro"].isin(plot_sectors["cluster.macro"])
    ][["x", "z", "name", "macro"]].rename(columns={"z": "y"})

    time_limit = frames.time_now - 3600 * cfg.overlay_hours
    police = _overlay(frames.police, plot_sectors, time_limit, "interdictions")
    pirates = _overlay(frames.pirates, plot_sectors, time_limit, "harassments")

    res = _resource_levels(plot_sectors, frames.sectors, frames.resource_cols)
    res = res.merge(police[["name", "interdictions"]], on="name", how="left") \
        if not police.empty else res.assign(interdictions=pd.NA)
    res = res.merge(pirates[["name", "harassments"]], on="name", how="left") \
        if not pirates.empty else res.assign(harassments=pd.NA)
    plot_sectors["tooltip"] = _tooltips(res, frames.resource_cols, ref,
                                        cfg.overlay_hours)
    labels = _labels(plot_sectors, ref)

    # R's fixed 5.10 ranges, widened if DLC content falls outside them.
    # The scene is the px-space image of the widened ranges, so without
    # widening it is exactly 1536x864 (the density the px sizes below are
    # tuned for).
    xr = (min(X_RANGE[0], plot_sectors["x"].min() - X_DIV / 2),
          max(X_RANGE[1], plot_sectors["x"].max() + X_DIV / 2))
    yr = (min(Y_RANGE[0], plot_sectors["y"].min() - Y_DIV / 2),
          max(Y_RANGE[1], plot_sectors["y"].max() + Y_DIV / 2))

    def px(x: float, y: float) -> tuple[float, float]:
        return round((x - xr[0]) / _UPX, 2), round((yr[1] - y) / _UPY, 2)

    sectors: list[dict] = []
    index: dict[str, int] = {}
    for _, r in plot_sectors.iterrows():
        x, y = px(r["x"], r["y"])
        index[r["macro"]] = len(sectors)
        sectors.append({
            "macro": r["macro"], "cluster": r["cluster.macro"],
            "name": str(r["name"]),
            "owner": str(r["ownername"]), "colour": str(r["colour"]),
            "big": bool(r["sizecat"] == "b"),
            "contested": int(r["contested"]),
            "tip": str(r["tooltip"]), "x": x, "y": y,
        })

    clusters = []
    for _, r in plot_clusters.iterrows():
        x, y = px(float(r["x"]), float(r["y"]))
        clusters.append({"macro": r["macro"], "x": x, "y": y})

    # stations per plotted sector (detail panel + facility overlays).
    # Spoiler mode also drops undiscovered stations, so no hidden names
    # reach the page.
    uni = frames.universe
    st = uni[uni["class"] == "station"].copy()
    if cfg.spoilers_hide:
        st = st[st["knownto"] == "player"]
    st = st[st["sector.macro"].isin(index)]
    st["fname"] = st["owner"].map(ref.faction_name).fillna(
        st["owner"].str.capitalize())
    st.loc[st["owner"] == "player", "fname"] = "Player"

    # facility flags from BUILT modules only (planned modules don't
    # count): _ships_ + l/xl -> shipyard, _ships_ without -> wharf,
    # _equip_ -> equipment dock. A station can be several at once (player
    # yards); display precedence shipyard > wharf > equipdock > trading.
    # Trading stations have no telltale module, so they come from the
    # save's own basename label (stype).
    bm = frames.built_modules
    bm = bm[bm["macro"].str.contains("buildmodule", na=False)]
    ships_bm = bm[bm["macro"].str.contains("_ships_", na=False)]
    lxl = ships_bm["macro"].str.contains("_l_|_xl_", na=False)
    shipyards = set(ships_bm[lxl]["id"])
    wharfs = set(ships_bm[~lxl]["id"])
    equips = set(bm[bm["macro"].str.contains("_equip_", na=False)]["id"])

    def facility(sid: str, owner: str, stype) -> str | None:
        if owner == "khaak":   # hives/nests/weapon platforms
            return "khaak"
        if sid in shipyards:
            return "shipyard"
        if sid in wharfs:
            return "wharf"
        if sid in equips:
            return "equipdock"
        t = str(stype or "").lower()
        if "trading station" in t or "free port" in t:
            return "trading"
        return None

    st_recs: list[tuple] = []   # (sector macro, sector idx, record, offset)
    # factions that own stations but no sectors (Ministry of Finance,
    # Alliance of the Word, Yaki, ...) still get a Factions legend entry
    # so their facility icons can be faction-dimmed; Kha'ak stays out —
    # it has its own facility toggle and never dims
    extra_factions: dict[str, str] = {}
    # sort by the DISPLAYED label: most NPC factories have an empty name
    # in the save and render their type instead, so the name alone would
    # collapse to a code sort. Facility stations (yards, trading, HQ)
    # sort above the plain stations of their faction.
    st["_disp"] = st["name"].replace("", pd.NA).fillna(st["stype"]) \
        .fillna("")
    tlow = st["stype"].fillna("").str.lower()
    attached = (st["id"].isin(shipyards | wharfs | equips)
                | tlow.str.contains("trading station|free port", regex=True))
    if "faction_hq" in st.columns:
        attached |= st["faction_hq"].fillna(0) == 1
    st["_pri"] = (~attached).astype(int).astype(str)
    for _, r in st.sort_values(["fname", "_pri", "_disp", "code"],
                               key=lambda s: s.str.lower()).iterrows():
        if r["owner"] != "khaak":
            extra_factions.setdefault(
                str(r["fname"]),
                ref.faction_colour.get(r["owner"], "#808080"))
        off = None
        if "sx" in st.columns and pd.notna(r["sx"]) and pd.notna(r["sz"]):
            off = (float(r["sx"]), float(r["sz"]))
        st_recs.append((r["sector.macro"], index[r["sector.macro"]], {
            "name": str(r["name"]), "code": str(r["code"]),
            "owner": str(r["fname"]),
            "type": str(r["stype"]) if pd.notna(r["stype"]) else "",
            "fac": facility(r["id"], str(r["owner"]), r["stype"]),
            "hq": bool("faction_hq" in st.columns
                       and pd.notna(r["faction_hq"])
                       and r["faction_hq"] == 1),
        }, off))

    # gate/accelerator links as sector-index pairs plus endpoint scene
    # coords (the renderer derives hover adjacency from the indices),
    # between plotted sectors only, so spoiler mode drops links touching
    # hidden sectors. Gate endpoints AND station positions share one
    # per-sector normalization (the farthest point sits at 75% of the hex
    # half-width) so they occupy a consistent sector space. Older
    # gates.csv without endpoint columns falls back to hex centres.
    # sub-sector hexes are sized to nearly fill their cluster-hex slots
    # (see _slot_xy); the single-sector 62px matches R
    big, small = 62, 29
    has_pts = {"ax", "az", "bx", "bz"} <= set(ref.gates.columns)
    raw_gates = []
    for r in ref.gates.itertuples(index=False):
        if r.sector_a in index and r.sector_b in index:
            pa = (float(r.ax), float(r.az)) if has_pts else (0.0, 0.0)
            pb = (float(r.bx), float(r.bz)) if has_pts else (0.0, 0.0)
            raw_gates.append((index[r.sector_a], index[r.sector_b], pa, pb))
    reach: dict[int, float] = {}
    for ia, ib, pa, pb in raw_gates:
        reach[ia] = max(reach.get(ia, 0.0), (pa[0]**2 + pa[1]**2) ** 0.5)
        reach[ib] = max(reach.get(ib, 0.0), (pb[0]**2 + pb[1]**2) ** 0.5)
    for _m, si, _rec, off in st_recs:
        if off:
            reach[si] = max(reach.get(si, 0.0),
                            (off[0] ** 2 + off[1] ** 2) ** 0.5)

    # data vaults (regular + Erlking) for the vault overlays, spoiler-
    # filtered like stations. "open" = the vault has been unlocked (the
    # loot flag lets the tooltip flag unlocked-but-uncollected loot);
    # blueprint macros are ware ids, resolved like the find command does
    dv = getattr(frames, "datavaults", None)
    vault_recs: list[tuple] = []   # (sector idx, record, offset)
    if dv is not None and len(dv):
        dv = dv[dv["sector.macro"].isin(index)]
        if cfg.spoilers_hide:
            dv = dv[dv["knownto"] == "player"]
        for _, r in dv.iterrows():
            off = None
            if pd.notna(r["sx"]) and pd.notna(r["sz"]):
                off = (float(r["sx"]), float(r["sz"]))
            bps = [ref.ware_name.get(b, b)
                   for b in str(r["blueprints"] or "").split(",") if b]
            vault_recs.append((index[r["sector.macro"]], {
                "kind": "erlking" if "erlking" in r["macro"] else "vault",
                "code": str(r["code"]),
                "open": int(r["unlocked"] == 1 or r["loot"] == 0),
                "loot": int(r["loot"]),
                "bp": ", ".join(bps),
            }, off))
    for si, _rec, off in vault_recs:
        if off:
            reach[si] = max(reach.get(si, 0.0),
                            (off[0] ** 2 + off[1] ** 2) ** 0.5)

    # local (ring) highway tracks — the extracted splinetube polylines —
    # drawn inside their sector hex; every point joins the shared
    # per-sector normalization so the curve keeps its true shape
    # relative to gates and stations
    hw = getattr(ref, "highways", None)
    hw_raw: list[tuple] = []   # (sector idx, [(x, z), ...])
    if hw is not None and len(hw):
        for r in hw.itertuples(index=False):
            if r.sector not in index:
                continue
            pts = []
            for tok in str(r.points).split(";"):
                xz = tok.split()
                if len(xz) == 2:
                    try:
                        pts.append((float(xz[0]), float(xz[1])))
                    except ValueError:
                        pass
            if len(pts) >= 2:
                hw_raw.append((index[r.sector], pts))
        for si, pts in hw_raw:
            for p in pts:
                reach[si] = max(reach.get(si, 0.0),
                                (p[0] ** 2 + p[1] ** 2) ** 0.5)

    def in_hex_pt(i: int, p: tuple[float, float]) -> tuple[float, float]:
        s = sectors[i]
        sc = reach.get(i, 0.0)
        if sc <= 0:
            return s["x"], s["y"]
        r_px = (big if s["big"] else small) / 2 * 0.75
        return (round(s["x"] + p[0] / sc * r_px, 2),
                round(s["y"] - p[1] / sc * r_px, 2))

    gates = [[ia, ib, *in_hex_pt(ia, pa), *in_hex_pt(ib, pb)]
             for ia, ib, pa, pb in raw_gates]

    # finalize station records with in-hex positions (centre when the
    # snapshot predates position tracking), grouped per sector. The
    # renderer derives the per-cluster low-zoom icon rows from these
    # (sector records carry their cluster macro), including per-kind
    # owners for faction-dimming.
    stations: dict[str, list[dict]] = {}
    for macro, si, rec, off in st_recs:
        rec["x"], rec["y"] = in_hex_pt(si, off) if off \
            else (sectors[si]["x"], sectors[si]["y"])
        stations.setdefault(macro, []).append(rec)

    vaults: list[dict] = []
    for si, rec, off in vault_recs:
        rec["x"], rec["y"] = in_hex_pt(si, off) if off \
            else (sectors[si]["x"], sectors[si]["y"])
        vaults.append(rec)

    hws = [[si] + [c for p in pts for c in in_hex_pt(si, p)]
           for si, pts in hw_raw]

    label_recs = []
    for _, r in labels.iterrows():
        x, y = px(float(r["x"]), float(r["y"]))
        label_recs.append({"x": x, "y": y, "kind": r["kind"],
                           "big": bool(r["big"]),
                           "lines": _WRAP.sub("\n", str(r["altname"]))
                           .split("\n")})

    # zoomed-in cluster names float just above the cluster hex's top
    # line; when another sector hex sits DIRECTLY above (same grid
    # column, e.g. Scale Plate Green under Company Regard) the name
    # flips below the bottom line instead. The horizontal window is
    # deliberately tight: diagonal neighbours sit half a grid column
    # (~36px) off-centre and do not count (Mercury is top-LEFT of Earth,
    # Jupiter top-RIGHT of Saturn).
    r3_4 = 3 ** 0.5 / 4
    c_half_h = 65 * r3_4
    for rec, (_, lr) in zip(label_recs, labels.iterrows()):
        if rec["kind"] != "base":
            continue
        strip_bot = rec["y"] - c_half_h
        strip_top = strip_bot - 14
        rec["flip"] = lr["cluster"] in _NAME_BELOW or any(
            abs(s["x"] - rec["x"]) < 20
            and s["y"] - (26.9 if s["big"] else 12.6) < strip_bot
            and s["y"] + (26.9 if s["big"] else 12.6) > strip_top
            for s in sectors)

    cbig, csmall = 44, 20  # contested marker sizes

    def overlay_recs(overlay: pd.DataFrame, count_name: str) -> list[dict]:
        recs = []
        for _, r in overlay.iterrows():
            size = int(1 + round(r["scale"] * ((cbig if r["sizecat"] == "b"
                                                else csmall) - 1)))
            recs.append({"i": index[r["macro"]],
                         "count": int(r[count_name]), "size": size})
        return recs

    # sunlight leads the resource list: a per-sector property from the
    # game files (mapdefaults.xml via sectors.csv), stored as a percentage
    # so e.g. Avarice's 1390% renders meaningfully
    resources = []
    if "sunlight" in ref.sectors.columns:
        smap = dict(zip(ref.sectors["macro"], ref.sectors["sunlight"]))
        resources.append({
            "id": "sunlight", "name": "Sunlight",
            "yields": [round(float(smap.get(s["macro"], 1.0)) * 100)
                       for s in sectors],
        })
    if frames.resource_cols:
        rep_cols = [f"rep.{c}" for c in frames.resource_cols
                    if f"rep.{c}" in frames.sectors.columns]
        res_raw = plot_sectors.merge(
            frames.sectors[["macro"] + frames.resource_cols + rep_cols],
            on="macro", how="left")
        for col in frames.resource_cols:
            rec = {
                "id": col, "name": ref.ware_name.get(col, col),
                "yields": [float(v) for v in res_raw[col].fillna(0.0)],
            }
            # max replenishment rate, units/h (Sigma capacity/respawndelay;
            # the client renders percentile ranks). Omitted when the reference
            # CSVs predate the replenishment extract, so the right gauge
            # simply doesn't draw
            rc = f"rep.{col}"
            if rc in res_raw.columns and res_raw[rc].fillna(0.0).gt(0).any():
                rec["rep"] = [round(float(v), 2)
                              for v in res_raw[rc].fillna(0.0)]
            resources.append(rec)

    # per-area status for the detail panel dropdown, keyed by sector macro
    # (only plotted sectors reach the payload, so this is already spoiler-safe).
    # macro -> ware -> [ {status, cap, now, eta_min} ]
    plotted = {s["macro"] for s in sectors}
    area_status = {m: waremap for m, waremap in
                   (frames.resource_areas or {}).items() if m in plotted}

    # the player is always a faction (sector ownership arrives later in a
    # playthrough; the legend entry and colour must exist from the start),
    # and station-only factions join for facility dimming
    factions = []
    names = {s["owner"] for s in sectors} | {"Player"} \
        | set(extra_factions)
    for owner in sorted(names, key=str):
        colour = next((s["colour"] for s in sectors if s["owner"] == owner),
                      extra_factions.get(owner)
                      or ref.faction_colour.get("player", "#28C76F"))
        factions.append({"name": owner, "colour": colour})


    return {
        "scene": {"w": round((xr[1] - xr[0]) / _UPX, 2),
                  "h": round((yr[1] - yr[0]) / _UPY, 2),
                  "pad": 12, "legend_w": 220},
        # marker sizing for the 1536x864 reference density (R makeMap
        # defaults)
        "const": {"big": big, "small": small, "border": 3,
                  "cbig": cbig, "csmall": csmall, "opacity": 0.6,
                  "hours": cfg.overlay_hours},
        "sectors": sectors, "clusters": clusters, "gates": gates,
        "labels": label_recs, "police": overlay_recs(police, "interdictions"),
        "pirates": overlay_recs(pirates, "harassments"),
        "resources": resources, "factions": factions, "stations": stations,
        "vaults": vaults, "hws": hws, "area_status": area_status,
    }


def _write_page(payload: dict, files_dir: Path, guid: str) -> str:
    """Assemble the self-contained map page from the template, the client
    script and the payload; returns the dashboard-relative src path."""
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    js = Path(__file__).with_name("map_page.js").read_text(encoding="utf-8")
    html = (
        _PAGE
        .replace("__JS__", js)
        .replace("__DATA__", data)
        .replace("__FSBTN__", fullscreen_button_html(resize_plotly=False))
        .replace("__BG__", DARK_BG)
        .replace("__FG__", DARK_FG)
        .replace("__LEGW__", str(payload["scene"]["legend_w"]))
    )
    name = f"Sector map_{guid}.html"
    (files_dir / name).write_text(html, encoding="utf-8")
    return f"files/{name}"


def build_map(frames: Frames, ref: RefData, cfg: Config, files_dir: Path,
              guid: str) -> tuple[str, int, int]:
    """Returns (widget src, iframe width px, iframe height px) — the page
    size depends on how far DLC content widens the axis ranges."""
    p = _payload(frames, ref, cfg)
    src = _write_page(p, files_dir, guid)
    return (src,
            round(p["scene"]["w"]) + 2 * p["scene"]["pad"]
            + p["scene"]["legend_w"],
            round(p["scene"]["h"]) + 2 * p["scene"]["pad"])

