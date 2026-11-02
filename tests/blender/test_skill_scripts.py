"""Smoke-test every skill script inside a real Blender (5.2+), in isolation.

Builds a throwaway test scene in a NEW scene datablock, runs each script with
representative ARGS, asserts on the returned result dict, then deletes the test
scene. Never saves the file.

Run headless (recommended), with a new out_dir each run because a reused one produces false failures:
    blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/bst-<new folder>"}'

Or through the official Blender MCP, against a scratch .blend:
    execute_blender_code_for_cli(blend_file="/tmp/empty.blend", code=
        'import runpy; result = runpy.run_path("<repo>/tests/blender/test_skill_scripts.py", '
        'init_globals={"ARGS": {"out_dir": "/tmp/bst-<new folder>"}})["result"]')
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


def _validate_evidence(d, name="validate_ev.json", obj="SM_EvidenceOk"):
    """A genuine result file from validate_asset.py, written fresh. Returns (path relative to d, verdict)."""
    if "SM_EvidenceOk" not in bpy.data.objects:
        _cube("SM_EvidenceOk", 1.0, loc=(60, 60, 0)).data.materials.append(bpy.data.materials.new("MAT_EvidenceOk"))
    res = run("blender-mcp-workflow", "validate_asset.py", {"objects": [obj], "evidence_path": os.path.join(d, name)})
    return name, res["verdict"]


def _failing_validate_evidence(d, name="validate_fail.json"):
    """A genuine validate_asset.py result that FAILs: a mesh with no SM_ prefix and an unapplied scale."""
    if "BadEvidence" not in bpy.data.objects:
        _cube("BadEvidence", 1.0, loc=(62, 60, 0)).scale = (2, 1, 1)
    res = run("blender-mcp-workflow", "validate_asset.py", {"objects": ["BadEvidence"], "evidence_path": os.path.join(d, name)})
    assert res["verdict"] == "FAIL", res["verdict"]
    return name


def _export_evidence(d, name="export_ev.json", glb="model.glb"):
    """A genuine result file from export_asset.py, written fresh, next to the exported file."""
    run("export-pipeline", "export_asset.py", {"objects": ["SM_Crate_01"], "engine": "web", "out_path": os.path.join(d, glb),
                                               "evidence_path": os.path.join(d, name)})
    return name


def _manifest_case():
    import hashlib
    d = os.path.join(OUT, "manifest_run")
    os.makedirs(d, exist_ok=True)
    base = {"out_dir": d, "skill": "blender-mcp-workflow", "script": "validate_asset.py", "args": {"objects": ["SM_Crate_01"]}}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    run("blender-director", "run_manifest.py", {"out_dir": d, "brief": {"asset": "SM_Crate_01"}})
    ev, verdict = _validate_evidence(d)
    rm(stage="validate", verdict="PASS", result_summary={"fails": 0}, evidence=ev, warn=verdict == "WARN", reason="crate WARN accepted")
    r2 = rm(stage="export", verdict="PASS", exports=["model.glb"], result_summary={"exists": True}, script="export_asset.py",
            evidence=_export_evidence(d))
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
            "expect_hash": hashlib.sha256(open(os.path.join(d, "model.glb"), "rb").read()).hexdigest(),
            "ev_hash": m["events"][1]["evidence"]["sha256"], "ev_script": m["events"][1]["evidence"]["script"],
            "ev_expect": hashlib.sha256(open(os.path.join(d, "export_ev.json"), "rb").read()).hexdigest(), "outside": outside, "outside_cap": outside_cap,
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


def _capture_ignores_marker_cameras(out_dir):
    """A marker bound to another camera must not hijack the capture camera (film scenes have one per shot)."""
    import numpy as np
    cam_data = bpy.data.cameras.new("__MarkerCam")
    other = bpy.data.objects.new("__MarkerCam", cam_data)
    bpy.context.scene.collection.objects.link(other)
    other.location = (0, 0, 200)  # far above, looking down at nothing in particular
    marker = bpy.context.scene.timeline_markers.new("__MarkerShot", frame=bpy.context.scene.frame_current)
    marker.camera = other
    try:
        r = run("blender-mcp-workflow", "capture_views.py", {"target": "SM_Crate_01", "out_dir": out_dir,
                                                             "views": ["front", "top"], "resolution": 96})
        px = []
        for p in r["images"]:
            img = bpy.data.images.load(p)
            px.append(np.array(img.pixels[:], dtype=np.float32))
            bpy.data.images.remove(img)
        diff = float(np.abs(px[0] - px[1]).mean())
        return {"views_differ": diff > 0.01, "diff": round(diff, 4), "binding_restored": marker.camera is other}
    finally:
        bpy.context.scene.timeline_markers.remove(marker)
        bpy.data.objects.remove(other)
        bpy.data.cameras.remove(cam_data)


def _export_keeps_state(skill, script, args):
    """An export must leave the scene camera and the Edit Mode it found: the exporters leave Edit Mode and move
    frames, which lets a marker bound to another camera replace scene.camera."""
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    saved = (scene.camera, view_layer.objects.active, list(bpy.context.selected_objects))
    objs, marker = [], None
    edit = bpy.data.objects["SM_Crate_01"]
    try:
        for n in ("__StateCam", "__StateMarkerCam"):
            objs.append(bpy.data.objects.new(n, bpy.data.cameras.new(n)))
            scene.collection.objects.link(objs[-1])
        marker = scene.timeline_markers.new("__StateMarker", frame=scene.frame_current)
        marker.camera = objs[1]
        scene.camera = objs[0]
        view_layer.objects.active = edit
        edit.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        r = run(skill, script, args)
        return {"exported": r.get("exists", r.get("exported")), "verify_ok": (r.get("verify") or {}).get("ok"),
                "camera": scene.camera.name if scene.camera else None, "mode": edit.mode,
                "active": view_layer.objects.active.name if view_layer.objects.active else None}
    finally:
        try:
            if edit.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            scene.camera, view_layer.objects.active = saved[0], saved[1]
            for o in bpy.context.selected_objects:
                o.select_set(False)
            for o in saved[2]:
                o.select_set(True)
            if marker:
                scene.timeline_markers.remove(marker)
            for o in objs:
                data = o.data
                bpy.data.objects.remove(o)
                bpy.data.cameras.remove(data)


def _kept_state(r):
    return r["exported"] and r["camera"] == "__StateCam" and r["mode"] == "EDIT" and r["active"] == "SM_Crate_01"


def _export_empty_mesh(skill, script, out_path):
    """glTF omits a mesh with no geometry and keeps the node: the read-back must not call that a good export."""
    mesh = bpy.data.meshes.new("__EmptyMesh")
    obj = bpy.data.objects.new("SM_EmptyProbe", mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        args = {"objects": [obj.name], "out_path": out_path}
        if skill == "export-pipeline":
            args["engine"] = "godot"
        return run(skill, script, args)["verify"]
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)


def _export_instancer(out_path):
    """A vertex instancer that hides itself exports as a transform node plus its child: that is a good export."""
    bm_mesh = bpy.data.meshes.new("__InstancerMesh")
    bm_mesh.from_pydata([(0, 0, 0), (3, 0, 0)], [], [])
    inst = bpy.data.objects.new("SM_InstancerProbe", bm_mesh)
    inst.instance_type = "VERTS"
    inst.show_instancer_for_render = False
    bpy.context.scene.collection.objects.link(inst)
    child = bpy.data.objects["SM_Crate_01"].copy()
    child.name = "SM_InstancerChild"
    bpy.context.scene.collection.objects.link(child)
    child.parent = inst
    try:
        return run("export-pipeline", "export_asset.py", {"objects": [inst.name, child.name], "engine": "godot",
                                                          "out_path": out_path})["verify"]
    finally:
        bpy.data.objects.remove(child)
        bpy.data.objects.remove(inst)
        bpy.data.meshes.remove(bm_mesh)


def _capture_keeps_depth(out_dir):
    im = bpy.context.scene.render.image_settings
    saved = (im.media_type, im.file_format, im.color_depth)
    im.file_format, im.color_depth = "OPEN_EXR", "32"
    try:
        run("blender-mcp-workflow", "capture_views.py", {"target": "SM_Crate_01", "out_dir": out_dir,
                                                         "views": ["front"], "resolution": 64})
        return {"fmt": im.file_format, "depth": im.color_depth}
    finally:
        im.media_type, im.file_format = saved[0], saved[1]
        im.color_depth = saved[2]


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


def _manifest_evidence():
    import hashlib
    d = os.path.join(OUT, "manifest_evidence")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "shot.png"), "wb") as fh:
        fh.write(b"png")
    base = {"out_dir": d, "skill": "lighting", "script": "camera_rig.py", "stage": "light_camera"}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    summary = {"occluded_by": []}
    no_capture = _expect_error(lambda: rm(verdict="PASS", result_summary=summary))
    ghost = _expect_error(lambda: rm(verdict="PASS", result_summary=summary, capture="missing.png"))
    empties = [_expect_error(lambda v=v: rm(verdict="PASS", capture="shot.png", result_summary=v)) for v in (None, {}, "  ")]
    no_capture_nc = rm(verdict="NOT_CHECKED", reason="window minimized")
    good = rm(verdict="PASS", result_summary=summary, capture="shot.png")
    with open(os.path.join(d, "run_manifest.json"), encoding="utf-8") as fh:
        last = json.load(fh)["events"][-1]
    return {"no_capture": no_capture, "ghost": ghost, "empties": empties, "nc": no_capture_nc["gates"]["light_camera"],
            "good": good["gates"]["light_camera"], "hash": last.get("capture_sha256"), "bytes": last.get("capture_bytes"),
            "expect": hashlib.sha256(b"png").hexdigest()}


def _turntable_tall_fits():
    from bpy_extras.object_utils import world_to_camera_view
    scene = bpy.context.scene
    r = scene.render
    saved = (r.resolution_x, r.resolution_y, r.resolution_percentage, scene.frame_start, scene.frame_end,
             scene.frame_current, scene.camera)
    box = _cube("SM_TallFit", 1.0, loc=(30, 30, 0))
    cam = bpy.data.objects["CAM_Turntable"]
    xs, ys = [], []
    try:
        r.resolution_percentage = 100
        for size, res, fit in (((0.3, 0.3, 2.0), (1280, 720), "AUTO"), ((2.0, 0.3, 0.3), (720, 1280), "AUTO"),
                               ((0.3, 0.3, 2.0), (1280, 720), "VERTICAL"), ((0.3, 0.3, 2.0), (1280, 720), "HORIZONTAL"),
                               ((2.0, 0.3, 0.3), (720, 1280), "VERTICAL"), ((2.0, 0.3, 0.3), (720, 1280), "HORIZONTAL")):
            box.scale = size
            r.resolution_x, r.resolution_y = res
            cam.data.sensor_fit = fit
            bpy.context.view_layer.update()
            run("animation", "turntable.py", {"target": "SM_TallFit", "frames": 8, "set_active": False})
            for frame in range(scene.frame_start, scene.frame_start + 8):
                scene.frame_set(frame)
                for corner in box.bound_box:
                    p = world_to_camera_view(scene, cam, box.matrix_world @ Vector(corner))
                    xs.append(p.x)
                    ys.append(p.y)
        return {"x": [round(min(xs), 3), round(max(xs), 3)], "y": [round(min(ys), 3), round(max(ys), 3)]}
    finally:
        cam.data.sensor_fit = "AUTO"
        r.resolution_x, r.resolution_y, r.resolution_percentage = saved[:3]
        run("animation", "turntable.py", {"target": "SM_Crate_01", "frames": 48})
        scene.frame_start, scene.frame_end = saved[3], saved[4]
        scene.frame_set(saved[5])
        scene.camera = saved[6]
        bpy.data.objects.remove(box)


def _hold_render_lock(out_dir):
    """Hold an out_dir's lock the way a running background_render.py does, from a separate descriptor."""
    fd = os.open(os.path.join(out_dir, "render.lock"), os.O_CREAT | os.O_RDWR)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _release_render_lock(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)


