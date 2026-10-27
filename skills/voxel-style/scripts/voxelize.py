"""Voxelize meshes with the Remesh modifier in Blocks mode (non-destructive), flat
shading, and an optional apply. Reports the resulting voxel count estimate.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/voxelize.py", init_globals={"ARGS": {
        "objects": ["SM_Tree_01"], "voxel_size": 0.1}})["result"]

ARGS:
    objects     (list[str], required)
    voxel_size  (float) target block size in meters (default 0.1)
    apply       (bool) apply the modifier (default False)
"""
import json
import math
import sys

import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def main(objects, voxel_size=0.1, apply=False):
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"error": "not a mesh"}
            continue
        largest = max(obj.dimensions) or 1.0
        # Blocks mode works in octree depth; pick the depth whose cell size is <= voxel_size.
        depth = max(1, min(10, math.ceil(math.log2(largest / voxel_size))))
        mod = obj.modifiers.get("Voxel_Remesh") or obj.modifiers.new("Voxel_Remesh", "REMESH")
        mod.mode = "BLOCKS"
        mod.octree_depth = depth
        mod.scale = min(0.99, (largest / voxel_size) / (2 ** depth))
        mod.use_remove_disconnected = False
        for poly in obj.data.polygons:
            poly.use_smooth = False
        if apply:
            with bpy.context.temp_override(object=obj, active_object=obj,
                                           selected_objects=[obj], selected_editable_objects=[obj]):
                bpy.ops.object.modifier_apply(modifier=mod.name)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        faces = len(mesh.polygons)
        ev.to_mesh_clear()
        out[name] = {"octree_depth": depth, "scale": round(mod.scale, 3) if not apply else None,
                     "faces": faces, "approx_voxel_size_m": round(largest / (2 ** depth) / max(mod.scale, 1e-6), 4)
                     if not apply else voxel_size, "applied": apply}
    return {"objects": out}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
