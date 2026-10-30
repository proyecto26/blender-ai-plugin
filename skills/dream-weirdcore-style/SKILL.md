---
name: dream-weirdcore-style
description: "Weirdcore/dreamcore nostalgic wrongness. Use for traumacore, wrong childhood rooms. Not empty offices or malls (liminal-space-style)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: style
  stage: brief
  requires: "blender-mcp-workflow, camera-cinematography, compositing, lighting, lowpoly-style"
  triggers: dreamcore, weirdcore, traumacore, dream horror, nostalgic horror, surreal childhood, weirdcore edit
  related-skills: liminal-space-style, dream-surreal-mood, horror-style, compositing, lighting
---

# Dream / Weirdcore Style

Nostalgic spaces. Soft dread. Surreal edits. Childhood UI/objects out of place.

## Tenets
1. Soft fog / bloom
2. Childhood objects oversized or abandoned
3. Text overlays / cryptic captions optional (comp)
4. Unclear geography
5. Emotion > logic

## Recipe

Target: low-res nostalgic frame (640x480), pale fog colour [0.82, 0.84, 0.9], nearest-neighbour textures, soft bloom, overcast daylight, no vertex snapping so it feels like a memory rather than a game.

1. `ps1_look` `resolution` [640, 480], `snap` 0 (no wobble), `fog` [0.82, 0.84, 0.9], `texture` False; this sets the low-res frame and distance fog in the compositor.
2. `light_rig` `overcast` for flat, shadowless, childhood-afternoon light.
3. `camera_rig` `lens_mm` 28, `elevation_deg` 8, `fill` 0.5; unclear geography comes from the framing, keep the horizon off-centre.
4. `comp_grade` `stylized_bloom` with `warmth` 0.2 and `vignette` 0.5 for the soft glow. Captions and cryptic text are Text objects or an overlay added last.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["prep"] = runpy.run_path(f"{skills}/blender-mcp-workflow/scripts/fix_asset.py", init_globals={"ARGS": {"objects": [target]}})["result"]  # apply scale, add box UVs if missing
r["look"] = runpy.run_path(f"{skills}/lowpoly-style/scripts/ps1_look.py", init_globals={"ARGS": {"objects": [target], "snap": 0, "resolution": [640, 480], "fog": [0.82, 0.84, 0.9], "texture": False}})["result"]
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "overcast", "target": target}})["result"]
r["camera"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Weird_01", "target": target, "lens_mm": 28, "elevation_deg": 8, "fill": 0.5}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "stylized_bloom", "warmth": 0.2, "vignette": 0.5}})["result"]
result = r
```
