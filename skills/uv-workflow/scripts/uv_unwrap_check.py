"""Unwrap (optional) and measure UVs per object: islands, collapsed faces, overlap, union coverage
per UDIM tile, per-island texel density spread, stretch, out-of-range loops. Measure only unless
`unwrap=True` or `lightmap=True`: a mesh with no UV channel is reported as an error and left
unchanged otherwise (unwrap creates "UVMap"; lightmap=True creates the missing channels).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/uv_unwrap_check.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "unwrap": True, "texture_px": 2048, "target_px_per_m": 512}})["result"]

ARGS:
    objects          (list[str], required)
    unwrap           (bool)  unwrap first (default False = measure only). Needs/creates a "UVMap" channel
    method           (str)   smart | seams | min_stretch (default smart). seams/min_stretch use the marked
                             seams (see seams_from_angle) and then pack the islands
    angle_deg        (float) smart project angle limit (default 66)
    margin_px        (float) gap between islands in pixels at texture_px (default 4); applied as an exact
                             fraction of the UV space (margin_method FRACTION)
    seams_from_angle (float) before a seams/min_stretch unwrap, mark seams on edges sharper than this many
                             degrees (default None = keep the seams already marked)
    texture_px       (int)   texture resolution used for density (default 2048)
    target_px_per_m  (float) target texel density in pixels per metre (lengths are converted with the
                             scene's unit scale_length, so surface_m2 is real m2); flags objects outside +/-25 %
    uv_layer         (str|int) channel to measure, by name or index (default the active render channel).
                             A missing channel is an error. The result names the channel measured
    allow_overlap    (bool)  the layout is declared mirrored or stacked: skip the overlap rule (default False)
    make_single_user (bool)  unwrap/lightmap on a mesh shared with other objects is refused (it would change
                             them too); True gives this object its own copy first ("made_single_user")
    lightmap         (bool)  also build a second, non-overlapping "UVMap_Lightmap" channel with Lightmap
                             Pack and measure it under the lightmap rules: result key "lightmap" when another
                             channel is the one measured, measured directly in the object entry when the lightmap
                             channel is the one measured (uv_layer names it, or it is the only channel). The first
                             channel stays the active render UV. Rerunning repacks the same channel
    result_path      (str)   write the result (plus run_id) as JSON here, atomically, on success
    run_id           (str)   copied into the result and the file

Verdicts: each check is PASS, WARN, FAIL or NOT_CHECKED. Unique-bake and lightmap channels FAIL on any
collapsed face (UV area < 1e-12) or overlap (interiors of two UV triangles intersect; shared edges and
corners do not count) and WARN on texel-density spread > 1.3 (max/min over islands), union coverage < 0.75
(per tile, averaged over occupied tiles) or stretch p95 > 1.2 (triangle UV/3D singular-value ratio).
`allow_overlap` skips only the overlap rule, and never for the lightmap channel. Object verdict is FAIL if any
check FAILs, else WARN if any WARNs or is NOT_CHECKED, else PASS; overall is the worst object.
Coverage is exact along U and sampled along V: 512 scanline rows per tile at jittered (stratified, seeded)
positions, so it is an unbiased estimate (typically within about 1 %), not a worst-case bound.
A non-finite UV (NaN/inf) fails the `uv_finite` check; its faces are excluded from the other measurements
and the result never contains NaN (null instead).

Reading UVs yourself in Blender 5.x: `mesh.uv_layers[i].uv[k].vector` (the per-loop value is a
Float2AttributeValue with `.vector`, not `.uv`), or `loop[bm.loops.layers.uv.active].uv` in bmesh.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np

LIGHTMAP_NAME = "UVMap_Lightmap"
COLLAPSED_AREA = 1e-12
SAT_EPS = 1e-7
SPREAD_WARN, COVERAGE_WARN, STRETCH_WARN = 1.3, 0.75, 1.2
ROWS = 512
PAIR_CAP = 3_000_000
METHODS = ("smart", "seams", "min_stretch")


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


# ----------------------------------------------------------------------------- unwrap

def _get_selection(me):
    out = []
    for coll in (me.vertices, me.edges, me.polygons):
        arr = np.zeros(len(coll), np.bool_)
        coll.foreach_get("select", arr)
        out.append(arr)
    return out


def _set_selection(me, saved):
    for coll, arr in zip((me.vertices, me.edges, me.polygons), saved):
        coll.foreach_set("select", arr)
    me.update()


def _edit_ops(obj, fn):
    """Run fn() in Edit Mode on this one object (entered from Object Mode). Afterwards, also when the
    operator fails: Object Mode, the object's active/selected state and its mesh selection as they were."""
    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    selected = [o for o in view_layer.objects if o.select_get()]
    saved = _get_selection(obj.data)
    try:
        for o in selected:
            o.select_set(False)  # Edit Mode would otherwise take every selected object along
        obj.select_set(True)
        view_layer.objects.active = obj
        with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj],
                                       selected_editable_objects=[obj]):
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            result = fn()
            if "FINISHED" not in result:
                raise RuntimeError(f"UV operator returned {sorted(result)} on {obj.name}")
    finally:
        with bpy.context.temp_override(active_object=obj, object=obj):
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        _set_selection(obj.data, saved)
        if obj.name in view_layer.objects:
            obj.select_set(False)
        for o in selected:
            o.select_set(True)
        view_layer.objects.active = prev_active
    return result


