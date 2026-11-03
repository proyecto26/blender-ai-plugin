# Evidence for the measured sentences added in iteration 12

Scope: lines added to `.md` files under `skills/` and `docs/` between `6493832` and `98d7076` that state a number, "measured",
"tested", "verified" or "checked" (found with `git diff 6493832 98d7076 -- skills docs`; the roadmap file is excluded).
Line numbers are those of the file at `98d7076`; batch E of iteration 13 has since edited some of the files, so the lines may
have moved. "Recipe run" means the block is inventoried in `tests/blender/recipes.json` and executed twice by
`tests/blender/run_recipes.py`, with the recipe's own `assert`s; those asserts bound the reported numbers (they pass or fail)
but the exact printed value is not compared to the sentence by any test. I did not re-run `run_recipes.py` for this list.

| # | Sentence (shortened) | File:line | Backing | Status |
|---|---|---|---|---|
| 1 | Mocap result: 120 to 45 keys, 120 to 4, error 0.141 to 0.016, rotation step 6.26 to 0.025, ramp error 4.06 to 0.043 | `animation/references/mocap-cleanup.md`:152 | Recipe run (asserts on spike, rms ratio, key count, rotation step, ramp error) | backed, numbers unasserted |
| 2 | Key reduction tolerance 0.005 m / 0.01 rad holds | `mocap-cleanup.md` Starting values table | `tests/blender/test_iter13_docs.py` `test_mocap_tolerance`: Bezier 0.0158 m / 0.0641 rad, linear 0.0049 / 0.0047 | was wrong for Bezier; fixed in iteration 13 |
| 3 | reference-image-depth: 1.4 mm point error, 0.5 mm ray gap, 56 mm on the wrong pair, four degenerate cases refused | `blender-mcp-workflow/references/reference-image-depth.md`:150 | Recipe run (its asserts) | backed, numbers unasserted |
| 4 | Flicker verdicts, `inconclusive`, `unmeasured_frames`, `dropout_cells`, dropout limits | `film-production/SKILL.md`:61, 63 | `tests/blender/test_parity_m.py` (flicker, partial dropout, inconclusive cases); the specific limits (neighbour mean near 0.01, dropout under 16 px, `dropout_gap`) were not individually looked for | partly backed |
| 5 | Scatter: names read from Blender 5.2 | `geometry-nodes/references/scatter-systems.md`:6 | Recipe run builds the nodes by those names | backed |
| 6 | Scatter result: 218 / 176 / 140 instances, nearest 0.76 m, lowest x -0.497 | `scatter-systems.md`:292 | Recipe run (asserts: counts above 100, clearance, mask, seeds) | backed, numbers unasserted |
| 7 | Scan-match result: matching model mean 0.15% worst 0.26%; shifted 1.45% / 3.11% | `realistic-style/references/scan-match.md`:141 | Recipe run (asserts good ok, shifted not ok) | backed, numbers unasserted |
| 8 | Corrective driver "not in the tested recipe" | `rigging/references/facial-shape-keys-drivers.md`:34 | statement of absence; the recipe contains no corrective key | backed by reading |
| 9 | Facial result: jaw drops 0.15 at half, 0.30 over-rotated, smile reads 1.0 | `facial-shape-keys-drivers.md`:135 | Recipe run (asserts on drivers, smile value) | backed, numbers unasserted |
| 10 | R4 tested with synthetic PNG maps | `texture-workflow/references/substance-painter-handoff.md`:7 | `tests/blender/test_roadmap.py` R4 | backed |
| 11 | Painter docs returned HTTP 403, so nothing was checked against them | `substance-painter-handoff.md`:15 | a fetch log from the iteration; not reproducible and not a test | **unbacked** (an account of a failed fetch) |
| 12 | Route table (16/8-bit, G at A 0.8 / 0.1 / 0.0) measured by decoding PNG bytes | `unity-export/references/hdrp-material-mapping.md`:48 | the recipe decodes PNG bytes for the shipped routes; the other rows (float `save()`, `alpha_mode` variants, `save_render` depths, premultiplied) were run ad hoc and no test asserts them | shipped routes backed; other rows **unbacked** |
| 13 | Blender writes `sRGB`, `gAMA`, `cHRM` chunks "seen on Windows and macOS" | `hdrp-material-mapping.md`:73 | no test reads the chunks; manual runs: macOS (M2 Max, Blender 5.2.3) in the validation comment on PR #10, and Windows (Blender 5.2.3) before that PR was merged, both listing the chunks of the recipe's 8-bit file and of byte images saved as Non-Color, sRGB and Linear Rec.709 | backed by manual runs, no test |
| 14 | Unity import was not tested; 16-bit import not checked | `hdrp-material-mapping.md`:75 | statements of absence | backed (honest negative) |
| 15 | HDRP result: alpha 0.8 where roughness 0.2, 0.1 where 0.9 | `hdrp-material-mapping.md`:240 | Recipe run (asserts on packed alpha) | backed, numbers unasserted |
| 16 | USD facts: transform + mesh prim pair, `BEST_MATCH` writes a cage, `.001` names, `MAKE_UNIQUE` | `usd-pipeline/SKILL.md`:55 | `test_roadmap.py` R5 covers `.001` round trip and the `BEST_MATCH` lossy case; the pairing and `TESSELLATE` default are exercised by the round trip but no assertion names them | partly backed |
| 17 | "Tested on Blender 5.2 LTS via the official Blender MCP" | `usd-pipeline/SKILL.md`:79 | the tests run headless; no MCP run is recorded | **unbacked** (the "via MCP" part) |
| 18 | Plan lines R11/R12 "with a tested recipe", S3 wording rule, branch/base commit | `docs/plans/iteration-12-parity-and-roadmap.md`:3, 77, 78, 90 | plan text, not a measurement; recipes in rows 1 and 9 | not a measurement |

Unbacked: rows 11, 12 (non-shipped rows), 17 (MCP). Row 13 rests on manual runs only. Rows marked "numbers unasserted" would be backed more strongly
by a test that compares the printed value to the doc.
