---
name: indie-horror-aesthetics
description: "Indie horror lanes: abandoned hospital, cabin, corporate horror, Puppet Combo. Use to pick a horror reference. Not generic scary (horror-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "camera-cinematography, compositing, lighting, lowpoly-style, materials"
  triggers: Silent Hill, Fear to Fathom, Puppet Combo, indie horror, corporate horror, cabin horror, hospital horror, forest horror, urban decay horror
  related-skills: horror-style, psx-horror-style, liminal-space-style, environment-artist, lighting
---

# Indie Horror Aesthetics

Reference-driven indie horror looks. Pick a lane; don’t mash all at once.

## Load subtype refs
Silent Hill fog/rust; Fear to Fathom domestic analog; Puppet Combo PSX crunch; corporate/empty office; cabin/forest; hospital; urban decay.

## Recipe

Pick one lane. This recipe is the Silent Hill / Puppet Combo lane: 320x240 PSX frame, vertex snap 0.02 m, grey-white fog, one flashlight-style spot. Fear to Fathom (domestic analog) swaps `ps1_look` for `comp_grade` `horror_vhs` at a normal resolution; corporate/office swaps in `overcast` plus yellowed `pbr_material`; cabin/forest uses `moonlight`.

1. `ps1_look` `resolution` [320, 240], `snap` 0.02, `flat` False, `fog` [0.55, 0.56, 0.58] (Silent Hill grey; use [0.05, 0.06, 0.08] for black-fog forest).
2. `pbr_material` MAT_Rust: `base_color` [0.3, 0.12, 0.06], `metallic` 0.5, `roughness` 0.8 for rusted, corroded surfaces.
3. `light_rig` `horror_practical` (warm spot, green point).
4. `camera_rig` `lens_mm` 28, `elevation_deg` 5, `fill` 0.5.
5. `comp_grade` `horror_vhs` with `vignette` 0.4 for the crunch.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["look"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0.02, "resolution": [320, 240], "fog": [0.55, 0.56, 0.58]}})["result"]
r["material"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_Rust", "base_color": [0.3, 0.12, 0.06], "metallic": 0.5, "roughness": 0.8, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "horror_practical", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Indie_01", "target": target, "lens_mm": 28, "elevation_deg": 5, "fill": 0.5}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "horror_vhs", "vignette": 0.4}})["result"]
result = r
```

Scale reference for first-person indie horror:

| Element | Size |
|---|---|
| Door | 0.9 x 2.1 m |
| Hallway width | 1.2 to 1.6 m |
| Ceiling height | 2.4 to 2.7 m |
| Eye height | 1.6 m |
| Flashlight range | 8 to 12 m |
