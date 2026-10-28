"""Export selected/listed objects with engine presets (FBX / glTF / USD / OBJ).
Validates the output file exists and reports its size. Does not modify the scene
(selection is restored; modifiers are applied only in the exported data).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/export_asset.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01", "UCX_SM_Crate_01_01"], "engine": "unreal", "out_path": "/tmp/SM_Crate_01.fbx"}})["result"]

ARGS:
    objects  (list[str]|None) default: everything in COL_Export, else selection
    engine   (str) unreal | unity | godot | web | generic
    out_path (str, required) file path; extension decides the format (.fbx .glb .gltf .usd/.usdc/.usda .obj)
    animation (bool) include animation (default False)
"""
import json
import os
import sys

import bpy

FBX_PRESETS = {
    # Unreal: -X forward / Z up, unit scale 1.0 with FBX_SCALE_NONE -> 1 BU = 1 cm handled by the importer
    "unreal": dict(axis_forward="-Y", axis_up="Z", apply_scale_options="FBX_SCALE_NONE", mesh_smooth_type="FACE",
                   use_tspace=True, add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X"),
    # Unity: apply unit scale so 1 Blender m = 1 Unity unit with scale (1,1,1), rotation baked
    "unity": dict(axis_forward="-Z", axis_up="Y", apply_scale_options="FBX_SCALE_UNITS", bake_space_transform=True,
                  mesh_smooth_type="FACE", use_tspace=True, add_leaf_bones=False),
    "generic": dict(axis_forward="-Z", axis_up="Y", apply_scale_options="FBX_SCALE_ALL", mesh_smooth_type="FACE",
                    add_leaf_bones=False),
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _targets(names):
    if names:
        missing = [n for n in names if n not in bpy.data.objects]
        if missing:
            raise ValueError(f"objects not found: {missing}")
        return [bpy.data.objects[n] for n in names]
    col = bpy.data.collections.get("COL_Export")
    if col and col.all_objects:
        return list(col.all_objects)
    if bpy.context.selected_objects:
        return list(bpy.context.selected_objects)
    raise ValueError("nothing to export: pass objects, fill COL_Export, or select objects")


def main(out_path, objects=None, engine="generic", animation=False):
    targets = _targets(objects)
    ext = os.path.splitext(out_path)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    view_layer = bpy.context.view_layer
    prev_sel = [o for o in bpy.context.selected_objects]
    prev_active = view_layer.objects.active
    for o in prev_sel:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    view_layer.objects.active = targets[0]
    try:
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            if ext == ".fbx":
                preset = FBX_PRESETS.get(engine, FBX_PRESETS["generic"])
                bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, use_mesh_modifiers=True,
                                         object_types={"MESH", "ARMATURE", "EMPTY"}, bake_anim=animation,
                                         path_mode="COPY", embed_textures=False, **preset)
            elif ext in (".glb", ".gltf"):
                bpy.ops.export_scene.gltf(filepath=out_path, use_selection=True, export_apply=True,
                                          export_format="GLB" if ext == ".glb" else "GLTF_SEPARATE",
                                          export_yup=True, export_animations=animation)
            elif ext in (".usd", ".usdc", ".usda"):
                bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=True,
                                      export_animation=animation, evaluation_mode="RENDER")
            elif ext == ".obj":
                bpy.ops.wm.obj_export(filepath=out_path, export_selected_objects=True, apply_modifiers=True,
                                      forward_axis="NEGATIVE_Z", up_axis="Y")
            else:
                raise ValueError(f"unsupported extension {ext}")
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev_sel:
            if o.name in bpy.data.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active
    ok = os.path.exists(out_path)
    return {"path": out_path, "exists": ok, "bytes": os.path.getsize(out_path) if ok else 0,
            "engine": engine, "objects": [o.name for o in targets]}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
