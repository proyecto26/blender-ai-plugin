# Official Blender MCP - Tool Recipes

Server: Blender Lab MCP (`blender-mcp`, Blender 5.1+), add-on from the `https://lab.blender.org/`
extensions repository. Tool names below are the server's; clients prefix them (e.g. Claude Code shows
`mcp__blender__execute_blender_code`). **The server's tool descriptors are authoritative.**

## Inspection (read-only - always first)

| Tool | Returns | Use |
|------|---------|-----|
| `get_objects_summary` | Collection tree with each object's name, type, parent, data, selection, visibility | First call of every task |
| `get_object_detail_summary(name)` | Transforms, parent/children, modifiers, constraints, materials, collections | Before editing a specific object |
| `get_blendfile_summary_datablocks` | Data-block counts, workspace, render engine | Scene size / engine check |
| `get_blendfile_summary_path_info` | File path, relative paths | Before saving or exporting |
| `get_blendfile_summary_missing_files` | Missing images, libraries, caches | Before render / export |
| `get_blendfile_summary_of_linked_libraries` | Linked `.blend` libraries | Scene assembly / overrides |
| `get_blendfile_summary_usage_guess` | Scored guess of what the file is for | Unknown files |
| `get_screenshot_of_window_as_json` | UI layout, areas, active object, selection | Understand UI state without an image |

## Execution

`execute_blender_code(code)` - runs in the live session. Assign a JSON-serialisable **dict** to
`result`; `print` output is not returned.

```python
import bpy
obj = bpy.data.objects.get("SM_Crate_01")
result = {"exists": obj is not None, "dims": list(obj.dimensions) if obj else None}
```

`execute_blender_code_for_cli(blend_file, code)` - opens the file with `blender --background` in a
separate process. Changes are **not saved** unless your code saves (to a new path). Ideal for
batch validation, exports and experiments that must not disturb the user's session.
The `*_for_cli` summary tools mirror the live ones for files on disk.
Needs the `BLENDER_PATH` environment variable (the Blender executable, or on a Microsoft Store install the
`blender-launcher.exe` alias) set in the MCP server's environment, then a restart of the agent; without it the
tool fails with "Blender executable not found". Fall back to the headless command in this skill.

Rules:
- Keep each call small (one phase) and return evidence (`names`, `tris`, `status`).
- Operators need context: set mode, selection and active object, or use `bpy.context.temp_override(...)`.
- Prefer `bpy.data` / `bmesh` for precise, side-effect-free edits; use `bpy.ops` for modifiers apply,
  UV unwrap, export, and other operator-only features.
- After changing geometry, use `obj.evaluated_get(bpy.context.evaluated_depsgraph_get())` for final counts.
- In Edit Mode use `bmesh.from_edit_mesh` + `bmesh.update_edit_mesh` (or edits are lost).

## Seeing the Result

| Tool | Notes |
|------|-------|
| `get_screenshot_of_area_as_image(area_ui_type="VIEW_3D")` | Live viewport - fastest visual check |
| `get_screenshot_of_window_as_image` | Whole UI (node editors, properties) |
| `render_thumbnail_to_path(output_path)` | Quick low-quality render, settings auto-restored |
| `render_viewport_to_path(output_path)` | Full render with current settings - can be slow in Cycles |
| `capture_views.py` (this skill) | Multi-angle PNG set with a temporary camera |

Use `jump_to_view3d_object_by_name(name)` to frame an object before a viewport screenshot.

## Documentation Lookup (before writing unfamiliar bpy)

- `get_python_api_docs("bpy.types.CompositorNodeGlare")` - exact members for this Blender version
- `search_api_docs("geometry nodes interface new_socket")` - full-text API search
- `search_manual_docs("smooth by angle")` - concepts and workflows from the user manual

## Common Fallback Snippets

```python
# Collection
import bpy
col = bpy.data.collections.get("COL_Props") or bpy.data.collections.new("COL_Props")
if col.name not in bpy.context.scene.collection.children:
    bpy.context.scene.collection.children.link(col)
```

```python
# Apply transforms on one object
with bpy.context.temp_override(active_object=obj, object=obj,
                               selected_objects=[obj], selected_editable_objects=[obj]):
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
```

```python
# Merge by distance without mode switching
import bmesh
bm = bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
bm.to_mesh(obj.data); bm.free()
```

## Error Recovery

| Error | Action |
|-------|--------|
| Connection refused / timeout | Blender closed or add-on disabled - ask the user to enable the MCP add-on |
| `result must be a dict` | Wrap the value: `result = {"value": x}` |
| `context is incorrect` / poll failed | Set mode/selection or use `temp_override` |
| `KeyError` on a node socket | Socket renamed in 5.x - see `blender-5-api-notes.md` / `get_python_api_docs` |
| Object not found | Re-run `get_objects_summary`; names get `.001` suffixes |
