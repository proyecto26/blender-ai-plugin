---
name: genre-strategy-sim
description: Art direction for strategy, RTS, turn-based strategy, tower defense, MOBA, city builder, colony sim, and simulation games in Blender.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: strategy, RTS, turn-based strategy, tower defense, MOBA, city builder, colony sim, simulation, life sim, farming sim
  related-skills: isometric-style, environment-artist, prop-artist, scene-assembly, vegetation-artist
---

# Genre: Strategy / Sim

Iconic buildings. Tile clarity. Unit read at camera distance. Sim props tell systems.

## Recipe

Tile-clear iconic view: 2:1 dimetric orthographic camera, 1 m or 2 m tiles, bright even light, strong silhouettes readable at 64 px.

1. Camera with `iso_camera.py`: `projection` dimetric_2_1, `pixel_tile` 64.
2. Even light with `light_rig.py` preset `overcast`.
3. Stylised color-block materials with `toon_material.py` (`bands` 3, `outline` 0.02) for buildings/units.
4. Populate props with `scatter_props.py` (`count` 12, `clusters` 4).
5. Optional bake LOD chain: `generate_lods.py` (`ratios` [0.5, 0.25]) for unit meshes.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["cam"] = runpy.run_path(f"{skills}/isometric-style/scripts/iso_camera.py", init_globals={"ARGS": {"projection": "dimetric_2_1", "target": None, "pixel_tile": 64}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["toon"] = runpy.run_path(f"{skills}/stylized-style/scripts/toon_material.py", init_globals={"ARGS": {"name": "MAT_Building", "base_color": [0.8, 0.5, 0.3], "bands": 3, "outline": 0.02, "objects": [target]}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 12, "clusters": 4}})["result"]
r["lod"] = runpy.run_path(f"{skills}/lod-pipeline/scripts/generate_lods.py", init_globals={"ARGS": {"object": target, "ratios": [0.5, 0.25]}})["result"]
result = r
```

| Item | Value |
|---|---|
| Tile | 1 or 2 m |
| Unit footprint | 1 tile |
| Building footprint | 2x2 to 4x4 tiles |
| Unit height | 1-2 m (exaggerated) |
| Tris per unit | 500-2000 |
