# Reference-Folder-First Workflow

Use this when a user builds a world, level or prop set for a game (or any multi-asset scene) and has, or can
collect, a folder of reference images. A folder of 10 good refs beats 10 paragraphs of vibes: refs first is
what keeps the style consistent across props, lighting and engine.

Single-image matching (one photo, one asset) is `reference-image-match.md`. This file is for a **folder** that
governs many assets, and for checking the result **in the engine**, not just in Blender.

## The loop

```
1 REFS      put images in a folder (e.g. game/ref/)
2 BOARD     ref_board.py -> style_bible.json; READ the images yourself; write a short style brief
3 PROPS     model in Blender (right skills), capture, compare_to_refs.py, fix drift
4 EXPORT    godot-export / export-pipeline
5 WORLD     build the level in the engine through ITS OWN MCP (outside this plugin), walk through it, capture
6 COMPARE   compare_to_refs.py on the walk-through screenshots, fix drift; stop after two flat rounds
```

### 1. Refs

One folder, png/jpg/jpeg/webp/tga/exr, names that say what they show (`forest_floor_dusk.png`,
`ruin_wall_moss.jpg`). Mix wide mood shots with close material shots. Sub-folders only with `"recursive": true`.
Do not mix in other styles "for contrast": the statistics average everything in the folder.

### 2. Board and brief

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/ref_board.py", init_globals={"ARGS": {"ref_dir": "<project>/game/ref", "colors": 6}})["result"]
```

Writes `<project>/game/ref/style_bible.json` and returns the palette, mean value (luma), mean saturation, contrast and
warm/cool ratio. **Then look at the images yourself** (open them or ask the user which matter most). The
statistics describe colour and tonal balance only. They say nothing about composition, silhouette language,
shape density, scale or what the images are *of*. Write a 5-8 line style brief from both:

- palette: the hexes, which are dominant, which is the accent
- value: dark/mid/light balance, how contrasty
- saturation and warm/cool bias
- shape language, materials, lighting direction, mood (from your reading of the images)

Show the brief to the user and get a yes before building. It is the contract the later comparisons enforce.

### 3. Props in Blender

Build each prop with the matching skills (blockout, materials, lighting). Keep material colours inside the
palette. Capture a render or viewport shot of the prop in a neutral lit scene and check it:

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/compare_to_refs.py", init_globals={"ARGS": {
    "bible": "<project>/game/ref/style_bible.json", "captures": ["<project>/game/work/crate_render.png"]}})["result"]
```

Read `drift` (plain-language findings such as `too saturated (+0.18 S vs refs)`, `values too bright`,
`palette missing warm accent ~#c86b3a`) and `score`. A single prop on a grey background will show palette
drift simply because most of the frame is background: judge the prop's own colours (`capture_palette`),
or crop the capture first. Fix the material, re-capture.

### 4. Export

Follow the engine skill (`godot-export` for Godot). Run `validate_asset.py` before exporting.

### 5. World in the engine

Blender does not drive the engine. Use the engine's own MCP or editor tooling (for Godot, a Godot MCP server
installed separately) to assemble the level with the exported props and lighting. Then walk through it with
a scripted or manual camera and save screenshots at the key spots: establishing view, a close material
view, the darkest and brightest areas. 4-8 shots cover most of it.

### 6. Compare the engine captures

Pass the screenshot paths to `compare_to_refs.py` the same way as in step 3. Typical drift and fixes:

| Finding | Usual fix |
|---------|-----------|
| too saturated / desaturated | material albedo, post-process saturation, fog tint |
| values too bright / dark | light energy, exposure, tonemap, ambient/sky |
| too flat (low contrast) | key-to-fill ratio, fog density, tonemap curve |
| too warm / cool | light colour temperature, sky/fog colour |
| palette missing accent | add or recolour the accent props (lanterns, flowers, signage) |
| off-palette colour | find the prop or light producing it and retint |

Make one class of change per round (all lighting, or all materials), recapture the same shots, compare again.
**Stop after two consecutive rounds with no improvement** in `score` and the drift list, then report what was
tried, what still drifts, and your best hypothesis. Do not loop forever on a metric the refs themselves do not
settle (for example when refs vary widely, the tolerances already widen to the spread across refs).

## What the numbers mean

- **Colour convention.** Display sRGB 0-1. 8-bit files are used as stored; float buffers (EXR, 16-bit) get a
  standard sRGB transfer so they compare with 8-bit screenshots. Alpha below 0.5 is dropped. The convention
  string is written into `style_bible.json`.
- **Palette.** k-means in Oklab (perceptual), seeded, `colors` clusters, each with a weight. Distances are
  Oklab distances (about 0.02 is barely visible, 0.1 is clearly different).
- **Value / saturation histograms.** 16 bins; compared by earth mover's distance (0 = same shape).
- **Contrast.** 95th minus 5th percentile of luma. **Warm ratio.** Chroma-weighted share of pixels with red
  above blue (0.5 is neutral).
- **Sampling.** Each image is capped at `max_pixels` (default 20000) opaque pixels with a fixed `seed`, so two
  runs on the same files give identical JSON. Captures use the bible's own seed, cap and palette size.
- **Score.** 1.0 identical; roughly 0.67 when every metric sits at its tolerance; the verdict is `match` only
  when the drift list is empty. The drift list, not the score, is what you act on.
- **Tolerances.** Override per metric with `"tolerances": {"saturation_mean": 0.05}`. Keys: luma_mean,
  saturation_mean, contrast, warm_ratio, palette, palette_missing, luma_hist, saturation_hist.

## Limits

- Statistics do not see composition, shapes, texture detail or mood. Always look at the captures too.
- Engine tonemapping, fog and post-processing change the numbers: compare engine screenshots with engine
  screenshots of the refs' intent, not with raw albedo renders.
- Keep captures at similar framing across rounds. A different crop changes every statistic.
