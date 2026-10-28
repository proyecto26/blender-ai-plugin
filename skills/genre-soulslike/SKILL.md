---
name: genre-soulslike
description: Art direction for soulslike games in Blender with monumental melancholy spaces, fog gates, bonfire landmarks, and lethal readability.
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

1. Light with `light_rig.py` preset `moonlight` (cold low-key); a rig replaces its own previous lights, so add the warm bonfire as a separate point light by hand.
2. Add fog gate / bonfire smoke with `smoke_domain.py` (`emitter` target, `flow_type` SMOKE, `resolution` 48).
3. Dress ruins with debris via `scatter_props.py` (`count` 12, `clusters` 4, `max_dist` 8).
4. Wide dramatic camera with `camera_rig.py`: `lens_mm` 24, `elevation_deg` 5.
5. Grade with `comp_grade.py` preset `noir`, `vignette` 0.5.

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
