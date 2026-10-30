# Iteration 7: skill routing, film and AI-video handoff, reference-driven worlds

Base: `main` + commit `ea25268` (iteration 6). Branch `iteration-6-review-fixes` continues.

## Goals

1. Answer, with measurements, "with this many skills, how do you keep the agent from grabbing the wrong
   one?" and "does the orchestrator route from descriptions alone or list the calls explicitly?"
2. Apply a routing strategy, and prove it with a routing eval that covers every skill.
3. Add three workflows people are asking for, built on Blender MCP and tested scripts:
   a. A multi-shot animated film made in Blender: shot list, preview-and-fix loop, EEVEE final, audio edit.
   b. A handoff to ComfyUI and to the Seam app (`C:\Users\jdnic\dev\ai\comfy\apps\seam`): Blender renders
      the parts that need precision; AI does backgrounds and motion.
   c. A reference-folder-first world: style statistics from `ref/` first, Blender props, Godot world,
      then compare captures against the refs and fix drift.
4. Make the plugin work on macOS and Windows; validate its structure and the orchestrator with plugin-dev.

## Current state (verified in this session)

- 95 skills, one agent (`agents/blender-design-orchestrator.md`), no commands/hooks.
- Routing today:
  - Layer 1: each skill's `description` (double-quoted, "Use when ...", lists shipped scripts).
  - Layer 2: `blender-director` as router. Its SKILL.md has a routing table, and
    `references/skill-routing.md` has tables by engine, phase, style x discipline, and "pack routers".
  - The orchestrator does NOT list skills explicitly. Its body says "Load blender-director for routing,
    then only the specialist skills needed", and stage lines name a few scripts. No `skills:` frontmatter.
- No description has a "Not for X (use Y)" boundary. Description word-overlap (TF-IDF cosine) is highest
  for retro-16bit~retro-8bit (0.54), hand-painted~painterly (0.44), dream-weirdcore~liminal-space (0.42),
  cartoon~vector, pixel-art~retro-8bit, frutiger-aero~neon-retrofuturism, anime~cartoon/manga,
  unity~unreal~godot export, export-pipeline~engine exports, geometry-nodes~procedural-modeling,
  and the horror cluster (horror-style, psx-horror, indie-horror-aesthetics, analog-found-footage, ...).
- Description budget: the 95 descriptions total ~31k characters (mean 328, max 870). Claude Code docs:
  the skill listing gets 1% of the context window; when it overflows, descriptions of the least-invoked
  skills are dropped and only names remain (`skillListingBudgetFraction`, `SLASH_COMMAND_TOOL_CHAR_BUDGET`,
  `skillOverrides` "name-only" adjust this). Each entry is capped at 1,536 chars.
  [Finding R1 is being independently verified: on a 200k-context model most descriptions would be dropped.]
- Subagents support `skills:` frontmatter that preloads full skill content at startup (max 32), and can
  otherwise invoke skills via the Skill tool.
- Windows candidates (being verified): F2 the `runpy.run_path("<abs path>")` recipe breaks on pasted
  backslash paths (`\U` escape); F3 the headless example `-- '{"tri_budget": 3000}'` does not survive
  cmd/PowerShell 5.1 quoting; F4 orchestrator `color: orange` may be outside the documented colour set.
- Seam (read-only survey): FastAPI + MCP + skill. Inputs are uploaded RGB images (role a/b/mid) and
  1-6 s clips; transitions/sequences (2-8 shots) on LTX-2.5 first/last frame at 24 fps, canvas multiples
  of 32 (256-2048); text fields `a_desc`/`b_desc`/`a_ref`/`b_ref`/`prompt_extra`. No depth, mask,
  camera, or audio input. `.glb` only through its browser orbit recorder. Outputs mp4 + receipt JSON.
