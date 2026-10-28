---
name: texture-workflow
description: Production texture workflow for atlases, baking AO/curvature/normal/roughness maps, decals, and texture memory optimization. Use for game-ready texture pipelines in Blender via MCP.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: texture, bake, normal map, AO, curvature, roughness, metallic, height, atlas, decal, emission
  related-skills: uv-workflow, materials, asset-optimization
---

# Texture Workflow

Bake high-poly detail to efficient texture sets. Optimize memory. Engine-ready outputs.

## When to Use

- Baking sculpt detail to normal maps
- Creating texture atlases for modular kits
- PBR texture set generation
- Decal placement and blending
- Texture memory optimization

## Workflow

```
High/Low Poly Setup → Cage Setup → Bake Maps → Composite
    → Atlas Pack → Engine Format Export → Validation
```

## Standard PBR Texture Set

| Map | Format | Notes |
|-----|--------|-------|
| Base Color | sRGB PNG | No embedded AO |
| Normal | Linear PNG | OpenGL convention unless engine specifies |
| Roughness | Linear PNG | Single channel |
| Metallic | Linear PNG | Single channel |
| AO | Linear PNG | Multiply in shader, not base color |
| Height | Linear PNG | Optional parallax |
| Emission | sRGB PNG | Mask-based |
| ORM Packed | Linear PNG | R=AO, G=Roughness, B=Metallic (Unreal) |

Naming: `T_[Asset]_[Map]` per `blender-mcp-workflow` skill → `references/naming-conventions.md`

## Bake Setup

```
1. Low-poly mesh with UVs (active)
2. High-poly mesh (sculpt or detail) — selected
3. Cage extrusion: 0.01–0.05m (adjust per asset scale)
4. Ray distance: match cage
5. Bake margin: 16px minimum
6. Anti-aliasing: enabled
```

## Maps to Bake

| Map | Source | Priority |
|-----|--------|----------|
| Normal | High→Low | Required |
| AO | High or low (cavity) | Required |
| Curvature | High sculpt | Wear masks |
| Position | High | Optional (blending) |
| Thickness | Subsurface meshes | Characters |

## Texture Atlas Strategy

Modular kits share one atlas:
```
1. All modules UV'd to shared 0–1 or UDIM space
2. Bake each module to atlas regions
3. Trim sheet areas for repeating detail
4. Single material references atlas
5. Document region map for artists
```

## Decals

- Decal mesh projected on surface
- Separate UV channel or atlas region
- Blend via alpha mask
- Limit decal overdraw in engine

## Memory Optimization

| Technique | Savings |
|-----------|---------|
| ORM packing | 3 textures → 1 |
| Shared atlas | N materials → 1 texture |
| Lower res on hidden surfaces | 50%+ memory |
| BC compression in engine | 4:1 or 6:1 |
| Trim sheets | Reuse detail across assets |

## Resolution Guidelines

See `blender-mcp-workflow` skill → `references/polycount-budgets.md` texture section.

## MCP Integration

1. Setup bake objects via MCP
2. Configure bake settings via MCP if supported
3. Export baked images via MCP
4. Assign baked textures to materials via MCP
5. Query texture count and resolution

## Validation Checklist

- [ ] Normal map correct orientation (test in engine)
- [ ] No UV seams visible in bake
- [ ] AO not baked into base color
- [ ] Consistent texel density in final textures
- [ ] Texture resolution within budget
- [ ] Files named per convention
- [ ] sRGB vs Linear correctly assigned

## Constraints

### MUST DO
- Bake high-poly detail before discarding sculpt
- Use cage for clean normal bakes
- Pack ORM for engine efficiency
- Test normal map orientation in target engine
- Document atlas regions for modular kits

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Bake without cage on complex shapes
- Embed AO in base color (PBR standard)
- Exceed texture budget without LOD justification
- Use inconsistent normal map conventions
- Skip margin in bake settings

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/bake_maps.py` | Bake high-poly -> low-poly maps in Cycles (normal, AO, roughness, diffuse color) to PNG files, with cage extrusion. Restores the render engine afterwards. Requires the low-poly to have a UV map. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/bake_maps.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `low`, `high`, `maps`, `size`, `extrusion`, `samples`, `out_dir`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Bake troubleshooting | `references/bake-troubleshooting.md` | Bake artifacts |
| ORM packing | `references/orm-packing.md` | Unreal/Unity export |
