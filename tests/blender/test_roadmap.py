"""Headless Blender tests for the iteration-12 roadmap scripts R1-R5.

R1 lowpoly-style/ps1_look.py          ordered dither, compared on real rendered pixels
R2 procedural-modeling/terrain_heightfield.py  seeded terrain + corridor along a curve
R3 rendering/render_preset.py         denoiser use-case presets and the prior values they return
R4 texture-workflow/import_painter_textures.py  synthetic maps wired by name (Painter itself is NOT tested)
R5 usd-pipeline/usd_roundtrip.py      export, reimport, compare, clean up
review-*  regressions for the round-1 review findings (rerun/cross-scene PS1, cyclic road, device restore, map names,
          shared images, render-level USD, negative USD fixtures)

Writes <out_dir>/roadmap_tests_report.json (summary passed/total/failed). Never saves the open file; the test scene,
objects and datablocks it makes are removed at the end. Use a NEW out_dir each run.

    blender -b --factory-startup --python tests/blender/test_roadmap.py -- '{"out_dir": "/tmp/roadmap-<new>"}'
"""
import json
import os
import runpy
import sys
import tempfile
import traceback

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))

COLLECTIONS = ("objects", "meshes", "materials", "images", "curves", "cameras", "lights", "node_groups",
               "collections", "worlds")
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])  # written out, not computed


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(skill, script, args):
    return runpy.run_path(os.path.join(SKILLS, skill, "scripts", script), init_globals={"ARGS": args},
                          run_name="__skill_test__")


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
        return bool(ok)

    def section(self, name, fn):
        try:
            fn(self)
        except Exception:
            self.results.append({"name": f"{name}: crashed", "ok": False, "detail": traceback.format_exc()[-700:]})


# ---------------------------------------------------------------- shared fixtures

