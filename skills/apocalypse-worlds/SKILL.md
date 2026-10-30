---
name: apocalypse-worlds
description: "Apocalypse and dystopia settings. Use for wasteland, ruined city, zombie outbreak or a dystopia vs utopia pair."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials, set-dressing"
  triggers: post-apocalyptic, post-apoc, zombie apocalypse, alien invasion, dystopian, utopian, post-human, wasteland
  related-skills: environment-artist, prop-artist, materials, set-dressing, vehicle-artist
---

# Apocalypse / Dystopia Worlds

Collapse language: scavenged materials, faded brands, improvised repairs.

## Lanes
Post-apoc wasteland · Zombie cities · Alien invasion damage · Dystopian control · Utopian veneer · Post-human ruins

## Recipe

Target look: desaturated, overcast, grimy. Key light 1.5 strength sun under a flat grey sky, 35 mm environment lens, 2.39:1, roughness 0.7-0.9 everywhere, one warm accent (rust/orange) against a grey-green base.

1. Light with `lighting/light_rig.py` preset `overcast` (flat, no hard shadows); switch to `golden_hour` for a dusty wasteland sunset, `moonlight` for night survival.
2. Material the hero with `materials/pbr_material.py`: rust base `[0.22, 0.09, 0.04]`, `metallic` 0.6, `roughness` 0.85 (faded paint: `[0.35, 0.37, 0.3]`, `metallic` 0, `roughness` 0.8).
3. Dress the scene with `set-dressing/scripts/scatter_props.py` (`kinds` box/barrel/pallet, 2-3 clusters) so debris tells a story: abandoned supply drop, barricade, scavenged pile.
4. Optional smoke from a burning barrel with `vfx-fx/smoke_domain.py` (`flow_type` BOTH); the bake is not started, ask first.
5. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35, `aspect` "2.39:1"), then grade with `compositing/comp_grade.py` preset `cinematic`, `warmth` -0.2 (cold, bleached), `vignette` 0.5.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_RustedMetal", "base_color": [0.22, 0.09, 0.04], "metallic": 0.6, "roughness": 0.85, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 8, "kinds": ["box", "barrel", "pallet"], "clusters": 3}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "aspect": "2.39:1"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": -0.2, "vignette": 0.5}})["result"]
result = r
```
