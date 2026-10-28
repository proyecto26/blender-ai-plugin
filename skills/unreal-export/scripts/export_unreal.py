"""Unreal Engine FBX export with pre-flight checks: SM_/SK_ prefixes, UCX_ collision
naming that matches a render mesh, LOD naming, SOCKET_ empties, applied transforms,
and scene unit scale. Exports render mesh + its UCX_ proxies + SOCKET_ empties.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/export_unreal.py", init_globals={"ARGS": {
        "mesh": "SM_Crate_01", "out_dir": "/tmp/unreal"}})["result"]

ARGS:
    mesh     (str, required) SM_ (static) or SK_ (skeletal: include its armature parent)
    out_dir  (str, required)
    strict   (bool) refuse to export when a FAIL check exists (default True)
"""
import json
import os
import sys

import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _applied(obj):
    return all(abs(s - 1) < 1e-4 for s in obj.scale) and all(abs(r) < 1e-4 for r in obj.rotation_euler)


def main(mesh, out_dir, strict=True):
    obj = bpy.data.objects.get(mesh)
    if obj is None or obj.type != "MESH":
        raise ValueError(f"mesh not found: {mesh}")
    checks = {}
    checks["prefix"] = "PASS" if obj.name.startswith(("SM_", "SK_")) else "FAIL"
    checks["transforms_applied"] = "PASS" if _applied(obj) else "FAIL"
    checks["has_uvs"] = "PASS" if obj.data.uv_layers else "FAIL"
    checks["lightmap_uv"] = "PASS" if len(obj.data.uv_layers) >= 2 else "WARN"
    checks["unit_scale"] = "PASS" if abs(bpy.context.scene.unit_settings.scale_length - 1.0) < 1e-6 else "WARN"
    ucx = [o for o in bpy.data.objects if o.name.startswith(f"UCX_{obj.name}") and o.type == "MESH"]
    stray_ucx = [o.name for o in bpy.data.objects if o.name.startswith("UCX_") and o not in ucx
                 and not any(o.name.startswith(f"UCX_{m.name}") for m in bpy.data.objects if m.type == "MESH" and not m.name.startswith("UCX_"))]
    checks["collision"] = "PASS" if ucx else "WARN"
    sockets = [o for o in bpy.data.objects if o.type == "EMPTY" and o.name.startswith("SOCKET_") and o.parent == obj]
    lods = sorted(o.name for o in bpy.data.objects if o.name.startswith(obj.name.removesuffix("_LOD0") + "_LOD"))
    targets = [obj] + ucx + sockets
    if obj.name.startswith("SK_") and obj.parent and obj.parent.type == "ARMATURE":
        targets.append(obj.parent)
    if strict and "FAIL" in checks.values():
        return {"exported": False, "checks": checks, "reason": "fix FAIL checks or pass strict=False"}
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{obj.name}.fbx")
    prev = [o for o in bpy.context.selected_objects]
    for o in prev:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    try:
        with bpy.context.temp_override(active_object=obj, selected_objects=targets, selected_editable_objects=targets):
            bpy.ops.export_scene.fbx(
                filepath=path, use_selection=True, object_types={"MESH", "EMPTY", "ARMATURE"},
                apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", axis_forward="-Y", axis_up="Z",
                mesh_smooth_type="FACE", use_tspace=True, use_mesh_modifiers=True, add_leaf_bones=False,
                primary_bone_axis="Y", secondary_bone_axis="X", bake_anim=obj.name.startswith("SK_"))
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev:
            o.select_set(True)
    return {"exported": os.path.exists(path), "path": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            "checks": checks, "collision": [o.name for o in ucx], "sockets": [o.name for o in sockets],
            "lods_found": lods, "stray_ucx": stray_ucx,
            "import_tips": "Import with 'Combine Meshes' off; Unreal reads UCX_ automatically; set LOD group in the asset."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
