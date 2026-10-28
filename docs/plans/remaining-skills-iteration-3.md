# Remaining 85 skills: eval iteration 3 and fix plan

## What was run

- One skill-creator eval per non-core skill (85 evals, ids 20-104 in
  `evals/skill-creator-workspace/evals.json`), `with_skill` arm, Sonnet subagents.
- Each agent writes one `solution.py` without Blender. The solution is executed through the
  official Blender Lab MCP (`execute_blender_code_for_cli`, Blender 5.2.3) on a fixture `.blend`
  (terrain, rocks, crate with unapplied scale and no UVs, an n-gon mesh, camera, sun), then an
  objective `check` expression is evaluated on the resulting scene (`grade_in_blender.py`,
  `mcp_grade.py`).
- Every check was first run on the untouched fixture: none passes on a no-op.

## Results

81 / 85 pass. Check expressions that were too strict were widened only when the solution
did what the prompt asked by a valid alternative route (renamed crate, modified existing sun,
Stepped F-modifier for "on twos", focus empty instead of focus distance, tower placed outside
the old radius). Each such change was re-verified to still fail on the untouched fixture.

Real failures (bugs in generated code, all in skills with no script and no verified API data):

| Eval | Skill | Failure | Verified 5.2 fact |
|------|-------|---------|-------------------|
| 064 | hd-2d-style | `BMElemSeq[index]` without `ensure_lookup_table()` | bmesh needs `bm.verts.ensure_lookup_table()` before indexing |
| 080 | procedural-modeling | Curve to Mesh output socket `Geometry` | Curve to Mesh outputs `Mesh`; inputs `Curve, Profile Curve, Scale, Fill Caps` |
| 092 | set-dressing | placement loop `continue`s on rejection: 5 props instead of 6-10 | needs retry-until-count scatter |
| 102 | vfx-fx | `flow_behavior = 'CONTINUOUS'` | enum is `INFLOW, OUTFLOW, GEOMETRY` |

## Finding: stub skills

49 of 85 skills have a 10-85 word body, no references of substance and no scripts
(all `genre-*`, most `*-style` and `*-mood`, `visual-console-eras`, ...). Agents report
"the skill is a one-line stub" and design from general knowledge. Their evals pass because
the base model is good, not because the skill helped; a without-skill baseline would score
the same. Those skills currently add almost no value and no hallucination protection.

## Proposed fixes

1. **Scripts for the failing skills** (ARGS in / result out, Blender 5.2 only, no fallbacks,
   tested through the MCP on the fixture):
   - `procedural-modeling/scripts/gn_curve_profile.py`: curve object + GN group
     (Curve to Mesh with Curve Circle profile, Fill Caps), exposed inputs set via
     `mod.properties.inputs.<identifier>.value`.
   - `set-dressing/scripts/scatter_props.py`: clustered props around a target with retries until
     the requested count, raycast to ground, keep-out of a target bbox, shared meshes, `PROP_` names.
   - `vfx-fx/scripts/smoke_domain.py`: Mantaflow gas domain + flow (`flow_type` SMOKE/FIRE/BOTH,
     `flow_behavior` INFLOW), Principled Volume material, low preview resolution.
   - `hd-2d-style/scripts/sprite_billboard.py`: pixel sprite plane (packed image, Closest
     interpolation, alpha), ground-snapped, facing the camera; uses the existing `camera_rig.py`
     for DoF.
2. **bmesh rule** in `blender-mcp-workflow/references/blender-5-api-notes.md`
   (`ensure_lookup_table`, `bm.to_mesh` + `bm.free`).
3. **Stub skills become recipe skills.** Each stub gets a short "Recipe" section that maps the
   style/genre to concrete existing scripts and ARGS, e.g. `retro-8bit-style` ->
   `lowpoly-style/scripts/ps1_look.py` (resolution, no AA) + `compositing/scripts/comp_grade.py`
   (posterize); `noir-style` -> `lighting/scripts/light_rig.py` + `comp_grade.py` monochrome;
   genre skills -> blockout/scale tables + the set-dressing / environment scripts.
   No new scripts unless a recipe repeats a step 3+ times across skills.
4. **Re-evaluate**: rerun the four failing evals and a sample of 10 stub-skill evals with and
   without the skill, graded through the MCP; expected 85/85 with skill and a measurable
   delta (script reuse, fewer hand-written API calls) on the recipe skills.

## Questions for review

- Is "recipe section pointing at shared scripts" the right fix for stubs, versus deleting or
  merging them into fewer, richer skills (e.g. one `retro-console-style` skill)?
