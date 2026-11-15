"""Headless Blender tests for iteration 15, batch uv (A1-A5, A16, section C).

  A1  uv_unwrap_check   measure-only never creates a UV channel (error, mesh unchanged)
  A2  uv_unwrap_check   uv_area_sum counts stacked faces twice; uv_coverage is the union
  A3  bake_maps         an existing image of another size is refused, real size reported
  A4  bake_maps         a bake that does not return FINISHED raises and saves nothing
  A5  pbr_material      emission texture gets strength 1.0 unless the caller sets one
  A16 scatter_props     props have one packed island per face: no collapsed faces, no overlap
  C   uv_unwrap_check   channels, islands, collapsed, overlap, coverage, density spread, stretch,
                        unwrap options, result_path / run_id, 20k-triangle speed

Run (a NEW out_dir every time):
    blender -b --factory-startup --python tests/blender/test_iter15_uv.py -- '{"out_dir": "/tmp/iter15-uv"}'
Optional "skills_dir" points at another copy of the skills tree (used to run the old scripts).
Writes <out_dir>/iter15_uv_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import hashlib
import json
import math
import os
import runpy
import sys
import time
import traceback

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
ARGS = {}
if "--" in sys.argv:
    raw = sys.argv[sys.argv.index("--") + 1:]
    if raw:
        ARGS = json.loads(raw[0])
SKILLS = ARGS.get("skills_dir") or os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
OUT = ARGS.get("out_dir", ".")


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def uvc(**kw):
    return run("uv-workflow", "uv_unwrap_check.py", kw)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_obj(name, me):
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def quads(name, faces, uv_layers):
    """Separate (unshared-vertex) quads. faces: list of 4 xyz; uv_layers: {name: list of 4 uv per face}."""
    bm = bmesh.new()
    for pts in faces:
        bm.faces.new([bm.verts.new(p) for p in pts])
    layers = {n: bm.loops.layers.uv.new(n) for n in uv_layers}
    for fi, f in enumerate(bm.faces):
        for n, lay in layers.items():
            for l, uv in zip(f.loops, uv_layers[n][fi]):
                l[lay].uv = uv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return make_obj(name, me)


def sq(x0, y0, size, z=0.0):
    return [(x0, y0, z), (x0 + size, y0, z), (x0 + size, y0 + size, z), (x0, y0 + size, z)]


def uvsq(u0, v0, size):
    return [(u0, v0), (u0 + size, v0), (u0 + size, v0 + size), (u0, v0 + size)]


def uv_hash(obj):
    out = []
    for l in obj.data.uv_layers:
        out += [round(x, 6) for d in l.uv for x in d.vector]
    return hashlib.md5(json.dumps(out).encode()).hexdigest()


# ------------------------------------------------------------------------------------------ A1 / A2

def test_a1_measure_only_no_uv():
    reset()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.data.uv_layers.remove(obj.data.uv_layers[0])
    assert len(obj.data.uv_layers) == 0
    r = uvc(objects=[obj.name])
    e = r["objects"][obj.name]
    assert "error" in e, e
    assert len(obj.data.uv_layers) == 0, "measure-only created a UV channel"
    r2 = uvc(objects=[obj.name], unwrap=True)
    assert len(obj.data.uv_layers) == 1 and r2["objects"][obj.name]["texel_density_px_per_m"] > 0
    reset()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.data.uv_layers.remove(obj.data.uv_layers[0])
    r3 = uvc(objects=[obj.name], lightmap=True)  # lightmap-only path keeps working
    assert r3["objects"][obj.name]["lightmap_channel"] == "UVMap_Lightmap"
    return {"error": e["error"][:60]}


def test_a2_union_coverage():
    reset()
    o = quads("Stack", [sq(0, 0, 1, 0), sq(0, 0, 1, 1)], {"UVMap": [uvsq(0, 0, 1), uvsq(0, 0, 1)]})
    e = uvc(objects=["Stack"], allow_overlap=True)["objects"]["Stack"]
    assert abs(e["uv_area_sum"] - 2.0) < 1e-3 and "uv_space_used" not in e, e
    assert abs(e["uv_coverage"] - 1.0) < 0.02, e["uv_coverage"]
    return {"uv_area_sum": e["uv_area_sum"], "uv_coverage": e["uv_coverage"]}


# ------------------------------------------------------------------------------------------ C fixtures

def test_c_stacked_and_declared():
    reset()
    quads("Stack", [sq(0, 0, 1, 0), sq(0, 0, 1, 1)], {"UVMap": [uvsq(0, 0, 1), uvsq(0, 0, 1)]})
    bad = uvc(objects=["Stack"])
    e = bad["objects"]["Stack"]
    assert bad["verdict"] == "FAIL" and e["checks"]["overlap"]["status"] == "FAIL" and e["overlap_pairs"] > 0, e
    assert e["overlap_area"] > 0.9, e["overlap_area"]
    ok = uvc(objects=["Stack"], allow_overlap=True)
    assert ok["verdict"] == "PASS" and ok["objects"]["Stack"]["uv_layer"] == "UVMap", ok
    return {"fail_pairs": e["overlap_pairs"], "declared_verdict": ok["verdict"]}


def test_c_shared_edges_not_overlap():
    reset()
    quads("Tiles", [sq(0, 0, 1), sq(1, 0, 1), sq(0, 1, 1), sq(1, 1, 1)],
          {"UVMap": [uvsq(0, 0, .5), uvsq(.5, 0, .5), uvsq(0, .5, .5), uvsq(.5, .5, .5)]})
    e = uvc(objects=["Tiles"])["objects"]["Tiles"]
    assert e["overlap_pairs"] == 0 and e["verdict"] == "PASS", e
    assert e["islands"] == 4 and abs(e["uv_coverage"] - 1.0) < 0.02, e
    return {"islands": e["islands"], "coverage": e["uv_coverage"]}


def test_c_collapsed_face():
    reset()
    quads("Col", [sq(0, 0, 1), sq(2, 0, 1)], {"UVMap": [uvsq(0.1, 0.1, 0.4), [(0.8, 0.8)] * 4]})
    r = uvc(objects=["Col"])
    e = r["objects"]["Col"]
    assert e["collapsed_faces"] == 1 and r["verdict"] == "FAIL", e
    return {"collapsed": e["collapsed_faces"]}


def test_c_density_spread():
    reset()
    quads("Spread", [sq(0, 0, 1), sq(2, 0, 1)], {"UVMap": [uvsq(0.05, 0.05, 0.4), uvsq(0.55, 0.05, 0.2)]})
    e = uvc(objects=["Spread"])["objects"]["Spread"]
    assert abs(e["density_spread"] - 2.0) < 0.01 and e["checks"]["density_spread"]["status"] == "WARN", e
    assert e["verdict"] == "WARN" and e["island_density_max"] > e["island_density_min"]
    return {"spread": e["density_spread"], "min": e["island_density_min"], "max": e["island_density_max"]}


def test_c_stretched_cylinder():
    reset()
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=16, radius1=1.0, radius2=1.0, depth=1.0)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        us = []
        for l in f.loops:
            a = math.atan2(l.vert.co.y, l.vert.co.x) / (2 * math.pi) % 1.0
            us.append(a)
        if max(us) - min(us) > 0.5:
            us = [u + 1.0 if u < 0.5 else u for u in us]
        for l, u in zip(f.loops, us):
            l[uv].uv = (u * 0.9 / 1.0, (l.vert.co.z + 0.5) * 0.9)
    me = bpy.data.meshes.new("Cyl")
    bm.to_mesh(me)
    bm.free()
    make_obj("Cyl", me)
    e = uvc(objects=["Cyl"])["objects"]["Cyl"]
    assert e["stretch_p95"] > 1.2 and e["checks"]["stretch_p95"]["status"] == "WARN", e
    assert e["islands"] == 1, e["islands"]
    return {"stretch_p95": e["stretch_p95"], "islands": e["islands"], "verdict": e["verdict"]}


def test_c_two_channels_opposite_verdicts():
    reset()
    faces = [sq(0, 0, 1, 0), sq(0, 0, 1, 1)]
    quads("Both", faces, {"UVMap": [uvsq(0, 0, 1), uvsq(0, 0, 1)],
                          "UVMap_Lightmap": [uvsq(0.1, 0.1, 0.5), uvsq(0.3, 0.3, 0.5)]})
    obj = bpy.data.objects["Both"]
    before = uv_hash(obj)
    a = uvc(objects=["Both"], uv_layer="UVMap", allow_overlap=True)
    b = uvc(objects=["Both"], uv_layer="UVMap_Lightmap", allow_overlap=True)
    c = uvc(objects=["Both"], uv_layer=1)
    assert a["verdict"] == "PASS" and a["objects"]["Both"]["uv_layer"] == "UVMap", a
    assert b["verdict"] == "FAIL" and b["objects"]["Both"]["uv_layer"] == "UVMap_Lightmap", b
    assert b["objects"]["Both"]["rules"] == "lightmap" and c["objects"]["Both"]["uv_layer"] == "UVMap_Lightmap"
    miss = uvc(objects=["Both"], uv_layer="Nope")
    assert "error" in miss["objects"]["Both"] and miss["verdict"] == "FAIL"
    assert uv_hash(obj) == before, "measuring changed the UVs"
    return {"render": a["verdict"], "lightmap": b["verdict"]}


def test_c_unwrap_methods_per_object():
    reset()
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    a = bpy.context.object
    a.name = "A"
    bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
    b = bpy.context.object
    b.name = "B"
    other = uv_hash(b)
    res = {}
    for method, extra in (("smart", {}), ("seams", {"seams_from_angle": 30}), ("min_stretch", {"seams_from_angle": 30})):
        r = uvc(objects=["A"], unwrap=True, method=method, margin_px=4, texture_px=1024, **extra)
        e = r["objects"]["A"]
        assert e["method"] == method and e["collapsed_faces"] == 0 and e["overlap_pairs"] == 0, (method, e)
        assert e["verdict"] != "FAIL", (method, e)
        res[method] = {"islands": e["islands"], "coverage": e["uv_coverage"], "stretch": e["stretch_p95"]}
        assert uv_hash(b) == other, f"{method} unwrap touched another object"
    assert a.mode == "OBJECT"
    try:
        uvc(objects=["A"], unwrap=True, method="bogus")
        raise AssertionError("bad method accepted")
    except ValueError:
        pass
    return res


def test_c_result_file_contract():
    reset()
    quads("Q", [sq(0, 0, 1)], {"UVMap": [uvsq(0.1, 0.1, 0.5)]})
    path = os.path.join(OUT, "uv_result.json")
    r = uvc(objects=["Q"], result_path=path, run_id="run-123")
    data = json.load(open(path))
    assert data["run_id"] == "run-123" and data["verdict"] == r["verdict"] and not os.path.exists(path + ".tmp")
    bad = os.path.join(OUT, "uv_result_bad.json")
    try:
        uvc(objects=["Q"], method="bogus", result_path=bad, run_id="x")
    except ValueError:
        pass
    assert not os.path.exists(bad) and not os.path.exists(bad + ".tmp"), "file written on exception"
    return {"verdict": data["verdict"]}


def test_c_speed_20k():
    reset()
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=100, y_segments=100, size=0.5)
    uv = bm.loops.layers.uv.new("UVMap")
    ov = bm.loops.layers.uv.new("Half")
    st = bm.loops.layers.uv.new("AllSame")
    for f in bm.faces:
        cx = f.calc_center_median().x
        for l in f.loops:
            u, v = l.vert.co.x + 0.5, l.vert.co.y + 0.5
            l[uv].uv = (u, v)
            l[ov].uv = (u if cx < 0 else u - 0.5, v)
            l[st].uv = ((l.vert.co.x * 100) % 1.0 * 0.01 + 0.2, (l.vert.co.y * 100) % 1.0 * 0.01 + 0.2)
    me = bpy.data.meshes.new("Grid")
    bm.to_mesh(me)
    bm.free()
    make_obj("Grid", me)
    assert len(me.loop_triangles) == 0 or True
    me.calc_loop_triangles()
    assert len(me.loop_triangles) == 20000, len(me.loop_triangles)
    out = {}
    for name, expect in (("UVMap", "PASS"), ("Half", "FAIL"), ("AllSame", "FAIL")):
        t = time.time()
        e = uvc(objects=["Grid"], uv_layer=name)["objects"]["Grid"]
        dt = time.time() - t
        out[name] = {"seconds": round(dt, 2), "overlap": e["checks"]["overlap"]["status"], "pairs": e["overlap_pairs"]}
        assert e["checks"]["overlap"]["status"] == expect, (name, e["checks"]["overlap"])
        assert dt < 8.0, (name, dt)
    assert out["UVMap"]["pairs"] == 0
    return out


# ------------------------------------------------------------------------------------------ A3 / A4 / A5

def _bake_fixture():
    reset()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = "SM_Bake"
    return obj


def test_a3_bake_size_mismatch():
    _bake_fixture()
    out = os.path.join(OUT, "bakes_a3")
    args = {"low": "SM_Bake", "maps": ["ao"], "size": 32, "samples": 2, "out_dir": out}
    r1 = run("texture-workflow", "bake_maps.py", args)
    assert bpy.data.images["T_Bake_Ao"].size[0] == 32, r1
    args2 = dict(args, size=64)
    try:
        r2 = run("texture-workflow", "bake_maps.py", args2)
    except ValueError as exc:
        assert "32x32" in str(exc), exc
        assert tuple(bpy.data.images["T_Bake_Ao"].size) == (32, 32)
        r3 = run("texture-workflow", "bake_maps.py", args)  # same size reruns fine
        assert r3["sizes"] == {"ao": [32, 32]} and r3["size"] == 32, r3
        assert tuple(bpy.data.images["T_Bake_Ao"].size) == (32, 32)
        return {"refused": str(exc)[:80], "sizes": r3["sizes"]}
    raise AssertionError(f"rerun at another size was accepted; reported size {r2['size']} but image is "
                         f"{tuple(bpy.data.images['T_Bake_Ao'].size)}")


class _Stub:
    """Proxy for a bpy.ops.<group>.<op> call that returns a fixed result and counts its calls."""

    def __init__(self, real, group, op, result):
        self._real, self._group, self._op, self._result = real, group, op, result
        self.calls = 0
        outer = self

        class _Group:
            def __getattr__(g, n):
                if n == outer._op:
                    def fake(*a, **kw):
                        outer.calls += 1
                        return outer._result
                    return fake
                return getattr(getattr(real.ops, outer._group), n)

        class _Ops:
            def __getattr__(o, n):
                return _Group() if n == outer._group else getattr(real.ops, n)

        self.ops = _Ops()

    def __getattr__(self, n):
        return getattr(self._real, n)


def with_stub(group, op, result, fn):
    real = sys.modules["bpy"]
    stub = _Stub(real, group, op, result)
    sys.modules["bpy"] = stub
    try:
        return fn(), stub
    finally:
        sys.modules["bpy"] = real


def test_a4_bake_cancelled():
    _bake_fixture()
    out = os.path.join(OUT, "bakes_a4")
    box = {}

    def go():
        try:
            run("texture-workflow", "bake_maps.py", {"low": "SM_Bake", "maps": ["ao"], "size": 16, "out_dir": out})
        except RuntimeError as exc:
            box["exc"] = exc
    _r, stub = with_stub("object", "bake", {"CANCELLED"}, go)
    assert stub.calls == 1, f"the stub was not reached ({stub.calls} calls)"
    assert "exc" in box, "a CANCELLED bake was saved and listed"
    assert "CANCELLED" in str(box["exc"]), box["exc"]
    assert not os.path.exists(os.path.join(out, "T_Bake_Ao.png")), "saved after a cancelled bake"
    return {"raised": str(box["exc"])[:80], "stub_calls": stub.calls}


def _bake_state():
    scene = bpy.context.scene
    b = scene.render.bake
    mats = {m.name: (m.node_tree.nodes.active.name if m.node_tree.nodes.active else None,
                     sorted(n.name for n in m.node_tree.nodes if n.select))
            for m in bpy.data.materials if m.node_tree}
    return {"sel": sorted(o.name for o in scene.objects if o.select_get()),
            "active": bpy.context.view_layer.objects.active.name,
            "bake": [b.use_selected_to_active, round(b.cage_extrusion, 5), b.margin], "mats": mats,
            "engine": scene.render.engine, "samples": scene.cycles.samples}


def test_bake_restores_state():
    _bake_fixture()
    bpy.ops.mesh.primitive_cube_add(location=(4, 0, 0))
    third = bpy.context.object
    third.name = "Other"
    mat = bpy.data.materials.new("MAT_Pre")
    mat.use_nodes = True
    bpy.data.objects["SM_Bake"].data.materials.append(mat)
    mat.node_tree.nodes.active = mat.node_tree.nodes["Principled BSDF"]
    for n in mat.node_tree.nodes:
        n.select = n.name == "Principled BSDF"
    scene = bpy.context.scene
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.cage_extrusion = 0.123
    scene.render.bake.margin = 7
    for o in scene.objects:
        o.select_set(o.name == "Other")
    bpy.context.view_layer.objects.active = third
    before = _bake_state()
    out = os.path.join(OUT, "bakes_state")
    args = {"low": "SM_Bake", "maps": ["ao"], "size": 16, "samples": 2, "out_dir": out}
    run("texture-workflow", "bake_maps.py", args)
    ok_after = _bake_state()
    assert before["mats"]["MAT_Pre"] == ["Principled BSDF", ["Principled BSDF"]] or \
        before["mats"]["MAT_Pre"] == ("Principled BSDF", ["Principled BSDF"]), before["mats"]

    def go():
        try:
            run("texture-workflow", "bake_maps.py", dict(args, maps=["roughness"]))
        except RuntimeError:
            pass
    _r, stub = with_stub("object", "bake", {"CANCELLED"}, go)
    assert stub.calls == 1
    fail_after = _bake_state()
    for label, got in (("success", ok_after), ("cancelled", fail_after)):
        for key in ("sel", "active", "bake", "engine", "samples", "mats"):
            assert got[key] == before[key], (label, key, got[key], before[key])
    assert "SK_BakeTarget" in bpy.data.materials["MAT_Pre"].node_tree.nodes, "bake target node was not created"
    return {"before": {k: before[k] for k in ("sel", "active", "bake")}}


def test_bake_restores_material_nodes():
    _bake_fixture()
    mat = bpy.data.materials.new("MAT_Pre")
    mat.use_nodes = True
    bpy.data.objects["SM_Bake"].data.materials.append(mat)
    nodes = mat.node_tree.nodes
    nodes.active = nodes["Principled BSDF"]
    for n in nodes:
        n.select = n.name == "Principled BSDF"
    out = os.path.join(OUT, "bakes_nodes")
    run("texture-workflow", "bake_maps.py", {"low": "SM_Bake", "maps": ["ao"], "size": 16, "samples": 2,
                                             "out_dir": out})
    assert nodes.active is not None and nodes.active.name == "Principled BSDF", nodes.active
    assert sorted(n.name for n in nodes if n.select) == ["Principled BSDF"], [n.name for n in nodes if n.select]
    return {"active": nodes.active.name}


def test_a5_emission_default():
    reset()
    bpy.ops.mesh.primitive_cube_add()
    img = bpy.data.images.new("em", 4, 4)
    path = os.path.join(OUT, "em.png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    out = {}
    for label, kw, want in (("texture", {"textures": {"emission": path}}, 1.0),
                            ("texture_explicit_zero", {"textures": {"emission": path}, "emission_strength": 0.0}, 0.0),
                            ("texture_explicit_3", {"textures": {"emission": path}, "emission_strength": 3.0}, 3.0),
                            ("no_texture", {}, 0.0)):
        run("materials", "pbr_material.py", dict({"name": "MAT_Em_" + label}, **kw))
        mat = bpy.data.materials["MAT_Em_" + label]
        got = mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value \
            if "Principled BSDF" in mat.node_tree.nodes else next(
                n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Emission Strength"].default_value
        assert abs(got - want) < 1e-6, (label, got, want)
        out[label] = got
    return out


# ------------------------------------------------------------------------------------------ A16

def test_a16_scatter_uvs():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=40)
    bpy.context.object.name = "Ground"
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))
    bpy.context.object.name = "SM_T"
    r = run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 8, "ground": "Ground"})
    names = [p["name"] for p in r["props"]]
    kinds = {p["kind"] for p in r["props"]}
    chk = uvc(objects=names)
    per = {}
    for n in names:
        e = chk["objects"][n]
        assert e["collapsed_faces"] == 0 and e["overlap_pairs"] == 0, (n, e)
        assert e["verdict"] != "FAIL", (n, e)
        per[e["uv_layer"] + ":" + n.split("_")[2]] = [e["islands"], e["uv_coverage"]]
    gaps = {}
    for kind in kinds:
        obj = next(bpy.data.objects[p["name"]] for p in r["props"] if p["kind"] == kind)
        e = chk["objects"][obj.name]
        assert e["islands"] == len(obj.data.polygons), (kind, e["islands"], len(obj.data.polygons))
        gap = _min_island_gap(obj)
        assert gap >= 0.004 - 1e-6, (kind, gap)
        gaps[kind] = round(gap, 5)
    return {"kinds": sorted(kinds), "per": per, "min_gap": gaps}


# ------------------------------------------------------------------------------------------ Seldon fixes

def test_s_cross_tile_coverage():
    reset()
    quads("Span", [sq(0, 0, 1)], {"UVMap": [[(0, 0), (1.1, 0), (1.1, 1), (0, 1)]]})
    e = uvc(objects=["Span"])["objects"]["Span"]
    cov = e["coverage_per_tile"]
    assert e["udim_tiles"] == [1001, 1002], e["udim_tiles"]
    assert abs(cov["1001"] - 1.0) < 0.02 and abs(cov["1002"] - 0.1) < 0.02, cov
    assert abs(e["uv_coverage"] - 0.55) < 0.02 and e["checks"]["coverage"]["status"] == "WARN", e
    return {"per_tile": cov, "mean": e["uv_coverage"]}


def _tri_obj(name, tris):
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    for k, t in enumerate(tris):
        f = bm.faces.new([bm.verts.new((u, v, k * 0.0 + 0.0 + 0.1 * k)) for u, v in t])
        for l, (u, v) in zip(f.loops, t):
            l[uv].uv = (u, v)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return make_obj(name, me)


def test_s_coverage_counts_only_covered_tiles():
    reset()
    tris = [[(0, 0), (3, 0), (0, 3)],
            [(3, 0), (3, 1), (2, 1)], [(2, 1), (2, 2), (1, 2)], [(1, 2), (1, 3), (0, 3)]]
    # six tiles are filled completely; the triangle's bounding box also touches three empty ones
    # (the three small complements together with the big triangle leave (2,1) and (1,2) tiles empty)
    _tri_obj("Big", tris)
    e = uvc(objects=["Big"], allow_overlap=True)["objects"]["Big"]
    cov = e["coverage_per_tile"]
    assert len(cov) == 6 and all(v > 0.97 for v in cov.values()), cov
    assert e["uv_coverage"] > 0.97 and e["checks"]["coverage"]["status"] == "PASS", e
    return {"tiles": sorted(cov), "mean": e["uv_coverage"]}


def test_s_loops_outside_counts_polygon_loops():
    reset()
    quads("Out", [sq(0, 0, 1)], {"UVMap": [uvsq(1.5, 0.2, 1.0)]})
    e = uvc(objects=["Out"], allow_overlap=True)["objects"]["Out"]
    assert e["loops_outside_0_1"] == 4, e["loops_outside_0_1"]
    return {"loops": e["loops_outside_0_1"]}


def test_s_coverage_sub_sample_strip():
    reset()
    quads("Strip", [sq(0, 0, 1)], {"UVMap": [[(0, 0), (1.0005, 0), (1.0005, 1), (0, 1)]]})
    e = uvc(objects=["Strip"])["objects"]["Strip"]
    assert e["udim_tiles"] == [1001, 1002], e["udim_tiles"]
    assert e["uv_coverage"] < 0.6 and e["checks"]["coverage"]["status"] == "WARN", e["checks"]["coverage"]
    return {"tiles": e["udim_tiles"], "mean": e["uv_coverage"]}


def test_s_lightmap_docs_match_behaviour():
    root = os.path.normpath(os.path.join(SKILLS, "uv-workflow"))
    skill = open(os.path.join(root, "SKILL.md"), encoding="utf8").read()
    doc = open(os.path.join(root, "scripts", "uv_unwrap_check.py"), encoding="utf8").read().split('"""')[1]
    for label, text in (("SKILL.md", skill), ("docstring", doc)):
        assert "creates the missing" in text, f"{label}: lightmap=True creating channels is not documented"
        assert "measured directly" in text, f"{label}: where a sole lightmap channel is reported is not documented"
    reset()
    quads("LM", [sq(0, 0, 1)], {"UVMap_Lightmap": [uvsq(0.1, 0.1, 0.5)]})
    e = uvc(objects=["LM"], lightmap=True)["objects"]["LM"]
    assert e["rules"] == "lightmap" and "lightmap" not in e, e.keys()
    reset()
    bpy.ops.mesh.primitive_cube_add()
    o = bpy.context.object
    o.data.uv_layers.remove(o.data.uv_layers[0])
    e = uvc(objects=[o.name], lightmap=True)["objects"][o.name]
    assert [l.name for l in o.data.uv_layers] == ["UVMap", "UVMap_Lightmap"] and "lightmap" in e, e.keys()
    return {"ok": True}


