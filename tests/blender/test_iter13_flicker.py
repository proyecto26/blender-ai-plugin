"""Headless Blender tests for batch A of iteration 13: film-production/flicker_check.py on motion, edge strips, event kind and
injected tiles. Every check here fails on c1999f5 (the iteration 12 code). Writes <out_dir>/iter13_flicker_report.json
(passed / total / failed / failures). A crash is recorded as a failed check, so the report always exists.

    blender -b --factory-startup --python tests/blender/test_iter13_flicker.py -- '{"out_dir": "/tmp/iter13_flicker"}'
"""
import json
import os
import runpy
import sys
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
N = 9


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(args):
    path = os.path.join(SKILLS, "film-production", "scripts", "flicker_check.py")
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def save_gray(path, arr):
    h, w = arr.shape
    img = bpy.data.images.new("tmp_iter13_fixture", w, h, alpha=True)
    try:
        img.colorspace_settings.name = "Non-Color"
        rgba = np.ones((h, w, 4), dtype=np.float32)
        rgba[..., :3] = np.clip(arr[::-1], 0, 1)[..., None]
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def seq(folder, frames):
    os.makedirs(folder, exist_ok=True)
    paths = []
    for i, fr in enumerate(frames):
        p = os.path.join(folder, f"f_{i:02d}.png")
        save_gray(p, fr)
        paths.append(p)
    return paths


def noise(h, w, seed):
    """Lightly smoothed noise, values about 0.05..0.65: a texture with no repeats."""
    rng = np.random.default_rng(seed)
    t = rng.random((h + 2, w + 2)).astype(np.float32)
    s = sum(t[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)) / 9.0
    return 0.05 + 0.6 * (s - s.min()) / (s.max() - s.min())


def summary(r):
    return (r["verdict"], [(e["frame"], e["kind"], e["region_px"]) for e in r["events"]][:3], r["measured_share"])


