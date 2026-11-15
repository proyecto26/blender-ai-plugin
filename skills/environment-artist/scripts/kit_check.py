"""Check that modular kit pieces sit on a grid so neighbours meet. Read only: nothing in the scene is changed.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/kit_check.py", init_globals={"ARGS": {
        "objects": ["SM_Env_Wall_2m"], "grid_m": 0.5}})["result"]

ARGS:
    objects     (list[str], required) mesh objects to check
    grid_m      (float, required)     grid size in metres (> 0)
    tolerance_m (float)               allowed distance off the grid, metres (default 1e-4)
    result_path (str)                 write the result (plus run_id) as JSON here, atomically, on success
    run_id      (str)                 copied into the result and the file

Everything is measured in world space on the evaluated mesh (modifiers included), so rotation, scale and
modifiers count. Per object, three checks (PASS, FAIL; NOT_CHECKED when there is nothing to measure):
    dimensions   each bounding-box extent is a multiple of grid_m
    origin       the object origin (its world location) is on a grid point
    snap_faces   for each of the six bounding-box faces, every vertex within tolerance of the face plane sits on a
                 grid line of that face (at least one of its two in-plane world coordinates is a multiple of
                 grid_m), so a neighbour with the same grid can meet it. Failing vertices are counted per face.
Object verdict is FAIL if any check FAILs, else WARN if any is NOT_CHECKED, else PASS; overall is the worst. An
object that is missing, not a mesh or has no vertices is FAIL (nothing measured is never PASS); an empty
`objects` list is FAIL with a note.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

AXES = "XYZ"


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


def _off_grid(values, grid):
    """Distance of each value to the nearest multiple of grid (numpy array)."""
    return np.abs(values - np.round(values / grid) * grid)


def _world_points(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
    finally:
        ev.to_mesh_clear()
    if n == 0:
        return co
    mw = np.array(obj.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


def _object(obj, grid, tol):
    pts = _world_points(obj)
    if not len(pts) or not np.isfinite(pts).all():
        return {"verdict": "FAIL", "error": "no finite vertices to measure"}
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    dims = hi - lo
    checks = {}

    bad = [(AXES[i], float(dims[i]), float(_off_grid(dims[i], grid))) for i in range(3)
           if _off_grid(dims[i], grid) > tol]
    checks["dimensions"] = {"status": "FAIL" if bad else "PASS", "dimensions_m": [float(d) for d in dims],
                            "off_grid": [{"axis": a, "size_m": s, "off_by_m": o} for a, s, o in bad]}

    loc = np.array(obj.matrix_world.translation, dtype=np.float64)
    bad = [(AXES[i], float(loc[i]), float(_off_grid(loc[i], grid))) for i in range(3)
           if _off_grid(loc[i], grid) > tol]
    checks["origin"] = {"status": "FAIL" if bad else "PASS", "origin_m": [float(v) for v in loc],
                        "off_grid": [{"axis": a, "at_m": s, "off_by_m": o} for a, s, o in bad]}

    faces, face_fail = {}, False
    for ax in range(3):
        o1, o2 = [a for a in range(3) if a != ax]
        for side, plane in (("-", lo[ax]), ("+", hi[ax])):
            sel = pts[np.abs(pts[:, ax] - plane) <= tol]
            on_line = (_off_grid(sel[:, o1], grid) <= tol) | (_off_grid(sel[:, o2], grid) <= tol)
            n_bad = int((~on_line).sum())
            faces[f"{side}{AXES[ax]}"] = {"vertices": int(len(sel)), "off_grid_vertices": n_bad}
            face_fail = face_fail or n_bad > 0
    checks["snap_faces"] = {"status": "FAIL" if face_fail else "PASS", "faces": faces}
    return {"verdict": _worst([c["status"] for c in checks.values()]), "checks": checks}


def main(objects=None, grid_m=None, tolerance_m=1e-4, result_path=None, run_id=None):
    if not isinstance(objects, (list, tuple)):
        raise ValueError("objects must be a list of object names")
    if grid_m is None or not grid_m > 0:
        raise ValueError("grid_m must be a number > 0")
    if not tolerance_m >= 0:
        raise ValueError("tolerance_m must be >= 0")
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"verdict": "FAIL", "error": "not found" if obj is None else "not a mesh"}
            continue
        out[name] = _object(obj, float(grid_m), float(tolerance_m))
    verdicts = [o["verdict"] for o in out.values()]
    if verdicts:
        verdict, note = _worst(verdicts), None
    else:
        verdict, note = "FAIL", "no objects measured"
    result = {"verdict": verdict, "run_id": run_id, "grid_m": grid_m, "tolerance_m": tolerance_m, "objects": out}
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
