"""Clash audit for a set of mesh objects (read-only): penetrations, objects inside other objects, floating parts.

World-space BVH trees are built from the evaluated meshes (modifiers count), with an AABB broad phase. Touching
faces are not a clash. Nothing in the scene is changed.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/clash_audit.py",
                            init_globals={"ARGS": {"objects": ["SM_Table", "SM_Lamp"], "gap_max_m": 0.01}})["result"]

What is reported:
  clashes     pairs whose surfaces cross (an edge of one pierces the other) with an estimated penetration depth.
              Depth = the deepest sampled point of one mesh inside the other (vertices first, then edge midpoints,
              triangle centres and a barycentric grid when the vertices alone find nothing). The depth is the
              shortest translation along +-X, +-Y or +-Z that carries every sampled inside point out of the other
              mesh (per direction the largest ray distance to the surface; the smallest of the six). It is a lower
              bound limited by the sampling, not an exact figure, and for rotated shapes an axis-aligned way out
              is longer than the shortest one. A contained object's `depth_m` is different: the distance from its
              deepest vertex to the nearest surface of the outer object.
              "Inside" is decided by ray parity (majority of three skew rays). Penetration up to `min_depth_m`
              counts as touching.
  coincident  two meshes whose sampled points all lie on each other's surface (duplicate geometry in the same
              place) are a clash with depth "coincident": nothing crosses and nothing is inside, yet they overlap
              completely.
  contained   an object whose surfaces cross nothing but which lies inside another closed object.
  floating    connected groups of objects (contact = overlap, containment, or a gap <= `gap_max_m` measured from
              sampled points to the other surface) other than the main group. Gaps between skew edges that no
              sample sits near can be missed, so a group may be reported floating when it only grazes along an edge.
  not_measured  what could not be decided: an open mesh has no inside, so containment inside it, and depth
              measured into it, are listed here and never count as a pass.
Verdict: FAIL on a clash, a contained object or (with `require_connected`) a floating part; WARN when only
not_measured entries exist; PASS otherwise.

ARGS:
    objects            (list[str]|None) mesh objects to audit; default = all visible mesh objects in the scene
    gap_max_m          (float) largest gap that still counts as contact for the floating-part grouping (default 0.005)
    min_depth_m        (float) penetration at or below this is touching, not a clash (default 0.001)
    require_connected  (bool)  more than one contact group fails the audit (default True)
    anchor             (str|None) object whose group is the main one; default = the group with most objects, then tris
    ignore_pairs       (list[[str, str]]) pairs allowed to overlap (a bolt in its hole); they still join a group
    max_samples        (int) cap on sample points per object and direction (default 4000; sets `sampled` when hit)
    evidence_path      (str|None) a .json file inside an existing run folder; the audit writes its own result there, as
                       script-evidence/1 (script, time, verdict PASS/WARN/FAIL, summary), which run_manifest.py reads to
                       back a `validate` PASS. An existing file is only replaced when it is a clash_audit evidence file.
"""
import datetime
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCRIPT = "clash_audit.py"
DIRS = [Vector(d).normalized() for d in ((0.5934, 0.6171, 0.5154), (-0.3182, 0.5017, 0.8043), (0.2651, -0.7483, 0.6101))]
GRID = 6  # barycentric grid divisions for the finest sampling level


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


