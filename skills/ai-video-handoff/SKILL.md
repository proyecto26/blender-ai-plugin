---
name: ai-video-handoff
description: "Render Blender shots as clips, masks and depth maps for Seam or ComfyUI to paint backgrounds and add motion. Use when handing shots to AI video. Ships tested scripts. Not for film editing (use film-production)."
license: MIT
metadata:
  author: https://github.com/proyecto26
  version: "1.0.0"
  category: production
  stage: handoff
---

# AI video handoff

Blender renders what needs precision: the subject, camera, composition and lighting. AI tools do what Blender
does slowly: painted backgrounds and motion. This skill renders the files and a manifest, then stops. It never
uploads, submits or pays for anything. Seam or ComfyUI runs the AI step, through their own MCP tools or skills.

## Pick the target

| User wants | `target` | Output |
|---|---|---|
| Transitions between shots ("send these shots to Seam") | `seam` | one mp4 clip per moving shot, one opaque PNG per still shot, `seam/seam_sequence.json` |
| A depth map, mask or beauty frame for a ComfyUI graph | `comfy` | `comfy/assets/<shot>/{beauty,mask,depth}.png`, `comfy/handoff.json` |
| Both (default) | `both` | everything above |

Seam takes only shots (2-8 stills or 1-6 s clips) and chooses its own output size. It ignores depth, alpha and
camera data. Use ComfyUI whenever the AI step needs the subject mask, the depth, or an image-to-video graph of
your own. See `references/seam.md` and `references/comfyui.md`.

## Recipe: Blender base image + AI background + AI motion

1. **Lock the shot in Blender.** Camera, lens, framing and light are final before any AI runs. The camera is the
   one thing AI cannot reproduce, so never move it afterwards.
2. **Render the subject pass.** Run the script with `target: "comfy"`, `subject: [...]`. You get the beauty frame,
   a mask (white = subject) and a depth map (normalized from Blender's mist pass).
3. **Generate the background in ComfyUI.** Feed the depth map to a depth ControlNet, or the inverted mask to an
   inpaint node, with a prompt for the environment. Use `depth_near_white: true` if the model expects near = white.
4. **Composite.** Put the Blender subject over the generated background with the mask (a ComfyUI composite
   node, or Blender's compositor). The subject stays pixel-identical to the Blender render.
5. **Animate.** Either hand the composited frames to Seam as shots (transitions between shots), or run an
   image-to-video workflow in ComfyUI from the composite as the first frame.
6. **Check frames.** Look at a contact sheet or the first/middle/last frames of each result before telling the
   user it worked. You cannot judge motion from one frame, so say what you inspected.

## Render the handoff

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/render_handoff.py", init_globals={"ARGS": {
    "out_dir": "<project>/handoff", "target": "seam", "size": [1280, 704]}})["result"]
```

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/render_handoff.py", init_globals={"ARGS": {
    "out_dir": "<project>/handoff", "target": "comfy", "subject": ["Hero"], "passes": ["beauty", "mask", "depth"]}})["result"]
```

Use forward slashes in paths. Read the header of `scripts/render_handoff.py` for every argument. Headless
Blender takes `--args-file <path.json>` instead of inline JSON.

How the script behaves:

- **Shots** come from `shots` (explicit), else `scene["film_shots"]` (written by the film-production skill:
  `{id, start, end, camera, lens_mm, motion, beat, description}`), else one still from the active camera at the current frame.
- **Size** is snapped to multiples of 32 (256-2048), default from the scene. Every shot renders at one size, so the
  aspect ratio is consistent. Check `result["warnings"]` for a snapped size.
- **Moving shots** (Seam) render an H.264 clip over the shot's frame range. A clip over 6 s is clamped to its first
  frames with a warning. A clip under 1 s raises an error: mark the shot `still` or lengthen it. Fix this before
  rendering, because every render is slow.
- **Still shots** render the middle frame as an opaque RGB PNG.
- **Mask**: only the named objects and their children render, on a transparent film. Occluders and ground are
  ignored. A name that does not exist raises an error before anything renders.
- **Depth**: 16-bit PNG, Non-Color, normalized between mist `start` and `start + depth` (linear). Not metric. The
  manifest records `{start, depth, falloff, polarity}` per shot. Default polarity is near = black.
- **Restore**: every setting the script touches is restored in `finally`, also when a render fails.
  `result["restored"]` is `false` only if a restore step itself failed.

The scripts need Blender 5.2+. With a window open (UI or MCP session) the script makes the rendered scene the
window's scene for the render, which transparent film needs, and switches it back; headless runs need nothing extra.

## Submit to Seam

1. Ask for consent before any paid or cloud render. Seam runs a local GPU job, but it is still the user's
   hardware and time. Say how many takes will render (one per segment).
2. Call Seam's `list_presets` through its MCP server. Each preset is qualified only at its listed lengths.
3. Read `seam/seam_sequence.json`. Set every segment's `preset` and `seconds` from `list_presets`. The script writes
   `preset: null` placeholders and never invents one. Add `seed`, `prompt_extra`, `a_desc`, `b_desc` as needed.
4. Call `create_sequence(shots, segments)` with the manifest's `shots` (local paths, in order) and the edited
   `segments` (exactly `len(shots) - 1`). Then `wait_sequence` and `preview_sequence`.
5. REST instead of MCP: upload each file with `POST /api/uploads` and `role=mid`, then build the sequence body
   yourself from the returned ids (details in `references/seam.md`).

Seam renders every take at the first shot's aspect ratio and picks the pixel size itself. The manifest records the
size Blender used, nothing more. Do not promise the user an output resolution.

## Submit to ComfyUI

Use the `comfy` CLI and its skills (`comfy`, `comfy-director`, `comfy-relay`). Do not reimplement them here.

1. `comfy project init` in a working folder (or use the existing project).
2. Copy `comfy/assets/<shot>/` into the project's `assets/` folder, keeping the shot subfolders.
3. `comfy assets push`, then reference files in blueprints as `$asset.<shot>/beauty.png`, `$asset.<shot>/mask.png`,
   `$asset.<shot>/depth.png`.
4. Ask the user before any partner-API or cloud run: it spends their Comfy credits (`comfy` requires
   `--allow-spend` for that). A free local run needs no consent flag.
5. Pull results back with `comfy download` and show frames, not paths.

## What Seam cannot take

- Alpha, masks, depth, camera data, 3D files. It re-encodes stills to RGB and works only from the first and last
  frame of each shot.
- More than 8 shots, fewer than 2, or a clip outside 1-6 s.
- A chosen output size. Aspect follows shot 1.
- A preset or length that `list_presets` does not list.

For anything that needs those inputs, use ComfyUI.

## Checks before reporting done

- Open the beauty, mask and depth for one shot and confirm the mask covers the subject only.
- Confirm `seam_sequence.json` has the shots in story order and `len(shots) - 1` segments.
- State what you submitted, what is still unsubmitted, and that no render of the AI step has happened yet if so.

## Reference Guide

| Topic | Reference | Load When |
|---|---|---|
| Seam contract, fields, limits, boundary frames | `references/seam.md` | Submitting to Seam or editing segments |
| ComfyUI layout, pass meaning, ControlNet and inpaint use | `references/comfyui.md` | Building a ComfyUI graph from the passes |

## Scripts

| Script | What it does |
|---|---|
| `scripts/render_handoff.py` | Renders Seam clips/stills and ComfyUI beauty, mask and depth passes per shot, writes the manifests, restores the scene. |
