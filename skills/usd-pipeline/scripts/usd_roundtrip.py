"""Export objects to a USD file, import that file back, compare the copy with the originals, then remove the copy.

Checks: mesh/empty/other counts, world transforms, evaluated vertex and face counts per object, and material names
per object. Your scene is left as it was: the imported objects, meshes, materials, images and collections created by
the import are removed again (`keep` leaves them). The scene's world, frame range, frame step, fps and current frame
are never changed: the import runs with `set_frame_range` and `create_world_material` off, and the time settings are put
back even if the run fails. The USD file is written to `out_path` and stays there.

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
(characters other than letters, digits and _ become _) and without Blender's .001 suffix. A mesh object is matched by
its MESH DATA name, not its object name: the export writes a transform prim named after the object and a mesh prim
named after the mesh data, and the import returns one object named after the mesh prim (measured on Blender 5.2:
object "Crate" with mesh "Cube" comes back as "Cube"). Empties and other types are matched by object name. Results
are still listed under the original object's name. Objects that share a label (linked duplicates share one mesh) are
paired with their imports by the closest world matrix. The import merges the transform prim into the mesh object, so
the object name is not recoverable: duplicates at the SAME transform are paired by the assignment with the fewest
differences (a minimum-cost assignment, optimal for any count; costs are small whole numbers for real differences in transform, material set and vert/face counts, plus a bounded tie-breaker from the evaluated bounding box relative to object size that can never outweigh a real difference; the whole-number part of a total is exact; the fractional tie-breakers are summed in floating point, so totals within 1e-9 count as equal). `ambiguous_pairings` lists the labels where coincident objects remain or another assignment has the same total, since that is a guess (`tie_check_one_move_only` lists labels with more than 300 pairs, where only one-move changes are checked); an intact round trip is never reported as a swap. Material names are compared the same way,
because the import renames a material that already exists. `ok` is true only when nothing differs.

Materials are read from the evaluated object's slots, so an OBJECT-linked slot override is what USD receives and is
compared. Known loss, reported as `ok: false`: a Geometry Nodes Set Material that puts a material different from the
slot's on the faces. Blender's USD exporter writes only the slot material, so the file and the import carry the slot
material and the node's material is gone (measured on Blender 5.2: NodeMat -> SlotMat). Setting the same material the
slot already holds is not a loss and is `ok: true`.
"""
import contextlib
import json
import os
import re
import sys

import bpy
import numpy as np

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
    verts = faces = bbox = None
    names = [s.material.name for s in obj.material_slots if s.material]
    if obj.type == "MESH":
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            verts, faces = len(me.vertices), len(me.polygons)
            if verts:  # evaluated local extent: separates coincident duplicates whose modifiers move vertices without changing counts
                co = np.empty(verts * 3, dtype=np.float32)
                me.vertices.foreach_get("co", co)
                co = co.reshape(-1, 3)
                bbox = [float(x) for x in (*co.min(axis=0), *co.max(axis=0))]
            # the materials the evaluated faces use: a Set Material node replaces a slot's material, and a slot that
            # no face uses is not written by the exporter, so the slot list alone gives false differences
            idx = np.empty(len(me.polygons), dtype=np.int32)
            me.polygons.foreach_get("material_index", idx)
            mats = list(me.materials)
            slots = ev.material_slots  # the evaluated object's slots honour an OBJECT-linked override of the mesh material
            used = []
            for i in sorted(set(idx.tolist())):
                m = slots[i].material if 0 <= i < len(slots) else None
                m = m or (mats[i] if 0 <= i < len(mats) else None)
                if m:
                    used.append(m.name)
            names = used
        finally:
            ev.to_mesh_clear()
    mats = sorted({_clean_key(SUFFIX_RE.sub("", n) if imported else n) for n in names})
    return {"type": obj.type, "verts": verts, "faces": faces, "bbox": bbox, "materials": mats,
            "matrix": [list(row) for row in obj.matrix_world]}


