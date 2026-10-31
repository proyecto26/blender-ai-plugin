# Blender AI Plugin — contributor guide for coding agents

This repository *is* a plugin (Agent Plugins 1.0 + Claude Code + Codex manifests). When you work **on** it:

## Layout

```
plugin.json                      # Agent Plugins 1.0 manifest (portable)
.claude-plugin/                  # Claude Code plugin + marketplace manifests
.codex-plugin/plugin.json        # OpenAI Codex manifest
.agents/plugins/marketplace.json # Codex / Copilot catalog entry
agents/blender-design-orchestrator.md
skills/<skill>/SKILL.md          # self-contained skills (+ references/, scripts/)
skills/blender-mcp-workflow/     # foundation: MCP rules, shared references, core scripts
tests/blender/                   # live Blender smoke tests for every script
evals/                           # `claude plugin eval` suite
scripts/                         # repo tooling (validators, manifest gate)
docs/                            # setup guide, skills guide, demo video
```

## Rules

1. **Skills are self-contained.** Never reference files outside a skill folder with `../`. Point to
   another skill by name: ``the `blender-mcp-workflow` skill → `references/x.md` ``.
2. **Scripts follow one contract:** module docstring with `ARGS:`, a `main(**kwargs)` that returns a
   JSON-safe dict, `ARGS = globals().get("ARGS") or _cli_args()`, `result = main(**ARGS)`.
   No `subprocess`, sockets, `eval`/`exec`, or file deletion. Non-destructive by default.
3. **Target Blender 5.2+ only (no fallbacks for older versions).** Check `skills/blender-mcp-workflow/references/blender-5-api-notes.md` and the
   MCP `get_python_api_docs` tool; never use pre-4.2 APIs.
4. **Keep manifests in sync** (name, version, description) across `plugin.json`, `.claude-plugin/*`,
   `.codex-plugin/plugin.json`.

## Checks before committing

```bash
python3 scripts/validate_skills.py                 # frontmatter, links, deprecated APIs, script safety
bash scripts/check-manifests.sh                    # manifest consistency + claude plugin validate + schema
blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/bst"}'
blender -b --factory-startup --python tests/blender/run_recipes.py -- '{"out_dir": "/tmp/bst_recipes"}'   # recipe runner
claude plugin eval --runs 1                        # pilot the eval suite (uses tokens)
```

With the official Blender MCP connected, the smoke tests can also run headless via
`execute_blender_code_for_cli` on a scratch `.blend` (not on Microsoft Store installs). Automated tests never run
against the user's open file. The one exception is an attended live acceptance: the user has agreed, is watching, and
the open file is disposable. See `docs/local_skill_development.md`.
