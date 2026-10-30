"""Read a folder of reference images and write a style bible (`style_bible.json`): palette, value and
saturation histograms, contrast and warm/cool balance, per image and aggregated. Pair with
`compare_to_refs.py`, which scores renders or engine screenshots against the bible.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/ref_board.py", init_globals={"ARGS": {
        "ref_dir": "<project>/game/ref", "colors": 6}})["result"]

Colour convention (stated in the JSON too): every statistic is computed on display sRGB values in 0-1.
8-bit files (png, jpg, webp, tga) are used as stored. Float buffers (exr, 16/32-bit) are scene-linear, so a
standard sRGB transfer is applied first, which makes them comparable with 8-bit files. Pixels with alpha
below 0.5 are dropped. Luma is Rec.709 weights on the display values; saturation is HSV S; warm/cool is
chroma-weighted (red channel above blue = warm). Palette clustering runs in Oklab (perceptual) with k-means++
seeded by `seed`; each image is sampled to at most `max_pixels` opaque pixels with the same seed, so the
output is deterministic.

ARGS:
    ref_dir     (str)  folder with png/jpg/jpeg/webp/tga/exr images (required)
    out_path    (str|None) where to write the JSON (default <ref_dir>/style_bible.json)
    colors      (int)  palette size (default 6)
    max_pixels  (int)  per-image sample cap (default 20000)
    seed        (int)  sampling and k-means seed (default 0)
    recursive   (bool) also read sub-folders (default False)
"""
import json
import os
import sys

import bpy
import numpy as np

BINS = 16
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tga", ".exr")
CONVENTION = ("display sRGB 0-1 (8-bit used as stored, float buffers sRGB-encoded); alpha<0.5 dropped; "
              "luma = Rec.709 weights on display values; saturation = HSV S; palette clustered in Oklab; "
              "warm = red channel above blue, chroma-weighted")


def _cli_args():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not raw:
        return {}
    try:
        if raw[0] == "--args-file":
            if len(raw) < 2:
                raise ValueError("--args-file needs a path")
            with open(raw[1], "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(raw[0])
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"could not read ARGS JSON ({exc}); pass a JSON object or --args-file <path.json>") from None
    if not isinstance(data, dict):
        raise ValueError("ARGS must be a JSON object")
    return data


# ---- shared core begin (identical in compare_to_refs.py) ----
def _r(x, n=5):
    return round(float(x), n)


def _srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _srgb_decode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def _to_oklab(rgb):
    lin = _srgb_decode(np.asarray(rgb, dtype=np.float64))
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l_ = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return np.stack([0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
                     1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
                     0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_], axis=-1)


def _hex(rgb):
    v = np.clip(np.round(np.asarray(rgb) * 255), 0, 255).astype(int)
    return "#%02x%02x%02x" % (v[0], v[1], v[2])


