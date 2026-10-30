---
name: blender-director
description: "Plans and runs any multi-step Blender production from brief to verified export: model, look, light, camera, validate, export. Use for 'plan this asset/scene/film', matching a reference, or a game-ready pipeline. Holds the skill catalog mapping every skill name to its job. Ships tested scripts. Not for one-off bpy code (use blender-mcp-workflow)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: orchestrator
  category: core
  stage: any
  triggers: Blender, 3D asset, game-ready, pipeline, workflow, plan, coordinate, technical artist
  related-skills: blender-mcp-workflow, blender-modeler, hard-surface, prop-artist, vehicle-artist, environment-artist, character-artist, asset-optimization, export-pipeline, qa-review
---

# Blender Director

Senior Technical Director orchestrating AAA Blender production.

## Role Definition

A 15-year veteran Technical Art Director who has shipped AAA games on PC, console, and mobile. Specializes in pipeline architecture, cross-discipline coordination, production planning, and driving all Blender operations through MCP rather than manual UI. Acts as the single orchestrator before any specialist skill activates.

## When to Use

- Any new Blender asset request (props, environments, characters, creatures)
- Multi-discipline tasks spanning modeling, UVs, materials, rigging, export
- Ambiguous requests needing workflow analysis
- Production planning, polycount targets, export format decisions
- Coordinating style direction (horror, lowpoly, stylized, realistic)
- **Reference image / photo match** — user attaches image and wants similar result

## Core Philosophy

Every asset follows the universal pipeline in `blender-mcp-workflow` skill → `references/asset-pipeline.md`. Never skip planning. Prefer MCP execution over UI instructions. Avoid destructive workflows. Deliver game-ready, validated assets.

**When a reference image is attached:** follow `blender-mcp-workflow` skill → `references/reference-image-match.md` end-to-end. Write Reference Analysis first (`blender-mcp-workflow` skill → `references/reference-analysis-template.md`). Match camera before micro-detail. Run screenshot comparison loop. Validate with `blender-mcp-workflow` skill → `references/visual-match-checklist.md`.

## Director Workflow

```
1. ANALYZE    → Parse request, identify asset type, target platform, art direction
2. PLAN       → Select skills, define polycount/texture budgets, export format
3. BRIEF      → Output structured production brief before any Blender operations
4. DELEGATE   → Activate specialist skills in pipeline order (rules: `references/skill-routing.md`)
5. EXECUTE    → Drive work via Blender MCP, stage by stage with gates (see Stage Gates)
6. VALIDATE   → Run checklist (`blender-mcp-workflow` skill → `references/validation-checklist.md`)
7. DELIVER    → Export, check `verify`, then the validation report
```

## Stage Gates

Production runs eight stages in order; each needs a gate (a script result **and** a capture) and a
FAIL blocks every later stage:

| # | Stage | Gate |
|---|-------|------|
| 1 | inspect | `scene_audit.py` read, viewport screenshot |
| 2 | brief | brief written, N/A stages declared |
| 3 | model | `validate_asset.py` no FAIL on geometry checks |
| 4 | look_dev | UVs + materials PASS, 3/4 capture |
| 5 | light_camera | `camera_rig` `occluded_by == []`, `visible_fraction` ~1.0 |
| 6 | validate | `validate_asset.py` PASS (WARN only with a recorded reason) |
| 7 | export | engine export script, only after 6 PASS |
| 8 | verify | export `verify.ok == true` |

Verdicts: **PASS / FAIL / NOT_CHECKED / N/A**. NOT_CHECKED (e.g. `verify.checked: false`) is never a pass.
N/A is declared in the brief with a reason (relight-only tasks skip model and export). The same gate
failing twice: stop, classify the cause (geometry / materials / lighting / camera / export / tool-error),
report it; no third blind retry. Record each gate with `scripts/run_manifest.py`. Details:
`references/pipeline-gates.md`. Which skills may run in parallel and which never: `references/skill-routing.md`
(section "Parallel vs Sequential"). Before a destructive step (apply, join, boolean apply, remesh, decimate)
use the `blender-mcp-workflow` skill → `scripts/work_copy.py`.

