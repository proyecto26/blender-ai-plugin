---
name: blender-mcp-workflow
description: "Safe way to drive Blender through the MCP server and write bpy code that survives Blender 5.x API removals. Use before ANY bpy snippet, scene audit, validation gate, naming or polycount rule, or references-first world. Ships tested scripts. Not for planning a production (use blender-director)."
license: MIT
metadata:
  author: https://github.com/proyecto26
  version: "2.0.0"
  domain: blender
  role: foundation
  category: core
  stage: any
  triggers: Blender MCP, execute_blender_code, bpy script, scene audit, validate asset, naming convention, polycount budget, viewport screenshot, Blender 5 API, reference match, reference folder, style bible, match my refs
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
# headless, outside MCP (bash/zsh): one JSON object after --
blender -b asset.blend --python <skill_dir>/scripts/validate_asset.py -- '{"tri_budget": 3000}'
# any shell, including cmd and PowerShell (they mangle JSON quotes): put the ARGS in a file
blender -b asset.blend --python <skill_dir>/scripts/validate_asset.py -- --args-file args.json
```

Read a script before running it the first time in a session; pass only the documented ARGS.

When Blender is not connected and the user will paste code into Blender's Scripting workspace, give them
the same short `runpy` call with the absolute path of the installed script and their ARGS. Don't inline or
rewrite the script: the tested file is what makes the result reliable.

Write that path with forward slashes, also on Windows (`"C:/Users/me/.claude/plugins/.../scene_audit.py"`):
a pasted backslash path such as `"C:\Users\..."` is a Python syntax error, because `\U` starts an escape.
Python and Blender accept forward slashes on every OS; macOS and Linux paths need no change.

## Scripts

| Script | Purpose | Mutates scene? |
|--------|---------|----------------|
| `scripts/scene_audit.py` | Collections, evaluated tris, materials, unapplied transforms, naming violations | No |
| `scripts/setup_collections.py` | Idempotent `COL_` hierarchy (Reference/Blockout/HighPoly/LowPoly/Collision/Lights/Cameras/Export) | Adds collections only |
| `scripts/validate_asset.py` | PASS/WARN/FAIL gate: transforms, tri budget, n-gons, manifold, loose geo, UVs, materials, naming, scale, origin | No |
| `scripts/fix_asset.py` | Fixes the usual FAILs: bakes unapplied scale (or rotation+scale) into the mesh and adds a box-projected or Smart UV layer only where none exists; idempotent | Edits the named meshes |
| `scripts/work_copy.py` | Disposable working copies for destructive steps: `begin` / `accept` / `revert` / `status`; originals are never modified, accepted originals go to an excluded `__Checkpoint` collection | Adds `__Work` copies; accept relinks |
| `scripts/scene_snapshot.py` | Named snapshots of the scene's objects: `save` / `list` / `diff` (added, removed, moved, mesh changed) / `restore` (appends named objects into `_Restored`, removes nothing). `save` never changes the open file's path | `save`, `list`, `diff`: no (writes snapshot files only). `restore`: adds objects |
| `scripts/capture_views.py` | Front / 3-4 / side / back / top / camera PNGs with a temporary camera; restores settings | No (temp camera removed) |
| `scripts/ref_board.py` | Reads a folder of reference images, writes `style_bible.json` (palette, value/saturation histograms, contrast, warm/cool) | No (writes the JSON only) |
| `scripts/compare_to_refs.py` | Scores renders, viewport captures or engine screenshots against the bible: distances, score, plain-language drift list | No |
| `scripts/clash_audit.py` | Clash gate for several meshes: penetrating pairs with an estimated depth, objects fully inside others, floating parts (groups by contact within `gap_max_m`); modifiers count, touching faces do not; optional `evidence_path` writes its own result file into a run folder | No (writes the evidence file only when asked) |
| `scripts/silhouette_score.py` | Projects the named meshes through named cameras and scores the silhouette against reference masks (alpha, or background from the corners): IoU, bbox and centroid drift per view, PASS/FAIL against `min_iou`; no render needed | No |
| `scripts/fit_search.py` | Coordinate search over named numeric properties (scale, location, a modifier value) that raises the `silhouette_score.py` IoU; bounded by `max_evals`, restores every value unless `apply` is true | Only with `apply: true` |
| `scripts/ingest_asset.py` | Imports a local GLB / glTF (external `.bin`) / FBX / OBJ / USD file into a new collection, scales it to a target size, puts its base centre at the origin, prefixes names, bakes transforms, then runs `validate_asset.py`; refuses URLs and `.blend` | Adds the imported objects only |

When to reach for the four newer scripts:

- **`clash_audit.py`** at the end of a multi-part build (furniture, kits, mechanical assemblies) and before the `validate`
  gate: it finds what `validate_asset.py` cannot see, because that checks one object at a time. Open meshes have no inside,
  so containment in them comes back as `not_measured` and the verdict is WARN, never PASS.
- **`silhouette_score.py`** when a reference photo, concept or render exists for a view and "does the outline match" needs a
  number instead of an opinion; **`fit_search.py`** when that number is low because of a few known dials (overall scale, one
  offset) and not because the shape is wrong. Both are described in `references/reference-image-match.md`.
- **`ingest_asset.py`** when the user supplies a model file (a purchased asset, a scan, an export from another tool) that must
  fit the project's scale and naming before anything is built around it. Download the file outside Blender first.

## Before a Destructive Step

Before a destructive step (apply transforms/modifiers, join, boolean apply, remesh, decimate) use
`scripts/work_copy.py`: `begin` copies the objects into `__Work`, edit the copies (for example
`fix_asset.py` on `SM_Crate__work`), check them, then `accept` (the copy takes the original name and
every reference; the untouched original goes to the excluded `__Checkpoint`) or `revert` (copies removed).
One pending work set at a time. Details: `references/mcp-integration.md`.

## Snapshots Before Risky Edits

Use `scripts/scene_snapshot.py` when you want a named restore point without File > Save As (which would make the snapshot the open file): `save` before a risky edit, `diff` afterwards to see exactly which objects were added, removed, moved or had their mesh changed, and `restore` with `objects: [...]` to bring back only what you need (copies land in `_Restored`; nothing is deleted or overwritten). Snapshots live in `<file folder>/snapshots` unless you pass `dir`. It covers objects and the data they use, not scene settings, and the mesh hash ignores modifiers and materials. For whole-asset destructive steps `work_copy.py` is still the tool; the snapshot is for scene-level history.

## Working Live

The user usually watches in the open window, so bounded work runs live: call `bpy.ops.ed.undo_push` before and after
each phase (MCP code adds no undo steps), and send long renders to a background process from a saved snapshot. A black
screenshot usually means a minimized window on Windows, not an empty scene. After a timeout the code or a render may still be
running, so do not retry or edit until it has been checked. Read `references/live-session.md` before the first live edit.

## Execution Protocol

```
1. CONNECT   get_objects_summary (or scene_audit.py) - confirm Blender responds, learn the scene
2. VERIFY    get_python_api_docs / search_api_docs for any API you are unsure of (Blender 5.x changed a lot)
3. ORGANIZE  setup_collections.py (asset name) - never dump objects in the scene root
4. EXECUTE   small execute_blender_code steps; each returns a result dict you check
5. LOOK      get_screenshot_of_area_as_image("VIEW_3D") or capture_views.py after each visual phase
6. VALIDATE  validate_asset.py before export; fix every FAIL (fix_asset.py covers scale and missing UVs)
7. REPORT    object names, tri counts, verdicts, file paths
```

## Reference Folder First

When the user has a folder of reference images for a game world, level or prop set (for example `game/ref/`),
read it before building anything: refs first is what keeps the style consistent.

1. Run `ref_board.py` on the folder, then look at the images yourself: the statistics cover colour and tonal
   balance, not composition. Write a short style brief and get the user's yes.
2. Model props in Blender with the matching skills; capture them and run `compare_to_refs.py`.
3. Export to the engine; the engine is assembled through its own MCP, outside this plugin. Capture
   walk-through screenshots and run `compare_to_refs.py` on them; fix the drift it names.
4. Stop after two consecutive rounds with no improvement and report what is left.

Full loop, what the numbers mean and the drift-to-fix table: `references/reference-folder-workflow.md`.

## Verify, Don't Guess

Model training data is full of Blender 2.8-4.0 code. Treat every API you did not just verify as suspect:

1. **Script first.** If a plugin script covers the task (see Scripts), run it with JSON ARGS instead of
   hand-writing bpy. Scripts are tested on Blender 5.2 and return a result dict you can check.
2. **Look it up.** For any hand-written API, call `search_api_docs` / `get_python_api_docs` (bundled with
   the server for the running version) or read `references/blender-5-api-notes.md`. Never invent
   operators or properties.
3. **Probe in isolation.** Check `bl_rna.properties`, or run a minimal snippet in a temporary scene you remove, or
   with `execute_blender_code_for_cli` on a scratch `.blend` where that tool works, before touching the user's scene.
4. **Apply, then confirm.** Make the real change, then confirm with `get_objects_summary`,
   `get_object_detail_summary`, or a screenshot. Report the evidence, not just "done".
5. **Current version only.** Write code for the running Blender (5.2+). No `bpy.app.version` branches or
   `hasattr` fallbacks for removed APIs.

## Shared References

| Topic | File |
|-------|------|
| Blender 5.x API changes (verified on 5.2 LTS) | `references/blender-5-api-notes.md` |
| Tool recipes and pitfalls | `references/mcp-tools.md` |
| Working live: checkpoints, traps, timeouts, background work | `references/live-session.md` |
| MCP-first operating rules | `references/mcp-integration.md` |
| Universal asset pipeline | `references/asset-pipeline.md` |
| Naming conventions | `references/naming-conventions.md` |
| Polycount budgets | `references/polycount-budgets.md` |
| Validation checklist | `references/validation-checklist.md` |
| Reference image matching | `references/reference-image-match.md`, `references/reference-analysis-template.md`, `references/visual-match-checklist.md` |
| Reference folder first (style bible, engine screenshots vs refs) | `references/reference-folder-workflow.md` |

## Anti-Patterns

- Narrating UI clicks ("press Tab...") when MCP is connected
- Calling `bpy.ops` without the right mode, selection and active object
- Using APIs removed in 4.1-5.2 (`use_auto_smooth`, `eevee.use_bloom`, `scene.node_tree`, `ShaderNodeTexMusgrave`, Principled `"Specular"`, `mod["Socket_N"] = v`) or writing version fallbacks: this plugin targets Blender 5.2+ only
- Huge single scripts - split into verifiable steps
- Reporting success without a validation result or a screenshot
