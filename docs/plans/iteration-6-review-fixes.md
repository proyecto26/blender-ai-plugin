# Iteration 6 — fix the verified review findings

Source: the skill review of 2026-10-29 (every finding below was re-checked by an independent
verifier before it was reported). Target: Blender 5.2 LTS only. All edits land on a branch
`iteration-6-review-fixes`; nothing is committed or pushed without the owner's go-ahead.

## Findings to fix

| # | Finding | Evidence |
|---|---|---|
| F1 | `blender-mcp-workflow` and `geometry-nodes` descriptions contain an unquoted `: `, so strict YAML fails and the description is dropped at load time. `scripts/validate_skills.py` uses its own lenient parser and does not catch it. | `skills/blender-mcp-workflow/SKILL.md:3`, `skills/geometry-nodes/SKILL.md:3`; `claude plugin validate .` fails |
| F2 | GLB/glTF exports include selected objects from other scenes: `use_selection=True` without `use_active_scene=True`. Tests only check byte size. | `skills/export-pipeline/scripts/export_asset.py:76`, `skills/godot-export/scripts/export_godot.py:50`, `tests/blender/test_skill_scripts.py:131,141` |
| F3 | `make_collision.py` is not idempotent: each run adds `UCX_X_02`, `X_02-colonly`, `X_COL_02`. | `skills/collision-proxy/scripts/make_collision.py:86-89` |
| F4 | genre-shooter places `CAM_FPS` at the target's centre height (elevation 0) at a framing distance shorter than the 4 m cover ring it builds, so the camera sits inside/behind `COVER_*` boxes; at least half the frame is blocked. The recipe's own table says FPS eye height is 1.6 m. `camera_rig.py` has no occlusion check. | `skills/genre-shooter/SKILL.md:27,33,39,45`; `skills/camera-cinematography/scripts/camera_rig.py:48-110` |
| F5 | `scatter_props.py` does not enforce `max_dist`: cluster centres are drawn up to `max(keep_out+0.9, max_dist)` and the spread grows with attempts, so props land beyond it (2.0 m requested → 4.82 m observed). | `skills/set-dressing/scripts/scatter_props.py:114-130` |
| F6 | `fix_asset.py` has no `main()` (module-level code), breaking the script contract in `AGENTS.md` rule 2; `validate_skills.py` reports it as the only error. | `skills/blender-mcp-workflow/scripts/fix_asset.py:101` |
| F7 | Dead `hasattr(x, "use_nodes")` guards emit 6.0-removal deprecation warnings and contradict "no fallbacks". | `light_rig.py:115`, `pbr_material.py:48`, `toon_material.py:50,68`, `bake_maps.py:43` |
| F8 | Six scripts have no committed smoke test: `fix_asset`, `blockout`, `gn_curve_profile`, `scatter_props`, `smoke_domain`, `sprite_billboard`. The recipe runner/fixture used by earlier iterations was in a git-ignored folder and is gone, so recipe verification is not reproducible. | `tests/blender/test_skill_scripts.py` (35 cases / 29 scripts) |
| F9 | Descriptions: 90/94 shared skills keep the upstream description verbatim; 27/31 skills that ship scripts never mention them; almost none carry a "Use when …" trigger. | `skills/*/SKILL.md` frontmatter vs `../examples/blender-skills` |
| F10 | One-line `ARGS:` summaries omit `posterize` (compositing) and `lightmap` (uv-workflow), though the script tables document them. | `skills/compositing/SKILL.md:121` vs `:114`; `skills/uv-workflow/SKILL.md:160` vs `:153` |
| D1 | README, SKILLS_GUIDE, manifests, AGENTS.md and the video timeline hard-code "95 skills / 29 scripts"; the owner wants no fixed counts. | `README.md:11`, `docs/SKILLS_GUIDE.md:3`, `plugin.json:5`, `.claude-plugin/plugin.json:4`, `.claude-plugin/marketplace.json:12`, `.codex-plugin/plugin.json:4,37`, `AGENTS.md:14`, `docs/video/timeline.json:108` |

## Fix design

- **F1** Quote both descriptions (double-quoted YAML scalar) and add a strict check to
  `validate_skills.py`: an unquoted frontmatter scalar containing `": "` or starting with a YAML
  indicator is an error (stdlib only — the validator has no dependencies). PyYAML, when importable,
  additionally parses the block strictly.
- **F2** Add `use_active_scene=True` to both glTF calls. Tests parse the GLB JSON chunk and assert
  the node names equal the exported set; the fixture adds a second scene with a selected object so
  a regression fails.