- Examples (`C:\Users\jdnic\dev\ai\blender\examples`, inspiration only, nothing copied or run):
  cc-blender-skill ships per-skill `should_trigger` evals and "Not for ... (use ...)" clauses; the
  Scenario blender-plugin plans film as shots with first-frame handoff and encodes with Blender's own
  FFmpeg; cc-blender-skill calibrates look against references with HSV/brightness statistics. Several
  examples use exec/network/`curl | bash`; none of that is adopted.

## Part R: routing strategy

Principle: garbage in, garbage out. The model can only route on what it is shown, so make what it is
shown short, distinct and measured.

R0. Baseline measurement first (before any description edit).
  - New eval suite `evals-routing/` (run with `--eval-dir evals-routing --ablation none`), one case per
    skill (95) plus ~15 near-miss/negative cases. Each case: a realistic user prompt that does not name
    the skill or copy its description; `allowed_tools: [Skill, Read]`, `max_turns: 4`, `runs: 1`.
    Grader: `tool_used` Skill with `input_match` for the expected skill (alternation allowed where two
    skills are equally right, e.g. a style plus its pack). Negative cases assert no plugin skill
    (`min: 0, max: 0, arm: both`) or that a confusable sibling did NOT fire.
  - Prompts are written by an agent that sees each skill's body but not its description, then reviewed.
  - Report: top-1 hit rate overall and per cluster, plus a confusion list (expected -> fired).
  - Run on the default model, and on a 200k-context model for the budget question.

R1. Descriptions (Layer 1).
  - Front-load: the first sentence names the job in user words (truncation cuts from the end).
  - Tiers by role: core pipeline/discipline/export skills keep full descriptions (<= 400 chars);
    leaf packs (style, mood, world, genre) get <= 220 chars.
  - Add "Not for X (use Y)" to every pair in the confusable list above and to any pair the R0
    confusion list shows.
  - Validator: `validate_skills.py` warns when a description exceeds its tier cap, when the plugin total
    exceeds a set budget, and when two descriptions exceed a similarity threshold without naming each
    other in a "Not for" clause.

R2. Director catalog (Layer 2, explicit).
  - `blender-director/references/skill-catalog.md`, generated by `scripts/build_catalog.py` from frontmatter:
    name, category (core / discipline / export / style / mood / world / genre), stage, one-line job,
    shipped scripts. Names survive the budget even when descriptions are dropped, so the director maps
    a name to its job from the catalog. The validator fails if the catalog is stale or misses a skill.

R3. Orchestrator (Layer 3, explicit calls).
  - Preload `skills: [blender-director, blender-mcp-workflow]` (verify the namespacing that works).
  - Body: a stage -> skill/script table (explicit for pipeline stages: inspect, validate, export, verify),
    and "pick style/genre/world packs from the director catalog, at most one per category unless the
    brief says otherwise; name the chosen skills in the brief".
  - Fix any frontmatter issue F4 confirms; convert `<example>` blocks to the current prose triggers +
    "When to invoke" body section (plugin-dev agent-development guidance).

R4. Re-run R0; acceptance below. If the 200k run still drops many descriptions, document
  `skillListingBudgetFraction` in README/SETUP and consider consolidating leaf packs (decision for the
  user, not taken in this iteration).

## Part V: film in Blender (new skill `film-production`)

Multi-shot animated film, all in Blender, no subprocess and no network from bpy:
- `shot_list.py`: apply a JSON shot list (id, frame range, camera, lens, beats, description) as timeline
  markers bound to cameras; idempotent; returns the shot table.
- `preview_frames.py`: render chosen frames per shot at low resolution/samples (EEVEE) to `out_dir`, plus a
  contact sheet assembled in bpy (image pixels), returns paths. The agent reads the sheet, fixes, re-renders.
- `assemble_edit.py`: build a VSE edit (scene strips per shot in order, sound strips with volume/fades from
  user-provided audio files), set FFmpeg H.264/AAC output, optionally render the animation. Audio must be
  user-supplied or free-licensed with a credits entry (`audio_credits.json`): the skill never downloads.
