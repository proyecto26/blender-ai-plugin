---
name: frutiger-aero-style
description: "Frutiger Aero art direction for Blender with glossy skeuomorphism, aqua UI cues, nature-tech optimism and mid-2000s futurism. Use when the user asks for 'Frutiger Aero', 'Windows Vista/2000s aqua' looks, glossy bubbles and glass with blue-sky nature (for dark synthwave looks use neon-retrofuturism)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: Frutiger Aero, aero, aqua UI, glossy 2000s, vista aesthetic, bubbly futurism
  related-skills: neon-retrofuturism, materials, lighting, environment-artist, lookdev
---

# Frutiger Aero

Glossy bubbles. Fresh greens/blues. Nature + tech optimism. Soft skeuomorphic forms.

## Recipe

Look: bright, airy, glossy. Sky-blue/aqua and fresh green palette (about 4 colours + white), high-key lighting, rounded bubble forms, glass with IOR about 1.45 and high gloss, soft bloom.

1. Light with `lighting/light_rig.py` preset `overcast` (bright soft sky, 1.2 world strength) or `studio_3pt` for product-style glossy shots.
2. Glossy aqua plastic/glass with `materials/pbr_material.py`: `base_color` `[0.1, 0.55, 0.8]`, `roughness` 0.05, `coat_weight` 1.0, `specular_ior_level` 0.8. Add a green variant `[0.3, 0.75, 0.25]` for the nature half.
3. For a more cartoon-bubbly variant, optionally use `stylized-style/toon_material.py` with `bands` 4 and `rim` 0.6 (EEVEE only).
4. Render with `rendering/render_preset.py` `eevee_final` (raytraced reflections matter for gloss), frame with `camera-cinematography/camera_rig.py` (`lens_mm` 50, `dof_fstop` 4).
5. Finish with `compositing/comp_grade.py` `stylized_bloom` with `warmth` -0.1 (cool, clean glow).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_AeroGloss", "base_color": [0.1, 0.55, 0.8], "roughness": 0.05, "coat_weight": 1.0, "specular_ior_level": 0.8, "objects": [target]}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 50, "dof_fstop": 4.0}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": -0.1}})["result"]
result = r
```