def test_s_shared_mesh_unwrap():
    reset()
    bpy.ops.mesh.primitive_cube_add()
    a = bpy.context.object
    a.name = "A"
    b = bpy.data.objects.new("B", a.data)  # linked duplicate: same mesh datablock
    bpy.context.scene.collection.objects.link(b)
    before = uv_hash(b)
    r = uvc(objects=["A"], unwrap=True, method="smart", angle_deg=30)
    e = r["objects"]["A"]
    assert "error" in e and "shared" in e["error"], e
    assert uv_hash(b) == before and a.data is b.data, "refusal changed the shared mesh"
    r2 = uvc(objects=["A"], unwrap=True, method="smart", angle_deg=30, make_single_user=True)
    e2 = r2["objects"]["A"]
    assert "error" not in e2 and e2.get("made_single_user") is True, e2
    assert a.data is not b.data and uv_hash(b) == before, "B changed after A was made single-user"
    assert uv_hash(a) != before, "A was not unwrapped"
    return {"refused": e["error"][:70], "copy_name": a.data.name}


def test_s_lightmap_only_rerun():
    reset()
    quads("LM", [sq(0, 0, 1)], {"UVMap_Lightmap": [uvsq(0.1, 0.1, 0.5)]})
    r = uvc(objects=["LM"], lightmap=True)
    e = r["objects"]["LM"]
    assert e["lightmap_channel"] == "UVMap_Lightmap" and e["uv_layers"] == ["UVMap_Lightmap"], e
    r2 = uvc(objects=["LM"], lightmap=True)  # and again
    assert r2["objects"]["LM"]["uv_layers"] == ["UVMap_Lightmap"]
    return {"layers": e["uv_layers"], "verdict": e["verdict"]}


