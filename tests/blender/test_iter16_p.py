"""Headless Blender tests for iteration 16, batch P (blender-mcp-workflow).

  P1  env_report.py       read-only preflight: version, engines, add-ons, Cycles devices, named enums; the session
                          snapshot is equal before and after (clean and already dirty file); errors become entries
  P2  validate_asset.py   material_slots (empty slot / index beyond slots), material_images (missing file unless
                          packed), material_color_space (sRGB into data sockets, Non-Color into Base Color)
  P3  validate_asset.py   max_materials, max_texture_px, max_bones: over budget FAILs with the measured value, a value
                          exactly at the limit passes, unset means the check is absent

Every fixture is built in code on the current scene and removed again; nothing is saved. Run:
    blender -b --factory-startup --python tests/blender/test_iter16_p.py -- '{"out_dir": "<a NEW folder>"}'
Optional "validate_script": a path to another copy of validate_asset.py (used to watch the P2/P3 tests fail on the
iteration 15 script). Writes <out_dir>/iter16_p_report.json with passed / total / failed / checks; exits 1 on failure.
"""
import json
import os
import runpy
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
WF = os.path.join(SKILLS, "blender-mcp-workflow")
CONFIG = {"out_dir": ".", "validate_script": None}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(script, args):
    path = os.path.join(WF, "scripts", script)
    if script == "validate_asset.py" and CONFIG["validate_script"]:
        path = CONFIG["validate_script"]
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


# ---------------------------------------------------------------------------------------------------------- fixtures
CUBE_V = [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0), (-.5, -.5, 1), (.5, -.5, 1), (.5, .5, 1), (-.5, .5, 1)]
CUBE_F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
QUAD = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
CREATED = {"objects": [], "meshes": [], "materials": [], "images": [], "armatures": []}
TEMP_FILES = []


