# How X4 wormholes / anomalies connect (current understanding)

Reference for the wormhole map-overlay feature. Assembled 2026-07-22 from a
full-galaxy sweep of one 600h save (41 anomalies) plus the object structure in
the save XML. Confidence tags:

- **[OBS]** — directly observed in save data (with evidence).
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
**not** predictable from the save. A wormhole with neither is an inert
**Unstable Warp Anomaly** — a god-placed scenery object, permanently "too
unstable to be active."

## The three tiers [OBS]

Sweeping the test save found **41** anomalies, all `class="anomaly"`:

| Tier | Count | `<transition>` | `<connections>` | Meaning |
|------|-------|----------------|-----------------|---------|
| **inert** | 30 | — | — | **Unstable Warp Anomaly**, one per base-game sector, permanently inactive. |
| **dormant** | 7 | `destination="0"` | — | Story warp, destination not yet assigned. All in Avarice (`cluster_500`, Tide of Avarice `S2A_/S2B_/S2C_` entries). |
| **linked** | 4 | some | yes | Actively paired warp — the exit is resolvable. |

### What the inert tier actually is [OBS]

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
activates them.** They are permanent scenery: the "unstable" cousins of the
functional warps, forever too unstable to be active.

Every *functional* warp is a **different** object that a story script
`create_object`s at runtime and pairs with `add_anomaly_destination`
(renaming it `{20109,4911}` = **"Stable Warp Anomaly"**): Boso Ta's "The
Anomalies" (`md/story_research_welfare_1.xml`), Tide of Avarice
(`setup_dlc_pirate.xml` — the dormant Avarice tier), Timelines wave attacks,
and the Freedom's Reach pair (`md/placedobjects.xml`). So the god-placed 30 and
the script-placed warps never overlap.

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
  `[0x88d11]`, which `IVC-752` owns → **WHT-407 ⟶ IVC-752**.
- `IVC-752` owns `[0x88d11]`; its `<connected>` points at `[0x30185]`, which
  `WHT-407` owns → the reverse confirms the same pair.

**Direction** comes from the `connection` role: the end labelled `origin` is
the entry, the end labelled `destination` is the exit. So the flow is
WHT-407 (origin, Dead End) → IVC-752 (destination, Unknown System). The map
draws the arrow origin→destination.

A **two-way** wormhole owns *both* roles and appears as a mirror pair. The
galaxy's one active example is in **Freedom's Reach** (`cluster_714`):
`ZIT-073` and `IZL-415` each own an `origin` **and** a `destination`
connection cross-linked to the other, so the pair is traversable both ways
(rendered as two opposing arrows). These two are `<source class="script">`
(placed at runtime), not godobjects, and both are `knownto="player"`.

*(Incidental observation: a wormhole's own warp connection id is its component
id + 1, and a two-way one also owns +2. This is just id-allocation order and
is **not** relied on — the ownership map is authoritative and handles multiple
connections per wormhole cleanly.)*

## What is and isn't predictable

- **Linked wormholes** → fully predictable from the save. [OBS]
- **Dormant story warps** (`transition destination="0"`, no `<connections>`) →
  **not** predictable. The 7 Avarice `S2A_/S2B_/S2C_` warps have no partner in
  the save; the Tide of Avarice mission script assigns their destinations when
  the story activates them. We can identify them as dormant and name their
  `source entry`, but the exit is genuinely absent until runtime. [INF]
- **Inert Unstable Warp Anomalies** → no warp at all, ever (verified above). [OBS]

The intended (but not-yet-wired) ToA pairing is visible in the entry ids:
`S2B_anomaly_01` (the one already linked) mates the `S3_anomaly_01` end in
Unknown System, and the remaining `S2B_*` warps in Dead End are its siblings.

## Where it lives in the code

- `save/parser.py` — collects every `class="anomaly"` in the single pass:
  `d.wormholes` (one row each, with sector-local position via the vault-style
  offset walk) and `d.wormhole_links` (one row per `<connection>`: own id,
  role, target id).
- `db/schema.py` + `db/store.py` — `wormhole` + `wormhole_link` world tables.
- `analysis/frames.py` — reads them into `frames.wormholes` / `wormhole_links`.
- `viz/map.py` `_payload` — resolves partners via the ownership map, tiers each
  wormhole, and emits `wormholes` (markers) + `wlinks` (directed edges),
  spoiler-filtered (an edge is dropped if either endpoint is undiscovered).
- `viz/map_page.js` — violet ring markers (solid = linked, dashed = dormant,
  dot = inert) and dashed arrowed link lines, one **Wormholes** legend toggle.
