"""Headless Blender tests for batch C of iteration 13 (scene state): scene_snapshot.py, silhouette_score.py,
usd_roundtrip.py, clash_audit.py and ingest_asset.py. Each check builds a small scene, runs the script and asserts on
what it did to the scene. Writes <out_dir>/iter13_scene_report.json (passed / total / failed) and exits non-zero on a
failure. A crash inside one test is recorded as a failed check, so the report always exists.

    blender -b --factory-startup --python tests/blender/test_iter13_scene.py -- '{"out_dir": "/tmp/iter13_scene"}'
"""
import json
import os
import runpy
import sys
import time
import traceback

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def snap(**kw):
    return run("blender-mcp-workflow", "scene_snapshot.py", kw)


def raises(fn, kinds=(ValueError, RuntimeError)):
    try:
        fn()
    except kinds as exc:
        return str(exc) or type(exc).__name__
    return None


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube(name, size=1.0, loc=(0, 0, 0), coll=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(o)
    o.location = loc
    return o


def quad(name, x0, x1, y0, y1, z):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def set_active(o):
    bpy.context.view_layer.update()
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def run_all(out_dir):
    results = []

    def check(name, ok, detail=None):
        results.append({"name": name, "ok": bool(ok), **({"detail": detail} if (detail is not None and not ok) else {})})

    def case(fn):
        def wrapped():
            try:
                fn()
            except Exception:
                results.append({"name": fn.__name__ + " (crashed)", "ok": False, "detail": traceback.format_exc()[-700:]})
        wrapped.__name__ = fn.__name__
        return wrapped

    # ------------------------------------------------------------------ C1 scene_snapshot
    @case
    def c1_depsgraph():
        reset()
        o = cube("Box")
        bpy.context.view_layer.update()
        d = os.path.join(out_dir, "c1a")
        snap(action="save", dir=d, name="A")
        o.location = (5, 0, 0)  # no update: matrix_world is stale until the depsgraph runs
        r = snap(action="diff", dir=d, a="A", b="current")
        ch = {c["name"]: c for c in r["changed"]}
        check("C1 diff against the live scene sees a move made without a prior depsgraph update",
              "Box" in ch and abs(ch["Box"].get("transform_delta", 0) - 5) < 1e-4, r)
        o.location = (0, 0, 0)
        bpy.context.view_layer.update()
        o.location = (7, 0, 0)  # stale at save time too
        snap(action="save", dir=d, name="B")
        with open(os.path.join(d, "B.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        check("C1 save records the new location, not the stale matrix", abs(m["objects"]["Box"]["matrix_world"][3] - 7) < 1e-4,
              m["objects"]["Box"]["matrix_world"][:4])

    @case
    def c1_armature_edit():
        reset()
        cube("Box")
        arm_data = bpy.data.armatures.new("Rig")
        arm = bpy.data.objects.new("Rig", arm_data)
        bpy.context.scene.collection.objects.link(arm)
        set_active(arm)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm_data.edit_bones.new("Bone")
        eb.head, eb.tail = (0, 0, 0), (0, 0, 1)
        d = os.path.join(out_dir, "c1b")
        msg = raises(lambda: snap(action="save", dir=d, name="E"))
        check("C1 save refuses while an armature is in Edit Mode (its bones are not in the saved file)",
              msg is not None and "Rig" in msg and "Edit Mode" in msg, msg)
        check("C1 the refused save leaves the armature in Edit Mode with its edit bone",
              arm.mode == "EDIT" and "Bone" in arm_data.edit_bones, arm.mode)
        bpy.ops.object.mode_set(mode="OBJECT")
        r = snap(action="save", dir=d, name="E2")
        check("C1 the same save works once Edit Mode is left", r["objects"] == 2, r)

    @case
    def c1_latest_unique():
        reset()
        cube("Box")
        d = os.path.join(out_dir, "c1c")
        real = time.strftime
        time.strftime = lambda fmt, *a: "2030-01-01T00:00:00" if "T" in fmt else "20300101_000000"
        try:
            a = snap(action="save", dir=d)
            b = snap(action="save", dir=d)
            check("C1 two default-named saves in the same second get different names", a["name"] != b["name"], [a["name"], b["name"]])
            snap(action="save", dir=d, name="zz_first")
            snap(action="save", dir=d, name="aa_second")
            rows = snap(action="list", dir=d)["snapshots"]
            check("C1 'latest' is the last save even when names and timestamps tie", rows[-1]["name"] == "aa_second",
                  [r["name"] for r in rows])
            r = snap(action="diff", dir=d)
            check("C1 diff default 'a' is the most recent save", r["a"] == "aa_second", r["a"])
        finally:
            time.strftime = real

    @case
    def c1_user_collection():
        reset()
        parent = cube("Parent")
        child = cube("Child", size=0.5)
        child.parent = parent
        bpy.context.view_layer.update()
        d = os.path.join(out_dir, "c1d")
        snap(action="save", dir=d, name="S")
        mine = bpy.data.collections.new("_Restored_dependencies")
        bpy.context.scene.collection.children.link(mine)
        keep = cube("Mine", coll=mine)
        r = snap(action="restore", dir=d, name="S", objects=["Child"])
        lc = bpy.context.view_layer.layer_collection.children.get("_Restored_dependencies")
        check("C1 restore reports the parent as a dependency", r["dependencies"], r)
        check("C1 a user collection named _Restored_dependencies stays visible",
              lc is not None and not lc.exclude and keep.name in bpy.context.view_layer.objects, lc.exclude if lc else "gone")
        check("C1 the user's collection gets no restored objects", [o.name for o in mine.objects] == ["Mine"],
              [o.name for o in mine.objects])

    # ------------------------------------------------------------------ C2 silhouette_score
    @case
    def c2_excluded():
        reset()
        hidden = bpy.data.collections.new("Hidden")
        bpy.context.scene.collection.children.link(hidden)
        o = cube("Hid", size=1.0, loc=(0, 0, 0), coll=hidden)
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        bpy.context.scene.collection.objects.link(cam)
        cam.location = (0, -6, 0)
        cam.rotation_euler = (1.5707963, 0, 0)
        bpy.context.view_layer.update()
        ref = os.path.join(out_dir, "ref.png")
        os.makedirs(out_dir, exist_ok=True)
        img = bpy.data.images.new("ref", 64, 64, alpha=True)
        px = [0.0, 0.0, 0.0, 0.0] * (64 * 64)
        for y in range(20, 44):
            for x in range(20, 44):
                i = (y * 64 + x) * 4
                px[i:i + 4] = [1, 1, 1, 1]
        img.pixels.foreach_set(px)
        img.filepath_raw = ref
        img.file_format = "PNG"
        img.save()
        bpy.data.images.remove(img)
        # exclude the collection, then move the object while it is excluded: its matrix_world is not recomputed
        bpy.context.view_layer.layer_collection.children["Hidden"].exclude = True
        o.location = (50.0, 0, 0)
        views = [{"camera": "Cam", "reference": ref}]
        res = []
        msg = raises(lambda: res.append(run("blender-mcp-workflow", "silhouette_score.py", {"objects": ["Hid"], "views": views})))
        if msg is not None:
            check("C2 an object in an excluded collection is refused, naming the reason",
                  "exclude" in msg.lower() or "view layer" in msg.lower(), msg)
        else:
            check("C2 an excluded object is scored with its real transform (x=50: out of view)",
                  res[0]["views"][0]["pixels_scored"] == 0, res[0]["views"][0])

    # ------------------------------------------------------------------ C3 usd_roundtrip
    def usd(args):
        return run("usd-pipeline", "usd_roundtrip.py", args)

    @case
    def c3_armature_orphans():
        reset()
        body = cube("Body")
        vg = body.vertex_groups.new(name="Bone")
        vg.add(list(range(len(body.data.vertices))), 1.0, "REPLACE")
        arm_data = bpy.data.armatures.new("Rig")
        arm = bpy.data.objects.new("Rig", arm_data)
        bpy.context.scene.collection.objects.link(arm)
        set_active(arm)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm_data.edit_bones.new("Bone")
        eb.head, eb.tail = (0, 0, -1), (0, 0, 1)
        bpy.ops.object.mode_set(mode="OBJECT")
        body.parent = arm
        mod = body.modifiers.new("Arm", "ARMATURE")
        mod.object = arm
        bpy.context.view_layer.update()
        before = {c: sorted(i.name for i in getattr(bpy.data, c)) for c in ("armatures", "actions", "meshes", "objects")}
        r = usd({"out_path": os.path.join(out_dir, "c3a", "rig.usdc"), "objects": ["Body", "Rig"]})
        after = {c: sorted(i.name for i in getattr(bpy.data, c)) for c in before}
        check("C3 no armature datablock is left behind by a run", after["armatures"] == before["armatures"],
              [after["armatures"], r["imported"]])
        check("C3 no new action/mesh/object is left behind either",
              all(after[c] == before[c] for c in ("actions", "meshes", "objects")), {c: [after[c], before[c]] for c in before})

    @case
    def c3_selection_refused():
        reset()
        a = cube("A", loc=(0, 0, 0))
        hidden = bpy.data.collections.new("Hidden")
        bpy.context.scene.collection.children.link(hidden)
        cube("H", loc=(3, 0, 0), coll=hidden)
        bpy.context.view_layer.layer_collection.children["Hidden"].exclude = True
        keep = cube("Keep", loc=(0, 3, 0))
        set_active(a)
        keep.select_set(True)
        sel_before = sorted(o.name for o in bpy.context.view_layer.objects if o.select_get())
        msg = raises(lambda: usd({"out_path": os.path.join(out_dir, "c3b", "x.usdc"), "objects": ["A", "H"]}))
        sel_after = sorted(o.name for o in bpy.context.view_layer.objects if o.select_get())
        check("C3 a run that cannot select its targets is refused", msg is not None, msg)
        check("C3 the refused run leaves selection as it was", sel_after == sel_before, [sel_before, sel_after])
        check("C3 the refused run leaves the active object as it was", bpy.context.view_layer.objects.active is a,
              str(bpy.context.view_layer.objects.active))

    def set_material_crate(same):
        """A crate whose slot 0 holds SlotMat and slot 1 NodeMat; a Set Material node puts SlotMat (same) or the
        distinct NodeMat on every face."""
        reset()
        o = cube("Crate")
        a = bpy.data.materials.new("SlotMat")
        b = bpy.data.materials.new("NodeMat")
        o.data.materials.append(a)
        o.data.materials.append(b)
        if same:
            b = a
        tree = bpy.data.node_groups.new("SetMat", "GeometryNodeTree")
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        gi, go = tree.nodes.new("NodeGroupInput"), tree.nodes.new("NodeGroupOutput")
        sm = tree.nodes.new("GeometryNodeSetMaterial")
        sm.inputs["Material"].default_value = b
        tree.links.new(gi.outputs[0], sm.inputs["Geometry"])
        tree.links.new(sm.outputs[0], go.inputs[0])
        mod = o.modifiers.new("GN", "NODES")
        mod.node_group = tree
        bpy.context.view_layer.update()
        return usd({"out_path": os.path.join(out_dir, "c3c" if same else "c3d", "crate.usdc"), "objects": ["Crate"]})

    @case
    def c3_set_material():
        r = set_material_crate(same=True)
        check("C3 a Set Material node that puts the slot's own material on the faces is ok:true", r["ok"],
              [r["problems"], r["per_object"]])

    @case
    def c3_set_material_distinct():
        r = set_material_crate(same=False)
        # Blender's USD exporter writes only the slot material, so the node's replacement is lost: a real loss
        check("C3 a Set Material node with a distinct replacement is reported ok:false",
              (not r["ok"]) and any("NodeMat" in p and "SlotMat" in p for p in r["problems"]),
              [r["ok"], r["problems"]])

    @case
    def c3_object_link_override():
        reset()
        o = cube("Ov")
        a = bpy.data.materials.new("MatA")
        b = bpy.data.materials.new("MatB")
        o.data.materials.append(a)
        o.material_slots[0].link = "OBJECT"
        o.material_slots[0].material = b  # USD receives MatB, not the mesh's MatA
        bpy.context.view_layer.update()
        r = usd({"out_path": os.path.join(out_dir, "c3e", "ov.usdc"), "objects": ["Ov"]})
        check("C3 an OBJECT-linked slot override is not a false ok:false", r["ok"], [r["problems"], r["per_object"]])
        check("C3 the override material is the one compared", r["per_object"]["Ov"]["materials"] == [["MatB"], ["MatB"]],
              r["per_object"])

    @case
    def c3_renamed_object_and_mesh():
        reset()
        crate = cube("Crate")
        crate.data.name = "Cube"  # a renamed primitive: object "Crate", mesh data "Cube"
        other = cube("Plain", loc=(3, 0, 0))
        other.data.name = "Shared_Shape"
        r = usd({"out_path": os.path.join(out_dir, "c3f", "r.usdc"), "objects": ["Crate", "Plain"]})
        check("C3 objects whose mesh data is named differently round-trip as ok:true", r["ok"],
              [r["problems"], r["imported"]])
        check("C3 both are found under the original object names",
              all(r["per_object"].get(n, {}).get("found") for n in ("Crate", "Plain")), r["per_object"])
        r = usd({"out_path": os.path.join(out_dir, "c3g", "r.usdc"), "objects": ["Crate"], "subdivision": "TESSELLATE"})
        sub = crate.modifiers.new("Sub", "SUBSURF")
        sub.levels = sub.render_levels = 1
        bpy.context.view_layer.update()
        r = usd({"out_path": os.path.join(out_dir, "c3h", "r.usdc"), "objects": ["Crate"], "subdivision": "BEST_MATCH"})
        check("C3 a real loss on a renamed object is still ok:false (BEST_MATCH drops the subdivision)",
              (not r["ok"]) and r["per_object"]["Crate"]["found"], [r["ok"], r["problems"]])

    @case
    def c1_excluded_moved():
        reset()
        coll = bpy.data.collections.new("Out")
        bpy.context.scene.collection.children.link(coll)
        o = cube("Mv", coll=coll)
        child = cube("Kid", loc=(0, 1, 0), coll=coll)
        child.parent = o
        bpy.context.view_layer.update()
        bpy.context.view_layer.layer_collection.children["Out"].exclude = True
        d = os.path.join(out_dir, "c1f")
        snap(action="save", dir=d, name="A")
        o.location = (5, 0, 0)  # excluded from every view layer: the depsgraph never evaluates it
        r = snap(action="diff", dir=d, a="A", b="current")
        ch = {c["name"]: c for c in r["changed"]}
        check("C1 an object excluded from every view layer and then moved is seen as moved",
              "Mv" in ch and abs(ch["Mv"].get("transform_delta", 0) - 5) < 1e-4, r)
        check("C1 its child moves with it", "Kid" in ch and abs(ch["Kid"].get("transform_delta", 0) - 5) < 1e-4, r)
        con = o.constraints.new("COPY_LOCATION")
        con.target = bpy.data.objects["Kid"]
        msg = raises(lambda: snap(action="diff", dir=d, a="A", b="current"))
        check("C1 an unevaluated object with a constraint is refused, naming it", msg is not None and "Mv" in msg, msg)

    # ------------------------------------------------------------------ C4 clash_audit
    def audit(**kw):
        return run("blender-mcp-workflow", "clash_audit.py", {"objects": None, **kw})

    @case
    def c4_open_mesh():
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))  # base on z=0, x/y -0.5..0.5
        quad("Sheet", 0.0, 2.0, -2.0, 2.0, 0.0)  # open mesh that covers only half of the base
        r = audit(objects=["Box", "Sheet"])
        check("C4 a box resting on part of an open sheet is not a clash", not r["clashes"], r["clashes"])
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))
        quad("Sheet", 0.0, 2.0, -2.0, 2.0, 0.5)  # slices through the box
        r = audit(objects=["Box", "Sheet"])
        check("C4 an open sheet slicing through a box is still a clash", len(r["clashes"]) == 1 and r["verdict"] == "FAIL",
              [r["clashes"], r["verdict"]])
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))
        quad("Sheet", -2.0, 2.0, -2.0, 2.0, 0.0)  # full contact under the base
        r = audit(objects=["Box", "Sheet"])
        check("C4 a box resting wholly on an open sheet is not a clash", not r["clashes"], r["clashes"])
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))
        quad("Sheet", 0.2, 2.0, -2.0, 2.0, 0.0)  # sheet edge cuts across the base, nothing penetrates
        r = audit(objects=["Box", "Sheet"])
        check("C4 a sheet edge ending under the base is not a clash", not r["clashes"], r["clashes"])
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))
        quad("Shelf", 0.5, 2.0, -2.0, 2.0, 0.75)  # open shelf whose border lies on the box side: the box edges meet it
        r = audit(objects=["Box", "Shelf"])
        check("C4 an open shelf attached to a box side (border on the face) is not a clash", not r["clashes"], r["clashes"])
        reset()
        cube("Box", size=1.0, loc=(0, 0, 0.5))
        quad("Shelf", 0.3, 2.0, -2.0, 2.0, 0.75)  # same shelf pushed 0.2 into the box
        r = audit(objects=["Box", "Shelf"])
        check("C4 the same shelf pushed into the box is a clash", len(r["clashes"]) == 1 and r["verdict"] == "FAIL",
              [r["clashes"], r["verdict"]])
        reset()
        quad("Floor", -1.0, 1.0, -1.0, 1.0, 0.0)  # two equal open sheets crossing in an exact X: every crossing
        wall = bpy.data.meshes.new("Wall")      # lies on a border, yet the sheets share a segment
        wall.from_pydata([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [], [(0, 1, 2, 3)])
        wall.update()
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("Wall", wall))
        r = audit(objects=["Floor", "Wall"])
        check("C4 two equal open sheets crossing in an exact X are a clash", len(r["clashes"]) == 1 and r["verdict"] == "FAIL",
              [r["clashes"], r["verdict"]])
        reset()
        quad("Floor", -1.0, 1.0, -1.0, 1.0, 0.0)  # T: the wall stands on the floor, its bottom edge on the floor
        wall = bpy.data.meshes.new("Wall")
        wall.from_pydata([(-1, 0, 0), (1, 0, 0), (1, 0, 1), (-1, 0, 1)], [], [(0, 1, 2, 3)])
        wall.update()
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("Wall", wall))
        r = audit(objects=["Floor", "Wall"], require_connected=False)
        check("C4 a sheet standing on another (T) is not a clash", not r["clashes"], r["clashes"])

    # ------------------------------------------------------------------ C5 ingest_asset
    @case
    def c5_edit_mode():
        reset()
        src = cube("Src", size=2.0)
        os.makedirs(os.path.join(out_dir, "c5"), exist_ok=True)
        path = os.path.join(out_dir, "c5", "thing.obj")
        set_active(src)
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
        bpy.data.objects.remove(src)
        ed = cube("Editing", loc=(10, 0, 0))
        set_active(ed)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(ed.data)
        bm.verts.new((9, 9, 9))
        bmesh.update_edit_mesh(ed.data)
        nverts = len(bmesh.from_edit_mesh(ed.data).verts)
        res = []
        msg = raises(lambda: res.append(run("blender-mcp-workflow", "ingest_asset.py", {"path": path})))
        kept = ed.mode == "EDIT" and len(bmesh.from_edit_mesh(ed.data).verts) == nverts
        if msg is not None:
            check("C5 a scene object in Edit Mode makes the run refuse, naming it", "Editing" in msg and "Edit Mode" in msg, msg)
            check("C5 the refused run leaves the object in Edit Mode with its uncommitted vertex", kept, [ed.mode, nverts])
            check("C5 the refused run imported nothing", len(bpy.data.objects) == 1, [o.name for o in bpy.data.objects])
        else:
            notes = json.dumps(res[0]["notes"])
            check("C5 the run reports the Edit Mode object and keeps its edit", "Editing" in notes and kept, [notes, ed.mode])

    for fn in (c1_depsgraph, c1_armature_edit, c1_latest_unique, c1_user_collection, c2_excluded, c3_armature_orphans,
               c3_selection_refused, c3_set_material, c3_set_material_distinct, c3_object_link_override, c3_renamed_object_and_mesh,
               c1_excluded_moved, c4_open_mesh, c5_edit_mode):
        fn()
    return results


def main(out_dir="/tmp/iter13_scene"):
    os.makedirs(out_dir, exist_ok=True)
    try:
        results = run_all(out_dir)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": traceback.format_exc()[-800:]}]
    failures = [r for r in results if not r["ok"]]
    report = {"passed": len(results) - len(failures), "total": len(results), "failed": len(failures),
              "failures": failures, "results": results}
    with open(os.path.join(out_dir, "iter13_scene_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("passed", "total", "failed", "failures")}, indent=2))
    sys.exit(0 if not result["failures"] else 1)
