"""Headless Blender tests for clash_audit.py, silhouette_score.py, fit_search.py and ingest_asset.py
(blender-mcp-workflow, iteration 12 batch H).

Every section builds its own tiny scene, runs the real script, and asserts on the result; each also has a case that
must FAIL when the script is wrong. The silhouette masks are NOT made by the scorer: they come from real Workbench
renders of the same camera, plus masks computed by hand from the pinhole equations and written with a pure-Python
PNG writer. Writes <out_dir>/parity_tests_report.json (passed / total / failures / results / measured).

    blender -b --factory-startup --python tests/blender/test_parity.py -- '{"out_dir": "<a NEW folder>"}'

Use a new out_dir each run. The launcher on Windows Store installs drops console output: read the report file.
"""
import json
import math
import os
import runpy
import struct
import sys
import traceback
import zlib

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "skills", "blender-mcp-workflow", "scripts"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw and raw[0] == "--args-file":
            with open(raw[1], encoding="utf-8") as fh:
                return json.load(fh)
        if raw:
            return json.loads(raw[0])
    return {}


def run(script, args):
    res = runpy.run_path(os.path.join(SCRIPTS, script), init_globals={"ARGS": args}, run_name="__skill_test__")["result"]
    json.dumps(res)  # the script contract: a JSON-safe result
    return res


def tb():
    """The last lines of the current traceback: where it ended, not where it began."""
    return " | ".join(traceback.format_exc().strip().splitlines()[-3:])[-380:]


def near(seq, value, tol=1e-5):
    return all(abs(a - b) <= tol for a, b in zip(seq, value))


def leaked_images():
    return [i.name for i in bpy.data.images if i.name not in ("Render Result", "Viewer Node")]


def raises(fn, kinds=(ValueError,)):
    try:
        fn()
    except kinds as exc:
        return str(exc) or type(exc).__name__
    return None


# ---------------------------------------------------------------- scene helpers
def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.cameras, bpy.data.materials, bpy.data.images, bpy.data.worlds,
                 bpy.data.lights):
        for d in list(coll):
            coll.remove(d)
    sc = bpy.context.scene
    for c in list(sc.collection.children):
        sc.collection.children.unlink(c)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    sc.camera = None
    sc.world = None
    bpy.context.view_layer.update()