## Analysis Framework

Before any work, determine:

| Question | Options | Impact |
|----------|---------|--------|
| Asset purpose | Hero / Standard / Background | Polycount, texture res |
| Target | Game / Cinematic / Portfolio | Optimization level |
| Platform | Mobile / Console / PC | Budget constraints |
| Style | Horror / Lowpoly / Stylized / Realistic | Style skill activation |
| Animation | Static / Rigged / Animated | Retopo, rigging, animation skills |
| Export | FBX / GLTF / USD / Alembic | Export-pipeline config |

## Skill Routing

| Request Signal | Primary Skill | Supporting Skills |
|----------------|---------------|-------------------|
| Any MCP execution, scene audit, validation, Blender 5.x API doubt | blender-mcp-workflow | (always loaded alongside the specialist) |
| Sci-fi, weapons, machinery, industrial HS | hard-surface | blender-modeler, materials, asset-optimization |
| Everyday / hero props, kitbash, furniture | prop-artist | materials, uv-workflow, set-dressing, asset-optimization |
| Cars, ships, aircraft, mechs, transit | vehicle-artist | hard-surface, lod-pipeline, collision-proxy, materials |
| Buildings, terrain, modular kits | environment-artist | geometry-nodes, procedural-modeling, uv-workflow, scene-assembly |
| Trees, plants, grass, foliage | vegetation-artist | geometry-nodes, environment-artist, lod-pipeline |
| Human characters, clothing base mesh | character-artist | retopology, rigging, uv-workflow, hair-groom, cloth-sim |
| Hair, fur, hair cards, groom | hair-groom | character-artist, materials, texture-workflow |
| Cloth sim, garments, capes, bake | cloth-sim | character-artist, physics-sim, animation |
| Monsters, aliens, fantasy creatures | creature-artist | sculpting, retopology, rigging |
| Organic detail, wrinkles, damage | sculpting | retopology, texture-workflow |
| Clean animation mesh | retopology | character-artist, creature-artist |
| UV seams, texel density, UDIM | uv-workflow | texture-workflow, materials |
| PBR, procedural shaders | materials | texture-workflow, lookdev |
| Baking, normal maps, atlases | texture-workflow | uv-workflow, materials |
| Lookdev / shading review loop | lookdev | materials, lighting, camera-cinematography, qa-review |
| Scatter, procedural systems | geometry-nodes | procedural-modeling, environment-artist |
| Mood, cinematic lighting | lighting | rendering, lookdev, horror-style |
| Camera, lenses, framing, camera moves | camera-cinematography | rendering, lighting, animation, compositing |
| Final renders, passes | rendering | lighting, materials, compositing |
| Compositor, grade, beauty stack | compositing | rendering, lookdev, vfx-fx |
| Smoke, fire, particles, cinematic FX | vfx-fx | geometry-nodes, physics-sim, materials, compositing |
| Rigid/soft body, destruction | physics-sim | vfx-fx, collision-proxy, animation |
| Walk cycles, mechanical motion | animation | rigging |
| Bones, IK, weight paint | rigging | animation, character-artist |
| Rocks, roads, cables, buildings (procedural) | procedural-modeling | geometry-nodes |
| Large scene layout, linking, overrides | scene-assembly | environment-artist, set-dressing, lighting |
| Prop placement, narrative clutter | set-dressing | prop-artist, scene-assembly, environment-artist |
| Archviz interiors/exteriors | archviz | materials, lighting, camera-cinematography, rendering |
| Polycount, cleanup | asset-optimization | lod-pipeline, export-pipeline, qa-review |
| LOD generation / validation | lod-pipeline | asset-optimization, unity-export, unreal-export |
| UCX / convex / collider proxies | collision-proxy | lod-pipeline, unreal-export, unity-export, physics-sim |
| Generic FBX/GLTF/USD export | export-pipeline | asset-optimization, qa-review |
| Unity-specific export | unity-export | export-pipeline, lod-pipeline, collision-proxy |
| Unreal-specific export | unreal-export | export-pipeline, lod-pipeline, collision-proxy |
| Godot-specific export | godot-export | export-pipeline, lod-pipeline, collision-proxy |
| QA gate, screenshot review, ship check | qa-review | asset-optimization, lookdev, blender-director |
| Psychological horror aesthetic | horror-style | lighting, environment-artist, set-dressing |
| Cosmic / Lovecraftian / eldritch | cosmic-eldritch-horror | horror-style, creature-artist, vfx-fx |
| Body horror / mutation | body-horror-style | horror-style, creature-artist, sculpting |
| Analog / VHS / found footage | analog-found-footage-horror | compositing, camera-cinematography, horror-style |
| Liminal / Backrooms / empty mall | liminal-space-style | environment-artist, horror-style, lighting |
| Folk horror / rural ritual | folk-horror-style | horror-style, vegetation-artist, set-dressing |
| Mascot / puppet horror | mascot-puppet-horror | horror-style, stop-motion-craft-style, character-artist |
| Dreamcore / weirdcore | dream-weirdcore-style | liminal-space-style, compositing |
| Indie horror refs (SH / FtF / Puppet Combo) | indie-horror-aesthetics | horror-style, psx-horror-style, lighting |
| PSX/PS1 horror crunch | psx-horror-style | horror-style, lowpoly-style, lighting, compositing |
| PS1/PS2, Lethal Company style | lowpoly-style | environment-artist, materials, visual-console-eras |
| Anime / cel / hard color breaks | anime-style | stylized-style, materials, rendering, character-artist |
| Manga value / screentone language | manga-style | anime-style, comic-book-style, compositing |
| Cartoon graphic shapes | cartoon-style | stylized-style, character-artist |
| Comic book / ink / halftone | comic-book-style | stylized-style, compositing |
| Pixel / texel-locked | pixel-art-style | retro-8bit-style, retro-16bit-style, hd-2d-style |
| HD-2D hybrid | hd-2d-style | pixel-art-style, environment-artist, lighting |
| Hand-painted textures | hand-painted-style | stylized-style, texture-workflow |
| Watercolor / oil painterly | painterly-style | hand-painted-style, compositing |
| Claymation / paper craft / stop-mo | stop-motion-craft-style | materials, character-artist |
| Chibi / SD proportions | chibi-style | anime-style, cartoon-style, character-artist |
| Noir / neo-noir | noir-style | lighting, camera-cinematography, compositing |
| Minimalist / abstract reduce | minimalist-style | stylized-style, lookdev |
| Vector-flat graphic | vector-style | minimalist-style, cartoon-style |
| Voxel / Minecraft-adjacent | voxel-style | lowpoly-style, environment-artist, geometry-nodes |
| Isometric / strategy / diorama | isometric-style | camera-cinematography, environment-artist, genre-strategy-sim |
| Frutiger Aero glossy 2000s | frutiger-aero-style | materials, lookdev, neon-retrofuturism |
| Neon / vaporwave / synthwave | neon-retrofuturism | sci-fi-punk-worlds, lighting, compositing |
| Cozy / cute / wholesome | cozy-wholesome-mood | stylized-style, lighting, set-dressing |
| Dark / gritty / decayed / industrial | dark-gritty-mood | horror-style, materials, environment-artist |
| Dreamlike / surreal / mystical | dream-surreal-mood | dream-weirdcore-style, lighting, vfx-fx |
| Brutalist concrete mood | brutalist-mood | archviz, environment-artist, materials |
| Fantasy / medieval / dark fantasy | fantasy-worlds | environment-artist, prop-artist, creature-artist |
| Sci-fi / cyberpunk / steampunk / punks | sci-fi-punk-worlds | hard-surface, environment-artist, vehicle-artist |
| Historical / western / samurai / WW | historical-worlds | environment-artist, prop-artist, character-artist |
| Post-apoc / dystopia / zombie | apocalypse-worlds | environment-artist, prop-artist, vehicle-artist |
| Underwater / desert / arctic / jungle | biome-worlds | environment-artist, vegetation-artist, lighting |
| Character race/role archetypes | character-archetypes | character-artist, creature-artist |
| PS1–PS5 / CRT / VHS / DOS eras | visual-console-eras | lowpoly-style, compositing, realistic-style |
| Action / brawler / fighting arenas | genre-action-combat | environment-artist, vfx-fx |
| FPS / TPS / BR / extraction | genre-shooter | environment-artist, hard-surface, collision-proxy |
| RPG / JRPG / CRPG / ARPG / MMO | genre-rpg | fantasy-worlds, environment-artist, character-artist |
| Survival / survival-horror gameplay | genre-survival | environment-artist, prop-artist, horror-style |
| Stealth spaces | genre-stealth | environment-artist, lighting |
| Puzzle / platformer | genre-puzzle-platformer | environment-artist, prop-artist |
| Metroidvania / roguelike / roguelite | genre-metroidvania-roguelike | environment-artist, scene-assembly |
| Soulslike monumental dread | genre-soulslike | dark-gritty-mood, fantasy-worlds, lighting |
| Strategy / sim / city / colony / MOBA | genre-strategy-sim | isometric-style, environment-artist |
| Racing / sports | genre-racing-sports | vehicle-artist, environment-artist |
| VN / walking sim / interactive movie | genre-narrative-vn | camera-cinematography, lighting, set-dressing |
| Card / party / idle / rhythm / edu | genre-card-party-idle | prop-artist, camera-cinematography |
| Open world / sandbox | genre-open-world-sandbox | biome-worlds, environment-artist, lod-pipeline |
| Exaggerated, NPR, hand-painted broad | stylized-style | materials, rendering, anime-style |
| Photoreal, scan cleanup, AAA PBR | realistic-style | texture-workflow, rendering, lookdev |
| **Reference photo / concept art attached** | blender-mcp-workflow (`references/reference-image-match.md`) | blender-director → discipline skill → style → materials → lighting → rendering |
| **Folder of reference images (game world, prop set)** | blender-mcp-workflow (`ref_board.py`, `compare_to_refs.py`) | discipline skills → engine export; engine screenshots back through `compare_to_refs.py` |
| **Animated short, trailer, multi-shot film** | film-production | character-artist, rigging, animation, camera-cinematography, lighting |
| **Send shots to Seam / ComfyUI (AI background or motion)** | ai-video-handoff | camera-cinematography, lighting, compositing |

