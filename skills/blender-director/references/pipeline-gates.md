# Pipeline stage gates

Every production runs these stages in order. A stage is done only when its **gate** has evidence:
a script result **and** a capture (screenshot / render). Parallel and sequential rules between
disciplines: `skill-routing.md` (section "Parallel vs Sequential").

## Verdicts

| Verdict | Meaning |
|---------|---------|
| PASS | The gate check ran and met the criterion |
| FAIL | The check ran and missed it. **Blocks every later stage** until fixed and re-checked |
| NOT_CHECKED | The check was not run or could not run (e.g. `verify.checked: false`). **Never a pass**; list it in the final report |
| N/A | The stage does not apply. Declare it up front in the brief with a reason (a relight-only task skips model and export) |

A `validate_asset.py` WARN passes only with a recorded reason (`warn: true` + `reason` in the manifest).

## Stages and gates

| # | Stage | Do | Gate (script result) | Capture |
|---|-------|----|----------------------|---------|
| 1 | inspect | `get_objects_summary`, `scene_audit.py` | scene read; dirty/unsaved state noted | viewport screenshot |
| 2 | brief | production brief, budgets, N/A stages | brief written before any change | reference (if any) |
| 3 | model | blockout, then modeling; destructive steps via `work_copy.py` | `validate_asset.py` has no FAIL on transforms, n-gons, manifold, loose geo | front / 3/4 / side views |
| 4 | look_dev | UVs, materials | validate: UVs and materials PASS; no missing textures | 3/4 view with materials |
| 5 | light_camera | `light_rig.py`, `camera_rig.py` | `camera_rig` result `occluded_by == []` and `visible_fraction` near 1.0; `eye_height` set for first-person views | camera render |
| 6 | validate | full `validate_asset.py` on the export set | verdict PASS (WARN only with a reason); tri budget met | final views |
| 7 | export | engine export script | `exists` true and bytes > 0; export only after stage 6 PASS | none |
| 8 | verify | read the export's `verify` | `verify.ok == true` (no `missing`, no `leaked`); `checked: false` is NOT_CHECKED | none |

## Recording

Append one event per gate with `scripts/run_manifest.py` (stage ids: inspect, brief, model, look_dev,
light_camera, validate, export, verify). The script refuses a PASS after an earlier FAIL, hashes
exported files, and keeps every path inside `out_dir`.

## Repeat-failure stop

The same gate failing twice in a row: stop. Classify the cause as one of **geometry, materials,
lighting, camera, export, tool-error**, record it (`cause` on the second FAIL; `run_manifest.py`
requires it), and report to the user what was tried, what still fails, and the best hypothesis.
No third blind retry.

## Working copies

Before a destructive step (apply transforms/modifiers, join, boolean apply, remesh, decimate) use
the `blender-mcp-workflow` skill → `scripts/work_copy.py`: begin, edit the copies, check, accept or revert.
