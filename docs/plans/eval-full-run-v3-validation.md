# Claim to verify: fresh full run (v3) of the Blender 5.x plugin eval

Fresh `claude plugin eval` run (3 runs per arm, Sonnet judge, $6.34) after the grader fix
described in `docs/plans/eval-full-run-validation.md`. This replaces the earlier local re-score.
Evidence: `evals/results/full-v3.json`, transcripts `evals/results/full-v3-traces/` (written only if the
runner kept them), cases in `evals/<case>/`.

| case | with | without |
|---|---|---|
| 01-bloom-5x | [1, 1, 1] | [0.8, 1, 1] |
| 02-gn-input-5x | [1, 1, 1] | [0.33, 0.33, 0.33] |
| 03-smooth-5x | [1, 1, 1] | [0.5, 0.5, 0.5] |
| 04-emissive-5x | [1, 1, 1] | [1, 1, 1] |
| 05-repair-legacy | [1, 1, 1] | [0.75, 0.75, 0.75] |
| 06-script-reuse | [1, 1, 1] | [0, 0, 0] |
| 07-neg-csv | [1, 1, 1] | [1, 1, 1] |
| 08-neg-threejs | [1, 1, 1] | [1, 1, 1] |

Mean 1.00 with vs 0.69 without (Δ +0.31). Verify the scores against `full-v3.json` grader verdicts and
any transcripts, and say whether any 1.0 is a grader artefact.
