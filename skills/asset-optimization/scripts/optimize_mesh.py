"""Safe mesh cleanup for game assets: merge by distance, delete loose geometry,
dissolve degenerate faces, recalculate normals outward, and optionally limited
dissolve + triangulate. Works on mesh data directly (no mode switching) and
reports before/after counts.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/optimize_mesh.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "merge_distance": 0.0001}})["result"]

ARGS:
    objects          (list[str], required)
    merge_distance   (float) default 0.0001
    limited_dissolve (float|None) angle in degrees for planar dissolve (e.g. 1.0); None skips
    triangulate      (bool) default False
    backup           (bool) keep an untouched hidden copy named <name>_BAK (default True)
"""
import json
import math
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


def _counts(bm):
    return {"verts": len(bm.verts), "faces": len(bm.faces), "tris": sum(len(f.verts) - 2 for f in bm.faces)}


def main(objects, merge_distance=0.0001, limited_dissolve=None, triangulate=False, backup=True):
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"error": "not a mesh"}
            continue
        if backup and not bpy.data.objects.get(f"{name}_BAK"):
            bak = obj.copy()
            bak.data = obj.data.copy()
            bak.name = f"{name}_BAK"
            for c in obj.users_collection:
                c.objects.link(bak)
            bak.hide_set(True)
            bak.hide_render = True
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before = _counts(bm)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_distance)
        bmesh.ops.dissolve_degenerate(bm, dist=merge_distance, edges=bm.edges)
        loose_e = [e for e in bm.edges if not e.link_faces]
        bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
        loose_v = [v for v in bm.verts if not v.link_edges]
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")
        if limited_dissolve:
            bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(limited_dissolve),
                                     verts=bm.verts, edges=bm.edges)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if triangulate:
            bmesh.ops.triangulate(bm, faces=bm.faces)
        after = _counts(bm)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        out[name] = {"before": before, "after": after, "backup": f"{name}_BAK" if backup else None}
    return {"objects": out}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
