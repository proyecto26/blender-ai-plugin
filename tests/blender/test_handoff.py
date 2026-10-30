"""Headless Blender 5.2 tests for skills/ai-video-handoff/scripts/render_handoff.py.

Builds a NEW scene (ground plane, subject cube with a child, a decoy pillar, two cameras, a world colour that
changes per frame, and a 2-shot scene["film_shots"]: one still, one moving shot of 24 frames at 24 fps), runs the
script, asserts on files / manifests / pixels, checks the scene settings are identical afterwards (after success AND
after forced failures), and removes everything it created.

Run:
    blender -b --factory-startup --python tests/blender/test_handoff.py -- '{"out_dir": "/tmp/handoff-tests"}'
Writes <out_dir>/handoff_tests_report.json with passed / total / failures.
"""
import json
import os
import runpy
import struct
import sys
import traceback

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "skills", "ai-video-handoff", "scripts", "render_handoff.py"))
SIZE = [512, 288]


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(args):
    return runpy.run_path(SCRIPT, init_globals={"ARGS": args}, run_name="__handoff_test__")["result"]


def _mesh_obj(scene, name, build, loc):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    obj.location = loc
    return obj


def build_fixture():
    scene = bpy.data.scenes.new("__HandoffTests")
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 4
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 640, 360, 100
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 36
    scene.world = bpy.data.worlds.new("__HandoffWorld")
    world = scene.world
    if world.node_tree is None:
        world.use_nodes = True
    bg_color = world.node_tree.nodes["Background"].inputs["Color"]
    for f in (1, 36):  # world colour changes per frame (linear ramp between the keys)
        bg_color.default_value = (f / 40.0, f / 40.0, f / 40.0, 1.0)
        bg_color.keyframe_insert("default_value", frame=f)
    ground = _mesh_obj(scene, "Ground", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=10.0), (0, 0, 0))
    subject = _mesh_obj(scene, "Subject", lambda bm: bmesh.ops.create_cube(bm, size=1.0), (0, 0, 0.5))
    child = _mesh_obj(scene, "SubjectChild", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.3),
                      (-1.2, 0, 0))
    child.parent = subject
    pillar = _mesh_obj(scene, "Pillar", lambda bm: bmesh.ops.create_cube(bm, size=1.0), (1.4, 0, 0.5))
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.rotation_euler = (0.8, 0.2, 0.5)
    cams = {}
    for name, x in (("CAM_S010", 0.0), ("CAM_S020", 0.0)):
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
        cam.location = (x, -6.0, 2.0)
        cam.rotation_euler = (np.radians(75), 0, 0)
        cams[name] = cam
    scene.camera = cams["CAM_S010"]
    shots = [{"id": "S010", "start": 1, "end": 12, "camera": "CAM_S010", "lens_mm": 50, "motion": "still",
              "beat": "intro", "description": "hero cube on a plain"},
             {"id": "S020", "start": 13, "end": 36, "camera": "CAM_S020", "lens_mm": 50, "motion": "moving",
              "beat": "move", "description": "the cube turns to the light"}]
    scene["film_shots"] = json.dumps({"version": 1, "fps": 24, "shots": shots})
    for s in shots:
        m = scene.timeline_markers.new(s["id"], frame=s["start"])
        m.camera = cams[s["camera"]]
    return scene, {"ground": ground, "subject": subject, "child": child, "pillar": pillar}, cams


