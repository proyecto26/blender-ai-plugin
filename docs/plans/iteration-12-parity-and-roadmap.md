# Iteration 12: example parity and the open roadmap

Branch: `feat/parity-and-roadmap`, off `main` at 6493832. Plugin 2.0.0, Blender 5.2+.

Source of the items: a comparison against `examples/` (third-party, used as inspiration only: no code is copied, no script
is run) and `docs/ROADMAP.md`. An independent verifier confirmed each gap against source.

Rules for every item: AGENTS.md script contract (`ARGS:` docstring, `main(**kwargs)`, JSON-safe result; no subprocess,
sockets, eval/exec, file deletion, network; only `bpy`, `bmesh`, `mathutils`, `numpy` and the standard library).
Non-destructive by default. Each script gets a test in a real Blender with a case that must FAIL when the script is wrong.
Reference prose with Blender code goes through the recipe runner, or is marked untested. Claims about other products are
checked against their docs and cited.

## H. High value

- **H1 `blender-mcp-workflow/scripts/clash_audit.py`** (read-only). World-space BVH on evaluated meshes; AABB broad phase.
  Reports penetrating pairs with an estimated depth, objects fully inside others, and floating parts (connected groups by
  contact within `gap_max_m`). Touching faces are not a clash. Accept: touching cubes pass; interpenetrating cubes fail;
  a cube inside a cube fails, although no surfaces cross; a floating part is named; modifiers count; scene unchanged.
  Depth means the deepest vertex of one mesh inside the other, found by ray parity along the nearest axis of overlap; a known
  0.25 m overlap must report 0.25 within 10%, and a known 0.03 m gap must group or not group according to `gap_max_m`.
  Open meshes have no inside: containment and depth are reported as `not_measured` for them, never as a pass.
- **H2 `blender-mcp-workflow/scripts/silhouette_score.py`** (read-only). Projects evaluated triangles through each named
  camera, rasterizes with numpy, compares with a reference mask (alpha, or background from the corners): IoU, bbox and
  centroid drift per view, verdict against a threshold. No render needed. Accept: exact mask IoU > 0.98; object moved or
  scaled scores measurably lower; wrong shape fails; loaded image datablocks are removed and the scene is unchanged. The test's masks are not made by the
  scorer: they come from a real Workbench or EEVEE render of the same camera, plus hand-computed masks for perspective
  foreshortening, an object partly behind the camera or outside the frame, and image orientation (an asymmetric shape).
- **H3 `blender-mcp-workflow/scripts/fit_search.py`**. Coordinate search over named numeric properties reached through
  `path_resolve`, scored by H2. Restores every value unless `apply: true`. Bounded by `max_evals`. Accept: recovers a known
  scale within tolerance from a wrong start; values restored when `apply` is false; a bad path is an error before any change.
- **H4 `blender-mcp-workflow/scripts/ingest_asset.py`**. Imports a local GLB/GLTF/FBX/OBJ/USD file the user supplied into a
  new collection, then normalizes only the imported objects: scale to a target size, origin at base center, names with a
  prefix, optional up-axis fix; ends with the `validate_asset.py` checks. Refuses URLs and `.blend`. Accept: round trip
  for each of GLB, FBX, OBJ and USD, with wrong scale, comes out at target height with the same vertex count; existing objects
  unchanged; a parented hierarchy keeps its world shape; URL refused. A format whose test does not pass is not advertised.

## M. Medium value

- **M1 `film-production/scripts/flicker_check.py`** (read-only). Local temporal metric on an image sequence. A plain
  second difference confuses a pan over stripes with flicker, so each block of frame t is first matched in t-1 and t+1 within
  a search window (`max_motion_px`), and only then is the second difference taken. Domain, stated in the output: motion within
  that window; faster motion is `not_measured` for that block. Accept: synthetic local flicker detected at the right frame and
  region; a constant-speed pan over high-contrast stripes passes (the case that breaks the naive metric); a global exposure
  pop is reported; flicker in a panning shot is still detected.
- **M2 `procedural-modeling/scripts/surface_tools.py`**. `loft` through ordered sections (resampled to one count), `patch`
  (Coons from four boundaries), `continuity` (G0/G1/G2 along a shared boundary). Accept: known cases pass and a creased
  join fails G1; a tangent join with a curvature jump passes G1 and fails G2; mismatched boundaries are refused.
