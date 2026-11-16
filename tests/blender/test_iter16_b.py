"""Headless Blender tests for iteration 16, batch B (B1 bake_maps controls, B2 + B3 animation bake_check).

  B1  bake_maps   DirectX green = 1 - OpenGL green; metallic (plain and linked) by temporary emission; ORM equals the
                  separate maps; several high-poly sources; cage / ray distance / UV map set during the bake and put
                  back; collisions refused without overwrite; nodes identical after a bake that fails midway
  B2  bake_check  the baked action alone reproduces the source: good bake PASS; wrong keys masked by a Copy Rotation
                  constraint or by a driver FAIL; another rest orientation PASS; piston without location keys FAIL;
                  hydraulic (Stretch To) without scale keys FAIL; no keys / no action FAIL; state restored
  B3  bake_check  loop seam: pose and velocity at the seam, root_motion; boundary fixtures at 0.5x and 1.5x each limit

Run (a NEW out_dir every time):
    blender -b --factory-startup --python tests/blender/test_iter16_b.py -- '{"out_dir": "/tmp/iter16-b"}'
Optional "skills_dir" points at another copy of the skills tree (used to see the B1 tests fail on the old script).
Writes <out_dir>/iter16_b_report.json with passed / total / failed / checks / measured; exits 1 on a failure.
"""
import json
import math
import os
import runpy
import subprocess
import sys
import traceback

import bpy
import numpy as np
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
ARGS = {}
if "--" in sys.argv:
    raw = sys.argv[sys.argv.index("--") + 1:]
    if raw:
        ARGS = json.loads(raw[0])
SKILLS = ARGS.get("skills_dir") or os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
OUT = ARGS.get("out_dir", ".")
# Every file the tests write goes to a folder only this process uses: bake_maps refuses existing output files, so a
# reused out_dir or two runs sharing one would otherwise fail on files left by the other.
WORK = os.path.join(OUT, f"work_{os.getpid()}")
MEASURED = {}


def script(skill, name):
    return os.path.join(SKILLS, skill, "scripts", name)


def run(skill, name, **kw):
    return runpy.run_path(script(skill, name), init_globals={"ARGS": kw}, run_name="__skill_test__")["result"]


def bake(**kw):
    return run("texture-workflow", "bake_maps.py", **kw)


def check(**kw):
    return run("animation", "bake_check.py", **kw)


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def finished(r):
    assert "FINISHED" in r, r


# ======================================================================================== B1 fixtures
class Hook:
    """Proxy for bpy.ops.<group>.<op>: `fn(call_number, kwargs)` returns a result set to fake it, or None to call through."""

    def __init__(self, real, group, op, fn):
        self._real, self.calls = real, 0
        outer = self

        class _Group:
            def __getattr__(g, n):
                if n == op:
                    def fake(*a, **kw):
                        outer.calls += 1
                        r = fn(outer.calls, kw)
                        return r if r is not None else getattr(getattr(real.ops, group), op)(*a, **kw)
                    return fake
                return getattr(getattr(real.ops, group), n)

        class _Ops:
            def __getattr__(o, n):
                return _Group() if n == group else getattr(real.ops, n)

        self.ops = _Ops()

    def __getattr__(self, n):
        return getattr(self._real, n)


def with_hook(group, op, fn, go):
    real = sys.modules["bpy"]
    hook = Hook(real, group, op, fn)
    sys.modules["bpy"] = hook
    try:
        return go(), hook
    finally:
        sys.modules["bpy"] = real


def pbr(name, metallic=0.0, rough=0.5, base=(0.8, 0.8, 0.8, 1.0)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    p.inputs["Base Color"].default_value = base
    return m


def plane(name, size=2.0, loc=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    return o


def bumpy_high(name="HP_Low", z=0.0):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=16, y_subdivisions=16, size=2, location=(0, 0, z))
    o = bpy.context.object
    o.name = name
    for v in o.data.vertices:
        v.co.z = 0.06 * math.sin(3 * v.co.x) * math.cos(3 * v.co.y)
    return o


def read_png(path):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        arr = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(arr)
        return arr.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)


def _val(v):
    try:
        return tuple(round(float(x), 5) for x in v)
    except TypeError:
        return round(float(v), 5) if isinstance(v, (int, float)) else None


def node_sig():
    sig = {}
    for m in bpy.data.materials:
        t = m.node_tree
        if t is None:
            continue
        nodes = sorted((n.name, n.bl_idname, bool(n.select),
                        tuple(_val(s.default_value) if hasattr(s, "default_value") else None for s in n.inputs))
                       for n in t.nodes if n.name != "SK_BakeTarget")
        links = sorted((lk.from_node.name, lk.from_socket.identifier, lk.to_node.name, lk.to_socket.identifier,
                        lk.is_muted) for lk in t.links)
        sig[m.name] = {"nodes": nodes, "links": links, "active": t.nodes.active.name if t.nodes.active else None}
    return sig


def bake_state():
    scene = bpy.context.scene
    b = scene.render.bake
    return {"engine": scene.render.engine, "samples": scene.cycles.samples, "sel": sorted(o.name for o in scene.objects if o.select_get()),
            "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            "bake": (b.use_selected_to_active, round(b.cage_extrusion, 5), b.margin, b.use_cage,
                     b.cage_object.name if b.cage_object else None, round(b.max_ray_distance, 5))}


# ======================================================================================== B1 tests
def test_b1_directx_green_is_flipped_opengl():
    fresh()
    plane("SM_Low")
    bumpy_high()
    o1, o2 = os.path.join(WORK, "nrm_gl"), os.path.join(WORK, "nrm_dx")
    r1 = bake(low="SM_Low", high="HP_Low", maps=["normal"], size=32, extrusion=0.3, samples=1, out_dir=o1)
    r2 = bake(low="SM_Low", high="HP_Low", maps=["normal"], size=32, extrusion=0.3, samples=1, out_dir=o2,
              normal_convention="DIRECTX", overwrite=True)
    gl, dx = read_png(r1["images"][0]), read_png(r2["images"][0])
    assert np.ptp(gl[..., 1]) > 0.02, "the OpenGL green channel is flat: the test would prove nothing"
    err_g = float(np.abs(dx[..., 1] - (1.0 - gl[..., 1])).max())
    err_rb = float(np.abs(dx[..., [0, 2]] - gl[..., [0, 2]]).max())
    assert err_g <= 1 / 255 and err_rb <= 1 / 255, (err_g, err_rb)
    assert r1["normal_convention"] == "OPENGL" and r2["normal_convention"] == "DIRECTX"
    MEASURED["b1_directx_green_err"] = round(err_g, 6)
    return {"green_err": err_g, "rb_err": err_rb, "green_range": float(np.ptp(gl[..., 1]))}