def _mark_seams(obj, angle_deg):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    limit = math.radians(angle_deg)
    marked = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            e.seam = e.calc_face_angle(0.0) > limit
        else:
            e.seam = True
        marked += e.seam
    bm.to_mesh(obj.data)
    bm.free()
    return marked


def _unwrap(obj, method, angle_deg, texture_px, margin_px, seams_from_angle):
    gap = margin_px / texture_px
    margin = gap / 2  # FRACTION margins are per island side: two neighbours leave twice this between them
    info = {"method": method, "island_margin": round(gap, 5)}
    if method == "smart":
        _edit_ops(obj, lambda: bpy.ops.uv.smart_project(
            angle_limit=math.radians(angle_deg), island_margin=margin, margin_method="FRACTION", scale_to_bounds=False))
        return info
    if seams_from_angle is not None:
        info["seams_marked"] = _mark_seams(obj, seams_from_angle)
    kind = "ANGLE_BASED" if method == "seams" else "MINIMUM_STRETCH"

    def run():
        res = bpy.ops.uv.unwrap(method=kind, margin=margin, margin_method="FRACTION")
        if "FINISHED" not in res:
            return res
        return bpy.ops.uv.pack_islands(margin=margin, margin_method="FRACTION", rotate=True)
    _edit_ops(obj, run)
    return info


def _lightmap(obj):
    me = obj.data
    if LIGHTMAP_NAME not in me.uv_layers:
        me.uv_layers.new(name=LIGHTMAP_NAME)
    # Names, not layer references: references go stale after an edit-mode round trip.
    others = [l.name for l in me.uv_layers if l.name != LIGHTMAP_NAME]
    render = next((l.name for l in me.uv_layers if l.active_render and l.name != LIGHTMAP_NAME),
                  others[0] if others else LIGHTMAP_NAME)  # lightmap as the only channel stays the render UV
    me.uv_layers.active = me.uv_layers[LIGHTMAP_NAME]
    try:
        _edit_ops(obj, lambda: bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True,
                                                        PREF_MARGIN_DIV=0.2))
    finally:
        me.uv_layers.active = me.uv_layers[render]
        me.uv_layers[render].active_render = True
    return LIGHTMAP_NAME


# ----------------------------------------------------------------------------- measuring

def _resolve_layer(me, uv_layer):
    """Return the UV layer named/indexed, or the active render one. None if missing."""
    layers = me.uv_layers
    if uv_layer is None:
        return next((l for l in layers if l.active_render), layers[0] if len(layers) else None)
    if isinstance(uv_layer, int) and not isinstance(uv_layer, bool):
        return layers[uv_layer] if -len(layers) <= uv_layer < len(layers) else None
    return layers.get(str(uv_layer))


def _metres_per_unit():
    """Metres per Blender unit (scene.unit_settings.scale_length); 1.0 when unset or not positive."""
    k = float(bpy.context.scene.unit_settings.scale_length)
    return k if math.isfinite(k) and k > 0 else 1.0


