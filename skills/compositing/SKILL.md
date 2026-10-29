---
name: compositing
description: "Blender compositor workflows for beauty stacks, render passes, color grade, glare, bloom/glow and delivery outputs via MCP. Use whenever adding bloom or glow (EEVEE's built-in bloom was removed in 4.2), grading a render, or writing compositor Python for Blender 5.x (the compositor now lives in scene.compositing_node_group). Ships tested scripts: comp_grade.py (compositor grade with presets, vignette, warmth and posterize)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  triggers: compositor, compositing, grade, beauty pass, render passes, cryptomatte, glare, vignette, color correction, post
  related-skills: rendering, lighting, lookdev, camera-cinematography, vfx-fx
---

# Compositing

Pass-aware beauty stack. Subtle grade. Delivery-ready outputs.

## When to Use

- Final beauty composites from Cycles/Eevee
- Grade, glare, vignette, chromatic subtlety
- Pass recombination (diffuse, glossy, volume, cryptomatte)
- Shot delivery plates

## Workflow

```
Enable passes → Render multilayer EXR (or needed passes)
  → Compositor graph → Grade → FX (glare/fog glow)
  → Output viewer + File Output → Validate exposure
```

## Bloom / glow in Blender 5.x (Python)

EEVEE's built-in bloom toggle was removed in 4.2, and in 5.0 the compositor moved to `scene.compositing_node_group`. Bloom is a compositor Glare node, and
its type is now a menu **input socket**:

```python
sc = bpy.context.scene
tree = sc.compositing_node_group or bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
sc.compositing_node_group = tree
if not tree.interface.items_tree:
    tree.interface.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = tree.nodes.new("CompositorNodeRLayers")
glare = tree.nodes.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"
glare.inputs["Threshold"].default_value = 0.8
glare.inputs["Strength"].default_value = 0.6
out = tree.nodes.new("NodeGroupOutput")
tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], out.inputs[0])
```

Or run `scripts/comp_grade.py` with `preset="stylized_bloom"`, which keeps your own nodes.

## Recommended Passes

| Pass | Use |
|------|-----|
| Beauty / Combined | Base |
| DiffCol / DiffDir / DiffInd | Relight flexibility |
| GlossDir / GlossCol | Spec control |
| Volume | Smoke/fire isolation |
| Cryptomatte Object/Material | Isolations |
| Mist | Depth grade / fog |

## Beauty Stack (Default)

```
Combined
  → Exposure / Color Balance (AgX-aware)
  → Glare (fog glow / streaks sparingly)
  → Lens distortion (subtle)
  → Vignette (subtle)
  → Output
```

## Grade Rules

1. Fix exposure before creative grade
2. Prefer lift/gamma/gain or color balance over crushed curves
3. Keep skin/product hues plausible
4. Match reference stills with side-by-side

## Outputs

- `OUT_Beauty_[Shot]`
- Optional: `OUT_Alpha`, `OUT_CryptoID`
- Prefer EXR for archival; PNG/JPEG for review

## Constraints

### MUST DO
- Grade on view transform–aware pipeline (AgX)
- Keep creative FX reversible in node graph
- Document exposure/look settings

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Crush blacks to hide lighting problems
- Over-glare every bright pixel
- Flatten multilayer to JPEG as only archive

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/comp_grade.py` | Build a compositor grade with the Blender 5.x API (scene.compositing_node_group, Group Output, socket-based Glare): bloom, lift/gamma/gain, saturation, lens, pixelate, posterize (`posterize` steps per channel, for 8-bit palettes) and a soft vignette. Replaces only nodes this script created (names starting "SK_"), so a user's own compositor nodes are kept. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/comp_grade.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `preset`, `vignette` (0-1), `warmth` (-1..1, warm/cool highlights), `posterize` (colour steps per channel). A "subtle vignette with warm
highlights" is `{"preset": "clean", "vignette": 0.35, "warmth": 0.4}`.

Blender 5.2 compositor facts this script relies on (hand-written graphs usually miss them): node settings
are input sockets (Color Balance `Type`, Blur `Size` as a 2D vector, Ellipse Mask `Size`); there is no
MixRGB node, use `ShaderNodeMix` with `data_type = "RGBA"` (its Factor socket is a `NodeSocketFloatFactor`).

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Pass Stack | `references/pass-stack.md` | When needed |
| Grade Presets | `references/grade-presets.md` | When needed |
| Delivery Outputs | `references/delivery-outputs.md` | When needed |
