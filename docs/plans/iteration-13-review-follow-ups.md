# Iteration 13: review follow-ups

Fixes the 22 open items under "Iteration 12, review follow-ups" in `docs/ROADMAP.md`. Each item names a reproduced wrong
answer or a wrong sentence; each fix has a test that fails without it. Blender 5.2+, headless, never the user's open file.

## Batches

Five batches, one edit agent each in its own worktree, on separate files. CHANGELOG, ROADMAP and the generated catalog are
done once by the integrating owner. New Blender tests go in a new suite per batch, `tests/blender/test_iter13_<batch>.py`,
which writes `iter13_<batch>_report.json` with `passed`, `total`, `failed` and exits non-zero on a failure.

### A. `flicker_check.py` (film-production)

- **A1 False alarms on real renders.** Today 14 of 31 clean sequences at 640x360 return `flicker`, and on macOS 4 of 6
  (every moving one). Causes to fix: motion beyond `max_motion_px` (8), the 8 px strip left at the frame edge, moving
  lights, cameras and rotating objects.
  Accept: on the clean real sequences in the verifier folders (`scratchpad/verify11/`, `scratchpad/verify12/`, 31 + 15),
  no `flicker` verdict that is not real content change (a strobe or a light going off for one frame stays flagged).
  Report the count before and after. The edge strip is covered (a defect inside it is found).
- **A2 Detection kept.** The synthetic matrix of iteration 12 (bands, tiles, whole frames, black and white, flat, noise,
  stripes, checker 0/0.05) still finds the frame and the region within one block; a tile injected into a real render is
  found. A textured foreign tile for one frame still gives no event.
- **A3 Event `kind`** uses the union of affected pixels, not a sum: a 33% band on a flat background is `local`.
- **A4 Limits stated honestly** in the docstring and SKILL.md: what is still missed (black frame in a very dark scene if
  not fixed, dropouts under 16 px, fast flat black or white objects) with the measurement.
- Speed: a 1080p 5-frame clean sequence stays within 2x of today's 8.6 s.

### B. `score_run.py` (tests/agent_runs)

- **B1** Detects `Start-Process blender -ArgumentList "-b scene.blend -a"`, `& $blender ...` and `"$BLENDER" ...` launches.
- **B2** Reads escaped inline JSON paths (`{\"out_dir\": \"C:\\\\x\"}`); does not read `p:/` inside a URL as a Windows path.
- **B3** Compares the total duration claimed in a message (sum of parts, or the stated total), not the first number.
- **B4** A shell comment (`-a # {"plan": true}`) does not grant the plan exemption; the status-path check needs the real
  status path, not any slash.
- Accept: a positive and a negative case per point in `tests/agent_runs/test_score_run.py`; existing cases still pass.

### C. Scene state

- **C1 `scene_snapshot.py`:** updates the depsgraph before reading transforms; refuses or reads the evaluated state of an
  armature in Edit Mode, saying which; "latest" is unique for two saves in the same second; a user collection named
  `_Restored_dependencies` is not hidden on restore.
- **C2 `silhouette_score.py`:** an object in an excluded collection is refused or scored with its real transform.
- **C3 `usd_roundtrip.py`:** no orphan armatures after a run; selection and active object restored on a refused run; a
  material slot plus a Set Material node is not a false `ok:false`.
- **C4 `clash_audit.py`:** partial contact against an open mesh does not report a false clash (and a real one still does).
- **C5 `ingest_asset.py`:** a scene object in Edit Mode is reported and the edit kept, or the run refuses; no silent switch.

### D. Content tools

- **D1 `import_painter_textures.py`:** a DirectX normal map gets its green channel flipped (or the run warns and asks for
  the convention); with shared mesh data, `assign_to=["A"]` does not give B the slot, and listing both adds it once.
- **D2 `terrain_heightfield.py`:** `replace` refuses an object with a rigid body or a Displace (or other deforming) modifier.
- **D3 `surface_tools.py`:** a two-point seam reports G1 with G2 not measured, as documented, instead of raising.
- **D4 `ps1_look.py`:** changing one scene does not change another scene that shares the compositor group (copy on write,
  or refuse with the reason).

### E. Docs

- **E1 `mocap-cleanup.md`:** the tolerance stated per key interpolation, with the Bezier number measured.
- **E2 `scan-match.md`:** a test for the scan-to-model direction, or the sentence removed.
- **E3 `facial-shape-keys-drivers.md`:** "Breaks all of them" and "matches the game minimum" rewritten to what is true.
- **E4 `scatter-systems.md`:** dividing by area is a soft cap (546 at 500 measured), or a hard cap implemented and tested.
- **E5 `hdrp-material-mapping.md`:** the attribution matches Unity's page on the linear import rule.
- **E6 S3:** the sentence-by-sentence evidence list (each stated measurement and the test or run that backs it) as
  `docs/evidence/iteration-12.md`.

## Review

Each batch: the agent's own test run, then an independent verifier that did not write the fix, then a Seldon review of the
delivered code (Codex CLI, read-only; no `judge-runner.sh` is installed, so it is run directly). Fix loops stop after two
rounds with no progress. One PR; the user merges.

## Checks

`validate_skills.py`, `check-manifests.sh`, `test_score_run.py`, every Blender suite including the new ones, the race test,
`userpref.blend` unchanged.

## Out of scope

Paid orchestrator run, ComfyUI, Godot and Unity imports (consent or install); Blender suites in CI is a separate PR.
