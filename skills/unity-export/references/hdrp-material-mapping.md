# HDRP material mapping

For Unity's High Definition Render Pipeline (HDRP) Lit shader. `unity-materials.md` is the short general note; this file is
the channel table and a tested packing recipe.

## Mask map channels (from Unity's documentation)

Source: https://docs.unity3d.com/Packages/com.unity.render-pipelines.high-definition@17.0/manual/Mask-Map-and-Detail-Map.html
(page for HDRP 17.0; check the page for your version.)

| Channel | Mask map holds | Detail map holds |
|---|---|---|
| R | Metallic | Desaturated albedo |
| G | Ambient occlusion | Normal Y |
| B | Detail mask | Smoothness |
| A | Smoothness | Normal X |

Unity's page uses smoothness throughout and does not mention roughness. This is not the Unreal ORM order in
`texture-workflow` -> `references/orm-packing.md` (R occlusion, G roughness, B metallic): a map packed for Unreal puts the wrong
data in each channel under HDRP. The orm-packing note that "some Unity shaders use Metallic(R) + AO(B)" does not hold for the HDRP
mask map, whose AO is in G.

## Blender to HDRP

| Blender source | HDRP slot | Notes |
|---|---|---|
| Base Color | Base Map | colour texture (sRGB) |
| Metallic | Mask map R | grayscale |
| Baked AO | Mask map G | grayscale |
| none (or a painted detail mask) | Mask map B | white when you do not use a detail mask |
| Roughness | Mask map A, inverted | smoothness is the inverse of roughness: `smoothness = 1 - roughness` |
| Normal | Normal Map | texture type Normal Map in Unity |

The inversion and the linear import come from third-party guidance, not Unity's page:
https://aitextured.com/articles/guides/unity-hdrp-mask-map-from-pbr-texture-set/ states to invert roughness before placing
it in alpha, to fill blue with white when no detail mask is used, and to import the mask map with sRGB disabled. Confirm it in
Unity with one known value: a material of roughness 0.2 should read smoothness 0.8.

Normal-map green-channel convention is not covered here: check a lit preview of the first import.

## Packing recipe (tested)

Packs three grayscale images into one RGBA image in the HDRP mask-map order, inside Blender and in memory (nothing is written
to disk). It makes small test images, checks pixel values (including the inversion and the white detail mask) and raises on
any mismatch. To save a real map, set the image's file path and `save()` it as 8 or 16 bit PNG, and import it in Unity with
sRGB off. Writing files is not part of this recipe.

```python
import bpy
import numpy as np

W = H = 4
for name in ("T_metal", "T_ao", "T_rough", "T_Test_MaskMap"):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)

def gray(name, array):
    img = bpy.data.images.new(name, W, H, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = array[..., None]
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    return img

def read_channel(name, channel=0):
    img = bpy.data.images[name]
    px = np.empty(W * H * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(H, W, 4)[..., channel]

def pack_mask_map(name, metal, ao, rough, detail=None):
    """R metallic, G ambient occlusion, B detail mask (white if none), A smoothness = 1 - roughness."""
    out = bpy.data.images.new(name, W, H, alpha=True, float_buffer=True)
    out.colorspace_settings.name = "Non-Color"
    px = np.empty((H, W, 4), dtype=np.float32)
    px[..., 0] = read_channel(metal)
    px[..., 1] = read_channel(ao)
    px[..., 2] = 1.0 if detail is None else read_channel(detail)
    px[..., 3] = 1.0 - read_channel(rough)
    out.pixels.foreach_set(px.ravel())
    out.update()
    return out

metal = np.zeros((H, W), np.float32)
metal[:, : W // 2] = 1.0                      # left half metal
ao = np.full((H, W), 0.5, np.float32)
rough = np.full((H, W), 0.2, np.float32)
rough[0, :] = 0.9                             # top row rough
gray("T_metal", metal)
gray("T_ao", ao)
gray("T_rough", rough)
mask = pack_mask_map("T_Test_MaskMap", "T_metal", "T_ao", "T_rough")

px = np.empty(W * H * 4, dtype=np.float32)
mask.pixels.foreach_get(px)
px = px.reshape(H, W, 4)
assert np.allclose(px[..., 0], metal), "R is not metallic"
assert np.allclose(px[..., 1], 0.5), "G is not ambient occlusion"
assert np.allclose(px[..., 2], 1.0), "B is not white when no detail mask is given"
assert np.allclose(px[1:, :, 3], 0.8, atol=1e-6) and np.allclose(px[0, :, 3], 0.1, atol=1e-6), "A is not 1 - roughness"
assert mask.colorspace_settings.name == "Non-Color"
for name in ("T_metal", "T_ao", "T_rough"):
    bpy.data.images.remove(bpy.data.images[name])
result = {"mask_map": mask.name, "alpha_rough_row": float(px[0, 0, 3]), "alpha_other": float(px[1, 0, 3]),
          "colorspace": mask.colorspace_settings.name}
```

Result when run on Blender 5.2.3: alpha reads 0.8 where roughness was 0.2 and 0.1 where it was 0.9; the image colour space is
Non-Color.

What the checks prove: the channel order and the inversion are what this file says. They do not prove how a given Unity
version reads the map; confirm with the known-value test above.

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Surface too shiny where it should be rough (or reverse) | roughness put in alpha without inversion | pack `1 - roughness` |
| Metal reads dark and non-metal reads shiny | ORM order used | repack in mask-map order |
| Mask map looks washed out or the wrong brightness | imported as sRGB | turn sRGB off for the mask map |
| Whole surface shows a detail pattern or none at all | blue channel not set as intended | fill white if no detail mask |