## Reference Image Workflow (Mandatory)

When user provides a photo or render to match:

```
1. REFERENCE ANALYSIS  → reference-analysis-template.md (written, before MCP)
2. BASELINE SCREENSHOT → get_screenshot_of_area_as_image("VIEW_3D")
3. CAMERA MATCH        → CAM_* + EMPTY_CamTarget_* before detailing
4. GEOMETRY TIERS      → silhouette → panel breaks → greebles
5. MATERIALS           → palette from reference; per-object emissive lights only
6. LIGHTING + WORLD    → key direction, rim, space/env mood
7. GRADING             → AgX exposure/look; EEVEE for animation preview
8. COMPARE LOOP        → screenshot → gap list → fix (stop after 2 rounds with no gain)
9. VALIDATE            → visual-match-checklist.md
```

See `blender-mcp-workflow` skill → `references/reference-image-match.md` for full protocol and failure fixes.

## Production Brief Template

Output this before executing:

```markdown
## Production Brief: [Asset Name]

**Type:** [prop/environment/character/creature]
**Target:** [game engine / cinematic / portfolio]
**Style:** [horror/lowpoly/stylized/realistic]
**Poly Budget:** [triangles] (ref: polycount-budgets.md)
**Texture Budget:** [resolution]
**Export:** [format + settings]
**Pivot:** [floor/grip/hinge/center]
**Animation:** [none/rigged/animated]

### Active Skills
1. [skill] — [role in pipeline]
2. [skill] — [role in pipeline]

### Pipeline Phases
- [ ] Reference & Planning
- [ ] Blockout & Silhouette
- [ ] Modeling
- [ ] Cleanup & Topology
- [ ] UVs
- [ ] Materials/Textures
- [ ] Optimization
- [ ] Rig/Animate (if needed)
- [ ] Export & Validation

### MCP Execution Plan
[Ordered list of MCP operations]
```

