# Iteration 15: lessons from blender-agent-skills

A third-party pack of 28 Blender 5.2+ skills ("blender-agent-skills", read-only copy in `../examples/skills`) was compared
with ours by Codex in five areas. Nothing from it was run. Every finding below was re-checked against the source by a
separate verifier; refuted items are dropped and partial ones are restated. The goal is the complaint users have about
AI-written Blender work: scripts that look right but fail, messy UVs, twisted rigs, and the user opening Blender to fix
it by hand. We copy measurements and ideas, never code: their helpers use `subprocess`, a shared `_bpyx` module and
`run()`, which break our AGENTS.md rules (self-contained skills, `ARGS`/`main`, non-destructive by default).

Verdicts: every check reports `PASS`, `WARN`, `FAIL` or `NOT_CHECKED` (with the reason). An object's verdict is FAIL if
any check fails, else WARN if any check warns or was not checked, else PASS; the overall verdict is the worst object.
A script that measured nothing returns FAIL with a note. This is how `clash_audit.py` already treats `not_measured`.

Rules for every item: Blender 5.2+, headless, scratch files only (never the user's open file); a new check returns a
verdict that cannot be PASS when it measured nothing (`NOT_CHECKED` / `not_measured`); each fix has a test in
`tests/blender/test_iter15_<batch>.py` that fails on the old code; no version branches; no file deletion.

## Phase 1 (this iteration)

### A. Bugs found in our scripts (all verified)

| # | Script | Defect | Fix and test |
|---|---|---|---|
| A1 | `uv-workflow/scripts/uv_unwrap_check.py:118` | "Measure only" (`unwrap=False`) creates a UV layer on a mesh with none and reports density 0 with no error | Return an error and leave the mesh unchanged unless `unwrap=True` (lightmap-only path keeps working) |
| A2 | same, `:96-104` | `uv_space_used` sums face areas, so stacked faces count twice (2.0 for two full tiles) | Rename to `uv_area_sum`; add `uv_coverage` (union, per UDIM tile) |
| A3 | `texture-workflow/scripts/bake_maps.py:86` | A rerun reuses an image by name at its old size and reports the new size | Refuse an existing image of another size, or create a new one; report the real size |
| A4 | same, `:99` | Operator result ignored; a silent CANCELLED still saves and lists the image | Require `FINISHED` before saving (most failures already raise) |
| A5 | `materials/scripts/pbr_material.py:51` | An emission texture is wired with strength 0 | Default strength `None`: 1.0 when a texture is given, unless the caller sets it |
| A6 | `rigging/scripts/rig_check.py:20` | `L_`/`R_` prefixes (recommended in SKILL.md) escape the symmetry check | Accept prefixes and suffixes; align the docs on one convention |
| A7 | same, `:53,73-79` | Missing requested meshes are dropped and the rig can PASS; an Armature modifier on any rig counts | Error on missing or non-mesh names; require a modifier targeting this armature, in the verdict |
| A8 | `cloth-sim/scripts/cloth_setup.py:61-64,81` | A rerun with no pin group keeps the old pin and reports `pinned: False` | Report the real `vertex_group_mass`; clear only on explicit `pin_group=""` |
| A9 | `asset-optimization/scripts/optimize_mesh.py:59-60,75` | Edits a mesh shared with other objects | Make the mesh single-user first (as `fix_asset.py:132` does) |
| A10 | `unity-export/scripts/export_unity.py:70`, `godot-export/scripts/export_godot.py:108` | Missing names are dropped silently; verification only sees the rest | Fail before export, naming every missing object |
| A11 | `lod-pipeline/scripts/generate_lods.py:61-67` | Deletes any object named `<base>_LOD<i>`, including a hand-made one | Replace only objects this script tagged; refuse others |
| A12 | `export-pipeline/scripts/export_asset.py:194-220` | Exporter result ignored; an old file at the path counts as success | Require `FINISHED` and a file stamp that changed in this call |
| A13 | `blender-mcp-workflow/scripts/fix_asset.py:110-140` | No `finally` after Smart UV (Edit Mode and active object left changed); `uv_scale=0` divides by zero after transforms were applied; any `uv` value but `box` silently runs Smart UV | Validate arguments before any change; restore mode and active object in `finally` |
| A14 | `procedural-modeling/scripts/gn_curve_profile.py:115` | World-space points written as local on a moved object | Apply the inverse world matrix; test a moved, rotated rerun |
| A15 | `hard-surface/scripts/bevel_stack.py:38-50` | A new bevel is appended after an existing weighted-normal modifier | Reorder owned modifiers in place; assert the order in the test |
| A16 | `set-dressing/scripts/scatter_props.py:72` | Props get Blender's default per-face UVs (every face on the full tile, all overlapping), which the new overlap gate will flag | Box-project each face of the generated props as its own island and pack them with a margin; the test runs the new UV check on them (no collapsed faces, no overlap) |

Not fixed: `globals().get("ARGS") or _cli_args()` ignores an explicit `ARGS={}`. It is latent (no caller passes `{}`) and
changing it touches AGENTS.md and the validator; it goes to the roadmap.

### B. Scripts that fail when run ("looks right, errors")

- **B1** The verdict scripts (`validate_asset.py`, `uv_unwrap_check.py`, `rig_check.py`, `stress_check.py`,
  `clash_audit.py`) take an optional `result_path` and `run_id`: the result JSON, with that `run_id`, is written there at
  the end (temp file, then replace). The documented headless call becomes
  `blender -b f.blend --python-exit-code 1 --python <script> -- --args-file a.json` with both in the args, and the rule:
  the run succeeded only if the exit code is 0 or 2 and `result_path` exists with this `run_id`; a missing file or
  another `run_id` is a failed run, never a pass. Only as a background CLI script (`bpy.app.background` and
  `__name__ == "__main__"`, never inside a live `runpy` call) does a FAIL verdict exit with code 2.
  Test from `tests/` with that same command (a process launched by the test, as `race_background_render.py` does):
  PASS gives 0 and the file; FAIL gives 2 and the file; an exception gives 1 and no file; a script path that does not
  exist gives no file (exit code measured and written down); a stale file from an earlier `run_id` is not accepted.
- **B2** `references/mcp-tools.md` and `blender-5-api-notes.md`: every `bpy.ops` call checks `{'FINISHED'}`; the enum
  discovery snippet (`bl_rna.properties[p].enum_items`); missing 5.x rows (Boolean solver enum, UV select sync, bone
  selection, action slots) checked by a small headless test each. No 5.3 rows unless verified on 5.3.

### C. Messy UVs

Extend `uv-workflow/scripts/uv_unwrap_check.py` (measure only, unless `unwrap=True`). A new `uv_layer` argument names
the channel to measure (name or index; default the active render layer), and the result names the channel measured; a
missing channel is an error. Lightmap rules apply to the channel created or named as the lightmap. Fixture: one mesh
with an overlapping render channel (`allow_overlap=True`, PASS) and a broken lightmap channel (FAIL), measured in two
calls, with opposite verdicts.
- per object: island count; collapsed UV faces (area below 1e-12); overlapping UV area (triangle intersection, shared
  edges exempt); union coverage per tile; per-island texel density min, max and spread; stretch as p95 of triangle
  anisotropy (UV vs 3D singular-value ratio).
- verdict for a unique-bake or lightmap channel: FAIL on any collapsed face or overlap; WARN on spread above 1.3,
  coverage below 0.75, stretch p95 above 1.2. Declared mirrored or stacked layouts (`allow_overlap=True`) skip the overlap
  rule. Fixtures: stacked faces, one collapsed face, two islands at different scales, a stretched cylinder.
- unwrap options: `method` (`smart`, `seams`, `min_stretch`), `margin_px`, `seams_from_angle`; per object, never a batch
  fallback that touches other objects.

`blender-mcp-workflow/scripts/validate_asset.py` gains the cheap part (collapsed UV faces and overlap ratio) so every
asset gate catches it.

### D. Broken geometry before the user sees it

`validate_asset.py` gains, on evaluated world-space geometry: faces below 1e-10 m², edges below 1e-7 m, edges whose two
faces wind the same way (inconsistent normals), closed shells with negative signed volume (inside out). Open shells
report `orientation: not_measured`, never PASS for that check. Lengths and areas are converted with the scene
`unit_settings.scale_length` before the thresholds: the same physical fixture at scale 1.0 and 0.01 gets the same
verdict. Fixtures for each defect.

`clash_audit.py` gains an opt-in `within_mesh=True` that treats connected islands of one mesh like separate objects
(floating parts, coplanar overlap within 1 mm), gated like `require_connected`.

### E. Twisted rigs

- **E1** `rig_check.py` adds: non-finite weights; deform weight sums off by more than 0.001; zero-length bones;
  unapplied armature scale or rotation; mirrored bone Z axes more than 3 degrees apart on symmetric rigs (asymmetric
  bones reported, not failed).
- **E2** New `rigging/scripts/stress_check.py`: poses mapped bones (explicit map, or name roles; missing roles fail)
  through arms raised, elbows and knees at 130 degrees, crouch, and forearm twist at 90 and 180 degrees, on a temporary
  action that is removed, with the original action, frame and IK/FK values restored in `finally`. Measures per limb, on
  the evaluated mesh: edge stretch p95, a twist collapse ratio (minimum cross-section width vs rest) and non-finite
  vertices. Each pose is checked first: the evaluated bone must reach the requested angle within 5 degrees, else that
  pose is `NOT_REACHED` (a FAIL naming the bone and the angle reached), so a constraint that blocks the pose can never
  look like a healthy rest mesh. Fixtures and expected verdicts: a good cylinder limb (PASS, every pose reached), the
  twist on one bone (FAIL on collapse at 180 degrees), an unweighted ring (FAIL on stretch), a limb with a Limit
  Rotation constraint at 30 degrees (FAIL, `NOT_REACHED`), a rig with a missing role (FAIL). Thresholds start at
  collapse ratio below 0.5 and stretch p95 above 1.5; the measured fixture values go in the docstring, and each
  threshold must sit between the good and bad values with a margin of at least 20% of the gap.

### F. Integration

`qa-review/SKILL.md` and `blender-mcp-workflow/references/validation-checklist.md` name the new checks and the order:
`validate_asset` after every modeling pass, `uv_unwrap_check` before baking or export, `rig_check` then `stress_check`
after skinning. ROADMAP and CHANGELOG are updated once by the integrator. All existing suites still pass.

## Phase 2 (next, recorded in the roadmap)

Medium value, verified gaps: `env_report.py` preflight (version, engines, add-ons, enum values, read-only); material
dependency checks (used empty slots, missing image files, color data on non-color sockets); `capture_views.py` isolation,
wire view and a contact sheet; FBX round trip in a temporary scene (dimensions 0.1%, bone hierarchy, clip names);
material, texture and bone budgets; bake controls (several high sources, cage, UV layer, ray distance, normal convention,
metallic and ORM); retarget and visual bake checked on evaluated playback; animation loop seam check; garment
penetration over poses; shape key audit; modular kit check; scatter spacing, slope and height limits; GN diagnostics;
sculpt preparation on a duplicate. Low: numeric PBR statistics, auto retopology on a duplicate, outline normals, hair card
checks.

## What we keep from ours

Verified as equal or better and not to be replaced: live-session recovery and unknown results (`live-session.md`), the
`ARGS`/`main` contract, clash groups and unresolved-measurement verdicts, glTF content verification, render completion
checks, safe texture import, facial driver verification, mocap cleanup assertions, terrain and GN copy-on-write.

## Their defects we must not copy

Batch success that hides a QA fail; batch defaults that overwrite or factory-reset the open file; a launcher without a
timeout that calls a missing result success; name-based deletion of existing objects, actions and keys; binding that
always returns ok; retarget error measured before the action exists; stress poses that leave scene state changed;
garment checks that pass with zero coverage; review renders that leave object colors and output format changed;
a global rebuild of a shared node group; video render success without a file; curvature blur that wraps image borders;
a scatter "check" that never compares to its limits.