class Rec:
    """One object's evaluated mesh in world space."""

    def __init__(self, obj, depsgraph):
        self.name = obj.name
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            co = np.empty(n * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            m = np.array(obj.matrix_world, dtype=np.float64)
            self.verts = co.reshape(n, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            tri = np.empty(nt * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri)
            self.tris = tri.reshape(nt, 3)
            ne, nl = len(me.edges), len(me.loops)
            le = np.empty(nl, dtype=np.int32)
            me.loops.foreach_get("edge_index", le)
            used = np.bincount(le, minlength=ne)
            used = used[used > 0]
            self.closed = bool(nt > 0 and np.all(used == 2))
            ed = np.empty(ne * 2, dtype=np.int32)
            me.edges.foreach_get("vertices", ed)
            self.edges = ed.reshape(ne, 2)
        finally:
            ev.to_mesh_clear()
        self.ok = len(self.tris) > 0
        if self.ok:
            self.lo, self.hi = self.verts.min(0), self.verts.max(0)
            self.bvh = BVHTree.FromPolygons([tuple(v) for v in self.verts.tolist()],
                                            [tuple(t) for t in self.tris.tolist()], epsilon=0.0)


def _aabb_gap(a, b):
    d = np.maximum(0.0, np.maximum(a.lo - b.hi, b.lo - a.hi))
    return float(np.linalg.norm(d))


def _samples(rec, level, cap, rng):
    v = rec.verts
    pts = [v]
    if level >= 1:
        pts.append(v[rec.edges].mean(1))
        pts.append(v[rec.tris].mean(1))
    if level >= 2:
        w = [(i / GRID, j / GRID) for i in range(GRID + 1) for j in range(GRID + 1 - i)]
        t = v[rec.tris]
        for a, b in w:
            pts.append(t[:, 0] * a + t[:, 1] * b + t[:, 2] * (1 - a - b))
    pts = np.concatenate(pts)
    sampled = False
    if len(pts) > cap:
        pts = pts[np.sort(rng.choice(len(pts), cap, replace=False))]
        sampled = True
    return pts, sampled


def _inside(bvh, p, far, adv):
    """Ray parity, majority of three skew rays."""
    votes = 0
    for d in DIRS:
        o, n = Vector(p), 0
        for _ in range(5000):
            hit = bvh.ray_cast(o, d, far)
            if hit[0] is None:
                break
            n += 1
            o = hit[0] + d * adv
        votes += n % 2
    return votes >= 2


AXES = [Vector(v) for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]


def _deepest(pts, other, tol, far, adv):
    """Deepest point of `pts` inside the closed mesh `other`, as the distance to its nearest surface:
    (deepest depth, number of points deeper than tol). Used for containment, where there is no overlap axis."""
    sel = pts[np.all(pts >= other.lo - tol, 1) & np.all(pts <= other.hi + tol, 1)]
    best, count = 0.0, 0
    for p in sel:
        if _inside(other.bvh, p, far, adv):
            d = other.bvh.find_nearest(Vector(p))
            if d[0] is not None:
                best = max(best, float(d[3]))
                count += d[3] > tol
    return best, count


def _penetration(pts, other, tol, far, adv):
    """Penetration depth of the points of one mesh found inside the closed mesh `other`: the shortest translation
    along +-X, +-Y or +-Z that carries all of them out. Per direction it is the largest ray distance from an inside
    point to the surface; the smallest of the six is the depth (0.0 when no point is inside)."""
    sel = pts[np.all(pts >= other.lo - tol, 1) & np.all(pts <= other.hi + tol, 1)]
    way = [0.0] * 6
    found = False
    for p in sel:
        if not _inside(other.bvh, p, far, adv):
            continue
        found = True
        o = Vector(p)
        for k, d in enumerate(AXES):
            h = other.bvh.ray_cast(o, d, far)
            way[k] = max(way[k], float(h[3]) if h[0] is not None else float("inf"))
    return (min(way) if found else 0.0), found


def _on_surface_fraction(src, dst, tol, cap, rng):
    """Share of src's sampled points (vertices, edge midpoints, triangle centres) within tol of dst's surface."""
    pts, _ = _samples(src, 1, cap, rng)
    n = sum(dst.bvh.find_nearest(Vector(p), tol)[0] is not None for p in pts)
    return n / len(pts)


def _pierces(src, dst, eps):
    """True when an edge of `src` passes through the surface of `dst` (not just ending on it)."""
    p0, p1 = src.verts[src.edges[:, 0]], src.verts[src.edges[:, 1]]
    keep = np.all(np.maximum(p0, p1) >= dst.lo - eps, 1) & np.all(np.minimum(p0, p1) <= dst.hi + eps, 1)
    for a, b in zip(p0[keep], p1[keep]):
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 1e-12:
            continue
        d = Vector(d / length)
        t = 0.0
        for _ in range(64):
            hit = dst.bvh.ray_cast(Vector(a) + d * t, d, length - t)
            if hit[0] is None:
                break
            s = t + hit[3]
            if eps < s < length - eps:
                return True
            t = s + 2 * eps
            if t >= length:
                break
    return False


def _min_gap(a, b, limit, cap, rng):
    """Smallest sampled point-to-surface distance between two meshes within `limit`, else None."""
    best = None
    for src, dst in ((a, b), (b, a)):
        pts, _ = _samples(src, 1, cap, rng)
        sel = pts[np.all(pts >= dst.lo - limit, 1) & np.all(pts <= dst.hi + limit, 1)]
        for p in sel:
            r = dst.bvh.find_nearest(Vector(p), limit)
            if r[0] is not None and (best is None or r[3] < best):
                best = float(r[3])
    return best


def _check_evidence_path(path):
    if path is None:
        return None
    path = os.path.abspath(str(path))
    if not path.lower().endswith(".json"):
        raise ValueError("evidence_path must be a .json file")
    if not os.path.isdir(os.path.dirname(path)):
        raise ValueError(f"evidence_path folder does not exist (it must be the run folder): {os.path.dirname(path)}")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            old = None
        if not (isinstance(old, dict) and old.get("script") == SCRIPT):
            raise ValueError(f"evidence_path exists and is not a {SCRIPT} evidence file; refusing to overwrite it")
    return path


def _write_evidence(path, result):
    numbers = {"objects_checked": result["objects_checked"], "pairs_tested": result["pairs_tested"],
               "clashes": len(result["clashes"]), "contained": len(result["contained"]),
               "floating_groups": len(result["floating"]), "not_measured": len(result["not_measured"]),
               "touching_pairs": len(result["touching"]),
               "max_depth_m": max([c["depth_m"] for c in result["clashes"] + result["contained"]
                                   if c.get("depth_m") is not None] or [0.0]),
               "gap_max_m": result["params"]["gap_max_m"], "min_depth_m": result["params"]["min_depth_m"]}
    doc = {"schema": "script-evidence/1", "script": SCRIPT,
           "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds"),
           "verdict": result["verdict"], "summary": numbers}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return doc


def _targets(names):
    if names:
        missing = [n for n in names if n not in bpy.data.objects]
        if missing:
            raise ValueError(f"objects not found: {missing}")
        bad = [n for n in names if bpy.data.objects[n].type != "MESH"]
        if bad:
            raise ValueError(f"not mesh objects: {bad}")
        return [bpy.data.objects[n] for n in names]
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]


