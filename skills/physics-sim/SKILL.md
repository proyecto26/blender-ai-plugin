---
name: physics-sim
description: Rigid body, soft body, and destruction setups in Blender including constraints, cell fracture debris, and baked caches via MCP.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: physics, rigid body, soft body, destruction, fracture, debris, constraint, simulation bake, collapse
  related-skills: vfx-fx, cloth-sim, animation, export-pipeline, collision-proxy
---

# Physics Sim

Stable rigid/soft body setups. Motivated destruction. Baked caches.

## When to Use

- Rigid body interactions and collapses
- Soft body jiggle / rubber / simple soft props
- Destruction and debris (cell fracture / pre-cut shards)
- Pre-vis physics before VFX polish

## Workflow

```
Simplify collision meshes → Assign rigid/soft bodies
  → Constraints → Passive settings → Bake → Art-direct → Export cache
```

## Rigid Body Quick Rules

| Role | Settings notes |
|------|----------------|
| Active | Moving debris / props |
| Passive | Floors, walls, heavy anchors |
| Convex hull | Fast, approximate |
| Mesh | Accurate, heavier |

- Apply scale before sim
- Use margin appropriate to scale
- Collection: `COL_Physics_[Shot]`

## Constraints

- Hinge / fixed / motor for mechanical links
- Breakable constraints for destruction beats
- Name: `RBCON_[Object]_[Type]`

## Destruction Approach

```
1. Pre-cut shards (cell fracture or manual)
2. Island meshes as active rigid bodies
3. Passive shell until trigger frame
4. Animate trigger (force / keyframed activation)
5. Bake → cleanup interpenetrations
```

## Soft Body

- Prefer for simple soft props; use `cloth-sim` for garments
- Goal weights to retain shape
- Soft + collision object required

## Bake / Export

- Bake to cache before render
- Alembic/USD for cinematic debris
- For games: bake key poses or flipbook; rarely live Blender physics

## Constraints

### MUST DO
- Apply scale; use simplified colliders
- Bake before final delivery
- Trigger destruction intentionally (frame)

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- High-res sculpt meshes as active colliders
- Unbounded shard counts
- Leave sims unbaked for final renders

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/rigid_body_setup.py` | Set up rigid bodies: ensure a rigid body world, make objects ACTIVE or PASSIVE with a collision shape and mass from a material density, configure the cache range, and optionally bake. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/rigid_body_setup.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `active`, `passive`, `shape`, `material`, `frames`, `substeps`, `bake`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Rigid Body Presets | `references/rigid-body-presets.md` | When needed |
| Destruction Pipeline | `references/destruction-pipeline.md` | When needed |
| Sim Bake Checklist | `references/sim-bake-checklist.md` | When needed |
