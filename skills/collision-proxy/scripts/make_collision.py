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
"""
import json
import sys

import bmesh
import bpy
from mathutils import Vector


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _name(engine, base, index):
    if engine == "unreal":
        return f"UCX_{base}_{index:02d}"
    if engine == "unity":
        return f"{base}_COL_{index:02d}"
    if engine == "godot":
        return f"{base}-colonly" if index == 1 else f"{base}_{index:02d}-colonly"
    return f"COL_{base}_{index:02d}"


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


def main(objects, shape="box", engine="unreal", max_hull_verts=64):
    if shape not in ("box", "convex"):
        raise ValueError("shape must be 'box' or 'convex'")
    col = bpy.data.collections.get("COL_Collision")
    if col is None:
        col = bpy.data.collections.new("COL_Collision")
        bpy.context.scene.collection.children.link(col)
    made = []
    for name in objects:
        src = bpy.data.objects.get(name)
        if src is None or src.type != "MESH":
            continue
        base = src.name
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
        col.objects.link(proxy)
        proxy.parent = src
        proxy.matrix_parent_inverse.identity()
        proxy.display_type = "WIRE"
        proxy.hide_render = True
        made.append({"name": proxy.name, "source": base, "verts": verts})
    return {"engine": engine, "shape": shape, "proxies": made}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
