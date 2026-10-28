---
name: export-pipeline
description: Production export from Blender to FBX, GLTF, OBJ, USD, and Alembic with scale, pivot, rotation, normals, materials, animation, and collision verification via MCP.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: export, FBX, GLTF, GLB, OBJ, USD, Alembic, Unity, Unreal, game engine import
  related-skills: asset-optimization, blender-modeler, materials
---

# Export Pipeline

Verified, engine-ready exports. Correct scale, axis, pivots, and data.

## When to Use

- Final asset delivery
- Engine import preparation
- Animation/rig export
- Batch export of modular kits

## Pre-Export Gate

**Required:** asset-optimization validation PASS before export.

## Workflow

```
Validation PASS → Export Settings → Test Export → Engine Verify
    → Fix Issues → Final Export → Documentation
```

## Format Selection

| Format | Best For |
|--------|----------|
| FBX | Unreal, Unity (legacy), animation |
| GLTF/GLB | Web, Godot, modern Unity |
| OBJ | Static mesh interchange (no rig) |
| USD | Pipelines, VFX, multi-asset |
| Alembic | VFX caches, sculpt animation |

## FBX Settings (Game Default)

```
Scale: 1.0
Apply Scalings: FBX All
Forward: -Z Forward
Up: Y Up
Apply Unit: ON
Mesh: ON
Armature: ON (if rigged)
Bake Animation: ON (if animated)
Path Mode: Copy (embed textures)
```

## GLTF Settings

```
Format: GLB (single file) or GLTF Separate
Include: Selected Objects
Transform: +Y Up
Compression: Draco (if supported by engine)
```

## Export Verification Matrix

| Check | Method |
|-------|--------|
| Scale | Measure known dimension in engine |
| Pivot | Verify floor contact / grip point |
| Forward axis | Compare to engine convention |
| Normals | Check shading in engine |
| Materials | Verify slot count and textures |
| Animation | Play action in engine |
| Collision | Import COL_ mesh separately |

## Engine-Specific Notes

### Unreal Engine
- Scale 1.0 = 1cm in UE (confirm project; may need 0.01 export scale)
- Import normals and tangents
- Separate collision mesh import
- LOD naming for auto-LOD: `SM_Asset_LOD0`

### Unity
- Scale 1.0 typically correct
- GLTF preferred for modern pipelines
- Humanoid rig mapping for characters

### Godot
- GLTF/GLB preferred
- +Y up default

## Collision Export

```
1. Export render mesh separately from collision
2. Collision: simple convex or box
3. Name: SM_Asset_COL
4. No materials on collision mesh
5. Apply transforms before export
```

## Animation Export

- Single action per export file (or document action list)
- Sample rate: 30fps default
- Bake constraints before export
- Include armature + skinned mesh in same file
- No unapplied scale on rig

## Batch Export (Modular Kits)

```
1. Select COL_Export collection
2. Export each module OR combined atlas per project spec
3. Maintain consistent origin per module type
4. Document grid snap points in README
```

## MCP Integration

1. Select export collection via MCP
2. Configure export settings via MCP
3. Execute export via MCP
4. Verify output file exists
5. Log export settings in delivery documentation

## Delivery Documentation Template

```markdown
## Export Package: [Asset Name]

**Format:** FBX / GLTF
**Scale:** 1 Blender unit = 1 meter
**Forward:** -Y / +X (document actual)
**Files:**
- SM_Asset.fbx
- T_Asset_BC.png, T_Asset_N.png, ...

**Import Notes:**
- [Engine-specific steps]

**Validation:** PASS — [date]
```

## Constraints

### MUST DO
- Pass asset-optimization before export
- Apply transforms on export objects
- Test import in target engine
- Document scale and axis conventions
- Export collision separately for games

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Export with unapplied scale
- Export without validation
- Mix collision and render in same export without documentation
- Assume default FBX settings work for all engines
- Export all modifiers without testing engine result

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/export_asset.py` | Export selected/listed objects with engine presets (FBX / glTF / USD / OBJ). Validates the output file exists and reports its size. Does not modify the scene (selection is restored; modifiers are applied only in the exported data). |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/export_asset.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `objects`, `engine`, `out_path`, `animation`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Engine import | `references/engine-import.md` | First import test |
| Validation | `blender-mcp-workflow` skill → `references/validation-checklist.md` | Pre-export gate |
