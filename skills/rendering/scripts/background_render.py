"""Render the open file's animation in a background Blender and keep a status file, so a long render never blocks the
user's window. It refuses to run inside the window. Save the .blend first, because this process reads the file on disk.

    blender -b file.blend --python-exit-code 1 --python <skill_dir>/scripts/background_render.py -- --args-file args.json

ARGS:
    out_dir     (str, required) frames go in <out_dir>/frames, status in <out_dir>/render_status.json
    frame_start (int|None) default: the scene's
    frame_end   (int|None) default: the scene's
    device      (str|None) Cycles compute type: OPTIX | CUDA | HIP | ONEAPI | METAL, or CPU. Default: leave as is.
                Set in this process only; preferences are not saved.
    overwrite   (bool) replace this range's existing frames and the status of a run that died. Default false: both are
                errors, so runs do not mix. It never gets past a process that is still rendering to this out_dir.
                Any other file in the frames folder is always an error, because encoding that folder would mix runs.
    plan        (bool) make every check and render one frame without saving it, then stop, so the user can be told how
                long the job will take before it starts. Default false. See "Before a long render" below.

The status file is replaced atomically: `state` is running, done or error, plus `frames_done`, `frames_total`,
`last_frame`, `elapsed_s`, `eta_s`, `started`, `ended`, `device`, `samples` and `error`. `done` means the run named by `started` rendered
every expected frame and they are on disk; it does not mean a video exists. Encode the frames as a separate step. Read this file rather than the log:
the Microsoft Store launcher drops all console output.

A refused launch exits 1 and leaves an existing status file as it was, because that file belongs to the earlier run. The
reason goes to `<out_dir>/render_refused.json` (`time`, `error`). So check the exit code as well as the status: a refusal
applies when its `time` is later than the status's `started`, and an old `done` then says nothing about this launch.
Exit 1 with no new refusal file means the arguments themselves were wrong, such as a misspelled name.

Before a long render, run this once with plan=true, in the foreground, with the same arguments. It writes
`<out_dir>/render_plan.json`: `time`, `frames_total`, `seconds_per_frame`, `expected_s`, `first_frame_s`, `measured_frames`,
`status_path`, `device`, `samples` and `tell_user`, one line to send the user before starting the job, and `next_step`. It leaves
no status and no frames, so the real run can use the same out_dir, and a refusal goes to `render_refused.json`.
The estimate is rough: frames of very different cost make it wrong, and it leaves out the 2 s or so a new Blender process
takes to start and load the file. The first frame of a process is slower than the rest (shader compilation, device
start-up), so when it took under 10 s and the range has a second frame, the plan renders that one too and estimates the job as the
first frame plus the second for each remaining frame (`measured_frames` is 2; `first_frame_s` keeps the first). Measured on
this machine (Windows, Blender 5.2.3, 320x180 to 480x270, 4 and 12 frames, 3 repeats): with n times the first frame, real
time over the estimate was 0.88 to 1.03 for Cycles on the CPU (16 and 64 samples) but 0.24 to 0.40 for Eevee, whose first
frame took 1.0 s and the rest 0.1 to 0.4 s; using only the second frame gave 1.7 to 3.3 for Eevee. With the first frame
added once, as now, the ratio was 1.00 to 1.17 in all 15 runs: the estimate still runs a little short, by the process start. On macOS (M2 Max, Cycles on METAL, 480x270, 12 frames)
it was 1.03 to 1.13 once warm, but 0.87 and 0.99 on the first plan of a new scene, whose first frame paid a one-off
compile the real run did not: the estimate then runs long. Check `time` before trusting an older plan file.
The real run prints nothing useful for this: its output usually goes to a log, and the Microsoft Store launcher drops it.

One process owns an out_dir at a time, through an OS lock on `<out_dir>/render.lock`. The operating system drops the lock
when the process ends, even in a crash, so the file stays behind and needs no cleanup.
"""
import errno
import json
import os
import sys
import time

import bpy

if os.name == "nt":
    import msvcrt
else:
    import fcntl

GPU_TYPES = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
LOCK_BUSY = (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK)
WARM_UP_LIMIT_S = 10  # a first frame slower than this is long enough that start-up cost no longer skews the estimate


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
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
    os.replace(tmp, path)


def _write_refusal(out_dir, exc):
    """Record why a launch was refused. Failing to record it must not replace that reason."""
    try:
        _write_status(os.path.join(out_dir, "render_refused.json"), {"time": time.time(), "error": str(exc)})
    except OSError:
        pass


