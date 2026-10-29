---
name: retro-8bit-style
description: "Retro 8-bit art direction for Blender-assisted pixel/low-res aesthetics inspired by NES-era constraints. Use when the user asks for an '8-bit' or 'NES' look with very small palettes and chunky pixels (for richer SNES-style color use retro-16bit-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: 8-bit, 8bit, NES, retro 8-bit, four color, chunky pixel
  related-skills: pixel-art-style, retro-16bit-style, lowpoly-style, materials
---

# Retro 8-bit Style

Severe palette limits. Chunky read. Sprite logic.

## Constraints
Very low color count, high contrast characters, simple props, avoid gradients unless dithered.

## Recipe

Target NES-like 256x240 internal render, 3 colors plus transparency per sprite (about 25 on screen), 2 hard bands, 8 px tiles, no gradients.

1. Camera: `iso_camera.py` `projection` "military" with `pixel_tile` 8 (flat 45 degree view reads like a top-down sprite).
2. Shading: `toon_material.py` with `bands` 2, `rim` 0, `outline` 0 and a saturated base color.
3. Render preset: `render_preset.py` `stylized_flat`, then `ps1_look.py` with `snap` 0, `resolution` [256, 240], `flat` True, `fog` False.
4. Palette limit: `comp_grade.py` with `preset` "clean" and `posterize` 4 (Posterize node, 4 steps per channel, at most 64 colours); keep 3-4 flat material colours per object.
5. No anti-aliasing: `scene.render.filter_size = 0` and `scene.eevee.taa_render_samples = 1` (the stylized_flat preset uses 32 samples).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["camera"] = runpy.run_path(f"{skills}/isometric-style/scripts/iso_camera.py", init_globals={"ARGS": {"projection": "military", "target": target, "pixel_tile": 8}})["result"]
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_8bit", "base_color": [0.9, 0.2, 0.2], "bands": 2, "rim": 0.0, "objects": [target], "outline": 0.0}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["pixel"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0, "resolution": [256, 240], "flat": True, "fog": False}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "clean", "posterize": 4}})["result"]
import bpy
bpy.context.scene.render.filter_size = 0.0
bpy.context.scene.eevee.taa_render_samples = 1
result = r
```
