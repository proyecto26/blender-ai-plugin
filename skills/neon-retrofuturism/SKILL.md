---
name: neon-retrofuturism
description: "Synthwave/vaporwave neon: grid horizons, chrome, dusk. Use for outrun or 80s sunset. Not glossy aqua (frutiger-aero-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  triggers: neon, vaporwave, synthwave, retrofuturistic, outrun, retrowave, neon nights
  related-skills: sci-fi-punk-worlds, lighting, materials, compositing, environment-artist
---

# Neon / Retrofuturism

Sunset gradients. Grid perspective. Chrome + neon. 80s future memory.

## Recipe

Look: dark base (world about 0.01-0.02), magenta `(1, 0.1, 0.6)` and cyan `(0.1, 0.6, 1)` rim lights at 400 W-equivalent, purple back light, glossy chrome/black surfaces, strong bloom, 16:9, 35 mm.

1. Apply `rendering/render_preset.py` `eevee_final` first (it resets the view transform), then light with `lighting/light_rig.py` preset `neon_night` (pink/cyan/purple area lights, AgX Punchy look).
2. Chrome/lacquer with `materials/pbr_material.py`: chrome `metallic` 1.0 `roughness` 0.1; neon tube `emission_color` `[1.0, 0.1, 0.6]` `emission_strength` 8; glossy black `coat_weight` 1.0.
3. Optional grid/synth shading: `stylized-style/toon_material.py` (`bands` 3, `rim` 0.8) for flat sunset-gradient objects.
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35, `elevation_deg` 5, low and wide for grid horizon).
5. Grade with `compositing/comp_grade.py` `stylized_bloom` (`warmth` -0.3 for cool glow; `vignette` 0.4).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_NeonChrome", "base_color": [0.8, 0.8, 0.9], "metallic": 1.0, "roughness": 0.1, "emission_color": [1.0, 0.1, 0.6], "emission_strength": 1.5, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "neon_night", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "elevation_deg": 5, "aspect": "16:9"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": -0.3, "vignette": 0.4}})["result"]
result = r
```
