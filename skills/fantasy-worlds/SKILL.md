---
name: fantasy-worlds
description: "Fantasy settings: medieval, high, dark and urban fantasy. Use for 'medieval castle' or 'dark fantasy ruins' props and palette."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials, set-dressing"
  triggers: fantasy, medieval, high fantasy, dark fantasy, urban fantasy, castle, magic world
  related-skills: environment-artist, prop-artist, materials, vegetation-artist, creature-artist
---

# Fantasy Worlds

Pick fantasy subgenre and keep material language consistent.

## Subgenres
Medieval low-magic · High fantasy · Dark fantasy · Urban fantasy

## Tenets
1. Material honesty (wood/stone/leather/magic emissive rules)
2. Silhouette heraldry readable
3. Magic FX gated by `vfx-fx`
4. Architecture matches tech level

## Recipe

Look: warm, material-honest fantasy. Medieval low-magic = golden hour, matte wood/stone (roughness 0.7-0.9), no emission; high fantasy = saturated, soft bloom; dark fantasy = moonlight, desaturated, grimy; magic is the only emissive (strength 2-5).

1. Light with `lighting/light_rig.py`: `golden_hour` (medieval/high), `moonlight` (dark fantasy), `overcast` (grim low-magic).
2. Materials via `materials/pbr_material.py`: weathered stone `[0.3, 0.29, 0.27]` `roughness` 0.9; oak `[0.25, 0.14, 0.07]` `roughness` 0.7; magic crystal `emission_color` `[0.3, 0.5, 1.0]` `emission_strength` 4.
3. Dress with `set-dressing/scatter_props.py` (barrels, crates, boxes as market/camp clutter); scatter rocks/trees on terrain with `geometry-nodes/scatter_points.py`.
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35, `aspect` "2.39:1"), grade with `compositing/comp_grade.py` `stylized_bloom` (high fantasy) or `cinematic` (dark).

| Item | Scale |
|---|---|
| Door | 2.2 m high, 1.1 m wide |
| Castle wall | 8-12 m high, 2-3 m thick |
| Table / chair seat | 0.75 m / 0.45 m |

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_WeatheredOak", "base_color": [0.25, 0.14, 0.07], "roughness": 0.7, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 8, "kinds": ["box", "barrel"]}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "aspect": "2.39:1"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom"}})["result"]
result = r
```
