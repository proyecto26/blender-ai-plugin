"""Render the files an AI video/image tool needs from Blender shots, plus a manifest, then stop.

Blender renders what needs precision (subject, camera, composition, lighting); Seam or ComfyUI paints the
background and adds motion. This script never uploads or submits anything.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/render_handoff.py", init_globals={"ARGS": {
        "out_dir": "<project>/handoff", "target": "both", "subject": ["Hero"]}})["result"]

Outputs under out_dir:
    seam/<shot>.mp4 | seam/<shot>.png   moving shot -> H.264 clip, still shot -> opaque RGB PNG (middle frame)
    seam/seam_sequence.json             {"shots": [abs paths], "segments": [...], "size", "fps", "notes"}
    comfy/assets/<shot>/beauty.png      opaque RGB render
    comfy/assets/<shot>/mask.png        8-bit grey, white (1) = subject coverage, black (0) = everything else
    comfy/assets/<shot>/depth.png       16-bit grey from the mist pass, Non-Color, normalized (not metric):
                                        0 at/before `start`, 1 at start+depth and beyond (near = dark) unless
                                        depth_near_white is true
    comfy/handoff.json                  camera data, mist {start, depth, falloff, polarity}, size, fps, shots

ARGS:
    out_dir          (str)  required, created if missing; files with the same names are overwritten
    target           (str)  "seam" | "comfy" | "both" (default "both")
    shots            (list|None) explicit shots in the scene-contract shape
                     {id, start, end, camera, motion: "still"|"moving", description?, beat?}; default:
                     scene["film_shots"]; if neither exists, one still shot from the active camera at the
                     current frame
    size             ([w, h]|None) snapped to multiples of 32 within 256-2048 (default: the scene's
                     resolution x percentage, snapped). Every shot renders at this one size.
    fps              (float|None) default: film_shots fps, else 24
    clip_seconds_max (float) longest clip, capped at 6 (Seam limit); a longer moving shot is CLAMPED to
                     floor(max*fps) frames from its start with a warning (default 6)
    subject          (list[str]) object names (their children are included) for the mask; required when
                     passes contains "mask" and target includes comfy
    passes           (list[str]) subset of beauty, mask, depth for comfy (default all three)
    segments         (list|None) Seam segments passed through as-is; must hold len(shots)-1 dicts
    engine           (str) BLENDER_EEVEE (default) | CYCLES | BLENDER_WORKBENCH (no depth)
    samples          (int|None) render samples for the engine; None keeps the scene value
    comfy_frame      (str) "middle" (default) | "start" | "end": frame rendered for comfy passes
    mist_range       ([start, depth]|None) fixed mist range; default fits the visible geometry per shot
    depth_near_white (bool) invert the depth so near = white (ControlNet convention); default false

A moving shot shorter than 1 s at fps raises ValueError (Seam rejects it): mark it "still" or lengthen it.
Every scene setting touched (engine, samples, resolution, fps, frame range/current, camera, film, file
format, view transform, compositor, mist pass/settings, hide_render, window scene) is restored in `finally`.
"""
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector

TARGETS = ("seam", "comfy", "both")
PASSES = ("beauty", "mask", "depth")
ENGINES = ("BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH")
RENDERABLE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}
SEAM_MAX_SECONDS = 6.0
SEAM_MIN_SECONDS = 1.0
DESC_LIMIT = 400