def test_b1_metallic_plain_and_linked_nodes_restored():
    fresh()
    low = plane("SM_Low")
    mat = pbr("MAT_A", metallic=0.75)
    low.data.materials.append(mat)
    before = node_sig()
    r = bake(low="SM_Low", maps=["metallic"], size=32, samples=1, out_dir=os.path.join(WORK, "met_a"))
    px = read_png(r["images"][0])
    assert abs(float(px[..., 0].mean()) - 0.75) < 3 / 255, px[..., 0].mean()
    assert node_sig() == before, "nodes changed beyond the SK_BakeTarget image node"
    # linked: a Value node feeds Metallic
    fresh()
    low = plane("SM_Low")
    mat = pbr("MAT_B", metallic=1.0)
    low.data.materials.append(mat)
    nt = mat.node_tree
    val = nt.nodes.new("ShaderNodeValue")
    val.outputs[0].default_value = 0.4
    nt.links.new(val.outputs[0], nt.nodes["Principled BSDF"].inputs["Metallic"])
    before = node_sig()
    r = bake(low="SM_Low", maps=["metallic"], size=32, samples=1, out_dir=os.path.join(WORK, "met_b"))
    px = read_png(r["images"][0])
    assert abs(float(px[..., 0].mean()) - 0.4) < 3 / 255, px[..., 0].mean()
    assert node_sig() == before, "linked metallic: nodes or links changed"
    assert "SK_BakeMetallic" not in nt.nodes
    return {"plain": 0.75, "linked": 0.4}


def test_b1_orm_channels_equal_separate_maps():
    fresh()
    low = plane("SM_Low")
    low.data.materials.append(pbr("MAT_O", metallic=0.75, rough=0.3))
    r = bake(low="SM_Low", maps=["ao"], orm=True, size=32, samples=2, out_dir=os.path.join(WORK, "orm"))
    names = {os.path.basename(p) for p in r["images"]}
    assert names == {"T_Low_Ao.png", "T_Low_Roughness.png", "T_Low_Metallic.png", "T_Low_Orm.png"}, names
    d = os.path.join(WORK, "orm")
    ao, ro, me, orm = (read_png(os.path.join(d, f"T_Low_{k}.png")) for k in ("Ao", "Roughness", "Metallic", "Orm"))
    errs = [float(np.abs(orm[..., c] - src[..., 0]).max()) for c, src in enumerate((ao, ro, me))]
    assert max(errs) <= 1.5 / 255, errs
    assert abs(float(me[..., 0].mean()) - 0.75) < 3 / 255 and abs(float(ro[..., 0].mean()) - 0.3) < 3 / 255
    assert float(ao[..., 0].mean()) > 0.9
    return {"channel_errs": errs}


def test_b1_nodes_identical_when_a_bake_fails_midway():
    out = {}
    for fail_at in (1, 3):
        fresh()
        low = plane("SM_Low")
        mat = pbr("MAT_F", metallic=1.0)
        low.data.materials.append(mat)
        nt = mat.node_tree
        val = nt.nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 0.4
        nt.links.new(val.outputs[0], nt.nodes["Principled BSDF"].inputs["Metallic"])
        before, state = node_sig(), bake_state()
        seen = {}

        def fn(n, kw):
            seen[n] = "SK_BakeMetallic" in nt.nodes
            return {"CANCELLED"} if n == fail_at else None

        def go():
            try:
                bake(low="SM_Low", maps=["ao"], orm=True, size=16, samples=1,
                     out_dir=os.path.join(WORK, f"fail_{fail_at}"))
            except RuntimeError as exc:
                return exc
        exc, hook = with_hook("object", "bake", fn, go)
        assert exc is not None and "CANCELLED" in str(exc), exc
        assert hook.calls == fail_at, hook.calls
        if fail_at == 3:
            assert seen[3] is True, "the metallic wiring was not in place when the failure was injected"
        assert node_sig() == before, f"fail_at={fail_at}: nodes changed"
        assert "SK_BakeTarget" not in nt.nodes and "SK_BakeMetallic" not in nt.nodes
        assert not [i.name for i in bpy.data.images if i.name.startswith("T_Low")], [i.name for i in bpy.data.images]
        assert bake_state() == state, (bake_state(), state)
        out[f"fail_at_{fail_at}"] = "identical"
    return out


def test_b1_collisions_refused_without_overwrite():
    fresh()
    plane("SM_Low")
    d = os.path.join(WORK, "coll")
    existing = bpy.data.images.new("T_Low_Ao", 16, 16)
    existing.pixels.foreach_set([0.5] * (16 * 16 * 4))
    sig = node_sig()
    state = bake_state()
    for size in (16, 32):
        try:
            bake(low="SM_Low", maps=["ao"], size=size, samples=1, out_dir=d)
        except ValueError as exc:
            assert "T_Low_Ao" in str(exc) and "overwrite" in str(exc), exc
        else:
            raise AssertionError(f"an existing image of the target name was accepted at size {size}")
        px = np.empty(16 * 16 * 4, dtype=np.float32)
        existing.pixels.foreach_get(px)
        assert np.allclose(px, 0.5, atol=0.01), "the existing image was modified"
        assert tuple(existing.size) == (16, 16)
        assert node_sig() == sig and bake_state() == state
        assert not os.path.exists(os.path.join(d, "T_Low_Ao.png"))
    # overwrite=True reuses the same datablock
    r = bake(low="SM_Low", maps=["ao"], size=32, samples=1, out_dir=d, overwrite=True)
    assert bpy.data.images["T_Low_Ao"].session_uid == existing.session_uid and tuple(existing.size) == (32, 32), tuple(existing.size)
    assert os.path.exists(r["images"][0]) and r["overwrite"] is True
    # an existing output file is refused, then replaced with overwrite=True
    bpy.data.images.remove(existing)
    try:
        bake(low="SM_Low", maps=["ao"], size=32, samples=1, out_dir=d)
    except ValueError as exc:
        assert "T_Low_Ao.png" in str(exc), exc
    else:
        raise AssertionError("an existing output file was overwritten without overwrite=True")
    bake(low="SM_Low", maps=["ao"], size=32, samples=1, out_dir=d, overwrite=True)
    return {"refused": "image at 16 and 32, file", "reused": True}


