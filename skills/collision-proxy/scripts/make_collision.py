"""Generate simple collision proxies for render meshes, named for the target engine.
Shapes: box (oriented to object), convex (hull of evaluated mesh). Proxies go to
COL_Collision, display as wire, are hidden from render, and parented to the source.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/make_collision.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "shape": "convex", "engine": "unreal"}})["result"]

ARGS:
    objects (list[str], required)
    shape   (str) box | convex (default box)
    engine  (str) unreal -> UCX_<name>_NN | unity -> <name>_COL_NN | godot -> <name>-colonly | generic -> COL_<name>_NN
    max_hull_verts (int) convex hull vertex cap via decimate (default 64; Unreal limit is 256)
    replace (bool) default True: each proxy is tagged custom property collision_proxy = "<source>|<engine>"; a rerun
            builds the new proxy first, then removes only the older proxies with the same tag (and their unused
            mesh), so there is one proxy per source+engine named _01. Untagged objects, and tagged copies that are not parented to the source or are
            renamed off the engine pattern, are never touched; if one
            holds the _01 name the suffixed name is kept and listed in name_conflicts. False appends _02, _03...
"""
import json
import re
import sys

import bmesh
import bpy
from mathutils import Vector


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


def _name(engine, base, index):
    if engine == "unreal":
        return f"UCX_{base}_{index:02d}"
    if engine == "unity":
        return f"{base}_COL_{index:02d}"
    if engine == "godot":
        return f"{base}-colonly" if index == 1 else f"{base}_{index:02d}-colonly"
    return f"COL_{base}_{index:02d}"


def _is_engine_name(engine, base, name):
    """True if `name` is what this script would have called a proxy of `base` (Blender .001 suffixes allowed)."""
    for i in range(1, 1000):
        if re.fullmatch(re.escape(_name(engine, base, i)) + r"(\.\d{3})?", name):
            return True
    return False


def _box_mesh(src):
    bm = bmesh.new()
    corners = [Vector(c) for c in src.bound_box]
    verts = [bm.verts.new(c) for c in corners]
    for f in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
        bm.faces.new([verts[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _convex_mesh(src, max_verts):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = src.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    ev.to_mesh_clear()
    hull = bmesh.ops.convex_hull(bm, input=bm.verts, use_existing_faces=False)
    interior = [g for g in hull["geom_interior"] if isinstance(g, bmesh.types.BMVert)]
    unused = [g for g in hull["geom_unused"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.delete(bm, geom=list(set(interior + unused)), context="VERTS")
    if len(bm.verts) > max_verts:
        # Collapse shortest edges until under the cap; keeps the hull convex enough for physics.
        while len(bm.verts) > max_verts:
            edge = min(bm.edges, key=lambda e: e.calc_length())
            bmesh.ops.collapse(bm, edges=[edge])
        bmesh.ops.convex_hull(bm, input=bm.verts, use_existing_faces=False)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    return bm


def _remove_proxy(obj):
    me = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def main(objects, shape="box", engine="unreal", max_hull_verts=64, replace=True):
    if shape not in ("box", "convex"):
        raise ValueError("shape must be 'box' or 'convex'")
    col = bpy.data.collections.get("COL_Collision")
    if col is None:
        col = bpy.data.collections.new("COL_Collision")
        bpy.context.scene.collection.children.link(col)
    made = []
    removed = []
    name_conflicts = []
    for name in objects:
        src = bpy.data.objects.get(name)
        if src is None or src.type != "MESH":
            continue
        base = src.name
        tag = f"{base}|{engine}"
        # A copy of a proxy carries the tag too: only remove tagged objects that are parented to the
        # source AND still have an engine-pattern name (a renamed duplicate is the user's).
        old = [o for o in bpy.data.objects if o.get("collision_proxy") == tag and o.parent is src
               and _is_engine_name(engine, base, o.name)] if replace else []
        index = 1
        while bpy.data.objects.get(_name(engine, base, index)):
            index += 1
        bm = _box_mesh(src) if shape == "box" else _convex_mesh(src, max_hull_verts)
        proxy_name = _name(engine, base, index)
        me = bpy.data.meshes.new(proxy_name)
        bm.to_mesh(me)
        verts = len(bm.verts)
        bm.free()
        proxy = bpy.data.objects.new(proxy_name, me)
        proxy["collision_proxy"] = tag
        col.objects.link(proxy)
        proxy.parent = src
        proxy.matrix_parent_inverse.identity()
        proxy.display_type = "WIRE"
        proxy.hide_render = True
        if replace:
            # New proxy exists first; only proxies carrying the same tag are removed.
            for o in old:
                removed.append(o.name)
                _remove_proxy(o)
            wanted = _name(engine, base, 1)
            if proxy.name != wanted:
                if bpy.data.objects.get(wanted) is None:
                    proxy.name = wanted
                    me.name = wanted
                else:
                    name_conflicts.append({"wanted": wanted, "got": proxy.name})
        made.append({"name": proxy.name, "source": base, "verts": verts})
    return {"engine": engine, "shape": shape, "replace": replace, "proxies": made,
            "removed": removed, "name_conflicts": name_conflicts}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
