# Blender MCP Integration Rules

When the Blender MCP server is connected, **execute operations through MCP** instead of describing
manual UI steps. Setup: the plugin's `docs/BLENDER_MCP_SETUP.md`.

## Priority Order

1. Inspect the scene (`get_objects_summary`, `scene_audit.py`)
2. Check the API for anything version-sensitive (`get_python_api_docs`, `blender-5-api-notes.md`)
3. Execute in small `execute_blender_code` steps that return evidence
4. Validate (`validate_asset.py`, screenshots)
5. Only fall back to UI instructions if MCP is unavailable

## Execution Protocol

```
1. get_objects_summary - learn the scene; note if the file is unsaved/dirty
2. If a reference image is attached -> reference-analysis-template.md BEFORE step 3
3. Plan the operation sequence (non-destructive first)
4. setup_collections.py for the asset
5. Execute step-by-step; check each result dict
6. get_screenshot_of_area_as_image("VIEW_3D") after camera, materials and lighting phases
7. Report object names, counts and metrics after each phase
```

## Reference Image Loop

| Step | MCP Tool |
|------|----------|
| Baseline | `get_screenshot_of_area_as_image("VIEW_3D")` |
| Audit scene | `scene_audit.py` via `execute_blender_code` |
| Camera / geometry / materials / lights | `execute_blender_code` |
| Compare pass | `capture_views.py` with `views: ["camera"]`, or `render_thumbnail_to_path` |
| Save (only if asked) | `bpy.ops.wm.save_as_mainfile(filepath=..., copy=True)` |

See `reference-image-match.md` for the full workflow.

## Scene Organization

```
Scene Collection
└── COL_<Asset>
    ├── COL_<Asset>_Reference   (hidden in viewport + render)
    ├── COL_<Asset>_Blockout
    ├── COL_<Asset>_HighPoly    (hidden)
    ├── COL_<Asset>_LowPoly
    ├── COL_<Asset>_Collision
    ├── COL_<Asset>_Lights
    ├── COL_<Asset>_Cameras
    └── COL_<Asset>_Export
```

Created by `scripts/setup_collections.py`. Naming prefixes: `naming-conventions.md`.

## Non-Destructive Defaults

- Run destructive operations on a working copy (`scripts/work_copy.py`, below); never edit the original first
- Apply modifiers only at export unless downstream work requires it
- Never delete or rename user objects you did not create without confirmation
- Never discard unsaved user work (`read_homefile`, `open_mainfile`, `revert`)

## Working Copies for Destructive Steps

Apply transforms/modifiers, join, boolean apply, remesh and decimate cannot be undone reliably through
MCP, so they run on disposable copies:

```python
import runpy
W = "<skill_dir>/scripts/work_copy.py"
r = runpy.run_path(W, init_globals={"ARGS": {"action": "begin", "objects": ["SM_Crate"]}})["result"]
# r["pairs"] == {"SM_Crate": "SM_Crate__work"}; edit and check the copy, e.g. fix_asset.py on it
runpy.run_path(W, init_globals={"ARGS": {"action": "accept"}})   # or {"action": "revert"}
```

| Action | Effect |
|--------|--------|
| `begin` | Full copies (object + `data.copy()`, materials too with `materials: true`) in `__Work`, re-targeted to each other. Originals untouched. Error if a work set is already pending |
| `accept` | `original.user_remap(copy)` moves every user (children's parent, modifier/constraint targets, collections, `scene.camera`) onto the copy; the original is linked into the excluded `__Checkpoint` collection as `<name>__prev`; the copy takes the original name |
| `revert` | Removes only the copies and datablocks they created |
| `status` | Pending state, from the scene custom property `work_copy` |

`__Checkpoint` is cleared only when the user asks. If the object has children outside the set (sockets,
colliders), they follow the accepted copy automatically. Gate order for a whole production:
the `blender-director` skill → `references/pipeline-gates.md`.

## Validation Queries

After major phases: object count and names, evaluated triangle counts, material count, collection
membership, origin placement, transform status - all returned by `scene_audit.py` / `validate_asset.py`.

## Error Handling

1. Read the error message completely
2. Check Blender is running and the add-on is enabled
3. Verify names against the current scene state
4. Retry with corrected parameters - never silently skip a failed step

## Fallback Mode (no MCP)

- Provide concise planning and specifications
- Output `bpy` scripts the user can run (`blender -b file.blend --python script.py -- '{json args}'`)
- Include the validation checklist for manual verification