def mesh_obj(name, build, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    bm = bmesh.new()
    build(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    if parent:
        o.parent = parent
    return o


def boxes(*specs):
    """bmesh builder: union of axis-aligned boxes, each (dims, centre)."""
    def build(bm):
        for dims, centre in specs:
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(centre) @ Matrix.Diagonal((*dims, 1.0)))
    return build


def box(name, dims, loc=(0, 0, 0), **kw):
    return mesh_obj(name, boxes((dims, (0, 0, 0))), loc=loc, **kw)


def open_box(name, dims, loc):
    """Five faces: a box without its top."""
    def build(bm):
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((*dims, 1.0)))
        top = max(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.delete(bm, geom=[top], context="FACES_ONLY")
    return mesh_obj(name, build, loc=loc)


def ico(name, dims, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    def build(bm):
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5, matrix=Matrix.Diagonal((*dims, 1.0)))
        for f in bm.faces:
            f.smooth = True
    return mesh_obj(name, build, loc=loc, parent=parent, rot=rot)


def uvsphere(name, radius, loc=(0, 0, 0)):
    def build(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    return mesh_obj(name, build, loc=loc)


def camera(name, loc, look_at=None, rot_deg=None, lens=50.0, ortho=None, clip=(0.1, 100.0)):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start, cd.clip_end = clip
    if ortho:
        cd.type, cd.ortho_scale = "ORTHO", ortho
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    if look_at is not None:
        o.rotation_euler = (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        o.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    return o


def world_verts(obj):
    me = obj.data
    return np.array([tuple(obj.matrix_world @ v.co) for v in me.vertices])


def snapshot():
    """Everything a read-only script must leave alone."""
    bpy.context.view_layer.update()  # matrices are lazy: settle them so a script's own evaluation cannot look like a change
    sc = bpy.context.scene
    return {"objects": {o.name: (tuple(round(x, 6) for x in sum((list(r) for r in o.matrix_world), [])),
                                 len(o.data.vertices) if o.type == "MESH" else 0, len(o.modifiers),
                                 o.select_get(), o.hide_viewport, tuple(c.name for c in o.users_collection))
                        for o in bpy.data.objects},
            "datablocks": {**{k: len(getattr(bpy.data, k)) for k in ("meshes", "cameras", "materials", "collections", "objects")},
                           "images": len(leaked_images())},
            "camera": sc.camera.name if sc.camera else None, "engine": sc.render.engine,
            "res": (sc.render.resolution_x, sc.render.resolution_y), "frame": sc.frame_current}


def snap_diff(a, b):
    out = {}
    for k in a:
        if a[k] != b[k]:
            if isinstance(a[k], dict):
                out[k] = {kk: (a[k].get(kk), b[k].get(kk)) for kk in set(a[k]) | set(b[k]) if a[k].get(kk) != b[k].get(kk)}
            else:
                out[k] = (a[k], b[k])
    return out


# ---------------------------------------------------------------- png helpers (independent of the scorer)
def write_png_rgba(path, rows):
    """rows: list of rows (top first) of lists of (r, g, b, a) bytes. Standard PNG: no Blender involved."""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write_mask_png(path, mask_rows):
    on, off = (255, 255, 255, 255), (0, 0, 0, 0)
    write_png_rgba(path, [[on if v else off for v in row] for row in mask_rows])


def hand_mask(w, h, f_px, inside):
    """Mask computed by hand from the pinhole equations: inside(u, v) takes image-plane coordinates (x/depth, z/depth)."""
    return [[inside((c + 0.5 - w / 2) / f_px, (h / 2 - (r + 0.5)) / f_px) for c in range(w)] for r in range(h)]


def read_alpha(path):
    """Alpha >= 0.5 of a PNG, top row first, read here (not by the scorer)."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
    finally:
        bpy.data.images.remove(img)
    return np.flipud(buf.reshape(h, w, 4))[..., 3] >= 0.5


def save_array_png(path, arr_top_down_bool):
    h, w = arr_top_down_bool.shape
    write_mask_png(path, arr_top_down_bool.tolist())


def render(path, cam, w=160, h=120, transparent=True, aa="FXAA"):
    """A real Workbench render of the current scene through `cam`."""
    sc = bpy.context.scene
    sc.camera = cam
    r = sc.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
    r.film_transparent = transparent
    r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
    sc.display.shading.light, sc.display.shading.color_type = "FLAT", "SINGLE"
    sc.display.shading.single_color = (1.0, 1.0, 1.0)
    sc.display.render_aa = aa
    sc.view_settings.view_transform = "Standard"
    r.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


# ---------------------------------------------------------------- H1 clash_audit
def test_clash(check, out_dir):
    reset_scene()
    audit = lambda **kw: run("clash_audit.py", {"objects": None, **kw})  # a non-empty ARGS: {} would fall back to the CLI

    # touching cubes pass (face contact), a clearly separate pair is not a clash either
    box("A", (1, 1, 1), (0, 0, 0))
    box("B", (1, 1, 1), (1, 0, 0))
    r = audit(objects=["A", "B"])
    check("H1 touching cubes pass", r["verdict"] == "PASS" and not r["clashes"] and not r["contained"], r)
    check("H1 touching cubes form one group", len(r["groups"]) == 1, r["groups"])

    # interpenetrating equal cubes (no vertex strictly inside: needs the finer sampling), known 0.25 m overlap
    bpy.data.objects["B"].location.x = 0.75
    r = audit(objects=["A", "B"])
    d = r["clashes"][0]["depth_m"] if r["clashes"] else None
    check("H1 interpenetrating cubes fail", r["verdict"] == "FAIL" and len(r["clashes"]) == 1, r["verdict"])
    check("H1 equal-cube depth 0.25 within 10%", d is not None and abs(d - 0.25) <= 0.025, d)

    # small cube poking 0.25 m through the face of a big one: deepest vertex gives the depth
    reset_scene()
    box("Big", (2, 2, 2))
    box("Small", (0.5, 0.5, 0.5), (1.0, 0, 0))
    r = audit(objects=["Big", "Small"])
    d = r["clashes"][0]["depth_m"] if r["clashes"] else None
    check("H1 vertex depth 0.25 within 10%", d is not None and abs(d - 0.25) <= 0.025, d)

    # review H-1: the depth is the penetration along the overlap axis, not the distance to the nearest surface.
    # The box pokes 0.25 m into the cube along X but sits only 0.01 m from the cube's Y and Z faces.
    reset_scene()
    box("Cube", (2, 2, 2))
    box("Slab", (0.5, 1.98, 1.98), (1.0, 0, 0))
    for order in (["Cube", "Slab"], ["Slab", "Cube"]):
        r = audit(objects=order)
        d = r["clashes"][0]["depth_m"] if r["clashes"] else None
        check(f"H1 depth is along the overlap axis (0.25, not the 0.01 to the nearest face), order {order[0]} first",
              r["verdict"] == "FAIL" and d is not None and abs(d - 0.25) <= 0.025, r["clashes"])

    # review H-2: two coincident solids are the worst overlap there is; they must not pass
    reset_scene()
    box("Twin1", (1, 1, 1))
    box("Twin2", (1, 1, 1))
    r = audit(objects=["Twin1", "Twin2"])
    check("H1 coincident cubes fail as a clash", r["verdict"] == "FAIL" and len(r["clashes"]) == 1
          and r["clashes"][0].get("depth") == "coincident", r)
    box("Twin3", (1, 1, 1), (1, 0, 0))  # a neighbour that only touches Twin1 stays a pass
    r = audit(objects=["Twin1", "Twin3"])
    check("H1 face-touching neighbour of a coincident pair still passes", r["verdict"] == "PASS", r)
    r = audit(objects=["Twin1", "Twin2"], ignore_pairs=[["Twin1", "Twin2"]])
    check("H1 coincident pair can be allowed with ignore_pairs", r["verdict"] == "PASS", r)
    reset_scene()
    for n in ("Sheet1", "Sheet2"):
        mesh_obj(n, lambda bm: bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0))
    r = audit(objects=["Sheet1", "Sheet2"])
    check("H1 coincident open sheets fail too", r["verdict"] == "FAIL", r)

    # a cube inside a cube: no surfaces cross, still a fail
    reset_scene()
    box("Outer", (2, 2, 2))
    box("Inner", (0.5, 0.5, 0.5))
    r = audit(objects=["Outer", "Inner"])
    check("H1 cube inside cube fails as contained",
          r["verdict"] == "FAIL" and not r["clashes"] and len(r["contained"]) == 1
          and r["contained"][0]["inner"] == "Inner" and r["contained"][0]["outer"] == "Outer", r)
    check("H1 containment depth ~0.75", abs(r["contained"][0]["depth_m"] - 0.75) < 0.02, r["contained"])

    # two bars crossing so that no vertex of either is inside the other
    reset_scene()
    box("BarX", (4, 0.2, 0.2))
    box("BarY", (0.3, 4, 0.3))
    r = audit(objects=["BarX", "BarY"])
    d = r["clashes"][0]["depth_m"] if r["clashes"] else None
    check("H1 crossing bars fail with a measured lower-bound depth", r["verdict"] == "FAIL" and d is not None and 0.04 <= d <= 0.16, r)

    # floating part is named; gap_max_m decides the grouping (known 0.03 m gap)
    reset_scene()
    box("Top", (2, 1, 0.1), (0, 0, 0.75))
    for i, (x, y) in enumerate([(-0.9, -0.4), (0.9, -0.4), (-0.9, 0.4), (0.9, 0.4)]):
        box(f"Leg{i}", (0.1, 0.1, 0.7), (x, y, 0.35))
    box("Cup", (0.2, 0.2, 0.2), (0, 0, 0.8 + 0.03 + 0.1))  # 0.03 m above the top (top surface z = 0.8)
    r = audit(gap_max_m=0.01)
    check("H1 floating cup is named", r["verdict"] == "FAIL" and len(r["floating"]) == 1 and r["floating"][0]["objects"] == ["Cup"], r["floating"])
    check("H1 floating gap measured ~0.03", r["floating"] and abs(r["floating"][0]["nearest_gap_m"] - 0.03) < 0.002, r["floating"])
    r2 = audit(gap_max_m=0.05)
    check("H1 same scene groups at gap_max_m 0.05", r2["verdict"] == "PASS" and len(r2["groups"]) == 1, r2["groups"])
    r3 = audit(gap_max_m=0.01, require_connected=False)
    check("H1 require_connected false lets floating pass", r3["verdict"] == "PASS" and r3["floating"], r3["verdict"])
    r4 = audit(gap_max_m=0.01, anchor="Cup")
    check("H1 anchor picks the main group", r4["main_group"] == ["Cup"], r4["main_group"])

    # bounding boxes overlap but the surfaces are 0.2 m apart (a cube in the crook of an L-shaped bracket)
    reset_scene()
    mesh_obj("Bracket", boxes(((3.0, 1.0, 0.2), (0, 0, 0.1)), ((0.2, 1.0, 2.0), (-1.4, 0, 1.1))))
    box("Block", (0.4, 0.4, 0.4), (0.3, 0, 0.2 + 0.2 + 0.2))
    r = audit(gap_max_m=0.01)
    check("H1 overlapping bounding boxes without contact are floating, not contained or clashing",
          r["verdict"] == "FAIL" and not r["clashes"] and not r["contained"] and len(r["floating"]) == 1
          and abs(r["floating"][0]["nearest_gap_m"] - 0.2) < 0.01, r)
    check("H1 the same scene groups once gap_max_m reaches the gap", audit(gap_max_m=0.25)["verdict"] == "PASS")

    # modifiers count: the array copy hits B, the base mesh does not
    reset_scene()
    a = box("ArrA", (1, 1, 1))
    box("ArrB", (1, 1, 1), (3.75, 0, 0))
    mod = a.modifiers.new("Arr", "ARRAY")
    mod.count, mod.use_relative_offset, mod.use_constant_offset = 2, False, True
    mod.constant_offset_displace = (3.0, 0, 0)
    r_on = audit(objects=["ArrA", "ArrB"], require_connected=False)
    mod.show_viewport = False
    bpy.context.view_layer.update()
    r_off = audit(objects=["ArrA", "ArrB"], require_connected=False)
    check("H1 modifier result clashes", len(r_on["clashes"]) == 1, r_on["clashes"])
    check("H1 same pair without the modifier is clean", not r_off["clashes"], r_off["clashes"])

    # open meshes: no inside, so containment is not_measured and never a pass
    reset_scene()
    open_box("Bowl", (2, 2, 1), (0, 0, 0))
    box("Ball", (0.3, 0.3, 0.3), (0, 0, -0.35))  # resting on the bowl floor, inside its walls
    r = audit()
    check("H1 containment in an open mesh is not_measured", len(r["not_measured"]) == 1 and r["verdict"] == "WARN"
          and "Bowl" in r["open_meshes"], r)
    # an open plane through a closed cube still measures depth into the cube
    reset_scene()
    box("Cube", (1, 1, 1))
    mesh_obj("Sheet", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0,
                                                       matrix=Matrix.Rotation(math.radians(90), 4, "X")),
             loc=(0, 0, 0))
    r = audit(objects=["Cube", "Sheet"], require_connected=False)
    check("H1 open sheet through a cube is a clash with depth", r["verdict"] == "FAIL" and r["clashes"]
          and r["clashes"][0]["depth_m"] is not None, r["clashes"])

    # ignore_pairs and hidden objects
    reset_scene()
    box("P", (1, 1, 1))
    box("Q", (1, 1, 1), (0.5, 0, 0))
    r = audit(objects=["P", "Q"], ignore_pairs=[["P", "Q"]])
    check("H1 ignore_pairs allows a known overlap", r["verdict"] == "PASS", r["verdict"])
    h = box("Hidden", (1, 1, 1), (0.25, 0, 0))
    h.hide_viewport = True
    r = audit(objects=None, ignore_pairs=[["P", "Q"]])
    check("H1 default scope skips hidden objects", "Hidden" not in r["main_group"] and r["objects_checked"] == 2, r["main_group"])

    # read-only: nothing in the scene changes, no leaked meshes
    reset_scene()
    box("A", (1, 1, 1))
    b = box("B", (1, 1, 1), (0.75, 0, 0))
    b.select_set(True)
    before = snapshot()
    audit(objects=["A", "B"])
    check("H1 scene unchanged", snapshot() == before, snap_diff(before, snapshot()))

    # argument errors
    check("H1 unknown object -> ValueError", raises(lambda: audit(objects=["Nope"])))
    check("H1 bad max_samples -> ValueError", raises(lambda: audit(objects=["A", "B"], max_samples=3)))

    # evidence file
    reset_scene()
    run_dir = os.path.join(out_dir, "h1_run")
    os.makedirs(run_dir, exist_ok=True)
    box("A", (1, 1, 1))
    box("B", (1, 1, 1), (1, 0, 0))
    ev = os.path.join(run_dir, "clash.json")
    audit(objects=["A", "B"], evidence_path=ev)
    doc = json.load(open(ev, encoding="utf-8"))
    from datetime import datetime, timedelta
    t = datetime.fromisoformat(doc["time"])
    check("H1 evidence has script, UTC time, verdict, numbers",
          doc["script"] == "clash_audit.py" and doc["verdict"] == "PASS" and t.utcoffset() == timedelta(0)
          and doc["summary"]["clashes"] == 0 and "objects_checked" in doc["summary"], doc)
    bpy.data.objects["B"].location.x = 0.75
    audit(objects=["A", "B"], evidence_path=ev)
    doc = json.load(open(ev, encoding="utf-8"))
    check("H1 failing audit writes verdict FAIL with the numbers",
          doc["verdict"] == "FAIL" and doc["summary"]["clashes"] == 1 and abs(doc["summary"]["max_depth_m"] - 0.25) < 0.03, doc)
    check("H1 evidence folder must exist", raises(lambda: audit(objects=["A", "B"], evidence_path=os.path.join(out_dir, "no_such", "e.json"))))
    foreign = os.path.join(run_dir, "other.json")
    json.dump({"script": "validate_asset.py", "verdict": "PASS"}, open(foreign, "w"))
    check("H1 refuses to overwrite another script's file", raises(lambda: audit(objects=["A", "B"], evidence_path=foreign))
          and json.load(open(foreign))["script"] == "validate_asset.py")
    check("H1 evidence must be .json", raises(lambda: audit(objects=["A", "B"], evidence_path=os.path.join(run_dir, "e.txt"))))
    bpy.data.objects["B"].location.x = 1.0
    audit(objects=["A", "B"], evidence_path=ev)  # a PASS run replaces the earlier FAIL file
    check("H1 later PASS replaces own evidence", json.load(open(ev))["verdict"] == "PASS")
    # a failing audit that raises writes nothing new
    stale = json.load(open(ev))["time"]
    raises(lambda: audit(objects=["Nope"], evidence_path=ev))
    check("H1 a crashed audit leaves the earlier evidence alone", json.load(open(ev))["time"] == stale)

    # the real run manifest accepts this file for `validate`, and refuses a failing one and `export`
    manifest_py = os.path.normpath(os.path.join(SCRIPTS, "..", "..", "blender-director", "scripts", "run_manifest.py"))

    def manifest(**kw):
        return runpy.run_path(manifest_py, init_globals={"ARGS": dict(out_dir=run_dir, skill="qa-review", script="clash_audit.py", **kw)})["result"]

    good = manifest(stage="validate", verdict="PASS", evidence="clash.json", result_summary={"clashes": 0})
    check("H1 run_manifest accepts clash evidence for validate", good["gates"]["validate"] == "PASS", good)
    check("H1 run_manifest refuses clash evidence for export",
          raises(lambda: manifest(stage="export", verdict="PASS", evidence="clash.json", result_summary={"clashes": 0})))
    bpy.data.objects["B"].location.x = 0.75
    audit(objects=["A", "B"], evidence_path=ev)
    check("H1 run_manifest refuses a failing clash file",
          raises(lambda: manifest(stage="validate", verdict="PASS", evidence="clash.json", result_summary={"clashes": 0})))


# ---------------------------------------------------------------- H2 silhouette_score + H3 fit_search
def sil(objects, views, **kw):
    return run("silhouette_score.py", {"objects": objects, "views": views, **kw})


def test_silhouette(check, out_dir, measured):
    reset_scene()
    d = os.path.join(out_dir, "h2")
    os.makedirs(d, exist_ok=True)

    # 1. real Workbench render of an asymmetric object, a perspective camera close enough to foreshorten
    obj = mesh_obj("Chair", boxes(((1.0, 1.0, 0.2), (0, 0, 0)), ((0.2, 1.0, 1.0), (-0.4, 0, 0.6)),
                                   ((0.3, 0.3, 0.7), (0.35, 0.3, -0.45))),
                   rot=(0, 0, math.radians(35)))
    cam = camera("CamP", (2.6, -3.0, 1.9), look_at=(0, 0, 0.2), lens=28)
    ref = render(os.path.join(d, "persp.png"), cam)
    ref_px = int(read_alpha(ref).sum())
    n_img = len(leaked_images())
    before = snapshot()
    r = sil(["Chair"], [{"camera": "CamP", "reference": ref}])
    v = r["views"][0]
    measured["workbench_perspective_iou"] = v["iou"]
    check("H2 exact mask (Workbench perspective): IoU > 0.98", v["iou"] > 0.98 and r["verdict"] == "PASS", v)
    check("H2 reference pixels agree with an independent alpha read", v["pixels_reference"] == ref_px, (v["pixels_reference"], ref_px))
    check("H2 mask taken from alpha", v["mask_from"] == "alpha", v["mask_from"])
    check("H2 loaded images removed", len(leaked_images()) == n_img, (n_img, leaked_images()))
    check("H2 scene unchanged", snapshot() == before, snap_diff(before, snapshot()))
    check("H2 drift near zero", v["centroid_drift_px"] < 0.6 and v["bbox_drift_px"] <= 1.5, v)

    for aa in ("OFF", "8"):
        p = render(os.path.join(d, f"persp_aa{aa}.png"), cam, aa=aa)
        vv = sil(["Chair"], [{"camera": "CamP", "reference": p}])["views"][0]
        measured[f"workbench_perspective_iou_aa_{aa}"] = vv["iou"]
        check(f"H2 Workbench AA={aa}: IoU > 0.98", vv["iou"] > 0.98, vv["iou"])

    # orthographic camera and a bigger frame
    ocam = camera("CamO", (0, -6, 0.5), look_at=(0, 0, 0.5), ortho=3.2)
    oref = render(os.path.join(d, "ortho.png"), ocam, 200, 150)
    vo = sil(["Chair"], [{"camera": "CamO", "reference": oref}])["views"][0]
    measured["workbench_ortho_iou"] = vo["iou"]
    check("H2 orthographic camera: IoU > 0.98", vo["iou"] > 0.98, vo)

    # 2. moved / scaled / wrong shape all score measurably lower; the right one still passes
    base = v["iou"]
    obj.location.x += 0.15
    moved = sil(["Chair"], [{"camera": "CamP", "reference": ref}])
    check("H2 moved object scores lower and fails", moved["views"][0]["iou"] < base - 0.1 and moved["verdict"] == "FAIL", moved["views"][0]["iou"])
    check("H2 moved object shows centroid drift", moved["views"][0]["centroid_drift_px"] > 3, moved["views"][0])
    obj.location.x -= 0.15
    obj.scale = (1.15, 1.15, 1.15)
    scaled = sil(["Chair"], [{"camera": "CamP", "reference": ref}])
    check("H2 scaled object scores lower", scaled["views"][0]["iou"] < base - 0.05, scaled["views"][0]["iou"])
    check("H2 scaled object: size ratio > 1", scaled["views"][0]["size_ratio"][0] > 1.05, scaled["views"][0].get("size_ratio"))
    obj.scale = (1, 1, 1)
    small = sil(["Chair"], [{"camera": "CamP", "reference": ref}])
    check("H2 restored object scores like the first run", abs(small["views"][0]["iou"] - base) < 1e-9, small["views"][0]["iou"])
    obj.location.x += 0.02
    nudge = sil(["Chair"], [{"camera": "CamP", "reference": ref}])["views"][0]["iou"]
    check("H2 a 2 cm nudge is visible in the score", nudge < base - 0.003, (nudge, base))
    obj.location.x -= 0.02

    reset_scene()
    box("Cube", (1, 1, 1))
    cam = camera("CamF", (0, -5, 0), rot_deg=(90, 0, 0))
    cube_ref = render(os.path.join(d, "cube.png"), cam)
    ok = sil(["Cube"], [{"camera": "CamF", "reference": cube_ref}])
    check("H2 cube vs its own render passes", ok["views"][0]["iou"] > 0.98, ok["views"][0]["iou"])
    sph = uvsphere("Sphere", 0.5)
    wrong = sil(["Sphere"], [{"camera": "CamF", "reference": cube_ref}])
    measured["sphere_vs_cube_iou"] = wrong["views"][0]["iou"]
    check("H2 wrong shape (sphere vs cube render) fails", wrong["verdict"] == "FAIL" and wrong["views"][0]["iou"] < 0.85, wrong["views"][0]["iou"])
    bpy.data.objects["Cube"].hide_render = True
    sph_ref = render(os.path.join(d, "sphere.png"), cam)
    bpy.data.objects["Cube"].hide_render = False
    right = sil(["Sphere"], [{"camera": "CamF", "reference": sph_ref}])
    check("H2 sphere vs its own render passes", right["views"][0]["iou"] > 0.97, right["views"][0]["iou"])
    check("H2 cube vs sphere render fails", sil(["Cube"], [{"camera": "CamF", "reference": sph_ref}])["verdict"] == "FAIL")

    # 3. object partly outside the frame, and fully outside
    bpy.data.objects.remove(bpy.data.objects["Sphere"])
    bpy.data.objects["Cube"].location = (1.05, 0, 0)  # half the cube is right of the frame edge
    edge_ref = render(os.path.join(d, "edge.png"), cam)
    edge = sil(["Cube"], [{"camera": "CamF", "reference": edge_ref}])["views"][0]
    measured["partly_outside_frame_iou"] = edge["iou"]
    check("H2 object partly outside the frame: IoU > 0.97", edge["iou"] > 0.97 and edge["pixels_reference"] > 500, edge)
    bpy.data.objects["Cube"].location = (40, 0, 0)
    gone = sil(["Cube"], [{"camera": "CamF", "reference": edge_ref}])
    check("H2 object outside the view scores 0 with a note", gone["views"][0]["iou"] == 0.0 and "note" in gone["views"][0] and gone["verdict"] == "FAIL", gone["views"][0])

    # 4. orientation: an asymmetric shape against a real render, flipped / mirrored copies must fail
    reset_scene()
    mesh_obj("L", boxes(((2.0, 0.3, 0.5), (0, 0, -0.75)), ((0.5, 0.3, 1.5), (-0.75, 0, 0.25))))  # foot at the bottom-right of the stroke
    cam = camera("CamF", (0, -6, 0), rot_deg=(90, 0, 0))
    lref = render(os.path.join(d, "l.png"), cam)
    good = sil(["L"], [{"camera": "CamF", "reference": lref}])["views"][0]["iou"]
    a = read_alpha(lref)
    save_array_png(os.path.join(d, "l_flipud.png"), np.flipud(a))
    save_array_png(os.path.join(d, "l_fliplr.png"), np.fliplr(a))
    fu = sil(["L"], [{"camera": "CamF", "reference": os.path.join(d, "l_flipud.png")}])["views"][0]["iou"]
    fl = sil(["L"], [{"camera": "CamF", "reference": os.path.join(d, "l_fliplr.png")}])["views"][0]["iou"]
    measured["orientation_iou_good_flipud_fliplr"] = [good, fu, fl]
    check("H2 asymmetric shape: right way up scores high, flipped copies score low", good > 0.98 and fu < 0.7 and fl < 0.7, (good, fu, fl))
    check("H2 render has the foot where expected (top-down check)", a[:, :a.shape[1] // 2].sum() > a[:, a.shape[1] // 2:].sum(), None)

    # 5. masks computed by hand from the pinhole equations (no render, no scorer, pure-Python PNG)
    W, H = 160, 120
    f_px = 50.0 / 36.0 * W
    reset_scene()
    # 5a. L-shaped pair of rectangles facing the camera, camera at y=-5: asymmetric, tests orientation
    def rects(bm):
        for (x0, x1, z0, z1) in ((-1.0, 1.0, -1.0, -0.5), (-1.0, -0.5, -0.5, 1.0)):
            vs = [bm.verts.new(p) for p in ((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1))]
            bm.faces.new(vs)
    mesh_obj("Quads", rects)
    camera("CamH", (0, -5, 0), rot_deg=(90, 0, 0))
    inside_l = lambda u, v: (-1 <= u * 5 <= 1 and -1 <= v * 5 <= -0.5) or (-1 <= u * 5 <= -0.5 and -0.5 <= v * 5 <= 1)
    write_mask_png(os.path.join(d, "hand_l.png"), hand_mask(W, H, f_px, inside_l))
    hl = sil(["Quads"], [{"camera": "CamH", "reference": os.path.join(d, "hand_l.png")}])["views"][0]
    measured["hand_mask_L_iou"] = hl["iou"]
    check("H2 hand-computed L mask: IoU > 0.98", hl["iou"] > 0.98, hl)
    write_mask_png(os.path.join(d, "hand_l_flip.png"), hand_mask(W, H, f_px, lambda u, v: inside_l(u, -v)))
    hf = sil(["Quads"], [{"camera": "CamH", "reference": os.path.join(d, "hand_l_flip.png")}])["views"][0]["iou"]
    check("H2 hand-computed L mask flipped vertically scores low", hf < 0.7, hf)

    # 5b. perspective foreshortening: a ground plane receding from the camera is a trapezoid
    reset_scene()
    def ground(y0, y1):
        def build(bm):
            vs = [bm.verts.new(p) for p in ((-2, y0, -1), (2, y0, -1), (2, y1, -1), (-2, y1, -1))]
            bm.faces.new(vs)
        return build
    mesh_obj("Ground", ground(3.0, 10.0))
    camera("CamG", (0, 0, 0), rot_deg=(90, 0, 0))
    def inside_g(y0, y1):
        def fn(u, v):
            if v >= 0:
                return False
            t = -1.0 / v
            return y0 <= t <= y1 and abs(u * t) <= 2.0
        return fn
    write_mask_png(os.path.join(d, "hand_g.png"), hand_mask(W, H, f_px, inside_g(3.0, 10.0)))
    hg = sil(["Ground"], [{"camera": "CamG", "reference": os.path.join(d, "hand_g.png")}])["views"][0]
    measured["hand_mask_foreshortening_iou"] = hg["iou"]
    check("H2 hand-computed foreshortened trapezoid: IoU > 0.97", hg["iou"] > 0.97, hg)

    # 5c. part of the object is behind the camera (plane runs from y=-10 to y=10 under the camera)
    bpy.data.objects.remove(bpy.data.objects["Ground"])
    mesh_obj("Ground", ground(-10.0, 10.0))
    write_mask_png(os.path.join(d, "hand_gb.png"), hand_mask(W, H, f_px, inside_g(0.1, 10.0)))
    hb = sil(["Ground"], [{"camera": "CamG", "reference": os.path.join(d, "hand_gb.png")}])["views"][0]
    measured["hand_mask_behind_camera_iou"] = hb["iou"]
    check("H2 object partly behind the camera: IoU > 0.97", hb["iou"] > 0.97, hb)
    # same, with the camera inside the object's span of a tall wall (near plane cuts it)
    # 5d. far clip: shrink the far plane to 6 m and the visible trapezoid shrinks too
    bpy.data.objects["CamG"].data.clip_end = 6.0
    write_mask_png(os.path.join(d, "hand_gf.png"), hand_mask(W, H, f_px, inside_g(0.1, 6.0)))
    hfar = sil(["Ground"], [{"camera": "CamG", "reference": os.path.join(d, "hand_gf.png")}])["views"][0]
    check("H2 far clip plane honoured: IoU > 0.97", hfar["iou"] > 0.97, hfar)

    # 6. background taken from the corners when there is no alpha
    reset_scene()
    box("Cube", (1, 1, 1), rot=(0.3, 0.2, 0.6))
    cam = camera("CamF", (0, -5, 0), rot_deg=(90, 0, 0))
    wd = bpy.data.worlds.new("W")
    wd.color = (0.1, 0.25, 0.4)
    bpy.context.scene.world = wd
    opaque = render(os.path.join(d, "opaque.png"), cam, transparent=False)
    vo = sil(["Cube"], [{"camera": "CamF", "reference": opaque}])["views"][0]
    check("H2 opaque render: mask from the corner background, IoU > 0.97", vo["mask_from"] == "background" and vo["iou"] > 0.97, vo)
    # corners that disagree -> refuse
    arr = np.ones((60, 80, 4), dtype=np.float32)
    arr[:30, :40, :3] = 0.9
    arr[30:, 40:, :3] = 0.1
    img = bpy.data.images.new("tmp_two", 80, 60, alpha=True)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = os.path.join(d, "two.png")
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    check("H2 corners that disagree -> ValueError", raises(lambda: sil(["Cube"], [{"camera": "CamF", "reference": os.path.join(d, "two.png")}])))
    check("H2 alpha mode on an opaque image -> ValueError", raises(lambda: sil(["Cube"], [{"camera": "CamF", "reference": opaque, "mask": "alpha"}])))

    # argument errors
    check("H2 missing camera -> ValueError", raises(lambda: sil(["Cube"], [{"camera": "Nope", "reference": opaque}])))
    check("H2 missing image -> ValueError", raises(lambda: sil(["Cube"], [{"camera": "CamF", "reference": os.path.join(d, "nope.png")}])))
    check("H2 non-mesh subject -> ValueError", raises(lambda: sil(["CamF"], [{"camera": "CamF", "reference": opaque}])))
    empty = os.path.join(d, "empty.png")
    write_mask_png(empty, [[False] * 16 for _ in range(12)])
    check("H2 empty reference mask -> ValueError", raises(lambda: sil(["Cube"], [{"camera": "CamF", "reference": empty}])))
    check("H2 no images leaked", not leaked_images(), leaked_images())


def fit(**kw):
    return run("fit_search.py", kw)


def test_fit(check, out_dir, measured):
    reset_scene()
    d = os.path.join(out_dir, "h3")
    os.makedirs(d, exist_ok=True)
    box("Box", (1, 1, 1))
    cam = camera("CamF", (0, -6, 0), rot_deg=(90, 0, 0))
    bpy.data.objects["Box"].scale = (1.3, 1.3, 1.3)
    bpy.data.objects["Box"].location.x = 0.25
    ref = render(os.path.join(d, "box13.png"), cam)
    views = [{"camera": "CamF", "reference": ref}]

    # wrong start: scale 0.8 and no shift. apply false -> everything restored
    box_o = bpy.data.objects["Box"]
    box_o.scale, box_o.location = (0.8, 0.8, 0.8), (0, 0, 0)
    start_iou = sil(["Box"], views)["views"][0]["iou"]
    before = snapshot()
    r = fit(objects=["Box"], views=views, params=[{"object": "Box", "path": "scale", "min": 0.3, "max": 3.0},
                                                  {"object": "Box", "path": "location[0]", "min": -1.0, "max": 1.0, "step": 0.4}],
            max_evals=80)
    found = {p["param"]: p["value"] for p in r["best"]}
    measured["fit_scale_found"] = found.get("Box.scale")
    measured["fit_location_x_found"] = found.get("Box.location[0]")
    measured["fit_evals"] = r["evals"]
    measured["fit_score_best"] = r["score_best"]
    check("H3 recovers the known scale 1.3 within 0.03", abs(found["Box.scale"] - 1.3) <= 0.03, found)
    check("H3 recovers the known shift 0.25 within 0.03", abs(found["Box.location[0]"] - 0.25) <= 0.03, found)
    check("H3 score improves a lot", r["score_best"] > 0.97 and r["score_best"] > start_iou + 0.2, (start_iou, r["score_best"]))
    check("H3 evals bounded", r["evals"] <= 80, r["evals"])
    check("H3 apply false restores every value", near(box_o.scale, (0.8, 0.8, 0.8)) and near(box_o.location, (0, 0, 0)) and r["restored"] and not r["applied"], (tuple(box_o.scale), tuple(box_o.location)))
    check("H3 scene otherwise unchanged", snapshot() == before, snap_diff(before, snapshot()))

    # apply true keeps the best values, and the H2 scorer agrees with the fit's own score
    r = fit(objects=["Box"], views=views, params=[{"object": "Box", "path": "scale", "min": 0.3, "max": 3.0},
                                                  {"object": "Box", "path": "location[0]", "min": -1.0, "max": 1.0, "step": 0.4}],
            max_evals=80, apply=True)
    check("H3 apply true keeps the fit", abs(box_o.scale[0] - 1.3) <= 0.03 and abs(box_o.scale[2] - 1.3) <= 0.03 and abs(box_o.location.x - 0.25) <= 0.03 and r["applied"], (tuple(box_o.scale), box_o.location.x))
    after = sil(["Box"], views)["views"][0]["iou"]
    check("H3 scored by H2: the applied state scores the reported best", abs(after - r["score_best"]) < 1e-6 and after > 0.97, (after, r["score_best"]))

    # max_evals bound
    box_o.scale, box_o.location = (0.8, 0.8, 0.8), (0, 0, 0)
    r = fit(objects=["Box"], views=views, params=[{"object": "Box", "path": "scale", "min": 0.3, "max": 3.0}], max_evals=5)
    check("H3 max_evals respected", r["evals"] == 5 and not r["converged"], (r["evals"], r["converged"]))
    check("H3 values restored after a capped run", near(box_o.scale, (0.8, 0.8, 0.8)), tuple(box_o.scale))

    # review M-1: count the real score calls (rasterize runs once per view per score) with a counter the script does not own
    calls = []
    real_run_path = runpy.run_path

    def counting_run_path(path, *a, **k):
        g = real_run_path(path, *a, **k)
        if os.path.basename(path) == "silhouette_score.py" and "rasterize" in g:
            inner = g["rasterize"]
            g["rasterize"] = lambda *x, **y: (calls.append(1), inner(*x, **y))[1]
        return g

    runpy.run_path = counting_run_path
    try:
        for cap in (1, 2, 5):
            calls.clear()
            box_o.scale, box_o.location = (0.8, 0.8, 0.8), (0, 0, 0)
            r = fit(objects=["Box"], views=views, params=[{"object": "Box", "path": "scale", "min": 0.3, "max": 3.0}], max_evals=cap)
            check(f"H3 max_evals={cap}: real score calls never exceed it, and the reported count is the real one",
                  len(calls) <= cap and r["evals"] == len(calls), (cap, len(calls), r["evals"]))
    finally:
        runpy.run_path = real_run_path

    # single axis component
    box_o.scale, box_o.location = (0.8, 1.3, 1.3), (0.25, 0, 0)  # the camera looks along Y, so X is the visible axis
    r = fit(objects=["Box"], views=views, params=[{"object": "Box", "path": "scale[0]", "min": 0.3, "max": 3.0}], max_evals=60, apply=True)
    check("H3 single component fit moves only that axis", near(box_o.scale[1:], (1.3, 1.3)) and abs(box_o.scale[0] - 1.3) <= 0.03, tuple(box_o.scale))

    # every error comes before any change
    box_o.scale, box_o.location = (0.8, 0.8, 0.8), (0, 0, 0)
    before = snapshot()
    good = {"object": "Box", "path": "scale", "min": 0.3, "max": 3.0}
    for label, bad in (("unknown property", {"object": "Box", "path": "scalee", "min": 0, "max": 1}),
                       ("unknown object", {"object": "Nope", "path": "scale", "min": 0, "max": 1}),
                       ("index out of range", {"object": "Box", "path": "scale[5]", "min": 0, "max": 1}),
                       ("read-only property", {"object": "Box", "path": "users", "min": 0, "max": 1}),
                       ("non-numeric property", {"object": "Box", "path": "name", "min": 0, "max": 1}),
                       ("bad data path", {"object": "Box", "path": "modifiers['X'].width", "min": 0, "max": 1}),
                       ("start outside bounds", {"object": "Box", "path": "scale", "min": 1.0, "max": 3.0}),
                       ("min above max", {"object": "Box", "path": "scale", "min": 3.0, "max": 1.0})):
        msg = raises(lambda bad=bad: fit(objects=["Box"], views=views, params=[good, bad], max_evals=20))
        check(f"H3 {label} -> error before any change", msg and snapshot() == before and near(box_o.scale, (0.8, 0.8, 0.8)), msg)
    check("H3 missing reference -> error", raises(lambda: fit(objects=["Box"], views=[{"camera": "CamF", "reference": os.path.join(d, "no.png")}], params=[good])))
    check("H3 no params -> error", raises(lambda: fit(objects=["Box"], views=views, params=[])))
    check("H3 no images leaked", not leaked_images(), leaked_images())


# ---------------------------------------------------------------- H4 ingest_asset
def build_source(sc_dims=100.0):
    """A two-mesh parented hierarchy at 100x scale ("centimetres"), smooth icospheres with no UVs, so that the file
    formats can keep one vertex per source vertex."""
    body = ico("Body", (0.6 * sc_dims, 0.4 * sc_dims, 1.8 * sc_dims), loc=(10, -20, 0.9 * sc_dims), rot=(0, 0, math.radians(20)))
    head = ico("Head", (0.3 * sc_dims, 0.3 * sc_dims, 0.3 * sc_dims), loc=(5, 0, 1.15 * sc_dims), parent=body)
    bpy.context.view_layer.update()
    return body, head


def export_src(kind, path):
    bpy.ops.object.select_all(action="DESELECT")
    for n in ("Body", "Head"):
        bpy.data.objects[n].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["Body"]
    if kind == "glb":
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    elif kind == "gltf":
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLTF_SEPARATE", use_selection=True)
    elif kind == "fbx":
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True)
    elif kind == "obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
    elif kind == "usd":
        bpy.ops.wm.usd_export(filepath=path, selected_objects_only=True)


def hausdorff(a, b):
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(2))
    return float(max(d.min(1).max(), d.min(0).max()))


def test_ingest(check, out_dir, measured):
    d = os.path.join(out_dir, "h4")
    os.makedirs(d, exist_ok=True)
    target = 1.8
    formats = {"glb": ".glb", "gltf": ".gltf", "fbx": ".fbx", "obj": ".obj", "usd": ".usd"}
    outcome = {}
    for kind, ext in formats.items():
        label = f"H4 {kind}"
        try:
            reset_scene()
            body, head = build_source()
            src_verts = np.concatenate([world_verts(body), world_verts(head)])
            src_count = len(src_verts)
            height = src_verts[:, 2].max() - src_verts[:, 2].min()
            s = target / height
            centre = np.array([(src_verts[:, 0].max() + src_verts[:, 0].min()) / 2, (src_verts[:, 1].max() + src_verts[:, 1].min()) / 2, src_verts[:, 2].min()])
            expected = (src_verts - centre) * s
            path = os.path.join(d, f"model_{kind}{ext}")
            export_src(kind, path)
            reset_scene()
            existing = box("Existing", (1, 1, 1), (3, 3, 0.5))
            existing.select_set(True)
            bpy.context.view_layer.update()
            before = {"m": [tuple(r) for r in existing.matrix_world], "v": len(existing.data.vertices),
                      "cols": [c.name for c in existing.users_collection], "all_cols": set(bpy.data.collections.keys())}
            r = run("ingest_asset.py", {"path": path, "target_size_m": target})
            meshes = [bpy.data.objects[n] for n in r["meshes"]]
            actual = np.concatenate([world_verts(m) for m in meshes])
            size_z = actual[:, 2].max() - actual[:, 2].min()
            hd = hausdorff(expected, actual)
            outcome[kind] = {"height_m": round(float(size_z), 5), "hausdorff_m": round(hd, 6),
                             "vertices_source": src_count, "vertices_imported": r["vertices"]["imported"],
                             "vertices_final": r["vertices"]["final"], "scale_factor": r["scale_factor"]}
            check(f"{label}: wrong-scale file comes out at the target height", abs(size_z - target) < 1e-3 * target, size_z)
            check(f"{label}: normalizing keeps the vertex count", r["vertices"]["imported"] == r["vertices"]["final"], r["vertices"])
            check(f"{label}: vertex count equals the source's", r["vertices"]["final"] == src_count, (r["vertices"], src_count))
            check(f"{label}: world shape matches the source normalized (Hausdorff < 0.2% of height)", hd < 0.002 * target, hd)
            base = [(actual[:, 0].max() + actual[:, 0].min()) / 2, (actual[:, 1].max() + actual[:, 1].min()) / 2, actual[:, 2].min()]
            check(f"{label}: base centre at the world origin", all(abs(v) < 2e-3 for v in base), base)
            cond = ([tuple(x) for x in existing.matrix_world] == before["m"], len(existing.data.vertices) == before["v"],
                    [c.name for c in existing.users_collection] == before["cols"], existing.select_get())
            check(f"{label}: existing object untouched (matrix, vertices, collection, selection)", all(cond), cond)
            check(f"{label}: imported objects live only in the new collection",
                  all([c.name for c in bpy.data.objects[n].users_collection] == [r["collection"]] for n in r["imported_objects"])
                  and set(bpy.data.collections.keys()) == before["all_cols"] | {r["collection"]}, (r["collection"], list(bpy.data.collections.keys())))
            check(f"{label}: meshes carry the prefix", all(n.startswith("SM_") for n in r["meshes"]), r["meshes"])
            check(f"{label}: validate_asset ran on the imported meshes", set(r["validation"]["objects"]) == set(r["meshes"]), list(r["validation"]["objects"]))
            check(f"{label}: transforms were baked (validate transforms_applied PASS)",
                  all(o["checks"]["transforms_applied"]["status"] == "PASS" for o in r["validation"]["objects"].values()), r["validation"]["objects"])
            roots = [bpy.data.objects[n] for n in r["imported_objects"] if bpy.data.objects[n].parent is None]
            check(f"{label}: every imported root has its origin at the world origin (base centre)",
                  roots and all(o.matrix_world.translation.length < 2e-3 for o in roots), [(o.name, tuple(o.matrix_world.translation)) for o in roots])
            if kind != "obj":  # OBJ has no hierarchy
                head_m = next(m for m in meshes if "Head" in m.name)
                chain, p = [], head_m.parent
                while p is not None:
                    chain.append(p.name)
                    p = p.parent
                check(f"{label}: head stays parented under the body", any("Body" in n for n in chain)
                      and all(n in r["imported_objects"] for n in chain), chain)
            outcome[kind]["passed"] = True
        except Exception:
            outcome.setdefault(kind, {})["passed"] = False
            check(f"{label}: round trip ran", False, tb())
    measured["ingest_formats"] = outcome

    # gltf with external buffers: the .bin is next to the .gltf and the .gltf refers to it by name
    gl = os.path.join(d, "model_gltf.gltf")
    doc = json.load(open(gl, encoding="utf-8"))
    uris = [b.get("uri", "") for b in doc.get("buffers", [])]
    check("H4 gltf fixture has an external .bin buffer", uris and all(u.endswith(".bin") and not u.startswith("data:") for u in uris)
          and all(os.path.isfile(os.path.join(d, u)) for u in uris), uris)
    # the same .gltf copied alone (buffer missing) must fail and roll back everything
    import shutil
    lone = os.path.join(d, "lone")
    os.makedirs(lone, exist_ok=True)
    shutil.copy(gl, os.path.join(lone, "model_gltf.gltf"))
    reset_scene()
    box("Existing", (1, 1, 1))
    names, cols = set(bpy.data.objects.keys()), set(bpy.data.collections.keys())
    msg = raises(lambda: run("ingest_asset.py", {"path": os.path.join(lone, "model_gltf.gltf")}), (ValueError, RuntimeError))
    check("H4 gltf without its .bin fails", msg is not None, msg)
    check("H4 failed import rolls back objects and collections", set(bpy.data.objects.keys()) == names and set(bpy.data.collections.keys()) == cols,
          (set(bpy.data.objects.keys()) - names, set(bpy.data.collections.keys()) - cols))

    # a file with no mesh: the import creates an object, then the script refuses and removes what it created
    reset_scene()
    bpy.ops.object.empty_add(location=(1, 2, 3))
    bpy.context.object.name = "OnlyAnEmpty"
    only = os.path.join(d, "only_empty.glb")
    bpy.ops.export_scene.gltf(filepath=only, export_format="GLB", use_selection=True)
    reset_scene()
    box("Existing", (1, 1, 1))
    names, cols = set(bpy.data.objects.keys()), set(bpy.data.collections.keys())
    msg = raises(lambda: run("ingest_asset.py", {"path": only}))
    check("H4 a file with no mesh is refused", msg and "no mesh" in msg, msg)
    check("H4 refusal after the import removes the objects and the collection it made",
          set(bpy.data.objects.keys()) == names and set(bpy.data.collections.keys()) == cols,
          (set(bpy.data.objects.keys()) - names, set(bpy.data.collections.keys()) - cols))

    # review (non-blocking): an importer that creates an object and then raises must not leave it behind
    reset_scene()
    box("Existing", (1, 1, 1))
    names, cols, meshes_before = set(bpy.data.objects.keys()), set(bpy.data.collections.keys()), set(bpy.data.meshes.keys())
    src = open(os.path.join(SCRIPTS, "ingest_asset.py"), encoding="utf-8").read()
    head, tail = src.split("def _run_import(kind, path):", 1)
    tail = tail.split("\ndef _layer_collection", 1)[1]
    broken = head + ("def _run_import(kind, path):\n"
                     "    me = bpy.data.meshes.new('Half'); o = bpy.data.objects.new('Half', me)\n"
                     "    bpy.context.scene.collection.objects.link(o)\n"
                     "    raise RuntimeError('corrupt mesh 2')\n\n\ndef _layer_collection") + tail
    g = {"ARGS": {"path": os.path.join(d, "model_glb.glb")}, "__name__": "__skill_test__", "__file__": os.path.join(SCRIPTS, "ingest_asset.py")}
    msg = raises(lambda: exec(compile(broken, "ingest_asset_broken.py", "exec"), g), (RuntimeError, ValueError))
    check("H4 partial import: the importer's error surfaces", msg and "corrupt mesh 2" in msg, msg)
    check("H4 partial import: the object the importer made is removed, with its mesh and the collection",
          set(bpy.data.objects.keys()) == names and set(bpy.data.collections.keys()) == cols and set(bpy.data.meshes.keys()) == meshes_before,
          (set(bpy.data.objects.keys()) - names, set(bpy.data.collections.keys()) - cols, set(bpy.data.meshes.keys()) - meshes_before))

    # up-axis fix: OBJ written with Y up, read with the importer's default -> comes in lying down
    reset_scene()
    body, head = build_source()
    sel = os.path.join(d, "lying.obj")
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    head.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.obj_export(filepath=sel, export_selected_objects=True, forward_axis="NEGATIVE_Z", up_axis="Z")
    reset_scene()
    plain = run("ingest_asset.py", {"path": sel, "target_size_m": target, "size_axis": "max"})
    reset_scene()
    def head_above_body(res):
        z = {k: np.mean([world_verts(bpy.data.objects[n])[:, 2].mean() for n in res["meshes"] if k in n]) for k in ("Head", "Body")}
        return bool(z["Head"] > z["Body"])

    fixed = {}
    for fix in ("y_up_to_z_up", "z_up_to_y_up"):
        reset_scene()
        rr = run("ingest_asset.py", {"path": sel, "target_size_m": target, "size_axis": "max", "up_axis_fix": fix})
        fixed[fix] = (rr["size_after_m"], head_above_body(rr))
    standing = {k: v[0][2] > v[0][0] and v[0][2] > v[0][1] and v[1] for k, v in fixed.items()}
    check("H4 up_axis_fix: the lying file ends up standing with its head up for exactly one direction", sum(standing.values()) == 1,
          {"plain": plain["size_after_m"], **{k: v for k, v in fixed.items()}})
    check("H4 up_axis_fix: without it the long side is not up", not (plain["size_after_m"][2] > plain["size_after_m"][0] and plain["size_after_m"][2] > plain["size_after_m"][1]), plain["size_after_m"])

    # refusals leave the scene untouched
    reset_scene()
    box("Existing", (1, 1, 1))
    before = (set(bpy.data.objects.keys()), set(bpy.data.collections.keys()))
    real = os.path.join(d, "model_glb.glb")
    for label, p, word in (("URL", "https://example.com/model.glb", "only local files"),
                           ("file URL naming a real file", "file:///" + real.replace("\\", "/"), "only local files"),
                           ("network path", "\\\\server\\share\\model.glb", "only local files"),
                           (".blend", os.path.join(d, "x.blend"), ".blend"),
                           ("unsupported type", os.path.join(d, "x.txt"), "unsupported"),
                           ("missing file", os.path.join(d, "missing.glb"), "not found")):
        msg = raises(lambda p=p: run("ingest_asset.py", {"path": p}))
        check(f"H4 refuses {label} for the right reason", msg and word in msg and
              (set(bpy.data.objects.keys()), set(bpy.data.collections.keys())) == before, msg)
    check("H4 bad size_axis -> ValueError", raises(lambda: run("ingest_asset.py", {"path": os.path.join(d, "model_glb.glb"), "size_axis": "w"})))

    # options: no scaling, no prefix, no baking
    reset_scene()
    r = run("ingest_asset.py", {"path": os.path.join(d, "model_glb.glb"), "prefix": "", "apply_transforms": False})
    check("H4 no target keeps the file's scale ratio and skips the prefix",
          r["scale_factor"] == 1.0 and not r["renamed"] and all(not n.startswith("SM_") for n in r["meshes"]), r["scale_factor"])
    check("H4 collection argument names the collection", run("ingest_asset.py", {"path": os.path.join(d, "model_glb.glb"), "collection": "MyAsset"})["collection"].startswith("MyAsset"))


def run_all(out_dir):
    results, measured = [], {}

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    os.makedirs(out_dir, exist_ok=True)
    for label, fn, wants_measured in (("clash_audit", test_clash, False), ("silhouette_score", test_silhouette, True),
                                      ("fit_search", test_fit, True), ("ingest_asset", test_ingest, True)):
        try:
            fn(check, out_dir, measured) if wants_measured else fn(check, out_dir)
        except Exception:
            check(f"{label} section crashed", False, tb())
    return results, measured


def main(out_dir="/tmp/parity_tests"):
    results, measured = [], {}
    try:
        results, measured = run_all(out_dir)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": tb()}]
    failures = [r for r in results if not r["ok"]]
    report = {"passed": len(results) - len(failures), "total": len(results), "failed": len(failures), "failures": failures,
              "measured": measured, "results": results}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "parity_tests_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("passed", "total", "failures")}, indent=2))