- **F3** Proxies get a custom property `collision_proxy = {source, engine}`. Before building, the
  script removes only proxies it created for that source + engine (tag match, never by name
  alone), then builds `_01`. New arg `replace=True` (default); `replace=False` keeps the old
  append behaviour for deliberate multi-hull sets. Non-destructive to user objects.
- **F4** `camera_rig.py` gains `eye_height` (float|None: absolute camera Z, keeps the horizontal
  bearing), `min_distance` (float|None) and always returns `occluded_by`: names of objects hit by
  `scene.ray_cast` from the camera to the target's bbox centre and corners-at-mid-height (target
  and its children excluded). genre-shooter passes `eye_height: 1.6`, `min_distance` outside the
  cover ring (radius + piece depth + 1 m) and the recipe asserts `occluded_by == []`. Other camera
  recipes are unchanged but get the field for free.
- **F5** Validate up front (`max_dist` must exceed `keep_out + largest prop radius`, else
  `ValueError` naming the minimum); clamp cluster centres to `max_dist - spread_cap`; cap spread;
  reject any candidate whose centre-to-target distance + prop radius > `max_dist`. The existing
  `RuntimeError` then fires for genuinely impossible counts on any ground.
- **F6** Wrap the body in `main(objects=None, apply_scale=True, …)` returning the same dict; keep
  documented ARGS identical; add `_cli_args`.
- **F7** Remove the guards (5.2 node trees always exist on new materials/worlds); verify no
  deprecation warning is printed during the smoke run.