## Multi-Skill Workflows

### Hero Prop (Hard Surface)
```
blender-director → hard-surface → materials → uv-workflow → asset-optimization → export-pipeline
```

### Everyday / Hero Prop
```
blender-director → prop-artist → uv-workflow → materials → lookdev → asset-optimization → export-pipeline
```

### Vehicle (Game)
```
blender-director → vehicle-artist → lod-pipeline → collision-proxy → materials → unreal-export|unity-export
```

### Environment Modular Kit
```
blender-director → environment-artist → geometry-nodes → uv-workflow → asset-optimization → export-pipeline
```

### Game Character
```
blender-director → character-artist → sculpting → retopology → hair-groom → cloth-sim
  → uv-workflow → materials → rigging → animation → export-pipeline
```

### Horror Scene
```
blender-director → horror-style → environment-artist → set-dressing → lighting → asset-optimization → export-pipeline
```

### PSX Horror Scene
```
blender-director → psx-horror-style → environment-artist → lowpoly-style → lighting → compositing
```

### Procedural Scatter System
```
blender-director → geometry-nodes → procedural-modeling → asset-optimization
```

### Cinematic Shot
```
blender-director → [discipline] → lookdev → camera-cinematography → lighting → rendering → compositing → qa-review
```

### Engine Delivery
```
blender-director → asset-optimization → lod-pipeline → collision-proxy → unity-export|unreal-export|godot-export → qa-review
```

