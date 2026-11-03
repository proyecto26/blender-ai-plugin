# Changelog

All notable changes to the Blender AI Plugin (formerly Blender Skills Pack).

Format: [Semantic Versioning](https://semver.org/) — `Major.Minor.Patch`

---

## [Unreleased]

Iteration 13: the review follow-ups of iteration 12. Plan: `docs/plans/iteration-13-review-follow-ups.md`.

### Changed
- `flicker_check.py`: no `flicker` and no `inconclusive` on 31 clean Eevee and Cycles renders (was 14 `flicker`), at
  640x360 and upscaled to 1280x720 and 1920x1080; a +0.2 tile for one or two frames, a black tile and a black frame are
  found in 31 of 31. Wider motion search (24 px, coarse to fine), ambiguous blocks scored by the range of their
  predictions, edge strips scored, event `kind` from the union of affected pixels, a noise-aware residual floor.
  Pixel-sized defaults scale with the shorter side (`scale`, reported with the effective sizes); explicit ARGS win
- `score_run.py`: reads `Start-Process` (single or double quotes), `& $blender` and `"$BLENDER"` launches and escaped
  inline JSON; a shell comment after any separator grants no plan exemption; the status path must be the real
  `render_status.json`; the claimed duration is the stated total, or per-frame time times the frame count; URLs no longer
  decide the platform; `echo` lines and quoted `--python-expr` text are not jobs
- `scene_snapshot.py`: updates the scene before reading transforms, computes the transform of an object outside every
  view layer (refuses one with constraints or a bone or vertex parent), refuses an armature in Edit Mode, gives two saves
  in one second distinct names, and leaves a user collection named `_Restored_dependencies` alone
- `silhouette_score.py` refuses an object or camera outside the view layer
- `usd_roundtrip.py`: matches objects whose mesh is named differently, reads object-linked material overrides, removes
  imported armatures and actions, restores the selection on a refused run; a Set Material node with a different material
  is reported as the loss it is
- `clash_audit.py`: partial contact against an open mesh is no clash; two sheets crossing in an X still are
- `ingest_asset.py` refuses while an object is in Edit Mode
- `import_painter_textures.py`: the normal convention is read from the file name when not given (DirectX flips green; a
  name with no token is OpenGL, with a warning); shared mesh data with only some objects listed is refused
- `terrain_heightfield.py` `replace` refuses a rigid body and deforming or subdividing modifiers
- `surface_tools.py`: a two-point seam reports G1 with G2 not measured
- `ps1_look.py` copies a compositor group shared with another scene before changing it
- Docs: mocap tolerance per interpolation (Bezier 0.0158 m), scatter cap stated as soft, shape keys per mesh operation,
  the scan-to-model direction tested, the Unity attribution, the 170 s background run, a covered window marked untested

### Added
- `docs/evidence/iteration-12.md`: the measured sentences of iteration 12 found by a pattern search of the `.md` files changed between `6493832` and `98d7076` (not `.py` docstrings), each with its backing or marked unbacked
- Suites `tests/blender/test_iter13_flicker.py`, `test_iter13_scene.py`, `test_iter13_content.py`, `test_iter13_docs.py`

---

Iteration 12: example parity and the open roadmap. Plan: `docs/plans/iteration-12-parity-and-roadmap.md`.

### Added
- `blender-mcp-workflow`: `clash_audit.py` (penetration, containment, floating parts), `silhouette_score.py` (camera view
  against a reference mask, no render), `fit_search.py` (bounded search of named properties against that score),
  `ingest_asset.py` (local GLB, GLTF, FBX, OBJ or USD file, normalized; URLs and `.blend` refused), `scene_snapshot.py`
  (save, list, diff, restore without removing anything)
- `film-production`: `flicker_check.py`, motion-compensated local flicker on an image sequence; blocks it cannot match are
  reported as not measured
- `procedural-modeling`: `surface_tools.py` (loft, Coons patch, G0/G1/G2 check) and `terrain_heightfield.py`
- `usd-pipeline`: new skill with a checked export and reimport
- `texture-workflow`: `import_painter_textures.py`. Painter itself was not run, and the doc makes no claim about its presets
- `lowpoly-style`: real ordered dither in `ps1_look.py`; the earlier hint promised one that did not exist
- `rendering`: denoiser presets per use case in `render_preset.py`
- References: multi-angle depth, scan match, scatter systems, clothing simulation, hair card topology, facial shape keys and
  drivers, mocap cleanup, Nanite prep, HDRP mapping, Bloober Team. Unreal, Unity and Painter were not run for these
- `.github/workflows/checks.yml` (unproven until it runs on a pull request), `.gitattributes`

### Changed
- **Breaking for one path:** in `run_manifest.py`, a `validate` or `export` PASS now needs `evidence`: a result file written
  by that stage's producer script through `evidence_path`. A typed `result_summary` alone is refused. A process that can write
  files can still forge one; this links gates to script output and stops batch typing
- Parallel work: agents never share one live session, only separate saved copies merged by one owner. Unmeasured
- `background_render.py` plan times a second frame when the first was short: the estimate was 2.5 to 4 times too long on short
  Eevee jobs, and is now within 1.00 to 1.17 of real time over 15 Windows runs
- `score_run.py` sees PowerShell launches and foreground renders, checks the duration claim, and judges the window by platform
- `rigid_body_setup.py` rejects an invalid collision shape before changing anything
- `flicker_check.py`: a sequence with a frame below `min_measured` no longer passes. A hard cut that used to return `pass` now
  returns `inconclusive` and names the frames in `unmeasured_frames`
- `ingest_asset.py` and `usd_roundtrip.py` leave the scene's world, frame range, current frame and fps as they were
- `clash_audit.py` reports a solid inside another even when it spans wall to wall
- `hdrp-material-mapping.md`: Blender's `save()` of a float image divides RGB by alpha; the reference now gives routes checked
  by decoding the file bytes. The only correct route through Blender's writer is 8 bit; the 16-bit route writes the PNG itself
- `scene_snapshot.py`: a repeated name in `restore` no longer crashes Blender
- `fit_search.py`: an integer property steps by at least 1, and `converged` means its neighbours were really tried
- `fit_search.py`: `converged` is true only after a full sweep of every parameter at its final step found no improvement; running out of `max_evals` gives `converged: false`
- `test_handoff.py` records an exception raised outside `check()` as a failure (report written, exit 1)
- `flicker_check.py` reports a tile, band or whole frame that goes flat black or white for one frame (`dropout_cells`; `dropout_level`, `dropout_flat_dev`, `dropout_gap`), checked only on near-uniform near-black or near-white cells against the frames either side. Textured content showing for one frame and a cut are not events; a fast flat black or white object can be reported as a dropout. A black frame in a very dark scene is a stated limit
- The Blender suites now exit non-zero when a check fails

- `hdrp-material-mapping.md` says Blender tags its 8-bit PNG as sRGB even for Non-Color (seen on Windows and macOS); the earlier text said it wrote no colour chunk
- The `background_render.py` estimate notes the macOS timings, which run long on the first plan of a new scene

Known open issues from the final review are listed in `docs/ROADMAP.md`.
- `validate_asset.py` and `clash_audit.py` refuse a mesh in Edit Mode rather than judge stale data; `export_asset.py` exports the current edit
- `fix_asset.py` scales shape keys together with the mesh

Iteration 11: fixes from a measured run of the real orchestrator agent, reviewed by Codex, then from a macOS review.

### Fixed after the macOS review
- `background_render.py`: a refused run no longer overwrites the status of the previous run, a second launch on a folder
  whose status says `running` is refused, and a backend the machine lacks gets a clear error naming the available ones
- `background_render.py`: one process owns an `out_dir`, through an OS lock released when it ends. Two launches at the
  same moment both rendered before, and `overwrite` no longer gets past a run that is still going.
  `tests/blender/race_background_render.py` starts two real processes to check it
- `animation` -> `turntable.py`: frames by the narrower view angle, so a tall subject is no longer cropped at 16:9
- Docs: black captures of a minimized window were seen on Windows only (a macOS review reported a minimized window still
  captured), `BLENDER_PATH` is optional, and a macOS review reported that the `*_for_cli` timeout kills a directly started
  Blender (not re-run since)
- `tests/blender/test_skill_scripts.py`: the rigid body case collides with the crate, not `GEO_Ground`, which scatters
  `COL_Rocks`; the dependency cycle crashed Blender on macOS (exit 139) in 2 of 3 suite runs, as reported by the macOS review
- `score_run.py`: announcements also sees a background render started with `nohup` or a trailing `&`
- `collision-proxy` -> `make_collision.py`: a convex proxy is now a closed hull. It kept the source's faces beside the hull
  (a 14-sided cylinder gave 104 faces and 50 non-manifold edges). A flat mesh is now an error that points to `shape: box`
- `background_render.py`: `plan: true` checks everything, measures one frame and writes the line to send the user before a
  long render starts
- Orchestrator: a render starts with `plan` and a message to the user, and plugin files are read-only during a task

### Added
- `rendering` -> `scripts/background_render.py`: render in a background Blender with an atomic progress status file; it
  refuses to run in the open window and sets the Cycles device in its own process
- `tests/agent_runs/score_run.py`: compares a run's claims with its session trace (preferences, window, skills, gates,
  claims, early finish). It catches regressions; it does not stop a bad report, and one run proves one case