def _unhex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def _read_samples(path, max_pixels, seed):
    """Load one image, return (display-sRGB samples (n, 3), info). The bpy image is always removed."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = int(img.size[0]), int(img.size[1])
        if w * h == 0:
            raise ValueError("image has no pixels (unreadable file?)")
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        is_float = bool(img.is_float)
    finally:
        bpy.data.images.remove(img)
    px = buf.reshape(-1, 4)
    px = px[px[:, 3] >= 0.5]
    rgb = px[:, :3].astype(np.float64)
    if is_float:
        rgb = _srgb_encode(rgb)
    rgb = np.clip(rgb, 0.0, 1.0)
    total_opaque = len(rgb)
    if total_opaque == 0:
        raise ValueError("no opaque pixels (alpha < 0.5 everywhere)")
    if total_opaque > max_pixels:
        idx = np.sort(np.random.default_rng(seed).choice(total_opaque, int(max_pixels), replace=False))
        rgb = rgb[idx]
    return rgb, {"width": w, "height": h, "float_buffer": is_float, "opaque_pixels": int(total_opaque)}


def _kmeans(lab, k, seed, iters=40):
    n = len(lab)
    k = max(1, min(int(k), len(np.unique(np.round(lab, 4), axis=0))))
    rng = np.random.default_rng(seed)
    centers = [lab[rng.integers(n)]]
    d2 = ((lab - centers[0]) ** 2).sum(1)
    for _ in range(1, k):
        total = d2.sum()
        if total <= 0:
            break
        i = rng.choice(n, p=d2 / total)
        centers.append(lab[i])
        d2 = np.minimum(d2, ((lab - lab[i]) ** 2).sum(1))
    c = np.array(centers)
    for _ in range(iters):
        assign = ((lab[:, None, :] - c[None, :, :]) ** 2).sum(2).argmin(1)
        new = c.copy()
        for j in range(len(c)):
            m = assign == j
            if m.any():
                new[j] = lab[m].mean(0)
        done = np.allclose(new, c, atol=1e-6)
        c = new
        if done:
            break
    return ((lab[:, None, :] - c[None, :, :]) ** 2).sum(2).argmin(1), len(c)


def _hist(values):
    h, _ = np.histogram(values, bins=BINS, range=(0.0, 1.0))
    return [_r(x) for x in h / max(1, h.sum())]


def _stats(rgb, colors, seed):
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = rgb.max(1), rgb.min(1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    chroma = mx - mn
    warm = chroma[rgb[:, 0] > rgb[:, 2]].sum()
    cool = chroma[rgb[:, 0] < rgb[:, 2]].sum()
    assign, k = _kmeans(_to_oklab(rgb), colors, seed)
    palette = []
    for j in range(k):
        m = assign == j
        if m.any():
            palette.append({"hex": _hex(rgb[m].mean(0)), "weight": _r(m.mean())})
    palette.sort(key=lambda p: -p["weight"])
    return {
        "pixels": int(len(rgb)),
        "palette": palette,
        "luma": {"mean": _r(luma.mean()), "std": _r(luma.std()), "hist": _hist(luma)},
        "saturation": {"mean": _r(sat.mean()), "std": _r(sat.std()), "hist": _hist(sat)},
        "contrast": _r(np.percentile(luma, 95) - np.percentile(luma, 5)),
        "warm_ratio": _r(warm / (warm + cool) if warm + cool > 1e-6 else 0.5),
    }
# ---- shared core end ----


def _list_images(ref_dir, recursive):
    found = []
    if recursive:
        for root, dirs, files in os.walk(ref_dir):
            dirs.sort()
            found += [os.path.join(root, f) for f in sorted(files)]
    else:
        found = [os.path.join(ref_dir, f) for f in sorted(os.listdir(ref_dir))]
    return [p for p in found if p.lower().endswith(IMAGE_EXTS) and os.path.isfile(p)
            and os.path.basename(p) != "style_bible.json"]


def main(ref_dir=None, out_path=None, colors=6, max_pixels=20000, seed=0, recursive=False):
    if not ref_dir or not os.path.isdir(ref_dir):
        raise ValueError(f"ref_dir is not a folder: {ref_dir!r}")
    colors, max_pixels, seed = int(colors), int(max_pixels), int(seed)
    if colors < 1 or max_pixels < 1:
        raise ValueError("colors and max_pixels must be >= 1")
    files = _list_images(ref_dir, bool(recursive))
    if not files:
        raise ValueError(f"no {'/'.join(IMAGE_EXTS)} images in {ref_dir}")
    out_path = out_path or os.path.join(ref_dir, "style_bible.json")

    images, skipped, pool = [], [], []
    for path in files:
        rel = os.path.relpath(path, ref_dir).replace("\\", "/")
        try:
            rgb, info = _read_samples(path, max_pixels, seed)
        except (RuntimeError, ValueError) as exc:
            skipped.append({"file": rel, "reason": str(exc).strip().splitlines()[0]})
            continue
        pool.append(rgb)
        images.append({"file": rel, **info, "stats": _stats(rgb, colors, seed)})
    if not images:
        raise ValueError(f"no readable images in {ref_dir}: {skipped}")

    agg = _stats(np.concatenate(pool), colors, seed)
    spread = {"luma_mean": _r(np.std([i["stats"]["luma"]["mean"] for i in images])),
              "saturation_mean": _r(np.std([i["stats"]["saturation"]["mean"] for i in images])),
              "contrast": _r(np.std([i["stats"]["contrast"] for i in images])),
              "warm_ratio": _r(np.std([i["stats"]["warm_ratio"] for i in images]))}
    bible = {"version": 1, "convention": CONVENTION, "bins": BINS,
             "params": {"colors": colors, "max_pixels": max_pixels, "seed": seed},
             "images": images, "skipped": skipped, "aggregate": agg, "spread_across_images": spread}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(bible, fh, indent=2)
    return {"out_path": out_path, "images_read": len(images), "skipped": skipped,
            "palette": [p["hex"] for p in agg["palette"]], "luma_mean": agg["luma"]["mean"],
            "saturation_mean": agg["saturation"]["mean"], "contrast": agg["contrast"],
            "warm_ratio": agg["warm_ratio"], "convention": CONVENTION}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
