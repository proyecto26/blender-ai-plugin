"""Game-ready validation gate for one or more mesh objects (read-only).

Checks: applied transforms, triangle budget, n-gons, non-manifold edges, loose geometry, degenerate faces and
edges, inconsistent winding, inside-out closed shells, UV layers + out-of-bounds UVs, collapsed UV faces,
overlapping UVs, empty material slots, naming prefix, origin placement, and scale sanity. Each check is PASS,
WARN, FAIL or NOT_CHECKED (it could not measure; the reason is in `detail`).

Verdict rule: an object is FAIL if any check fails, else WARN if any check warns or was NOT_CHECKED, else PASS;
the overall verdict is the worst object. A run that measured no mesh is FAIL.

Geometry checks use the evaluated mesh in world space, and lengths and areas are converted to metres with the
scene `unit_settings.scale_length` first, so the same physical asset gets the same verdict at scale 1.0 and 0.01.
Thresholds: degenerate face < 1e-10 m2, degenerate edge < 1e-7 m, collapsed UV face < 1e-12 UV area, UV overlap
> 1% of the covered UV area (rasterized at 256 px per UV tile, so faces smaller than a pixel are not resolved).
An open shell (a plane, a card, a mesh with holes) has no inside: `orientation` is NOT_CHECKED for it, never PASS.
The UV checks read the active render UV map.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/validate_asset.py",
                            init_globals={"ARGS": {"objects": ["SM_Crate_01"], "tri_budget": 3000}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python <skill_dir>/scripts/validate_asset.py -- --args-file a.json`
exits 0 on PASS or WARN, 2 on FAIL, 1 when the script raised. Trust the run only when the exit code is 0 or 2 AND
`result_path` exists with this run's `run_id`.

ARGS:
    objects     (list[str]|None) object names; default = selected meshes, else all meshes in COL_Export
    tri_budget  (int|None)       per-object triangle budget
    prefix      (str)            required name prefix (default "SM_"; use "" to skip)
    max_size_m  (float)          WARN when the largest dimension exceeds this (catches cm/m mix-ups)
    allow_overlap (bool)         declared mirrored or stacked UVs (default False): the overlap is reported but
                                 does not fail
    evidence_path (str|None)     write this run's result there (script-evidence/1: script, time, verdict, summary) so
                                 run_manifest.py can back a `validate` PASS with it. Use a path inside the run folder.
    result_path (str|None)       write the result dict plus "run_id" there as JSON (temp file, then replace) at the
                                 end of a successful run; a run that raised writes nothing
    run_id      (str|None)       echoed into that file so a caller can tell this run's file from an older one
"""
import datetime
import json
import os
import sys

import bmesh
import bpy
import numpy as np

RANK = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}
MIN_FACE_AREA_M2 = 1e-10
MIN_EDGE_M = 1e-7
MIN_UV_AREA = 1e-12
UV_OVERLAP_FAIL = 0.01
UV_RES = 256  # raster pixels per UV tile for the overlap measurement
UV_MAX_TILES = 16


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


def _targets(names):
    if names:
        missing = [n for n in names if n not in bpy.data.objects]
        if missing:
            raise ValueError(f"objects not found: {missing}")
        return [bpy.data.objects[n] for n in names]
    selected = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if selected:
        return selected
    export = bpy.data.collections.get("COL_Export")
    if export:
        return [o for o in export.all_objects if o.type == "MESH"]
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def _aggregate(statuses):
    """Object verdict: FAIL if any FAIL, else WARN if any WARN or NOT_CHECKED, else PASS."""
    statuses = list(statuses)
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses or "NOT_CHECKED" in statuses:
        return "WARN"
    return "PASS"


def _shells(bm):
    """Face-connected shells: [(face indices, closed, consistent)]. Closed = every edge has exactly two faces."""
    seen, out = set(), []
    for start in bm.faces:
        if start.index in seen:
            continue
        seen.add(start.index)
        stack, faces, closed, consistent = [start], [], True, True
        while stack:
            f = stack.pop()
            faces.append(f.index)
            for e in f.edges:
                links = e.link_faces
                if len(links) != 2:
                    closed = False
                elif not e.is_contiguous:
                    consistent = False
                for g in links:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        out.append((faces, closed, consistent))
    return out


