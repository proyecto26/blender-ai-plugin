# Iteration 9: camera markers must not override the camera a script asked for

## Verified findings

Blender 5.2 calls `BKE_scene_camera_switch_update` when a render starts (`render_init_depsgraph`), so a
timeline marker bound to a camera at the current frame replaces `scene.camera`. A script that sets
`scene.camera = X` and renders can therefore render camera Y. `capture_views.py` was fixed for this in the
previous PR (unbind markers during the capture, restore them in `finally`). Two more scripts have it,
reproduced on Blender 5.2.3 with new tests that fail on the current code:

1. `skills/film-production/scripts/preview_frames.py:124-129` sets `scene.camera = cam` after `frame_set` and
   renders. A user marker at frame 2 bound to CAM_S020, inside shot S010 (frames 1-3): the S010_2 tile
   decodes to RGB [0.19, 0.95, 0.19] (plane of CAM_S020) instead of red; the returned metadata says
   CAM_S010. Test: `tests/blender/test_film.py` case `preview.marker_conflict`.
2. `skills/ai-video-handoff/scripts/render_handoff.py:340-359` (`_set_frame`, `_clip`) do the same for
   stills, passes and clips. Both shot markers rebound to a decoy camera: S010 beauty differs from the
   unbound render by up to 0.600. `handoff.json` still names CAM_S010. Test:
   `tests/blender/test_handoff.py` case `restore.marker_cameras_do_not_override_shots`.

## Fix

Same pattern as `capture_views.py`, kept inside each script (skills are self-contained):

- `preview_frames.py`: before the `try`, `bound = [(m, m.camera) for m in scene.timeline_markers if m.camera]`;
  first lines inside `try` set each `m.camera = None`; `finally` puts each binding back before restoring
  `scene.camera`. The per-shot `scene.camera = cam` stays. The docstring's restore list gains "camera
  marker bindings". The comment on line 126 changes, since markers no longer rebind.
- `render_handoff.py`: `_State.__init__` records `self.markers = [(m, m.camera) ...]`; a new
  `_State.unbind_markers()` is called right after `state = _State(...)` inside the `try`; `restore()` puts
  the bindings back (before `scene.camera = self.camera`). Docstring line 44 lists marker bindings too.
- Clips render with `animation=True`: with no bound markers, `scene.camera` stays the shot camera for every
  frame, which is what a single-shot clip needs.

Not changed: `turntable.py`, `iso_camera.py`, `camera_rig.py` (they create cameras, they do not render),
`assemble_edit.py` (scene strips use `scene_camera`, which overrides markers per strip; the e2e film is
correct), `shot_list.py` (it is what binds the markers on purpose).

## Verification

- New tests fail on HEAD (done: film 28/29, handoff 20/21) and pass after the fix.
- Full suites after the fix: film, handoff, smoke (`test_skill_scripts.py`), refs, recipes; validator,
  `build_catalog.py --check`, `check-manifests.sh`, `claude plugin validate .`.
- Codex review of the diff before commit.

## Delivery: stacked PRs, PR #4 left alone

No `gh stack` extension is installed, so plain stacked branches:

- PR A `fix/edit-fit-and-capture-markers`, base `iteration-6-review-fixes`: the already verified fixes
  (`assemble_edit.py` scales scene strips to the edit size; `capture_views.py` unbinds markers) with their
  tests and a CHANGELOG entry.
- PR B `fix/marker-camera-conflicts`, base PR A's branch: this plan, the two fixes, their tests, CHANGELOG.
- `tests/blender/test_film.py` has hunks for both; PR A's commit carries only its hunks (split by
  temporarily removing the B hunk, then restoring it for commit B).
- When PR #4 merges, PR A is retargeted to `main`, then PR B to `main` after PR A.

## Revision 1 (Seldon/Codex: approve_with_changes, no blocking findings)

- Marker bindings are now part of both test snapshots (`test_film.settings_snapshot`, `test_handoff.snapshot`),
  so every existing restore/failure case (`preview.restore_on_failure`, `restore.after_failure_mid_render`,
  `restore.after_missing_subject`, ...) also checks that bindings come back after an exception.
- The handoff case renders `target: "both"` and also compares the first decoded frame of the moving shot's
  Seam clip (animation render), with `scene.camera` set to a camera that differs from the marker camera and
  checked after the run. Pre-fix tree with the still checks skipped: the clip check alone fails (max diff 0.345).
- `claude plugin eval --runs 1` is not run for this change: no SKILL.md, description or reference changes,
  only script internals, docstrings and tests; the eval suite measures routing and answers, not these renders.
- Results: fixed tree film 29/29, handoff 21/21, smoke 66/66, refs 23/23; validator 0 errors, catalog up to
  date, manifests and `claude plugin validate` OK. Pre-fix tree: only the two new cases fail.
