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
        return {"refused": str(exc)[:80], "sizes": r3.get("sizes")}
    raise AssertionError(f"rerun at another size was accepted; reported size {r2['size']} but image is "
                         f"{tuple(bpy.data.images['T_Bake_Ao'].size)}")


class _ObjOps:
    def __init__(self, real):
        self._real = real

    def bake(self, **kw):
        return {"CANCELLED"}

    def __getattr__(self, n):
        return getattr(self._real, n)


class _Ops:
    def __init__(self, real):
        self._real = real
        self.object = _ObjOps(real.object)

    def __getattr__(self, n):
        return getattr(self._real, n)


class _Bpy:
    def __init__(self, real):
        self._real = real
        self.ops = _Ops(real.ops)

    def __getattr__(self, n):
        return getattr(self._real, n)


def test_a4_bake_cancelled():
    _bake_fixture()
    out = os.path.join(OUT, "bakes_a4")
    real = sys.modules["bpy"]
    sys.modules["bpy"] = _Bpy(real)
    try:
        run("texture-workflow", "bake_maps.py", {"low": "SM_Bake", "maps": ["ao"], "size": 16, "out_dir": out})
    except RuntimeError as exc:
        assert not os.path.exists(os.path.join(out, "T_Bake_Ao.png")), "saved after a cancelled bake"
        return {"raised": str(exc)[:80]}
    finally:
        sys.modules["bpy"] = real
    raise AssertionError("a CANCELLED bake was saved and listed")


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
    return {"kinds": sorted(kinds), "per": per}


TESTS = (test_a1_measure_only_no_uv, test_a2_union_coverage, test_c_stacked_and_declared,
         test_c_shared_edges_not_overlap, test_c_collapsed_face, test_c_density_spread,
         test_c_stretched_cylinder, test_c_two_channels_opposite_verdicts, test_c_unwrap_methods_per_object,
         test_c_result_file_contract, test_c_speed_20k, test_a3_bake_size_mismatch, test_a4_bake_cancelled,
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
