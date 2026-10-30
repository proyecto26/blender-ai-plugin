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
    eye_height     (float|None) absolute camera Z in metres (e.g. 1.6 for a first-person eye); keeps the
                   horizontal bearing from azimuth_deg and recomputes the direction (elevation_deg is ignored)
    min_distance, max_distance (float|None) clamp the framing distance (metres), e.g. to keep the camera
                   inside a ring of cover

Result `distance_m` is the actual camera-to-centre distance; `notes` lists any clamp that was applied.
Result also reports `occluded_by` (sorted names of objects between the camera and the subject) and
`visible_fraction` (share of 6 sample points on the subject's bounds that a ray from the camera reaches).
Ignored when casting: the subject and its children (all visible meshes when target is None), hide_render
objects, objects carrying the `collision_proxy` property, and fluid domains (they render as volumes).
"""
import json
import math
import sys

import bpy
from mathutils import Vector

ASPECTS = {"16:9": (1920, 1080), "2.39:1": (2048, 858), "1:1": (1080, 1080), "9:16": (1080, 1920), "4:3": (1440, 1080)}


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


def _bounds(target):
    scene = bpy.context.scene
    objs = [bpy.data.objects[target]] if target else [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not objs:
        raise ValueError("nothing to frame")
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, (hi - lo)


def _subject(target):
    scene = bpy.context.scene
    if target:
        root = bpy.data.objects[target]
        return {root} | set(root.children_recursive)
    return {o for o in scene.objects if o.type == "MESH" and o.visible_get()}


def _is_volume(obj):
    """Fluid domains render as a volume, not as their box surface."""
    return any(m.type == "FLUID" and m.fluid_type == "DOMAIN" for m in getattr(obj, "modifiers", ()))


def _occluders(cam, subject, center, dims):
    """Cast from the camera to 6 sample points on the subject bounds; skip ignorable hits."""
    scene = bpy.context.scene
    bpy.context.view_layer.update()  # evaluate the Track To constraint and transforms before casting
    dg = bpy.context.evaluated_depsgraph_get()
    eye = cam.matrix_world.translation.copy()
    hx, hy, hz = dims.x / 2 * 0.9, dims.y / 2 * 0.9, dims.z / 2 * 0.9
    points = [center, center + Vector((hx, 0, 0)), center + Vector((-hx, 0, 0)),
              center + Vector((0, hy, 0)), center + Vector((0, -hy, 0)), center + Vector((0, 0, hz))]
    blockers, visible = set(), 0
    for p in points:
        origin = eye.copy()
        blocked = False
        for _ in range(16):
            vec = p - origin
            remaining = vec.length
            if remaining <= 1e-4:
                break
            direction = vec / remaining
            hit, loc, _n, _i, obj, _m = scene.ray_cast(dg, origin, direction, distance=remaining)
            if not hit:
                break
            if obj in subject or obj.hide_render or obj.get("collision_proxy") is not None or _is_volume(obj):
                origin = loc + direction * 1e-4
                continue
            blockers.add(obj.name)
            blocked = True
            break
        visible += 0 if blocked else 1
    return sorted(blockers), round(visible / len(points), 3)


def main(name="CAM_Shot_01", target=None, lens_mm=50.0, azimuth_deg=30.0, elevation_deg=12.0, fill=0.7,
         dof_fstop=None, set_active=True, aspect=None, eye_height=None, min_distance=None, max_distance=None):
    if min_distance is not None and max_distance is not None and min_distance > max_distance:
        raise ValueError("min_distance must not exceed max_distance")
    if not name.startswith("CAM_"):
        name = "CAM_" + name
    if target and target not in bpy.data.objects:
        raise ValueError(f"object not found: {target}")
    scene = bpy.context.scene
    if aspect:
        scene.render.resolution_x, scene.render.resolution_y = ASPECTS[aspect]
    bpy.context.view_layer.update()  # matrix_world of objects moved in this same call is stale until updated
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
    notes = []
    if min_distance is not None and distance < min_distance:
        notes.append(f"framing distance {distance:.2f} m raised to min_distance {min_distance:.2f} m")
        distance = min_distance
    if max_distance is not None and distance > max_distance:
        notes.append(f"framing distance {distance:.2f} m lowered to max_distance {max_distance:.2f} m")
        distance = max_distance
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    if eye_height is None:
        cam.location = center + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * distance
    else:
        dz = eye_height - center.z
        if abs(dz) > distance:
            notes.append(f"eye_height is {abs(dz):.2f} m from the subject centre, more than the framing distance "
                         f"{distance:.2f} m: the horizontal offset is clamped to ~0, so the camera sits almost "
                         "directly above/below the subject")
        horiz = math.sqrt(max(distance * distance - dz * dz, 1e-4))
        cam.location = Vector((center.x + math.sin(a) * horiz, center.y - math.cos(a) * horiz, eye_height))
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
    occluded_by, visible_fraction = _occluders(cam, _subject(target), center, dims)
    actual = (cam.matrix_world.translation - center).length  # with eye_height this differs from the framing distance
    return {"camera": cam.name, "lens_mm": lens_mm, "distance_m": round(actual, 3), "notes": notes,
            "location": [round(v, 3) for v in cam.matrix_world.translation],
            "dof": data.dof.use_dof, "resolution": [res_x, res_y], "active": scene.camera == cam,
            "occluded_by": occluded_by, "visible_fraction": visible_fraction}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
