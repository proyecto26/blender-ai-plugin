---
name: dream-surreal-mood
description: Dreamlike, surreal, mysterious, mystical, hopeful, and chaotic mood direction for Blender scenes.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: dreamlike, surreal, mysterious, mystical, hopeful, chaotic, uncanny mood
  related-skills: dream-weirdcore-style, lighting, vfx-fx, compositing, camera-cinematography
---

# Dream / Surreal Mood

Logic bent. Scale play. Soft physics. Symbolic props.

## Recipe

Target: soft physics and scale play: pastel emissive form, hazy golden-hour light, drifting mist, 85 mm shallow DOF (f/1.8) with strong bloom.

1. `pbr_material` MAT_Dream: pastel `base_color` [0.75, 0.7, 0.95], `roughness` 0.3, `emission_color` [0.6, 0.5, 0.9], `emission_strength` 0.6.
2. Scale play: scale the object non-uniformly or float it above a floor, then apply (`bpy.ops.object.transform_apply`); pair it with tiny or giant symbolic props instead of realistic proportions.
3. `light_rig` `golden_hour` for hazy dawn light; `smoke_domain` `flow_type` SMOKE, `resolution` 32, `padding` 2.0 for soft mist.
4. `camera_rig` `lens_mm` 85, `elevation_deg` 5, `dof_fstop` 1.8.
5. `comp_grade` `stylized_bloom` with `warmth` 0.2 and `vignette` 0.4.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Dream", "base_color": [0.75, 0.7, 0.95], "roughness": 0.3, "emission_color": [0.6, 0.5, 0.9], "emission_strength": 0.6, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["mist"] = runpy.run_path(f"{skills}/vfx-fx/scripts/smoke_domain.py", init_globals={"ARGS": {"emitter": target, "flow_type": "SMOKE", "resolution": 32, "padding": 2.0}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Dream_01", "target": target, "lens_mm": 85, "elevation_deg": 5, "dof_fstop": 1.8}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": 0.2, "vignette": 0.4}})["result"]
result = r
```