def _sel_state(obj):
    me = obj.data
    return ([v.select for v in me.vertices], [e.select for e in me.edges], [f.select for f in me.polygons])


def _partial_select(obj):
    me = obj.data
    for coll in (me.vertices, me.edges, me.polygons):
        for it in coll:
            it.select = False
    me.vertices[0].select = True
    me.vertices[1].select = True
    me.edges[0].select = True


def test_s_edit_mode_and_selection_restored():
    reset()
    bpy.ops.mesh.primitive_cube_add()
    a = bpy.context.object
    a.name = "A"
    bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
    other = bpy.context.object
    other.name = "Other"
    _partial_select(a)
    sel0 = _sel_state(a)
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "Other")
    bpy.context.view_layer.objects.active = other
    objsel0 = sorted(o.name for o in bpy.context.scene.objects if o.select_get())
    # 1) entered from Object Mode
    uvc(objects=["A"], unwrap=True)
    assert a.mode == "OBJECT" and _sel_state(a) == sel0, "component selection not restored (object mode entry)"
    assert bpy.context.view_layer.objects.active is other
    assert sorted(o.name for o in bpy.context.scene.objects if o.select_get()) == objsel0
    # 2) operator failure
    box = {}

    def go():
        try:
            uvc(objects=["A"], unwrap=True)
        except RuntimeError as exc:
            box["exc"] = exc
    _r, stub = with_stub("uv", "smart_project", {"CANCELLED"}, go)
    assert stub.calls == 1 and "exc" in box, (stub.calls, box)
    assert a.mode == "OBJECT" and _sel_state(a) == sel0, "state not restored after an operator failure"
    assert bpy.context.view_layer.objects.active is other
    assert sorted(o.name for o in bpy.context.scene.objects if o.select_get()) == objsel0
    # 3) entered from Edit Mode
    bpy.context.view_layer.objects.active = a
    for o in bpy.context.scene.objects:
        o.select_set(o is a)
    bpy.ops.object.mode_set(mode="EDIT")  # Blender itself normalises the selection on entry: take the baseline here
    bpy.ops.object.mode_set(mode="OBJECT")
    sel0 = _sel_state(a)
    bpy.ops.object.mode_set(mode="EDIT")
    uvc(objects=["A"], unwrap=True)
    assert a.mode == "EDIT", f"entry mode EDIT not restored, now {a.mode}"
    bpy.ops.object.mode_set(mode="OBJECT")
    assert _sel_state(a) == sel0, "component selection changed (edit mode entry)"
    return {"mode_after": "EDIT restored", "failure": str(box["exc"])[:60]}


