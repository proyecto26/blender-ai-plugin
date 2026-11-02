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
    min_measured        (float) below this share of measured blocks, over the sequence or in any one evaluated frame,
                        the verdict is "inconclusive", never "pass" (default 0.5)
    dropout_level       (float) a dropout cell's mean is within this of 0 (black) or 1 (white) (default 0.015; the darkest
                        flat cells in 31 clean renders are 0 to 0.06, injected dropouts are exactly 0 or 1)
    dropout_flat_dev    (float) a dropout cell's mean absolute deviation is at most this (default 0.01)
    dropout_gap         (float) both neighbours of a dropout cell are at least this far from its flat value, as a mean
                        absolute difference (default 0.02; a 0 / 0.05 checker is 0.025 away from black)

Dropouts (a separate, narrow rule, run only on candidate cells; a cell is half a block, `block // 2` px): a cell of frame t
is a dropout when it is nearly uniform (mean absolute deviation <= `dropout_flat_dev`) and near black or near white (its mean
within `dropout_level` of 0 or 1), while the same place in t-1 and t+1, shifted symmetrically by up to `max_motion_px` per
frame, has real content: each is at least `dropout_gap` away from the flat value (mean absolute difference) and the two
agree with each other at least twice as closely as with it, and clearly better than the typical shift fits. The best shift
is searched per candidate cell only (every shift on every second px, then +-1 px at full resolution), and the smallest raw difference is kept, so a periodic
texture or a pan cannot hide the agreement. At least 4 flat cells must sit in a 3x3 neighbourhood. This catches a tile, a band
or a whole frame gone black or white for one frame, in the middle of a shot, whatever fraction of the frame it covers (there
is no share limit, a wholly black frame is the same rule). The event has the frame, the region of the cells found (within
one block of the true region: whole cells only) and `dropout_cells`. A textured moving object cannot qualify, since its cells
are not flat; other content showing for one frame, a fade, a cut and black bars that never change are not dropouts either.
Limits, measured: (1) a very dark scene whose neighbours are themselves nearly flat black (mean about 0.01) returns `pass` for a
black frame at the default `dropout_gap` (0.02); lower it to 0.005 to find it there, at the price of more false events in dark
renders; (2) a dropout smaller than two cells in each direction (16 px at the default block) is not looked for; (3) a flat
black or white object that moves fast (24 px at 30 px per frame, and about 148 px at about 90 px per frame, were measured) is the same
shape as a dropout and is reported as one when it spans 2x2 cells (a shadow is not: the darkest flat cells in 31 clean renders, shadows included, are above 0.015
unless the scene itself is black);
(4) the neighbours must be a steady shift of each other: a pan that accelerates, or a dropout beside another bad frame,
is not confirmed and is left to `unmeasured_frames`; (5) a region that turns not black or white but another level (a
gain pop on part of the frame) is found only when it is a block-wide jump, as before.

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
The same holds per frame: a pure black or white frame has no matchable block in itself or its neighbours, which a long
sequence can hide in the aggregate share. Such a frame is judged on its whole-frame mean luma: if it jumps by more than
`flicker_threshold` while the frames either side agree with each other (they differ from each other by less than a
quarter of the jump), it is reported as a "global_exposure" event with source "frame_luma" (its neighbours, matched
against it, are explained by it). A hard cut does not have that shape (the neighbours differ), and neither do several
bad frames in a row; those frames are listed in `unmeasured_frames` and the verdict is "inconclusive". A bad first
or last frame cannot be judged (no second difference); the frame beside it is the one listed.

Returns verdict ("flicker" | "pass" | "inconclusive"), events (frame, kind "local" | "global_exposure", signed
deviation, region box in px, blocks), `unmeasured_frames` (frames with too few measured blocks that no event explains),
per-frame counts, and `not_measured` totals by reason. The first and last frame
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


def _grab(F, ys, xs, ky, kx, R, sub):
    """Cells of the R-padded frame F at (ys + ky, xs + kx): ys, xs are [K, c] pixel indices, ky, kx [K] shifts."""
    return F[(ys[:, ::sub] + R + ky[:, None])[:, :, None], (xs[:, ::sub] + R + kx[:, None])[:, None, :]]


