---
name: set-dressing
description: "Set dressing: prop placement and environmental storytelling. Use when a scene feels empty or props should tell a story. Ships tested scripts. Mass terrain scatter goes to geometry-nodes."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: discipline
  stage: model
  triggers: set dressing, dressing, storytelling props, interior dressing, clutter, narrative placement, set decals
  related-skills: prop-artist, scene-assembly, environment-artist, horror-style, qa-review
---

# Set Dressing

Story through placement. Controlled clutter. Readable clusters.

## When to Use

- Interior/exterior dressing passes
- Narrative prop clusters
- Avoiding empty or overstuffed spaces
- After modular layout is locked

## Workflow

```
Layout locked → Hero narrative props → Secondary clusters
  → Background filler → Decals/wear → Lighting check → QA
```

## Density Rules

| Zone | Density |
|------|---------|
| Hero interact zone | High intent, low noise |
| Midground | Supporting story clusters |
| Background | Sparse; silhouette only |
| Traversal path | Clearance for player/camera |

## Cluster Method

1. Pick a story beat (meal abandoned, workbench used, escape rushed)
2. Place 3–7 props that sell the beat
3. Add 1–2 wear/decal cues
4. Stop — do not fill every surface

## Prop Sources

- `prop-artist` for unique pieces
- Kitbash / modular libraries for filler
- Instance repeats; vary rotation/scale slightly

## Horror / Sparse Styles

- Fewer props, more meaning
- Negative space intentional
- Coordinate with `horror-style` / `psx-horror-style`

## Constraints

### MUST DO
- Dress after greybox navigation works
- Keep player/camera paths clear
- Instance repeated meshes

### MUST NOT DO
- Uniform clutter wallpaper
- Block doors/windows without story reason

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/scatter_props.py` | Exact-count story clusters of boxes/barrels/pallets around a target: ground raycast, keep-out of the target bbox, no overlaps, shared meshes, `PROP_` names. For many small instances on terrain use geometry-nodes `scatter_points.py`. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/scatter_props.py", init_globals={"ARGS": {"target": "SM_Crate", "count": 8, "kinds": ["box", "barrel", "pallet"]}})["result"]
```

`max_dist` (default 3.5) is the maximum horizontal (XY) distance from the target's bbox centre to any prop origin, enforced per prop. If the requested count cannot fit inside it the script raises `RuntimeError` (raise `max_dist` or lower `count`).

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Story Clusters | `references/story-clusters.md` | When needed |
| Density Map | `references/density-map.md` | When needed |