def _background_render():
    scene = bpy.context.scene
    r = scene.render
    saved = (r.engine, r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage, r.use_overwrite,
             scene.frame_start, scene.frame_end, scene.frame_current, r.image_settings.media_type,
             r.image_settings.file_format)
    handlers = len(bpy.app.handlers.render_post)
    d = os.path.join(OUT, "bg_render")
    status_path = os.path.join(d, "render_status.json")
    read = lambda: json.load(open(status_path, encoding="utf-8"))
    args = {"out_dir": d, "frame_start": 1, "frame_end": 2}
    try:
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x, r.resolution_y, r.resolution_percentage = 32, 32, 100
        r.image_settings.media_type = "IMAGE"
        r.image_settings.file_format = "PNG"
        res = run("rendering", "background_render.py", args)
        first = read()
        repeat = _expect_error(lambda: run("rendering", "background_render.py", args))
        repeat_state = read()["state"]
        again = run("rendering", "background_render.py", dict(args, overwrite=True))["state"]
        kept_error = _expect_error(lambda: run("rendering", "background_render.py", dict(args, overwrite=True, device="NOPE")))
        kept_state = read()["state"]
        refused = json.load(open(os.path.join(d, "render_refused.json"), encoding="utf-8"))
        refused_later = refused["time"] > read()["started"] and "device" in refused["error"]
        with open(os.path.join(d, "render_status.json"), encoding="utf-8") as fh:
            good_status = fh.read()
        with open(os.path.join(d, "render_status.json"), "w", encoding="utf-8") as fh:
            fh.write("[]")
        unreadable = _expect_error(lambda: run("rendering", "background_render.py", dict(args)))
        with open(os.path.join(d, "render_status.json"), "w", encoding="utf-8") as fh:
            fh.write(good_status)
        bad_dir = d + "_bad"
        bad_device = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=bad_dir, device="NOPE")))
        bad_state = json.load(open(os.path.join(bad_dir, "render_status.json"), encoding="utf-8"))
        busy_dir = d + "_busy"
        os.makedirs(busy_dir, exist_ok=True)
        with open(os.path.join(busy_dir, "render_status.json"), "w", encoding="utf-8") as fh:
            json.dump({"state": "running"}, fh)
        busy = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=busy_dir)))
        busy_state = json.load(open(os.path.join(busy_dir, "render_status.json"), encoding="utf-8"))["state"]
        died = run("rendering", "background_render.py", dict(args, out_dir=busy_dir, overwrite=True))["state"]
        held_dir = d + "_held"
        os.makedirs(held_dir, exist_ok=True)
        held_status = os.path.join(held_dir, "render_status.json")
        lock = _hold_render_lock(held_dir)
        try:
            held = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=held_dir)))
            held_no_status = not os.path.exists(held_status)
            with open(held_status, "w", encoding="utf-8") as fh:
                json.dump({"state": "running", "started": 1}, fh)
            held_over = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=held_dir, overwrite=True)))
            held_kept = json.load(open(held_status, encoding="utf-8")) == {"state": "running", "started": 1}
            held_reason = json.load(open(os.path.join(held_dir, "render_refused.json"), encoding="utf-8"))["error"]
        finally:
            _release_render_lock(lock)
        after_held = run("rendering", "background_render.py", dict(args, out_dir=held_dir, overwrite=True))["state"]
        # bad_dir's run took the lock and was refused inside it, so this shows the refusal gave the lock back.
        _release_render_lock(_hold_render_lock(bad_dir))
        r.engine = "CYCLES"
        cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
        have = {t[0] for t in cycles_prefs.get_device_types(bpy.context)}
        absent = next(t for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL") if t not in have)
        no_backend = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=d + "_none", device=absent)))
        r.engine = "BLENDER_WORKBENCH"
        strays = _expect_error(lambda: run("rendering", "background_render.py", dict(args, frame_start=3, frame_end=4)))
        r.image_settings.media_type = "VIDEO"
        movie = _expect_error(lambda: run("rendering", "background_render.py", dict(args, overwrite=True)))
        r.image_settings.media_type = "IMAGE"
        r.image_settings.file_format = "PNG"
        # A plan measures one frame and leaves the folder ready; its refusals never become a status.
        plan_dir = d + "_plan"
        plan = run("rendering", "background_render.py", dict(args, out_dir=plan_dir, plan=True))
        plan_saved = json.load(open(os.path.join(plan_dir, "render_plan.json"), encoding="utf-8"))
        # Two frames: the first pays the start-up cost, so the second is timed too and the estimate adds the first once.
        plan_math = abs(plan["expected_s"] - (plan["first_frame_s"] + plan["seconds_per_frame"]) ) <= 0.06
        one = run("rendering", "background_render.py", dict(args, out_dir=d + "_plan1", frame_end=1, plan=True))
        plan_clean = not os.path.exists(os.path.join(plan_dir, "render_status.json")) and not os.listdir(os.path.join(plan_dir, "frames"))
        after_plan = run("rendering", "background_render.py", dict(args, out_dir=plan_dir))["state"]
        plan_done = _expect_error(lambda: run("rendering", "background_render.py", dict(args, plan=True)))
        plan_bad_dir = d + "_plan_bad"
        plan_bad = _expect_error(lambda: run("rendering", "background_render.py", dict(args, out_dir=plan_bad_dir, plan=True, device="NOPE")))
        plan_bad_clean = not os.path.exists(os.path.join(plan_bad_dir, "render_status.json"))
        return {"state": res["state"], "done": first["frames_done"], "total": first["frames_total"],
                "files": sorted(os.listdir(os.path.join(d, "frames"))), "ended": first["ended"], "repeat": repeat,
                "repeat_state": repeat_state, "again": again, "bad_device": bad_device, "bad_state": bad_state["state"],
                "bad_error": bad_state["error"], "kept_error": kept_error, "kept_state": kept_state, "refused_later": refused_later,
                "unreadable": unreadable, "busy": busy, "died": died, "held": held, "held_no_status": held_no_status,
                "held_over": held_over, "held_kept": held_kept, "held_reason": held_reason, "after_held": after_held,
                "plan": plan, "plan_saved": plan_saved, "plan_math": plan_math, "one": one, "plan_clean": plan_clean, "after_plan": after_plan, "plan_done": plan_done,
                "plan_bad": plan_bad, "plan_bad_clean": plan_bad_clean,
                "busy_state": busy_state, "no_backend": no_backend, "strays": strays, "movie": movie, "handlers_kept": len(bpy.app.handlers.render_post) == handlers}
    finally:
        r.image_settings.media_type, r.image_settings.file_format = saved[9], saved[10]
        r.engine, r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage, r.use_overwrite = saved[:6]
        scene.frame_start, scene.frame_end = saved[6], saved[7]
        scene.frame_set(saved[8])


