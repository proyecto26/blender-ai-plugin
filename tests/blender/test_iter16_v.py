"""Headless Blender tests for iteration 16, batch V (views and round trip).

  V1  capture_views     isolate / wire / contact_sheet; hide flags, shading, object display, render settings,
                        file format and camera restored, also when a capture fails
  V2  fbx_roundtrip     identity by temporary custom property, refuses an existing file, removes only what the
                        import created, a global_scale 2 export FAILs, duplicate names and two actions PASS

Run (a NEW out_dir every time):
    blender -b --factory-startup --python tests/blender/test_iter16_v.py -- '{"out_dir": "/tmp/iter16-v"}'
Optional "skills_dir" points at another copy of the skills tree (used to run the old scripts).
Writes <out_dir>/iter16_v_report.json with passed / total / failed / checks; exits 1 on a failure.
All files the tests create are written under out_dir.
"""
import hashlib
import json
import os
import runpy
import sys
import traceback

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
ARGS = {}
if "--" in sys.argv:
    raw = sys.argv[sys.argv.index("--") + 1:]
    if raw:
        ARGS = json.loads(raw[0])
SKILLS = ARGS.get("skills_dir") or os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
OUT = ARGS.get("out_dir", ".")
os.makedirs(OUT, exist_ok=True)
_counter = [0]


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def sub(name=None):
    """A fresh folder under out_dir."""
    _counter[0] += 1
    p = os.path.join(OUT, f"{_counter[0]:02d}_{name or 'w'}")
    os.makedirs(p, exist_ok=True)
    return p


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def box(name, size=2.0, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    return o


def scene_with_wall():
    """Target cube at the origin, a wall between the front camera and it, a render camera."""
    reset()
    sc = bpy.context.scene
    target = box("Target", 2.0)
    me = bpy.data.meshes.new("Wall")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
    bm.to_mesh(me)
    bm.free()
    wall = bpy.data.objects.new("Wall", me)
    wall.rotation_euler = (1.5707963, 0, 0)  # grid in the XZ plane
    wall.location = (0, -3.0, 0)
    sc.collection.objects.link(wall)
    cam_d = bpy.data.cameras.new("UserCam")
    cam = bpy.data.objects.new("UserCam", cam_d)
    cam.location = (0, -10, 0)
    cam.rotation_euler = (1.5707963, 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return target, wall, cam


def px(path):
    img = bpy.data.images.load(path)
    try:
        a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(a)
        return a.reshape(img.size[1], img.size[0], 4), tuple(img.size)
    finally:
        bpy.data.images.remove(img)


def cv_state(target, wall):
    sc = bpy.context.scene
    r = sc.render
    return {
        "hide_render": {o.name: o.hide_render for o in bpy.data.objects},
        "hide_viewport": {o.name: o.hide_viewport for o in bpy.data.objects},
        "hide_get": {o.name: o.hide_get() for o in sc.objects},
        "display": {o.name: o.display_type for o in bpy.data.objects},
        "color": {o.name: tuple(o.color) for o in bpy.data.objects},
        "shading": (sc.display.shading.type, sc.display.shading.color_type),
        "engine": r.engine, "res": (r.resolution_x, r.resolution_y, r.resolution_percentage),
        "fmt": (r.image_settings.file_format, r.image_settings.color_depth, r.filepath),
        "camera": sc.camera.name if sc.camera else None,
        "cams": sorted(c.name for c in bpy.data.cameras), "objs": sorted(o.name for o in bpy.data.objects),
        "images": sorted(i.name for i in bpy.data.images if i.name != "Render Result"),
        "modifiers": {o.name: [m.name for m in o.modifiers] for o in bpy.data.objects},
    }


def cv_odd_state(target, wall):
    """Move every setting capture_views touches away from its default."""
    sc = bpy.context.scene
    r = sc.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1234, 567, 50
    r.image_settings.file_format = "JPEG"
    r.filepath = os.path.join(OUT, "user_render_")
    sc.display.shading.type = "RENDERED"
    sc.display.shading.color_type = "OBJECT"
    target.color = (0.2, 0.4, 0.6, 1.0)
    wall.display_type = "TEXTURED"
    target.display_type = "SOLID"
    wall.hide_render = False
    target.hide_render = False


# ----------------------------------------------------------------------------------------------- V1

def test_v1_isolate():
    target, wall, cam = scene_with_wall()
    d = sub("iso")
    plain = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["front"],
                                                              "resolution": 96})
    a, _ = px(plain["images"][0])
    d2 = sub("iso2")
    iso = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d2, "views": ["front"],
                                                            "resolution": 96, "isolate": True})
    b, _ = px(iso["images"][0])
    assert not wall.hide_render and not target.hide_render, "hide flags not restored"
    wall.hide_render = True  # reference: the wall hidden by hand
    d3 = sub("iso3")
    ref = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d3, "views": ["front"],
                                                            "resolution": 96})
    wall.hide_render = False
    c, _ = px(ref["images"][0])
    blocked = float(np.abs(a - b).mean())
    vs_ref = float(np.abs(b - c).mean())
    assert blocked > 0.02, f"the wall did not block the plain view ({blocked})"
    assert vs_ref < 0.002, f"isolated view differs from a hand-hidden reference ({vs_ref})"
    assert cam.name in bpy.context.scene.objects
    return {"plain_vs_isolated": round(blocked, 4), "isolated_vs_reference": round(vs_ref, 6)}