def _cli_args():
    if "--" not in sys.argv:
        return {}
    raw = sys.argv[sys.argv.index("--") + 1:]
    if not raw:
        return {}
    try:
        if raw[0] == "--args-file":
            if len(raw) < 2:
                raise ValueError("--args-file needs a path to a JSON file")
            with open(raw[1], encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(raw[0])
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read ARGS (pass a JSON object or --args-file <path.json>): {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("ARGS must be a JSON object")
    return data


# ---------------------------------------------------------------- helpers
def snap32(value):
    return int(min(2048, max(256, round(float(value) / 32.0) * 32)))


def _safe_id(text):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(text)) or "shot"


def _rel(path, root):
    return Path(path).relative_to(root).as_posix()


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _matrix(m):
    return [[round(float(m[r][c]), 6) for c in range(4)] for r in range(4)]


def _camera_data(cam):
    d = cam.data
    return {"object": cam.name, "type": d.type, "lens_mm": round(d.lens, 4), "sensor_width_mm": d.sensor_width,
            "sensor_height_mm": d.sensor_height, "sensor_fit": d.sensor_fit, "ortho_scale": d.ortho_scale,
            "shift_x": d.shift_x, "shift_y": d.shift_y, "clip_start": d.clip_start, "clip_end": d.clip_end,
            "matrix_world": _matrix(cam.matrix_world)}


def _resolve_shots(scene, shots_arg, default_fps):
    fps = default_fps
    if shots_arg is None:
        raw = scene.get("film_shots")
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw.to_dict()
            except (ValueError, AttributeError) as exc:
                raise ValueError(f'scene["film_shots"] is not valid JSON: {exc}') from exc
            shots_arg = data.get("shots") or []
            fps = fps or data.get("fps")
    if not shots_arg:
        if scene.camera is None:
            raise ValueError("no shots given, no scene['film_shots'] and no active camera")
        frame = scene.frame_current
        shots_arg = [{"id": "SHOT_01", "start": frame, "end": frame, "camera": scene.camera.name, "motion": "still",
                      "description": ""}]
    shots, seen, last_end = [], set(), None
    for raw in sorted(shots_arg, key=lambda s: int(s["start"])):
        try:
            start, end = int(raw["start"]), int(raw["end"])
            sid = str(raw["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"shot needs id, start, end: {raw!r}") from exc
        if end < start:
            raise ValueError(f"shot {sid}: end {end} < start {start}")
        if last_end is not None and start <= last_end:
            raise ValueError(f"shot {sid} overlaps the previous shot (start {start} <= {last_end})")
        last_end = end
        folder = _safe_id(sid)
        if folder in seen:
            raise ValueError(f"duplicate shot id {sid!r}")
        seen.add(folder)
        cam_name = raw.get("camera")
        cam = bpy.data.objects.get(cam_name) if cam_name else scene.camera
        if cam is None or cam.type != "CAMERA":
            raise ValueError(f"shot {sid}: camera {cam_name!r} not found or not a camera")
        motion = raw.get("motion", "still")
        if motion not in ("still", "moving"):
            raise ValueError(f"shot {sid}: motion must be 'still' or 'moving'")
        shots.append({"id": sid, "folder": folder, "start": start, "end": end, "camera": cam, "motion": motion,
                      "beat": raw.get("beat", ""), "description": raw.get("description", "") or ""})
    return shots, fps


def _plan_clip_frames(shot, fps, max_seconds, warnings):
    """Frames to render for a moving shot; raises when shorter than Seam's minimum, clamps when longer."""
    frames = shot["end"] - shot["start"] + 1
    if frames / fps < SEAM_MIN_SECONDS - 1e-9:
        raise ValueError(f"shot {shot['id']}: {frames} frames at {fps:g} fps is {frames / fps:.2f} s, Seam needs "
                         f"1-6 s clips; set motion to 'still' or lengthen the shot")
    limit = int(math.floor(min(max_seconds, SEAM_MAX_SECONDS) * fps + 1e-9))
    if frames > limit:
        warnings.append(f"shot {shot['id']}: {frames / fps:.2f} s clamped to its first {limit} frames "
                        f"({limit / fps:.2f} s) for Seam")
        frames = limit
    return frames


# ---------------------------------------------------------------- state snapshot
class _State:
    """Captures every scene setting this script touches and puts it back."""

    def __init__(self, scene, window):
        r, im, ff, vs = scene.render, scene.render.image_settings, scene.render.ffmpeg, scene.view_settings
        self.scene, self.window = scene, window
        self.window_scene = window.scene if window else None
        self.render = {k: getattr(r, k) for k in (
            "engine", "resolution_x", "resolution_y", "resolution_percentage", "fps", "fps_base", "film_transparent",
            "filepath", "use_compositing", "dither_intensity")}
        self.image = {k: getattr(im, k) for k in ("media_type", "file_format", "color_mode", "color_depth")}
        self.ffmpeg = {k: getattr(ff, k) for k in ("format", "codec", "constant_rate_factor", "audio_codec")}
        self.view = {k: getattr(vs, k) for k in ("view_transform", "look", "exposure", "gamma", "use_curve_mapping")}
        self.frames = {k: getattr(scene, k) for k in ("frame_current", "frame_start", "frame_end", "frame_step")}
        self.camera = scene.camera
        self.eevee_samples = scene.eevee.taa_render_samples
        self.cycles_samples = scene.cycles.samples if hasattr(scene, "cycles") and scene.cycles else None
        self.comp_group = scene.compositing_node_group
        self.world = scene.world
        self.mist = ({k: getattr(scene.world.mist_settings, k) for k in ("start", "depth", "falloff")}
                     if scene.world else None)
        self.pass_mist = [(vl, vl.use_pass_mist) for vl in scene.view_layers]
        self.hide = [(o, o.hide_render) for o in scene.objects]
        self.temp_groups, self.temp_world = [], None
        self.errors = []

    def restore_view(self):
        vs = self.scene.view_settings
        vs.view_transform = self.view["view_transform"]
        for key, value in self.view.items():
            if key != "view_transform":
                setattr(vs, key, value)
        self.scene.render.dither_intensity = self.render["dither_intensity"]

    def restore_hide(self):
        for obj, value in self.hide:
            obj.hide_render = value

    def _set(self, target, values):
        for key, value in values.items():
            try:
                setattr(target, key, value)
            except (TypeError, ValueError, RuntimeError, AttributeError) as exc:
                self.errors.append(f"{key}: {exc}")

    def restore(self):
        scene = self.scene
        self.restore_hide()
        for vl, value in self.pass_mist:
            vl.use_pass_mist = value
        scene.compositing_node_group = self.comp_group
        for group in self.temp_groups:
            if group.name in bpy.data.node_groups:
                bpy.data.node_groups.remove(group)
        scene.world = self.world
        if self.world is not None and self.mist:
            self._set(self.world.mist_settings, self.mist)
        if self.temp_world is not None and self.temp_world.name in bpy.data.worlds:
            bpy.data.worlds.remove(self.temp_world)
        # order matters: engine, then media type before file format, view transform before look
        self._set(scene.render, {"engine": self.render["engine"]})
        scene.eevee.taa_render_samples = self.eevee_samples
        if self.cycles_samples is not None:
            scene.cycles.samples = self.cycles_samples
        self._set(scene.render, {k: v for k, v in self.render.items() if k != "engine"})
        self._set(scene.render.image_settings, {k: self.image[k] for k in ("media_type", "file_format")})
        self._set(scene.render.image_settings, {k: self.image[k] for k in ("color_mode", "color_depth")})
        self._set(scene.render.ffmpeg, self.ffmpeg)
        self._set(scene.view_settings, {"view_transform": self.view["view_transform"]})
        self._set(scene.view_settings, {k: v for k, v in self.view.items() if k != "view_transform"})
        self._set(scene, {k: self.frames[k] for k in ("frame_start", "frame_end", "frame_step")})
        scene.frame_set(self.frames["frame_current"])
        scene.camera = self.camera
        if self.window is not None and self.window_scene is not None:
            self.window.scene = self.window_scene


# ---------------------------------------------------------------- rendering
def _render(scene, animation=False):
    bpy.ops.render.render(animation=animation, write_still=not animation, scene=scene.name)


def _render_png(scene, path, color_mode, depth):
    im = scene.render.image_settings
    im.media_type = "IMAGE"
    im.file_format = "PNG"
    im.color_mode = color_mode
    im.color_depth = depth
    scene.render.filepath = str(path)
    _render(scene)
    if not Path(path).exists():
        raise RuntimeError(f"render did not write {path}")


def _linear_view(scene):
    vs = scene.view_settings
    vs.view_transform = "Raw"
    vs.look = "None"
    vs.exposure = 0.0
    vs.gamma = 1.0
    vs.use_curve_mapping = False
    scene.render.dither_intensity = 0.0


def _comp_group(scene, state, kind, invert=False):
    """Temporary compositor group: Render Layers (Alpha | Mist) -> output (optionally 1 - x)."""
    tree = bpy.data.node_groups.new("HANDOFF_TMP", "CompositorNodeTree")
    state.temp_groups.append(tree)
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = tree.nodes.new("CompositorNodeRLayers")
    layer = next((vl for vl in scene.view_layers if vl.use), scene.view_layers[0])
    if hasattr(rl, "scene"):
        rl.scene = scene
    rl.layer = layer.name
    out = tree.nodes.new("NodeGroupOutput")
    source = rl.outputs["Alpha" if kind == "alpha" else "Mist"]
    if invert:
        math_node = tree.nodes.new("ShaderNodeMath")
        math_node.operation = "SUBTRACT"
        math_node.inputs[0].default_value = 1.0
        tree.links.new(source, math_node.inputs[1])
        source = math_node.outputs[0]
    tree.links.new(source, out.inputs[0])
    scene.compositing_node_group = tree
    scene.render.use_compositing = True


def _fit_mist(scene, cam, depsgraph):
    inv = cam.matrix_world.inverted()
    zs = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        ev = obj.evaluated_get(depsgraph)
        for corner in ev.bound_box:
            z = -(inv @ (ev.matrix_world @ Vector(corner))).z
            if z > 0:
                zs.append(z)
    if not zs:
        return cam.data.clip_start, max(cam.data.clip_end - cam.data.clip_start, 0.001)
    lo, hi = min(zs), max(zs)
    span = max(hi - lo, 1e-3)
    start = max(0.0, lo - 0.02 * span)
    return start, max(hi - start + 0.02 * span, 1e-3)


def _subject_set(names):
    missing = [n for n in names if n not in bpy.data.objects]
    if missing:
        raise ValueError(f"subject objects not found: {missing}")
    found = set()
    for name in names:
        obj = bpy.data.objects[name]
        found.add(obj)
        found.update(obj.children_recursive)
    return found


def _hide_all_but(scene, subject):
    for obj in scene.objects:
        if obj in subject:
            if obj.type in RENDERABLE:
                obj.hide_render = False
        elif obj.type in RENDERABLE or (obj.type == "EMPTY" and obj.instance_type == "COLLECTION"):
            obj.hide_render = True


def _set_frame(scene, cam, frame):
    scene.frame_set(frame)
    scene.camera = cam


def _clip(scene, shot, frames, path, fps):
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.image_settings.color_mode = "RGB"
    ff = scene.render.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "MEDIUM"
    ff.audio_codec = "NONE"
    scene.render.film_transparent = False
    scene.frame_start, scene.frame_end, scene.frame_step = shot["start"], shot["start"] + frames - 1, 1
    scene.frame_set(shot["start"])
    scene.camera = shot["camera"]
    scene.render.filepath = str(path)
    _render(scene, animation=True)
    if not Path(path).exists() or Path(path).stat().st_size == 0:
        raise RuntimeError(f"clip was not written: {path}")


def _still_frame(shot, which):
    return {"start": shot["start"], "end": shot["end"]}.get(which, (shot["start"] + shot["end"]) // 2)


def main(out_dir=None, target="both", shots=None, size=None, fps=None, clip_seconds_max=6, subject=None,
         passes=None, segments=None, engine="BLENDER_EEVEE", samples=None, comfy_frame="middle", mist_range=None,
         depth_near_white=False):
    if not out_dir:
        raise ValueError("out_dir is required")
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    passes = list(passes) if passes else list(PASSES)
    if any(p not in PASSES for p in passes):
        raise ValueError(f"passes must be a subset of {PASSES}")
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}")
    if comfy_frame not in ("middle", "start", "end"):
        raise ValueError("comfy_frame must be middle, start or end")
    do_seam, do_comfy = target in ("seam", "both"), target in ("comfy", "both")
    if do_comfy and "depth" in passes and engine == "BLENDER_WORKBENCH":
        raise ValueError("BLENDER_WORKBENCH has no mist pass; use BLENDER_EEVEE or CYCLES for depth")
    if do_comfy and "mask" in passes and not subject:
        raise ValueError('"mask" needs subject=[object names]; or drop "mask" from passes')
    scene = bpy.context.scene
    shot_list, film_fps = _resolve_shots(scene, shots, fps)
    fps = float(fps or film_fps or 24)
    warnings, notes = [], []
    subject_objs = _subject_set(subject) if (do_comfy and "mask" in passes) else set()
    if segments is not None and len(segments) != len(shot_list) - 1:
        raise ValueError(f"segments must hold len(shots)-1 = {len(shot_list) - 1} entries, got {len(segments)}")
    if size:
        w, h = snap32(size[0]), snap32(size[1])
        if [w, h] != [int(size[0]), int(size[1])]:
            warnings.append(f"size {list(size)} snapped to {[w, h]} (multiples of 32, 256-2048)")
    else:
        r = scene.render
        w = snap32(r.resolution_x * r.resolution_percentage / 100)
        h = snap32(r.resolution_y * r.resolution_percentage / 100)
    clip_frames = {}
    if do_seam:
        for shot in shot_list:
            if shot["motion"] == "moving":
                clip_frames[shot["id"]] = _plan_clip_frames(shot, fps, float(clip_seconds_max), warnings)
    out_root = Path(out_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    window = bpy.context.window
    state = _State(scene, window)
    seam_paths, seam_files, comfy_entries, files = [], [], [], []
    mist_note = None
    try:
        if window is not None and window.scene != scene:
            window.scene = scene
        scene.render.engine = engine
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = w, h, 100
        scene.render.fps = int(round(fps))
        scene.render.fps_base = round(fps) / fps
        if samples:
            if engine == "BLENDER_EEVEE":
                scene.eevee.taa_render_samples = int(samples)
            elif engine == "CYCLES":
                scene.cycles.samples = int(samples)
        if do_comfy and "depth" in passes and scene.world is None:
            state.temp_world = bpy.data.worlds.new("HANDOFF_TMP_WORLD")
            scene.world = state.temp_world

        for shot in shot_list:
            cam, sid = shot["camera"], shot["folder"]
            if do_seam:
                (out_root / "seam").mkdir(parents=True, exist_ok=True)
                if shot["id"] in clip_frames:
                    path = out_root / "seam" / f"{sid}.mp4"
                    _clip(scene, shot, clip_frames[shot["id"]], path, fps)
                else:
                    path = out_root / "seam" / f"{sid}.png"
                    _set_frame(scene, cam, (shot["start"] + shot["end"]) // 2)
                    scene.render.film_transparent = False
                    _render_png(scene, path, "RGB", "8")
                seam_paths.append(path)
                files.append(path)
            if do_comfy:
                folder = out_root / "comfy" / "assets" / sid
                folder.mkdir(parents=True, exist_ok=True)
                frame = _still_frame(shot, comfy_frame)
                _set_frame(scene, cam, frame)
                entry = {"id": shot["id"], "frame": frame, "motion": shot["motion"], "beat": shot["beat"],
                         "description": shot["description"], "camera": _camera_data(cam), "files": {}}
                if "beauty" in passes:
                    scene.render.film_transparent = False
                    _render_png(scene, folder / "beauty.png", "RGB", "8")
                    entry["files"]["beauty"] = f"{sid}/beauty.png"
                if "mask" in passes:
                    scene.render.film_transparent = True
                    _hide_all_but(scene, subject_objs)
                    _linear_view(scene)
                    _comp_group(scene, state, "alpha")
                    try:
                        _render_png(scene, folder / "mask.png", "BW", "8")
                    finally:
                        state.restore_hide()
                        state.restore_view()
                        scene.compositing_node_group = state.comp_group
                        scene.render.use_compositing = state.render["use_compositing"]
                        scene.render.film_transparent = False
                    entry["files"]["mask"] = f"{sid}/mask.png"
                if "depth" in passes:
                    world = scene.world
                    if mist_range:
                        start, depth = float(mist_range[0]), float(mist_range[1])
                    else:
                        start, depth = _fit_mist(scene, cam, bpy.context.evaluated_depsgraph_get())
                    world.mist_settings.start, world.mist_settings.depth = start, depth
                    world.mist_settings.falloff = "LINEAR"
                    for vl in scene.view_layers:
                        vl.use_pass_mist = True
                    _linear_view(scene)
                    _comp_group(scene, state, "mist", invert=bool(depth_near_white))
                    try:
                        _render_png(scene, folder / "depth.png", "BW", "16")
                    finally:
                        for vl, value in state.pass_mist:
                            vl.use_pass_mist = value
                        state.restore_view()
                        scene.compositing_node_group = state.comp_group
                        scene.render.use_compositing = state.render["use_compositing"]
                    entry["files"]["depth"] = f"{sid}/depth.png"
                    entry["mist"] = {"start": round(start, 5), "depth": round(depth, 5), "falloff": "LINEAR",
                                     "polarity": "near_is_white" if depth_near_white else "near_is_black",
                                     "normalized": True}
                    mist_note = entry["mist"]["polarity"]
                comfy_entries.append(entry)
                written = [folder / f"{k}.png" for k in entry["files"]]
                files += written
                left = [n for n in ("beauty.png", "mask.png", "depth.png")
                        if (folder / n).exists() and folder / n not in written]
                if left:
                    warnings.append(f"{sid}: left from an earlier run, not rendered now: {', '.join(left)}")
    finally:
        state.restore()
    if state.errors:
        warnings.append("could not restore: " + "; ".join(state.errors))

    manifests = {}
    seam_note_size = (f"size {w}x{h} is what Blender rendered; Seam renders every take at the first shot's aspect "
                      f"ratio and picks the pixel size itself, so its output is not promised to be {w}x{h}")
    if do_seam:
        n = len(seam_paths)
        if not 2 <= n <= 8:
            warnings.append(f"Seam takes 2-8 shots; this sequence has {n}")
        seg = segments
        if seg is None:
            seg = [{"preset": None, "seconds": None,
                    "a_desc": shot_list[i]["description"][:DESC_LIMIT],
                    "b_desc": shot_list[i + 1]["description"][:DESC_LIMIT]} for i in range(len(shot_list) - 1)]
        seam_notes = [
            "preset and seconds are null placeholders: choose them from Seam's list_presets (each preset is "
            "qualified only at its listed lengths) before calling create_sequence",
            seam_note_size,
            "Seam takes a clip's first frame (the transition lands on it) and last frame (the next transition "
            "leaves from it); a still PNG serves as both ends",
            "stills are opaque RGB; Seam ignores depth, alpha and camera data"]
        seam_doc = {"shots": [p.as_posix() for p in seam_paths], "segments": seg, "size": [w, h], "fps": fps,
                    "notes": seam_notes}
        _write_json(out_root / "seam" / "seam_sequence.json", seam_doc)
        manifests["seam"] = str(out_root / "seam" / "seam_sequence.json")
        files.append(out_root / "seam" / "seam_sequence.json")
    if do_comfy:
        doc = {"version": 1, "size": [w, h], "fps": fps, "passes": passes, "subject": list(subject or []),
               "asset_root": "assets", "shots": comfy_entries,
               "notes": ["mask.png: white = subject coverage (subject objects and children only, occluders ignored)",
                         "depth.png: 16-bit Non-Color, normalized from the mist pass, not metric; polarity in each "
                         "shot's mist block",
                         "copy assets/ into the ComfyUI project assets/ folder and reference $asset.<shot>/beauty.png"]}
        _write_json(out_root / "comfy" / "handoff.json", doc)
        manifests["comfy"] = str(out_root / "comfy" / "handoff.json")
        files.append(out_root / "comfy" / "handoff.json")
    return {"out_dir": str(out_root), "target": target, "size": [w, h], "fps": fps, "shots": [s["id"] for s in shot_list],
            "files": [str(p) for p in files], "manifests": manifests, "depth_polarity": mist_note,
            "warnings": warnings, "restored": not state.errors}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
