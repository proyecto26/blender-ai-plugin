---
name: stylized-style
description: Stylized art direction for Blender with shape language, exaggeration, color harmony, NPR rendering, and hand-painted asset workflows. Use for non-photorealistic game and animation projects.
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: stylized, NPR, hand-painted, toon, cartoon, exaggerated, shape language, cel shading
  related-skills: materials, rendering, lowpoly-style, environment-artist
---

# Stylized Style Specialist

Deliberate shape language. Exaggerated proportions. Color harmony. NPR rendering.

## When to Use

- Non-photorealistic games
- Hand-painted texture workflows
- Animated/stylized characters
- Fantasy environments with art direction
- Toon/cel-shaded rendering

## Core Principles

1. **Shape language** — Circles=friendly, squares=stable, triangles=danger
2. **Exaggeration** — Push proportions beyond realistic
3. **Color harmony** — Limited palette; intentional accent colors
4. **Silhouette clarity** — Strong readable shapes
5. **Detail in texture** — Not micro-geometry

## Shape Language

| Shape | Association | Use |
|-------|-------------|-----|
| Circle/Oval | Friendly, approachable | Heroes, cute creatures |
| Square/Rectangle | Stable, reliable | Architecture, guards |
| Triangle | Dynamic, dangerous | Villains, spikes, roofs |

Combine shapes consistently per character/faction.

## Proportion Exaggeration

| Feature | Stylized Approach |
|---------|-------------------|
| Head | 25–40% of height (chibi to semi-realistic) |
| Hands | Larger for expressiveness |
| Eyes | Enlarged for emotion |
| Limbs | Tapered; simplified joints |
| Weapons | Oversized for readability |

## Color Harmony

**Triadic:** Three equidistant hues — vibrant, balanced
**Complementary:** Opposite hues — high contrast accents
**Analogous:** Adjacent hues — harmonious environments

Rules:
- Limit palette to 3–5 core colors + neutrals
- Reserve saturated accents for interactive elements
- Desaturate backgrounds; saturate foreground subjects

## Material Approach

- Hand-painted albedo priority over PBR accuracy
- Flat or stepped roughness (not continuous PBR)
- Rim lighting built into texture (not just shader)
- Subsurface on skin: exaggerated warm tones
- No photoreal micro-detail

## NPR Rendering

Coordinate with rendering skill:
- Toon BSDF or Shader to RGB setups
- Stepped lighting (2–3 bands)
- Outline pass: inverted hull or Freestyle
- Bloom on emissive accents (compositor Glare node, `Type` = Bloom)
- Flat ambient forbidden — maintain form readability

## Hand-Painted Texture Workflow

```
1. Flat base color blocks
2. Define light/shadow shapes (not gradients from bake)
3. Edge highlights (warm) and shadows (cool)
4. Detail pass: minimal; suggestive not literal
5. Ambient occlusion painted, not baked
```

## Character Stylization

- Simplified anatomy; avoid uncanny valley
- Hair as solid shapes or card clusters
- Clothing folds: painted, not simulated
- Facial features: large eyes, small nose (style dependent)

## Environment Stylization

- Exaggerated verticality in forests/mountains
- Architecture: oversized elements (doors, windows)
- Vegetation: puff/cloud shapes (not botanical accuracy)
- Water: stylized foam patterns

## MCP Integration

1. Block exaggerated proportions via MCP
2. Assign stylized materials via MCP
3. Configure NPR render settings via MCP
4. Validate silhouette with flat shading via MCP
5. Limit geometry detail per stylized budgets

## Constraints

### MUST DO
- Define shape language per asset/faction
- Maintain color palette consistency
- Exaggerate intentionally, not accidentally
- Paint detail in textures
- Test NPR render early

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Mix photoreal PBR with stylized shapes without intent
- Micro-detail geometry (use texture)
- Realistic proportions unless semi-stylized target
- Full PBR roughness accuracy
- Skip outline/rim if NPR project requires

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/toon_material.py` | Create a cel/toon material (Diffuse -> Shader to RGB -> constant ColorRamp bands, optional Fresnel rim) and optionally an inverted-hull outline (Solidify with flipped normals + backface-culled black material). EEVEE only (Shader to RGB). |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/toon_material.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `name`, `base_color`, `bands`, `rim`, `objects`, `outline`

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| NPR shader setup | `references/npr-shaders.md` | Rendering setup |
| Color palettes | `references/palette-examples.md` | Art direction |

## Related Style Packs
- `cartoon-style`, `anime-style`, `comic-book-style`, `manga-style`, `hand-painted-style`, `painterly-style`
- `chibi-style`, `pixel-art-style`, `hd-2d-style`, `stop-motion-craft-style`

