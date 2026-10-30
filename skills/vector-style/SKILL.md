---
name: vector-style
description: "Flat vector look: clean fills, sharp silhouettes. Use for 'flat design' or SVG-like. Not bouncy cartoons (cartoon-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: vector, flat design, clean vector, graphic flat, svg-like
  related-skills: minimalist-style, cartoon-style, materials, rendering
---

# Vector Style

Flat fills. Clean edges. Iconic shapes. Almost no gradients unless intentional.

## Recipe

Target flat fills with no gradients, clean 1-2 px edges, 3-5 color palette, view transform Standard so colors match the swatches.

1. Fills: `toon_material.py` with `bands` 2, `rim` 0, `outline` 0.01 (a thin uniform contour; use `outline` 0 for pure flat shapes).
2. Lighting: `light_rig.py` preset `overcast` (soft, so band edges are the only shading).
3. Render: `render_preset.py` `stylized_flat`, then `comp_grade.py` `clean`.
4. Camera: use an orthographic camera (`camera_rig.py` `lens_mm` 85 with a long distance approximates it) to keep icon-like silhouettes.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Vector", "base_color": [0.2, 0.6, 0.9], "bands": 2, "rim": 0.0, "objects": [target], "outline": 0.01}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "clean"}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 85, "aspect": "1:1"}})["result"]
result = r
```
