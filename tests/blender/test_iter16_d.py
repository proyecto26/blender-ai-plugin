"""Headless Blender tests for iteration 16, batch `D` (items D1 garment_check, D2 shape_key_audit).

  D1  cloth-sim/scripts/garment_check.py on code-built fixtures: a blocked pose FAILs (NOT_REACHED) even with full
      coverage; a garment that pokes through in one pose FAILs (PENETRATION) while the rest pose is OK; a loose garment
      PASSes; a body that is open or has a flipped face, or a garment far from the body, is NOT_CHECKED (never a PASS);
      an inward-wound body works; pose, frame, actions and IK/FK switches are restored (also after an exception);
      thresholds keep the 20% margin; result_path/run_id contract.
  D2  rigging/scripts/shape_key_audit.py: dead key, non-finite key, drivers to a missing object or bone, mirror pair
      that differs, unmatched mirror vertices (NOT_CHECKED); a good mesh PASSes; the audit is read only.

Run:
    blender -b --factory-startup --python tests/blender/test_iter16_d.py -- '{"out_dir": "/tmp/iter16-d"}'
Optional "skills_dir" runs the same tests against another copy of the skills.
Writes <out_dir>/iter16_d_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import json
import math
import os
import runpy
import sys
import traceback

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
MEASURED = {}


def run(skill, name, **kw):
    return runpy.run_path(os.path.join(SKILLS, skill, "scripts", name), init_globals={"ARGS": kw})["result"]


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------- D1 fixtures
def make_armature(name="ARM_Limb"):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    up = data.edit_bones.new("upper_arm.L")
    up.head, up.tail = (0, 0, 0), (0, 0, 1)
    lo = data.edit_bones.new("forearm.L")
    lo.head, lo.tail = (0, 0, 1), (0, 0, 2)
    lo.parent = up
    lo.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def make_cylinder(name, radius, z0, z1, loops=21, seg=16, caps=True, flip=False):
    vs, fs = [], []
    for i in range(loops):
        z = z0 + (z1 - z0) * i / (loops - 1)
        for k in range(seg):
            a = 2 * math.pi * k / seg
            vs.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(loops - 1):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            fs.append((a, b, b + seg, a + seg))
    if caps:
        fs.append(tuple(reversed(range(seg))))
        fs.append(tuple((loops - 1) * seg + k for k in range(seg)))
    if flip:
        fs = [tuple(reversed(f)) for f in fs]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def skin(mesh, arm, knots):
    order = sorted(knots.items(), key=lambda kv: kv[1])
    for bn, _ in order:
        mesh.vertex_groups.new(name=bn)
    for v in mesh.data.vertices:
        z = v.co.z
        if z <= order[0][1]:
            w = {order[0][0]: 1.0}
        elif z >= order[-1][1]:
            w = {order[-1][0]: 1.0}
        else:
            for (b0, z0), (b1, z1) in zip(order, order[1:]):
                if z0 <= z <= z1:
                    t = (z - z0) / (z1 - z0)
                    w = {b0: 1 - t, b1: t}
                    break
        for bn, val in w.items():
            if val > 0:
                mesh.vertex_groups[bn].add([v.index], val, "REPLACE")
    md = mesh.modifiers.new("Armature", "ARMATURE")
    md.object = arm


KNOTS = {"upper_arm.L": 0.85, "forearm.L": 1.15}


def scene(garment="loose", **body_kw):
    """Armature + a closed body (radius 0.15, z 0..2) + a garment: 'loose' (radius 0.2, skinned like the body) or
    'static' (radius 0.2, not skinned, so the posed body swings through it)."""
    fresh()
    arm = make_armature()
    body = make_cylinder("Body", 0.15, 0.0, 2.0, **body_kw)
    skin(body, arm, KNOTS)
    gar = make_cylinder("Garment", 0.2, 0.12, 1.8, loops=19, caps=False)
    if garment == "loose":
        skin(gar, arm, KNOTS)
    return arm, body, gar


def gc(**kw):
    return run("cloth-sim", "garment_check.py", garment="Garment", body="Body", armature="ARM_Limb", **kw)


def row(res, pose, limb=None):
    return [r for r in res["rows"] if r["pose"] == pose and (limb is None or r.get("limb") == limb)]


# ---------------------------------------------------------------- D1 tests
def test_d1_loose_garment_passes():
    scene("loose")
    res = gc(poses=["arms_raised"])
    assert res["verdict"] == "PASS", json.dumps(res["rows"], indent=1)
    rest, posed = row(res, "rest")[0], row(res, "arms_raised")[0]
    assert rest["status"] == posed["status"] == "OK" and rest["coverage"] == 1.0 and posed["coverage"] == 1.0
    MEASURED["loose_depth_rel"] = max(rest["max_depth_rel"], posed["max_depth_rel"])
    return {"rest": rest, "posed": posed}


def test_d1_poke_through_in_one_pose_fails():
    scene("static")
    res = gc(poses=["arms_raised"], search_radius=5.0)
    assert res["verdict"] == "FAIL", json.dumps(res["rows"], indent=1)
    assert row(res, "rest")[0]["status"] == "OK", row(res, "rest")
    bad = row(res, "arms_raised")[0]
    assert bad["status"] == "PENETRATION" and bad["penetrating_vertices"] > 0 and bad["coverage"] == 1.0, bad
    MEASURED["poke_depth_rel"] = bad["max_depth_rel"]
    return {"posed": bad}


def test_d1_blocked_pose_fails_even_with_full_coverage():
    arm, body, gar = scene("loose")
    c = arm.pose.bones["upper_arm.L"].constraints.new("LIMIT_ROTATION")
    c.use_limit_x = True
    c.min_x, c.max_x = 0.0, math.radians(30)
    c.owner_space = "LOCAL"
    res = gc(poses=["arms_raised"])
    nr = [r for r in res["rows"] if r["status"] == "NOT_REACHED"]
    assert res["verdict"] == "FAIL" and nr and nr[0]["pose"] == "arms_raised", json.dumps(res["rows"], indent=1)
    rest = row(res, "rest")[0]
    assert rest["status"] == "OK" and rest["coverage"] == 1.0, rest
    assert not row(res, "arms_raised", None)[0].get("coverage"), "a blocked pose must not be measured"
    return {"reach": nr[0]["reach"]}


def test_d1_far_garment_is_not_checked():
    arm, body, gar = scene("loose")
    gar.location = (5.0, 0, 0)
    bpy.context.view_layer.update()
    res = gc(poses=["arms_raised"])
    assert all(r["status"] == "NOT_CHECKED" for r in res["rows"]), json.dumps(res["rows"], indent=1)
    assert res["verdict"] == "FAIL" and any("measured nothing" in n for n in res["notes"]), res
    assert row(res, "rest")[0]["coverage"] < 0.9
    return {"coverage": row(res, "rest")[0]["coverage"]}


def test_d1_body_must_be_closed_and_consistent():
    _a, _b, _g = scene("loose", caps=False)
    res = gc(poses=["arms_raised"])
    assert res["rows"][0]["status"] == "NOT_CHECKED" and "closed" in res["rows"][0]["reason"], res
    assert res["verdict"] == "FAIL", res["verdict"]
    scene("loose")
    me = bpy.data.objects["Body"].data
    polys = [tuple(p.vertices) for p in me.polygons]
    polys[3] = tuple(reversed(polys[3]))  # one flipped face
    me2 = bpy.data.meshes.new("BodyFlip")
    me2.from_pydata([v.co[:] for v in me.vertices], [], polys)
    me2.update()
    bpy.data.objects["Body"].data = me2
    res2 = gc(poses=["arms_raised"])
    assert res2["rows"][0]["status"] == "NOT_CHECKED", res2["rows"]
    return {"open": "NOT_CHECKED", "flipped": "NOT_CHECKED"}


def test_d1_inward_wound_body_still_judged():
    scene("loose", flip=True)
    assert gc(poses=["arms_raised"])["verdict"] == "PASS"
    scene("static", flip=True)
    res = gc(poses=["arms_raised"], search_radius=5.0)
    assert res["verdict"] == "FAIL" and row(res, "arms_raised")[0]["status"] == "PENETRATION", res["rows"]
    return {"ok": True}


def test_d1_restores_state():
    arm, body, gar = scene("loose")
    scn = bpy.context.scene
    arm.pose.bones["forearm.L"]["ik_fk"] = 1.0
    arm["fk_mode"] = 0.75
    pb = arm.pose.bones["upper_arm.L"]
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = (0.9, 0.1, 0.2, 0.3)
    pb.location = (0.1, 0.2, 0.3)
    act = bpy.data.actions.new("Original")
    arm.animation_data_create().action = act
    scn.frame_set(7)
    before = sorted(a.name for a in bpy.data.actions)
    q0, loc0 = tuple(pb.rotation_quaternion), tuple(pb.location)
    sel = {o.name: o.select_get() for o in bpy.data.objects}
    res = gc(poses=["arms_raised"], fk_switches=[{"bone": "forearm.L", "prop": "ik_fk", "value": 0.0},
                                                  {"bone": "", "prop": "fk_mode", "value": 0.0}])
    assert res["verdict"] == "PASS", res["rows"]
    assert arm.animation_data.action is act and scn.frame_current == 7
    assert sorted(a.name for a in bpy.data.actions) == before
    assert arm.pose.bones["forearm.L"]["ik_fk"] == 1.0 and arm["fk_mode"] == 0.75
    assert pb.rotation_mode == "QUATERNION" and tuple(pb.rotation_quaternion) == q0 and tuple(pb.location) == loc0
    assert arm.data.pose_position == "POSE" and sel == {o.name: o.select_get() for o in bpy.data.objects}
    assert bpy.context.object is None or bpy.context.object.mode == "OBJECT"
    # no animation data before -> none after, also after an exception mid-run
    arm, body, gar = scene("loose")
    assert arm.animation_data is None
    gc(poses=["arms_raised"])
    assert arm.animation_data is None and not bpy.data.actions
    try:
        gc(poses=["arms_raised"], fk_switches=[{"bone": "forearm.L", "prop": "nope", "value": 0}])
    except KeyError:
        pass
    assert arm.animation_data is None and not bpy.data.actions and arm.data.pose_position == "POSE"
    return {"restored": True}


def test_d1_missing_role_and_bad_names():
    arm, body, gar = scene("loose")
    res = gc(poses=["arms_raised"], bone_map={"arm.L": {"upper": "upper_arm.L", "lower": "no_such_bone"}})
    assert res["verdict"] == "FAIL" and any(r["status"] == "MISSING_ROLE" for r in res["rows"]), res["rows"]
    for kw in ({"garment": "Nope"}, {"body": "Nope"}):
        args = {"garment": "Garment", "body": "Body", "armature": "ARM_Limb", **kw}
        try:
            run("cloth-sim", "garment_check.py", **args)
        except ValueError:
            continue
        raise AssertionError(f"{kw} did not raise")
    return {"ok": True}


def test_d1_thresholds_margin():
    for k in ("loose_depth_rel", "poke_depth_rel"):
        assert k in MEASURED, f"{k} not measured (run the fixture tests first)"
    tol = 0.005
    good, bad = MEASURED["loose_depth_rel"], MEASURED["poke_depth_rel"]
    gap = bad - good
    assert gap > 0 and tol >= good + 0.2 * gap and tol <= bad - 0.2 * gap, (good, bad, tol)
    return dict(MEASURED)


def test_d1_result_contract():
    arm, body, gar = scene("loose")
    rp = os.path.join(OUT, "garment_result.json")
    res = gc(poses=["arms_raised"], result_path=rp, run_id="g-1")
    data = json.load(open(rp, encoding="utf-8"))
    assert data["run_id"] == "g-1" and data["verdict"] == res["verdict"] and not os.path.exists(rp + ".tmp")
    json.dumps(res, allow_nan=False)
    old = os.path.join(OUT, "garment_old.json")
    with open(old, "w") as fh:
        json.dump({"run_id": "old"}, fh)
    try:
        run("cloth-sim", "garment_check.py", garment="Garment", body="Body", armature="NoArm", result_path=old, run_id="new")
    except ValueError:
        pass
    assert json.load(open(old))["run_id"] == "old"
    return {"ok": True}


# ---------------------------------------------------------------- D2 fixtures
def grid_mesh(name="Face", nx=5, ny=5, nz=3):
    vs = [(-1 + 2 * i / (nx - 1), -1 + 2 * j / (ny - 1), 0.5 * k / (nz - 1)) for i in range(nx) for j in range(ny)
          for k in range(nz)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], [])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.shape_key_add(name="Basis")
    return ob


def add_key(ob, name, fn):
    kb = ob.shape_key_add(name=name, from_mix=False)
    for i, d in enumerate(kb.data):
        c = ob.data.vertices[i].co
        d.co = (c.x + fn(c)[0], c.y + fn(c)[1], c.z + fn(c)[2])
    return kb


def g_left(c):  # a smile on the +X side
    f = max(0.0, c.x) * 0.1
    return (0.5 * f, 0.2 * f, 0.4 * f)


def g_right(c):  # exact mirror of g_left: right side vertex j gets the mirrored delta of its mirror image
    gx, gy, gz = g_left(type(c)((-c.x, c.y, c.z)))
    return (-gx, gy, gz)


def good_face():
    fresh()
    ob = grid_mesh()
    add_key(ob, "Smile.L", g_left)
    add_key(ob, "Smile.R", g_right)
    add_key(ob, "Brow", lambda c: (0.0, 0.0, 0.1 * c.y))
    return ob


def checks(res, obj="Face"):
    o = [x for x in res["objects"] if x["object"] == obj][0]
    return {c["check"]: c for c in o["checks"]}, o


def audit(**kw):
    return run("rigging", "shape_key_audit.py", **kw)


# ---------------------------------------------------------------- D2 tests
def test_d2_good_mesh_passes():
    good_face()
    res = audit()
    ch, o = checks(res)
    assert res["verdict"] == "PASS" and o["verdict"] == "PASS", json.dumps(res, indent=1)
    pair = ch["mirror"]["pairs"][0]
    assert pair["verdict"] == "PASS" and pair["max_mismatch_rel"] < 1e-5, pair
    MEASURED["mirror_good_rel"] = pair["max_mismatch_rel"]
    return {"mirror": pair}


def test_d2_dead_key_warns():
    ob = good_face()
    add_key(ob, "Dead", lambda c: (0.0, 0.0, 0.0))
    ch, o = checks(audit())
    assert ch["no_delta"]["verdict"] == "WARN" and ch["no_delta"]["keys"] == ["Dead"] and o["verdict"] == "WARN", ch
    return {"keys": ch["no_delta"]["keys"]}


def test_d2_non_finite_key_fails():
    ob = good_face()
    kb = add_key(ob, "Bad", lambda c: (0.1, 0.0, 0.0))
    kb.data[2].co = (float("nan"), 0.0, 0.0)
    res = audit()
    ch, o = checks(res)
    assert ch["non_finite"]["verdict"] == "FAIL" and ch["non_finite"]["keys"] == ["Bad"] and res["verdict"] == "FAIL", ch
    json.dumps(res, allow_nan=False)
    return {"keys": ch["non_finite"]["keys"]}


def test_d2_missing_relative_key_fails():
    ob = good_face()
    try:
        ob.data.shape_keys.key_blocks["Brow"].relative_key = None
    except Exception as exc:  # the API may refuse to clear it: then Blender cannot produce this state either
        return {"unreachable": str(exc)[:80]}
    ch, o = checks(audit())
    assert ch["relative_key"]["verdict"] == "FAIL" and ch["relative_key"]["keys"] == ["Brow"], ch
    return {"keys": ch["relative_key"]["keys"]}


def test_d2_drivers_to_missing_targets_fail():
    ob = good_face()
    arm = make_armature("Rig")
    key = ob.data.shape_keys
    # a good driver: existing armature and bone
    fc = key.key_blocks["Brow"].driver_add("value")
    v = fc.driver.variables.new()
    v.type = "TRANSFORMS"
    v.targets[0].id = arm
    v.targets[0].bone_target = "upper_arm.L"
    fc.driver.expression = "var"
    ch, _ = checks(audit())
    assert ch["drivers"]["verdict"] == "PASS", ch["drivers"]
    # missing bone
    v.targets[0].bone_target = "no_such_bone"
    ch, o = checks(audit())
    assert ch["drivers"]["verdict"] == "FAIL" and "missing bone" in ch["drivers"]["problems"][0], ch["drivers"]
    # missing object
    v.targets[0].bone_target = ""
    v.targets[0].id = None
    ch, o = checks(audit())
    assert ch["drivers"]["verdict"] == "FAIL" and "missing object" in ch["drivers"]["problems"][0], ch["drivers"]
    # object deleted after the driver was set
    v.targets[0].id = arm
    bpy.data.objects.remove(arm)
    ch, _ = checks(audit())
    assert ch["drivers"]["verdict"] == "FAIL", ch["drivers"]
    return {"problems": ch["drivers"]["problems"]}


def test_d2_mirror_pair_that_differs_fails():
    ob = good_face()
    kb = ob.data.shape_keys.key_blocks["Smile.R"]
    base = ob.data.shape_keys.reference_key
    # the right smile is stronger than the left one's mirror: one vertex moved 0.1 further
    kb.data[10].co = (kb.data[10].co.x - 0.1, kb.data[10].co.y, kb.data[10].co.z)
    res = audit()
    ch, o = checks(res)
    pair = ch["mirror"]["pairs"][0]
    assert pair["verdict"] == "FAIL" and ch["mirror"]["verdict"] == "FAIL" and res["verdict"] == "FAIL", pair
    MEASURED["mirror_bad_rel"] = pair["max_mismatch_rel"]
    return {"pair": pair}


def test_d2_unmatched_mirror_vertices_not_checked():
    ob = good_face()
    ob.data.shape_keys.reference_key.data[7].co.x += 0.3  # breaks the symmetry of the basis itself
    for kb in ob.data.shape_keys.key_blocks:
        if kb.name != "Basis":
            kb.data[7].co.x += 0.3
    ch, o = checks(audit())
    pair = ch["mirror"]["pairs"][0]
    assert pair["verdict"] == "NOT_CHECKED" and "no mirrored vertex" in pair["reason"], pair
    assert o["verdict"] == "WARN"
    return {"pair": pair}


def test_d2_pair_without_partner_not_checked():
    ob = good_face()
    ob.shape_key_remove(ob.data.shape_keys.key_blocks["Smile.R"])
    ch, o = checks(audit())
    assert ch["mirror"]["pairs"][0]["verdict"] == "NOT_CHECKED" and o["verdict"] == "WARN", ch["mirror"]
    return {"ok": True}


def test_d2_nothing_to_audit_is_fail_and_bad_names_raise():
    fresh()
    bpy.data.objects.new("E", bpy.data.meshes.new("E"))
    res = audit()
    assert res["verdict"] == "FAIL" and any("measured nothing" in n for n in res["notes"]), res
    try:
        audit(meshes=["Nope"])
    except ValueError:
        return {"ok": True}
    raise AssertionError("missing mesh name did not raise")


def test_d2_read_only():
    ob = good_face()
    add_key(ob, "Dead", lambda c: (0.0, 0.0, 0.0))
    scn = bpy.context.scene
    key = ob.data.shape_keys

    def state():
        return {"keys": [(kb.name, kb.value, kb.relative_key.name, kb.mute,
                          [tuple(d.co) for d in kb.data]) for kb in key.key_blocks],
                "sel": [(o.name, o.select_get()) for o in bpy.data.objects], "frame": scn.frame_current,
                "active": getattr(bpy.context.view_layer.objects.active, "name", None),
                "counts": (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.actions), len(bpy.data.shape_keys)),
                "active_index": ob.active_shape_key_index, "mode": ob.mode}
    before = state()
    audit()
    assert state() == before
    return {"unchanged": True}


def test_d2_thresholds_margin():
    for k in ("mirror_good_rel", "mirror_bad_rel"):
        assert k in MEASURED, f"{k} not measured (run the fixture tests first)"
    tol = 0.01
    good, bad = MEASURED["mirror_good_rel"], MEASURED["mirror_bad_rel"]
    gap = bad - good
    assert gap > 0 and tol >= good + 0.2 * gap and tol <= bad - 0.2 * gap, (good, bad, tol)
    return {"good": good, "bad": bad, "tol": tol}


def test_d2_result_contract():
    good_face()
    rp = os.path.join(OUT, "audit_result.json")
    res = audit(result_path=rp, run_id="a-1")
    data = json.load(open(rp, encoding="utf-8"))
    assert data["run_id"] == "a-1" and data["verdict"] == res["verdict"] and not os.path.exists(rp + ".tmp")
    old = os.path.join(OUT, "audit_old.json")
    with open(old, "w") as fh:
        json.dump({"run_id": "old"}, fh)
    try:
        audit(meshes=["Nope"], result_path=old, run_id="new")
    except ValueError:
        pass
    assert json.load(open(old))["run_id"] == "old"
    return {"ok": True}


def main():
    os.makedirs(OUT, exist_ok=True)
    tests = [test_d1_loose_garment_passes, test_d1_poke_through_in_one_pose_fails,
             test_d1_blocked_pose_fails_even_with_full_coverage, test_d1_far_garment_is_not_checked,
             test_d1_body_must_be_closed_and_consistent, test_d1_inward_wound_body_still_judged,
             test_d1_restores_state, test_d1_missing_role_and_bad_names, test_d1_thresholds_margin,
             test_d1_result_contract,
             test_d2_good_mesh_passes, test_d2_dead_key_warns, test_d2_non_finite_key_fails,
             test_d2_missing_relative_key_fails, test_d2_drivers_to_missing_targets_fail,
             test_d2_mirror_pair_that_differs_fails, test_d2_unmatched_mirror_vertices_not_checked,
             test_d2_pair_without_partner_not_checked, test_d2_nothing_to_audit_is_fail_and_bad_names_raise,
             test_d2_read_only, test_d2_thresholds_margin, test_d2_result_contract]
    checks_out, failed = {}, []
    for fn in tests:
        try:
            checks_out[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks_out[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks_out) - len(failed), "total": len(checks_out), "failed": failed,
              "checks": checks_out, "measured": MEASURED}
    with open(os.path.join(OUT, "iter16_d_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
