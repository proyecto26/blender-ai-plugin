---
name: vfx-fx
description: "VFX: smoke, fire, steam, particles, trails. Use for gas effects from an emitter, sparks or muzzle flash. Ships tested scripts."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: discipline
  stage: animate
  triggers: VFX, FX, smoke, fire, explosion, particles, sparks, trails, muzzle flash, magic effect, geometry nodes FX
  related-skills: geometry-nodes, physics-sim, materials, lighting, rendering, compositing
---

# VFX / FX

Readable effects. Controlled simulation domains. Game sprites vs cinematic volumes.

## When to Use

- Smoke, fire, dust, sparks, debris
- Magic / sci-fi energy FX
- Muzzle flashes, trails, impacts
- Geometry Nodes driven particle systems

## Path Decision

```
Game real-time → Meshes/cards/ribbons + emissive mats (+ GN)
Cinematic     → Mantaflow / particles / GN → render → comp
Hybrid        → Sim in Blender → bake flipbooks/meshes for engine
```

## Workflow

```
Brief (silhouette + timing) → Proxy emitter → Sim/GN prototype
  → Art-direct motion → Materials/lights → Cache → Render/comp or export
```

## Effect Types

| Type | Blender Approach |
|------|------------------|
| Smoke/fire | Mantaflow domain + flow; keep domain tight |
| Sparks | Particle Newtonian + collision + trail |
| Debris | Rigid body shards (`physics-sim`) |
| Magic ribbons | Curves / GN extrude + emissive |
| Dust hit | Short particle burst + soft sprites |

## Domain Rules (Volume)

- Domain only as large as needed
- Resolution from low → high after motion approved
- Open borders intentionally; avoid wasted empty voxels
- Collection: `COL_FX_[Shot]`

## Naming

- Emitters: `FX_Emit_[Name]`
- Domains: `FX_Domain_[Name]`
- Caches: document frame range in brief

## Game Export Notes

- Prefer mesh cards / GN instances over volume export
- Atlas flipbooks when baking fire/smoke for engines
- Keep pivot at logical spawn point

## Constraints

### MUST DO
- Approve motion at low res before high-res sim
- Light FX intentionally (emissive + key)
- Cache before final render

### MUST NOT DO
- Huge empty domains
- Unbounded particle counts
- Skip timing brief (start/peak/end frames)

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/smoke_domain.py` | Mantaflow gas domain fitted around an emitter + flow (`SMOKE`/`FIRE`/`BOTH`, `INFLOW`), Principled Volume material, open top, low preview resolution; never bakes. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/smoke_domain.py", init_globals={"ARGS": {"emitter": "SM_Crate", "flow_type": "BOTH"}})["result"]
```

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Fx Timing Brief | `references/fx-timing-brief.md` | When needed |
| Volume Domain Rules | `references/volume-domain-rules.md` | When needed |
| Game Fx Export | `references/game-fx-export.md` | When needed |
