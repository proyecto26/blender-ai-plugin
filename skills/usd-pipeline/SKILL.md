---
name: usd-pipeline
description: "USD for film/VFX hand-offs, tested scripts: export, reimport, round-trip checks of counts, transforms, mesh sizes, material names. Not for engine FBX/GLB delivery (use export-pipeline)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: delivery
  stage: export
  triggers: USD, USDC, USDA, OpenUSD, round trip, reimport, pipeline hand-off, VFX interchange, Omniverse, Houdini, Solaris
  related-skills: export-pipeline, asset-optimization, materials
---

# USD Pipeline

Write a USD file from Blender and prove that what comes back is what went out, before it goes to another tool.

## When to Use

- A studio, VFX or lookdev team asks for USD (.usd, .usdc, .usda)
- Checking that an export keeps the object count, placement, mesh size and material names
- Finding out what the Blender exporter drops or changes before the hand-off

Engine delivery (FBX, GLB, scale and axis presets per engine) belongs to `export-pipeline`. This skill covers the check
that the USD file is faithful, and the USD-specific settings.

## Workflow

```
Validate asset → Round trip (usd_roundtrip.py) → Read the problems → Fix or document → Final export
```

1. Run `asset-optimization` validation first: unapplied scale or loose parts show up as round-trip noise.
2. Run `scripts/usd_roundtrip.py` on the objects to deliver. It writes the file, imports it back, compares, and removes the
   copy from the scene.
3. `ok: false` lists each problem as a sentence (`RT_Crate: materials [...] -> [...]`). Fix the scene or document the loss
   in the delivery note. Do not hand over a file whose round trip you have not read.
   Linked duplicates at the same transform cannot be told apart after import, so they are paired by a minimum-difference
   assignment (any count). Real differences (transform, materials, vert/face counts) always outweigh the evaluated
   bounding box, which only breaks ties. Labels in `ambiguous_pairings` have coincident objects or another assignment
   with the same total: if they differ only in something the script does not measure, the pairing is still a guess.
4. Deliver the file the script wrote (`path`).

## What the check covers, and what it does not

| Checked | How |
|---------|-----|
| Mesh count | exported meshes against imported meshes |
| Transforms | `matrix_world` of each object, tolerance `tol` (default 1e-4) |
| Geometry size | evaluated vertex and face counts per mesh |
| Material names | set of names per object, ignoring Blender's `.001` suffix |

Not checked: UV values, normals, vertex colours, shape keys, rigs and animation, light and camera settings, shader
networks, texture files. A passing run says the counts, placement and names survived, not that the file looks right in the
other tool. Open it there before you call the delivery done.

## Facts the tests established (Blender 5.2.3)

- The exporter writes a transform prim and a mesh prim of the same name per mesh object. The import therefore gives an
  Empty AND a Mesh object with one base name. The script pairs them by type.
- A Subdivision Surface modifier exported with `BEST_MATCH` is written as the base cage plus a subdivision scheme, and a plain
  import returns the cage. The script defaults to `TESSELLATE` so the evaluated mesh is what is compared.
- Imported material names get `.001` when the name exists in the file, which is why names are compared without it.
  The check runs with `mtl_name_collision_mode="MAKE_UNIQUE"`, so reusing the original material cannot fake a pass.

## Constraints

### MUST DO
- Read `problems` from every round trip before delivering
- Keep the written USD file where the user can find it (`out_path` in the project folder)
- Say what the check does not cover (see above)

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Claim another tool will read the file correctly: only Blender's own import was run
- Run the round trip on the user's only copy of unsaved work without saying the scene is changed and restored (the import
  adds objects, then they are removed)

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/usd_roundtrip.py` | Export objects to USD, import the file back, compare object counts, world transforms, evaluated vertex/face counts and material names, then remove the imported copy. Writes the USD file to `out_path`. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/usd_roundtrip.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `out_path` (required), `objects`, `tol`, `keep`, `subdivision`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Format choice and scale | `export-pipeline` skill → `references/engine-import.md` | Not sure USD is the right format |
