---
name: genre-open-world-sandbox
description: "Art direction for open world and sandbox games in Blender with biome landmarks, traversable scale and discovery props. Use when the user asks for an open-world map, exploration landmarks, or sandbox-game environments that guide the player visually."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: open world, sandbox, open-world, exploration, traversable world, sandbox game
  related-skills: biome-worlds, environment-artist, vegetation-artist, scene-assembly, lod-pipeline
---

# Genre: Open World / Sandbox

Landmarking. Biome borders. Traversal toys. Discovery crumbs without clutter walls.

## Recipe

Traversable world: landmarks visible from 200+ m, scatter density 0.5-2 per m2 for ground clutter, LODs for everything repeated.

1. Scatter rocks/foliage on the terrain with `scatter_points.py`: `surface` the ground mesh, `collection` the collection holding the asset variants, `density` 0.5, `scale_min` 0.6, `scale_max` 1.6.
2. Time-of-day light with `light_rig.py` preset `golden_hour`.
3. Generate LODs for repeated assets with `generate_lods.py` (`ratios` [0.5, 0.25, 0.1]).
4. Add discovery crumbs with `scatter_props.py` (`count` 5, `clusters` 3, `max_dist` 25).
5. Validate budget with `scene_audit.py` (`tri_budget` 500000).

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
ground = "GEO_Ground"    # terrain mesh to scatter on
assets = "COL_Assets"    # collection of rock/foliage variants
r = {}
r["scatter"] = runpy.run_path(f"{skills}/geometry-nodes/scripts/scatter_points.py", init_globals={"ARGS": {"surface": ground, "collection": assets, "density": 0.5, "scale_min": 0.6, "scale_max": 1.6}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["lod"] = runpy.run_path(f"{skills}/lod-pipeline/scripts/generate_lods.py", init_globals={"ARGS": {"object": target, "ratios": [0.5, 0.25, 0.1]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 5, "clusters": 3, "max_dist": 25}})["result"]
r["audit"] = runpy.run_path(f"{skills}/blender-mcp-workflow/scripts/scene_audit.py", init_globals={"ARGS": {"tri_budget": 500000}})["result"]
result = r
```

| Item | Value |
|---|---|
| Player height | 1.8 m |
| Sprint speed | 6-8 m/s |
| Landmark visibility | 200-500 m |
| Point of interest spacing | 60-100 m |
| Climbable ledge | 1-2.5 m |
