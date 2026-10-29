---
name: chibi-style
description: "Chibi and SD (super-deformed) proportion art direction for Blender characters with oversized heads, simplified anatomy and cute silhouette rules. Use when the user asks for 'chibi', 'cute big-head proportions' or a super-deformed version of a character."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: chibi, SD, super deformed, cute proportions, chibi character
  related-skills: anime-style, cartoon-style, character-artist, stylized-style
---

# Chibi Style

Big head. Short body. Maximum appeal silhouette.

## Ratios
Head often 1/2 to 1/3 of total height. Simplify fingers. Large eyes optional by genre.

## Recipe

Target a cute 1:2 to 1:3 head-to-body character, 2-band soft toon shading with a thin outline, framed close on a square or portrait crop.

1. Proportions are modeled, not scripted: head 1/2 to 1/3 of total height, short limbs, simplified hands.
2. Shading: `toon_material.py` with `bands` 2, `rim` 0.3, `outline` 0.012 (thinner outline keeps small features readable).
3. Lighting: `light_rig.py` preset `overcast` for soft, shadow-light appeal.
4. Camera: `camera_rig.py` `lens_mm` 85, `elevation_deg` 5, `fill` 0.85, `aspect` "1:1" (flattering, low distortion).
5. Render and finish: `render_preset.py` `stylized_flat`, then `comp_grade.py` `stylized_bloom`.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Chibi", "base_color": [1.0, 0.7, 0.75], "bands": 2, "rim": 0.3, "objects": [target], "outline": 0.012}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Style", "target": target, "lens_mm": 85, "elevation_deg": 5, "fill": 0.85, "aspect": "1:1"}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom"}})["result"]
result = r
```
