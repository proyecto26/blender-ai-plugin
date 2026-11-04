"""Headless Blender tests for iteration-13 batch D (content tools): D1 import_painter_textures, D2 terrain_heightfield,
D3 surface_tools, D4 ps1_look.

Writes <out_dir>/iter13_content_report.json (passed, total, failed) and exits non-zero on a failure. Never saves the open
file. Use a NEW out_dir each run.

    blender -b --factory-startup --python tests/blender/test_iter13_content.py -- '{"out_dir": "/tmp/iter13-content-<new>"}'
"""
import json
import os
import runpy
import sys
import tempfile
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw and raw[0] == "--args-file":
            with open(raw[1], encoding="utf-8") as fh:
                return json.load(fh)
        if raw:
            return json.loads(raw[0])
    return {}


def run(skill, script, args):
    return runpy.run_path(os.path.join(SKILLS, skill, "scripts", script), init_globals={"ARGS": args},
                          run_name="__skill_test__")["result"]


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


class Recorder:
    def __init__(self):
        self.results = []

    def check(self, name, ok, detail=""):
        self.results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    def section(self, name, fn):
        try:
            fn(self)
        except Exception:
            self.results.append({"name": f"{name}: crashed", "ok": False, "detail": traceback.format_exc()[-700:]})


def eval_chain(sock, rgb, want_image=None):
    """Value of a socket: follow the links back from `sock` to a texture node whose pixels are `rgb`. With `want_image`
    (a file name fragment) the texture node must show that image and be read through its Color socket."""
    link = sock.links[0]
    node, out = link.from_node, link.from_socket
    if node.bl_idname == "ShaderNodeTexImage":
        if want_image is not None:
            name = os.path.basename(node.image.filepath or node.image.name).lower() if node.image else ""
            assert want_image.lower() in name, f"terminal image is {name!r}, expected the normal map {want_image!r}"
            assert out.name == "Color", f"image read through the {out.name!r} socket, expected Color"
        return rgb
    if node.bl_idname == "ShaderNodeSeparateColor":
        return eval_chain(node.inputs["Color"], rgb, want_image)[("Red", "Green", "Blue").index(out.name)]
    if node.bl_idname == "ShaderNodeCombineColor":
        return tuple(eval_chain(node.inputs[c], rgb, want_image) for c in ("Red", "Green", "Blue"))
    if node.bl_idname == "ShaderNodeMath" and node.operation == "SUBTRACT":
        a, b = (i.default_value if not i.links else eval_chain(i, rgb, want_image) for i in node.inputs[:2])
        return a - b
    raise AssertionError(node.bl_idname)


def normal_color_in(nt, rgb):
    nm = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeNormalMap")
    return tuple(round(c, 4) for c in eval_chain(nm.inputs["Color"], rgb, "normal"))


def save_map(path, value, size=8):
    img = bpy.data.images.new("tmp_map", size, size, alpha=False)
    try:
        px = np.ones((size, size, 4), dtype=np.float32)
        px[:, :, :3] = value
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def in_scene(scene, fn):
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        return fn()


def mesh_obj(scene, name, mesh=None):
    me = mesh or bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------- D1

def check_eval_chain_strict(rec):
    """The evaluator must reject a flip fed from Base Color, or read through the Alpha socket."""
    mat = bpy.data.materials.new("I13_EVAL_SELF")
    mat.use_nodes = True
    nt = mat.node_tree
    for img_name, sock, ok in (("Crate_BaseColor.png", "Color", False), ("Crate_Normal.png", "Alpha", False),
                               ("Crate_Normal.png", "Color", True)):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.new(img_name, 2, 2)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex.outputs[sock], nm.inputs["Color"])
        try:
            eval_chain(nm.inputs["Color"], (0.1, 0.2, 0.3), "normal")
            passed = True
        except AssertionError:
            passed = False
        rec.check(f"D1 evaluator self-check: {img_name} via {sock}", passed == ok)
    bpy.data.materials.remove(mat)


