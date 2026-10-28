# Claim to verify: full run of the "Blender 5.x bpy code" plugin eval (3 runs per arm)

Judge's job: verify each score against the transcripts, find grader false positives/negatives, and say
whether the reported delta is real. Pay special attention to the with-plugin regressions in 01 and 04.

Evidence: `evals/results/full-v2.json` (all grader verdicts), transcripts
`evals/results/full-v2-traces/<case>--<arm>--runN.jsonl`, cases and graders in `evals/<case>/`.
Earlier pilot validation: `docs/plans/eval-score-validation.md`. Owner spec: Blender 5.2 only, no
fallbacks, reuse plugin scripts.

Changes since the pilot: trigger descriptions for blender-mcp-workflow, blender-modeler,
geometry-nodes, set-dressing; a "no pre-5.2 code or fallbacks" MUST NOT rule in 27 skills; a
"hand the user the runpy call, don't inline the script" rule in 26 skills; case 04 hardened (coat +
sheen + no-fallback graders).

Cost $6.31. Judge model Sonnet.

| case | with (3 runs) | without (3 runs) | failed graders |
|---|---|---|---|
| 01-bloom-5x | [0.6, 1, 0.8] | [0.8, 1, 0.8] | {'with': ['uses-compositor-group', 'uses-glare-node', 'uses-glare-node'], 'without': ['no-glare-type-attr', 'no-scene-node-tree']} |
| 02-gn-input-5x | [1, 1, 1] | [0.33, 0.33, 0.33] | {'without': ['no-item-assignment', 'uses-properties-inputs', 'no-item-assignment', 'uses-properties-inputs', 'no-item-assignment', 'uses-properties-inputs']} |
| 03-smooth-5x | [1, 1, 1] | [0.5, 0.5, 0.5] | {'without': ['no-removed-auto-smooth', 'no-removed-auto-smooth', 'no-removed-auto-smooth']} |
| 04-emissive-5x | [1, 0.6, 0.6] | [1, 0.8, 1] | {'with': ['uses-coat-weight', 'uses-emission-color', 'uses-coat-weight', 'uses-emission-color'], 'without': ['no-version-fallback']} |
| 05-repair-legacy | [1, 1, 1] | [0.75, 0.75, 0.75] | {'without': ['fixed-script-clean', 'fixed-script-clean', 'fixed-script-clean']} |
| 06-script-reuse | [1, 1, 1] | [0, 0, 0] | {'without': ['names-plugin-script', 'reuses-script', 'names-plugin-script', 'reuses-script', 'names-plugin-script', 'reuses-script']} |
| 07-neg-csv | [1, 1, 1] | [1, 1, 1] | {} |
| 08-neg-threejs | [1, 1, 1] | [1, 1, 1] | {} |

## Questions

1. Why did with-plugin runs fail 01 (bloom) and 04 (emissive)? Plugin problem or grader artefact?
2. Are 02/03/05/06 deltas real (code-level evidence in the transcripts)?
3. Anything in the suite that rewards the plugin for something the owner did not ask for?

## Author's finding and grader change (verify this)

The with-plugin failures in 01 and 04 are answers that call the plugin's tested scripts
(`comp_grade.py` with `preset: stylized_bloom`; `pbr_material.py` with `emission_*`/`coat_weight` ARGS)
instead of spelling out `CompositorNodeGlare` / `"Emission Color"` / `"Coat Weight"`. The owner asked
for script reuse, so those regex graders were changed to accept either the literal 5.2 API or a call to
the script that does it (`evals/01-bloom-5x/graders/uses-*.md`, `evals/04-emissive-5x/graders/uses-*.md`).
The scripts are covered by `tests/blender/test_skill_scripts.py` (34/34 on Blender 5.2.3).

No re-run (budget). The saved transcripts were re-scored locally with the updated regex graders
(llm/tool verdicts unchanged): `evals/results/full-v2-rescored.json` -> mean 1.00 with vs 0.67 without
(Δ +0.33); baseline scores are identical to the recorded ones, which checks the re-scorer.
Question 4: is accepting "calls the tested script" a fair pass, or does it hide wrong ARGS?
