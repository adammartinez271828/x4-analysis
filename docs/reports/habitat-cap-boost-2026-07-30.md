# Registering `nd_habitat_cap_boost` (E-061) — 2026-07-30

Plan item **P7** of [../plans/model-gaps-2026-07-29.md](../plans/model-gaps-2026-07-29.md).
Snapshot basis: analysis DB `x4_8E0C8E37-…`, `save_id` **71** (`save_002`,
game time 82,688). Nothing was written to the DB and no reference CSV was
regenerated; the mod's values reach a run through
`gamedata/modpatch.py` only.

## 1. What the mod actually does

`/games/SteamLibrary/…/extensions/nd_habitat_cap_boost` (`ws_3737446888`,
"Habitat Capacity Boost", v100, author Ninja_Dog81) ships **26 files, all of
them `<diff>` documents with exactly one op**:

```xml
<diff>
  <replace sel="/macros/macro/properties/workforce/@capacity">2500</replace>
</diff>
```

So it moves `<workforce capacity>` — the **housing** column of `modcaps.csv` —
and nothing else. It does **not** touch `<workforce max>`, the employment-target
term of E-124. E-061's phrasing ("replaces habitat `<workforce max>`") is
inaccurate on that point; the register's own prediction line
(`hab_arg_s_01_macro` 250 → 2,500) is correct and is what the files say.

Two further corrections to E-061's numbers:

* **Stock is not one triple.** 333/666/999 are the *Paranid* values. Measured
  stock housing per race: arg/bor/pir/spl/tel 250/500/1000, par 333/666/999,
  ter 100/250/500, plus the two Antigone landmarks 1000/2000. The mod flattens
  everything by SIZE (S 2500 / M 5000 / L 10000) and gives the landmarks
  15,000 / 20,000, so the boost is **7.51× (par M/L) to 25× (ter S)**, not a
  single ratio.
* **Affected built modules on snapshot 71 = 1,839, not 2,499** — 1,830
  `hab_*` plus 8 Antigone pillars and 1 spire, counted on `v_built_module`
  (2,103 including unbuilt plan entries; the double-listed build plan is
  already excluded by the view). 1,254 of the save's 1,771 module-bearing
  stations carry at least one boosted module.

Three of the mod's targets — `hab_par_m_02_macro`, `hab_par_s_02_macro`,
`hab_par_s_03_macro` — exist in no installed content. They are kept verbatim in
the registry and simply find no row to patch.

| macro | stock | mod | ×  |
|---|---|---|---|
| hab_{arg,bor,pir,spl,tel}_{s,m,l}_01 | 250 / 500 / 1000 | 2500 / 5000 / 10000 | 10.0 |
| hab_par_{s,m,l}_01 | 333 / 666 / 999 | 2500 / 5000 / 10000 | 7.51 / 7.51 / 10.01 |
| hab_ter_{s,m,l}_01 | 100 / 250 / 500 | 2500 / 5000 / 10000 | 25.0 / 20.0 / 20.0 |
| landmarks_arg_antigonepillar_01 | 1000 | 15000 | 15.0 |
| landmarks_arg_antigonespire_01 | 2000 | 20000 | 10.0 |

23 of the 247 `modcaps` rows change. Save-wide built housing capacity goes
**1,155,002 → 11,754,500 (×10.18)**.

## 2. Detection route: exact, by extension id

The mod is **`save="true"`** — the savegame's `<patches>` block records

```xml
<patch extension="ws_3737446888" version="100" name="Habitat Capacity Boost"/>
```

which `save/parser.py` already collects into `SaveData.extensions`. So no
fingerprint is needed and none is registered (`fingerprint_ware=None`): the
patch fires **iff** the save names the extension.

**Failure modes of this route**, stated plainly:

* *False positive on an unmodded save:* impossible. Nothing but the recorded
  extension id can trigger it — verified by a test that an empty extension
  list and an unrelated id both detect nothing.
* *False negative:* a save made with the mod's files present but the extension
  disabled at the time of saving, or a differently-packaged rebuild of the same
  mod under another id, is not detected and keeps stock housing — the current,
  known-wrong behaviour, i.e. no worse than before.
* *Version drift:* detection ignores the version field, so a future version of
  the mod with different numbers would be detected and patched with the OLD
  numbers. Guarded by `test_registry_matches_the_installed_mod_files`, which
  re-reads the installed mod's XML and fails if the registry disagrees (skipped
  when the mod is not installed).

## 3. The two recorded blockers, and how far the extraction was extended

E-061's blockers were (a) `extract_modcaps` cannot read `<diff>` files with no
`<macro>` element and (b) `extract_wares` handles only `<add sel=…>`, never
`<replace>`. Only (a) is in this mod's path — it ships no `wares.xml` — so (b)
was left alone rather than extended speculatively.

`gamedata/extract.py` gained the minimum:

* `macro_attr_diffs(root)` — returns `{(properties-child, attribute): value}`
  for a `<diff>` of `<replace sel="/macros/macro/properties/X/@a">` ops, and
  `{}` for anything else (including a normal `<macros>` document, so callers
  can hand it any parsed macro file).
