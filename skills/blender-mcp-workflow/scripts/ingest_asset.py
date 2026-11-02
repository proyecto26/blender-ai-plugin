"""Import a local model file into a new collection and normalize only the imported objects.

Formats: .glb, .gltf (with its external .bin), .fbx, .obj, .usd (each has a round-trip test in tests/blender/test_parity.py;
a format without a passing test is not listed: .usda, .usdc, .usdz and others are untested and refused).
The file must be on disk: URLs, network paths and `.blend` files are refused (download outside Blender; to bring in
a `.blend` use Blender's own Append/Link). Existing objects are not touched: only the objects the import created
are scaled, moved, renamed and (optionally) baked.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/ingest_asset.py", init_globals={"ARGS": {
        "path": "C:/assets/chair.glb", "target_size_m": 0.9, "prefix": "SM_"}})["result"]

Steps: import into a fresh collection; optional up-axis fix (rotation about world X); uniform scale so the chosen
axis of the combined mesh bounds equals `target_size_m`; the combined bounds are then moved so their base centre
(middle of X and Y, lowest Z) sits at the world origin; a mesh that is alone in its hierarchy also gets its origin
there; every root object of the imported hierarchy also gets its origin there (children keep their world shape);
mesh objects get the name prefix; transforms are baked into the meshes (children keep their world shape);
finally `validate_asset.py` (same folder) is run on the imported meshes and returned as `validation`. A failure after
the import removes everything the import created: its objects and collections, and every other datablock
(meshes, materials, images, cameras, lights, ...) that did not exist before and has no user left. Scenes, workspaces and
libraries are never touched.

ARGS:
    path            (str, required) local file
    collection      (str|None) new collection name; default "Ingest_<file name>" (Blender adds a suffix if taken)
    target_size_m   (float|None) size to scale to; None keeps the file's scale
    size_axis       (str) "z" (height, default), "x", "y" or "max" (largest of the three)
    up_axis_fix     (str) "none" (default), "y_up_to_z_up" or "z_up_to_y_up"; importers already convert the axes
                    their format defines, so use this only for a file that comes in lying on its side
    prefix          (str) added to imported mesh object names that lack it (default "SM_"; "" to skip)
    apply_transforms (bool) bake rotation and scale into the imported meshes (default True)
    tri_budget, max_size_m   passed on to validate_asset.py
    scripts_dir     (str|None) folder holding validate_asset.py and fix_asset.py; default = the folder of this script
"""
import json
import os
import re
import runpy
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

IMPORTERS = {".glb": "gltf", ".gltf": "gltf", ".fbx": "fbx", ".obj": "obj", ".usd": "usd"}


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


def _check_path(path):
    if not path or not isinstance(path, str):
        raise ValueError("path (a local model file) is required")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", path) or path.startswith(("\\\\", "//")):
        raise ValueError(f"refusing {path!r}: only local files are imported. Download it outside Blender first")
    ext = os.path.splitext(path)[1].lower()
    if ext.startswith(".blend"):
        raise ValueError(".blend files are not ingested (they carry whole scenes); use Blender's Append or Link")
    if ext not in IMPORTERS:
        raise ValueError(f"unsupported file type {ext!r}; supported: {', '.join(sorted(IMPORTERS))}")
    full = os.path.abspath(path)
    if not os.path.isfile(full):
        raise ValueError(f"file not found: {full}")
    return full, ext


def _run_import(kind, path):
    if kind == "gltf":
        return bpy.ops.import_scene.gltf(filepath=path)
    if kind == "fbx":
        return bpy.ops.wm.fbx_import(filepath=path)
    if kind == "obj":
        return bpy.ops.wm.obj_import(filepath=path)
    return bpy.ops.wm.usd_import(filepath=path)


def _layer_collection(root, col):
    if root.collection is col:
        return root
    for child in root.children:
        found = _layer_collection(child, col)
        if found:
            return found
    return None