def plane_with_texture(scene, name, pixels):
    """4 x 3 m plane facing +Z with UVs 0..1 and a Closest-filtered image texture; returns (object, image)."""
    h, w = pixels.shape[:2]
    img = bpy.data.images.new(f"{name}_img", w, h, alpha=False)
    img.colorspace_settings.name = "sRGB"
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = pixels
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-2, -1.5, 0), (2, -1.5, 0), (2, 1.5, 0), (-2, 1.5, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = co
    mat = bpy.data.materials.new(f"{name}_mat")
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation = img, "Closest"
    nt.nodes.active = tex
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    return obj, img


def set_texture_pixels(img, pixels):
    h, w = pixels.shape[:2]
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = pixels
    img.pixels.foreach_set(rgba.ravel())


def ortho_camera(scene):
    cam = bpy.data.objects.new("CAM_RT", bpy.data.cameras.new("CAM_RT"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 4.0
    cam.location = (0, 0, 5)
    scene.collection.objects.link(cam)
    scene.camera = cam


def workbench_flat(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light, sh.color_type, sh.show_cavity, sh.show_object_outline = "FLAT", "TEXTURE", False, False
    scene.display.render_aa = "OFF"
    scene.render.film_transparent = False


def render_pixels(scene, path):
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    bpy.ops.render.render(write_still=True, scene=scene.name)
    img = bpy.data.images.load(path)
    try:
        img.colorspace_settings.name = "Non-Color"  # raw 8-bit values / 255
        w, h = img.size
        arr = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, :3]
    finally:
        bpy.data.images.remove(img)
    return arr


# ---------------------------------------------------------------- R1

def test_r1(rec, scene, out_dir):
    W, H = 320, 240
    gx = np.linspace(0.0, 1.0, W, dtype=np.float32)
    grad = np.repeat(gx[None, :, None], H, axis=0).repeat(3, axis=2)
    obj, img = plane_with_texture(scene, "RT_DitherPlane", np.round(grad * 255) / 255)
    ortho_camera(scene)
    workbench_flat(scene)
    base = {"objects": [], "snap": 0, "fog": False, "texture": False, "resolution": [W, H]}

    res_off = run("lowpoly-style", "ps1_look.py", {**base, "dither": False})["result"]
    rec.check("R1 dither off: no dither stage", res_off["dither"] is None)
    plain = render_pixels(scene, os.path.join(out_dir, "r1_plain.png"))
    uniq_plain = len(np.unique(np.round(plain[:, :, 0] * 255)))
    rec.check("R1 baseline gradient has many levels", uniq_plain > 150, uniq_plain)

    levels = 8
    steps = levels - 1
    res = run("lowpoly-style", "ps1_look.py", {**base, "dither": True, "color_levels": levels, "dither_size": 4})["result"]
    rec.check("R1 result reports the dither", bool(res["dither"]) and res["dither"]["levels"] == levels, res["dither"])
    rec.check("R1 hint no longer sends the user to comp_grade for dithering",
              "comp_grade does not dither" in res["hint"], res["hint"][:80])
    rec.check("R1 render dither_intensity zeroed", scene.render.dither_intensity == 0.0, scene.render.dither_intensity)
    dith = render_pixels(scene, os.path.join(out_dir, "r1_dither.png"))
    vals = np.unique(np.round(dith * 255))
    rec.check("R1 dithered gradient has at most `levels` values per channel", len(vals) <= levels, len(vals))
    rec.check("R1 dithered gradient uses the levels (not collapsed)", len(vals) >= levels - 1, len(vals))
    expect_levels = np.round(np.arange(levels) / steps * 255)
    rec.check("R1 values sit on the k/(levels-1) grid",
              bool(np.isin(vals, expect_levels).all()), sorted(set(vals) - set(expect_levels)))
    ys, xs = np.mgrid[0:H, 0:W]
    t = (BAYER4[ys % 4, xs % 4] + 0.5) / 16.0  # row 0 = bottom, like image.pixels
    expected = np.floor(plain[:, :, 0] * steps + t) / steps
    got = dith[:, :, 0]
    exact = float((np.abs(got - expected) < 0.5 / 255).mean())
    worst = float(np.abs(got - expected).max())
    rec.check("R1 gradient pixels match an independent numpy Bayer dither (>= 99% exact)", exact >= 0.99, f"exact={exact:.4f}")
    rec.check("R1 no pixel is more than one level from the expectation", worst <= 1.0 / steps + 2.0 / 255, worst)
    rec.check("R1 channels agree (grey in, grey out)", bool(np.allclose(dith[:, :, 0], dith[:, :, 1])
                                                            and np.allclose(dith[:, :, 1], dith[:, :, 2])))

    # Flat grey between two levels: the exact Bayer pattern must come out, pixel for pixel.
    flat = np.full((H, W, 3), 118 / 255.0, dtype=np.float32)
    set_texture_pixels(img, flat)
    flat_out = render_pixels(scene, os.path.join(out_dir, "r1_flat.png"))[:, :, 0]
    frac = 118 / 255.0 * steps - np.floor(118 / 255.0 * steps)
    want_upper = (BAYER4[ys % 4, xs % 4] + 0.5) / 16.0 >= 1.0 - frac
    lo, hi = np.floor(118 / 255.0 * steps) / steps, np.ceil(118 / 255.0 * steps) / steps
    got_upper = flat_out > (lo + hi) / 2
    rec.check("R1 flat grey: two values only", len(np.unique(np.round(flat_out * 255))) == 2,
              np.unique(np.round(flat_out * 255)))
    rec.check("R1 flat grey: upper-level pixels follow the 4x4 Bayer matrix exactly", bool((got_upper == want_upper).all()),
              f"mismatch={int((got_upper != want_upper).sum())}")
    rec.check("R1 flat grey: pattern repeats with period 4",
              bool((got_upper[:, :-4] == got_upper[:, 4:]).all() and (got_upper[:-4] == got_upper[4:]).all()))

    # Re-run is idempotent and arguments are checked.
    run("lowpoly-style", "ps1_look.py", {**base, "dither": True, "color_levels": levels})
    n = len([x for x in scene.compositing_node_group.nodes if x.name.startswith("SK_PS1_Dither")])
    rec.check("R1 rerun does not stack dither nodes", n == 5, n)
    rec.check("R1 color_levels < 3 refused", raises(lambda: run("lowpoly-style", "ps1_look.py", {**base, "color_levels": 2})))
    rec.check("R1 dither_size 3 refused", raises(lambda: run("lowpoly-style", "ps1_look.py", {**base, "dither_size": 3})))


# ---------------------------------------------------------------- R2

def mesh_coords(obj):
    return np.array([(obj.matrix_world @ v.co)[:] for v in obj.data.vertices], dtype=np.float64)


def test_r2(rec, scene, out_dir):
    before = {o.name for o in bpy.data.objects}
    args = {"size": 40, "resolution": 41, "seed": 7, "height": 4, "frequency": 0.08}
    a = run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrA"})["result"]
    b = run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrB"})["result"]
    c = run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrC", "seed": 8})["result"]
    ca, cb, cc = (mesh_coords(bpy.data.objects[n]) for n in ("RT_TerrA", "RT_TerrB", "RT_TerrC"))
    rec.check("R2 grid size", a["vertices"] == 41 * 41 and a["faces"] == 40 * 40, a["vertices"])
    rec.check("R2 same seed gives the same mesh", bool(np.array_equal(ca, cb)))
    rec.check("R2 different seed gives a different mesh", not np.allclose(ca[:, 2], cc[:, 2]))
    rec.check("R2 terrain has relief within the amplitude scale", 0.5 < np.ptp(ca[:, 2]) < 8 * 4, np.ptp(ca[:, 2]))
    rec.check("R2 only the new objects were added",
              {o.name for o in bpy.data.objects} - before == {"RT_TerrA", "RT_TerrB", "RT_TerrC"})
    rec.check("R2 existing name refused", raises(lambda: run("procedural-modeling", "terrain_heightfield.py",
                                                            {**args, "name": "RT_TerrA"})))
    run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrA", "seed": 8, "replace": True})
    rec.check("R2 replace swaps the mesh in place", np.array_equal(mesh_coords(bpy.data.objects["RT_TerrA"]), cc))

    # Corridor along a straight, sloping poly curve: z must be 2 + x/10 on the bed.
    cu = bpy.data.curves.new("CRV_RT", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    sp.points[0].co = (-10, 0, 1, 1)
    sp.points[1].co = (10, 0, 3, 1)
    crv = bpy.data.objects.new("CRV_RT", cu)
    scene.collection.objects.link(crv)
    half, fall = 3.0, 5.0
    r = run("procedural-modeling", "terrain_heightfield.py",
            {**args, "name": "RT_TerrRoad", "corridor": {"curve": "CRV_RT", "half_width": half, "falloff": fall}})["result"]
    road = mesh_coords(bpy.data.objects["RT_TerrRoad"])
    x, y, z = road[:, 0], road[:, 1], road[:, 2]
    bed = (np.abs(y) <= half) & (np.abs(x) <= 10)
    rec.check("R2 corridor reports flat vertices", r["corridor"] and r["corridor"]["flat_vertices"] > 20,
              r["corridor"])
    err = float(np.abs(z[bed] - (2 + x[bed] / 10)).max()) if bed.any() else 99
    rec.check("R2 corridor height equals the curve height (<= 1 mm)", bed.sum() > 20 and err < 1e-3, f"n={bed.sum()} err={err}")
    far = np.abs(y) > half + fall
    rec.check("R2 outside corridor + falloff the terrain is the untouched noise", bool(np.allclose(z[far], cb[far, 2], atol=1e-6)))
    rec.check("R2 the corridor really changed the terrain", float(np.abs(z[bed] - cb[bed, 2]).max()) > 0.05)
    rec.check("R2 bad curve refused", raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {
        **args, "name": "RT_TerrBad", "corridor": {"curve": "nope"}})))
    rec.check("R2 refused call left no object", "RT_TerrBad" not in bpy.data.objects)


# ---------------------------------------------------------------- R3

DEN_KEYS = ["use_denoising", "denoiser", "denoising_input_passes", "denoising_prefilter", "denoising_quality",
            "denoising_use_gpu", "use_preview_denoising", "preview_denoiser", "preview_denoising_input_passes",
            "preview_denoising_prefilter", "preview_denoising_quality", "preview_denoising_start_sample",
            "samples", "adaptive_threshold", "use_animated_seed"]


def test_r3(rec, scene, out_dir):
    cy = scene.cycles

    def snap():
        return {k: getattr(cy, k) for k in DEN_KEYS}
    probe = run("rendering", "render_preset.py", {"preset": "eevee_preview"})
    presets = probe["PRESETS"]
    new = [p for p in presets if p.startswith("denoise_")]
    rec.check("R3 five denoise presets exist", len(new) == 5, new)
    order = ["cycles_final", "denoise_draft", "denoise_final_still", "denoise_animation", "denoise_viewport",
             "denoise_off", "cycles_preview", "denoise_final_still", "denoise_draft"]
    for name in order:
        before = snap()
        res = run("rendering", "render_preset.py", {"preset": name})["result"]
        after = snap()
        cfg = presets[name]["cycles"] if "cycles" in presets[name] else {}
        rec.check(f"R3 {name}: nothing skipped (all properties real)", res["skipped"] == [], res["skipped"])
        wrong = {k: (getattr(cy, k), v) for k, v in cfg.items()
                 if not (abs(getattr(cy, k) - v) < 1e-6 if isinstance(v, float) else getattr(cy, k) == v)}
        rec.check(f"R3 {name}: every property holds the preset value", not wrong, wrong)
        changed = [k for k in DEN_KEYS if before[k] != after[k]]
        missing = [k for k in changed if f"cycles.{k}" not in res["previous"]]
        rec.check(f"R3 {name}: previous lists every denoise property that changed", not missing, f"changed={changed} missing={missing}")
        bad = {k: (res["previous"].get(f"cycles.{k}"), before[k]) for k in changed
               if res["previous"].get(f"cycles.{k}") != before[k]}
        rec.check(f"R3 {name}: prior values are the real prior values", not bad, bad)
    # Revert from `previous` alone puts the denoiser state back.
    state0 = snap()
    res = run("rendering", "render_preset.py", {"preset": "denoise_animation"})["result"]
    for key, value in res["previous"].items():
        group, _, prop = key.partition(".")
        if group == "cycles":
            setattr(cy, prop, value)
    rec.check("R3 reverting with `previous` restores the denoiser state", snap() == state0, {k: (snap()[k], state0[k]) for k in DEN_KEYS if snap()[k] != state0[k]})
    rec.check("R3 existing keys kept in previous", {"engine", "resolution_percentage", "view_transform", "look"} <= set(res["previous"]))
    rec.check("R3 unknown preset refused", raises(lambda: run("rendering", "render_preset.py", {"preset": "denoise_nope"})))


# ---------------------------------------------------------------- R4

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


def linked(sock):
    return sock.links[0].from_node if sock.is_linked else None


def test_r4(rec, scene, out_dir):
    folder = os.path.join(out_dir, "r4_maps")
    os.makedirs(folder, exist_ok=True)
    for stem in ("BaseColor", "Roughness", "Metallic", "Normal", "Height", "Emissive", "Opacity", "AmbientOcclusion",
                 "Mystery", "BaseColor.1001"):
        save_map(os.path.join(folder, f"Crate_{stem}.png"), 0.5)
    save_map(os.path.join(folder, "Other_BaseColor.png"), 0.5)
    open(os.path.join(folder, "notes.txt"), "w").write("not an image")
    cube = bpy.data.objects.new("RT_Cube", bpy.data.meshes.new("RT_Cube"))
    scene.collection.objects.link(cube)
    r = run("texture-workflow", "import_painter_textures.py",
            {"folder": folder, "texture_set": "Crate", "material": "MAT_RT_Crate", "assign_to": ["RT_Cube"]})["result"]
    mat = bpy.data.materials["MAT_RT_Crate"]
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")

    def img_of(socket_name):
        node = linked(bsdf.inputs[socket_name])
        return node.image if node and node.bl_idname == "ShaderNodeTexImage" else None
    bc, ro, me = img_of("Base Color"), img_of("Roughness"), img_of("Metallic")
    em, al = img_of("Emission Color"), img_of("Alpha")
    rec.check("R4 base colour wired from the BaseColor file", bc is not None and bc.filepath.endswith("Crate_BaseColor.png"),
              bc and bc.filepath)
    rec.check("R4 roughness wired from the Roughness file", ro is not None and ro.filepath.endswith("Crate_Roughness.png"))
    rec.check("R4 metallic wired from the Metallic file", me is not None and me.filepath.endswith("Crate_Metallic.png"))
    rec.check("R4 emissive and opacity wired", em is not None and al is not None and em.filepath.endswith("Emissive.png")
              and al.filepath.endswith("Opacity.png"))
    rec.check("R4 colour maps are sRGB", bc.colorspace_settings.name == "sRGB" and em.colorspace_settings.name == "sRGB",
              (bc.colorspace_settings.name, em.colorspace_settings.name))
    rec.check("R4 data maps are Non-Color",
              all(i.colorspace_settings.name == "Non-Color" for i in (ro, me, al)),
              [i.colorspace_settings.name for i in (ro, me, al)])
    bump = linked(bsdf.inputs["Normal"])
    nmap = linked(bump.inputs["Normal"]) if bump and bump.bl_idname == "ShaderNodeBump" else None
    nimg = linked(nmap.inputs["Color"]) if nmap and nmap.bl_idname == "ShaderNodeNormalMap" else None
    himg = linked(bump.inputs["Height"]) if bump else None
    rec.check("R4 normal: texture -> Normal Map -> Bump -> BSDF", nimg is not None and nimg.image.filepath.endswith("Normal.png"))
    rec.check("R4 normal and height images are Non-Color",
              nimg is not None and himg is not None and nimg.image.colorspace_settings.name == "Non-Color"
              and himg.image.colorspace_settings.name == "Non-Color")
    rec.check("R4 AO not wired by default", not any(n.bl_idname == "ShaderNodeMix" for n in mat.node_tree.nodes))
    rec.check("R4 unmatched and UDIM files reported",
              "Crate_Mystery.png" in r["unmatched"] and "Crate_BaseColor.1001.png" in r["skipped_udim"], (r["unmatched"], r["skipped_udim"]))
    rec.check("R4 other texture set and non-images ignored",
              not any("Other" in v for v in r["files"].values()) and "notes.txt" not in r["unmatched"])
    rec.check("R4 material assigned", [s.material.name for s in cube.material_slots] == ["MAT_RT_Crate"])
    rec.check("R4 existing material refused", raises(lambda: run("texture-workflow", "import_painter_textures.py", {
        "folder": folder, "texture_set": "Crate", "material": "MAT_RT_Crate"})))
    rec.check("R4 missing folder refused", raises(lambda: run("texture-workflow", "import_painter_textures.py", {
        "folder": os.path.join(out_dir, "nope")})))

    # DirectX normals get a green flip between the texture and the Normal Map node.
    run("texture-workflow", "import_painter_textures.py", {
        "folder": folder, "texture_set": "Crate", "material": "MAT_RT_DX", "normal_convention": "DIRECTX"})
    dx = bpy.data.materials["MAT_RT_DX"].node_tree
    nm = next(n for n in dx.nodes if n.bl_idname == "ShaderNodeNormalMap")
    comb = linked(nm.inputs["Color"])
    inv = linked(comb.inputs["Green"]) if comb else None
    sep = linked(inv.inputs[1]) if inv else None
    tex = linked(sep.inputs["Color"]) if sep else None
    rec.check("R4 DirectX: texture -> split -> 1-G -> combine -> Normal Map",
              bool(comb and inv and inv.operation == "SUBTRACT" and tex and tex.image.filepath.endswith("Normal.png")))
    ok_default = not any(n.name.startswith("FLIP_G") for n in mat.node_tree.nodes)
    rec.check("R4 OpenGL default has no flip", ok_default)

    # Packed ORM.
    orm = os.path.join(out_dir, "r4_orm")
    os.makedirs(orm, exist_ok=True)
    save_map(os.path.join(orm, "Rock_BaseColor.png"), 0.4)
    save_map(os.path.join(orm, "Rock_OcclusionRoughnessMetallic.png"), 0.3)
    run("texture-workflow", "import_painter_textures.py", {"folder": orm, "material": "MAT_RT_ORM"})
    on = bpy.data.materials["MAT_RT_ORM"].node_tree
    ob = next(n for n in on.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    rs, ms = linked(ob.inputs["Roughness"]), linked(ob.inputs["Metallic"])
    rec.check("R4 ORM: G -> Roughness, B -> Metallic from one Non-Color image",
              bool(rs and ms and rs.name == ms.name and rs.bl_idname == "ShaderNodeSeparateColor"
                   and ob.inputs["Roughness"].links[0].from_socket.name == "Green"
                   and ob.inputs["Metallic"].links[0].from_socket.name == "Blue"
                   and linked(rs.inputs["Color"]).image.colorspace_settings.name == "Non-Color"))


# ---------------------------------------------------------------- R5

def test_r5(rec, scene, out_dir):
    def mat(name, rgb):
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*rgb, 1.0)
        return m

    def mesh_obj(name, build, loc, mats=()):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        build(bm)
        bm.to_mesh(me)
        bm.free()
        for m in mats:
            me.materials.append(m)
        o = bpy.data.objects.new(name, me)
        scene.collection.objects.link(o)
        o.location = loc
        return o
    red, blue, green = mat("RT_Red", (1, 0, 0)), mat("RT_Blue", (0, 0, 1)), mat("RT_Green", (0, 1, 0))
    cube = mesh_obj("RT_USD_Cube", lambda bm: bmesh.ops.create_cube(bm, size=1.0), (1, 2, 0.5), [red])
    cube.rotation_euler = (0.1, 0.2, 0.3)
    cube.scale = (1.0, 2.0, 0.5)
    sph = mesh_obj("RT_USD_Sphere", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.4),
                   (-2, 0, 1), [blue, green])
    for i, p in enumerate(sph.data.polygons):
        p.material_index = i % 2
    child = mesh_obj("RT_USD_Child", lambda bm: bmesh.ops.create_cube(bm, size=0.3), (0.0, 0.0, 1.0), [green])
    child.parent = cube
    sub = mesh_obj("RT_USD_Sub", lambda bm: bmesh.ops.create_cube(bm, size=1.0), (4, 0, 0.5), [red])
    sub.modifiers.new("Subsurf", "SUBSURF").levels = 1
    sub.modifiers[0].render_levels = 1
    bpy.context.view_layer.update()
    names = ["RT_USD_Cube", "RT_USD_Sphere", "RT_USD_Child", "RT_USD_Sub"]
    snapshot = {c: sorted(i.name for i in getattr(bpy.data, c)) for c in ("objects", "meshes", "materials")}
    matrices = {n: [list(r) for r in bpy.data.objects[n].matrix_world] for n in names}
    path = os.path.join(out_dir, "r5", "roundtrip.usdc")
    r = run("usd-pipeline", "usd_roundtrip.py", {"objects": names, "out_path": path})["result"]
    rec.check("R5 round trip ok", r["ok"], r["problems"])
    rec.check("R5 file written", os.path.isfile(path) and r["bytes"] > 0, r["bytes"])
    rec.check("R5 all four objects found after import", all(r["per_object"][n]["found"] for n in names), r["per_object"])
    rec.check("R5 transforms match", all(v["matrix_max_diff"] < 1e-4 for v in r["per_object"].values()),
              {k: v["matrix_max_diff"] for k, v in r["per_object"].items()})
    sub_counts = r["per_object"]["RT_USD_Sub"]
    rec.check("R5 modifier result exported (evaluated verts/faces match, more than the base cube)",
              sub_counts["verts"][0] == sub_counts["verts"][1] and sub_counts["verts"][0] > 8, sub_counts["verts"])
    rec.check("R5 material names survive (two-material sphere)",
              r["per_object"]["RT_USD_Sphere"]["materials"][1] == ["RT_Blue", "RT_Green"],
              r["per_object"]["RT_USD_Sphere"]["materials"])
    after = {c: sorted(i.name for i in getattr(bpy.data, c)) for c in ("objects", "meshes", "materials")}
    rec.check("R5 scene datablocks unchanged after the check", after == snapshot,
              {c: set(after[c]) ^ set(snapshot[c]) for c in snapshot if after[c] != snapshot[c]})
    rec.check("R5 original transforms untouched",
              all(np.allclose(np.array([list(r_) for r_ in bpy.data.objects[n].matrix_world]), np.array(matrices[n]))
                  for n in names))
    rec.check("R5 bad extension refused", raises(lambda: run("usd-pipeline", "usd_roundtrip.py", {
        "objects": names, "out_path": os.path.join(out_dir, "x.fbx")})))
    rec.check("R5 missing object refused", raises(lambda: run("usd-pipeline", "usd_roundtrip.py", {
        "objects": ["nope"], "out_path": os.path.join(out_dir, "x.usdc")})))


# ---------------------------------------------------------------- review findings (round 1)
# Each check below reproduces one verified review finding; it must fail on the unfixed scripts.

def in_scene(scene, fn):
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        return fn()


def upstream_names(tree):
    """Names of every node that feeds the group output, found by walking links backwards."""
    out = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")
    seen, todo = set(), [out]
    while todo:
        node = todo.pop()
        for sock in node.inputs:
            for lk in sock.links:
                if lk.from_node.name not in seen:
                    seen.add(lk.from_node.name)
                    todo.append(lk.from_node)
    return seen


def test_review_r1(rec, scene, out_dir):
    base = {"objects": [], "snap": 0, "fog": False, "texture": False, "resolution": [64, 48]}
    sc = bpy.data.scenes.new("__RT_R1_rerun")
    sc.render.resolution_x, sc.render.resolution_y = 64, 48
    in_scene(sc, lambda: run("compositing", "comp_grade.py", {"preset": "noir"}))
    tree = sc.compositing_node_group
    grade = {n.name for n in tree.nodes if n.name.startswith("SK_") and n.bl_idname != "NodeGroupOutput"}
    rec.check("R1-review fixture: comp_grade made grade nodes", len(grade) > 0, sorted(grade))
    for i in (1, 2, 3):
        in_scene(sc, lambda: run("lowpoly-style", "ps1_look.py", base))
        up = upstream_names(sc.compositing_node_group)
        missing = sorted(grade - up)
        rec.check(f"R1-review: comp_grade -> PS1 run {i}: every grade node still feeds the output", not missing, missing)
        rec.check(f"R1-review: PS1 run {i}: dither stage still feeds the output", "SK_PS1_DitherPosterize" in up, sorted(up))

    a = bpy.data.scenes.new("__RT_R1_A")
    b = bpy.data.scenes.new("__RT_R1_B")
    for s in (a, b):
        s.render.resolution_x, s.render.resolution_y = 32, 24
    in_scene(a, lambda: run("lowpoly-style", "ps1_look.py", {**base, "resolution": [32, 24]}))
    node_a = a.compositing_node_group.nodes["SK_PS1_DitherThreshold"]
    img_a = node_a.image
    keep_name = img_a.name if img_a else None
    in_scene(b, lambda: run("lowpoly-style", "ps1_look.py", {**base, "resolution": [32, 24]}))
    node_a = a.compositing_node_group.nodes["SK_PS1_DitherThreshold"]
    rec.check("R1-review: applying PS1 in scene B leaves scene A's threshold image in use",
              node_a.image is not None and keep_name in bpy.data.images and node_a.image.size[0] == 32, keep_name)
    node_b = b.compositing_node_group.nodes["SK_PS1_DitherThreshold"]
    rec.check("R1-review: scene B has its own threshold image", node_b.image is not None and node_b.image != node_a.image)


def test_review_r2(rec, scene, out_dir):
    cu = bpy.data.curves.new("CRV_RT_LOOP", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(3)
    for p, co in zip(sp.points, [(-10, -10, 1, 1), (10, -10, 1, 1), (10, 10, 3, 1), (-10, 10, 3, 1)]):
        p.co = co
    sp.use_cyclic_u = True
    scene.collection.objects.link(bpy.data.objects.new("CRV_RT_LOOP", cu))
    args = {"size": 40, "resolution": 81, "seed": 7, "height": 4, "frequency": 0.08}
    run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrLoopFree"})
    noise_z = mesh_coords(bpy.data.objects["RT_TerrLoopFree"])[:, 2]
    r = run("procedural-modeling", "terrain_heightfield.py",
            {**args, "name": "RT_TerrLoop", "corridor": {"curve": "CRV_RT_LOOP", "half_width": 1.5, "falloff": 1.0}})["result"]
    co = mesh_coords(bpy.data.objects["RT_TerrLoop"])
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    rec.check("R2-review: cyclic curve has four segments", r["corridor"]["curve_points"] == 5, r["corridor"])
    # The closing edge runs (-10, 10, 3) -> (-10, -10, 1): z = 2 + y / 10 on x = -10.
    bed = (np.abs(x + 10) <= 1.5) & (np.abs(y) <= 8)
    err = float(np.abs(z[bed] - (2 + y[bed] / 10)).max()) if bed.any() else 99
    rec.check("R2-review: the closing segment of a cyclic curve is flattened to the curve height (<= 1 mm)",
              bed.sum() > 10 and err < 1e-3, f"n={bed.sum()} err={err}")
    rec.check("R2-review: the closing segment really changed the noise",
              float(np.abs(z[bed] - noise_z[bed]).max()) > 0.05)


def test_review_r3(rec, scene, out_dir):
    cy = scene.cycles
    cy.device = "CPU"
    res = run("rendering", "render_preset.py", {"preset": "cycles_final", "device": "GPU"})["result"]
    rec.check("R3-review: device argument records the prior device in `previous`",
              res["previous"].get("cycles.device") == "CPU", res["previous"].get("cycles.device"))
    for key, value in res["previous"].items():
        group, _, prop = key.partition(".")
        if group == "cycles":
            setattr(cy, prop, value)
    rec.check("R3-review: reverting from `previous` restores the device", cy.device == "CPU", cy.device)


def test_review_r4(rec, scene, out_dir):
    folder = os.path.join(out_dir, "r4_review")
    os.makedirs(folder, exist_ok=True)
    # Name meaning: "Metal" in the asset name must not turn a normal map into a metallic map.
    for stem in ("BaseColor", "Normal", "Roughness"):
        save_map(os.path.join(folder, f"MetalDoor_{stem}.png"), 0.5)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": folder, "material": "MAT_RT_MetalDoor"})["result"]
    rec.check("R4-review: MetalDoor_Normal is classified as normal", r["files"].get("normal") == "MetalDoor_Normal.png", r["files"])
    mat = bpy.data.materials["MAT_RT_MetalDoor"]
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    rec.check("R4-review: nothing wired into Metallic from the normal map", not bsdf.inputs["Metallic"].is_linked)
    rec.check("R4-review: normal map reaches the BSDF Normal input", bsdf.inputs["Normal"].is_linked)

    # Shared image: loading a map already used by another material must not change that material's colour space.
    shared = os.path.join(out_dir, "r4_review_shared")
    os.makedirs(shared, exist_ok=True)
    save_map(os.path.join(shared, "Wall_Roughness.png"), 0.5)
    existing = bpy.data.images.load(os.path.join(shared, "Wall_Roughness.png"))
    existing.colorspace_settings.name = "sRGB"
    old_mat = bpy.data.materials.new("MAT_RT_OldWall")
    old_mat.use_nodes = True
    tex = old_mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = existing
    run("texture-workflow", "import_painter_textures.py", {"folder": shared, "material": "MAT_RT_NewWall"})
    rec.check("R4-review: an image already used elsewhere keeps its colour space", existing.colorspace_settings.name == "sRGB",
              existing.colorspace_settings.name)
    new_tex = next(n for n in bpy.data.materials["MAT_RT_NewWall"].node_tree.nodes if n.bl_idname == "ShaderNodeTexImage")
    rec.check("R4-review: the new material's roughness image is Non-Color",
              new_tex.image.colorspace_settings.name == "Non-Color", new_tex.image.colorspace_settings.name)


def test_review_r5(rec, scene, out_dir):
    def cube(name, loc, subsurf=None):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        scene.collection.objects.link(o)
        o.location = loc
        if subsurf:
            mod = o.modifiers.new("Subsurf", "SUBSURF")
            mod.levels, mod.render_levels = subsurf
        return o
    # Viewport level 1, render level 2: the export is the render result and the comparison must measure the same.
    cube("RT_USD_Lvl", (0, 0, 0), subsurf=(1, 2))
    bpy.context.view_layer.update()
    r = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Lvl"],
                                                  "out_path": os.path.join(out_dir, "r5_levels", "lvl.usdc")})["result"]
    rec.check("R5-review: viewport 1 / render 2 subdivision round-trips ok", r["ok"], r["problems"])
    rec.check("R5-review: compared counts are the render-level result (98 vertices)",
              r["per_object"]["RT_USD_Lvl"]["verts"] == [98, 98], r["per_object"]["RT_USD_Lvl"]["verts"])
    mod = bpy.data.objects["RT_USD_Lvl"].modifiers["Subsurf"]
    rec.check("R5-review: modifier levels restored after the check", (mod.levels, mod.render_levels) == (1, 2),
              (mod.levels, mod.render_levels))

    # Negative fixtures: a lossy round trip must be rejected, never reported ok.
    objects_before = {o.name for o in bpy.data.objects}
    cube("RT_USD_Lossy", (3, 0, 0), subsurf=(2, 2))
    objects_before.add("RT_USD_Lossy")
    bpy.context.view_layer.update()
    bad = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Lossy"], "subdivision": "BEST_MATCH",
                                                    "out_path": os.path.join(out_dir, "r5_lossy", "lossy.usdc")})["result"]
    rec.check("R5 negative: subdivision written as a scheme (cage only on import) is rejected", not bad["ok"], bad["problems"])
    rec.check("R5 negative: the rejection names the vertex/face difference",
              any("verts/faces" in p for p in bad["problems"]), bad["problems"])
    strict = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Lvl"], "tol": -1.0,
                                                       "out_path": os.path.join(out_dir, "r5_lossy", "strict.usdc")})["result"]
    rec.check("R5 negative: an impossible transform tolerance rejects the round trip",
              not strict["ok"] and any("transform differs" in p for p in strict["problems"]), strict["problems"])
    rec.check("R5 negative: a rejected round trip still removes the imported copy from the scene",
              {o.name for o in bpy.data.objects} == objects_before, sorted({o.name for o in bpy.data.objects} ^ objects_before))