def test_v1_wire():
    target, wall, cam = scene_with_wall()
    wall.hide_render = True
    d = sub("wire")
    r = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["three_quarter"],
                                                          "resolution": 128, "wire": True})
    names = [os.path.basename(p) for p in r["images"]]
    assert names == ["Target_three_quarter.png", "Target_wire.png"], names
    solid, _ = px(r["images"][0])
    wired, _ = px(r["images"][1])
    bg = solid[0, 0]

    def filled(a):
        return float((np.abs(a - bg).sum(axis=2) > 0.05).mean())

    fs, fw = filled(solid), filled(wired)
    assert fw > 0.003, f"wire view is empty ({fw})"
    assert fw < fs * 0.5, f"wire view is not much emptier than the solid one ({fw} vs {fs})"
    assert target.display_type == "TEXTURED", target.display_type
    assert not target.modifiers, "wire modifier left behind"
    return {"solid_fill": round(fs, 4), "wire_fill": round(fw, 4)}


def test_v1_contact_sheet_size_and_tiles():
    target, wall, cam = scene_with_wall()
    wall.hide_render = True
    res = 64
    for views, cols, rows in ((["front", "top", "side", "back", "three_quarter"], 3, 2), (["front"], 1, 1),
                              (["front", "top", "side", "back"], 2, 2)):
        d = sub("sheet")
        r = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": views,
                                                              "resolution": res, "contact_sheet": True})
        sheet, size = px(r["contact_sheet"])
        assert size == (cols * res, rows * res), (views, size)
        assert r["contact_sheet_size"] == [cols * res, rows * res], r["contact_sheet_size"]
        # tile i (row from the top, column) matches view i
        for i, p in enumerate(r["images"]):
            tile, _ = px(p)
            c, rr = i % cols, i // cols
            y0 = (rows - 1 - rr) * res
            region = sheet[y0:y0 + res, c * res:(c + 1) * res]
            diff = float(np.abs(region[..., :3] - tile[..., :3]).mean())
            assert diff < 0.01, f"tile {i} of {views} differs from its view ({diff})"
        assert not [i for i in bpy.data.images if i.name.startswith("__capture")], "sheet image left behind"
    d = sub("sheet_wire")
    r = run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["front", "top"],
                                                          "resolution": res, "wire": True, "contact_sheet": True})
    assert len(r["images"]) == 3 and r["contact_sheet_size"] == [2 * res, 2 * res], r
    return {"five_views": "3x2", "wire_included": True}


def test_v1_restores_state():
    target, wall, cam = scene_with_wall()
    cv_odd_state(target, wall)
    other = bpy.data.objects.new("Other", bpy.data.meshes.new("OtherMe"))
    bpy.context.scene.collection.objects.link(other)
    other.hide_render = True  # already hidden by the user: must stay hidden
    before = cv_state(target, wall)
    d = sub("restore")
    run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["front", "camera"],
                                                      "resolution": 64, "isolate": True, "wire": True,
                                                      "contact_sheet": True})
    after = cv_state(target, wall)
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert other.hide_render is True
    return {"keys_compared": len(before)}


