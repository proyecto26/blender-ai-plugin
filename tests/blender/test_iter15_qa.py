"""Headless Blender tests for iteration 15, batch qa (blender-mcp-workflow).

  A13  fix_asset.py       arguments validated before any change; Smart UV restores mode and active object
  B1   validate_asset / clash_audit   result_path + run_id, verdict rule, FAIL tail (the process-level exit codes are in
                          tests/blender/test_iter15_exit_codes.py, which launches Blender itself)
  B2   references         every claim in the 5.x rows and the operator rules is re-measured here
  C    validate_asset     collapsed UV faces, UV overlap ratio, allow_overlap opt-out
  D    validate_asset     degenerate faces/edges, winding, inside-out shells, open shells NOT_CHECKED, scale_length
       clash_audit        within_mesh opt-in

Every fixture is built in code on the current scene and removed again; nothing is saved. Run:
    blender -b --factory-startup --python tests/blender/test_iter15_qa.py -- '{"out_dir": "<a NEW folder>"}'
Writes <out_dir>/iter15_qa_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import json
import os
import re
import runpy
import sys
import tempfile
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
WF = os.path.join(SKILLS, "blender-mcp-workflow")


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(script, args):
    g = runpy.run_path(os.path.join(WF, "scripts", script), init_globals={"ARGS": args}, run_name="__skill_test__")
    return g["result"]


def module(script):
    """The script's globals, for its helper functions; ARGS point at no object so main() itself does nothing useful."""
    ob = bpy.data.objects.new("ModProbe", None)
    bpy.context.scene.collection.objects.link(ob)
    try:
        return runpy.run_path(os.path.join(WF, "scripts", script), run_name="__skill_test__",
                              init_globals={"ARGS": {"objects": []} if script != "validate_asset.py" else {"objects": ["ModProbe"]}})
    finally:
        bpy.data.objects.remove(ob)


# ---------------------------------------------------------------------------------------------------------- fixtures
CUBE_V = [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0), (-.5, -.5, 1), (.5, -.5, 1), (.5, .5, 1), (-.5, .5, 1)]
CUBE_F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]  # outward, CCW
QUAD = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def cube_uvs(mode="grid"):
    uvs = []
    for fi in range(6):
        cu, cv = (fi % 3) / 3, (fi // 3) / 2
        for (u, v) in QUAD:
            if mode == "stacked":
                uvs.append((u, v))
            elif mode == "collapsed" and fi == 0:
                uvs.append((0.5, 0.5))
            else:
                uvs.append((cu + 0.02 + 0.29 * u, cv + 0.02 + 0.46 * v))
    return uvs


CREATED = {"objects": [], "meshes": [], "materials": []}


def mesh_obj(name, verts, faces, uvs, k=1.0, scale=(1, 1, 1), material=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x * k, y * k, z * k) for x, y, z in verts], [], faces)
    me.update()
    if uvs is not None:
        layer = me.uv_layers.new(name="UVMap")
        for li, uv in enumerate(uvs):
            layer.uv[li].vector = uv
    if material:
        mat = bpy.data.materials.new("MAT_" + name)
        me.materials.append(mat)
        CREATED["materials"].append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.scale = scale
    CREATED["objects"].append(ob)
    CREATED["meshes"].append(me)
    return ob


def tri_extra(verts, a, b, c):
    n = len(verts)
    return verts + [a, b, c], (n, n + 1, n + 2)