def _rigid_shapes():
    """The collision shape asked for is the one Blender holds, and a bad shape changes nothing."""
    names = {"box": "SM_RB_Box", "sphere": "SM_RB_Sphere", "hull": "SM_RB_Hull", "mesh": "SM_RB_Mesh", "bad": "SM_RB_Bad"}
    for i, n in enumerate(names.values()):
        _cube(n, 0.5, loc=(40 + 2 * i, 40, 0))
    base = {"material": "wood", "frames": 3}
    out = {}
    for key, shape in (("box", "BOX"), ("sphere", "SPHERE"), ("hull", "CONVEX_HULL")):
        rep = run("physics-sim", "rigid_body_setup.py", dict(base, active=[names[key]], shape=shape))
        out[key] = (rep["active"][names[key]]["shape"], bpy.data.objects[names[key]].rigid_body.collision_shape)
    mesh = run("physics-sim", "rigid_body_setup.py", dict(base, active=[names["mesh"]], shape="MESH"))
    out["mesh_active"] = bpy.data.objects[names["mesh"]].rigid_body.collision_shape
    out["bad_error"] = _expect_error(lambda: run("physics-sim", "rigid_body_setup.py", dict(base, active=[names["bad"]], shape="TRIANGLES")))
    out["bad_untouched"] = bpy.data.objects[names["bad"]].rigid_body is None
    out["box_mass"] = bpy.data.objects[names["box"]].rigid_body.mass
    out["sphere_mass"] = bpy.data.objects[names["sphere"]].rigid_body.mass
    return out


