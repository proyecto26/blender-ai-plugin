"""Headless Blender tests for iteration 16, batch E (environment and procedural).

  E1  kit_check.py        grid dimensions, origin, snapping faces; read only
  E2  scatter_props.py    min_spacing_m, max_slope_deg, height_range_m honoured and measured on the placed props
  E3  gn_diagnostics.py   missing group, Group Output, node messages, empty vs curve-only vs instance-only output,
                          later modifiers' visibility restored
  E4  sculpt_prep.py      duplicate, apply modifiers, voxel remesh; the original is never changed

Run:
    blender -b --factory-startup --python tests/blender/test_iter16_e.py -- '{"out_dir": "/tmp/iter16-e"}'
Optional "skills_dir" runs the same tests against another copy of the skills (used to see the tests fail on old code).
Writes <out_dir>/iter16_e_report.json with passed / total / failed / checks; exits 1 on a failure.

Measured fixture values behind the thresholds are asserted in the tests themselves (kit tolerance 1e-4 m sits
between exact grid fixtures, off by about 1e-6, and a bad fixture off by 4e-4).
"""
import json
import math
import os
import runpy
import sys
import traceback

import bmesh
import bpy
import numpy as np
from mathutils import Vector

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


def ns(skill, name, **kw):
    """The script's whole namespace (functions and result)."""
    return runpy.run_path(script(skill, name), init_globals={"ARGS": kw})


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_obj(name, verts, faces=(), loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], list(faces))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    bpy.context.view_layer.update()
    return ob