def fixtures(k, tag):
    """The physical fixtures, in coordinates scaled by k = 1 / scale_length so a metre is a metre at any unit scale."""
    out = {}
    good = cube_uvs()
    out["good"] = mesh_obj(f"good{tag}", CUBE_V, CUBE_F, good, k)
    flipped = [tuple(reversed(f)) for f in CUBE_F]
    out["flip_all"] = mesh_obj(f"flip_all{tag}", CUBE_V, flipped, good, k)
    one = [tuple(reversed(CUBE_F[0]))] + CUBE_F[1:]
    out["flip_one"] = mesh_obj(f"flip_one{tag}", CUBE_V, one, good, k)
    out["plane"] = mesh_obj(f"plane{tag}", [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0)], [(0, 1, 2, 3)],
                            QUAD, k)
    tri_uv = [(0.8, 0.8), (0.9, 0.8), (0.8, 0.9)]
    for key, c in (("sliver", (1e-4, 2e-7)), ("short_edge", (1.0, 5e-8))):  # (long edge, short edge) in metres
        v, t = tri_extra(list(CUBE_V), (0, 0, 2), (c[0], 0, 2), (0, c[1], 2))
        if key == "short_edge":
            v[-2] = (1.0, 0, 2)
            v[-1] = (0, 5e-8, 2)
        out[key] = mesh_obj(f"{key}{tag}", v, CUBE_F + [t], good + tri_uv, k)
    out["uv_stacked"] = mesh_obj(f"uv_stacked{tag}", CUBE_V, CUBE_F, cube_uvs("stacked"), k)
    out["uv_collapsed"] = mesh_obj(f"uv_collapsed{tag}", CUBE_V, CUBE_F, cube_uvs("collapsed"), k)
    out["mirrored"] = mesh_obj(f"mirrored{tag}", CUBE_V, CUBE_F, good, k, scale=(-1, 1, 1))
    return out


def statuses(res, name):
    return {c: v["status"] for c, v in res["objects"][name]["checks"].items()}


def validate(names, **kw):
    return run("validate_asset.py", {"objects": names, "prefix": "", **kw})


def cleanup():
    for ob in CREATED["objects"]:
        if ob.name in bpy.data.objects:
            bpy.data.objects.remove(ob, do_unlink=True)
    for key in ("meshes", "materials"):
        for d in CREATED[key]:
            coll = getattr(bpy.data, key)
            if d.name in coll:
                coll.remove(d)
    for key in CREATED:
        CREATED[key].clear()


GEOM = ("degenerate_faces", "degenerate_edges", "winding", "orientation", "uv_collapsed", "uv_overlap")


# ------------------------------------------------------------------------------------------------------------ tests
def test_d_geometry_and_scale():
    """D: every defect fixture gets the expected check statuses, identical at scale_length 1.0 and 0.01."""
    scene = bpy.context.scene
    seen = {}
    original = scene.unit_settings.scale_length
    try:
        for s in (1.0, 0.01):
            scene.unit_settings.scale_length = s
            fx = fixtures(1.0 / s, f"_s{int(s * 100)}")
            res = validate([o.name for o in fx.values()])
            seen[s] = {k: {"status": statuses(res, o.name), "verdict": res["objects"][o.name]["verdict"],
                           "not_checked": sorted(res["objects"][o.name]["not_checked"])} for k, o in fx.items()}
            seen[s]["stacked_allowed"] = validate([fx["uv_stacked"].name], allow_overlap=True)["objects"][
                fx["uv_stacked"].name]["checks"]["uv_overlap"]
            cleanup()
    finally:
        scene.unit_settings.scale_length = original
        cleanup()
    assert seen[1.0] == seen[0.01], {"scale_1.0": seen[1.0], "scale_0.01": seen[0.01]}
    r = seen[1.0]
    for key in ("good",):
        assert all(r[key]["status"][c] == "PASS" for c in GEOM), r[key]
        assert r[key]["verdict"] == "PASS", r[key]
    assert r["flip_all"]["status"]["orientation"] == "FAIL" and r["flip_all"]["status"]["winding"] == "PASS", r["flip_all"]
    assert r["flip_one"]["status"]["winding"] == "FAIL" and r["flip_one"]["status"]["orientation"] == "NOT_CHECKED", r["flip_one"]
    assert r["plane"]["status"]["orientation"] == "NOT_CHECKED" and r["plane"]["verdict"] != "PASS", r["plane"]
    assert "orientation" in r["plane"]["not_checked"], r["plane"]
    assert r["sliver"]["status"]["degenerate_faces"] == "FAIL" and r["sliver"]["status"]["degenerate_edges"] == "PASS", r["sliver"]
    assert r["short_edge"]["status"]["degenerate_edges"] == "FAIL" and r["short_edge"]["status"]["degenerate_faces"] == "PASS", r["short_edge"]
    assert r["uv_stacked"]["status"]["uv_overlap"] == "FAIL" and r["uv_stacked"]["status"]["uv_collapsed"] == "PASS", r["uv_stacked"]
    assert r["stacked_allowed"]["status"] == "PASS" and "allow_overlap" in r["stacked_allowed"]["detail"], r["stacked_allowed"]
    assert r["uv_collapsed"]["status"]["uv_collapsed"] == "FAIL" and r["uv_collapsed"]["status"]["uv_overlap"] == "PASS", r["uv_collapsed"]
    assert r["mirrored"]["status"]["orientation"] == "PASS", ("a mirrored object renders correctly", r["mirrored"])
    for key in ("flip_all", "flip_one", "sliver", "short_edge", "uv_stacked", "uv_collapsed"):
        assert r[key]["verdict"] == "FAIL", (key, r[key])
    return {"verdicts": {k: v["verdict"] for k, v in r.items() if isinstance(v, dict) and "verdict" in v},
            "same_at_both_scales": True}


