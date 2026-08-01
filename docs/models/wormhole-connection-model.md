# How X4 wormholes / anomalies connect (current understanding)

Reference for the wormhole map-overlay feature. Assembled 2026-07-22 from a
full-galaxy sweep of one 600h save (41 anomalies) plus the object structure in
the save XML; revised 2026-07-24 (backlog B4): the direction rule was
re-derived — and inverted — from the DLC script wiring plus a 13-save sweep,
and the link census is now known to be tide-cycled (details in their
sections). Confidence tags:

- **[OBS]** — directly observed in save data (with evidence).
- **[SCRIPT]** — read from the game's own mission scripts (authoritative for
  intent, but the in-game traversal itself has not been play-tested).
- **[INF]** — inferred/consistent-with, not independently verified.

## The one-paragraph model

Every "anomaly" in the galaxy — the scannable lore swirls **and** the story
warp points — is the same object: `class="anomaly"`, macro
`wormhole_v1_macro` (or `wormhole_v1_standalone_macro`), carrying a gravity
well. What separates a decoration from a working warp is **two optional
children**: a `<transition destination="N">` marks it as a *story* warp (N=0
while dormant), and a `<connections>` block **links it to a partner**. A
wormhole with a partner link is an active warp; you can resolve exactly where
it goes from the save alone. A wormhole with only a transition is a dormant
story warp whose exit is wired up at runtime by the mission director and is
**not** predictable from the save. A wormhole with neither is a **random**
wormhole — the god-placed "Unstable Warp Anomaly": flying into one
teleports the ship to another random wormhole, the exit rolled at transit
time, which is exactly why the save stores no destination for it
(player-verified in game, 2026-08-01 — E-149; this doc previously called
the tier inert scenery, which is FALSIFIED).

## The three tiers [OBS]

Sweeping the test save found **41** anomalies, all `class="anomaly"`:

| Tier | Count | `<transition>` | `<connections>` | Meaning |
|------|-------|----------------|-----------------|---------|
| **random** | 30 | — | — | **Unstable Warp Anomaly**, god-placed; transit exits at another random wormhole (E-149), so no destination is persisted. |
| **dormant** | 7 | `destination="0"` | — | Story warp, destination not yet assigned. All in Avarice (`cluster_500`, Tide of Avarice `S2A_/S2B_/S2C_` entries). |
| **linked** | 4 | some | yes | Actively paired warp — the exit is resolvable. |

The census is **stable across saves, except that the linked tier's *edge
set* is tide-cycled** (see the tide-cycle section): during an Avarice wave
window the WHT-407/IVC-752 pair temporarily gains a second, reverse link
(4 rows instead of 2), reverting on deactivation. The tier of every
anomaly — which of random/dormant/linked it is — did not change in any
observed save: a 13-save sweep (2026-07-24, game time 64,377–78,583 s,
~3.9 game-hours) reproduced 30/7/4 with byte-identical link rows in every
save, all calm-phase. [OBS]

### What the random tier actually is [OBS]

*(This section was titled "What the inert tier actually is" until
2026-08-01 — the game-file facts below all stand, but the conclusion
drawn from them was wrong; see the correction at the end.)*

Verified against the game files (not inferred). The macro
`wormhole_v1_macro` (`assets/environments/asteroids/macros/`) is
`class="anomaly"` with name text `{20109,4901}` = **"Unstable Warp Anomaly"**
and `inactivename="Too unstable to be active"`. It carries a
`<longrangescan minlevel="1">` (so it shows as a scannable long-range signal)
and a gravity `<force range="8000" strength="-2.52e7">` well — but the macro
defines **no transition and no connections**.

The base game's `libraries/god.xml` statically places **exactly 30** of them,
one per base-game sector, each `id="<sector>_anomaly_01"`
(`thevoid_anomaly_01`, `nopileosfortune_anomaly_01`, …). A sweep of all 9,215
game XML files finds those entry ids **only in `god.xml`** — **no script ever
activates them.**

**Correction (2026-08-01, E-149):** "no script activates them" does NOT mean
"no warp at all" — that conclusion is **FALSIFIED** by in-game observation:
the player flew through them repeatedly and was teleported to another
random wormhole each time. The transit is engine-native `class="anomaly"`
behaviour needing no script and no persisted destination — the exit is
rolled at transit time, which is precisely why these carry neither
`<transition>` nor `<connections>` in the save. The absence of a link
identifies the tier; it never implied inactivity. Whether the random exit
pool includes the dormant/linked warps or only other unpaired anomalies is
unprobed.

