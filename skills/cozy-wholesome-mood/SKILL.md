---
name: cozy-wholesome-mood
description: "Cozy wholesome mood. Use for hygge warm lighting, a calm game room, or a scene that feels cold and should comfort."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  requires: "camera-cinematography, compositing, hard-surface, lighting, rendering, set-dressing, stylized-style"
  triggers: cozy, cute, wholesome, relaxing, peaceful, hygge, warm lighting cozy
  related-skills: stylized-style, lighting, set-dressing, materials, camera-cinematography
---

# Cozy / Wholesome Mood

Warm light. Soft shapes. Safe clutter. Low threat.

## Tenets
1. Warm keys / soft fill
2. Rounded prop language
3. Clutter = comfort, not hazard
4. Gentle palettes
5. Cameras at friendly eye height

## Recipe

Target: warm key (golden-hour, about 2:1 key to fill), soft 3-band toon shading, rounded props, friendly 50 mm camera near eye height (about 1.2 m seated, 10 degrees up).

1. `render_preset` `eevee_final` for soft real-time GI.
2. `toon_material` MAT_Toon_Cozy: warm `base_color` [0.95, 0.72, 0.5], `bands` 3, `rim` 0.2, `outline` 0 (outlines read hostile in cozy scenes).
3. `bevel_stack` `width` 0.03, `segments` 4 for pillowy, rounded edges.
4. `light_rig` `golden_hour`; `scatter_props` `kinds` `box_small`/`barrel` with `count` 6 in 2 clusters for safe clutter.
5. `camera_rig` `lens_mm` 50, `elevation_deg` 10, `dof_fstop` 2.8; `comp_grade` `stylized_bloom` with `warmth` 0.3 for a gentle glow.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["material"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Cozy", "base_color": [0.95, 0.72, 0.5], "bands": 3, "rim": 0.2, "objects": [target], "outline": 0}})["result"]
r["bevel"] = runpy.run_path(f"{skills}/hard-surface/scripts/bevel_stack.py", init_globals={"ARGS": {"objects": [target], "width": 0.03, "segments": 4}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 6, "kinds": ["box_small", "barrel"], "clusters": 2}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Cozy_01", "target": target, "lens_mm": 50, "elevation_deg": 10, "dof_fstop": 2.8}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": 0.3}})["result"]
result = r
```
