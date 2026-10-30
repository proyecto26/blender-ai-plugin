---
name: hand-painted-style
description: "Hand-painted game textures, WoW-style brushwork. Use for painted-in lighting. Not whole-image watercolor (painterly-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  requires: "compositing, lighting, materials, rendering"
  triggers: hand painted, hand-painted, painted texture, brushwork, stylized painted
  related-skills: stylized-style, texture-workflow, materials, lookdev
---

# Hand Painted Style

Brushwork in albedo. Geometry supports paint, not microdetail.

## Tenets
1. Paint values in albedo
2. Low roughness variation unless wet/metal accents
3. Soft bevels for paint catch
4. Atlas-friendly for kits
5. Avoid photoreal photo-bashed noise

## Recipe

Target a 512-1024 px per-asset painted atlas feel: baked-in value in albedo, roughness 0.85-1.0, almost no specular, soft overcast light for checking the paint.

1. Base material: `pbr_material.py` `roughness` 0.9, `specular_ior_level` 0.2, `metallic` 0 (paint carries the form; add the painted texture through `textures` {"base_color": path} once it exists).
2. Preview lighting: `light_rig.py` preset `overcast` so painted shading is not fighting real shadows.
3. Soft bevels for paint catch: add a Bevel modifier (width ~0.01, 2 segments) on hand-painted kit pieces.
4. Render: `render_preset.py` `eevee_final`, then `comp_grade.py` `clean`.
5. Textures: paint in Texture Paint mode or bake with `texture-workflow` before final.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_HandPainted", "base_color": [0.55, 0.4, 0.25], "roughness": 0.9, "metallic": 0.0, "specular_ior_level": 0.2, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "clean"}})["result"]
result = r
```