def test_d_world_space():
    """D: areas are measured in world space (object scale counts), not on the local mesh."""
    tri = [(0, 0, 2), (1e-4, 0, 2), (0, 1.2e-6, 2)]  # local area 6e-11 m2 (below the 1e-10 threshold)
    big = [(0, 0, 2), (1e-4, 0, 2), (0, 4e-6, 2)]    # local area 2e-10 m2 (above it)
    a = mesh_obj("ws_grow", tri, [(0, 1, 2)], [(0.1, 0.1), (0.2, 0.1), (0.1, 0.2)], scale=(2, 1, 1))
    b = mesh_obj("ws_shrink", big, [(0, 1, 2)], [(0.1, 0.1), (0.2, 0.1), (0.1, 0.2)], scale=(0.25, 1, 1))
    try:
        res = validate([a.name, b.name])
        grow, shrink = statuses(res, a.name)["degenerate_faces"], statuses(res, b.name)["degenerate_faces"]
    finally:
        cleanup()
    assert grow == "PASS" and shrink == "FAIL", (grow, shrink)
    return {"local 6e-11 scaled x2": grow, "local 2e-10 scaled x0.25": shrink}


def test_verdict_rule():
    """Object = FAIL if any FAIL, else WARN if any WARN or NOT_CHECKED, else PASS; measured nothing = FAIL."""
    agg = module("validate_asset.py")["_aggregate"]
    table = {("PASS", "PASS"): "PASS", ("PASS", "NOT_CHECKED"): "WARN", ("NOT_CHECKED", "WARN"): "WARN",
             ("NOT_CHECKED", "FAIL"): "FAIL", ("WARN", "FAIL"): "FAIL"}
    got = {k: agg(k) for k in table}
    assert got == table, got
    assert agg([]) == "PASS" and agg(["NOT_CHECKED"]) == "WARN"
    empty = bpy.data.objects.new("EmptyNotMesh", None)
    bpy.context.scene.collection.objects.link(empty)
    try:
        res = validate([empty.name])
    finally:
        bpy.data.objects.remove(empty)
    assert res["verdict"] == "FAIL" and res["note"], res
    # a closed cube whose only non-PASS check is NOT_CHECKED must come out WARN: UVs that span more than 16 tiles are not
    # rasterized, and one UV loop far outside 0-1 also warns; check the NOT_CHECKED path on its own with the overlap check
    far = cube_uvs()
    far[0] = (40.0, 40.0)
    ob = mesh_obj("nc_cube", CUBE_V, CUBE_F, far)
    try:
        res = validate([ob.name])["objects"][ob.name]
    finally:
        cleanup()
    assert res["checks"]["uv_overlap"]["status"] == "NOT_CHECKED", res["checks"]["uv_overlap"]
    assert "uv_overlap" in res["not_checked"] and res["verdict"] != "PASS", res
    return {"aggregation": {f"{a}+{b}": v for (a, b), v in got.items()}, "empty_verdict": "FAIL"}