def box(name, size, loc=(0, 0, 0), extra=()):
    """Corner-origin box with extent `size`; `extra` vertices are added loose."""
    sx, sy, sz = size
    v = [(x, y, z) for x in (0, sx) for y in (0, sy) for z in (0, sz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return mesh_obj(name, v + list(extra), f, loc)


# ================================================================ E1 kit_check
def kit(**kw):
    return run("environment-artist", "kit_check.py", **kw)


def test_e1_good_piece_passes():
    fresh()
    box("Good", (2, 1, 3), extra=[(1.0, 0.0, 0.0), (2.0, 0.5, 1.5)])  # extra verts sit on grid lines
    r = kit(objects=["Good"], grid_m=0.5)
    o = r["objects"]["Good"]
    assert r["verdict"] == "PASS" and o["verdict"] == "PASS", r
    assert {k: v["status"] for k, v in o["checks"].items()} == {"dimensions": "PASS", "origin": "PASS", "snap_faces": "PASS"}
    return {"faces": o["checks"]["snap_faces"]["faces"]["+X"]}


def test_e1_bad_dimensions_fail():
    fresh()
    box("Bad", (2.3, 1, 1))
    o = kit(objects=["Bad"], grid_m=0.5)["objects"]["Bad"]
    assert o["verdict"] == "FAIL" and o["checks"]["dimensions"]["status"] == "FAIL", o
    assert o["checks"]["dimensions"]["off_grid"][0]["axis"] == "X"
    return o["checks"]["dimensions"]["off_grid"]


def test_e1_bad_origin_fails():
    fresh()
    box("Off", (2, 2, 2), loc=(0.25, 0, 0))
    o = kit(objects=["Off"], grid_m=0.5)["objects"]["Off"]
    assert o["checks"]["origin"]["status"] == "FAIL" and o["checks"]["dimensions"]["status"] == "PASS", o
    return o["checks"]["origin"]["off_grid"]


def test_e1_stray_snap_vertex_fails_on_its_face_only():
    fresh()
    box("Stray", (2, 2, 2), extra=[(2.0, 0.3, 0.3)])  # on the +X face plane, off the face's grid lines
    o = kit(objects=["Stray"], grid_m=1.0)["objects"]["Stray"]
    snap = o["checks"]["snap_faces"]
    assert o["verdict"] == "FAIL" and snap["status"] == "FAIL", o
    assert snap["faces"]["+X"]["off_grid_vertices"] == 1, snap
    assert all(f["off_grid_vertices"] == 0 for k, f in snap["faces"].items() if k != "+X"), snap
    assert o["checks"]["dimensions"]["status"] == "PASS" and o["checks"]["origin"]["status"] == "PASS"
    return snap["faces"]["+X"]


def test_e1_tolerance_boundary():
    """Exact grid pieces pass (float noise ~1e-6 or less); 4e-4 off fails: 1e-4 keeps the 20% margin to both."""
    fresh()
    box("Exact", (2, 2, 2), loc=(0, 0, 1e-6))
    box("Near", (2.0004, 2, 2))
    r = kit(objects=["Exact", "Near"], grid_m=1.0)["objects"]
    assert r["Exact"]["checks"]["origin"]["status"] == "PASS" and r["Exact"]["checks"]["dimensions"]["status"] == "PASS", r["Exact"]
    assert r["Near"]["checks"]["dimensions"]["status"] == "FAIL", r["Near"]
    gap = 4e-4
    assert 1e-4 - 0.0 >= 0.2 * gap and 4e-4 - 1e-4 >= 0.2 * gap
    return {"good_off_by_m": 1e-6, "bad_off_by_m": 4e-4, "tolerance_m": 1e-4}


def test_e1_rotation_and_scale_count():
    fresh()
    ob = box("Scaled", (1, 1, 1))
    ob.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    o = kit(objects=["Scaled"], grid_m=1.0)["objects"]["Scaled"]
    assert o["verdict"] == "PASS", o  # 1 m mesh scaled to 2 m is on a 1 m grid in world space
    ob.scale = (2.5, 2, 2)
    bpy.context.view_layer.update()
    o = kit(objects=["Scaled"], grid_m=1.0)["objects"]["Scaled"]
    assert o["checks"]["dimensions"]["status"] == "FAIL", o
    return {}


def test_e1_nothing_measured_is_fail():
    fresh()
    bpy.ops.object.empty_add()
    empty = bpy.context.object.name
    r = kit(objects=["Missing", empty], grid_m=1.0)
    assert r["verdict"] == "FAIL" and r["objects"]["Missing"]["verdict"] == "FAIL" and r["objects"][empty]["error"] == "not a mesh"
    r = kit(objects=[], grid_m=1.0)
    assert r["verdict"] == "FAIL" and r.get("note")
    # a mesh with no vertices
    me = bpy.data.meshes.new("E")
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Hollow", me))
    r = kit(objects=["Hollow"], grid_m=1.0)
    assert r["verdict"] == "FAIL" and "no finite" in r["objects"]["Hollow"]["error"], r
    return {}


def test_e1_bad_args_and_read_only_and_result_file():
    fresh()
    ob = box("RO", (2, 2, 2))
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    before = (tuple(ob.location), len(ob.data.vertices), ob.select_get(), bpy.context.view_layer.objects.active.name,
              len(bpy.data.objects), len(bpy.data.meshes), ob.mode)
    for bad in ({"objects": ["RO"], "grid_m": 0}, {"objects": ["RO"], "grid_m": None}, {"objects": "RO", "grid_m": 1}):
        try:
            kit(**bad)
        except ValueError:
            continue
        raise AssertionError(f"bad args accepted: {bad}")
    rp = os.path.join(OUT, "kit_result.json")
    r = kit(objects=["RO"], grid_m=1.0, result_path=rp, run_id="k1")
    data = json.load(open(rp, encoding="utf-8"))
    assert data["run_id"] == "k1" and data["verdict"] == r["verdict"] and not os.path.exists(rp + ".tmp")
    after = (tuple(ob.location), len(ob.data.vertices), ob.select_get(), bpy.context.view_layer.objects.active.name,
             len(bpy.data.objects), len(bpy.data.meshes), ob.mode)
    assert before == after, (before, after)
    # no result file on an exception
    rp2 = os.path.join(OUT, "kit_none.json")
    try:
        kit(objects=["RO"], grid_m=-1, result_path=rp2)
    except ValueError:
        pass
    assert not os.path.exists(rp2)
    return {}


# ================================================================ E2 scatter limits
def scatter_setup():
    """Target cube on a ground that is flat for x < 0 and a 45 degree ramp for x > 0."""
    fresh()
    v = [(-20, -20, 0), (0, -20, 0), (0, 20, 0), (-20, 20, 0), (20, -20, 20), (20, 20, 20)]
    f = [(0, 1, 2, 3), (1, 4, 5, 2)]
    mesh_obj("Ramp", v, f)
    bpy.ops.mesh.primitive_cube_add(location=(-1.5, 0, 1))
    bpy.context.object.name = "SM_T"


def scat(**kw):
    base = {"target": "SM_T", "count": 10, "kinds": ["box", "barrel"], "ground": "Ramp", "seed": 3}
    base.update(kw)
    return run("set-dressing", "scatter_props.py", **base)


def test_e2_min_spacing():
    scatter_setup()
    free = scat()
    assert free["measured"]["min_spacing_m"] < 1.3, free["measured"]  # the fixture is meaningful
    r = scat(min_spacing_m=1.3)
    assert r["measured"]["min_spacing_m"] >= 1.3 - 1e-6 and r["verdict"] == "PASS", r["measured"]
    lim = r["limits"]["min_spacing_m"]
    assert lim["ok"] and lim["limit"] == 1.3 and abs(lim["measured"] - r["measured"]["min_spacing_m"]) < 1e-9
    return {"free": free["measured"]["min_spacing_m"], "limited": r["measured"]["min_spacing_m"]}


def test_e2_max_slope():
    scatter_setup()
    free = scat()
    assert abs(free["measured"]["max_slope_deg"] - 45.0) < 0.01, free["measured"]  # props stand on the ramp
    r = scat(max_slope_deg=20)
    assert r["measured"]["max_slope_deg"] <= 20 and r["verdict"] == "PASS", r["measured"]
    assert all(abs(p["loc"][2]) < 1e-6 or p["loc"][0] < 1e-6 for p in r["props"]), "a prop stands on the ramp"
    return {"free": free["measured"]["max_slope_deg"], "limited": r["measured"]["max_slope_deg"]}


def test_e2_height_range():
    scatter_setup()
    free = scat()
    assert free["measured"]["height_range_m"][1] > 0.6, free["measured"]
    r = scat(height_range_m=[-0.01, 0.5])
    lo, hi = r["measured"]["height_range_m"]
    assert lo >= -0.01 - 1e-6 and hi <= 0.5 + 1e-6 and r["verdict"] == "PASS", r["measured"]
    for p in r["props"]:
        assert -0.01 - 1e-6 <= bpy.data.objects[p["name"]].location.z <= 0.5 + 1e-6
    return {"free": free["measured"]["height_range_m"], "limited": r["measured"]["height_range_m"]}


def test_e2_all_limits_without_ground_argument():
    """Scene raycast mode: the measurement must not hit the props themselves (it hides them while measuring)."""
    scatter_setup()
    free = scat(ground=None)
    assert abs(free["measured"]["max_slope_deg"] - 45.0) < 0.01, free["measured"]
    r = scat(ground=None, max_slope_deg=20, min_spacing_m=1.2, height_range_m=[-0.01, 0.5])
    assert r["verdict"] == "PASS" and set(r["limits"]) == {"min_spacing_m", "max_slope_deg", "height_range_m"}, r
    assert all(v["ok"] for v in r["limits"].values())
    assert all(not bpy.data.objects[p["name"]].hide_viewport for p in r["props"]), "visibility not restored"
    return r["measured"]


def test_e2_violation_fails():
    scatter_setup()
    n = ns("set-dressing", "scatter_props.py", target="SM_T", count=2, kinds=["box"], ground="Ramp")
    check = n["_check_limits"]
    res, v = check({"min_spacing_m": 2.0}, {"min_spacing_m": 1.0, "max_slope_deg": 0, "height_range_m": [0, 0]})
    assert v == "FAIL" and not res["min_spacing_m"]["ok"]
    res, v = check({"max_slope_deg": 10}, {"max_slope_deg": 10.5})
    assert v == "FAIL"
    res, v = check({"height_range_m": [0, 1]}, {"height_range_m": [0, 1.2]})
    assert v == "FAIL"
    res, v = check({"height_range_m": [0, 1]}, {"height_range_m": [-0.2, 0.5]})
    assert v == "FAIL"
    res, v = check({"max_slope_deg": 10}, {"max_slope_deg": None})
    assert v == "FAIL", "an unmeasured limit must not pass"
    res, v = check({"max_slope_deg": 10, "min_spacing_m": 1, "height_range_m": [0, 1]},
                   {"max_slope_deg": 10, "min_spacing_m": 1.0, "height_range_m": [0, 1]})
    assert v == "PASS"
    return {}


def test_e2_bad_limits_refused_before_anything_changes():
    scatter_setup()
    r1 = scat(count=3, kinds=["box"])
    names = sorted(p["name"] for p in r1["props"])
    for bad in ({"max_slope_deg": 95}, {"max_slope_deg": -1}, {"height_range_m": [1, 0]}, {"height_range_m": [0]},
                {"min_spacing_m": -1}):
        try:
            scat(count=3, kinds=["box"], **bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    assert sorted(o.name for o in bpy.data.objects if o.name.startswith("PROP_")) == names
    return {}


def test_e2_unreachable_limit_raises_instead_of_violating():
    scatter_setup()
    try:
        scat(count=3, kinds=["box"], height_range_m=[50, 60])
    except RuntimeError as exc:
        return {"raised": str(exc)[:60]}
    raise AssertionError("props placed outside an impossible height range")


def test_e2_ownership_unchanged():
    """The iteration 15 ownership rule still holds with limits on: an untagged ME_Prop_box is refused."""
    scatter_setup()
    me = bpy.data.meshes.new("ME_Prop_box")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    try:
        scat(count=2, kinds=["box"], max_slope_deg=30)
    except ValueError as exc:
        assert "ME_Prop_box" in str(exc)
        return {}
    raise AssertionError("untagged mesh adopted")


# ================================================================ E3 gn_diagnostics
def gn_fixture(name, build, base=None, add_mod=True):
    """Mesh object with a GN modifier. build(ng, gi, go) wires the group; the group has a Geometry in and out."""
    ob = base or box(name, (1, 1, 1))
    ng = bpy.data.node_groups.new(f"G_{name}", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    build(ng, gi, go)
    md = ob.modifiers.new("GN", "NODES")
    md.node_group = ng
    bpy.context.view_layer.update()
    return ob, md, ng


def link(ng, a, b):
    ng.links.new(a, b)


def gn(**kw):
    kw.setdefault("objects", None)
    return run("geometry-nodes", "gn_diagnostics.py", **kw)


def only(r):
    assert len(r["modifiers"]) == 1, r
    return r["modifiers"][0]


def b_passthrough(ng, gi, go):
    link(ng, gi.outputs[0], go.inputs[0])


def test_e3_passthrough_passes():
    fresh()
    gn_fixture("A", b_passthrough)
    m = only(gn())
    assert m["verdict"] == "PASS", m
    assert {k: c["status"] for k, c in m["checks"].items()} == {
        "node_group": "PASS", "group_output": "PASS", "node_warnings": "PASS", "evaluated_geometry": "PASS", "timing": "PASS"}
    assert m["checks"]["evaluated_geometry"]["components"]["mesh_vertices"] == 8 and not m["info"]
    return {"ms": m["execution_ms"]}


def test_e3_generator_with_unused_geometry_input_is_pass_and_listed():
    fresh()

    def build(ng, gi, go):
        ng.interface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketInt")
        cube = ng.nodes.new("GeometryNodeMeshCube")
        link(ng, cube.outputs["Mesh"], go.inputs[0])

    gn_fixture("Gen", build)
    m = only(gn())
    kinds = sorted(i["kind"] for i in m["info"])
    assert m["verdict"] == "PASS" and kinds == ["geometry_input_unused", "input_unlinked"], m
    assert m["checks"]["evaluated_geometry"]["components"]["mesh_vertices"] > 0
    return m["info"]


def test_e3_missing_node_group_fails():
    fresh()
    ob = box("NoGroup", (1, 1, 1))
    ob.modifiers.new("GN", "NODES")
    m = only(gn())
    assert m["verdict"] == "FAIL" and m["checks"]["node_group"]["status"] == "FAIL", m
    assert m["checks"]["evaluated_geometry"]["status"] == "NOT_CHECKED"
    return {}


def test_e3_group_output_without_geometry_link_fails():
    fresh()
    gn_fixture("NoLink", lambda ng, gi, go: None)
    m = only(gn())
    assert m["verdict"] == "FAIL" and m["checks"]["group_output"]["status"] == "FAIL", m
    assert "no link" in m["checks"]["group_output"]["note"]
    return m["checks"]["group_output"]


def test_e3_group_without_output_socket_or_node_fails():
    fresh()
    ob = box("NoOut", (1, 1, 1))
    ng = bpy.data.node_groups.new("G_NoOut", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    md = ob.modifiers.new("GN", "NODES")
    md.node_group = ng
    m = only(gn())
    assert m["checks"]["group_output"]["status"] == "FAIL" and "no Geometry output" in m["checks"]["group_output"]["note"], m
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for n in list(ng.nodes):
        ng.nodes.remove(n)
    m = only(gn())
    assert "no Group Output node" in m["checks"]["group_output"]["note"], m
    return {}


def test_e3_empty_output_fails():
    fresh()

    def build(ng, gi, go):
        d = ng.nodes.new("GeometryNodeDeleteGeometry")  # Selection defaults to True: deletes everything
        link(ng, gi.outputs[0], d.inputs[0])
        link(ng, d.outputs[0], go.inputs[0])

    gn_fixture("Empty", build)
    m = only(gn())
    ev = m["checks"]["evaluated_geometry"]
    assert m["verdict"] == "FAIL" and ev["status"] == "FAIL" and not any(ev["components"].values()), m
    assert m["checks"]["group_output"]["status"] == "PASS"
    return ev["components"]


def test_e3_curve_only_output_is_not_empty():
    fresh()

    def build(ng, gi, go):
        c = ng.nodes.new("GeometryNodeMeshToCurve")
        link(ng, gi.outputs[0], c.inputs[0])
        link(ng, c.outputs[0], go.inputs[0])

    gn_fixture("Curve", build)
    m = only(gn())
    comps = m["checks"]["evaluated_geometry"]["components"]
    assert m["verdict"] == "PASS" and comps["curve_points"] > 0 and comps["mesh_vertices"] == 0, m
    return comps


def test_e3_unrealized_instances_are_not_empty():
    fresh()

    def build(ng, gi, go):
        pts = ng.nodes.new("GeometryNodeMeshToPoints")
        ins = ng.nodes.new("GeometryNodeInstanceOnPoints")
        cube = ng.nodes.new("GeometryNodeMeshCube")
        link(ng, gi.outputs[0], pts.inputs[0])
        link(ng, pts.outputs[0], ins.inputs["Points"])
        link(ng, cube.outputs["Mesh"], ins.inputs["Instance"])
        link(ng, ins.outputs[0], go.inputs[0])

    gn_fixture("Inst", build)
    m = only(gn())
    comps = m["checks"]["evaluated_geometry"]["components"]
    assert m["verdict"] == "PASS" and comps["instances"] > 0 and comps["mesh_vertices"] == 0, m
    return comps


def test_e3_points_only_output_is_not_empty():
    fresh()

    def build(ng, gi, go):
        pts = ng.nodes.new("GeometryNodeMeshToPoints")
        link(ng, gi.outputs[0], pts.inputs[0])
        link(ng, pts.outputs[0], go.inputs[0])

    gn_fixture("Pts", build)
    m = only(gn())
    assert m["verdict"] == "PASS" and m["checks"]["evaluated_geometry"]["components"]["pointcloud_points"] > 0, m
    return {}


def test_e3_node_error_fails_and_info_is_listed_only():
    fresh()

    def build(ng, gi, go):
        o = ng.nodes.new("GeometryNodeObjectInfo")
        o.inputs[0].default_value = bpy.data.objects["Err"]
        link(ng, o.outputs["Geometry"], go.inputs[0])

    ob = box("Err", (1, 1, 1))
    gn_fixture("Err", build, base=ob)
    m = only(gn())
    w = m["checks"]["node_warnings"]
    assert w["status"] == "FAIL" and w["messages"][0]["type"] == "ERROR", m
    # an INFO message alone does not change the verdict of that check
    fresh()

    def build2(ng, gi, go):
        c = ng.nodes.new("GeometryNodeCurveToMesh")  # "Input geometry has unsupported type: Mesh" (INFO)
        link(ng, gi.outputs[0], c.inputs[0])
        link(ng, c.outputs[0], go.inputs[0])

    gn_fixture("Info", build2)
    w = only(gn())["checks"]["node_warnings"]
    assert w["messages"] and w["messages"][0]["type"] == "INFO" and w["status"] == "PASS", w
    return {"error": m["checks"]["node_warnings"]["messages"][0]["message"]}


def test_e3_classify_message_levels():
    fresh()
    gn_fixture("C", b_passthrough)
    cm = ns("geometry-nodes", "gn_diagnostics.py", objects=None)["classify_message"]
    assert (cm("ERROR"), cm("WARNING"), cm("INFO")) == ("FAIL", "WARN", "PASS")
    return {}


def test_e3_later_modifiers_hidden_while_measuring_and_restored():
    fresh()

    def empties(ng, gi, go):
        d = ng.nodes.new("GeometryNodeDeleteGeometry")
        link(ng, gi.outputs[0], d.inputs[0])
        link(ng, d.outputs[0], go.inputs[0])

    ob, m1, _ng1 = gn_fixture("Two", b_passthrough)
    _ob, m2, _ng2 = gn_fixture("Two2", empties, base=ob)
    assert [m.name for m in ob.modifiers] == ["GN", "GN.001"]
    r = gn()
    by = {e["modifier"]: e for e in r["modifiers"]}
    assert by["GN"]["checks"]["evaluated_geometry"]["status"] == "PASS", by["GN"]  # later empty modifier hidden
    assert by["GN.001"]["checks"]["evaluated_geometry"]["status"] == "FAIL", by["GN.001"]
    assert m1.show_viewport and m2.show_viewport, "visibility not restored"
    return {"first": by["GN"]["verdict"], "second": by["GN.001"]["verdict"]}


def test_e3_visibility_restored_when_evaluation_fails():
    fresh()
    ob, m1, _ = gn_fixture("Boom", b_passthrough)
    m2 = ob.modifiers.new("Later", "SUBSURF")
    n = ns("geometry-nodes", "gn_diagnostics.py", objects=None)

    class Proxy:
        modifiers = ob.modifiers

        def evaluated_get(self, _dg):
            raise RuntimeError("evaluation failed")

    try:
        n["_evaluate"](Proxy(), m1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("no failure raised")
    assert m2.show_viewport and m1.show_viewport
    return {}


def test_e3_hidden_modifier_is_not_checked():
    fresh()
    ob, m, _ = gn_fixture("Hid", b_passthrough)
    m.show_viewport = False
    e = only(gn())
    assert e["checks"]["evaluated_geometry"]["status"] == "NOT_CHECKED" and e["verdict"] == "WARN", e
    assert m.show_viewport is False
    return {}


def test_e3_no_modifiers_is_fail_and_result_file_contract():
    fresh()
    box("Plain", (1, 1, 1))
    r = gn()
    assert r["verdict"] == "FAIL" and r["note"] and r["modifiers"] == []
    gn_fixture("A2", b_passthrough, base=bpy.data.objects["Plain"])
    rp = os.path.join(OUT, "gn_result.json")
    r = gn(result_path=rp, run_id="g1")
    data = json.load(open(rp, encoding="utf-8"))
    assert data["run_id"] == "g1" and data["verdict"] == "PASS" and not os.path.exists(rp + ".tmp")
    rp2 = os.path.join(OUT, "gn_none.json")
    try:
        gn(objects=["Nope"], result_path=rp2)
    except ValueError:
        pass
    assert not os.path.exists(rp2)
    return {}


def test_e3_max_ms_warns():
    fresh()
    gn_fixture("T", b_passthrough)
    m = only(gn(max_ms=-1.0))  # any non-negative time exceeds -1 ms
    assert m["checks"]["timing"]["status"] == "WARN" and m["verdict"] == "WARN", m
    return {}


# ================================================================ E4 sculpt_prep
def sculpt_fixture():
    fresh()
    bpy.ops.mesh.primitive_cube_add(size=2, location=(1, 2, 3))
    ob = bpy.context.object
    ob.name = "SM_Head"
    sub = ob.modifiers.new("Sub", "SUBSURF")
    sub.levels = 2
    other = bpy.data.objects.new("Other", bpy.data.meshes.new("OtherMesh"))
    bpy.context.scene.collection.objects.link(other)
    for o in bpy.data.objects:
        o.select_set(False)
    other.select_set(True)
    bpy.context.view_layer.objects.active = other
    return ob, other


def snapshot(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return (co.tobytes(), [(m.name, m.type, m.levels) for m in ob.modifiers], me.name, tuple(map(tuple, ob.matrix_world)))


def test_e4_original_untouched_copy_remeshed():
    ob, other = sculpt_fixture()
    before = snapshot(ob)
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    r = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.1)
    assert r["verdict"] == "PASS" and r["original_unchanged"] is True, r
    assert snapshot(ob) == before, "the original changed"
    cp = bpy.data.objects[r["copy"]]
    assert cp.name == "SM_Head_sculpt" and cp is not ob and cp.data is not ob.data
    assert len(cp.modifiers) == 0 and len(ob.modifiers) == 1
    assert r["vertices_before"] == 8 and r["vertices_after_modifiers"] == 98 and         r["vertices_after_remesh"] == len(cp.data.vertices) > 100, r
    assert abs(cp.dimensions.x - 2.0) < 0.5 and tuple(round(v, 4) for v in cp.location) == (1, 2, 3)
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (counts[0] + 1, counts[1] + 1)
    assert [c.name for c in cp.users_collection] == [c.name for c in ob.users_collection]
    return {"vertices": r["vertices_after_remesh"]}


def test_e4_selection_active_restored_and_name_collision():
    ob, other = sculpt_fixture()
    r1 = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.25)
    sel = sorted(o.name for o in bpy.data.objects if o.select_get())
    assert sel == ["Other"] and bpy.context.view_layer.objects.active.name == "Other", sel
    assert bpy.context.object is None or bpy.context.object.mode == "OBJECT"
    r2 = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.25)
    assert r2["copy"] != r1["copy"] and r1["copy"] in bpy.data.objects and r2["copy"] in bpy.data.objects
    return {"names": [r1["copy"], r2["copy"]]}


def test_e4_smaller_voxel_means_more_vertices():
    sculpt_fixture()
    a = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.2)
    b = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.1)
    assert b["vertices_after_remesh"] > 2 * a["vertices_after_remesh"], (a, b)
    return {"0.2": a["vertices_after_remesh"], "0.1": b["vertices_after_remesh"]}


def test_e4_refuses_before_creating_anything():
    sculpt_fixture()
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    for bad in ({"object": "SM_Head", "voxel_size_m": 1e-6}, {"object": "SM_Head", "voxel_size_m": 0},
                {"object": "Nope", "voxel_size_m": 0.1}, {"object": "Other", "voxel_size_m": None}):
        try:
            run("sculpting", "sculpt_prep.py", **bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    bpy.ops.object.empty_add()
    try:
        run("sculpting", "sculpt_prep.py", object=bpy.context.object.name, voxel_size_m=0.1)
    except ValueError:
        pass
    else:
        raise AssertionError("non-mesh accepted")
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (counts[0] + 1, counts[1])
    return {}


def test_e4_failure_after_copy_removes_the_copy_and_restores_state():
    ob, other = sculpt_fixture()
    before = snapshot(ob)
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    try:
        run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.1, name=123)  # fails after the copy exists
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("no failure")
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts, "the script's own copy was left behind"
    assert snapshot(ob) == before
    assert [o.name for o in bpy.data.objects if o.select_get()] == ["Other"]
    assert bpy.context.view_layer.objects.active.name == "Other"
    return {}


def test_e4_detects_a_changed_original():
    """The comparison is real: change the original between the two fingerprints and the verdict is FAIL."""
    ob, _o = sculpt_fixture()
    n = ns("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.5)
    fp = n["_fingerprint"]
    a = fp(ob)
    ob.data.vertices[0].co.x += 0.01
    b = fp(ob)
    assert not n["_same"](a, b)
    ob.modifiers.new("Extra", "BEVEL")
    assert fp(ob)["modifiers"] != b["modifiers"]
    return {}


def test_e4_result_file_contract():
    sculpt_fixture()
    rp = os.path.join(OUT, "sculpt_result.json")
    run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.3, result_path=rp, run_id="s1")
    data = json.load(open(rp, encoding="utf-8"))
    assert data["run_id"] == "s1" and data["original_unchanged"] is True and not os.path.exists(rp + ".tmp")
    rp2 = os.path.join(OUT, "sculpt_none.json")
    try:
        run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0, result_path=rp2)
    except ValueError:
        pass
    assert not os.path.exists(rp2)
    return {}


# ================================================================ review round 1 (Seldon findings)
def set_unit_scale(v):
    bpy.context.scene.unit_settings.scale_length = v


def mean_edge_world_m(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ev = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    local = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1).mean()
    return float(local * max(abs(v) for v in ob.matrix_world.to_scale()) * bpy.context.scene.unit_settings.scale_length)


def cube_obj(size, scale=1.0, name="SM_Head"):
    fresh()
    bpy.ops.mesh.primitive_cube_add(size=size)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    return ob


def test_r1_e4_scaled_object_gets_world_voxel_size():
    ob = cube_obj(20, 0.1)  # 2 m cube
    r = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.2)
    edge = mean_edge_world_m(bpy.data.objects[r["copy"]])
    assert 0.1 <= edge <= 0.3, f"mean edge {edge} m for a 0.2 m voxel"
    return {"mean_edge_m": edge}