def _assign(n_k, n_c, cost):
    """Pairs (key index, candidate index) of the minimum-total-cost one-to-one assignment (Hungarian algorithm,
    O(n^2 m) pure Python): optimal for any size, every row paired when n_k <= n_c, else every candidate."""
    if n_k == 0 or n_c == 0:
        return []
    flip = n_k > n_c  # the algorithm assigns every ROW, so the smaller side must be the rows
    n, m = (n_c, n_k) if flip else (n_k, n_c)
    c = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c[i][j] = cost(j - 1, i - 1) if flip else cost(i - 1, j - 1)
    inf = float("inf")
    u, v, way, match = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        match[0], j0 = i, 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = match[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = c[i0][j] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if match[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            match[j0], j0 = match[j1], j1
    pairs = [(match[j] - 1, j - 1) for j in range(1, m + 1) if match[j]]
    return sorted((j, i) for i, j in pairs) if flip else sorted(pairs)


TIE_SOLVE_LIMIT = 300  # matched pairs for which every pair is forbidden and the assignment re-solved


def _has_tie(pairs, n_k, n_c, cost, eps=1e-9):
    """True when a different assignment has the same total: forbid each matched pair in turn and re-solve; an
    unchanged total means the pairing is a guess between equals (this also covers rows left unmatched with equal
    options). Beyond TIE_SOLVE_LIMIT pairs only the one-move check (a swap of two candidates, taking an unused
    candidate, or an unmatched original taking a matched one's candidate) runs, which can miss a longer cycle; `_tie_checked_fully` says which one applied."""
    if not pairs:
        return False
    base = sum(cost(i, j) for i, j in pairs)
    if len(pairs) <= TIE_SOLVE_LIMIT:
        big = 1e6 + abs(base) * 10
        for fi, fj in pairs:
            alt = _assign(n_k, n_c, lambda i, j: big if (i, j) == (fi, fj) else cost(i, j))
            if len(alt) == len(pairs) and sum(big if (i, j) == (fi, fj) else cost(i, j) for i, j in alt) <= base + eps:
                return True
        return False
    cur = dict(pairs)
    used = set(cur.values())
    free = [j for j in range(n_c) if j not in used]
    rows = sorted(cur)
    unmatched = [r for r in range(n_k) if r not in cur]
    for x, i in enumerate(rows):
        if any(abs(cost(i, j) - cost(i, cur[i])) <= eps for j in free):
            return True
        if any(abs(cost(r, cur[i]) - cost(i, cur[i])) <= eps for r in unmatched):
            return True
        for i2 in rows[x + 1:]:
            if abs(cost(i, cur[i2]) + cost(i2, cur[i]) - cost(i, cur[i]) - cost(i2, cur[i2])) <= eps:
                return True
    return False


def _tie_checked_fully(n_pairs):
    return n_pairs <= TIE_SOLVE_LIMIT


def _pair_cost(b, c, tol, n):
    """Cost of pairing original description `b` with imported `c`, lexicographic by construction. Real differences are
    whole numbers (1000 for a transform beyond tol, 10 each for a material set or vert/face count mismatch) and the
    tie-breakers (matrix distance, evaluated bounding box relative to the object's size) add less than 1 over the
    whole assignment of `n` pairs, so a tie-breaker can never outweigh a real difference or make a passing pairing fail."""
    d = max(abs(x - y) for ra, rb in zip(b["matrix"], c["matrix"]) for x, y in zip(ra, rb))
    primary = (1000 if d > tol else 0) + 10 * (b["materials"] != c["materials"]) \
        + 10 * ((b["verts"], b["faces"]) != (c["verts"], c["faces"]))
    rel = 0.0
    if b.get("bbox") is not None and c.get("bbox") is not None:
        size = max(max(b["bbox"][3 + k] - b["bbox"][k] for k in range(3)), 1e-6)
        rel = min(1.0, max(abs(x - y) for x, y in zip(b["bbox"], c["bbox"])) / size)
    return primary + (0.5 * rel + 0.5 * d / (1.0 + d)) / (n + 1)


def _match_key(obj):
    """Where an original shows up after the round trip: the exporter writes a mesh object as a transform prim named
    after the object and a mesh prim named after the MESH DATA, and the import gives the merged object the mesh prim's
    name (measured on Blender 5.2: object "Crate" with mesh "Cube" comes back as "Cube"). Other types keep the object name."""
    label = obj.data.name if obj.type == "MESH" and obj.data else obj.name
    return (obj.type, _clean_key(label))


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
        before = {(o.type, _clean_key(o.name), o.name): _describe(o, dg) for o in targets}

    snap = {coll: {i.name for i in getattr(bpy.data, coll)}
            for coll in ("objects", "meshes", "materials", "images", "collections", "cameras", "lights", "node_groups", "worlds",
                 "armatures", "actions")}
    scene = bpy.context.scene
    world, rd = scene.world, scene.render
    timing = (scene.frame_start, scene.frame_end, scene.frame_step, scene.frame_current, rd.fps, rd.fps_base)
    view_layer = bpy.context.view_layer
    prev_sel = list(bpy.context.selected_objects)
    prev_active = view_layer.objects.active
    try:
        # inside the try: an object that cannot be selected (its collection is excluded) refuses the run, and the
        # selection and active object the user had are put back below
        for o in prev_sel:
            o.select_set(False)
        for o in targets:
            o.select_set(True)
        view_layer.objects.active = targets[0]
        with bpy.context.temp_override(active_object=targets[0], selected_objects=targets,
                                       selected_editable_objects=targets):
            bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=True, export_materials=True,
                                  export_subdivision=subdivision, evaluation_mode="RENDER")
        if not os.path.isfile(out_path):
            raise RuntimeError("usd_export wrote no file")
        bpy.ops.wm.usd_import(filepath=out_path, create_collection=True, import_materials=True,
                              mtl_name_collision_mode="MAKE_UNIQUE", set_frame_range=False,
                              create_world_material=False)
    finally:
        (scene.frame_start, scene.frame_end, scene.frame_step, scene.frame_current, rd.fps, rd.fps_base) = timing
        if scene.world is not world:
            scene.world = world
        for o in targets:
            try:
                o.select_set(False)
            except RuntimeError:
                pass  # not in this view layer: it was never selected
        for o in prev_sel:
            if o.name in bpy.data.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active

    new = {coll: [i for i in getattr(bpy.data, coll) if i.name not in snap[coll]] for coll in snap}
    dg = bpy.context.evaluated_depsgraph_get()
    # Objects that share one mesh (linked duplicates) share a label, so each label holds a LIST of imported objects
    # and the originals with that label are paired with them by transform below.
    after = {}
    for o in new["objects"]:
        # a mesh object is named after its mesh prim, which the exporter names from the MESH DATA (see "Matching")
        label = o.data.name if o.type == "MESH" and o.data else o.name
        k = (o.type, _clean_key(SUFFIX_RE.sub("", label)))
        after.setdefault(k, []).append(_describe(o, dg, imported=True))

    def _matrix_diff(a, b):
        return max(abs(x - y) for ra, rb in zip(a["matrix"], b["matrix"]) for x, y in zip(ra, rb))

    # Pair originals with imports within each label by the closest world matrix, so two linked duplicates at
    # different transforms are each compared with their own import and never with each other's.
    paired, duplicates, ambiguous, tie_partial = {}, [], [], []
    groups = {}
    for key in before:
        groups.setdefault(_match_key(bpy.data.objects[key[2]]), []).append(key)
    for mk, keys in groups.items():
        cands = list(after.get(mk, []))
        # The import merges the transform prim into the mesh object, so the object's name is not recoverable and
        # coincident duplicates tie on the matrix. A pair costs its matrix distance (beyond tol, dominant) plus a
        # step for each differing material set or vert/face count; the cheapest whole assignment wins, so an
        # intact round trip never reports a swap as a loss while a real loss on one still shows.
        n_max = max(len(keys), len(cands))

        def cost(ki, ci):
            return _pair_cost(before[keys[ki]], cands[ci], tol, n_max)
        pairs = _assign(len(keys), len(cands), cost)
        for ki, ci in pairs:
            paired[keys[ki]] = cands[ci]
        if len({tuple(round(x, 4) for row in before[k]["matrix"] for x in row) for k in keys}) < len(keys) \
                or _has_tie(pairs, len(keys), len(cands), cost):
            ambiguous.append(mk[1])
        if not _tie_checked_fully(len(pairs)):
            tie_partial.append(mk[1])
        if len(cands) > len(keys):
            duplicates.append(f"{mk[1]} ({len(cands)} imported for {len(keys)} exported)")

    problems = []
    count_before = {}
    for d in before.values():
        count_before[d["type"]] = count_before.get(d["type"], 0) + 1
    # Compare only objects that exist on both sides by type: the import may add Xform empties for parents.
    for typ in ("MESH",):
        n_after = sum(1 for ds in after.values() for d in ds if d["type"] == typ)
        if n_after != count_before.get(typ, 0):
            problems.append(f"{typ} count: exported {count_before.get(typ, 0)}, imported {n_after}")
    per_object = {}
    for key, b in before.items():
        k = key[1]
        a = paired.get(key)
        if a is None:
            problems.append(f"{k}: not found after import as {key[0]}")
            per_object[k] = {"found": False}
            continue
        worst = max(abs(x - y) for ra, rb in zip(a["matrix"], b["matrix"]) for x, y in zip(ra, rb))
        entry = {"found": True, "matrix_max_diff": worst, "verts": [b["verts"], a["verts"]],
                 "faces": [b["faces"], a["faces"]], "materials": [b["materials"], a["materials"]],
                 "bbox_max_diff": (max(abs(x - y) for x, y in zip(b["bbox"], a["bbox"]))
                                   if b["bbox"] is not None and a["bbox"] is not None else None)}
        per_object[k] = entry
        if worst > tol:
            problems.append(f"{k}: transform differs by {worst:.6f}")
        if (a["verts"], a["faces"]) != (b["verts"], b["faces"]):
            problems.append(f"{k}: verts/faces {b['verts']}/{b['faces']} -> {a['verts']}/{a['faces']}")
        if a["materials"] != b["materials"]:
            problems.append(f"{k}: materials {b['materials']} -> {a['materials']}")
    for name in duplicates:
        problems.append(f"{name}: more objects imported than exported")

    removed = 0
    if not keep:
        for o in new["objects"]:
            bpy.data.objects.remove(o, do_unlink=True)
            removed += 1
        for coll in ("meshes", "armatures", "actions", "materials", "images", "cameras", "lights", "node_groups", "collections", "worlds"):
            for item in new[coll]:
                try:
                    getattr(bpy.data, coll).remove(item)
                except (ReferenceError, RuntimeError):
                    pass
    return {"ok": not problems, "problems": problems, "path": out_path, "bytes": os.path.getsize(out_path),
            "exported": sorted(k[1] for k in before), "imported": sorted(f"{t}:{n}" for (t, n), ds in after.items() for _ in ds), "per_object": per_object,
            "counts_exported": count_before, "ambiguous_pairings": ambiguous, "tie_check_one_move_only": tie_partial, "removed_from_scene": removed, "kept": bool(keep)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