- SKILL.md: story-first order (concept -> beats -> shot list -> previs -> fix loop -> final -> edit), the
  preview-inspect-fix loop with a stop rule, continuity rules, and how to hand shots to Part H.

## Part H: AI image/video handoff (new skill `ai-video-handoff`)

- `render_handoff.py`: for each shot, render boundary frames (first/last), an optional short clip
  (1-6 s mp4 via Blender FFmpeg), RGBA beauty with transparent film (alpha = subject mask), optional mist
  depth PNG; canvas snapped to multiples of 32, fps fixed per target; writes `handoff/manifest.json`
  with shot ids, files, size, fps, camera data and `a_desc`/`b_desc` from the shot list.
- References: `references/seam.md` (Seam sequence/transition fields, upload roles, what Seam cannot take),
  `references/comfyui.md` (project/1 `assets/` + `$asset`, which comfy skills take over: comfy, comfy-director),
  and the "Blender base image + AI background + AI motion" recipe.
- The handoff stops at files + manifest; submitting is done by the Seam MCP/skill or the comfy CLI, with
  the user's consent for any paid run.

## Part W: reference-folder-first worlds

- `blender-mcp-workflow/scripts/ref_board.py`: read a folder of reference images (bpy image load, numpy),
  compute palette (k-means), value and saturation histograms, contrast; write `style_bible.json`.
- `blender-mcp-workflow/scripts/compare_to_refs.py`: compare any captures (Blender renders, Godot screenshots)
  against the style bible; return per-metric distance and a drift list ("too saturated", "values too high").
- Docs: `references/reference-folder-workflow.md` (refs first, props in Blender, world in Godot via the
  Godot MCP, walk-through captures compared, fix drift) and a pointer from godot-export and the director.

## Part P: platform and structure

- Fix F2/F3 if verified: forward-slash path guidance (`Path(...).as_posix()` / raw strings) and a portable
  headless invocation (JSON in a file `--args-file`, or documented per-shell quoting).
- plugin-dev: run the plugin-validator and skill-reviewer agents (all skills sampled + every new/changed
  skill), validate-agent.sh, and `claude plugin validate`.
- macOS notes in BLENDER_MCP_SETUP (Blender path `/Applications/Blender.app/Contents/MacOS/Blender`).

## Testing

- Headless Blender 5.2 smoke tests for every new script (added to `tests/blender/test_skill_scripts.py`),
  recipe runner inventory updated for new md blocks.
- skill-creator loop for the two new skills: 2-3 eval prompts each, with-skill vs without-skill runs,
  assertions graded, static review viewer (`generate_review.py --static`).
- `claude plugin eval` main suite re-run; new cases for film, handoff, and refs-first.
- Routing suite R0/R4 numbers reported per cluster.

## Acceptance

- Routing: top-1 hit rate after >= baseline + 10 points or >= 85%, no cluster below 70%, negatives pass.
- All validators 0 errors; smoke suite and recipe runner 100%; new evals pass with a positive delta.
- Every finding reported only after an independent verifier.

## Execution

- Edit agents (sonnet) each in their own worktree: E1 routing suite authoring; E2 film-production;
  E3 ai-video-handoff; E4 ref board + compare; E5 descriptions/catalog/orchestrator/platform fixes
  (after the R0 baseline). Merge after diff review + tests; discard failing worktrees.
- Fix loops stop after two rounds with no progress.

---

## Revision 1 (after Seldon/Codex pass 1: request_major_revision, 0.90)

Verified since v0 (independent verifier, `claude` 2.1.312):
- R1 VERIFIED, sharper: the listing budget was a fixed 30,000 chars on both claude-haiku-5-5 and
  claude-opus-5-5. With only this plugin + built-ins (`--setting-sources project,local`) the debug log says
  `Skill listing over budget: 109 skills, 41615 chars > 30000 budget`; 37 plugin skills (the alphabetical
  tail `lookdev` .. `voxel-style`, no usage history) were shown with NO description.