def _dropouts(frames, t, cell, R, level, flat_dev, gap):
    """Cells of frame t that went flat black or white while the frames either side agree there: (x0, y0, x1, y1, dev).
    Only candidate cells are searched: t is nearly uniform (mean abs deviation <= flat_dev) and its mean is within `level`
    of 0 or 1. For those, t-1 and t+1 are compared at the same place, shifted symmetrically by up to R px per frame
    (every shift on every second px, then +-1 px of the best at full resolution) and the smallest raw difference is kept:
    a periodic texture cannot make that worse, it can only match at a period. A candidate is a dropout when both
    neighbours are at least `gap` away from the flat value (mean absolute difference) and agree with each other at
    least twice as closely as with it, and at least twice as closely as the typical shift does (so a smooth or noisy dark
    area, where every shift fits about as well, is not a match). Cells alone in a 3x3 neighbourhood (fewer than 4 flat
    cells there) are dropped: a dropout is a region, and a thin dark line is more often a shadow or an edge."""
    H, W = frames[t].shape
    ny, nx = H // cell, W // cell
    if not ny or not nx:
        return []
    T = frames[t][:ny * cell, :nx * cell].reshape(ny, cell, nx, cell)
    tm = T.mean(axis=(1, 3))
    td = np.abs(T - tm[:, None, :, None]).mean(axis=(1, 3))
    cy, cx = np.nonzero((td <= flat_dev) & ((tm <= level) | (tm >= 1.0 - level)))
    if not len(cy):
        return []
    v = tm[cy, cx]
    ar = np.arange(cell)
    ys, xs = cy[:, None] * cell + ar[None, :], cx[:, None] * cell + ar[None, :]
    Pp = np.pad(frames[t - 1], R, mode="constant", constant_values=np.nan)
    Np = np.pad(frames[t + 1], R, mode="constant", constant_values=np.nan)
    sub = 2 if cell >= 8 else 1
    K = len(cy)
    best = np.full(K, np.inf)
    by = np.zeros(K, dtype=int)
    bx = np.zeros(K, dtype=int)

    def try_shift(ky, kx, s):
        nonlocal best, by, bx
        e = np.abs(_grab(Pp, ys, xs, -ky, -kx, R, s) - _grab(Np, ys, xs, ky, kx, R, s)).mean(axis=(1, 2))
        e = np.where(np.isnan(e), np.inf, e)
        coarse.append(e)
        better = e < best - 1e-6  # the first of equal fits wins: the smallest shift (the loop below runs outward)
        best = np.where(better, e, best)
        by = np.where(better, ky, by)
        bx = np.where(better, kx, bx)

    coarse = []
    for ky, kx in sorted(((a, b) for a in range(-R, R + 1) for b in range(-R, R + 1)), key=lambda k: abs(k[0]) + abs(k[1])):
        try_shift(np.full(K, ky), np.full(K, kx), sub)
    typical = np.median(np.stack(coarse), axis=0)
    cy0, cx0 = by.copy(), bx.copy()
    best[:] = np.inf
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            try_shift(np.clip(cy0 + dy, -R, R), np.clip(cx0 + dx, -R, R), 1)
    Pb = _grab(Pp, ys, xs, -by, -bx, R, 1)
    Nb = _grab(Np, ys, xs, by, bx, R, 1)
    dP = np.abs(Pb - v[:, None, None]).mean(axis=(1, 2))
    dN = np.abs(Nb - v[:, None, None]).mean(axis=(1, 2))
    ok = np.isfinite(best) & (dP >= gap) & (dN >= gap) & (best <= 0.5 * np.minimum(dP, dN)) & (best <= 0.5 * typical)
    grid = np.zeros((ny + 2, nx + 2), dtype=np.int8)
    grid[cy + 1, cx + 1] = ok
    near = sum(grid[1 + a:1 + a + ny, 1 + b:1 + b + nx] for a in (-1, 0, 1) for b in (-1, 0, 1))
    ok = ok & (near[cy, cx] >= 4)
    nb = 0.5 * (Pb.mean(axis=(1, 2)) + Nb.mean(axis=(1, 2)))
    return [(int(cx[i]) * cell, int(cy[i]) * cell, int(cx[i]) * cell + cell, int(cy[i]) * cell + cell, float(v[i] - nb[i]))
            for i in np.nonzero(ok)[0]]


def _natural_files(d):
    names = [f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in IMG_EXT]
    return [os.path.join(d, f) for f in sorted(names, key=_natural)]


