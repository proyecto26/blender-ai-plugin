"""Read-only topology report: quads/tris/n-gons ratio, poles (3- and 5+-valence
vertices), non-manifold edges, triangle count and a deformation-readiness verdict.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/topology_report.py",
                            init_globals={"ARGS": {"objects": ["SK_Hero_Body"], "deforming": True}})["result"]

ARGS:
    objects    (list[str], required)
    deforming  (bool) stricter rules for animated meshes (quads >= 90 %, no n-gons)
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


def main(objects, deforming=False):
    out = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            out[name] = {"error": "not a mesh"}
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        faces = len(bm.faces) or 1
        quads = sum(1 for f in bm.faces if len(f.verts) == 4)
        tris = sum(1 for f in bm.faces if len(f.verts) == 3)
        ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
        interior = [v for v in bm.verts if not v.is_boundary and v.link_faces]
        poles3 = sum(1 for v in interior if len(v.link_edges) == 3)
        poles5 = sum(1 for v in interior if len(v.link_edges) >= 5)
        poles6 = sum(1 for v in interior if len(v.link_edges) >= 6)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        triangles = sum(len(f.verts) - 2 for f in bm.faces)
        bm.free()
        quad_pct = 100 * quads / faces
        if deforming:
            verdict = "PASS" if quad_pct >= 90 and ngons == 0 and non_manifold == 0 and poles6 == 0 else "FAIL"
        else:
            verdict = "PASS" if non_manifold == 0 else "WARN"
        out[name] = {"faces": faces, "quads_pct": round(quad_pct, 1), "tris": tris, "ngons": ngons,
                     "triangles_total": triangles, "poles_3": poles3, "poles_5_plus": poles5,
                     "poles_6_plus": poles6, "non_manifold_edges": non_manifold, "verdict": verdict}
    return {"deforming_rules": deforming, "objects": out}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