def cube_uvs():
    uvs = []
    for fi in range(6):
        cu, cv = (fi % 3) / 3, (fi // 3) / 2
        uvs.extend((cu + 0.02 + 0.29 * u, cv + 0.02 + 0.46 * v) for (u, v) in QUAD)
    return uvs


def mesh_obj(name, materials=(), face_slots=None):
    """A unit cube with UVs, the given material slots (None = an empty slot) and per-face slot indices."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(CUBE_V, [], CUBE_F)
    me.update()
    layer = me.uv_layers.new(name="UVMap")
    for li, uv in enumerate(cube_uvs()):
        layer.uv[li].vector = uv
    for mat in materials:
        me.materials.append(mat)
    if face_slots is not None:
        for poly, idx in zip(me.polygons, face_slots):
            poly.material_index = idx
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    CREATED["objects"].append(ob)
    CREATED["meshes"].append(me)
    return ob


def new_mat(name):
    """A material with its own Principled BSDF + Material Output (nothing from defaults is assumed)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    CREATED["materials"].append(mat)
    return mat, tree, bsdf


def gen_image(name, w, h, colorspace="sRGB"):
    img = bpy.data.images.new(name, w, h)
    img.colorspace_settings.name = colorspace
    CREATED["images"].append(img)
    return img


def file_image(name, folder, colorspace="sRGB"):
    """A real PNG on disk, loaded as a FILE image."""
    path = os.path.join(folder, name + ".png")
    gen = bpy.data.images.new(name + "_src", 4, 4)
    gen.filepath_raw = path
    gen.file_format = "PNG"
    gen.save()
    bpy.data.images.remove(gen)
    TEMP_FILES.append(path)
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = colorspace
    CREATED["images"].append(img)
    return img, path


def tex_node(tree, image):
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    return node


def cleanup():
    for ob in CREATED["objects"]:
        if ob.name in bpy.data.objects:
            bpy.data.objects.remove(ob, do_unlink=True)
    for key in ("meshes", "materials", "images", "armatures"):
        for d in CREATED[key]:
            coll = getattr(bpy.data, key)
            if d.name in coll:
                coll.remove(d)
        CREATED[key].clear()
    CREATED["objects"].clear()
    for path in TEMP_FILES:
        if os.path.isfile(path):
            os.remove(path)
    TEMP_FILES.clear()


def validate(name, **kw):
    return run("validate_asset.py", {"objects": [name], "prefix": "", **kw})


def check(res, name, key):
    return res["objects"][name]["checks"][key]


# ---------------------------------------------------------------------------------------------- session snapshot
def snapshot():
    """Everything env_report could touch, in a comparable form."""
    scene = bpy.context.scene
    cp = bpy.context.preferences.addons["cycles"].preferences if "cycles" in bpy.context.preferences.addons else None
    names = {}
    for attr in dir(bpy.data):
        coll = getattr(bpy.data, attr, None)
        if isinstance(coll, bpy.types.bpy_prop_collection) and attr not in ("window_managers", "screens", "workspaces"):
            names[attr] = sorted(i.name for i in coll)
    active = bpy.context.view_layer.objects.active
    return {
        "datablocks": names,
        "selected": sorted(o.name for o in scene.objects if o.select_get()),
        "active": active.name if active else None,
        "mode": active.mode if active else None,
        "frame": scene.frame_current,
        "engine": scene.render.engine,
        "cycles_device": scene.cycles.device if hasattr(scene, "cycles") else None,
        "cycles_prefs": None if cp is None else {"type": cp.compute_device_type,
                                                 "devices": [(d.name, d.type, d.use) for d in cp.devices]},
        "addons": sorted(bpy.context.preferences.addons.keys()),
        "is_dirty": bpy.data.is_dirty,
    }


# ------------------------------------------------------------------------------------------------------------ tests
def test_p1_env_report_state_and_values(out_dir):
    """P1: the report matches the session, enum values are real, and a clean and a dirty file both come out unchanged."""
    scene = bpy.context.scene
    ob = mesh_obj("P1_Obj")
    other = mesh_obj("P1_Other")
    original_frame = scene.frame_current
    seen = {}
    try:
        for label in ("clean", "dirty"):
            if label == "dirty":
                assert bpy.ops.ed.undo_push(message="iter16 p1 make dirty") == {"FINISHED"}  # tags the file as changed
            scene.frame_set(7)
            for o in bpy.context.scene.objects:
                o.select_set(False)
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            before = snapshot()
            res = run("env_report.py", {"enums": ["BooleanModifier.solver", "Object.mode"]})
            after = snapshot()
            assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
            seen[label] = {"is_dirty": before["is_dirty"], "frame": after["frame"]}
        assert seen["dirty"]["is_dirty"] is True, f"the dirty fixture was not dirty: {seen}"
        assert seen["clean"]["is_dirty"] is False, f"the clean fixture was not clean: {seen}"
        assert res["blender"]["version"] == list(bpy.app.version) and res["blender"]["version_string"] == bpy.app.version_string
        assert "BLENDER_EEVEE" in res["render_engines"] and res["scene_engine"] == scene.render.engine, res["render_engines"]
        assert "cycles" in res["addons_enabled"] and res["addons_enabled"] == sorted(bpy.context.preferences.addons.keys())
        solver = res["enums"]["BooleanModifier.solver"]
        assert solver["values"] == ["FLOAT", "EXACT", "MANIFOLD"], solver
        assert res["cycles"]["present"] is True and "CPU" in res["cycles"]["devices"], res["cycles"]
        assert all("name" in d and "id" in d for d in res["cycles"]["devices"]["CPU"]), res["cycles"]["devices"]
        json.dumps(res)  # JSON-safe
    finally:
        scene.frame_set(original_frame)
        cleanup()
    return {"clean_vs_dirty": seen, "solver": solver["values"], "cpu_devices": res["cycles"]["devices"]["CPU"],
            "engines": res["render_engines"]}


def test_p1_enum_errors_and_args(out_dir):
    """P1: an unknown name is an error entry (not a crash); bad ARGS raise before anything is written."""
    res = run("env_report.py", {"enums": ["NoSuchClass.prop", "BooleanModifier.nope", "Object.location", "bad",
                                          "bpy.types.BooleanModifier.operation", "A.b.c", ".x", "Object.mode"]})
    enums = res["enums"]
    assert "error" in enums["NoSuchClass.prop"] and "NoSuchClass" in enums["NoSuchClass.prop"]["error"], enums
    assert "no property" in enums["BooleanModifier.nope"]["error"], enums
    assert "not an enum" in enums["Object.location"]["error"], enums
    for bad in ("bad", "A.b.c", ".x"):
        assert "not 'Class.property'" in enums[bad]["error"], (bad, enums[bad])
    assert "DIFFERENCE" in enums["bpy.types.BooleanModifier.operation"]["values"], enums["bpy.types.BooleanModifier.operation"]
    assert "values" in enums["Object.mode"], enums["Object.mode"]
    path = os.path.join(CONFIG["out_dir"], "p1_should_not_exist.json")
    try:
        run("env_report.py", {"enums": "BooleanModifier.solver", "result_path": path})
    except ValueError as exc:
        raised = str(exc)
    else:
        raise AssertionError("a string for enums did not raise")
    assert not os.path.exists(path) and not os.path.exists(path + ".tmp")
    return {"errors": {k: v.get("error") for k, v in enums.items() if "error" in v}, "raised": raised}


def test_p1_result_file(out_dir):
    path = os.path.join(out_dir, "p1_result.json")
    res = run("env_report.py", {"enums": ["BooleanModifier.solver"], "result_path": path, "run_id": "rid-1"})
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["run_id"] == "rid-1" and data["enums"] == res["enums"] and not os.path.exists(path + ".tmp")
    return {"keys": sorted(data)}


def test_p2_material_slots():
    """P2: a face on an empty slot or beyond the slots FAILs; an empty slot nobody uses is fine."""
    try:
        mat, _, _ = new_mat("P2_A")
        empty = mesh_obj("P2_Empty", [mat, None], [0, 0, 0, 0, 0, 1])
        beyond = mesh_obj("P2_Beyond", [mat], [0, 0, 0, 0, 0, 5])
        unused = mesh_obj("P2_UnusedEmpty", [mat, None], [0, 0, 0, 0, 0, 0])
        good = mesh_obj("P2_GoodSlots", [mat], [0] * 6)
        res = run("validate_asset.py", {"objects": [o.name for o in (empty, beyond, unused, good)], "prefix": ""})
        got = {n: check(res, n, "material_slots")["status"] for n in ("P2_Empty", "P2_Beyond", "P2_UnusedEmpty", "P2_GoodSlots")}
        detail = {n: check(res, n, "material_slots")["detail"] for n in got}
    finally:
        cleanup()
    assert got == {"P2_Empty": "FAIL", "P2_Beyond": "FAIL", "P2_UnusedEmpty": "PASS", "P2_GoodSlots": "PASS"}, (got, detail)
    assert res["objects"]["P2_Empty"]["verdict"] == "FAIL" and res["objects"]["P2_GoodSlots"]["verdict"] == "PASS"
    return {"statuses": got, "detail": detail}


def test_p2_material_images(out_dir):
    """P2: an image whose file is gone FAILs unless it is packed; generated and present files pass."""
    try:
        folder = os.path.join(out_dir, "p2_img")
        os.makedirs(folder, exist_ok=True)
        cases = {}
        img_missing, p_missing = file_image("p2_missing", folder)
        img_packed, p_packed = file_image("p2_packed", folder)
        img_packed.pack()
        img_here, _ = file_image("p2_here", folder)
        img_gen = gen_image("p2_generated", 8, 8)
        for key, img in (("missing", img_missing), ("packed", img_packed), ("present", img_here), ("generated", img_gen)):
            mat, tree, bsdf = new_mat(f"P2_I_{key}")
            tree.links.new(tex_node(tree, img).outputs["Color"], bsdf.inputs["Base Color"])
            cases[key] = mesh_obj(f"P2_Img_{key}", [mat], [0] * 6)
        os.remove(p_missing)
        os.remove(p_packed)
        res = run("validate_asset.py", {"objects": [o.name for o in cases.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_images")["status"] for k, o in cases.items()}
        detail = {k: check(res, o.name, "material_images")["detail"] for k, o in cases.items()}
    finally:
        cleanup()
    assert got == {"missing": "FAIL", "packed": "PASS", "present": "PASS", "generated": "PASS"}, (got, detail)
    assert "p2_missing" in detail["missing"]
    return {"statuses": got, "missing_detail": detail["missing"]}


def test_p2_color_space():
    """P2: sRGB colour into data sockets and Non-Color into Base Color WARN; the right wiring and Alpha output pass."""
    results = {}
    try:
        def case(key, build):
            mat, tree, bsdf = new_mat(f"P2_C_{key}")
            build(tree, bsdf)
            results[key] = mesh_obj(f"P2_Cs_{key}", [mat], [0] * 6)

        def srgb(name="s"):
            return gen_image(f"p2_srgb_{name}", 8, 8, "sRGB")

        def data(name="d"):
            return gen_image(f"p2_data_{name}", 8, 8, "Non-Color")

        def link(tree, src, out, dst, inp):
            tree.links.new(src.outputs[out], dst.inputs[inp])

        case("bad_srgb_roughness", lambda t, b: link(t, tex_node(t, srgb("r")), "Color", b, "Roughness"))
        case("bad_srgb_metallic", lambda t, b: link(t, tex_node(t, srgb("m")), "Color", b, "Metallic"))
        case("bad_srgb_alpha", lambda t, b: link(t, tex_node(t, srgb("a")), "Color", b, "Alpha"))

        def srgb_normal_map(t, b):
            nm = t.nodes.new("ShaderNodeNormalMap")
            link(t, tex_node(t, srgb("n")), "Color", nm, "Color")
            link(t, nm, "Normal", b, "Normal")
        case("bad_srgb_normal_map", srgb_normal_map)

        def srgb_bump(t, b):
            bump = t.nodes.new("ShaderNodeBump")
            link(t, tex_node(t, srgb("h")), "Color", bump, "Height")
            link(t, bump, "Normal", b, "Normal")
        case("bad_srgb_bump_height", srgb_bump)

        def srgb_via_reroute(t, b):
            rr = t.nodes.new("NodeReroute")
            link(t, tex_node(t, srgb("rr")), "Color", rr, 0)
            t.links.new(rr.outputs[0], b.inputs["Roughness"])
        case("bad_srgb_via_reroute", srgb_via_reroute)
        case("bad_noncolor_base_color", lambda t, b: link(t, tex_node(t, data("bc")), "Color", b, "Base Color"))

        case("good_srgb_base_color", lambda t, b: link(t, tex_node(t, srgb("bc")), "Color", b, "Base Color"))
        case("good_noncolor_roughness", lambda t, b: link(t, tex_node(t, data("r")), "Color", b, "Roughness"))
        case("good_srgb_alpha_output", lambda t, b: link(t, tex_node(t, srgb("ao")), "Alpha", b, "Alpha"))

        def good_normal(t, b):
            nm = t.nodes.new("ShaderNodeNormalMap")
            link(t, tex_node(t, data("n")), "Color", nm, "Color")
            link(t, nm, "Normal", b, "Normal")
        case("good_noncolor_normal_map", good_normal)
        res = run("validate_asset.py", {"objects": [o.name for o in results.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_color_space")["status"] for k, o in results.items()}
        verdicts = {k: res["objects"][o.name]["verdict"] for k, o in results.items()}
        detail = {k: check(res, o.name, "material_color_space")["detail"] for k, o in results.items()}
    finally:
        cleanup()
    want = {k: ("WARN" if k.startswith("bad") else "PASS") for k in got}
    assert got == want, (got, detail)
    assert all(verdicts[k] == "WARN" for k in got if k.startswith("bad")), verdicts
    assert all(verdicts[k] == "PASS" for k in got if k.startswith("good")), verdicts
    return {"statuses": got, "example_detail": detail["bad_srgb_roughness"]}


def test_p3_max_materials():
    """P3: distinct materials used by faces; exactly the limit passes; unused slots do not count; unset = absent."""
    try:
        mats = [new_mat(f"P3_M{i}")[0] for i in range(3)]
        three = mesh_obj("P3_Three", mats, [0, 0, 1, 1, 2, 2])
        two_used = mesh_obj("P3_TwoUsed", mats, [0, 0, 1, 1, 1, 0])
        at = validate(three.name, max_materials=3)
        over = validate(three.name, max_materials=2)
        unused = validate(two_used.name, max_materials=2)
        unset = validate(three.name)
        zero = validate(three.name, max_materials=0)
    finally:
        cleanup()
    assert check(at, "P3_Three", "budget_materials")["status"] == "PASS", at
    assert check(over, "P3_Three", "budget_materials")["status"] == "FAIL" and "3 material" in check(over, "P3_Three", "budget_materials")["detail"]
    assert over["objects"]["P3_Three"]["verdict"] == "FAIL" and over["verdict"] == "FAIL"
    assert check(unused, "P3_TwoUsed", "budget_materials")["status"] == "PASS", unused
    assert "budget_materials" not in unset["objects"]["P3_Three"]["checks"]
    assert check(zero, "P3_Three", "budget_materials")["status"] == "FAIL"
    return {"at_limit": check(at, "P3_Three", "budget_materials"), "over": check(over, "P3_Three", "budget_materials")}


def test_p3_max_texture_px():
    """P3: the largest width or height of the slot materials' images, each image once; the limit itself passes."""
    try:
        wide = gen_image("p3_wide", 128, 32)
        tall = gen_image("p3_tall", 16, 64)
        mat, tree, bsdf = new_mat("P3_T")
        n1, n2, n3 = tex_node(tree, wide), tex_node(tree, wide), tex_node(tree, tall)  # `wide` twice
        tree.links.new(n1.outputs["Color"], bsdf.inputs["Base Color"])
        ob = mesh_obj("P3_Tex", [mat], [0] * 6)
        small_mat, stree, sbsdf = new_mat("P3_Small")
        stree.links.new(tex_node(stree, gen_image("p3_small", 8, 8)).outputs["Color"], sbsdf.inputs["Base Color"])
        small = mesh_obj("P3_Small", [small_mat], [0] * 6)
        at = validate(ob.name, max_texture_px=128)
        over = validate(ob.name, max_texture_px=127)
        small_ok = validate(small.name, max_texture_px=127)
        unset = validate(ob.name)
    finally:
        cleanup()
    assert check(at, "P3_Tex", "budget_texture_px")["status"] == "PASS", at
    d = check(over, "P3_Tex", "budget_texture_px")
    assert d["status"] == "FAIL" and "128 px" in d["detail"], d
    assert check(small_ok, "P3_Small", "budget_texture_px")["status"] == "PASS"
    assert "budget_texture_px" not in unset["objects"]["P3_Tex"]["checks"]
    return {"at_limit": check(at, "P3_Tex", "budget_texture_px")["detail"], "over": d["detail"]}


def make_armature(name, deform, plain):
    """An armature object with `deform` deforming bones and `plain` non-deforming ones (edit mode, restored)."""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    CREATED["objects"].append(ob)
    CREATED["armatures"].append(arm)
    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.object.mode_set(mode="EDIT") == {"FINISHED"}
    try:
        for i in range(deform + plain):
            bone = arm.edit_bones.new(f"b{i}")
            bone.head, bone.tail = (i, 0, 0), (i, 0, 1)
            bone.use_deform = i < deform
    finally:
        assert bpy.ops.object.mode_set(mode="OBJECT") == {"FINISHED"}
        bpy.context.view_layer.objects.active = prev_active
    return ob


def test_p3_max_bones():
    """P3: deform bones of the armatures its Armature modifiers point at; non-deform bones and a second modifier on the
    same armature do not add; a mesh with no Armature modifier measures 0."""
    try:
        mat, _, _ = new_mat("P3_B")
        arm = make_armature("P3_Arm", deform=3, plain=2)
        skinned = mesh_obj("P3_Skinned", [mat], [0] * 6)
        for i in range(2):
            mod = skinned.modifiers.new(f"Arm{i}", "ARMATURE")
            mod.object = arm
        free = mesh_obj("P3_NoArm", [mat], [0] * 6)
        at = validate(skinned.name, max_bones=3)
        over = validate(skinned.name, max_bones=2)
        none = validate(free.name, max_bones=0)
        unset = validate(skinned.name)
    finally:
        cleanup()
    assert check(at, "P3_Skinned", "budget_bones")["status"] == "PASS", at
    d = check(over, "P3_Skinned", "budget_bones")
    assert d["status"] == "FAIL" and "3 deform bone" in d["detail"], d
    assert check(none, "P3_NoArm", "budget_bones")["status"] == "PASS"
    assert "budget_bones" not in unset["objects"]["P3_Skinned"]["checks"]
    return {"at_limit": check(at, "P3_Skinned", "budget_bones")["detail"], "over": d["detail"]}


def test_p3_bad_budget_args():
    """P3: a negative, boolean or string budget raises before any result is written."""
    path = os.path.join(CONFIG["out_dir"], "p3_should_not_exist.json")
    try:
        mat, _, _ = new_mat("P3_Args")
        ob = mesh_obj("P3_ArgsObj", [mat], [0] * 6)
        raised = {}
        for key, value in (("max_materials", -1), ("max_texture_px", True), ("max_bones", "8")):
            try:
                validate(ob.name, result_path=path, **{key: value})
            except ValueError as exc:
                raised[key] = str(exc)
    finally:
        cleanup()
    assert set(raised) == {"max_materials", "max_texture_px", "max_bones"}, raised
    assert not os.path.exists(path)
    return raised


def test_p23_state_restored(out_dir):
    """The validator changes nothing: names, selection, active object, mode, frame, engine are equal before and after."""
    scene = bpy.context.scene
    try:
        mat, tree, bsdf = new_mat("P23_S")
        tree.links.new(tex_node(tree, gen_image("p23_img", 16, 16)).outputs["Color"], bsdf.inputs["Roughness"])
        arm = make_armature("P23_Arm", 2, 1)
        ob = mesh_obj("P23_Obj", [mat, None], [0, 0, 0, 0, 0, 1])
        ob.modifiers.new("A", "ARMATURE").object = arm
        for o in scene.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        scene.frame_set(5)
        before = snapshot()
        res = validate(ob.name, max_materials=1, max_texture_px=8, max_bones=1)
        after = snapshot()
        scene.frame_set(1)
    finally:
        cleanup()
    assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert res["verdict"] == "FAIL"
    return {"verdict": res["verdict"]}


def main():
    args = _cli_args()
    out_dir = args.get("out_dir", ".")
    os.makedirs(out_dir, exist_ok=True)
    CONFIG.update(out_dir=out_dir, validate_script=args.get("validate_script"))
    checks, failed = {}, []
    tests = [test_p1_env_report_state_and_values, test_p1_enum_errors_and_args, test_p1_result_file,
             test_p2_material_slots, test_p2_material_images, test_p2_color_space, test_p3_max_materials,
             test_p3_max_texture_px, test_p3_max_bones, test_p3_bad_budget_args, test_p23_state_restored]
    if CONFIG["validate_script"]:  # old-script run: only the P2/P3 tests are meaningful
        tests = [t for t in tests if t.__name__.startswith(("test_p2", "test_p3", "test_p23"))]
    for fn in tests:
        try:
            takes_dir = fn.__code__.co_argcount == 1
            checks[fn.__name__] = {"ok": True, "data": fn(out_dir) if takes_dir else fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()[-1500:]}
            failed.append(fn.__name__)
            try:
                if bpy.context.object and bpy.context.object.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
            cleanup()
    report = {"blender": bpy.app.version_string, "passed": len(checks) - len(failed), "total": len(checks),
              "failed": failed, "checks": checks}
    with open(os.path.join(out_dir, "iter16_p_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    sys.exit(1 if failed else 0)


main()
