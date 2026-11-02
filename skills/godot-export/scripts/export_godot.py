"""Godot 4 glTF (.glb) export with import-hint naming checks. Godot reads node-name
suffixes on import: -col (trimesh static body), -convcolonly / -colonly (collision
only), -rigid, -navmesh, -noimp. Reports which hints are present.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/export_godot.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01", "SM_Crate_01-colonly"], "out_path": "/tmp/godot/crate.glb"}})["result"]

ARGS:
    objects   (list[str]|None) default: COL_Export contents, else selection
    out_path  (str, required) .glb (binary, recommended) or .gltf
    animation (bool) default False

Returns `verify` (the file is read back): {checked, nodes, joints, missing, no_geometry, leaked, ok}.
The scene camera and the mode the active object was in are restored (the glTF exporter changes both).
"""
import json
import os
import struct
import sys

import bpy

HINTS = ("-colonly", "-convcolonly", "-col", "-convcol", "-rigid", "-navmesh", "-noimp", "-vehicle", "-wheel", "-occ")


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


def main(out_path, objects=None, animation=False):
    if objects:
        targets = [bpy.data.objects[n] for n in objects if n in bpy.data.objects]
    else:
        col = bpy.data.collections.get("COL_Export")
        targets = list(col.all_objects) if col else list(bpy.context.selected_objects)
    if not targets:
        raise ValueError("nothing to export")
    hints = {o.name: next((h for h in HINTS if o.name.endswith(h)), None) for o in targets}
    unapplied = [o.name for o in targets if o.type == "MESH" and not all(abs(s - 1) < 1e-4 for s in o.scale)]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prev = [o for o in bpy.context.selected_objects]
    prev_active = bpy.context.view_layer.objects.active
    prev_mode = prev_active.mode if prev_active else "OBJECT"
    prev_camera = bpy.context.scene.camera
    for o in prev:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    try:
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            bpy.ops.export_scene.gltf(
                filepath=out_path, use_selection=True, use_active_scene=True, export_apply=True, export_yup=True,
                export_format="GLB" if out_path.lower().endswith(".glb") else "GLTF_SEPARATE",
                export_animations=animation, export_extras=True)
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev:
            o.select_set(True)
        _restore_state(prev_camera, prev_active, prev_mode)
    ok = os.path.exists(out_path)
    return {"exported": ok, "path": out_path, "bytes": os.path.getsize(out_path) if ok else 0,
            "verify": _verify(out_path, targets),
            "import_hints": {k: v for k, v in hints.items() if v}, "unapplied_scale": unapplied,
            "import_tips": "Godot: keep the .glb in res://; use Advanced Import Settings for per-mesh physics/LOD."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
