---
name: dark-gritty-mood
description: "Grim, rusty, abandoned mood. Use for 'grimy', 'bleak and lonely', or a too-clean scene needing wear and decay."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials, set-dressing"
  triggers: dark, grim, gritty, rusty, abandoned, decayed, industrial, lonely, melancholic, tense, eerie, creepy
  related-skills: horror-style, materials, lighting, set-dressing, environment-artist
---

# Dark / Gritty Mood

Wear as story. Low key lighting. Melancholy palettes. Industrial weight.

## Recipe

Target: low-key scene (world strength about 0.003, one practical key at 300 W), rusted metal with roughness 0.85, desaturated grade, 10 story props abandoned in 3 clusters.

1. `pbr_material` MAT_Rust: `base_color` [0.28, 0.11, 0.05], `metallic` 0.6, `roughness` 0.85. Break up the rust with a Noise texture into a ColorRamp mixing bare steel and rust by hand.
2. `light_rig` `horror_practical`; `moonlight` for a colder, lonelier variant.
3. `scatter_props` `count` 10, `kinds` box/barrel/pallet, `clusters` 3, fixed `seed`: abandoned cargo reads as story.
4. `camera_rig` `lens_mm` 35, `elevation_deg` 6, `fill` 0.6.
5. `comp_grade` `cinematic` with `warmth` -0.15 and `vignette` 0.5 (melancholy teal-grey), or `noir` for monochrome.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Rust", "base_color": [0.28, 0.11, 0.05], "metallic": 0.6, "roughness": 0.85, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 10, "kinds": ["box", "barrel", "pallet"], "clusters": 3, "seed": 7}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Grim_01", "target": target, "lens_mm": 35, "elevation_deg": 6, "fill": 0.6}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": -0.15, "vignette": 0.5}})["result"]
result = r
```
