"""Read-only scene audit: collections, objects, evaluated triangle counts,
materials, unapplied transforms and naming-prefix violations.

Run through the official Blender MCP (`execute_blender_code`):

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/scene_audit.py",
                            init_globals={"ARGS": {"collection": None}})["result"]

or headless: blender -b file.blend --python scene_audit.py -- '{"collection": "COL_Export"}'

ARGS:
    collection   (str|None)  limit the audit to one collection (recursive)
    tri_budget   (int|None)  flag the scene total when it exceeds this budget
    max_objects  (int)       cap the per-object list to keep MCP replies small
"""
import json
import sys

import bpy

PREFIXES = {
    "MESH": ("SM_", "SK_", "UCX_", "UBX_", "USP_", "UCP_", "COL_", "LOD", "GEO_", "HP_", "LP_", "BL_", "REF_"),
    "ARMATURE": ("ARM_", "SK_", "RIG_"),
    "CAMERA": ("CAM_",),
    "LIGHT": ("LGT_",),
    "EMPTY": ("EMP_", "SOCKET_", "ROOT_", "CTRL_"),
    "CURVES": ("HAIR_", "CRV_"),
    "CURVE": ("CRV_",),
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _objects_in(collection_name):
    if not collection_name:
        return list(bpy.context.scene.objects)
    col = bpy.data.collections.get(collection_name)
    if col is None:
        raise ValueError(f"collection not found: {collection_name}")
    return list(col.all_objects)


def _triangles(obj, depsgraph):
    if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE", "META"}:
        return 0
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def main(collection=None, tri_budget=None, max_objects=200):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = _objects_in(collection)
    rows, total_tris, naming, unapplied = [], 0, [], []

    for obj in objects:
        tris = _triangles(obj, depsgraph)
        total_tris += tris
        scale_ok = all(abs(s - 1.0) < 1e-4 for s in obj.scale)
        rot_ok = all(abs(r) < 1e-4 for r in obj.rotation_euler)
        if obj.type == "MESH" and not (scale_ok and rot_ok):
            unapplied.append(obj.name)
        allowed = PREFIXES.get(obj.type)
        if allowed and not obj.name.startswith(allowed):
            naming.append(obj.name)
        if len(rows) < max_objects:
            rows.append({
                "name": obj.name,
                "type": obj.type,
                "collections": [c.name for c in obj.users_collection],
                "tris": tris,
                "materials": [s.material.name for s in obj.material_slots if s.material],
                "modifiers": [m.type for m in getattr(obj, "modifiers", [])],
                "dimensions": [round(d, 4) for d in obj.dimensions],
                "location": [round(v, 4) for v in obj.location],
            })

    def tree(col, depth=0):
        return {"name": col.name, "objects": len(col.objects),
                "children": [tree(c, depth + 1) for c in col.children] if depth < 6 else []}

    scene = bpy.context.scene
    return {
        "scene": scene.name,
        "file": bpy.data.filepath or "<unsaved>",
        "unit_system": scene.unit_settings.system,
        "unit_scale": scene.unit_settings.scale_length,
        "render_engine": scene.render.engine,
        "view_transform": scene.view_settings.view_transform,
        "collections": tree(scene.collection),
        "object_count": len(objects),
        "total_tris": total_tris,
        "over_budget": bool(tri_budget) and total_tris > tri_budget,
        "unapplied_transforms": unapplied,
        "naming_violations": naming,
        "orphan_materials": [m.name for m in bpy.data.materials if m.users == 0],
        "objects": rows,
        "truncated": len(objects) > max_objects,
    }


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
