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

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Tools missing in the agent | Restart the agent after `mcp add`; check `claude mcp list` |
| "Connection refused" / timeouts | Blender is closed or the MCP add-on is disabled |
| `result must be a dict` | Scripts must assign `result = {...}` |
| API errors like `use_auto_smooth` / `scene.node_tree` | Old Blender API - see `blender-5-api-notes.md` |
| Running scripts without the add-on | Use `execute_blender_code_for_cli` (background Blender) or `blender -b file.blend --python script.py -- '{json}'` |
