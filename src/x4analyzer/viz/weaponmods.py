"""Game-data analysis dashboard: weapon-mod comparison tool.

Static page built straight from the installed game's files (no savegame
involved): `x4-analyzer gamedata-dashboard` -> output/gamedata_dashboard.html.
Follows the market.py pattern — all data embedded as JSON, rendered
client-side — but is fully self-contained (vanilla JS + inline CSS, no
vendored libs needed: it is a single table, not a plotly figure).

For every weapon the page shows the firing-cycle stats bare and under each
applicable weapon mod at its OPTIMAL roll (roll ranges in the tooltip and
the detail panel). Applicable = the mod's guaranteed effects (primary stat
+ forced bonuses) touch the simulated stats; weighted optional pools don't
count (they are listed as detail only), so e.g. the projectile-speed and
mining mods stay off the table. Mods that change nothing on the selected
weapon (cooling mods on a heatless clip weapon) are flagged "no effect",
not hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..cli import log
from ..config import Config
from ..gamedata.catalog import GameFiles
from ..gamedata.extract import load_textdb
from ..gamedata.weapons import extract_weapon_mods, extract_weapons
from ..gamedata.weaponsim import (SIM_STATS, guaranteed_stats,
                                  mod_multipliers, reload_kind, stat_vector)
from .common import DARK_BG, DARK_FG, DARK_MUTED, DARK_PLOT

_SIZE_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4, "?": 5}


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


def _notes(w: dict) -> list[str]:
    notes = []
    if w.get("ammo_clip"):
        notes.append(
            f"Clip weapon: {w['ammo_clip']:g} shots per clip, fixed "
            f"{w.get('ammo_reload') or 0:g} s clip reload. Reload mods only "
            "speed up the shots within a burst; the clip reload itself is "
            "never modified.")
    if w.get("chargetime"):
        notes.append(
            f"Charge weapon — simplified model: volley interval = reload "
            f"time + charge time ({w['chargetime']:g} s).")
    if w.get("forcecooldown"):
        notes.append("Forces a cooldown after every shot (beam); the heat "
                     "cycle shown is simplified.")
    if (w.get("dmg_repair") or 0) > 0:
        notes.append("Repair weapon: damage values are repair amounts.")
    if not w.get("has_damage"):
        notes.append("No damage data in the game files.")
    if not (w.get("heat") or 0):
        notes.append("Builds no heat: it can fire indefinitely, so cooling "
                     "mods and the overheat rows do not apply.")
    return notes


def build_weapon_data(gf: GameFiles) -> tuple[list[dict], list[dict]]:
    """(weapons, mods) JSON-ready structures for the page."""
    tdb = load_textdb(gf)
    weapons = extract_weapons(gf, tdb)
    all_mods = extract_weapon_mods(gf, tdb)
    mods = [m for m in all_mods
            if set(guaranteed_stats(m)) & set(SIM_STATS)]
    log(f"  {len(weapons)} weapons/turrets, {len(mods)} of {len(all_mods)} "
        "weapon mods affect the firing cycle")

    weapons.sort(key=lambda w: (_SIZE_ORDER.get(w["size"], 9),
                                w["wclass"], w["name"]))
    wrows = []
    for w in weapons:
        bare = [_round(v) for v in stat_vector(w)]
        per_mod: dict[str, list | int] = {}
        for mod in mods:
            vec = [_round(v) for v in stat_vector(w, mod_multipliers(mod, w))]
            per_mod[mod["ware"]] = 0 if vec == bare else vec
        group = f"{w['size']} {'turrets' if w['wclass'] == 'turret' else 'weapons'}"
        wrows.append({"id": w["macro"], "n": w["name"], "g": group,
                      "rk": reload_kind(w), "notes": _notes(w),
                      "bare": bare, "mods": per_mod})

    mrows = [{"w": m["ware"], "n": m["name"], "q": m["quality"],
              "s": m["stat"], "min": m["min"], "max": m["max"],
              "forced": ([{"s": b["stat"], "min": b["min"], "max": b["max"]}
                          for b in m["bonuses"]] if m["forced"] else []),
              "pool": ([] if m["forced"] else
                       [{"s": b["stat"], "min": b["min"], "max": b["max"],
                         "wt": b["weight"]} for b in m["bonuses"]])}
             for m in mods]
    return wrows, mrows


_CSS = f"""
body{{font-family:sans-serif;background:{DARK_BG};color:{DARK_FG};margin:0;}}
header{{padding:12px 16px 0 16px;}}
h2{{margin:0 0 12px 0;font-size:20px;}}
h2 small{{color:{DARK_MUTED};font-weight:normal;}}
nav{{display:flex;gap:4px;padding:0 16px;border-bottom:1px solid #444;}}
nav button{{background:#2a2a2a;color:{DARK_MUTED};border:1px solid #444;
  border-bottom:none;border-radius:6px 6px 0 0;padding:8px 18px;
  font-size:14px;cursor:pointer;}}
nav button.active{{background:{DARK_BG};color:{DARK_FG};font-weight:bold;
  border-bottom:1px solid {DARK_BG};margin-bottom:-1px;}}
section{{padding:12px 16px;}}
label{{color:{DARK_MUTED};margin-right:10px;user-select:none;}}
select{{background:#2a2a2a;color:{DARK_FG};border:1px solid #555;
  padding:4px 8px;font-size:14px;max-width:460px;}}
.note{{color:{DARK_MUTED};font-size:12px;margin:6px 0;}}
#stats{{border-collapse:collapse;margin-top:10px;font-size:13px;}}
#stats th,#stats td{{border:1px solid #3a3a3a;padding:5px 9px;
  text-align:right;white-space:nowrap;}}