def test_b1_several_high_sources():
    fresh()
    plane("SM_Low", size=2.0)
    for name, x, col in (("HP_Red", -0.5, (1, 0, 0, 1)), ("HP_Green", 0.5, (0, 1, 0, 1))):
        o = plane(name, size=2.0, loc=(x, 0, 0.01), scale=(0.5, 1, 1))
        o.data.materials.append(pbr("MAT_" + name, base=col))
    r = bake(low="SM_Low", high=["HP_Red", "HP_Green"], maps=["diffuse"], size=32, extrusion=0.1, samples=1,
             out_dir=os.path.join(WORK, "multi"))
    assert r["high"] == ["HP_Red", "HP_Green"] and r["selected_to_active"] is True, r
    px = np.empty(0)
    img = bpy.data.images.load(r["images"][0], check_existing=False)
    try:
        arr = np.empty(32 * 32 * 4, dtype=np.float32)
        img.pixels.foreach_get(arr)
        px = arr.reshape(32, 32, 4)
    finally:
        bpy.data.images.remove(img)
    left, right = px[16, 8], px[16, 24]
    assert left[0] > 0.7 and left[1] < 0.3, left
    assert right[1] > 0.7 and right[0] < 0.3, right
    return {"left": [round(float(c), 3) for c in left], "right": [round(float(c), 3) for c in right]}


def test_b1_cage_ray_distance_and_uv_layer_set_and_restored():
    fresh()
    low = plane("SM_Low")
    bumpy_high()
    cage = low.copy()
    cage.data = low.data.copy()
    cage.name = "CG_Low"
    cage.location.z = 0.2
    bpy.context.scene.collection.objects.link(cage)
    other = low.copy()
    other.name = "Other"
    bpy.context.scene.collection.objects.link(other)
    uv2 = low.data.uv_layers.new(name="Second")
    for i, loop in enumerate(low.data.uv_layers[0].data):
        uv2.data[i].uv = (loop.uv[0] * 0.1, loop.uv[1] * 0.1)
    low.data.uv_layers.active = low.data.uv_layers[0]
    b = bpy.context.scene.render.bake
    b.use_cage, b.cage_object, b.max_ray_distance = True, other, 1.5
    state = bake_state()
    seen = {}

    def fn(n, kw):
        bk = bpy.context.scene.render.bake
        seen.update(use_cage=bk.use_cage, cage=bk.cage_object.name if bk.cage_object else None,
                    ray=round(bk.max_ray_distance, 4), uv=low.data.uv_layers.active.name, s2a=bk.use_selected_to_active)

    r, hook = with_hook("object", "bake", fn, lambda: bake(
        low="SM_Low", high="HP_Low", cage="CG_Low", max_ray_distance=0.5, uv_layer="Second", maps=["normal"],
        size=32, samples=1, out_dir=os.path.join(WORK, "ctl")))
    assert seen == {"use_cage": True, "cage": "CG_Low", "ray": 0.5, "uv": "Second", "s2a": True}, seen
    assert bake_state() == state and low.data.uv_layers.active.name == UVNAME(low), (bake_state(), state)
    assert r["cage"] == "CG_Low" and r["uv_layer"] == "Second"
    for kw, text in (({"cage": "CG_Low"}, "cage needs a high"), ({"uv_layer": "Nope"}, "no UV map named"),
                     ({"normal_convention": "DX"}, "normal_convention"), ({"high": "HP_Missing"}, "not found")):
        args = dict(low="SM_Low", maps=["ao"], size=16, samples=1, out_dir=os.path.join(WORK, "ctl_bad"))
        args.update(kw)
        try:
            bake(**args)
        except ValueError as exc:
            assert text in str(exc), (kw, exc)
        else:
            raise AssertionError(f"{kw} was accepted")
    assert bake_state() == state
    return {"seen": seen}


def UVNAME(obj):
    return obj.data.uv_layers[0].name


def test_b1_uv_layer_chooses_the_bake_target_area():
    fresh()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.object
    cube.name = "SM_Low"
    uv2 = cube.data.uv_layers.new(name="Small")
    for i, loop in enumerate(cube.data.uv_layers[0].data):
        uv2.data[i].uv = (loop.uv[0] * 0.1, loop.uv[1] * 0.1)
    cube.data.uv_layers.active = cube.data.uv_layers[0]
    cov = {}
    for layer in (None, "Small"):
        r = bake(low="SM_Low", maps=["ao"], size=64, samples=2, uv_layer=layer, overwrite=True,
                 out_dir=os.path.join(WORK, f"uvl_{layer}"))
        cov[layer] = float((read_png(r["images"][0])[..., 0] > 0.5).mean())
        assert cube.data.uv_layers.active.name == cube.data.uv_layers[0].name
    assert cov[None] > 3 * cov["Small"] and cov["Small"] < 0.15, cov
    return {"coverage": cov}


# ======================================================================================== B2 / B3 fixtures
K = math.radians(4)
CHAIN = [("root", (0, 0, 0), (0, 0, 0.3), None), ("spine", (0, 0, 0.3), (0, 0, 0.6), "root"),
         ("arm", (0, 0, 0.6), (0, 0, 1.0), "spine")]
HYD = [("root", (0, 0, 0), (0, 0, 0.3), None), ("cyl", (0, 0, 0.3), (0, 0, 0.6), "root"),
       ("tip", (0, 0, 0.6), (0, 0, 1.0), "root")]


def make_rig(name, bones=CHAIN, roll=None, scale=1.0):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    for o in bpy.context.view_layer.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    finished(bpy.ops.object.mode_set(mode="EDIT"))
    eb = {}
    for bn, head, tail, parent in bones:
        b = data.edit_bones.new(bn)
        b.head, b.tail = tuple(c * scale for c in head), tuple(c * scale for c in tail)
        if roll and bn in roll:
            b.roll = math.radians(roll[bn])
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
        eb[bn] = b
    finished(bpy.ops.object.mode_set(mode="OBJECT"))
    for pb in obj.pose.bones:
        pb.rotation_mode = "XYZ"
    return obj