def run_all(out_dir, check):
    base = os.path.join(out_dir, "iter13_flicker")
    W, H = 320, 184  # 184 = 11 * 16 + 8: an 8 px strip is left at the bottom, as in 1080 and 360

    # A1: a camera pan faster than 8 px a frame, on both axes, with the default search: a clean pass, not "inconclusive"
    world = noise(H + N * 12 + 8, W + N * 14 + 8, 1)
    fr = [world[t * 12:t * 12 + H, t * 14:t * 14 + W].copy() for t in range(N)]
    r = run({"paths": seq(os.path.join(base, "pan"), fr)})
    check("pan of 14 x 12 px a frame, default window: pass, no event", r["verdict"] == "pass" and not r["events"], summary(r))
    fr[4] = fr[4].copy()
    fr[4][48:96, 96:160] += 0.15
    r = run({"paths": seq(os.path.join(base, "pan_flicker"), fr)})
    ev = r["events"]
    check("a +0.15 tile in that pan is found at frame 4, within one block of the box",
          r["verdict"] == "flicker" and [e["frame"] for e in ev] == [4]
          and max(abs(a - b) for a, b in zip(ev[0]["region_px"], [96, 48, 160, 96])) <= 16, summary(r))

    # A1: a flat-faced object moving 16 px a frame over a static texture gives no event (it did, at its edges)
    tex = noise(H, W, 8)
    for speed in (10, 16):
        fr = []
        for t in range(N):
            f = tex.copy()
            x = 20 + t * speed
            f[70:110, x:x + 30] = 0.75
            f[70:110, x + 30:x + 44] = 0.35
            fr.append(f)
        r = run({"paths": seq(os.path.join(base, f"box{speed}"), fr)})
        check(f"flat-faced object at {speed} px a frame: no event", not r["events"] and r["verdict"] != "flicker", summary(r))

    # A1: the edge strip. 184 = 11 * 16 + 8. A clean pan has no event there ...
    world = noise(H + 40, W + 40, 4)

    def panned():
        return [world[t * 2:t * 2 + H, t * 3:t * 3 + W].copy() for t in range(N)]
    r = run({"paths": seq(os.path.join(base, "strip_clean"), panned())})
    check("clean pan with an 8 px bottom strip: pass", r["verdict"] == "pass" and not r["events"], summary(r))
    # ... and a defect inside the strip is found, with the strip as its region
    fr = panned()
    fr[4][H - 8:H, 64:160] += 0.15
    r = run({"paths": seq(os.path.join(base, "strip_defect"), fr)})
    ev = r["events"]
    check("a +0.15 defect in the 8 px bottom strip of a pan is found at frame 4, region in the strip",
          [e["frame"] for e in ev] == [4] and ev[0]["region_px"][1] >= H - 8 and ev[0]["region_px"][3] == H
          and ev[0]["region_px"][0] <= 80 and ev[0]["region_px"][2] >= 144, summary(r))
    W2 = W + 4  # 324 = 20 * 16 + 4: a 4 px strip is left at the right
    world2 = noise(H + 40, W2 + 40, 6)
    fr = [world2[t * 2:t * 2 + H, t * 3:t * 3 + W2].copy() for t in range(N)]
    fr[4][32:96, W2 - 4:W2] += 0.15
    r = run({"paths": seq(os.path.join(base, "strip_right"), fr)})
    ev = r["events"]
    check("a defect in the 4 px right strip of a pan is found at frame 4, region ends at the frame edge",
          [e["frame"] for e in ev] == [4] and ev[0]["region_px"][2] == W2, summary(r))

    # A3: kind is the union of affected pixels. A band over a third of a flat frame is local, not global
    for label, level in (("black", 0.0), ("bright", 0.8)):
        fr = [np.full((H, W), 0.5, np.float32) for _ in range(N)]
        fr[4][:, 0:112] = level
        r = run({"paths": seq(os.path.join(base, f"band_{label}"), fr)})
        ev = r["events"]
        check(f"a band over 35% of a flat frame going {label} for one frame: one event at frame 4, kind local",
              [e["frame"] for e in ev] == [4] and ev[0]["kind"] == "local" and ev[0]["region_px"] == [0, 0, 112, H], summary(r))
    fr = [np.full((H, W), 0.5, np.float32) for _ in range(N)]
    fr[4][:, 0:240] = 0.0
    r = run({"paths": seq(os.path.join(base, "band_big"), fr)})
    check("a band over 75% of a flat frame is still global_exposure",
          [e["kind"] for e in r["events"]] == ["global_exposure"], summary(r))

    # A2: real content change stays flagged: a light off for one frame, a strobe
    fr = [tex.copy() for _ in range(N)]
    fr[4] = fr[4] * 0.3
    r = run({"paths": seq(os.path.join(base, "light_off"), fr)})
    check("a light off for one frame: global_exposure at frame 4",
          r["verdict"] == "flicker" and [(e["frame"], e["kind"]) for e in r["events"]] == [(4, "global_exposure")], summary(r))
    fr = [tex.copy() * (1.0 if t % 2 else 0.4) for t in range(N)]
    r = run({"paths": seq(os.path.join(base, "strobe"), fr)})
    check("a strobe: flicker", r["verdict"] == "flicker" and len(r["events"]) >= 4, summary(r))

    # A2: a flicker that lasts two frames is still found (it is two steps in a row at the same place)
    fr = [tex.copy() for _ in range(N)]
    for k in (4, 5):
        fr[k] = fr[k].copy()
        fr[k][48:112, 96:192] += 0.15
    r = run({"paths": seq(os.path.join(base, "two_frame"), fr)})
    check("a +0.15 tile for two frames (4 and 5): flicker, events at 4 and 5 only",
          r["verdict"] == "flicker" and [e["frame"] for e in r["events"]] == [4, 5], summary(r))

    # A2: a tile with an odd position injected into a textured frame (and into a pan): found, region within one block, local
    Wb, Hb = 640, 360
    big = noise(Hb, Wb, 12)
    box = (200, 120, 296, 216)
    fr = [big.copy() for _ in range(N)]
    fr[4][box[1]:box[3], box[0]:box[2]] += 0.15
    r = run({"paths": seq(os.path.join(base, "tile_static"), fr)})
    ev = r["events"]
    err = max(abs(a - b) for a, b in zip(ev[0]["region_px"], box)) if ev else None
    check("a +0.15 tile at [200,120,296,216] in a 640x360 frame: one event at frame 4, kind local, region error <= 16 px",
          [e["frame"] for e in ev] == [4] and ev[0]["kind"] == "local" and err is not None and err <= 16, (summary(r), err))
    bigw = noise(Hb + 40, Wb + 60, 13)
    fr = [bigw[t * 3:t * 3 + Hb, t * 6:t * 6 + Wb].copy() for t in range(N)]
    fr[4][box[1]:box[3], box[0]:box[2]] += 0.15
    r = run({"paths": seq(os.path.join(base, "tile_pan"), fr)})
    ev = r["events"]
    err = max(abs(a - b) for a, b in zip(ev[0]["region_px"], box)) if ev else None
    check("the same tile in a pan of 6 x 3 px a frame: one event at frame 4, kind local, region error <= 16 px",
          [e["frame"] for e in ev] == [4] and ev[0]["kind"] == "local" and err is not None and err <= 16, (summary(r), err))

    # Round 3 (these fail on bc9cf8e, where every block of a smooth floor was "ambiguous" and nothing there was scored):
    # a smooth floor (a steep gradient: a shift of a few px changes a block's mean), and a slow push-in over flat shapes.
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    floor = 0.8 * np.clip(0.05 + 0.9 * xx / W + 0.1 * yy / H, 0, 1)
    tile = (96, 48, 160, 96)

    def near(ev, box):
        return bool(ev) and max(abs(a - b) for a, b in zip(ev[0]["region_px"], box)) <= 16

    fr = [floor.copy() for _ in range(N)]
    fr[4] = fr[4].copy()
    fr[4][tile[1]:tile[3], tile[0]:tile[2]] += 0.2
    r = run({"paths": seq(os.path.join(base, "floor_tile"), fr)})
    check("a +0.2 tile on a smooth floor in one frame: one event at frame 4, region within one block",
          [e["frame"] for e in r["events"]] == [4] and near(r["events"], tile), summary(r))
    fr = [floor.copy() for _ in range(N)]
    for k in (4, 5):
        fr[k] = fr[k].copy()
        fr[k][tile[1]:tile[3], tile[0]:tile[2]] += 0.2
    r = run({"paths": seq(os.path.join(base, "floor_tile2"), fr)})
    check("the same tile for two frames: events at 4 and 5 only, each region within one block",
          [e["frame"] for e in r["events"]] == [4, 5] and near(r["events"], tile) and near(r["events"][1:], tile), summary(r))
    for size, expect in ((16, False), (32, True)):
        fr = [floor.copy() for _ in range(N)]
        fr[4] = fr[4].copy()
        fr[4][48:48 + size, 96:96 + size] += 0.2
        r = run({"paths": seq(os.path.join(base, f"floor_lone{size}"), fr)})
        check(f"a {size} px square on a smooth floor: {'an event at frame 4' if expect else 'no event'} (an ambiguous block alone is "
              "not evidence, four touching ones are)",
              ([e["frame"] for e in r["events"]] == [4]) if expect else (not r["events"] and r["verdict"] == "pass"), summary(r))

    def dolly():
        out = []
        for t in range(N):
            s = 1 + 0.01 * t  # a push-in about the centre
            X, Y = (xx - W / 2) / s + W / 2, (yy - H / 2) / s + H / 2
            f = 0.15 + 0.3 * Y / H + 0.2 * X / W
            for (x0, y0, x1, y1, v) in ((20, 20, 100, 120, 0.2), (200, 10, 300, 90, 0.7), (120, 90, 180, 140, 0.45)):
                f = np.where((X >= x0) & (X < x1) & (Y >= y0) & (Y < y1), v, f)
            out.append(f.astype(np.float32))
        return out
    r = run({"paths": seq(os.path.join(base, "dolly"), dolly())})
    check("a slow push-in over a smooth floor and flat shapes gets a verdict: pass, no event, more than half measured",
          r["verdict"] == "pass" and not r["events"] and r["measured_share"] > 0.5, summary(r))
    fr = dolly()
    fr[4] = fr[4].copy()
    fr[4][16:64, 112:176] += 0.2
    r = run({"paths": seq(os.path.join(base, "dolly_tile"), fr)})
    check("a +0.2 tile in that push-in is found at frame 4 only, region within one block",
          [e["frame"] for e in r["events"]] == [4] and near(r["events"], (112, 16, 176, 64)), summary(r))

    # Round 4: the pixel-sized defaults scale with the frame. Renders upscaled 2x (here 1280x720, a 640x360 texture doubled, a pan
    # of 14 x 12 px a frame at 1x = 28 x 24 px, beyond the old fixed window of 24) must get a verdict with the DEFAULTS.
    # These fail on the code before round 4 (block 16, window 24 at any size: "inconclusive" / no event).
    n2 = 6
    big = np.kron(noise(360 + n2 * 12 + 8, 640 + n2 * 14 + 8, 11), np.ones((2, 2), np.float32))

    def big_pan():
        return [big[t * 24:t * 24 + 720, t * 28:t * 28 + 1280].copy() for t in range(n2)]
    r = run({"paths": seq(os.path.join(base, "big_pan"), big_pan())})
    check("1280x720 pan of 28 x 24 px a frame, default ARGS: pass, no event; effective block 32 and window 48 are reported",
          r["verdict"] == "pass" and not r["events"] and r["block_px"] == 32 and r["max_motion_px"] == 48
          and r["scale"] == 2 and r["scaled_defaults"] == ["block", "max_motion_px"], summary(r))
    fr = big_pan()
    fr[3] = fr[3].copy()
    fr[3][240:432, 400:592] += 0.2
    r = run({"paths": seq(os.path.join(base, "big_pan_tile"), fr)})
    check("a +0.2 tile in that 1280x720 pan is found at frame 3 only, region within one (32 px) block, default ARGS",
          [e["frame"] for e in r["events"]] == [3]
          and max(abs(a - b) for a, b in zip(r["events"][0]["region_px"], [400, 240, 592, 432])) <= 32, summary(r))
    # (a black tile is searched within 8 x scale px, so it needs a pan of up to 16 px a frame, here 12 x 8)
    fr = [big[t * 8:t * 8 + 720, t * 12:t * 12 + 1280].copy() for t in range(n2)]
    fr[3][240:432, 400:592] = 0.0
    r = run({"paths": seq(os.path.join(base, "big_pan_black"), fr)})
    check("a black tile in that 1280x720 pan is found at frame 3, region within one block, default ARGS",
          [e["frame"] for e in r["events"]] == [3]
          and max(abs(a - b) for a, b in zip(r["events"][0]["region_px"], [400, 240, 592, 432])) <= 32, summary(r))
    fr = [big_pan()[0].copy() * (1.0 if t % 2 else 0.4) for t in range(n2)]
    r = run({"paths": seq(os.path.join(base, "big_strobe"), fr)})
    check("a strobe at 1280x720, default ARGS: flicker", r["verdict"] == "flicker" and len(r["events"]) >= 3, summary(r))
    r = run({"paths": seq(os.path.join(base, "big_pan_explicit"), big_pan()), "block": 32, "max_motion_px": 40})
    check("explicit ARGS win over the scaled defaults and are reported as given",
          r["block_px"] == 32 and r["max_motion_px"] == 40 and r["scaled_defaults"] == [], summary(r))
    r = run({"paths": [os.path.join(base, "pan", f"f_{i:02d}.png") for i in range(N)]})  # written by the first check
    check("at 320x184 the scale is 1: block 16, window 24, results as before",
          r["scale"] == 1 and r["block_px"] == 16 and r["max_motion_px"] == 24, summary(r))

    check("no images leaked", len([i for i in bpy.data.images if i.name.startswith("tmp_iter13")]) == 0)


def main():
    out_dir = _cli_args().get("out_dir") or os.path.join(os.getcwd(), "iter13_flicker_out")
    os.makedirs(out_dir, exist_ok=True)
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:600]})

    try:
        run_all(out_dir, check)
    except Exception:
        check("suite crashed", False, traceback.format_exc()[-800:])
    failed = [r for r in results if not r["ok"]]
    report = {"passed": len(results) - len(failed), "total": len(results), "failed": len(failed),
              "failures": failed, "results": results}
    with open(os.path.join(out_dir, "iter13_flicker_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({k: report[k] for k in ("passed", "total", "failed")}))
    if failed and bpy.app.background:
        sys.exit(1)


main()