def _world_bounds(meshes, depsgraph):
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for obj in meshes:
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            if not n:
                continue
            co = np.empty(n * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            m = np.array(obj.matrix_world, dtype=np.float64)
            w = co.reshape(n, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
            lo, hi = np.minimum(lo, w.min(0)), np.maximum(hi, w.max(0))
        finally:
            ev.to_mesh_clear()
    return lo, hi


def _update():
    for vl in bpy.context.scene.view_layers:
        vl.update()


def _sibling(scripts_dir, name):
    base = scripts_dir or (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None)
    if not base:
        raise ValueError(f"cannot find {name}: pass scripts_dir")
    path = os.path.join(base, name)
    if not os.path.isfile(path):
        raise ValueError(f"{name} not found next to this script: {path}")
    return path


# ID collections of bpy.data that are never touched by a rollback: UI/session state, not import output
_KEEP_TYPES = {"scenes", "workspaces", "screens", "window_managers", "libraries", "brushes", "palettes", "all_ids"}


def _id_collections():
    for attr in dir(bpy.data):
        coll = getattr(bpy.data, attr, None)
        if attr in _KEEP_TYPES or not isinstance(coll, bpy.types.bpy_prop_collection) or not hasattr(coll, "remove"):
            continue
        yield attr, coll


def _id_pointers():
    return {attr: {i.as_pointer() for i in coll} for attr, coll in _id_collections()}


def _remove_created(before):
    """Remove what an import created, whatever its type: compared with the snapshot of every bpy.data collection.
    Objects and collections the import made always go; any other datablock goes only when it did not exist before
    and nothing uses it any more (a pre-existing datablock, or one with a user such as a fake user, stays)."""
    for o in [o for o in bpy.data.objects if o.as_pointer() not in before["objects"]]:
        bpy.data.objects.remove(o)
    for c in [c for c in bpy.data.collections if c.as_pointer() not in before["collections"]]:
        bpy.data.collections.remove(c)
    for _ in range(6):  # removing a material frees its images, and so on: repeat until nothing more is released
        gone = 0
        for attr, coll in _id_collections():
            old = before.get(attr, set())
            for d in [d for d in coll if d.as_pointer() not in old and d.users == 0]:
                coll.remove(d)
                gone += 1
        if not gone:
            break


def main(path=None, collection=None, target_size_m=None, size_axis="z", up_axis_fix="none", prefix="SM_",
         apply_transforms=True, tri_budget=None, max_size_m=50.0, scripts_dir=None):
    full, ext = _check_path(path)
    if size_axis not in ("x", "y", "z", "max"):
        raise ValueError("size_axis must be x, y, z or max")
    if up_axis_fix not in ("none", "y_up_to_z_up", "z_up_to_y_up"):
        raise ValueError("up_axis_fix must be none, y_up_to_z_up or z_up_to_y_up")
    if target_size_m is not None and float(target_size_m) <= 0:
        raise ValueError("target_size_m must be > 0")
    validate_path = _sibling(scripts_dir, "validate_asset.py")
    fix_path = _sibling(scripts_dir, "fix_asset.py")

    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    objs_before = set(bpy.data.objects.keys())
    cols_before = set(bpy.data.collections.keys())
    ids_before = _id_pointers()
    selected = [o.name for o in scene.objects if o.select_get()]
    active = view_layer.objects.active.name if view_layer.objects.active else None
    prev_layer_col = view_layer.active_layer_collection

    stem = os.path.splitext(os.path.basename(full))[0]
    col = bpy.data.collections.new(collection or f"Ingest_{stem}")
    scene.collection.children.link(col)
    new = []
    try:
        view_layer.active_layer_collection = _layer_collection(view_layer.layer_collection, col)
        _run_import(IMPORTERS[ext], full)
        new = [o for o in bpy.data.objects if o.name not in objs_before]
        if not new:
            raise ValueError("the import created no objects")
        for o in new:
            for c in list(o.users_collection):
                if c is not col:
                    c.objects.unlink(o)
            if o.name not in col.objects:
                col.objects.link(o)
        for _ in range(8):  # drop collections the importer created and that are now empty
            empty = [c for c in bpy.data.collections if c.name not in cols_before and c is not col
                     and not c.objects and not c.children]
            if not empty:
                break
            for c in empty:
                bpy.data.collections.remove(c)
        new_names = {o.name for o in new}
        # an armature import adds helper meshes that only draw its bones (pose bone custom shapes, e.g. glTF's
        # "Icosphere"): they are not part of the asset's body, so they never set its size, name or validation
        bone_shapes = {pb.custom_shape for o in new if o.type == "ARMATURE" for pb in o.pose.bones if pb.custom_shape}
        meshes = [o for o in new if o.type == "MESH" and o not in bone_shapes]
        if not meshes:
            raise ValueError("the file contains no mesh objects")
        roots = [o for o in new if o.parent is None or o.parent.name not in new_names]
        imported_verts = sum(len(o.data.vertices) for o in meshes)
        _update()
        notes = []

        if up_axis_fix != "none":
            rx = Matrix.Rotation(np.radians(90.0 if up_axis_fix == "y_up_to_z_up" else -90.0), 4, "X")
            for r in roots:
                r.matrix_world = rx @ r.matrix_world
            _update()

        depsgraph = bpy.context.evaluated_depsgraph_get()
        lo, hi = _world_bounds(meshes, depsgraph)
        size_before = (hi - lo)
        scale = 1.0
        if target_size_m is not None:
            cur = float(size_before.max() if size_axis == "max" else size_before["xyz".index(size_axis)])
            if cur <= max(1e-9, 1e-5 * float(size_before.max())):  # float32 noise on a flat mesh is not an extent
                raise ValueError(f"the imported meshes have no extent along {size_axis!r}; cannot scale")
            scale = float(target_size_m) / cur
        centre_xy = (lo[:2] + hi[:2]) / 2 * scale
        shift = Vector((-centre_xy[0], -centre_xy[1], -lo[2] * scale))
        move = Matrix.Translation(shift) @ Matrix.Diagonal((scale, scale, scale, 1.0))
        for r in roots:
            r.matrix_world = move @ r.matrix_world
        _update()

        renamed = {}
        if prefix:
            for o in meshes:
                if not o.name.startswith(prefix):
                    old = o.name
                    o.name = prefix + old
                    renamed[old] = o.name

        mesh_names = [o.name for o in meshes]
        if apply_transforms:
            fixed = runpy.run_path(fix_path, init_globals={"ARGS": {"objects": mesh_names, "apply": "rotation_scale",
                                                                    "uv": ""}}, run_name="__ingest_fix__")["result"]
            skipped = {k: v["children_not_preserved"] for k, v in fixed["objects"].items() if v.get("children_not_preserved")}
            if skipped:
                notes.append({"children_not_preserved": skipped})
        _update()

        # every root gets its origin at the world origin, which is the base centre now (set origin without moving
        # anything: a mesh root's data is shifted to compensate, and the children keep their world matrices)
        for r in roots:
            if r in bone_shapes:
                continue
            if r.type == "MESH" and not apply_transforms:
                notes.append(f"origin of {r.name} left as imported: it can only be reset after the transforms are baked")
                continue
            if r.type not in ("MESH", "EMPTY"):
                continue
            if r.type == "MESH" and not np.allclose(np.array(r.matrix_world.to_3x3()), np.eye(3), atol=1e-6):
                notes.append(f"origin of {r.name} left as imported: it still carries rotation or scale")
                continue
            kids = [(c, c.matrix_world.copy()) for c in r.children]
            if r.type == "MESH":
                if r.data.users > 1:
                    r.data = r.data.copy()
                r.data.transform(Matrix.Translation(r.matrix_world.to_translation()), shape_keys=True)
            at_origin = r.matrix_world.copy()  # an empty may carry rotation and scale for its children: keep those
            at_origin.translation = (0.0, 0.0, 0.0)
            r.matrix_world = at_origin
            _update()
            for c, mw in kids:
                c.matrix_world = mw
            _update()

        depsgraph = bpy.context.evaluated_depsgraph_get()
        lo2, hi2 = _world_bounds(meshes, depsgraph)
        final_verts = sum(len(o.data.vertices) for o in meshes)
        validation = runpy.run_path(validate_path, init_globals={"ARGS": {
            "objects": [o.name for o in meshes], "tri_budget": tri_budget, "prefix": prefix,
            "max_size_m": float(max_size_m)}}, run_name="__ingest_validate__")["result"]
    except Exception:
        # what the import made, even when it failed half way and `new` is still empty
        _remove_created(ids_before)
        raise
    finally:
        try:
            view_layer.active_layer_collection = prev_layer_col
        except (RuntimeError, ReferenceError):
            pass
        for o in scene.objects:
            o.select_set(o.name in selected)
        view_layer.objects.active = bpy.data.objects.get(active) if active else None

    return {"format": ext, "collection": col.name, "imported_objects": sorted(o.name for o in new),
            "meshes": mesh_names, "renamed": renamed, "scale_factor": round(scale, 8),
            "size_before_m": [round(float(v), 5) for v in size_before],
            "size_after_m": [round(float(v), 5) for v in (hi2 - lo2)],
            "base_center_after_m": [round(float((lo2[0] + hi2[0]) / 2), 5), round(float((lo2[1] + hi2[1]) / 2), 5),
                                    round(float(lo2[2]), 5)],
            "vertices": {"imported": imported_verts, "final": final_verts},
            "validation": validation, "notes": notes}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
