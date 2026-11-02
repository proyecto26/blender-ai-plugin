# Substance Painter hand-off

`scripts/import_painter_textures.py` turns a folder of exported texture maps into one Blender material.

## What is and is not tested

- Tested (`tests/blender/test_roadmap.py`, R4): synthetic PNG files with names such as `Crate_BaseColor.png`,
  `Crate_Roughness.png`, `Crate_Normal.png`, written by the test itself. It checks which socket each file reaches, the
  colour space set on each image, the DirectX green flip structure, the packed ORM split, and the refusals.
- **Substance 3D Painter itself was not run.** No file in the tests came out of Painter.
- **No claim is made here about what names, packing or normal convention Painter's export templates produce.** The Adobe
  documentation pages for export presets and output templates
  (https://helpx.adobe.com/substance-3d-painter/getting-started/export/export-presets/default-presets.html and
  https://helpx.adobe.com/substance-3d-painter/getting-started/export/export-window/output-templates.html) answered
  HTTP 403 when fetched during this work, so nothing could be checked against them. They are listed as where to look,
  not as sources for any statement in this file.

Because of that the script matches generic keywords in file names, and you tell it the rest.

## Matching rules

| Kind | Keywords (any one in the file name) | Goes to | Colour space |
|------|--------------------------------------|---------|--------------|
| `orm` | `orm` as a whole word, `occlusionroughnessmetallic` | Roughness from G, Metallic from B | Non-Color |
| `base_color` | `basecolor`, `base_color`, `base-color`, `albedo`, `diffuse`, `color`, `colour` | Base Color | sRGB |
| `roughness` | `roughness`, `rough` | Roughness | Non-Color |
| `metallic` | `metallic`, `metalness`, `metal` | Metallic | Non-Color |
| `normal` | `normal`, `nrm`, `nor` (whole word) | Normal Map, then Normal | Non-Color |
| `height` | `height`, `displacement`, `disp` (whole word), `bump` | Bump (Height), then Normal | Non-Color |
| `ao` | `ambientocclusion`, `ambient_occlusion`, `occlusion`, `ao` (whole word) | skipped unless `ao: "multiply"` | Non-Color |
| `emissive` | `emissive`, `emission`, `emit` (whole word) | Emission Color | sRGB |
| `opacity` | `opacity`, `alpha`, `transparency` | Alpha | Non-Color |

Words of four characters or fewer match whole name parts only, so `orm` does not fire inside `Normal`. If your files use
other words, pass `patterns`, for example `{"roughness": ["rgh"]}`. Run once and read `files`, `unmatched` and
`ambiguous` before trusting the material: two files of one kind keep the first in name order and report the other.

## Settings you must decide

- **Normal convention.** The script cannot tell from a file whether its green channel points up or down. Set
  `normal_convention` to `OPENGL` (Blender's own, no change) or `DIRECTX` (inserts a green invert before the Normal Map
  node). Look at your export settings, or look at a bump on the model: if the lighting on it looks inverted vertically,
  flip the setting.
- **AO** is skipped by default, in line with the texture-workflow rule not to bake AO into base colour. `multiply` exists
  for a quick look only.
- **Height** goes through a Bump node (`height_strength`, default 0.5). It is not true displacement.
- **UDIM** tile files (`name.1001.png`) are listed in `skipped_udim` and not wired.
- **Alpha blend mode** of the material is not changed: set it yourself if opacity is used.

## Checklist after import

- [ ] `unmatched` empty, or each entry understood
- [ ] Normal looks right under a moving light (convention)
- [ ] Roughness and metallic images are Non-Color
- [ ] Material assigned and the UV set is the one the textures were painted on
- [ ] Textures packed or copied next to the .blend (`pack: true` packs them)
