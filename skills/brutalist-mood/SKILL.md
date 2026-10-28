---
name: brutalist-mood
description: Brutalist and concrete-monument mood direction for Blender architecture and scenes with raw concrete, monumental scale, and austere composition.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: brutalist, brutalism, raw concrete, monumental concrete, austere architecture
  related-skills: archviz, environment-artist, materials, camera-cinematography, minimalist-style
---

# Brutalist Mood

Monumental concrete. Austere. Human small. Few materials.

## Recipe

Target: one raw concrete material (grey about 0.35, roughness 0.9, metallic 0), flat overcast light, wide 24 mm low camera so the monolith dominates and a human-sized figure is under 1/10 of frame height.

1. `pbr_material` MAT_Concrete: `base_color` [0.36, 0.36, 0.35], `roughness` 0.9, `metallic` 0.0. Add board-formed grain with a Noise or Wave texture into the `Bump` node by hand; no second material.
2. `bevel_stack` with `width` 0.02, `segments` 1: concrete edges are chamfered, never rounded.
3. `light_rig` `overcast` (large soft sun, grey sky) for even, shadowless mass; use `moonlight` for a night variant.
4. `camera_rig` `lens_mm` 24, `elevation_deg` 4 (looking up), `fill` 0.9, `dof_fstop` None.
5. `comp_grade` `noir` for monochrome, or `cinematic` with `warmth` -0.2 and `vignette` 0.25 for cold colour.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Concrete", "base_color": [0.36, 0.36, 0.35], "roughness": 0.9, "metallic": 0.0, "objects": [target]}})["result"]
r["bevel"] = runpy.run_path(f"{skills}/hard-surface/scripts/bevel_stack.py", init_globals={"ARGS": {"objects": [target], "width": 0.02, "segments": 1}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Mono_01", "target": target, "lens_mm": 24, "elevation_deg": 4, "fill": 0.9}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": -0.2, "vignette": 0.25}})["result"]
result = r
```
