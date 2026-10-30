# Iteration 8: close the known issues left after iteration 7

Branch: `iteration-6-review-fixes` (PR #4). Each issue below was re-checked against the source on
2026-10-30; evidence is the current file and line. Rules that apply: AGENTS.md (script contract, no
subprocess/eval/exec/deletion, Blender 5.2+ only, skills self-contained, manifests in sync) and the user's
rule that every finding is verified independently before it is reported.

## K1. `fix_asset.py`: triangle-parented (VERTEX_3) children shift when a transform is applied

Evidence: `skills/blender-mcp-workflow/scripts/fix_asset.py:60-66`. Only `parent_type == "OBJECT"` children
get a corrected `matrix_parent_inverse`; the comment says a VERTEX_3 child "may shift, as with Blender's own
Apply Scale". The docstring (line 18) promises "Children of a fixed object keep their world transform".

Fix: snapshot `matrix_world` of every child of `obj` (any `parent_type`), apply, update the view layer, then
for each child solve the parent inverse that restores its world matrix:
`W_c = P @ Mpi @ B` (P parent frame, Mpi parent inverse, B child basis), so with the measured new world
`W_new`, `Mpi_new = Mpi @ B @ W_new^-1 @ W_old @ B^-1`. This is exact for OBJECT, VERTEX and VERTEX_3
parents because it never needs P. Keep the existing OBJECT formula or replace it with the general one
(one code path is simpler; the general one subsumes it).

Test (tests/blender/test_skill_scripts.py): a scaled + rotated parent with an OBJECT child, a VERTEX child
and a VERTEX_3 child; after `apply: "scale"` and `apply: "rotation_scale"` every child's world matrix is
within 1e-5 of before. Fails on the current code for VERTEX_3.

## K2. `render_handoff.py`: the result lists stale files from an earlier run

Evidence: `skills/ai-video-handoff/scripts/render_handoff.py:496`
`files += [folder / n for n in ("beauty.png", "mask.png", "depth.png") if (folder / n).exists()]`.
A run with `passes: ["beauty"]` into a folder that still holds `mask.png` from an earlier run reports that
mask as produced now. The docstring (line 21) says same-name files are overwritten, nothing about leftovers.

Fix: append each path at the point it is written (as the Seam branch already does at line 444), and drop
the `.exists()` sweep. Optionally report pre-existing files not written this run under `warnings`
("left from an earlier run: ...") without touching them (no deletion, per AGENTS.md).

Test (tests/blender/test_handoff.py): run once with beauty+mask+depth, then with beauty only into the same
folder; second result's `files` has no mask/depth, and a warning names them.

## K3. Film: the docs promise an audio check and an image-sequence path that have no tooling

Evidence:
- `skills/film-production/references/audio-and-licensing.md:43` "You can verify duration, start frame,
  channel, volume and that the rendered mp4 contains audio". `assemble_edit.py:232` returns strip data
  (`audio` = requested strips), never anything read back from the rendered file.
- `skills/film-production/SKILL.md:89` tells long films to render each shot to an image sequence and swap in
  image strips; no script does either.

Fix:
- `assemble_edit.py` with `render: True` returns `verify`: after rendering, load the mp4 with
  `bpy.data.movieclips.load` (frame count, size) and `bpy.data.sounds.load` (audio present, duration via a
  temporary sound strip in a throwaway scene that is removed in `finally`), compare to the edit's frame
  count and fps, and report `ok`. The datablocks it loads are removed afterwards. Same shape as the export
  scripts' `verify` (`checked`, `ok`, details), so the pipeline gate reads one convention.
- Rewrite SKILL.md:89 as an explicit manual procedure (per shot: set frame range and camera marker, set
  `render.image_settings` to PNG, render animation to `<project>/renders/<shot>/`; then in the EDIT scene
  use image strips) and say plainly no script automates it yet. No new script this round.
- audio-and-licensing.md:43 states what `verify` checks and what still needs the user's ears.

Test (tests/blender/test_film.py): `render: True, frames: [1, 8]` returns `verify.ok` with `has_audio` true
when audio is given and false without; frame count matches 8.

## K4. `unity-export`: SKILL.md recommends GLB, the script only writes FBX

Evidence: `skills/unity-export/SKILL.md:18,37,39` ("Prefer GLB/GLTF for modern", table rows "Static mesh
modern | GLB"); `skills/unity-export/scripts/` holds only `export_unity.py` (FBX).

Fix: make FBX the documented, scripted default (Unity imports FBX natively; GLB needs the glTFast package).
Keep a GLB row that says: requires the glTFast package; export with the `export-pipeline` skill →
`export_asset.py` `engine: "web"` (glTF, Y-up, metallic-roughness), and note `verify` comes from that
script. No new code.

## K5. Cross-skill recipes are undeclared dependencies

Evidence: 47 SKILL.md files call another skill's script through `{skills}/<other>/scripts/...` (grep
`{skills}/`). Inside the plugin that is the intended convention (AGENTS.md rule 1 forbids `../` file
references, not naming another skill), but a skill copied alone into `.agents/skills/` breaks silently.

Fix:
- Add `metadata.requires: [<skill>, ...]` to each SKILL.md whose code blocks reference `{skills}/<other>/`.
- `validate_skills.py`: every `{skills}/<x>/scripts/<y>.py` reference must point to an existing script and
  `<x>` must appear in `metadata.requires` (or be the skill itself); every `requires` entry must exist.
- README "Known limitations": skills are designed to be installed as one plugin; copying one skill alone
  needs the skills in its `requires`.
- Not chosen: copying shared scripts into each skill (47 duplicates, drift).

## K6. Demo video re-render: out of scope

`docs/blender-ai-plugin.mp4` is a docs asset built by `docs/video/` (macOS font paths, ffmpeg via
subprocess in maintainer tooling). It shows no counts and no changed behaviour, so it is left as is.

## Verification and stop rule

- Each fix lands with the test named above; full suites after: smoke, recipes, film, handoff, refs;
  `validate_skills.py`, `build_catalog.py --check`, `check-manifests.sh`, `claude plugin validate .`.
- Every new test must fail on the pre-fix code (checked by running it against `git stash`-free copies of
  the old scripts in a scratch worktree) before it counts.
- Independent verifier (Codex) on the final diff; findings re-checked against source before reporting.
- Fix loops stop after two rounds with no progress.

---

## Revision 1 (after Seldon/Codex pass 1: request_major_revision, 5 blocking)

Codex findings re-checked against the source before revising: AAC is set unconditionally
(`assemble_edit.py:220`), and `validate_skills.py:111-119` returns a flow collection as its raw string.

### K1 revised: explicit supported domain, no new inversions on the OBJECT path
- OBJECT children keep the current correction (`fix_asset.py:66`), which inverts only the parent's
  world matrices, never the child's, so zero-scale children stay supported.
- VERTEX and VERTEX_3 children use the measured correction
  `Mpi_new = Mpi @ B @ W_new^-1 @ W_old @ B^-1`, only when all hold: the child has no constraints, `B` and
  `W_old` have |det| > 1e-9, and the child is in the current scene (so the view-layer update evaluates it).
- Every child outside that domain is left untouched and listed in the result as
  `children_not_preserved: [{"name", "reason": "constraints" | "singular" | "other scene"}]`; all checks run
  before any mutation. Grandchildren follow their restored parent and need no step. The docstring promise
  (line 18) is narrowed to match.
- Tests: OBJECT, VERTEX, VERTEX_3 children of a scaled + rotated parent keep world matrices within 1e-5
  under `scale` and `rotation_scale`; a zero-scale OBJECT child keeps its world matrix; a constrained
  VERTEX_3 child and a VERTEX_3 child linked only in another scene are reported, not moved.

### K2 revised: the leftover warning is required
Paths are appended where they are written; pre-existing beauty/mask/depth files not written this run are
listed in `warnings` ("left from an earlier run: ..."), untouched. The test requires that warning.

### K3 revised: an audio stream only when audio is supplied, verified by decoding
- `audio_codec` is "AAC" when `audio` is given and "NONE" otherwise, so "no audio supplied" means "no audio
  stream" (no silent track).
- `verify` (render: True only): `bpy.data.movieclips.load` for frame count and size (removed after);
  `aud.Sound(path).data()` decodes the audio, as `tests/blender/test_film.py:404-419` already does on
  Blender 5.2. Reports `audio_stream` (decode succeeded with samples > 0), `audio_seconds`
  (samples / rate), `audio_rms`. `ok` = frames equal the edit's frame count, size matches, and
  `audio_stream` equals "audio was supplied"; with audio, `audio_seconds` must be within 2 frames + 0.05 s
  of the rendered length (AAC padding). A failed decode is `audio_stream: false` with the error, never a pass.
- Tests: with audio, `verify.ok` and `audio_stream` true with RMS > 0; without audio, `verify.ok` and
  `audio_stream` false; the frame count is 8 for `frames: [1, 8]`.

### K4 revised: say how GLB is produced
GLB row: install Unity's glTFast package; export with `export-pipeline` → `export_asset.py` and a `.glb`
`out_path` (the extension picks glTF, Y-up; `engine` only affects FBX presets).

### K5 revised: string-valued dependencies, per the Agent Skills metadata rule
`metadata.requires: "isometric-style, stylized-style"`, a quoted comma-separated string (Agent Skills
metadata values are strings; the validator's parser already handles quoted scalars). The validator splits
it, then checks every `{skills}/<x>/scripts/<y>.py` reference: the script exists and `<x>` is the skill
itself or listed in `requires`; every `requires` name is an existing skill. Self-test cases for a missing
requirement and an unknown name.

### Test-must-fail-on-old-code, made checkable
Each new test is named. Before merging, the new test files run in a scratch worktree at the pre-fix commit
(HEAD) with the old scripts, and the JSON report must show exactly those named cases as FAIL (not
`not_checked`, not an exit code). Then the same cases must PASS on the fixed tree.

## Revision 2 (after Seldon/Codex pass 2: 2 blocking)

### K1: "evaluated" means "a base in the active view layer"
The domain test is `child.name in bpy.context.view_layer.objects` (view-layer bases omit objects whose
collections are excluded, and the depsgraph is built from those bases), and only the active view layer is
updated and read. A child that is in the scene but not a base there is reported with
`reason: "not evaluated in the active view layer"`. Added test: a VERTEX_3 child in an excluded collection is
reported and left untouched.

### K3: absence is known from the encoder setting, never inferred from a decode error
- No audio supplied: the script sets `audio_codec = "NONE"` itself, so `verify` records
  `audio_expected: false` and does not probe audio; `ok` depends on frames and size only. The test also
  asserts, test-side, that `aud.Sound(mp4).data()` raises (confirming no stream was written).
- Audio supplied: `audio_expected: true`; the decode must succeed with samples > 0 and the duration must fit
  the tolerance. Any exception is `audio_stream: false`, `error` recorded, `ok: false`.
