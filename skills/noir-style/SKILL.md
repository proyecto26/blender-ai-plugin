---
name: noir-style
description: Noir art direction for Blender with high-contrast lighting, wet streets, silhouettes, and monochrome or limited-color grading.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: noir, neo-noir, hardboiled, detective noir, high contrast black and white
  related-skills: camera-cinematography, lighting, compositing, materials, lookdev
---

# Noir Style

Shadows as design. Silhouettes. Wet ground mirrors. Limited color or mono.

## Tenets
1. Motivated hard keys / blinds / neon slash
2. Negative fill
3. Smoke/fog shafts
4. Costume readable in silhouette
5. Grade crushed but detailed shadows

## Recipe

Target 2.39:1, crushed blacks, one hard warm practical against cold moonlight, wet reflective ground, monochrome grade.

1. Lighting: `light_rig.py` preset `moonlight` (cold sun plus a warm point; world near-black).
2. Wet ground: `pbr_material.py` with `roughness` 0.08 and `coat_weight` 1.0 on the ground/target; keep the subject dark and matte (`roughness` 0.8).
3. Camera: `camera_rig.py` `lens_mm` 35, `elevation_deg` -4, `dof_fstop` 2.8, `aspect` "2.39:1" for a low, cinematic angle.
4. Render: `render_preset.py` `eevee_final` (screen-space raytracing gives the wet reflections).
5. Grade: `comp_grade.py` preset `noir` (saturation 0, bloom, slight lens distortion) with `vignette` 0.5. Add fog or a volume cube by hand for light shafts.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "moonlight", "target": target}})["result"]
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Wet_Asphalt", "base_color": [0.03, 0.03, 0.035], "roughness": 0.08, "coat_weight": 1.0, "objects": [target]}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 35, "elevation_deg": -4, "dof_fstop": 2.8, "aspect": "2.39:1"}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "noir", "vignette": 0.5}})["result"]
result = r
```
