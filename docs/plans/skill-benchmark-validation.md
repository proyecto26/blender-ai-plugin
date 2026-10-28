# Claim to verify: skill-creator benchmark of the 10 core skills (Blender 5.2)

Judge's job: independently check, for EACH of the 20 evals, that the grades below are correct given the
actual `solution.py` and the Blender execution record, and that the comparison with/without the plugin
is fair. Flag wrong grades, weak/non-discriminating checks, and any place the plugin's skill made the
answer worse. Report per-skill verdicts for: blender-director, blender-mcp-workflow, geometry-nodes,
compositing, materials, lighting, rendering, hard-surface, export-pipeline, lowpoly-style.

## Method

- 20 realistic prompts (2 per skill), fixture scene `GEO_Terrain`, `COL_Rocks`, `SM_Crate` (unapplied
  scale, no UVs), `SM_Dirty` (n-gon), camera, sun. Spec: `evals/skill-creator-workspace/evals.json`
  (each eval has an objective Python `check`).
- Each prompt run by a Sonnet subagent twice: with the skill (told to read `skills/<skill>/SKILL.md`) and
  without (forbidden to read the plugin). Blender was NOT connected; agents wrote `solution.py`.
- Grading: every `solution.py` was executed in background Blender 5.2.3 on a fresh copy of the fixture by
  `evals/skill-creator-workspace/grade_in_blender.py` (driver `run_grades.sh`), producing `exec.json`
  (traceback, result, check). `grading.json` has 3 assertions: executes / no removed APIs or version
  fallbacks (patterns from `scripts/validate_skills.py` DEPRECATED + `bpy.app.version`/hasattr guards) /
  objective scene check.
- Layout: `evals/skill-creator-workspace/iteration-1/eval-NN-<skill>--<name>/<with_skill|without_skill>/run-1/`
  with `outputs/solution.py`, `exec.json`, `grading.json`, `timing.json`.

## Results (iteration 1)

| eval | with skill | without skill |
|---|---|---|
| blender-director--director-crate-unity | 3/3 | 3/3 |
| blender-director--director-horror-mood | 3/3 | 3/3 |
| blender-mcp-workflow--mcp-audit-report | 3/3 | 3/3 |
| blender-mcp-workflow--mcp-safe-cleanup | 3/3 | 3/3 |
| geometry-nodes--gn-scatter-rocks | 3/3 | 3/3 |
| geometry-nodes--gn-array-count-input | 3/3 | 1/3 (fails: executes, scene) |
| compositing--comp-bloom | 3/3 | 1/3 (fails: no, scene) |
| compositing--comp-cinematic-grade | 1/3 (fails: executes, scene) | 0/3 (fails: executes, no, scene) |
| materials--mat-worn-metal | 3/3 | 3/3 |
| materials--mat-emissive-coat-sheen | 3/3 | 3/3 |
| lighting--light-studio-3pt | 3/3 | 3/3 |
| lighting--light-golden-hour | 3/3 | 2/3 (fails: no) |
| rendering--render-eevee-final | 3/3 | 2/3 (fails: no) |
| rendering--render-cycles-product | 3/3 | 3/3 |
| hard-surface--hs-bevel-weighted | 3/3 | 3/3 |
| hard-surface--hs-panel-lines | 3/3 | 3/3 |
| export-pipeline--export-fbx-unreal | 3/3 | 3/3 |
| export-pipeline--export-glb-godot | 3/3 | 3/3 |
| lowpoly-style--lowpoly-ps1-look | 3/3 | 2/3 (fails: no) |
| lowpoly-style--lowpoly-reduce-terrain | 3/3 | 3/3 |

Aggregate (`iteration-1/benchmark.md`): pass rate 97% with vs 83% without (+0.13); +2.7 s and +7.1k
tokens per run with the skill.

## Fix and iteration 2

The only with-skill failure (eval-07 cinematic grade) hand-built a vignette and looked for the Mix
node's Factor as `NodeSocketFloat` (it is `NodeSocketFloatFactor` on 5.2) -> StopIteration. Fix:
`skills/compositing/scripts/comp_grade.py` gained `vignette` and `warmth` ARGS (verified on 5.2.3:
edge luminance 0.87 -> 0.77 at vignette 0.6, centre unchanged), documented in
`skills/compositing/SKILL.md`, smoke test added (`tests/blender/test_skill_scripts.py`, 34/34 pass).
Iteration 2 re-ran ONLY eval-07 with the skill: `iteration-2/eval-07-.../with_skill/run-1` -> 3/3, a
5-line runpy call.

## Questions

1. Are any objective checks too weak (e.g. director-horror-mood only checks a new light + world exists;
   hard-surface panel-lines accepts any face-count increase)? Which evals are non-discriminating?
2. Is a 3-assertion rubric enough to call a skill "working as designed", or which skill needs a
   qualitative look (materials, lighting) that this method misses?
3. Is re-running only the failed eval in iteration 2 acceptable evidence for the fix?