def snapshot(scene, window):
    r, im, ff, vs = scene.render, scene.render.image_settings, scene.render.ffmpeg, scene.view_settings
    return {
        "render": {k: getattr(r, k) for k in ("engine", "resolution_x", "resolution_y", "resolution_percentage", "fps",
                                              "fps_base", "film_transparent", "filepath", "use_compositing",
                                              "dither_intensity")},
        "image": {k: getattr(im, k) for k in ("media_type", "file_format", "color_mode", "color_depth")},
        "ffmpeg": {k: getattr(ff, k) for k in ("format", "codec", "constant_rate_factor", "audio_codec")},
        "view": {k: getattr(vs, k) for k in ("view_transform", "look", "exposure", "gamma", "use_curve_mapping")},
        "frames": {k: getattr(scene, k) for k in ("frame_current", "frame_start", "frame_end", "frame_step")},
        "camera": scene.camera.name if scene.camera else None,
        "samples": scene.eevee.taa_render_samples,
        "comp_group": scene.compositing_node_group.name if scene.compositing_node_group else None,
        "world": scene.world.name if scene.world else None,
        "mist": {k: getattr(scene.world.mist_settings, k) for k in ("start", "depth", "falloff")},
        "pass_mist": [vl.use_pass_mist for vl in scene.view_layers],
        "hide_render": {o.name: o.hide_render for o in scene.objects},
        "window_scene": window.scene.name if window else None,
        "datablocks": {"node_groups": len(bpy.data.node_groups), "worlds": len(bpy.data.worlds)},
    }


def png_info(path):
    with open(path, "rb") as fh:
        head = fh.read(33)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    w, h, depth, ctype = struct.unpack(">IIBB", head[16:26])
    return {"w": w, "h": h, "bit_depth": depth, "color_type": ctype}  # 0 grey, 2 RGB, 4 grey+alpha, 6 RGBA


def pixels(path, non_color=True):
    img = bpy.data.images.load(path, check_existing=False)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    arr = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(arr)
    arr = arr.reshape(h, w, img.channels)
    bpy.data.images.remove(img)
    return arr


def px_at(scene, cam, point, w, h):
    co = world_to_camera_view(scene, cam, point)
    return min(max(int(co.x * w), 0), w - 1), min(max(int(co.y * h), 0), h - 1), co


