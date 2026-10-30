---
name: mascot-puppet-horror
description: "Mascot and puppet horror: cheerful characters gone wrong, felt and foam. Use for creepy costumes or felt puppets."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials"
  triggers: mascot horror, puppet horror, felt horror, costume horror, Happy Tree wrongness, puppet combo adjacent
  related-skills: horror-style, stop-motion-craft-style, character-artist, psx-horror-style, materials
---

# Mascot / Puppet Horror

Cute brand language corrupted. Felt, foam, plastic eyes. Performance uncanny.

## Tenets
1. Friendly shapes + dead/wrong eyes
2. Craft materials (felt, plush, plastic)
3. Stage/set like children’s show gone wrong
4. Bright palette with one sick shift
5. Often pairs with PSX or analog crunch

## Recipe

Target: a bright children's-show palette with one sick shift: saturated felt body (roughness 1.0, Sheen on), 50 mm camera at puppet eye level, even studio light, grade shifted toward green-cold (`warmth` -0.4).

1. `pbr_material` MAT_Felt: saturated `base_color` [0.8, 0.1, 0.12], `roughness` 1.0, `specular_ior_level` 0.2. Add fuzz by hand with Principled `Sheen Weight` 1.0, `Sheen Roughness` 0.5.
2. Eyes: a second plastic material the same way (`base_color` white, `roughness` 0.1, `coat_weight` 1.0) with tiny dark pupils; keep the eyes slightly off-axis.
3. `light_rig` `studio_3pt` (a cheerful, flat TV-set key).
4. `camera_rig` `lens_mm` 50, `elevation_deg` 0, `fill` 0.8, `dof_fstop` 4.
5. `comp_grade` `stylized_bloom` with `warmth` -0.4 and `vignette` 0.45 to push the sick shift; for the analog-tape variant use `horror_vhs` instead.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Felt", "base_color": [0.8, 0.1, 0.12], "roughness": 1.0, "specular_ior_level": 0.2, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "studio_3pt", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Puppet_01", "target": target, "lens_mm": 50, "elevation_deg": 0, "fill": 0.8, "dof_fstop": 4}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": -0.4, "vignette": 0.45}})["result"]
result = r
```
