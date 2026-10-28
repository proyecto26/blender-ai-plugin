"""Create (or update) a shot camera that frames a target: focal length, framing
distance from bounds, optional depth of field focused on the target, a Track To
constraint to a focus empty, and composition guides.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/camera_rig.py", init_globals={"ARGS": {
        "name": "CAM_Hero_01", "target": "SM_Crate_01", "lens_mm": 85, "azimuth_deg": 30, "elevation_deg": 12}})["result"]

ARGS:
    name           (str)  camera name, CAM_ prefix (default CAM_Shot_01)
    target         (str|None) object to frame (default: visible meshes)
    lens_mm        (float) 24 wide/horror, 35 environment, 50 neutral, 85 hero detail (default 50)
    azimuth_deg, elevation_deg (float) orbit angles around the target
    fill           (float) fraction of frame height the subject fills (default 0.7)
    dof_fstop      (float|None) enable DOF with this f-stop (e.g. 2.8); None disables
    set_active     (bool) make it the scene camera (default True)
    aspect         (str|None) "16:9", "2.39:1", "1:1", "9:16" - sets render resolution
"""
import json
import math
import sys

import bpy
from mathutils import Vector

ASPECTS = {"16:9": (1920, 1080), "2.39:1": (2048, 858), "1:1": (1080, 1080), "9:16": (1080, 1920), "4:3": (1440, 1080)}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _bounds(target):
    scene = bpy.context.scene
    objs = [bpy.data.objects[target]] if target else [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not objs:
        raise ValueError("nothing to frame")
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, (hi - lo)


def main(name="CAM_Shot_01", target=None, lens_mm=50.0, azimuth_deg=30.0, elevation_deg=12.0, fill=0.7,
         dof_fstop=None, set_active=True, aspect=None):
    if not name.startswith("CAM_"):
        name = "CAM_" + name
    if target and target not in bpy.data.objects:
        raise ValueError(f"object not found: {target}")
    scene = bpy.context.scene
    if aspect:
        scene.render.resolution_x, scene.render.resolution_y = ASPECTS[aspect]
    center, dims = _bounds(target)

    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        col = bpy.data.collections.get("COL_Cameras")
        if col is None:
            col = bpy.data.collections.new("COL_Cameras")
            scene.collection.children.link(col)
        col.objects.link(cam)
    data = cam.data
    data.lens = lens_mm
    data.sensor_fit = "AUTO"
    data.passepartout_alpha = 0.9
    data.show_composition_thirds = True

    focus_name = f"EMP_{name}_Focus"
    focus = bpy.data.objects.get(focus_name)
    if focus is None:
        focus = bpy.data.objects.new(focus_name, None)
        focus.empty_display_size = 0.1
        for c in cam.users_collection:
            c.objects.link(focus)
    focus.location = center

    # Distance so the subject's bounding sphere fills `fill` of the smaller frame dimension.
    radius = max(dims.length / 2, 0.01)
    res_x, res_y = scene.render.resolution_x, scene.render.resolution_y
    sensor = data.sensor_width
    fov_h = 2 * math.atan(sensor / (2 * lens_mm))
    fov_small = fov_h if res_x <= res_y else 2 * math.atan(math.tan(fov_h / 2) * res_y / res_x)
    distance = radius / math.sin(fov_small * fill / 2)
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    cam.location = center + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * distance
    data.clip_start = max(0.01, distance * 0.01)
    data.clip_end = max(100.0, distance * 20)

    track = cam.constraints.get("Track_Focus") or cam.constraints.new("TRACK_TO")
    track.name = "Track_Focus"
    track.target = focus
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    data.dof.use_dof = dof_fstop is not None
    if dof_fstop is not None:
        data.dof.focus_object = focus
        data.dof.aperture_fstop = dof_fstop
    if set_active:
        scene.camera = cam
    return {"camera": cam.name, "lens_mm": lens_mm, "distance_m": round(distance, 3),
            "dof": data.dof.use_dof, "resolution": [res_x, res_y], "active": scene.camera == cam}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