def _take_lock(out_dir):
    """Own out_dir until _release_lock, or raise ValueError if another process owns it."""
    fd = os.open(os.path.join(out_dir, "render.lock"), os.O_CREAT | os.O_RDWR)
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in LOCK_BUSY:
            raise ValueError(f"another process is rendering to {out_dir}; wait for it to end or use a new out_dir") from exc
        raise
    return fd


def _release_lock(fd):
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _running_elsewhere(path):
    """True if the status file says a render is running. A file we cannot read is an error, not a free folder."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["state"] == "running"
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}; pass overwrite=true to replace it, or use a new out_dir") from exc


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
    available = [t[0] for t in prefs.get_device_types(bpy.context) if t[0] != "NONE"]
    if device not in available:
        raise ValueError(f"{device} is not available on this machine; available: {available + ['CPU']}")
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


def _duration(seconds):
    return f"{max(1, round(seconds))} s" if seconds < 90 else f"{seconds / 60:.0f} min"


def _timed_render(frame):
    """Render one frame without saving it and return how long it took."""
    bpy.context.scene.frame_set(frame)
    begun = time.time()
    if "FINISHED" not in bpy.ops.render.render(write_still=False):
        raise RuntimeError(f"the test render of frame {frame} did not finish")
    return time.time() - begun


def _plan(out_dir, status, frames, path):
    """Measure the render, and write what the user should hear before the job starts. The first frame of a process also
    pays for shader compilation and device start-up (about 1 s in Eevee), so
    n times the first frame overstates a short job 2.5 to 4 times. When that frame was fast and a second one exists, the
    estimate is the first frame plus the second frame for each remaining frame."""
    first = _timed_render(frames[0])
    each, measured = first, 1
    if len(frames) > 1 and first < WARM_UP_LIMIT_S:
        each, measured = _timed_render(frames[1]), 2
    plan = {"time": time.time(), "frames_total": len(frames), "seconds_per_frame": round(each, 2), "expected_s": round(first + each * (len(frames) - 1), 1),
            "first_frame_s": round(first, 2), "measured_frames": measured,
            "status_path": path.replace("\\", "/"), "device": status["device"], "samples": status["samples"]}
    plan["tell_user"] = (f"Rendering {len(frames)} frames in a separate Blender process, about "
                         f"{_duration(plan['expected_s'])}. Your Blender window stays free. Progress: {plan['status_path']}")
    plan["next_step"] = "Send tell_user to the user as a message now, then start the job without plan. No tool call shows it to them."
    _write_status(os.path.join(out_dir, "render_plan.json"), plan)
    return plan


def main(out_dir, frame_start=None, frame_end=None, device=None, overwrite=False, plan=False):
    if not bpy.app.background:
        raise RuntimeError("background_render.py must run with `blender -b`, not in the open window: it blocks Blender "
                           "until the render ends and changes device settings")
    if not out_dir:
        raise ValueError("out_dir is required")
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    # A process that loses here must leave the status alone: the owner may not have published it yet.
    try:
        lock = _take_lock(out_dir)
    except ValueError as exc:
        _write_refusal(out_dir, exc)
        raise
    try:
        return _render(out_dir, frames_dir, frame_start, frame_end, device, overwrite, plan)
    finally:
        _release_lock(lock)


def _render(out_dir, frames_dir, frame_start, frame_end, device, overwrite, plan=False):
    """Everything that reads or writes the folder; the caller holds its lock."""
    path = os.path.join(out_dir, "render_status.json")
    scene = bpy.context.scene
    status = {"state": "running", "started": time.time(), "ended": None, "blend": bpy.data.filepath, "device": None,
              "samples": scene.cycles.samples if scene.render.engine == "CYCLES" else None, "frames_done": 0,
              "frames_total": 0, "last_frame": None, "elapsed_s": 0.0, "eta_s": None, "error": None}

    def on_frame(sc, *_):
        status["frames_done"] += 1
        status["last_frame"] = sc.frame_current
        status["elapsed_s"] = round(time.time() - status["started"], 1)
        left = status["frames_total"] - status["frames_done"]
        status["eta_s"] = round(status["elapsed_s"] / status["frames_done"] * left, 1)
        _write_status(path, status)

    # A refused run must not touch the status of the run that already owns this folder.
    try:
        if os.path.exists(path) and not overwrite:
            if _running_elsewhere(path):
                raise ValueError(f"{path} says a render is running, but no process owns this folder, so that run died; "
                                 "pass overwrite=true to replace it, or use a new out_dir")
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
        if plan:
            return _plan(out_dir, status, list(frames), path)
    except Exception as exc:
        if plan or os.path.exists(path):
            _write_refusal(out_dir, exc)
        else:
            status.update(state="error", error=str(exc), ended=time.time())
            _write_status(path, status)
        raise
    try:
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
