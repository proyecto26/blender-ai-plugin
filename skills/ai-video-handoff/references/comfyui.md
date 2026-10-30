# ComfyUI handoff

`target: "comfy"` writes a folder that matches ComfyUI project/1 conventions, so the files can be copied into a
project's `assets/` folder and referenced with `$asset`.

## Layout

    <out_dir>/comfy/
      handoff.json
      assets/
        S010/beauty.png
        S010/mask.png
        S010/depth.png
        S020/...

`handoff.json` holds `size`, `fps`, `passes`, `subject`, and per shot: `id`, `frame` (the frame rendered),
`motion`, `beat`, `description`, `files` (paths relative to `assets/`), `camera` (lens, sensor, shift, clip
range, `matrix_world` 4x4) and `mist {start, depth, falloff, polarity, normalized}`.

`comfy_frame` chooses the frame per shot: `middle` (default), `start` or `end`. For image-to-video, use `start`.

## What each pass means

- `beauty.png`: opaque 8-bit RGB, in the scene's own colour management (the Blender look).
- `mask.png`: 8-bit grey. White (1) = subject coverage; black (0) = everything else. Edges are anti-aliased.
  Only the named subject objects and their children are rendered, so ground and set pieces never count and an
  object standing in front of the subject does not cut it out.
- `depth.png`: 16-bit grey, Non-Color. Built from Blender's mist pass with a linear falloff fitted to the visible
  geometry (or `mist_range`). Value 0 = at or before `start`, 1 = at `start + depth` or beyond (the sky is 1).
  Normalized, not metric. The default polarity is `near_is_black`. With `depth_near_white: true` it is inverted
  and the polarity is `near_is_white`.

Load `mask.png` and `depth.png` with a loader that does not apply sRGB conversion (ComfyUI's LoadImage plus
"Image to Mask" with channel red works; 16-bit depth may be read as 8-bit by some loaders, which is acceptable for
ControlNet).

## Using the passes

- **Depth ControlNet**: most depth ControlNets (MiDaS, Depth Anything style) expect near = white. Render with
  `depth_near_white: true`, or invert in the graph, then feed the image straight to the ControlNet apply node. The
  depth is already a depth map, so skip the preprocessor.
- **Background around the subject (inpaint)**: invert the mask so the background is the area to generate; feed the
  beauty as the image and the inverted mask as the inpaint mask, with a prompt describing the environment. Grow the
  mask by a few pixels so the seam is repainted. Then composite the original beauty over the result with the
  un-inverted mask to keep the subject identical.
- **Image to video**: use the composite (or beauty) as the start frame. Keep the camera locked; the Blender
  camera data is for reference, ComfyUI nodes do not read it.
- **Consistency**: use one size for every shot (the script enforces it) so graphs can be reused across shots.

## Submitting

Use the `comfy` skill and CLI; this skill does not run them.

1. `comfy project init` (once per project).
2. Copy `assets/<shot>/` folders into the project `assets/` folder.
3. `comfy assets push`; reference as `$asset.S010/beauty.png`, `$asset.S010/mask.png`, `$asset.S010/depth.png`.
   Blueprints take `$asset.<relative/path>` as a whole value only (no string interpolation).
4. Survey templates and models first (`comfy templates ls`, `comfy knowledge pick`); do not hardcode model names.
5. Ask the user before any partner-API or cloud run; it spends Comfy credits and needs `--allow-spend`. Local runs
   with open models are free.
6. For a multi-shot narrative with continuity, read the `comfy-director` skill.
