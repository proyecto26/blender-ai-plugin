---
name: genre-stealth
description: Art direction for stealth-game spaces in Blender with shadow volumes, patrol-friendly layouts, and concealment materials.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: stealth, stealth game, shadow play, infiltration, stealth level art
  related-skills: environment-artist, lighting, materials, scene-assembly
---

# Genre: Stealth

Shadows are gameplay. Noise materials. Vertical infiltration routes.

## Recipe

Shadows are gameplay: lit pools vs dark zones at 1:8 or higher ratio, 2-3 m vertical routes, cover at 1.2 m.

1. Dark base with `light_rig.py` preset `horror_practical` (small pools of light in darkness = guard-visible zones; a rig replaces its own previous lights, so use one preset).
2. Concealment materials with `pbr_material.py` (dark `base_color` [0.03, 0.03, 0.04], `roughness` 0.9) on hiding spots; noisy floors with `roughness` 0.4.
3. Dress with `scatter_props.py` (`count` 8) for cover.
4. Camera `camera_rig.py`: `lens_mm` 35, `elevation_deg` 40. Grade `comp_grade.py` preset `noir`.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["pools"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["hide"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Concealment", "base_color": [0.03, 0.03, 0.04], "roughness": 0.9, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 8}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Stealth", "target": target, "lens_mm": 35, "elevation_deg": 40}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "noir"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Cover height | 1.2 m (crouch) |
| Vent / crawl | 0.6-0.8 m |
| Ledge to grab | 2.5-3 m |
| Guard sight cone | 10-15 m, 90 deg |
| Lit pool radius | 2-4 m |
