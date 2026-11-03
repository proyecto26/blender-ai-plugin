# Reference Image Match Workflow

**Mandatory when the user attaches a photo, concept art, or render and asks to match, recreate, or build "like this."**

Goal: produce a Blender result that is **visually similar** to the reference — silhouette, proportions, materials, lighting, camera, and mood. "Exact" pixel match is not realistic; **iterative visual convergence** is.

## Golden Rules

1. **Analyze the reference BEFORE any Blender operations** — output a Reference Analysis (see template below).
2. **Never skip the screenshot comparison loop** — render/viewport capture after every major phase.
3. **Execute via Blender MCP** — do not narrate UI steps when MCP is connected.
4. **Upgrade in place** when a `.blend` already exists — do not rebuild from scratch unless asked.
5. **Separate emissive lights from hull materials** — never keyframe shared structural materials (causes blown-out white hull).
6. **Match camera early** — wrong framing makes every other pass look wrong.
7. **Depth before micro-detail** — panel breaks, recesses, ribs, and silhouette tiers before tiny greebles.

## Workflow Overview

```
REFERENCE ANALYSIS (written brief)
        ↓
CAMERA + FRAMING MATCH
        ↓
SILHOUETTE + PROPORTION BLOCKOUT
        ↓
PRIMARY SHAPES + SECONDARY PANEL BREAKS
        ↓
TERTIARY GREEBLES + FEATURES
        ↓
MATERIALS + COLOR PALETTE
        ↓
LIGHTING + ENVIRONMENT
        ↓
RENDER SETTINGS + COLOR GRADING
        ↓
SCREENSHOT COMPARE → FIX GAP LIST → REPEAT (max 3 passes)
        ↓
VALIDATION (visual-match-checklist.md)
```

## Phase 0 — Reference Analysis (Required)

Before MCP execution, document:

| Category | Extract from image |
|----------|-------------------|
| **Subject** | Asset type, hero vs background, forward axis |
| **Silhouette** | Overall shape language (blocky, curved, tapered), major masses |
| **Proportions** | Length/width/height ratios, nose/tail/engine balance |
| **Camera** | Angle (3/4, side, low, high), lens feel (wide/normal/tele), subject fill % |
| **Lighting** | Key direction, fill level, rim/back light, ambient color |
| **Materials** | Metal vs paint vs glass; roughness (matte/satin/gloss); weathering level |
| **Color palette** | 5–8 hex values: hull light, hull dark, recess, trim, emissive, sky/ambient |
| **Unique features** | Decals, windows, antennas, planet/env, volumetrics |
| **Mood** | Industrial, horror, cinematic, retro, clean sci-fi |

Output format: use `reference-analysis-template.md`.

## Phase 1 — Camera Match

Match the reference framing before detailing geometry.

```
CAM_[Asset]_Hero  +  EMPTY_CamTarget_[Subject]
```

| Reference signal | Camera setup |
|------------------|--------------|
| Full vehicle in frame | Wide lens (24–32mm), TRACK_TO ship center/midship |
| Nose/bridge close-up | 40–50mm, target forward section (+Y forward ships) |
| Low orbit cinematic | Elevated 3/4, key light from upper-left |
| Side profile | Orthographic feel: camera perpendicular to longest axis |

**MCP validation:** `get_screenshot_of_area_as_image("VIEW_3D")` at Numpad 0 camera view. Compare subject size and angle to reference.

## Phase 2 — Geometry Match (Least → Most Detail)

Build in three tiers so the asset stops looking "boxy" early:

### Tier 1 — Silhouette (blockout)
- Primary masses only; correct proportions vs reference
- Forward axis and scale locked (1 unit = 1 meter)
- Screenshot: silhouette overlay check at reference camera angle

### Tier 2 — Panel breaks (depth)
- Horizontal ribs, vertical stiffeners, belt lines, keel strips
- Recessed bays, inset panels, stepped noses
- Raised spine segments, module offsets
- **Use cylinders, torus, chamfered boxes** — break 90° corners