def test_c_uv_ratio_values():
    """C: the measured overlap ratio of the fixtures sits far from the 1% threshold on both sides."""
    mod = module("validate_asset.py")
    import numpy as np

    def ratio(mode):
        uvs = np.array(cube_uvs(mode)).reshape(6, 4, 2)
        tris = np.concatenate([uvs[:, [0, 1, 2]], uvs[:, [0, 2, 3]]])
        tris = tris[0.5 * np.abs(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])) >= 1e-12]
        return mod["_uv_overlap"](tris)[0]
    good, stacked = ratio("grid"), ratio("stacked")
    assert good == 0.0 and stacked > 0.5, (good, stacked)
    assert mod["MIN_UV_AREA"] == 1e-12 and mod["UV_OVERLAP_FAIL"] == 0.01
    return {"grid_ratio": good, "stacked_ratio": round(stacked, 4), "fail_above": 0.01}


def test_d_clash_within_mesh():
    """D: within_mesh is opt-in; islands of one mesh then count like separate objects."""
    def two_cubes(name, gap):
        v = [(x, y, z) for x, y, z in CUBE_V] + [(x + gap, y, z) for x, y, z in CUBE_V]
        f = CUBE_F + [tuple(i + 8 for i in face) for face in CUBE_F]
        return mesh_obj(name, v, f, None, material=False)

    def squares(name, dz):
        v = [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0)]
        v = v + [(x, y, z + dz) for x, y, z in v]
        return mesh_obj(name, v, [(0, 1, 2, 3), (4, 5, 6, 7)], None, material=False)
    out = {}
    try:
        far = two_cubes("wm_far", 3.0)          # 2 m of air between the cubes
        cross = two_cubes("wm_cross", 0.5)      # half-overlapping cubes
        flat = squares("wm_flat", 0.0005)       # coplanar squares 0.5 mm apart
        touch = two_cubes("wm_touch", 1.0)      # face to face, a normal modelled join
        for ob in (far, cross, flat, touch):
            default = run("clash_audit.py", {"objects": [ob.name]})
            within = run("clash_audit.py", {"objects": [ob.name], "within_mesh": True})
            out[ob.name] = {"default": default["verdict"], "within_mesh": within["verdict"],
                            "floating": len(within["floating"]), "clashes": len(within["clashes"]),
                            "kinds": [c.get("depth", c.get("depth_m")) for c in within["clashes"]]}
        loose = run("clash_audit.py", {"objects": [far.name], "within_mesh": True, "require_connected": False})
        out["far_require_connected_false"] = loose["verdict"]
        names = run("clash_audit.py", {"objects": [far.name], "within_mesh": True})["groups"]
    finally:
        cleanup()
    assert all(v["default"] == "PASS" for k, v in out.items() if isinstance(v, dict)), out
    assert out["wm_far"]["within_mesh"] == "FAIL" and out["wm_far"]["floating"] == 1, out
    assert out["far_require_connected_false"] == "PASS", out
    assert out["wm_cross"]["within_mesh"] == "FAIL" and out["wm_cross"]["clashes"] >= 1, out
    assert out["wm_flat"]["within_mesh"] == "FAIL" and "coincident" in out["wm_flat"]["kinds"], out
    assert out["wm_touch"]["within_mesh"] == "PASS", out
    assert names == [["wm_far#1"], ["wm_far#2"]] or sorted(map(sorted, names)) == [["wm_far#1"], ["wm_far#2"]], names
    return out


