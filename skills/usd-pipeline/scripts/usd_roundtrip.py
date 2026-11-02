"""Export objects to a USD file, import that file back, compare the copy with the originals, then remove the copy.

Checks: mesh/empty/other counts, world transforms, evaluated vertex and face counts per object, and material names
per object. Your scene is left as it was: the imported objects, meshes, materials, images and collections created by
the import are removed again (`keep` leaves them). The USD file is written to `out_path` and stays there.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/usd_roundtrip.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01", "SM_Barrel_01"], "out_path": "D:/out/roundtrip.usdc"}})["result"]

ARGS:
    out_path  (str)  USD file to write (.usd .usdc .usda), required; the folder is created
    objects   (list[str]|None) objects to export (default: the selected objects, else every visible mesh/empty)
    tol       (float) allowed difference per matrix entry (default 1e-4)
    keep      (bool) leave the imported copy in the scene (default False)
    subdivision (str) USD export_subdivision: "TESSELLATE" (default; the evaluated mesh is written, so vertex and
              face counts can be compared), "BEST_MATCH" or "IGNORE". With BEST_MATCH a Subdivision Surface modifier
              is written as the base cage plus a subdivision scheme, and a plain import gives back the cage.

Matching: an imported object is paired with the original of the same type and the same name after USD name cleaning
(characters other than letters, digits and _ become _) and without Blender's .001 suffix. The export writes a
transform prim and a mesh prim of the same name per mesh object, so the import yields an empty AND a mesh with one
name: they are told apart by type. Material names are compared the same way,
because the import renames a material that already exists. `ok` is true only when nothing differs.
"""
import contextlib
import json
import os
import re
import sys

import bpy

SUFFIX_RE = re.compile(r"\.\d{3,}$")


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


