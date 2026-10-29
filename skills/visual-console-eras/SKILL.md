---
name: visual-console-eras
description: "Visual era art direction for Blender covering PS1 through PS5 stylistic cues, retro arcade, DOS, CRT and VHS and film-grain presentation. Use when the user asks for a specific console generation look ('PS2-era graphics', 'make it look like a DOS game') or CRT/VHS/film-grain presentation without horror framing."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: PS1 style, PS2 style, PS3 style, PS4 style, PS5 style, retro arcade, DOS style, CRT style, VHS style, film grain
  related-skills: lowpoly-style, psx-horror-style, realistic-style, compositing, materials
---

# Visual Console / Media Eras

Match era constraints: polycount, texture filtering, lighting model, and post stack.

## Recipe

Match the era's constraints. PS1: 320x240, 32px textures, nearest filtering, vertex snap 0.02 m, under 1,000 tris per character, fog. PS2: 640x480, bilinear, 5-10k tris. VHS/CRT: 4:3 low-res plus noise and desaturation. Film grain: `cinematic`/`noir` grade.

1. PS1 (and PS1-like arcade): `lowpoly-style/ps1_look.py` with `objects` [target], `snap` 0.02, `resolution` [320, 240], `fog` True, `texture` True.
2. Reduce geometry to era budget with `lod-pipeline/generate_lods.py` (`ratios` [0.5, 0.25]) or `asset-optimization/optimize_mesh.py` (`limited_dissolve` 1.0, `triangulate` True).
3. Light with `lighting/light_rig.py` `overcast` (flat vertex-lit feel) and no raytracing: `rendering/render_preset.py` `stylized_flat`.
4. For VHS/CRT/film: `compositing/comp_grade.py` `horror_vhs` (VHS, CRT pixelation 2), `noir` (B&W film), `cinematic` (PS4/PS5 filmic).
5. PS3-PS5: use `rendering/render_preset.py` `eevee_final` instead of `stylized_flat` for full PBR and raytracing.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["ps1"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0.02, "resolution": [320, 240], "fog": True, "texture": True}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "stylized_flat"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "horror_vhs"}})["result"]
result = r
```
