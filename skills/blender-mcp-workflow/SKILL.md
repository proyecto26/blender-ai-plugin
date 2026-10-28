---
name: blender-mcp-workflow
description: Use before writing ANY Blender Python (bpy) code, even a short snippet and even when no Blender version is mentioned: Blender 5.2 removed APIs that most examples online still use (mesh auto smooth, EEVEE bloom, scene.node_tree, Geometry Nodes modifier item assignment, old Principled socket names), so unchecked code usually breaks. Also use whenever driving Blender through the official Blender Lab MCP server (execute_blender_code, get_objects_summary, screenshots, API/manual doc search) and for the shared production rules: naming, polycount budgets, the asset pipeline, validation gates, reference matching. Ships tested bpy scripts for scene audit, collection setup, game-ready validation and review captures, and points to every other skill's scripts.
license: MIT
metadata:
  author: https://github.com/proyecto26
  version: "2.0.0"
  domain: blender
  role: foundation
  triggers: Blender MCP, execute_blender_code, bpy script, scene audit, validate asset, naming convention, polycount budget, viewport screenshot, Blender 5 API, reference match
  related-skills: blender-director, qa-review, export-pipeline, asset-optimization
---

# Blender MCP Workflow

The foundation every other skill in this plugin builds on: how to work safely through the
**official Blender MCP server** (Blender Lab; this plugin targets Blender 5.2+), the shared production standards,
and a set of tested scripts.

## Safety First

`execute_blender_code` runs arbitrary Python inside the user's Blender with their OS permissions.
Blender Lab's own guidance: review generated code, and prefer a VM or a machine without sensitive data.

- **Inspect before editing** - `get_objects_summary` / `scene_audit.py` first; never assume an empty scene.
- **Never destroy user work silently** - the open file may be unsaved (`bpy.data.is_dirty`). Do not
  `wm.read_homefile`, delete the user's authored objects/scenes, or overwrite the `.blend` without asking.
  Removing clearly **unused** data is fine: orphan datablocks (`users == 0`, e.g.
  `bpy.data.orphans_purge(do_recursive=True)`), empty collections, and objects this plugin created
  (report what was removed).
- **Experiment in isolation** - test risky code with `execute_blender_code_for_cli` (background Blender on
  a copy/scratch `.blend`) or inside a temporary scene you remove afterwards.
- **No network / no shell from bpy** - never call `subprocess`, `os.system`, sockets or downloads from
  Blender code unless the user explicitly asks.
- **Save only on request**, or with `copy=True` to a new path.

## Official MCP Tool Catalog

| Need | Tool |
|------|------|
| Scene hierarchy (collections -> objects) | `get_objects_summary` |
| One object in depth (modifiers, materials, constraints) | `get_object_detail_summary` |
| File-level info | `get_blendfile_summary_datablocks`, `..._path_info`, `..._missing_files`, `..._of_linked_libraries`, `..._usage_guess` |
| Run bpy in the live session | `execute_blender_code` (assign a JSON-safe dict to `result`) |
| Run bpy headless on a file | `execute_blender_code_for_cli(blend_file, code)` and the `*_for_cli` summaries |
| See the UI / viewport | `get_screenshot_of_window_as_image`, `get_screenshot_of_area_as_image(area_ui_type="VIEW_3D")`, `get_screenshot_of_window_as_json` |
| Render | `render_viewport_to_path` (current settings), `render_thumbnail_to_path` (fast, low quality) |
| Navigate the UI | `jump_to_view3d_object_by_name`, `jump_to_view3d_object_data_by_name`, `jump_to_tab_by_name`, `jump_to_tab_by_space_type` |
| Verify API before writing code | `get_python_api_docs("bpy.types.X")`, `search_api_docs`, `search_manual_docs` |

Tool descriptors from the server are authoritative - read them if a call fails. Details and
recipes: `references/mcp-tools.md`.

## Running This Plugin's Scripts

Every script under `<skill>/scripts/` follows one contract: module-level `ARGS` dict in, JSON-safe
`result` dict out. Use the absolute path of the skill directory you loaded:

