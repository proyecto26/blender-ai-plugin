"""Render review stills of a target from standard angles (front, 3/4, side,
back, top, plus the active camera) to a folder, without changing the scene.

A temporary camera is created, used and removed; render settings are restored. Timeline markers bound to
cameras (shot lists) would switch the camera at render time, so their bindings are lifted while capturing and
put back afterwards. Everything the script changes (render engine, resolution, file format, camera, marker
bindings, hide flags, temporary wireframe modifiers) is put back in `finally`, also when a capture fails.
Use it for QA review or the reference-match comparison loop, then open the PNGs
(or call the MCP screenshot tools for the live viewport).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/capture_views.py",
                            init_globals={"ARGS": {"target": "SM_Crate_01", "out_dir": "/tmp/qa"}})["result"]

ARGS:
    out_dir     (str, required) folder for PNGs (created if missing)
    target      (str|None)      object to frame; default = all visible meshes
    views       (list[str])     subset of front, three_quarter, side, back, top, camera
    resolution  (int)           square resolution in px (default 768)
    engine      (str)           BLENDER_WORKBENCH (fast, default) | BLENDER_EEVEE | CYCLES
    isolate     (bool)          render only the asset: every other geometry object is hidden from the render for the
                                capture (lights and cameras stay). The asset is the target (or the framed meshes)
                                and its children. Default False.
    wire        (bool)          add a `wire` view (three-quarter angle, wireframe, Workbench engine) after the
                                other views. Default False.
    contact_sheet (bool)        also write `<name>_sheet.png`, one image tiling all captured views in a grid
                                (columns = ceil(sqrt(n)); size = columns*resolution x rows*resolution). Default False.

Returns images (one path per view), center, framed_size_m and, with contact_sheet, contact_sheet (path) and
contact_sheet_size ([width, height]). A render that does not produce its file raises RuntimeError.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ANGLES = {  # (azimuth deg, elevation deg)
    "front": (0, 8),
    "three_quarter": (35, 20),
    "side": (90, 8),
    "back": (180, 8),
    "top": (0, 89),
}
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"}


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


def _bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, max((hi - lo).length, 0.01)


WIRE_MOD = "__capture_wire"


def _drop_wire(pairs):
    """Remove the Wireframe modifiers this script added (and only those)."""
    while pairs:
        o, m = pairs.pop()
        if m.name in o.modifiers and o.modifiers[m.name] == m:
            o.modifiers.remove(m)


def _stamp(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _descendants(objs):
    out, stack = [], list(objs)
    while stack:
        o = stack.pop()
        if o not in out:
            out.append(o)
            stack.extend(o.children)
    return out


def _tile_sheet(paths, resolution, sheet_path):
    """Tile the PNGs (all resolution x resolution) into one grid image. Returns [width, height]."""
    n = len(paths)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    w, h = cols * resolution, rows * resolution
    sheet = np.zeros((h, w, 4), dtype=np.float32)
    sheet[..., 3] = 1.0
    loaded, out = [], None
    try:
        for i, p in enumerate(paths):
            img = bpy.data.images.load(p)
            loaded.append(img)
            if tuple(img.size) != (resolution, resolution):
                raise RuntimeError(f"{p} is {tuple(img.size)}, expected {resolution}x{resolution}")
            buf = np.empty(resolution * resolution * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            y0 = (rows - 1 - i // cols) * resolution  # pixel rows run bottom to top
            x0 = (i % cols) * resolution
            sheet[y0:y0 + resolution, x0:x0 + resolution] = buf.reshape(resolution, resolution, 4)
            sheet[y0:y0 + resolution, x0:x0 + resolution, 3] = 1.0  # the sheet is opaque (a transparent render saves wrongly)
        out = bpy.data.images.new("__capture_sheet", w, h)
        out.pixels.foreach_set(sheet.ravel())
        out.filepath_raw = sheet_path
        out.file_format = "PNG"
        out.save()
    finally:
        for img in loaded:
            bpy.data.images.remove(img)
        if out is not None:
            bpy.data.images.remove(out)
    if not os.path.isfile(sheet_path):
        raise RuntimeError(f"contact sheet was not written: {sheet_path}")
    return [w, h]


def main(out_dir, target=None, views=None, resolution=768, engine="BLENDER_WORKBENCH", isolate=False, wire=False,
         contact_sheet=False):
    scene = bpy.context.scene
    views = list(views or list(ANGLES) + (["camera"] if scene.camera else []))
    bad = [v for v in views if v not in ANGLES and v not in ("camera", "wire")]
    if bad:
        raise ValueError(f"unknown views {bad}; choose from {list(ANGLES) + ['camera', 'wire']}")
    if wire and "wire" not in views:
        views.append("wire")
    if target:
        if target not in bpy.data.objects:
            raise ValueError(f"object not found: {target}")
        objs = [bpy.data.objects[target]]
    else:
        objs = [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not objs:
        raise ValueError("nothing to frame")
    os.makedirs(out_dir, exist_ok=True)
    center, size = _bounds(objs)

    r = scene.render
    saved = dict(engine=r.engine, x=r.resolution_x, y=r.resolution_y, pct=r.resolution_percentage,
                 path=r.filepath, fmt=r.image_settings.file_format, depth=r.image_settings.color_depth,
                 camera=scene.camera)
    asset = _descendants(objs)
    hidden_before = {o: o.hide_render for o in scene.objects}
    wire_mods = []
    cam_data = bpy.data.cameras.new("__capture_cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("__capture_cam", cam_data)
    scene.collection.objects.link(cam)
    written = []
    sheet_info = None
    bound = [(m, m.camera) for m in scene.timeline_markers if m.camera]
    try:
        for m, _ in bound:
            m.camera = None
        r.engine = engine
        r.resolution_x = r.resolution_y = resolution
        r.resolution_percentage = 100
        r.image_settings.file_format = "PNG"
        if isolate:
            for o in scene.objects:
                if o not in asset and o.type in GEOMETRY_TYPES:
                    o.hide_render = True
        distance = size * 1.9
        for view in views:
            if view == "camera":
                if not saved["camera"]:
                    continue
                scene.camera = saved["camera"]
            else:
                az, el = (math.radians(a) for a in ANGLES["three_quarter" if view == "wire" else view])
                offset = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
                cam.location = center + offset * distance
                cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
                cam_data.clip_end = distance * 10
                scene.camera = cam
            path = os.path.join(out_dir, f"{(target or 'scene')}_{view}.png")
            r.filepath = path
            if view == "wire":
                r.engine = "BLENDER_WORKBENCH"
                for o in asset:  # Workbench ignores the WIRE display type in renders, so a Wireframe modifier shows the edges
                    if o.type == "MESH":
                        m = o.modifiers.new(WIRE_MOD, "WIREFRAME")
                        m.thickness = size * 0.006
                        m.use_replace = True
                        m.use_boundary = True
                        wire_mods.append((o, m))
            try:
                before = _stamp(path)  # an older file there must not pass for this render
                status = bpy.ops.render.render(write_still=True)
                if status != {"FINISHED"} or _stamp(path) in (None, before):
                    raise RuntimeError(f"render of view {view} did not produce {path} (operator returned {status})")
            finally:
                if view == "wire":
                    r.engine = engine
                    _drop_wire(wire_mods)
            written.append(path)
        if contact_sheet:
            sheet_path = os.path.join(out_dir, f"{(target or 'scene')}_sheet.png")
            sheet_info = (sheet_path, _tile_sheet(written, resolution, sheet_path))
    finally:
        for m, c in bound:
            m.camera = c
        for o, hr in hidden_before.items():
            o.hide_render = hr
        _drop_wire(wire_mods)
        r.engine, r.resolution_x, r.resolution_y = saved["engine"], saved["x"], saved["y"]
        r.resolution_percentage, r.filepath = saved["pct"], saved["path"]
        r.image_settings.file_format = saved["fmt"]
        r.image_settings.color_depth = saved["depth"]
        scene.camera = saved["camera"]
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data)
    result = {"images": written, "center": list(center), "framed_size_m": round(size, 3)}
    if sheet_info:
        result["contact_sheet"], result["contact_sheet_size"] = sheet_info
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
