"""Surfaces from curves, and a continuity check for the seam between two of them: `loft` through ordered sections,
`patch` (Coons) from four boundary curves, `continuity` (G0 / G1 / G2) along a shared boundary.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/surface_tools.py", init_globals={"ARGS": {
        "action": "loft", "name": "Vase", "closed": True, "count": 24,
        "sections": [[[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]], [[0.6, 0, 1], [0, 0.6, 1], [-0.6, 0, 1], [0, -0.6, 1]]]}})["result"]

ARGS:
    action    (str, required) "loft" | "patch" | "continuity"

  loft (creates a new mesh object; nothing existing is changed):
    sections  (list[list[[x,y,z]]]) at least 2 ordered polylines (2+ points each). Each is resampled by arc length to
              `count` points; the surface passes through every section. Rings must start at matching places.
    count     (int)  points per section (default 16)
    closed    (bool) sections are closed rings (default False): resampled periodically and the faces wrap around
    subdiv    (int)  extra rows between neighbouring sections, by Catmull-Rom through the sections (default 0 = straight
              between sections, no extra rows)
    name      (str)  object name (default "Loft"); an existing name gets Blender's ".001"

  patch (creates a new mesh object):
    bottom, top, left, right  (list[[x,y,z]]) the four boundary curves. bottom and top run u: 0 -> 1, left and right run
              v: 0 -> 1, so bottom[0] = left[0], bottom[-1] = right[0], top[0] = left[-1], top[-1] = right[-1].
    nu, nv    (int)  grid size along u and v (default 16, 16)
    name      (str)  default "Patch"
    tol       (float) corner mismatch accepted (default 1e-4); larger is refused with the corners named.
              The surface is bilinearly blended (Coons): it reproduces the four boundaries exactly.

  continuity (read-only):
    a, b      each a surface: either an object name (mesh; world-space vertices read row by row; in Edit Mode the live edit mesh is read, nothing flushed) with
              a_shape / b_shape = [rows, cols], or a_grid / b_grid = rows x cols x 3 nested lists.
    edge_a    (str) boundary of a: "last_row" (default) | "first_row" | "last_col" | "first_col"
    edge_b    (str) boundary of b, default "first_row"
              Rows run away from the boundary after normalising; each surface needs at least 4 rows across the seam
              (equal spacing across the seam is assumed; resample if not).
    tol       (float) G0 distance accepted between the two boundaries (default 1e-4)
    g1_deg    (float) G1: largest angle between the two surface normals along the seam (default 1.0)
    g2_tol    (float) G2: largest difference of normal curvature across the seam times the seam's size (default 0.05)

Returns for continuity: g0 {max_distance, ok}, g1 {max_angle_deg, ok}, g2 {max_curvature_jump, ok}, and `level`, the highest
of "G2" | "G1" | "G0" | "none" whose test and all lower ones pass. Boundaries that do not coincide (different point
counts, or points farther than `tol` apart in either direction) are refused with a ValueError, not scored. Derivatives are
second-order one-sided differences, so the check is accurate for smooth surfaces sampled finely enough; G2 compares the
normal curvature of the two surfaces in the surface direction perpendicular to the seam (from the second fundamental
form, so it does not depend on how either grid is laid out or sheared; the seam's own curvature is estimated by
differencing it twice, so a seam sampled with fewer than 5 points gives g2.ok = null, "not_measured", and level stops
at G1). Limit: the rows must be a smooth function of the row index; a kinked grid gives wrong derivatives.
"""
import json
import sys

import bmesh
import bpy
import numpy as np


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


