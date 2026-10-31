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
   On a Microsoft Store install use the terminal form through `blender-launcher.exe` and read the JSON report in
   `out_dir`; the `*_for_cli` tool cannot return results there.
4. Look at the result: `capture_views.py` renders PNGs you can open, and in the live session
   `get_screenshot_of_area_as_image("VIEW_3D")` shows the viewport.
5. Check it live when it matters. Background runs cannot prove the viewport, screenshots or how long the window
   freezes. With the user's agreement, on a disposable file they can watch, run the script in the open window and
   compare selection, mode, frame, camera and render settings before and after.

## Testing through the real MCP tools, unattended

A separate Blender can serve the add-on's socket, so tests go through the real tools without touching the open window.
This also works on Microsoft Store installs, since the results do not depend on stdout:

```powershell
blender-launcher.exe --background scratch.blend --online-mode --command blender_mcp --port 9877
```

Run the MCP server with `BLENDER_MCP_PORT=9877`. Tested with a JSON-RPC client, not yet from an agent session. Keep to these rules:

- Check the port is free first. Windows lets a second instance bind it without error, and the older one keeps answering.
- **Reverting and stopping destroy work, so guard each in the same call,** in case the client reached the wrong Blender:
  `assert bpy.app.background and bpy.path.abspath(bpy.data.filepath) == SCRATCH`, comparing to the scratch file's
  absolute path. A free port does not prove where a call went.
- Make the guarded `bpy.ops.wm.revert_mainfile()` the first call: a fresh instance has no window context, and export
  scripts fail on `selected_objects` until then.
- Use one instance per test. Scene changes, render settings and handlers carry over between calls.
- Stop it with a guarded `os._exit(0)` through `execute_blender_code`; `quit_blender` is refused and `sys.exit` does not stop it.
- Screenshots and viewport operators are not available, so a pass proves nothing about them.

## Checklist

- [ ] `python3 scripts/validate_skills.py` → 0 errors
- [ ] `bash scripts/check-manifests.sh` → all OK
- [ ] Blender smoke tests pass on 5.2+
- [ ] Skill triggers on the prompts you expect (`claude plugin eval --runs 1`)
