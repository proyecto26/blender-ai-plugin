---
name: genre-soulslike
description: "Art direction for soulslike games in Blender with monumental melancholy spaces, fog gates, bonfire landmarks and lethal readability. Use when the user asks for 'Dark Souls/Elden Ring-like' areas, fog-gate boss approaches, bonfire checkpoints or vast ruined spaces."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: soulslike, souls like, bonfire, fog gate, monumental ruins, difficult action RPG art
  related-skills: dark-gritty-mood, fantasy-worlds, environment-artist, lighting, set-dressing
---

# Genre: Soulslike

Monumental ruins. Melancholy grandeur. Fog gates. Landmark shortcuts. Enemy silhouettes lethal-clear.

## Recipe

Monumental melancholy: structures 3-5x human scale, desaturated palette with one warm bonfire light, heavy fog, low-key 5:1 contrast.

1. Light with `light_rig.py` preset `moonlight` (cold low-key); a rig replaces its own previous lights, so build the bonfire last (step 6).
2. Add fog gate / bonfire smoke with `smoke_domain.py` (`emitter` target, `flow_type` SMOKE, `resolution` 48).
3. Dress ruins with debris via `scatter_props.py` (`count` 12, `clusters` 4, `max_dist` 8).
4. Wide dramatic camera with `camera_rig.py`: `lens_mm` 24, `elevation_deg` 5.
5. Grade with `comp_grade.py` preset `noir`, `vignette` 0.5.
6. Bonfire / checkpoint with `blockout.py`: a ring of 9 `rock` pieces (0.35 m), a sword `box` (0.08 x 0.02 x 1.1 m) and a warm `light` piece with `flicker` True (Noise F-modifier on energy); run it after `light_rig` so the rig does not remove it. Move `at` / `center` next to your target.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["moon"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "moonlight", "target": target}})["result"]
r["smoke"] = runpy.run_path(f"{skills}/vfx-fx/scripts/smoke_domain.py", init_globals={"ARGS": {"emitter": target, "flow_type": "SMOKE", "resolution": 48}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 12, "clusters": 4, "max_dist": 8}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Ruins", "target": target, "lens_mm": 24, "elevation_deg": 5}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "noir", "vignette": 0.5}})["result"]
r["bonfire_stones"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "BonfireStones", "pieces": [{"kind": "rock", "size": [0.35, 0.3, 0.22], "color": [0.3, 0.3, 0.32]}], "layout": {"pattern": "ring", "count": 9, "radius": 0.6, "center": [3.0, 0.0]}}})["result"]
r["bonfire"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "Bonfire", "pieces": [{"kind": "box", "size": [0.08, 0.02, 1.1], "at": [3.0, 0.0], "rot_z": 15, "name": "SM_Sword", "color": [0.6, 0.6, 0.65]}, {"kind": "cone", "size": [0.4, 0.4, 0.6], "at": [3.0, 0.0], "color": [1.0, 0.4, 0.1]}, {"kind": "light", "type": "POINT", "at": [3.0, 0.0, 0.6], "color": [1.0, 0.5, 0.2], "energy": 120, "flicker": True}]}})["result"]
result = r
```

| Item | Value |
|---|---|
| Hero height | 1.8 m |
| Boss arena | 30-40 m diameter |
| Fog gate | 3 x 4 m |
| Ruin archway | 8-15 m high |
| Bonfire clearing | 6 m radius |
| Enemy silhouette | 2-4 m, distinct shape |
