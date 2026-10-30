---
name: sci-fi-punk-worlds
description: "Sci-fi and -punk settings: cyberpunk, steampunk, space station, solarpunk. Use for 'cyberpunk city' or 'steampunk workshop'."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "blender-mcp-workflow, camera-cinematography, compositing, lighting, materials"
  triggers: sci-fi, hard sci-fi, space, cyberpunk, steampunk, dieselpunk, atompunk, solarpunk, biopunk, clockpunk, retrofuturism
  related-skills: hard-surface, environment-artist, vehicle-artist, materials, vfx-fx, neon-retrofuturism
---

# Sci-Fi / Punk Worlds

Choose one punk/sci-fi lane. Don’t mix chrome cyber with brass steam unless intentional mashup.

## Lanes
Hard sci-fi · Space opera · Cyberpunk · Steampunk · Dieselpunk · Atompunk · Solarpunk · Biopunk · Clockpunk

## Recipe

Pick one lane, then fix its light and material rules. Cyberpunk: `neon_night`, wet dark surfaces (roughness 0.2). Hard sci-fi/space: `studio_3pt` with hard single key, no atmosphere. Steam/diesel/clock: `golden_hour` or `horror_practical` with brass/iron. Solarpunk/biopunk: `overcast`/`golden_hour` with green emissive accents.

1. Light with `lighting/light_rig.py`: `neon_night` (cyber), `studio_3pt` (hard sci-fi), `golden_hour` (steam, solarpunk), `horror_practical` (biopunk).
2. Materials via `materials/pbr_material.py`: brass `[0.7, 0.5, 0.2]` `metallic` 1 `roughness` 0.35; painted hull `[0.5, 0.52, 0.55]` `metallic` 0.8 `roughness` 0.4; panel glow `emission_color` `[0.1, 0.8, 1.0]` `emission_strength` 5.
3. Panels and bolts: `hard-surface/bevel_stack.py` for beveled edges on hero parts.
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35, `aspect` "2.39:1"), then `compositing/comp_grade.py` `stylized_bloom` (cyber/solar) or `cinematic` (steam/space).

| Item | Scale |
|---|---|
| Corridor | 2.5-3 m wide, 2.6 m high |
| Door | 1.2 x 2.2 m |
| Hatch / vent | 0.6-0.8 m |

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["prep"] = runpy.run_path(f"{skills}/blender-mcp-workflow/scripts/fix_asset.py", init_globals={"ARGS": {"objects": [target]}})["result"]  # apply scale, add box UVs if missing
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "neon_night", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_PaintedHull", "base_color": [0.5, 0.52, 0.55], "metallic": 0.8, "roughness": 0.4, "objects": [target]}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "aspect": "2.39:1"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom"}})["result"]
result = r
```
