---
name: analog-found-footage-horror
description: "VHS, CRT and found-footage horror shots. Use for 'analog horror', security-cam or lost-media looks. Not PS1 crunch (psx-horror-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: mood
  stage: brief
  requires: "camera-cinematography, compositing, lighting, rendering"
  triggers: analog horror, found footage, VHS horror, CRT horror, tape horror, Mandel effect, lost media
  related-skills: horror-style, psx-horror-style, camera-cinematography, compositing, lighting
---

# Analog / Found Footage Horror

Documentary camera. Tape damage. Dead channels. Corporate/educational uncanny.

## Tenets
1. Handheld / locked security cam language
2. Timestamp / tracking UI optional (comp)
3. VHS blur, chroma bad, tracking lines
4. Mundane spaces made wrong
5. Less monster, more implication

## Recipe

Target: 4:3-feeling tape footage, ~480p, wide 24 mm lens at chest height, desaturated (about 60 % saturation), heavy vignette (0.5), practical-light-only scene.

1. Lower the render cost with `render_preset` `eevee_final` at `resolution_percentage` 50 (tape is soft; do not render clean 1080p).
2. `light_rig` `horror_practical` (one warm spot, one sickly green point) so the room is lit like a flashlight/camcorder scene.
3. `camera_rig` `lens_mm` 24, `elevation_deg` 0 to 5, `fill` 0.5, `dof_fstop` None for deep focus; use `aspect` `16:9` (or `1:1` for a security feed).
4. Handheld: add an F-Curve Noise modifier to the camera's `location` and `rotation_euler` curves (`fcurve.modifiers.new('NOISE')`, strength about 0.01 m / 0.01 rad, scale 6 frames). A locked security cam gets no noise.
5. `comp_grade` `horror_vhs` (bloom, desaturation, lens distortion, 2 px pixelation, vignette 0.5). Timestamp/REC overlays are a Text object or an image strip composited last.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final", "resolution_percentage": 50}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Tape_01", "target": target, "lens_mm": 24, "elevation_deg": 3, "fill": 0.5, "aspect": "16:9"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "horror_vhs", "vignette": 0.5}})["result"]
result = r
```