def _manifest_evidence_binding():
    """validate and export PASS only on the right producer's fresh, passing result file."""
    import time
    d = os.path.join(OUT, "manifest_binding")
    os.makedirs(d, exist_ok=True)
    base = {"out_dir": d, "skill": "blender-mcp-workflow"}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    gates = lambda: rm()["gates"]
    summary = {"result_summary": {"fails": 0}}
    warn_ok = lambda v: {"warn": True, "reason": "crate WARN accepted"} if v == "WARN" else {}

    def forged(name, script, verdict="PASS", when=None, schema="script-evidence/1"):
        import datetime
        stamp = when or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump({"schema": schema, "script": script, "verdict": verdict, "summary": {}, "time": stamp}, fh)
        return name

    out = {}
    # 1. only a typed summary
    out["summary_only"] = _expect_error(lambda: rm(stage="validate", script="validate_asset.py", verdict="PASS", **summary))
    out["summary_only_gate"] = gates()["validate"]
    # 2. a failing file
    out["failing"] = _expect_error(lambda: rm(stage="validate", script="validate_asset.py", verdict="PASS",
                                              evidence=_failing_validate_evidence(d), **summary))
    out["failing_gate"] = gates()["validate"]
    # 3. another script's file: an export file cannot back a validate PASS, nor an unknown or malformed one
    out["export_for_validate"] = _expect_error(lambda: rm(
        stage="validate", script="export_asset.py", verdict="PASS", evidence=_export_evidence(d, "genuine_export.json"), **summary))
    out["unknown_script"] = _expect_error(lambda: rm(
        stage="validate", script="made_up.py", verdict="PASS", evidence=forged("other.json", "made_up.py"), **summary))
    out["not_evidence"] = _expect_error(lambda: rm(
        stage="validate", script="validate_asset.py", verdict="PASS", evidence=forged("schema.json", "validate_asset.py", schema="x"), **summary))
    out["outside"] = _expect_error(lambda: rm(
        stage="validate", script="validate_asset.py", verdict="PASS", evidence="../genuine_export.json", **summary))
    out["gates_after_refusals"] = (gates()["validate"], gates()["export"])
    # 4. a stale file: the model was recorded after the script wrote it
    ev, verdict = _validate_evidence(d, "stale.json")
    time.sleep(1.2)
    rm(stage="model", script="manual", verdict="PASS", **summary)
    out["stale"] = _expect_error(lambda: rm(stage="validate", script="validate_asset.py", verdict="PASS", evidence=ev,
                                            **summary, **warn_ok(verdict)))
    out["stale_gate"] = gates()["validate"]
    # 4b. the same second: evidence written, then a model event less than a second later, must also be stale
    ev, verdict = _validate_evidence(d, "stale_fast.json")
    rm(stage="model", script="manual", verdict="PASS", **summary)
    out["stale_fast"] = _expect_error(lambda: rm(stage="validate", script="validate_asset.py", verdict="PASS", evidence=ev,
                                                 **summary, **warn_ok(verdict)))
    out["event_time_fraction"] = "." in json.load(open(os.path.join(d, "run_manifest.json")))["events"][-1]["time"]
    # 5. a fresh file passes; clash_audit.py is an allowed validate producer, export_asset.py the only export producer
    ev, verdict = _validate_evidence(d, "fresh.json")
    out["fresh"] = rm(stage="validate", script="validate_asset.py", verdict="PASS", evidence=ev, **summary, **warn_ok(verdict))["gates"]["validate"]
    out["clash_allowed"] = rm(stage="validate", script="clash_audit.py", verdict="PASS",
                              evidence=forged("clash.json", "clash_audit.py"), **summary)["gates"]["validate"]
    # 6. validate is PASS now, so an export refusal below is about the evidence and nothing else
    ev, _ = _validate_evidence(d, "genuine_validate.json")
    out["validate_for_export"] = _expect_error(lambda: rm(
        stage="export", script="export_asset.py", verdict="PASS", evidence=ev, **summary))
    out["validate_for_export_script"] = _expect_error(lambda: rm(
        stage="export", script="validate_asset.py", verdict="PASS", evidence=ev, **summary))
    out["clash_for_export"] = _expect_error(lambda: rm(stage="export", script="clash_audit.py", verdict="PASS",
                                                        evidence=forged("clash2.json", "clash_audit.py"), **summary))
    out["export_gate_after_refusals"] = gates()["export"]
    out["export"] = rm(stage="export", script="export_asset.py", verdict="PASS", evidence=_export_evidence(d, "ok_export.json"),
                       **summary)["gates"]["export"]
    # 7. the stored record carries the file's hash and the producer
    with open(os.path.join(d, "run_manifest.json"), encoding="utf-8") as fh:
        events = json.load(fh)["events"]
    out["recorded"] = [(e["stage"], e["evidence"]["script"], len(e["evidence"]["sha256"])) for e in events if "evidence" in e]
    # 8. a PASS refused for its evidence must not leave an earlier PASS standing: the gate reads NOT_CHECKED again
    out["export_before_reject"] = gates()["export"]
    out["rejected_after_pass"] = _expect_error(lambda: rm(
        stage="export", script="export_asset.py", verdict="PASS", evidence=forged("late_fail.json", "export_asset.py", verdict="FAIL"), **summary))
    out["export_after_reject"] = gates()["export"]
    with open(os.path.join(d, "run_manifest.json"), encoding="utf-8") as fh:
        last = json.load(fh)["events"][-1]
    out["reject_event"] = (last["stage"], last["verdict"], last.get("rejected"), "reports FAIL" in (last.get("reason") or ""))
    return out


