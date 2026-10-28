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
"""
import json
import os
import sys

import bpy

HINTS = ("-colonly", "-convcolonly", "-col", "-convcol", "-rigid", "-navmesh", "-noimp", "-vehicle", "-wheel", "-occ")


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


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
    for o in prev:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    try:
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            bpy.ops.export_scene.gltf(
                filepath=out_path, use_selection=True, export_apply=True, export_yup=True,
                export_format="GLB" if out_path.lower().endswith(".glb") else "GLTF_SEPARATE",
                export_animations=animation, export_extras=True)
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev:
            o.select_set(True)
    ok = os.path.exists(out_path)
    return {"exported": ok, "path": out_path, "bytes": os.path.getsize(out_path) if ok else 0,
            "import_hints": {k: v for k, v in hints.items() if v}, "unapplied_scale": unapplied,
            "import_tips": "Godot: keep the .glb in res://; use Advanced Import Settings for per-mesh physics/LOD."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