def test_b1_result_file():
    """B1 (in-process part): result_path gets the result plus run_id, atomically; a run that raises writes nothing."""
    d = tempfile.mkdtemp(prefix="iter15-result-")
    good = mesh_obj("SM_ResGood", CUBE_V, CUBE_F, cube_uvs())
    try:
        path = os.path.join(d, "r.json")
        res = run("validate_asset.py", {"objects": [good.name], "result_path": path, "run_id": "abc"})
        doc = json.load(open(path))
        assert doc["run_id"] == "abc" and doc["verdict"] == res["verdict"] == "PASS" and "objects" in doc, doc
        assert not os.path.exists(path + ".tmp")
        cpath = os.path.join(d, "c.json")
        cres = run("clash_audit.py", {"objects": [good.name], "result_path": cpath, "run_id": "xyz"})
        cdoc = json.load(open(cpath))
        assert cdoc["run_id"] == "xyz" and cdoc["verdict"] == cres["verdict"], cdoc
        # a run that raises leaves an earlier file untouched and writes no new one
        for script in ("validate_asset.py", "clash_audit.py"):
            stale = os.path.join(d, f"stale_{script}.json")
            json.dump({"run_id": "old"}, open(stale, "w"))
            try:
                run(script, {"objects": ["NoSuchObject"], "result_path": stale, "run_id": "new"})
            except ValueError:
                pass
            else:
                raise AssertionError(f"{script} did not raise for a missing object")
            assert json.load(open(stale)) == {"run_id": "old"}, script
            fresh = os.path.join(d, f"never_{script}.json")
            try:
                run(script, {"objects": ["NoSuchObject"], "result_path": fresh, "run_id": "new"})
            except ValueError:
                pass
            assert not os.path.exists(fresh), script
        # the live (runpy) call must never exit the interpreter on FAIL: only a background `__main__` run does
        bad = mesh_obj("BadResult", CUBE_V, CUBE_F, cube_uvs(), material=False)
        assert run("validate_asset.py", {"objects": [bad.name]})["verdict"] == "FAIL"
    finally:
        cleanup()
    return {"run_id_echoed": True, "failed_run_writes_nothing": True, "folder": d}


def test_a13_fix_asset():
    """A13: bad arguments change nothing; Smart UV puts mode and active object back, also when it fails."""
    import bmesh

    def plain(name, scale):
        ob = mesh_obj(name, CUBE_V, CUBE_F, None, scale=scale, material=False)
        return ob

    def state(ob):
        return (tuple(ob.scale), len(ob.data.uv_layers), [tuple(round(c, 6) for c in v.co) for v in ob.data.vertices])
    out = {}
    try:
        for label, kw in (("uv_unknown", {"uv": "bogus"}), ("uv_scale_zero", {"uv": "box", "uv_scale": 0}),
                          ("uv_scale_negative", {"uv": "box", "uv_scale": -1.0}), ("uv_scale_nan", {"uv": "box", "uv_scale": float("nan")}),
                          ("apply_unknown", {"apply": "all"})):
            ob = plain(f"fa_{label}", (2, 1, 1))
            before = state(ob)
            try:
                run("fix_asset.py", {"objects": [ob.name], **kw})
            except ValueError as exc:
                out[label] = str(exc)[:60]
            else:
                raise AssertionError(f"{label}: no ValueError")
            assert state(ob) == before, (label, before, state(ob))
        # Smart UV: restores Object Mode and the active object
        other = plain("fa_other", (1, 1, 1))
        target = plain("fa_smart", (1, 1, 1))
        bpy.context.view_layer.objects.active = other
        r = run("fix_asset.py", {"objects": [target.name], "uv": "smart", "apply": ""})
        assert r["objects"][target.name]["uv_added"] == "smart" and target.mode == "OBJECT", r
        assert bpy.context.view_layer.objects.active is other, "active object not restored"
        # Smart UV that cannot run (a mesh with no faces): raises, and still restores mode and active object
        empty_me = bpy.data.meshes.new("fa_empty")
        empty = bpy.data.objects.new("fa_empty", empty_me)
        bpy.context.scene.collection.objects.link(empty)
        CREATED["objects"].append(empty)
        CREATED["meshes"].append(empty_me)
        bpy.context.view_layer.objects.active = other
        err = None
        try:
            run("fix_asset.py", {"objects": [empty.name], "uv": "smart", "apply": ""})
        except Exception as exc:  # noqa: BLE001 - the type is Blender's to choose; the state afterwards is the test
            err = type(exc).__name__
        out["empty_mesh_smart"] = {"raised": err, "mode": empty.mode,
                                   "active_restored": bpy.context.view_layer.objects.active is other}
        assert err is not None and empty.mode == "OBJECT" and out["empty_mesh_smart"]["active_restored"], out
        # the working paths still work
        ok = plain("fa_box", (2, 1, 1))
        res = run("fix_asset.py", {"objects": [ok.name], "uv": "box", "uv_scale": 0.5})["objects"][ok.name]
        assert res["uv_added"] == "box" and res["scale"] == [1.0, 1.0, 1.0], res
    finally:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        cleanup()
    return out


