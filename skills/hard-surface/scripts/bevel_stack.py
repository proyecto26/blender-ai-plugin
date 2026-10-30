"""Add the standard non-destructive hard-surface finishing stack:
Bevel (angle-limited, harden normals) -> Weighted Normal (keep sharp) -> optional Triangulate.
Existing modifiers with the same names are updated, not duplicated.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/bevel_stack.py",
                            init_globals={"ARGS": {"objects": ["SM_Rifle_Body"], "width": 0.004}})["result"]

ARGS:
    objects      (list[str], required) mesh object names
    width        (float)  bevel width in meters (default 0.003 = 3 mm)
    segments     (int)    bevel segments (default 2; 1 for game low-poly chamfers, 3+ for hero/cinematic)
    angle_deg    (float)  bevel angle limit (default 30)
    triangulate  (bool)   add a Triangulate modifier last (default False; usually done at export)
"""
import json
import math
import sys

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


def _modifier(obj, name, kind):
    mod = obj.modifiers.get(name)
    return mod if mod and mod.type == kind else obj.modifiers.new(name, kind)


def main(objects, width=0.003, segments=2, angle_deg=30.0, triangulate=False):
    report = {}
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            report[name] = "skipped: not a mesh"
            continue
        bevel = _modifier(obj, "HS_Bevel", "BEVEL")
        bevel.width = width
        bevel.segments = segments
        bevel.limit_method = "ANGLE"
        bevel.angle_limit = math.radians(angle_deg)
        bevel.harden_normals = True
        bevel.use_clamp_overlap = True
        bevel.miter_outer = "MITER_ARC"
        wn = _modifier(obj, "HS_WeightedNormal", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
        wn.weight = 50
        wn.mode = "FACE_AREA"
        if triangulate:
            tri = _modifier(obj, "HS_Triangulate", "TRIANGULATE")
            tri.keep_custom_normals = True
        # Smooth shading is required for weighted normals to take effect.
        for poly in obj.data.polygons:
            poly.use_smooth = True
        depsgraph = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        mesh.calc_loop_triangles()
        tris = len(mesh.loop_triangles)
        ev.to_mesh_clear()
        report[name] = {"stack": [m.name for m in obj.modifiers], "evaluated_tris": tris}
    return {"objects": report}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