- **F8** Add smoke cases for the six scripts (incl. re-run idempotency for blockout, scatter_props,
  make_collision, smoke_domain, gn_curve_profile). Commit `tests/blender/run_recipes.py`: runs every
  complete ```python block in `skills/**/*.md` twice on a deterministic fixture, skips `{...}`
  templates and documented fragments, and asserts: no exception, JSON-safe `result`, zero object
  delta on the second run, and — when the block sets a camera — the active camera is not occluded
  from the scene's main subject. Output: one JSON report; non-zero exit on failure.
- **F9** For every skill that ships scripts: rewrite the description to "<what it does>. Use when
  <triggers>. Ships tested scripts: <names>." (≤1024 chars, quoted). Other skills: add a
  "Use when …" clause to the existing text. No count claims.
- **F10** Add the two missing ARGS keys.
- **D1** Replace counts with count-free wording in README, SKILLS_GUIDE, all four manifests (kept
  identical — rule 4), AGENTS.md, CONTRIBUTING and the timeline text. Historical CHANGELOG entries
  and old `docs/plans/*` are history and stay; add a new CHANGELOG entry. The rendered
  `docs/blender-ai-plugin.mp4` is not re-rendered (title card text changes only in the source).
  There is no `site/` in this repo; nothing to change there.

## Workflow improvements (from the example plugins)

Survey of `../examples/*` (cc-blender-skill, dsh-blender-plugin, 3dviz-pro-max, blender-skills).
Already present here: routing table, parallel/sequential rules
(`skills/blender-director/references/skill-routing.md:64-78`, not linked from SKILL.md or the
agent), naming prefixes, idempotent scripts, PASS/WARN/FAIL `validate_asset.py`. Adopted:

- **W1 Blocking stage gates.** The director pipeline becomes explicit stages — inspect → brief →
  blockout/model → look-dev → light & camera → validate → export → post-export verify — each with a
  gate (script result + capture). A failed gate blocks later stages (cc-blender-skill
  fit-repair-optimizer:36-45). Verdicts are tri-state PASS / FAIL / NOT_CHECKED; NOT_CHECKED never
  counts as a pass (dsh 验收清单). Link `skill-routing.md` from SKILL.md and the agent.
- **W2 Edit transactions.** Before a destructive step (boolean, join, apply transforms, remesh,
  decimate): duplicate or work in a `__Work` scene, run, check, then accept or revert; one pending
  edit at a time (dsh runtime/txn.py:6-41, prose only — no file snapshots, no deletion of user data).
- **W3 Run manifest.** New tested script `skills/blender-director/scripts/run_manifest.py` appends
  stage events (stage, skill, script, ARGS, result summary, verdict, capture path) to
  `<out_dir>/run_manifest.json` and records sha256 of exported files; schema in
  `skills/blender-director/references/run-manifest.schema.json` (cc-blender-skill harmonizer:57-67,
  3dviz capture-log). Writes only inside `out_dir`; never deletes.
- **W4 Repeat-failure stop + post-export verify.** Same gate failing twice → stop, classify
  (geometry / materials / lighting / camera / export / tool error) and report instead of a third
  blind retry. `export_asset.py` / `export_godot.py` return `verify` (GLB: node names read back
  from the file vs the requested objects) — ties to F2.
- **W5 Triggers.** Director/agent descriptions gain symptom phrases ("looks wrong", "doesn't match
  the reference", "make it game-ready"). Add `evals/triggers.json` (should/shouldn't-trigger
  queries for the foundation, director and the script-shipping skills) as a static fixture.
- Not adopted: the upstream director's `../references/` links (violate rule 1) and
  `get_viewport_screenshot` (third-party MCP tool name).

Files: `skills/blender-director/**`, `agents/blender-design-orchestrator.md`, body of
`skills/blender-mcp-workflow/SKILL.md` (+ its `references/mcp-integration.md`), `evals/triggers.json`.

## Execution

Edit work runs as separate sonnet agents, each in its own git worktree, with disjoint file sets:

1. **scripts** — F2, F3, F4 (script), F5, F6, F7 + the matching ARGS docs in each script's SKILL.md.
2. **tests** — F8 + F2 assertions + F1 validator check (`tests/`, `scripts/validate_skills.py`).
3. **skill text** — F1 quoting, F4 recipe, F9, F10 (frontmatter + genre-shooter recipe).
4. **workflow** — W1–W5 (the `verify` return in W4 belongs to agent 1).
5. **docs** — D1 + CHANGELOG.

Integration (main session): review each diff, apply to the branch, then run
`validate_skills.py`, `check-manifests.sh`, the smoke suite and `run_recipes.py` in background
Blender 5.2 (spawned from the live MCP session as before; never against the open file). An
independent verifier agent re-checks every finding F1–F10/D1 against the merged tree. A worktree
whose diff fails is discarded and redone; the fix loop stops after two rounds without progress.

## Success criteria

- `validate_skills.py`: 0 errors; strict YAML parses every SKILL.md; `claude plugin validate .` passes.
- Smoke suite: all old + new cases pass in background Blender 5.2; no `use_nodes` deprecation warning.
- `run_recipes.py`: every complete recipe passes twice with zero object delta; genre-shooter
  camera not occluded.
- GLB tests prove other-scene objects are excluded.
- `grep -rE "[0-9]+ (tested )?(bpy )?(skills|scripts)"` finds nothing outside CHANGELOG history and old plans.

## Risks

- F9 touches ~94 frontmatters: risk of description regressions. Mitigation: validator length/strict
  YAML checks + reviewer diff read; no change to `name`.
- F3 `replace=True` changes default behaviour: callers relying on accumulating hulls must pass
  `replace=False` (none in the repo today; grep confirms).
- Running Blender only via subprocess from the live MCP session (BLENDER_PATH unset for the CLI tool).

## Revision 1 — after the Seldon review (Codex, verdict request_major_revision)

Codex confirmed F2, F3, F6, F7, F10, D1 and partially confirmed F1, F4, F5, F8, F9 (static only; it
could not run Blender). Corrections: F9 is **28/31** script-shipping skills without a script
mention; `AGENTS.md:13` (not :14); the routing link already exists at `blender-director/SKILL.md:310`
(make it prominent instead of "adding" it). Runtime evidence for F1/F2/F4/F5 is from the earlier
background-Blender runs (scratchpad `run_block_occ.py`, `probe2.py`, `probe4.py`) and is re-proven by
the new tests below. Each blocking item is resolved as follows.

- **B1 F4 occlusion contract.** `camera_rig.py` adds `_occluders(cam, target)`: for sample points
  (bbox centre + 4 side-midpoints at mid-height + top centre) cast `scene.ray_cast(depsgraph,
  origin, dir, distance=segment_len)`; when the hit object is ignorable (the target, its children,
  `hide_render`, `display_type in {WIRE, BOUNDS}`, or tagged `collision_proxy`) re-cast from just past
  the hit (bounded to 16 steps). Result adds `occluded_by` (sorted names) and `visible_fraction`
  (unblocked samples / samples). With `target=None` the subject is the visible-mesh set. New args:
  `eye_height` (absolute Z, keeps bearing), `max_distance`/`min_distance` (clamp). genre-shooter:
  `eye_height: 1.6`, `max_distance: 3.0` (camera stays inside the 4 m ring, cover is behind it and
  below eye height), and the recipe raises if `occluded_by` is non-empty. Fixture for the test: the
  run_recipes fixture (`SM_Asset` 1.2×0.8×1.5 grounded, 16:9).
- **B2 W2 isolation.** "Checkpoint" = `obj.copy()` **and** `obj.data.copy()` (and `material.copy()`
  when the step edits materials) linked into a `__Checkpoint` collection excluded from the view
  layer. Revert = restore the copied data onto the original object; accept = remove the checkpoint
  object and its copied datablocks (only datablocks the checkpoint created). Shared mesh data is
  made single-user before editing. Documented in `blender-mcp-workflow/references/mcp-integration.md`;
  one pending checkpoint at a time.
- **B3 Blender launch for tests.** The `subprocess` ban in AGENTS.md rule 2 governs shipped skill
  scripts; the test harness is maintainer tooling run at the owner's explicit request ("verify with
  tests in my local Blender"). The live MCP session is used only as a launcher for
  `blender -b --factory-startup` on scratch files, never touching the open file. Add to
  `docs/BLENDER_MCP_SETUP.md`: set `BLENDER_PATH` so `execute_blender_code_for_cli` works without
  that workaround.
- **B4 F5 semantics.** `max_dist` is redefined (docstring + SKILL.md) as "max distance of any prop
  centre from the target centre". No up-front keep_out inequality. Cluster centres are clamped to
  `max_dist - 0.3`, spread is capped at `min(1.2, 0.6 + 0.15*attempts/count)`, and any candidate
  with centre distance > `max_dist` is rejected; the existing `RuntimeError` reports genuinely
  infeasible counts. Result adds `max_dist`.
- **B5 F6 signature.** `main(objects, apply="scale", uv="box", uv_scale=1.0)` — identical
  documented ARGS; helpers take `apply`/`uv_scale` as parameters (no module globals); existing
  `_cli_args` kept.
- **B6 export verify predicate.** `verify` is a leak check, not equality: for GLB/glTF read the
  JSON chunk (GLB) or file (.gltf) and report `nodes`, `missing` (requested mesh objects absent) and
  `leaked` (node names equal to scene objects outside the export set and its descendants). `ok` =
  no missing and no leaked. Other formats: `{"checked": false}` (NOT_CHECKED, never a pass).
  Tests: a second scene with a selected object; plus the skinned fixture must pass (joints are not
  objects).
- **B7 recipe runner contract.** `tests/blender/recipes.json` is an explicit inventory: each entry
  = `{file, block, fixture_extras, invariants}`; everything not listed is reported "skipped" with
  a reason (template/fragment). Fixture rebuilt per file. Invariants on run 2 vs run 1: equal
  counts of objects, meshes, materials, node_groups, collections and total modifiers; no exception;
  JSON-safe `result` when assigned; camera recipes: `occluded_by == []` for the active camera.
- **B8 sequencing (no overlapping edits).**
  - Phase A (parallel worktrees, disjoint): **A1 scripts** (`skills/*/scripts/*.py` only, including
    docstrings), **A2 tests+validator** (`tests/`, `scripts/validate_skills.py`, written against the
    API spec above), **A3 docs** (README, SKILLS_GUIDE, BLENDER_MCP_SETUP, manifests, AGENTS.md,
    CONTRIBUTING, timeline, CHANGELOG).
  - Merge A, run validators + smoke suite + recipe runner.
  - Phase B: **B-workflow** (director body/references/new `run_manifest.py` + its smoke case,
    agent file, foundation body + mcp-integration.md, new evals).
  - Phase C: **C-skill-text** (all SKILL.md frontmatter, ARGS docs for new args, genre-shooter
    recipe, F9, F10), after B so it sees the director's new script.
- **Non-blocking, adopted:** F3 builds the new proxy first, then removes the old tagged ones, then
  renames to `_01` (an unrelated object holding the name → keep Blender's suffix and report it);
  tests cover rerun, `replace=False`, and an unrelated same-name object. W1 stages declare
  applicability (N/A ≠ NOT_CHECKED); WARN passes only with a recorded reason. W3 smoke test covers
  append, hash, schema shape and refusal of paths outside `out_dir`. W5 becomes real eval dirs
  (`evals/09-director-gates`, `evals/10-shooter-camera`) in the existing prompt+graders format
  instead of a static JSON. F1 success = `claude plugin validate .` passes (real YAML parser) plus
  the validator heuristic. Manifests: identity fields and description in sync, host fields stay
  host-specific. Video: source text updated; re-rendering the mp4 is left to the owner.

## Revision 2 — after Seldon pass 2 (resolved: B4, B5, B7, B8)

- **B1'** The occlusion filter ignores only: the target and its children (or the visible-mesh
  subject set when `target=None`), objects with `hide_render=True`, and objects tagged
  `collision_proxy` by `make_collision.py`. Viewport `display_type` is **not** a filter.
- **B2'** Destructive steps (apply transforms/modifiers, join, boolean apply, remesh, decimate)
  run on a **disposable working copy**: copy every participant (object + `data.copy()` + modifiers,
  materials when edited) into `__Work`, operate there, check. Accept = move the untouched
  originals into an excluded `__Checkpoint` collection and give the working copies their names;
  revert = remove the working copies only. Originals are never modified, so transforms, applied
  modifiers and joined-away objects are all recoverable. `__Checkpoint` is cleared only when the
  user asks.
- **B3'** Tests no longer spawn Blender from bpy. They run from the shell through the Microsoft
  Store execution alias `%LOCALAPPDATA%\Microsoft\WindowsApps\blender-launcher.exe -b
  --factory-startup --python <test> -- <json>` (verified: runs 5.2.3 LTS headless). Reports go to
  JSON files in the out dir (the alias does not forward stdout). BLENDER_MCP_SETUP gains a note on
  the alias and on `BLENDER_PATH` for `execute_blender_code_for_cli`.
- **B6'** Allowed export set = requested objects + their descendants + their dependencies
  (armature-modifier objects, parent chain). Nodes listed in any `skins[].joints` are joints and
  never count as leaks. `leaked` = non-joint node whose name equals a Blender object outside the
  allowed set. Test with the existing `SK_Arm` + `ARM_Test` fixture (must pass) and a second
  scene with a selected object (must report it as prevented, i.e. absent).
- **Non-blocking adopted:** A1 also fixes `blockout.py` room rebuilds to reuse/remove the mesh it
  created (mesh count stable on rerun). F5 distance is horizontal (XY) from the target bbox centre
  to the prop origin; tests assert exactly that. Validator/recipe checks after Phase A are interim
  (F1 quoting and the shooter recipe land in Phase C); the full check suite is re-run after C and
  is the only one that counts.

## Revision 3 — after Seldon pass 3 (resolved: B1', B3', B6')

- **B2''** Accept remaps references, not just names: `original.user_remap(working)` (Blender's
  ID remap — moves every user of the original, i.e. children's `parent`, modifier/constraint
  targets, collection links, `scene.camera`, onto the working copy), then link the original into the
  excluded `__Checkpoint` collection and swap names so the accepted object keeps the original name.
  Revert before accept needs no remap (nothing references the working copies). Inside the working
  set, copies are re-parented/re-targeted to each other at copy time. Phase B adds a smoke test:
  `SM_Crate` with a `SOCKET_Crate_Top` child → working-copy edit → accept → the socket's parent is
  the accepted mesh, `export_unreal.py` still exports the socket, and `__Checkpoint` holds the
  untouched original; revert path leaves the scene identical to before.

## Outcome (2026-10-29)

Seldon (Codex) approved Revision 3 on pass 4 (confidence 0.96). Executed as phases A (scripts,
tests/validator, docs) → B (workflow) → C (skill text) → D (fixes from the independent verifier),
each in its own worktree, merged after review and re-test.

Deviations from the plan, all deliberate:
- Occluders also ignore fluid domains (they render as volumes); `run_recipes.py` found smoke
  domains "blocking" three style recipes otherwise.
- `generate_lods.py`: stacked LOD copies get `hide_render` (genre-strategy-sim's LOD1 rendered over
  LOD0 and blocked its camera); exports are unaffected.
- `camera_rig.py` refreshes the view layer before reading bounds (targets moved in the same call
  were framed at their stale position); genre-action-combat passes `max_dist` 5.5 (its `min_dist`
  2.5 left no room inside the default 3.5 once `max_dist` became a hard limit).
- The verifier found and D fixed: `fix_asset` moved children when applying scale; `work_copy`
  accept re-parented checkpoint children and moved outside children; export PASS was accepted
  without a validate PASS; a renamed copy of a proxy was deleted on rerun.
- Eval 05's judge failed a correct answer over a `# was glare_type` comment; the grader now judges
  executable code only (the answer was run in Blender 5.2: no errors, no warnings).

Results: validate_skills 0 errors; check-manifests OK; smoke suite 63/63 and recipe runner 54/54
(0 not inventoried) in headless Blender 5.2.3 LTS; `claude plugin eval` 10 cases with/without
plugin — mean Δ +0.41, new evals 09 (1.0 vs 0.0) and 10 (1.0 vs 0.67); case 05 re-run 3× after the
grader fix: 1.0 vs 0.75.
