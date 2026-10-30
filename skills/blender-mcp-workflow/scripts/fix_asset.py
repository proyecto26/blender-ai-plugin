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
Children of a fixed object keep their world transform (their parent inverse absorbs the change). Vertex- and
triangle-parented children are corrected by measuring them, which needs a child with no constraints, a
non-singular transform and a base in the active view layer; any other child is left as is and listed in
`children_not_preserved` with the reason.
"""
import json
import math
import sys

import bmesh
import bpy
from mathutils import Matrix


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


def _apply(obj, apply):
    loc, rot, scale = obj.matrix_basis.decompose()
    if apply == "rotation_scale":
        bake = rot.to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1.0))
        keep = Matrix.Translation(loc)
    else:
        bake = Matrix.Diagonal((*scale, 1.0))
        keep = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
    if bake == Matrix.Identity(4):
        return False, []
    # Like Blender's Apply Scale, children keep their world transform: the parent's world matrix
    # changes from W to W @ basis^-1 @ keep, so fold the difference into each child's parent inverse.
    for vl in bpy.context.scene.view_layers:
        vl.update()
    old_world = obj.matrix_world.copy()
    new_world = old_world @ obj.matrix_basis.inverted_safe() @ keep
    # Vertex/triangle-parented children follow the baked geometry, so their parent frame is measured instead:
    # world = frame @ parent_inverse @ basis, hence parent_inverse' = pi @ B @ W_new^-1 @ W_old @ B^-1.
    # All checks run before anything changes; children outside the supported cases are only reported.
    view_layer = bpy.context.view_layer
    kids = [c for c in bpy.data.objects if c.parent is obj]
    object_kids, measured, skipped = [], [], []
    for c in kids:
        if c.parent_type == "OBJECT":
            object_kids.append(c)
        elif c.parent_type not in ("VERTEX", "VERTEX_3"):
            skipped.append({"name": c.name, "reason": f"parent type {c.parent_type}"})
        elif c.constraints:
            skipped.append({"name": c.name, "reason": "constraints"})
        elif c.name not in view_layer.objects:
            skipped.append({"name": c.name, "reason": "not evaluated in the active view layer"})
        elif abs(c.matrix_basis.determinant()) < 1e-9 or abs(c.matrix_world.determinant()) < 1e-9:
            skipped.append({"name": c.name, "reason": "singular"})
        else:
            measured.append((c, c.matrix_world.copy()))
    obj.data.transform(bake)
    obj.matrix_basis = keep
    for c in object_kids:
        c.matrix_parent_inverse = new_world.inverted_safe() @ old_world @ c.matrix_parent_inverse
    if any(s < 0 for s in scale):
        obj.data.flip_normals()
    if measured:
        view_layer.update()
        for c, w_old in measured:
            b = c.matrix_basis.copy()
            c.matrix_parent_inverse = c.matrix_parent_inverse @ b @ c.matrix_world.inverted() @ w_old @ b.inverted()
        view_layer.update()
    return True, skipped


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
        applied, skipped = _apply(obj, apply) if apply else (False, [])
        r = {"applied": applied, "uv_added": None}
        if skipped:
            r["children_not_preserved"] = skipped
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