### Tier 3 — Greebles + hero features
- Pipes, vents, antennas, windows, lights, decals
- Reference-specific features (logo, sensor, dish, planet placeholder)

**Anti-pattern:** 200 identical tiny cubes at origin. **Pattern:** Named, positioned, parented parts on hull surfaces.

## Phase 3 — Materials Match

Extract palette from reference analysis. Limit unique materials (8–12 hero assets).

| Reference look | Shader approach |
|--------------|-----------------|
| Matte weathered metal | Principled: metallic 0.85–1.0, roughness 0.45–0.65, noise variation |
| Dark recesses | Separate `MAT_*_Recess`, very low base color, roughness 0.7+ |
| Panel contrast | Light/dark hull pair, ΔL ≥ 15% between adjacent panels |
| Glass / windows | Transmission + low emission; static strength (no shared blink) |
| Emissive lights | **Per-object** `MAT_LightInst_*` materials only |
| Decals | Emission or transparent BSDF; white/industrial lettering |

See `realistic-style/references/pbr-values.md` and `materials/references/surface-recipes.md`.

**Never:** animate `Emission Strength` on `MAT_Hull_*` or other multi-user structural materials.

## Phase 4 — Lighting Match

| Reference lighting | Setup |
|-------------------|--------|
| Strong sun, hard shadows | `LGT_Key_Sun` SUN, energy 3–8, angle 2–5° |
| Space / orbit | Dark world (strength 0.08–0.15), no flat gray background |
| Rim separation | `LGT_Rim_*` area/spot from behind-above |
| Fill in shadows | Low `LGT_Fill_*` or slight world ambient — avoid pure black crush |
| Planet / nebula | World shader or `SM_Env_*` placeholder sphere |

Activate **lighting** skill. Match key direction first; tune energy second.

## Phase 5 — Rendering + Grading Match

| Task | Preview (playback) | Final quality |
|------|-------------------|---------------|
| Engine | EEVEE — sharp animation preview | Cycles or EEVEE per target |
| Motion blur | Off during preview | On only if reference shows blur |
| DOF | Off unless reference is shallow | Match focus subject |
| Color management | AgX | Match reference contrast |
| Exposure | 0.2–0.45 typical space scenes | Adjust until hull readable |
| Look | AgX Base Contrast default | High Contrast if reference is punchy |

**Playback blur fix:** EEVEE + `taa_samples` 1–8 + motion blur off + no Cycles viewport during animation scrub.

Activate **rendering** skill for pass output and final stills.

## Phase 6 — Screenshot Comparison Loop

After each phase, capture and compare:

```
1. get_screenshot_of_area_as_image("VIEW_3D") (or render still at hero camera)
2. List GAPS vs reference (max 5 prioritized items)
3. Fix gaps via MCP
4. Re-screenshot
5. Repeat until PASS or 3 iterations
```

### Measure the silhouette instead of eyeballing it

When a reference gives a clean outline (a transparent-background render, a cut-out, or a photo on a flat background),
score it. `scripts/silhouette_score.py` projects the evaluated triangles of the named objects through a named camera
(lens, sensor fit, shift, orthographic and the clip planes are honoured) and compares them with the reference mask: IoU,
bounding-box drift and centroid drift per view. No render is needed, so it is cheap enough to run after every phase. Match
the camera first (Phase 1): a wrong camera scores low whatever the geometry.

```json
{"objects": ["SM_Ship"], "min_iou": 0.9,
 "views": [{"camera": "CAM_Ship_Hero", "reference": "C:/proj/ref/ship_front.png"}]}
```

- The mask is the alpha channel when the image has any transparency, otherwise everything that differs from the
  background colour read at the four corners; if the corners disagree the script refuses. A busy photo background needs
  a cut-out first.
- The silhouette is the union of the projected triangles: other objects do not hide it, so name only the subject, and
  features thinner than a pixel can drop out. IoU near 1 means the outline matches at that image size, not that the
  surface does.
