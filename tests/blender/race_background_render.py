"""Start two background renders on one out_dir at the same moment and check that only one of them renders.

This starts real Blender processes, so run it with plain Python, not inside Blender:

    python3 tests/blender/race_background_render.py --blender <path to blender> [--rounds 3]

Exit 0 when every round has exactly one winner, a complete status, and a refusal from the loser saying another process
owns the folder. That refusal also shows the two really overlapped: a loser that started after the winner ended gets a
different message and fails the round, so a very slow start reads as a failure, never as a pass. The temporary folder is
printed and kept, so a failure can be inspected.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "skills", "rendering", "scripts", "background_render.py")
SCRATCH = """
import bpy, sys
s = bpy.context.scene
s.render.engine = "BLENDER_WORKBENCH"
s.render.resolution_x = s.render.resolution_y = 256
s.frame_start, s.frame_end = 1, 12
s.render.image_settings.media_type = "IMAGE"
s.render.image_settings.file_format = "PNG"
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
"""
LEAD_S = 25  # both processes wait for this moment, so that their checks overlap
TIMEOUT_S = 300


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _round(blender, blend, folder, overwrite):
    args_file = os.path.join(folder, "args.json")
    out_dir = os.path.join(folder, "out")
    with open(args_file, "w", encoding="utf-8") as fh:
        json.dump({"out_dir": out_dir, "overwrite": overwrite}, fh)
    go = time.time() + LEAD_S
    wait = f"import time; time.sleep(max(0, {go} - time.time()))"
    cmd = [blender, "-b", blend, "--python-exit-code", "1", "--python-expr", wait, "--python", SCRIPT,
           "--", "--args-file", args_file]
    procs = []
    try:
        for _ in range(2):
            procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        codes = [p.wait(timeout=TIMEOUT_S) for p in procs]
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=30)
    status = _read(os.path.join(out_dir, "render_status.json"))
    refused = _read(os.path.join(out_dir, "render_refused.json"))
    frames_dir = os.path.join(out_dir, "frames")
    frames = sorted(os.listdir(frames_dir)) if os.path.isdir(frames_dir) else []
    report = {"exit_codes": sorted(codes), "state": status and status["state"],
              "frames_done": status and status["frames_done"], "frames_total": status and status["frames_total"],
              "frames_on_disk": len(frames), "refused": refused and refused["error"]}
    report["passed"] = (report["exit_codes"] == [0, 1] and report["state"] == "done"
                        and report["frames_done"] == report["frames_total"] == report["frames_on_disk"] == 12
                        and "another" in (report["refused"] or ""))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    opts = parser.parse_args()
    base = tempfile.mkdtemp(prefix="render_race_")
    print("folder:", base)
    blend = os.path.join(base, "scratch.blend")
    subprocess.run([opts.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python-expr", SCRATCH,
                    "--", blend], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
    results = []
    # The last round passes overwrite: it must not let a second process past the one already rendering.
    for i in range(opts.rounds + 1):
        folder = os.path.join(base, f"round_{i}")
        os.makedirs(folder)
        result = _round(opts.blender, blend, folder, overwrite=i == opts.rounds)
        print(json.dumps(result))
        results.append(result)
    passed = all(r["passed"] for r in results)
    print("PASSED" if passed else "FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
