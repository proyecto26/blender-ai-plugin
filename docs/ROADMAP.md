# Roadmap

State of the Blender AI Plugin 2.0.0 (Blender 5.2+ only) and what is still open. Nothing here carries a version number
for a release that did not happen: the old v1.2 to v1.5 labels were removed, and each open item names its plan id.

The plan with the acceptance test of every item is `docs/plans/iteration-12-parity-and-roadmap.md`. An item is ticked only
when it is merged and its test passes. The iteration 12 items were merged in PR #10 and their suites passed on Windows
and macOS (Blender 5.2.3); what the reviews left open is under "Iteration 12, review follow-ups".

## Shipped

- Official Blender MCP integration, live work in the open window as the default, background renders for long work
- Skills with tested scripts (`tests/blender/`), a recipe runner, a routing eval and an orchestrator agent
- Validators: `scripts/validate_skills.py`, `scripts/check-manifests.sh`
- Stage gates with a run manifest, `work_copy.py` for destructive steps, `background_render.py`, `generate_lods.py`,
  `geometry-nodes/scripts/scatter_points.py`, the Blender 5.x API notes
- `tests/agent_runs/score_run.py`, which compares an agent run's claims with its trace

## Iteration 12, merged in PR #10

### S. Follow-ups from PR #9 (first batch)

- [x] **S1** Scorer sees PowerShell launches, foreground renders and real paths, and checks the duration claim
- [x] **S2** `.gitattributes` keeps `*.sh` at LF
- [x] **S3** Wording that stated a measured result beyond what was run
- [x] **S4** The rigid body test fails on a bad collision shape
- [x] **S5** Render time estimate: first-frame overhead measured and corrected
- [x] **S6** GitHub Actions run `validate_skills.py` and `check-manifests.sh` on pull requests (unproven until pushed)
- [x] **S7** Window check made platform-aware (a minimized window is a Windows problem)
- [x] **S8** `validate` and `export` gates backed by the producer script's result file
- [x] **S9** This roadmap, and the README credit line

### H. High value

- [x] **H1** `clash_audit.py`: penetration, containment and floating parts
- [x] **H2** `silhouette_score.py`: compare a camera view with a reference mask
- [x] **H3** `fit_search.py`: search named properties against the silhouette score
- [x] **H4** `ingest_asset.py`: import a local GLB/GLTF/FBX/OBJ/USD file and normalize it

### M. Medium value

- [x] **M1** `film-production/scripts/flicker_check.py`
- [x] **M2** `procedural-modeling/scripts/surface_tools.py` (loft, patch, continuity)
- [x] **M3** `blender-mcp-workflow/scripts/scene_snapshot.py`

### R. Older roadmap items, still open

Scripts:
- [x] **R1** Real ordered dithering for the PS1 look (`lowpoly-style`)
- [x] **R2** Terrain heightfield and road corridor (`procedural-modeling`)
- [x] **R3** Cycles denoiser presets per use case (`rendering`)
- [x] **R4** Substance Painter texture handoff (`texture-workflow`)
- [x] **R5** `usd-pipeline` skill with a round-trip script

References:
- [x] **R6** Multi-angle reference triangulation (`blender-mcp-workflow`)
- [x] **R7** Scan-match material workflow (`realistic-style`)
- [x] **R8** Scatter systems: instancing, density masks, collision-aware scatter (`geometry-nodes`; a shorter
  `scatter-systems.md` exists today)
- [x] **R9** Clothing simulation reference (`character-artist`)
- [x] **R10** Hair card topology reference (`retopology`)
- [x] **R11** Facial shape keys and drivers (`rigging`)
- [x] **R12** Mocap cleanup (`animation`)
- [x] **R13** Unreal Nanite prep (`unreal-export`)
- [x] **R14** Unity HDRP material mapping (`unity-export`)
- [x] **R15** Bloober Team analysis (`indie-horror-aesthetics`)
- [x] **R16** Parallel work rule: agents never share one live session; stated as unmeasured

## Iteration 12, review follow-ups

Reproduced by the final review of iteration 12; fixed in iteration 13 (`docs/plans/iteration-13-review-follow-ups.md`). The text below is the defect as it was found.

