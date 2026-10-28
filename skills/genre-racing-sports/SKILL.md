---
name: genre-racing-sports
description: Art direction for racing and sports games in Blender with track landmarks, stadium kits, and high-speed readability.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: racing, sports, track, stadium, race course, sports arena
  related-skills: vehicle-artist, environment-artist, materials, camera-cinematography
---

# Genre: Racing / Sports

Landmarks for speed. Track edge clarity. Stadium modular kits. Team color systems.

## Recipe

High-speed readability: track 10-14 m wide, bold edge markings, landmarks every 150-300 m, team colors as flat saturated materials, low chase camera at 28 mm.

1. Set lighting with `light_rig.py` preset `golden_hour`.
2. Make team/kerb colors with `pbr_material.py` (`roughness` 0.4, saturated `base_color`, `coat_weight` 0.5).
3. Add track barriers or guard rails with `gn_curve_profile.py` (`name` GEO_Barrier, `radius` 0.15).
4. Chase camera with `camera_rig.py`: `lens_mm` 28, `elevation_deg` 10, `aspect` 16:9.
5. Stylise speed look with `comp_grade.py` preset `cinematic`, `warmth` 0.2.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["team"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_TeamRed", "base_color": [0.8, 0.03, 0.03], "roughness": 0.4, "coat_weight": 0.5, "objects": [target]}})["result"]
r["barrier"] = runpy.run_path(f"{skills}/procedural-modeling/scripts/gn_curve_profile.py", init_globals={"ARGS": {"name": "GEO_Barrier", "points": [[-6, -20, 0.5], [-6, 0, 0.5], [-3, 20, 0.5]], "radius": 0.15}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Chase", "target": target, "lens_mm": 28, "elevation_deg": 10, "aspect": "16:9"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": 0.2}})["result"]
result = r
```

| Item | Value |
|---|---|
| Track width | 10-14 m |
| Kerb width | 0.5-1 m |
| Car length | 4.5 m |
| Football pitch | 105 x 68 m |
| Basketball court | 28 x 15 m |
| Stadium seat row | 0.8 m deep |
