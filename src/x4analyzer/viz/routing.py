"""Trade > Routing: how long from here to there, for any ship and any
pair of stations.

Trade Opportunities answers "which lane pays"; this pane answers the
logistics question underneath it — pick a ship and an origin, and every
station in the galaxy gets Jumps / Distance / Time. There are no
financial columns and every hull is pickable, not just the traders.

The heavy lifting is client-side: 1,800 stations × any origin cannot be
precomputed, so `analysis/routing.py` ships the gate graph itself and
`routing_page.js` re-walks it (a transcription of
`opportunities._Router`, checked at load against Python-computed
reference routes). The trip-time arithmetic is the Opportunities model
verbatim — see docs/reference/viz-internals.md § Routing pane.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..analysis.frames import Frames
from ..analysis.opportunities import player_trade_ships
from ..analysis.routing import check_routes, graph_payload, routing_stations
from ..config import Config
from ..gamedata.refdata import RefData
from .common import DARK_BG, DARK_FG
from .market import _PAGE_CSS

_PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Routing</title>
<link rel='stylesheet' href='lib/datatables.min.css'>
<script src='lib/jquery.min.js'></script>
<script src='lib/datatables.min.js'></script>
<style>__CSS__
.rtq{background:#2a2a2a;color:__FG__;border:1px solid #555;padding:3px 6px;
  font-size:12px;width:100%;box-sizing:border-box;margin-bottom:4px;}
.oppcard select{max-width:340px;}
</style></head><body>
<h3 style='margin:4px 0'>Routing</h3>
<details class='note'>
<summary>How these times are computed &amp; caveats</summary>
<div class='notebody'>
<p>Pick one of <b>your ships</b> and an <b>origin</b>: every station in
this save is then listed with the gate <b>jumps</b>, the real one-way
<b>route length</b> in km — measured through the actual station and gate
positions along the time-optimal path — and the estimated <b>voyage
time</b> for that ship. The "To" selector narrows the table to a single
pair. No cargo, no prices: this is the travel half of
<b>Trade&nbsp;&gt;&nbsp;Opportunities</b>, and both panes deliberately
use the identical route graph and time model.</p>
<p><b>Model assumptions</b> — the knobs behind Time:</p>
<ul>
<li><b>Dock time</b> — flat per-trip overhead: docking approach, cargo
transfer and undocking at both endpoints combined. S/M default 2 min
(the transfer itself is ~15&ndash;30 s once docked); L/XL default
5 min because big ships queue for piers, fly long mandatory approach
paths and transfer for ~60 s.</li>
<li><b>Travel drive ratio</b> — the fraction of the loadout's travel
top speed a ship actually averages over a leg; spool-up, gate
transits, evasion and endpoint deceleration eat the rest. The 0.9
default was fitted against logged runs of real traders.</li>
<li><b>Use highways</b> + <b>at km/s</b> — S and M ships (never L/XL)
ride local ring highways where a sector has them: the route switches
to a highway-favouring path and highway-sector legs move at the set
average speed. Rings run ~6&ndash;14 km/s depending on the sector;
10 is a middle-of-the-road default. The checkbox is preset from
whether this save contains ring highways at all.</li>
<li><b>Gate and superhighway transits count as ZERO time</b> — only the
flying between gates is charged — and a one-way gate is treated as
two-way, so a route that is actually one-directional in game can appear
in both directions.</li>
</ul>
<p>Speed is the ship's ACTUAL loadout: mounted engines &times; travel
thrust &divide; hull drag, the in-game encyclopedia formula (engine mods
are not modelled). Ships of the same model, class, hold and speed are
rolled into one pickable row. Hostility, travel bans and accelerator
detours are not modelled.</p>
<p>Origin "<b>selected ship's current location</b>" uses the ship's host
station position when it is docked; a free-flying ship is only known to
the save by its sector, so it is placed at the <b>sector centre</b> —
expect tens of km of slack on the first leg.</p>
</div>
</details>
<div class='oppcards'>
<div class='oppcard'><h4>Route</h4>
<div class='oprow'><label for='rtfrom'>From:</label><br>
<input class='rtq' id='rtfromq' placeholder='filter stations/sectors…'>
<select id='rtfrom'></select></div>
<div class='oprow'><label for='rtto'>To:</label><br>
<input class='rtq' id='rttoq' placeholder='filter stations/sectors…'>
<select id='rtto'></select></div>
<div class='oprow note'>Origin: <span id='rtorigin'>&mdash;</span>
&nbsp;<span id='rtcount'></span></div>
</div>
<div class='oppcard'><h4>Your ship</h4>
<div class='oprow'><label for='rtship'>Ship:</label>
<select id='rtship'></select></div>
<div class='oprow'><span style='color:#9a9a9a' title='loadout travel
speed: mounted engines &times; travel thrust &divide; hull drag;
effective cruise applies the travel drive ratio'>Travel speed:</span>
<span id='rtspeed'>&mdash;</span></div>
<div class='oprow'><span style='color:#9a9a9a'>Currently at:</span>
<span id='rtwhere'>&mdash;</span></div>
</div>
<div class='oppcard'><h4>Model assumptions</h4>
<div class='oprow'><span style='color:#9a9a9a' title='flat per-trip
overhead: docking, cargo transfer and undocking at both
endpoints'>Dock time (min):</span>
&nbsp;<label for='rtdock'>S/M</label>
<input type='number' id='rtdock' min='0' step='0.5' value='2'
       style='width:60px;background:#2a2a2a;color:__FG__;
       border:1px solid #555;padding:4px'>
&nbsp;<label for='rtdockl' title='L/XL ships queue for piers and fly
long docking approaches'>L/XL</label>
<input type='number' id='rtdockl' min='0' step='0.5' value='5'
       style='width:60px;background:#2a2a2a;color:__FG__;
       border:1px solid #555;padding:4px'></div>
<div class='oprow'><label for='rtcruise' title='fraction of the
loadout travel-drive top speed a ship actually averages over a leg
(0.9 validated against logged trader runs)'>Travel drive ratio:</label>
<input type='number' id='rtcruise' min='0.1' max='1' step='0.05'
       value='0.9'
       style='width:60px;background:#2a2a2a;color:__FG__;
       border:1px solid #555;padding:4px'></div>
<div class='oprow'><label title='S/M ships ride local ring highways;
untick for saves without highways'><input type='checkbox'
id='rthw'__HWCHK__> use highways</label>
&nbsp;<label for='rthwv' title='average speed on local ring highways
(~6&ndash;14 km/s depending on the sector)'>at km/s:</label>
<input type='number' id='rthwv' min='1' max='20' step='1' value='10'
       style='width:60px;background:#2a2a2a;color:__FG__;
       border:1px solid #555;padding:4px'></div>
</div>
</div>
<table id='rtroutes' class='display nowrap' style='width:100%'>
<thead><tr><th>From</th><th>To</th><th>Jumps</th>
<th title='one-way route length in km through the actual station and
gate positions (S/M ships may take a highway-favouring route)'>Distance
km</th>
<th title='estimated one-way voyage time for the picked ship: real route
length at the travel drive ratio &times; loadout travel speed (S/M on
highways at the set highway speed when enabled) plus the flat dock
time'>Time</th></tr></thead>
</table>
<script>window.X4RT = __DATA__;</script>
<script>__JS__</script>
</body></html>"""