### Changed
- `run_manifest.py`: a capture must exist and is hashed; look_dev and light_camera need one to PASS; any PASS needs a
  non-empty `result_summary`. These check that evidence is present and linked, not that it is true
- The orchestrator names only loaded skills, records gates as stages end, reports a running job as still running, and
  uses its caller line only with a calling agent
- `live-session.md`: no preference changes in the open window, one Blender call at a time, tell the user at once about an
  unusable screenshot

### Fixed
- `live-session.md` said `*_for_cli` stops the process at 120 s; the tool gives up, and through the launcher Blender kept
  running to at least 150 s

Iteration 10: fixes found by running the skills live in an open Blender window.

### Changed
- Live work in the open window is the documented default; long renders and batches run in a background process from a
  saved snapshot. New `blender-mcp-workflow` -> `references/live-session.md` covers undo checkpoints, minimized-window
  screenshots, blocking renders and timeouts, all measured

### Fixed
- Docs no longer offer the Microsoft Store launcher as `BLENDER_PATH`: the `*_for_cli` tools cannot return results
  through it, and `No result marker` now means "outcome unknown"
- Docs no longer say `print` output is lost, or treat `bpy.data.is_dirty` as proof that a file is saved
- `export_asset.py` and `export_godot.py`: `verify` reports `no_geometry` and is not `ok` when a requested mesh
  was written without geometry (glTF omits an empty mesh and keeps its node, so a 176-byte file passed)
