---
name: genre-card-party-idle
description: "Card, party, idle and rhythm game staging. Use for a card table, idle scene or party stage with UI room."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: genre
  stage: brief
  triggers: card game, deck builder, party game, idle, incremental, educational, rhythm game, UI stage
  related-skills: prop-artist, camera-cinematography, materials, lookdev, minimalist-style
---

# Genre: Card / Party / Idle / Rhythm / Edu

Table clarity. Readable icons in 3D. Stages for UI. Low distraction backgrounds.

## Recipe

Clean table stage for UI: neutral low-contrast backdrop, soft shadowless lighting, top-down-ish camera at 50 mm, 16:9 or 9:16 for mobile.

1. Set a flat, cheap render with `render_preset.py` preset `stylized_flat`.
2. Light with `light_rig.py` preset `overcast` (soft, no hard shadows behind cards/icons).
3. Frame the table with `camera_rig.py`: `lens_mm` 50, `elevation_deg` 60, `fill` 0.8, `aspect` "9:16" for mobile (or "16:9").
4. Give the table/props a matte neutral material with `pbr_material.py` (`roughness` 0.9, mid-grey `base_color`) so icons carry the color.
5. Optional icon pop with `comp_grade.py` preset `stylized_bloom`.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Table", "target": target, "lens_mm": 50, "elevation_deg": 60, "fill": 0.8, "aspect": "9:16"}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Table", "base_color": [0.25, 0.27, 0.3], "roughness": 0.9, "objects": [target]}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom"}})["result"]
result = r
```

| Item | Value |
|---|---|
| Poker-size card | 0.063 x 0.088 m |
| Card thickness | 0.3 mm |
| Table play area | 0.9 x 0.9 m |
| Safe UI margin | 10 % of frame |
