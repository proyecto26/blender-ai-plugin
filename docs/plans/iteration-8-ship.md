# Iteration 8 ship plan: commit, CHANGELOG, doc link, push to PR #4

Branch `iteration-6-review-fixes`, HEAD 18458e3 (pushed, PR #4). Working tree: 67 modified files plus
`docs/plans/iteration-8-known-issues.md`, `docs/plans/iteration-8-ship.md` and 15 new `evals-routing/deliv-*`
cases. `evals-work/` is git-ignored and holds scratch eval/test output; it is not committed.

## Q1. What goes in, as how many commits

Two commits, so each can be reviewed and reverted on its own:

1. **Delivery routing** - the 7 delivery skill descriptions (unreal-export, unity-export, godot-export,
   lod-pipeline, asset-optimization, collision-proxy, export-pipeline), the regenerated
   `skill-catalog.md`, 15 `evals-routing/deliv-*` cases, the `evals-routing/README.md` bullet, `.gitignore`
   (`evals-work/`). Evidence: deliv subset route 0.667 -> 0.938 (clean-in-both 32/42 -> 44/44, forbidden 0);
   full dev set 0.952 over 125 runs (5 errors, all the 4-turn cap), one extra non-delivery load.
2. **Known issues K1-K5** - fix_asset.py, render_handoff.py, assemble_edit.py, film SKILL.md and
   audio-and-licensing.md, unity-export SKILL.md (the K4 part; its description line belongs to commit 1),
   validate_skills.py, `metadata.requires` in 47 SKILL.md files, README limitation, the three test files,
   the two plan files, CHANGELOG. Evidence: Blender 5.2.3 headless smoke 65/65, film 26/26, handoff 20/20,
   refs 23/23, recipes 54/0; the 4 new cases fail on the pre-fix tree; Codex approved plan and diff.

Files touched by both (e.g. `unity-export/SKILL.md`, and SKILL.md files that got both a new description and
`requires`) are split with `git add -p` only if the hunks separate cleanly; otherwise the file goes in
commit 2 and the commit message says so.

## Q2. CHANGELOG

Under `[Unreleased]`, add an "Iteration 8" block above Iteration 7 with Changed (delivery descriptions:
symptom words, "load even for advice"), Added (`metadata.requires` + validator check, `assemble_edit`
`verify`, handoff leftover warning, `children_not_preserved`), Fixed (K1-K4 wording as in the plan).
No numbers about skill counts.

## Q3. Doc link for `execute_blender_code_for_cli`

Verified gap: `docs/BLENDER_MCP_SETUP.md:91-104` documents that the tool needs `BLENDER_PATH` (and the
Microsoft Store `blender-launcher.exe` case), but the places that recommend the tool do not point there.
Skills cannot link outside their folder (AGENTS.md rule 1), so:
- `skills/blender-mcp-workflow/references/mcp-tools.md:31`: one sentence, self-contained: "Needs `blender`
  on PATH or `BLENDER_PATH` set in the MCP server's environment (on a Microsoft Store install, the
  `blender-launcher.exe` alias); without it the tool fails with 'Blender executable not found'. Fall back to
  the headless command in this skill." No link to `docs/`.
- `README.md:147`: append "(needs `BLENDER_PATH`, see [setup](docs/BLENDER_MCP_SETUP.md))".
- SKILL.md is left alone (keeps the body lean; the reference is where tool details live).

## Q4. Verification before push

`validate_skills.py` (0 errors), `--self-test`, `build_catalog.py --check`, `check-manifests.sh`,
`claude plugin validate .`. No Blender rerun needed for doc-only Q3 edits. Then `git push`, and update the
PR #4 description with an "Iteration 8" section ending with the Claude Code attribution line.

## Out of scope

The e2e test project (`C:\Users\jdnic\dev\ai\blender\e2e-film`) stays outside the repo; its findings
(S010 end framing, fix-loop behaviour) are reported, not committed.

## Revision 1 (Seldon/Codex: approve_with_changes, 2 low findings)
- Commit 2 also carries the Q3 edits: `skills/blender-mcp-workflow/references/mcp-tools.md` and the
  README.md:147 hunk. The only file with hunks for both commits is `skills/unity-export/SKILL.md`
  (description line 3 -> commit 1; K4 lines 18, 35-38, 51 -> commit 2), split with `git add -p`.
- Q3 wording follows `docs/BLENDER_MCP_SETUP.md:102-104`: "Needs the `BLENDER_PATH` environment variable
  (the Blender executable, or on a Microsoft Store install the `blender-launcher.exe` alias) set in the MCP
  server's environment, then a restart of the agent; without it the tool fails with 'Blender executable not
  found'. Fall back to the headless command in this skill."