- F2 VERIFIED (backslash path in a Python literal -> SyntaxError). F3 VERIFIED (cmd and PS 5.1 break the
  JSON arg; `_cli_args` raises a raw traceback). F4 REFUTED (`orange` is a documented colour; plugin-dev's
  validate-agent.sh is itself buggy).

### B1 primary route vs recall
Metrics computed by `tests/routing/score_routing.py` from the eval JSON plus each run's `trace.jsonl`
(`--keep-temp`; the pilot confirmed traces exist per run and the JSON alone has no call order):
- **primary**: the FIRST plugin Skill call equals the expected skill (exactly one expected name per case;
  no alternation). A case may list `also_ok` skills, counted only for recall.
- **recall**: the expected skill fired at any point.
- **forbidden**: named siblings that must not fire (near-miss cases) and "no plugin skill" negatives.
- Confusion list (expected -> first fired) per cluster.
The `tool_used` grader stays as the plugin-eval score but is not the reported routing metric.

### B2 orchestrator path
A separate suite `evals-orchestrator/` (6 cases: prop for Unreal, refs-folder world, relight existing scene,
multi-shot film, Seam handoff, 2D-only negative). Tools: Agent, Skill, Read. Checks:
- the Agent tool was called with `blender-design-orchestrator`;
- the skills the subagent loaded (from trace events if subagent events are recorded; a pilot decides),
  else an `llm` grader on the returned brief's skill list and stage table against an expected set.
Preload naming (`skills: [blender-director]` vs `[blender-ai-plugin:blender-director]`) is tested
empirically before it is committed.

### B3 acceptance without overfitting
- Two prompt sets, each one prompt per skill (95) + 15 near-miss/negative cases: **dev** (used to tune
  descriptions) and **held-out** (written by a different agent, frozen, never read while tuning). Both are
  written from skill bodies; the skill's name and distinctive description phrases are banned in prompts.
- Models pinned: `claude-opus-5-5` (default) on both sets; `claude-haiku-5-5` on held-out as the weaker
  router. CLI version and the debug-log budget line are recorded with each run.
- Acceptance on HELD-OUT: primary(after) >= primary(before) overall; no cluster drops more than 5 points;
  primary(after) >= 80% on opus; all negatives/forbidden pass; no over-budget warning.
- Final held-out pass at `runs: 2` to show variance; dev at `runs: 1`.
- The 95-skill baseline is kept; the 2 new skills are reported separately.

### B4 budget gate and fallback
- Gate: with `--setting-sources project,local` the debug log shows no "Skill listing over budget" line,
  i.e. plugin names + descriptions <= 21,000 chars (leaves ~9k for built-ins). Tier caps: core <= 400,
  discipline/delivery <= 210, style/mood/world/genre <= 130 (incl. "Not for" clauses). Script name lists
  move to the catalog.
- As built: caps shipped at discipline/delivery <= 230 and style/mood/world/genre <= 150. The
  210/130 caps would cut the "Not for (use X)" clause from about 30 skills; the binding gate is the total
  (about 16.5k of 21k).
- Fallback when other plugins push the listing over budget anyway: names always show, so the director's
  description stays strong and its catalog maps every name to its job. Experiment: held-out with
  `SLASH_COMMAND_TOOL_CHAR_BUDGET=8000` (mostly name-only), primary reported with the catalog in place.
  Docs tell users with many plugins to raise `skillListingBudgetFraction`.
- Consolidating leaf packs into fewer skills is the next lever if the gate cannot be met: a product
  decision for the user, with these numbers, not done now.

### B5 Seam adapter contract
`handoff/seam_sequence.json` mirrors Seam's `SequenceIn`, nothing more:
- ordered `shots[]` (2-8), each exactly one still (`image`) OR one clip (`clip`, 1-6 s), as local paths;
  the agent uploads through Seam (MCP, or `POST /api/uploads` with role a/b/mid) and substitutes the
  upload ids itself.
