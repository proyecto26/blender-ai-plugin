# Plan: Blender 5.x-only skills + "5.x bpy code" eval suite

Status: **approved with changes** by Seldon (Codex judge, `--focus evaluation`, 2026-10-27); implemented.
Owner: Proyecto 26.

## Decisions after review

- **Minimum version is Blender 5.2** (Codex blocker: removing fallbacks while claiming 5.1 would break 5.1).
  README, AGENTS, CONTRIBUTING, setup guide, tests and the foundation skill now say 5.2+; the MCP server
  itself still runs on 5.1, which the setup guide notes.
- `use_nodes` guards stay: verified on 5.2.3 that `Material/World.use_nodes` is not deprecated, and the guard
  handles old materials with nodes disabled (data state, not a version fallback).
- `turntable.py`: `Action.fcurves` does not exist on 5.2.3 (verified), so only the layered path remains.
- The validator now errors on `bpy.app.version` branches and on removed APIs inside scripts or fenced code.
- Eval suite: 8 cases approved by the owner (Gate 1), including 2 should-NOT-fire cases.

## Goal

Make every skill target the **current Blender (5.1+; tested on 5.2.3 LTS)** only, so agents produce code
that runs today, reuse the plugin's tested scripts instead of improvising, and verify results through the
official Blender Lab MCP. Then measure that with a `claude plugin eval` suite focused on one flow:
**"write/repair bpy code for Blender 5.x"**.

## Author's quality spec (from the plugin owner)

- **Bad**: uses APIs removed in 4.2/5.x; hallucinated operators/properties; guesses instead of verifying.
- **Good**: reuses the plugin's tested scripts when they fit; code is correct for the *current* Blender
  version with **no fallbacks for older versions**; verifies with the Blender MCP ("don't trust, always
  verify"): `search_api_docs` / `get_python_api_docs` before using an unfamiliar API, run, then
  `get_objects_summary` / screenshot to confirm.
- Destructive operations are acceptable for clearly unused data (orphans, empty collections, the plugin's
  own temporary objects); not for the user's authored content without confirmation.

## Part A: remove deprecated material and version fallbacks

1. Scripts: drop version branches that exist only for pre-5.x Blender:
   - `geometry-nodes/scripts/scatter_points.py` and `lowpoly-style/scripts/ps1_look.py` `_set_input`:
     keep only `mod.properties.inputs.<identifier>.value` (5.2+); remove the `mod[identifier]` fallback.
     *Open point:* 5.1 lacks `modifier.properties` — decide whether minimum version becomes 5.2.
   - `turntable.py`: keep only the slotted-actions/layered path (`action.layers` → channelbags) if that is
     the only 5.x path; remove the legacy `action.fcurves` branch.
   - `use_nodes` guards on materials/world (`hasattr(mat, "use_nodes")`) — remove if 5.x always has nodes.
2. Skill text: remove "older versions" / 4.x fallback snippets (e.g. the `else: mod[ident] = v` branch in
   `geometry-nodes/SKILL.md`). Keep the *removed-API table* in `blender-mcp-workflow/references/
   blender-5-api-notes.md` (it is a "do not use" list, which helps the model avoid stale training data),
   but no runnable legacy code anywhere.
3. Validator: add a rule to `scripts/validate_skills.py` that fails on `bpy.app.version` branches and on the
   removed-API list appearing inside fenced code blocks (prose mentions in the API-notes table stay allowed).
4. Verify every change on Blender 5.2.3 via the MCP (`execute_blender_code_for_cli` on a scratch file) and
   keep `tests/blender/test_skill_scripts.py` at 100%.

## Part B: "verify, don't guess" workflow in the skills

- `blender-mcp-workflow/SKILL.md` gains an explicit **API verification loop**: unknown/changed API →
  `search_api_docs` / `get_python_api_docs` → minimal probe in background Blender → real change → confirm
  with `get_objects_summary` / `get_screenshot_of_area_as_image`.
- Prefer scripts: each script's ARGS docstring is the contract; skills say "run X.py with …" first and only
  hand-write bpy when no script fits.

## Part C: eval suite (one flow: Blender 5.x bpy code)

Each case runs with and without the plugin (`--ablation with-without`), `runs: 3`, judge `--judge-model sonnet`.

| Case | Prompt shape | Graders |
|------|--------------|---------|
| bloom-5x | "add bloom/glow to my EEVEE render (5.2)" | regex no `.use_bloom =`; regex `CompositorNodeGlare` + `compositing_node_group`; llm: runnable on 5.2, no legacy fallback |
| gn-input-5x | "set GN modifier input 'Density' from Python (5.2)" | regex `properties.inputs`; regex not_contains `mod\[` assignment; llm |
| smooth-5x | "auto smooth 30° on selected meshes" | regex no `.use_auto_smooth =`; regex `shade_auto_smooth`/`smooth_by_angle` |
| principled-5x | "glowing emissive metal material via Python" | regex `Emission Color`, no `inputs["Emission"]`; regex `Specular IOR Level` if specular set |
| repair-legacy | user pastes a 3.x/4.0 script (use_bloom, scene.node_tree, ShaderNodeSeparateRGB) → "make it work in 5.2" | regex none of the legacy tokens in code; llm: every legacy call replaced |
| script-reuse | "scatter rocks on my terrain with random scale" | llm: points to/uses `scatter_points.py` (ARGS) instead of a from-scratch node tree |
| should-NOT-fire | "how do I bake bread at home?" / generic Python question | tool_used Skill min 0 max 0 arm both |

Side channels recorded: cost per run, turns, latency. Pilot `--runs 1 --no-publish` (~$3 observed for 6
cases × 2 arms), full suite ≈ pilot × 3.

## Risks / questions for the judge

- Is "no fallbacks" safe when the official MCP itself only requires 5.1, while `modifier.properties` is 5.2+?
- Are the regex graders robust to prose mentions (an answer *explaining* that `use_bloom` is gone)?
- What other good-output criteria would make the skills easier for users of the Blender MCP?