- The four export scripts restore the scene camera and the active object's mode, also when the export fails
  (glTF left Edit Mode; moving frames, as glTF and animated FBX do, let a camera marker replace `scene.camera`)
- `capture_views.py` and `preview_frames.py` restore the image colour depth (an EXR at 32 bits came back at 16)

Iteration 9: fixes found by an end-to-end film and export test (a fox short, Blender 5.2.3 headless).

### Fixed
- `assemble_edit.py` scales each scene strip to fit the edit resolution (Blender renders a scene strip at
  the source scene's size, so a 1920x1080 scene in a 1280x720 edit showed only the centre of each shot);
  `strips[].scale` reports the factor
- `capture_views.py` lifts camera-marker bindings while capturing (a shot list's markers switched every
  view to a shot camera) and puts them back afterwards
- `preview_frames.py` and `render_handoff.py` do the same, so a preview, still, pass or clip always shows
  the shot's own camera even when a marker in the shot is bound to another camera

Iteration 8: delivery routing in user words, and the known issues left after iteration 7.

### Changed
- The seven delivery descriptions (unreal-export, unity-export, godot-export, lod-pipeline,
  asset-optimization, collision-proxy, export-pipeline) name the symptoms users report ("imports tiny",
  "comes in rotated -90", "walk through walls") and say to load the skill even for advice
- `unity-export` documents FBX (`export_unity.py`) as the scripted path; GLB goes through glTFast and the
  `export-pipeline` skill
- `assemble_edit.py` writes an AAC audio stream only when audio is supplied (no silent track)

### Added
- `metadata.requires` on every skill that calls another skill's script; `validate_skills.py` checks that each
  `{skills}/<x>/scripts/<y>.py` exists and that `<x>` is declared
- `assemble_edit.py` `verify` (with `render: True`): reads the mp4 back for frame count, size and a decoded
  audio stream of the film's length
- `fix_asset.py` reports `children_not_preserved` (constraints, singular transform, not in the active view
  layer) instead of moving them silently
- Symptom-worded delivery routing cases (`evals-routing/deliv-*`); `execute_blender_code_for_cli` notes that
  it needs `BLENDER_PATH`

### Fixed
- `fix_asset.py`: vertex- and triangle-parented children keep their world transform when scale or rotation is
  applied
- `render_handoff.py`: lists only the files written in this run and warns about leftovers from earlier runs
- Film docs no longer promise an audio check or image-sequence automation that no script performed

---

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
