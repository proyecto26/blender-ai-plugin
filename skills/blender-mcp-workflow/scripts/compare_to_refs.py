"""Compare captures (Blender renders, viewport captures, Godot or other engine screenshots) against the
`style_bible.json` written by `ref_board.py`. Returns per-metric distances, an overall score and a drift
list of plain-language findings with direction.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/compare_to_refs.py", init_globals={"ARGS": {
        "bible": "<project>/game/ref/style_bible.json", "captures": ["<project>/game/shots/walk_01.png"]}})["result"]

Captures are read with the same colour convention and sampling as the bible (display sRGB 0-1, float buffers
sRGB-encoded, alpha<0.5 dropped, same seed / max_pixels / palette size taken from the bible), pooled, and
compared with the bible's aggregate. Distances: palette = mean nearest-colour distance in Oklab, averaged
both ways (capture to refs, refs to capture); histograms = 1-D earth mover's distance on the 16 bins, in
units of the 0-1 range; scalars = capture minus refs. A scalar tolerance is widened to 1.5x the spread seen
across the reference images themselves, so varied refs are not over-policed. Score: 1.0 = identical, falls
with each metric's distance divided by its tolerance; verdict is "match" when the drift list is empty.

ARGS:
    bible       (str)  path to style_bible.json (required)
    captures    (list[str]|str) image paths to check (required)
    tolerances  (dict|None) overrides; keys: luma_mean, saturation_mean, contrast, warm_ratio, palette,
                palette_missing, luma_hist, saturation_hist (defaults 0.10, 0.10, 0.15, 0.15, 0.08, 0.12,
                0.06, 0.06)
"""
import json
import os
import sys

import bpy
import numpy as np

BINS = 16
DEFAULT_TOL = {"luma_mean": 0.10, "saturation_mean": 0.10, "contrast": 0.15, "warm_ratio": 0.15,
               "palette": 0.08, "palette_missing": 0.12, "luma_hist": 0.06, "saturation_hist": 0.06}


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


# ---- shared core begin (identical in ref_board.py) ----
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


def _emd(h1, h2):
    c = np.cumsum(np.asarray(h1)) - np.cumsum(np.asarray(h2))
    return float(np.abs(c).sum() / len(h1))


def _palette_distance(cap_pal, ref_pal):
    """Weighted mean nearest-colour Oklab distance, both directions. Returns (mean, cap_to_ref, ref_to_cap, matrix)."""
    cl = _to_oklab(np.array([_unhex(p["hex"]) for p in cap_pal]))
    rl = _to_oklab(np.array([_unhex(p["hex"]) for p in ref_pal]))
    d = np.sqrt(((cl[:, None, :] - rl[None, :, :]) ** 2).sum(2))
    cw = np.array([p["weight"] for p in cap_pal])
    rw = np.array([p["weight"] for p in ref_pal])
    c2r = float((d.min(1) * cw).sum() / cw.sum())
    r2c = float((d.min(0) * rw).sum() / rw.sum())
    return (c2r + r2c) / 2, c2r, r2c, d


def _distances(cap, ref):
    pal, c2r, r2c, d = _palette_distance(cap["palette"], ref["palette"])
    return {"palette": pal, "palette_capture_to_refs": c2r, "palette_refs_to_capture": r2c,
            "luma_hist": _emd(cap["luma"]["hist"], ref["luma"]["hist"]),
            "saturation_hist": _emd(cap["saturation"]["hist"], ref["saturation"]["hist"]),
            "luma_mean": cap["luma"]["mean"] - ref["luma"]["mean"],
            "saturation_mean": cap["saturation"]["mean"] - ref["saturation"]["mean"],
            "contrast": cap["contrast"] - ref["contrast"],
            "warm_ratio": cap["warm_ratio"] - ref["warm_ratio"]}, d


def _score(dist, tol):
    keys = ["palette", "luma_hist", "saturation_hist", "luma_mean", "saturation_mean", "contrast", "warm_ratio"]
    parts = [min(abs(dist[k]) / (3 * tol[k]), 1.0) for k in keys]
    return max(0.0, 1.0 - sum(parts) / len(parts))


def _warmth(hexcol):
    c = _unhex(hexcol)
    return "warm" if c[0] > c[2] else "cool"


