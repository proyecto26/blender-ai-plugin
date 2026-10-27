# Local Skill Development

## Load the plugin from your clone

```bash
git clone https://github.com/proyecto26/blender-ai-plugin.git
cd blender-ai-plugin

# Claude Code: run with the plugin loaded from this folder (no install needed)
claude --plugin-dir .

# or add the local folder as a marketplace and install it
claude plugin marketplace add ./
claude plugin install blender-ai-plugin@blender-ai-plugin
```

Codex / Copilot CLI read `.agents/plugins/marketplace.json` + `.codex-plugin/plugin.json`; other Agent
Plugins clients read the root `plugin.json`.

## Create a skill

```bash
mkdir -p skills/my-skill/references skills/my-skill/scripts
$EDITOR skills/my-skill/SKILL.md
```

Follow the frontmatter and script contract in [CONTRIBUTING.md](../CONTRIBUTING.md), then add the skill to
the routing table in `skills/blender-director/SKILL.md` and to [SKILLS_GUIDE.md](SKILLS_GUIDE.md).

## Test against real Blender

1. Install the official Blender MCP ([BLENDER_MCP_SETUP.md](BLENDER_MCP_SETUP.md)).
2. Write a scratch file once (never test against work you care about):
   ```python
   # via execute_blender_code
   import bpy
   bpy.data.libraries.write("/tmp/empty.blend", set())
   result = {"ok": True}
   ```
3. Run the smoke tests headless through MCP:
   `execute_blender_code_for_cli(blend_file="/tmp/empty.blend", code='import runpy; result = runpy.run_path("<repo>/tests/blender/test_skill_scripts.py", init_globals={"ARGS": {"only": ["my-skill"]}})["result"]')`
   or from a terminal:
   `blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"only": ["my-skill"]}'`
4. Look at the result: `capture_views.py` renders PNGs you can open, and in the live session
   `get_screenshot_of_area_as_image("VIEW_3D")` shows the viewport.

## Checklist

- [ ] `python3 scripts/validate_skills.py` → 0 errors
- [ ] `bash scripts/check-manifests.sh` → all OK
- [ ] Blender smoke tests pass on 5.1+
- [ ] Skill triggers on the prompts you expect (`claude plugin eval --runs 1`)