def put_keys(obj, aname, keys, frames):
    """keys: {bone: fn(frame) -> {"loc": v3, "eul": v3, "scale": v3}}; keys every frame in `frames`."""
    ad = obj.animation_data or obj.animation_data_create()
    act = bpy.data.actions.new(aname)
    ad.action = act
    for f in frames:
        for bone, fn in keys.items():
            d = fn(f)
            pb = obj.pose.bones[bone]
            for key, prop in (("loc", "location"), ("eul", "rotation_euler"), ("scale", "scale")):
                if key in d:
                    setattr(pb, prop, d[key])
                    pb.keyframe_insert(prop, frame=f)
    for pb in obj.pose.bones:
        pb.location, pb.rotation_euler, pb.scale = (0, 0, 0), (0, 0, 0), (1, 1, 1)
    return act


def scenario(src_keys, tgt_keys, frames=range(1, 12), tgt_roll=None, bones=CHAIN, tgt_scale=1.0, tgt_scale_loc=1.0,
             src_setup=None, src_roll=None):
    """A source rig playing `src_keys` and a target rig carrying the baked action AN_baked (not assigned)."""
    fresh()
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = min(frames), max(frames)
    src, tgt = make_rig("SRC", bones, roll=src_roll), make_rig("TGT", bones, roll=tgt_roll, scale=tgt_scale)
    if src_setup:
        src_setup(src)
    put_keys(src, "AN_src", src_keys, frames)
    if callable(tgt_keys):
        tgt_keys = tgt_keys(src, tgt, frames)
    put_keys(tgt, "AN_baked", tgt_keys, frames).use_fake_user = True
    tgt.animation_data.action = None
    bpy.context.scene.frame_set(min(frames))
    return src, tgt


def rotx(f):
    return {"eul": ((f - 1) * K, 0.0, 0.0)}


def lift(f):
    return {"loc": (0.0, 0.1 * (f - 1) / 10, 0.0)}


GOOD = {"arm": rotx, "spine": lift}


def sampled(bone, parts=("loc", "eul", "scale")):
    """Factory: the basis of `bone` on the target that reproduces the source's evaluated pose, per frame."""
    def make(src, tgt, frames):
        table, prev = {}, None
        for f in frames:
            bpy.context.scene.frame_set(f)
            bpy.context.view_layer.update()
            ev = src.evaluated_get(bpy.context.evaluated_depsgraph_get())
            rs, rt = src.data.bones[bone].matrix_local, tgt.data.bones[bone].matrix_local
            d = ev.pose.bones[bone].matrix @ rs.inverted()
            b = rt.inverted() @ d @ rt
            loc, quat, sc = b.decompose()
            prev = quat.to_euler("XYZ", prev) if prev is not None else quat.to_euler("XYZ")
            table[f] = {"loc": tuple(loc), "eul": tuple(prev), "scale": tuple(sc)}
        return {bone: lambda f: {k: v for k, v in table[f].items() if k in parts}}
    return make


def combine(*factories_or_dicts):
    def make(src, tgt, frames):
        out = {}
        for item in factories_or_dicts:
            out.update(item(src, tgt, frames) if callable(item) else item)
        return out
    return make


def verdicts(res):
    return {b: v["verdict"] for b, v in res["bones"].items()}


def worst(res, kind):
    return max(v[kind]["max"] for v in res["bones"].values())


def margin_ok(good, limit, bad):
    gap = bad - good
    return limit - good >= 0.2 * gap - 1e-9 and bad - limit >= 0.2 * gap - 1e-9


def baked(**kw):
    return check(source="SRC", target="TGT", action="AN_baked", **kw)


# ======================================================================================== B2 tests
def test_b2_correct_bake_passes():
    scenario(GOOD, GOOD)
    res = baked()
    assert res["verdict"] == "PASS" and set(verdicts(res).values()) == {"PASS"}, res
    assert all(v["keyed"] for b, v in res["bones"].items() if b != "root") and res["frames"] == [1, 11]
    MEASURED["b2_good"] = {k: worst(res, k) for k in ("rotation", "translation", "scale")}
    assert max(MEASURED["b2_good"].values()) < 0.001
    return MEASURED["b2_good"]


def test_b2_wrong_keys_fail_and_nothing_is_masked_by_the_target():
    wrong = {"arm": lambda f: {"eul": (-(f - 1) * K, 0.0, 0.0)}, "spine": lift}
    src, tgt = scenario(GOOD, wrong)
    res = baked()
    assert res["verdict"] == "FAIL" and res["bones"]["arm"]["rotation"]["verdict"] == "FAIL", res["bones"]["arm"]
    MEASURED["b2_wrong_rotation_deg"] = res["bones"]["arm"]["rotation"]["max"]
    assert abs(res["bones"]["arm"]["rotation"]["max"] - 80.0) < 0.5, res["bones"]["arm"]["rotation"]
    out = {"plain": res["bones"]["arm"]["rotation"]["max"]}
    # masked by a Copy Rotation constraint on the target: the raw evaluation looks right, the check still FAILs
    c = tgt.pose.bones["arm"].constraints.new("COPY_ROTATION")
    c.target, c.subtarget = src, "arm"
    tgt.animation_data.action = bpy.data.actions["AN_baked"]
    tgt.animation_data.action_slot = tgt.animation_data.action_suitable_slots[0]
    bpy.context.scene.frame_set(11)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    raw = (src.evaluated_get(dg).pose.bones["arm"].matrix.to_3x3() - tgt.evaluated_get(dg).pose.bones["arm"].matrix.to_3x3())
    assert max(abs(x) for r in raw for x in r) < 1e-3, "the constraint does not mask the wrong action: the fixture is wrong"
    tgt.animation_data.action = None
    bpy.context.scene.frame_set(1)
    res = baked()
    assert res["verdict"] == "FAIL" and res["bones"]["arm"]["rotation"]["verdict"] == "FAIL", res["bones"]["arm"]
    assert c.mute is False, "the constraint was left muted"
    out["constraint_masked"] = res["bones"]["arm"]["rotation"]["max"]
    return out


