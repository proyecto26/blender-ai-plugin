"""Unity FBX export with pre-flight checks: applied transforms, UVs, material slots,
and axis/scale conversion so the asset imports at scale (1,1,1) with no -90 X rotation
(Apply Scalings = FBX Units Scale + Apply Transform).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/export_unity.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "out_path": "/tmp/unity/SM_Crate_01.fbx"}})["result"]

ARGS:
    objects  (list[str], required) meshes (+ optional armature/empties)
    out_path (str, required) .fbx path
    animation (bool) include animation (default False)
    strict   (bool) refuse to export on FAIL (default True)
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


def main(objects, out_path, animation=False, strict=True):
    targets = [bpy.data.objects[n] for n in objects if n in bpy.data.objects]
    if not targets:
        raise ValueError("no valid objects")
    checks = {}
    for o in targets:
        if o.type != "MESH":
            continue
        c = {
            "transforms_applied": "PASS" if all(abs(s - 1) < 1e-4 for s in o.scale)
            and all(abs(r) < 1e-4 for r in o.rotation_euler) else "FAIL",
            "uvs": "PASS" if o.data.uv_layers else "FAIL",
            "materials": "PASS" if o.material_slots and all(s.material for s in o.material_slots) else "WARN",
            "collider_naming": "PASS" if not o.name.lower().endswith(("_col", "_collider")) or "_COL" in o.name else "WARN",
        }
        checks[o.name] = c
    failed = any("FAIL" in c.values() for c in checks.values())
    if strict and failed:
        return {"exported": False, "checks": checks, "reason": "fix FAIL checks or pass strict=False"}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prev = [o for o in bpy.context.selected_objects]
    for o in prev:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    try:
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            bpy.ops.export_scene.fbx(
                filepath=out_path, use_selection=True, object_types={"MESH", "ARMATURE", "EMPTY"},
                apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", bake_space_transform=True,
                axis_forward="-Z", axis_up="Y", mesh_smooth_type="FACE", use_tspace=True,
                use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=animation)
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev:
            o.select_set(True)
    ok = os.path.exists(out_path)
    return {"exported": ok, "path": out_path, "bytes": os.path.getsize(out_path) if ok else 0, "checks": checks,
            "import_tips": "Unity: Model > Scale Factor 1, Convert Units on; Materials > Extract; Rig per asset type."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