#stats th{{background:{DARK_PLOT};font-weight:normal;}}
#stats thead th{{vertical-align:top;text-align:center;cursor:default;}}
#stats thead th .mn{{font-weight:bold;display:block;}}
#stats thead th .rng{{color:{DARK_MUTED};font-size:11px;display:block;}}
#stats thead th .q1{{color:#8fd18f;}} #stats thead th .q2{{color:#6ab7e8;}}
#stats thead th .q3{{color:#d8a35a;}}
#stats tbody th{{text-align:left;}}
#stats td.base{{background:#252525;font-weight:bold;}}
#stats .up{{color:#4ecf71;}} #stats .down{{color:#ff6b6b;}}
#stats .same{{color:{DARK_MUTED};}}
#stats .delta{{font-size:11px;display:block;}}
#stats th.noeff,#stats td.noeff{{color:#666;}}
#stats th.noeff .rng{{color:#666;}}
.tblwrap{{overflow-x:auto;}}
details{{margin:4px 0;max-width:1000px;}}
summary{{cursor:pointer;color:{DARK_MUTED};}}
summary:hover{{color:{DARK_FG};}}
.detbody{{background:#252525;border:1px solid #3a3a3a;border-radius:6px;
  padding:8px 14px;margin:4px 0 8px 0;font-size:13px;line-height:1.5;}}
.detbody .mut{{color:{DARK_MUTED};}}
"""

# rows: [STAT_KEYS index, label, decimals, good direction (+1/-1/0), suffix]
_ROWS_JS = """
const ROWS = [
  [0,  'Damage / volley vs shields', 0, 1, ''],
  [1,  'Damage / volley vs hull',    0, 1, ''],
  [2,  'Fire rate',                  2, 1, ' /s'],
  [3,  'Cool rate',                  0, 1, ' heat/s'],
  [4,  'Time to overheat (cold)',    1, 1, ' s'],
  [5,  'Full cool-down',             1, -1, ' s'],
  [6,  'Full cycle time',            1, 0, ' s'],
  [7,  'Shots per cycle',            1, 1, ''],
  [8,  'Damage per cycle vs shields', 0, 1, ''],
  [9,  'Damage per cycle vs hull',   0, 1, ''],
  [10, 'Full-cycle DPS vs shields',  1, 1, ''],
  [11, 'Full-cycle DPS vs hull',     1, 1, ''],
  [12, 'Steady-state firing',        1, 1, ' s'],
  [13, 'Steady-state cooldown',      1, -1, ' s'],
  [14, 'Steady-state duty cycle',    0, 1, ' %'],
  [15, 'Steady-state DPS vs shields', 1, 1, ''],
  [16, 'Steady-state DPS vs hull',   1, 1, ''],
];
"""

_JS = """
const QNAMES = {1:'Mk1', 2:'Mk2', 3:'Mk3'};
const sel = document.getElementById('weapon');
const groups = {};
WEAPONS.forEach((w, i) => {
  if (!groups[w.g]) {
    groups[w.g] = document.createElement('optgroup');
    groups[w.g].label = w.g;
    sel.appendChild(groups[w.g]);
  }
  const o = document.createElement('option');
  o.value = i; o.textContent = w.n + '  [' + w.id + ']';
  groups[w.g].appendChild(o);
});

