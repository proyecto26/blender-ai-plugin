"""Headless Blender tests for iteration 15, batch `export`.

  A9   optimize_mesh        a mesh shared with other objects is made single-user first
  A10  export_unity/godot   missing object names raise before any export, naming every one
  A11  generate_lods        replaces only objects it tagged; refuses (and changes nothing for) a hand-made same-named one
  A12  export_asset         needs FINISHED and a file stamp that changed in this call; an old file is never deleted
  A14  gn_curve_profile     world-space points land on the same world path after the object moved and rotated
  A15  bevel_stack          owned modifiers are reordered in place to bevel -> weighted normal -> triangulate

Run:
    blender -b --factory-startup --python tests/blender/test_iter15_export.py -- '{"out_dir": "<new folder>"}'
Writes <out_dir>/iter15_export_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import json
import os
import runpy
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
OUT = {"dir": "."}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(skill, script, args):
    return runpy.run_path(os.path.join(SKILLS, skill, "scripts", script), init_globals={"ARGS": args})["result"]


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube(name, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def raises(fn, exc, *needles):
    try:
        fn()
    except exc as e:
        for n in needles:
            assert n in str(e), (n, str(e))
        return str(e)
    raise AssertionError(f"{exc.__name__} not raised")


def test_a9_shared_mesh():
    fresh()
    a = cube("A")
    b = bpy.data.objects.new("B", a.data)
    bpy.context.scene.collection.objects.link(b)
    assert a.data is b.data and a.data.users == 2
    res = run("asset-optimization", "optimize_mesh.py", {"objects": ["A"], "triangulate": True, "backup": False})
    assert a.data is not b.data, "A still shares its mesh with B"
    assert len(b.data.polygons) == 6, f"B was changed: {len(b.data.polygons)} faces"
    assert len(a.data.polygons) == 12
    assert res["objects"]["A"]["made_single_user"] is True
    return {"a_faces": len(a.data.polygons), "b_faces": len(b.data.polygons)}


def test_a10_missing_objects():
    fresh()
    cube("SM_Real")
    out = {}
    for skill, script, fname in (("unity-export", "export_unity.py", "x.fbx"), ("godot-export", "export_godot.py", "x.glb")):
        path = os.path.join(OUT["dir"], "a10_" + fname)
        msg = raises(lambda: run(skill, script, {"objects": ["SM_Real", "Ghost1", "Ghost2"], "out_path": path}),
                     ValueError, "Ghost1", "Ghost2")
        assert not os.path.exists(path), f"{script} exported anyway"
        out[script] = msg
    return out


def test_a11_lods():
    fresh()
    cube("Crate")
    hand = bpy.data.objects.new("Crate_LOD2", bpy.data.meshes.new("handmade"))
    bpy.context.scene.collection.objects.link(hand)
    n_objects = len(bpy.data.objects)
    raises(lambda: run("lod-pipeline", "generate_lods.py", {"object": "Crate", "ratios": [0.5, 0.25]}),
           ValueError, "Crate_LOD2")
    assert bpy.data.objects.get("Crate_LOD2") is hand and hand.data.name == "handmade", "hand-made object was touched"
    assert len(bpy.data.objects) == n_objects and "Crate_LOD1" not in bpy.data.objects, "refusal still changed the scene"
    bpy.data.objects.remove(hand)
    run("lod-pipeline", "generate_lods.py", {"object": "Crate", "ratios": [0.5, 0.25]})
    assert bpy.data.objects["Crate_LOD1"].get("bap_lod_source") == "Crate"
    run("lod-pipeline", "generate_lods.py", {"object": "Crate", "ratios": [0.5, 0.25]})  # replaces its own LODs
    names = sorted(o.name for o in bpy.data.objects)
    assert names == ["Crate", "Crate_LOD1", "Crate_LOD2"], names
    return {"objects": names}


class _Sub:
    def __init__(self, real, over):
        self._real, self._over = real, over

    def __getattr__(self, name):
        return self._over.get(name) or getattr(self._real, name)


class _Ops:
    def __init__(self, real, over):
        self._real, self._over = real, over

    def __getattr__(self, name):
        return _Sub(getattr(self._real, name), self._over.get(name, {}))


def _with_fake_obj_export(fn, result_set):
    """Run fn with bpy.ops.wm.obj_export replaced by a stub that returns result_set and writes nothing."""
    real = bpy.ops
    bpy.ops = _Ops(real, {"wm": {"obj_export": lambda **kw: result_set}})
    try:
        return fn()
    finally:
        bpy.ops = real


def test_a12_export_stamp():
    fresh()
    cube("SM_Box")
    path = os.path.join(OUT["dir"], "a12_old.obj")
    old = b"# old export from an earlier run\n"
    with open(path, "wb") as fh:
        fh.write(old)
    args = {"objects": ["SM_Box"], "out_path": path}
    out = {}
    out["cancelled"] = _with_fake_obj_export(
        lambda: raises(lambda: run("export-pipeline", "export_asset.py", args), RuntimeError, "did not finish"), {"CANCELLED"})
    out["unchanged"] = _with_fake_obj_export(
        lambda: raises(lambda: run("export-pipeline", "export_asset.py", args), RuntimeError, "unchanged"), {"FINISHED"})
    assert open(path, "rb").read() == old, "the old file was altered or deleted"
    res = run("export-pipeline", "export_asset.py", args)  # a real export over the old file succeeds
    assert res["exists"] and res["bytes"] > len(old) and open(path, "rb").read() != old
    glb = os.path.join(OUT["dir"], "a12_new.glb")  # a real export to a new path, then again over itself: both count
    run("export-pipeline", "export_asset.py", {"objects": ["SM_Box"], "out_path": glb})
    run("export-pipeline", "export_asset.py", {"objects": ["SM_Box"], "out_path": glb})
    return out


def _world_bbox(ob):
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    pts = [ob.matrix_world @ v.co for v in mesh.vertices]
    ev.to_mesh_clear()
    return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]


def test_a14_curve_world_space():
    fresh()
    args = {"name": "GEO_Pipe", "points": [[0, 0, 0], [4, 0, 0]], "radius": 0.1, "fill_caps": True}
    run("procedural-modeling", "gn_curve_profile.py", args)
    ob = bpy.data.objects["GEO_Pipe"]
    ob.location = (3, 2, 1)
    ob.rotation_euler = (0.2, 0.3, 0.5)
    bpy.context.view_layer.update()
    args["points"] = [[1, 1, 1], [5, 1, 1]]
    run("procedural-modeling", "gn_curve_profile.py", args)
    bb = _world_bbox(ob)
    # world path: along x from 1 to 5 at y = z = 1. The profile circle is in the curve's local frame (tilted by the
    # object rotation), so allow the radius on each side in y/z and a little at the ends.
    assert abs(bb[0][0] - 1) < 0.15 and abs(bb[0][1] - 5) < 0.15, bb
    assert abs(sum(bb[1]) / 2 - 1) < 0.02 and abs(sum(bb[2]) / 2 - 1) < 0.02, bb
    return {"world_bbox": [[round(a, 4), round(b, 4)] for a, b in bb]}


def test_a15_bevel_order():
    fresh()
    ob = cube("SM_Part")
    ob.modifiers.new("User_Mirror", "MIRROR")
    ob.modifiers.new("HS_WeightedNormal", "WEIGHTED_NORMAL")
    run("hard-surface", "bevel_stack.py", {"objects": ["SM_Part"], "triangulate": True})
    first = [m.name for m in ob.modifiers]
    assert first == ["User_Mirror", "HS_Bevel", "HS_WeightedNormal", "HS_Triangulate"], first
    ob2 = cube("SM_Part2", loc=(5, 0, 0))
    ob2.modifiers.new("HS_Triangulate", "TRIANGULATE")
    ob2.modifiers.new("HS_WeightedNormal", "WEIGHTED_NORMAL")
    ob2.modifiers.new("HS_Bevel", "BEVEL")
    run("hard-surface", "bevel_stack.py", {"objects": ["SM_Part2"], "triangulate": True})
    second = [m.name for m in ob2.modifiers]
    assert second == ["HS_Bevel", "HS_WeightedNormal", "HS_Triangulate"], second
    return {"first": first, "second": second}


def main():
    args = _cli_args()
    OUT["dir"] = args.get("out_dir", ".")
    os.makedirs(OUT["dir"], exist_ok=True)
    checks, failed = {}, []
    for fn in (test_a9_shared_mesh, test_a10_missing_objects, test_a11_lods, test_a12_export_stamp,
               test_a14_curve_world_space, test_a15_bevel_order):
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(OUT["dir"], "iter15_export_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