def _tri_arrays(obj, layer):
    """World-space 3D triangle corners (T,3,3) in metres, UV corners (T,3,2), polygon index per triangle,
    plus per-loop data needed for islands."""
    me = obj.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    nl = len(me.loops)
    nv = len(me.vertices)
    tri_loops = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)
    tri_poly = np.empty(nt, np.int32)
    me.loop_triangles.foreach_get("polygon_index", tri_poly)
    co = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    m = np.array(obj.matrix_world, dtype=np.float64)
    co = (co @ m[:3, :3].T + m[:3, 3]) * _metres_per_unit()
    loop_vert = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", loop_vert)
    loop_edge = np.empty(nl, np.int32)
    me.loops.foreach_get("edge_index", loop_edge)
    uv = np.empty(nl * 2, np.float32)
    layer.uv.foreach_get("vector", uv)
    uv = uv.reshape(-1, 2).astype(np.float64)
    tri_loops = tri_loops.reshape(-1, 3)
    return {
        "p3": co[loop_vert[tri_loops]], "uv": uv[tri_loops], "poly": tri_poly,
        "loop_uv": uv, "loop_vert": loop_vert, "loop_edge": loop_edge, "n_poly": len(me.polygons),
        "poly_start": _poly_arr(me, "loop_start"), "poly_total": _poly_arr(me, "loop_total"),
    }


def _poly_arr(me, attr):
    a = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get(attr, a)
    return a


def _tri_area_uv(uvt):
    d1, d2 = uvt[:, 1] - uvt[:, 0], uvt[:, 2] - uvt[:, 0]
    return np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2


def _tri_area_3d(p3):
    return np.linalg.norm(np.cross(p3[:, 1] - p3[:, 0], p3[:, 2] - p3[:, 0]), axis=1) / 2


def _islands(d):
    """Island id per polygon. Two faces are one island when they share an edge and agree on the UV of both
    edge ends."""
    n_poly = d["n_poly"]
    parent = list(range(n_poly))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    start, total = d["poly_start"], d["poly_total"]
    nl = len(d["loop_uv"])
    if nl == 0:
        return np.zeros(0, np.int32)
    loop_poly = np.repeat(np.arange(n_poly), total)
    nxt = np.arange(nl) + 1
    last = start + total - 1
    nxt[last] = start
    order = np.argsort(d["loop_edge"], kind="stable")
    e = d["loop_edge"][order]
    same = e[1:] == e[:-1]
    la, lb = order[:-1][same], order[1:][same]
    uv, vert = d["loop_uv"], d["loop_vert"]
    tol = 1e-6
    fwd = vert[la] == vert[lb]
    match_f = (np.abs(uv[la] - uv[lb]).max(axis=1) < tol) & (np.abs(uv[nxt[la]] - uv[nxt[lb]]).max(axis=1) < tol)
    match_r = (np.abs(uv[la] - uv[nxt[lb]]).max(axis=1) < tol) & (np.abs(uv[nxt[la]] - uv[lb]).max(axis=1) < tol)
    joined = np.where(fwd, match_f, match_r)
    for a, b in zip(loop_poly[la[joined]].tolist(), loop_poly[lb[joined]].tolist()):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(n_poly)], np.int64)
    _, ids = np.unique(roots, return_inverse=True)
    return ids.astype(np.int32)


def _stretch(p3, uvt):
    """Per-triangle anisotropy: ratio of the singular values of the 3D -> UV Jacobian (1 = conformal)."""
    e1, e2 = p3[:, 1] - p3[:, 0], p3[:, 2] - p3[:, 0]
    l1 = np.linalg.norm(e1, axis=1)
    ok = l1 > 1e-12
    x = np.zeros_like(e1)
    x[ok] = e1[ok] / l1[ok, None]
    e2x = (e2 * x).sum(axis=1)
    yv = e2 - e2x[:, None] * x
    l2 = np.linalg.norm(yv, axis=1)
    ok &= l2 > 1e-12
    q1, q2 = uvt[:, 1] - uvt[:, 0], uvt[:, 2] - uvt[:, 0]
    with np.errstate(all="ignore"):
        # P = [[l1, e2x], [0, l2]] columns are the local 3D edges; J = Q P^-1
        inv00, inv01, inv11 = 1 / l1, -e2x / (l1 * l2), 1 / l2
        a = q1[:, 0] * inv00
        b = q1[:, 0] * inv01 + q2[:, 0] * inv11
        c = q1[:, 1] * inv00
        dd = q1[:, 1] * inv01 + q2[:, 1] * inv11
        E, F, G, H = (a + dd) / 2, (a - dd) / 2, (c + b) / 2, (c - b) / 2
        s_big = np.hypot(E, H) + np.hypot(F, G)
        s_small = np.abs(np.hypot(E, H) - np.hypot(F, G))
        ratio = s_big / np.maximum(s_small, 1e-12)
    return ratio[ok & np.isfinite(ratio)]


