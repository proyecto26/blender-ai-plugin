---
name: genre-survival
description: "Art direction for survival and survival-horror gameplay spaces in Blender emphasizing resource props, crafting readability and tension routes. Use when the user is building a survival game, crafting/scavenging environments, or a survival-horror map with scarce resources."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: survival, survival horror, crafting, resource gathering, survival game art
  related-skills: environment-artist, prop-artist, horror-style, set-dressing, biome-worlds
---

# Genre: Survival

Resources must read at speed. Safe vs unsafe zones. Crafting benches iconic.

## Recipe

Resource-readable survival space: resource props in high-contrast accents, safe zone warm 3000 K light vs cold dark outside, benches iconic.

1. Warm safe-zone light: `light_rig.py` preset `horror_practical`; threat areas get `moonlight`.
2. Scatter resource props with `scatter_props.py` (`count` 10, `clusters` 4, `max_dist` 10).
3. Resource highlight material with `pbr_material.py` (`base_color` [0.8, 0.6, 0.1], `roughness` 0.5).
4. Camera `camera_rig.py`: `lens_mm` 28, `elevation_deg` 15 for tension.
5. Grade with `comp_grade.py` preset `horror_vhs` for grit, or `cinematic` for subtle.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["fire"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 10, "clusters": 4, "max_dist": 10}})["result"]
r["res"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Resource", "base_color": [0.8, 0.6, 0.1], "roughness": 0.5, "objects": [target]}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Survival", "target": target, "lens_mm": 28, "elevation_deg": 15}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Crafting bench | 1.5 x 0.8 x 0.9 m |
| Safe zone radius | 8-12 m |
| Resource node | 0.5-1 m |
| Shelter door | 0.9 x 2 m |
| Threat sightline | 15-25 m |