- `transitions[]`: one per adjacent pair `{from, to, preset, seconds (5|10), seed, a_desc, b_desc,
  a_ref?, b_ref?, prompt_extra?}`. Boundary semantics: a transition starts at shot A's LAST frame and ends
  at shot B's FIRST frame; the script renders exactly those frames.
- The manifest records Blender's render size/fps but does not promise Seam's output size, and does not
  claim Seam consumes depth, alpha or camera data (Seam re-encodes stills to RGB, so handoff stills are
  opaque).
The Comfy handoff (`handoff/comfy/`) is separate: project/1 `assets/` layout, consumed through `$asset`.

### B6 masks and depth
- Subject mask: render with only the subject set render-visible (others `hide_render` temporarily,
  restored in `finally`) and transparent film; alpha = subject coverage. Subject set = named objects and
  their children; ground/scenery never count.
- Depth: mist pass written as 16-bit PNG, Non-Color, with `{start, depth, falloff, polarity}` in the
  manifest; documented as normalized, not metric.
- Seam beauty frames are opaque RGB.

### B7 test invariants (headless, deterministic fixtures)
- shot_list: markers bound to the right cameras; rerun idempotent; ranges contiguous.
- preview_frames: files exist at the requested size; contact sheet is cols x rows tiles of the expected
  size and tile k matches frame k (flat-colour-per-frame fixture).
- assemble_edit: strips in shot order with the right durations; a sound strip at the configured
  channel/volume; FFmpeg H.264/AAC set; an 8-frame render produces an mp4 > 0 bytes; render settings
  restored.
- render_handoff: first/last frames are frames `start`/`end` (fixture colour changes per frame); mask
  alpha 1 on the subject pixel, 0 on the ground pixel; mist near < far; scene restored (hide_render, film,
  output) after success AND after a forced failure.
- ref_board / compare_to_refs: synthetic refs with known palettes; identical images -> distance ~0; a
  saturated copy -> "too saturated"; fixed seed, capped samples, alpha-weighted, colour convention stated.

### Non-blocking adopted
- Shared contract first: film-production stores its shot list in the scene (`scene["film_shots"]` JSON +
  markers); ai-video-handoff reads the scene, so neither skill references the other's files.
- Blender 5.2 traps written into the scripts: `sequence_editor.strips` + `strips.new_scene/new_sound`, a
  separate edit scene, `image_settings.media_type = "VIDEO"` before FFmpeg and restored after, sound fades
  via `volume` keyframes.
- Catalog metadata is authoritative frontmatter (`metadata.category`, `metadata.stage`), validated; the
  director's skill table is generated from it.
- Film/handoff use the director's verdict model (PASS/FAIL/NOT_CHECKED/N/A) with their own stage names in
  their SKILL.md; `run_manifest.py` is unchanged (its stage enum is fixed), so those gates are recorded in
  the brief.
- macOS: no Mac hardware here. Mac support is checked statically (paths, quoting, Blender path docs) and
  reported as such; Windows is verified at runtime.

---

## Revision 2 (after Seldon/Codex pass 2: request_major_revision, 0.92)

### N1 routing metric respects the router (replaces B1's "primary")
- **route** (headline): the first plugin skill fired that is NOT a router/foundation skill
  (`blender-director`, `blender-mcp-workflow`) equals `expected`. When `expected` is itself one of those two,
  route = the first plugin skill call. Director-mediated routing is therefore not penalized.
- **strict-first**: the first plugin skill call equals `expected` (reported, not gated).
- **mediated rate**: share of runs whose first call was a router skill (reported).
- recall / forbidden unchanged. Implemented in `tests/routing/score_routing.py` (`ROUTERS`).

### N2 Seam contract = Seam's MCP `create_sequence(shots, segments)` arguments
Read from `src/seam/mcp_server.py:176` and `server.py:129-165`:
- `handoff/seam_sequence.json` = `{"shots": [<local path>, ...], "segments": [{...}, ...]}` exactly as the
  MCP tool takes them: `shots` 2-8 local file paths in order, each a PNG still OR an mp4 clip of 1-6 s;
  `segments` has len(shots)-1 entries `{preset, seconds, seed?, prompt_extra?, a_desc?, b_desc?}`.
