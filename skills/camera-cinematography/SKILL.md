---
name: camera-cinematography
description: "Camera work: framing, lenses, depth of field, hero shots and camera moves. Use for 'frame the subject', eye-level first-person views, or a subject blocked from view. Ships tested scripts. Not for render settings (use rendering)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: discipline
  stage: light_camera
  triggers: camera, cinematography, lens, framing, composition, shot, dolly, orbit, focal length, depth of field, camera animation
  related-skills: rendering, lighting, animation, compositing, lookdev
---

# Camera Cinematography

Intentional framing. Lens language. Motivated camera moves. Shot-ready cameras.

## When to Use

- Cinematic stills and turntables with purpose
- Animated camera moves (dolly, crane, orbit, handheld)
- Matching reference camera / lens feel
- Shot layout for lookdev and portfolio

## Workflow

```
Shot intent → Camera + target empty → Lens/FOV → Composition
  → Focus/DoF → Move (if animated) → Viewport check → Render/comp
```

## Naming

- `CAM_[Shot]_[Angle]`
- `EMPTY_CamTarget_[Shot]`
- Collection: `COL_Cameras`

## Lens Guide

| Feel | Focal (FF equiv) | Notes |
|------|------------------|-------|
| Wide establishing | 18–28mm | Distortion; watch edges |
| Story / product | 35–50mm | Natural |
| Portrait / hero | 85–135mm | Compression |
| Tele drama | 150mm+ | Flat space |

Sensor fit and resolution affect FOV — set camera sensor intentionally.

## Composition Checklist

- [ ] Subject readable in silhouette
- [ ] Headroom / lead room intentional
- [ ] Horizon level (unless motivated)
- [ ] Foreground / mid / background depth
- [ ] Avoid tangent mergers on edges

## Camera Animation

| Move | Use |
|------|-----|
| Orbit | Product / character showcase |
| Dolly in | Reveal / tension |
| Crane | Scale / establishing |
| Handheld noise | Documentary / horror unease |
| Locked off | Archviz / product purity |

Animate camera + target empties; prefer slow ease-in/out.

## DoF

- Focus on primary subject empty
- F-stop for style: shallow for hero, deeper for environments
- Preview in Eevee; final in Cycles if needed

## Constraints

### MUST DO
- Name cameras and targets
- Match aspect ratio to delivery
- Check framing at start, mid, end of moves

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Default 50mm for every shot without intent
- Animate FOV wildly unless motivated
- Crop critical silhouette out of frame

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/camera_rig.py` | Create (or update) a shot camera that frames a target: focal length, framing distance from bounds, optional depth of field focused on the target, a Track To constraint to a focus empty, and composition guides. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/camera_rig.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `name`, `target`, `lens_mm`, `azimuth_deg`, `elevation_deg`, `fill`, `dof_fstop`, `set_active`, `aspect`, `eye_height` (absolute camera Z, e.g. 1.6), `min_distance`, `max_distance`

Occlusion check: the result carries `occluded_by` (names of objects between camera and subject) and `visible_fraction`. Hidden-from-render objects, collision proxies, fluid domains (they render as volumes, not as their box, so they never count as occluders) and the subject itself are ignored. If `occluded_by` is non-empty, move the camera (other azimuth, `eye_height`, distance clamps), don't ship.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Lens And Composition | `references/lens-and-composition.md` | When needed |
| Camera Move Library | `references/camera-move-library.md` | When needed |
| Dof Guide | `references/dof-guide.md` | When needed |
