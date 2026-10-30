"""Headless Blender tests for ref_board.py and compare_to_refs.py (blender-mcp-workflow).

Synthesises reference PNGs with known content, runs the scripts, asserts on the results and writes
<out_dir>/refs_tests_report.json. Touches no scene; only images in bpy.data (which must be unchanged).

    blender -b --factory-startup --python tests/blender/test_refs.py -- '{"out_dir": "/tmp/refs_tests"}'
"""
import json
import os
import runpy
import sys
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "skills", "blender-mcp-workflow", "scripts"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(script, args):
    return runpy.run_path(os.path.join(SCRIPTS, script), init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def save_png(path, rgba):
    """rgba: (h, w, 4) floats 0-1 stored as-is in an 8-bit sRGB image."""
    h, w = rgba.shape[:2]
    img = bpy.data.images.new("tmp_ref_fixture", w, h, alpha=True)
    try:
        img.pixels.foreach_set(rgba.astype(np.float32).ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def two_tone(c1, c2, size=64):
    a = np.ones((size, size, 4), dtype=np.float32)
    a[:, : size // 2, :3] = hexrgb(c1)
    a[:, size // 2:, :3] = hexrgb(c2)
    return a


def hex_close(h1, h2, tol=8 / 255):
    return bool(np.abs(hexrgb(h1) - hexrgb(h2)).max() <= tol)


def run_all(out_dir):
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})

    os.makedirs(out_dir, exist_ok=True)
    refs = os.path.join(out_dir, "refs")
    single = os.path.join(out_dir, "refs_single")
    os.makedirs(refs, exist_ok=True)
    os.makedirs(single, exist_ok=True)
    ORANGE, BLUE = "#c86b3a", "#2b4c7e"
    tone = two_tone(ORANGE, BLUE)
    grad = np.ones((64, 64, 4), dtype=np.float32)
    grad[:, :, :3] = np.linspace(0, 1, 64, dtype=np.float32)[None, :, None]
    save_png(os.path.join(refs, "two_tone.png"), tone)
    save_png(os.path.join(refs, "gradient.png"), grad)
    save_png(os.path.join(single, "two_tone.png"), tone)

    # 1. palette recovers the known colours
    n0 = len(bpy.data.images)
    r1 = run("ref_board.py", {"ref_dir": refs, "out_path": os.path.join(out_dir, "bible_a.json")})
    check("images removed after ref_board", len(bpy.data.images) == n0, f"{n0} -> {len(bpy.data.images)}")
    check("two images read", r1["images_read"] == 2, r1["images_read"])
    bible = json.load(open(r1["out_path"], encoding="utf-8"))
    pal = [p["hex"] for p in next(i for i in bible["images"] if i["file"] == "two_tone.png")["stats"]["palette"]]
    check("palette has the two known colours",
          len(pal) == 2 and any(hex_close(p, ORANGE) for p in pal) and any(hex_close(p, BLUE) for p in pal), pal)
    wts = [p["weight"] for p in bible["images"][1]["stats"]["palette"]]
    check("palette weights ~50/50", all(abs(w - 0.5) < 0.02 for w in wts), wts)
    check("convention stated", "sRGB" in bible["convention"], bible["convention"][:40])
    check("histograms have 16 bins", len(bible["aggregate"]["luma"]["hist"]) == 16)

    # 2. deterministic
    run("ref_board.py", {"ref_dir": refs, "out_path": os.path.join(out_dir, "bible_b.json")})
    a = open(os.path.join(out_dir, "bible_a.json"), encoding="utf-8").read()
    b = open(os.path.join(out_dir, "bible_b.json"), encoding="utf-8").read()
    check("two runs give identical JSON", a == b)

    # sample cap
    rc = run("ref_board.py", {"ref_dir": refs, "out_path": os.path.join(out_dir, "bible_cap.json"), "max_pixels": 500})
    capd = json.load(open(rc["out_path"], encoding="utf-8"))
    check("max_pixels caps samples", all(i["stats"]["pixels"] <= 500 for i in capd["images"]),
          [i["stats"]["pixels"] for i in capd["images"]])

    # 3. identical image -> distance ~0, no drift
    sb = run("ref_board.py", {"ref_dir": single, "out_path": os.path.join(single, "style_bible.json")})
    cap_same = os.path.join(out_dir, "cap_same.png")
    save_png(cap_same, tone)
    n1 = len(bpy.data.images)
    same = run("compare_to_refs.py", {"bible": sb["out_path"], "captures": [cap_same]})
    check("images removed after compare", len(bpy.data.images) == n1, f"{n1} -> {len(bpy.data.images)}")
    check("identical: palette distance ~0", same["distances"]["palette"] < 0.01, same["distances"]["palette"])
    check("identical: no drift, score ~1", not same["drift"] and same["score"] > 0.98, (same["drift"], same["score"]))

    # 4. saturated copy
    sat = two_tone("#ff5500", "#0033ff")
    cap_sat = os.path.join(out_dir, "cap_sat.png")
    save_png(cap_sat, sat)
    rs = run("compare_to_refs.py", {"bible": sb["out_path"], "captures": [cap_sat]})
    check("saturated copy -> 'too saturated'", any("too saturated" in d for d in rs["drift"]), rs["drift"])
    check("saturated copy scores lower", rs["score"] < same["score"], rs["score"])

    # 5. brighter copy
    bright = tone.copy()
    bright[:, :, :3] = bright[:, :, :3] * 0.4 + 0.6
    cap_bright = os.path.join(out_dir, "cap_bright.png")
    save_png(cap_bright, bright)
    rb = run("compare_to_refs.py", {"bible": sb["out_path"], "captures": [cap_bright]})
    check("brighter copy -> 'bright' drift", any("bright" in d for d in rb["drift"]), rb["drift"])

    # missing accent: capture is only the blue half
    blue_only = two_tone(BLUE, BLUE)
    cap_blue = os.path.join(out_dir, "cap_blue.png")
    save_png(cap_blue, blue_only)
    rm = run("compare_to_refs.py", {"bible": sb["out_path"], "captures": [cap_blue]})
    check("missing orange -> palette missing finding",
          any("palette missing" in d and "warm" in d for d in rm["drift"]), rm["drift"])

    # 6. transparent padding ignored
    pad = np.zeros((64, 64, 4), dtype=np.float32)
    pad[:, :32, :3] = hexrgb(BLUE)
    pad[:, :32, 3] = 1.0
    pad[:, 32:, :3] = hexrgb("#ff0000")  # alpha 0: must be ignored
    padref = os.path.join(out_dir, "refs_pad")
    os.makedirs(padref, exist_ok=True)
    save_png(os.path.join(padref, "pad.png"), pad)
    rp = run("ref_board.py", {"ref_dir": padref})
    pb = json.load(open(rp["out_path"], encoding="utf-8"))
    check("transparent pixels dropped", pb["images"][0]["stats"]["pixels"] == 64 * 32, pb["images"][0]["stats"]["pixels"])
    check("transparent colour absent from palette",
          len(rp["palette"]) == 1 and hex_close(rp["palette"][0], BLUE), rp["palette"])
    check("default out_path is <ref_dir>/style_bible.json",
          rp["out_path"] == os.path.join(padref, "style_bible.json") and os.path.isfile(rp["out_path"]))

    # argument errors and CLI args
    def raises(fn):
        try:
            fn()
        except ValueError as exc:
            return str(exc)
        return None

    check("missing ref_dir -> ValueError", raises(lambda: run("ref_board.py", {"ref_dir": os.path.join(out_dir, "nope")})))
    check("bad bible -> ValueError", raises(lambda: run("compare_to_refs.py", {"bible": os.path.join(out_dir, "nope.json"),
                                                                              "captures": [cap_same]})))
    saved = sys.argv
    try:
        sys.argv = ["x", "--", "{not json"]
        msg = raises(lambda: runpy.run_path(os.path.join(SCRIPTS, "ref_board.py"), run_name="__skill_test__"))
        check("bad JSON -> clear ValueError", msg and "ARGS JSON" in msg, msg)
        af = os.path.join(out_dir, "args.json")
        json.dump({"ref_dir": padref, "out_path": os.path.join(out_dir, "bible_cli.json")}, open(af, "w"))
        sys.argv = ["x", "--", "--args-file", af]
        res = runpy.run_path(os.path.join(SCRIPTS, "ref_board.py"), run_name="__skill_test__")["result"]
        check("--args-file works", res["images_read"] == 1, res)
    finally:
        sys.argv = saved
    check("no images leaked overall", len(bpy.data.images) == n0, len(bpy.data.images))
    return results


def main(out_dir="/tmp/refs_tests"):
    try:
        results = run_all(out_dir)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": traceback.format_exc()[-600:]}]
    failures = [r for r in results if not r["ok"]]
    report = {"passed": len(results) - len(failures), "total": len(results), "failures": failures, "results": results}
    with open(os.path.join(out_dir, "refs_tests_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("passed", "total", "failures")}, indent=2))
