"""Headless Blender tests for the measured claims fixed in iteration 13, batch E (reference docs).

  E1  mocap-cleanup.md      evaluated error of the recipe's reduced keys: Bezier outside the stated tolerance, linear inside
  E2  scan-match.md         scan-to-model direction sees a part the model lacks; model-to-scan does not
  E3  facial-shape-keys...  Edit Mode vertex add/delete keeps shape keys consistent; an isolated new vertex has zero offset;
                            extrude, duplicate and subdivide give new vertices a non-zero offset
  E4  scatter-systems.md    density = cap / area is a soft cap (count above the cap on some seeds)

Recipes are read from the docs themselves (the first ```python block of each file), so the doc and the test cannot drift.

Run:
    blender -b --factory-startup --python tests/blender/test_iter13_docs.py -- '{"out_dir": "/tmp/iter13-docs"}'
Writes <out_dir>/iter13_docs_report.json with passed / total / failed / checks; exits 1 on a failure.
"""
import json
import os
import re
import sys
import traceback

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def recipe(rel):
    text = open(os.path.join(SKILLS, rel), encoding="utf8").read()
    return re.search(r"```python\n(.*?)```", text, re.S).group(1)


def test_mocap_tolerance():
    out = {}
    for interp in ("BEZIER", "LINEAR"):
        src = recipe("animation/references/mocap-cleanup.md")
        assert 'slot.interpolation = "BEZIER"' in src and "    v = smooth(v, 1.5)\n" in src, "recipe text changed"
        src = src.replace('slot.interpolation = "BEZIER"', f'slot.interpolation = "{interp}"')
        src = src.replace("    v = smooth(v, 1.5)\n", "    v = smooth(v, 1.5)\n    SM[path] = v.copy()\n")
        g = {"SM": {}}
        exec(compile(src, "mocap-recipe", "exec"), g)
        r = {}
        for path in ("location", "rotation_euler"):
            fc = g["curves"][path]
            r[path] = max(abs(fc.evaluate(float(f)) - g["SM"][path][f - 1]) for f in range(1, 121))
        out[interp] = r
    assert out["BEZIER"]["location"] > 0.005 and out["BEZIER"]["rotation_euler"] > 0.01, out
    assert out["LINEAR"]["location"] <= 0.005 and out["LINEAR"]["rotation_euler"] <= 0.01, out
    return {k: {p: round(x, 5) for p, x in v.items()} for k, v in out.items()}


def test_scan_to_model():
    g = {}
    exec(compile(recipe("realistic-style/references/scan-match.md"), "scan-match-recipe", "exec"), g)
    sphere, deviation = g["sphere"], g["deviation"]
    # a scan with a small block standing off the sphere (a "handle") that the model does not have
    bumpy = sphere("ScanWithHandle", (0, 0, 0), True)
    bm = bmesh.new()
    bm.from_mesh(bumpy.data)
    ret = bmesh.ops.create_cube(bm, size=0.1)
    bmesh.ops.translate(bm, verts=ret["verts"], vec=(0.8, 0, 0))
    bm.to_mesh(bumpy.data)
    bm.free()
    bpy.context.view_layer.update()
    model = g["low"]
    m2s_mean, m2s_max = deviation(model, bumpy)
    s2m_mean, s2m_max = deviation(bumpy, model)
    assert m2s_max < 0.02, ("model to scan should stay small", m2s_max)
    assert s2m_max > 0.25, ("scan to model must see the handle", s2m_max)
    # through the recipe's own verdict(): the model lacks the part, so only the scan-to-model distance can fail it
    g["scan"] = bumpy
    diag = g["diagonal"](bumpy)
    assert m2s_max / diag <= 0.015 and m2s_mean / diag <= 0.002, "fixture must pass on the model-to-scan direction alone"
    v = g["verdict"](model)
    assert not v["ok"], ("verdict() passed a model that lacks a part of the scan", v)
    assert v["worst_pct"] > 1.5, v
    return {"model_to_scan_max": round(m2s_max, 4), "scan_to_model_max": round(s2m_max, 4), "verdict": v}