def test_b2_wrong_keys_masked_by_a_driver_fail():
    wrong = {"arm": lambda f: {"eul": (0.0, 0.0, 0.0)}, "spine": lift}
    src, tgt = scenario(GOOD, wrong)
    fc = tgt.pose.bones["arm"].driver_add("rotation_euler", 0)
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = f"(frame-1)*{K!r}"
    tgt.animation_data.action = bpy.data.actions["AN_baked"]
    tgt.animation_data.action_slot = tgt.animation_data.action_suitable_slots[0]
    bpy.context.scene.frame_set(11)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    raw = (src.evaluated_get(dg).pose.bones["arm"].matrix.to_3x3() - tgt.evaluated_get(dg).pose.bones["arm"].matrix.to_3x3())
    assert max(abs(x) for r in raw for x in r) < 1e-3, "the driver does not mask the wrong action: the fixture is wrong"
    tgt.animation_data.action = None
    bpy.context.scene.frame_set(1)
    res = baked()
    assert res["verdict"] == "FAIL" and res["bones"]["arm"]["rotation"]["verdict"] == "FAIL", res["bones"]["arm"]
    assert fc.mute is False, "the driver was left muted"
    return {"rotation_deg": res["bones"]["arm"]["rotation"]["max"]}


def test_b2_different_rest_orientation_passes():
    roll = {"arm": 90.0}
    src, tgt = scenario(GOOD, combine({"spine": lift}, sampled("arm", parts=("eul",))), tgt_roll=roll)
    diff = tgt.data.bones["arm"].matrix_local - src.data.bones["arm"].matrix_local
    assert max(abs(x) for r in diff for x in r) > 0.5, "the rest orientations do not differ"
    res = baked()
    assert res["verdict"] == "PASS", res["bones"]["arm"]
    out = {"rotation": res["bones"]["arm"]["rotation"]["max"]}
    # copying the source's local keys into the rolled bone is a real bug and must FAIL
    scenario(GOOD, GOOD, tgt_roll=roll)
    res2 = baked()
    assert res2["verdict"] == "FAIL" and res2["bones"]["arm"]["rotation"]["verdict"] == "FAIL", res2["bones"]["arm"]
    out["naive_copy"] = res2["bones"]["arm"]["rotation"]["max"]
    return out


def test_b2_rig_of_another_height_passes_with_scaled_translation():
    bigger = {"arm": rotx, "spine": lambda f: {"loc": (0.0, 0.2 * (f - 1) / 10, 0.0)}}
    scenario(GOOD, bigger, tgt_scale=2.0)
    res = baked()
    assert res["verdict"] == "PASS" and abs(res["rig_height"]["ratio"] - 2.0) < 1e-3, res
    smaller = {"arm": rotx, "spine": lift}
    scenario(GOOD, smaller, tgt_scale=2.0)  # forgot to scale the translation: 0.1 instead of 0.2
    res2 = baked()
    assert res2["verdict"] == "FAIL" and res2["bones"]["spine"]["translation"]["verdict"] == "FAIL", res2
    return {"ratio": res["rig_height"]["ratio"], "unscaled_translation": res2["bones"]["spine"]["translation"]["max"]}


def test_b2_piston_without_location_keys_fails():
    piston = {"spine": lift, "arm": lambda f: {"eul": (0.0, 0.0, 0.0)}}
    scenario(piston, piston)
    assert baked()["verdict"] == "PASS"
    scenario(piston, {"arm": lambda f: {"eul": (0.0, 0.0, 0.0)}})  # the bake lost the location keys
    res = baked()
    assert res["verdict"] == "FAIL" and res["bones"]["spine"]["translation"]["verdict"] == "FAIL", res
    assert res["bones"]["spine"]["rotation"]["verdict"] == "PASS" and res["bones"]["spine"]["scale"]["verdict"] == "PASS"
    MEASURED["b2_piston_translation_frac"] = res["bones"]["spine"]["translation"]["max"]
    assert abs(res["bones"]["spine"]["translation"]["max"] - 0.1) < 0.005
    return {"translation": res["bones"]["spine"]["translation"]["max"]}


def _hydraulic(parts):
    def setup(src):
        c = src.pose.bones["cyl"].constraints.new("STRETCH_TO")
        c.target, c.subtarget = src, "tip"
    keys = {"tip": lambda f: {"loc": (0.0, 0.3 * (f - 1) / 10, 0.0)}}
    return scenario(keys, combine(sampled("cyl", parts=parts), sampled("tip", parts=("loc",))), bones=HYD,
                    src_setup=setup)


def test_b2_hydraulic_bake_without_scale_keys_fails():
    src, _tgt = _hydraulic(("loc", "eul", "scale"))
    bpy.context.scene.frame_set(11)
    bpy.context.view_layer.update()
    sy = src.evaluated_get(bpy.context.evaluated_depsgraph_get()).pose.bones["cyl"].matrix.to_scale()
    assert sy[1] > 1.8, f"the Stretch To fixture does not stretch: {tuple(sy)}"
    res = baked()
    assert res["verdict"] == "PASS", res["bones"]
    _hydraulic(("loc", "eul"))
    res2 = baked()
    assert res2["verdict"] == "FAIL" and res2["bones"]["cyl"]["scale"]["verdict"] == "FAIL", res2["bones"]["cyl"]
    MEASURED["b2_hydraulic_scale_rel"] = res2["bones"]["cyl"]["scale"]["max"]
    return {"stretch_y": round(sy[1], 3), "lost_scale_rel": res2["bones"]["cyl"]["scale"]["max"]}


def test_b2_no_action_or_no_keys_is_fail_not_pass():
    scenario(GOOD, GOOD)
    res = check(source="SRC", target="TGT", action="AN_missing")
    assert res["verdict"] == "FAIL" and res["bones"] == {} and any("does not exist" in n for n in res["notes"]), res
    bpy.data.actions.new("AN_empty")
    res2 = check(source="SRC", target="TGT", action="AN_empty")
    assert res2["verdict"] == "FAIL" and res2["bones"] == {} and any("nothing measured" in n or "measured nothing" in n for n in res2["notes"]), res2
    only_root = {"root": lambda f: {"loc": (0.0, 0.0, 0.0)}}
    scenario(GOOD, only_root)
    res3 = baked()  # keys exist, but the moving bones have none: measured, mismatch, FAIL
    assert res3["verdict"] == "FAIL" and res3["bones"]["arm"]["keyed"] is False, res3
    res4 = baked(bone_map={"arm": "spine", "spine": "arm"})
    assert res4["verdict"] == "FAIL"
    return {"notes": res["notes"] + res2["notes"]}


