---
name: blender-mcp-workflow
description: Use whenever you write or review Blender Python (bpy) code for Blender 4.2+/5.x, or drive Blender through the official Blender Lab MCP server (execute_blender_code, get_objects_summary, screenshots, render_viewport_to_path, API/manual doc search) or needs the shared production rules - naming conventions, polycount budgets, the universal asset pipeline, validation gates, reference-image matching, and Blender 5.x API changes. Ships tested bpy scripts for scene audit, COL_ hierarchy setup, game-ready validation, and multi-angle review captures.
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
**official Blender MCP server** (Blender Lab, Blender 5.1+), the shared production standards,
and a set of tested scripts.

## Safety First

`execute_blender_code` runs arbitrary Python inside the user's Blender with their OS permissions.
Blender Lab's own guidance: review generated code, and prefer a VM or a machine without sensitive data.

- **Inspect before editing** - `get_objects_summary` / `scene_audit.py` first; never assume an empty scene.
- **Never destroy user work silently** - the open file may be unsaved (`bpy.data.is_dirty`). Do not
  `wm.read_homefile`, delete scenes/objects you did not create, or overwrite the `.blend` without asking.
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
- Using pre-4.x APIs: `use_auto_smooth`, `eevee.use_bloom`, `scene.node_tree`, `ShaderNodeTexMusgrave`, Principled `"Specular"`
- Huge single scripts - split into verifiable steps
- Reporting success without a validation result or a screenshot
