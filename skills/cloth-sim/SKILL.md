---
name: cloth-sim
description: Garment blockout, cloth simulation, pin groups, and bake to shape keys or caches for characters and props in Blender via MCP.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: cloth, garment, clothing sim, fabric sim, pin group, shape key bake, cloth bake, dress, cape, soft clothing
  related-skills: character-artist, physics-sim, materials, animation, export-pipeline
---

# Cloth Sim

Garment blockout → sim → art-direct → bake. Stable pins. Engine-friendly caches/shape keys.

## When to Use

- Dresses, capes, coats, flags, banners
- Character clothing that needs drape
- Baking sim to shape keys or Alembic/USD caches
- Pre-roll settling before animation export

## Workflow

```
Garment mesh (quad-friendly) → Vertex groups (pin/collide)
  → Cloth modifier settings → Collision objects
  → Pre-roll settle → Sim pass → Art-direct fixes
  → Bake shape keys / cache → Cleanup → Export
```

## Mesh Prep

- Quads preferred; even density on deforming areas
- Avoid long skinny triangles on folds
- Apply scale before sim
- Separate garment from body collider

## Vertex Groups

| Group | Purpose |
|-------|---------|
| `PIN_Cloth` | Anchors (waist, shoulders, collar) |
| `COL_Ignore` | Optional non-colliding regions |
| `STIFF_High` | Belts, seams that should resist stretch |

## Settings Starters

| Look | Quality | Speed | Bending |
|------|---------|-------|---------|
| Soft dress | 8–12 | 1.0 | Low |
| Stiff coat | 5–8 | 1.0 | Higher |
| Flag/cape | 8–10 | 1.0–1.5 | Low–mid |

Tune mass and air viscosity for scale. Always run a settle pre-roll.

## Bake Targets

| Target | Use |
|--------|-----|
| Shape keys | Game poses / few frames |
| Alembic/USD | Cinematic caches |
| Armature weights | If converting to deform-only |

## Constraints

### MUST DO
- Apply scale; define pin groups before long sims
- Collide against simplified body capsule/mesh
- Art-direct after sim (sculpt/corrective keys)

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Sim hero cloth on ultra-dense sculpt meshes
- Skip pre-roll (starts mid-air / exploding)
- Export raw unstable caches

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/cloth_setup.py` | Add a cloth simulation with a fabric preset, optional pin group, collision on listed colliders, and cache range. Re-running updates the existing modifier. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/cloth_setup.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `cloth`, `fabric`, `pin_group`, `colliders`, `frames`, `self_collision`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Cloth Settings Presets | `references/cloth-settings-presets.md` | When needed |
| Pin And Collide | `references/pin-and-collide.md` | When needed |
| Bake Targets | `references/bake-targets.md` | When needed |
