# Roadmap

State of the Blender AI Plugin 2.0.0 (Blender 5.2+ only) and what is still open. Nothing here carries a version number
for a release that did not happen: the old v1.2 to v1.5 labels were removed, and each open item names its plan id.

The plan with the acceptance test of every item is `docs/plans/iteration-12-parity-and-roadmap.md`. An item is ticked only
when it is merged and its test passes; the iteration 12 work is on branch `feat/parity-and-roadmap` and none of it is
merged yet, so every iteration 12 box below is open.

## Shipped

- Official Blender MCP integration, live work in the open window as the default, background renders for long work
- Skills with tested scripts (`tests/blender/`), a recipe runner, a routing eval and an orchestrator agent
- Validators: `scripts/validate_skills.py`, `scripts/check-manifests.sh`
- Stage gates with a run manifest, `work_copy.py` for destructive steps, `background_render.py`, `generate_lods.py`,
  `geometry-nodes/scripts/scatter_points.py`, the Blender 5.x API notes
- `tests/agent_runs/score_run.py`, which compares an agent run's claims with its trace

## Iteration 12, open

### S. Follow-ups from PR #9 (first batch)

- [ ] **S1** Scorer sees PowerShell launches, foreground renders and real paths, and checks the duration claim
- [ ] **S2** `.gitattributes` keeps `*.sh` at LF
- [ ] **S3** Wording that stated a measured result beyond what was run
- [ ] **S4** The rigid body test fails on a bad collision shape
- [ ] **S5** Render time estimate: first-frame overhead measured and corrected
- [ ] **S6** GitHub Actions run `validate_skills.py` and `check-manifests.sh` on pull requests (unproven until pushed)
- [ ] **S7** Window check made platform-aware (a minimized window is a Windows problem)
- [ ] **S8** `validate` and `export` gates backed by the producer script's result file
- [ ] **S9** This roadmap, and the README credit line

### H. High value

- [ ] **H1** `clash_audit.py`: penetration, containment and floating parts
- [ ] **H2** `silhouette_score.py`: compare a camera view with a reference mask
- [ ] **H3** `fit_search.py`: search named properties against the silhouette score
- [ ] **H4** `ingest_asset.py`: import a local GLB/GLTF/FBX/OBJ/USD file and normalize it

### M. Medium value

- [ ] **M1** `film-production/scripts/flicker_check.py`
- [ ] **M2** `procedural-modeling/scripts/surface_tools.py` (loft, patch, continuity)
- [ ] **M3** `blender-mcp-workflow/scripts/scene_snapshot.py`

### R. Older roadmap items, still open

Scripts:
- [ ] **R1** Real ordered dithering for the PS1 look (`lowpoly-style`)
- [ ] **R2** Terrain heightfield and road corridor (`procedural-modeling`)
- [ ] **R3** Cycles denoiser presets per use case (`rendering`)
- [ ] **R4** Substance Painter texture handoff (`texture-workflow`)
- [ ] **R5** `usd-pipeline` skill with a round-trip script

References:
- [ ] **R6** Multi-angle reference triangulation (`blender-mcp-workflow`)
- [ ] **R7** Scan-match material workflow (`realistic-style`)
- [ ] **R8** Scatter systems: instancing, density masks, collision-aware scatter (`geometry-nodes`; a shorter
  `scatter-systems.md` exists today)
- [ ] **R9** Clothing simulation reference (`character-artist`)
- [ ] **R10** Hair card topology reference (`retopology`)
- [ ] **R11** Facial shape keys and drivers (`rigging`)
- [ ] **R12** Mocap cleanup (`animation`)
- [ ] **R13** Unreal Nanite prep (`unreal-export`)
- [ ] **R14** Unity HDRP material mapping (`unity-export`)
- [ ] **R15** Bloober Team analysis (`indie-horror-aesthetics`)
- [ ] **R16** Parallel work rule: agents never share one live session; stated as unmeasured