def test_shape_keys_edit_mode():
    me = bpy.data.meshes.new("FaceTest")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("FaceTest", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.shape_key_add(name="Basis")
    smile = ob.shape_key_add(name="smile")
    for v in smile.data:
        v.co.z += 0.5
    n0 = len(me.vertices)
    bpy.ops.object.mode_set(mode="EDIT")
    b = bmesh.from_edit_mesh(me)
    b.verts.new((2, 2, 0))
    bmesh.update_edit_mesh(me)
    bpy.ops.object.mode_set(mode="OBJECT")
    keys = me.shape_keys.key_blocks
    assert len(me.vertices) == n0 + 1 and all(len(k.data) == n0 + 1 for k in keys), "keys not resized after add"
    assert all(abs(keys["smile"].data[i].co.z - keys["Basis"].data[i].co.z - 0.5) < 1e-5 for i in range(n0))
    assert abs(keys["smile"].data[n0].co.z - keys["Basis"].data[n0].co.z) < 1e-6, "new vertex should have zero offset"
    bpy.ops.object.mode_set(mode="EDIT")
    b = bmesh.from_edit_mesh(me)
    b.verts.ensure_lookup_table()
    bmesh.ops.delete(b, geom=[b.verts[0]], context="VERTS")
    bmesh.update_edit_mesh(me)
    bpy.ops.object.mode_set(mode="OBJECT")
    keys = me.shape_keys.key_blocks
    assert len(me.vertices) == n0 and all(len(k.data) == n0 for k in keys), "keys not resized after delete"
    assert all(abs(keys["smile"].data[i].co.z - keys["Basis"].data[i].co.z - 0.5) < 1e-5 for i in range(n0 - 1)), "offsets changed after delete"
    return {"verts": n0, "key_lengths": [len(k.data) for k in keys]}


def _keyed_grid(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.shape_key_add(name="Basis")
    key = ob.shape_key_add(name="smile")
    for i, v in enumerate(key.data):
        v.co.z += 0.1 * (i % 4)  # a different offset per vertex
    return me


def _key_offsets(me):
    ks = me.shape_keys.key_blocks
    return [ks["smile"].data[i].co.z - ks["Basis"].data[i].co.z for i in range(len(me.vertices))]


def _select_vertex(me, idx):
    b = bmesh.from_edit_mesh(me)
    b.verts.ensure_lookup_table()
    for v in b.verts:
        v.select = False
    b.verts[idx].select = True
    b.select_flush(True)
    bmesh.update_edit_mesh(me)


def test_shape_keys_copying_ops():
    """Extrude, duplicate and subdivide on a keyed mesh: key lengths follow the mesh, new vertices are NOT zero offset."""
    out = {}
    for op in ("extrude", "duplicate", "subdivide"):
        me = _keyed_grid("Keyed_" + op)
        n0, before = len(me.vertices), _key_offsets(me)
        bpy.ops.object.mode_set(mode="EDIT")
        if op == "subdivide":
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.subdivide(number_cuts=1)
        else:
            _select_vertex(me, 5)
            if op == "extrude":
                bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, 0.3)})
            else:
                bpy.ops.mesh.duplicate()
        bpy.ops.object.mode_set(mode="OBJECT")
        after = _key_offsets(me)
        assert len(me.vertices) > n0 and all(len(k.data) == len(me.vertices) for k in me.shape_keys.key_blocks), op
        assert all(abs(after[i] - before[i]) < 1e-5 for i in range(n0)), ("old offsets changed", op)
        new = after[n0:]
        assert any(abs(x) > 1e-4 for x in new), ("new vertices all have zero offset", op, new)
        out[op] = {"new_vertices": len(new), "new_offsets": [round(x, 4) for x in new]}
    # extrude and duplicate copy vertex 5 (offset 0.1); extrude then moves only the Basis position by 0.3
    assert abs(out["duplicate"]["new_offsets"][0] - 0.1) < 1e-4, out
    assert abs(out["extrude"]["new_offsets"][0] - (0.1 - 0.3)) < 1e-4, out
    # subdivide interpolates: every new offset lies within the old range
    assert all(-1e-4 <= x <= 0.3 + 1e-4 for x in out["subdivide"]["new_offsets"]), out
    return out


def test_scatter_soft_cap():
    me = bpy.data.meshes.new("CapGround")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=20, y_segments=20, size=5.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("CapGround", me)
    bpy.context.scene.collection.objects.link(ob)
    ng = bpy.data.node_groups.new("CapScatter", "GeometryNodeTree")
    io = ng.interface
    io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    io.new_socket("Density", in_out="INPUT", socket_type="NodeSocketFloat")
    io.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt")
    io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin, gout = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    dist = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
    dist.distribute_method = "RANDOM"
    p2v = ng.nodes.new("GeometryNodePointsToVertices")
    ln = ng.links
    ln.new(gin.outputs["Geometry"], dist.inputs["Mesh"])
    ln.new(gin.outputs["Density"], dist.inputs["Density"])
    ln.new(gin.outputs["Seed"], dist.inputs["Seed"])
    ln.new(dist.outputs["Points"], p2v.inputs["Points"])
    ln.new(p2v.outputs["Mesh"], gout.inputs["Geometry"])
    mod = ob.modifiers.new("cap", "NODES")
    mod.node_group = ng
    ids = {i.name: i.identifier for i in ng.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    area = 100.0
    out = {}
    for cap in (500, 100):
        getattr(mod.properties.inputs, ids["Density"]).value = cap / area
        counts = []
        for seed in range(100):
            getattr(mod.properties.inputs, ids["Seed"]).value = seed
            ob.update_tag()
            bpy.context.view_layer.update()
            ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            counts.append(len(ev.data.vertices))
        out[str(cap)] = {"min": min(counts), "max": max(counts), "mean": sum(counts) / len(counts),
                         "seeds_over_cap": sum(c > cap for c in counts)}
        assert out[str(cap)]["seeds_over_cap"] > 0, ("cap / area was a hard cap here", out)
    return out


def test_shape_key_doc_text():
    """The doc must not contradict the measurements: Edit Mode add/delete keeps keys, and key lengths grow with the mesh."""
    text = open(os.path.join(SKILLS, "rigging/references/facial-shape-keys-drivers.md"), encoding="utf8").read()
    assert "never add or delete vertices once keys exist" not in text, "stale blanket ban on vertex edits"
    assert "key lengths were unchanged" not in text, "key lengths grow with the vertex count"
    assert "key length equals mesh vertex count" in text
    return {"checked": 3}


def main():
    args = _cli_args()
    out_dir = args.get("out_dir", ".")
    os.makedirs(out_dir, exist_ok=True)
    checks, failed = {}, []
    for fn in (test_mocap_tolerance, test_scan_to_model, test_shape_keys_edit_mode, test_shape_keys_copying_ops, test_scatter_soft_cap, test_shape_key_doc_text):
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks}
    with open(os.path.join(out_dir, "iter13_docs_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    sys.exit(1 if failed else 0)


main()