* `extract_modcaps` now collects those ops keyed on the file's **basename**
  (X4's one-macro-per-file convention) and applies them after the main pass,
  mapping `workforce/@capacity → housing`, `workforce/@max → workers`,
  `cargo/@max`, `cargo/@tags`, `storage/@unit`. A diff for a macro no full
  document defined is dropped rather than inventing a half-empty row.
* The glob's extension segment became repeatable,
  `(extensions/[^/]+/)*assets/structures/…` — a mod packs its per-DLC overrides
  under the DLC's own path (`extensions/nd_habitat_cap_boost/extensions/
  ego_dlc_terran/assets/…`), which the single-segment pattern never matched.

**The committed CSVs are unaffected**, and this was verified rather than
assumed: re-running `extract_modcaps` against a stock `GameFiles` (base + DLC,
which is all `extract-gamedata` ever loads) reproduces `data/modcaps.csv`
exactly — 247 rows, zero differing cells in any column. No base or DLC macro
file under `assets/structures` is a `<diff>`, so the new branch is dead code on
stock content. With `nd_habitat_cap_boost` added to the extension list, all 23
macros read the boosted values — that path is exercised only by the test.

## 4. Where the value flows — measured, not assumed

`ref.modcaps["housing"]` has exactly **one consumer in `src/`**:
`viz/audit.py` § staffing, which sums housing over a player station's built
modules and prints the `Housing` column plus a "not enough housing" warning
when `housing < Σ workers`. `analysis/storage.py` uses `workers`, `cargo_max`,
`cargo_tags`; `analysis/drones.py` uses `unit_storage`; neither reads
`housing`, and E-124 excludes it from the employment target **by law**. The DB
mirrors the patched value into `module_cap.housing` (`write_reference` runs
after `patch_reference` in `analyze.py`, and the reference digest covers the
rows, so the next pipeline run rewrites the table).

So the honest statement of impact: **the plan's expectation that this feeds
ration buffers and efficiency is not borne out — nothing in the storage or
pricing model consumes habitat housing.** Registering the mod makes a
known-wrong input correct and unblocks anything that later wants a true housing
capacity (workforce-growth interpretation is the obvious candidate); today it
fixes one widget.

### Before / after on snapshot 71

Recomputed off the DB's built modules with stock vs patched `modcaps`:

| population | n | metric | stock | patched |
|---|---|---|---|---|
| player stations with worker demand (the audit's own population) | 6 | stations flagged "not enough housing" | **6** | **5** |
| all stations with worker demand | 1,273 | housing < worker demand | **413** | **59** |
| all built modules on affected macros | 1,839 | Σ housing capacity | 1,155,002 | 11,754,500 |

The one player station that changes is **MXH-411 (Fabrication Complex TI)**:
4 Terran habitats, worker demand 22,130, live workforce 959. Stock housing
2,000 → flagged; patched 40,000 → not flagged. The flag was a false positive:
in game those habitats really do house 40,000. The other five player stations
(JQR-498, MAL-475, QNF-337, TIH-455, ABR-398) carry **no** habitat module at
all — housing 0 either way — so they stay flagged, correctly.

Save-wide, 59 stations still have housing below their worker demand after the
boost; that is a property of NPC station designs, not of the patch.

## 5. Tests and regressions

* `uv run pytest -q` — **286 passed** (277 baseline + 9 new in
  `tests/test_modpatch_habitat.py`). No existing test file was edited.
* `uv run python tests/readings.py` — **131/132** in-game readings within 1 %,
  133/137 overall: **unchanged**, and it cannot change — the readings fixture
  drives `analysis/storage.py`, which never reads `housing`.
* New tests cover: reading a `<replace>` diff with no `<macro>`; rejecting
  non-diffs and unknown ops; `extract_modcaps` applying a diff and dropping one
  for an unknown macro (incl. the doubly-nested extension path); detection
  firing on the id and *only* on the id; the patch being a copy that leaves the
  loaded frame untouched; every other `modcaps` column surviving; and the
  registry equalling the installed mod's own XML.

## 6. Register recommendation (for the Phase 4 docs-sync agent)

**E-061 → CONFIRMED**, with the claim restated to what the files say:

> `nd_habitat_cap_boost` (`ws_3737446888`, `save="true"`) replaces habitat
> `<workforce capacity>` — housing, not the employment target — flattening it
> by size to S 2500 / M 5000 / L 10000 (Antigone pillar 15000, spire 20000)
> against per-race stock of 250/500/1000 (par 333/666/999, ter 100/250/500),
> i.e. 7.51×–25×. It touches 1,839 built modules over 1,254 stations on
> snapshot 71.

Evidence: the mod's own packed XML, read through the extended
`extract_modcaps`; detection is exact on the recorded extension id; the values
are applied at runtime in `gamedata/modpatch.py` and the committed CSVs verify
byte-identical against stock content.

Register/reference edits worth making at the same time, all of them mine to
recommend and none of them mine to write:

1. E-061's "333/666/999 vs stock" and "2,499 modules" numbers are wrong —
   correct them as above.
2. E-061's second blocker, "`extract_wares` handles only `<add sel=…>`, never
   `<replace>`", is **still open and still true**; it is unrelated to this mod
   and should survive as its own entry (suggest a NEW id rather than keeping
   E-061 open for it), since a future wares-rewriting mod will hit it.
3. Worth stating in `reference/save-semantics.md` § Mod-aware reference data:
   detection now has three shapes, not two — extension id (exact, for
   `save="true"` mods), value fingerprint (for `save="false"` mods), and the
   patch target is now either recipes (wholesale) or `modcaps` fields
   (attribute-level, because that is the shape of the diffs).
4. `csv-reference.md` § Extraction and override machinery: macro files may be
   `<diff>` documents applied by basename, and the extension path segment
   repeats for a mod's per-DLC overrides.
5. E-124 is untouched and should say so explicitly if habitat housing is
   mentioned: the boost cannot move the employment target, because the mod
   never writes `<workforce max>`.
