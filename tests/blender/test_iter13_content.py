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


def baked_normal(h, w, convention, seed=1, slope=0.8, invert_red=False, sigma=None):
    """RGB (h, w, 3) 0..1 8-bit-quantised tangent-space normal map of a smooth, periodic random height field."""
    rng = np.random.default_rng(seed)
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    sigma = sigma or max(3.0, min(h, w) / 40)
    k = np.exp(-(fx ** 2 + fy ** 2) * (2 * (np.pi * sigma) ** 2))
    hf = np.fft.ifft2(np.fft.fft2(rng.standard_normal((h, w))) * k).real
    gv, gu = np.gradient(hf)
    rms = np.sqrt((gu ** 2 + gv ** 2).mean()) + 1e-12
    n = np.stack([-gu / rms * slope, -gv / rms * slope, np.ones_like(gu)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    if convention == "DIRECTX":
        n[:, :, 1] *= -1
    if invert_red:
        n[:, :, 0] *= -1
    return np.round((n * 0.5 + 0.5) * 255) / 255


def save_normal(path, rgb):
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("tmp_nrm", w, h, alpha=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        px = np.ones((h, w, 4), dtype=np.float32)
        px[:, :, :3] = rgb
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def test_d1_content(rec, scene, out_dir):
    counter = [0]

    def go(rgb, normal_name="Mat_Normal.png", **extra):
        counter[0] += 1
        f = os.path.join(out_dir, f"d1c_{counter[0]}")
        os.makedirs(f, exist_ok=True)
        save_map(os.path.join(f, "Mat_BaseColor.png"), 0.5)
        save_normal(os.path.join(f, normal_name), rgb)
        r = run("texture-workflow", "import_painter_textures.py", {"folder": f, "material": f"MAT_I13C_{counter[0]}", **extra})
        r["flipped"] = "FLIP_G_Invert" in bpy.data.materials[r["material"]].node_tree.nodes
        return r

    # default mode (no argument, no name hint): never flips from content; DirectX-looking pixels only suggest
    for seed in (1, 2, 3):
        r = go(baked_normal(128, 128, "DIRECTX", seed))
        rec.check(f"D1c seed {seed} DirectX pixels, neutral name, no argument: NOT flipped, suggestion 'directx', warning",
                  not r["flipped"] and r["normal_convention"] == "OPENGL" and r["normal_convention_source"] == "default"
                  and r["normal_convention_suggestion"] == "directx" and any("look like DirectX" in w for w in r["warnings"]), r)
        r = go(baked_normal(128, 128, "OPENGL", seed))
        rec.check(f"D1c seed {seed} OpenGL pixels, neutral name: not flipped, no suggestion",
                  not r["flipped"] and r["normal_convention_suggestion"] is None and r["normal_convention_source"] == "default", r)
    # auto: the pixels decide, on several seeds and shapes (2048x64 and 64x2048 failed when the map was block-averaged first)
    for seed in (1, 2, 3):
        for conv in ("DIRECTX", "OPENGL"):
            r = go(baked_normal(128, 128, conv, seed), normal_convention="auto")
            rec.check(f"D1c auto seed {seed} {conv} pixels: {conv} from content",
                      r["normal_convention"] == conv and r["normal_convention_source"] == "content" and r["flipped"] == (conv == "DIRECTX"), r)
    for (h, w) in ((2048, 64), (64, 2048), (2048, 2048)):
        for conv in ("DIRECTX", "OPENGL"):
            r = go(baked_normal(h, w, conv, 5, slope=1.0), normal_convention="auto")
            sc = r["normal_convention_scores"]
            rec.check(f"D1c auto {h}x{w} {conv}: {conv} from content, ratio >= 4",
                      r["normal_convention"] == conv and r["normal_convention_source"] == "content" and sc["ratio"] >= 4, r)
    # fine detail (about 1 px features): averaging normals before the gradient flips the answer on such maps
    for (h, w) in ((2048, 64), (64, 2048), (2048, 2048)):
        for conv in ("DIRECTX", "OPENGL"):
            r = go(baked_normal(h, w, conv, 7, slope=0.5, sigma=1.0), normal_convention="auto")
            rec.check(f"D1c auto fine-detail {h}x{w} {conv}: {conv} from content (full-resolution measurement)",
                      r["normal_convention"] == conv and r["normal_convention_source"] == "content", r["normal_convention_scores"])
    r = go(baked_normal(128, 128, "OPENGL", 1), normal_convention="auto")
    sc = r["normal_convention_scores"]
    rec.check("D1c scores are reported, with the right convention clearly lower",
              sc["opengl_curl"] * 4 <= sc["directx_curl"], sc)
    # nothing to read: default everywhere, auto included
    flat = np.ones((64, 64, 3)) * np.array([0.5, 0.5, 1.0])
    for extra in ({}, {"normal_convention": "auto"}):
        r = go(flat, **extra)
        rec.check(f"D1c flat map {extra}: default OPENGL, no flip, no suggestion",
                  r["normal_convention_source"] == "default" and not r["flipped"] and r["normal_convention_suggestion"] is None, r)
    # pins the 4.0 margin: a correct-direction map whose ratio (3.5) is above the signal floor but below the margin
    weak = baked_normal(128, 128, "DIRECTX", 1, slope=0.03, sigma=5.0)
    r = go(weak, normal_convention="auto")
    sc = r["normal_convention_scores"]
    rec.check("D1c auto, ratio between 3 and 4 and above the signal floor: stays default",
              3.0 < sc["ratio"] < 4.0 and sc["opengl_curl"] > 0.004 and r["normal_convention_source"] == "default" and not r["flipped"], r)
    r = go(weak)
    rec.check("D1c ratio between 3 and 4, no argument: no suggestion",
              r["normal_convention_suggestion"] is None and not r["flipped"], r)
    r = go(baked_normal(128, 128, "DIRECTX", 1, slope=0.01), normal_convention="auto")
    rec.check("D1c auto, near-flat map: default rather than a guess", r["normal_convention_source"] == "default" and not r["flipped"], r)
    rng = np.random.default_rng(4)
    xy = rng.standard_normal((128, 128, 2)) * 0.15
    white = np.round((np.concatenate([xy, np.sqrt(1 - (xy ** 2).sum(-1, keepdims=True))], -1) * 0.5 + 0.5) * 255) / 255
    r = go(white, normal_convention="auto")
    rec.check("D1c auto, uncorrelated noise (scores about equal): default", r["normal_convention_source"] == "default" and not r["flipped"], r)
    mix = np.concatenate([baked_normal(64, 128, "OPENGL", 1), baked_normal(64, 128, "DIRECTX", 2)], axis=0)
    r = go(mix, normal_convention="auto")
    rec.check("D1c auto, half OpenGL half DirectX (below the margin): default", r["normal_convention_source"] == "default" and not r["flipped"], r)
    # an inverted red channel swaps the scores: default mode must not flip, auto may be wrong and says so
    inv = baked_normal(128, 128, "OPENGL", 1, invert_red=True)
    r = go(inv)
    rec.check("D1c OpenGL map with inverted red, no argument: not flipped (suggestion may be wrong, warning says so)",
              not r["flipped"] and any("inverted red" in w for w in r["warnings"]), r)
    r = go(inv, normal_convention="auto")
    rec.check("D1c auto on an inverted-red OpenGL map picks DIRECTX (known failure) and the warning says it can be wrong",
              r["normal_convention"] == "DIRECTX" and any("inverted" in w and "wrong" in w for w in r["warnings"]), r)
    # argument and file name still win over content
    dx = baked_normal(128, 128, "DIRECTX", 1)
    r = go(dx, normal_convention="OPENGL")
    rec.check("D1c explicit argument beats content: not flipped, source argument",
              r["normal_convention_source"] == "argument" and not r["flipped"] and r["normal_convention_scores"] is None, r)
    r = go(dx, "Mat_Normal_OpenGL.png", normal_convention="auto")
    rec.check("D1c file name beats auto and content (DirectX pixels named OpenGL): not flipped, source filename",
              r["normal_convention_source"] == "filename" and r["normal_convention"] == "OPENGL" and not r["flipped"], r)
    r = go(baked_normal(128, 128, "OPENGL", 1), "Mat_Normal_DirectX.png")
    rec.check("D1c file name beats content (OpenGL pixels named DirectX): flipped, source filename",
              r["normal_convention_source"] == "filename" and r["flipped"], r)


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
    for name, fn in (("D1", test_d1), ("D1c", test_d1_content), ("D2", test_d2), ("D3", test_d3), ("D4", test_d4)):
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