def _scan(tris, rows=ROWS):
    """(union length, summed length) averaged over `rows` jittered scanlines across the unit tile, for
    triangles (T,3,2) in tile-local UV. Spans are exact along U; the union is merged per row."""
    union_sum = total_sum = 0.0
    if len(tris) == 0:
        return 0.0, 0.0
    ys = (np.arange(rows) + np.random.default_rng(12345).random(rows)) / rows  # one stratified sample per row
    ymin, ymax = tris[:, :, 1].min(axis=1), tris[:, :, 1].max(axis=1)
    j0 = np.clip(np.floor(ymin * rows), 0, rows - 1).astype(np.int64)
    j1 = np.clip(np.floor(ymax * rows), 0, rows - 1).astype(np.int64)
    r0 = 0
    while r0 < rows:
        # grow the row block while the entry count stays moderate
        r1 = r0
        while r1 < rows:
            r1 = min(rows, r1 + 32)
            sel = np.nonzero((j1 >= r0) & (j0 < r1))[0]
            if int((np.minimum(j1[sel], r1 - 1) - np.maximum(j0[sel], r0) + 1).sum()) > 1_500_000:
                break
        reps = np.minimum(j1[sel], r1 - 1) - np.maximum(j0[sel], r0) + 1
        t = np.repeat(sel, reps)
        j = np.repeat(np.maximum(j0[sel], r0), reps) + (np.arange(len(t)) - np.repeat(np.cumsum(reps) - reps, reps))
        py = ys[j]
        xlo = np.full(len(t), np.inf)
        xhi = np.full(len(t), -np.inf)
        for k in range(3):
            A, B = tris[t, k], tris[t, (k + 1) % 3]
            dy = B[:, 1] - A[:, 1]
            ok = (np.minimum(A[:, 1], B[:, 1]) <= py) & (py < np.maximum(A[:, 1], B[:, 1])) & (dy != 0)
            with np.errstate(all="ignore"):
                x = A[:, 0] + (py - A[:, 1]) * (B[:, 0] - A[:, 0]) / dy
            xlo = np.where(ok, np.minimum(xlo, x), xlo)
            xhi = np.where(ok, np.maximum(xhi, x), xhi)
        good = np.isfinite(xlo) & np.isfinite(xhi)
        xlo, xhi, jj = np.clip(xlo[good], 0, 1), np.clip(xhi[good], 0, 1), j[good].astype(np.float64)
        keep = xhi > xlo
        xlo, xhi, jj = xlo[keep], xhi[keep], jj[keep]
        if len(xlo):
            order = np.lexsort((xlo, jj))
            xlo, xhi, jj = xlo[order], xhi[order], jj[order]
            kl, kh = jj * 4 + xlo, jj * 4 + xhi
            prev = np.concatenate(([-1.0], np.maximum.accumulate(kh)[:-1]))
            union_sum += float(np.maximum(0.0, kh - np.maximum(kl, prev)).sum())
            total_sum += float((xhi - xlo).sum())
        r0 = r1
    return union_sum / rows, total_sum / rows


def _tile_of(uvt):
    c = uvt.mean(axis=1)
    return np.floor(c[:, 0]).astype(np.int64), np.floor(c[:, 1]).astype(np.int64)


