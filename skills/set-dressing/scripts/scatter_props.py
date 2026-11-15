"""Place a requested number of small props (boxes, barrels, pallets) in narrative clusters
around a target object. Props sit on the ground via raycast, never intersect the target's
bounding box or each other, share one mesh per kind, and are named PROP_<Cluster>_<kind>_NN.
Placement retries until the requested count is reached (or raises), so the count is exact.
Re-running removes only the props this script made in the same collection. A mesh named
ME_Prop_<kind> that lacks this script's tag is refused before anything is removed (rename or delete it by hand);
meshes that carry the tag are rebuilt in place when the UV layout is out of date.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/scatter_props.py", init_globals={"ARGS": {
        "target": "SM_Crate", "count": 8, "kinds": ["box", "barrel", "pallet"]}})["result"]

ARGS:
    target      (str)   object to dress around (required)
    count       (int)   number of props (default 8)
    kinds       (list)  any of box, box_small, barrel, pallet (default all)
    clusters    (int)   number of story clusters (default 3)
    min_dist    (float) min distance from target bbox, metres (default 0.4)
    max_dist    (float) max horizontal (XY) distance from the target bbox centre to any prop origin, metres
                        (default 3.5); enforced per prop, so no prop lands farther out
    ground      (str)   mesh to raycast onto (default: any visible mesh below)
    collection  (str)   default "COL_SetDressing"
    seed        (int)   default 0
    min_spacing_m (float) minimum horizontal (XY) distance between any two prop origins, metres (default none)
    max_slope_deg (float) steepest ground slope a prop may stand on, degrees from level, 0-90 (default none)
    height_range_m (list) [lowest, highest] allowed world Z of a prop's origin (its ground point), metres
                        (default none)

Limits are honoured while placing, then measured again on the props actually placed (slope by a fresh ray
cast with the props hidden for the measurement, spacing and height from the finished objects) and compared with each
limit with a 1e-6 m / 1e-4 degree tolerance. The result has "measured" (min_spacing_m, max_slope_deg,
height_range_m of the placed props; null when there is nothing to measure), and when any limit was given
"limits" (limit, measured, ok per limit) and "verdict": FAIL if any limit is violated, else PASS.
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


def _shelf(sizes, scale, gap):
    """Shelf-pack (w, h) boxes (metres * scale) into the unit square with a gap; positions or None."""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][1])
    pos, x, y, row_h = {}, gap, gap, 0.0
    for i in order:
        w, h = sizes[i][0] * scale, sizes[i][1] * scale
        if x + w + gap > 1.0:
            x, y, row_h = gap, y + row_h + gap, 0.0
        if x + w + gap > 1.0 or y + h + gap > 1.0:
            return None
        pos[i] = (x, y)
        x += w + gap
        row_h = max(row_h, h)
    return pos


def _island_uvs(bm, gap=0.004):
    """Every face is its own island, laid flat in its own plane (no stretch) and packed with a margin
    at one shared scale, so the props have no overlapping or collapsed UVs."""
    layer = bm.loops.layers.uv.new("UVMap")
    flat = []
    for f in bm.faces:
        n = f.normal
        ref = Vector((1, 0, 0)) if abs(n.z) > 0.9 else Vector((0, 0, 1))
        t = (ref - n * ref.dot(n)).normalized()
        b = n.cross(t)
        pts = [(l.vert.co.dot(t), l.vert.co.dot(b)) for l in f.loops]
        x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
        pts = [(x - x0, y - y0) for x, y in pts]
        flat.append((pts, (max(p[0] for p in pts), max(p[1] for p in pts))))
    sizes = [s for _p, s in flat]
    lo, hi = 0.0, 1.0 / max(max(w, h) for w, h in sizes)
    for _ in range(40):
        mid = (lo + hi) / 2
        if _shelf(sizes, mid, gap) is not None:
            lo = mid
        else:
            hi = mid
    scale = lo
    pos = _shelf(sizes, scale, gap)
    for i, f in enumerate(bm.faces):
        ox, oy = pos[i]
        for l, (x, y) in zip(f.loops, flat[i][0]):
            l[layer].uv = (ox + x * scale, oy + y * scale)


UV_VERSION = 1  # bump when the prop UV layout changes; older script-made meshes are rebuilt


def _shape(kind):
    (sx, sy, sz), prim, _color = KINDS[kind]
    bm = bmesh.new()
    if prim == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
    else:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5, radius2=0.5, depth=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, sz / 2), verts=bm.verts)  # pivot on the floor
    return bm


def _preflight(kind):
    """Refuse, before anything is changed, a mesh named ME_Prop_<kind> that does not carry this script's tag.
    The script never adopts, rewrites or deletes a mesh it did not make."""
    me = bpy.data.meshes.get(f"ME_Prop_{kind}")
    if me is not None and not me.get("set_dressing"):
        raise ValueError(f"mesh {me.name!r} already exists and this script did not make it; rename it, or delete "
                         "it by hand (the script never deletes it), then run again")


def _mesh(kind):
    name = f"ME_Prop_{kind}"
    me = bpy.data.meshes.get(name)
    if me is not None and me.get("set_dressing_uv") == UV_VERSION and len(me.uv_layers):
        return me
    _preflight(kind)
    bm = _shape(kind)
    _island_uvs(bm)
    if me is None:
        me = bpy.data.meshes.new(name)
    else:
        me.clear_geometry()  # our own older mesh: rebuild in place so existing props keep their data
        for layer in list(me.uv_layers):
            me.uv_layers.remove(layer)
    bm.to_mesh(me)
    bm.free()
    me["set_dressing"] = True
    me["set_dressing_uv"] = UV_VERSION
    color = KINDS[kind][2]
    mat = bpy.data.materials.get(f"MAT_Prop_{kind}") or bpy.data.materials.new(f"MAT_Prop_{kind}")
    mat.diffuse_color = (*color, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
    if not len(me.materials):
        me.materials.append(mat)
    return me


def _ground_hit(xy, ground, top):
    """(z, world unit normal) of the ground below xy, or None."""
    dg = bpy.context.evaluated_depsgraph_get()
    origin = Vector((xy.x, xy.y, top + 50.0))
    if ground:
        mw = ground.matrix_world
        inv = mw.inverted()
        ok, loc, nrm, _i = ground.evaluated_get(dg).ray_cast(inv @ origin, inv.to_3x3() @ Vector((0, 0, -1)))
        if not ok:
            return None
        nrm = (inv.to_3x3().transposed() @ nrm).normalized()
        return (mw @ loc).z, nrm
    ok, loc, nrm, _i, _o, _m = bpy.context.scene.ray_cast(dg, origin, Vector((0, 0, -1)))
    return (loc.z, nrm.normalized()) if ok else None


def _slope_deg(nrm):
    return math.degrees(math.acos(max(-1.0, min(1.0, abs(nrm.z)))))


def _measure(objs, gnd, top):
    """Measured spacing, slope and height of the placed prop objects. Slope is a fresh ray cast at each prop
    with the props hidden (restored afterwards)."""
    out = {"min_spacing_m": None, "max_slope_deg": None, "height_range_m": None}
    if not objs:
        return out
    pts = [o.location.xy.copy() for o in objs]
    if len(pts) > 1:
        out["min_spacing_m"] = min((a - b).length for i, a in enumerate(pts) for b in pts[:i])
    zs = [o.location.z for o in objs]
    out["height_range_m"] = [min(zs), max(zs)]
    hidden = [(o, o.hide_viewport) for o in objs]
    try:
        for o in objs:
            o.hide_viewport = True
        bpy.context.view_layer.update()
        slopes = []
        for o in objs:
            hit = _ground_hit(o.location.xy, gnd, top)
            if hit is not None:
                slopes.append(_slope_deg(hit[1]))
        out["max_slope_deg"] = max(slopes) if slopes else None
    finally:
        for o, h in hidden:
            o.hide_viewport = h
        bpy.context.view_layer.update()
    return out


def _check_limits(limits, measured):
    """limits: {name: value}; returns ({name: {limit, measured, ok}}, verdict). An unmeasurable limit FAILs."""
    res = {}
    for name, lim in limits.items():
        m = measured.get(name)
        if name == "min_spacing_m":
            ok = m is None or m >= lim - 1e-6   # fewer than two props: nothing to violate
        elif name == "max_slope_deg":
            ok = m is not None and m <= lim + 1e-4
        else:
            ok = m is not None and m[0] >= lim[0] - 1e-6 and m[1] <= lim[1] + 1e-6
        res[name] = {"limit": lim, "measured": m, "ok": bool(ok)}
    return res, ("PASS" if all(v["ok"] for v in res.values()) else "FAIL")


def main(target, count=8, kinds=None, clusters=3, min_dist=0.4, max_dist=3.5, ground=None,
         collection="COL_SetDressing", seed=0, min_spacing_m=None, max_slope_deg=None, height_range_m=None):
    tgt = bpy.data.objects.get(target)
    if tgt is None:
        raise ValueError(f"target not found: {target}")
    gnd = bpy.data.objects.get(ground) if ground else None
    kinds = kinds or list(KINDS)
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise ValueError(f"unknown kinds {bad}; use {list(KINDS)}")
    limits = {}
    if min_spacing_m is not None:
        if not min_spacing_m >= 0:
            raise ValueError("min_spacing_m must be >= 0")
        limits["min_spacing_m"] = float(min_spacing_m)
    if max_slope_deg is not None:
        if not 0 <= max_slope_deg <= 90:
            raise ValueError("max_slope_deg must be between 0 and 90")
        limits["max_slope_deg"] = float(max_slope_deg)
    if height_range_m is not None:
        if len(height_range_m) != 2 or not height_range_m[0] <= height_range_m[1]:
            raise ValueError("height_range_m must be [lowest, highest] with lowest <= highest")
        limits["height_range_m"] = [float(height_range_m[0]), float(height_range_m[1])]
    for k in kinds:
        _preflight(k)  # every mesh is checked before any earlier prop is removed
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
        reach = max(max_dist - 0.3, 0.0)  # cluster centres stay inside max_dist, leaving room for the spread
        d = min(d, reach)
        if keep_out <= reach:
            d = max(d, keep_out)
        cluster_centres.append(Vector((centre.x + math.cos(ang) * d, centre.y + math.sin(ang) * d)))

    made = []
    attempts = 0
    fails = [0] * clusters  # consecutive failures per cluster; many -> uniform annulus fallback
    c2 = Vector((centre.x, centre.y))
    while len(made) < count:
        attempts += 1
        if attempts > count * 600:
            raise RuntimeError(f"could only place {len(made)}/{count} props; raise max_dist or lower count")
        ci = len(made) % clusters
        kind = kinds[(len(made) + ci) % len(kinds)]
        size = KINDS[kind][0]
        radius = math.hypot(size[0], size[1]) / 2
        cc = cluster_centres[ci]
        spread = min(1.2, 0.6 + 0.15 * attempts / count)
        if fails[ci] > 40:
            # fallback: uniform sample over the annulus between the keep-out ring and max_dist
            r_in, r_out = min(keep_out, max_dist), max_dist
            rr = math.sqrt(rng.uniform(r_in * r_in, r_out * r_out))
            th = rng.uniform(0, 2 * math.pi)
            xy = Vector((centre.x + math.cos(th) * rr, centre.y + math.sin(th) * rr))
        else:
            xy = Vector((cc.x + rng.uniform(-spread, spread), cc.y + rng.uniform(-spread, spread)))
        off = xy - c2
        if off.length > max_dist:  # pull back radially instead of rejecting
            xy = c2 + off.normalized() * max(max_dist - radius, 0.0)
        # outside the target bbox (expanded by prop radius + min_dist)
        if lo.x - radius - min_dist < xy.x < hi.x + radius + min_dist and \
           lo.y - radius - min_dist < xy.y < hi.y + radius + min_dist:
            fails[ci] += 1
            continue
        if any((xy - p).length < radius + r + 0.05 for p, r in placed):
            fails[ci] += 1
            continue
        hit = _ground_hit(xy, gnd, hi.z)
        if hit is None:
            fails[ci] += 1
            continue
        z, nrm = hit
        if (max_slope_deg is not None and _slope_deg(nrm) > max_slope_deg) or \
           (height_range_m is not None and not height_range_m[0] <= z <= height_range_m[1]) or \
           (min_spacing_m is not None and any((xy - p).length < min_spacing_m for p, _r in placed)):
            fails[ci] += 1
            continue
        obj = bpy.data.objects.new(f"PROP_{'ABCDEFGH'[ci]}_{kind}_{len(made):02d}", _mesh(kind))
        obj["set_dressing"] = True
        obj.location = (xy.x, xy.y, z)
        obj.rotation_euler.z = rng.uniform(0, 2 * math.pi)
        col.objects.link(obj)
        placed.append((xy, radius))
        fails[ci] = 0
        made.append({"name": obj.name, "kind": kind, "cluster": ci,
                     "loc": [round(v, 3) for v in obj.location]})
    measured = _measure([bpy.data.objects[m["name"]] for m in made], gnd, hi.z)
    result = {"count": len(made), "collection": col.name, "props": made,
              "shared_meshes": len({m["kind"] for m in made}), "max_dist": max_dist, "measured": measured,
              "verdict": "PASS"}
    if limits:
        result["limits"], result["verdict"] = _check_limits(limits, measured)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