def main(bible=None, captures=None, tolerances=None):
    if not bible or not os.path.isfile(bible):
        raise ValueError(f"bible not found: {bible!r} (run ref_board.py first)")
    if isinstance(captures, str):
        captures = [captures]
    if not captures:
        raise ValueError("captures must be a non-empty list of image paths")
    with open(bible, "r", encoding="utf-8") as fh:
        ref_doc = json.load(fh)
    if ref_doc.get("version") != 1 or "aggregate" not in ref_doc:
        raise ValueError("not a style bible written by ref_board.py (version 1)")
    ref = ref_doc["aggregate"]
    p = ref_doc["params"]
    tol = dict(DEFAULT_TOL)
    tol.update({k: float(v) for k, v in (tolerances or {}).items() if k in DEFAULT_TOL})
    spread = ref_doc.get("spread_across_images", {})
    for k in ("luma_mean", "saturation_mean", "contrast", "warm_ratio"):
        if k not in (tolerances or {}):
            tol[k] = max(tol[k], 1.5 * float(spread.get(k, 0.0)))

    per_capture, pool, skipped = [], [], []
    for path in captures:
        try:
            rgb, info = _read_samples(path, p["max_pixels"], p["seed"])
        except (RuntimeError, ValueError) as exc:
            skipped.append({"file": path, "reason": str(exc).strip().splitlines()[0]})
            continue
        pool.append(rgb)
        st = _stats(rgb, p["colors"], p["seed"])
        dist, _ = _distances(st, ref)
        per_capture.append({"file": path, "width": info["width"], "height": info["height"],
                            "score": _r(_score(dist, tol)), "palette": [q["hex"] for q in st["palette"]],
                            "luma_mean": st["luma"]["mean"], "saturation_mean": st["saturation"]["mean"]})
    if not pool:
        raise ValueError(f"no readable captures: {skipped}")

    cap = _stats(np.concatenate(pool), p["colors"], p["seed"])
    dist, d = _distances(cap, ref)
    drift = []

    def flag(key, label_hi, label_lo, unit):
        v = dist[key]
        if abs(v) > tol[key]:
            drift.append({"metric": key, "delta": _r(v), "tolerance": _r(tol[key]),
                          "finding": f"{label_hi if v > 0 else label_lo} ({v:+.2f} {unit} vs refs)"})

    flag("saturation_mean", "too saturated", "too desaturated", "S")
    flag("luma_mean", "values too bright", "values too dark", "luma")
    flag("contrast", "too contrasty", "too flat (low contrast)", "p95-p05 luma")
    flag("warm_ratio", "too warm", "too cool", "warm ratio")
    for key, name in (("luma_hist", "value distribution"), ("saturation_hist", "saturation distribution")):
        mean_key = "luma_mean" if key == "luma_hist" else "saturation_mean"
        if dist[key] > tol[key] and abs(dist[mean_key]) <= tol[mean_key]:
            drift.append({"metric": key, "delta": _r(dist[key]), "tolerance": _r(tol[key]),
                          "finding": f"{name} differs from refs (EMD {dist[key]:.2f}) at a similar mean"})
    # palette: ref colours the capture lacks, capture colours the refs lack
    for j, q in enumerate(ref["palette"]):
        if q["weight"] >= 0.05 and d[:, j].min() > tol["palette_missing"]:
            kind = "accent" if q["weight"] < 0.25 else "colour"
            drift.append({"metric": "palette_missing", "delta": _r(d[:, j].min()),
                          "tolerance": _r(tol["palette_missing"]),
                          "finding": f"palette missing {_warmth(q['hex'])} {kind} ~{q['hex']} "
                                     f"({q['weight'] * 100:.0f}% of refs)"})
    for i, q in enumerate(cap["palette"]):
        if q["weight"] >= 0.10 and d[i, :].min() > tol["palette_missing"]:
            drift.append({"metric": "palette_extra", "delta": _r(d[i, :].min()),
                          "tolerance": _r(tol["palette_missing"]),
                          "finding": f"off-palette {_warmth(q['hex'])} colour ~{q['hex']} "
                                     f"({q['weight'] * 100:.0f}% of capture)"})

    return {"score": _r(_score(dist, tol)), "verdict": "match" if not drift else "drift",
            "distances": {k: _r(v) for k, v in dist.items()},
            "tolerances": {k: _r(v) for k, v in tol.items()},
            "capture_palette": [q["hex"] for q in cap["palette"]], "ref_palette": [q["hex"] for q in ref["palette"]],
            "drift": [x["finding"] for x in drift], "drift_detail": drift,
            "per_capture": per_capture, "skipped": skipped, "convention": ref_doc.get("convention")}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
