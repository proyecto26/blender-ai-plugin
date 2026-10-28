# Iteration 5: full with/without-skill baseline (85 skills) and a shared blockout script

Follows `remaining-skills-iteration-3.md` (iteration 3: 81/85 with skill; iteration 4: 14 evals, with 14/14 vs
without 13/14, script reuse 11 vs 0, API errors 0 vs 1). Seldon's open items from iteration 4:
(a) the with/without delta was measured on only 14 of 85 evals; (b) geometry blockout steps are hand-written.

## Part A: shared blockout script (do first, because it changes recipes the baseline will measure)

### Evidence for graduating it (rule: a hand-written step in 3+ recipes becomes a script)
- Iteration 4 with-skill runs that did not call any plugin script were exactly the 3 geometry-blockout evals:
  056 genre-shooter (cover ring: `bmesh.ops.create_cube` + Bevel + `ray_cast` ground snap), 057 genre-soulslike
  (bonfire: cones, icospheres, cubes, ring layout, ground snap), 069 liminal-space (corridor shell from
  `from_pydata`, ceiling panels via Array).
- Recipes that describe blockout geometry in prose ("by hand", walls, corridors, cover, platforms):
  genre-shooter, genre-soulslike, genre-metroidvania-roguelike, genre-puzzle-platformer, genre-action-combat,
  genre-stealth, liminal-space-style, brutalist-mood, fantasy-worlds, sci-fi-punk-worlds, dark-gritty-mood.
- No existing script covers it (34 scripts listed; none builds primitives or room shells).

### Script: `skills/environment-artist/scripts/blockout.py`
Same contract as the other scripts: `ARGS` in, `result` dict out, Blender 5.2 API only, no fallbacks,
idempotent, never touches objects it did not create.

ARGS:
- `group` (str): name prefix and idempotency key; rerunning replaces only objects tagged `obj["blockout"] == group`.
- `pieces` (list): each `{kind, size:[x,y,z], at:[x,y] | [x,y,z], rot_z, name, material}`, where
  `kind` is box | cylinder | cone | rock | ramp | stairs. The pivot is on the floor, and the piece is ground-snapped
  by raycast when `at` has 2 components.
- `layout` (optional): `{pattern: ring | line | grid, count, radius | spacing, center: [x,y] | object name,
  face_center: bool}`. It repeats `pieces[0]` (or cycles through `pieces`) over the pattern.
- `room` (optional): `{size:[w,l,h], at, wall:0.2, open_ends:[...], fixtures:{size, spacing, emission}}`. It builds a
  floor/walls/ceiling shell with inward normals, plus emissive ceiling fixtures (one shared mesh, instanced).
- `ground` (str, optional): mesh to snap onto. The default is the lowest surface hit, ignoring the group's own pieces.
- `bevel` (float, default 0), `collection` (default `COL_Blockout`), `seed`.

Behaviour: shared mesh per kind and size, UV layer (box projection), grey `MAT_Blockout_*` materials (or
the named material), and stable names `BLK_<group>_<kind>_NN`. The result reports names, world bboxes, the
minimum neighbour spacing and any intersections with non-group meshes.

### Verification (via MCP on the fixture, background only)
1. Unit runs: a ring of 6 boxes around SM_Crate (spacing >= 3 m, z on terrain, no overlap with the crate bbox),
   a bonfire (ring of 9 rocks + cones), a 24 m corridor with 6 fixtures (inward normals, emissive count),
   ramps and stairs (bbox matches size), and running each twice (object count unchanged).
2. Recipes of the skills above are updated to call it. `run_recipes.py` must stay at 47/47 OK.
3. Eval checks 056, 057 and 069 must pass when evaluated on the recipe output alone.

## Part B: full baseline over all 85 non-core skills

### Design
- Frozen state: all runs use the repo at one commit (after Part A), recorded in the results.
- `without_skill` arm: all 85 evals. The baseline does not depend on skill content, so the 14 iteration-4
  baseline runs are reused and 71 are new. The prompt is the same with the plugin path forbidden (as in iteration 4).
- `with_skill` arm: every eval whose skill changed since its last with-skill run is re-run. That is 37 skills changed
  since iteration 3 and not in iteration 4, plus the skills whose recipe changes in Part A, plus 087 (already
  re-run after its fix). Unchanged skills (34) reuse their iteration-3 with-skill run, which used identical skill
  content. Reuse is flagged per row so it can be audited.
- Grading: every solution executes via `mcp_grade.py` on a fresh fixture with the same objective check, and
  `it4_metrics.py` is generalized to `metrics.py`.
- Metrics per arm: pass rate, script reuse (`runpy.run_path` of a plugin script), API errors (bpy
  AttributeError/KeyError/TypeError/IndexError/RuntimeError at runtime). Per skill category (core-scripted,
  recipe/stub, genre) so a weak category is visible.
- Non-discriminating evals (both arms pass) are listed. Evals where the baseline passes and the skill fails are
  treated as regressions and investigated individually.

### Cost and variance
- ~110 new agent runs at ~55k Sonnet tokens each (~6M tokens), in batches of 20 (the concurrency limit).
- One run per arm per eval. Single-run variance is acknowledged; any eval whose arms disagree is re-run once in
  both arms before it is reported (a tie-breaker, not cherry-picking: both arms re-run).

### Exit criteria
- with_skill pass rate >= without_skill on every category, and 0 with-skill API errors.
- Every with_skill failure gets a skill fix (script, recipe or API note) verified via MCP, then re-run.
- Results appended to this file and reviewed by Seldon/Codex before merging.

## Safety
- Background Blender only (`execute_blender_code_for_cli`) on the fixture copy; the user's live session is
  never touched.
- Agents only write `solution.py` under the git-ignored eval workspace; skills are edited only by the main agent.

## Questions for review
- Is reusing iteration-3 with-skill runs for unchanged skills sound, or should all 85 with-skill runs be fresh?
- Is `environment-artist` the right home for `blockout.py`, and is the ARGS surface (pieces/layout/room) too broad?
- Is a single run per arm, with a tie-breaker re-run on disagreement, enough?

## Seldon / Codex review of this plan (evaluation focus)

Verdict **approve**, confidence 0.95, no blocking findings. Non-blocking (low): reusing iteration-3 with-skill runs
for unchanged skills assumes no drift. Mitigation adopted: those runs were regraded on the current fixture/grader
(81/85, unchanged), and a random 5 of the 34 reused evals get a fresh with-skill run as a drift check; any
drift (different verdict) triggers fresh runs for that whole category.
