"""Temporal flicker check on a rendered image sequence: finds frames and regions whose brightness jumps against
their neighbours, without mistaking motion for flicker. Read-only.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/flicker_check.py",
                            init_globals={"ARGS": {"dir": "<project>/renders/S010"}})["result"]

ARGS:
    paths               (list[str]) frame images in playing order; or
    dir                 (str) a folder of frames, read in natural filename order (use one of paths / dir)
    scale               (int)   frame scale, default from the frame size: the shorter side / 360 rounded to a whole number (1 up to
                        539 px, 2 at 1280x720, 3 at 1920x1080, 6 at 3840x2160). Every pixel-sized default below was tuned at
                        640x360 and is multiplied by it when you do not set it: block, max_motion_px, the 8 px first search
                        window, the dropout search and its steps, the smallest edge strip (4 px). Results at 640x360 are unchanged.
                        The values used are in the result (`scale`, `block_px`, `max_motion_px`, `dropout_search_px`, `cell_px`,
                        `scaled_defaults`). An explicit `block` or `max_motion_px` is used as given; the other still scales.
    block               (int)   block size in px (default 16 x scale: 16 at 640x360, 32 at 1280x720, 48 at 1920x1080)
    max_motion_px       (int)   search window: a block may move up to this many px in x and y between
                        consecutive frames (default 24 x scale). Searched in two tiers: every shift up to 8 x scale px (at
                        full resolution when scale is 1, else on scale x scale averaged copies, then +-1 px), and, for blocks
                        nothing in that window explains (only when they are at least 3% of the blocks), the whole window
                        coarse to fine (2 x scale averaged copies, then refined at full resolution). The averaging needs a
                        block divisible by 2 x scale; with an explicit block that is not, the search runs at full resolution as
                        at scale 1, which is slow on big frames. Timing, 5 frames at 1920x1080 (a noisy Cycles shot): 5.9 s with
                        the defaults against 20.9 s with block 16 and window 24.
    flicker_threshold   (float) a block flickers when its mean differs from the average of its motion-matched
                        previous and next blocks by more than this (default 0.03, on 0..1 encoded values)
    reject_ratio        (float) match rejection: the best match is rejected when its residual (mean absolute
                        difference after removing each block's mean) exceeds max(0.01, reject_ratio * the
                        block's own mean absolute deviation) (default 0.5)
    ambiguity_margin    (float) another candidate (more than 1 px from the best) within this residual of the
                        best counts as a rival (default 0.02)
    bound               (float) an ambiguous block (see Method) is scored by the range of its prediction and counts as measured
                        when that range is at most this wide, or when every candidate already says it differs by more than
                        `flicker_threshold` (default 0.09)
    slack               (float) a block flickers only when its deviation exceeds `flicker_threshold` by this x the worse of its
                        two match residuals (default 0.5; an exact match, as in a static or cleanly panning shot, loses nothing)
    ambiguous_support   (int)   a flagged block whose match was ambiguous counts only inside a group of at least this many
                        touching flagged blocks of the same sign (default 4, a 32 x 32 px area at the default block); a flagged
                        block of the leftover edge strip needs 2, an exactly matched block needs 1
    global_fraction     (float) an event is "global_exposure" when its affected pixels (the UNION of flagged blocks and
                        dropout cells, each pixel once) are at least this share of the pixels that were measured or
                        flagged (default 0.6); a band over a third of a flat frame is "local"
    neighbour_agreement (float) a block is a pulse, and only then an event, when its two matched neighbours differ from each
                        other by at most this x its deviation (default 0.5). A step (the frame equals one neighbour, not
                        the other: an object arriving or leaving, a light changing for good) is not; two steps of the same
                        sign and size at the same block in consecutive frames are (a flicker lasting two frames)
    min_measured        (float) below this share of measured blocks, over the sequence or in any one evaluated frame,
                        the verdict is "inconclusive", never "pass" (default 0.5)
    dropout_level       (float) a dropout cell's mean is within this of 0 (black) or 1 (white) (default 0.015; the darkest
                        flat cells in 31 clean renders are 0 to 0.06, injected dropouts are exactly 0 or 1)
    dropout_flat_dev    (float) a dropout cell's mean absolute deviation is at most this (default 0.01)
    dropout_gap         (float) both neighbours of a dropout cell are at least this far from its flat value, as a mean
                        absolute difference (default 0.02; a 0 / 0.05 checker is 0.025 away from black)

Dropouts (a separate, narrow rule, run only on candidate cells; a cell is half a block, `block // 2` px): a cell of frame t
is a dropout when it is nearly uniform (mean absolute deviation <= `dropout_flat_dev`) and near black or near white (its mean
within `dropout_level` of 0 or 1), while the same place in t-1 and t+1, shifted symmetrically by up to min(`max_motion_px`, 8 x scale) px per
frame (the search window is capped there, see `dropout_search_px`), has real content: each is at least `dropout_gap` away from the flat value (mean absolute difference) and the two
agree with each other at least twice as closely as with it, and clearly better than the typical shift fits. The best shift
is searched per candidate cell only (every shift on every second px, then +-1 px at full resolution), and the smallest raw difference is kept, so a periodic
texture or a pan cannot hide the agreement. At least 4 flat cells must sit in a 3x3 neighbourhood. This catches a tile, a band
or a whole frame gone black or white for one frame, in the middle of a shot, whatever fraction of the frame it covers (there
is no share limit, a wholly black frame is the same rule). The event has the frame, the region of the cells found (within
one block of the true region: whole cells only) and `dropout_cells`. A textured moving object cannot qualify, since its cells
are not flat; other content showing for one frame, a fade, a cut and black bars that never change are not dropouts either.
Limits, measured: (1) a very dark scene whose neighbours are themselves nearly flat black (mean about 0.01) returns `pass` for a
black frame at the default `dropout_gap` (0.02); lower it to 0.005 to find it there, at the price of more false events in dark
renders; (2) a dropout smaller than two cells in each direction (16 px at 640x360, 32 at 1280x720) is not looked for; (3) a flat
black or white object that moves fast (24 px at 30 px per frame, and about 148 px at about 90 px per frame, were measured) is the same
shape as a dropout and is reported as one when it spans 2x2 cells (a shadow is not: the darkest flat cells in 31 clean renders, shadows included, are above 0.015
unless the scene itself is black);
(4) the neighbours must be a steady shift of each other: a pan that accelerates, or a dropout beside another bad frame,
is not confirmed and is left to `unmeasured_frames`; (5) a region that turns not black or white but another level (a
gain pop on part of the frame) is found only when it is a block-wide jump, as before.

Method (ambiguous blocks): on a smooth gradient, a flat shape or a periodic pattern several candidates fit about as well with
different block means, so there is no single prediction. The block is then scored by the RANGE of the means over the candidates
that fit (`ambiguous_ranged` counts them): its deviation is a range too, it is a flicker only when the whole range is beyond
the threshold (the end nearest zero is used), and it counts as measured when the range is narrow (`bound`) or already beyond
the threshold. A +0.2 tile on a smooth floor is therefore found (every candidate says brighter) while a +0.02 one is not (the
range reaches zero). `not_measured.ambiguous` counts every block whose match was ambiguous, including the ranged ones, which are
in `measured_blocks` as well; `not_measured.blocks` is what really was not measured. An echo (a block's half-size opposite-sign
copy in the next frame) is dropped only for the opposite sign and a neighbour at least 1.5x as large, so a two-frame flicker
(same sign in both frames) is not taken for one. The residual a good match still has (render noise differs per frame) is taken from
the better matched 30% of the blocks, between 0.01 and 0.02.

Method: each block of frame t is matched in t-1 and in t+1 inside the search window by minimising the residual
after subtracting each block's own mean (so a brightness change does not stop the match). The second difference
is then taken between the block means at the matched places: a pan, however fast inside the window, gives 0, while
a block that brightens or darkens only in frame t does not. Brightness is the Rec.709 luma of the encoded pixel values.

Frame sizes that are not a multiple of `block`: the leftover bottom rows and right columns (at least 4 px; a smaller
remainder overlaps the main grid) are scored too, so nothing is cropped away silently. A thin block of the leftover size matches
anything it is flat in and cannot see content entering the strip (it gave false events at the bottom edge of 640x360 frames,
360 = 22 x 16 + 8), so the motion is taken from the full block that ends where the strip begins and the strip pixels are scored
at that motion; the region of an event is the strip itself (a +0.15 defect in the 8 px bottom strip of a panning 320x184 frame
is found, with the region [64,176,160,184] for a defect at [64,176,160,184]). An ambiguous match is not scored in a strip.
That motion cannot see content that enters the strip from outside the block above (a shadow edge sliding in gave a false `flicker`
at the bottom of a clean 1920x1080 Eevee pan, 1080 = 22 x 48 + 24), so the strip is also matched from the full block that ends flush
with the frame edge (it contains the strip and overlaps the grid), and a strip flag is dropped when that second match measured the
same pixels within the threshold or found them ambiguous; when it could not match at all (a real defect in the strip spoils the
match) the flag stands. The second match scores nothing else and adds a row of blocks to the work, 12.2 s against 12.0 s for 10 frames
at 1920x1080 (Eevee, defaults).
Event `blocks` are [x_px, y_px, deviation] (top-left corner of the block, in frame pixels).

What counts as an event (besides the dropout rule): a measured block whose mean differs from the matched neighbours by more
than `flicker_threshold`, whose neighbours agree with each other (a pulse, above), and whose pixels agree (the interquartile
mean of the per-pixel differences has the same sign and size: an object edge across a block changes the mean, not most pixels).
Events from a frame in which fewer than `min_measured` of the blocks could be followed (a fast camera, lights moving, every
surface changing shape) are not events: they are listed in `unconfirmed_events`, the frame is in `unmeasured_frames`, and the
verdict is "inconclusive" (a global exposure pop and a dropout are judged by their own rules and stay events).

Round 4, frame size: the same 31 clean renders and their injections at 640x360, upscaled 2x (1280x720) and 3x (1920x1080), all with
default ARGS: clean 31 `pass`, 0 `flicker`, 0 `inconclusive` at each size (the earlier defaults: 21 `flicker` at 2x, 24 at 3x). A +0.2 one-frame
tile, the same tile for two frames, a black tile (scaled with the frame) and a black frame: 31 of 31 found at each size, and the
region error is exactly the 640x360 one times the scale (tile: 30 within 8 x scale px, one 40 x scale short; black tile: four near-black
shots 32 to 72 x scale short). Longest single run of the 155: 10.8 s, 21.4 s, 56.5 s at 1x, 2x, 3x.

Measured on 31 clean real renders (640x360, EEVEE and Cycles: balls, fans, spheres, rotating objects, cameras, moving lights)
the verdict was flicker 14, pass 13, inconclusive 4 on the iteration 12 code, flicker 0, pass 19, inconclusive 12 on the
iteration 13 round 1 code, and is flicker 0, pass 31, inconclusive 0 now. Each of those 31 with a one-frame +0.2 tile at
[200,120,296,216] was `flicker` in 31 of 31 (round 1: 15, iteration 12: 25), region within 8 px of the tile in 29, 24 px short in
one (`noise_ee_rot`) and 56 px short in another (a noisy dolly: `noise_ee_cam`, its lower blocks' residual 0.011 to 0.017 is above the noise floor; a block with a rejected match in one neighbour is never scored); the same tile for two
frames 31 of 31, within 8 px in 29 and 24 px short in two; a black tile 31 of 31, a black frame 31 of 31. On 15 more renders of flat black or white fast
objects, a strobe and a light off for one frame: both of those stay `flicker` (global_exposure), 8 of the 13 others
(propellers, black boxes) are still reported, see limit (c).
Remaining limits, measured: (a) a flicker that lasts three frames or more is a hold, not a pulse, and is not found (two
frames are); (b) a defect smaller than four touching blocks (32 x 32 px at the default block) on an ambiguous area, or than two
blocks in the leftover edge strip, is not reported: a lone ambiguous block over the threshold was the form every false event on
the clean renders took (a 16 px square of +0.2 on a smooth floor is `pass`, a 32 px one is found, at 640x360; both sizes scale with the frame); (c) a flat black or white
object that is in the frame for one frame, or crosses a flat region faster than the window, has the shape of a defect and is
reported (8 of the 13 flat-object renders above; a ball or its shadow arriving over a smooth floor is the same shape: a clean
`cy_ball_32dn` shot reports no event only because its ellipse is 2 blocks wide); (d) motion beyond `max_motion_px`
is not judged reliably: shots where most of the picture changes shape are `inconclusive` only while under half of the blocks are
followed, and a smooth background now counts as followed, so an object that jumps farther than the window over it shows as
a flat region and is reported. The window and the block scale with the frame, so motion that is the same in
picture terms (a render upscaled 2x or 3x, motion doubled or tripled) stays inside it; a shot whose pixel motion is large
for its size (a 1080p pan of 100 px a frame) still needs `max_motion_px` raised, and beyond the window (a 1080p pan of about 100 to 200 px a frame, 4 of 10 frames measured
with a 105 px step) the result can be `flicker` rather than `inconclusive`: the share of textured blocks with a rejected match is no usable gate, since clean dark Cycles shots reach 0.67 of them;
(e) dropouts are searched within min(`max_motion_px`, 8 x scale) px; (f) a black tile is found only where the original is
brighter than about 0.02 (the dropout rule): in four near-black shots (the tile region averages 0.01 to 0.04) its region
came out 32 to 72 px short of the tile; (g) shots where camera, lights and objects all move under Cycles noise are the ones most
likely to stay `inconclusive`: `noise_cy16_mixed` is `pass` here with 74% of its blocks measured (exactly or by range).

Not measured (the block is skipped and counted, never scored as a pass):
    high_residual  the best match is still poor: fast motion beyond the window, an object appearing, disappearing or
                   being occluded, or content that changes shape.
    ambiguous      a rival candidate fits about as well but has a different block mean, so the answer would depend on
                   a guess: smooth gradients, and periodic patterns whose repeats are not equally bright. Scored by range
                   (see Method) and counted as measured when the range is narrow; not measured when it is wide.
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
deviation, region box in px, blocks), `unconfirmed_events` (blocks flagged in a frame where under `min_measured` of the blocks could be followed), `unmeasured_frames` (frames with too few measured blocks that no event explains),
per-frame counts, and `not_measured` totals by reason. The first and last frame
have no second difference and are not evaluated. Loads frames into temporary images and removes them.
"""
import json
import os
import re
import sys
import warnings

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