def _blocked_capture(block_name):
    target, wall, cam = scene_with_wall()
    cv_odd_state(target, wall)
    before = cv_state(target, wall)
    d = sub("fail")
    os.makedirs(os.path.join(d, block_name))  # a folder where the PNG must go: that render cannot be written
    try:
        run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["front"],
                                                          "resolution": 64, "isolate": True, "wire": True,
                                                          "contact_sheet": True})
    except RuntimeError as exc:
        err = str(exc)[:80]
    else:
        raise AssertionError("a capture that could not be written did not raise")
    after = cv_state(target, wall)
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    return err


def test_v1_restores_state_on_failed_first_view():
    return {"error": _blocked_capture("Target_front.png")}


def test_v1_restores_state_on_failed_wire_view():
    return {"error": _blocked_capture("Target_wire.png")}


def test_v1_restores_state_on_failed_sheet():
    target, wall, cam = scene_with_wall()
    cv_odd_state(target, wall)
    before = cv_state(target, wall)
    d = sub("failsheet")
    os.makedirs(os.path.join(d, "Target_sheet.png"))
    try:
        run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": d, "views": ["front"],
                                                          "resolution": 64, "isolate": True, "wire": True,
                                                          "contact_sheet": True})
    except Exception as exc:
        err = type(exc).__name__
    else:
        raise AssertionError("an unwritable sheet did not raise")
    after = cv_state(target, wall)
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    return {"error": err}


def test_v1_unknown_view_changes_nothing():
    target, wall, cam = scene_with_wall()
    before = cv_state(target, wall)
    try:
        run("blender-mcp-workflow", "capture_views.py", {"target": "Target", "out_dir": sub("bad"),
                                                          "views": ["sideways"]})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown view was accepted")
    assert cv_state(target, wall) == before
    return {"ok": True}


# ----------------------------------------------------------------------------------------------- V2

def rig(name="Rig", actions=("Idle", "Walk")):
    d = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    b1 = d.edit_bones.new("Root")
    b1.head, b1.tail = (0, 0, 0), (0, 0, 1)
    b2 = d.edit_bones.new("Arm")
    b2.head, b2.tail = (0, 0, 1), (0, 0, 2)
    b2.parent = b1
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.animation_data_create()
    made = []
    for nm in actions:
        a = bpy.data.actions.new(nm)
        arm.animation_data.action = a
        pb = arm.pose.bones["Arm"]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
        pb.keyframe_insert("rotation_euler", frame=1)
        pb.rotation_euler = (0, 0, 1)
        pb.keyframe_insert("rotation_euler", frame=10)
        made.append(a)
    if made:
        arm.animation_data.action = made[0]
    return arm


def snap():
    """Everything a round trip must leave alone: datablock names per type, custom properties, selection, active
    object, frame and the window's scene."""
    colls = ("objects", "meshes", "armatures", "materials", "images", "actions", "cameras", "lights", "curves",
             "collections", "textures", "node_groups", "scenes")
    return {
        "names": {c: sorted(i.name for i in getattr(bpy.data, c)) for c in colls},
        "props": {o.name: {k: o[k] for k in o.keys()} for o in bpy.data.objects},
        "selected": sorted(o.name for o in bpy.context.selected_objects),
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "frame": bpy.context.scene.frame_current, "window_scene": bpy.context.window.scene.name,
        "dirty_names": sorted(s.name for s in bpy.data.scenes),
    }


class fake_importer:
    """Replace bpy.ops.import_scene for the duration of a with block (fault injection)."""

    def __init__(self, fn):
        self.ns = type("FakeImportScene", (), {"fbx": staticmethod(fn)})

    def __enter__(self):
        bpy.ops.import_scene = self.ns

    def __exit__(self, *exc):
        del bpy.ops.import_scene


def fbx(**kw):
    return run("export-pipeline", "fbx_roundtrip.py", kw)