def test_d1(rec, scene, out_dir):
    check_eval_chain_strict(rec)
    dx = os.path.join(out_dir, "d1_dx")
    gl = os.path.join(out_dir, "d1_plain")
    os.makedirs(dx, exist_ok=True)
    os.makedirs(gl, exist_ok=True)
    for f, name in ((dx, "Crate_BaseColor.png"), (dx, "Crate_Normal_DirectX.png"), (gl, "Rock_BaseColor.png"),
                    (gl, "Rock_Normal.png")):
        save_map(os.path.join(f, name), 0.5)
    rgb = (0.2, 0.3, 0.7)  # asymmetric green: inverting 0.5 would be invisible
    for f, name in ((dx, "Crate_Normal_DirectX.png"), (gl, "Rock_Normal.png")):
        save_map(os.path.join(f, name), rgb)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": dx, "material": "MAT_I13_DX"})
    nt = bpy.data.materials["MAT_I13_DX"].node_tree
    rec.check("D1 DirectX file name without the param: green flipped", "FLIP_G_Invert" in nt.nodes and r["normal_convention"] == "DIRECTX", r)
    rec.check("D1 DirectX map: the Normal Map receives (R, 1-G, B), by following the links",
              normal_color_in(nt, rgb) == (0.2, 0.7, 0.7), normal_color_in(nt, rgb))
    dx2 = os.path.join(out_dir, "d1_dx2")
    os.makedirs(dx2, exist_ok=True)
    for name in ("Box_BaseColor.png", "Box_normal_dx.png"):
        save_map(os.path.join(dx2, name), 0.5)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": dx2, "material": "MAT_I13_DX3"})
    rec.check("D1 lower-case _normal_dx suffix without the param: green flipped",
              "FLIP_G_Invert" in bpy.data.materials["MAT_I13_DX3"].node_tree.nodes, r)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": gl, "material": "MAT_I13_GL"})
    rec.check("D1 normal map naming no convention: OPENGL assumed and the run warns",
              r["normal_convention"] == "OPENGL" and any("OPENGL" in w for w in r["warnings"]), r["warnings"])
    rec.check("D1 OpenGL map: the Normal Map receives the pixels untouched",
              normal_color_in(bpy.data.materials["MAT_I13_GL"].node_tree, rgb) == rgb)
    arm = os.path.join(out_dir, "d1_arm")
    os.makedirs(arm, exist_ok=True)
    save_map(os.path.join(arm, "DX_Armor_BaseColor.png"), 0.5)
    save_map(os.path.join(arm, "DX_Armor_Normal_OpenGL.png"), rgb)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": arm, "material": "MAT_I13_ARM"})
    ant = bpy.data.materials["MAT_I13_ARM"].node_tree
    rec.check("D1 'DX_' prefix does not outvote the OpenGL suffix next to 'Normal': not flipped, conflict warned",
              r["normal_convention"] == "OPENGL" and "FLIP_G_Invert" not in ant.nodes and normal_color_in(ant, rgb) == rgb
              and any("both" in w for w in r["warnings"]), r)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": dx, "material": "MAT_I13_DX2", "normal_convention": "OPENGL"})
    rec.check("D1 explicit value that contradicts the file name warns", any("disagrees" in w for w in r["warnings"]), r["warnings"])

    shared = bpy.data.meshes.new("I13_SharedMesh")
    a, b = mesh_obj(scene, "I13_A", shared), mesh_obj(scene, "I13_B", shared)
    msg = raises(lambda: run("texture-workflow", "import_painter_textures.py",
                             {"folder": gl, "material": "MAT_I13_Shared", "assign_to": ["I13_A"]}))
    rec.check("D1 assign_to one object of shared mesh data is refused, B gets no slot, no material made",
              msg is not None and len(b.material_slots) == 0 and "MAT_I13_Shared" not in bpy.data.materials, msg)
    r = run("texture-workflow", "import_painter_textures.py",
            {"folder": gl, "material": "MAT_I13_Shared", "assign_to": ["I13_A", "I13_B"]})
    rec.check("D1 listing both objects of shared data adds the slot once",
              len(shared.materials) == 1 and len(a.material_slots) == 1 and len(b.material_slots) == 1, len(shared.materials))


# ---------------------------------------------------------------- D2

