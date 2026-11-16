"""Prepare an even-topology copy of an object for sculpting. The original is never changed: the script duplicates it,
applies the duplicate's modifiers (the viewport result), voxel-remeshes the duplicate at `voxel_size_m`, and reports the
vertex counts and proof that the original is unchanged.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/sculpt_prep.py", init_globals={"ARGS": {
        "object": "SM_Head", "voxel_size_m": 0.01}})["result"]

ARGS:
    object        (str, required)   mesh object to prepare
    voxel_size_m  (float, required) voxel size of the remesh in world metres (> 0); smaller means more vertices.
                                    Converted to mesh units with the object scale and the scene unit scale; the
                                    budget uses the mesh-space bounding box. Non-uniform scale is refused (apply it).
    name          (str)             name for the copy (default "<object>_sculpt"); an existing name gets Blender's
                                    numeric suffix, so nothing is overwritten
    max_voxels    (float)           refuse before doing anything when the bounding box holds more than this many
                                    voxels (default 2e8), because a tiny voxel size can exhaust memory
    result_path   (str)             write the result (plus run_id) as JSON here, atomically, on success
    run_id        (str)             copied into the result and the file

The copy goes into the same collections as the original. Selection, active object and mode are restored; the copy is
left unselected. The copy has its own mesh (shape keys, vertex groups and UVs do not survive a voxel remesh; the
original keeps them). Result: "copy" (name), "vertices_before" (original), "vertices_after_modifiers",
"vertices_after_remesh", "original_unchanged" (vertex positions, modifier stack, transform, mesh and selection compared
before and after) and "verdict": FAIL if the original changed or the remesh produced no vertices, else PASS.
If anything fails after the copy exists, the copy and its mesh are removed again (they are this script's own).
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector


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


def _json_safe(x):
    """NaN/inf become None, recursively, so the result is valid JSON."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x


def _fingerprint(obj):
    """Everything about the original this script promises not to touch."""
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return {
        "mesh": me.name,
        "vertices": n,
        "positions": co.tobytes(),
        "modifiers": [(m.name, m.type, m.show_viewport, m.show_render) for m in obj.modifiers],
        "matrix": tuple(tuple(r) for r in obj.matrix_world),
        "collections": sorted(c.name for c in obj.users_collection),
        "mesh_users": me.users,
        "selected": sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()),
        "active": (bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None),
    }


def _same(a, b):
    return a == b


def main(object=None, voxel_size_m=None, name=None, max_voxels=2e8, result_path=None, run_id=None):
    obj = bpy.data.objects.get(object) if object else None
    if obj is None:
        raise ValueError(f"object not found: {object}")
    if obj.type != "MESH":
        raise ValueError(f"{object} is not a mesh")
    if voxel_size_m is None or not voxel_size_m > 0:
        raise ValueError("voxel_size_m must be a number > 0")
    # The remesher works in mesh (object-space) units, so convert the world voxel size in metres to mesh units.
    scale = obj.matrix_world.to_scale()
    s = max(abs(v) for v in scale)
    if s <= 0 or min(abs(v) for v in scale) < s * (1 - 1e-4):
        raise ValueError(f"{obj.name} has non-uniform scale {tuple(round(v, 6) for v in scale)}; apply its scale "
                         "(Object > Apply > Scale) or make it uniform first (this script does not change the original)")
    unit = bpy.context.scene.unit_settings.scale_length or 1.0  # metres per Blender unit
    mesh_voxel = voxel_size_m / (s * unit)
    ev0 = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners = [Vector(c) for c in ev0.bound_box]
    local = [max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]
    voxels = (local[0] / mesh_voxel + 1) * (local[1] / mesh_voxel + 1) * (local[2] / mesh_voxel + 1)
    if voxels > max_voxels:
        raise ValueError(f"the bounding box holds about {voxels:.3g} voxels at voxel_size_m={voxel_size_m}; "
                         f"raise voxel_size_m (limit max_voxels={max_voxels:g})")

    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = [o for o in view_layer.objects if o.select_get()]
    prev_mode = obj.mode
    if prev_mode != "OBJECT":
        if bpy.ops.object.mode_set(mode="OBJECT") != {"FINISHED"}:
            raise RuntimeError("could not leave the current mode")
    before = _fingerprint(obj)
    copy = new_mesh = None
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        new_mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        after_mods = len(new_mesh.vertices)
        copy = obj.copy()
        copy.name = name or f"{obj.name}_sculpt"
        copy.data = new_mesh
        copy.modifiers.clear()
        for col in obj.users_collection:
            col.objects.link(copy)
        if not copy.users_collection:
            bpy.context.scene.collection.objects.link(copy)
        new_mesh.name = f"{copy.name}_mesh"
        new_mesh.remesh_voxel_size = float(mesh_voxel)
        new_mesh.use_remesh_preserve_volume = False
        for o in prev_selected:
            o.select_set(False)
        copy.select_set(True)
        view_layer.objects.active = copy
        if bpy.ops.object.voxel_remesh() != {"FINISHED"}:
            raise RuntimeError("voxel remesh did not finish")
        after_remesh = len(copy.data.vertices)
    except BaseException:
        if copy is not None:
            bpy.data.objects.remove(copy)
        if new_mesh is not None and new_mesh.users == 0:
            bpy.data.meshes.remove(new_mesh)
        raise
    finally:
        for o in view_layer.objects:
            o.select_set(False)
        for o in prev_selected:
            if o.name in view_layer.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active
        if prev_mode != "OBJECT" and obj.name in bpy.data.objects:
            bpy.ops.object.mode_set(mode=prev_mode)

    after = _fingerprint(obj)
    unchanged = _same(before, after)
    verdict = "PASS" if unchanged and after_remesh > 0 else "FAIL"
    result = {"verdict": verdict, "run_id": run_id, "original": obj.name, "copy": copy.name,
              "voxel_size_m": float(voxel_size_m), "vertices_before": before["vertices"],
              "vertices_after_modifiers": after_mods, "vertices_after_remesh": after_remesh,
              "original_unchanged": unchanged}
    if not unchanged:
        result["note"] = "the original differs from before the run"
    elif after_remesh == 0:
        result["note"] = "the remesh produced no vertices"
    result = _json_safe(result)
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, allow_nan=False)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
