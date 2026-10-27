# Roadmap

Planned improvements for the Blender AI Plugin. v2.0.0 shipped the official Blender MCP migration, tested scripts, the orchestrator agent, evals and validators.

## v1.2.0 — Reference & Photogrammetry

- [ ] `references/photogrammetry-cleanup.md` — scan mesh cleanup workflow
- [ ] `references/reference-image-depth.md` — multi-angle reference triangulation
- [ ] `realistic-style` — scan-match material workflow (Quixel-style)
- [ ] Deeper `rendering` SKILL.md — Cycles denoiser presets per use-case

## v1.3.0 — Procedural Systems

- [ ] `geometry-nodes` — advanced scatter system reference
- [ ] `procedural-modeling` — terrain + road generation reference
- [x] Blender 5.x geometry nodes API (`geometry-nodes/scripts/scatter_points.py`)

## v1.4.0 — Character & Creature Pipeline

- [ ] `character-artist` — clothing simulation reference
- [ ] `retopology` — hair card topology reference
- [ ] `rigging` — shape key + driver reference for facial rigs
- [ ] `animation` — mocap cleanup workflow

## v1.5.0 — Engine Export Polish

- [ ] `export-pipeline` — Unreal 5 Nanite prep reference
- [ ] `export-pipeline` — Unity HDRP material mapping reference
- [x] `lod-pipeline` — automated LOD generation (`scripts/generate_lods.py`)

## v2.0.0 — Multi-Agent Orchestration

- [ ] Parallel skill execution (Blender Director routes to multiple agents simultaneously)
- [ ] Blender + Substance Painter bridge (material handoff workflow)
- [ ] USD pipeline skill (OpenUSD for film/VFX)

## Backlog

- [x] Validation script (`scripts/validate_skills.py`) — next: wire into GitHub Actions
- GitHub Actions for SKILL.md schema lint on PRs
- [x] Blender 5.x API notes (`skills/blender-mcp-workflow/references/blender-5-api-notes.md`)
- `horror-style` — expanded Silent Hill / Bloober Team analysis reference
- `lowpoly-style` — PS1 dithering shader for Blender