def _export_evidence_collision():
    """evidence_path equal to out_path is refused before anything is written."""
    d = os.path.join(OUT, "export_collision")
    os.makedirs(d, exist_ok=True)
    target = os.path.join(d, "collide.glb")
    err = {}
    for label, ev in (("same", target), ("dotdot", os.path.join(d, "sub", "..", "collide.glb"))):
        err[label] = _expect_error(lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "web", "out_path": target, "evidence_path": ev}))
    # a glTF export writes model.bin beside model.gltf: evidence named model.bin must be refused, not replace it
    side = os.path.join(d, "sidecar.gltf")
    err["sidecar"] = _expect_error(lambda: run("export-pipeline", "export_asset.py", {
        "objects": ["SM_Crate_01"], "engine": "web", "out_path": side, "evidence_path": os.path.join(d, "sidecar.bin")}))
    return {"errors": err, "written": os.path.exists(target), "side_written": os.path.exists(side)}


def _manifest_validate_gate():
    d = os.path.join(OUT, "manifest_gate")
    os.makedirs(d, exist_ok=True)
    base = {"out_dir": d, "skill": "blender-mcp-workflow", "script": "validate_asset.py"}
    rm = lambda **kw: run("blender-director", "run_manifest.py", dict(base, **kw))
    ok = {"result_summary": {"fails": 0}}
    # Valid export evidence in every call, so only the validate gate can be the reason for a refusal.
    exp = lambda: dict(ok, script="export_asset.py", evidence=_export_evidence(d))
    rm(stage="model", verdict="PASS", **ok)
    missing = _expect_error(lambda: rm(stage="export", verdict="PASS", **exp()))
    rm(stage="validate", verdict="NOT_CHECKED", reason="not run yet")
    not_checked = _expect_error(lambda: rm(stage="export", verdict="PASS", **exp()))
    verify_nc = _expect_error(lambda: rm(stage="verify", verdict="PASS"))
    rm(stage="validate", verdict="N/A", reason="no mesh output")
    ok_na = rm(stage="export", verdict="PASS", **exp())
    ev, verdict = _validate_evidence(d)
    rm(stage="validate", verdict="PASS", evidence=ev, warn=verdict == "WARN", reason="crate WARN accepted", **ok)
    ok_verify = rm(stage="verify", verdict="PASS", **ok)
    return {"missing": missing, "not_checked": not_checked, "verify_nc": verify_nc,
            "export_after_na": ok_na["gates"]["export"], "verify_after_pass": ok_verify["gates"]["verify"]}