def build_routing(frames: Frames, ref: RefData, cfg: Config,
                  files_dir: Path, guid: str) -> str | None:
    """Emit the Routing page; None when the save has no routable
    stations (or none the player has discovered)."""
    stations, secnames = routing_stations(frames, ref, cfg)
    if not stations:
        return None
    ships = player_trade_ships(frames, ref, container_only=False,
                               with_location=True)
    payload = {
        "graph": graph_payload(ref),
        "stations": stations,
        "secnames": {str(k): v for k, v in sorted(secnames.items())},
        "ships": ships,
        "chk": check_routes(ref, stations),
        "colours": {s: ref.colour_of_short(s)
                    for s in sorted(set(ref.faction_short.values())
                                    | {"PLA", "OTH"})},
    }
    payload["colours"]["PLA"] = ref.faction_colour.get(
        "player", payload["colours"]["PLA"])
    # the ship's home sector may not host any listed station, but it is
    # player-known by construction, so its name is safe to show
    sidx = {s[0]: i for i, s in enumerate(payload["graph"]["sec"])}
    sec_name = dict(zip(frames.sectors["macro"], frames.sectors["name"]))
    for sh in ships:
        loc = sh.get("loc")
        if loc and loc[0] in sidx:
            payload["secnames"].setdefault(
                str(sidx[loc[0]]), sec_name.get(loc[0], loc[0]))

    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    js = Path(__file__).with_name("routing_page.js").read_text(
        encoding="utf-8")
    html = (_PAGE
            .replace("__CSS__", _PAGE_CSS)
            .replace("__DATA__", data)
            .replace("__JS__", js)
            .replace("__HWCHK__", " checked" if frames.has_highways else "")
            .replace("__BG__", DARK_BG)
            .replace("__FG__", DARK_FG))
    fname = f"Trade Routing_{guid}.html"
    (files_dir / fname).write_text(html, encoding="utf-8")
    return f"files/{fname}"
