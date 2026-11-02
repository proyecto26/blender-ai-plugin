"""Temporal flicker check on a rendered image sequence: finds frames and regions whose brightness jumps against
their neighbours, without mistaking motion for flicker. Read-only.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/flicker_check.py",
                            init_globals={"ARGS": {"dir": "<project>/renders/S010"}})["result"]

ARGS:
    paths               (list[str]) frame images in playing order; or
    dir                 (str) a folder of frames, read in natural filename order (use one of paths / dir)
    block               (int)   block size in px (default 16)
    max_motion_px       (int)   search window: a block may move up to this many px in x and y between
                        consecutive frames (default 8). Cost grows with its square.
    flicker_threshold   (float) a block flickers when its mean differs from the average of its motion-matched
                        previous and next blocks by more than this (default 0.03, on 0..1 encoded values)
    reject_ratio        (float) match rejection: the best match is rejected when its residual (mean absolute
                        difference after removing each block's mean) exceeds max(0.01, reject_ratio * the
                        block's own mean absolute deviation) (default 0.5)
    ambiguity_margin    (float) another candidate (more than 1 px from the best) within this residual of the
                        best counts as a rival (default 0.02)
    global_fraction     (float) an event is "global_exposure" when at least this share of its measured blocks
                        flicker (default 0.6)
    min_measured        (float) below this share of measured blocks the verdict is "inconclusive", never "pass"
                        (default 0.5)

Method: each block of frame t is matched in t-1 and in t+1 inside the search window by minimising the residual
after subtracting each block's own mean (so a brightness change does not stop the match). The second difference
is then taken between the block means at the matched places: a pan, however fast inside the window, gives 0, while
a block that brightens or darkens only in frame t does not. Brightness is the Rec.709 luma of the encoded pixel values.

Frame sizes that are not a multiple of `block`: the leftover bottom rows and right columns are analysed as thinner
blocks (at least 4 px; a smaller remainder overlaps the main grid), so nothing is cropped away silently. Thin blocks match
less reliably and are rejected into `not_measured` like any other. Event `blocks` are [x_px, y_px, deviation] (top-left
corner of the block, in frame pixels).

Not measured (the block is skipped and counted, never scored as a pass):
    high_residual  the best match is still poor: fast motion beyond the window, an object appearing, disappearing or
                   being occluded, or content that changes shape.
    ambiguous      a rival candidate fits about as well but has a different block mean, so the answer would depend on
                   a guess: smooth gradients, and periodic patterns whose repeats are not equally bright.
Periodic patterns (stripes, grids): a shift by one period fits as well as the true motion, so the motion found is not
guaranteed to be the true one. The brightness measured is still right when every rival has the same block mean
(plain stripes, checkers); when rivals differ in mean the block is "ambiguous" and not measured. A flicker that
changes the pattern itself (not just its brightness) can also land in high_residual. A sequence in which fewer
than `min_measured` of the blocks are measured has verdict "inconclusive".

Returns verdict ("flicker" | "pass" | "inconclusive"), events (frame, kind "local" | "global_exposure", signed
deviation, region box in px, blocks), per-frame counts, and `not_measured` totals by reason. The first and last frame
have no second difference and are not evaluated. Loads frames into temporary images and removes them.
"""
import json
import os
import re
import sys

import bpy
import numpy as np


def _cli_args():
    """ARGS after `--`: one JSON object, or `--args-file <path.json>` (quoting-proof on every shell)."""
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not raw:
        return {}
    if raw[0] == "--args-file":
        with open(raw[1], encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"ARGS after '--' must be one JSON object, got {raw[0]!r}; "
                         "cmd/PowerShell mangle JSON quotes, so pass --args-file <path.json> instead") from exc


IMG_EXT = {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".tga"}


def _natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _load_luma(path):
    img = bpy.data.images.load(path)
    try:
        img.colorspace_settings.name = "Non-Color"  # raw encoded values, as a viewer shows them
        w, h = img.size
        ch = img.channels
        buf = np.empty(w * h * ch, dtype=np.float32)
        img.pixels.foreach_get(buf)
        buf = buf.reshape(h, w, ch)
        rgb = buf[..., :3] if ch >= 3 else np.repeat(buf[..., :1], 3, axis=2)
        luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        return luma[::-1].copy()  # row 0 = top
    finally:
        bpy.data.images.remove(img)