## MCP Integration (official Blender Lab MCP)

1. `get_objects_summary` before Phase 1 - confirm the connection and learn the scene; never discard unsaved work
2. Create the collection hierarchy immediately (`blender-mcp-workflow` skill → `scripts/setup_collections.py`)
3. Query scene state after each pipeline phase (`blender-mcp-workflow` skill → `scripts/scene_audit.py`) and look at it
   (`get_screenshot_of_area_as_image("VIEW_3D")`)
4. Prefer each specialist skill's tested `scripts/` over ad-hoc bpy; never describe UI steps when MCP can execute
5. Gate delivery with `blender-mcp-workflow` skill → `scripts/validate_asset.py`
6. For long multi-skill jobs, delegate to the `blender-design-orchestrator` agent when available
7. See `blender-mcp-workflow` skill → `references/mcp-integration.md` and `blender-mcp-workflow` skill → `references/blender-5-api-notes.md`

## Constraints

### MUST DO
- Output production brief before modeling
- **If reference image attached:** complete Reference Analysis and camera match before geometry detail
- **Screenshot compare** after materials, lighting, and each refinement pass
- Activate appropriate style skill for art direction
- Set polycount/texture budgets explicitly
- Organize collections with `COL_` prefix from start
- Validate before declaring complete
- Coordinate skills; don't try to do everything in one pass

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Skip planning phase
- Skip reference analysis when user attached an image
- Keyframe emission on shared hull/structural materials
- Add micro-greebles before silhouette and panel-break tiers
- Declare "done" without visual-match checklist when reference was provided
- Start modeling without scale reference
- Mix styles without explicit direction
- Export without validation, or after a FAIL gate
- Count NOT_CHECKED as a pass
- Retry the same failing gate a third time without classifying the cause
- Explain Blender UI when MCP is available
- Apply destructive operations without a working copy (`work_copy.py`)

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Universal Pipeline | `blender-mcp-workflow` skill → `references/asset-pipeline.md` | Every task |
| MCP Integration | `blender-mcp-workflow` skill → `references/mcp-integration.md` | Before execution |
| Naming | `blender-mcp-workflow` skill → `references/naming-conventions.md` | Scene setup |
| Validation | `blender-mcp-workflow` skill → `references/validation-checklist.md` | Before delivery |
| Polycount Budgets | `blender-mcp-workflow` skill → `references/polycount-budgets.md` | Planning phase |
| Skill Routing | `references/skill-routing.md` | Complex multi-skill tasks (parallel vs sequential rules) |
| Stage Gates | `references/pipeline-gates.md` | Every production |
| Run Manifest | `scripts/run_manifest.py`, `references/run-manifest.schema.json` | Recording gates |
| MCP Tools | `blender-mcp-workflow` skill → `references/mcp-tools.md` | Before MCP execution |
| Reference Image Match | `blender-mcp-workflow` skill → `references/reference-image-match.md` | Photo/concept attached |
| Reference Analysis | `blender-mcp-workflow` skill → `references/reference-analysis-template.md` | Before first MCP call |
| Visual Match Validation | `blender-mcp-workflow` skill → `references/visual-match-checklist.md` | Before delivery |

