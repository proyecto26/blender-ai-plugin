---
name: collision-proxy
description: Collision proxy authoring for games including UCX/UHX naming, convex hulls, capsules, and simple collider meshes in Blender via MCP.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: collision, collider, UCX, UHX, convex hull, physics proxy, hitbox, blocking volume
  related-skills: lod-pipeline, unity-export, unreal-export, asset-optimization, physics-sim
---

# Collision Proxy

Simple, stable colliders. Prefer primitives and convex pieces over render mesh.

## When to Use

- Game physics / blocking volumes
- Unreal UCX export
- Unity mesh or primitive colliders
- Hitboxes for interactables

## Workflow

```
Identify collision needs → Build proxies → Name correctly
  → Test overlaps → Export with render mesh
```

## Collider Types

| Type | Use |
|------|-----|
| Box | Crates, walls, simple props |
| Capsule | Characters, poles |
| Sphere | Balls, soft approximates |
| Convex hull | Organic / irregular single body |
| Multiple convex (UCX) | Vehicles, complex props |

## Unreal Naming

```
UCX_SM_Asset_01
UCX_SM_Asset_02
```

- Must match associated mesh naming rules for auto-association
- Convex only for UCX

## Unity Notes

- Prefer engine primitives when possible
- Mesh colliders: convex toggle for dynamic rigidbodies
- Keep proxy collection exportable

## Authoring Rules

1. Slightly smaller than visual mesh to reduce snagging (project-dependent)
2. No holes; watertight convex pieces
3. Apply scale
4. Origin aligned with render mesh
5. Collection: `COL_Collision_[Asset]`

## Validation

- [ ] Player cannot fall through intended blockers
- [ ] No huge invisible walls beyond mesh
- [ ] Wheel/character capsules oriented correctly
- [ ] Named for target engine

## Constraints

### MUST DO
- Prefer few simple shapes over one complex mesh
- Match engine naming conventions
- Keep proxies in dedicated collection

### MUST NOT DO
- Use render LOD0 as physics mesh by default
- Non-convex UCX for Unreal auto-convex workflows

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.

| Script | What it does |
|--------|--------------|
| `scripts/make_collision.py` | Generate simple collision proxies for render meshes, named for the target engine. Shapes: box (oriented to object), convex (hull of evaluated mesh). Proxies go to COL_Collision, display as wire, are hidden from render, and parented to the source. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/make_collision.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `objects`, `shape`, `engine`, `max_hull_verts`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Collider Recipes | `references/collider-recipes.md` | When needed |
| Engine Naming | `references/engine-naming.md` | When needed |