def _match(cur, ref, y0, x0, nby, nbx, bh, bw, R, margin, ratio, mean_tol):
    """Per block (bh x bw, nby x nbx of them from (y0, x0)) of `cur`: matched block mean in `ref`, or a reject code.
    Returns (mean[nby,nbx] with NaN when not measured, code[nby,nbx]: 0 ok, 1 high_residual, 2 ambiguous,
    oy, ox [nby,nbx]: the matched offset of each block in `ref`, in pixels)."""
    C = cur[y0:y0 + nby * bh, x0:x0 + nbx * bw].reshape(nby, bh, nbx, bw)
    cm = C.mean(axis=(1, 3))
    Cz = C - cm[:, None, :, None]
    dev = np.abs(Cz).mean(axis=(1, 3))
    pad = np.pad(ref, R, mode="constant", constant_values=np.nan)
    offs = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1)]
    resid = np.full((len(offs), nby, nbx), np.inf, dtype=np.float32)
    means = np.full((len(offs), nby, nbx), np.nan, dtype=np.float32)
    for k, (dy, dx) in enumerate(offs):
        P = pad[R + y0 + dy:R + y0 + dy + nby * bh, R + x0 + dx:R + x0 + dx + nbx * bw].reshape(nby, bh, nbx, bw)
        pm = P.mean(axis=(1, 3))  # NaN when any pixel is outside the frame
        r = np.abs(Cz - (P - pm[:, None, :, None])).mean(axis=(1, 3))
        ok = ~np.isnan(pm)
        resid[k] = np.where(ok, r, np.inf)
        means[k] = pm
    best = resid.argmin(axis=0)
    ar = np.arange(nby)[:, None], np.arange(nbx)[None, :]
    best_r = resid[best, ar[0], ar[1]]
    best_m = means[best, ar[0], ar[1]]
    oy = np.array([o[0] for o in offs])[best]
    ox = np.array([o[1] for o in offs])[best]
    code = np.zeros((nby, nbx), dtype=np.int8)
    code[best_r > np.maximum(0.01, ratio * dev)] = 1
    # rivals: near-best residual, more than 1 px from the best, and a block mean that would change the answer
    for k, (dy, dx) in enumerate(offs):
        far = (np.abs(dy - oy) > 1) | (np.abs(dx - ox) > 1)
        rival = far & (resid[k] <= best_r + margin) & (np.abs(means[k] - best_m) > mean_tol)
        code[(code == 0) & rival] = 2
    out = np.where(code == 0, best_m, np.nan)
    return out, code, oy, ox


def _natural_files(d):
    names = [f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in IMG_EXT]
    return [os.path.join(d, f) for f in sorted(names, key=_natural)]