def test_b2_bad_arguments_raise_without_a_result_file():
    scenario(GOOD, GOOD)
    path = os.path.join(WORK, "bad_args.json")
    for kw in ({"source": "NOPE"}, {"bone_map": {"nope": "arm"}}, {"target": "SRC"}):
        args = dict(source="SRC", target="TGT", action="AN_baked", result_path=path, run_id="x")
        args.update(kw)
        try:
            check(**args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{kw} was accepted")
    assert not os.path.exists(path) and not os.path.exists(path + ".tmp"), "a result file exists after an exception"
    return {"file": None}


def tgt_state(src, tgt):
    ad = tgt.animation_data
    return {"action": ad.action.name if ad.action else None, "slot": ad.action_slot.identifier if ad.action_slot else None,
            "infl": ad.action_influence, "blend": ad.action_blend_type, "use_nla": ad.use_nla,
            "tracks": [(t.name, t.mute) for t in ad.nla_tracks],
            "drivers": [(fc.data_path, fc.array_index, fc.mute) for fc in ad.drivers],
            "cons": [(pb.name, c.name, c.mute, c.influence) for pb in tgt.pose.bones for c in pb.constraints],
            "bones": {pb.name: (pb.rotation_mode, tuple(pb.location), tuple(pb.rotation_euler), tuple(pb.scale))
                      for pb in tgt.pose.bones},
            "pose": (src.data.pose_position, tgt.data.pose_position), "frame": bpy.context.scene.frame_current,
            "actions": sorted(a.name for a in bpy.data.actions), "action_users": {a.name: a.users for a in bpy.data.actions}}


def test_b2_state_restored_also_on_failure():
    wrong = {"arm": lambda f: {"eul": (-(f - 1) * K, 0.0, 0.0)}, "spine": lift}
    src, tgt = scenario(GOOD, wrong)
    c = tgt.pose.bones["arm"].constraints.new("COPY_ROTATION")
    c.target, c.subtarget = src, "arm"
    fc = tgt.pose.bones["arm"].driver_add("rotation_euler", 0)
    fc.driver.type, fc.driver.expression = "SCRIPTED", f"(frame-1)*{K!r}"
    other = bpy.data.actions.new("AN_other")
    ad = tgt.animation_data
    ad.action = other
    tgt.pose.bones["root"].keyframe_insert("location", frame=1)
    track = ad.nla_tracks.new()
    track.strips.new("strip", 1, bpy.data.actions.new("AN_nla"))
    ad.action_influence, ad.action_blend_type, ad.use_nla = 0.7, "ADD", True
    tgt.pose.bones["root"].location = (0.01, 0.02, 0.03)
    tgt.pose.bones["spine"].scale = (1.0, 1.2, 1.0)
    src.data.pose_position = "REST"
    bpy.context.scene.frame_set(7)
    before = tgt_state(src, tgt)
    assert before["tracks"] and before["drivers"] and before["cons"]
    res = baked()
    assert res["verdict"] == "FAIL"
    assert tgt_state(src, tgt) == before, (tgt_state(src, tgt), before)
    try:
        baked(frames=[5, 3])
    except ValueError:
        pass
    else:
        raise AssertionError("an inverted frame range was accepted")
    assert tgt_state(src, tgt) == before, "state not restored after an exception during the measurement"
    # a target that had no animation data gets none afterwards
    tgt.animation_data_clear()
    tgt_ad_before = tgt.animation_data
    bpy.data.actions["AN_baked"].use_fake_user = True
    check(source="SRC", target="TGT", action="AN_baked")
    assert tgt.animation_data is None and tgt_ad_before is None, tgt.animation_data
    return {"restored": ["action", "slot", "influence", "blend", "nla", "drivers", "constraints", "pose", "frame"]}


def test_b2_result_file_and_exit_codes():
    src, tgt = scenario(GOOD, GOOD)
    good_blend = os.path.join(WORK, "bake_good.blend")
    bpy.ops.wm.save_as_mainfile(filepath=good_blend, copy=True)
    scenario(GOOD, {"arm": lambda f: {"eul": (-(f - 1) * K, 0.0, 0.0)}, "spine": lift})
    bad_blend = os.path.join(WORK, "bake_bad.blend")
    bpy.ops.wm.save_as_mainfile(filepath=bad_blend, copy=True)
    out = {}
    for label, blend, code_want, verdict in (("pass", good_blend, 0, "PASS"), ("fail", bad_blend, 2, "FAIL")):
        rp = os.path.join(WORK, f"bake_{label}.json")
        af = os.path.join(WORK, f"bake_{label}_args.json")
        with open(af, "w", encoding="utf-8") as fh:
            json.dump({"source": "SRC", "target": "TGT", "action": "AN_baked", "result_path": rp, "run_id": label + "-1"}, fh)
        cmd = [bpy.app.binary_path, "-b", blend, "--python-exit-code", "1", "--python", script("animation", "bake_check.py"),
               "--", "--args-file", af]
        code = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200).returncode
        data = json.load(open(rp, encoding="utf-8"))
        assert code == code_want and data["run_id"] == label + "-1" and data["verdict"] == verdict, (code, data["verdict"])
        assert not os.path.exists(rp + ".tmp")
        out[label] = code
    return out


# ---------------------------------------------------------------- boundaries (0.5x and 1.5x each limit)
def _offset_keys(kind, amount, last_only=False):
    def rot(f):
        extra = math.radians(amount) if (not last_only or f == LAST[0]) else 0.0
        return {"eul": ((f - 1) * K + extra, 0.0, 0.0)}

    def spine(f):
        d = lift(f)
        d["loc"] = (0.0, d["loc"][1] + (amount if kind == "trans" else 0.0), 0.0)
        if kind == "scale":
            d["scale"] = (1.0, 1.0 + amount, 1.0)
        return d
    return {"arm": rot if kind == "rot" else rotx, "spine": spine}


LAST = [11]


def test_b2_thresholds_boundary_fixtures():
    out = {}
    cases = (("rot", "rotation", 2.0, (1.0, 3.0)), ("trans", "translation", 0.01, (0.005, 0.015)),
             ("scale", "scale", 0.01, (0.005, 0.015)))
    for kind, key, limit, (lo, hi) in cases:
        vals = []
        for amount, want in ((lo, "PASS"), (hi, "FAIL")):
            scenario(GOOD, _offset_keys(kind, amount))
            res = baked()
            vals.append(res["bones"]["spine" if kind != "rot" else "arm"][key]["max"])
            got = res["bones"]["spine" if kind != "rot" else "arm"][key]["verdict"]
            assert got == want, (kind, amount, got, res["bones"])
        assert margin_ok(vals[0], limit, vals[1]), (kind, vals)
        out[key] = {"good": vals[0], "limit": limit, "bad": vals[1]}
    MEASURED["b2_boundaries"] = out
    return out