def test_r1_e4_scene_unit_scale_is_honoured():
    cube_obj(200)  # 200 units
    set_unit_scale(0.01)  # = 2 m
    r = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.2)
    edge = mean_edge_world_m(bpy.data.objects[r["copy"]])
    assert 0.1 <= edge <= 0.3, edge
    return {"mean_edge_m": edge}


def test_r1_e4_large_mesh_tiny_scale_is_accepted_correctly_and_fast():
    """The reviewed case: a 2000-unit cube scaled 0.001 is a 2 m object; 0.1 m voxels need ~20 cells per axis."""
    cube_obj(2000, 0.001)
    r = run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.1)
    edge = mean_edge_world_m(bpy.data.objects[r["copy"]])
    assert 0.05 <= edge <= 0.15 and r["vertices_after_remesh"] < 20000, (edge, r)
    return {"mean_edge_m": edge, "vertices": r["vertices_after_remesh"]}


def test_r1_e4_budget_uses_mesh_space_and_refuses_the_huge_case():
    cube_obj(2000, 0.001)
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    try:
        run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=1e-5)  # 2 m object at 10 micron voxels
    except ValueError as exc:
        assert "voxels" in str(exc)
    else:
        raise AssertionError("huge budget accepted")
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
    return {}


def test_r1_e4_non_uniform_scale_refused():
    ob = cube_obj(2)
    ob.scale = (1, 2, 1)
    bpy.context.view_layer.update()
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    try:
        run("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.2)
    except ValueError as exc:
        assert "non-uniform" in str(exc) and "apply" in str(exc)
    else:
        raise AssertionError("non-uniform scale accepted")
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
    return {}


def test_r1_e1_scene_unit_scale():
    fresh()
    box("Small", (2, 2, 2))
    set_unit_scale(0.01)  # 2 units = 0.02 m
    o = kit(objects=["Small"], grid_m=1.0)["objects"]["Small"]
    assert o["checks"]["dimensions"]["status"] == "FAIL", o
    fresh()
    box("Big", (200, 200, 200))
    set_unit_scale(0.01)  # 2 m
    o = kit(objects=["Big"], grid_m=1.0)["objects"]["Big"]
    assert o["verdict"] == "PASS", o
    assert abs(o["checks"]["dimensions"]["dimensions_m"][0] - 2.0) < 1e-6
    return {}


def test_r1_e2_limits_are_metres_with_scene_unit_scale():
    scatter_setup()
    set_unit_scale(0.5)  # 1 unit = 0.5 m
    r = scat(min_spacing_m=1.3, height_range_m=[-0.01, 0.25], count=4, max_dist=6)
    objs = [bpy.data.objects[p["name"]] for p in r["props"]]
    pts = [o.location.xy for o in objs]
    dmin_units = min((a - b).length for i, a in enumerate(pts) for b in pts[:i])
    assert dmin_units >= 1.3 / 0.5 - 1e-6, dmin_units  # 2.6 units
    assert all(o.location.z * 0.5 <= 0.25 + 1e-6 for o in objs)
    assert abs(r["measured"]["min_spacing_m"] - dmin_units * 0.5) < 1e-6 and r["verdict"] == "PASS", r["measured"]
    assert r["measured"]["height_range_m"][1] <= 0.25 + 1e-6
    return r["measured"]


def test_r1_e3_real_warning_message_warns():
    fresh()

    def build(ng, gi, go):
        w = ng.nodes.new("GeometryNodeWarning")  # Blender 5.x Warning node
        w.warning_type = "WARNING"
        w.inputs["Message"].default_value = "custom warn"
        link(ng, gi.outputs[0], go.inputs[0])

    gn_fixture("W", build)
    m = only(gn())
    nw = m["checks"]["node_warnings"]
    assert nw["status"] == "WARN" and nw["messages"][0]["type"] == "WARNING", m
    assert m["verdict"] == "WARN" and m["checks"]["evaluated_geometry"]["status"] == "PASS"
    return nw



def test_r2_e4_fingerprint_covers_selection_and_active():
    ob, other = sculpt_fixture()
    n = ns("sculpting", "sculpt_prep.py", object="SM_Head", voxel_size_m=0.5)
    fp = n["_fingerprint"]
    a = fp(ob)
    assert a["selected"] == ["Other"] and a["active"] == "Other", a
    ob.select_set(True)
    assert not n["_same"](a, fp(ob)), "selection change not detected"
    ob.select_set(False)
    bpy.context.view_layer.objects.active = ob
    assert not n["_same"](a, fp(ob)), "active change not detected"
    return {}


def main():
    os.makedirs(OUT, exist_ok=True)
    tests = [v for k, v in sorted(globals().items(), key=lambda kv: list(globals()).index(kv[0]))
             if k.startswith("test_") and callable(v)]
    only_prefix = ARGS.get("only")  # optional: run just the tests whose name starts with this
    if only_prefix:
        tests = [t for t in tests if t.__name__.startswith(only_prefix)]
    checks, failed = {}, []
    for fn in tests:
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(OUT, "iter16_e_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