- [x] `flicker_check.py`: false alarms on real renders. 14 of 31 clean Eevee and Cycles sequences at 640x360 return `flicker`. In 4 of them every event is in the 8 px strip left at the frame edge (360 = 22x16 + 8); the other 10 have moving lights, cameras or rotating objects. Until this is fixed, a `flicker` verdict on a real render needs a look at the frames
- [x] `flicker_check.py` dropout limits: a black frame in a very dark scene (neighbours with a mean near 0.01) is not found at the default `dropout_gap`; a dropout under 16 px is not looked for; a fast flat black or white object is reported as a dropout (113 cells for a box of about 148 px moving about 90 px per frame, and up to 470 cells per frame for a propeller); on a real render, false block events on the same frame can widen the reported region; the event `kind` adds block and cell areas without removing overlap, so a band of 33% on a flat background is called `global_exposure` (the verdict stays `flicker`); on 31 clean Eevee and Cycles renders at 640x360, 14 return `flicker` at ec6c5c3 and still do (events in the 8 px bottom strip of a fast ball and in moving-light, moving-camera and rotating-object scenes)
- [x] `score_run.py`: misses `Start-Process blender -ArgumentList "-b scene.blend -a"`, `& $blender` and `"$BLENDER"` launches; does not read escaped inline JSON paths; reads `p:/` in a URL as a Windows path; compares the first duration in a message, not the total
- [x] `scene_snapshot.py`: reads stale transforms when the scene was not updated; saves stale data for an armature in Edit Mode; "latest" can be wrong for two saves in the same second
- [x] `import_painter_textures.py`: wires a DirectX normal map without flipping it, and without a warning
- [x] `terrain_heightfield.py`: `replace` accepts an object with a rigid body or a Displace modifier, where vertex Z no longer equals world height
- [x] `mocap-cleanup.md`: the stated tolerance does not hold on Bezier keys (0.0158 measured against 0.005); linear keys stay within it
- [x] `silhouette_score.py`: scores a stale transform for an object in an excluded collection
- [x] `usd_roundtrip.py`: leaves orphan armatures, and loses the selection on a refused run
- [x] `scan-match.md`: the scan-to-model direction has no test
- [x] `facial-shape-keys-drivers.md`: "Breaks all of them" and "matches the game minimum" are wrong as written
- [x] `clash_audit.py`: partial contact against an open mesh can report a false clash
- [x] `ingest_asset.py`: switches a scene object out of Edit Mode without saying so; the edit is kept
- [x] `usd_roundtrip.py`: a material slot plus a Set Material node gives a false `ok:false`
- [x] `score_run.py`: a shell comment such as `-a # {"plan": true}` grants the plan exemption; any slash in a message satisfies the status-path check
- [x] `import_painter_textures.py`: with shared mesh data, `assign_to=["A"]` also gives B the slot, and listing both adds it twice
- [x] `surface_tools.py`: a two-point seam raises instead of the documented G1 with G2 not measured
- [x] `ps1_look.py`: scenes that deliberately share a compositor group both change
- [x] `scatter-systems.md`: dividing by area is a soft cap, not a maximum (up to 546 at a cap of 500)
- [x] `scene_snapshot.py`: a user collection named `_Restored_dependencies` gets hidden on restore
- [x] `hdrp-material-mapping.md`: Unity's page does state the linear import rule; the attribution says otherwise
- [x] S3: the sentence-by-sentence evidence list the plan asks for is not in the repo

## Iteration 13, open

Measured limits left after the iteration 13 fixes.

- [ ] `flicker_check.py`: 8 of 13 renders of fast flat black or white objects (propellers, black boxes) are still
  reported; a black tile in a near-black shot is found but its region is 32 to 72 px short; a flicker lasting 3 or more
  frames is not found; a pan faster than 24 px per frame at 640x360 (scaled with size) needs `max_motion_px` raised, and
  far beyond the search window (about 200 px per frame at 1080p) a clean shot is reported as `flicker`, not
  `inconclusive`; native 1080p was checked on three Eevee sequences only (no Cycles); in a 1080p pan with a black tile
  an extra small event is reported one frame later; a +0.2 tile's region is more than one block (16 px at 640x360)
  short in 2 of 31 shots (24 and 56 px); the Blender test covers synthetic cases and one real pan, not the 155-case
  harness, which is run by hand
- [ ] `score_run.py`: matches tokens and does not parse the shell (`eval`, command substitution, aliases and paths built
  at run time are not read); without an out_dir the status path is only checked by its file name
- [ ] `usd_roundtrip.py`: linked duplicates at the same transform are paired by fewest differences (reported in
  `ambiguous_pairings`); if they differ only in something it does not measure, the pairing is a guess
- [ ] `import_painter_textures.py`: the normal convention is read from the file name only
- [ ] Blender suites in CI (they run by hand today)

## Not planned, and why

- Needs consent or hardware: a paid orchestrator run, ComfyUI generation (credits), Godot import (not installed), Mac runs
- Low value: mask-to-mesh, segmentation, Scenario-style generation
- Three.js is a non-goal. Downloading assets from inside Blender is banned; fetching stays outside `bpy`
