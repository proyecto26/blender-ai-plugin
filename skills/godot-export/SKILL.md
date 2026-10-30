---
name: godot-export
description: "Godot 4 export, tested scripts: GLB scale, PBR, clips, -col collision. Use when an asset goes to Godot, looks grey, merges clips or needs import collision; load even for advice. Not Unity/Unreal (use unity-export, unreal-export)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: delivery
  stage: export
  triggers: Godot, Godot export, Godot GLTF, Godot GLB, Godot materials, Godot animation
  related-skills: export-pipeline, lod-pipeline, collision-proxy, asset-optimization, materials
---

# Godot Export

GLTF/GLB first. Clean nodes. Godot-friendly materials and animation.

## When to Use

- Shipping meshes/animations to Godot 4.x
- GLB single-file props and characters
- Simple collision companions

## Pre-Flight

1. `asset-optimization` PASS
2. Apply transforms; Y-up friendly hierarchy
3. Materials metallic-roughness compatible

## Format

| Case | Format |
|------|--------|
| Default | GLB |
| Editable sidecar textures | GLTF separate |

## Settings

```
Format: GLB
+Y Up
Apply Modifiers: ON (when final)
Animation: include when needed
```

## Hierarchy

- Root empty or object named for scene root
- Avoid deep useless empties
- Name collision with Godot's import suffixes (`-col`, `-colonly`, `-convcolonly`); Godot ignores `COL_` / `UCX_` names

## Materials

- Principled BSDF → GLTF PBR
- Pack images or keep relative paths consistent
- Emission only where intended

## Animation

- NLA or actions exported as clips
- Name actions `AN_[Clip]`
- Root motion documented if used

## Verify in Godot

- [ ] Scale
- [ ] Import materials
- [ ] Animation libraries
- [ ] Collision shapes

## Compare the Godot World to Your Refs

Screenshots from the Godot world (captured through a Godot MCP, outside this plugin) can be scored against a
reference folder with the `blender-mcp-workflow` skill: run its ref_board script once, then its
compare_to_refs script on the screenshots. The loop and drift fixes are in that skill's
reference-folder-workflow reference.

## Constraints

### MUST DO
- Prefer GLB unless project says otherwise
- Test import once
- Keep naming consistent with `naming-conventions.md`

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Rely on Blender-only shader nodes that do not export

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/export_godot.py` | Godot 4 glTF (.glb) export with import-hint naming checks. Godot reads node-name suffixes on import: -col (trimesh static body), -convcolonly / -colonly (collision only), -rigid, -navmesh, -noimp. Reports which hints are present. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/export_godot.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `objects`, `out_path`, `animation`

The export uses the active scene only and reads the file back: check `verify.ok` after export (`missing` and `leaked` list mismatches). `verify.checked: false` means NOT_CHECKED, never a pass.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Godot Checklist | `references/godot-checklist.md` | When needed |