def _clipped_area(tri, u, v):
    """Area of the triangle (3,2) inside the unit tile [u,u+1] x [v,v+1] (Sutherland-Hodgman)."""
    poly = [(float(x), float(y)) for x, y in tri]
    for axis, bound, keep_ge in ((0, u, True), (0, u + 1, False), (1, v, True), (1, v + 1, False)):
        out = []
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            ina = a[axis] >= bound if keep_ge else a[axis] <= bound
            inb = b[axis] >= bound if keep_ge else b[axis] <= bound
            if ina != inb:
                t = (bound - a[axis]) / (b[axis] - a[axis])
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            if inb:
                out.append(b)
        poly = out
        if not poly:
            return 0.0
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _coverage(uvt):
    """({tile: union coverage}, overlap area = summed minus union area).
    A triangle is rasterised into every tile its bounding box touches and clipped to each."""
    lo = np.floor(uvt.min(axis=1)).astype(np.int64)
    hi = np.floor(uvt.max(axis=1) - 1e-9).astype(np.int64)
    hi = np.maximum(hi, lo)
    tiles = {}
    for dx in range(int((hi[:, 0] - lo[:, 0]).max()) + 1):
        for dy in range(int((hi[:, 1] - lo[:, 1]).max()) + 1):
            tu, tv = lo[:, 0] + dx, lo[:, 1] + dy
            ok = (tu <= hi[:, 0]) & (tv <= hi[:, 1])
            for u in np.unique(tu[ok]):
                for v in np.unique(tv[ok & (tu == u)]):
                    tiles.setdefault((int(u), int(v)), []).append(np.nonzero(ok & (tu == u) & (tv == v))[0])
    cov, overlap_area = {}, 0.0
    for (u, v), parts in sorted(tiles.items()):
        idx = np.concatenate(parts)
        # Occupancy is exact: a triangle whose box spans several tiles must have clipped area > 0 in this one.
        # (the raster below only measures the fraction, and cannot see a strip narrower than one sample)
        multi = (hi[idx, 0] > lo[idx, 0]) | (hi[idx, 1] > lo[idx, 1])
        keep = np.ones(len(idx), bool)
        for k in np.nonzero(multi)[0]:
            keep[k] = _clipped_area(uvt[idx[k]], u, v) > 1e-12
        if not keep.any():
            continue
        idx = idx[keep]
        union, total = _scan(uvt[idx] - np.array([u, v], np.float64))
        cov[1001 + u + 10 * v] = union
        overlap_area += max(0.0, total - union)
    return cov, overlap_area


def _sat_overlap(A, B):
    """True where triangle interiors intersect (touching edges/corners do not). A, B: (P,3,2)."""
    hit = np.ones(len(A), bool)
    for T in (A, B):
        for k in range(3):
            e = T[:, (k + 1) % 3] - T[:, k]
            n = np.stack([-e[:, 1], e[:, 0]], axis=1)
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
            pa = (A * n[:, None, :]).sum(axis=2)
            pb = (B * n[:, None, :]).sum(axis=2)
            sep = (pa.max(axis=1) <= pb.min(axis=1) + SAT_EPS) | (pb.max(axis=1) <= pa.min(axis=1) + SAT_EPS)
            hit &= ~sep
    return hit


def _overlap_pairs(uvt):
    """Count overlapping triangle pairs with a grid broad phase. Returns (pairs, truncated)."""
    t = len(uvt)
    if t < 2:
        return 0, False
    bmin, bmax = uvt.min(axis=1), uvt.max(axis=1)
    ext = (bmax - bmin).max(axis=1)
    cs = float(np.clip(np.mean(ext) * 1.5, 1.0 / 1024, 1.0))
    c0 = np.floor(bmin / cs).astype(np.int64)
    c1 = np.floor(bmax / cs).astype(np.int64)
    nx, ny = c1[:, 0] - c0[:, 0] + 1, c1[:, 1] - c0[:, 1] + 1
    cnt = nx * ny
    big = cnt > 256
    ids = np.nonzero(~big)[0]
    reps = cnt[ids]
    tri_rep = np.repeat(ids, reps)
    off = np.arange(len(tri_rep)) - np.repeat(np.cumsum(reps) - reps, reps)
    nxr = np.repeat(nx[ids], reps)
    cx = c0[tri_rep, 0] + off % nxr
    cy = c0[tri_rep, 1] + off // nxr
    cx -= cx.min() if len(cx) else 0
    cy -= cy.min() if len(cy) else 0
    key = cx * (int(cy.max()) + 2 if len(cy) else 1) + cy
    order = np.argsort(key, kind="stable")
    key, tri_rep = key[order], tri_rep[order]
    bounds = np.nonzero(np.diff(key))[0] + 1
    starts = np.concatenate(([0], bounds))
    ends = np.concatenate((bounds, [len(key)]))
    codes, budget, truncated = [], PAIR_CAP, False
    for s, e in zip(starts.tolist(), ends.tolist()):
        g = e - s
        if g < 2:
            continue
        members = tri_rep[s:e]
        if g * (g - 1) // 2 <= max(budget, 0):
            a, b = np.triu_indices(g, 1)
            pa, pb = members[a], members[b]
            budget -= len(a)
        else:
            truncated = True
            k = max(budget, 0) // g
            if k < 1:
                continue
            pa = np.concatenate([members[:-d] for d in range(1, min(k, g - 1) + 1)])
            pb = np.concatenate([members[d:] for d in range(1, min(k, g - 1) + 1)])
            budget -= len(pa)
        lo_i, hi_i = np.minimum(pa, pb), np.maximum(pa, pb)
        codes.append(lo_i.astype(np.int64) * t + hi_i)
    big_ids = np.nonzero(big)[0]
    if len(big_ids):
        allt = np.arange(t)
        for i in big_ids.tolist():
            other = allt[allt != i]
            codes.append(np.minimum(other, i).astype(np.int64) * t + np.maximum(other, i))
    if not codes:
        return 0, truncated
    codes = np.unique(np.concatenate(codes))
    if len(codes) > PAIR_CAP:
        codes, truncated = codes[:PAIR_CAP], True
    ia, ib = codes // t, codes % t
    found = 0
    for s in range(0, len(ia), 400_000):
        a, b = ia[s:s + 400_000], ib[s:s + 400_000]
        bb = ((bmin[a] < bmax[b] - SAT_EPS) & (bmin[b] < bmax[a] - SAT_EPS)).all(axis=1)
        a, b = a[bb], b[bb]
        if len(a):
            found += int(_sat_overlap(uvt[a], uvt[b]).sum())
    return found, truncated