- Read the drift as a direction: a centroid drift with a good size ratio means the object is offset; a size ratio away from
  1 with a centred centroid means it is too big or small; a low IoU with both near zero means the shape differs.
- Measured against real Workbench renders of the same cameras in the plugin's test (`tests/blender/test_parity.py`):
  IoU 0.992 for a perspective close-up with anti-aliasing, 1.0 for an orthographic view and for hard edges. Treat 0.98 as the
  ceiling for edge noise and 0.9 as a sensible pass line for a hand-built match.

If the score is low only because of a few known dials, `scripts/fit_search.py` can find them: it moves the named numeric
properties one at a time (for example `scale`, `location[0]`, a modifier width) to raise the mean IoU, within `min`/`max`
bounds and `max_evals`, then restores every value unless `apply` is true. It is a local search from the current values: it
finds the nearest good fit, cannot fix a wrong shape, and is as accurate as the mask resolution allows (about one pixel).
Run it with `apply: false` first, read `best`, then decide.

```json
{"objects": ["SM_Ship"], "max_evals": 60,
 "views": [{"camera": "CAM_Ship_Hero", "reference": "C:/proj/ref/ship_front.png"}],
 "params": [{"object": "SM_Ship", "path": "scale", "min": 0.3, "max": 3.0}]}
```

Both snippets are the ARGS for `runpy.run_path` as in the scripts table of the `blender-mcp-workflow` skill.

### Gap categories (prioritize top-down)

1. Camera / framing wrong
2. Silhouette / proportions wrong
3. Too flat / boxy (missing tier-2 breaks)
4. Materials too uniform / wrong value range
5. Lighting direction or exposure wrong
6. Missing hero features (decals, windows, env)
7. Micro-detail density mismatch

## Skill Routing (Reference Tasks)

```
blender-director
  → reference-image-match (this doc)
  → [discipline: hard-surface | environment-artist | character-artist]
  → [style: realistic-style | horror-style | stylized-style | lowpoly-style]
  → materials → lighting → rendering
  → visual-match-checklist → validation-checklist
```

## MCP Execution Checklist

- [ ] `get_objects_summary` or audit script — bounds, collections, materials
- [ ] `get_screenshot_of_area_as_image("VIEW_3D")` — baseline before changes
- [ ] Reference analysis written
- [ ] Camera + target empty positioned
- [ ] Geometry tiers 1→2→3
- [ ] Materials from extracted palette
- [ ] Lights + world
- [ ] Grading (AgX exposure/look)
- [ ] Comparison screenshot vs reference
- [ ] Gap list + fixes
- [ ] `save_mainfile`
- [ ] Validation report

## Common Failures (Fix Immediately)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Entire ship white when animating | Emission keyed on shared hull material | Per-light materials; clear structural mat animation |
| Black camera view | Camera inside mesh or no lights | Reposition CAM; boost key + world |
| Boxy, toy-like | Tier-2 panel breaks skipped | Ribs, belts, recesses, chamfers before greebles |
| Reference angle wrong | Camera not matched first | TRACK_TO target; match lens and position |
| Blurry on spacebar | Cycles viewport + low samples | EEVEE preview; motion blur off |
| Flat grey clay | No lighting / no material contrast | Sun + rim; light/dark panel pair |
| Details float at origin | Parent/position not set | Parent to root; place on hull surface |

## Good User Prompts

- "Match this photo — industrial freighter, matte grey hull, strong upper-left sun, full ship in frame"
- "Upgrade existing ship in `spacecraft.blend` to match attached reference; do not rebuild"
- "Reference attached. Analyze first, then camera match, then materials and lighting"
- "Iterate until viewport matches reference — screenshot compare after each pass"

## Delivery

Include in completion message:

- Reference analysis summary (palette + camera + lighting)
- Before/after screenshot description
- Remaining gaps (if any) with honest assessment
- File path saved
- Active skills used
