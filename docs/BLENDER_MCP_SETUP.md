# Blender MCP Setup (official Blender Lab server)

This plugin drives Blender through the **official MCP server from Blender Lab**
([blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/)). It is not bundled with the plugin:
you install it once and every agent (Claude Code, Codex, Cursor, Copilot CLI...) connects to it.

> **Security:** the server lets an LLM run arbitrary Python inside Blender with your user permissions,
> without guards. Blender Lab recommends a virtual machine or a system without access to sensitive data.
> Review what your agent runs, keep backups of `.blend` files, and only enable the add-on while you use it.

## Requirements

| Requirement | Version |
|-------------|---------|
| Blender | **5.2 or newer** (the MCP server runs on 5.1+, this plugin's skills and scripts need 5.2) |
| Python | 3.10+ (for the MCP server process) |
| [uv](https://docs.astral.sh/uv/) | recommended, to run the server from source |

## 1. Install the Blender add-on

1. Download `mcp-<version>.zip` from the [Blender Lab MCP page](https://www.blender.org/lab/mcp-server/).
2. Drag the zip into Blender **twice**: the first drop adds the `https://lab.blender.org/` extensions
   repository (enables update notifications), the second installs the add-on.
   Alternatively: **Edit → Preferences → Get Extensions → Install from Disk**.
3. Enable the **MCP** add-on. Keep Blender open while your agent works.

## 2. Install the MCP server

Pick one:

- **MCP Bundle (`.mcpb`)** - for clients that support bundles (e.g. Claude Desktop): download
  `blender-<version>.mcpb` from the release page and open it.
- **From source with pip**:
  ```bash
  pip install "git+https://projects.blender.org/lab/blender_mcp.git#subdirectory=mcp"
  # installs the `blender-mcp` command
  ```
- **From an extracted release with uv** (no global install):
  ```bash
  uv run --directory /path/to/blender_mcp/server blender-mcp
  ```

## 3. Connect your agent

### Claude Code

```bash
# pip install
claude mcp add --scope user blender -- blender-mcp
# or extracted release with uv
claude mcp add --scope user blender -- uv run --directory ~/.blender-mcp/v1.0.3/server blender-mcp
```

Check with `claude mcp list` (should show `blender: ✓ Connected`). Tools appear as `mcp__blender__*`.

### Codex CLI

```bash
codex mcp add blender -- blender-mcp
```

### Cursor / other clients (`mcp.json`)

```json
{
  "mcpServers": {
    "blender": { "command": "blender-mcp" }
  }
}
```

## 4. Smoke test

Ask your agent:

> *"Use the Blender MCP to summarize the objects in my open scene."*

It should call `get_objects_summary`. Then try a skill script:

> *"Audit my scene with the blender-mcp-workflow scene_audit script."*

## Tools exposed by the server

`get_objects_summary`, `get_object_detail_summary`, `execute_blender_code`, `execute_blender_code_for_cli`,
`get_blendfile_summary_*` (datablocks, path info, missing files, linked libraries, usage guess) and their
`*_for_cli` variants, `get_screenshot_of_window_as_image` / `_as_json`, `get_screenshot_of_area_as_image`,
`render_viewport_to_path`, `render_thumbnail_to_path`, `jump_to_*` navigation, and documentation tools
`get_python_api_docs`, `search_api_docs`, `search_manual_docs` (bundled API reference and user manual for
the installed version). Recipes: [`skills/blender-mcp-workflow/references/mcp-tools.md`](../skills/blender-mcp-workflow/references/mcp-tools.md).

## Headless tests on Windows (Microsoft Store install)

`blender.exe` inside `WindowsApps` cannot be executed directly. Use the execution alias instead:

```powershell
& "$env:LOCALAPPDATA\Microsoft\WindowsApps\blender-launcher.exe" -b --factory-startup --python tests\blender\test_skill_scripts.py -- '{"out_dir": "C:\\temp\\bst"}'
```

This runs Blender 5.2.3 LTS headless, but the alias does not forward stdout, so the tests write JSON
reports to `out_dir`; read those instead of the console.

## Which tools work on your install

Live work in the open window does not need `BLENDER_PATH`, and it is how the plugin works by default.

The `*_for_cli` tools start a background Blender and need `BLENDER_PATH` in the environment of the MCP server process.
Set it in whichever way your client passes environment variables to MCP servers, then restart the agent.

| Install | `BLENDER_PATH` | `*_for_cli` tools |
|---------|----------------|-------------------|
| Microsoft Store | Do not set it to the launcher | **Do not work** ([upstream issue](https://projects.blender.org/lab/blender_mcp/issues/69)): the launcher runs the code but drops its output, so the tool reports `No result marker` after the code ran. Check for its outputs before running anything again. Run background work through the launcher with a script that writes JSON, as above |
| Windows zip or installer | Path to `blender.exe` | Should work, not tested here; [a hang is reported upstream](https://projects.blender.org/lab/blender_mcp/issues/42) |
| macOS, Linux | Path to the Blender binary | See below |

## Headless runs on macOS and Linux

Use the app's binary directly; the commands are otherwise the same:

```bash
# macOS
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/bst"}'
# Linux
blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/bst"}'
```

On macOS set `BLENDER_PATH=/Applications/Blender.app/Contents/MacOS/Blender` for `execute_blender_code_for_cli`.

## Passing ARGS to scripts on any shell

Every skill script reads its ARGS from one JSON object after `--`. bash and zsh pass `'{"tri_budget": 3000}'`
unchanged; cmd and PowerShell 5.1 strip or mangle the inner quotes. On those shells, and in any script you want
to be portable, put the ARGS in a file:

```
blender -b asset.blend --python <skill_dir>/scripts/validate_asset.py -- --args-file args.json
```

Malformed JSON stops with a `ValueError` that says what was received, instead of a raw traceback. Inside the
MCP session (`runpy.run_path(..., init_globals={"ARGS": {...}})`) no quoting is involved; write the script path
with forward slashes on Windows too.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Tools missing in the agent | Restart the agent after `mcp add`; check `claude mcp list` |
| "Connection refused" | Blender is closed or the MCP add-on is disabled |
| A call timed out | The code or a render may still be running. Do not restart Blender or run it again: see "After a Timeout" in [`live-session.md`](../skills/blender-mcp-workflow/references/live-session.md) |
| `result must be a dict` | Scripts must assign `result = {...}` |
| API errors like `use_auto_smooth` / `scene.node_tree` | Old Blender API - see `blender-5-api-notes.md` |
| Running scripts without the add-on | Use `execute_blender_code_for_cli` (background Blender) or `blender -b file.blend --python script.py -- '{json}'` |