# ======================================================================================== B3 tests
LOOP = range(1, 26)


def sine(f):
    return math.sin(2 * math.pi * (f - 1) / 24)


def loop_keys(rot=None, loc=None, root=None, spine_extra=None):
    keys = {}
    keys["arm"] = lambda f: {"eul": (math.radians(60) * (rot or sine)(f), 0.0, 0.0)}
    keys["spine"] = lambda f: {"loc": (0.0, 0.05 * (loc or sine)(f) + (spine_extra(f) if spine_extra else 0.0), 0.0)}
    if root:
        keys["root"] = lambda f: {"loc": (0.0, root(f), 0.0)}
    return keys


def run_loop(keys, **kw):
    scenario(keys, keys, frames=LOOP)
    return baked(cyclic=True, **kw)


def test_b3_clean_loop_passes_and_non_cyclic_is_not_checked():
    res = run_loop(loop_keys())
    assert res["verdict"] == "PASS" and res["loop"]["verdict"] == "PASS", res["loop"]
    assert set(verdicts(res).values()) == {"PASS"}
    scenario(loop_keys(), loop_keys(), frames=LOOP)
    res2 = baked()  # the action is not flagged cyclic and the caller did not ask
    assert res2["loop"] is None and res2["verdict"] == "PASS"
    return {"loop": res["loop"]["verdict"], "non_cyclic_loop": None}


def test_b3_seam_pops_fail():
    out = {}
    ramp = run_loop(loop_keys(rot=lambda f: (f - 1) / 24 * 1.5))  # 90 degrees that never come back
    assert ramp["loop"]["bones"]["arm"]["rotation_pose"]["verdict"] == "FAIL" and ramp["verdict"] == "FAIL"
    assert set(verdicts(ramp).values()) == {"PASS"}, "the source comparison must not be what fails here"
    out["rotation_ramp_deg"] = ramp["loop"]["bones"]["arm"]["rotation_pose"]["value"]
    half = run_loop(loop_keys(rot=lambda f: math.sin(math.pi * (f - 1) / 24)))  # poses match, directions flip
    arm = half["loop"]["bones"]["arm"]
    assert arm["rotation_pose"]["verdict"] == "PASS" and arm["rotation_velocity"]["verdict"] == "FAIL", arm
    out["half_sine_velocity_diff_deg"] = arm["rotation_velocity"]["value"]
    lramp = run_loop(loop_keys(loc=lambda f: (f - 1) / 24 * 4))  # spine ends 0.2 above where it started
    sp = lramp["loop"]["bones"]["spine"]
    assert sp["location_pose"]["verdict"] == "FAIL" and abs(sp["location_pose"]["value"] - 0.2) < 0.01, sp
    out["location_pop_frac"] = sp["location_pose"]["value"]
    MEASURED["b3_pops"] = out
    return out


def test_b3_root_motion():
    travel = lambda f: 0.4 * (f - 1) / 24
    plain = run_loop(loop_keys(root=travel))
    assert plain["loop"]["bones"]["root"]["location_pose"]["verdict"] == "FAIL" and plain["verdict"] == "FAIL", plain["loop"]
    rm = run_loop(loop_keys(root=travel), root_motion=True)
    assert rm["verdict"] == "PASS" and rm["loop"]["bones"]["root"]["location_pose"].get("excluded") is True, rm["loop"]
    assert rm["loop"]["root_bone"] == "root"
    pop = run_loop(loop_keys(root=lambda f: 0.4 * math.sin(math.pi * (f - 1) / 24)), root_motion=True)
    assert pop["loop"]["bones"]["root"]["location_velocity"]["verdict"] == "FAIL" and pop["verdict"] == "FAIL", pop["loop"]
    return {"plain_pose": plain["loop"]["bones"]["root"]["location_pose"]["value"],
            "pop_velocity": pop["loop"]["bones"]["root"]["location_velocity"]["value"]}


def test_b3_thresholds_boundary_fixtures():
    out = {}
    LAST[0] = 25
    rot_vals = []
    for amount, want in ((0.5, "PASS"), (1.5, "FAIL")):
        keys_t = loop_keys()
        keys_t["arm"] = lambda f, a=amount: {"eul": (math.radians(60) * sine(f) + (math.radians(a) if f == 25 else 0.0), 0.0, 0.0)}
        scenario(loop_keys(), keys_t, frames=LOOP)
        res = baked(cyclic=True)
        v = res["loop"]["bones"]["arm"]["rotation_pose"]
        assert v["verdict"] == want, (amount, v)
        rot_vals.append(v["value"])
    assert margin_ok(rot_vals[0], 1.0, rot_vals[1]), rot_vals
    out["rotation_pose"] = {"good": rot_vals[0], "limit": 1.0, "bad": rot_vals[1]}
    loc_vals = []
    for amount, want in ((0.0025, "PASS"), (0.0075, "FAIL")):
        keys_t = loop_keys()
        keys_t["spine"] = lambda f, a=amount: {"loc": (0.0, 0.05 * sine(f) + (a if f == 25 else 0.0), 0.0)}
        scenario(loop_keys(), keys_t, frames=LOOP)
        res = baked(cyclic=True)
        v = res["loop"]["bones"]["spine"]["location_pose"]
        assert v["verdict"] == want, (amount, v)
        loc_vals.append(v["value"])
    assert margin_ok(loc_vals[0], 0.005, loc_vals[1]), loc_vals
    out["location_pose"] = {"good": loc_vals[0], "limit": 0.005, "bad": loc_vals[1]}
    MEASURED["b3_boundaries"] = out
    return out


