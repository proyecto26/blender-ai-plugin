# Changelog

All notable changes to the Blender AI Plugin (formerly Blender Skills Pack).

Format: [Semantic Versioning](https://semver.org/) — `Major.Minor.Patch`

---

## [Unreleased]

Iteration 7: routing that holds up with many skills, film and AI-video pipelines, refs-first worlds.

### Changed
- Rewrote every skill description to lead with the job in user words, add a "Use when" trigger and a
  "Not for ... (use X)" clause for look-alikes. The plugin's names and descriptions dropped from 32,808 to
  about 16,000 characters, so Claude Code's skill listing no longer drops the descriptions of 37 skills
- `blender-design-orchestrator` now preloads `blender-director` and `blender-mcp-workflow`, reads the skill
  catalog, follows an explicit stage-to-skill table and describes its triggers in prose ("When to invoke")
- Every script's command line accepts `--args-file <path.json>` (portable to cmd and PowerShell) and reports
  malformed JSON with a clear `ValueError`
- Script paths in `runpy` calls are written with forward slashes on every OS; example paths use `<project>`

### Added
- `film-production`: shot list, preview frames and contact sheet, fix loop, EEVEE render, edit with
  user-supplied, licensed audio to mp4 (`shot_list.py`, `preview_frames.py`, `assemble_edit.py`)
- `ai-video-handoff`: renders stills, clips, masks and depth with a manifest for Seam (`seam_sequence.json`,
  the `create_sequence` arguments) or ComfyUI (`handoff.json`); it never submits or pays for anything
- Reference-folder-first workflow: `ref_board.py` (style bible from a folder of refs) and
  `compare_to_refs.py` (plain-language drift of renders or engine screenshots against the refs)
- `metadata.category` / `metadata.stage` on every skill; `scripts/build_catalog.py` generates
  `blender-director/references/skill-catalog.md`
- Validator checks: per-category description caps, total listing budget, look-alike descriptions without a
  "Not for" clause, stale catalog
- Routing evals: `evals-routing/` (tuning), frozen `evals-routing-heldout/`, `evals-orchestrator/`, scored by
  `tests/routing/score_routing.py`; headless tests `test_film.py`, `test_handoff.py`, `test_refs.py`
- macOS and Linux headless commands in `docs/BLENDER_MCP_SETUP.md`

### Fixed
- Unreal and Unity FBX exports now read the file back (`verify`: missing, leaked, `ok`), so the pipeline's
  verify gate can pass for FBX targets; skinned exports count the armature and ignore bone names
- `run_manifest.py` knows the optional `animate`, `film` and `handoff` stages (N/A until recorded); the schema
  and `pipeline-gates.md` match
- `assemble_edit.py` refuses to rebuild an edit scene it did not create; `shot_list.py` merges no longer
  duplicate the markers of kept shots
- `blender-director` routes film, AI handoff and reference folders; the orchestrator loads every stage's
  skill and returns a stage table with a skill per stage
- Description and body contradictions: geometry-nodes vs procedural-modeling, lighting vs lookdev,
  horror-style, lowpoly-style, stylized-style, qa-review; Godot collision naming; pixel-art step order

Iteration 6: fixes from the skill review, verified in headless Blender 5.2.

### Fixed
- Quoted skill frontmatter values so descriptions with colons parse as YAML
- glTF exports were limited to the active scene and are now verified after export
- Made collision proxy generation idempotent: re-running replaces its own proxies instead of stacking `_02`, `_03`
- Placed the genre-shooter FPS camera at eye height; `camera_rig` now reports occlusion
- Made `scatter_props` enforce `max_dist`
- Gave `fix_asset` a proper `main()`; applying scale now keeps object-parented children in place
- Fixed `work_copy` accept so checkpoint originals stay untouched (parent links included)
- Made the run manifest refuse an export or verify PASS unless validate is PASS or N/A
- Stopped collision proxy reruns from deleting a user's renamed duplicate of a proxy
- Fixed `camera_rig` to report the real camera distance and note every clamp it applies
- Made the recipe runner fail on blocks that are not inventoried and sample 6 occlusion points
- Removed deprecated `use_nodes` guards (Blender 5.2+ only)

### Added
- New smoke tests, a recipe runner (`tests/blender/run_recipes.py`) and a stricter skill validator
- Director stage gates (PASS / FAIL / NOT_CHECKED / N/A), `run_manifest.py` and `work_copy.py` for destructive steps
- Evals `09-director-gates` and `10-shooter-camera`
- Skill descriptions carry "Use when" triggers and name the scripts they ship

### Changed
- `scatter_props` `max_dist` is a hard limit on prop distance; stacked LOD copies no longer render; fluid domains never count as camera occluders
- User-facing docs and manifests no longer state fixed skill or script counts
- `docs/BLENDER_MCP_SETUP.md`: running the headless tests on Windows with a Microsoft Store install

---

## [2.0.0] — 2026-10-27

Fork maintained by [Proyecto 26](https://github.com/proyecto26) as **Blender AI Plugin**.

### Added
- **Agent Plugins 1.0** manifest (`plugin.json`), **Codex** manifest (`.codex-plugin/plugin.json`) and
  Codex/Copilot catalog (`.agents/plugins/marketplace.json`) next to the Claude Code manifests
- **`blender-design-orchestrator` agent** for end-to-end, verified multi-skill execution
- **`blender-mcp-workflow` foundation skill**: official Blender Lab MCP tool catalog, safety rules, shared
  references, Blender 5.x API notes, and core scripts (`scene_audit`, `setup_collections`,
  `validate_asset`, `capture_views`)
- **29 bpy scripts** across 26 skills (bevel stack, PBR/toon materials, UV density, GN scatter, light rigs,
  camera rigs, render presets, 5.x compositor grades, LODs, collision proxies, Unreal/Unity/Godot export,
  rig check, turntable, PS1 look, voxelize, isometric camera, rigid body, cloth, topology report, baking,
  mesh cleanup) — all passing `tests/blender/test_skill_scripts.py` on Blender 5.2 LTS
- `scripts/validate_skills.py` (frontmatter, links, self-containment, deprecated APIs, script safety) and
  `scripts/check-manifests.sh` (manifest consistency + `claude plugin validate` + Agent Plugins schema)
- `claude plugin eval` suite under `evals/` (Blender 5.x bpy code: 6 should-fire + 2 should-NOT-fire cases)
- Demo video `docs/blender-ai-plugin.mp4`, rendered with Blender using the plugin's own scripts

### Changed
- Skill triggers: `blender-mcp-workflow` now fires before any bpy code; `geometry-nodes`/`set-dressing` route scattering to `scatter_points.py`; 27 skills forbid pre-5.2 code and version fallbacks; 26 skills hand users the `runpy` call instead of inlining scripts.
- `compositing/comp_grade.py`: `vignette` and `warmth` ARGS (Blender 5.2 `ShaderNodeMix` + socket-based Ellipse Mask/Blur).
- `lowpoly-style/ps1_look.py`: real compositor fog from the mist pass (`fog` takes an RGB colour) and 32px posterized, nearest-filtered textures for untextured meshes (`texture`).
- `lighting/light_rig.py`: `golden_hour` preset now renders warm (warm horizon world, dimmer cool fill).
- Evals: graders accept a call to the plugin's tested script as well as the literal 5.2 API; case 04 hardened (coat, sheen, no fallbacks).
- Skills moved from `.claude/skills/` to `skills/` (Agent Skills layout); shared `references/` moved into
  `blender-mcp-workflow`; every skill is self-contained (no `../` paths)
- MCP integration targets the **official Blender Lab MCP server** (Blender 5.1+) instead of the third-party
  `blender-mcp` add-on; tool names updated (`get_screenshot_of_area_as_image`, `get_objects_summary`, ...)
- Outdated Blender API guidance fixed: Auto Smooth → Smooth by Angle, EEVEE bloom/SSR/AO → compositor
  Glare + ray tracing, `scene.node_tree` → `scene.compositing_node_group`, Principled `Specular` →
  `Specular IOR Level`, `Subsurface Color` removed, Combine RGB → Combine Color, Filmic → AgX looks
- `dream-weirdcore-style` linked a non-existent `surreal-mood` skill → `dream-surreal-mood`
- `blender-director` frontmatter had a duplicate `role` key

- **Blender 5.2+ only**: version fallbacks removed from scripts and skill code (`mod.properties.inputs`,
  layered actions); `validate_skills.py` rejects `bpy.app.version` branches and removed APIs in code
- `blender-mcp-workflow` gained a "Verify, Don't Guess" loop (script first → API docs → isolated probe →
  confirm) and allows removing clearly unused data (orphans, empty collections, plugin-created objects)

### Removed
- `site/` (Next.js website), `.cursor/` duplicate skill copy, Windows-only `.mcp.json` pointing to the
  third-party server, `version.json`, `QUICKSTART.md` (merged into README), root `CLAUDE.md` (→ `AGENTS.md`)

---

## [1.3.0] — 2026-07-10

### Added
- Deep `references/` docs for production skills (prop, vehicle, hair, cloth, VFX, camera, compositing, physics, engine exports, LOD, collision, scene, QA, styles, vegetation, set-dressing, archviz, lookdev)
- **Extended art styles:** cartoon, comic-book, manga, pixel-art, hand-painted, painterly, stop-motion-craft, chibi, noir, minimalist, vector, retro-8bit, retro-16bit, hd-2d, frutiger-aero
- **Horror packs:** cosmic-eldritch, body-horror, analog-found-footage, liminal-space, folk-horror, mascot-puppet, dream-weirdcore, indie-horror-aesthetics
- **Worlds:** fantasy-worlds, sci-fi-punk-worlds, historical-worlds, apocalypse-worlds, biome-worlds
- **Moods:** cozy-wholesome, dark-gritty, dream-surreal, neon-retrofuturism, brutalist
- **Gameplay genre direction:** action-combat, shooter, rpg, survival, stealth, puzzle-platformer, metroidvania-roguelike, soulslike, strategy-sim, racing-sports, narrative-vn, card-party-idle, open-world-sandbox
- **character-archetypes**, **visual-console-eras**
- Subtype coverage map in `SKILLS_GUIDE.md` (genres/styles map into pack skills + refs)

### Changed
- Skill count **46 → 94**; references **~40 → 175**
- `blender-director` routing expanded for genre/style/world/mood packs

---

## [1.2.0] — 2026-07-10

### Added
- **Modeling:** `prop-artist`, `vehicle-artist`, `vegetation-artist`
- **Character / sim:** `hair-groom`, `cloth-sim`
- **Technical:** `vfx-fx`, `camera-cinematography`, `compositing`, `physics-sim`, `lookdev`
- **Pipeline:** `unity-export`, `unreal-export`, `godot-export`, `lod-pipeline`, `collision-proxy`, `scene-assembly`, `set-dressing`, `qa-review`, `archviz`
- **Styles:** `anime-style`, `voxel-style`, `isometric-style`, `psx-horror-style`
- Expanded `blender-director` routing tables and multi-skill workflows
- Updated `SKILLS_GUIDE.md` decision trees for new disciplines and engines

### Changed
- Skill count **23 → 46** (`version.json`, README, plugin metadata)
- `hard-surface` now defers dedicated vehicles to `vehicle-artist`
- `skill-routing.md` engine targets point at Unity/Unreal/Godot export skills

---

## [1.1.0] — 2026-07-05

### Added
- `references/reference-image-match.md` — Full photo/concept-art-to-Blender workflow
- `references/reference-analysis-template.md` — Mandatory pre-flight analysis form for reference tasks
- `references/visual-match-checklist.md` — Pass/fail validation vs reference image
- Reference image routing added to `blender-director` SKILL.md
- Screenshot comparison loop protocol in `mcp-integration.md`
- Visual match section in `validation-checklist.md`
- `docs/local_skill_development.md` — Guide for adding custom skills
- `CONTRIBUTING.md` — Contribution guidelines
- `CHANGELOG.md`, `LICENSE`, `.gitignore`, `version.json`, `ROADMAP.md`
- Reference image workflow added to `SKILLS_GUIDE.md`, `README.md`, `CLAUDE.md`

### Changed
- `blender-director` — Now detects attached reference images and routes to match workflow
- `asset-pipeline.md` — Reference collection phase now covers photo analysis
- `rendering` SKILL.md — AgX grading and EEVEE preview settings for animation playback documented
- `skill-routing.md` — Reference phase added to production phase table
- `QUICKSTART.md` — Reference task routing added to cheat sheet
- All SKILL.md frontmatter updated to follow Jeffallan schema (description formula, metadata fields)
- `plugin.json` / `marketplace.json` — Author field updated; keywords expanded

### Fixed
- White hull blowout: documented per-object light material pattern; shared structural material animation flagged as anti-pattern
- EEVEE playback blur: taa_samples + motion blur off pattern documented in rendering skill

---

## [1.0.0] — 2026-07-05

### Added
- 23 specialist skills: `blender-director`, `blender-modeler`, `hard-surface`, `environment-artist`, `character-artist`, `creature-artist`, `sculpting`, `retopology`, `uv-workflow`, `materials`, `texture-workflow`, `geometry-nodes`, `lighting`, `rendering`, `animation`, `rigging`, `procedural-modeling`, `asset-optimization`, `export-pipeline`, `horror-style`, `lowpoly-style`, `stylized-style`, `realistic-style`
- Shared references: `asset-pipeline.md`, `mcp-integration.md`, `mcp-tools.md`, `naming-conventions.md`, `polycount-budgets.md`, `validation-checklist.md`
- Blender MCP integration (`.cursor/mcp.json`, `.mcp.json`)
- `SKILLS_GUIDE.md` — Decision trees and workflow combinations
- `QUICKSTART.md` — Installation for Claude Code and Cursor
- `docs/BLENDER_MCP_SETUP.md` — Full MCP connection guide
- `CLAUDE.md` — Agent instructions
- `.claude-plugin/` — Claude Code plugin manifest
