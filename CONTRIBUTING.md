# Contributing to the Blender AI Plugin

Thanks for helping! Please open an [issue](https://github.com/proyecto26/blender-ai-plugin/issues) to
discuss larger changes first. General guidelines: [Proyecto 26 contribution guide](https://github.com/proyecto26/.github/blob/master/CONTRIBUTING.md).

## Workflow

```bash
git clone https://github.com/proyecto26/blender-ai-plugin.git
cd blender-ai-plugin
git checkout -b feat/my-skill
# edit skills/...
python3 scripts/validate_skills.py
bash scripts/check-manifests.sh
blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/bst"}'
```

Commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.

## Skill layout (Agent Skills spec)

```
skills/my-skill/
├── SKILL.md          # frontmatter + lean instructions (aim for < 300 lines)
├── references/       # optional deep-dive docs loaded on demand
└── scripts/          # optional bpy scripts (tested in tests/blender)
```

Skills are **self-contained**: no `../` paths. Point to another skill by name, e.g.
``the `blender-mcp-workflow` skill → `references/validation-checklist.md` ``.

### Frontmatter

```yaml
---
name: my-skill                      # = folder name, lowercase a-z0-9-
description: Use when [conditions]. Invoke for [keywords].   # <= 1024 chars
license: MIT
metadata:
  author: https://github.com/<you>
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: keyword1, keyword2
  related-skills: blender-director, materials      # must exist in skills/
---
```

### Recommended sections

`Role Definition` → `When to Use` → `Core Workflow` → `Technical Guidelines` → `Scripts` (if any) →
`Constraints (MUST DO / MUST NOT DO)` → `Reference Guide` → `Knowledge Reference`.

## Script contract

Scripts run inside Blender through the official MCP (`execute_blender_code` + `runpy`) or headless:

```python
"""One-line summary.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/my_script.py", init_globals={"ARGS": {...}})["result"]

ARGS:
    objects (list[str], required) ...
"""
import json, sys
import bpy

def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}

def main(objects):
    ...
    return {"ok": True}          # JSON-safe dict

ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
```

Rules (enforced by `scripts/validate_skills.py`): no `subprocess`, sockets/HTTP, `eval`/`exec`, or file
deletion; non-destructive by default (create/update named objects, never delete user data); Blender 5.1+
APIs only (see `skills/blender-mcp-workflow/references/blender-5-api-notes.md`). Add a case to
`tests/blender/test_skill_scripts.py` for every new script.

## Evals

Behavioral changes to skills should keep `claude plugin eval` green. Pilot with `--runs 1` first; evals
call the model and use tokens.