def select(*names, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for n in names:
        bpy.data.objects[n].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[active or names[0]]


def test_v2_good_roundtrip_passes_and_cleans_up():
    reset()
    box("SM_Box", 2.0, (1, 2, 3))
    box("SM_Crate", 1.0, (-4, 0, 0))
    rig()
    bpy.data.objects["SM_Box"]["user_prop"] = 7
    select("SM_Box", "SM_Crate", "Rig")
    bpy.context.scene.frame_set(4)
    before = snap()
    r = fbx(objects=["SM_Box", "SM_Crate", "Rig"], out_path=os.path.join(sub("fbx"), "good.fbx"))
    assert r["verdict"] == "PASS", json.dumps(r["objects"], indent=1)
    rigc = r["objects"]["Rig"]["checks"]
    assert rigc["bones"]["status"] == "PASS" and rigc["actions"]["status"] == "PASS", rigc
    assert rigc["actions"]["exported"] == ["Idle", "Walk"] == rigc["actions"]["imported"], rigc["actions"]
    assert r["objects"]["SM_Box"]["checks"]["dimensions"]["max_relative_difference"] < 1e-5
    after = snap()
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert os.path.isfile(r["path"])
    return {"verdict": r["verdict"], "dim_rel_diff": r["objects"]["SM_Box"]["checks"]["dimensions"]["max_relative_difference"]}


def test_v2_scaled_export_fails():
    reset()
    box("SM_Box", 2.0)
    select("SM_Box")
    before = snap()
    r = fbx(objects=["SM_Box"], global_scale=2.0, out_path=os.path.join(sub("fbx"), "scaled.fbx"))
    dim = r["objects"]["SM_Box"]["checks"]["dimensions"]
    assert r["verdict"] == "FAIL" and dim["status"] == "FAIL", r
    assert dim["max_relative_difference"] > 0.4, dim  # a factor of 2 is a relative difference of 0.5
    assert snap() == before
    return {"max_relative_difference": dim["max_relative_difference"], "tolerance": dim["tolerance"]}


def test_v2_refuses_existing_file_unless_overwrite():
    reset()
    box("SM_Box", 2.0)
    select("SM_Box")
    path = os.path.join(sub("fbx"), "exists.fbx")
    with open(path, "wb") as fh:
        fh.write(b"user data, not an fbx")
    digest = hashlib.md5(open(path, "rb").read()).hexdigest()
    before = snap()
    try:
        fbx(objects=["SM_Box"], out_path=path)
    except ValueError as exc:
        msg = str(exc)
    else:
        raise AssertionError("an existing file was not refused")
    assert hashlib.md5(open(path, "rb").read()).hexdigest() == digest, "existing file was changed"
    assert snap() == before and "overwrite" in msg
    r = fbx(objects=["SM_Box"], out_path=path, overwrite=True)
    assert r["verdict"] == "PASS" and r["bytes"] > 100
    return {"refused": msg[:70]}


def test_v2_duplicate_names_matched_by_id():
    reset()
    a = box("SM_Box", 2.0, (0, 0, 0))
    b = box("SM_Box.001", 1.0, (5, 0, 0))
    b.scale = (1.0, 2.0, 3.0)  # a different shape: pairing by name would measure the wrong object
    select("SM_Box", "SM_Box.001")
    before = snap()
    r = fbx(objects=["SM_Box", "SM_Box.001"], out_path=os.path.join(sub("fbx"), "dups.fbx"))
    assert r["verdict"] == "PASS", json.dumps(r["objects"], indent=1)
    imp_a = r["objects"]["SM_Box"]["checks"]["imported"]["imported_name"]
    imp_b = r["objects"]["SM_Box.001"]["checks"]["imported"]["imported_name"]
    assert imp_a != imp_b and "SM_Box" in imp_a and "SM_Box" in imp_b, (imp_a, imp_b)
    da = r["objects"]["SM_Box"]["checks"]["dimensions"]
    db = r["objects"]["SM_Box.001"]["checks"]["dimensions"]
    assert abs(db["imported"][2] - 3.0) < 1e-3 and abs(da["imported"][2] - 2.0) < 1e-3, (da, db)
    assert snap() == before
    return {"imported_names": [imp_a, imp_b]}


def test_v2_two_actions_one_armature():
    reset()
    rig("Rig", ("Idle", "Walk"))
    select("Rig")
    r = fbx(objects=["Rig"], out_path=os.path.join(sub("fbx"), "act.fbx"))
    c = r["objects"]["Rig"]["checks"]["actions"]
    assert r["verdict"] == "PASS" and c["exported"] == ["Idle", "Walk"] == c["imported"], c
    return c


def test_v2_no_import_match_is_fail_entry():
    """Replace the importer with one that creates nothing: every exported object is a FAIL entry naming it."""
    reset()
    box("SM_Box", 2.0)
    select("SM_Box")
    before = snap()
    with fake_importer(lambda **kw: {"FINISHED"}):
        r = fbx(objects=["SM_Box"], out_path=os.path.join(sub("fbx"), "nomatch.fbx"))
    e = r["objects"]["SM_Box"]
    assert r["verdict"] == "FAIL" and e["checks"]["imported"]["status"] == "FAIL", r
    assert "SM_Box" in e["checks"]["imported"]["reason"], e
    assert snap() == before
    return {"reason": e["checks"]["imported"]["reason"]}


def test_v2_failure_midway_restores_everything():
    reset()
    box("SM_Box", 2.0)
    select("SM_Box")
    before = snap()
    def broken(**kw):  # creates data like a half-finished import, then fails
        o = box("Half", 1.0)
        bpy.data.materials.new("HalfMat")
        bpy.data.actions.new("HalfAct")
        raise RuntimeError("injected import failure")

    try:
        with fake_importer(broken):
            fbx(objects=["SM_Box"], out_path=os.path.join(sub("fbx"), "broken.fbx"))
    except RuntimeError as exc:
        assert "injected" in str(exc)
    else:
        raise AssertionError("failure did not propagate")
    after = snap()
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    return {"restored": True}


def test_v2_existing_user_data_survives():
    """Datablocks that existed before (even ones that look like import products) are never removed."""
    reset()
    box("SM_Box", 2.0)
    mat = bpy.data.materials.new("Material.001")
    act = bpy.data.actions.new("Rig|Idle")
    mat.use_fake_user = True
    act.use_fake_user = True
    select("SM_Box")
    fbx(objects=["SM_Box"], out_path=os.path.join(sub("fbx"), "keep.fbx"))
    assert "Material.001" in bpy.data.materials and "Rig|Idle" in bpy.data.actions
    return {"kept": True}


def test_v2_refuses_existing_tag_and_non_exportable():
    reset()
    o = box("SM_Box", 2.0)
    o["bap_rt_id"] = 99
    select("SM_Box")
    try:
        fbx(objects=["SM_Box"], out_path=os.path.join(sub("fbx"), "tag.fbx"))
    except ValueError as exc:
        assert "bap_rt_id" in str(exc)
    else:
        raise AssertionError("pre-existing bap_rt_id not refused")
    assert o["bap_rt_id"] == 99
    return {"ok": True}


def test_v2_result_file_contract():
    reset()
    box("SM_Box", 2.0)
    select("SM_Box")
    d = sub("fbx")
    rp = os.path.join(d, "res.json")
    r = fbx(objects=["SM_Box"], out_path=os.path.join(d, "rf.fbx"), result_path=rp, run_id="abc")
    data = json.load(open(rp))
    assert data["run_id"] == "abc" and data["verdict"] == r["verdict"] and not os.path.exists(rp + ".tmp")
    rp2 = os.path.join(d, "res2.json")
    try:
        fbx(objects=["Nope"], out_path=os.path.join(d, "rf2.fbx"), result_path=rp2)
    except ValueError:
        pass
    assert not os.path.exists(rp2), "result written for a failed run"
    return {"run_id": data["run_id"]}


TESTS = (test_v1_isolate, test_v1_wire, test_v1_contact_sheet_size_and_tiles, test_v1_restores_state,
         test_v1_restores_state_on_failed_first_view, test_v1_restores_state_on_failed_wire_view,
         test_v1_restores_state_on_failed_sheet, test_v1_unknown_view_changes_nothing,
         test_v2_good_roundtrip_passes_and_cleans_up, test_v2_scaled_export_fails,
         test_v2_refuses_existing_file_unless_overwrite, test_v2_duplicate_names_matched_by_id,
         test_v2_two_actions_one_armature, test_v2_no_import_match_is_fail_entry,
         test_v2_failure_midway_restores_everything, test_v2_existing_user_data_survives,
         test_v2_refuses_existing_tag_and_non_exportable, test_v2_result_file_contract)


def main():
    checks, failed = {}, []
    for fn in TESTS:
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(OUT, "iter16_v_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
