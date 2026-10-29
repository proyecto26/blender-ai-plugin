---
name: lod-pipeline
description: "Dedicated LOD generation, naming, screen-size targets and validation for game meshes in Blender via MCP. Use when a mesh needs LOD1..N, a lower-poly distant version, or LOD naming for Unreal, Unity or Godot. Ships tested scripts: generate_lods.py (Decimate-based LOD copies in COL_LODs; stacked copies get hide_render so renders show LOD0 only)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: LOD, LODs, level of detail, decimate, LOD0, LOD1, impostor, screen size
  related-skills: asset-optimization, export-pipeline, unity-export, unreal-export, collision-proxy
---

# LOD Pipeline

Intentional LOD chains. Preserve silhouette. Validate reductions.

## When to Use

- Game assets needing LOD0–N
- Batch LOD for modular kits
- Before Unity/Unreal/Godot export

## Workflow

```
Approve LOD0 → Generate LOD1..N → Fix silhouette breaks
  → Naming → Screen-size table → Export verify
```

## Typical Budgets (guide)

| LOD | Tris vs LOD0 | Keep |
|-----|--------------|------|
| LOD0 | 100% | Full detail |
| LOD1 | 40–60% | Major forms |
| LOD2 | 15–30% | Silhouette |
| LOD3 | 5–10% | Blob / impostor candidate |

Tune per asset importance and camera.

## Generation Methods

1. **Decimate (planar/collapse)** — fast props
2. **Manual retopo low** — hero characters/vehicles
3. **Delete interiors / small parts** — vehicles, buildings
4. **Bake normals from LOD0 → low** — when detail must move to texture

## Naming

```
SM_Asset_LOD0
SM_Asset_LOD1
SM_Asset_LOD2
```

Collection: `COL_LODs_[Asset]`

## Validation Checklist

- [ ] Silhouette matches at intended distance
- [ ] No major holes / inverted normals
- [ ] UVs still valid (or rebaked)
- [ ] Materials slots consistent across LODs
- [ ] Vertex colors/UVs needed by shader preserved
- [ ] LOD transitions planned (screen size %)

## Screen Size Starters

| LOD | Screen size (UE-like guide) |
|-----|-----------------------------|
| LOD0 | 1.0 – 0.5 |
| LOD1 | 0.5 – 0.25 |
| LOD2 | 0.25 – 0.1 |
| LOD3 | 0.1 – 0.0 |

## Constraints

### MUST DO
- Protect silhouette before poly reduction
- Keep LOD0 as source of truth
- Document budgets in production brief

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Blind decimate until unrecognizable
- Different material slot counts across LODs without reason

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/generate_lods.py` | Generate LOD copies of a mesh with Decimate (collapse) at given ratios. The source becomes/keeps LOD0; copies are named <base>_LOD1.. and placed in a COL_LODs collection. Copies share nothing with the source (single-user data). |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/generate_lods.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `object`, `ratios`, `apply`, `rename_source`, `offset_x`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Lod Budgets | `references/lod-budgets.md` | When needed |
| Lod Validation | `references/lod-validation.md` | When needed |
