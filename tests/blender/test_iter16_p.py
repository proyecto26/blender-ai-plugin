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
CREATED = {"objects": [], "meshes": [], "materials": [], "images": [], "armatures": [], "node_groups": []}
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
    for key in ("meshes", "materials", "images", "armatures", "node_groups"):
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
    """P2: a face on an empty slot or beyond the slots FAILs the material_slots check. An empty slot no face uses
    passes material_slots, but the object's verdict is still FAIL because the existing `materials` check fails every
    empty slot (an unfilled slot is a defect of its own, whether or not a face uses it)."""
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
    unused_checks = res["objects"]["P2_UnusedEmpty"]["checks"]
    assert unused_checks["material_slots"]["status"] == "PASS" and unused_checks["materials"]["status"] == "FAIL", unused_checks
    assert res["objects"]["P2_UnusedEmpty"]["verdict"] == "FAIL"
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


def gn_set_material(ob, material, name="GN_SetMat"):
    """A Geometry Nodes modifier that sets every face of `ob` to `material`."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    CREATED["node_groups"].append(ng)
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin = ng.nodes.new("NodeGroupInput")
    gout = ng.nodes.new("NodeGroupOutput")
    setm = ng.nodes.new("GeometryNodeSetMaterial")
    setm.inputs["Material"].default_value = material
    ng.links.new(gin.outputs[0], setm.inputs["Geometry"])
    ng.links.new(setm.outputs["Geometry"], gout.inputs[0])
    mod = ob.modifiers.new("GN", "NODES")
    mod.node_group = ng
    return mod


def test_r1_evaluated_materials(out_dir):
    """Review 1: materials come from the evaluated mesh, so a Geometry Nodes Set Material is audited, not the slots."""
    try:
        folder = os.path.join(out_dir, "r1_img")
        os.makedirs(folder, exist_ok=True)
        orig, _, _ = new_mat("R1_Orig")
        img_missing, p_missing = file_image("r1_missing", folder)
        bad, btree, bbsdf = new_mat("R1_Bad")
        btree.links.new(tex_node(btree, img_missing).outputs["Color"], bbsdf.inputs["Base Color"])
        ob = mesh_obj("R1_Gn", [orig], [0] * 6)
        gn_set_material(ob, bad)
        big = gen_image("r1_big", 256, 256)
        big_mat, ttree, tbsdf = new_mat("R1_Big")
        ttree.links.new(tex_node(ttree, big).outputs["Color"], tbsdf.inputs["Base Color"])
        ob2 = mesh_obj("R1_GnBig", [orig], [0] * 6)
        gn_set_material(ob2, big_mat, "GN_SetMat2")
        os.remove(p_missing)
        res = run("validate_asset.py", {"objects": [ob.name, ob2.name], "prefix": "", "max_texture_px": 128,
                                        "max_materials": 1})
        images = check(res, "R1_Gn", "material_images")
        tex = check(res, "R1_GnBig", "budget_texture_px")
        mats = check(res, "R1_GnBig", "budget_materials")
    finally:
        cleanup()
    assert images["status"] == "FAIL" and "r1_missing" in images["detail"], images
    assert tex["status"] == "FAIL" and "256 px" in tex["detail"], tex
    assert mats["status"] == "PASS", mats
    return {"images": images["detail"], "texture": tex["detail"], "materials": mats["detail"]}


def test_r2_udim_movie_sequence_missing(out_dir):
    """Review 2: a UDIM, sequence or movie image whose files are not on disk FAILs unless packed; present ones pass."""
    try:
        folder = os.path.join(out_dir, "r2_img")
        os.makedirs(folder, exist_ok=True)
        cases = {}

        def case(key, img):
            mat, tree, bsdf = new_mat(f"R2_{key}")
            tree.links.new(tex_node(tree, img).outputs["Color"], bsdf.inputs["Base Color"])
            cases[key] = mesh_obj(f"R2_{key}", [mat], [0] * 6)

        def special(name, source, path):
            img = gen_image(name, 4, 4)
            img.source = source
            img.filepath = path
            return img
        gone = os.path.join(folder, "gone")
        case("udim_missing", special("r2_udim_missing", "TILED", gone + ".<UDIM>.png"))
        case("movie_missing", special("r2_movie_missing", "MOVIE", gone + ".mp4"))
        case("sequence_missing", special("r2_seq_missing", "SEQUENCE", gone + "_0001.png"))
        real, real_path = file_image("r2_real", folder)
        tile_path = os.path.join(folder, "tile.1001.png")
        os.replace(real_path, tile_path)
        TEMP_FILES.append(tile_path)
        case("udim_present", special("r2_udim_present", "TILED", os.path.join(folder, "tile.<UDIM>.png")))
        res = run("validate_asset.py", {"objects": [o.name for o in cases.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_images")["status"] for k, o in cases.items()}
        detail = {k: check(res, o.name, "material_images")["detail"] for k, o in cases.items()}
    finally:
        cleanup()
    assert got == {"udim_missing": "FAIL", "movie_missing": "FAIL", "sequence_missing": "FAIL",
                   "udim_present": "PASS"}, (got, detail)
    return {"statuses": got}


def test_r3_group_boundaries():
    """Review 3: colour-space tracing follows links through node groups, out of Group Output and into Group Input."""
    results = {}
    try:
        def make_group(name, inner):
            ng = bpy.data.node_groups.new(name, "ShaderNodeTree")
            CREATED["node_groups"].append(ng)
            ng.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
            ng.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
            gin, gout = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
            inner(ng, gin, gout)
            return ng

        def case(key, wire):
            mat, tree, bsdf = new_mat(f"R3_{key}")
            wire(tree, bsdf)
            results[key] = mesh_obj(f"R3_{key}", [mat], [0] * 6)

        def out_of_group(colorspace, socket):
            def wire(tree, bsdf):
                def inner(ng, gin, gout):
                    img = gen_image(f"r3_out_{colorspace}_{socket}", 8, 8, colorspace)
                    ng.links.new(tex_node(ng, img).outputs["Color"], gout.inputs[0])
                grp = tree.nodes.new("ShaderNodeGroup")
                grp.node_tree = make_group(f"R3G_out_{colorspace}_{socket}", inner)
                tree.links.new(grp.outputs[0], bsdf.inputs[socket])
            return wire

        def into_group(colorspace, socket):
            def wire(tree, bsdf):
                def inner(ng, gin, gout):
                    ng.links.new(gin.outputs[0], gout.inputs[0])
                grp = tree.nodes.new("ShaderNodeGroup")
                grp.node_tree = make_group(f"R3G_in_{colorspace}_{socket}", inner)
                img = gen_image(f"r3_in_{colorspace}_{socket}", 8, 8, colorspace)
                tree.links.new(tex_node(tree, img).outputs["Color"], grp.inputs[0])
                tree.links.new(grp.outputs[0], bsdf.inputs[socket])
            return wire
        case("bad_noncolor_out_of_group_base", out_of_group("Non-Color", "Base Color"))
        case("bad_srgb_out_of_group_roughness", out_of_group("sRGB", "Roughness"))
        case("bad_noncolor_into_group_base", into_group("Non-Color", "Base Color"))
        case("good_srgb_out_of_group_base", out_of_group("sRGB", "Base Color"))
        case("good_noncolor_into_group_roughness", into_group("Non-Color", "Roughness"))
        res = run("validate_asset.py", {"objects": [o.name for o in results.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_color_space")["status"] for k, o in results.items()}
    finally:
        cleanup()
    assert got == {k: ("WARN" if k.startswith("bad") else "PASS") for k in got}, got
    return got


def test_r4_registered_engines_only():
    """Review 4: the engine list holds registered engines (also indirect subclasses), not merely defined classes."""
    class Unreg(bpy.types.RenderEngine):
        bl_idname = "BAP_R4_UNREGISTERED"
        bl_label = "never registered"

    class Mid(bpy.types.RenderEngine):
        bl_idname = "BAP_R4_MID"
        bl_label = "mid"

    class Leaf(Mid):
        bl_idname = "BAP_R4_LEAF"
        bl_label = "leaf"
    bpy.utils.register_class(Leaf)
    try:
        engines = run("env_report.py", {"enums": []})["render_engines"]
    finally:
        bpy.utils.unregister_class(Leaf)
    assert "BAP_R4_UNREGISTERED" not in engines, engines
    assert "BAP_R4_LEAF" in engines, engines
    assert "CYCLES" in engines and "BLENDER_EEVEE" in engines, engines
    return {"engines": engines}


def test_s1_incomplete_udim_set(out_dir):
    """Round 2, 1: every declared UDIM tile must exist; one missing tile FAILs and the detail names its file."""
    try:
        folder = os.path.join(out_dir, "s1_img")
        os.makedirs(folder, exist_ok=True)
        cases = {}
        for key, present in (("partial", (1001,)), ("complete", (1001, 1002)), ("none", ())):
            for number in present:
                src, path = file_image(f"s1_{key}_{number}", folder)
                target = os.path.join(folder, f"{key}.{number}.png")
                os.replace(path, target)
                TEMP_FILES.append(target)
            img = gen_image(f"s1_{key}", 4, 4)
            img.source = "TILED"
            img.filepath = os.path.join(folder, key + ".<UDIM>.png")
            img.tiles.new(tile_number=1002)
            mat, tree, bsdf = new_mat(f"S1_{key}")
            tree.links.new(tex_node(tree, img).outputs["Color"], bsdf.inputs["Base Color"])
            cases[key] = mesh_obj(f"S1_{key}", [mat], [0] * 6)
        res = run("validate_asset.py", {"objects": [o.name for o in cases.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_images") for k, o in cases.items()}
    finally:
        cleanup()
    assert got["partial"]["status"] == "FAIL" and "partial.1002.png" in got["partial"]["detail"], got["partial"]
    assert "partial.1001.png" not in got["partial"]["detail"], got["partial"]
    assert got["complete"]["status"] == "PASS", got["complete"]
    assert got["none"]["status"] == "FAIL", got["none"]
    return {k: v["status"] for k, v in got.items()} | {"partial_detail": got["partial"]["detail"]}


def test_s2_linked_materials_same_name(out_dir):
    """Round 2, 2: two different linked materials both named Paint are two materials, not one."""
    libs = []
    try:
        folder = os.path.join(out_dir, "s2_libs")
        os.makedirs(folder, exist_ok=True)
        paths = []
        for tag in ("a", "b"):
            mat = bpy.data.materials.new("Paint")
            path = os.path.join(folder, f"lib_{tag}.blend")
            bpy.data.libraries.write(path, {mat}, fake_user=True)
            bpy.data.materials.remove(mat)
            paths.append(path)
        linked = []
        for path in paths:
            with bpy.data.libraries.load(path, link=True) as (src, dst):
                dst.materials = ["Paint"]
            linked.append(dst.materials[0])
        libs = [m.library for m in linked]
        assert linked[0] != linked[1] and linked[0].name == linked[1].name == "Paint", linked
        ob = mesh_obj("S2_Two", linked, [0, 0, 0, 1, 1, 1])
        one = mesh_obj("S2_One", [linked[0]], [0] * 6)
        res = run("validate_asset.py", {"objects": [ob.name, one.name], "prefix": "", "max_materials": 1})
        two_check = check(res, "S2_Two", "budget_materials")
        one_check = check(res, "S2_One", "budget_materials")
        ok = run("validate_asset.py", {"objects": [ob.name], "prefix": "", "max_materials": 2})
        at = check(ok, "S2_Two", "budget_materials")
    finally:
        cleanup()
        for m in [m for m in bpy.data.materials if m.library]:
            bpy.data.materials.remove(m)
        for lib in list(bpy.data.libraries):
            bpy.data.libraries.remove(lib)
    assert two_check["status"] == "FAIL" and "2 material" in two_check["detail"], two_check
    assert "lib_a.blend" in two_check["detail"] and "lib_b.blend" in two_check["detail"], two_check
    assert one_check["status"] == "PASS" and at["status"] == "PASS", (one_check, at)
    return {"two": two_check["detail"], "at_limit": at["detail"]}


def test_t1_image_sequence_frames(out_dir):
    """Round 3, 1: every frame an image sequence can sample must exist; the detail names the first missing files."""
    try:
        folder = os.path.join(out_dir, "t1_seq")
        os.makedirs(folder, exist_ok=True)
        cases = {}

        def sequence(key, present, duration, offset=0):
            for n in present:
                src, path = file_image(f"t1_{key}_{n}", folder)
                target = os.path.join(folder, f"{key}_{n:04d}.png")
                os.replace(path, target)
                TEMP_FILES.append(target)
            img = gen_image(f"t1_{key}", 4, 4)
            img.source = "SEQUENCE"
            img.filepath = os.path.join(folder, f"{key}_{1 + offset:04d}.png")
            mat, tree, bsdf = new_mat(f"T1_{key}")
            node = tex_node(tree, img)
            node.image_user.frame_duration = duration
            node.image_user.frame_offset = offset
            tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            cases[key] = mesh_obj(f"T1_{key}", [mat], [0] * 6)
        sequence("gap", (1, 3), 3)
        sequence("full", (1, 2, 3), 3)
        sequence("offset", (11, 12), 2, offset=10)
        sequence("short", (1, 2), 5)
        sequence("unknown", (1, 2), 0)
        res = run("validate_asset.py", {"objects": [o.name for o in cases.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_images") for k, o in cases.items()}
    finally:
        cleanup()
    assert got["gap"]["status"] == "FAIL" and "gap_0002.png" in got["gap"]["detail"], got["gap"]
    assert "gap_0001.png" not in got["gap"]["detail"] and "gap_0003.png" not in got["gap"]["detail"], got["gap"]
    assert got["full"]["status"] == "PASS" and got["offset"]["status"] == "PASS", got
    assert got["short"]["status"] == "FAIL" and "short_0003.png" in got["short"]["detail"], got["short"]
    assert got["unknown"]["status"] == "NOT_CHECKED", got["unknown"]
    return {k: v["status"] for k, v in got.items()} | {"gap_detail": got["gap"]["detail"]}


def test_t2_channel_split_and_math():
    """Round 3, 2: colour-space tracing continues through Separate Color/XYZ and single-value Math, Map Range, Clamp."""
    results = {}
    try:
        def case(key, wire):
            mat, tree, bsdf = new_mat(f"T2_{key}")
            wire(tree, bsdf)
            results[key] = mesh_obj(f"T2_{key}", [mat], [0] * 6)

        def orm(colorspace):
            def wire(tree, bsdf):
                sep = tree.nodes.new("ShaderNodeSeparateColor")
                tree.links.new(tex_node(tree, gen_image(f"t2_orm_{colorspace}", 8, 8, colorspace)).outputs["Color"],
                               sep.inputs["Color"])
                tree.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
                tree.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
            return wire

        def chain(colorspace, kind):
            def wire(tree, bsdf):
                node = tree.nodes.new({"math": "ShaderNodeMath", "range": "ShaderNodeMapRange",
                                       "clamp": "ShaderNodeClamp", "xyz": "ShaderNodeSeparateXYZ"}[kind])
                src = tex_node(tree, gen_image(f"t2_{kind}_{colorspace}", 8, 8, colorspace))
                if kind == "xyz":
                    tree.links.new(src.outputs["Color"], node.inputs[0])
                    tree.links.new(node.outputs["X"], bsdf.inputs["Roughness"])
                else:
                    tree.links.new(src.outputs["Color"], node.inputs[0] if kind == "math" else node.inputs["Value"])
                    tree.links.new(node.outputs[0], bsdf.inputs["Roughness"])
            return wire
        case("bad_srgb_orm", orm("sRGB"))
        case("bad_srgb_math", chain("sRGB", "math"))
        case("bad_srgb_map_range", chain("sRGB", "range"))
        case("bad_srgb_clamp", chain("sRGB", "clamp"))
        case("good_noncolor_orm", orm("Non-Color"))
        case("good_noncolor_math", chain("Non-Color", "math"))
        res = run("validate_asset.py", {"objects": [o.name for o in results.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_color_space")["status"] for k, o in results.items()}
    finally:
        cleanup()
    assert got == {k: ("WARN" if k.startswith("bad") else "PASS") for k in got}, got
    return got


def test_t3_sequence_extension_digits(out_dir):
    """Round 4: the frame number is the last digit group of the name WITHOUT its extension (smoke_0001.jp2 is not .jp1)."""
    try:
        folder = os.path.join(out_dir, "t3_seq")
        os.makedirs(folder, exist_ok=True)
        cases = {}
        for key, present in (("complete", (1, 2)), ("gap", (1,))):
            for n in present:
                path = os.path.join(folder, f"{key}_{n:04d}.jp2")
                with open(path, "wb") as fh:
                    fh.write(b"x")
                TEMP_FILES.append(path)
            img = gen_image(f"t3_{key}", 4, 4)
            img.source = "SEQUENCE"
            img.filepath = os.path.join(folder, f"{key}_0001.jp2")
            mat, tree, bsdf = new_mat(f"T3_{key}")
            node = tex_node(tree, img)
            node.image_user.frame_duration = 2
            tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            cases[key] = mesh_obj(f"T3_{key}", [mat], [0] * 6)
        res = run("validate_asset.py", {"objects": [o.name for o in cases.values()], "prefix": ""})
        got = {k: check(res, o.name, "material_images") for k, o in cases.items()}
    finally:
        cleanup()
    assert got["complete"]["status"] == "PASS", got["complete"]
    assert got["gap"]["status"] == "FAIL" and "gap_0002.jp2" in got["gap"]["detail"] and ".jp1" not in got["gap"]["detail"], got["gap"]
    return {k: v["status"] for k, v in got.items()}


def main():
    args = _cli_args()
    out_dir = args.get("out_dir", ".")
    os.makedirs(out_dir, exist_ok=True)
    CONFIG.update(out_dir=out_dir, validate_script=args.get("validate_script"))
    checks, failed = {}, []
    tests = [test_p1_env_report_state_and_values, test_p1_enum_errors_and_args, test_p1_result_file,
             test_p2_material_slots, test_p2_material_images, test_p2_color_space, test_p3_max_materials,
             test_p3_max_texture_px, test_p3_max_bones, test_p3_bad_budget_args, test_p23_state_restored,
             test_r1_evaluated_materials, test_r2_udim_movie_sequence_missing, test_r3_group_boundaries,
             test_r4_registered_engines_only,
             test_s1_incomplete_udim_set, test_s2_linked_materials_same_name,
             test_t1_image_sequence_frames, test_t2_channel_split_and_math,
             test_t3_sequence_extension_digits]
    if CONFIG["validate_script"]:  # old-script run: only the P2/P3 tests are meaningful
        tests = [t for t in tests if t.__name__.startswith(("test_p2", "test_p3", "test_p23", "test_r", "test_s", "test_t")) and t.__name__ != "test_r4_registered_engines_only"]
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
