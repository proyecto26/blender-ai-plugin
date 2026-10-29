"""Fix the two asset problems validate_asset.py flags most: unapplied scale/rotation and missing UVs.

The fixing counterpart of validate_asset.py. It bakes the object's rotation/scale into its mesh
(data API, no operators, so it works headless) and adds a UV layer only where none exists.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/fix_asset.py",
                            init_globals={"ARGS": {"objects": ["SM_Crate"], "uv": "box"}})["result"]

ARGS:
    objects     (list[str], required) mesh objects to fix
    apply       (str)   "scale" (default), "rotation_scale", or "" to keep transforms
    uv          (str)   "box" (default): world-size box projection, 1 UV unit = `uv_scale` m;
                        "smart": Smart UV Project; "" to skip. Never replaces an existing UV layer.
    uv_scale    (float) metres per UV unit for "box" (default 1.0)

A mesh shared by several objects is made single-user first, so siblings are never changed.
Children of a fixed object keep their world transform (their parent inverse absorbs the change).
"""
import json
import math
import sys

import bmesh
import bpy
from mathutils import Matrix


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _apply(obj, apply):
    loc, rot, scale = obj.matrix_basis.decompose()
    if apply == "rotation_scale":
        bake = rot.to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1.0))
        keep = Matrix.Translation(loc)
    else:
        bake = Matrix.Diagonal((*scale, 1.0))
        keep = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
    if bake == Matrix.Identity(4):
        return False
    # Like Blender's Apply Scale, children keep their world transform: the parent's world matrix
    # changes from W to W @ basis^-1 @ keep, so fold the difference into each child's parent inverse.
    for vl in bpy.context.scene.view_layers:
        vl.update()
    old_world = obj.matrix_world.copy()
    new_world = old_world @ obj.matrix_basis.inverted_safe() @ keep
    # Vertex-parented children follow the baked vertices instead (a VERTEX child stays put; a VERTEX_3
    # child may shift, as with Blender's own Apply Scale): re-check them after applying.
    kids = [c for c in bpy.data.objects if c.parent is obj and c.parent_type == "OBJECT"]
    obj.data.transform(bake)
    obj.matrix_basis = keep
    for c in kids:
        c.matrix_parent_inverse = new_world.inverted_safe() @ old_world @ c.matrix_parent_inverse
    if any(s < 0 for s in scale):
        obj.data.flip_normals()
    return True


def _box_uv(me, uv_scale):
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        u, v = [i for i in range(3) if i != ax]
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co[u] / uv_scale, loop.vert.co[v] / uv_scale)
    bm.to_mesh(me)
    bm.free()


def _smart_uv(obj):
    prev = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = obj
    with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.002)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = prev


def main(objects=None, apply="scale", uv="box", uv_scale=1.0):
    if not objects:
        raise ValueError("objects (list of mesh object names) is required")
    uv_scale = float(uv_scale)
    report = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            report[name] = {"error": "not a mesh object"}
            continue
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        r = {"applied": _apply(obj, apply) if apply else False, "uv_added": None}
        if uv and not obj.data.uv_layers:
            _box_uv(obj.data, uv_scale) if uv == "box" else _smart_uv(obj)
            r["uv_added"] = uv
        r["scale"] = [round(s, 4) for s in obj.scale]
        r["dimensions"] = [round(d, 4) for d in obj.dimensions]
        r["uv_layers"] = [l.name for l in obj.data.uv_layers]
        report[name] = r
    return {"objects": report}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