- A moving shot is handed off as a CLIP: Seam itself takes the clip's first frame (the transition lands on
  it) and last frame (the next transition leaves from it). A still shot is one PNG used as both ends. So
  the script renders a clip for moving shots and one representative frame for still shots; it does not
  render separate boundary stills for Seam.
- `preset` and `seconds` come from the user/agent after Seam's `list_presets` (each launch preset is
  qualified only at its listed lengths); the script writes what it is given and never invents presets.
- REST users upload with `role=mid` and build `SequenceIn` themselves; the skill doc shows the mapping
  but the manifest targets the MCP tool. Every take renders at the first shot's size: the script renders
  all shots at one size (multiples of 32, 256-2048) and the doc says Seam's output size follows shot 1.
- No claim that Seam consumes depth, alpha or camera data.

### Scoring protocol, frozen before the held-out baseline
- Unit = one run. Runs with an eval error, a missing trace or a turn-cap stop count as route = false.
- Rates pool runs (2 runs x 110 cases on the final held-out pass = 220 units).
- Cluster non-regression is gated only for clusters with n >= 8 cases (discipline 29, style 27, genre 13,
  mood 8, world 8); allowed drop max(5 points, 1 case / n). Smaller clusters (core, delivery, near-miss,
  negative) are reported and covered by the pooled gate.
- `max_turns: 6` on held-out and orchestrator cases (room for director -> catalog -> specialist).
- Held-out is run once BEFORE any description change and once after; prompts frozen at commit time.

### Stress experiment (name-only fallback)
Run with `claude -p --plugin-dir . --setting-sources project,local --debug-file <log>` (not through the eval
child) on a 30-case held-out sample with `SLASH_COMMAND_TOOL_CHAR_BUDGET=8000`; the experiment counts only
if `<log>` contains the over-budget line with the 8000 budget. Route rate reported. If it is below 60%, the
report recommends leaf-pack consolidation to the user (no consolidation in this iteration).

### Orchestrator evidence vs declarations
- Loading evidence: in the trace, the `Agent` call to `blender-design-orchestrator` and the Skill calls whose
  `parent_tool_use_id` is that call (the pilot showed these are recorded). Success = Agent called, its Skill
  calls include each case's `required` list, none of its `forbidden`.
- Plan quality (separate score): an `llm` grader on the returned brief. It never counts as loading evidence.
- Preload: if `skills:` preloads are used, the evidence is the subagent's behaviour (no redundant Skill call
  for a preloaded skill plus correct stage use), noted as indirect.

### Film test strengthened
The 8-frame render is re-loaded in Blender: `bpy.data.movieclips.load` -> frame count and size match the
edit; the audio stream is present (`aud.Sound(path)` length > 0, or the reloaded sound strip's
`frame_duration` > 0). A missing audio stream fails the test.

## Revision 3 (after Seldon/Codex pass 3: approve_with_changes, 0.92)

- Scorer: a forbidden sibling counts as a hit wherever it fires in the run, even after the correct
  specialist (fixed in `score_routing.py`).
- Seam output: every take follows the FIRST shot's aspect ratio; Seam picks the pixel size. Docs and the
  manifest state the render size Blender used and never promise Seam's output size.
- Film test: the reloaded mp4 is decoded per shot (one frame inside each shot range must show that shot's
  fixture colour, which catches wrong camera, trimming and repeats), and the audio must be non-silent at
  the expected offset (read samples via `aud`); if a decode API is unavailable headless, the test reports
  NOT_CHECKED instead of passing.
- Replication: held-out baseline and final both run at `runs: 2` (frontmatter of the frozen set). Prompts are
  body-derived; this measures routing on body vocabulary and realistic phrasing, not on unseen domains —
  stated as a limitation in the report.