def _min_island_gap(obj):
    """Smallest distance between UV edges of different islands (islands from loop-uv connectivity)."""
    me = obj.data
    uv = me.uv_layers.active.uv
    segs = []  # (island face index, p, q)
    for f in me.polygons:
        idx = list(f.loop_indices)
        for k in range(len(idx)):
            p = tuple(uv[idx[k]].vector)
            q = tuple(uv[idx[(k + 1) % len(idx)]].vector)
            segs.append((f.index, p, q))
    # islands via shared uv points
    parent = {f.index: f.index for f in me.polygons}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    pts = {}
    for fi, p, q in segs:
        for pt in (p, q):
            key = (round(pt[0], 5), round(pt[1], 5))
            if key in pts:
                parent[find(fi)] = find(pts[key])
            else:
                pts[key] = fi

    def d_pt_seg(p, a, b):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy or 1)))
        return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)
    best = 9.0
    for i, (fi, p1, q1) in enumerate(segs):
        for fj, p2, q2 in segs[i + 1:]:
            if find(fi) == find(fj):
                continue
            best = min(best, d_pt_seg(p1, p2, q2), d_pt_seg(q1, p2, q2), d_pt_seg(p2, p1, q1), d_pt_seg(q2, p1, q1))
    return best


def test_s_margin_px_enforced():
    out = {}
    for px in (4, 16):
        reset()
        bpy.ops.mesh.primitive_cube_add()
        o = bpy.context.object
        uvc(objects=[o.name], unwrap=True, method="smart", margin_px=px, texture_px=1024)
        gap = _min_island_gap(o)
        want = px / 1024
        out[px] = {"gap": round(gap, 5), "want": round(want, 5)}
        assert 0.8 * want <= gap <= 1.3 * want, ("smart", px, out[px])
    for method in ("seams", "min_stretch"):
        reset()
        bpy.ops.mesh.primitive_cube_add()
        o = bpy.context.object
        uvc(objects=[o.name], unwrap=True, method=method, seams_from_angle=30, margin_px=16, texture_px=1024)
        gap = _min_island_gap(o)
        out[method] = round(gap, 5)
        assert 0.8 * 16 / 1024 <= gap <= 1.3 * 16 / 1024, (method, gap)
    return out