def test_b2_rows():
    """B2: each 5.x row and operator rule written in the references is re-measured on this Blender."""
    out = {"blender": bpy.app.version_string}
    # Boolean solver enum
    items = [e.identifier for e in bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items]
    assert items == ["FLOAT", "EXACT", "MANIFOLD"], items
    ob = bpy.data.objects.new("b2_bool", bpy.data.meshes.new("b2_bool"))
    bpy.context.scene.collection.objects.link(ob)
    CREATED["objects"].append(ob)
    CREATED["meshes"].append(ob.data)
    mod = ob.modifiers.new("B", "BOOLEAN")
    try:
        mod.solver = "FAST"
    except TypeError:
        out["FAST_rejected"] = True
    else:
        raise AssertionError("solver 'FAST' still accepted")
    out["solver"] = items
    # UV select sync
    ts = bpy.context.scene.tool_settings
    assert hasattr(ts, "use_uv_select_sync") and "uv_select_mode" in ts.bl_rna.properties
    old = ts.use_uv_select_sync
    ts.use_uv_select_sync = not old
    assert ts.use_uv_select_sync is (not old)
    ts.use_uv_select_sync = old
    out["uv_select_mode"] = [e.identifier for e in ts.bl_rna.properties["uv_select_mode"].enum_items]
    # Bone selection
    assert not hasattr(bpy.types.Bone, "select") and "select" in bpy.types.PoseBone.bl_rna.properties
    assert {"select", "select_head", "select_tail"} <= set(bpy.types.EditBone.bl_rna.properties.keys())
    out["bone_select"] = {"Bone.select": False, "PoseBone.select": True, "EditBone": ["select", "select_head", "select_tail"]}
    # Action slots
    act = bpy.data.actions.new("b2_act")
    slot = act.slots.new("OBJECT", "Slot")
    ob.animation_data_create()
    ob.animation_data.action = act
    assert ob.animation_data.action_slot is None, "assigning an action does not pick a slot"
    ob.animation_data.action_slot = slot
    assert ob.animation_data.action_slot == slot
    ob2 = bpy.data.objects.new("b2_key", bpy.data.meshes.new("b2_key"))
    bpy.context.scene.collection.objects.link(ob2)
    CREATED["objects"].append(ob2)
    CREATED["meshes"].append(ob2.data)
    ob2.keyframe_insert("location", frame=1)
    auto = ob2.animation_data.action.slots[0].identifier
    assert auto == "OBb2_key", auto
    out["action_slots"] = {"identifier": slot.identifier, "auto_slot_on_keyframe": auto}
    # operators: a result is a set; CANCELLED can come back without an exception
    res = bpy.ops.mesh.primitive_cube_add()
    assert res == {"FINISHED"}, res
    CREATED["objects"].append(bpy.context.object)
    CREATED["meshes"].append(bpy.context.object.data)
    import bmesh  # noqa: F401
    empty_me = bpy.data.meshes.new("b2_empty")
    empty = bpy.data.objects.new("b2_empty", empty_me)
    bpy.context.scene.collection.objects.link(empty)
    CREATED["objects"].append(empty)
    CREATED["meshes"].append(empty_me)
    bpy.context.view_layer.objects.active = empty
    results = {}
    try:
        with bpy.context.temp_override(active_object=empty, object=empty, selected_objects=[empty],
                                       selected_editable_objects=[empty]):
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            try:
                bpy.ops.uv.smart_project()
            except RuntimeError as exc:
                results["smart_project_on_mesh_without_faces"] = "RuntimeError (poll failed)"
                assert "poll() failed" in str(exc), exc
            else:
                raise AssertionError("smart_project on a mesh without faces did not raise")
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.objects.active = cube = CREATED["objects"][-2]
        with bpy.context.temp_override(active_object=cube, object=cube, selected_objects=[cube],
                                       selected_editable_objects=[cube]):
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="DESELECT")
            cancelled = bpy.ops.mesh.bevel(offset=0.1)  # nothing selected: no work, and no exception either
            assert cancelled == {"CANCELLED"}, cancelled
            results["bevel_with_nothing_selected"] = sorted(cancelled)
    finally:
        for o in (empty, CREATED["objects"][-2]):
            if o.mode != "OBJECT":
                with bpy.context.temp_override(active_object=o, object=o):
                    bpy.ops.object.mode_set(mode="OBJECT")
    out["operator_without_work"] = results
    # the enum discovery snippet in references/mcp-tools.md runs as written and agrees with the measurement above
    text = open(os.path.join(WF, "references", "mcp-tools.md"), encoding="utf8").read()
    block = next(b for b in re.findall(r"```python\n(.*?)```", text, re.S) if "enum_items" in b)
    g = {}
    exec(compile(block, "mcp-tools-enum-snippet", "exec"), g)
    assert g.get("choices") == ["FLOAT", "EXACT", "MANIFOLD"], g.get("choices")
    # the docs say what was measured
    api = open(os.path.join(WF, "references", "blender-5-api-notes.md"), encoding="utf8").read()
    for needle in ("FLOAT", "MANIFOLD", "use_uv_select_sync", "EditBone", "PoseBone", "action_slot", "OB<"):
        assert needle in api, f"blender-5-api-notes.md lacks {needle}"
    assert "{'FINISHED'}" in text and "CANCELLED" in text, "mcp-tools.md lacks the FINISHED rule"
    cleanup()
    return out