def _uv_overlap(tri_uv):
    """Fraction of the covered UV area that lies under two or more triangles, by rasterizing at UV_RES per tile.

    Sample points are offset by different irrational fractions in u and v, so a shared edge (axis-aligned or
    diagonal) never double counts. Returns (ratio, None) or (None, reason).
    """
    if not len(tri_uv):
        return None, "no UV triangles with area"
    lo, hi = tri_uv.reshape(-1, 2).min(0), tri_uv.reshape(-1, 2).max(0)
    u0, v0 = float(np.floor(lo[0])), float(np.floor(lo[1]))
    w, h = int(np.ceil(hi[0] - u0)), int(np.ceil(hi[1] - v0))
    w, h = max(w, 1), max(h, 1)
    if w * h > UV_MAX_TILES:
        return None, f"UVs span {w}x{h} tiles (more than {UV_MAX_TILES}); overlap not measured"
    count = np.zeros((h * UV_RES, w * UV_RES), dtype=np.uint16)
    px = np.asarray(tri_uv[..., 0] - u0) * UV_RES
    py = np.asarray(tri_uv[..., 1] - v0) * UV_RES
    for t in range(len(tri_uv)):
        ax, bx, cx = px[t]
        ay, by, cy = py[t]
        x0, x1 = int(np.floor(min(ax, bx, cx))), int(np.ceil(max(ax, bx, cx)))
        y0, y1 = int(np.floor(min(ay, by, cy))), int(np.ceil(max(ay, by, cy)))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, count.shape[1]), min(y1, count.shape[0])
        if x1 <= x0 or y1 <= y0:
            continue
        gx = np.arange(x0, x1) + 0.6234567
        gy = (np.arange(y0, y1) + 0.3712345)[:, None]
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if det == 0.0:
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / det
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / det
        inside = (l1 > 0) & (l2 > 0) & (l1 + l2 < 1)
        count[y0:y1, x0:x1] += inside
    covered = int((count >= 1).sum())
    if covered == 0:
        return None, "no UV area was sampled"
    return float((count >= 2).sum()) / covered, None


def _geometry(bm, matrix_world, scale_length, add):
    """Degenerate faces/edges, winding, orientation, on world-space evaluated geometry converted to metres."""
    m = np.array(matrix_world, dtype=np.float64)
    co = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    world = co @ m[:3, :3].T + m[:3, 3]
    flips = np.linalg.det(m[:3, :3]) < 0  # a mirrored object renders with its winding reversed
    if not len(bm.faces):
        for name in ("degenerate_faces", "winding", "orientation"):
            add(name, "NOT_CHECKED", "no faces to measure")
    else:
        tris = bm.calc_loop_triangles()
        ti = np.array([[l.vert.index for l in t] for t in tris], dtype=np.int64)
        tf = np.array([t[0].face.index for t in tris], dtype=np.int64)
        a, b, c = world[ti[:, 0]], world[ti[:, 1]], world[ti[:, 2]]
        cross = np.cross(b - a, c - a)
        tri_area = 0.5 * np.linalg.norm(cross, axis=1)
        face_area = np.bincount(tf, weights=tri_area, minlength=len(bm.faces)) * scale_length ** 2
        bad = int((face_area < MIN_FACE_AREA_M2).sum())
        add("degenerate_faces", "PASS" if bad == 0 else "FAIL",
            f"{bad} face(s) below {MIN_FACE_AREA_M2:g} m2 (smallest {float(face_area.min()):.3g} m2)")
        shared = sum(1 for e in bm.edges if len(e.link_faces) == 2)
        flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
        if shared == 0:
            add("winding", "NOT_CHECKED", "no edge is shared by two faces, so there is no winding to compare")
        else:
            add("winding", "PASS" if flipped == 0 else "FAIL",
                f"{flipped} of {shared} shared edges join faces that wind opposite ways (flip normals / recalculate)")
        vol = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
        inside_out, unmeasured, measured = [], 0, 0
        for faces, closed, consistent in _shells(bm):
            if not (closed and consistent):
                unmeasured += 1
                continue
            measured += 1
            volume = float(vol[np.isin(tf, faces)].sum()) * (-1.0 if flips else 1.0)
            if volume < 0:
                inside_out.append(len(faces))
        if inside_out:
            add("orientation", "FAIL", f"{len(inside_out)} closed shell(s) have negative volume (inside out)"
                + (f"; {unmeasured} open shell(s): orientation not_measured" if unmeasured else ""))
        elif unmeasured:
            add("orientation", "NOT_CHECKED",
                f"{unmeasured} open or inconsistent shell(s) have no inside: orientation not_measured"
                + (f"; {measured} closed shell(s) face outward" if measured else ""))
        else:
            add("orientation", "PASS", f"{measured} closed shell(s) face outward")
    if not len(bm.edges):
        add("degenerate_edges", "NOT_CHECKED", "no edges to measure")
    else:
        ev = np.array([[v.index for v in e.verts] for e in bm.edges], dtype=np.int64)
        length = np.linalg.norm(world[ev[:, 0]] - world[ev[:, 1]], axis=1) * scale_length
        bad = int((length < MIN_EDGE_M).sum())
        add("degenerate_edges", "PASS" if bad == 0 else "FAIL",
            f"{bad} edge(s) below {MIN_EDGE_M:g} m (shortest {float(length.min()):.3g} m)")