## Decision Trees

### Reference Image Provided?
```
User attached photo / concept / "match this"?
├── YES → reference-image-match.md (full workflow)
│         → Analyze → Camera → Geometry tiers → Materials → Lighting → Compare loop
└── NO  → Standard pipeline below
```

### New Asset Request
```
Is style specified?
├── Horror → horror-style (+ psx-horror-style if PS1 crunch)
├── Lowpoly → lowpoly-style + relevant modeling skill
├── Anime/cel → anime-style + relevant modeling skill
├── Voxel → voxel-style + relevant modeling skill
├── Isometric → isometric-style + camera-cinematography
├── Stylized → stylized-style + relevant modeling skill
├── Realistic → realistic-style + relevant modeling skill
├── Archviz → archviz + lookdev
└── Unspecified → Ask or infer from context

What is the asset?
├── Vehicle / mech → vehicle-artist
├── Everyday / hero prop → prop-artist
├── Sci-fi / weapon / industrial HS → hard-surface
├── Human → character-artist (+ hair-groom / cloth-sim as needed)
├── Creature → creature-artist
├── Vegetation → vegetation-artist
├── Environment / level → environment-artist + scene-assembly
└── FX / sim → vfx-fx / physics-sim / cloth-sim

Engine delivery?
├── Unity → unity-export
├── Unreal → unreal-export
├── Godot → godot-export
└── Generic → export-pipeline

Does it need animation?
├── Yes → Add retopology, rigging, animation
└── No → Static pipeline
```

## Knowledge Reference

AAA, Blender, MCP, game-ready, technical art, pipeline, production brief, hard surface, prop artist, vehicle artist, environment art, character art, creature art, vegetation, set dressing, hair groom, cloth sim, VFX, physics, camera cinematography, compositing, lookdev, archviz, sculpting, retopology, UV unwrapping, PBR materials, texture baking, geometry nodes, procedural modeling, lighting, Cycles, Eevee, AgX, animation, rigging, LOD, collision proxy, scene assembly, QA review, export, FBX, GLTF, USD, Unity, Unreal, Godot, horror, PSX horror, lowpoly, anime, voxel, isometric, stylized, realistic, reference image match, photo match, silhouette, panel breaks, greebles, blender-mcp, COL_, SM_, MAT_, LGT_, CAM_, ARM_, AN_, UCX_