def main(paths=None, dir=None, block=16, max_motion_px=8, flicker_threshold=0.03, reject_ratio=0.5,
         ambiguity_margin=0.02, global_fraction=0.6, min_measured=0.5):
    if bool(paths) == bool(dir):
        raise ValueError("pass exactly one of 'paths' or 'dir'")
    files = list(paths) if paths else _natural_files(dir)
    if len(files) < 3:
        raise ValueError(f"need at least 3 frames, got {len(files)}")
    for f in files:
        if not os.path.isfile(f):
            raise ValueError(f"frame not found: {f}")
    B, R = int(block), int(max_motion_px)
    if B < 4 or R < 0:
        raise ValueError("'block' must be >= 4 and 'max_motion_px' >= 0")
    thr = float(flicker_threshold)
    frames = [_load_luma(f) for f in files]
    H, W = frames[0].shape
    if any(fr.shape != (H, W) for fr in frames):
        raise ValueError("all frames must have the same size")
    nby, nbx = H // B, W // B
    if nby < 1 or nbx < 1:
        raise ValueError(f"frames {W}x{H} are smaller than one {B}px block")
    # full B x B blocks tile the frame from the top-left. A size that is not a multiple of B leaves a bottom strip and/or a
    # right strip; they are analysed too, as thinner blocks (never below 4 px, so a 1-3 px remainder overlaps the main
    # grid), because dropping them would let a flicker confined to the strip pass.
    hs, ws = max(H - nby * B, 4) if H % B else 0, max(W - nbx * B, 4) if W % B else 0
    regions = [(0, 0, nby, nbx, B, B)]  # y0, x0, rows of blocks, cols of blocks, block height, block width
    if hs:
        regions.append((H - hs, 0, 1, nbx, hs, B))
    if ws:
        regions.append((0, W - ws, nby, 1, B, ws))
    if hs and ws:
        regions.append((H - hs, W - ws, 1, 1, hs, ws))

    per_frame = {t: {"frame": t, "file": os.path.basename(files[t]), "measured": 0,
                     "not_measured": {"high_residual": 0, "ambiguous": 0}, "max_abs_dev": None}
                 for t in range(1, len(frames) - 1)}
    flagged_by_t = {t: [] for t in per_frame}  # (x0, y0, x1, y1, dev) of blocks over the threshold
    dev_at = {t: {} for t in per_frame}  # (x0, y0) of a block -> its signed deviation in frame t (measured blocks only)
    foot_at = {t: {} for t in per_frame}  # (x0, y0, neighbour frame) -> (x, y, w, h) of the matched footprint there
    totals = {"high_residual": 0, "ambiguous": 0}
    n_meas = n_all = 0
    for (ry, rx, ny, nx, bh, bw) in regions:
        for t in range(1, len(frames) - 1):
            mp, cp, pyo, pxo = _match(frames[t], frames[t - 1], ry, rx, ny, nx, bh, bw, R, ambiguity_margin, reject_ratio, thr / 2)
            mn, cn, nyo, nxo = _match(frames[t], frames[t + 1], ry, rx, ny, nx, bh, bw, R, ambiguity_margin, reject_ratio, thr / 2)
            code = np.maximum(cp, cn)
            tmean = frames[t][ry:ry + ny * bh, rx:rx + nx * bw].reshape(ny, bh, nx, bw).mean(axis=(1, 3))
            dev = tmean - 0.5 * (mp + mn)  # signed; NaN where not measured
            dev[code != 0] = np.nan
            hi, amb = int((code == 1).sum()), int((code == 2).sum())
            meas = int((code == 0).sum())
            totals["high_residual"] += hi
            totals["ambiguous"] += amb
            n_meas += meas
            n_all += code.size
            pf = per_frame[t]
            pf["measured"] += meas
            pf["not_measured"]["high_residual"] += hi
            pf["not_measured"]["ambiguous"] += amb
            if meas:
                m = round(float(np.nanmax(np.abs(dev))), 5)
                pf["max_abs_dev"] = m if pf["max_abs_dev"] is None else max(pf["max_abs_dev"], m)
            for y, x in zip(*np.nonzero(~np.isnan(dev))):
                dev_at[t][(rx + int(x) * bw, ry + int(y) * bh, bw, bh)] = float(dev[y, x])
                # where this block's content sits in the previous / next frame (its motion match)
                for u, oy_, ox_ in ((t - 1, pyo, pxo), (t + 1, nyo, nxo)):
                    foot_at[t][(rx + int(x) * bw, ry + int(y) * bh, u)] = (
                        rx + int(x) * bw + int(ox_[y, x]), ry + int(y) * bh + int(oy_[y, x]), bw, bh)
            ys, xs = np.nonzero(np.abs(dev) > thr)  # NaN compares False
            flagged_by_t[t] += [(rx + int(x) * bw, ry + int(y) * bh, rx + int(x) * bw + bw, ry + int(y) * bh + bh,
                                 float(dev[y, x])) for y, x in zip(ys, xs)]

    events = []
    for t, flagged in flagged_by_t.items():
        # a one-frame bump also shows at half size, opposite sign, in its neighbours, at the place the motion match
        # carries it to: drop a block whose deviation is smaller than that of a block overlapping the footprint it
        # matched to in an adjacent frame (per block and per match, so an independent event elsewhere survives)
        def echo(f, t=t):
            for u in (t - 1, t + 1):
                fx, fy, fw, fh = foot_at[t].get((f[0], f[1], u), (f[0], f[1], f[2] - f[0], f[3] - f[1]))
                for (bx, by, bw_, bh_), d in dev_at.get(u, {}).items():
                    ov = max(0, min(fx + fw, bx + bw_) - max(fx, bx)) * max(0, min(fy + fh, by + bh_) - max(fy, by))
                    if ov >= 0.25 * min(fw * fh, bw_ * bh_) and abs(d) > abs(f[4]):
                        return True
            return False

        flagged = [f for f in flagged if not echo(f)]
        if not flagged:
            continue
        meas = per_frame[t]["measured"]
        kind = "global_exposure" if len(flagged) >= global_fraction * meas else "local"
        events.append({"frame": t, "file": os.path.basename(files[t]), "kind": kind,
                       "mean_deviation": round(float(np.mean([f[4] for f in flagged])), 5),
                       "region_px": [min(f[0] for f in flagged), min(f[1] for f in flagged),
                                     max(f[2] for f in flagged), max(f[3] for f in flagged)],
                       "blocks_flagged": len(flagged), "blocks_measured": meas,
                       "blocks": [[f[0], f[1], round(f[4], 5)] for f in flagged[:32]]})
    share = n_meas / n_all if n_all else 0.0
    verdict = "flicker" if events else ("pass" if share >= min_measured else "inconclusive")
    return {"verdict": verdict, "events": events, "frames": len(frames), "evaluated_frames": len(per_frame),
            "block_px": B, "max_motion_px": R, "flicker_threshold": thr,
            "measured_blocks": n_meas, "total_blocks": n_all, "measured_share": round(share, 4),
            "not_measured": {"blocks": n_all - n_meas, **totals},
            "per_frame": [per_frame[t] for t in sorted(per_frame)],
            "domain": f"motion up to {R}px per frame in x and y between consecutive frames; blocks outside it, "
                      "ambiguous matches and occlusions are not_measured, never counted as a pass"}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
