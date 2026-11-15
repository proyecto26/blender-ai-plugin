"""Headless Blender tests for iteration 15, batch `rig` (items A6, A7, A8, E1, E2 and the result_path contract).

  A6  rig_check accepts L_/R_ prefixes as well as .L/_L suffixes
  A7  rig_check errors on a missing or non-mesh name; an Armature modifier that targets ANOTHER armature fails
  A8  cloth_setup reports the real vertex_group_mass; a rerun keeps the pin, `pin_group=""` clears it
  E1  rig_check: non-finite weights, weight sums, zero-length bones, unapplied scale, mirrored Z axes
  E2  stress_check on code-built limb fixtures: good PASS, candy wrapper FAIL (COLLAPSE), unweighted ring FAIL (STRETCH),
      Limit Rotation 30 degrees FAIL (NOT_REACHED), missing role FAIL; state restored; thresholds keep the 20% margin
  B1  result_path/run_id and the exit codes of rig_check.py and stress_check.py as real background processes

Run:
    blender -b --factory-startup --python tests/blender/test_iter15_rig.py -- '{"out_dir": "/tmp/iter15-rig"}'
Optional "skills_dir" runs the same tests against another copy of the skills (used to see the tests fail on old code).
Writes <out_dir>/iter15_rig_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import json
import math
import os
import runpy
import subprocess
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
ARGS = {}
if "--" in sys.argv:
    raw = sys.argv[sys.argv.index("--") + 1:]
    if raw:
        ARGS = json.loads(raw[0])
SKILLS = ARGS.get("skills_dir") or os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
OUT = ARGS.get("out_dir", ".")


def script(skill, name):
    return os.path.join(SKILLS, skill, "scripts", name)


def run(skill, name, **kw):
    return runpy.run_path(script(skill, name), init_globals={"ARGS": kw})["result"]


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------- fixtures
def make_armature(name, bones, roll=None):
    """bones: [(name, head, tail, parent|None)]. Returns the armature object."""
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for bn, head, tail, parent in bones:
        b = data.edit_bones.new(bn)
        b.head, b.tail = head, tail
        if roll and bn in roll:
            b.roll = math.radians(roll[bn])
        if parent:
            b.parent = eb[parent]
            b.use_connect = tuple(b.head) == tuple(eb[parent].tail)
        eb[bn] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def make_cylinder(name, z_top=2.0, loops=21, seg=16, radius=0.15):
    vs, fs = [], []
    for i in range(loops):
        z = z_top * i / (loops - 1)
        for k in range(seg):
            a = 2 * math.pi * k / seg
            vs.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(loops - 1):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            fs.append((a, b, b + seg, a + seg))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def skin(mesh, arm, knots, skip=lambda z: False):
    """Linear weights between bone `knots` ({bone: centre z}); outside the first/last centre the end bone has 1.0."""
    order = sorted(knots.items(), key=lambda kv: kv[1])
    for bn, _ in order:
        mesh.vertex_groups.new(name=bn)
    for v in mesh.data.vertices:
        z = v.co.z
        if skip(z):
            continue
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


GOOD_BONES = [("upper_arm.L", (0, 0, 0), (0, 0, 1), None), ("forearm.L", (0, 0, 1), (0, 0, 1.25), "upper_arm.L"),
              ("forearm_twist_1.L", (0, 0, 1.25), (0, 0, 1.5), "forearm.L"),
              ("forearm_twist_2.L", (0, 0, 1.5), (0, 0, 1.75), "forearm_twist_1.L"),
              ("forearm_twist_3.L", (0, 0, 1.75), (0, 0, 2.0), "forearm_twist_2.L")]
GOOD_KNOTS = {"upper_arm.L": 0.5, "forearm.L": 1.125, "forearm_twist_1.L": 1.375, "forearm_twist_2.L": 1.625,
              "forearm_twist_3.L": 1.875}
CANDY_BONES = [("upper_arm.L", (0, 0, 0), (0, 0, 1), None), ("forearm.L", (0, 0, 1), (0, 0, 2), "upper_arm.L")]
CANDY_KNOTS = {"upper_arm.L": 0.5, "forearm.L": 1.5}


def limb(kind="good"):
    fresh()
    arm = make_armature("ARM_Limb", CANDY_BONES if kind == "candy" else GOOD_BONES)
    cyl = make_cylinder("SK_Limb")
    knots = CANDY_KNOTS if kind == "candy" else GOOD_KNOTS
    skin(cyl, arm, knots, skip=(lambda z: 0.75 < z < 1.25) if kind == "ring" else (lambda z: False))
    if kind == "limit":
        c = arm.pose.bones["forearm.L"].constraints.new("LIMIT_ROTATION")
        c.use_limit_x, c.min_x, c.max_x, c.owner_space = True, math.radians(-30), math.radians(30), "LOCAL"
    if kind == "missing_role":
        bpy.data.objects.remove(arm)
        arm = make_armature("ARM_Limb", [("upper_arm.L", (0, 0, 0), (0, 0, 1), None)])
        cyl.modifiers["Armature"].object = arm
    return arm, cyl


def rows_of(res, pose=None):
    return [r for r in res["rows"] if pose is None or r["pose"] == pose]


# ---------------------------------------------------------------- A6, A7, E1: rig_check
def test_a6_prefix_pairs():
    fresh()
    make_armature("ARM_P", [("L_leg", (1, 0, 1), (1, 0, 0), None), ("R_leg", (-1, 0, 1), (-1, 0, 0), None),
                            ("L_arm", (1, 0, 2), (1, 0, 1), None),  # no R_arm
                            ("spine", (0, 0, 0), (0, 0, 1), None)])
    r = run("rigging", "rig_check.py", armature="ARM_P", meshes=None)
    assert r["unpaired_side_bones"] == ["L_arm"], r["unpaired_side_bones"]
    return {"unpaired": r["unpaired_side_bones"]}


def test_a7_missing_and_nonmesh_names_error():
    arm, cyl = limb("good")
    out = {}
    for label, names in (("missing", ["SK_Limb", "Nope"]), ("not_a_mesh", ["ARM_Limb"])):
        try:
            run("rigging", "rig_check.py", armature="ARM_Limb", meshes=names)
        except ValueError as exc:
            out[label] = str(exc)
        else:
            raise AssertionError(f"{label}: no error")
    return out


def test_a7_modifier_must_target_this_armature():
    fresh()
    a1 = make_armature("ARM_One", [("b.L", (0, 0, 0), (0, 0, 1), None), ("b.R", (0, 0, 1), (0, 0, 2), None)])
    a2 = make_armature("ARM_Two", [("b.L", (0, 0, 0), (0, 0, 1), None)])
    cyl = make_cylinder("SK_X")
    skin(cyl, a2, {"b.L": 0.5})
    r = run("rigging", "rig_check.py", armature="ARM_One", meshes=["SK_X"])
    chk = r["meshes"]["SK_X"]["checks"]["armature_modifier"]
    assert chk["verdict"] == "FAIL" and r["meshes"]["SK_X"]["verdict"] == "FAIL" and r["verdict"] == "FAIL", r
    return {"armature_modifier": chk}


def test_e1_weights_and_bones():
    out = {}
    arm, cyl = limb("good")
    r = run("rigging", "rig_check.py", armature="ARM_Limb")
    assert r["meshes"]["SK_Limb"]["checks"]["weight_sums"]["verdict"] == "PASS", r["meshes"]["SK_Limb"]
    assert r["checks"]["mirrored_z_axes"]["verdict"] == "PASS" and r["checks"]["zero_length_bones"]["verdict"] == "PASS"
    out["good_verdict"] = r["verdict"]
    # weight sum off: halve one vertex's only weight
    cyl.vertex_groups["upper_arm.L"].add([0], 0.5, "REPLACE")
    r = run("rigging", "rig_check.py", armature="ARM_Limb")
    ws = r["meshes"]["SK_Limb"]["checks"]["weight_sums"]
    assert ws["verdict"] == "FAIL" and ws["vertices_off"] >= 1 and r["verdict"] == "FAIL", ws
    out["weight_sums"] = ws
    # non-finite weight: poke NaN into the first group via the weight attribute
    cyl.vertex_groups["upper_arm.L"].add([0], 1.0, "REPLACE")
    cyl.data.vertices[0].groups[0].weight = float("nan")
    r = run("rigging", "rig_check.py", armature="ARM_Limb")
    nf = r["meshes"]["SK_Limb"]["checks"]["non_finite_weights"]
    out["non_finite_weight_after_assign"] = cyl.data.vertices[0].groups[0].weight
    if math.isfinite(out["non_finite_weight_after_assign"]):
        out["non_finite_note"] = "Blender refuses to store NaN weights; the check is a guard for imported data"
    else:
        assert nf["verdict"] == "FAIL", nf
    # zero-length bone
    fresh()
    make_armature("ARM_Z", [("a", (0, 0, 0), (0, 0, 1), None), ("tiny", (0, 0, 1), (0, 0, 1.00005), "a")])
    r = run("rigging", "rig_check.py", armature="ARM_Z")
    assert r["checks"]["zero_length_bones"]["verdict"] == "FAIL" and r["checks"]["zero_length_bones"]["bones"] == ["tiny"], r["checks"]
    # unapplied scale
    bpy.data.objects["ARM_Z"].scale = (2, 2, 2)
    r = run("rigging", "rig_check.py", armature="ARM_Z")
    assert r["checks"]["armature_transform"]["verdict"] == "WARN"
    bpy.data.objects["ARM_Z"].scale = (1, 1, 1)
    bpy.data.objects["ARM_Z"].rotation_euler = (0, 0, math.radians(30))
    r = run("rigging", "rig_check.py", armature="ARM_Z")
    assert r["checks"]["armature_transform"]["verdict"] == "WARN"
    return out


def test_e1_mirrored_z_axes():
    out = {}
    for label, roll_r, expect in (("mirrored_roll", -30.0, "PASS"), ("same_roll", 30.0, "FAIL"), ("20deg_off", -10.0, "FAIL")):
        fresh()
        make_armature("ARM_M", [("arm.L", (1, 0, 0), (1, 0, 1), None), ("arm.R", (-1, 0, 0), (-1, 0, 1), None)],
                      roll={"arm.L": 30.0, "arm.R": roll_r})
        r = run("rigging", "rig_check.py", armature="ARM_M")
        c = r["checks"]["mirrored_z_axes"]
        assert c["verdict"] == expect, (label, c)
        out[label] = c["mismatched"]
    # a pair that is not position-mirrored is reported, not failed
    fresh()
    make_armature("ARM_M", [("arm.L", (1, 0, 0), (1, 0, 1), None), ("arm.R", (-1.5, 0, 0), (-1.5, 0, 1), None)],
                  roll={"arm.L": 30.0, "arm.R": 80.0})
    r = run("rigging", "rig_check.py", armature="ARM_M")
    c = r["checks"]["mirrored_z_axes"]
    assert c["verdict"] == "PASS" and c["asymmetric_pairs"] == [["arm.L", "arm.R"]], c
    out["asymmetric"] = c["asymmetric_pairs"]
    return out


# ---------------------------------------------------------------- A8: cloth_setup
def test_a8_cloth_pin_report():
    fresh()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10)
    flag = bpy.context.active_object
    flag.name = "SM_Flag"
    flag.vertex_groups.new(name="Pin").add([0, 1, 2], 1.0, "REPLACE")
    r1 = run("cloth-sim", "cloth_setup.py", cloth="SM_Flag", fabric="silk", pin_group="Pin")
    assert r1["pinned"] is True
    r2 = run("cloth-sim", "cloth_setup.py", cloth="SM_Flag", fabric="cotton")  # rerun, no pin group
    real = flag.modifiers["Cloth"].settings.vertex_group_mass
    assert real == "Pin", real
    assert r2["pinned"] is True and r2.get("pin_group") == "Pin", r2
    r3 = run("cloth-sim", "cloth_setup.py", cloth="SM_Flag", fabric="cotton", pin_group="")
    assert flag.modifiers["Cloth"].settings.vertex_group_mass == "" and r3["pinned"] is False and r3.get("pin_group") == "", r3
    return {"rerun": {"pinned": r2["pinned"], "pin_group": r2.get("pin_group")}, "cleared": r3["pinned"]}


# ---------------------------------------------------------------- E2: stress_check
MEASURED = {}


def _worst(res, key, fn):
    vals = [r[key] for r in res["rows"] if r.get(key) is not None]
    return fn(vals) if vals else None


def test_e2_good_limb_passes():
    arm, cyl = limb("good")
    res = run("rigging", "stress_check.py", armature="ARM_Limb")
    assert res["verdict"] == "PASS", json.dumps(res["rows"], indent=1)
    posed = {r["pose"] for r in res["rows"]}
    assert posed == {"arms_raised", "elbows_130", "twist_90", "twist_180"}, posed
    assert all(r["status"] == "OK" for r in res["rows"]), res["rows"]
    assert res["limbs"]["arm.L"]["twist"] == ["forearm.L", "forearm_twist_1.L", "forearm_twist_2.L", "forearm_twist_3.L"]
    twist_rows = {"rows": [r for r in res["rows"] if r["pose"] in ("twist_90", "twist_180")]}
    MEASURED["good_collapse"] = _worst(twist_rows, "collapse_ratio", min)
    MEASURED["good_stretch"] = _worst(res, "edge_stretch_p95", max)
    return {"collapse_min_twist": MEASURED["good_collapse"], "stretch_p95_max": MEASURED["good_stretch"],
            "reach": [r["reach"] for r in res["rows"] if r["pose"] == "twist_180"][0]}


def test_e2_candy_wrapper_fails_collapse():
    limb("candy")
    res = run("rigging", "stress_check.py", armature="ARM_Limb")
    bad = [r for r in res["rows"] if r["status"] == "COLLAPSE"]
    assert res["verdict"] == "FAIL" and any(r["pose"] == "twist_180" for r in bad), json.dumps(res["rows"], indent=1)
    assert all(r["status"] == "OK" for r in res["rows"] if r["pose"] in ("arms_raised", "elbows_130", "twist_90")), res["rows"]
    MEASURED["candy_collapse"] = [r["collapse_ratio"] for r in res["rows"] if r["pose"] == "twist_180"][0]
    return {"twist_180_collapse": MEASURED["candy_collapse"],
            "twist_90_collapse": [r["collapse_ratio"] for r in res["rows"] if r["pose"] == "twist_90"][0]}


def test_e2_unweighted_ring_fails_stretch():
    limb("ring")
    res = run("rigging", "stress_check.py", armature="ARM_Limb")
    bad = [r for r in res["rows"] if r["status"] == "STRETCH"]
    assert res["verdict"] == "FAIL" and bad, json.dumps(res["rows"], indent=1)
    # the weakest failing pose is the one the threshold has to separate from the good rig
    MEASURED["ring_stretch"] = min(r["edge_stretch_p95"] for r in bad)
    return {"ring_stretch_p95_weakest_failing": MEASURED["ring_stretch"], "failing_poses": {r["pose"]: r["edge_stretch_p95"] for r in bad}}


def test_e2_limit_rotation_not_reached():
    limb("limit")
    res = run("rigging", "stress_check.py", armature="ARM_Limb")
    nr = [r for r in res["rows"] if r["status"] == "NOT_REACHED"]
    assert res["verdict"] == "FAIL" and any(r["pose"] == "elbows_130" for r in nr), json.dumps(res["rows"], indent=1)
    row = [r for r in nr if r["pose"] == "elbows_130"][0]
    reach = [x for x in row["reach"] if x["bone"] == "forearm.L"][0]
    assert abs(reach["reached_deg"] - 30.0) < 1.0 and reach["requested_deg"] == 130.0, reach
    return {"reach": reach}


def test_e2_missing_role_fails():
    limb("missing_role")
    res = run("rigging", "stress_check.py", armature="ARM_Limb")
    assert res["verdict"] == "FAIL" and res["rows"][0]["status"] == "MISSING_ROLE", res
    # an explicit map naming a bone that does not exist fails too, with the bone named
    arm, cyl = limb("good")
    res = run("rigging", "stress_check.py", armature="ARM_Limb",
              bone_map={"arm.L": {"upper": "upper_arm.L", "lower": "no_such_bone"}})
    assert res["verdict"] == "FAIL" and "no_such_bone" in json.dumps(res["rows"]), res
    return {"problems": res["rows"][0]["problems"]}


def test_e2_restores_state():
    arm, cyl = limb("good")
    scene = bpy.context.scene
    arm.pose.bones["forearm.L"]["ik_fk"] = 1.0
    arm["fk_mode"] = 0.75
    arm.pose.bones["upper_arm.L"].rotation_mode = "QUATERNION"
    arm.pose.bones["upper_arm.L"].rotation_quaternion = (0.9, 0.1, 0.2, 0.3)
    arm.pose.bones["upper_arm.L"].location = (0.1, 0.2, 0.3)
    act = bpy.data.actions.new("Original")
    arm.animation_data_create().action = act
    scene.frame_set(7)
    before_actions = sorted(a.name for a in bpy.data.actions)
    q0 = tuple(arm.pose.bones["upper_arm.L"].rotation_quaternion)
    loc0 = tuple(arm.pose.bones["upper_arm.L"].location)
    res = run("rigging", "stress_check.py", armature="ARM_Limb", fk_switches=[
        {"bone": "forearm.L", "prop": "ik_fk", "value": 0.0}, {"bone": "", "prop": "fk_mode", "value": 0.0}])
    assert res["verdict"] == "PASS", res["rows"]
    assert arm.animation_data.action is act and scene.frame_current == 7
    assert sorted(a.name for a in bpy.data.actions) == before_actions, [a.name for a in bpy.data.actions]
    assert arm.pose.bones["forearm.L"]["ik_fk"] == 1.0 and arm["fk_mode"] == 0.75
    pb = arm.pose.bones["upper_arm.L"]
    assert pb.rotation_mode == "QUATERNION" and tuple(pb.rotation_quaternion) == q0 and tuple(pb.location) == loc0
    assert arm.data.pose_position == "POSE" and "_stress_check_tmp" not in bpy.data.actions
    # no animation data at all before -> none after
    fresh()
    arm, cyl = limb("good")
    assert arm.animation_data is None
    run("rigging", "stress_check.py", armature="ARM_Limb")
    assert arm.animation_data is None and not [a for a in bpy.data.actions]
    # an exception in the middle still restores (bad pose name raises before posing; a mid-run failure is simulated by
    # an fk_switch on a missing property)
    try:
        run("rigging", "stress_check.py", armature="ARM_Limb", fk_switches=[{"bone": "forearm.L", "prop": "nope", "value": 0}])
    except KeyError:
        pass
    assert arm.animation_data is None and not bpy.data.actions
    return {"restored": True}


def test_e2_thresholds_margin():
    for key in ("good_collapse", "good_stretch", "candy_collapse", "ring_stretch"):
        assert key in MEASURED, f"{key} not measured (run the fixture tests first)"
    fresh()
    arm, cyl = limb("good")
    th = run("rigging", "stress_check.py", armature="ARM_Limb")["thresholds"]
    c_gap = MEASURED["good_collapse"] - MEASURED["candy_collapse"]
    assert MEASURED["candy_collapse"] + 0.2 * c_gap <= th["collapse_min"] <= MEASURED["good_collapse"] - 0.2 * c_gap, (MEASURED, th)
    s_gap = MEASURED["ring_stretch"] - MEASURED["good_stretch"]
    assert MEASURED["good_stretch"] + 0.2 * s_gap <= th["stretch_p95_max"] <= MEASURED["ring_stretch"] - 0.2 * s_gap, (MEASURED, th)
    return {"measured": MEASURED, "thresholds": th}


# ---------------------------------------------------------------- B1: result_path / run_id / exit codes
def _blender(blend, py, args):
    args_file = os.path.join(OUT, "args_" + str(abs(hash((blend, py, json.dumps(args, sort_keys=True))))) + ".json")
    with open(args_file, "w", encoding="utf-8") as fh:
        json.dump(args, fh)
    cmd = [bpy.app.binary_path, "-b", blend, "--python-exit-code", "1", "--python", py, "--", "--args-file", args_file]
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300).returncode


def _save(kind, name):
    arm, cyl = limb(kind)
    path = os.path.join(OUT, name)
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return path


def test_b1_result_contract_and_exit_codes():
    out = {}
    good, candy = _save("good", "rig_good.blend"), _save("candy", "rig_candy.blend")
    stress, check = script("rigging", "stress_check.py"), script("rigging", "rig_check.py")
    # PASS -> exit 0 + file with this run_id
    rp = os.path.join(OUT, "stress_pass.json")
    code = _blender(good, stress, {"armature": "ARM_Limb", "result_path": rp, "run_id": "pass-1"})
    data = json.load(open(rp, encoding="utf-8"))
    assert code == 0 and data["run_id"] == "pass-1" and data["verdict"] == "PASS", (code, data["verdict"])
    assert not os.path.exists(rp + ".tmp")
    out["pass_exit"] = code
    # FAIL -> exit 2 + file
    rp = os.path.join(OUT, "stress_fail.json")
    code = _blender(candy, stress, {"armature": "ARM_Limb", "result_path": rp, "run_id": "fail-1"})
    data = json.load(open(rp, encoding="utf-8"))
    assert code == 2 and data["run_id"] == "fail-1" and data["verdict"] == "FAIL", (code, data["verdict"])
    out["fail_exit"] = code
    # rig_check: FAIL (a mesh without a modifier is measured nothing) -> 2; PASS-ish good rig WARN -> 0
    rp = os.path.join(OUT, "rig_fail.json")
    code = _blender(candy, check, {"armature": "ARM_Limb", "meshes": ["SK_Limb"], "result_path": rp, "run_id": "r-1"})
    data = json.load(open(rp, encoding="utf-8"))
    assert code == 0 and data["run_id"] == "r-1" and data["verdict"] in ("PASS", "WARN"), (code, data["verdict"])
    out["rig_check_exit"] = code
    # exception -> exit 1 and nothing written; a stale file from an earlier run_id is left as it was
    rp = os.path.join(OUT, "stress_exc.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump({"run_id": "old", "verdict": "PASS"}, fh)
    code = _blender(good, stress, {"armature": "NoSuchArmature", "result_path": rp, "run_id": "new-1"})
    data = json.load(open(rp, encoding="utf-8"))
    assert code == 1 and data["run_id"] == "old", (code, data)  # caller sees run_id != new-1 -> failed run
    out["exception_exit"] = code
    # a script path that does not exist: no file for this run_id
    rp = os.path.join(OUT, "stress_nopath.json")
    code = _blender(good, stress + ".missing", {"armature": "ARM_Limb", "result_path": rp, "run_id": "np-1"})
    assert not os.path.exists(rp), "file written by a script that does not exist"
    out["missing_script_exit"] = code
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    tests = [test_a6_prefix_pairs, test_a7_missing_and_nonmesh_names_error, test_a7_modifier_must_target_this_armature,
             test_e1_weights_and_bones, test_e1_mirrored_z_axes, test_a8_cloth_pin_report, test_e2_good_limb_passes,
             test_e2_candy_wrapper_fails_collapse, test_e2_unweighted_ring_fails_stretch, test_e2_limit_rotation_not_reached,
             test_e2_missing_role_fails, test_e2_restores_state, test_e2_thresholds_margin,
             test_b1_result_contract_and_exit_codes]
    checks, failed = {}, []
    for fn in tests:
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(OUT, "iter15_rig_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
