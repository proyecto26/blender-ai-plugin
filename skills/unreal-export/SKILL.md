---
name: unreal-export
description: "Unreal Engine export: FBX scale, SM_/SK_ naming, UCX collision, sockets. Use when an asset is headed for Unreal or arrives mis-scaled. Ships tested scripts. Not for Unity or Godot (use unity-export, godot-export)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: delivery
  stage: export
  triggers: Unreal, UE5, UE4, Unreal export, UCX, Unreal LOD, skeletal mesh, Unreal FBX, socket
  related-skills: export-pipeline, lod-pipeline, collision-proxy, asset-optimization, materials
---

# Unreal Export

UE-ready FBX. Correct centimeter scale awareness. UCX collision. LOD and socket naming.

## When to Use

- Static mesh or skeletal mesh to Unreal
- UCX/UCLX collision export
- LOD chain import
- Socket / pivot setup for gameplay

## Pre-Flight

1. `asset-optimization` PASS
2. `lod-pipeline` for LOD0–N
3. `collision-proxy` for UCX meshes
4. Apply scale; pivots at intended UE origin

## Scale Note

Unreal is centimeter-based. Common approaches:
- Model in meters in Blender, export FBX with unit conversion / 0.01 awareness per project pipeline
- Or work to project-documented scale and verify with a 100cm reference

**Always measure a known edge after import.**

## FBX Defaults (Static)

```
Selected Objects
Apply Scalings: FBX All
Forward: -Z Forward
Up: Y Up
Mesh: ON
Smoothing: Face
```

## Naming for UE

| Type | Pattern |
|------|---------|
| Static mesh | `SM_Name` |
| Skeletal | `SK_Name` |
| Skeleton | `SKEL_Name` |
| LOD | `SM_Name_LOD0` … |
| Collision | `UCX_SM_Name_01` |
| Socket empty | `SOCKET_Name` |

## Collision

- Prefer convex UCX pieces over complex mesh colliders
- Multiple UCX meshes supported
- See `collision-proxy`

## Skeletal

- UE mannequin-oriented proportions when required
- Root bone; no leftover Blender deform leftovers
- Export morph targets if needed (shape keys)

## Verify in Unreal

- [ ] Scale (door ~200cm, character ~180cm)
- [ ] Collision wireframe
- [ ] LODs auto-detected
- [ ] Materials / texture sampling
- [ ] Sockets transform

## Constraints

### MUST DO
- Confirm scale with known-dimension test
- Prefix collision with `UCX_`
- Validate LODs and materials after import

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Export without collision plan for physics actors
- Mix unit systems undocumented

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/export_unreal.py` | Unreal Engine FBX export with pre-flight checks: SM_/SK_ prefixes, UCX_ collision naming that matches a render mesh, LOD naming, SOCKET_ empties, applied transforms, and scene unit scale. Exports render mesh + its UCX_ proxies + SOCKET_ empties. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/export_unreal.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `mesh`, `out_dir`, `strict`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Unreal Checklist | `references/unreal-checklist.md` | When needed |
| Ucx Naming | `references/ucx-naming.md` | When needed |