def test_s_run_id_in_returned_result():
    reset()
    quads("Q", [sq(0, 0, 1)], {"UVMap": [uvsq(0.1, 0.1, 0.5)]})
    r = uvc(objects=["Q"], run_id="abc")
    assert r["run_id"] == "abc", r.keys()
    r2 = uvc(objects=["Q"])
    assert "run_id" in r2 and r2["run_id"] is None
    return {"run_id": r["run_id"]}


def _old_style_prop_mesh(name, size, kind="cube"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, size[2] / 2), verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    return me


def _scatter_setup():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=40)
    bpy.context.object.name = "Ground"
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))
    bpy.context.object.name = "SM_T"


def test_s_scatter_reuses_old_mesh():
    _scatter_setup()
    old = _old_style_prop_mesh("ME_Prop_box", (0.6, 0.6, 0.6))
    probe = make_obj("Probe", old)
    pre = uvc(objects=["Probe"])["objects"]["Probe"]
    assert pre["overlap_pairs"] > 0, f"fixture is not an old-style defective mesh: {pre['overlap_pairs']}"
    r = run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 3, "kinds": ["box"], "ground": "Ground"})
    names = [p["name"] for p in r["props"]]
    e = uvc(objects=names)["objects"][names[0]]
    assert e["overlap_pairs"] == 0 and e["collapsed_faces"] == 0 and e["islands"] == 6, e
    assert bpy.data.objects[names[0]].data.name == "ME_Prop_box", "the old mesh was replaced by a new name"
    return {"rebuilt_islands": e["islands"]}