def test_b2_scale_is_compared_per_axis_in_the_rest_frame():
    sx = {"spine": lambda f: {"scale": (2.0, 1.0, 1.0)}}
    sz = {"spine": lambda f: {"scale": (1.0, 1.0, 2.0)}}
    scenario(sx, sz)  # same rest orientation: an X stretch is not a Z stretch
    res = baked()
    assert res["verdict"] == "FAIL" and res["bones"]["spine"]["scale"]["verdict"] == "FAIL", res["bones"]["spine"]
    out = {"x_vs_z": res["bones"]["spine"]["scale"]["max"]}
    scenario(sx, sx)
    assert baked()["verdict"] == "PASS"
    # rolled rest (90 degrees): the same stretch in space is local X on one bone and local Z on the other -> PASS
    src_keys = {"arm": lambda f: {"scale": (2.0, 1.0, 1.0), "eul": ((f - 1) * K, 0.0, 0.0)}}
    scenario(src_keys, sampled("arm", parts=("eul", "scale")), tgt_roll={"arm": 90.0})
    res2 = baked()
    assert res2["verdict"] == "PASS", res2["bones"]["arm"]
    out["rolled_same_stretch"] = res2["bones"]["arm"]["scale"]["max"]
    # the wrong axis on the rolled rig must FAIL
    wrong = {"arm": lambda f: {"scale": (2.0, 1.0, 1.0), "eul": (0.0, 0.0, 0.0)}}
    scenario(src_keys, wrong, tgt_roll={"arm": 90.0})
    res3 = baked()
    assert res3["bones"]["arm"]["scale"]["verdict"] == "FAIL", res3["bones"]["arm"]
    return out


def test_b3_loop_that_cannot_run_is_not_a_pass():
    jump = {"arm": lambda f: {"eul": (math.radians(90) * (f - 1), 0.0, 0.0)}}
    out = {}
    for frames in (range(1, 3), range(1, 2)):
        scenario(jump, jump, frames=frames)
        res = baked(cyclic=True)
        assert res["loop"]["verdict"] == "NOT_CHECKED", res["loop"]
        assert res["verdict"] in ("WARN", "FAIL"), res["verdict"]
        out[f"{len(frames)}_frames"] = res["verdict"]
    return out


def _seam_keys(bone, vb, va, n=8):
    """Positions that start and end at 0 with a first step of vb and a last step of va (the rest stays 0)."""
    def pos(f):
        return vb if f == 2 else (-va if f == n - 1 else 0.0)
    if bone == "arm":
        return {"arm": lambda f: {"eul": (math.radians(pos(f)), 0.0, 0.0)}}
    return {"spine": lambda f: {"loc": (0.0, pos(f), 0.0)}}


def test_b3_seam_velocity_boundary_fixtures():
    """25% allowance and each floor, just inside (PASS) and just outside (FAIL). Units: degrees / rig heights per frame."""
    cases = (("arm", "rotation_velocity", 10.0, 10.0 + 2.7, 10.0 + 5.4, "relative, 10 deg/frame"),
             ("arm", "rotation_velocity", 0.0, 0.15, 0.5, "floor 0.2 deg/frame"),
             ("spine", "location_velocity", 0.1, 0.1 + 0.026, 0.1 + 0.06, "relative, 0.1 height/frame"),
             ("spine", "location_velocity", 0.0, 0.0008, 0.002, "floor 0.001 height/frame"))
    out = {}
    for bone, key, vb, inside, outside, label in cases:
        got = []
        for va, want in ((inside, "PASS"), (outside, "FAIL")):
            keys = _seam_keys(bone, vb, va)
            scenario(keys, keys, frames=range(1, 9))
            res = baked(cyclic=True)
            v = res["loop"]["bones"][bone][key]
            assert v["verdict"] == want, (label, va, v)
            assert res["loop"]["bones"][bone]["location_pose" if bone == "spine" else "rotation_pose"]["verdict"] == "PASS"
            got.append(v["value"])
        out[label] = got
    MEASURED["b3_velocity_boundaries"] = out
    return out


def test_b2_scale_percentage_is_exact_on_a_rolled_rest():
    """Identical rest bones rolled 45 degrees (Y-aligned): a stretch on one local axis is judged by its own percentage."""
    roll = {"arm": 45.0}
    src_keys = {"arm": lambda f: {"scale": (1.0, 1.0, 1.0)}}
    out = {}
    for amount, want in ((0.005, "PASS"), (0.015, "FAIL")):
        tgt_keys = {"arm": lambda f, a=amount: {"scale": (1.0 + a, 1.0, 1.0)}}
        scenario(src_keys, tgt_keys, tgt_roll=roll, src_roll=roll)
        res = baked()
        v = res["bones"]["arm"]["scale"]
        assert v["verdict"] == want, (amount, v)
        out[str(amount)] = v["max"]
    assert abs(out["0.015"] - 0.015) < 1e-3 and abs(out["0.005"] - 0.005) < 1e-3, out
    return out


TESTS = (
    test_b1_directx_green_is_flipped_opengl, test_b1_metallic_plain_and_linked_nodes_restored,
    test_b1_orm_channels_equal_separate_maps, test_b1_nodes_identical_when_a_bake_fails_midway,
    test_b1_collisions_refused_without_overwrite, test_b1_several_high_sources,
    test_b1_cage_ray_distance_and_uv_layer_set_and_restored, test_b1_uv_layer_chooses_the_bake_target_area,
    test_b2_correct_bake_passes, test_b2_wrong_keys_fail_and_nothing_is_masked_by_the_target,
    test_b2_wrong_keys_masked_by_a_driver_fail, test_b2_different_rest_orientation_passes,
    test_b2_rig_of_another_height_passes_with_scaled_translation, test_b2_piston_without_location_keys_fails,
    test_b2_hydraulic_bake_without_scale_keys_fails, test_b2_no_action_or_no_keys_is_fail_not_pass,
    test_b2_bad_arguments_raise_without_a_result_file, test_b2_state_restored_also_on_failure,
    test_b2_result_file_and_exit_codes, test_b2_thresholds_boundary_fixtures,
    test_b3_clean_loop_passes_and_non_cyclic_is_not_checked, test_b3_seam_pops_fail, test_b3_root_motion,
    test_b3_thresholds_boundary_fixtures, test_b2_scale_is_compared_per_axis_in_the_rest_frame,
    test_b2_scale_percentage_is_exact_on_a_rolled_rest, test_b3_loop_that_cannot_run_is_not_a_pass, test_b3_seam_velocity_boundary_fixtures,
)


def main():
    os.makedirs(WORK, exist_ok=True)
    only = ARGS.get("only")
    checks, failed = {}, []
    for fn in TESTS:
        if only and only not in fn.__name__:
            continue
        try:
            checks[fn.__name__] = {"ok": True, "data": fn()}
        except Exception:
            checks[fn.__name__] = {"ok": False, "error": traceback.format_exc()}
            failed.append(fn.__name__)
    report = {"passed": len(checks) - len(failed), "total": len(checks), "failed": failed, "checks": checks,
              "measured": MEASURED}
    with open(os.path.join(OUT, "iter16_b_report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    sys.exit(1 if failed else 0)


main()
