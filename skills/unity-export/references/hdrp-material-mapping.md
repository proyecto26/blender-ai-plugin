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

The linear import rule is in Unity's page: it says to disable sRGB (Color Texture) in the Image Importer Inspector when importing
the texture, and to build the mask map as a linear composited map
(https://docs.unity3d.com/Packages/com.unity.render-pipelines.high-definition@17.0/manual/Mask-Map-and-Detail-Map.html, read for this
revision). The same page does not mention inverting roughness, and it does not say what to put in blue when there is no detail
mask (it only says blue is the detail mask: 1 shows the detail, 0 masks it). Those two come from third-party guidance:
https://aitextured.com/articles/guides/unity-hdrp-mask-map-from-pbr-texture-set/ states to invert roughness before placing
it in alpha and to fill blue with white when no detail mask is used. Confirm it in
Unity with one known value: a material of roughness 0.2 should read smoothness 0.8.

Normal-map green-channel convention is not covered here: check a lit preview of the first import.

## Saving the map: use an 8-bit byte image, never a float image

Do not call `save()` (or `save_render()`) on the float image the packing step builds. Blender keeps a float image's
colour premultiplied by alpha, so when it writes a PNG it divides RGB by alpha. With smoothness in alpha, that corrupts
metallic and occlusion wherever the surface is not fully smooth. Measured by decoding the PNG bytes (`zlib`, PNG filters
undone) for a pixel packed with R 0.25, G (occlusion) 0.5, B 1.0:

| Route (Blender 5.2.3) | Depth written | G at A 0.8 | G at A 0.1 | At A 0.0 |
|---|---|---|---|---|
| float image, `save()` | 16 | 0.625 | 1.0 (clipped) | not run |
| float image, `alpha_mode` STRAIGHT / PREMUL / CHANNEL_PACKED / NONE, `save()` | 16 | 0.625 | 1.0 | not run |
| float image, `save_render()`, scene depth 8 | 8 | 0.624 | 1.0 | not run |
| float image, `save_render()`, scene depth 16, Raw or Standard view | 16 | 0.625 | 1.0 | not run |
| byte image (`float_buffer=False`), `save_render()` at scene depth 16 | 16 | 0.627 | 1.0 | not run |
| float image with RGB pre-multiplied by A first, `save_render()` depth 16 | 16 | 0.5 | 0.5 | R, G, B all 0 (lost) |
| byte image (`float_buffer=False`), `save()` | 8 | 0.502 | 0.502 | 0.502 |
| byte image, `save_render()` at scene depth 8 | 8 | 0.502 | 0.502 | not run |
| PNG written by the recipe's own `write_png16` | 16 | 0.5 | 0.5 | 0.5 |

`alpha_mode` changed nothing on any route. `bpy.ops.image.save_as` takes no depth argument here, so it was not a route.

What follows:

- **Through Blender's own PNG writer the only correct route is 8 bit**: a `float_buffer=False` image saved with `save()`.
  What is lost is precision: each channel has 256 levels (0.5 is stored as 128/255 = 0.502, so a value can move by half a
  level). Metallic is usually 0 or 1 and 256 smoothness levels are normally enough; if you need more, use the next route.
- **No 16-bit route through Blender keeps RGB independent of alpha.** Pre-multiplying RGB by alpha cancels the division at
  A 0.1 but destroys RGB at A 0.0 (fully rough), so it is not a route either.
- **A correct 16-bit file is possible by writing the PNG yourself.** `write_png16` in the recipe (standard library and
  numpy only) stores the straight RGBA values with no colour management and no premultiplication. Its output was verified
  by decoding the bytes.
- Blender's PNG writer tags the 8-bit file as sRGB (`sRGB`, `gAMA` and `cHRM` chunks) whatever the image's colour
  space, Non-Color included; this was seen on Windows and macOS with Blender 5.2.3. `write_png16` writes no colour
  chunk. So import the map in Unity with sRGB off: that setting, not the file, decides how it is read. A tool that
  honours the chunks could read the 8-bit map as sRGB; the Unity import itself was not tested. Whether a given Unity version keeps 16 bits of a PNG on import was not checked; the 8-bit file is the
  one to rely on.