def main(paths=None, dir=None, block=16, max_motion_px=8, flicker_threshold=0.03, reject_ratio=0.5,
         ambiguity_margin=0.02, global_fraction=0.6, min_measured=0.5, dropout_level=0.015, dropout_flat_dev=0.01,
         dropout_gap=0.02):
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
    drops_by_t = {t: [] for t in per_frame}  # the same for dropout blocks (rejected by the match, neighbours agree)
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
    cell = max(4, B // 2)
    for t in per_frame:
        drops_by_t[t] = _dropouts(frames, t, cell, R, dropout_level, dropout_flat_dev, dropout_gap)

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
                # the same for a dropout in the adjacent frame: a block matched into or beside a region that went flat there
                # (a cell wide on each side: the edge of the region is only partly flat) differs because of it
                for (x0_, y0_, x1_, y1_, _d) in drops_by_t.get(u, []):
                    x0_, y0_, x1_, y1_ = x0_ - cell, y0_ - cell, x1_ + cell, y1_ + cell
                    ov = max(0, min(fx + fw, x1_) - max(fx, x0_)) * max(0, min(fy + fh, y1_) - max(fy, y0_))
                    if ov >= 0.25 * min(fw * fh, (x1_ - x0_) * (y1_ - y0_)):
                        return True
            return False

        flagged = [f for f in flagged if not echo(f)]
        drops = drops_by_t[t]
        flagged = flagged + drops
        if not flagged:
            continue
        meas = per_frame[t]["measured"]
        if drops:  # blocks and cells differ in size: judge the share by area
            covered = sum((f[2] - f[0]) * (f[3] - f[1]) for f in flagged)
            kind = "global_exposure" if covered >= global_fraction * H * W else "local"
        else:
            kind = "global_exposure" if len(flagged) >= global_fraction * meas else "local"
        events.append({"frame": t, "file": os.path.basename(files[t]), "kind": kind,
                       "mean_deviation": round(float(np.mean([f[4] for f in flagged])), 5),
                       "region_px": [min(f[0] for f in flagged), min(f[1] for f in flagged),
                                     max(f[2] for f in flagged), max(f[3] for f in flagged)],
                       "blocks_flagged": len(flagged), "blocks_measured": meas, "dropout_cells": len(drops), "cell_px": cell,
                       "blocks": [[f[0], f[1], round(f[4], 5)] for f in flagged[:32]]})
    # Frames the block method could not judge. A frame that is pure black or white (or otherwise unlike its neighbours
    # everywhere) has no measured block in itself or in the frames beside it, and the aggregate share can still look fine
    # on a longer sequence. So each evaluated frame is checked on its own: below `min_measured` it is "unmeasured". On
    # those frames (and their neighbours) the whole-frame mean luma is read as well: a frame whose mean jumps while the
    # two frames around it agree with each other is an exposure pop even when no block could be matched. A hard cut does
    # not have that shape (the two neighbours differ), and neither do several bad frames in a row.
    gm = [float(fr.mean()) for fr in frames]
    unmeasured = []
    for t, pf in per_frame.items():
        total_t = pf["measured"] + pf["not_measured"]["high_residual"] + pf["not_measured"]["ambiguous"]
        pf["measured_share"] = round(pf["measured"] / total_t, 4) if total_t else 0.0
        if total_t and pf["measured"] < min_measured * total_t:
            unmeasured.append(t)
    have_event = {e["frame"] for e in events}
    pops = set()
    for t in sorted({u + d for u in unmeasured for d in (-1, 0, 1)} & set(per_frame)):
        if t in have_event:
            continue
        dev = gm[t] - 0.5 * (gm[t - 1] + gm[t + 1])
        if abs(dev) > thr and abs(gm[t - 1] - gm[t + 1]) < 0.25 * abs(dev):
            pops.add(t)
            events.append({"frame": t, "file": os.path.basename(files[t]), "kind": "global_exposure",
                           "source": "frame_luma", "mean_deviation": round(dev, 5),
                           "region_px": [0, 0, W, H], "blocks_flagged": 0, "blocks_measured": per_frame[t]["measured"],
                           "blocks": []})
    events.sort(key=lambda e: e["frame"])
    # a pop explains the unmeasured frame itself and the frames either side of it (they were matched against it)
    unexplained = [t for t in unmeasured if not ({t - 1, t, t + 1} & pops)]
    unmeasured_frames = [{"frame": t, "file": os.path.basename(files[t]), "measured_share": per_frame[t]["measured_share"]}
                         for t in unexplained]
    share = n_meas / n_all if n_all else 0.0
    verdict = "flicker" if events else ("pass" if share >= min_measured and not unmeasured_frames else "inconclusive")
    return {"verdict": verdict, "events": events, "unmeasured_frames": unmeasured_frames,
            "frames": len(frames), "evaluated_frames": len(per_frame),
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