def _cube_like_foreign(name, triangulate=False, extra_uv=False):
    me = _old_style_prop_mesh(name, (0.6, 0.6, 0.6))
    if triangulate:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()
    if extra_uv:
        me.uv_layers.new(name="Authored")
    return me


def test_s_scatter_refuses_same_vertices_other_topology():
    out = {}
    for label, kw in (("triangulated", {"triangulate": True}), ("extra_uv", {"extra_uv": True})):
        _scatter_setup()
        foreign = _cube_like_foreign("ME_Prop_box", **kw)
        faces0 = [tuple(p.vertices) for p in foreign.polygons]
        uvs0 = [l.name for l in foreign.uv_layers]
        try:
            run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 2, "kinds": ["box"], "ground": "Ground"})
        except ValueError as exc:
            assert [tuple(p.vertices) for p in foreign.polygons] == faces0 and [l.name for l in foreign.uv_layers] == uvs0
            out[label] = str(exc)[:50]
            continue
        raise AssertionError(f"{label}: a foreign mesh with the same vertices was adopted and rewritten")
    return out


def test_s_scatter_refuses_authored_uvs():
    _scatter_setup()
    foreign = _cube_like_foreign("ME_Prop_box")
    for d in foreign.uv_layers[0].uv:
        d.vector = (0.25 + 0.1 * d.vector[0], 0.5 + 0.1 * d.vector[1])  # authored coordinates, same layer name
    uv0 = [tuple(d.vector) for d in foreign.uv_layers[0].uv]
    try:
        run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 2, "kinds": ["box"], "ground": "Ground"})
    except ValueError as exc:
        assert [tuple(d.vector) for d in foreign.uv_layers[0].uv] == uv0, "authored UVs were rewritten"
        return {"refused": str(exc)[:60]}
    raise AssertionError("a mesh with authored UVs was adopted and rewritten")