## Iteration 12, review follow-ups

Reproduced by the final review and left open. The first ones can give a wrong answer.

- [ ] `flicker_check.py`: false alarms on real renders. 14 of 31 clean Eevee and Cycles sequences at 640x360 return `flicker`. In 4 of them every event is in the 8 px strip left at the frame edge (360 = 22x16 + 8); the other 10 have moving lights, cameras or rotating objects. Until this is fixed, a `flicker` verdict on a real render needs a look at the frames
- [ ] `flicker_check.py` dropout limits: a black frame in a very dark scene (neighbours with a mean near 0.01) is not found at the default `dropout_gap`; a dropout under 16 px is not looked for; a fast flat black or white object is reported as a dropout (113 cells for a box of about 148 px moving about 90 px per frame, and up to 470 cells per frame for a propeller); on a real render, false block events on the same frame can widen the reported region; the event `kind` adds block and cell areas without removing overlap, so a band of 33% on a flat background is called `global_exposure` (the verdict stays `flicker`); on 31 clean Eevee and Cycles renders at 640x360, 14 return `flicker` at ec6c5c3 and still do (events in the 8 px bottom strip of a fast ball and in moving-light, moving-camera and rotating-object scenes)
- [ ] `score_run.py`: misses `Start-Process blender -ArgumentList "-b scene.blend -a"`, `& $blender` and `"$BLENDER"` launches; does not read escaped inline JSON paths; reads `p:/` in a URL as a Windows path; compares the first duration in a message, not the total
- [ ] `scene_snapshot.py`: reads stale transforms when the scene was not updated; saves stale data for an armature in Edit Mode; "latest" can be wrong for two saves in the same second
- [ ] `import_painter_textures.py`: wires a DirectX normal map without flipping it, and without a warning
- [ ] `terrain_heightfield.py`: `replace` accepts an object with a rigid body or a Displace modifier, where vertex Z no longer equals world height
- [ ] `mocap-cleanup.md`: the stated tolerance does not hold on Bezier keys (0.0158 measured against 0.005); linear keys stay within it
- [ ] `silhouette_score.py`: scores a stale transform for an object in an excluded collection
- [ ] `usd_roundtrip.py`: leaves orphan armatures, and loses the selection on a refused run
- [ ] `scan-match.md`: the scan-to-model direction has no test
- [ ] `facial-shape-keys-drivers.md`: "Breaks all of them" and "matches the game minimum" are wrong as written
- [ ] `clash_audit.py`: partial contact against an open mesh can report a false clash
- [ ] `ingest_asset.py`: switches a scene object out of Edit Mode without saying so; the edit is kept
- [ ] `usd_roundtrip.py`: a material slot plus a Set Material node gives a false `ok:false`
- [ ] `score_run.py`: a shell comment such as `-a # {"plan": true}` grants the plan exemption; any slash in a message satisfies the status-path check
- [ ] `import_painter_textures.py`: with shared mesh data, `assign_to=["A"]` also gives B the slot, and listing both adds it twice
- [ ] `surface_tools.py`: a two-point seam raises instead of the documented G1 with G2 not measured
- [ ] `ps1_look.py`: scenes that deliberately share a compositor group both change
- [ ] `scatter-systems.md`: dividing by area is a soft cap, not a maximum (up to 546 at a cap of 500)
- [ ] `scene_snapshot.py`: a user collection named `_Restored_dependencies` gets hidden on restore
- [ ] `hdrp-material-mapping.md`: Unity's page does state the linear import rule; the attribution says otherwise
- [ ] S3: the sentence-by-sentence evidence list the plan asks for is not in the repo

## Not planned, and why

- Needs consent or hardware: a paid orchestrator run, ComfyUI generation (credits), Godot import (not installed), Mac runs
- Low value: mask-to-mesh, segmentation, Scenario-style generation
- Three.js is a non-goal. Downloading assets from inside Blender is banned; fetching stays outside `bpy`