def _convex_closed():
    """Convex proxies must be closed, and hold no faces or stray vertices from the source."""
    def hull(name, build, **extra):
        bm = bmesh.new()
        build(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, me))
        made = run("collision-proxy", "make_collision.py", dict({"objects": [name], "shape": "convex", "engine": "godot"}, **extra))
        bm = bmesh.new()
        bm.from_mesh(bpy.data.objects[made["proxies"][0]["name"]].data)
        stats = {"verts": len(bm.verts), "faces": len(bm.faces), "open": sum(not e.is_manifold for e in bm.edges)}
        bm.free()
        return stats

    def inner_point(bm):
        bmesh.ops.create_cube(bm, size=2.0)
        bm.verts.new((0.0, 0.0, 0.0))

    flat = _expect_error(lambda: hull("SM_HullFlat", lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)))
    flat_ngon = _expect_error(lambda: hull("SM_HullNgon", lambda bm: bmesh.ops.create_circle(bm, cap_ends=True, segments=14, radius=1.0)))
    return {"flat": flat, "flat_ngon": flat_ngon, "cylinder": hull("SM_HullCyl", lambda bm: bmesh.ops.create_cone(
                bm, cap_ends=True, segments=14, radius1=1.0, radius2=1.0, depth=2.0)),
            "cube": hull("SM_HullCube", lambda bm: bmesh.ops.create_cube(bm, size=2.0)),
            "inner": hull("SM_HullInner", inner_point),
            "capped": hull("SM_HullCap", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0),
                           max_hull_verts=32)}


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
        ("blender-mcp-workflow.capture_ignores_marker_cameras", lambda: _capture_ignores_marker_cameras(out_dir),
         lambda r: r["views_differ"] and r["binding_restored"]),
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
        ("collision-proxy.convex_closed", lambda: _convex_closed(),
         lambda r: "flat" in (r["flat"] or "") and "flat" in (r["flat_ngon"] or "")
         and all(c["open"] == 0 and c["faces"] == 2 * c["verts"] - 4 for k, c in r.items() if not k.startswith("flat"))
         and r["cylinder"]["verts"] == 28 and r["cube"]["verts"] == 8 and r["inner"]["verts"] == 8
         and r["capped"]["verts"] <= 32),
        ("export-pipeline.fbx", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "unreal", "out_path": os.path.join(out_dir, "SM_Crate_01.fbx")}),
         lambda r: r["exists"] and r["bytes"] > 1000),
        ("export-pipeline.glb", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "web", "out_path": os.path.join(out_dir, "SM_Crate_01.glb")}),
         lambda r: r["bytes"] > 500 and _glb_check(r, {"SM_Crate_01"}) and set(glb_nodes(r["path"])) == {"SM_Crate_01"}),
        ("core.capture_keeps_color_depth", lambda: _capture_keeps_depth(out_dir),
         lambda r: r == {"fmt": "OPEN_EXR", "depth": "32"}),
        ("export-pipeline.glb_keeps_camera_and_mode", lambda: _export_keeps_state("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "web", "out_path": os.path.join(out_dir, "state.glb")}), _kept_state),
        ("export-pipeline.fbx_keeps_camera_and_mode", lambda: _export_keeps_state("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "unity", "out_path": os.path.join(out_dir, "state.fbx")}), _kept_state),
        ("godot-export.keeps_camera_and_mode", lambda: _export_keeps_state("godot-export", "export_godot.py", {
            "objects": ["SM_Crate_01"], "out_path": os.path.join(out_dir, "state_godot.glb")}), _kept_state),
        ("unity-export.keeps_camera_and_mode", lambda: _export_keeps_state("unity-export", "export_unity.py", {
            "objects": ["SM_Crate_01"], "out_path": os.path.join(out_dir, "state_unity.fbx"), "strict": False}), _kept_state),
        ("unity-export.animated_keeps_camera_and_mode", lambda: _export_keeps_state("unity-export", "export_unity.py", {
            "objects": ["SM_Crate_01"], "out_path": os.path.join(out_dir, "state_unity_anim.fbx"), "strict": False,
            "animation": True}), _kept_state),
        ("export-pipeline.fbx_animated_keeps_camera_and_mode", lambda: _export_keeps_state("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "unity", "animation": True,
            "out_path": os.path.join(out_dir, "state_anim.fbx")}), _kept_state),
        ("export-pipeline.glb_instancer_is_ok", lambda: _export_instancer(os.path.join(out_dir, "instancer.glb")),
         lambda r: r["no_geometry"] == []),
        ("unreal-export.keeps_camera_and_mode", lambda: _export_keeps_state("unreal-export", "export_unreal.py", {
            "mesh": "SM_Crate_01", "out_dir": os.path.join(out_dir, "state_unreal"), "strict": False}), _kept_state),
        ("export-pipeline.glb_empty_mesh_not_ok", lambda: _export_empty_mesh(
            "export-pipeline", "export_asset.py", os.path.join(out_dir, "empty.glb")),
         lambda r: r["ok"] is False and r["no_geometry"] == ["SM_EmptyProbe"]),
        ("godot-export.empty_mesh_not_ok", lambda: _export_empty_mesh(
            "godot-export", "export_godot.py", os.path.join(out_dir, "empty_godot.glb")),
         lambda r: r["ok"] is False and r["no_geometry"] == ["SM_EmptyProbe"]),
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
        # The crate, not GEO_Ground, is the collider: GEO_Ground scatters COL_Rocks, so a rigid body ground makes a
        # dependency cycle that crashed Blender 5.2.3 on macOS in Instance on Points (exit 139, 2 of 3 runs).
        ("physics-sim.rigid_body_setup", lambda: run("physics-sim", "rigid_body_setup.py", {
            "active": ["SM_Rock_B"], "passive": ["SM_Crate_01"], "material": "stone", "frames": 20, "bake": True}),
         lambda r: r["active"]["SM_Rock_B"]["mass_kg"] > 0 and r.get("baked") is True),
        ("physics-sim.rigid_body_shapes_applied", lambda: _rigid_shapes(),
         lambda r: r["box"] == ("BOX", "BOX") and r["sphere"] == ("SPHERE", "SPHERE") and r["hull"] == ("CONVEX_HULL", "CONVEX_HULL")
         and r["mesh_active"] == "CONVEX_HULL" and r["bad_error"] and "shape" in r["bad_error"] and r["bad_untouched"]
         and r["box_mass"] > r["sphere_mass"] > 0),
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
        ("director.manifest_needs_evidence", lambda: _manifest_evidence(),
         lambda r: "capture" in (r["no_capture"] or "") and "not found" in (r["ghost"] or "")
         and all(e and "result_summary" in e for e in r["empties"]) and r["nc"] == "NOT_CHECKED"
         and r["good"] == "PASS" and r["hash"] == r["expect"] and r["bytes"] == 3),
        ("animation.turntable_fits_any_aspect", lambda: _turntable_tall_fits(),
         lambda r: r["y"][0] >= 0 and r["y"][1] <= 1 and r["x"][0] >= 0 and r["x"][1] <= 1),
        ("rendering.background_render", lambda: _background_render(),
         lambda r: r["state"] == "done" and r["done"] == 2 and r["total"] == 2 and len(r["files"]) == 2 and r["ended"]
         and "already exist" in (r["repeat"] or "") and r["repeat_state"] == "done" and r["again"] == "done"
         and "device" in (r["kept_error"] or "") and r["kept_state"] == "done" and r["refused_later"]
         and "cannot read" in (r["unreadable"] or "")
         and "running" in (r["busy"] or "") and r["busy_state"] == "running" and r["died"] == "done"
         and "another process" in (r["held"] or "") and r["held_no_status"] and "another process" in (r["held_over"] or "")
         and r["held_kept"] and "another process" in r["held_reason"] and r["after_held"] == "done"
         and "not available on this machine" in (r["no_backend"] or "")
         and "device" in (r["bad_device"] or "") and r["bad_state"] == "error" and "device" in (r["bad_error"] or "")
         and "outside this frame range" in (r["strays"] or "") and "image format" in (r["movie"] or "")
         and r["plan"] == r["plan_saved"] and r["plan"]["frames_total"] == 2 and r["plan"]["expected_s"] > 0
         and r["plan"]["status_path"] in r["plan"]["tell_user"] and "2 frames" in r["plan"]["tell_user"]
         and r["plan"]["measured_frames"] == 2 and r["plan"]["first_frame_s"] > 0 and r["plan_math"]
         and r["one"]["measured_frames"] == 1 and abs(r["one"]["expected_s"] - r["one"]["first_frame_s"]) <= 0.06
         and r["plan_clean"] and r["after_plan"] == "done" and "already exist" in (r["plan_done"] or "")
         and "device" in (r["plan_bad"] or "") and r["plan_bad_clean"]
         and r["handlers_kept"]),
        ("director.evidence_binds_producers", lambda: _manifest_evidence_binding(),
         lambda r: "without evidence" in (r["summary_only"] or "") and r["summary_only_gate"] == "NOT_CHECKED"
         and "reports FAIL" in (r["failing"] or "") and r["failing_gate"] == "NOT_CHECKED"
         and "must come from" in (r["validate_for_export"] or "") and "export_asset.py" in (r["validate_for_export"] or "")
         and "must come from" in (r["validate_for_export_script"] or "")
         and "must come from" in (r["export_for_validate"] or "")
         and "must come from" in (r["unknown_script"] or "") and "script-evidence/1" in (r["not_evidence"] or "")
         and "outside" in (r["outside"] or "") and list(r["gates_after_refusals"]) == ["NOT_CHECKED", "NOT_CHECKED"] and r["export_gate_after_refusals"] == "NOT_CHECKED"
         and "stale" in (r["stale"] or "") and r["stale_gate"] == "NOT_CHECKED"
         and r["fresh"] == "PASS" and r["clash_allowed"] == "PASS" and "must come from" in (r["clash_for_export"] or "")
         and r["export"] == "PASS"
         and r["recorded"] == [("validate", "validate_asset.py", 64), ("validate", "clash_audit.py", 64), ("export", "export_asset.py", 64)]
         and r["export_before_reject"] == "PASS" and "reports FAIL" in (r["rejected_after_pass"] or "")
         and r["export_after_reject"] == "NOT_CHECKED" and r["reject_event"] == ("export", "NOT_CHECKED", True, True)),
        ("export-pipeline.evidence_path_is_not_out_path", lambda: _export_evidence_collision(),
         lambda r: all(r["errors"].get(k) and "same file" in r["errors"][k] for k in ("same", "dotdot"))
         and "shares the export's name" in (r["errors"].get("sidecar") or "") and not r["written"] and not r["side_written"]),
        ("director.run_manifest", lambda: _manifest_case(),
         lambda r: r["events"] == 2 and r["r2_events"] == 2 and r["hash"] == r["expect_hash"]
         and r["ev_hash"] == r["ev_expect"] and r["ev_script"] == "export_asset.py"
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