def main(objects=None, gap_max_m=0.005, min_depth_m=0.001, require_connected=True, anchor=None,
         ignore_pairs=None, max_samples=4000, evidence_path=None):
    evidence_path = _check_evidence_path(evidence_path)
    gap_max_m, tol, cap = float(gap_max_m), float(min_depth_m), int(max_samples)
    if gap_max_m < 0 or tol < 0 or cap < 100:
        raise ValueError("gap_max_m and min_depth_m must be >= 0 and max_samples >= 100")
    ignore = {frozenset(p) for p in (ignore_pairs or [])}
    objs = _targets(objects)
    editing = [o.name for o in objs if o.type == "MESH" and o.data.is_editmode]
    if editing:
        raise ValueError(f"{', '.join(editing)} {'is' if len(editing) == 1 else 'are'} in Edit Mode: obj.data holds the "
                         "pre-edit mesh, so a result read now could PASS on stale geometry. Leave Edit Mode "
                         "(Tab, or bpy.ops.object.mode_set(mode='OBJECT')) and run again; nothing was written")
    if anchor and anchor not in [o.name for o in objs]:
        raise ValueError(f"anchor {anchor!r} is not among the audited objects")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    recs, skipped = [], []
    for o in objs:
        r = Rec(o, depsgraph)
        (recs if r.ok else skipped).append(r if r.ok else o.name)
    notes = []
    if not recs:
        result = {"verdict": "FAIL", "objects_checked": 0, "pairs_tested": 0, "clashes": [], "contained": [],
                  "touching": [], "floating": [], "groups": [], "not_measured": [], "open_meshes": [],
                  "skipped": skipped, "notes": ["no mesh objects with faces to audit"],
                  "params": {"gap_max_m": gap_max_m, "min_depth_m": tol}}
        if evidence_path:
            result["evidence"] = _write_evidence(evidence_path, result)
        return result

    rng = np.random.default_rng(0)
    clashes, contained, touching, not_measured = [], [], [], []
    parent = list(range(len(recs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    pairs = 0
    sampled_any = False
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            a, b = recs[i], recs[j]
            # every tolerance below belongs to this pair alone: sized from the pair's own bounds, so a distant or
            # unrelated object elsewhere in the audit can never loosen or tighten a decision about a and b
            diag = float(np.linalg.norm(np.maximum(a.hi, b.hi) - np.minimum(a.lo, b.lo)))
            eps, adv = max(1e-6, 1e-6 * diag), max(2e-6, 2e-6 * diag)
            gap = _aabb_gap(a, b)
            if gap > gap_max_m + eps:
                continue
            overlap = gap <= eps
            joined = False
            if overlap:
                pairs += 1
                # "same surface" must be tighter than a slab is thick: face-touching slabs thinner than min_depth_m
                # have every sample within min_depth_m of each other without being duplicates
                thick = [float(np.min(r.hi - r.lo)) for r in (a, b) if r.closed]
                dup_tol = max(tol if not thick else min(tol, 0.2 * min(thick)), eps)
                crossing = _pierces(a, b, eps) or _pierces(b, a, eps)
                far = 4 * diag + 1.0
                if crossing:
                    joined = True
                    depth, how = 0.0, None
                    measurable = []
                    for src, dst in ((a, b), (b, a)):
                        if dst.closed:
                            measurable.append((src, dst))
                    for level in (0, 1, 2):
                        for src, dst in measurable:
                            pts, s = _samples(src, level, cap, rng)
                            sampled_any = sampled_any or s
                            d, _ = _penetration(pts, dst, tol, far, adv)
                            if d > depth:
                                depth, how = d, src.name
                        if depth > tol:
                            break
                    if frozenset((a.name, b.name)) in ignore:
                        pass
                    elif not measurable:
                        clashes.append({"a": a.name, "b": b.name, "depth_m": None, "depth": "not_measured",
                                        "reason": "both meshes are open: no inside to measure into"})
                    elif depth > tol:
                        clashes.append({"a": a.name, "b": b.name, "depth_m": round(depth, 5), "deepest_object": how})
                    elif depth == 0.0:
                        clashes.append({"a": a.name, "b": b.name, "depth_m": None, "depth": "below_sampling",
                                        "reason": "surfaces cross but no sample point lies inside; depth unresolved"})
                    else:
                        touching.append({"a": a.name, "b": b.name, "depth_m": round(depth, 5)})
                elif min(_on_surface_fraction(a, b, dup_tol, cap, rng),
                         _on_surface_fraction(b, a, dup_tol, cap, rng)) >= 0.9:
                    joined = True  # duplicate geometry in the same place: nothing crosses, nothing is inside
                    if frozenset((a.name, b.name)) not in ignore:
                        clashes.append({"a": a.name, "b": b.name, "depth_m": None, "depth": "coincident",
                                        "reason": "the two meshes occupy the same surface: duplicate geometry"})
                else:
                    for inner, outer in ((a, b), (b, a)):
                        if not np.all(inner.lo >= outer.lo - eps) or not np.all(inner.hi <= outer.hi + eps):
                            continue
                        if not outer.closed:
                            not_measured.append({"a": inner.name, "b": outer.name,
                                                 "what": f"containment of {inner.name} in {outer.name}",
                                                 "reason": f"{outer.name} is an open mesh and has no inside"})
                            continue
                        pts, s = _samples(inner, 0, cap, rng)
                        sampled_any = sampled_any or s
                        depth, count = _deepest(pts, outer, tol, far, adv)
                        if count:
                            joined = True
                            if frozenset((a.name, b.name)) not in ignore:
                                contained.append({"inner": inner.name, "outer": outer.name, "depth_m": round(depth, 5),
                                                  "fraction_inside": round(count / len(pts), 3)})
            if not joined:
                g = _min_gap(a, b, max(gap_max_m, eps) + eps, cap, rng)
                joined = g is not None
                if joined and overlap and g <= tol:
                    touching.append({"a": a.name, "b": b.name, "depth_m": 0.0})
            if joined:
                union(i, j)

    groups = {}
    for i, r in enumerate(recs):
        groups.setdefault(find(i), []).append(r)
    glist = sorted(groups.values(), key=lambda g: (-len(g), -sum(len(r.tris) for r in g), g[0].name))
    if anchor:
        glist.sort(key=lambda g: anchor not in [r.name for r in g])
    main_group = glist[0]
    floating = []
    for g in glist[1:]:
        best, near = None, None
        for r in g:
            for m in main_group:
                d = _min_gap(r, m, 1e9, cap, rng)
                if d is not None and (best is None or d < best):
                    best, near = d, m.name
        floating.append({"objects": sorted(r.name for r in g),
                         "nearest_gap_m": None if best is None else round(best, 5), "nearest_to": near})

    failed = bool(clashes or contained or (require_connected and floating))
    verdict = "FAIL" if failed else ("WARN" if not_measured else "PASS")
    if sampled_any:
        notes.append(f"sample cap {cap} reached on at least one mesh: depth and gap figures are from a subset")
    result = {"verdict": verdict, "objects_checked": len(recs), "pairs_tested": pairs, "clashes": clashes,
              "contained": contained, "touching": touching, "floating": floating,
              "groups": [sorted(r.name for r in g) for g in glist], "main_group": sorted(r.name for r in main_group),
              "not_measured": not_measured, "open_meshes": sorted(r.name for r in recs if not r.closed),
              "skipped": skipped, "notes": notes, "sampled": sampled_any,
              "params": {"gap_max_m": gap_max_m, "min_depth_m": tol, "require_connected": bool(require_connected)}}
    if evidence_path:
        result["evidence"] = _write_evidence(evidence_path, result)
        result["evidence"]["path"] = evidence_path
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