_POOL = {}
WIDE_MIN_SHARE = 0.03
NOISE_CAP = 0.02


def _pooled(F, py, px, S):
    """F cropped by (py, px) rows / columns at the top-left, then averaged over S x S (cached per array, crop and S)."""
    key = (id(F), py, px, S)
    if key not in _POOL:
        G = F[py:, px:]
        h, w = G.shape[0] // S * S, G.shape[1] // S * S
        _POOL[key] = (F, G[:h, :w].reshape(h // S, S, w // S, S).mean(axis=(1, 3)))  # F kept so its id stays unique
    return _POOL[key][1]


def _gather(F, ys, xs, y0, x0, bh, bw, oy, ox, sub=None):
    """Blocks of F: block (ys[i], xs[i]) of the grid at (y0, x0), moved by (oy[i], ox[i]) px -> [K, h, w]; `sub` =
    (r0, r1, c0, c1) takes only that part of each block. Indices are clipped, so only call it for matches that were found
    inside the frame."""
    H, W = F.shape
    r0, r1, c0, c1 = sub or (0, bh, 0, bw)
    r = np.clip(y0 + ys[:, None] * bh + r0 + oy[:, None] + np.arange(r1 - r0)[None, :], 0, H - 1)
    c = np.clip(x0 + xs[:, None] * bw + c0 + ox[:, None] + np.arange(c1 - c0)[None, :], 0, W - 1)
    return F[r[:, :, None], c[:, None, :]]


def _match_window(cur, ref, y0, x0, nby, nbx, bh, bw, R, margin, ratio, mean_tol, S=1, unit=1):
    """Per block (bh x bw, nby x nbx of them from (y0, x0)) of `cur`: its match in `ref` within +-R px, coarse to fine.
    The search runs on 2x2-averaged copies (every candidate within R // 2 of those px; the mean of a block there is exactly
    the mean of the full-resolution block at an even offset), then the best candidate is refined at full resolution
    (+-1 px, never beyond R). With an odd block size or R < 2 the search is exhaustive at full resolution instead.
    `unit` is the frame scale (see main): a rival must be more than `unit` px from the best, 1 px at the 640x360 scale.
    Returns (mean[nby,nbx] of the matched block, NaN when not measured; code[nby,nbx]: 0 ok, 1 high_residual,
    2 ambiguous; oy, ox [nby,nbx]: the matched offset of each block in `ref`, in px)."""
    C = cur[y0:y0 + nby * bh, x0:x0 + nbx * bw].reshape(nby, bh, nbx, bw)
    cm = C.mean(axis=(1, 3))
    Cz = C - cm[:, None, :, None]
    dev = np.abs(Cz).mean(axis=(1, 3))
    ar = np.arange(nby)[:, None], np.arange(nbx)[None, :]
    S = S if (S > 1 and bh % S == 0 and bw % S == 0 and R >= S) else 1
    coarse = S > 1
    if coarse:
        py, px = y0 % S, x0 % S
        cy0, cx0, kbh, kbw, Rk = (y0 - py) // S, (x0 - px) // S, bh // S, bw // S, R // S
        src = _pooled(cur, py, px, S)[cy0:cy0 + nby * kbh, cx0:cx0 + nbx * kbw].reshape(nby, kbh, nbx, kbw)
        srcref = _pooled(ref, py, px, S)
        ky0, kx0 = cy0, cx0
    else:
        src, srcref, ky0, kx0, kbh, kbw, Rk = C, ref, y0, x0, bh, bw, R
    km = src.mean(axis=(1, 3))
    Kz = src - km[:, None, :, None]
    pad = np.pad(srcref, Rk, mode="constant", constant_values=np.nan)
    offs = [(dy, dx) for dy in range(-Rk, Rk + 1) for dx in range(-Rk, Rk + 1)]
    resid = np.full((len(offs), nby, nbx), np.inf, dtype=np.float32)
    means = np.full((len(offs), nby, nbx), np.nan, dtype=np.float32)
    for k, (dy, dx) in enumerate(offs):
        P = pad[Rk + ky0 + dy:Rk + ky0 + dy + nby * kbh, Rk + kx0 + dx:Rk + kx0 + dx + nbx * kbw].reshape(nby, kbh, nbx, kbw)
        pm = P.mean(axis=(1, 3))  # NaN when any pixel is outside the frame
        r = np.abs(Kz - (P - pm[:, None, :, None])).mean(axis=(1, 3))
        resid[k] = np.where(np.isnan(pm), np.inf, r)
        means[k] = pm
    best = resid.argmin(axis=0)
    best_r = resid[best, ar[0], ar[1]]
    best_m = means[best, ar[0], ar[1]]
    dys = np.array([o[0] for o in offs]) * S
    dxs = np.array([o[1] for o in offs]) * S
    oy, ox = dys[best], dxs[best]
    near = resid <= best_r[None] + margin  # candidates that fit about as well as the best (never an outside one: inf)
    rival = np.zeros((nby, nbx), dtype=bool)
    for k in range(len(offs)):
        far = (np.abs(dys[k] - oy) > unit) | (np.abs(dxs[k] - ox) > unit)
        rival |= far & near[k] & (np.abs(means[k] - best_m) > mean_tol)
    if coarse:  # refine at full resolution: +-S/2 px around the best coarse candidate (never beyond R)
        rad = S // 2
        pad1 = np.pad(ref, R + rad, mode="constant", constant_values=np.nan)
        gy, gx = np.meshgrid(np.arange(nby), np.arange(nbx), indexing="ij")
        Czt = Cz.transpose(0, 2, 1, 3)
        fr_ = np.full((nby, nbx), np.inf, dtype=np.float32)
        fy, fx, fm = oy.copy(), ox.copy(), best_m.copy()
        for ddy in range(-rad, rad + 1):
            for ddx in range(-rad, rad + 1):
                ty, tx = np.clip(oy + ddy, -R, R), np.clip(ox + ddx, -R, R)
                rr = R + rad + y0 + gy[:, :, None] * bh + ty[:, :, None] + np.arange(bh)[None, None, :]
                cc = R + rad + x0 + gx[:, :, None] * bw + tx[:, :, None] + np.arange(bw)[None, None, :]
                P = pad1[rr[:, :, :, None], cc[:, :, None, :]]  # [nby, nbx, bh, bw]
                pm = P.mean(axis=(2, 3))
                r = np.abs(Czt - (P - pm[:, :, None, None])).mean(axis=(2, 3))
                r = np.where(np.isnan(pm), np.inf, r)
                better = r < fr_
                fr_ = np.where(better, r, fr_)
                fy, fx, fm = np.where(better, ty, fy), np.where(better, tx, fx), np.where(better, pm, fm)
        oy, ox, best_m, best_r = fy, fx, fm, fr_
    code = np.zeros((nby, nbx), dtype=np.int8)
    fin = best_r[np.isfinite(best_r)]
    # render noise differs from frame to frame and no shift removes it: the residual a well-matched block still has is
    # taken from the better matched third of the blocks, between the fixed 0.01 and NOISE_CAP
    floor = float(np.clip(1.5 * np.percentile(fin, 30), 0.01, NOISE_CAP)) if fin.size else 0.01
    code[~np.isfinite(best_r) | (best_r > np.maximum(floor, ratio * dev))] = 1
    code[(code == 0) & rival] = 2
    # the range of block means over every candidate that fits about as well as the best: what an ambiguous block's
    # prediction could be (the best candidate's refined mean is included)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN column: no candidate inside the frame
        lo = np.fmin(np.nanmin(np.where(near, means, np.nan), axis=0), best_m)
        hi = np.fmax(np.nanmax(np.where(near, means, np.nan), axis=0), best_m)
    return np.where(code == 0, best_m, np.nan), code, oy, ox, lo, hi, best_r


def _match(cur, ref, y0, x0, nby, nbx, bh, bw, R, margin, ratio, mean_tol, unit=1):
    """`_match_window` in two tiers: the window of 8 x `unit` px (or R if smaller) first (exhaustive at full resolution when
    unit is 1, else searched on unit x unit averaged copies, every shift a multiple of unit then +-1 px), and the wide window
    (up to R, coarse to fine) only for the blocks that found no match in it, and only when they are at least
    `WIDE_MIN_SHARE` of the blocks (a few unmatched blocks are an object edge or a frame border, not a fast camera, and the
    wide search costs about as much as the first one). A wide window offers more look-alike candidates, so searching it
    first would turn plain smooth content ambiguous; the blocks a small window cannot follow are the ones that need it."""
    w1 = 8 * unit
    res = _match_window(cur, ref, y0, x0, nby, nbx, bh, bw, min(R, w1), margin, ratio, mean_tol, S=unit, unit=unit)
    if R > w1 and (res[1] == 1).mean() >= WIDE_MIN_SHARE:
        wide = _match_window(cur, ref, y0, x0, nby, nbx, bh, bw, R, margin, ratio, mean_tol, S=2 * unit, unit=unit)
        C = cur[y0:y0 + nby * bh, x0:x0 + nbx * bw].reshape(nby, bh, nbx, bw)
        texture = np.abs(C - C.mean(axis=(1, 3))[:, None, :, None]).mean(axis=(1, 3))
        # a nearly flat block fits any flat place in a wide window: it is only taken when it has more texture than the
        # ambiguity margin, i.e. when "fits about as well" can tell places apart
        take = (res[1] == 1) & (wide[1] != 1) & (texture >= margin)
        res = tuple(np.where(take, w, r) for r, w in zip(res, wide))
    return res


def _grab(F, ys, xs, ky, kx, R, sub):
    """Cells of the R-padded frame F at (ys + ky, xs + kx): ys, xs are [K, c] pixel indices, ky, kx [K] shifts."""
    return F[(ys[:, ::sub] + R + ky[:, None])[:, :, None], (xs[:, ::sub] + R + kx[:, None])[:, None, :]]


def _dropouts(frames, t, cell, R, level, flat_dev, gap, step=1):
    """Cells of frame t that went flat black or white while the frames either side agree there: (x0, y0, x1, y1, dev).
    Only candidate cells are searched: t is nearly uniform (mean abs deviation <= flat_dev) and its mean is within `level`
    of 0 or 1. For those, t-1 and t+1 are compared at the same place, shifted symmetrically by up to R px per frame
    (every `step`-th shift on every (2 x step)-th px, then +-step px of the best at full resolution; step is 1 at 640x360) and the smallest raw difference is kept:
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
    sub = (2 if cell >= 8 * step else 1) * step
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
    nstep = R // step
    for ky, kx in sorted(((a * step, b * step) for a in range(-nstep, nstep + 1) for b in range(-nstep, nstep + 1)),
                         key=lambda k: abs(k[0]) + abs(k[1])):
        try_shift(np.full(K, ky), np.full(K, kx), sub)
    typical = np.median(np.stack(coarse), axis=0)
    cy0, cx0 = by.copy(), bx.copy()
    best[:] = np.inf
    for dy in range(-step, step + 1):
        for dx in range(-step, step + 1):
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


def _supported(flagged):
    """The flagged blocks (x0, y0, x1, y1, dev, need) that sit in a group of touching blocks of the same sign at least as large
    as the biggest `need` in it. A block matched exactly needs 1; a block of the leftover edge strip needs 2; a block whose
    match was ambiguous needs 4 (a 32 x 32 px area at the default block): an ambiguous or edge block is weak evidence, and
    one alone over the threshold is an object edge or a chance match far more often than a defect."""
    if not flagged or all(len(f) < 6 or f[5] <= 1 for f in flagged):
        return flagged
    n = len(flagged)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            a, b = flagged[i], flagged[j]
            if a[4] * b[4] > 0 and a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                parent[find(i)] = find(j)
    size, need = {}, {}
    for i in range(n):
        r = find(i)
        size[r] = size.get(r, 0) + 1
        need[r] = max(need.get(r, 1), flagged[i][5] if len(flagged[i]) > 5 else 1)
    return [flagged[i] for i in range(n) if size[find(i)] >= need[find(i)]]


def _natural_files(d):
    names = [f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in IMG_EXT]
    return [os.path.join(d, f) for f in sorted(names, key=_natural)]


def main(paths=None, dir=None, block=None, max_motion_px=None, scale=None, flicker_threshold=0.03, reject_ratio=0.5,
         ambiguity_margin=0.02, bound=0.09, slack=0.5, ambiguous_support=4, global_fraction=0.6, min_measured=0.5, dropout_level=0.015, dropout_flat_dev=0.01,
         dropout_gap=0.02, neighbour_agreement=0.5):
    if bool(paths) == bool(dir):
        raise ValueError("pass exactly one of 'paths' or 'dir'")
    files = list(paths) if paths else _natural_files(dir)
    if len(files) < 3:
        raise ValueError(f"need at least 3 frames, got {len(files)}")
    for f in files:
        if not os.path.isfile(f):
            raise ValueError(f"frame not found: {f}")
    thr = float(flicker_threshold)
    frames = [_load_luma(f) for f in files]
    H, W = frames[0].shape
    if any(fr.shape != (H, W) for fr in frames):
        raise ValueError("all frames must have the same size")
    # Every pixel-sized default was tuned at 640x360 and is multiplied by the frame scale: the shorter side over 360, rounded
    # to a whole number (1 up to 539 px, 2 at 720p, 3 at 1080p, 6 at 4K). An explicit `block` / `max_motion_px` wins as given.
    sc = max(1, int(round(min(H, W) / 360.0))) if scale is None else int(scale)
    if sc < 1:
        raise ValueError("'scale' must be >= 1")
    B = int(block) if block is not None else 16 * sc
    R = int(max_motion_px) if max_motion_px is not None else 24 * sc
    if B < 4 or R < 0:
        raise ValueError("'block' must be >= 4 and 'max_motion_px' >= 0")
    # The coarse searches average sc x sc (first window) and 2sc x 2sc (wide window) px, which needs a block that divides by
    # both; otherwise (an explicit odd block) they run at full resolution as at 640x360, and the search scale is 1.
    us = sc if B % (2 * sc) == 0 else 1
    if H < B or W < B:
        raise ValueError(f"frames {W}x{H} are smaller than one {B}px block")
    # The blocks tile the frame from the top-left. A size that is not a multiple of B leaves a bottom strip and/or a right
    # strip (at least 4 px: a smaller remainder overlaps the main grid). A thin block of the leftover size matches anything
    # it is flat in and cannot see content entering the strip, so its motion is taken from the full B x B block that ends
    # where the strip begins (real context), and the strip pixels are then scored at that motion: the region reported is the
    # strip itself, and a defect inside it is neither diluted nor taken for part of the match.
    nby, nbx = H // B, W // B
    smin = 4 * sc  # a smaller leftover overlaps the main grid
    hs, ws = max(H - nby * B, smin) if H % B else 0, max(W - nbx * B, smin) if W % B else 0
    regions = [(0, 0, nby, nbx, B, B, None)]  # y0, x0, rows of blocks, cols of blocks, block h, w, scored sub-rectangle
    yb, xr = max(0, H - hs - B), max(0, W - ws - B)  # origin of the context block above / left of a strip
    # Each strip is scored twice, by two motion estimates for the same pixels: (1) from the block that ends where the strip
    # begins and (2) from the block that ends flush with the frame edge (it overlaps the grid and contains the strip). (1)
    # alone cannot see content that enters the strip (a shadow edge sliding in gave a false event on clean 1080p), so a strip
    # flag of (1) is dropped when (2) measured the same pixels and found them within the threshold, or found its own match
    # ambiguous (the strip content can be explained at several brightnesses). When (2) could not match its block at all
    # (rejected: a real defect in the strip spoils the match) the flag stands. (2) scores nothing else.
    yf, xf = H - B, W - B
    if hs:
        regions.append((yb, 0, 1, nbx, B, B, (H - hs - yb, H - yb, 0, B)))
        regions.append((yf, 0, 1, nbx, B, B, (max(0, B - hs), B, 0, B), True))
    if ws:
        regions.append((0, xr, nby, 1, B, B, (0, B, W - ws - xr, W - xr)))
        regions.append((0, xf, nby, 1, B, B, (0, B, max(0, B - ws), B), True))
    if hs and ws:
        regions.append((yb, xr, 1, 1, B, B, (H - hs - yb, H - yb, W - ws - xr, W - xr)))
        regions.append((yf, xf, 1, 1, B, B, (max(0, B - hs), B, max(0, B - ws), B), True))
    _POOL.clear()

    per_frame = {t: {"frame": t, "file": os.path.basename(files[t]), "measured": 0,
                     "not_measured": {"high_residual": 0, "ambiguous": 0}, "ambiguous_ranged": 0, "blocks": 0,
                     "max_abs_dev": None}
                 for t in range(1, len(frames) - 1)}
    flagged_by_t = {t: [] for t in per_frame}  # (x0, y0, x1, y1, dev) of blocks over the threshold
    step_by_t = {t: [] for t in per_frame}  # the same for blocks that equal one neighbour and differ from the other
    drops_by_t = {t: [] for t in per_frame}  # the same for dropout blocks (rejected by the match, neighbours agree)
    dev_at = {t: {} for t in per_frame}  # (x0, y0) of a block -> its signed deviation in frame t (measured blocks only)
    foot_at = {t: {} for t in per_frame}  # (x0, y0, neighbour frame) -> (x, y, w, h) of the matched footprint there
    totals = {"high_residual": 0, "ambiguous": 0}
    ranged_total = 0
    meas_mask = {t: np.zeros((H, W), dtype=bool) for t in per_frame}  # pixels of measured blocks
    n_meas = n_all = 0
    strip_a = {t: [] for t in per_frame}  # strip flags of the first estimate, and the strip blocks the second found quiet
    strip_b = {t: set() for t in per_frame}
    for (ry, rx, ny, nx, bh, bw, sub, *aux) in regions:
        r0, r1, c0, c1 = sub or (0, bh, 0, bw)
        for t in range(1, len(frames) - 1):
            mp, cp, pyo, pxo, lop, hip, rsp = _match(frames[t], frames[t - 1], ry, rx, ny, nx, bh, bw, R, ambiguity_margin, reject_ratio, thr / 2, us)
            mn, cn, nyo, nxo, lon, hin, rsn = _match(frames[t], frames[t + 1], ry, rx, ny, nx, bh, bw, R, ambiguity_margin, reject_ratio, thr / 2, us)
            code = np.maximum(cp, cn)
            rej = (cp == 1) | (cn == 1)  # a rejected match is no evidence at all, whatever the other neighbour says (ambiguous or not)
            tmean = frames[t][ry:ry + ny * bh, rx:rx + nx * bw].reshape(ny, bh, nx, bw).mean(axis=(1, 3))
            if sub:  # score only the leftover pixels of an edge block, at the offsets the whole block matched at
                gy, gx = np.nonzero(code == 0)
                z = np.zeros(len(gy), dtype=int)
                sm = np.full((ny, nx), np.nan)
                spm, snm = sm.copy(), sm.copy()
                if len(gy):
                    sm[gy, gx] = _gather(frames[t], gy, gx, ry, rx, bh, bw, z, z, sub).mean(axis=(1, 2))
                    spm[gy, gx] = _gather(frames[t - 1], gy, gx, ry, rx, bh, bw, pyo[gy, gx], pxo[gy, gx], sub).mean(axis=(1, 2))
                    snm[gy, gx] = _gather(frames[t + 1], gy, gx, ry, rx, bh, bw, nyo[gy, gx], nxo[gy, gx], sub).mean(axis=(1, 2))
                tmean, mp, mn = sm, spm, snm
            # An ambiguous block (several candidates fit about as well, with different means) has a prediction known only
            # as a range [lo, hi] per neighbour. Its deviation is then a range too, and the block is scored by the end nearest
            # zero: it is a flicker only when every candidate says so. It counts as measured when that range is narrow
            # enough (`bounded`) to certify that no deviation above `bound` hides in it.
            if sub:
                Pl, Ph, Nl, Nh = mp, mp, mn, mn
                bounded = code == 0
            else:
                Pl, Ph = np.where(cp == 0, mp, lop), np.where(cp == 0, mp, hip)
                Nl, Nh = np.where(cn == 0, mn, lon), np.where(cn == 0, mn, hin)
                d_hi, d_lo = tmean - 0.5 * (Pl + Nl), tmean - 0.5 * (Ph + Nh)
                bounded = (code == 0) | ((code == 2) & ~rej & (((d_hi - d_lo) <= bound) | (d_lo > thr) | (d_hi < -thr)))
            if sub:
                dev = tmean - 0.5 * (mp + mn)
            else:
                dev = np.where(d_lo > 0, d_lo, np.where(d_hi < 0, d_hi, 0.0))  # signed, nearest zero; NaN where not measured
            dev[~bounded] = np.nan
            gap = np.maximum(0.0, np.maximum(Pl, Nl) - np.minimum(Ph, Nh))  # how far apart the neighbours' predictions must be
            # Ambiguous blocks are not scored: a block no candidate match explains is not evidence of flicker.
            # A flicker moves the whole block: the middle half of the per-pixel differences against the matched
            # neighbours (interquartile mean) must show it too. An object edge crossing the block changes the mean but
            # not most of the pixels.
            cdev = dev.copy()
            # a match that leaves a residual is evidence with that much slack: the deviation must clear the threshold by
            # half the worse of the two residuals (exact matches, as in a static or a cleanly panning shot, lose nothing)
            thr_eff = thr + slack * np.maximum(rsp, rsn)
            lvl = np.full(cdev.shape, 2.0 if sub else 1.0)  # how many touching blocks a flag needs (see _supported)
            if not sub:
                lvl[(cp == 2) | (cn == 2)] = float(ambiguous_support)
            cy_, cx_ = np.nonzero(np.abs(cdev) > thr_eff)
            if len(cy_):
                zz = np.zeros(len(cy_), dtype=int)
                Cb = _gather(frames[t], cy_, cx_, ry, rx, bh, bw, zz, zz, sub)
                Pb = _gather(frames[t - 1], cy_, cx_, ry, rx, bh, bw, pyo[cy_, cx_], pxo[cy_, cx_], sub)
                Nb = _gather(frames[t + 1], cy_, cx_, ry, rx, bh, bw, nyo[cy_, cx_], nxo[cy_, cx_], sub)
                d = np.sort((Cb - 0.5 * (Pb + Nb)).reshape(len(cy_), -1), axis=1)
                q = d.shape[1] // 4
                iqm = d[:, q:d.shape[1] - q].mean(axis=1)
                robust = np.sign(iqm) == np.sign(cdev[cy_, cx_])
                robust &= np.abs(iqm) > thr
                cdev[cy_[~robust], cx_[~robust]] = np.nan
            # A flicker is a pulse: the two neighbours agree with each other (the same content at the same brightness)
            # and the frame differs from both. A step, where the frame equals one neighbour and not the other (the
            # neighbours' means are more than `neighbour_agreement` x the deviation apart), is an object arriving or leaving
            # or a light changing for good: it is not an event by itself. It is kept as a candidate, because a flicker
            # that lasts two frames looks like two steps in a row at the same place (see below).
            step = gap > neighbour_agreement * np.abs(dev)
            sdev = np.where(step, cdev, np.nan)
            cdev = np.where(step, np.nan, cdev)
            if aux:  # the second estimate of a strip: which strip blocks it measured and found quiet; nothing is counted
                for y, x in zip(*np.nonzero((bounded & (np.abs(dev) <= thr_eff)) | ((code == 2) & ~rej))):  # NaN compares False
                    strip_b[t].add((rx + int(x) * bw + c0, ry + int(y) * bh + r0, rx + int(x) * bw + c1, ry + int(y) * bh + r1))
                continue
            for y, x in zip(*np.nonzero(np.abs(sdev) > thr_eff)):
                step_by_t[t].append((rx + int(x) * bw + c0, ry + int(y) * bh + r0, rx + int(x) * bw + c1, ry + int(y) * bh + r1,
                                     float(sdev[y, x]), int(lvl[y, x])))
            hi, amb, rng_ = int(rej.sum()), int(((code == 2) & ~rej).sum()), int(((code == 2) & bounded).sum())
            meas = int(bounded.sum())
            totals["high_residual"] += hi
            totals["ambiguous"] += amb
            ranged_total += rng_
            n_meas += meas
            n_all += code.size
            pf = per_frame[t]
            pf["measured"] += meas
            pf["not_measured"]["high_residual"] += hi
            pf["not_measured"]["ambiguous"] += amb
            pf["ambiguous_ranged"] += rng_
            pf["blocks"] += code.size
            if meas:
                m = round(float(np.nanmax(np.abs(dev))), 5)
                pf["max_abs_dev"] = m if pf["max_abs_dev"] is None else max(pf["max_abs_dev"], m)
            for y, x in zip(*np.nonzero(~np.isnan(dev))):
                dev_at[t][(rx + int(x) * bw, ry + int(y) * bh, bw, bh)] = float(dev[y, x])
                # where this block's content sits in the previous / next frame (its motion match)
                for u, oy_, ox_ in ((t - 1, pyo, pxo), (t + 1, nyo, nxo)):
                    foot_at[t][(rx + int(x) * bw, ry + int(y) * bh, u)] = (
                        rx + int(x) * bw + int(ox_[y, x]), ry + int(y) * bh + int(oy_[y, x]), bw, bh)
            ys, xs = np.nonzero(np.abs(cdev) > thr_eff)  # NaN compares False
            mine = [(rx + int(x) * bw + c0, ry + int(y) * bh + r0, rx + int(x) * bw + c1, ry + int(y) * bh + r1,
                     float(cdev[y, x]), int(lvl[y, x])) for y, x in zip(ys, xs)]
            if sub:
                strip_a[t] += mine
            else:
                flagged_by_t[t] += mine
            if sub:
                for y, x in zip(*np.nonzero(bounded)):
                    meas_mask[t][ry + int(y) * bh + r0:ry + int(y) * bh + r1, rx + int(x) * bw + c0:rx + int(x) * bw + c1] = True
            else:
                meas_mask[t][ry:ry + ny * bh, rx:rx + nx * bw] |= np.repeat(np.repeat(bounded, bh, axis=0), bw, axis=1)
    for t, mine in strip_a.items():  # a strip flag the second estimate measured as quiet is dropped
        flagged_by_t[t] += [f for f in mine if f[:4] not in strip_b[t]]
    # a flicker that lasts two frames: the same block is a step of the same sign and size in two consecutive frames
    for t, steps in step_by_t.items():
        for f in steps:
            for u in (t - 1, t + 1):
                if any(g[:2] == f[:2] and g[4] * f[4] > 0 and 0.5 <= abs(g[4]) / abs(f[4]) <= 2.0 for g in step_by_t.get(u, [])):
                    flagged_by_t[t].append(f)
                    break
    cell = max(4, B // 2)
    for t in per_frame:
        drops_by_t[t] = _dropouts(frames, t, cell, min(R, 8 * us), dropout_level, dropout_flat_dev, dropout_gap, us)

    events = []
    unconfirmed = []
    for t, flagged in flagged_by_t.items():
        # a one-frame bump also shows at half size, opposite sign, in its neighbours, at the place the motion match
        # carries it to: drop a block whose deviation is smaller than that of a block of the opposite sign overlapping the
        # footprint it matched to in an adjacent frame (the same sign is a flicker lasting two frames, not an echo) (per block and per match, so an independent event elsewhere survives)
        def echo(f, t=t):
            for u in (t - 1, t + 1):
                fx, fy, fw, fh = foot_at[t].get((f[0], f[1], u), (f[0], f[1], f[2] - f[0], f[3] - f[1]))
                for (bx, by, bw_, bh_), d in dev_at.get(u, {}).items():
                    ov = max(0, min(fx + fw, bx + bw_) - max(fx, bx)) * max(0, min(fy + fh, by + bh_) - max(fy, by))
                    if ov >= 0.25 * min(fw * fh, bw_ * bh_) and abs(d) > 1.5 * abs(f[4]) and d * f[4] < 0:
                        return True
                # the same for a dropout in the adjacent frame: a block matched into or beside a region that went flat there
                # (a cell wide on each side: the edge of the region is only partly flat) differs because of it
                for (x0_, y0_, x1_, y1_, _d) in drops_by_t.get(u, []):
                    x0_, y0_, x1_, y1_ = x0_ - cell, y0_ - cell, x1_ + cell, y1_ + cell
                    ov = max(0, min(fx + fw, x1_) - max(fx, x0_)) * max(0, min(fy + fh, y1_) - max(fy, y0_))
                    if ov >= 0.25 * min(fw * fh, (x1_ - x0_) * (y1_ - y0_)):
                        return True
            return False

        flagged = _supported([f for f in flagged if not echo(f)])
        drops = drops_by_t[t]
        flagged = flagged + drops
        if not flagged:
            continue
        meas = per_frame[t]["measured"]
        # kind: the share of pixels affected, as a UNION (a block and a dropout cell over the same pixels count once, and so
        # do overlapping edge blocks), out of the pixels that were measured or flagged
        hit = np.zeros((H, W), dtype=bool)
        for f in flagged:
            hit[f[1]:f[3], f[0]:f[2]] = True
        kind = "global_exposure" if hit.sum() >= global_fraction * (hit | meas_mask[t]).sum() else "local"
        pf = per_frame[t]
        total_t = pf["blocks"]
        if kind == "local" and not drops and total_t and pf["measured"] < min_measured * total_t:
            # blocks from a frame where most of the picture could not be followed (a fast camera, lights moving, everything
            # changing shape): the few that matched are as likely to be a chance match as a defect. Not an event; the frame
            # is listed in unmeasured_frames and the verdict is inconclusive. A dropout (flat black / white region) is
            # judged by its own rule and is not demoted.
            unconfirmed.append({"frame": t, "file": os.path.basename(files[t]), "blocks": [[f[0], f[1], round(f[4], 5)] for f in flagged[:8]]})
            continue
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
        total_t = pf["blocks"]
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
    return {"verdict": verdict, "events": events, "unconfirmed_events": unconfirmed, "unmeasured_frames": unmeasured_frames,
            "frames": len(frames), "evaluated_frames": len(per_frame),
            "scale": sc, "block_px": B, "max_motion_px": R, "dropout_search_px": min(R, 8 * us), "cell_px": cell,
            "scaled_defaults": [k for k, v in (("block", block), ("max_motion_px", max_motion_px)) if v is None], "flicker_threshold": thr,
            "measured_blocks": n_meas, "total_blocks": n_all, "measured_share": round(share, 4),
            "not_measured": {"blocks": n_all - n_meas, **totals}, "ambiguous_ranged": ranged_total,
            "per_frame": [per_frame[t] for t in sorted(per_frame)],
            "domain": f"motion up to {R}px per frame in x and y between consecutive frames; blocks outside it, "
                      "ambiguous matches and occlusions are not_measured, never counted as a pass"}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