def _poly(pts, what):
    a = np.asarray(pts, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 3 or len(a) < 2:
        raise ValueError(f"{what} must be a list of at least 2 [x, y, z] points")
    return a


def _resample(poly, n, closed=False):
    """n points evenly spaced by arc length (a closed ring is sampled periodically, first point not repeated)."""
    p = np.vstack([poly, poly[:1]]) if closed else poly
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 0:
        raise ValueError("a curve has zero length")
    t = np.linspace(0.0, s[-1], n, endpoint=not closed)
    return np.stack([np.interp(t, s, p[:, k]) for k in range(3)], axis=1)


def _catmull(rows, sub):
    """Insert `sub` rows between neighbouring rows (uniform Catmull-Rom; passes through every row)."""
    out = []
    n = len(rows)
    for i in range(n - 1):
        p0, p1, p2, p3 = rows[max(i - 1, 0)], rows[i], rows[i + 1], rows[min(i + 2, n - 1)]
        for k in range(sub + 1):
            t = k / (sub + 1)
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(rows[-1])
    return np.array(out)


def _make_object(name, grid, closed_cols):
    rows, cols = grid.shape[:2]
    verts = grid.reshape(-1, 3).tolist()
    faces = []
    ncol = cols if closed_cols else cols - 1
    for r in range(rows - 1):
        for c in range(ncol):
            c2 = (c + 1) % cols
            faces.append((r * cols + c, r * cols + c2, (r + 1) * cols + c2, (r + 1) * cols + c))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return {"object": obj.name, "rows": rows, "cols": cols, "vertices": len(verts), "faces": len(faces)}


def _loft(sections, count, closed, subdiv, name):
    if not sections or len(sections) < 2:
        raise ValueError("loft needs at least 2 sections")
    if int(count) < 2 or (closed and int(count) < 3):
        raise ValueError("'count' is too small")
    rows = np.array([_resample(_poly(s, f"section {i}"), int(count), closed) for i, s in enumerate(sections)])
    if int(subdiv) > 0:
        rows = _catmull(rows, int(subdiv))
    return {"action": "loft", **_make_object(name or "Loft", rows, closed), "closed": bool(closed),
            "sections": len(sections)}


def _coons(bottom, top, left, right, nu, nv):
    u = np.linspace(0, 1, nu)[None, :, None]
    v = np.linspace(0, 1, nv)[:, None, None]
    B = _resample(bottom, nu)[None, :, :]
    T = _resample(top, nu)[None, :, :]
    L = _resample(left, nv)[:, None, :]
    R = _resample(right, nv)[:, None, :]
    c00, c10, c01, c11 = B[0, 0], B[0, -1], T[0, 0], T[0, -1]
    bil = (1 - u) * (1 - v) * c00 + u * (1 - v) * c10 + (1 - u) * v * c01 + u * v * c11
    return (1 - v) * B + v * T + (1 - u) * L + u * R - bil


def _patch(bottom, top, left, right, nu, nv, tol, name):
    b, t, l, r = (_poly(c, n) for c, n in ((bottom, "bottom"), (top, "top"), (left, "left"), (right, "right")))
    if int(nu) < 2 or int(nv) < 2:
        raise ValueError("'nu' and 'nv' must be at least 2")
    corners = {"bottom[0] vs left[0]": (b[0], l[0]), "bottom[-1] vs right[0]": (b[-1], r[0]),
               "top[0] vs left[-1]": (t[0], l[-1]), "top[-1] vs right[-1]": (t[-1], r[-1])}
    bad = {k: round(float(np.linalg.norm(x - y)), 6) for k, (x, y) in corners.items() if np.linalg.norm(x - y) > tol}
    if bad:
        raise ValueError(f"boundary curves do not meet at their corners (distance > {tol}): {bad}")
    grid = _coons(b, t, l, r, int(nu), int(nv))
    return {"action": "patch", **_make_object(name or "Patch", grid, False)}


def _grid_from(obj_name, shape, grid, label):
    if grid is not None:
        g = np.asarray(grid, dtype=np.float64)
    else:
        obj = bpy.data.objects.get(obj_name) if obj_name else None
        if obj is None or obj.type != "MESH":
            raise ValueError(f"{label}: give a mesh object name with {label}_shape, or {label}_grid")
        if not shape or len(shape) != 2:
            raise ValueError(f"{label}_shape must be [rows, cols]")
        if obj.data.is_editmode:  # obj.data holds the stale pre-edit mesh; read the live edit mesh without changing anything
            bm = bmesh.from_edit_mesh(obj.data)
            pts = np.array([tuple(v.co) for v in bm.verts], dtype=np.float64).reshape(-1, 3)
        else:
            co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
            obj.data.vertices.foreach_get("co", co)
            pts = co.reshape(-1, 3)
        if shape[0] * shape[1] != len(pts):
            raise ValueError(f"{label}_shape {shape} does not match {len(pts)} vertices")
        mw = np.array(obj.matrix_world)
        g = (pts @ mw[:3, :3].T + mw[:3, 3]).reshape(int(shape[0]), int(shape[1]), 3)
    if g.ndim != 3 or g.shape[2] != 3:
        raise ValueError(f"{label} must be rows x cols x 3")
    return g


def _normalise(g, edge, want_last):
    """Return the grid with rows running across the seam and the seam at the last row (want_last) or first row."""
    if edge in ("last_col", "first_col"):
        g = g.transpose(1, 0, 2)
        edge = "last_row" if edge == "last_col" else "first_row"
    if edge not in ("last_row", "first_row"):
        raise ValueError(f"unknown edge {edge!r}")
    at_last = edge == "last_row"
    if at_last != want_last:
        g = g[::-1]
    return g


def _frame(rows):
    """Position, boundary tangent, cross-boundary first and second derivative at the seam of a normalised grid whose seam
    is row 0 (rows run away from it). For `a` the grid is flipped first so that row 0 is the seam as well, then the
    derivative is negated so both point the same way (from a into b)."""
    p0, p1, p2, p3 = rows[0], rows[1], rows[2], rows[3]
    d1 = (-3 * p0 + 4 * p1 - p2) / 2.0
    d2 = 2 * p0 - 5 * p1 + 4 * p2 - p3
    tang = np.gradient(p0, axis=0, edge_order=2)
    return p0, tang, d1, d2


def _normal_curvature(tang, d1, d2, n):
    """Normal curvature of the surface at each seam point in the direction in the tangent plane perpendicular to the
    seam. That direction is a property of the surface (not of how its grid is laid out), so two grids sampling the same
    surface give the same value whatever their parameterisation. w = Su + c*Ss with w . Ss = 0; kn = II(w,w) / I(w,w),
    with the second fundamental form from Suu (d2), Sus (d1 differenced along the seam) and Sss (seam differenced twice)."""
    sus = np.gradient(d1, axis=0, edge_order=2)
    sss = np.gradient(tang, axis=0, edge_order=2)
    c = -(d1 * tang).sum(axis=1) / (tang * tang).sum(axis=1)
    w = d1 + c[:, None] * tang
    ii = (d2 * n).sum(axis=1) + 2 * c * (sus * n).sum(axis=1) + c * c * (sss * n).sum(axis=1)
    return ii / (w * w).sum(axis=1)


def _continuity(a, b, edge_a, edge_b, tol, g1_deg, g2_tol):
    ga, gb = _normalise(a, edge_a, True), _normalise(b, edge_b, False)
    if min(len(ga), len(gb)) < 4:
        raise ValueError("each surface needs at least 4 rows across the seam")
    ba, bb = ga[-1], gb[0]
    if ba.shape != bb.shape:
        raise ValueError(f"boundaries have different point counts: {len(ba)} vs {len(bb)}")
    flipped = False
    if np.linalg.norm(ba - bb, axis=1).max() > tol:
        if np.linalg.norm(ba - bb[::-1], axis=1).max() <= tol:
            gb, flipped = gb[:, ::-1], True
        else:
            raise ValueError(f"boundaries do not coincide (max distance "
                             f"{min(np.linalg.norm(ba - bb, axis=1).max(), np.linalg.norm(ba - bb[::-1], axis=1).max()):.6g} "
                             f"> tol {tol}); move or resample them first")
    pa, ta, da, sa = _frame(ga[::-1])
    pb, tb, db, sb = _frame(gb)
    da = -da  # a's derivative pointed away from the seam into a; flip it to point from a toward b
    na, nb = np.cross(ta, da), np.cross(tb, db)
    la, lb = np.linalg.norm(na, axis=1), np.linalg.norm(nb, axis=1)
    if (la < 1e-12).any() or (lb < 1e-12).any():
        raise ValueError("degenerate surface at the seam (zero-area normal)")
    na, nb = na / la[:, None], nb / lb[:, None]
    g0 = float(np.linalg.norm(pa - pb, axis=1).max())
    ang = np.degrees(np.arccos(np.clip((na * nb).sum(axis=1), -1.0, 1.0)))
    # G2 needs the seam differenced twice; with fewer than 5 points that is not trustworthy, so it is not measured
    measured2 = len(pa) >= 5
    if measured2:
        ka = _normal_curvature(ta, da, sa, na)
        kb = _normal_curvature(tb, db, sb, nb)
        size = float(np.linalg.norm(pa.max(axis=0) - pa.min(axis=0))) or 1.0
        jump = float(np.abs(ka - kb).max() * size)
    ok0, ok1 = g0 <= tol, bool(ang.max() <= g1_deg)
    ok2 = bool(jump <= g2_tol) if measured2 else None
    level = "none"
    if ok0:
        level = "G0"
        if ok1:
            level = "G1"
            if ok2:  # None (not measured) stops at G1
                level = "G2"
    return {"action": "continuity", "level": level, "boundary_points": int(len(pa)), "b_reversed": flipped,
            "g0": {"max_distance": g0, "ok": ok0}, "g1": {"max_angle_deg": float(ang.max()), "ok": ok1},
            "g2": ({"max_curvature_jump": jump, "ok": ok2} if measured2 else
                   {"max_curvature_jump": None, "ok": None,
                    "not_measured": "needs at least 5 points along the seam"})}


def main(action=None, sections=None, count=16, closed=False, subdiv=0, name=None, bottom=None, top=None, left=None,
         right=None, nu=16, nv=16, tol=1e-4, a=None, b=None, a_shape=None, b_shape=None, a_grid=None, b_grid=None,
         edge_a="last_row", edge_b="first_row", g1_deg=1.0, g2_tol=0.05):
    if action == "loft":
        return _loft(sections, count, closed, subdiv, name)
    if action == "patch":
        if any(c is None for c in (bottom, top, left, right)):
            raise ValueError("patch needs bottom, top, left and right")
        return _patch(bottom, top, left, right, nu, nv, float(tol), name)
    if action == "continuity":
        return _continuity(_grid_from(a, a_shape, a_grid, "a"), _grid_from(b, b_shape, b_grid, "b"), edge_a, edge_b,
                           float(tol), float(g1_deg), float(g2_tol))
    raise ValueError("'action' must be loft | patch | continuity")


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