## Packing recipe (tested)

Packs three grayscale images into one RGBA map in the HDRP mask-map order, then saves it two ways and checks the files.
It makes small test images, checks the packed pixel values (including the inversion and the white detail mask), writes
`recipe_hdrp_maskmap_8bit.png` (Blender's writer, 8 bit) and `recipe_hdrp_maskmap_16bit.png` (`write_png16`) into
Blender's temp folder, decodes both files' bytes, and compares every pixel with the packed values at smoothness 0.1, 0.8,
0.5 and 0.0. It raises on any mismatch. The two files are overwritten on a re-run and never deleted by the recipe.
Everything it creates in Blender carries a `recipe_owner` tag; re-running removes only tagged images from an earlier run,
and images of yours with the same names are left alone (the recipe's copies get a `.001` suffix). To keep a map, change
`OUT_DIR` to your folder.

```python
import os
import struct
import tempfile
import zlib

import bpy
import numpy as np

W = H = 4
OUT_DIR = bpy.app.tempdir or tempfile.gettempdir()
# Remove only images this recipe tagged on an earlier run; the recipe holds image references and never looks up by name.
TAG, OWNER = "recipe_owner", "hdrp-material-mapping"
for stale in [i for i in bpy.data.images if i.get(TAG) == OWNER]:
    bpy.data.images.remove(stale)

def gray(name, array):
    img = bpy.data.images.new(name, W, H, alpha=False, float_buffer=True)
    img[TAG] = OWNER
    img.colorspace_settings.name = "Non-Color"
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = array[..., None]
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    return img

def read_channel(img, channel=0):
    px = np.empty(W * H * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(H, W, 4)[..., channel]

def pack_mask_map(name, metal, ao, rough, detail=None):
    """R metallic, G ambient occlusion, B detail mask (white if none), A smoothness = 1 - roughness."""
    out = bpy.data.images.new(name, W, H, alpha=True, float_buffer=True)
    out[TAG] = OWNER
    out.colorspace_settings.name = "Non-Color"
    px = np.empty((H, W, 4), dtype=np.float32)
    px[..., 0] = read_channel(metal)
    px[..., 1] = read_channel(ao)
    px[..., 2] = 1.0 if detail is None else read_channel(detail)
    px[..., 3] = 1.0 - read_channel(rough)
    out.pixels.foreach_set(px.ravel())
    out.update()
    return out

def save_8bit(src, path):
    """Blender's writer, 8 bit. A BYTE image keeps RGB independent of alpha; a float image would not (see the table)."""
    px = np.empty(W * H * 4, dtype=np.float32)
    src.pixels.foreach_get(px)
    img = bpy.data.images.new(src.name + "_8bit", W, H, alpha=True, float_buffer=False)
    img[TAG] = OWNER
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(px)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)

def write_png16(src, path):
    """16-bit RGBA PNG written directly: straight (not premultiplied) values, no colour management."""
    px = np.empty(W * H * 4, dtype=np.float32)
    src.pixels.foreach_get(px)
    top_first = px.reshape(H, W, 4)[::-1]  # PNG rows run top to bottom, Blender's bottom to top
    q = np.clip(np.rint(top_first.astype(np.float64) * 65535), 0, 65535).astype(">u2")
    raw = b"".join(b"\x00" + q[y].tobytes() for y in range(H))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 16, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def decode_png(path):
    """Decode an RGBA PNG's bytes (8 or 16 bit, all five filter types) to floats, bottom row first like Blender."""
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, head = 8, b"", None
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + size]
        pos += 12 + size
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
    w, h, depth, ctype = head[:4]
    assert (w, h, ctype) == (W, H, 6), f"expected {W}x{H} RGBA, got {w}x{h} colour type {ctype}"
    bpp, stride, raw = 4 * depth // 8, W * 4 * depth // 8, zlib.decompress(idat)
    rows, prev = [], bytearray(stride)
    for y in range(h):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + a) & 255
            elif kind == 2:
                line[i] = (line[i] + b) & 255
            elif kind == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif kind == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        rows.append(bytes(line))
        prev = line
    dtype, scale = (np.uint8, 255.0) if depth == 8 else (">u2", 65535.0)
    arr = np.frombuffer(b"".join(rows), dtype).astype(np.float64) / scale
    return depth, arr.reshape(H, W, 4)[::-1]

metal = np.zeros((H, W), np.float32)
metal[:, : W // 2] = 1.0                      # left half metal
ao = np.full((H, W), 0.5, np.float32)
rough = np.zeros((H, W), np.float32)
rough[0, :], rough[1, :], rough[2, :], rough[3, :] = 0.9, 0.2, 0.5, 1.0   # smoothness 0.1, 0.8, 0.5, 0.0
img_metal = gray("T_metal", metal)
img_ao = gray("T_ao", ao)
img_rough = gray("T_rough", rough)
mask = pack_mask_map("T_Test_MaskMap", img_metal, img_ao, img_rough)

px = np.empty(W * H * 4, dtype=np.float32)
mask.pixels.foreach_get(px)
px = px.reshape(H, W, 4)
assert np.allclose(px[..., 0], metal), "R is not metallic"
assert np.allclose(px[..., 1], 0.5), "G is not ambient occlusion"
assert np.allclose(px[..., 2], 1.0), "B is not white when no detail mask is given"
assert np.allclose(px[..., 3], 1.0 - rough, atol=1e-6), "A is not 1 - roughness"
assert mask.colorspace_settings.name == "Non-Color"

# Save both ways, then decode the FILE BYTES (not a reload in Blender) and compare with what was packed.
path8 = os.path.join(OUT_DIR, "recipe_hdrp_maskmap_8bit.png")
path16 = os.path.join(OUT_DIR, "recipe_hdrp_maskmap_16bit.png")
save_8bit(mask, path8)
write_png16(mask, path16)
file_error = {}
for label, path, depth_expected in (("8bit", path8, 8), ("16bit", path16, 16)):
    depth, dec = decode_png(path)
    assert depth == depth_expected, f"{label}: file is {depth} bit"
    file_error[label] = float(np.abs(dec - px).max())
    limit = (0.5 / 255 if depth == 8 else 0.5 / 65535) + 1e-6
    for row, alpha in enumerate((0.1, 0.8, 0.5, 0.0)):
        assert np.allclose(dec[row, :, 3], alpha, atol=limit), f"{label}: alpha row {row} is not {alpha}"
        assert np.abs(dec[row, :, :3] - px[row, :, :3]).max() <= limit, \
            f"{label}: RGB changed at alpha {alpha} (occlusion reads {dec[row, 0, 1]:.3f}, packed 0.5)"
for img in (img_metal, img_ao, img_rough):
    bpy.data.images.remove(img)
result = {"mask_map": mask.name, "alpha_rough_row": float(px[0, 0, 3]), "alpha_other": float(px[1, 0, 3]),
          "colorspace": mask.colorspace_settings.name, "max_error_in_file": file_error,
          "files": [path8, path16]}
```

Result when run on Blender 5.2.3: alpha reads 0.8 where roughness was 0.2 and 0.1 where it was 0.9 (0.5 and 0.0 on the
other two rows); the image colour space is Non-Color. the largest difference between a decoded file and the packed values is 0.0020 (half an 8-bit level) in the 8-bit file and 0.000008 in the 16-bit file, at every alpha including 0.1 and 0.0.

What the checks prove: the channel order and the inversion are what this file says, and the two saved files hold those
values at every alpha tested. They do not prove how a given Unity version reads the map: nothing here was run in Unity;
confirm with the known-value test above.

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Surface too shiny where it should be rough (or reverse) | roughness put in alpha without inversion | pack `1 - roughness` |
| Metal reads dark and non-metal reads shiny | ORM order used | repack in mask-map order |
| Mask map looks washed out or the wrong brightness | imported as sRGB | turn sRGB off for the mask map |
| Whole surface shows a detail pattern or none at all | blue channel not set as intended | fill white if no detail mask |
| Occlusion or metallic brighter than packed where the surface is not fully smooth | the map was saved from a float image, so RGB was divided by alpha | save a `float_buffer=False` image, or use `write_png16` |