def _check(status, **kw):
    return dict(status=status, **kw)


def _measure(obj, layer, texture_px, lightmap_rules, allow_overlap, target_px_per_m):
    d = _tri_arrays(obj, layer)
    p3, uvt, poly = d["p3"], d["uv"], d["poly"]
    if len(uvt) == 0:
        return {"uv_layer": layer.name, "verdict": "FAIL", "error": "mesh has no faces; nothing measured",
                "checks": {}}
    tri_ok = np.isfinite(uvt).all(axis=(1, 2)) & np.isfinite(p3).all(axis=(1, 2))
    loop_ok = np.isfinite(d["loop_uv"]).all(axis=1)
    bad_loops = int((~loop_ok).sum())
    bad_polys = np.unique(np.concatenate([poly[~tri_ok], np.repeat(np.arange(d["n_poly"]), d["poly_total"])[~loop_ok]]))
    excluded_faces = len(bad_polys)
    finite_check = (_check("FAIL", value=bad_loops, excluded_faces=excluded_faces,
                           note="non-finite UV or position; those faces are excluded from the other checks")
                    if (bad_loops or excluded_faces) else _check("PASS", value=0))
    if not tri_ok.any():
        return {"uv_layer": layer.name, "verdict": "FAIL", "non_finite_loops": bad_loops,
                "excluded_faces": excluded_faces, "error": "no finite UV triangle; nothing measured",
                "checks": {"uv_finite": finite_check}}
    uvt = np.where(tri_ok[:, None, None], uvt, 0.0)
    p3 = np.where(tri_ok[:, None, None], p3, 0.0)
    a_uv, a_3d = _tri_area_uv(uvt), _tri_area_3d(p3)  # excluded triangles measure 0
    area_3d, area_uv = float(a_3d.sum()), float(a_uv.sum())
    poly_uv = np.bincount(poly, weights=a_uv, minlength=d["n_poly"])
    collapsed_mask = poly_uv < COLLAPSED_AREA
    collapsed_mask[bad_polys] = False
    collapsed = int(collapsed_mask.sum())
    islands = _islands(d)
    n_islands = int(islands.max()) + 1 if len(islands) else 0
    tri_island = islands[poly]
    isl_uv = np.bincount(tri_island, weights=a_uv, minlength=n_islands)
    isl_3d = np.bincount(tri_island, weights=a_3d, minlength=n_islands)
    good = (isl_uv > COLLAPSED_AREA) & (isl_3d > 0)
    dens = np.sqrt(isl_uv[good] / isl_3d[good]) * texture_px
    live = (a_uv > COLLAPSED_AREA) & tri_ok
    live_uv = uvt[live]
    pairs, truncated = _overlap_pairs(live_uv)
    cov, overlap_area = _coverage(live_uv) if len(live_uv) else ({}, 0.0)
    cov_mean = sum(cov.values()) / len(cov) if cov else 0.0
    str_ratio = _stretch(p3[live], live_uv)
    stretch_p95 = float(np.percentile(str_ratio, 95)) if len(str_ratio) else None
    spread = float(dens.max() / dens.min()) if len(dens) else None
    flat = d["loop_uv"]  # polygon loops, not triangle corners
    oob = int((((flat < -1e-4) | (flat > 1.0001)).any(axis=1) & loop_ok).sum())
    density = math.sqrt(area_uv / area_3d) * texture_px if area_3d > 0 else 0.0

    entry = {
        "uv_layer": layer.name, "islands": n_islands, "collapsed_faces": collapsed,
        "overlap_pairs": pairs, "overlap_area": round(overlap_area, 5),
        "overlap_ratio": round(overlap_area * 1.0 / area_uv, 5) if area_uv > 0 else 0.0,
        "coverage_per_tile": {str(k): round(v, 4) for k, v in sorted(cov.items())},
        "uv_coverage": round(cov_mean, 4),
        "texel_density_px_per_m": round(density, 1),
        "island_density_min": round(float(dens.min()), 1) if len(dens) else None,
        "island_density_max": round(float(dens.max()), 1) if len(dens) else None,
        "density_spread": round(spread, 3) if spread is not None else None,
        "stretch_p95": round(stretch_p95, 3) if stretch_p95 is not None else None,
        "non_finite_loops": bad_loops, "excluded_faces": excluded_faces,
        "excluded_face_indices": [int(i) for i in bad_polys[:50]],
        "uv_area_sum": round(area_uv, 4), "surface_m2": round(area_3d, 4), "loops_outside_0_1": oob,
        "udim_tiles": sorted(cov),
    }
    unique_rules = lightmap_rules or not allow_overlap
    checks = {"uv_finite": finite_check,
              "collapsed_faces": _check("FAIL" if collapsed else "PASS", value=collapsed)}
    if allow_overlap and not lightmap_rules:
        checks["overlap"] = _check("PASS", value=pairs, note="allow_overlap declared; rule skipped")
    elif pairs:
        checks["overlap"] = _check("FAIL", value=pairs)
    elif truncated:
        checks["overlap"] = _check("NOT_CHECKED", reason="too many candidate pairs; search truncated, none found")
    else:
        checks["overlap"] = _check("PASS", value=0)
    checks["density_spread"] = (_check("NOT_CHECKED", reason="no measurable island") if spread is None else
                                _check("WARN" if spread > SPREAD_WARN else "PASS", value=round(spread, 3)))
    checks["coverage"] = _check("WARN" if cov_mean < COVERAGE_WARN else "PASS", value=round(cov_mean, 4))
    checks["stretch_p95"] = (_check("NOT_CHECKED", reason="no measurable triangle") if stretch_p95 is None else
                             _check("WARN" if stretch_p95 > STRETCH_WARN else "PASS", value=round(stretch_p95, 3)))
    if target_px_per_m:
        ratio = density / target_px_per_m
        entry["density_status"] = "PASS" if 0.75 <= ratio <= 1.25 else "WARN"
        checks["density_target"] = _check(entry["density_status"], value=round(density, 1))
    entry["rules"] = "lightmap" if lightmap_rules else ("unique" if unique_rules else "stacked_declared")
    entry["checks"] = checks
    entry["verdict"] = _worst(c["status"] for c in checks.values())
    return entry


