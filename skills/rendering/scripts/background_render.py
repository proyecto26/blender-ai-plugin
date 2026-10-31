"""Render the open file's animation in a background Blender and keep a status file, so a long render never blocks the
user's window. It refuses to run inside the window. Save the .blend first, because this process reads the file on disk.

    blender -b file.blend --python-exit-code 1 --python <skill_dir>/scripts/background_render.py -- --args-file args.json

ARGS:
    out_dir     (str, required) frames go in <out_dir>/frames, status in <out_dir>/render_status.json
    frame_start (int|None) default: the scene's
    frame_end   (int|None) default: the scene's
    device      (str|None) Cycles compute type: OPTIX | CUDA | HIP | ONEAPI | METAL, or CPU. Default: leave as is.
                Set in this process only; preferences are not saved.
    overwrite   (bool) replace this range's existing frames. Default false: they are an error, so runs do not mix.
                Any other file in the frames folder is always an error, because encoding that folder would mix runs.

The status file is replaced atomically: `state` is running, done or error, plus `frames_done`, `frames_total`,
`last_frame`, `elapsed_s`, `eta_s`, `started`, `ended`, `device`, `samples` and `error`. `done` means this run rendered
every expected frame and they are on disk; it does not mean a video exists. Encode the frames as a separate step. Read this file rather than the log:
the Microsoft Store launcher drops all console output.
"""
import json
import os
import sys
import time

import bpy

GPU_TYPES = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")


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


def _write_status(path, status):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
    os.replace(tmp, path)


def _set_device(scene, device):
    """Set the Cycles device for this process only. The caller never saves preferences."""
    if device not in GPU_TYPES + ("CPU",):
        raise ValueError(f"device must be one of {GPU_TYPES + ('CPU',)}, got {device!r}")
    if scene.render.engine != "CYCLES":
        raise ValueError(f"device needs the Cycles engine; this scene uses {scene.render.engine}")
    if device == "CPU":
        scene.cycles.device = "CPU"
        return ["CPU"]
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = device
    prefs.refresh_devices()
    used = []
    for d in prefs.devices:
        d.use = d.type == device
        if d.use:
            used.append(d.name)
    if not used:
        raise ValueError(f"no {device} device found on this machine")
    scene.cycles.device = "GPU"
    return used


def main(out_dir, frame_start=None, frame_end=None, device=None, overwrite=False):
    if not bpy.app.background:
        raise RuntimeError("background_render.py must run with `blender -b`, not in the open window: it blocks Blender "
                           "until the render ends and changes device settings")
    if not out_dir:
        raise ValueError("out_dir is required")
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    path = os.path.join(out_dir, "render_status.json")
    scene = bpy.context.scene
    status = {"state": "running", "started": time.time(), "ended": None, "blend": bpy.data.filepath, "device": None,
              "samples": scene.cycles.samples if scene.render.engine == "CYCLES" else None, "frames_done": 0,
              "frames_total": 0, "last_frame": None, "elapsed_s": 0.0, "eta_s": None, "error": None}
    _write_status(path, status)

    def on_frame(sc, *_):
        status["frames_done"] += 1
        status["last_frame"] = sc.frame_current
        status["elapsed_s"] = round(time.time() - status["started"], 1)
        left = status["frames_total"] - status["frames_done"]
        status["eta_s"] = round(status["elapsed_s"] / status["frames_done"] * left, 1)
        _write_status(path, status)

    try:
        if scene.render.image_settings.media_type == "VIDEO":
            raise ValueError("set an image format for the frames; encode the video afterwards")
        if frame_start is not None:
            scene.frame_start = frame_start
        if frame_end is not None:
            scene.frame_end = frame_end
        if device:
            status["device"] = _set_device(scene, device)
        scene.render.filepath = frames_dir.replace("\\", "/") + "/f_"
        scene.render.use_overwrite = True
        frames = range(scene.frame_start, scene.frame_end + 1, scene.frame_step)
        expected = [scene.render.frame_path(frame=f) for f in frames]
        status["frames_total"] = len(expected)
        names = {os.path.basename(p) for p in expected}
        others = sorted(set(os.listdir(frames_dir)) - names)
        if others:
            raise ValueError(f"{len(others)} file(s) outside this frame range in {frames_dir}, first: {others[0]}; "
                             "use a new out_dir")
        existing = [p for p in expected if os.path.exists(p)]
        if existing and not overwrite:
            raise ValueError(f"{len(existing)} frame(s) already exist in {frames_dir}; "
                             "pass overwrite=true or use a new out_dir")
        _write_status(path, status)
        bpy.app.handlers.render_post.append(on_frame)
        try:
            outcome = bpy.ops.render.render(animation=True)
        finally:
            bpy.app.handlers.render_post.remove(on_frame)
        if "FINISHED" not in outcome or status["frames_done"] != len(expected):
            raise RuntimeError(f"render ended as {sorted(outcome)} after {status['frames_done']} of {len(expected)} frames")
        absent = [p for p in expected if not os.path.exists(p)]
        if absent:
            raise RuntimeError(f"{len(absent)} of {len(expected)} frames missing after the render, first: {absent[0]}")
    except Exception as exc:
        status.update(state="error", error=str(exc), ended=time.time())
        _write_status(path, status)
        raise
    status.update(state="done", ended=time.time(), elapsed_s=round(time.time() - status["started"], 1), eta_s=0.0)
    _write_status(path, status)
    return status


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if __name__ == "__main__":
    print(json.dumps(result, indent=2))
