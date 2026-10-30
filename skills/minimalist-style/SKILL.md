---
name: minimalist-style
description: "Minimalist, abstract look: reduced forms, negative space. Use for 'keep it minimal' or a cluttered scene."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: minimalist, minimal, abstract, reduced forms, negative space, simple shapes
  related-skills: stylized-style, materials, camera-cinematography, lookdev
---

# Minimalist Style

Reduce until it breaks — then add one thing back.

## Tenets
1. Few shapes
2. Few colors
3. Negative space intentional
4. Typography-like clarity of form
5. Abstract OK if brief asks

## Recipe

Target 1 subject, 2-3 colors total, 70% or more negative space, soft even light, square crop.

1. Material: `pbr_material.py` single flat color, `roughness` 0.7, `metallic` 0, no textures.
2. Lighting: `light_rig.py` preset `overcast` (soft, almost shadowless).
3. Camera: `camera_rig.py` `lens_mm` 85, `fill` 0.35 (subject small in frame), `aspect` "1:1".
4. Render: `render_preset.py` `eevee_final`, then `comp_grade.py` `clean`.
5. Keep the background a single color in World (the light rig sets it); remove props until the shot breaks, then restore one.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Minimal", "base_color": [0.9, 0.35, 0.25], "roughness": 0.7, "metallic": 0.0, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 85, "fill": 0.35, "aspect": "1:1"}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "clean"}})["result"]
result = r
```
