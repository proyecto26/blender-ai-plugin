---
name: folk-horror-style
description: Folk horror art direction for Blender with rural ritual uncanny, pastoral daylight dread, and community-wrongness storytelling.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: folk horror, rural horror, ritual, pagan, pastoral dread, village horror, Wicker Man
  related-skills: horror-style, environment-artist, set-dressing, vegetation-artist, materials
---

# Folk Horror

Daylight dread. Pastoral beauty wrong. Ritual objects. Closed communities.

## Tenets
1. Beautiful nature + wrong customs
2. Handmade ritual props
3. Village scale, fields, woods
4. Warm daylight can be scarier than night
5. Symbols repeating

## Recipe

Target: pastoral daylight dread: warm low sun (golden hour, about 12 degrees), straw/wood handmade props, camera at field height (35 mm, about 1.4 m), a ring of 7 ritual props around the focal object.

1. `pbr_material` MAT_Straw: `base_color` [0.62, 0.45, 0.2], `roughness` 0.9, `metallic` 0.0 for hay, rope and unpainted wood.
2. `light_rig` `golden_hour`; the world stays warm so the scene looks lovely and wrong. Use `overcast` for a damp-moor variant.
3. `scatter_props` `count` 7, `kinds` `box_small`, `clusters` 1, `min_dist` 2.0, `max_dist` 3.0: a tight ritual ring (symbols repeat, so keep one prop kind).
4. `camera_rig` `lens_mm` 35, `elevation_deg` 4, `fill` 0.4.
5. `comp_grade` `cinematic` with `warmth` 0.15 and `vignette` 0.3; keep saturation high, the horror is in the daylight.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Straw", "base_color": [0.62, 0.45, 0.2], "roughness": 0.9, "metallic": 0.0, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["ring"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 7, "kinds": ["box_small"], "clusters": 1, "min_dist": 2.0, "max_dist": 3.0}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Folk_01", "target": target, "lens_mm": 35, "elevation_deg": 4, "fill": 0.4}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": 0.15, "vignette": 0.3}})["result"]
result = r
```