- Are the 4 new scripts the right granularity?
- Is the objective-check suite sufficient evidence, or does it need a without-skill arm for all 85?

## Seldon / Codex review (evaluation focus)

Verdict **approve_with_changes**, confidence 0.90, no blocking findings. Change requested: define
the baseline and the delta for recipe skills. Adopted metrics, both arms graded identically through
the MCP on the same fixture:

| Metric | Definition |
|--------|------------|
| Pass rate | objective check passes after executing `solution.py` |
| Script reuse | `solution.py` calls at least one plugin script via `runpy.run_path` |
| API errors | `solution.py` raises (AttributeError/KeyError/TypeError from a wrong bpy name) |

Graduation rule for recipes: a hand-written step that appears in 3+ recipes becomes a script.

## Changes made

- New tested scripts: `procedural-modeling/scripts/gn_curve_profile.py`,
  `set-dressing/scripts/scatter_props.py`, `vfx-fx/scripts/smoke_domain.py`,
  `hd-2d-style/scripts/sprite_billboard.py` (each verified via the MCP on the fixture, idempotent on re-run,
  and passing the eval check that the generated code had failed).
- `blender-5-api-notes.md`: Curve to Mesh sockets, fluid `flow_behavior` enum, layered-action F-curves,
  bmesh `ensure_lookup_table` pattern.
- 47 stub skills: `## Recipe` section mapping the look/genre onto existing scripts, each code block
  executed through the MCP on the fixture.
- `compositing/scripts/comp_grade.py`: removes only its own nodes (`OWN_NODES`) and chains the grade after whatever
  feeds the output, so the lowpoly `SK_PS1_Fog` stage survives (verified fog→grade, grade×2, grade→fog→grade).
  New `posterize` ARG (Posterize node, `Steps` per channel) for 8-bit palettes.

## Iteration 4: with vs without skill

14 evals (the 4 former failures plus 10 recipe skills), both arms run by fresh Sonnet agents; the
`without_skill` arm was forbidden from reading the plugin. Every `solution.py` was executed through the
Blender MCP (5.2.3, background) on a fresh fixture and graded by the same objective check.

| Metric | with_skill | without_skill |
|--------|-----------:|--------------:|
| Pass rate | **14 / 14** | 13 / 14 |
| Script reuse (`runpy.run_path` of a plugin script) | 11 / 14 | 0 / 14 |
| API errors | 0 | 1 |

- All 4 iteration-3 failures (064 hd-2d, 080 procedural-modeling, 092 set-dressing, 102 vfx-fx) now pass
  with the skill, each by calling the new script.
- Baseline failure: 080 (GN pipe, wrong bpy API -> `TypeError: id properties not supported`). Two more baseline
  runs (072 manga, 076 noir) first failed `monochrome()` while reaching black and white by valid routes
  (`image_settings.color_mode = 'BW'`; all-grey materials + white light + black world). The check was widened to
  those routes (`_achromatic_scene()`, camera-invisible shadow casters ignored), re-verified to fail on the
  untouched fixture, and all of iteration 3/4 regraded (iteration 3 unchanged at 81/85).
- Reading: on these prompts the base model mostly succeeds alone, so the pass-rate delta is small (+1). The skill's
  measurable value is reliability and reuse: 11/14 solutions call tested plugin scripts instead of hand-written
  bpy, and 0 API errors vs 1.
- First with-skill pass was 13/14: 087 retro-8bit posterized with hand-written math nodes because its recipe said
  "palette limit is not scripted". Fix: `comp_grade.py` `posterize` + recipe steps 4-5 (posterize, explicit
  no-AA). Recipe re-verified through the MCP (check passes, idempotent, chains after PS1 fog), all 47 recipes
  re-executed (47/47 OK), and a fresh agent re-ran 087 -> PASS. Pre-fix run kept in `run-1-before-fix/`.
- The 3 with-skill runs without script reuse (genre-shooter, genre-soulslike, liminal-space) are geometry
  blockouts the recipes describe with scale tables; they passed by hand-written bmesh/bpy. Candidates for a
  shared `blockout` script if the 3+ graduation rule triggers.

### Seldon / Codex review of iteration 4 (evaluation focus)

Verdict **approve**, confidence 0.95, no blocking findings. Non-blocking (low): the with/without delta is
measured on 14 evals, so it does not capture variance across all 47 recipe skills. Open: a full
without-skill baseline for all 85 skills, and promoting the geometry-blockout steps to a script once 3+
recipes repeat them.
