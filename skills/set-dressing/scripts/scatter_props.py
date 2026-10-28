"""Place a requested number of small props (boxes, barrels, pallets) in narrative clusters
around a target object. Props sit on the ground via raycast, never intersect the target's
bounding box or each other, share one mesh per kind, and are named PROP_<Cluster>_<kind>_NN.
Placement retries until the requested count is reached (or raises), so the count is exact.
Re-running removes only the props this script made in the same collection.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/scatter_props.py", init_globals={"ARGS": {
        "target": "SM_Crate", "count": 8, "kinds": ["box", "barrel", "pallet"]}})["result"]

ARGS:
    target      (str)   object to dress around (required)
    count       (int)   number of props (default 8)
    kinds       (list)  any of box, box_small, barrel, pallet (default all)
    clusters    (int)   number of story clusters (default 3)
    min_dist    (float) min distance from target bbox, metres (default 0.4)
    max_dist    (float) max cluster distance from target centre (default 3.5)
    ground      (str)   mesh to raycast onto (default: any visible mesh below)
    collection  (str)   default "COL_SetDressing"
    seed        (int)   default 0
"""
import json
import math
import random
import sys

import bmesh
import bpy
from mathutils import Vector

# kind: (size x, y, z in metres, primitive, colour)
KINDS = {
    "box": ((0.6, 0.6, 0.6), "cube", (0.45, 0.32, 0.2)),
    "box_small": ((0.4, 0.35, 0.3), "cube", (0.5, 0.38, 0.24)),
    "barrel": ((0.6, 0.6, 0.9), "cylinder", (0.25, 0.3, 0.33)),
    "pallet": ((1.2, 0.8, 0.15), "cube", (0.55, 0.42, 0.28)),
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _mesh(kind):
    name = f"ME_Prop_{kind}"
    me = bpy.data.meshes.get(name)
    if me:
        return me
    (sx, sy, sz), prim, color = KINDS[kind]
    bm = bmesh.new()
    if prim == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
    else:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5, radius2=0.5, depth=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, sz / 2), verts=bm.verts)  # pivot on the floor
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    mat = bpy.data.materials.get(f"MAT_Prop_{kind}") or bpy.data.materials.new(f"MAT_Prop_{kind}")
    mat.diffuse_color = (*color, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
    me.materials.append(mat)
    return me


def _ground_z(xy, ground, top):
    dg = bpy.context.evaluated_depsgraph_get()
    origin = Vector((xy.x, xy.y, top + 50.0))
    if ground:
        inv = ground.matrix_world.inverted()
        ok, loc, _n, _i = ground.evaluated_get(dg).ray_cast(inv @ origin, inv.to_3x3() @ Vector((0, 0, -1)))
        return (ground.matrix_world @ loc).z if ok else None
    ok, loc, _n, _i, _o, _m = bpy.context.scene.ray_cast(dg, origin, Vector((0, 0, -1)))
    return loc.z if ok else None


def main(target, count=8, kinds=None, clusters=3, min_dist=0.4, max_dist=3.5, ground=None,
         collection="COL_SetDressing", seed=0):
    tgt = bpy.data.objects.get(target)
    if tgt is None:
        raise ValueError(f"target not found: {target}")
    gnd = bpy.data.objects.get(ground) if ground else None
    kinds = kinds or list(KINDS)
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise ValueError(f"unknown kinds {bad}; use {list(KINDS)}")
    rng = random.Random(seed)

    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection)
        bpy.context.scene.collection.children.link(col)
    for o in [o for o in col.objects if o.name.startswith("PROP_") and o.get("set_dressing")]:
        bpy.data.objects.remove(o)

    corners = [tgt.matrix_world @ Vector(c) for c in tgt.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    centre = (lo + hi) / 2
    # Hide the props being built from raycasts by excluding them while we place
    placed = []  # (xy, radius)
    keep_out = max(hi.x - lo.x, hi.y - lo.y) / 2 + min_dist

    cluster_centres = []
    for c in range(clusters):
        ang = 2 * math.pi * c / clusters + rng.uniform(-0.4, 0.4)
        d = rng.uniform(keep_out + 0.8, max(keep_out + 0.9, max_dist))
        cluster_centres.append(Vector((centre.x + math.cos(ang) * d, centre.y + math.sin(ang) * d)))

    made = []
    attempts = 0
    while len(made) < count:
        attempts += 1
        if attempts > count * 200:
            raise RuntimeError(f"could only place {len(made)}/{count} props; raise max_dist or lower count")
        ci = len(made) % clusters
        kind = kinds[(len(made) + ci) % len(kinds)]
        size = KINDS[kind][0]
        radius = math.hypot(size[0], size[1]) / 2
        cc = cluster_centres[ci]
        spread = 0.6 + 0.15 * attempts / count
        xy = Vector((cc.x + rng.uniform(-spread, spread), cc.y + rng.uniform(-spread, spread)))
        # outside the target bbox (expanded by prop radius + min_dist)
        if lo.x - radius - min_dist < xy.x < hi.x + radius + min_dist and \
           lo.y - radius - min_dist < xy.y < hi.y + radius + min_dist:
            continue
        if any((xy - p).length < radius + r + 0.05 for p, r in placed):
            continue
        z = _ground_z(xy, gnd, hi.z)
        if z is None:
            continue
        obj = bpy.data.objects.new(f"PROP_{'ABCDEFGH'[ci]}_{kind}_{len(made):02d}", _mesh(kind))
        obj["set_dressing"] = True
        obj.location = (xy.x, xy.y, z)
        obj.rotation_euler.z = rng.uniform(0, 2 * math.pi)
        col.objects.link(obj)
        placed.append((xy, radius))
        made.append({"name": obj.name, "kind": kind, "cluster": ci,
                     "loc": [round(v, 3) for v in obj.location]})
    return {"count": len(made), "collection": col.name, "props": made,
            "shared_meshes": len({m["kind"] for m in made})}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
