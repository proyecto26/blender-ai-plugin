---
name: genre-shooter
description: Art direction for FPS, TPS, shooter, battle royale, and extraction-shooter maps and props in Blender with sightline and cover language.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: shooter, FPS, TPS, battle royale, extraction shooter, cover shooter, gun game art
  related-skills: environment-artist, hard-surface, prop-artist, collision-proxy, scene-assembly
---

# Genre: Shooter

Sightlines. Cover. Landmarking. Loot readability. Scale for camera height (FPS vs TPS).

## Recipe

Sightline-driven map: cover at 1.0-1.2 m (crouch) and 1.8 m (full), lanes 4-8 m wide, FPS eye 1.6 m, collision on all cover.

1. Blockout cover first with `blockout.py`: waist-high boxes (1.0-1.2 m, chest-high 1.4 m) in a ring or lines with 3+ m gaps, `face_center` so the long side faces the fight.
2. Collision for cover with `make_collision.py` (`shape` box, `engine` unreal).
3. Bevel cover edges with `bevel_stack.py` (`width` 0.01, `segments` 1) so edges catch light.
4. Scatter low cover props with `scatter_props.py` (`count` 10, `kinds` [box, barrel, pallet]).
5. Light with `light_rig.py` preset `overcast` for fair, readable visibility.
6. Eye-level camera with `camera_rig.py`: `lens_mm` 24, `elevation_deg` 0 (FPS-like view).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["cover"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "Cover", "pieces": [{"kind": "box", "size": [1.8, 0.6, 1.1], "name": "COVER"}], "layout": {"pattern": "ring", "count": 6, "radius": 4.0, "center": target, "face_center": True}, "bevel": 0.02}})["result"]
r["bevel"] = runpy.run_path(f"{skills}/hard-surface/scripts/bevel_stack.py", init_globals={"ARGS": {"objects": [target], "width": 0.01, "segments": 1}})["result"]
r["col"] = runpy.run_path(f"{skills}/collision-proxy/scripts/make_collision.py", init_globals={"ARGS": {"objects": [target], "shape": "box", "engine": "unreal"}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 10, "kinds": ["box", "barrel", "pallet"]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_FPS", "target": target, "lens_mm": 24, "elevation_deg": 0}})["result"]
result = r
```

| Item | Value |
|---|---|
| FPS eye height | 1.6 m (crouch 1.0 m) |
| Low cover | 1.0-1.2 m |
| High cover | 1.8-2.2 m |
| Lane width | 4-8 m |
| Doorway | 1.1 x 2.2 m |
| Corridor | 2.5-3 m |
