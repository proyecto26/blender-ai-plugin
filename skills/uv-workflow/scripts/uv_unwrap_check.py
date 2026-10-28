"""Unwrap (optional) and measure UVs: texel density, UV-space usage and out-of-range
loops, per object. Unwrapping runs Smart UV Project with an island margin sized
for the target texture resolution.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/uv_unwrap_check.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "unwrap": True, "texture_px": 2048, "target_px_per_m": 512}})["result"]

ARGS:
    objects          (list[str], required)
    unwrap           (bool)  run Smart UV Project first (default False = measure only)
    angle_deg        (float) smart project angle limit (default 66)
    texture_px       (int)   texture resolution used for density (default 2048)
    target_px_per_m  (float) target texel density; flags objects outside +/-25 %
"""
import json
import math
import sys

import bmesh
import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _unwrap(obj, angle_deg, texture_px):
    margin = 4.0 / texture_px  # ~4 px padding at the target resolution
    bm = None
    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = obj
    with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle_deg), island_margin=margin,
                                 scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = prev_active
    return margin


def _measure(obj, texture_px):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    uv = bm.loops.layers.uv.active
    if uv is None:
        bm.free()
        return None
    area_3d = area_uv = 0.0
    oob = 0
    for f in bm.faces:
        area_3d += f.calc_area()
        pts = [l[uv].uv for l in f.loops]
        a = 0.0
        for k in range(len(pts)):
            x1, y1 = pts[k]
            x2, y2 = pts[(k + 1) % len(pts)]
            a += x1 * y2 - x2 * y1
            if not (-1e-4 <= x1 <= 1.0001 and -1e-4 <= y1 <= 1.0001):
                oob += 1
        area_uv += abs(a) / 2
    bm.free()
    density = math.sqrt(area_uv / area_3d) * texture_px if area_3d > 0 else 0.0
    return {"texel_density_px_per_m": round(density, 1), "uv_space_used": round(area_uv, 4),
            "surface_m2": round(area_3d, 4), "loops_outside_0_1": oob}


def main(objects, unwrap=False, angle_deg=66.0, texture_px=2048, target_px_per_m=None):
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"error": "not a mesh"}
            continue
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")
        entry = {}
        if unwrap:
            entry["island_margin"] = round(_unwrap(obj, angle_deg, texture_px), 5)
        m = _measure(obj, texture_px)
        entry.update(m or {"error": "no UV layer"})
        if m and target_px_per_m:
            ratio = m["texel_density_px_per_m"] / target_px_per_m
            entry["density_status"] = "PASS" if 0.75 <= ratio <= 1.25 else "WARN"
        out[name] = entry
    return {"texture_px": texture_px, "objects": out}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
