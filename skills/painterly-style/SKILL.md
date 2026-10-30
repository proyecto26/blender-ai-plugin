---
name: painterly-style
description: "Whole-render watercolor or oil painting looks. Use for gouache or impressionist illustration. Not painted textures (hand-painted-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: painterly, watercolor, oil painting, impressionist, illustrative paint, gouache
  related-skills: hand-painted-style, stylized-style, materials, compositing, rendering
---

# Painterly Style

Pigment feel. Soft edges. Illustration lighting.

## Sublooks
- Watercolor: paper grain, bleeds, light washes
- Oil: thicker strokes, richer impasto suggestion in texture

## Tenets
1. Soft terminators
2. Pigment/paper overlays in mat or comp
3. Limited harsh specular
4. Composition like a canvas, not a game HUD shot

## Recipe

Target a soft, warm, low-spec look: roughness 0.85+, wide soft light, glow and gentle vignette, paper/canvas texture added at the end.

1. Material: `pbr_material.py` `roughness` 0.9, `specular_ior_level` 0.1, `metallic` 0 with a painted albedo.
2. Lighting: `light_rig.py` preset `golden_hour` (warm key, cool fill, soft terminators).
3. Render: `render_preset.py` `eevee_final`.
4. Grade: `comp_grade.py` preset `stylized_bloom` with `warmth` 0.2 and `vignette` 0.3.
5. Pigment/paper: no script covers it. Multiply a paper-grain Image Texture over the final image in the compositor (Mix node, Multiply, factor ~0.3), and for watercolor soften edges with a small Blur node on the color pass.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Painterly", "base_color": [0.6, 0.45, 0.3], "roughness": 0.9, "metallic": 0.0, "specular_ior_level": 0.1, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": 0.2, "vignette": 0.3}})["result"]
result = r
```
