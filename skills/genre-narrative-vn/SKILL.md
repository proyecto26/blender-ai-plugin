---
name: genre-narrative-vn
description: "Visual novel and narrative game spaces. Use for a VN background or story scene with clear character staging."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: genre
  stage: brief
  requires: "camera-cinematography, compositing, lighting, rendering, set-dressing"
  triggers: visual novel, interactive movie, walking simulator, narrative game, story scene, VN background
  related-skills: camera-cinematography, lighting, set-dressing, archviz, compositing
---

# Genre: Narrative / VN / Walking Sim

Emotion cameras. Backgrounds plate-ready. Sparse interaction highlights.

## Recipe

Plate-ready backgrounds: 1920x1080, 35 mm eye-level camera, soft key with warm/cool contrast, light film grade; leave the lower third calm for dialogue boxes.

1. Light with `light_rig.py` preset `golden_hour` (warm emotional key) or `overcast` for melancholy.
2. Frame the plate with `camera_rig.py`: `lens_mm` 35, `elevation_deg` 5, `dof_fstop` 2.8, `aspect` 16:9.
3. Dress sparsely with `scatter_props.py` (`count` 4, `clusters` 2); only props that tell story.
4. Render quality with `render_preset.py` preset `eevee_final`.
5. Grade with `comp_grade.py` preset `cinematic`, `vignette` 0.25.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "golden_hour", "target": target}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"name": "CAM_Plate", "target": target, "lens_mm": 35, "elevation_deg": 5, "dof_fstop": 2.8, "aspect": "16:9"}})["result"]
r["props"] = runpy.run_path(f"{skills}/set-dressing/scripts/scatter_props.py", init_globals={"ARGS": {"target": target, "count": 4, "clusters": 2}})["result"]
r["render"] = runpy.run_path(f"{skills}/rendering/scripts/render_preset.py", init_globals={"ARGS": {"preset": "eevee_final"}})["result"]
r["grade"] = runpy.run_path(f"{skills}/compositing/scripts/comp_grade.py", init_globals={"ARGS": {"preset": "cinematic", "vignette": 0.25}})["result"]
result = r
```

| Item | Value |
|---|---|
| Eye height (walking sim) | 1.6 m |
| Doorway | 0.9 x 2.1 m |
| Corridor width | 1.2-2 m |
| Interactable highlight | 1 per view |
