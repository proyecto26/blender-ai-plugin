"""Smoke-test every skill script inside a real Blender (5.2+), in isolation.

Builds a throwaway test scene in a NEW scene datablock, runs each script with
representative ARGS, asserts on the returned result dict, then deletes the test
scene. Never saves the file.

Run headless (recommended):
    blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/blender-skill-tests"}'

Or through the official Blender MCP, against a scratch .blend:
    execute_blender_code_for_cli(blend_file="/tmp/empty.blend", code=
        'import runpy; result = runpy.run_path("<repo>/tests/blender/test_skill_scripts.py", '
        'init_globals={"ARGS": {"out_dir": "/tmp/blender-skill-tests"}})["result"]')
"""
import json
import os
import runpy
import struct
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _cube(name, size=1.0, loc=(0, 0, 0), collection=None, segments=0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if segments:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=segments, use_grid_fill=True)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, size / 2))
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    obj.location = loc
    return obj


def _sphere(name, radius=0.5, collection=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _grid(name, size=5.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=size)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def run_globals(skill, script, args):
    """Like run(), but also reports whether the script exposes a callable main() (the script contract)."""
    path = os.path.join(SKILLS, skill, "scripts", script)
    g = runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")
    return {"has_main": callable(g.get("main")), "result": g["result"]}


def glb_nodes(path):
    """Node names from the JSON chunk of a .glb (or from a .gltf file)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] == b"glTF":
        length, kind = struct.unpack("<I4s", data[12:20])
        assert kind == b"JSON", "first GLB chunk is not JSON"
        doc = json.loads(data[20:20 + length].decode("utf-8"))
    else:
        doc = json.loads(data.decode("utf-8"))
    return [n.get("name", "") for n in doc.get("nodes", [])]


def _bbox_centre(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(pts, Vector()) / len(pts)


def _tag(obj):
    v = obj.get("collision_proxy")
    if v is None:
        return None
    source, _, engine = str(v).rpartition("|")  # make_collision tags "<source>|<engine>"
    return {"source": source, "engine": engine}


def _objs(prefix):
    return sorted(o.name for o in bpy.data.objects if o.name.startswith(prefix))


def _camera_occlusion_case(stage):
    """Camera rig occlusion: free view, wall between camera and target, then a hide_render wall."""
    if "SM_CamTarget" not in bpy.data.objects:
        _cube("SM_CamTarget", 1.0, loc=(30, 30, 0))
    args = {"name": "CAM_Occ_Test", "target": "SM_CamTarget", "lens_mm": 50}
    r = run("camera-cinematography", "camera_rig.py", args)
    if stage == "free":
        return r
    bpy.context.view_layer.update()
    cam = bpy.data.objects["CAM_Occ_Test"]
    centre = _bbox_centre(bpy.data.objects["SM_CamTarget"])
    mid = cam.matrix_world.translation.lerp(centre, 0.5)
    wall = bpy.data.objects.get("WALL_Occ_Test") or _cube("WALL_Occ_Test", 1.0)
    wall.scale = (1.2, 1.2, 1.2)
    wall.location = (mid.x, mid.y, mid.z - 0.6)
    wall.hide_render = stage == "hidden_wall"
    bpy.context.view_layer.update()
    return run("camera-cinematography", "camera_rig.py", args)


def _glb_check(r, expected, forbidden=("OTHER_Selected",)):
    """Exported nodes contain the requested objects, none of the other-scene object, and verify.ok is true."""
    nodes = set(glb_nodes(r["path"]))
    v = r.get("verify") or {}
    return bool(r["exists"] and set(expected) <= nodes and not (nodes & set(forbidden))
                and v.get("ok") is True and not v.get("missing") and not v.get("leaked"))


def _blockout_twice(args, group):
    r1 = run("environment-artist", "blockout.py", args)
    n1 = len([o for o in bpy.data.objects if o.get("blockout") == group])
    meshes1, objs1 = len(bpy.data.meshes), len(bpy.data.objects)
    run("environment-artist", "blockout.py", args)
    n2 = len([o for o in bpy.data.objects if o.get("blockout") == group])
    return {"first": r1, "n1": n1, "n2": n2, "meshes1": meshes1, "meshes2": len(bpy.data.meshes),
            "objs1": objs1, "objs2": len(bpy.data.objects)}


def _rerun2(skill, script, args_a, args_b):
    return {"a": run(skill, script, args_a), "b": run(skill, script, args_b)}


def _scatter_twice():
    args = {"target": "SM_Crate_01", "count": 6, "max_dist": 3.0, "min_dist": 0.4, "clusters": 2, "seed": 3,
            "ground": "GEO_Ground"}
    r1 = run("set-dressing", "scatter_props.py", args)
    r2 = run("set-dressing", "scatter_props.py", args)
    centre = _bbox_centre(bpy.data.objects["SM_Crate_01"])
    props = [bpy.data.objects[p["name"]] for p in r2["props"]]
    max_xy = max(((o.matrix_world.translation.xy - centre.xy).length for o in props), default=0.0)
    col = bpy.data.collections["COL_SetDressing"]
    return {"count1": r1["count"], "count2": r2["count"], "max_dist": r2.get("max_dist"), "max_xy": max_xy,
            "props2": len([o for o in col.objects if o.name.startswith("PROP_")]),
            "extra_props": [o.name for o in col.objects if not o.name.startswith("PROP_")]}


OUT = None


def _wc(args):
    return run("blender-mcp-workflow", "work_copy.py", args)


def _mesh_sig(obj):
    return (tuple(round(c, 5) for v in obj.data.vertices for c in v.co), tuple(obj.scale), tuple(obj.location))


def _work_copy_accept():
    crate = _cube("SM_Crate", 1.0)
    crate.scale = (1.2, 0.8, 1.5)
    sock = bpy.data.objects.new("SOCKET_Crate_Top", None)
    bpy.context.scene.collection.objects.link(sock)
    sock.parent = crate
    sig = _mesh_sig(crate)
    begin = _wc({"action": "begin", "objects": ["SM_Crate"]})
    run("blender-mcp-workflow", "fix_asset.py", {"objects": [begin["pairs"]["SM_Crate"]]})
    untouched = _mesh_sig(bpy.data.objects["SM_Crate"]) == sig
    acc = _wc({"action": "accept"})
    new = bpy.data.objects["SM_Crate"]
    prev = bpy.data.objects[acc["accepted"]["SM_Crate"]["checkpoint"]]
    cp = bpy.data.collections["__Checkpoint"]
    ex = run("unreal-export", "export_unreal.py", {"mesh": "SM_Crate", "out_dir": os.path.join(OUT, "wc_unreal")})
    return {"untouched_during": untouched, "scale_applied": tuple(new.scale) == (1.0, 1.0, 1.0),
            "socket_parent": sock.parent is new, "prev_in_cp": prev.name in cp.objects, "prev_sig": _mesh_sig(prev) == sig,
            "no_work_left": "SM_Crate__work" not in bpy.data.objects and "__Work" not in bpy.data.collections,
            "exported": ex["exported"], "sockets": ex["sockets"],
            "excluded": any(lc.exclude for lc in bpy.context.view_layer.layer_collection.children
                            if lc.name == "__Checkpoint"),
            "status": _wc({"action": "status"})["pending"]}


def _work_copy_revert():
    obj = _cube("SM_Revert", 1.0)
    obj.scale = (1.2, 0.8, 1.5)
    obj.data.materials.append(bpy.data.materials.new("MAT_Revert"))
    before = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.collections),
              _mesh_sig(obj))
    b = _wc({"action": "begin", "objects": ["SM_Revert"], "materials": True})
    run("blender-mcp-workflow", "fix_asset.py", {"objects": [b["pairs"]["SM_Revert"]]})
    mid_pending = _wc({"action": "status"})["pending"]
    _wc({"action": "revert"})
    after = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.collections),
             _mesh_sig(bpy.data.objects["SM_Revert"]))
    return {"mid_pending": mid_pending, "before": before, "after": after,
            "pending_after": _wc({"action": "status"})["pending"]}


def _work_copy_twice():
    _cube("SM_Twice", 1.0)
    _wc({"action": "begin", "objects": ["SM_Twice"]})
    err = None
    try:
        _wc({"action": "begin", "objects": ["SM_Twice"]})
    except Exception as exc:  # the error text is the assertion
        err = str(exc)
    _wc({"action": "revert"})
    return {"error": err, "pending_after": _wc({"action": "status"})["pending"]}


def _expect_error(fn):
    try:
        fn()
    except Exception as exc:
        return str(exc)
    return None


def _manifest_case():
    import hashlib
    d = os.path.join(OUT, "manifest_run")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "model.glb"), "wb") as fh:
        fh.write(b"abc")
    base = {"out_dir": d, "skill": "blender-mcp-workflow", "script": "validate_asset.py", "args": {"objects": ["SM_Crate_01"]}}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    run("blender-director", "run_manifest.py", {"out_dir": d, "brief": {"asset": "SM_Crate_01"}})
    rm(stage="validate", verdict="PASS", result_summary={"fails": 0})
    r2 = rm(stage="export", verdict="PASS", exports=["model.glb"], result_summary={"exists": True})
    outside = _expect_error(lambda: rm(stage="verify", verdict="PASS", exports=[os.path.join(d, "..", "x.glb")]))
    outside_cap = _expect_error(lambda: rm(stage="verify", verdict="PASS", capture="../shot.png"))
    with open(os.path.join(d, "run_manifest.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    with open(os.path.join(SKILLS, "blender-director", "references", "run-manifest.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    item = schema["properties"]["events"]["items"]
    keys_ok = all(k in m for k in schema["required"]) and all(all(k in e for k in item["required"]) for e in m["events"])
    enums_ok = all(e["stage"] in item["properties"]["stage"]["enum"] and e["verdict"] in item["properties"]["verdict"]["enum"]
                   for e in m["events"])
    rm(stage="validate", verdict="FAIL", reason="n-gons")
    blocked = _expect_error(lambda: rm(stage="export", verdict="PASS"))
    need_cause = _expect_error(lambda: rm(stage="validate", verdict="FAIL", reason="n-gons again"))
    stopped = rm(stage="validate", verdict="FAIL", reason="n-gons again", cause="geometry")
    return {"events": len(m["events"]), "r2_events": r2["events"], "hash": m["events"][1]["exports"][0]["sha256"],
            "expect_hash": hashlib.sha256(b"abc").hexdigest(), "outside": outside, "outside_cap": outside_cap,
            "keys_ok": keys_ok, "enums_ok": enums_ok, "blocked": blocked, "need_cause": need_cause,
            "stop": stopped["stop"], "blocked_by": stopped["blocked_by"], "final_events": stopped["events"]}


def _world_close(a, b, tol=1e-5):
    return all(abs(a[i][j] - b[i][j]) <= tol for i in range(4) for j in range(4))


def _kid_scene(parent_name, kid_name, loc=(1.0, 2.0, 0.0), rot_z=0.5, scale=2.0):
    """Scaled + rotated parent cube with an offset empty child (non-identity parent inverse)."""
    parent = _cube(parent_name, 1.0, loc=loc)
    parent.scale = (scale, scale, scale)
    parent.rotation_euler = (0.0, 0.0, rot_z)
    kid = bpy.data.objects.new(kid_name, None)
    bpy.context.scene.collection.objects.link(kid)
    bpy.context.view_layer.update()
    kid.parent = parent
    kid.matrix_parent_inverse = parent.matrix_world.inverted()
    kid.location = (0.0, 0.0, 0.5)
    bpy.context.view_layer.update()
    return parent, kid


def _fix_asset_children_world():
    parent, kid = _kid_scene("SM_FixKidP", "SOCKET_FixKid")
    before = kid.matrix_world.copy()
    run("blender-mcp-workflow", "fix_asset.py", {"objects": ["SM_FixKidP"]})
    bpy.context.view_layer.update()
    return {"kid_world_kept": _world_close(before, kid.matrix_world), "applied": tuple(parent.scale) == (1.0, 1.0, 1.0),
            "z": round(kid.matrix_world.translation.z, 4)}


def _fix_asset_vertex_children():
    import bmesh as _bm
    from mathutils import Euler, Matrix as _M
    out = {}
    for mode in ("scale", "rotation_scale"):
        me = bpy.data.meshes.new(f"FixVP_{mode}")
        bm = _bm.new()
        _bm.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        parent = bpy.data.objects.new(f"SM_FixVP_{mode}", me)
        bpy.context.scene.collection.objects.link(parent)
        parent.scale = (2.0, 0.5, 1.5)
        parent.rotation_euler = Euler((0.3, 0.2, 0.7))
        hidden = bpy.data.collections.new(f"FixVP_hidden_{mode}")
        bpy.context.scene.collection.children.link(hidden)
        kids = {}
        for kind, ptype, coll, constrain in (("obj", "OBJECT", None, False), ("vert", "VERTEX", None, False),
                                             ("tri", "VERTEX_3", None, False), ("zero", "OBJECT", None, False),
                                             ("con", "VERTEX_3", None, True), ("excl", "VERTEX_3", hidden, False)):
            k = bpy.data.objects.new(f"FixVK_{mode}_{kind}", None)
            (coll or bpy.context.scene.collection).objects.link(k)
            k.parent = parent
            k.parent_type = ptype
            if ptype == "VERTEX":
                k.parent_vertices[0] = 2
            elif ptype == "VERTEX_3":
                k.parent_vertices = (0, 3, 5)
            k.location = (0.3, -0.2, 0.4)
            k.rotation_euler = Euler((0.1, 0.5, -0.2))
            if kind == "zero":
                k.scale = (0.0, 1.0, 1.0)
            if constrain:
                k.constraints.new("LIMIT_LOCATION")
            kids[kind] = k
        bpy.context.view_layer.update()
        bpy.context.view_layer.layer_collection.children[hidden.name].exclude = True
        before = {n: k.matrix_world.copy() for n, k in kids.items()}
        r = run("blender-mcp-workflow", "fix_asset.py", {"objects": [parent.name], "apply": mode, "uv": ""})
        bpy.context.view_layer.update()
        rep = r["objects"][parent.name]
        reported = {c["name"]: c["reason"] for c in rep.get("children_not_preserved", [])}
        out[mode] = {
            "kept": {n: _world_close(before[n], kids[n].matrix_world) for n in ("obj", "vert", "tri", "zero")},
            "reported": reported,
            "con_reason": reported.get(kids["con"].name), "excl_reason": reported.get(kids["excl"].name),
            "applied": rep["applied"]}
    return out


def _work_copy_child_world():
    parent, kid = _kid_scene("SM_WcKidP", "SOCKET_WcKid")
    before = kid.matrix_world.copy()
    b = _wc({"action": "begin", "objects": ["SM_WcKidP"]})
    run("blender-mcp-workflow", "fix_asset.py", {"objects": [b["pairs"]["SM_WcKidP"]]})
    _wc({"action": "accept"})
    bpy.context.view_layer.update()
    return {"kid_world_kept": _world_close(before, kid.matrix_world), "parent_is_new": kid.parent is bpy.data.objects["SM_WcKidP"],
            "applied": tuple(bpy.data.objects["SM_WcKidP"].scale) == (1.0, 1.0, 1.0)}


def _work_copy_set_checkpoint():
    """Parent and child both in the work set: the checkpoint originals must stay exactly as they were."""
    parent = _cube("SM_SetP", 1.0, loc=(4.0, 5.0, 0.0))
    parent.scale = (1.5, 1.5, 1.5)
    bpy.context.view_layer.update()
    child = _cube("SM_SetC", 0.5, loc=(0.5, 0.0, 0.0))
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    bpy.context.view_layer.update()
    child_world = child.matrix_world.copy()
    pinv = child.matrix_parent_inverse.copy()
    _wc({"action": "begin", "objects": ["SM_SetP", "SM_SetC"]})
    _wc({"action": "accept"})
    bpy.context.view_layer.update()
    prev_p, prev_c = bpy.data.objects["SM_SetP__prev"], bpy.data.objects["SM_SetC__prev"]
    return {"prev_child_parent": prev_c.parent.name if prev_c.parent else None,
            "prev_child_world": _world_close(child_world, prev_c.matrix_world),
            "prev_child_pinv": _world_close(pinv, prev_c.matrix_parent_inverse),
            "new_child_parent": bpy.data.objects["SM_SetC"].parent.name if bpy.data.objects["SM_SetC"].parent else None,
            "prev_parent_is_prev": prev_p.name}


def _manifest_validate_gate():
    d = os.path.join(OUT, "manifest_gate")
    os.makedirs(d, exist_ok=True)
    base = {"out_dir": d, "skill": "blender-mcp-workflow", "script": "validate_asset.py"}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    rm(stage="model", verdict="PASS")
    missing = _expect_error(lambda: rm(stage="export", verdict="PASS"))
    rm(stage="validate", verdict="NOT_CHECKED", reason="not run yet")
    not_checked = _expect_error(lambda: rm(stage="export", verdict="PASS"))
    verify_nc = _expect_error(lambda: rm(stage="verify", verdict="PASS"))
    rm(stage="validate", verdict="N/A", reason="no mesh output")
    ok_na = rm(stage="export", verdict="PASS")
    rm(stage="validate", verdict="PASS")
    ok_verify = rm(stage="verify", verdict="PASS")
    return {"missing": missing, "not_checked": not_checked, "verify_nc": verify_nc,
            "export_after_na": ok_na["gates"]["export"], "verify_after_pass": ok_verify["gates"]["verify"]}


def _collision_dup_survives():
    _cube("SM_DupCol", 1.0, loc=(-12, 0, 0))
    run("collision-proxy", "make_collision.py", {"objects": ["SM_DupCol"], "shape": "box", "engine": "unreal"})
    dup = bpy.data.objects["UCX_SM_DupCol_01"].copy()
    dup.name = "MY_HANDMADE_HULL"
    bpy.context.scene.collection.objects.link(dup)
    r = run("collision-proxy", "make_collision.py", {"objects": ["SM_DupCol"], "shape": "box", "engine": "unreal"})
    return {"survives": "MY_HANDMADE_HULL" in bpy.data.objects, "removed": r["removed"],
            "proxies": _objs("UCX_SM_DupCol_")}


def _camera_eye_height_case():
    _cube("SM_EyeT", 1.0, loc=(60, 60, 0))
    r = run("camera-cinematography", "camera_rig.py", {"name": "CAM_Eye_Test", "target": "SM_EyeT", "eye_height": 1.6,
                                                        "azimuth_deg": 40})
    cam = bpy.data.objects["CAM_Eye_Test"]
    centre = _bbox_centre(bpy.data.objects["SM_EyeT"])
    ok = abs((cam.matrix_world.translation - centre).length - r["distance_m"]) < 2e-3
    clamp = run("camera-cinematography", "camera_rig.py", {"name": "CAM_Eye_Clamp", "target": "SM_EyeT", "eye_height": 400.0,
                                                           "max_distance": 5.0})
    return {"distance_matches": ok, "notes_free": r["notes"], "notes_clamp": clamp["notes"], "z": r["location"][2]}


def build_cases(out_dir):
    """Each case: (id, callable returning result, assertion on result)."""
    global OUT
    OUT = out_dir
    W = "blender-mcp-workflow"
    return [
        ("core.setup_collections", lambda: run(W, "setup_collections.py", {"asset": "Crate"}),
         lambda r: "COL_Crate_Export" in r["created"] + r["existing"]),
        ("core.scene_audit", lambda: run(W, "scene_audit.py", {"tri_budget": 100000}),
         lambda r: r["object_count"] > 0 and "naming_violations" in r),
        ("core.validate_asset", lambda: run(W, "validate_asset.py", {"objects": ["SM_Crate_01"], "tri_budget": 5000}),
         lambda r: r["objects"]["SM_Crate_01"]["checks"]["transforms_applied"]["status"] == "PASS"),
        ("core.capture_views", lambda: run(W, "capture_views.py", {"target": "SM_Crate_01", "out_dir": out_dir,
                                                                  "views": ["three_quarter"], "resolution": 128}),
         lambda r: all(os.path.exists(p) for p in r["images"])),
        ("hard-surface.bevel_stack", lambda: run("hard-surface", "bevel_stack.py", {"objects": ["SM_Crate_01"], "width": 0.02}),
         lambda r: r["objects"]["SM_Crate_01"]["evaluated_tris"] > 12),
        ("materials.pbr_material", lambda: run("materials", "pbr_material.py", {
            "name": "MAT_CratePaint", "base_color": [0.3, 0.2, 0.1], "roughness": 0.6, "objects": ["SM_Crate_01"]}),
         lambda r: r["assigned"] == ["SM_Crate_01"]),
        ("uv-workflow.uv_unwrap_check", lambda: run("uv-workflow", "uv_unwrap_check.py", {
            "objects": ["SM_Crate_01"], "unwrap": True, "texture_px": 1024}),
         lambda r: r["objects"]["SM_Crate_01"]["texel_density_px_per_m"] > 0),
        ("geometry-nodes.scatter_points", lambda: run("geometry-nodes", "scatter_points.py", {
            "surface": "GEO_Ground", "collection": "COL_Rocks", "density": 1.0}),
         lambda r: r["instances"] > 10),
        ("lighting.light_rig", lambda: run("lighting", "light_rig.py", {"preset": "studio_3pt", "target": "SM_Crate_01"}),
         lambda r: len(r["lights"]) == 3),
        ("lighting.light_rig_rerun", lambda: run("lighting", "light_rig.py", {"preset": "horror_practical"}),
         lambda r: len(r["lights"]) == 2 and len([o for o in bpy.data.collections["COL_Lights"].objects]) == 2),
        ("camera.camera_rig", lambda: run("camera-cinematography", "camera_rig.py", {
            "name": "CAM_Hero_01", "target": "SM_Crate_01", "lens_mm": 85, "dof_fstop": 2.8, "aspect": "16:9"}),
         lambda r: r["active"] and r["distance_m"] > 0),
        ("rendering.render_preset", lambda: run("rendering", "render_preset.py", {"preset": "cycles_preview"}),
         lambda r: r["engine"] == "CYCLES" and not r["skipped"]),
        ("rendering.render_preset_eevee", lambda: run("rendering", "render_preset.py", {"preset": "eevee_final"}),
         lambda r: r["engine"] == "BLENDER_EEVEE" and not r["skipped"]),
        ("compositing.comp_grade", lambda: run("compositing", "comp_grade.py", {"preset": "horror_vhs"}),
         lambda r: len(r["nodes"]) >= 4),
        ("compositing.comp_grade_rerun", lambda: run("compositing", "comp_grade.py", {"preset": "cinematic"}),
         lambda r: "SK_Pixelate" not in r["nodes"]),
        ("compositing.comp_grade_vignette", lambda: run("compositing", "comp_grade.py", {
            "preset": "clean", "vignette": 0.35, "warmth": 0.4}),
         lambda r: {"SK_Vignette", "SK_ColorBalance"} <= set(r["nodes"])),
        ("lod-pipeline.generate_lods", lambda: run("lod-pipeline", "generate_lods.py", {
            "object": "SM_Sphere_01", "ratios": [0.5, 0.25]}),
         lambda r: r["lods"][1]["tris"] < r["lods"][0]["tris"] and r["lods"][2]["tris"] < r["lods"][1]["tris"]),
        ("collision-proxy.make_collision", lambda: run("collision-proxy", "make_collision.py", {
            "objects": ["SM_Sphere_01"], "shape": "convex", "engine": "unreal", "max_hull_verts": 32}),
         lambda r: r["proxies"][0]["name"].startswith("UCX_SM_Sphere_01") and r["proxies"][0]["verts"] <= 32),
        ("export-pipeline.fbx", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "unreal", "out_path": os.path.join(out_dir, "SM_Crate_01.fbx")}),
         lambda r: r["exists"] and r["bytes"] > 1000),
        ("export-pipeline.glb", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "web", "out_path": os.path.join(out_dir, "SM_Crate_01.glb")}),
         lambda r: r["bytes"] > 500 and _glb_check(r, {"SM_Crate_01"}) and set(glb_nodes(r["path"])) == {"SM_Crate_01"}),
        ("unreal-export.export_unreal", lambda: run("unreal-export", "export_unreal.py", {
            "mesh": "SM_Sphere_01", "out_dir": out_dir, "strict": False}),
         lambda r: r["exported"] and r["collision"] and r["checks"]["prefix"] == "PASS"
         and r["verify"]["ok"] and {"SM_Sphere_01", *r["collision"]} <= set(r["verify"]["nodes"])),
        ("unity-export.export_unity", lambda: run("unity-export", "export_unity.py", {
            "objects": ["SM_Crate_01"], "out_path": os.path.join(out_dir, "unity", "SM_Crate_01.fbx")}),
         lambda r: r["exported"] and r["verify"]["ok"] and r["verify"]["nodes"] == ["SM_Crate_01"]),
        ("godot-export.export_godot", lambda: run("godot-export", "export_godot.py", {
            "objects": ["SM_Crate_01", "SM_Crate_01-colonly"], "out_path": os.path.join(out_dir, "godot", "crate.glb")}),
         lambda r: r["exported"] and r["import_hints"].get("SM_Crate_01-colonly") == "-colonly"
         and set(glb_nodes(r["path"])) == {"SM_Crate_01", "SM_Crate_01-colonly"}
         and (r.get("verify") or {}).get("ok") is True),
        ("rigging.rig_check", lambda: run("rigging", "rig_check.py", {"armature": "ARM_Test"}),
         lambda r: r["deform_bones"] == 3 and r["unpaired_side_bones"] == [] and "SK_Arm" in r["meshes"]),
        ("animation.turntable", lambda: run("animation", "turntable.py", {"target": "SM_Crate_01", "frames": 48}),
         lambda r: r["frames"][1] - r["frames"][0] == 47),
        ("lowpoly-style.ps1_look", lambda: run("lowpoly-style", "ps1_look.py", {"objects": ["SM_Sphere_01"], "snap": 0.05}),
         lambda r: r["snapped"] == ["SM_Sphere_01"] and r["resolution"] == [320, 240]),
        ("lowpoly-style.ps1_look_fog_texture", lambda: run("lowpoly-style", "ps1_look.py", {
            "objects": ["SM_Sphere_01"], "flat": True, "fog": [0.2, 0.2, 0.25]}),
         lambda r: r["fog_node"] == "SK_PS1_Fog"),
        ("stylized-style.toon_material", lambda: run("stylized-style", "toon_material.py", {
            "name": "Toon_Test", "base_color": [0.9, 0.4, 0.3], "bands": 3, "objects": ["SM_Rock_A"], "outline": 0.01}),
         lambda r: r["outlined"] == ["SM_Rock_A"] and r["bands"] == 3),
        ("voxel-style.voxelize", lambda: run("voxel-style", "voxelize.py", {"objects": ["SM_Rock_B"], "voxel_size": 0.05}),
         lambda r: r["objects"]["SM_Rock_B"]["faces"] > 6),
        ("isometric-style.iso_camera", lambda: run("isometric-style", "iso_camera.py", {"projection": "dimetric_2_1", "pixel_tile": 32}),
         lambda r: r["ortho_scale"] > 0 and r["resolution"][0] % 32 == 0),
        ("physics-sim.rigid_body_setup", lambda: run("physics-sim", "rigid_body_setup.py", {
            "active": ["SM_Rock_B"], "passive": ["GEO_Ground"], "material": "stone", "frames": 20, "bake": True}),
         lambda r: r["active"]["SM_Rock_B"]["mass_kg"] > 0 and r.get("baked") is True),
        ("cloth-sim.cloth_setup", lambda: run("cloth-sim", "cloth_setup.py", {
            "cloth": "SM_Flag", "fabric": "silk", "pin_group": "Pin", "colliders": ["SM_Crate_01"]}),
         lambda r: r["pinned"] and r["colliders"] == ["SM_Crate_01"]),
        ("retopology.topology_report", lambda: run("retopology", "topology_report.py", {
            "objects": ["SM_Flag", "SM_Sphere_01"], "deforming": True}),
         lambda r: r["objects"]["SM_Flag"]["verdict"] == "PASS" and r["objects"]["SM_Sphere_01"]["tris"] > 0),
        ("asset-optimization.optimize_mesh", lambda: run("asset-optimization", "optimize_mesh.py", {
            "objects": ["SM_Dirty"], "merge_distance": 0.001}),
         lambda r: r["objects"]["SM_Dirty"]["after"]["verts"] < r["objects"]["SM_Dirty"]["before"]["verts"]),
        ("texture-workflow.bake_maps", lambda: run("texture-workflow", "bake_maps.py", {
            "low": "SM_Crate_01", "high": "HP_Crate_01", "maps": ["normal", "ao"], "size": 64, "samples": 4,
            "out_dir": os.path.join(out_dir, "bakes")}),
         lambda r: len(r["images"]) == 2 and all(os.path.exists(p) for p in r["images"])),

        # ---- iteration 6: leak-proof exports, idempotency, occlusion, distance contract ----
        ("export-pipeline.glb_skinned", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SK_Arm", "ARM_Test"], "engine": "web", "out_path": os.path.join(out_dir, "skinned.glb")}),
         lambda r: _glb_check(r, {"SK_Arm", "ARM_Test"}) and {"spine", "arm.L", "arm.R"} <= set(glb_nodes(r["path"]))),
        ("unity-export.fbx_skinned_verify", lambda: run("unity-export", "export_unity.py", {
            "objects": ["SK_Arm", "ARM_Test"], "out_path": os.path.join(out_dir, "unity", "skinned.fbx"), "strict": False}),
         lambda r: r["verify"]["ok"] and {"SK_Arm", "ARM_Test"} <= set(r["verify"]["nodes"])
         and r["verify"]["leaked"] == [] and r["verify"]["missing"] == []),
        ("export-pipeline.glb_other_scene_excluded", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Sphere_01"], "engine": "web", "out_path": os.path.join(out_dir, "sphere.glb")}),
         lambda r: _glb_check(r, {"SM_Sphere_01"}) and "SM_Crate_01" not in glb_nodes(r["path"])),
        ("collision-proxy.rerun_x3_single_proxy", lambda: [
            run("collision-proxy", "make_collision.py", {"objects": ["SM_Sphere_01"], "shape": "box", "engine": "unity"})
            for _ in range(3)][-1],
         lambda r: _objs("SM_Sphere_01_COL_") == ["SM_Sphere_01_COL_01"] and r["proxies"][0]["name"] == "SM_Sphere_01_COL_01"
         and _tag(bpy.data.objects["SM_Sphere_01_COL_01"]) == {"source": "SM_Sphere_01", "engine": "unity"}),
        ("collision-proxy.replace_false_appends", lambda: run("collision-proxy", "make_collision.py", {
            "objects": ["SM_Sphere_01"], "shape": "box", "engine": "unity", "replace": False}),
         lambda r: _objs("SM_Sphere_01_COL_") == ["SM_Sphere_01_COL_01", "SM_Sphere_01_COL_02"]),
        ("collision-proxy.replace_true_collapses", lambda: run("collision-proxy", "make_collision.py", {
            "objects": ["SM_Sphere_01"], "shape": "box", "engine": "unity"}),
         lambda r: _objs("SM_Sphere_01_COL_") == ["SM_Sphere_01_COL_01"]),
        ("collision-proxy.other_engine_untouched", lambda: run("collision-proxy", "make_collision.py", {
            "objects": ["SM_Sphere_01"], "shape": "box", "engine": "generic"}),
         lambda r: _objs("SM_Sphere_01_COL_") == ["SM_Sphere_01_COL_01"] and _objs("COL_SM_Sphere_01_") == ["COL_SM_Sphere_01_01"]),
        ("collision-proxy.name_conflict_reported", lambda: (
            _cube("UCX_SM_ColTest_01", 0.5), _cube("SM_ColTest", 1.0, loc=(-9, 0, 0)),
            run("collision-proxy", "make_collision.py", {"objects": ["SM_ColTest"], "shape": "box", "engine": "unreal"}))[-1],
         lambda r: "UCX_SM_ColTest_01" in json.dumps(r.get("name_conflicts"))
         and _tag(bpy.data.objects["UCX_SM_ColTest_01"]) is None
         and r["proxies"][0]["name"] != "UCX_SM_ColTest_01"),
        ("camera.occlusion_free_view", lambda: _camera_occlusion_case("free"),
         lambda r: r["occluded_by"] == [] and r["visible_fraction"] == 1.0),
        ("camera.occlusion_wall_reported", lambda: _camera_occlusion_case("wall"),
         lambda r: "WALL_Occ_Test" in r["occluded_by"] and r["visible_fraction"] < 1.0),
        ("camera.occlusion_hide_render_ignored", lambda: _camera_occlusion_case("hidden_wall"),
         lambda r: r["occluded_by"] == [] and r["visible_fraction"] == 1.0),
        ("blender-mcp-workflow.fix_asset_main_contract", lambda: run_globals("blender-mcp-workflow", "fix_asset.py", {
            "objects": ["SM_FixMe"]}),
         lambda g: g["has_main"] and g["result"]["objects"]["SM_FixMe"]["uv_added"] == "box"
         and tuple(bpy.data.objects["SM_FixMe"].scale) == (1.0, 1.0, 1.0)
         and len(bpy.data.objects["SM_FixMe"].data.uv_layers) == 1
         and abs(bpy.data.objects["SM_FixMe"].dimensions.x - 2.4) < 1e-3),
        ("blender-mcp-workflow.fix_asset_rerun", lambda: run("blender-mcp-workflow", "fix_asset.py", {"objects": ["SM_FixMe"]}),
         lambda r: r["objects"]["SM_FixMe"]["uv_added"] is None and len(r["objects"]["SM_FixMe"]["uv_layers"]) == 1),
        ("environment-artist.blockout_ring", lambda: _blockout_twice({
            "group": "TestRing", "pieces": [{"kind": "box", "size": [1.8, 0.6, 1.1]}],
            "layout": {"pattern": "ring", "count": 6, "radius": 4.0, "center": "SM_Crate_01", "face_center": True}}, "TestRing"),
         lambda r: r["n1"] == 6 and r["n1"] == r["n2"] and r["meshes1"] == r["meshes2"] and r["objs1"] == r["objs2"]),
        ("environment-artist.blockout_room", lambda: _blockout_twice({
            "group": "TestRoom", "room": {"size": [6, 8, 3], "at": [-20, -20], "wall": 0.2,
                                          "fixtures": {"size": [0.8, 0.3], "spacing": 3.0, "lights": False}}}, "TestRoom"),
         lambda r: r["n1"] >= 1 and r["n1"] == r["n2"] and r["meshes1"] == r["meshes2"] and r["objs1"] == r["objs2"]),
        ("procedural-modeling.gn_curve_profile", lambda: _rerun2("procedural-modeling", "gn_curve_profile.py", {
            "name": "GEO_TestPipe", "points": [[0, -5, 0.5], [0, 5, 0.5]], "radius": 0.15}, {
            "name": "GEO_TestPipe", "points": [[0, -5, 0.5], [0, 5, 0.5], [3, 5, 0.5]], "radius": 0.3, "resolution": 8}),
         lambda r: len(_objs("GEO_TestPipe")) == 1 and r["b"]["object"] == "GEO_TestPipe"
         and r["b"]["evaluated"]["verts"] != r["a"]["evaluated"]["verts"]
         and len(bpy.data.objects["GEO_TestPipe"].modifiers) == 1 and r["b"]["radius"] == 0.3),
        ("set-dressing.scatter_props_max_dist", lambda: _scatter_twice(),
         lambda r: r["count1"] == 6 and r["count2"] == 6 and r["props2"] == 6 and r["max_xy"] <= 3.0 + 1e-3
         and r["max_dist"] == 3.0 and not r["extra_props"]),
        ("vfx-fx.smoke_domain", lambda: _rerun2("vfx-fx", "smoke_domain.py", {"emitter": "SM_Crate_01", "flow_type": "BOTH"},
                                                {"emitter": "SM_Crate_01", "flow_type": "BOTH"}),
         lambda r: r["a"]["domain"] == r["b"]["domain"] and r["b"]["flow_type"] == "BOTH"
         and len([o for o in bpy.data.objects if o.name.startswith(r["b"]["domain"].split(".")[0])]) == 1
         and len([o for o in bpy.data.objects if any(m.type == "FLUID" and m.fluid_type == "DOMAIN" for m in o.modifiers)]) == 1),
        ("hd-2d-style.sprite_billboard", lambda: run("hd-2d-style", "sprite_billboard.py", {
            "name": "SPR_Test", "location": [-4, 3], "height": 1.6}),
         lambda r: r["object"] == "SPR_Test" and abs(bpy.data.objects["SPR_Test"].dimensions.z - 1.6) < 1e-2
         and r["interpolation"] == "Closest"),
        ("work-copy.accept_remaps_children", lambda: _work_copy_accept(),
         lambda r: r["untouched_during"] and r["scale_applied"] and r["socket_parent"] and r["prev_in_cp"] and r["prev_sig"]
         and r["no_work_left"] and r["exported"] and "SOCKET_Crate_Top" in r["sockets"] and r["excluded"]
         and not r["status"]),
        ("work-copy.revert_identical", lambda: _work_copy_revert(),
         lambda r: r["mid_pending"] and r["before"] == r["after"] and not r["pending_after"]),
        ("work-copy.begin_twice_errors", lambda: _work_copy_twice(),
         lambda r: r["error"] and "pending" in r["error"] and not r["pending_after"]),
        ("director.run_manifest", lambda: _manifest_case(),
         lambda r: r["events"] == 2 and r["r2_events"] == 2 and r["hash"] == r["expect_hash"]
         and r["outside"] and "outside" in r["outside"] and r["outside_cap"] and "outside" in r["outside_cap"]
         and r["keys_ok"] and r["enums_ok"] and r["blocked"] and "blocked" in r["blocked"]
         and r["need_cause"] and "cause" in r["need_cause"] and r["stop"] is True
         and r["blocked_by"] == "validate" and r["final_events"] == 4),
        ("blender-mcp-workflow.fix_asset_children_keep_world", lambda: _fix_asset_children_world(),
         lambda r: r["kid_world_kept"] and r["applied"]),
        ("blender-mcp-workflow.fix_asset_vertex_children_keep_world", lambda: _fix_asset_vertex_children(),
         lambda r: all(m["applied"] and all(m["kept"].values()) and m["con_reason"] == "constraints"
                       and m["excl_reason"] == "not evaluated in the active view layer" and len(m["reported"]) == 2
                       for m in r.values())),
        ("work-copy.accept_children_keep_world", lambda: _work_copy_child_world(),
         lambda r: r["kid_world_kept"] and r["parent_is_new"] and r["applied"]),
        ("work-copy.checkpoint_set_untouched", lambda: _work_copy_set_checkpoint(),
         lambda r: r["prev_child_parent"] == "SM_SetP__prev" and r["prev_child_world"] and r["prev_child_pinv"]
         and r["new_child_parent"] == "SM_SetP"),
        ("director.export_needs_validate_pass", lambda: _manifest_validate_gate(),
         lambda r: r["missing"] and "validate" in r["missing"] and r["not_checked"] and "validate" in r["not_checked"]
         and r["verify_nc"] and r["export_after_na"] == "PASS" and r["verify_after_pass"] == "PASS"),
        ("collision-proxy.user_duplicate_survives", lambda: _collision_dup_survives(),
         lambda r: r["survives"] and r["proxies"] == ["UCX_SM_DupCol_01"]),
        ("camera.eye_height_distance_and_notes", lambda: _camera_eye_height_case(),
         lambda r: r["distance_matches"] and r["notes_free"] == [] and len(r["notes_clamp"]) == 1 and abs(r["z"] - 1.6) < 1e-3),
    ]


def _fixtures(scene):
    """Extra objects for rigging, cloth, bake, cleanup and engine-export cases."""
    # Armature with spine + mirrored arms, and a skinned mesh weighted to all deform bones.
    arm_data = bpy.data.armatures.new("ARM_Test")
    arm = bpy.data.objects.new("ARM_Test", arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=[arm],
                                   selected_editable_objects=[arm]):
        bpy.ops.object.mode_set(mode="EDIT")
        spine = arm_data.edit_bones.new("spine")
        spine.head, spine.tail = (0, 0, 0), (0, 0, 1)
        for side, x in (("L", 1), ("R", -1)):
            b = arm_data.edit_bones.new(f"arm.{side}")
            b.head, b.tail, b.parent = (0, 0, 1), (x, 0, 1), spine
        bpy.ops.object.mode_set(mode="OBJECT")
    skin = _cube("SK_Arm", 1.0, segments=1)
    skin.location = (0, 3, 0)
    for bone in ("spine", "arm.L", "arm.R"):
        vg = skin.vertex_groups.new(name=bone)
        vg.add([v.index for v in skin.data.vertices], 0.33, "REPLACE")
    mod = skin.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    # Cloth plane with a pin group on one edge.
    me = bpy.data.meshes.new("SM_Flag")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=1.0)
    bm.to_mesh(me)
    bm.free()
    flag = bpy.data.objects.new("SM_Flag", me)
    scene.collection.objects.link(flag)
    flag.location = (0, -3, 2)
    pin = flag.vertex_groups.new(name="Pin")
    pin.add([v.index for v in me.vertices if v.co.x < -0.99], 1.0, "REPLACE")
    # High-poly bake source around the crate.
    hp = _sphere("HP_Crate_01", 0.75)
    hp.location = (0, 0, 0.5)
    # Mesh with duplicate vertices for cleanup.
    dirty = _cube("SM_Dirty", 0.5)
    dirty.location = (-3, 0, 0)
    bm = bmesh.new()
    bm.from_mesh(dirty.data)
    bmesh.ops.split_edges(bm, edges=bm.edges)
    bm.to_mesh(dirty.data)
    bm.free()
    # Unapplied scale and no UVs, for fix_asset.
    fixme = _cube("SM_FixMe", 2.0, loc=(8, 8, 0))
    fixme.data.uv_layers.remove(fixme.data.uv_layers[0])
    fixme.scale = (1.2, 0.8, 1.5)
    # Godot collision-only twin.
    col_twin = _cube("SM_Crate_01-colonly", 1.0)
    col_twin.hide_render = True


def _other_scene():
    """A second scene holding a SELECTED object: exports must never pick it up (use_active_scene)."""
    other = bpy.data.scenes.new("__SkillTestsOther")
    me = bpy.data.meshes.new("OTHER_Selected")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("OTHER_Selected", me)
    other.collection.objects.link(obj)
    obj.select_set(True, view_layer=other.view_layers[0])
    return other


def main(out_dir=None, only=None):
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "blender-skill-tests")
    os.makedirs(out_dir, exist_ok=True)
    window = bpy.context.window
    original_scene = window.scene if window else bpy.context.scene
    scene = bpy.data.scenes.new("__SkillTests")
    if window:
        window.scene = scene
    created_before = {c.name for c in bpy.data.collections}
    results, passed, other = [], 0, None
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]) if not window else _nullctx():
            _cube("SM_Crate_01", 1.0)
            _sphere("SM_Sphere_01", 0.5).location = (2.5, 0, 0.5)
            _grid("GEO_Ground", 5.0)
            rocks = bpy.data.collections.new("COL_Rocks")
            scene.collection.children.link(rocks)
            _cube("SM_Rock_A", 0.2, collection=rocks)
            _cube("SM_Rock_B", 0.3, collection=rocks)
            _fixtures(scene)
            other = _other_scene()
            for case_id, fn, check in build_cases(out_dir):
                if only and not any(case_id.startswith(o) for o in only):
                    continue
                try:
                    res = fn()
                    ok = bool(check(res))
                    results.append({"case": case_id, "ok": ok, "result": res if not ok else None})
                except Exception:
                    results.append({"case": case_id, "ok": False, "error": traceback.format_exc()[-800:]})
                passed += results[-1]["ok"]
    finally:
        if window:
            window.scene = original_scene
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        if other is not None:
            for obj in list(other.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.scenes.remove(other)
        for name in {c.name for c in bpy.data.collections} - created_before:
            bpy.data.collections.remove(bpy.data.collections[name])
    return {"blender": bpy.app.version_string, "passed": passed, "total": len(results),
            "failures": [r for r in results if not r["ok"]], "cases": [r["case"] for r in results], "out_dir": out_dir}


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
with open(os.path.join(result["out_dir"], "skill_tests_report.json"), "w", encoding="utf-8") as _fh:
    json.dump(result, _fh, indent=2, default=str)  # report file: some Blender launchers do not forward stdout
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["passed"] == result["total"] else 1)
