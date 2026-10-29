---
name: genre-rpg
description: "Art direction for RPG, JRPG, CRPG, ARPG and MMORPG worlds in Blender including loot rarity reads and region identity. Use when the user asks for an RPG town, quest hub, region identity, or items whose rarity should be readable at a glance."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: RPG, JRPG, CRPG, ARPG, MMORPG, loot, quest hub, RPG environment
  related-skills: fantasy-worlds, environment-artist, prop-artist, character-artist, materials
---

# Genre: RPG Family

Region identity. Quest hubs. Loot rarity visual language. Class-readable gear.

## Recipe

Region-identity world with loot rarity color language (grey, green, blue, purple, orange) and 1.8 m hero scale; warm 3/4 camera at 50 mm.

1. Make rarity materials with `pbr_material.py`: one call per tier, e.g. `MAT_Loot_Epic` `base_color` [0.4, 0.1, 0.8], `emission_strength` 1.5.
2. Scatter region props around a quest hub with `scatter_props.py` (`count` 10, `clusters` 3).
3. Light with `light_rig.py` preset `golden_hour`.
4. Hero/hub camera with `camera_rig.py`: `lens_mm` 50, `azimuth_deg` 30, `elevation_deg` 25.
5. Finish with `comp_grade.py` preset `cinematic`.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["loot"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Loot_Epic", "base_color": [0.4, 0.1, 0.8], "emission_color": [0.5, 0.2, 1.0], "emission_strength": 1.5, "metallic": 0.8, "roughness": 0.3, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 10, "clusters": 3}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Hub", "target": target, "lens_mm": 50, "azimuth_deg": 30, "elevation_deg": 25}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Hero height | 1.8 m |
| Door | 1 x 2.2 m |
| Quest hub radius | 15-30 m |
| Chest | 1 x 0.6 x 0.6 m |
| Loot pickup glow | emission 1-3 |
