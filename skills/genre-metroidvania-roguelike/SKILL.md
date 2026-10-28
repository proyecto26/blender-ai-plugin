---
name: genre-metroidvania-roguelike
description: Art direction for metroidvania, roguelike, and roguelite games in Blender with biome gates, room modules, and run-readable props.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: metroidvania, roguelike, roguelite, room modules, procedural rooms, ability gate
  related-skills: environment-artist, scene-assembly, materials, biome-worlds
---

# Genre: Metroidvania / Roguelike

Modular rooms. Ability gates. Biome mastery. Run-to-run readable modifiers.

## Recipe

Side-view modular rooms on a 1 m grid, 16x9 m screen-sized rooms, orthographic-feeling 85 mm camera, one distinct palette per biome.

1. Block out each room with `blockout.py`: a `room` shell (about 16 x 9 m, 6 m tall) plus `box` platforms at jump-height steps (1.0-1.5 m rises, 3-4 m gaps) and `stairs` between levels.
2. Build the room kit from `bevel_stack.py` on wall/floor modules (`width` 0.02, `segments` 1) so tiles snap and read crisp.
3. Dress each room with `scatter_props.py` (`count` 6, `clusters` 2) and tag ability-gate props with a unique emissive `pbr_material.py` (`emission_color` cyan, `emission_strength` 3).
4. Add one biome mood with `light_rig.py` (`moonlight` for caves, `horror_practical` for ruins).
5. Side camera with `camera_rig.py`: `azimuth_deg` 0, `elevation_deg` 0, `lens_mm` 85, `aspect` 16:9.
6. Check budget per room with `scene_audit.py` (`tri_budget` 20000).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["room"] = runpy.run_path(f"{skills}/environment-artist/scripts/blockout.py", init_globals={"ARGS": {"group": "Room01", "room": {"size": [16.0, 9.0, 6.0], "at": [30, 0], "open_ends": True}, "pieces": [{"kind": "box", "size": [3.0, 2.0, 1.2], "at": [27, 3]}, {"kind": "box", "size": [3.0, 2.0, 2.4], "at": [33, 4]}, {"kind": "stairs", "size": [1.5, 3.0, 1.2], "at": [30, 1.5]}]}})["result"]
r["bevel"] = runpy.run_path(f"{skills}/hard-surface/scripts/bevel_stack.py", init_globals={"ARGS": {"objects": [target], "width": 0.02, "segments": 1}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 6, "clusters": 2}})["result"]
r["gate"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_AbilityGate", "base_color": [0.0, 0.6, 0.8], "emission_color": [0.0, 0.8, 1.0], "emission_strength": 3.0, "objects": [target]}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "moonlight", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Room", "target": target, "lens_mm": 85, "azimuth_deg": 0, "elevation_deg": 0, "aspect": "16:9"}})["result"]
r["audit"] = runpy.run_path(f"{skills}/blender-mcp-workflow/scripts/scene_audit.py", init_globals={"ARGS": {"tri_budget": 20000}})["result"]
result = r
```

| Item | Value |
|---|---|
| Room (screen) | 16 x 9 m |
| Grid unit | 1 m |
| Standing hero | 1.8 m |
| Single jump | 3-4 m high, 5-6 m long |
| Doorway | 2 x 3 m |
| Ability gate opening | 1 x 1 m (morph-ball) to 2 x 3 m |