def test_s_scatter_preflight_keeps_previous_props():
    _scatter_setup()
    r1 = run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 3, "kinds": ["box"], "ground": "Ground"})
    first = sorted(p["name"] for p in r1["props"])
    _old_style_prop_mesh("ME_Prop_barrel", (9.0, 0.1, 0.1))  # foreign mesh for a kind used only on the rerun
    try:
        run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 3, "kinds": ["box", "barrel"],
                                                 "clusters": 1, "ground": "Ground"})
    except ValueError:
        now = sorted(o.name for o in bpy.data.collections["COL_SetDressing"].objects)
        assert now == first, f"previous props lost: {first} -> {now}"
        return {"survived": now}
    raise AssertionError("foreign mesh was not refused")


def test_s_scatter_refuses_foreign_mesh():
    _scatter_setup()
    foreign = _old_style_prop_mesh("ME_Prop_box", (3.0, 0.1, 0.1))
    before = [tuple(round(c, 4) for c in v.co) for v in foreign.vertices]
    try:
        run("set-dressing", "scatter_props.py", {"target": "SM_T", "count": 2, "kinds": ["box"], "ground": "Ground"})
    except ValueError as exc:
        assert "ME_Prop_box" in str(exc), exc
        assert [tuple(round(c, 4) for c in v.co) for v in foreign.vertices] == before, "foreign mesh was modified"
        return {"refused": str(exc)[:80]}
    raise AssertionError("a foreign mesh named ME_Prop_box was silently reused or overwritten")


