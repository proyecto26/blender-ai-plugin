"""Render review stills of a target from standard angles (front, 3/4, side,
back, top, plus the active camera) to a folder, without changing the scene.

A temporary camera is created, used and removed; render settings are restored.
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
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ANGLES = {  # (azimuth deg, elevation deg)
    "front": (0, 8),
    "three_quarter": (35, 20),
    "side": (90, 8),
    "back": (180, 8),
    "top": (0, 89),
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, max((hi - lo).length, 0.01)


def main(out_dir, target=None, views=None, resolution=768, engine="BLENDER_WORKBENCH"):
    scene = bpy.context.scene
    views = views or list(ANGLES) + (["camera"] if scene.camera else [])
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
                 path=r.filepath, fmt=r.image_settings.file_format, camera=scene.camera)
    cam_data = bpy.data.cameras.new("__capture_cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("__capture_cam", cam_data)
    scene.collection.objects.link(cam)
    written = []
    try:
        r.engine = engine
        r.resolution_x = r.resolution_y = resolution
        r.resolution_percentage = 100
        r.image_settings.file_format = "PNG"
        distance = size * 1.9
        for view in views:
            if view == "camera":
                if not saved["camera"]:
                    continue
                scene.camera = saved["camera"]
            else:
                az, el = (math.radians(a) for a in ANGLES[view])
                offset = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
                cam.location = center + offset * distance
                cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
                cam_data.clip_end = distance * 10
                scene.camera = cam
            path = os.path.join(out_dir, f"{(target or 'scene')}_{view}.png")
            r.filepath = path
            bpy.ops.render.render(write_still=True)
            written.append(path)
    finally:
        r.engine, r.resolution_x, r.resolution_y = saved["engine"], saved["x"], saved["y"]
        r.resolution_percentage, r.filepath = saved["pct"], saved["path"]
        r.image_settings.file_format = saved["fmt"]
        scene.camera = saved["camera"]
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data)
    return {"images": written, "center": list(center), "framed_size_m": round(size, 3)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
