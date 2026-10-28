# Claim to verify: pilot scores of the "Blender 5.x bpy code" eval suite

Judge's job: independently verify that each score below is **correct given the actual transcript**, that
each grader measures what it claims, and that Δ (with-plugin minus without-plugin) is not inflated or
deflated by grader artefacts. Report any score you would change, any grader that is a false
positive/negative, and anything that makes the suite a vanity metric.

Evidence in the workspace:

- Case definitions: `evals/<case>/prompt.md`, graders in `evals/<case>/graders/*.md`
  (format: regex `pattern` is a JavaScript regex; `match: not_contains` passes when absent;
  `flags: m` = multiline; `tool_used` with `tool: Skill` is display-only under ablation unless `arm: both`;
  `llm` graders are judged by Sonnet, majority of 3 votes).
- Pilot result JSON: `evals/results/interview-pilot.json` (per-run scores, grader verdicts).
- Full transcripts: `evals/results/interview-pilot-traces/<case>--<with|without>.jsonl` (one JSON message per
  line; the final assistant text is what `last_message` graders read).
- The owner's quality spec: correct for the *current* Blender (5.2) with **no fallbacks for older versions**;
  reuse the plugin's tested scripts; never use removed APIs. See `docs/plans/blender5-only-and-evals.md`.

## Pilot scores (1 run per arm, Sonnet judge)

| Case | With | Without | Author's reading |
|---|---|---|---|
| 01-bloom-5x | 1.00 | 0.60 | baseline used `glare.glare_type =` and `scene.node_tree` |
| 02-gn-input-5x | 0.67 → 1.00 after grader fix | 0.33 | with-arm failure was a prose false positive (`mod["Socket_2"] = 2.5` inside an explanation); graders were then anchored to code lines (`^\s*…`, flag m). Baseline used `mod[ident] =` (fails on 5.2) |
| 03-smooth-5x | 0.50 | 0.50 | both arms shipped a `<= 4.0` fallback with `me.use_auto_smooth = True`; no skill fired |
| 04-emissive-5x | 1.00 | 1.00 | both correct (`Emission Color`) |
| 05-repair-legacy | 1.00 | 0.75 | Sonnet judge 3/3 FAIL on baseline: final script still had legacy calls |
| 06-script-reuse | 0.00 | 0.00 | no skill fired; both hand-wrote a scatter instead of `scatter_points.py` |
| 07-neg-csv | 1.00 | 1.00 | no plugin skill invoked, correct |
| 08-neg-threejs | 1.00 | 1.00 | no plugin skill invoked, answer used `UnrealBloomPass` |

Pilot cost: $2.14 (8 cases × 2 arms × 1 run). Mean Δ reported by the runner: +0.12 (before the 02 fix).

## Questions

1. Are the updated (line-anchored) `not_contains` graders now free of prose false positives but still
   catching real code? Check them against the transcripts.
2. Is 04 non-discriminating (passes in both arms) and therefore worth replacing or hardening?
3. Is 06 fair? It requires the plugin's script, which a baseline cannot know; the owner explicitly wants
   script reuse, but say whether the grading is reasonable.
4. Does any grader reward the plugin for something the owner did not ask for?
