---
name: cosmic-eldritch-horror
description: "Lovecraftian cosmic horror: impossible scale, non-Euclidean forms. Use for 'eldritch', void entities, wrong vast architecture."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials, vfx-fx"
  triggers: cosmic horror, eldritch, Lovecraftian, Lovecraft, non-Euclidean, unknowable, void horror
  related-skills: horror-style, creature-artist, lighting, vfx-fx, compositing
---

# Cosmic / Eldritch Horror

Incomprehensible scale. Wrong geometry. Void pressure.

## Tenets
1. Scale mismatch (tiny human vs vast form)
2. Suggestive detail — never fully explain the monster
3. Non-Euclidean architecture cues
4. Color: abyssal blues, sickly golds, void blacks
5. Sound-design-friendly spaces (long falls, vast chambers)

## Recipe

Target: an abyssal scene, world near black, one cold moon key plus a faint sickly-gold emissive glow on the form, wide 24 mm low camera so the form looms; mist volume adds void pressure.

1. `pbr_material` MAT_Void: near-black `base_color` [0.02, 0.025, 0.04], `roughness` 0.2, `emission_color` [0.8, 0.6, 0.1] with `emission_strength` 0.4 (sickly gold seams).
2. `light_rig` `moonlight` (cold sun 0.4 W/m2, warm point 60 W) with world strength 0.5.
3. `smoke_domain` `flow_type` SMOKE, `resolution` 32, `padding` 3.0, `height` 6.0 for drifting mist; the bake is not started, ask before baking.
4. `camera_rig` `lens_mm` 24, `elevation_deg` 5, `fill` 0.3 (target looks huge only if the camera is close; keep the figure/foreground tiny).
5. `comp_grade` `cinematic` with `warmth` -0.5 and `vignette` 0.6 for abyssal blue and crushed edges.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Void", "base_color": [0.02, 0.025, 0.04], "roughness": 0.2, "emission_color": [0.8, 0.6, 0.1], "emission_strength": 0.4, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "moonlight", "target": target}})["result"]
r["mist"] = runpy.run_path(f"{skills}/vfx-fx/scripts/smoke_domain.py", init_globals={"ARGS": {"emitter": target, "flow_type": "SMOKE", "resolution": 32, "padding": 3.0, "height": 6.0}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Abyss_01", "target": target, "lens_mm": 24, "elevation_deg": 5, "fill": 0.3}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": -0.5, "vignette": 0.6}})["result"]
result = r
```