# ---------------------------------------------------------------- review findings (round 2)

def test_review2(rec, scene, out_dir):
    # R4: the compound packed-ORM spelling used by many exporters must not be read as plain roughness.
    orm = os.path.join(out_dir, "r4_orm_compound")
    os.makedirs(orm, exist_ok=True)
    save_map(os.path.join(orm, "Rock_BaseColor.png"), 0.4)
    save_map(os.path.join(orm, "Rock_occlusion_roughness_metallic.png"), 0.3)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": orm, "material": "MAT_RT_ORM2"})["result"]
    rec.check("R4-review2: Rock_occlusion_roughness_metallic.png is classified as orm", r["files"].get("orm") ==
              "Rock_occlusion_roughness_metallic.png", r["files"])
    nt = bpy.data.materials["MAT_RT_ORM2"].node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    rec.check("R4-review2: compound ORM feeds Roughness from G and Metallic from B",
              bsdf.inputs["Metallic"].is_linked and bsdf.inputs["Roughness"].is_linked
              and bsdf.inputs["Roughness"].links[0].from_socket.name == "Green"
              and bsdf.inputs["Metallic"].links[0].from_socket.name == "Blue")

    # R1: switching dither off on a scene that already has it must remove the stage.
    sc = bpy.data.scenes.new("__RT_R1_off")
    sc.render.resolution_x, sc.render.resolution_y = 64, 48
    base = {"objects": [], "snap": 0, "fog": False, "texture": False, "resolution": [64, 48]}
    in_scene(sc, lambda: run("lowpoly-style", "ps1_look.py", {**base, "dither": True}))
    rec.check("R1-review2 fixture: dither installed",
              "SK_PS1_DitherPosterize" in upstream_names(sc.compositing_node_group))
    res = in_scene(sc, lambda: run("lowpoly-style", "ps1_look.py", {**base, "dither": False}))["result"]
    tree = sc.compositing_node_group
    left = sorted(n.name for n in tree.nodes if n.name.startswith("SK_PS1_"))
    rec.check("R1-review2: dither=False on a dithered scene removes the SK_PS1_ nodes", not left, left)
    rec.check("R1-review2: dither=False on a dithered scene leaves nothing dithering the output",
              not any(n.startswith("SK_PS1_") for n in upstream_names(tree)), sorted(upstream_names(tree)))
    rec.check("R1-review2: result reports no dither", res["dither"] is None)

    def cube(name, loc, mat):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me)
        scene.collection.objects.link(o)
        o.location = loc
        return o

    # R5: a normally suffixed material name (Material.001) must round-trip.
    bpy.data.materials.new("RT_Suf")
    suf = bpy.data.materials.new("RT_Suf")
    rec.check("R5-review2 fixture: material really is named with a numeric suffix", suf.name == "RT_Suf.001", suf.name)
    cube("RT_USD_Suf", (0, 0, 0), suf)
    bpy.context.view_layer.update()
    rs = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Suf"],
                                                  "out_path": os.path.join(out_dir, "r5_suffix", "suf.usdc")})["result"]
    rec.check("R5-review2: material named RT_Suf.001 round-trips ok", rs["ok"], rs["problems"])

    # R5: a REAL transform change (not tol=-1): every object that appears during the import is moved 0.5 on X.
    cube("RT_USD_Move", (2, 0, 0), bpy.data.materials.new("RT_Mv"))
    bpy.context.view_layer.update()
    known = {o.name for o in bpy.data.objects}
    busy = []

    def shift(*_):
        if busy:
            return
        busy.append(1)
        try:
            for o in bpy.data.objects:
                if o.name not in known and not o.get("rt_shifted"):
                    o["rt_shifted"] = 1
                    o.location.x += 0.5
        finally:
            busy.clear()
    clean = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Move"],
                                                     "out_path": os.path.join(out_dir, "r5_move", "clean.usdc")})["result"]
    rec.check("R5 negative: without the mover the same object round-trips ok at default tolerance",
              clean["ok"], clean["problems"])
    bpy.app.handlers.depsgraph_update_post.append(shift)
    try:
        tolerant = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Move"], "tol": 10.0,
                                                            "out_path": os.path.join(out_dir, "r5_move", "tolerant.usdc")})["result"]
        bad = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_Move"],
                                                       "out_path": os.path.join(out_dir, "r5_move", "move.usdc")})["result"]
    finally:
        bpy.app.handlers.depsgraph_update_post.remove(shift)
    diff = bad["per_object"].get("RT_USD_Move", {}).get("matrix_max_diff")
    rec.check("R5 negative: a genuinely moved import is measured as a ~0.5 transform difference (not tol=-1)",
              diff is not None and abs(diff - 0.5) < 1e-3, diff)
    rec.check("R5 negative: default tolerance rejects the genuinely moved import",
              not bad["ok"] and any("transform differs" in p for p in bad["problems"]), bad["problems"])
    rec.check("R5 negative: the same moved import passes under a tolerance above the shift (tolerance, not identity)",
              tolerant["ok"], tolerant["problems"])


