---
name: geometry-nodes
description: Blender Geometry Nodes for procedural modeling, scatter systems, vegetation, buildings, pipes, cables, and reusable node groups. Use for procedural asset generation and instancing pipelines via MCP, and whenever Python code builds node groups or reads/sets Geometry Nodes modifier inputs (Blender 5.2 changed that API).
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: geometry nodes, procedural, scatter, node group, GN_, instancing, parametric
  related-skills: procedural-modeling, environment-artist, blender-modeler
---

# Geometry Nodes

Reusable procedural systems. Parametric assets. Performance-aware instancing.

## When to Use

- Scatter systems (rocks, vegetation, debris)
- Parametric buildings, roads, pipes, cables
- Procedural variation without unique modeling
- Kit assembly with randomization
- Non-destructive iteration on large scenes

## Workflow

```
Define Parameters → Build Node Tree → Create Node Group (GN_)
    → Test Variations → Bake/Instance Decision → Export Integration
```

## Node Group Standards

- Prefix: `GN_[System]_[Descriptor]`
- Expose only necessary inputs (seed, density, scale range)
- Document input ranges in group name or custom properties
- Version node groups: `GN_Scatter_Rocks_v02`

## Core Patterns

### Scatter System
```
Mesh Surface → Distribute Points on Faces → Instance on Points
    → Randomize Rotation (Z) → Randomize Scale → Realize (optional)
```

### Building Generator
```
Floor Count (input) → Repeat Mesh → Stack Instances
    → Window Cut Pattern → Material Variation → Output
```

### Cable/Pipe Routing
```
Curve Input → Curve to Mesh (profile) → Subdivide → Set Material
    → Multiple curves from single path node
```

### Rock Formation
```
Ico Sphere → Displace (noise) → Decimate → Instance Scatter
```

## Randomization

| Parameter | Typical Range |
|-----------|---------------|
| Scale | 0.8–1.2 (uniform or per-axis) |
| Rotation Z | 0–360° |
| Density | 0.1–2.0 per m² |
| Seed | Integer for reproducibility |

Always expose seed as group input for art direction iteration.

## Performance Rules

| Scenario | Approach |
|----------|----------|
| Game export | Realize instances → decimate → export mesh |
| Background scatter | Keep instanced; limit count |
| Hero procedural | Bake to static mesh for engine |
| Viewport preview | Limit instance count attribute |

## Reusable Systems Library

| Group | Purpose |
|-------|---------|
| GN_Scatter_Objects | Generic surface scatter |
| GN_Array_Modular | Linear modular repetition |
| GN_Curve_Pipe | Pipe/cable along curve |
| GN_Wall_Variant | Parametric wall sections |
| GN_Vegetation_Cluster | Tree/bush clustering |

## Python: set modifier inputs (Blender 5.x)

Modifier inputs are keyed by the socket **identifier** (`Socket_2`), not its name. Blender 5.2 removed
ID-property access (`mod["Socket_2"] = v` raises `TypeError: id properties not supported`):

```python
mod = obj.modifiers["GeometryNodes"]
ident = next(i.identifier for i in mod.node_group.interface.items_tree
             if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == "Density")
if hasattr(mod, "properties"):                 # Blender 5.2+
    getattr(mod.properties.inputs, ident).value = 2.5
else:                                          # 4.x - 5.1
    mod[ident] = 2.5
```

Node sockets keep hidden same-name variants per data type, so pick inputs with
`next(s for s in node.inputs if s.name == "Density" and s.enabled)`.

## MCP Integration

1. Create geometry nodes modifier via MCP
2. Configure group inputs via MCP
3. Query instance count and final polycount
4. Realize geometry for export via MCP
5. Organize GN objects in dedicated collection

## Integration with Export

Before export:
1. Apply geometry nodes modifier OR
2. Realize instances and merge OR
3. Export as instances if engine supports (Unreal HISM)

Document which approach per target engine.

## Constraints

### MUST DO
- Create reusable node groups, not one-off trees
- Expose seed and density as inputs
- Test at min/max parameter extremes
- Realize/bake before game export unless engine supports instances
- Name groups with `GN_` prefix

### MUST NOT DO
- Million-instance scatter without LOD/culling plan
- Nested realize operations (performance killer)
- Hardcode values that should be inputs
- Export procedural without polycount validation
- Skip variation testing at boundary values

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.

| Script | What it does |
|--------|--------------|
| `scripts/scatter_points.py` | Build a reusable geometry-nodes scatter on a surface object: Distribute Points on Faces -> Instance on Points (collection, random pick) with random rotation/scale, aligned to the surface normal. Density, seed and scale are exposed as modifier inputs. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/scatter_points.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `surface`, `collection`, `density`, `seed`, `scale_min`, `scale_max`, `align_to_normal`, `realize`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Scatter recipes | `references/scatter-systems.md` | Environment scatter |
| Building generators | `references/building-generators.md` | Architectural procedural |