function fmt(v, dec) {
  return v.toLocaleString('en-US',
    {minimumFractionDigits: dec, maximumFractionDigits: dec});
}
// literal-multiply rule: the optimal end of a roll range depends on how the
// weapon stores the stat (reload rate wants max, reload time wants min)
function applied(stat, lo, hi, rk) {
  if (stat === 'chargetime') return Math.min(lo, hi);
  if (stat === 'reload' && rk === 'time') return Math.min(lo, hi);
  return Math.max(lo, hi);
}
function range(lo, hi) {
  return '\\u00d7' + lo + '\\u2013' + hi;
}
function visibleMods() {
  return MODS.filter(m =>
    document.getElementById('q' + m.q).checked);
}

function render() {
  const w = WEAPONS[+sel.value];
  const mods = visibleMods();
  document.getElementById('notes').innerHTML =
    w.notes.map(n => '<p class="note">' + n + '</p>').join('');

  const head = ['<tr><th></th><th><span class="mn">Bare</span></th>'];
  mods.forEach(m => {
    const noeff = w.mods[m.w] === 0;
    const ap = applied(m.s, m.min, m.max, w.rk);
    const forced = m.forced.map(b =>
      b.s + ' ' + range(b.min, b.max) + ' (applied \\u00d7'
      + applied(b.s, b.min, b.max, w.rk) + ')').join('; ');
    const title = 'Primary ' + m.s + ' ' + range(m.min, m.max)
      + ' (optimal \\u00d7' + ap + ')'
      + (forced ? ' | forced: ' + forced : '')
      + (m.pool.length ? ' | may also roll: '
         + m.pool.map(b => b.s).join(', ') : '')
      + ' | ' + m.w;
    head.push('<th' + (noeff ? ' class="noeff"' : '') + ' title="'
      + title.replace(/"/g, '&quot;') + '">'
      + '<span class="mn">' + m.n + ' <span class="q' + m.q + '">'
      + QNAMES[m.q] + '</span></span>'
      + '<span class="rng">' + m.s + ' ' + range(m.min, m.max) + '</span>'
      + (noeff ? '<span class="rng">(no effect)</span>' : '')
      + '</th>');
  });
  head.push('</tr>');

  const body = [];
  ROWS.forEach(r => {
    const [idx, label, dec, dir, suffix] = r;
    const pct = suffix === ' %';
    const scale = pct ? 100 : 1;
    const bare = w.bare[idx];
    const cells = ['<tr><th>' + label + '</th>'];
    cells.push('<td class="base">' + (bare === null ? '\\u2014'
      : fmt(bare * scale, dec) + suffix) + '</td>');
    mods.forEach(m => {
      const vec = w.mods[m.w] === 0 ? w.bare : w.mods[m.w];
      const v = vec[idx];
      const noeff = w.mods[m.w] === 0;
      if (v === null) {
        cells.push('<td' + (noeff ? ' class="noeff"' : '')
          + '>\\u2014</td>');
        return;
      }
      let delta = '';
      if (bare !== null && bare !== 0 && Math.abs(v - bare) > 1e-9) {
        const p = (v / bare - 1) * 100;
        const cls = dir === 0 ? 'same'
          : (p * dir > 0 ? 'up' : 'down');
        delta = '<span class="delta ' + cls + '">'
          + (p >= 0 ? '+' : '') + p.toFixed(1) + '%</span>';
      }
      cells.push('<td' + (noeff ? ' class="noeff"' : '') + '>'
        + fmt(v * scale, dec) + suffix + delta + '</td>');
    });
    cells.push('</tr>');
    body.push(cells.join(''));
  });
  document.getElementById('stats').innerHTML =
    '<thead>' + head.join('') + '</thead><tbody>' + body.join('')
    + '</tbody>';

  // expandable per-mod detail: full ranges, forced bonuses at the applied
  // roll, and the optional weighted pool that is NOT in the table numbers
  const det = mods.map(m => {
    const ap = applied(m.s, m.min, m.max, w.rk);
    let b = '<div class="detbody"><b>' + m.n + '</b> <span class="q'
      + m.q + '">' + QNAMES[m.q] + '</span> <span class="mut">('
      + m.w + ')</span><br>'
      + 'Primary: ' + m.s + ' ' + range(m.min, m.max)
      + ' \\u2014 applied at optimal \\u00d7' + ap + '<br>';
    if (m.forced.length) {
      b += 'Forced bonuses (always present, applied at their best value '
        + 'for this weapon):<br>' + m.forced.map(x =>
          '\\u2022 ' + x.s + ' ' + range(x.min, x.max) + ' \\u2192 applied '
          + '\\u00d7' + applied(x.s, x.min, x.max, w.rk)).join('<br>')
        + '<br>';
    }
    if (m.pool.length) {
      b += 'Possible extra bonuses (weighted roll, NOT included in the '
        + 'table):<br>' + m.pool.map(x =>
          '\\u2022 ' + x.s + ' ' + range(x.min, x.max) + ' (weight '
          + x.wt + ')').join('<br>') + '<br>';
    }
    return '<details><summary>' + m.n + ' \\u2014 ' + QNAMES[m.q] + ' '
      + m.s + ' mod</summary>' + b + '</div></details>';
  });
  document.getElementById('moddetail').innerHTML = det.join('');
}

sel.addEventListener('change', render);
['q1', 'q2', 'q3'].forEach(id =>
  document.getElementById(id).addEventListener('change', render));
if (WEAPONS.length) { sel.value = 0; render(); }
"""


def build_gamedata_dashboard(cfg: Config) -> int:
    game_dir = cfg.resolve_game_dir()
    log("Indexing game catalogs:", game_dir)
    gf = GameFiles(game_dir)
    log("Extracting weapons and equipment mods")
    weapons, mods = build_weapon_data(gf)

    def emb(obj) -> str:
        return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>X4 game data — weapon mods</title>
<style>{_CSS}</style></head><body>
<header><h2>X4 game data analysis
<small>built from the installed game files (base + DLC)</small></h2></header>
<nav><button class='active'>Weapon Mods</button></nav>
<section>
<p>
<label for='weapon'>Weapon:</label><select id='weapon'></select>
&nbsp;&nbsp;<label>Mod quality:</label>
<label><input type='checkbox' id='q1' checked> Mk1</label>
<label><input type='checkbox' id='q2' checked> Mk2</label>
<label><input type='checkbox' id='q3' checked> Mk3</label>
</p>
<div id='notes'></div>
<p class='note'>Each mod column applies the mod at its OPTIMAL roll
(hover a column header for the roll range and applied multipliers; a mod
multiplies the stat field exactly as the game stores it). Forced negative
bonuses are taken at their least-bad value. Optional weighted bonuses are
NOT included — expand a mod below the table to see them. Damage per volley
= (value + shield/hull bonus) &times; projectiles per volley; vs-shield
and vs-hull damage apply the bullet's shield/hull attributes on top of its
base value.</p>
<div class='tblwrap'><table id='stats'></table></div>
<h3 style='font-size:15px;margin-bottom:4px'>Mod details</h3>
<div id='moddetail'></div>
</section>
<script>
const WEAPONS = {emb(weapons)};
const MODS = {emb(mods)};
{_ROWS_JS}
{_JS}
</script></body></html>"""

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.output_dir / "gamedata_dashboard.html"
    out.write_text(html, encoding="utf-8")
    log("Wrote", out)
    return 0