# ---------------------------------------------------------------- review findings (round 3)

def test_review3(rec, scene, out_dir):
    # R1: scene names that share a long prefix must not share a threshold image (name truncation, deletion).
    prefix = "Environment_Exterior_Industrial_District_Sequence_"
    base = {"objects": [], "snap": 0, "fog": False, "texture": False, "resolution": [32, 24]}
    la, lb = bpy.data.scenes.new(prefix + "A"), bpy.data.scenes.new(prefix + "B")
    for s_ in (la, lb):
        s_.render.resolution_x, s_.render.resolution_y = 32, 24
    in_scene(la, lambda: run("lowpoly-style", "ps1_look.py", base))
    img_a = la.compositing_node_group.nodes["SK_PS1_DitherThreshold"].image
    name_a = img_a.name
    in_scene(lb, lambda: run("lowpoly-style", "ps1_look.py", base))
    node_a = la.compositing_node_group.nodes["SK_PS1_DitherThreshold"]
    img_b = lb.compositing_node_group.nodes["SK_PS1_DitherThreshold"].image
    rec.check("R1-review3: long scene names: scene A's threshold image survives applying PS1 in scene B",
              node_a.image is not None and name_a in bpy.data.images and bpy.data.images[name_a] == node_a.image, name_a)
    rec.check("R1-review3: long scene names: scenes A and B have different threshold images",
              img_b is not None and node_a.image is not None and img_b.name != node_a.image.name,
              (img_b and img_b.name, node_a.image and node_a.image.name))
    rec.check("R1-review3: image names stay within 63 characters", len(name_a) <= 63 and len(img_b.name) <= 63,
              (len(name_a), len(img_b.name)))
    in_scene(la, lambda: run("lowpoly-style", "ps1_look.py", base))
    rec.check("R1-review3: rerunning in A replaces its own image (one image per scene, none leaked)",
              sum(1 for i in bpy.data.images if prefix in i.name or i.get("sk_ps1_scene", "").startswith(prefix)) == 2,
              [i.name for i in bpy.data.images if prefix in i.name or i.get("sk_ps1_scene", "").startswith(prefix)])
    # A user image that happens to carry the name the script would pick must not be deleted.
    lc = bpy.data.scenes.new("__RT_R1_C")
    lc.render.resolution_x, lc.render.resolution_y = 32, 24
    in_scene(lc, lambda: run("lowpoly-style", "ps1_look.py", base))
    cname = lc.compositing_node_group.nodes["SK_PS1_DitherThreshold"].image.name
    lc.compositing_node_group.nodes.remove(lc.compositing_node_group.nodes["SK_PS1_DitherThreshold"])
    bpy.data.images.remove(bpy.data.images[cname])
    mine = bpy.data.images.new(cname, 4, 4)
    mine.use_fake_user = True
    in_scene(lc, lambda: run("lowpoly-style", "ps1_look.py", {**base, "dither": True}))
    rec.check("R1-review3: an image not made by PS1 for this scene is never deleted", mine.name in bpy.data.images
              and bpy.data.images[mine.name] == mine)

    # R2: a curve object with several splines flattens under every one of them.
    cu = bpy.data.curves.new("CRV_RT_TWO", "CURVE")
    cu.dimensions = "3D"
    for yy, zz in ((-12.0, 1.0), (12.0, 3.0)):
        sp = cu.splines.new("POLY")
        sp.points.add(1)
        for p_, co in zip(sp.points, [(-10, yy, zz, 1), (10, yy, zz, 1)]):
            p_.co = co
    scene.collection.objects.link(bpy.data.objects.new("CRV_RT_TWO", cu))
    args = {"size": 40, "resolution": 81, "seed": 7, "height": 4, "frequency": 0.08}
    run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrTwoFree"})
    free = mesh_coords(bpy.data.objects["RT_TerrTwoFree"])[:, 2]
    r = run("procedural-modeling", "terrain_heightfield.py",
            {**args, "name": "RT_TerrTwo", "corridor": {"curve": "CRV_RT_TWO", "half_width": 1.5, "falloff": 1.0}})["result"]
    co = mesh_coords(bpy.data.objects["RT_TerrTwo"])
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    for yy, zz in ((-12.0, 1.0), (12.0, 3.0)):
        bed = (np.abs(y - yy) <= 1.5) & (np.abs(x) <= 8)
        err = float(np.abs(z[bed] - zz).max()) if bed.any() else 99
        rec.check(f"R2-review3: spline at y={yy:g} is flattened to z={zz:g} (<= 1 mm)", bed.sum() > 10 and err < 1e-3,
                  f"n={bed.sum()} err={err}")
    mid = (np.abs(y) <= 3) & (np.abs(x) <= 8)
    rec.check("R2-review3: terrain between the splines is untouched noise", bool(np.allclose(z[mid], free[mid], atol=1e-6)))
    rec.check("R2-review3: result reports both splines", r["corridor"].get("splines") == 2, r["corridor"])

    # R3: independent literal values for each documented use case (SKILL.md table), not read from PRESETS.
    cy = scene.cycles
    literal = {
        "denoise_draft": dict(samples=32, use_denoising=True, denoiser="OPENIMAGEDENOISE", denoising_quality="FAST",
                              denoising_prefilter="FAST", denoising_input_passes="RGB_ALBEDO", adaptive_threshold=0.05),
        "denoise_final_still": dict(samples=1024, use_denoising=True, denoiser="OPENIMAGEDENOISE",
                                    denoising_quality="HIGH", denoising_prefilter="ACCURATE",
                                    denoising_input_passes="RGB_ALBEDO_NORMAL", adaptive_threshold=0.01),
        "denoise_animation": dict(samples=512, use_denoising=True, denoising_quality="BALANCED",
                                  denoising_prefilter="ACCURATE", denoising_input_passes="RGB_ALBEDO_NORMAL",
                                  use_animated_seed=False, adaptive_threshold=0.02),
        "denoise_viewport": dict(use_preview_denoising=True, preview_denoiser="AUTO", preview_denoising_quality="FAST",
                                 preview_denoising_prefilter="FAST", preview_denoising_input_passes="RGB_ALBEDO",
                                 preview_denoising_start_sample=1),
    }
    for name, want in literal.items():
        cy.use_denoising, cy.use_preview_denoising, cy.samples = False, False, 7  # known starting point
        run("rendering", "render_preset.py", {"preset": name})
        bad = {k: (getattr(cy, k), v) for k, v in want.items()
               if not (abs(getattr(cy, k) - v) < 1e-6 if isinstance(v, float) else getattr(cy, k) == v)}
        rec.check(f"R3-review3: {name} sets the documented values", not bad, bad)
    cy.use_denoising, cy.use_preview_denoising = True, True
    run("rendering", "render_preset.py", {"preset": "denoise_off"})
    rec.check("R3-review3: denoise_off turns both denoisers off", not cy.use_denoising and not cy.use_preview_denoising)
    cy.use_denoising, cy.use_preview_denoising = True, False
    run("rendering", "render_preset.py", {"preset": "denoise_viewport"})
    rec.check("R3-review3: denoise_viewport leaves the final-render denoise switch alone", cy.use_denoising is True)

    # R4: the map kind sits at the END of the name; asset-name words earlier in it are not map kinds.
    table = [
        ("Metal_Panel_Normal", "normal"), ("Metal_Panel_Metallic", "metallic"), ("MetalDoor_Normal", "normal"),
        ("Rock_occlusion_roughness_metallic", "orm"), ("Rock_OcclusionRoughnessMetallic", "orm"), ("Rock_ORM", "orm"),
        ("Rough_Stone_BaseColor", "base_color"), ("Rough_Stone_Albedo", "base_color"),
        ("Base_Metal_Roughness", "roughness"), ("Normal_Wall_Height", "height"),
        ("Normal_Wall_BaseColor", "base_color"), ("Color_Wall_Normal", "normal"), ("Wall_Base_Color", "base_color"),
        ("Wall_base-color", "base_color"), ("Metal_Door_AO", "ao"), ("AO_Panel_Roughness", "roughness"),
        ("Wall_Normal_DirectX", "normal"), ("Bump_Rock_Height", "height"), ("Disp_Rock_Normal", "normal"),
        ("Alpha_Tree_Opacity", "opacity"), ("Emissive_Lamp_BaseColor", "base_color"), ("Door_Metalness", "metallic"),
        ("Height_Crate_Metallic", "metallic"), ("Crate_Roughness_2k", "roughness"), ("MetalDoorNormal", "normal"),
        ("Crate_Mystery", None), ("Normal_Mystery", None),
    ]
    for i, (stem, kind) in enumerate(table):
        folder = os.path.join(out_dir, "r4_table", f"c{i}")
        os.makedirs(folder, exist_ok=True)
        save_map(os.path.join(folder, stem + ".png"), 0.5)
        args4 = {"folder": folder, "material": f"MAT_RT_T{i}"}
        if kind is None:
            rec.check(f"R4-review3 table: {stem} matches no map kind",
                      raises(lambda: run("texture-workflow", "import_painter_textures.py", args4)) is not None)
            continue
        got = run("texture-workflow", "import_painter_textures.py", args4)["result"]["files"]
        rec.check(f"R4-review3 table: {stem} -> {kind}", got == {kind: stem + ".png"}, got)
    folder = os.path.join(out_dir, "r4_metal_panel")
    os.makedirs(folder, exist_ok=True)
    for stem in ("BaseColor", "Normal", "Metallic", "Roughness"):
        save_map(os.path.join(folder, f"Metal_Panel_{stem}.png"), 0.5)
    r = run("texture-workflow", "import_painter_textures.py", {"folder": folder, "material": "MAT_RT_MetalPanel"})["result"]
    bsdf = next(n for n in bpy.data.materials["MAT_RT_MetalPanel"].node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    rec.check("R4-review3: Metal_Panel set: normal wired, metallic from Metallic file, nothing ambiguous",
              bsdf.inputs["Normal"].is_linked and r["files"].get("metallic") == "Metal_Panel_Metallic.png"
              and not r["ambiguous"], (r["files"], r["ambiguous"]))


def tree_has_image(sc):
    t = sc.compositing_node_group
    return t is not None and any(n.bl_idname == "CompositorNodeImage" and n.image for n in t.nodes)


def test_review4(rec, scene, out_dir):
    base = {"objects": [], "snap": 0, "fog": False, "texture": False, "resolution": [32, 24]}
    # R1a: PS1 -> comp_grade -> PS1 (and the fog variant) must keep every grade node connected to the source.
    for tag, fog in (("dither only", False), ("fog+dither", True)):
        sc = bpy.data.scenes.new("__RT_R4_order_" + tag[:3])
        sc.render.resolution_x, sc.render.resolution_y = 32, 24
        in_scene(sc, lambda: run("lowpoly-style", "ps1_look.py", {**base, "fog": fog}))
        in_scene(sc, lambda: run("compositing", "comp_grade.py", {"preset": "noir"}))
        tree = sc.compositing_node_group
        grade = {n.name for n in tree.nodes if n.name.startswith("SK_") and not n.name.startswith("SK_PS1_")
                 and n.bl_idname not in ("NodeGroupOutput", "CompositorNodeRLayers")}
        in_scene(sc, lambda: run("lowpoly-style", "ps1_look.py", {**base, "fog": fog}))
        tree = sc.compositing_node_group
        out = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")
        up = upstream_names(tree)
        rl = next(n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers")
        unfed = sorted(n.name for n in tree.nodes if n.name in grade
                       and not any(i.is_linked for i in n.inputs if i.enabled and i.type == "RGBA"))
        rec.check(f"R1-review4: PS1 -> grade -> PS1 ({tag}): every grade node still has an image input", not unfed, unfed)
        rec.check(f"R1-review4: PS1 -> grade -> PS1 ({tag}): Render Layers still reaches the output", rl.name in up, sorted(up))
        last = out.inputs[0].links[0].from_node.name if out.inputs[0].is_linked else None
        rec.check(f"R1-review4: PS1 -> grade -> PS1 ({tag}): dither is the last stage", last == "SK_PS1_DitherToLinear", last)
        dsrc = tree.nodes["SK_PS1_DitherToSRGB"].inputs[0]
        dfrom = dsrc.links[0].from_node.name if dsrc.is_linked else None
        rec.check(f"R1-review4: PS1 -> grade -> PS1 ({tag}): dither is fed by the grade (or the fog stage that follows it)",
                  dfrom in grade or (fog and dfrom == "SK_PS1_Fog"), dfrom)

    # R2: rename a scene, make a new scene with the old name; its PS1 run must not delete the renamed scene's image.
    a = bpy.data.scenes.new("__RT_R4_RenA")
    a.render.resolution_x, a.render.resolution_y = 32, 24
    in_scene(a, lambda: run("lowpoly-style", "ps1_look.py", base))
    iname = a.compositing_node_group.nodes["SK_PS1_DitherThreshold"].image.name
    a.name = "__RT_R4_RenB"
    a2 = bpy.data.scenes.new("__RT_R4_RenA")
    a2.render.resolution_x, a2.render.resolution_y = 32, 24
    in_scene(a2, lambda: run("lowpoly-style", "ps1_look.py", base))
    node = a.compositing_node_group.nodes["SK_PS1_DitherThreshold"]
    rec.check("R2-review4: renamed scene keeps its threshold image after a same-named new scene runs PS1",
              node.image is not None and iname in bpy.data.images and bpy.data.images[iname] == node.image
              and node.image.size[0] == 32, iname)
    rec.check("R2-review4: the new scene has a different image",
              a2.compositing_node_group.nodes["SK_PS1_DitherThreshold"].image != node.image)
    owned = lambda: sum(1 for i in bpy.data.images if i.get("sk_ps1_scene") is not None)
    n_before = owned()
    in_scene(a, lambda: run("lowpoly-style", "ps1_look.py", base))
    rec.check("R2-review4: rerun in the renamed scene does not leak or delete images", owned() == n_before, (n_before, owned()))
    in_scene(a, lambda: run("lowpoly-style", "ps1_look.py", {**base, "dither": False}))
    rec.check("R2-review4: dither off removes the unused image of this scene", owned() == n_before - 1, (n_before, owned()))
    rec.check("R2-review4: the other scene's image survives", tree_has_image(a2))

    # R3: replace must never edit a mesh shared with another object.
    twin_args = {"size": 10, "resolution": 9, "seed": 1, "height": 2, "name": "RT_Shared"}
    run("procedural-modeling", "terrain_heightfield.py", twin_args)
    obj = bpy.data.objects["RT_Shared"]
    twin = bpy.data.objects.new("RT_SharedTwin", obj.data)
    scene.collection.objects.link(twin)
    before = mesh_coords(twin).copy()
    shared_mesh = obj.data
    try:
        run("procedural-modeling", "terrain_heightfield.py", {**twin_args, "seed": 99, "replace": True})
        refused = False
    except ValueError:
        refused = True
    after = mesh_coords(twin)
    rec.check("R3-review4: replacing a terrain whose mesh is shared leaves the other object's mesh untouched",
              twin.data == shared_mesh and after.shape == before.shape and np.allclose(after, before),
              (after.shape, before.shape))
    rec.check("R3-review4: the shared-mesh replace either refused or gave the object its own mesh",
              refused or obj.data != twin.data, refused)
    run("procedural-modeling", "terrain_heightfield.py", {**twin_args, "name": "RT_Solo"})
    solo_mesh = bpy.data.objects["RT_Solo"].data
    run("procedural-modeling", "terrain_heightfield.py", {**twin_args, "name": "RT_Solo", "seed": 5, "replace": True})
    rec.check("R3-review4: single-user replace still works and reuses its mesh",
              bpy.data.objects["RT_Solo"].data == solo_mesh and solo_mesh.users == 1)

    # R4 (low): doc describes trailing keywords
    doc = open(os.path.join(SKILLS, "texture-workflow", "references", "substance-painter-handoff.md"), encoding="utf-8").read()
    rec.check("R4-review4: doc no longer says 'any one in the file name'",
              "any one in the file name" not in doc and "end of the file name" in doc)


# ---------------------------------------------------------------- review findings (round 5)

def test_review5(rec, scene, out_dir):
    import math
    # R2: a replace on a terrain object that carries scale / rotation / a parent must keep world heights, or refuse.
    cu = bpy.data.curves.new("CRV_RT_R5", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    for p, co in zip(sp.points, [(-8, 0, 3, 1), (8, 0, 3, 1)]):
        p.co = co
    scene.collection.objects.link(bpy.data.objects.new("CRV_RT_R5", cu))
    corr = {"curve": "CRV_RT_R5", "half_width": 2.0, "falloff": 1.0}
    args = {"size": 30, "resolution": 61, "seed": 3, "height": 3, "frequency": 0.05, "corridor": corr}
    cases = {
        "scaled Z": lambda o, par: setattr(o, "scale", (1, 1, 2)),
        "rotated": lambda o, par: setattr(o, "rotation_euler", (0, math.radians(30), 0)),
        "parented": lambda o, par: (setattr(o, "parent", par), setattr(par, "location", (0, 0, 5))),
    }
    for tag, mutate in cases.items():
        nm = "RT_TerrXf_" + tag.replace(" ", "")
        run("procedural-modeling", "terrain_heightfield.py", {**args, "name": nm})
        o = bpy.data.objects[nm]
        par = bpy.data.objects.new(nm + "_Par", None)
        scene.collection.objects.link(par)
        mutate(o, par)
        bpy.context.view_layer.update()
        err = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**args, "name": nm, "replace": True}))
        bpy.context.view_layer.update()
        if err is not None:
            rec.check(f"R2-review5 ({tag}): refused with a message naming the transform",
                      any(w in err for w in ("scale", "rotation", "parent")), err)
            continue
        w = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
        bed = (np.abs(w[:, 1]) <= 1.5) & (np.abs(w[:, 0]) <= 6)
        e = float(np.abs(w[bed, 2] - 3.0).max()) if bed.any() else 99
        rec.check(f"R2-review5 ({tag}): corridor bed sits at the curve's world height (<= 1 mm)", bed.sum() > 5 and e < 1e-3,
                  f"n={bed.sum()} err={e}")

    # R1: PS1 flat shading in Edit Mode must take effect (live edit faces) or refuse, not be overwritten on exit.
    me = bpy.data.meshes.new("RT_PS1Edit")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new("RT_PS1Edit", me)
    scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, 0.5)})
    refused = raises(lambda: run("lowpoly-style", "ps1_look.py", {"objects": ["RT_PS1Edit"], "snap": 0.02, "flat": True,
                                                                  "fog": False, "dither": False, "texture": False,
                                                                  "resolution": [32, 24]}))
    smooth_live = None
    if refused is None:
        smooth_live = sum(1 for f in bmesh.from_edit_mesh(me).faces if f.smooth)
    bpy.ops.object.mode_set(mode="OBJECT")
    if refused is not None:
        rec.check("R1-review5: Edit Mode flat shading refused with a message naming Edit Mode", "Edit" in refused, refused)
    else:
        smooth_after = sum(1 for p in me.polygons if p.use_smooth)
        rec.check("R1-review5: Edit Mode flat shading leaves no smooth face, live or after leaving Edit Mode",
                  smooth_live == 0 and smooth_after == 0, (smooth_live, smooth_after, len(me.polygons)))

    # R5: USD material comparison uses the evaluated state the exporter writes (Geometry Nodes Set Material).
    mat = bpy.data.materials.new("RT_USD_GNMat")
    me2 = bpy.data.meshes.new("RT_USD_GN")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me2)
    bm.free()
    gob = bpy.data.objects.new("RT_USD_GN", me2)
    scene.collection.objects.link(gob)
    ng = bpy.data.node_groups.new("RT_USD_GN_Group", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    sm = ng.nodes.new("GeometryNodeSetMaterial")
    sm.inputs["Material"].default_value = mat
    ng.links.new(gi.outputs[0], sm.inputs["Geometry"])
    ng.links.new(sm.outputs[0], go.inputs[0])
    gob.modifiers.new("GN", "NODES").node_group = ng
    gob.location = (6, 0, 0)
    bpy.context.view_layer.update()
    r = run("usd-pipeline", "usd_roundtrip.py", {"objects": ["RT_USD_GN"],
                                                  "out_path": os.path.join(out_dir, "r5_gnmat", "gn.usdc")})["result"]
    rec.check("R5-review5: a material set by Geometry Nodes round-trips ok (compared as the exporter writes it)",
              r["ok"], r["problems"])


def test_review6(rec, scene, out_dir):
    import math
    cu = bpy.data.curves.new("CRV_RT_R6", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    for p, co in zip(sp.points, [(-8, 0, 3, 1), (8, 0, 3, 1)]):
        p.co = co
    scene.collection.objects.link(bpy.data.objects.new("CRV_RT_R6", cu))
    corr = {"curve": "CRV_RT_R6", "half_width": 2.0, "falloff": 1.0}
    args = {"size": 30, "resolution": 61, "seed": 3, "height": 3, "frequency": 0.05, "corridor": corr}

    def make(nm):
        run("procedural-modeling", "terrain_heightfield.py", {**args, "name": nm})
        return bpy.data.objects[nm]

    def bed_error(o):
        w = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
        bed = (np.abs(w[:, 1]) <= 1.5) & (np.abs(w[:, 0]) <= 6)
        return float(np.abs(w[bed, 2] - 3.0).max()) if bed.any() else 99.0

    def axis_angle(o):
        o.rotation_mode = "AXIS_ANGLE"
        o.rotation_axis_angle = (math.radians(30), 0, 1, 0)

    def delta_quat(o):
        o.rotation_mode = "QUATERNION"
        o.delta_rotation_quaternion = (math.cos(math.radians(15)), 0, math.sin(math.radians(15)), 0)

    def constraint(o):
        tgt = bpy.data.objects.new("RT_R6_Tgt", None)
        tgt.location = (0, 0, 4)
        scene.collection.objects.link(tgt)
        c = o.constraints.new("COPY_LOCATION")
        c.target = tgt

    for tag, mutate in (("axis-angle rotation", axis_angle), ("delta quaternion", delta_quat), ("constraint", constraint)):
        nm = "RT_TerrR6_" + tag.replace(" ", "").replace("-", "")
        o = make(nm)
        mutate(o)
        bpy.context.view_layer.update()
        err = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**args, "name": nm, "replace": True}))
        bpy.context.view_layer.update()
        if err is not None:
            rec.check(f"R2-review6 ({tag}): refused with a message", "replace" in err or "transform" in err, err)
        else:
            e = bed_error(o)
            rec.check(f"R2-review6 ({tag}): not refused, so the bed must sit at the curve's world height", e < 1e-3, e)

    # replace on a clean, translated object still works
    o = make("RT_TerrR6_ok")
    o.location = (4, 4, 9)
    bpy.context.view_layer.update()
    r = run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrR6_ok", "replace": True})["result"]
    bpy.context.view_layer.update()
    rec.check("R2-review6: a terrain that is only moved is still replaced, bed at world height",
              r["object"] == "RT_TerrR6_ok" and bed_error(o) < 1e-3, bed_error(o))

    # R3: shape keys on the terrain mesh
    o = make("RT_TerrR6_sk")
    o.shape_key_add(name="Basis")
    key = o.shape_key_add(name="Up")
    for pt in key.data:
        pt.co.z += 5.0
    key.value = 1.0
    n_before = len(o.data.vertices)
    err = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrR6_sk", "replace": True}))
    bpy.context.view_layer.update()
    rec.check("R3-review6: replace on a mesh with shape keys is refused with a message naming shape keys",
              err is not None and "shape key" in err.lower(), err)
    rec.check("R3-review6: the refused mesh keeps its shape keys and vertices",
              o.data.shape_keys is not None and len(o.data.shape_keys.key_blocks) == 2 and len(o.data.vertices) == n_before, "")

    # R3: Edit Mode
    o = make("RT_TerrR6_edit")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    err = raises(lambda: run("procedural-modeling", "terrain_heightfield.py", {**args, "name": "RT_TerrR6_edit", "replace": True}))
    still_edit = o.mode == "EDIT"
    bpy.ops.object.mode_set(mode="OBJECT")
    rec.check("R3-review6: replace in Edit Mode is refused with a clear message naming Edit Mode, before anything changes",
              err is not None and "Edit Mode" in err and still_edit and len(o.data.vertices) == 61 * 61, (err, still_edit))


