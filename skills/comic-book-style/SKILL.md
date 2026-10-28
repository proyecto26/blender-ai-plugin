---
name: comic-book-style
description: Comic book and graphic-novel art direction for Blender with ink-line emphasis, halftone cues, and high-contrast framing.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: comic book, comics, graphic novel, ink lines, halftone, Ben Day, superhero comic
  related-skills: stylized-style, materials, rendering, compositing, camera-cinematography
---

# Comic Book Style

Ink-ready contrast. Panel-friendly staging. Halftone optional.

## Tenets
1. High contrast lighting for ink read
2. Strong contour / crease support
3. Limited screentone / hatch language in textures or comp
4. Hero poses and camera angles
5. Speeds lines / impacts as FX meshes when needed

## Reference Guide
| Topic | Reference |
|-------|-----------|
| Ink & tone | `references/ink-tone.md` |

## Recipe

Target ink-ready contrast: 2 hard bands, thick black contour, hard key light, low heroic camera angle, punchy saturation.

1. Ink + flats: `toon_material.py` with `bands` 2, `rim` 0 and `outline` 0.025 (heavy contour).
2. Lighting: `light_rig.py` preset `golden_hour` (hard sun plus a cool fill gives a strong shadow shape).
3. Camera: `camera_rig.py` `lens_mm` 24, `elevation_deg` -10, `fill` 0.8 for a dramatic low hero angle.
4. Render: `render_preset.py` `stylized_flat`, then `comp_grade.py` `stylized_bloom` with `vignette` 0.25.
5. Halftone/speed lines have no script: add a Image Texture dot pattern (Nearest, Multiply) in the material, or draw FX as separate meshes.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Comic", "base_color": [0.9, 0.2, 0.15], "bands": 2, "rim": 0.0, "objects": [target], "outline": 0.025}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 24, "elevation_deg": -10, "fill": 0.8}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "vignette": 0.25}})["result"]
result = r
```