- **M3 `blender-mcp-workflow/scripts/scene_snapshot.py`**. `save` (copy of the file, never changing the open file's path),
  `list`, `diff` (added, removed, changed transforms and mesh hashes), `restore` (appends named objects from the snapshot
  into a `_Restored` collection, removes nothing). Accept: all four, with the open file's path and dirty objects untouched.

## R. Open roadmap

Scripts:
- **R1 PS1 dithering**: real ordered dither in the compositing path used by `lowpoly-style/scripts/ps1_look.py`; fixes the
  false hint at `ps1_look.py:193`. Accept: a rendered gradient has few levels and a Bayer pattern; a test compares pixels.
- **R2 Terrain and road**: `procedural-modeling/scripts/terrain_heightfield.py` (seeded `mathutils.noise`, optional
  flattened corridor along a curve) plus `references/terrain-road.md`. Accept: same seed gives the same mesh; corridor height
  matches the curve.
- **R3 Denoiser presets**: use-case presets in `rendering/scripts/render_preset.py`, table in SKILL.md. Accept: each preset
  sets real 5.2 properties and returns prior values.
- **R4 Substance Painter handoff**: `texture-workflow/scripts/import_painter_textures.py` wires exported maps by name, with
  `references/substance-painter-handoff.md`. Accept: synthetic maps wired, non-color set for data maps. Painter itself is
  untested and the doc says so.
- **R5 USD skill**: new `usd-pipeline` skill with `scripts/usd_roundtrip.py`. Accept: export, reimport, object count, transforms,
  vertex and face counts match, and material names survive. Catalog rebuilt; routing eval cases added.

References, each short, in the skill that owns the topic:
- **R6** `blender-mcp-workflow/references/reference-image-depth.md` (multi-angle triangulation)
- **R7** `realistic-style/references/scan-match.md`
- **R8** `geometry-nodes/references/scatter-systems.md` expanded with instancing, density masks and collision-aware scatter
- **R9** `character-artist/references/clothing-sim.md`, pointing at `cloth-sim`
- **R10** `retopology/references/hair-card-topology.md`, pointing at `hair-groom`
- **R11** `rigging/references/facial-shape-keys-drivers.md`, with a tested recipe
- **R12** `animation/references/mocap-cleanup.md`, with a tested recipe
- **R13** `unreal-export/references/nanite-prep.md`
- **R14** `unity-export/references/hdrp-material-mapping.md`
- **R15** `indie-horror-aesthetics/references/bloober-team.md`
- **R16 Parallel work**: rule in `agents/blender-design-orchestrator.md` and `skill-routing.md`. Agents never share one live
  session; parallel work happens only on separate saved copies, merged by one owner. Stated as unmeasured.

## S. Follow-ups from PR #9

- **S1** Scorer `tests/agent_runs/score_run.py`: sees PowerShell launches, foreground renders, real paths, and checks the
  duration claim. Test: replayed baseline transcripts that told the user nothing score FLAG, not merely not OK, and valid ones score OK.
- **S2** `.gitattributes` with `*.sh text eol=lf`; `check-manifests.sh` passes in WSL and Git Bash.
- **S3** Wording found in the PR #9 review: `mcp-tools.md` and CHANGELOG entries must not state a measured result beyond
  what was run. The agent lists each changed sentence and its evidence.
- **S4** The rigid body test fails on a bad collision shape.
- **S5** Time estimate on short renders: measure the first-frame overhead, then correct or document it.
- **S6** GitHub Actions: `validate_skills.py` and `check-manifests.sh` on pull requests, with actions pinned by commit and
  read-only permissions. `check-manifests.sh` needs the Claude CLI and a schema validator and allows no skip in CI, so the
  workflow installs both at pinned versions. Blender suites stay local. Accept: the same commands pass locally, and the
  workflow runs on the PR once it is pushed; until then it is unproven and reported so.
- **S7** Window check made platform-aware. **S8** Thread 8: gates backed by a result file, not typed in at the end. Boundary:
  `validate_asset.py`, `clash_audit.py` and `export_asset.py` take an optional `evidence_path` inside the run folder and write
  their own result there (`script`, time, verdict inputs). `run_manifest.py` gets `evidence`: for `validate` and `export`, a
  PASS needs it. The manifest reads the file, records its sha256, derives the verdict, and refuses a PASS when the file names
  another script, reports a failure, or predates the stage's last earlier event. A typed `result_summary` alone is refused for
  those stages. Stages judged by eye (`look_dev`, `light_camera`) keep the capture rule; others stay as they are. Accept,
  negative cases: PASS with only a summary, with a failing file, with another script's file and with a stale file are all
  refused and leave the gate NOT_CHECKED. Stated limit: a process that can write files can forge one; this links gates to real
  script output and stops batch typing, it is no proof against an adversary. Existing tests and the schema are updated, and
  the change is called out as breaking for that one path.
- **S9** `docs/ROADMAP.md` rewritten to the real state with stale version labels removed; `README.md:320` says "based on".

## Out of scope, and why

Needs consent or hardware: the paid orchestrator run (last $7.21), ComfyUI generation (credits), Godot import (not
installed), Mac runs. Value Low: mask-to-mesh, segmentation, Scenario-style generation. Three.js stays a non-goal.
Downloading assets from inside Blender is banned; fetching stays outside `bpy`.

## Delivery

Batches, in order: S (first, it protects the rest), H, M, R. One edit agent per batch in its own worktree. New code goes in new
files; edits to shared files (SKILL.md, agents, tests) stay with the batch that owns them, CHANGELOG and the generated catalog
are done once by the integrating owner, who reruns the suites after every merge. New suites: `tests/blender/test_parity.py`, `test_roadmap.py`.
Each point gets a Seldon review of the code delivered. Fix loops stop after two rounds with no progress. No merge.

## Checks

`validate_skills.py`, `check-manifests.sh`, every Blender suite, the routing eval offline scorer if it needs no tokens (the
token-spending eval pilot is deferred with the paid run), and
a stat of the user's `userpref.blend` before and after, so the tests are shown not to touch it.
