"""Create a looping 360-degree turntable: a pivot empty with linear Z rotation and
a camera parented to it, framed on the target. Non-destructive (adds objects to
COL_Turntable only); sets the frame range.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/turntable.py", init_globals={"ARGS": {
        "target": "SM_Crate_01", "frames": 120}})["result"]

ARGS:
    target        (str, required)
    frames        (int)   frames per revolution (default 120 = 5 s at 24 fps)
    lens_mm       (float) default 70
    elevation_deg (float) default 15
    set_active    (bool)  make the turntable camera the scene camera (default True)
"""
import json
import math
import sys

import bpy
from mathutils import Vector


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _linear(action_owner):
    """Force linear interpolation on every key (layered/slotted actions: layer -> strip -> channelbag)."""
    anim = action_owner.animation_data
    action = anim.action if anim else None
    if action is None:
        return
    curves = [fc for layer in action.layers for strip in layer.strips
              for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def main(target, frames=120, lens_mm=70.0, elevation_deg=15.0, set_active=True):
    obj = bpy.data.objects.get(target)
    if obj is None:
        raise ValueError(f"object not found: {target}")
    scene = bpy.context.scene
    col = bpy.data.collections.get("COL_Turntable")
    if col is None:
        col = bpy.data.collections.new("COL_Turntable")
        scene.collection.children.link(col)
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, radius = (lo + hi) / 2, max((hi - lo).length / 2, 0.01)

    pivot = bpy.data.objects.get("EMP_Turntable_Pivot") or bpy.data.objects.new("EMP_Turntable_Pivot", None)
    if pivot.name not in col.objects:
        col.objects.link(pivot)
    pivot.location = center
    pivot.rotation_euler = (0, 0, 0)
    pivot.animation_data_clear()

    cam = bpy.data.objects.get("CAM_Turntable")
    if cam is None:
        cam = bpy.data.objects.new("CAM_Turntable", bpy.data.cameras.new("CAM_Turntable"))
        col.objects.link(cam)
    cam.data.lens = lens_mm
    fov = 2 * math.atan(cam.data.sensor_width / (2 * lens_mm))
    distance = radius / math.sin(fov * 0.75 / 2)
    e = math.radians(elevation_deg)
    cam.parent = pivot
    cam.location = Vector((0, -math.cos(e) * distance, math.sin(e) * distance))
    cam.rotation_euler = (math.pi / 2 - e, 0, 0)
    cam.data.clip_end = max(100.0, distance * 10)

    start = scene.frame_start
    pivot.keyframe_insert("rotation_euler", index=2, frame=start)
    pivot.rotation_euler.z = 2 * math.pi
    pivot.keyframe_insert("rotation_euler", index=2, frame=start + frames)
    _linear(pivot)
    scene.frame_end = start + frames - 1  # last frame != first frame -> seamless loop
    if set_active:
        scene.camera = cam
    return {"pivot": pivot.name, "camera": cam.name, "frames": [scene.frame_start, scene.frame_end],
            "distance_m": round(distance, 3), "fps": scene.render.fps}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
