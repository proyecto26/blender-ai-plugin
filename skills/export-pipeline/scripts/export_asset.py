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

glTF/GLB exports use the active scene only and return `verify` (the file is read back):
{checked, nodes, joints, missing, no_geometry, leaked, ok}. Other formats return {"checked": False}.
The scene camera and the mode the active object was in are restored (the glTF exporter changes both).
"""
import json
import os
import struct
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


def _gltf_json(path):
    """Return the glTF JSON dict of a .glb (JSON chunk) or .gltf file."""
    if path.lower().endswith(".gltf"):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    with open(path, "rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] != b"glTF":
            raise ValueError("not a GLB file")
        length, ctype = struct.unpack("<I4s", fh.read(8))
        if ctype != b"JSON":
            raise ValueError("first GLB chunk is not JSON")
        return json.loads(fh.read(length).decode("utf-8"))


def _allowed_names(targets):
    allowed = set()
    stack = list(targets)
    while stack:
        o = stack.pop()
        if o.name in allowed:
            continue
        allowed.add(o.name)
        stack.extend(o.children)
        for mod in o.modifiers:
            if mod.type == "ARMATURE" and mod.object:
                stack.append(mod.object)
        if o.parent:
            stack.append(o.parent)
    return allowed


def _verify(path, targets):
    """Read the exported file back: nodes, joints, requested meshes missing or written with no geometry (glTF
    omits an empty mesh and keeps its node), other objects leaked."""
    if not path.lower().endswith((".glb", ".gltf")) or not os.path.exists(path):
        return {"checked": False}
    data = _gltf_json(path)
    nodes = [n.get("name", "") for n in data.get("nodes", [])]
    joint_idx = {j for s in data.get("skins", []) for j in s.get("joints", [])}
    joints = sorted({nodes[i] for i in joint_idx if i < len(nodes)})
    allowed = _allowed_names(targets)
    present = set(nodes)
    missing = sorted(o.name for o in targets if o.type == "MESH" and o.name not in present)
    with_mesh = {n.get("name", "") for n in data.get("nodes", []) if "mesh" in n}
    no_geometry = sorted(o.name for o in targets if o.type == "MESH" and o.instance_type == "NONE"
                         and o.name in present and o.name not in with_mesh)
    leaked = sorted({n for i, n in enumerate(nodes)
                     if i not in joint_idx and n in bpy.data.objects and n not in allowed})
    return {"checked": True, "nodes": sorted(present), "joints": joints, "missing": missing,
            "no_geometry": no_geometry, "leaked": leaked, "ok": not missing and not no_geometry and not leaked}


def _restore_state(camera, active, mode):
    """Put back the scene camera and the active object's mode. Never raises, so an export error stays the reported one."""
    try:
        bpy.context.scene.camera = camera
        if active and active.mode != mode:
            with bpy.context.temp_override(active_object=active, object=active):
                bpy.ops.object.mode_set(mode=mode)
    except (RuntimeError, ReferenceError) as exc:
        print(f"export: could not restore camera/mode: {exc}", file=sys.stderr)


def main(out_path, objects=None, engine="generic", animation=False):
    targets = _targets(objects)
    ext = os.path.splitext(out_path)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    view_layer = bpy.context.view_layer
    prev_sel = [o for o in bpy.context.selected_objects]
    prev_active = view_layer.objects.active
    prev_mode = prev_active.mode if prev_active else "OBJECT"
    prev_camera = bpy.context.scene.camera
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
                bpy.ops.export_scene.gltf(filepath=out_path, use_selection=True, use_active_scene=True, export_apply=True,
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
        _restore_state(prev_camera, prev_active, prev_mode)
    ok = os.path.exists(out_path)
    return {"path": out_path, "exists": ok, "bytes": os.path.getsize(out_path) if ok else 0,
            "engine": engine, "objects": [o.name for o in targets],
            "verify": _verify(out_path, targets)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