Every *functional* warp is a **different** object from the base-game 30 —
but functional does **not** mean script-created (an earlier revision claimed
that; the doc's own excerpts refute it). Two provenances exist among the 11
functional warps of this galaxy:

- **God-placed by a DLC's own `god.xml`** (`<source class="godobject">`):
  all 8 Avarice warps (`S2A_/S2B_/S2C_` entries, including the *linked*
  WHT-407) and Unknown System's IVC-752 (`S3_anomaly_01`). Scripts don't
  create these — `setup_dlc_pirate.xml` only *wires* them, looking them up
  by `godobjectentry` and calling `add_anomaly_destination`.
- **Script-created at runtime** (`<source class="script">`): only the
  Freedom's Reach pair (`md/placedobjects.xml`).

What stays true is that the *base-game* god-placed 30 are never activated
by any script; activation machinery (`add_anomaly_destination`, renaming to
`{20109,4911}` = **"Stable Warp Anomaly"**) is also called from Boso Ta's
"The Anomalies" (`md/story_research_welfare_1.xml`), Timelines scenario
maps, and two further scripts (call-site sweep, 2026-07-23 review W6).

## How a link is encoded [OBS]

A linked wormhole owns one or more `<connection>` elements, each of which
points at a **partner's** connection id:

```xml
<!-- WHT-407, Avarice V Dead End (cluster_500_sector002), id [0x30184] -->
<component class="anomaly" macro="wormhole_v1_macro" code="WHT-407" id="[0x30184]">
  <source entry="S2B_anomaly_01" class="godobject"/>
  <transition destination="0"/>
  <connections>
    <connection connection="origin" id="[0x30185]">
      <connected connection="[0x88d11]"/>       <!-- -> IVC-752's connection -->
    </connection>
  </connections>
</component>

<!-- IVC-752, Unknown System (cluster_504_sector001), id [0x88d10] -->
<component class="anomaly" macro="wormhole_v1_standalone_macro" code="IVC-752" id="[0x88d10]">
  <source entry="S3_anomaly_01" class="godobject"/>
  <connections>
    <connection connection="destination" id="[0x88d11]">
      <connected connection="[0x30185]"/>       <!-- -> WHT-407's connection -->
    </connection>
  </connections>
</component>
```

## The prediction rule [OBS]

**Build a map of `connection id -> owning wormhole`, then resolve each
`<connected connection="X"/>` to the wormhole that owns X.** This is exact and
bidirectional — no arithmetic, no guessing:

- `WHT-407` owns connection `[0x30185]`; its `<connected>` points at
  `[0x88d11]`, which `IVC-752` owns → **WHT-407 pairs with IVC-752**.
- `IVC-752` owns `[0x88d11]`; its `<connected>` points at `[0x30185]`, which
  `WHT-407` owns → the reverse confirms the same pair.

(This resolves *pairing* only — which anomaly mates which. Traversal
direction is the role question below.)

**Direction** comes from the `connection` role, and the role names the
**partner**, not the owner: a wormhole owning a `destination`-role
connection is an **entry** (its connection points at its destination — the
exit); a wormhole owning an `origin`-role connection is an **exit** (its
connection points back at its origin — the entry). So the flow is
**IVC-752 (owns `destination`, Unknown System) → WHT-407 (owns `origin`,
Dead End)**: you enter at IVC-752 and come out at WHT-407. The map draws
the arrow from the `destination`-role owner to its target. [SCRIPT+OBS]

An earlier revision read the roles the other way ("origin = entry") and had
this arrow backwards. It calibrated on zero discriminating cases (Freedom's
Reach is symmetric); the galaxy's only asymmetric pair settles it:
`setup_dlc_pirate.xml` wires the permanent link with
`add_anomaly_destination anomaly=<S3_anomaly_01 = IVC-752>
destination=<S2B_anomaly_01 = WHT-407>`, comment *"exit from S3 into S2
(not tied to the wave)"* — the `anomaly=` argument is the enterable end, and
in every save that end (IVC-752) owns the `destination`-role connection
(13/13 saves, byte-stable). The re-derived rule is **[SCRIPT]**-grade:
definitive at the script/save level, but the fly-both-ends in-game
confirmation (backlog B4's play half) is still pending.

A **two-way** wormhole owns *both* roles and appears as a mirror pair. The
galaxy's one always-on example is in **Freedom's Reach** (`cluster_714`):
`ZIT-073` and `IZL-415` each own an `origin` **and** a `destination`
connection cross-linked to the other, so the pair is traversable both ways
(rendered as two opposing arrows — under the corrected rule each
`destination`-role link contributes one arrow). These two are
`<source class="script">` (placed at runtime), not godobjects, and both are
`knownto="player"`.

### The Avarice link is tide-cycled [SCRIPT]

The S3↔S2B pairing is wired at universe generation — no story condition —
and only in the S3→S2 direction (the `add_anomaly_destination` call above).
Each Avarice tide wave then **adds the reverse direction and removes it
again**: `TheWave_Anomaly_Activate` calls `add_anomaly_destination
anomaly=<WHT-407> destination=<IVC-752>` and `TheWave_Anomaly_Deactivate`
removes exactly that link (setup_dlc_pirate.xml, cues at lines ~2514/2525).
So during a wave window the pair is two-way (4 link rows); in a calm phase
it is one-way S3→S2 (2 rows). All 13 archived saves are calm-phase — the
4-row state has not yet been captured in a save. Tier assignments do not
change with the tide (both ends stay "linked"); only the edge's
one-way/two-way state does, so a map built from a wave-window save would
show one extra arrow, not a different census.

*(Incidental observation: a wormhole's own warp connection id is its component
id + 1, and a two-way one also owns +2. This is just id-allocation order and
is **not** relied on — the ownership map is authoritative and handles multiple
connections per wormhole cleanly.)*

## What is and isn't predictable

- **Linked wormholes** → fully predictable from the save — for the moment
  the save was written; the Avarice pair's second (reverse) direction comes
  and goes with the tide, so a link census is a snapshot, not a constant.
  [OBS/SCRIPT]
- **Dormant story warps** (`transition destination="0"`, no `<connections>`) →
  **not** predictable. The 7 Avarice `S2A_/S2B_/S2C_` warps have no partner in
  the save; the Tide of Avarice mission script assigns their destinations when
  the story activates them. We can identify them as dormant and name their
  `source entry`, but the exit is genuinely absent until runtime. [INF]
- **Random Unstable Warp Anomalies** → a working warp whose exit is rolled
  at transit time and never persisted — identifiable from the save,
  destination fundamentally unpredictable from it (E-149; the earlier "no
  warp at all, ever" reading is FALSIFIED). [OBS in-game]

The intended (but not-yet-wired) ToA pairing is visible in the entry ids:
`S2B_anomaly_01` (the one already linked) mates the `S3_anomaly_01` end in
Unknown System, and the remaining `S2B_*` warps in Dead End are its siblings.

## Scope: game-file claims are vanilla+DLC only (B13)

Every game-file sweep behind this doc ("all 9,215 game XML files",
"no script ever activates them") ran over the cat-indexed vanilla+DLC
virtual filesystem — `GameFiles` loads 7 of the 74 installed extensions
(see csv-reference.md's trust-scope note) — while the analyzed saves are
`modified="1"`. **Save-side** facts (the 41-anomaly census, link rows,
roles) see everything, mods included; **file-side** universal claims are
vanilla+DLC-scoped. This is not hypothetical: the install carries a
(currently disabled) mod, `new_anomaly_sbh_toa`, whose `ext_01.cat`
patches `wormhole_v1_macro.xml` / `wormhole_v1_standalone_macro.xml` and
adds a new anomaly asset — if the user enabled it, the macro-level facts
above would need re-verification against the patched files, and a new
anomaly could appear in saves with no vanilla explanation.

## Where it lives in the code

- `save/parser.py` — collects every `class="anomaly"` in the single pass:
  `d.wormholes` (one row each, with sector-local position via the vault-style
  offset walk) and `d.wormhole_links` (one row per `<connection>`: own id,
  role, target id).
- `db/schema.py` + `db/store.py` — `wormhole` + `wormhole_link` world tables.
- `analysis/frames.py` — reads them into `frames.wormholes` / `wormhole_links`.
- `viz/map.py` `_payload` — resolves partners via the ownership map, tiers each
  wormhole, and emits `wormholes` (markers) + `wlinks` (directed edges, one per
  `destination`-role link, arrow entry→exit per the corrected rule),
  spoiler-filtered (an edge is dropped if either endpoint is undiscovered).
- `viz/map_page.js` — violet ring markers (solid = linked, dashed = dormant,
  dot = random) and dashed arrowed link lines, one **Wormholes** legend toggle.
