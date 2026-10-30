---
name: genre-puzzle-platformer
description: "Puzzle and platformer levels. Use when players cannot tell what is climbable, jumpable or dangerous."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: genre
  stage: brief
  requires: "camera-cinematography, collision-proxy, environment-artist, lighting, materials, procedural-modeling"
  triggers: puzzle, platformer, jump puzzle, puzzle game art, platforming
  related-skills: environment-artist, prop-artist, materials, camera-cinematography
---

# Genre: Puzzle / Platformer

Interactables pop. Hazards unique color/shape. Jump distances honest in mesh.

## Recipe

Honest jump geometry: platforms on a 1 m grid, gaps 2-4 m, interactables in a saturated accent color against desaturated level, side camera at 50 mm.

1. Block out platforms with `blockout.py`: `box` platforms, `ramp` and `stairs` pieces on a 1 m grid (jump height about 1.2 m, gap about 2-3 m) before materials.
2. Give the level a neutral matte material via `pbr_material.py` (`roughness` 0.8, low-saturation `base_color`).
3. Mark interactables with emissive `pbr_material.py` (`emission_color` [0.1, 0.9, 0.3], `emission_strength` 2) and hazards with a unique red material.
4. Build rails/pipes for contraptions with `gn_curve_profile.py` (`name` GEO_Rail, `radius` 0.05).
5. Light flat with `light_rig.py` preset `studio_3pt`.
6. Side camera with `camera_rig.py`: `lens_mm` 50, `elevation_deg` 0, `aspect` 16:9. Collision with `make_collision.py` (`shape` box).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["platforms"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "Platforms", "pieces": [{"kind": "box", "size": [3.0, 3.0, 0.5], "at": [8, 0]}, {"kind": "box", "size": [3.0, 3.0, 1.2], "at": [11, 0]}, {"kind": "ramp", "size": [2.0, 3.0, 1.2], "at": [14, 0]}, {"kind": "stairs", "size": [1.5, 3.0, 1.44], "at": [17, 0]}]}})["result"]
r["base"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Level", "base_color": [0.3, 0.32, 0.34], "roughness": 0.8, "objects": [target]}})["result"]
r["hazard"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Hazard", "base_color": [0.8, 0.05, 0.05], "emission_color": [1.0, 0.1, 0.1], "emission_strength": 1.0}})["result"]
r["rail"] = runpy.run_path(f"{skills}/procedural-modeling/scripts/gn_curve_profile.py", init_globals={"ARGS": {"name": "GEO_Rail", "points": [[0, -3, 1], [0, 3, 1]], "radius": 0.05}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "studio_3pt", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Side", "target": target, "lens_mm": 50, "elevation_deg": 0, "aspect": "16:9"}})["result"]
r["col"] = runpy.run_path(f"{skills}/collision-proxy/scripts/make_collision.py", init_globals={"ARGS": {"objects": [target], "shape": "box", "engine": "godot"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Character height | 1.8 m |
| Max jump height | 1.5-2 m |
| Max jump gap | 3-4 m (design at 75 %) |
| Platform min width | 1 m |
| Hazard clearance | 0.5 m |
