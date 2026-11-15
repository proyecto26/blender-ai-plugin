---
name: uv-workflow
description: "Unwrap UVs: seams, packing, texel density, UDIM, lightmap UVs. Use when textures look stretched or blurry, or before texturing and export. Ships tested scripts. Not for baking (use texture-workflow)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: discipline
  stage: look_dev
  triggers: UV, unwrap, seam, texel density, UV pack, UDIM, lightmap UV, UV layout
  related-skills: texture-workflow, materials, export-pipeline
---

# UV Workflow

Efficient UV layouts with consistent texel density. Seams at hidden edges. Engine-ready.

## When to Use

- After topology locked, before texturing
- Modular kit UV atlas planning
- Lightmap UV channel setup
- UDIM workflows for hero assets

## Workflow

```
UV Planning → Seam Marking → Unwrap → Texel Density Check
    → Pack → Mirror/Overlap Decision → Lightmap UV (if needed) → Validation
```

## Seam Placement Rules

Place seams at:
- Back of head, spine centerline
- Inner arms, inner legs
- Bottom of chin, underside of objects
- Panel edges on hard surface (construction seams)
- Hidden areas under clothing/overlaps

Never place seams on:
- Face (front)
- Primary gameplay-visible surfaces
- Deforming joint centers (relocate to nearby hidden area)

## Texel Density

**Formula:** `Texel Density = Texture Resolution / UV Island Size in UV space`

Target consistency across visible surfaces:

| Asset Tier | Target TD (px/m) |
|------------|------------------|
| Hero | 512–1024 px/m |
| Standard | 256–512 px/m |
| Background | 128–256 px/m |

Use same density for modular kit pieces sharing atlas.

## Unwrap Methods

| Method | Use When |
|--------|----------|
| Smart UV Project | Quick blockout UVs only |
| Follow Active Quads | Strip UVs (roads, limbs) |
| Cube Project | Boxy hard surface |
| Lightmap Pack | Lightmap channel |
| Manual seam + Unwrap | Production default |

## UV Packing

- Margin: 0.002–0.01 UV units (engine dependent)
- Rotate islands for maximum packing efficiency
- Group islands by material ID
- Keep related islands near each other in UV space
- Use UVPackmaster or native pack for production

## Mirrored UVs

- Mirror UVs for symmetrical characters (save texture space)
- Offset mirrored islands slightly if engine requires unique bakes
- Mark mirrored halves in object naming: `_L` / `_R` meshes if separate

## UDIM Workflow

For hero assets exceeding single 4K texture:
- Tile 1001: head
- Tile 1002: torso
- Tile 1003: limbs
- Document tile assignment in production brief

## Lightmap UVs

Second UV channel requirements:
- No overlapping islands
- Consistent texel density less critical
- Larger margin (0.02+) for light bleed prevention
- Pack separately from texture UVs

## Modular UV Atlas

```
1. Plan shared atlas resolution (2048/4096)
2. Assign UV islands per module to atlas regions
3. Trim sheet regions for repeating detail
4. Vertex color variation for module differentiation
5. Document atlas layout for texture artist
```

## MCP Integration

1. Mark seams via MCP if supported
2. Execute unwrap via MCP
3. Query UV island count and pack efficiency
4. Assign UV channels via MCP
5. Validate no overlapping UVs (except intentional mirror)

## Validation Checklist

- [ ] No unintended overlapping UVs
- [ ] Consistent texel density on visible surfaces
- [ ] Seams hidden at gameplay angles
- [ ] UV islands within 0–1 (or UDIM tiles assigned)
- [ ] Lightmap channel separate if required
- [ ] Pack efficiency > 75%

## Constraints

### MUST DO
- Plan UVs before final modeling (topology informed by UV needs)
- Maintain texel density consistency
- Hide seams at logical construction edges
- Create lightmap UVs for baked lighting pipelines
- Document atlas layout for modular kits

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Smart UV Project as final production UVs
- Overlapping UVs on unique surface detail (unless mirrored)
- Inconsistent texel density on same asset tier
- Seams across faces or primary visible surfaces
- Skip packing margins

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/uv_unwrap_check.py` | Measure UVs per object and give a PASS/WARN/FAIL verdict: islands, collapsed faces, overlap, coverage per UDIM tile, per-island texel density spread, stretch (p95), out-of-range loops. Measure only unless `unwrap: True` (a mesh with no UV channel is an error and stays unchanged). `uv_layer` picks the channel (default: active render); the result names it. Overlap or a collapsed face FAILs a unique-bake or lightmap channel; `allow_overlap: True` declares a mirrored/stacked layout and skips the overlap rule. Unwrap `method`: `smart`, `seams`, `min_stretch`, with `margin_px` and `seams_from_angle`. `lightmap: True` adds a non-overlapping `UVMap_Lightmap` channel, measured under the lightmap rules (result key `lightmap`). `result_path` + `run_id` write the result to a file (`run_id` is also in the returned result). Unwrap or lightmap on a mesh shared with other objects is refused unless `make_single_user: True` (gives this object its own copy); `margin_px` is the real gap between islands. Edit Mode, component selection, selected objects and the active object are restored. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/uv_unwrap_check.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `objects`, `unwrap`, `method`, `angle_deg`, `margin_px`, `seams_from_angle`, `texture_px`, `target_px_per_m`, `uv_layer`, `allow_overlap`, `lightmap`, `make_single_user`, `result_path`, `run_id`

Thresholds: WARN when texel-density spread (max/min over islands) is above 1.3, union coverage is below 0.75, or stretch p95 is above 1.2. `uv_space_used` is now `uv_area_sum` (face areas added up, so stacked faces count twice); `uv_coverage` is the union.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Texel density calc | `references/texel-density.md` | Hero assets |
| Trim sheets | `references/trim-sheets.md` | Modular kits |