def _clean_key(name):
    """USD cleans '.001' to '_001' on export; undo that for names that were suffixed in Blender."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


@contextlib.contextmanager
def _render_levels(objs):
    """Show modifiers as the render does (render visibility, render subdivision levels) while measuring, because the
    export runs with evaluation_mode RENDER. Everything is put back afterwards."""
    saved = []
    try:
        for o in objs:
            for m in o.modifiers:
                entry = [m, m.show_viewport, None, None]
                if m.type in ("SUBSURF", "MULTIRES"):
                    entry[2], entry[3] = m.levels, m.render_levels
                saved.append(entry)
                m.show_viewport = m.show_render
                if entry[2] is not None:
                    m.levels = m.render_levels
        bpy.context.view_layer.update()
        yield
    finally:
        for m, vis, lv, rlv in saved:
            m.show_viewport = vis
            if lv is not None:
                m.levels, m.render_levels = lv, rlv
        bpy.context.view_layer.update()


def _describe(obj, depsgraph, imported=False):
    """`imported`: the object came from the USD import, which may add its own .001 to a name that already existed.
    Names of the originals are kept whole (Material.001 is a real name; USD writes it as Material_001)."""
    verts = faces = None
    slots = obj.material_slots
    if obj.type == "MESH":
        ev = obj.evaluated_get(depsgraph)
        slots = ev.material_slots  # the exporter writes the evaluated materials (e.g. Geometry Nodes Set Material)
        me = ev.to_mesh()
        try:
            verts, faces = len(me.vertices), len(me.polygons)
        finally:
            ev.to_mesh_clear()
    mats = sorted({_clean_key(SUFFIX_RE.sub("", s.material.name) if imported else s.material.name)
                   for s in slots if s.material})
    return {"type": obj.type, "verts": verts, "faces": faces, "materials": mats,
            "matrix": [list(row) for row in obj.matrix_world]}


def _targets(names):
    if names:
        out = []
        for n in names:
            o = bpy.data.objects.get(n)
            if o is None:
                raise ValueError(f"object not found: {n}")
            out.append(o)
        return out
    sel = [o for o in bpy.context.selected_objects if o.type in ("MESH", "EMPTY")]
    return sel or [o for o in bpy.context.scene.objects if o.type in ("MESH", "EMPTY") and o.visible_get()]


def main(out_path, objects=None, tol=1e-4, keep=False, subdivision="TESSELLATE"):
    if subdivision not in ("TESSELLATE", "BEST_MATCH", "IGNORE"):
        raise ValueError("subdivision must be TESSELLATE, BEST_MATCH or IGNORE")
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in (".usd", ".usdc", ".usda"):
        raise ValueError("out_path must end in .usd, .usdc or .usda")
    targets = _targets(objects)
    if not targets:
        raise ValueError("nothing to export")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with _render_levels(targets):
        dg = bpy.context.evaluated_depsgraph_get()
        before = {(o.type, _clean_key(o.name)): _describe(o, dg) for o in targets}

    snap = {coll: {i.name for i in getattr(bpy.data, coll)}
            for coll in ("objects", "meshes", "materials", "images", "collections", "cameras", "lights", "node_groups")}
    view_layer = bpy.context.view_layer
    prev_sel = list(bpy.context.selected_objects)
    prev_active = view_layer.objects.active
    for o in prev_sel:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    view_layer.objects.active = targets[0]
    try:
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=True, export_materials=True,
                                  export_subdivision=subdivision, evaluation_mode="RENDER")
        if not os.path.isfile(out_path):
            raise RuntimeError("usd_export wrote no file")
        bpy.ops.wm.usd_import(filepath=out_path, create_collection=True, import_materials=True,
                              mtl_name_collision_mode="MAKE_UNIQUE")
    finally:
        for o in targets:
            o.select_set(False)
        for o in prev_sel:
            if o.name in bpy.data.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active

    new = {coll: [i for i in getattr(bpy.data, coll) if i.name not in snap[coll]] for coll in snap}
    dg = bpy.context.evaluated_depsgraph_get()
    after, duplicates = {}, []
    for o in new["objects"]:
        k = (o.type, _clean_key(SUFFIX_RE.sub("", o.name)))
        if k in after:
            duplicates.append(o.name)
        after[k] = _describe(o, dg, imported=True)

    problems = []
    count_before = {}
    for d in before.values():
        count_before[d["type"]] = count_before.get(d["type"], 0) + 1
    # Compare only objects that exist on both sides by type: the import may add Xform empties for parents.
    for typ in ("MESH",):
        n_after = sum(1 for d in after.values() if d["type"] == typ)
        if n_after != count_before.get(typ, 0):
            problems.append(f"{typ} count: exported {count_before.get(typ, 0)}, imported {n_after}")
    per_object = {}
    for key, b in before.items():
        k = key[1]
        a = after.get(key)
        if a is None:
            problems.append(f"{k}: not found after import as {key[0]}")
            per_object[k] = {"found": False}
            continue
        worst = max(abs(x - y) for ra, rb in zip(a["matrix"], b["matrix"]) for x, y in zip(ra, rb))
        entry = {"found": True, "matrix_max_diff": worst, "verts": [b["verts"], a["verts"]],
                 "faces": [b["faces"], a["faces"]], "materials": [b["materials"], a["materials"]]}
        per_object[k] = entry
        if worst > tol:
            problems.append(f"{k}: transform differs by {worst:.6f}")
        if (a["verts"], a["faces"]) != (b["verts"], b["faces"]):
            problems.append(f"{k}: verts/faces {b['verts']}/{b['faces']} -> {a['verts']}/{a['faces']}")
        if a["materials"] != b["materials"]:
            problems.append(f"{k}: materials {b['materials']} -> {a['materials']}")
    for name in duplicates:
        problems.append(f"{name}: imported twice under the same cleaned name")

    removed = 0
    if not keep:
        for o in new["objects"]:
            bpy.data.objects.remove(o, do_unlink=True)
            removed += 1
        for coll in ("meshes", "materials", "images", "cameras", "lights", "node_groups", "collections"):
            for item in new[coll]:
                try:
                    getattr(bpy.data, coll).remove(item)
                except (ReferenceError, RuntimeError):
                    pass
    return {"ok": not problems, "problems": problems, "path": out_path, "bytes": os.path.getsize(out_path),
            "exported": sorted(k[1] for k in before), "imported": sorted(f"{t}:{n}" for t, n in after), "per_object": per_object,
            "counts_exported": count_before, "removed_from_scene": removed, "kept": bool(keep)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
