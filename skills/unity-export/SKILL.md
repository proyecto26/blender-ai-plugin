---
name: unity-export
description: "Unity export, tested scripts: FBX axis, scale, materials, humanoid rigs. Use when an asset goes to Unity, comes in rotated -90, at scale 100 or white; load even for advice. Not Unreal/Godot (use unreal-export, godot-export)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: delivery
  stage: export
  triggers: Unity, Unity export, Unity FBX, Unity GLTF, humanoid, Unity materials, Unity LOD, Unity collision
  related-skills: export-pipeline, lod-pipeline, collision-proxy, asset-optimization, materials
---

# Unity Export

Unity-ready transforms, materials, LODs, and collision. Prefer GLB/GLTF for modern; FBX for legacy/animation.

## When to Use

- Shipping assets to Unity
- Humanoid character export
- Prefab-oriented mesh splits and LODs

## Pre-Flight

1. `asset-optimization` PASS
2. `lod-pipeline` if LODs required
3. `collision-proxy` if physics required
4. Apply transforms; correct pivots

## Recommended Formats

| Case | Format |
|------|--------|
| Static mesh modern | GLB |
| Animated / humanoid | FBX |
| Simple props | GLB or FBX |

## Transform Defaults

```
Unit: Meters (Unity 1 unit = 1m)
Forward: -Z (Blender) → verify in Unity
Scale Factor: 1.0 (fix if model tiny/huge)
```

## Materials

- Prefer single material slots matching Unity workflow
- Metallic-Roughness for GLTF
- Embed or provide textures beside FBX
- Name materials `MAT_` consistently

## Characters

- T-pose or A-pose per project
- Root bone at origin; hips correctly placed
- Humanoid: clear bone naming; test Avatar mapping
- Export animations as separate clips when needed

## LODs & Collision

- LOD Group naming: `SM_Name_LOD0..N` or Unity LOD Group meshes
- Collision: convex meshes or Unity primitive colliders from proxies
- See `collision-proxy` for UCX-style naming if using FBX conventions

## Verify in Unity

- [ ] Scale vs reference cube
- [ ] Pivot / prefab placement
- [ ] Normals / tangents
- [ ] Materials assigned
- [ ] LOD transitions
- [ ] Animator clips (if any)

## Constraints

### MUST DO
- Validate before export
- Document scale factor used
- Test import once before declaring done

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Assume FBX settings without project convention
- Leave unused high-poly LODs in prefab

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/export_unity.py` | Unity FBX export with pre-flight checks: applied transforms, UVs, material slots, and axis/scale conversion so the asset imports at scale (1,1,1) with no -90 X rotation (Apply Scalings = FBX Units Scale + Apply Transform). |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/export_unity.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `objects`, `out_path`, `animation`, `strict`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Unity Checklist | `references/unity-checklist.md` | When needed |
| Unity Materials | `references/unity-materials.md` | When needed |
