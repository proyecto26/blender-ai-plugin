---
name: liminal-space-style
description: Liminal space and Backrooms art direction for Blender with empty transitional architecture, wrong familiarity, and endless repetition.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: liminal, liminal space, Backrooms, empty mall, empty school, poolrooms, transitional space
  related-skills: horror-style, environment-artist, lighting, materials, scene-assembly
---

# Liminal Space / Backrooms

Familiar architecture without people. Repetition. Wrong lighting. Endless continuation.

## Subplaces
Backrooms, empty mall, empty school, poolrooms, hotels, offices

## Tenets
1. Repetitive modular kits
2. Fluorescent hum lighting
3. Stained carpet / yellowed walls (variant-dependent)
4. No narrative clutter — emptiness is the story
5. Soft wrongness over jump scares

## Recipe

Target: an empty yellowed office/Backrooms hall: wallpaper base about [0.55, 0.5, 0.25], flat even overhead light, wide 24 mm camera at eye height (1.6 m), no clutter, one vanishing point.

1. Corridor with `blockout.py` `room`: 2.6 m wide, 2.7 m tall, 20+ m long, open ends, `fixtures` every 2.4 m (emissive 0.6 x 1.2 m panels plus matching area lights). Assign MAT_Wallpaper to the shell afterwards.
2. `pbr_material` MAT_Wallpaper: `base_color` [0.55, 0.5, 0.25], `roughness` 0.85 (stained carpet: [0.35, 0.3, 0.15], `roughness` 1.0).
3. Repetition is the unease: keep the corridor long (20+ m) and the fixture spacing exactly regular; for modular walls tile one 2.4 m module with an Array modifier (`count` 12).
4. `light_rig` `overcast` as flat fluorescent fill on top of the corridor's own fixture lights.
5. `camera_rig` `lens_mm` 24, `elevation_deg` 0, `fill` 0.6; centre the frame on the vanishing point.
6. `comp_grade` `clean` with `warmth` 0.1 and `vignette` 0.3 for a subtle, non-jarring grade.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["hall"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "Backrooms", "room": {"size": [2.6, 24.0, 2.7], "at": [40, -12], "color": [0.55, 0.5, 0.25], "fixtures": {"spacing": 2.4}}}})["result"]
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Wallpaper", "base_color": [0.55, 0.5, 0.25], "roughness": 0.85, "objects": ["BLK_Backrooms_room_01"]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Liminal_01", "target": "BLK_Backrooms_room_01", "lens_mm": 24, "elevation_deg": 0, "fill": 0.6}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "clean", "warmth": 0.1, "vignette": 0.3}})["result"]
result = r
```

Module scale numbers:

| Element | Size |
|---|---|
| Corridor width | 2.4 to 3.0 m |
| Ceiling height | 2.4 to 2.7 m |
| Ceiling tile | 0.6 x 0.6 m |
| Light panel spacing | 2.4 m |
| Door | 0.9 x 2.1 m |
| Camera height | 1.6 m |