def _uv_checks(bm, uv_layer, allow_overlap, add):
    tris = bm.calc_loop_triangles()
    uv = np.array([[l[uv_layer].uv[:] for l in t] for t in tris], dtype=np.float64).reshape(-1, 3, 2)
    tf = np.array([t[0].face.index for t in tris], dtype=np.int64)
    d1, d2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    tri_area = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    face_area = np.bincount(tf, weights=tri_area, minlength=len(bm.faces))
    collapsed = int((face_area < MIN_UV_AREA).sum())
    add("uv_collapsed", "PASS" if collapsed == 0 else "FAIL",
        f"{collapsed} of {len(face_area)} face(s) have UV area below {MIN_UV_AREA:g} (unwrap again or fix the layout)")
    ratio, why = _uv_overlap(uv[tri_area >= MIN_UV_AREA])
    if ratio is None:
        add("uv_overlap", "NOT_CHECKED", why)
    elif ratio > UV_OVERLAP_FAIL and allow_overlap:
        add("uv_overlap", "PASS", f"{ratio:.1%} of the covered UV area is stacked (allowed: allow_overlap=True)")
    else:
        add("uv_overlap", "PASS" if ratio <= UV_OVERLAP_FAIL else "FAIL",
            f"{ratio:.1%} of the covered UV area is under two or more faces (limit {UV_OVERLAP_FAIL:.0%}; "
            "mirrored or stacked on purpose: allow_overlap=True)")


