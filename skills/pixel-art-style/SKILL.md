---
name: pixel-art-style
description: Pixel-art and texel-constrained art direction for Blender assets destined for pixel rendering, low-res textures, or HD-2D-adjacent pixel reads.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: pixel art, pixel, texel, low res texture, sprite-like, pixelated
  related-skills: lowpoly-style, retro-8bit-style, retro-16bit-style, hd-2d-style, materials
---

# Pixel Art Style

Texel discipline. Crisp pixels. Limited palette.

## Tenets
1. Declare target texel size / texture res
2. Nearest filtering intent
3. Limited palette
4. Avoid thin triangles that shimmer
5. Ortho or locked angles help readability

## Reference Guide
| Topic | Reference |
|-------|-----------|
| Texel rules | `references/texel-rules.md` |

## Recipe

Target 320x180 internal render (16 px tiles), dimetric 2:1 camera, a 16-32 color palette, nearest filtering, no shading gradients.

1. Camera: `iso_camera.py` `projection` "dimetric_2_1" with `pixel_tile` 16 (2:1 pixel-art tile ratio, crisp resolution multiple).
2. Shading: `toon_material.py` with `bands` 3, `rim` 0, `outline` 0 for flat palette-friendly bands.
3. Render settings: `ps1_look.py` with `snap` 0, `resolution` [320, 180], `flat` True, `fog` False (low-res, Nearest texture filtering, 32 px textures).
4. Render preset: `render_preset.py` `stylized_flat` (Standard view transform keeps palette colors exact). Run it before `ps1_look.py`, since presets reset resolution.
5. Palette reduction is not scripted: quantize afterwards in an image tool, or use a ColorRamp with constant interpolation in the compositor.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["camera"] = runpy.run_path(f"{skills}/isometric-style/scripts/iso_camera.py", init_globals={"ARGS": {"projection": "dimetric_2_1", "target": target, "pixel_tile": 16}})["result"]
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Pixel", "base_color": [0.8, 0.5, 0.3], "bands": 3, "rim": 0.0, "objects": [target], "outline": 0.0}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["pixel"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0, "resolution": [320, 180], "flat": True, "fog": False}})["result"]
result = r
```