def test_d2(rec, scene, out_dir):
    base = {"size": 4, "resolution": 5, "replace": True}
    plain = mesh_obj(scene, "I13_T_plain")
    scene.collection.objects  # noqa
    r = run("procedural-modeling", "terrain_heightfield.py", {**base, "name": "I13_T_plain"})
    rec.check("D2 control: a plain object is replaced", r["vertices"] == 25, r)

    disp = mesh_obj(scene, "I13_T_disp")
    disp.modifiers.new("D", "DISPLACE")
    msg = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**base, "name": "I13_T_disp"}))
    rec.check("D2 Displace modifier refused", msg is not None and "DISPLACE" in msg and len(disp.data.vertices) == 0, msg)

    for mtype in ("SUBSURF", "MULTIRES", "BEVEL", "DECIMATE", "REMESH", "SOLIDIFY"):
        sm = mesh_obj(scene, f"I13_T_{mtype}")
        sm.modifiers.new("M", mtype)
        msg = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**base, "name": f"I13_T_{mtype}"}))
        rec.check(f"D2 {mtype} modifier refused, mesh untouched", msg is not None and mtype in msg and len(sm.data.vertices) == 0, msg)

    off = mesh_obj(scene, "I13_T_off")
    m = off.modifiers.new("B", "BEVEL")
    m.show_viewport = m.show_render = False
    r = run("procedural-modeling", "terrain_heightfield.py", {**base, "name": "I13_T_off"})
    rec.check("D2 a disabled Bevel is ignored", r["vertices"] == 25, r)
    neutral = mesh_obj(scene, "I13_T_neutral")
    neutral.modifiers.new("W", "WEIGHTED_NORMAL")
    r = run("procedural-modeling", "terrain_heightfield.py", {**base, "name": "I13_T_neutral"})
    rec.check("D2 a geometry-neutral modifier is allowed", r["vertices"] == 25, r)

    rb = mesh_obj(scene, "I13_T_rb")
    rb.data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    bpy.context.view_layer.objects.active = rb
    with bpy.context.temp_override(object=rb, active_object=rb, selected_objects=[rb], selected_editable_objects=[rb]):
        bpy.ops.rigidbody.object_add()
    msg = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**base, "name": "I13_T_rb"}))
    rec.check("D2 rigid body refused, mesh untouched", rb.rigid_body is not None and msg is not None and "rigid body" in msg
              and len(rb.data.vertices) == 4, msg)


# ---------------------------------------------------------------- D3

def test_d3(rec, scene, out_dir):
    a = [[[x, y, 0.0] for x in (0.0, 1.0)] for y in (-3.0, -2.0, -1.0, 0.0)]
    b = [[[x, y, 0.0] for x in (0.0, 1.0)] for y in (0.0, 1.0, 2.0, 3.0)]
    res = {}
    msg = None
    try:
        res = run("procedural-modeling", "surface_tools.py", {"action": "continuity", "a_grid": a, "b_grid": b})
    except Exception as exc:
        msg = repr(exc)
    rec.check("D3 two-point seam reports G1 with G2 not measured instead of raising",
              msg is None and res.get("level") == "G1" and res["g2"]["ok"] is None and "not_measured" in res["g2"], msg or res)


# ---------------------------------------------------------------- D4

def test_d4(rec, scene, out_dir):
    a = bpy.data.scenes.new("__I13_D4_A")
    b = bpy.data.scenes.new("__I13_D4_B")
    for s in (a, b):
        s.render.resolution_x, s.render.resolution_y = 32, 24
    shared = bpy.data.node_groups.new("I13_Compositing", "CompositorNodeTree")
    a.compositing_node_group = shared
    b.compositing_node_group = shared
    in_scene(b, lambda: run("lowpoly-style", "ps1_look.py", {"objects": [], "snap": 0, "fog": False, "texture": False,
                                                              "resolution": [32, 24], "dither": True}))
    ours_a = [n.name for n in a.compositing_node_group.nodes if n.name.startswith("SK_PS1_")]
    rec.check("D4 scene A's compositor group is unchanged after PS1 on scene B", not ours_a and a.compositing_node_group is shared, ours_a)
    rec.check("D4 scene B got its own group with the dither", b.compositing_node_group is not shared
              and "SK_PS1_DitherPosterize" in b.compositing_node_group.nodes)


# ---------------------------------------------------------------- harness

def run_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rec = Recorder()
    scene = bpy.context.scene
    for name, fn in (("D1", test_d1), ("D2", test_d2), ("D3", test_d3), ("D4", test_d4)):
        rec.section(name, lambda r, fn=fn: fn(r, scene, out_dir))
    return rec.results


def main(out_dir=None):
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "blender-iter13-content")
    try:
        results = run_all(out_dir)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": traceback.format_exc()[-700:]}]
    failures = [r for r in results if not r["ok"]]
    report = {"blender": bpy.app.version_string,
              "summary": {"passed": len(results) - len(failures), "total": len(results), "failed": len(failures)},
              "passed": len(results) - len(failures), "total": len(results), "failed": len(failures),
              "failures": failures, "results": results}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "iter13_content_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("summary", "failures")}, indent=2))
    sys.exit(0 if not result["failures"] else 1)