def main(out_dir=None):
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "handoff-tests")
    os.makedirs(out_dir, exist_ok=True)
    window = bpy.context.window
    original = window.scene if window else None
    failures, total = [], [0]

    def check(name, fn):
        total[0] += 1
        try:
            fn()
        except BaseException:
            failures.append({"test": name, "error": traceback.format_exc(limit=4)})

    scene, objs, cams = build_fixture()
    if window:
        window.scene = scene
    try:
        S = scene
        d = lambda *p: os.path.join(out_dir, *p)  # noqa: E731
        cache = {}

        before = snapshot(S, window)

        # ---- seam target
        def seam_run():
            cache["seam"] = run({"out_dir": d("seam_case"), "target": "seam", "size": [520, 300]})
        check("seam.run", seam_run)
        seam = cache.get("seam")

        def seam_size_snapped():
            assert seam["size"] == [512, 288], seam["size"]
            assert any("snapped" in w for w in seam["warnings"]), seam["warnings"]
        check("seam.size_snapped_to_32", seam_size_snapped)

        def seam_still_opaque_rgb():
            info = png_info(d("seam_case", "seam", "S010.png"))
            assert (info["w"], info["h"], info["color_type"], info["bit_depth"]) == (512, 288, 2, 8), info
        check("seam.still_opaque_rgb_right_size", seam_still_opaque_rgb)

        def seam_clip_reloads():
            mc = bpy.data.movieclips.load(d("seam_case", "seam", "S020.mp4"))
            try:
                assert mc.frame_duration == 24, mc.frame_duration
                assert list(mc.size) == [512, 288], list(mc.size)
                assert round(mc.fps) == 24, mc.fps
            finally:
                bpy.data.movieclips.remove(mc)
        check("seam.clip_reloads_with_24_frames", seam_clip_reloads)

        def seam_manifest():
            doc = json.load(open(d("seam_case", "seam", "seam_sequence.json"), encoding="utf-8"))
            names = [os.path.basename(p) for p in doc["shots"]]
            assert names == ["S010.png", "S020.mp4"], names
            assert all(os.path.isabs(p) and os.path.exists(p) for p in doc["shots"]), doc["shots"]
            assert len(doc["segments"]) == len(doc["shots"]) - 1 == 1
            seg = doc["segments"][0]
            assert seg["preset"] is None and seg["a_desc"] == "hero cube on a plain" and seg["b_desc"].startswith("the cube")
            assert doc["size"] == [512, 288] and doc["fps"] == 24
            joined = " ".join(doc["notes"])
            assert "list_presets" in joined and "aspect ratio" in joined, doc["notes"]
        check("seam.manifest_order_and_segments", seam_manifest)

        def seam_segments_passthrough():
            segs = [{"preset": "smoke", "seconds": 5, "seed": 3, "prompt_extra": "x"}]
            shots = [{"id": "A", "start": 1, "end": 1, "camera": "CAM_S010", "motion": "still"},
                     {"id": "B", "start": 2, "end": 2, "camera": "CAM_S010", "motion": "still"}]
            run({"out_dir": d("seg_case"), "target": "seam", "shots": shots, "size": SIZE, "segments": segs})
            doc = json.load(open(d("seg_case", "seam", "seam_sequence.json"), encoding="utf-8"))
            assert doc["segments"] == segs
            try:
                run({"out_dir": d("seg_case2"), "target": "seam", "shots": shots, "size": SIZE, "segments": segs * 2})
            except ValueError as exc:
                assert "segments" in str(exc)
            else:
                raise AssertionError("wrong segment count was accepted")
        check("seam.segments_passed_through_and_counted", seam_segments_passthrough)

        def seam_clamp_and_min():
            moving = {"id": "M", "start": 1, "end": 36, "camera": "CAM_S010", "motion": "moving"}
            r = run({"out_dir": d("clamp_case"), "target": "seam", "shots": [moving], "size": SIZE, "clip_seconds_max": 1})
            assert any("clamped" in w for w in r["warnings"]), r["warnings"]
            mc = bpy.data.movieclips.load(d("clamp_case", "seam", "M.mp4"))
            try:
                assert mc.frame_duration == 24, mc.frame_duration
            finally:
                bpy.data.movieclips.remove(mc)
            short = {"id": "T", "start": 1, "end": 12, "camera": "CAM_S010", "motion": "moving"}
            try:
                run({"out_dir": d("short_case"), "target": "seam", "shots": [short], "size": SIZE})
            except ValueError as exc:
                assert "1-6 s" in str(exc)
            else:
                raise AssertionError("a 0.5 s clip was accepted")
        check("seam.clip_length_clamp_and_minimum", seam_clamp_and_min)

        def default_single_still():
            saved = S["film_shots"]
            del S["film_shots"]
            try:
                r = run({"out_dir": d("single_case"), "target": "seam"})
            finally:
                S["film_shots"] = saved
            assert r["shots"] == ["SHOT_01"] and r["size"] == [640, 352], r
            assert any("2-8" in w for w in r["warnings"]), r["warnings"]
        check("seam.default_single_still_and_scene_size", default_single_still)

        # ---- comfy target
        def comfy_run():
            cache["comfy"] = run({"out_dir": d("comfy_case"), "target": "comfy", "size": SIZE, "subject": ["Subject"]})
        check("comfy.run", comfy_run)

        def comfy_layout_and_formats():
            for sid in ("S010", "S020"):
                base = d("comfy_case", "comfy", "assets", sid)
                b, m, z = png_info(os.path.join(base, "beauty.png")), png_info(os.path.join(base, "mask.png")), \
                    png_info(os.path.join(base, "depth.png"))
                assert (b["w"], b["h"], b["color_type"]) == (512, 288, 2), b
                assert (m["w"], m["h"], m["color_type"], m["bit_depth"]) == (512, 288, 0, 8), m
                assert (z["w"], z["h"], z["color_type"], z["bit_depth"]) == (512, 288, 0, 16), z
                assert z["w"] % 32 == 0 and z["h"] % 32 == 0
            doc = json.load(open(d("comfy_case", "comfy", "handoff.json"), encoding="utf-8"))
            assert doc["size"] == [512, 288] and doc["fps"] == 24 and [s["id"] for s in doc["shots"]] == ["S010", "S020"]
            shot = doc["shots"][0]
            assert shot["files"] == {"beauty": "S010/beauty.png", "mask": "S010/mask.png", "depth": "S010/depth.png"}
            assert shot["camera"]["lens_mm"] == 50 and len(shot["camera"]["matrix_world"]) == 4
            assert {"clip_start", "clip_end", "sensor_width_mm"} <= set(shot["camera"])
            assert set(shot["mist"]) >= {"start", "depth", "falloff", "polarity"} and shot["mist"]["polarity"] == "near_is_black"
            assert shot["description"] == "hero cube on a plain"
        check("comfy.layout_formats_manifest", comfy_layout_and_formats)

        S.frame_set(6)
        cam = cams["CAM_S010"]
        W, H = SIZE

        def mask_values():
            m = pixels(d("comfy_case", "comfy", "assets", "S010", "mask.png"))[..., 0]
            cx, cy, _ = px_at(S, cam, objs["subject"].matrix_world.translation, W, H)
            assert m[cy, cx] > 0.95, f"subject centre {m[cy, cx]}"
            kx, ky, _ = px_at(S, cam, objs["child"].matrix_world.translation, W, H)
            assert m[ky, kx] > 0.95, f"child {m[ky, kx]} (children must count as subject)"
            px_, py_, _ = px_at(S, cam, objs["pillar"].matrix_world.translation, W, H)
            assert m[py_, px_] < 0.05, f"non-subject pillar {m[py_, px_]}"
            assert m[int(0.05 * H), int(0.05 * W)] < 0.05, "ground-only pixel must be 0"
        check("comfy.mask_subject_1_ground_0", mask_values)

        def depth_values():
            doc = json.load(open(d("comfy_case", "comfy", "handoff.json"), encoding="utf-8"))
            mist = doc["shots"][0]["mist"]
            z = pixels(d("comfy_case", "comfy", "assets", "S010", "depth.png"))[..., 0]
            near, far = z[int(0.05 * H), int(0.5 * W)], z[int(0.97 * H), int(0.5 * W)]
            assert near < far, f"near_is_black violated: near {near} far {far}"
            cx, cy, _ = px_at(S, cam, objs["subject"].matrix_world.translation, W, H)
            zc = -(cam.matrix_world.inverted() @ __import__("mathutils").Vector((0, -0.5, 0.5))).z
            expected = min(max((zc - mist["start"]) / mist["depth"], 0.0), 1.0)
            assert abs(z[cy, cx] - expected) < 0.03, f"centre depth {z[cy, cx]} vs linear mist {expected}"
        check("comfy.depth_polarity_and_normalization", depth_values)

        def depth_inverted():
            r = run({"out_dir": d("inv_case"), "target": "comfy", "size": SIZE, "passes": ["depth"], "depth_near_white": True})
            assert r["depth_polarity"] == "near_is_white"
            z = pixels(d("inv_case", "comfy", "assets", "S010", "depth.png"))[..., 0]
            assert z[int(0.05 * H), int(0.5 * W)] > z[int(0.97 * H), int(0.5 * W)]
            assert not os.path.exists(d("inv_case", "comfy", "assets", "S010", "mask.png"))
        check("comfy.depth_near_white_option", depth_inverted)

        def comfy_frame_selection():
            for which in ("start", "end"):
                run({"out_dir": d("frame_" + which), "target": "comfy", "size": SIZE, "passes": ["beauty"], "comfy_frame": which})
            a = pixels(d("frame_start", "comfy", "assets", "S020", "beauty.png"), False)
            b = pixels(d("frame_end", "comfy", "assets", "S020", "beauty.png"), False)
            top = int(0.97 * H)
            assert abs(float(a[top, W // 2, 0]) - float(b[top, W // 2, 0])) > 0.02, "world colour should differ start vs end"
            doc = json.load(open(d("frame_end", "comfy", "handoff.json"), encoding="utf-8"))
            assert doc["shots"][1]["frame"] == 36
        check("comfy.frame_selection_follows_shot_range", comfy_frame_selection)

        def comfy_rerun_lists_only_new_files():
            run({"out_dir": d("rerun"), "target": "comfy", "size": SIZE, "subject": ["Subject"]})
            r = run({"out_dir": d("rerun"), "target": "comfy", "size": SIZE, "passes": ["beauty"]})
            names = [os.path.basename(f) for f in r["files"] if f.endswith(".png")]
            assert names and set(names) == {"beauty.png"}, names
            assert any("left from an earlier run" in w and "mask.png" in w for w in r["warnings"]), r["warnings"]
        check("comfy.rerun_lists_only_files_written_now", comfy_rerun_lists_only_new_files)

        def mask_needs_subject():
            try:
                run({"out_dir": d("nosub"), "target": "comfy", "size": SIZE})
            except ValueError as exc:
                assert "subject" in str(exc)
            else:
                raise AssertionError("mask without subject was accepted")
        check("comfy.mask_requires_subject", mask_needs_subject)

        # ---- settings restored
        S.frame_set(1)
        before = snapshot(S, window)  # the test's own frame_set calls above are not the script's business
        run({"out_dir": d("restore_ok"), "target": "both", "size": SIZE, "subject": ["Subject"]})
        after_ok = snapshot(S, window)

        def restored_after_success():
            assert after_ok == before, {k: (before[k], after_ok[k]) for k in before if before[k] != after_ok[k]}
        check("restore.after_success", restored_after_success)

        def restored_after_bad_subject():
            try:
                run({"out_dir": d("bad_subject"), "target": "both", "size": SIZE, "subject": ["NoSuchObject"]})
            except ValueError:
                pass
            else:
                raise AssertionError("missing subject was accepted")
            assert snapshot(S, window) == before
        check("restore.after_missing_subject", restored_after_bad_subject)

        def restored_after_mid_render_failure():
            blocker = d("midfail", "comfy", "assets")
            os.makedirs(blocker, exist_ok=True)
            with open(os.path.join(blocker, "S020"), "w") as fh:  # a FILE where shot 2's folder must go
                fh.write("x")
            try:
                run({"out_dir": d("midfail"), "target": "both", "size": SIZE, "subject": ["Subject"]})
            except (FileExistsError, NotADirectoryError, OSError):
                pass
            else:
                raise AssertionError("expected an I/O failure after shot 1 was rendered")
            assert os.path.exists(d("midfail", "comfy", "assets", "S010", "mask.png")), "shot 1 should have rendered first"
            now = snapshot(S, window)
            assert now == before, {k: (before[k], now[k]) for k in before if before[k] != now[k]}
        check("restore.after_failure_mid_render", restored_after_mid_render_failure)

        # ---- CLI argument handling
        def cli_args():
            ns = runpy.run_path(SCRIPT, init_globals={"ARGS": {"out_dir": d("cli"), "target": "seam", "size": SIZE,
                                                                  "shots": [{"id": "A", "start": 1, "end": 1,
                                                                             "camera": "CAM_S010"}]}})
            saved = list(sys.argv)
            try:
                sys.argv = ["x", "--", "{not json"]
                try:
                    ns["_cli_args"]()
                except ValueError as exc:
                    assert "could not read ARGS" in str(exc)
                else:
                    raise AssertionError("bad JSON accepted")
                path = d("args.json")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"out_dir": d("cli"), "target": "nope"}, fh)
                sys.argv = ["x", "--", "--args-file", path]
                assert ns["_cli_args"]()["target"] == "nope"
                sys.argv = ["x", "--", "--args-file", d("missing.json")]
                try:
                    ns["_cli_args"]()
                except ValueError as exc:
                    assert "could not read ARGS" in str(exc)
                else:
                    raise AssertionError("missing args file accepted")
            finally:
                sys.argv = saved
        check("cli.args_file_and_bad_json", cli_args)
    finally:
        if window and original:
            window.scene = original
        for o in list(scene.objects):
            bpy.data.objects.remove(o)
        world = scene.world
        bpy.data.scenes.remove(scene)
        if world:
            bpy.data.worlds.remove(world)

    report = {"passed": total[0] - len(failures), "total": total[0], "failures": failures}
    with open(os.path.join(out_dir, "handoff_tests_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("passed", "total")}))
