---
name: rendering
description: "Blender rendering with Cycles and Eevee: sampling, denoising, camera setup, render passes, color management and render optimization via MCP. Use when the user wants a final render, noisy or slow renders, a quick preview, or consistent output settings. Ships tested scripts: render_preset.py (engine, samples, denoise, resolution and color-management presets)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: render, Cycles, Eevee, sampling, denoise, camera, render pass, color management, output
  related-skills: lighting, materials, realistic-style, stylized-style
---

# Rendering

Appropriate engine selection. Optimized settings. Production render passes.

## When to Use

- Final portfolio/cinematic renders
- Look development validation
- Render pass output for compositing
- Game asset preview renders (Turntable)
- Style validation (realistic vs stylized)

## Engine Selection

| Engine | Use When |
|--------|----------|
| Cycles | Final quality, realistic, portfolio |
| EEVEE (`BLENDER_EEVEE`) | Real-time preview, stylized, game look dev; ray-traced reflections + virtual shadow maps in Blender 4.2+/5.x |
| Workbench | Fast clay/QA renders, silhouette and topology checks |

## Workflow

```
Camera Setup → Render Settings → Sample Tests → Full Render
    → Pass Output → Color Management → Delivery
```

## Camera Setup

Naming: `CAM_[Shot]_[Number]`
- Focal length: 35mm (environment), 85mm (hero detail), 24mm (wide horror)
- Depth of field: subject distance focused
- Composition: rule of thirds; leading lines
- Turntable: empty parent rotating 360° for asset preview

## Cycles Settings

| Setting | Preview | Production |
|---------|---------|------------|
| Samples | 64–128 | 512–2048 |
| Denoise | OpenImageDenoise | OpenImageDenoise |
| Max bounces | 8 | 12 |
| Caustics | Off (default) | On if glass/water hero |

## Eevee Settings

| Setting | Value |
|---------|-------|
| Ray tracing (`eevee.use_raytracing`) | On for metals/glossy floors |
| Fast GI (`eevee.use_fast_gi`) | On for contact occlusion (replaces legacy AO toggle) |
| Bloom | Compositor Glare node, `Type` = Bloom (EEVEE bloom toggle removed in 4.2) |
| Shadows (`eevee.use_shadows`) | On; lower light `shadow_maximum_resolution` (e.g. 0.001) for crisp hero shadows, `shadow_filter_radius` for softness |
| Light threshold / sample counts | `taa_render_samples` 64+ for final |

## Render Passes

| Pass | Use |
|------|-----|
| Combined | Final composite |
| Diffuse Direct/Indirect | Relighting |
| Glossy | Reflection control |
| Normal | Compositing effects |
| AO | Contact shadow enhancement |
| Z (Depth) | DOF, fog in comp |
| Cryptomatte | Object masking |
| Emission | Screen glow effects |

## Color Management

```
View Transform: AgX (default) | Khronos PBR Neutral (product accuracy) | Standard (stylized/pixel exact)
Look: "AgX - Base Contrast" (neutral) or "AgX - High Contrast" / "AgX - Punchy" (dramatic)
Exposure: Adjust in compositor, not by blowing lights
```

## Render Optimization

- Use render region for test crops
- Adaptive sampling (Cycles)
- Disable unseen objects in render layers
- GPU rendering default when available
- Persistent data for animation sequences

## Asset Turntable Template

```
1. CAM_Turntable at 3/4 height, 45° angle
2. Empty at asset origin → rotate animation 0–360° (120 frames)
3. 3-point lighting rig
4. Render 1280×1280 or project-specified resolution
5. Output PNG sequence or MP4
```

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/render_preset.py` | Apply a render preset (engine, samples, denoise, resolution, color management). Returns the previous values so the change can be reverted. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/render_preset.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `preset`, `resolution_percentage`, `device`

## Reference Image Validation

When matching a photo/concept (`blender-mcp-workflow` skill → `references/reference-image-match.md`):

| Setting | Reference match |
|---------|-----------------|
| Hero camera | Match reference angle before grading |
| AgX Look | Base Contrast default; High Contrast if reference is punchy |
| Exposure | 0.15–0.45 typical; hull must read, not clip white |
| Preview playback | EEVEE, motion blur off, `taa_samples` 1–8 |
| Final still | Render at hero `CAM_*` — compare to reference |
| Compare tool | `get_screenshot_of_area_as_image("VIEW_3D")` or bpy render still |

Run `blender-mcp-workflow` skill → `references/visual-match-checklist.md` before delivery.

## MCP Integration

1. Configure render engine settings via MCP
2. Setup camera via MCP
3. Trigger test render via MCP if supported
4. Query render settings validation
5. Set output paths via MCP

## Constraints

### MUST DO
- Match render engine to project style
- **Screenshot or render compare** when reference image was provided
- Use denoising for Cycles production renders
- Setup color management before final render
- Render validation turntable for hero assets
- Organize cameras in `COL_Cameras`

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Production render without sample test
- Ignore color management (sRGB vs Linear)
- Render at excessive resolution without purpose
- Skip render passes when compositing planned
- Use Cycles for real-time game preview needs

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Pass compositing | `references/render-passes.md` | Multi-pass output |
| NPR/stylized render | `references/npr-rendering.md` | Stylized-style projects |
| Reference image match | `blender-mcp-workflow` skill → `references/reference-image-match.md` | Photo/concept attached |
| Visual match validation | `blender-mcp-workflow` skill → `references/visual-match-checklist.md` | Before delivery |
