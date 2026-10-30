"""Game-ready validation gate for one or more mesh objects (read-only).

Checks: applied transforms, triangle budget, n-gons, non-manifold edges, loose
geometry, UV layers + out-of-bounds UVs, empty material slots, naming prefix,
origin placement, and scale sanity. Returns PASS / WARN / FAIL per check.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/validate_asset.py",
                            init_globals={"ARGS": {"objects": ["SM_Crate_01"], "tri_budget": 3000}})["result"]

ARGS:
    objects     (list[str]|None) object names; default = selected meshes, else all meshes in COL_Export
    tri_budget  (int|None)       per-object triangle budget
    prefix      (str)            required name prefix (default "SM_"; use "" to skip)
    max_size_m  (float)          WARN when the largest dimension exceeds this (catches cm/m mix-ups)
"""
import json
import sys

import bmesh
import bpy


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


def _check(obj, tri_budget, prefix, max_size_m, depsgraph):
    checks = {}

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
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        loose_verts = sum(1 for v in bm.verts if not v.link_edges)
        loose_edges = sum(1 for e in bm.edges if not e.link_faces)
        uv_layer = bm.loops.layers.uv.active
        uv_oob = 0
        if uv_layer:
            for f in bm.faces:
                for loop in f.loops:
                    u, v = loop[uv_layer].uv
                    if u < -1e-4 or u > 1.0001 or v < -1e-4 or v > 1.0001:
                        uv_oob += 1
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
    else:
        add("uvs", "PASS" if uv_oob == 0 else "WARN",
            f"{len(obj.data.uv_layers)} UV map(s); {uv_oob} loops outside 0-1 (ok only for tiling/trim)")
    empty_slots = [i for i, s in enumerate(obj.material_slots) if s.material is None]
    if not obj.material_slots:
        add("materials", "FAIL", "no material assigned")
    else:
        add("materials", "PASS" if not empty_slots else "FAIL",
            f"{len(obj.material_slots)} slot(s); empty slots: {empty_slots}")
    if prefix:
        add("naming", "PASS" if obj.name.startswith(prefix) else "FAIL", f"expected prefix {prefix!r}")
    largest = max(obj.dimensions) if obj.dimensions else 0
    add("scale_sanity", "PASS" if 0.001 < largest <= max_size_m else "WARN",
        f"largest dimension {largest:.3f} m (unit scale {bpy.context.scene.unit_settings.scale_length})")
    min_z = min((obj.matrix_world @ v.co).z for v in obj.data.vertices) if obj.data.vertices else 0.0
    add("origin", "PASS" if abs(obj.location.z - min_z) < 0.01 or abs(obj.location.length) < 1e-4 else "WARN",
        f"origin z={obj.location.z:.3f}, mesh min z={min_z:.3f} (props usually sit origin-at-base)")
    return tris, checks


def main(objects=None, tri_budget=None, prefix="SM_", max_size_m=50.0):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    report, overall = {}, "PASS"
    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
    for obj in _targets(objects):
        if obj.type != "MESH":
            continue
        tris, checks = _check(obj, tri_budget, prefix, max_size_m, depsgraph)
        worst = max((c["status"] for c in checks.values()), key=rank.get)
        report[obj.name] = {"tris": tris, "verdict": worst, "checks": checks}
        if rank[worst] > rank[overall]:
            overall = worst
    return {"verdict": overall if report else "FAIL", "objects": report,
            "note": "" if report else "no mesh objects to validate"}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
