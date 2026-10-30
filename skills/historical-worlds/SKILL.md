---
name: historical-worlds
description: "Historical settings: pirate, samurai, Viking, Victorian, WWII, ancient Rome. Use for period-accurate props and architecture."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "camera-cinematography, compositing, lighting, materials, set-dressing"
  triggers: western, pirate, samurai, ninja, Viking, ancient Egypt, ancient Greece, Roman, Victorian, modern, military, Cold War, World War
  related-skills: environment-artist, prop-artist, character-artist, materials, set-dressing
---

# Historical Worlds

Period-accurate silhouettes and materials. Document era before kitbashing.

## Groups
Western · Pirate · Samurai/Ninja · Viking · Ancient (Egypt/Greece/Rome) · Victorian · Modern · Military/WW/Cold War

## Recipe

Look: period-accurate materials under era-appropriate light (candle/oil/torch before 1880, no emissive plastics or glossy synthetics). Pick the era first, then: wood, hemp, iron (roughness 0.6-0.8), stone, leather; palette of 5-6 earth tones.

1. Light with `lighting/light_rig.py`: `golden_hour` (Western, Ancient, Samurai), `overcast` (Viking, Victorian), `moonlight` (pirate night, ninja; the warm point light acts as lantern).
2. Materials via `materials/pbr_material.py`: aged iron `[0.2, 0.2, 0.21]` `metallic` 1 `roughness` 0.6; planked wood `[0.3, 0.18, 0.09]` `roughness` 0.75; sandstone `[0.6, 0.5, 0.35]` `roughness` 0.9.
3. Dress with `set-dressing/scatter_props.py` (barrels, crates, boxes = cargo, saloon stock, dock clutter).
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 35, `aspect` "2.39:1" for Western/epic), grade with `compositing/comp_grade.py` `cinematic` (`warmth` 0.4 for Western dust), `noir` for Victorian/Cold War mood.

| Item | Scale |
|---|---|
| Door | 1.9-2.0 m (pre-1800), 2.1 m (modern) |
| Ship deck height | 2.0 m between decks |
| Saloon bar | 1.1 m high |
| Katana | about 1.0 m total |

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_PlankWood", "base_color": [0.3, 0.18, 0.09], "roughness": 0.75, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 8, "kinds": ["box", "barrel"]}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 35, "aspect": "2.39:1"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "warmth": 0.4}})["result"]
result = r
```
