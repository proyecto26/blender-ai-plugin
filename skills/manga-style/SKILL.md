---
name: manga-style
description: "Manga-inspired art direction for Blender emphasizing monochrome value design, speed lines, screentone feel and manga panel staging. Use when the user wants a 'manga panel', a black-and-white screentone render, or shonen/seinen speed lines (for colored cel-shaded anime use anime-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: manga, seinen, shonen, shojo, screentone, manga panel, Japanese comic
  related-skills: anime-style, comic-book-style, compositing, camera-cinematography
---

# Manga Style

Value-first. Screentone feel. Panel staging. Distinct from full-color anime.

## Tenets
1. Design in grayscale values first
2. Screentone / hatch textures sparingly
3. Speed lines and emphasis FX
4. Expressive faces / eyes per demographic
5. Black-heavy compositions OK

## Vs anime-style
Anime = color cel; Manga = print value language (can still be 3D color with manga staging).

## Recipe

Target a print-value look: 2 hard bands, black-heavy shadows, desaturated to grayscale, thin consistent contour, dynamic angles.

1. Cel material: `toon_material.py` with `bands` 2, `rim` 0 and `outline` 0.015, base color a mid-gray.
2. Lighting: `light_rig.py` preset `golden_hour` for one hard key and deep shadow (grayscale in comp).
3. Camera: `camera_rig.py` `lens_mm` 35, `elevation_deg` -5, `azimuth_deg` 35, `aspect` "9:16" for a tall panel.
4. Render: `render_preset.py` `stylized_flat`, then `comp_grade.py` preset `noir` (saturation 0 = monochrome) with `vignette` 0.
5. Screentone and speed lines have no script: use an Image Texture dot pattern with Nearest filtering as a mix over the shadow band, and radial line meshes for FX.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Manga", "base_color": [0.6, 0.6, 0.6], "bands": 2, "rim": 0.0, "objects": [target], "outline": 0.015}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 35, "elevation_deg": -5, "azimuth_deg": 35, "aspect": "9:16"}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "noir", "vignette": 0.0}})["result"]
result = r
```
