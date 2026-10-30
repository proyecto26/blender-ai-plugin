"""Create an orthographic isometric / dimetric game camera framed on the scene or a target.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/iso_camera.py", init_globals={"ARGS": {
        "projection": "dimetric_2_1", "target": None}})["result"]

ARGS:
    projection (str) true_iso (35.264 deg elevation, 1:1.73) | dimetric_2_1 (30 deg, 2:1 pixel-art tiles) | military (45 deg)
    rotation   (int) 0/90/180/270 - which corner faces the camera (default 0 = 45 deg view)
    target     (str|None) object to frame (default: visible meshes)
    padding    (float) frame padding factor (default 1.15)
    pixel_tile (int|None) tile width in px; sets resolution multiple of it for crisp pixel art
"""
import json
import math
import sys

import bpy
from mathutils import Vector

ELEVATION = {"true_iso": math.degrees(math.atan(1 / math.sqrt(2))),  # 35.264
             "dimetric_2_1": 30.0, "military": 45.0}


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


def main(projection="true_iso", rotation=0, target=None, padding=1.15, pixel_tile=None):
    if projection not in ELEVATION:
        raise ValueError(f"projection must be one of {sorted(ELEVATION)}")
    scene = bpy.context.scene
    objs = [bpy.data.objects[target]] if target else [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not objs:
        raise ValueError("nothing to frame")
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2

    cam = bpy.data.objects.get("CAM_Isometric")
    if cam is None:
        cam = bpy.data.objects.new("CAM_Isometric", bpy.data.cameras.new("CAM_Isometric"))
        scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    elev = math.radians(ELEVATION[projection])
    az = math.radians(45 + rotation)
    direction = Vector((math.sin(az) * math.cos(elev), -math.cos(az) * math.cos(elev), math.sin(elev)))
    distance = (hi - lo).length * 2 + 10
    cam.location = center + direction * distance
    cam.rotation_euler = (math.pi / 2 - elev, 0, az)
    cam.data.clip_start, cam.data.clip_end = 0.1, distance * 3

    # Ortho scale = largest extent of the bounds projected onto the camera plane.
    view = cam.rotation_euler.to_matrix().transposed()
    proj = [view @ (p - center) for p in pts]
    width = max(p.x for p in proj) - min(p.x for p in proj)
    height = max(p.y for p in proj) - min(p.y for p in proj)
    r = scene.render
    if pixel_tile:
        r.resolution_x = pixel_tile * max(8, round(r.resolution_x / pixel_tile))
        r.resolution_y = (pixel_tile // 2) * max(8, round(r.resolution_y / (pixel_tile // 2)))
        r.filter_size = 0.0
    aspect = r.resolution_x / r.resolution_y
    cam.data.ortho_scale = max(width, height * aspect) * padding
    scene.camera = cam
    return {"camera": cam.name, "projection": projection, "elevation_deg": round(ELEVATION[projection], 3),
            "azimuth_deg": 45 + rotation, "ortho_scale": round(cam.data.ortho_scale, 3),
            "resolution": [r.resolution_x, r.resolution_y]}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