def _check(obj, tri_budget, prefix, max_size_m, depsgraph, allow_overlap=False):
    checks = {}
    scale_length = bpy.context.scene.unit_settings.scale_length or 1.0

    def add(name, status, detail=""):
        checks[name] = {"status": status, "detail": detail}

    scale_ok = all(abs(s - 1.0) < 1e-4 for s in obj.scale)
    rot_ok = all(abs(r) < 1e-4 for r in obj.rotation_euler)
    add("transforms_applied", "PASS" if scale_ok and rot_ok else "FAIL",
        f"scale={tuple(round(s, 4) for s in obj.scale)} rot={tuple(round(r, 4) for r in obj.rotation_euler)}")

    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        loose_verts = sum(1 for v in bm.verts if not v.link_edges)
        loose_edges = sum(1 for e in bm.edges if not e.link_faces)
        render_uv = mesh.uv_layers.active_render or mesh.uv_layers.active
        uv_layer = bm.loops.layers.uv.get(render_uv.name) if render_uv else None
        uv_oob = 0
        if uv_layer:
            for f in bm.faces:
                for loop in f.loops:
                    u, v = loop[uv_layer].uv
                    if u < -1e-4 or u > 1.0001 or v < -1e-4 or v > 1.0001:
                        uv_oob += 1
        _geometry(bm, obj.matrix_world, scale_length, add)
        if uv_layer and len(bm.faces):
            _uv_checks(bm, uv_layer, allow_overlap, add)
        bm.free()
    finally:
        evaluated.to_mesh_clear()

    if tri_budget:
        status = "PASS" if tris <= tri_budget else ("WARN" if tris <= tri_budget * 1.1 else "FAIL")
        add("tri_budget", status, f"{tris}/{tri_budget}")
    else:
        add("tri_budget", "PASS", f"{tris} (no budget given)")
    add("ngons", "PASS" if ngons == 0 else "WARN", f"{ngons} n-gons (triangulate on export or fix)")
    add("non_manifold", "PASS" if non_manifold == 0 else "FAIL", f"{non_manifold} non-manifold edges")
    add("open_boundaries", "PASS" if boundary == 0 else "WARN", f"{boundary} boundary edges (fine for planes/cards)")
    add("loose_geometry", "PASS" if loose_verts + loose_edges == 0 else "FAIL",
        f"{loose_verts} loose verts, {loose_edges} loose edges")
    if not obj.data.uv_layers:
        add("uvs", "FAIL", "no UV map")
        add("uv_collapsed", "NOT_CHECKED", "no UV map")
        add("uv_overlap", "NOT_CHECKED", "no UV map")
    else:
        add("uvs", "PASS" if uv_oob == 0 else "WARN",
            f"{len(obj.data.uv_layers)} UV map(s); {uv_oob} loops outside 0-1 (ok only for tiling/trim)")
        if "uv_collapsed" not in checks:
            add("uv_collapsed", "NOT_CHECKED", "mesh has no faces")
            add("uv_overlap", "NOT_CHECKED", "mesh has no faces")
    empty_slots = [i for i, s in enumerate(obj.material_slots) if s.material is None]
    if not obj.material_slots:
        add("materials", "FAIL", "no material assigned")
    else:
        add("materials", "PASS" if not empty_slots else "FAIL",
            f"{len(obj.material_slots)} slot(s); empty slots: {empty_slots}")
    if prefix:
        add("naming", "PASS" if obj.name.startswith(prefix) else "FAIL", f"expected prefix {prefix!r}")
    largest = (max(obj.dimensions) if obj.dimensions else 0) * scale_length
    add("scale_sanity", "PASS" if 0.001 < largest <= max_size_m else "WARN",
        f"largest dimension {largest:.3f} m (unit scale {scale_length})")
    min_z = min((obj.matrix_world @ v.co).z for v in obj.data.vertices) if obj.data.vertices else 0.0
    add("origin", "PASS" if abs(obj.location.z - min_z) * scale_length < 0.01 or abs(obj.location.length) < 1e-4 else "WARN",
        f"origin z={obj.location.z * scale_length:.3f} m, mesh min z={min_z * scale_length:.3f} m "
        "(props usually sit origin-at-base)")
    return tris, checks


def _write_evidence(path, verdict, summary):
    """Write the result file the run manifest reads. Atomic, so a reader never sees half of it."""
    record = {"schema": "script-evidence/1", "script": "validate_asset.py", "verdict": verdict, "summary": summary,
              "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    os.replace(tmp, path)


def _write_result(path, result, run_id):
    """Result plus run_id as JSON: temp file, then replace, so a reader never sees half of it."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({**result, "run_id": run_id}, fh, indent=2)
    os.replace(tmp, path)


def main(objects=None, tri_budget=None, prefix="SM_", max_size_m=50.0, evidence_path=None, allow_overlap=False,
         result_path=None, run_id=None):
    targets = _targets(objects)
    editing = [o.name for o in targets if o.type == "MESH" and o.data.is_editmode]
    if editing:
        raise ValueError(f"{', '.join(editing)} {'is' if len(editing) == 1 else 'are'} in Edit Mode: obj.data holds the "
                         "pre-edit mesh, so a result read now could PASS on stale geometry. Leave Edit Mode "
                         "(Tab, or bpy.ops.object.mode_set(mode='OBJECT')) and run again; nothing was written")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    report, overall = {}, "PASS"
    for obj in targets:
        if obj.type != "MESH":
            continue
        tris, checks = _check(obj, tri_budget, prefix, max_size_m, depsgraph, bool(allow_overlap))
        worst = _aggregate(c["status"] for c in checks.values())
        report[obj.name] = {"tris": tris, "verdict": worst, "checks": checks,
                            "not_checked": [n for n, c in checks.items() if c["status"] == "NOT_CHECKED"]}
        if RANK[worst] > RANK[overall]:
            overall = worst
    verdict = overall if report else "FAIL"
    if evidence_path:
        _write_evidence(evidence_path, verdict, {"objects": {n: r["verdict"] for n, r in report.items()},
                                                 "tris": sum(r["tris"] for r in report.values())})
    result = {"verdict": verdict, "objects": report,
              "note": "" if report else "no mesh objects to validate"}
    if result_path:
        _write_result(result_path, result, run_id)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