# ---------------------------------------------------------------- harness

def run_all(out_dir):
    rec = Recorder()
    os.makedirs(out_dir, exist_ok=True)
    before = {c: {i.name for i in getattr(bpy.data, c)} for c in COLLECTIONS}
    scenes_before = {s.name for s in bpy.data.scenes}
    window = bpy.context.window
    original = window.scene if window else bpy.context.scene
    scene = bpy.data.scenes.new("__RoadmapTests")
    if window:
        window.scene = scene
    try:
        ctx = bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]) if not window else None
        if ctx:
            ctx.__enter__()
        try:
            for name, fn in (("R1", test_r1), ("R2", test_r2), ("R3", test_r3), ("R4", test_r4), ("R5", test_r5),
                             ("R1-review", test_review_r1), ("R2-review", test_review_r2),
                             ("R3-review", test_review_r3), ("R4-review", test_review_r4),
                             ("R5-review", test_review_r5), ("review2", test_review2),
                             ("review3", test_review3), ("review4", test_review4),
                             ("review5", test_review5), ("review6", test_review6)):
                rec.section(name, lambda r, fn=fn: fn(r, scene, out_dir))
        finally:
            if ctx:
                ctx.__exit__(None, None, None)
    finally:
        if window:
            window.scene = original
        for s in [s for s in bpy.data.scenes if s.name not in scenes_before]:
            bpy.data.scenes.remove(s)
        for coll in COLLECTIONS:
            for item in [i for i in getattr(bpy.data, coll) if i.name not in before[coll]]:
                try:
                    getattr(bpy.data, coll).remove(item)
                except (ReferenceError, RuntimeError):
                    pass
    return rec.results


def main(out_dir=None):
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "blender-roadmap-tests")
    try:
        results = run_all(out_dir)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": traceback.format_exc()[-700:]}]
    failures = [r for r in results if not r["ok"]]
    report = {"blender": bpy.app.version_string,
              "summary": {"passed": len(results) - len(failures), "total": len(results), "failed": len(failures)},
              "passed": len(results) - len(failures), "total": len(results), "failures": failures, "results": results}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "roadmap_tests_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("summary", "failures")}, indent=2))