def _json_safe(x):
    """NaN/inf become None, recursively, so the result is valid JSON."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x


def _worst(statuses):
    s = set(statuses)
    if "FAIL" in s:
        return "FAIL"
    if "WARN" in s or "NOT_CHECKED" in s:
        return "WARN"
    return "PASS"


def _object(obj, a):
    entry_mode = obj.mode
    if entry_mode == "EDIT":
        obj.update_from_editmode()
        with bpy.context.temp_override(active_object=obj, object=obj):
            bpy.ops.object.mode_set(mode="OBJECT")
    try:
        return _object_in_object_mode(obj, a)
    finally:
        if entry_mode == "EDIT" and obj.mode != "EDIT":
            with bpy.context.temp_override(active_object=obj, object=obj):
                bpy.ops.object.mode_set(mode="EDIT")


def _users(me):
    return [o.name for o in bpy.data.objects if o.data is me]


def _object_in_object_mode(obj, a):
    me = obj.data
    entry = {}
    bpy.context.view_layer.update()  # objects linked a moment ago only join the view layer after an update
    if (a["unwrap"] or a["lightmap"]) and obj.name not in bpy.context.view_layer.objects:
        return {"error": f"{obj.name} is not in the active view layer (its collection is excluded); "
                         "UV operators cannot edit it. Include the collection or measure only",
                "verdict": "FAIL"}
    if (a["unwrap"] or a["lightmap"]) and len(_users(me)) > 1:
        others = [n for n in _users(me) if n != obj.name]
        if not a["make_single_user"]:
            return {"error": f"mesh {me.name!r} is shared with {others}; unwrapping would change those objects too. "
                             "Pass make_single_user=True to give this object its own copy, or make it single-user first",
                    "verdict": "FAIL"}
        obj.data = me.copy()
        me = obj.data
        entry["made_single_user"] = True
    uv_layer = a["uv_layer"]
    if not me.uv_layers:
        if not (a["unwrap"] or a["lightmap"]):
            return {"error": "no UV layer; measure-only leaves the mesh unchanged. Pass unwrap=True to create one",
                    "verdict": "FAIL"}
        if uv_layer is not None:
            return {"error": f"UV layer {uv_layer!r} not found (mesh has none)", "verdict": "FAIL"}
        me.uv_layers.new(name="UVMap")
    elif uv_layer is not None and _resolve_layer(me, uv_layer) is None:
        return {"error": f"UV layer {uv_layer!r} not found; layers: {[l.name for l in me.uv_layers]}",
                "verdict": "FAIL"}
    if a["unwrap"]:
        target = _resolve_layer(me, uv_layer)
        prev_active = me.uv_layers.active.name if me.uv_layers.active else None
        me.uv_layers.active = target
        try:
            entry.update(_unwrap(obj, a["method"], a["angle_deg"], a["texture_px"], a["margin_px"],
                                 a["seams_from_angle"]))
        finally:
            if prev_active and prev_active in me.uv_layers:
                me.uv_layers.active = me.uv_layers[prev_active]
    if a["lightmap"]:
        entry["lightmap_channel"] = _lightmap(obj)
    entry["uv_layers"] = [l.name for l in me.uv_layers]
    layer = _resolve_layer(me, uv_layer)
    is_lm = layer.name == a["lightmap_uv_layer"]
    entry.update(_measure(obj, layer, a["texture_px"], is_lm, a["allow_overlap"], a["target_px_per_m"]))
    if a["lightmap"] and not is_lm:
        lm = _measure(obj, me.uv_layers[LIGHTMAP_NAME], a["texture_px"], True, False, None)
        entry["lightmap"] = lm
        entry["verdict"] = _worst([entry["verdict"], lm["verdict"]])
    return entry


def main(objects, unwrap=False, angle_deg=66.0, texture_px=2048, target_px_per_m=None, lightmap=False,
         uv_layer=None, allow_overlap=False, method="smart", margin_px=4.0, seams_from_angle=None,
         lightmap_uv_layer=LIGHTMAP_NAME, make_single_user=False, result_path=None, run_id=None):
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    a = dict(unwrap=unwrap, angle_deg=angle_deg, texture_px=texture_px, target_px_per_m=target_px_per_m,
             lightmap=lightmap, uv_layer=uv_layer, allow_overlap=allow_overlap, method=method,
             make_single_user=make_single_user,
             margin_px=margin_px, seams_from_angle=seams_from_angle, lightmap_uv_layer=lightmap_uv_layer)
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"error": "not a mesh", "verdict": "FAIL"}
            continue
        out[name] = _object(obj, a)
    verdicts = [o["verdict"] for o in out.values()]
    if not verdicts:
        verdict, note = "FAIL", "no objects measured"
    else:
        verdict, note = _worst(verdicts), None
        if "FAIL" in verdicts:
            verdict = "FAIL"
    result = {"verdict": verdict, "run_id": run_id, "texture_px": texture_px, "objects": out}
    if note:
        result["note"] = note
    result = _json_safe(result)
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, allow_nan=False)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
