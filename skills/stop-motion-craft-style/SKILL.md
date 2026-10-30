---
name: stop-motion-craft-style
description: "Stop-motion/craft look: claymation, papercraft, felt. Use for fingerprints in clay or cardboard."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  triggers: stop motion, claymation, clay, paper craft, papercraft, handmade, craft aesthetic, puppet physical
  related-skills: materials, lighting, camera-cinematography, character-artist, mascot-puppet-horror
---

# Stop Motion / Craft Style

Handmade physicality. Imperfect edges. Material honesty.

## Sublooks
Claymation, paper craft, felt/plush, wooden puppet

## Tenets
1. Visible craft seams / fingerprints (subtle)
2. Real-world craft materials
3. Slight irregularity in forms
4. Practical light feel
5. Step-like motion if animating (optional)

## Recipe

Look: tabletop miniature. Practical-feeling soft key (one dominant light, small fill), shallow DoF (f/2.8, 85 mm so the subject reads as small), matte materials (roughness 0.7-0.95), no perfect edges; 12 fps feel is done in animation, not here.

1. Light with `lighting/light_rig.py` preset `studio_3pt` (warm key like a desk lamp) and render with `rendering/render_preset.py` `eevee_final`.
2. Clay/felt/paper material with `materials/pbr_material.py`: clay `[0.8, 0.35, 0.25]` `roughness` 0.85, `specular_ior_level` 0.2; paper `[0.9, 0.88, 0.82]` `roughness` 0.95. Add fingerprints/fibres by a noise bump in prose (Noise Texture to Bump, strength 0.15).
3. Soft handmade shading: `stylized-style/toon_material.py` with `bands` 4, `rim` 0.1, `outline` 0 for gentle stepped light.
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 85, `dof_fstop` 2.8, `fill` 0.6), grade with `compositing/comp_grade.py` `cinematic` (`warmth` 0.3).
5. If animating, key every 2 frames on 24 fps (stepped interpolation, constant) for the stop-motion stutter.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "studio_3pt", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Clay", "base_color": [0.8, 0.35, 0.25], "roughness": 0.85, "specular_ior_level": 0.2, "objects": [target]}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 85, "dof_fstop": 2.8, "fill": 0.6}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": 0.3}})["result"]
result = r
```