```python
# via execute_blender_code
import runpy
result = runpy.run_path("<skill_dir>/scripts/scene_audit.py",
                        init_globals={"ARGS": {"tri_budget": 5000}})["result"]
```

```bash
# headless, outside MCP
blender -b asset.blend --python <skill_dir>/scripts/validate_asset.py -- '{"tri_budget": 3000}'
```

Read a script before running it the first time in a session; pass only the documented ARGS.

When Blender is not connected and the user will paste code into Blender's Scripting workspace, give them
the same short `runpy` call with the absolute path of the installed script and their ARGS. Don't inline or
rewrite the script: the tested file is what makes the result reliable.

## Scripts

| Script | Purpose | Mutates scene? |
|--------|---------|----------------|
| `scripts/scene_audit.py` | Collections, evaluated tris, materials, unapplied transforms, naming violations | No |
| `scripts/setup_collections.py` | Idempotent `COL_` hierarchy (Reference/Blockout/HighPoly/LowPoly/Collision/Lights/Cameras/Export) | Adds collections only |
| `scripts/validate_asset.py` | PASS/WARN/FAIL gate: transforms, tri budget, n-gons, manifold, loose geo, UVs, materials, naming, scale, origin | No |
| `scripts/capture_views.py` | Front / 3-4 / side / back / top / camera PNGs with a temporary camera; restores settings | No (temp camera removed) |

## Execution Protocol

```
1. CONNECT   get_objects_summary (or scene_audit.py) - confirm Blender responds, learn the scene
2. VERIFY    get_python_api_docs / search_api_docs for any API you are unsure of (Blender 5.x changed a lot)
3. ORGANIZE  setup_collections.py (asset name) - never dump objects in the scene root
4. EXECUTE   small execute_blender_code steps; each returns a result dict you check
5. LOOK      get_screenshot_of_area_as_image("VIEW_3D") or capture_views.py after each visual phase
6. VALIDATE  validate_asset.py before export; fix every FAIL
7. REPORT    object names, tri counts, verdicts, file paths
```

## Verify, Don't Guess

Model training data is full of Blender 2.8-4.0 code. Treat every API you did not just verify as suspect:

1. **Script first.** If a plugin script covers the task (see Scripts), run it with JSON ARGS instead of
   hand-writing bpy. Scripts are tested on Blender 5.2 and return a result dict you can check.
2. **Look it up.** For any hand-written API, call `search_api_docs` / `get_python_api_docs` (bundled with
   the server for the running version) or read `references/blender-5-api-notes.md`. Never invent
   operators or properties.
3. **Probe in isolation.** Run a minimal snippet with `execute_blender_code_for_cli` on a scratch `.blend`
   (or check `bl_rna.properties`) before touching the user's scene.
4. **Apply, then confirm.** Make the real change, then confirm with `get_objects_summary`,
   `get_object_detail_summary`, or a screenshot. Report the evidence, not just "done".
5. **Current version only.** Write code for the running Blender (5.2+). No `bpy.app.version` branches or
   `hasattr` fallbacks for removed APIs.

## Shared References

| Topic | File |
|-------|------|
| Blender 5.x API changes (verified on 5.2 LTS) | `references/blender-5-api-notes.md` |
| Tool recipes and pitfalls | `references/mcp-tools.md` |
| MCP-first operating rules | `references/mcp-integration.md` |
| Universal asset pipeline | `references/asset-pipeline.md` |
| Naming conventions | `references/naming-conventions.md` |
| Polycount budgets | `references/polycount-budgets.md` |
| Validation checklist | `references/validation-checklist.md` |
| Reference image matching | `references/reference-image-match.md`, `references/reference-analysis-template.md`, `references/visual-match-checklist.md` |

## Anti-Patterns

- Narrating UI clicks ("press Tab...") when MCP is connected
- Calling `bpy.ops` without the right mode, selection and active object
- Using APIs removed in 4.1-5.2 (`use_auto_smooth`, `eevee.use_bloom`, `scene.node_tree`, `ShaderNodeTexMusgrave`, Principled `"Specular"`, `mod["Socket_N"] = v`) or writing version fallbacks: this plugin targets Blender 5.2+ only
- Huge single scripts - split into verifiable steps
- Reporting success without a validation result or a screenshot
