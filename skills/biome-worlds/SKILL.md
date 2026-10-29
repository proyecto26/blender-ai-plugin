---
name: biome-worlds
description: "Biome and setting art direction for Blender covering underwater, desert, arctic, jungle, underground/cave and floating-island environments. Use when the user asks for a specific climate or biome ('underwater level', 'snowy tundra', 'jungle ruins', 'cave system', 'floating islands') and needs palette, props and landmark language."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: underwater, desert, arctic, jungle, underground, cave, floating islands, biome, climate setting
  related-skills: environment-artist, vegetation-artist, lighting, materials, scene-assembly
---

# Biome Worlds

Climate drives palette, fog, vegetation density, and material wear.

## Recipe

Climate drives the palette: pick one biome and key the light, world colour and material roughness to it (desert: warm sun, roughness 0.9, sand `[0.75, 0.55, 0.3]`; arctic: cool overcast, roughness 0.4 ice; jungle: saturated greens, low sun, high density; underground/underwater: near-black world, one practical light).

1. Light with `lighting/light_rig.py`: `golden_hour` (desert), `overcast` (arctic, jungle canopy), `moonlight` (underwater/cave, then keep exposure low), `neon_night` for bioluminescent caves.
2. Ground/material the hero with `materials/pbr_material.py` (sand, snow `roughness` 0.5, wet rock `roughness` 0.2 and `coat_weight` 0.3, moss green).
3. Fill the biome with `set-dressing/scatter_props.py` for rocks/crates/camps, and for vegetation or rocks on a terrain use `geometry-nodes/scatter_points.py` (`surface`, `collection`, `density` 2-8 per m2, `align_to_normal` False for trees).
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35 for vistas, `dof_fstop` 4 for jungle depth).
5. Atmosphere: `compositing/comp_grade.py` `stylized_bloom` (jungle, underwater) or `cinematic` (desert, arctic); fog is world/volume based, set it in prose via a Volume Scatter on the world.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Sand", "base_color": [0.52, 0.3, 0.1], "roughness": 0.9, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 6, "kinds": ["box", "barrel"], "clusters": 2}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "dof_fstop": 4.0}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": 0.3}})["result"]
result = r
```