def test_docs_headless():
    """B1 docs: SKILL.md documents the exact headless call and the acceptance rule; scripts take the new ARGS."""
    skill = open(os.path.join(WF, "SKILL.md"), encoding="utf8").read()
    for needle in ("--python-exit-code 1", "--args-file", "result_path", "run_id", "exit code is 0 or 2"):
        assert needle in skill, f"SKILL.md lacks {needle!r}"
    for script in ("validate_asset.py", "clash_audit.py"):
        src = open(os.path.join(WF, "scripts", script), encoding="utf8").read()
        assert "result_path" in src and "run_id" in src and "sys.exit(2)" in src, script
    return {"checked": 7}


def main():
    args = _cli_args()
    out_dir = args.get("out_dir", ".")
    os.makedirs(out_dir, exist_ok=True)
    checks, failed = {}, []
    tests = (test_d_geometry_and_scale, test_d_world_space, test_verdict_rule, test_c_uv_ratio_values,
             test_d_clash_within_mesh, test_b1_result_file, test_a13_fix_asset, test_b2_rows, test_docs_headless)
    for fn in tests:
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()[-1500:]}
            failed.append(fn.__name__)
            cleanup()
    report = {"blender": bpy.app.version_string, "passed": len(checks) - len(failed), "total": len(checks),
              "failed": failed, "checks": checks}
    with open(os.path.join(out_dir, "iter15_qa_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    sys.exit(1 if failed else 0)


main()
