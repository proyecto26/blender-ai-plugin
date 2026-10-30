---
name: retro-16bit-style
description: "16-bit SNES/Genesis look: richer palettes, dither. Use for 'SNES'. Not NES four-color (retro-8bit-style) or pixel-art-style."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: 16-bit, 16bit, SNES, Genesis, Mega Drive, retro 16-bit
  related-skills: pixel-art-style, retro-8bit-style, materials, lookdev
---

# Retro 16-bit Style

Richer palettes than 8-bit. Dither/gradient cues. Still texel-disciplined.

## Recipe

Target SNES-like 256x224 internal render, 16 colors per sprite (about 256 on screen), 3-4 shading bands plus dither, 16 px tiles.

1. Camera: `iso_camera.py` `projection` "dimetric_2_1" with `pixel_tile` 16.
2. Shading: `toon_material.py` with `bands` 4, `rim` 0.15, `outline` 0 (richer ramps than 8-bit).
3. Render preset: `render_preset.py` `stylized_flat`, then `ps1_look.py` with `snap` 0, `resolution` [256, 224], `flat` True, `fog` False.
4. Dither is not scripted: add an Image Texture Bayer pattern (Nearest) as the ColorRamp factor offset, or dither in an image tool after rendering.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["camera"] = runpy.run_path(f"{skills}/isometric-style/scripts/iso_camera.py", init_globals={"ARGS": {"projection": "dimetric_2_1", "target": target, "pixel_tile": 16}})["result"]
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_16bit", "base_color": [0.35, 0.6, 0.9], "bands": 4, "rim": 0.15, "objects": [target], "outline": 0.0}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["pixel"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0, "resolution": [256, 224], "flat": True, "fog": False}})["result"]
result = r
```
