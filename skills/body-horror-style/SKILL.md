---
name: body-horror-style
description: "Body horror: flesh wrongness, mutation, wet organic materials. Use for 'Cronenberg', fused or grotesque anatomy."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: body horror, mutation, flesh, visceral, grotesque anatomy, Cronenberg
  related-skills: horror-style, creature-artist, sculpting, materials, character-artist
---

# Body Horror

Flesh as wrong material. Fusion. Mutation. Uncomfortable sympathy.

## Tenets
1. Anatomy almost-right then broken
2. Material transitions: skin→meat→metal→plastic
3. Moist specular sparingly (not gore porn by default)
4. Human recognition remains (uncanny)
5. Coordinate with creature-artist / sculpting

## Recipe

Target: a hero mutation shot at 85 mm, shallow DOF (f/2.8), wet-looking flesh (Coat Weight about 0.6, roughness 0.35), cold-green rim against a near-black world.

1. `pbr_material` MAT_Flesh: pinkish-red `base_color`, `roughness` 0.45, `coat_weight` 0.6 for the moist sheen. For translucency set Principled `Subsurface Weight` 0.3 by hand (not exposed by the script).
2. Material transitions (skin to meat to metal to plastic): make a second material the same way (`metallic` 1.0, `roughness` 0.3) and blend the two in the shader with a Mix Shader driven by a noise or vertex-colour mask.
3. `light_rig` `horror_practical`: warm spot as key, green point as the sickly rim.
4. `camera_rig` `lens_mm` 85, `fill` 0.8, `dof_fstop` 2.8 so only one part of the mutation is sharp.
5. `comp_grade` `cinematic` with `warmth` -0.1 and `vignette` 0.45; keep saturation high so the flesh reads.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Flesh", "base_color": [0.55, 0.16, 0.14], "roughness": 0.45, "coat_weight": 0.6, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Flesh_01", "target": target, "lens_mm": 85, "fill": 0.8, "dof_fstop": 2.8}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": -0.1, "vignette": 0.45}})["result"]
result = r
```
