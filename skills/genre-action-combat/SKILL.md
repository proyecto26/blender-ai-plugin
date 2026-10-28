---
name: genre-action-combat
description: Art direction for action, hack-and-slash, beat 'em up, and fighting-game readable combat spaces and prop language in Blender.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: action game, hack and slash, beat em up, brawler, fighting game, combat arena, action adventure
  related-skills: environment-artist, prop-artist, camera-cinematography, vfx-fx
---

# Genre: Action / Combat

Readable arenas. Attack silhouettes. Breakables clear. Camera-friendly volumes.

## Recipe

Readable combat arena: 16-24 m diameter flat floor, 3 m clear sword/combo radius, dramatic but even lighting at about 3:1 key to fill, 35 mm action camera.

1. Light the arena with `light_rig.py` preset `golden_hour` (strong directional key reads attack silhouettes).
2. Frame a combat camera with `camera_rig.py`: `lens_mm` 35, `elevation_deg` 20, `fill` 0.5, `aspect` 16:9.
3. Scatter breakable props (boxes, barrels) around the arena edge with `scatter_props.py`, `min_dist` 2.5 so the center stays clear.
4. Give breakables a high-contrast material with `pbr_material.py` (`base_color` warm, `roughness` 0.7) so they read apart from the floor.
5. Add punch with `comp_grade.py` preset `cinematic`.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Combat", "target": target, "lens_mm": 35, "elevation_deg": 20, "fill": 0.5, "aspect": "16:9"}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 8, "kinds": ["box", "barrel"], "min_dist": 2.5}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Breakable", "base_color": [0.55, 0.3, 0.12], "roughness": 0.7, "objects": [target]}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Arena diameter | 16-24 m |
| Clear combo radius | 3 m |
| Dodge/roll lane | 2 m wide |
| Breakable height | 0.6-1.2 m |
| Ceiling / camera clearance | 6 m+ |
