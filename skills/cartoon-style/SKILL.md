---
name: cartoon-style
description: Cartoon art direction for Blender with squash-stretch readable shapes, bold colors, and graphic silhouettes for games and animation.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: cartoon, toon, rubber hose, Saturday morning, bold cartoon, graphic cartoon
  related-skills: stylized-style, anime-style, materials, rendering, character-artist
---

# Cartoon Style

Bold shapes. Graphic color. Readability over realism.

## When to Use
- Cartoon games / animated props and characters
- Exaggerated silhouettes and expressions
- When anime cel language is too specific

## Tenets
1. Silhouette first
2. Exaggerated proportions
3. Limited palette, bold accents
4. Soft or graphic shading (project choice)
5. Detail in shapes, not micro-PBR

## Handoff
`character-artist` / `prop-artist` → `materials` → `lookdev`

## Reference Guide
| Topic | Reference |
|-------|-----------|
| Shape language | `references/cartoon-shape-language.md` |

## Recipe

Target a 1080p readable toon look: 3 light bands, saturated 4-6 color palette, one 2 cm black outline, soft studio light with a gentle bloom.

1. Cel material: `toon_material.py` with `bands` 3, `rim` 0.2 and `outline` 0.02 (inverted hull, EEVEE only).
2. Lighting: `light_rig.py` preset `studio_3pt` (readable key/fill/rim).
3. Render: `render_preset.py` `stylized_flat` (EEVEE, Standard view transform). Run it after the light rig, which sets an AgX look.
4. Finish: `comp_grade.py` preset `stylized_bloom` for slight saturation lift and glow.
5. Keep shape exaggeration (squash/stretch, oversized hands and feet) in the modeling, not in shaders.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Toon_Cartoon", "base_color": [0.95, 0.45, 0.2], "bands": 3, "rim": 0.2, "objects": [target], "outline": 0.02}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "studio_3pt", "target": target}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom"}})["result"]
result = r
```