TESTS = (test_a1_measure_only_no_uv, test_a2_union_coverage, test_c_stacked_and_declared,
         test_c_shared_edges_not_overlap, test_c_collapsed_face, test_c_density_spread,
         test_c_stretched_cylinder, test_c_two_channels_opposite_verdicts, test_c_unwrap_methods_per_object,
         test_c_result_file_contract, test_c_speed_20k, test_a3_bake_size_mismatch, test_a4_bake_cancelled,
         test_bake_restores_state, test_bake_restores_material_nodes, test_s_cross_tile_coverage,
         test_s_shared_mesh_unwrap, test_s_lightmap_only_rerun, test_s_edit_mode_and_selection_restored,
         test_s_margin_px_enforced, test_s_run_id_in_returned_result, test_s_scatter_reuses_old_mesh,
         test_s_scatter_refuses_foreign_mesh,
         test_s_coverage_sub_sample_strip, test_s_lightmap_docs_match_behaviour, test_s_scatter_refuses_authored_uvs,
         test_s_coverage_counts_only_covered_tiles, test_s_loops_outside_counts_polygon_loops,
         test_s_scatter_refuses_same_vertices_other_topology, test_s_scatter_preflight_keeps_previous_props,
         test_a5_emission_default, test_a16_scatter_uvs)


def main():
    os.makedirs(OUT, exist_ok=True)
    checks, failed = {}, []
    for fn in TESTS:
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(OUT, "iter15_uv_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
