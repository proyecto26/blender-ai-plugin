---
name: hd-2d-style
description: "HD-2D art direction combining pixel-art characters and sprites with 3D environments, depth of field and theatrical lighting. Use when the user wants an Octopath-style look, pixel sprites standing in a 3D scene, or billboard sprites in Blender. Ships tested scripts: sprite_billboard.py (vertical plane carrying a nearest-neighbour pixel image with alpha cut-out)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: HD-2D, HD2D, Octopath, triangle strategy, pixel 3D hybrid
  related-skills: pixel-art-style, environment-artist, camera-cinematography, lighting, compositing
---

# HD-2D Style

Pixel actors. 3D stage. Tilted theatrical camera. Creamy DoF.

## Tenets
1. Characters: pixel/billboard or texel-locked
2. Environments: soft 3D with painted textures
3. Strong DoF / god rays
4. Ortho-leaning perspective
5. Warm theatrical keys

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/sprite_billboard.py` | Pixel sprite plane: packed image with Closest interpolation and alpha, feet on the ground, turned to face the camera. Then add DoF with camera-cinematography `camera_rig.py`. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/sprite_billboard.py", init_globals={"ARGS": {"name": "SPR_Hero", "location": [0, 0], "height": 1.6}})["result"]
```
