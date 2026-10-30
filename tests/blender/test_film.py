"""Headless tests for the film-production skill scripts (shot_list, preview_frames, assemble_edit).

Builds a NEW scene with three shots, each looking at its own flat emissive plane (red / green / blue
dominant) whose colour is keyframed per frame, so every frame has a known flat colour and every shot a
known hue. Never touches the user's scene; removes everything it created; writes
<out_dir>/film_tests_report.json (passed / total / failures / not_checked).

Run:
    blender -b --factory-startup --python tests/blender/test_film.py -- '{"out_dir": "/tmp/film-tests"}'
"""
import json
import math
import os
import runpy
import struct
import sys
import tempfile
import traceback
import wave

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILL = os.path.normpath(os.path.join(HERE, "..", "..", "skills", "film-production", "scripts"))

SHOTS = [("S010", 1, 3), ("S020", 4, 6), ("S030", 7, 8)]
BASE_ARGS = {"fps": 24, "shots": [
    {"id": sid, "start": a, "end": b, "camera": f"CAM_{sid}", "lens_mm": 35, "motion": "still",
     "beat": f"beat {i}", "description": f"shot {i}", "camera_location": [50 * i, -6, 0], "look_at": [50 * i, 0, 0]}
    for i, (sid, a, b) in enumerate(SHOTS)]}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(script, args):
    return runpy.run_path(os.path.join(SKILL, script), init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def srgb(c):
    c = float(c)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def frame_color(frame):
    for i, (_, a, b) in enumerate(SHOTS):
        if a <= frame <= b:
            level = 0.9 - 0.15 * (frame - a)
            col = [0.03, 0.03, 0.03]
            col[i] = level
            return col
    raise ValueError(frame)


def build_fixture(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 4
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    world = bpy.data.worlds.new("__FilmWorld")
    world.color = (0, 0, 0)
    scene.world = world
    for i, (sid, a, b) in enumerate(SHOTS):
        me = bpy.data.meshes.new(f"__FilmPlane{i}")
        me.from_pydata([(-10, 0, -10), (10, 0, -10), (10, 0, 10), (-10, 0, 10)], [], [(0, 1, 2, 3)])
        obj = bpy.data.objects.new(f"__FilmPlane{i}", me)
        scene.collection.objects.link(obj)
        obj.location = (50 * i, 0, 0)
        mat = bpy.data.materials.new(f"__FilmMat{i}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        emi = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
        me.materials.append(mat)
        for f in range(a, b + 1):
            emi.inputs["Color"].default_value = (*frame_color(f), 1.0)
            emi.inputs["Color"].keyframe_insert("default_value", frame=f)
    return world


def write_sine(path, seconds=1.0, rate=48000, freq=440.0, amp=0.8):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * freq * i / rate)))
                               for i in range(n)))


def read_png(path):
    img = bpy.data.images.load(path)
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return w, h, buf.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)


def settings_snapshot(sc):
    r, im = sc.render, sc.render.image_settings
    return {"fps": r.fps, "res": (r.resolution_x, r.resolution_y, r.resolution_percentage), "engine": r.engine,
            "filepath": r.filepath, "range": (sc.frame_start, sc.frame_end, sc.frame_current),
            "camera": sc.camera.name if sc.camera else None, "fmt": im.file_format, "media": im.media_type,
            "samples": sc.eevee.taa_render_samples, "color_mode": im.color_mode, "seq": sc.sequence_editor is not None}


def tile_mean(arr, tile_w, tile_h, col, row_from_top, rows):
    y0 = (rows - 1 - row_from_top) * tile_h
    x0 = col * tile_w
    mx, my = tile_w // 4, tile_h // 4
    return arr[y0 + my:y0 + tile_h - my, x0 + mx:x0 + tile_w - mx, :3].reshape(-1, 3).mean(axis=0)


def decode_frame_colors(mp4, edit_frames, out_dir, region=None):
    """Decode mp4 frames through a throw-away VSE scene; returns {frame: [r,g,b]} (display values) averaged over
    the centre, or over `region` = (x0, x1, y0, y1) as fractions of the frame."""
    sc = bpy.data.scenes.new("__FilmDecode")
    try:
        clip = bpy.data.movieclips.load(mp4)
        size = tuple(clip.size)
        bpy.data.movieclips.remove(clip)
        sc.view_settings.view_transform = "Standard"
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = size[0], size[1], 100
        sc.sequence_editor_create()
        sc.sequence_editor.strips.new_movie(name="m", filepath=mp4, channel=1, frame_start=1)
        sc.render.image_settings.media_type = "IMAGE"
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGB"
        sc.render.use_file_extension = True
        sc.frame_start, sc.frame_end = min(edit_frames), max(edit_frames)
        sc.render.filepath = os.path.join(out_dir, "decode_")
        bpy.ops.render.render(animation=True, scene=sc.name)
        out = {}
        for f in edit_frames:
            w, h, arr = read_png(os.path.join(out_dir, f"decode_{f:04d}.png"))
            if region:
                x0, x1, y0, y1 = (int(region[0] * w), int(region[1] * w), int(region[2] * h), int(region[3] * h))
                out[f] = arr[y0:y1, x0:x1, :3].reshape(-1, 3).mean(axis=0).tolist()
            else:
                out[f] = arr[h // 2 - 4:h // 2 + 4, w // 2 - 4:w // 2 + 4, :3].reshape(-1, 3).mean(axis=0).tolist()
        return out
    finally:
        bpy.data.scenes.remove(sc)


def build_cases(out_dir, scene):
    pre = os.path.join(out_dir, "previews")
    edit_dir = os.path.join(out_dir, "edit")
    os.makedirs(edit_dir, exist_ok=True)
    wav_a = os.path.join(edit_dir, "tone_a.wav")
    wav_b = os.path.join(edit_dir, "tone_b.wav")
    write_sine(wav_a, 1.0, freq=440.0)
    write_sine(wav_b, 1.0, freq=220.0, amp=0.5)
    state = {}

    # ---------------- shot_list ----------------
    def sl_apply():
        res = run("shot_list.py", BASE_ARGS)
        state["first_json"] = scene["film_shots"]
        names = {m.name: m.camera.name for m in scene.timeline_markers if m.camera}
        ok = (names == {sid: f"CAM_{sid}" for sid, _, _ in SHOTS}
              and {m.name: m.frame for m in scene.timeline_markers} == {sid: a for sid, a, _ in SHOTS}
              and scene.render.fps == 24 and (scene.frame_start, scene.frame_end) == (1, 8)
              and sorted(res["created_cameras"]) == sorted(f"CAM_{sid}" for sid, _, _ in SHOTS)
              and json.loads(scene["film_shots"])["version"] == 1)
        return ok, res

    def sl_cam_placement():
        cam = bpy.data.objects["CAM_S020"]
        return abs(cam.location.x - 50) < 1e-4 and abs(cam.location.y + 6) < 1e-4 and cam.data.lens == 35

    def sl_idempotent():
        scene.timeline_markers.new("USER_note", frame=2)
        res = run("shot_list.py", BASE_ARGS)
        run("shot_list.py", BASE_ARGS)
        names = [m.name for m in scene.timeline_markers]
        ok = (len(names) == 4 and names.count("S010") == 1 and "USER_note" in names
              and scene["film_shots"] == state["first_json"] and res["created_cameras"] == []
              and len([o for o in bpy.data.objects if o.name.startswith("CAM_")]) == 3)
        return ok, names

    def sl_merge_no_duplicate_markers():
        one = {"fps": 24, "replace": False, "shots": [dict(BASE_ARGS["shots"][1], description="merged")]}
        run("shot_list.py", one)
        run("shot_list.py", one)
        names = [m.name for m in scene.timeline_markers if m.name != "USER_note"]
        ok = sorted(names) == sorted(s["id"] for s in BASE_ARGS["shots"])
        run("shot_list.py", BASE_ARGS)  # back to the canonical list for later cases
        return ok, names

    def sl_overlap():
        before = scene["film_shots"]
        bad = json.loads(json.dumps(BASE_ARGS))
        bad["shots"][1]["start"] = 3
        try:
            run("shot_list.py", bad)
        except ValueError as exc:
            return "overlap" in str(exc) and scene["film_shots"] == before
        return False

    def sl_validation():
        results = []
        for mutate in (lambda a: a["shots"][1].update(id="S010"),
                       lambda a: a["shots"][0].update(start=9, end=2)):
            bad = json.loads(json.dumps(BASE_ARGS))
            mutate(bad)
            try:
                run("shot_list.py", bad)
                results.append(False)
            except ValueError:
                results.append(True)
        try:
            bad = json.loads(json.dumps(BASE_ARGS))
            bad["shots"][0]["camera"] = "CAM_nope"
            bad["create_cameras"] = False
            run("shot_list.py", bad)
            results.append(False)
        except ValueError:
            results.append(True)
        return all(results), results

    # ---------------- preview_frames ----------------
    def pv_files():
        before = settings_snapshot(scene)
        res = run("preview_frames.py", {"out_dir": pre, "frames_per_shot": 2, "resolution": [160, 90]})
        state["pv"] = res
        want = [f"{s}_{f}.png" for s, f in [("S010", 1), ("S010", 3), ("S020", 4), ("S020", 6), ("S030", 7), ("S030", 8)]]
        exist = all(os.path.isfile(os.path.join(pre, n)) for n in want)
        sizes = [read_png(os.path.join(pre, n))[:2] for n in want]
        ok = exist and all(s == (160, 90) for s in sizes) and settings_snapshot(scene) == before
        return ok, {"exist": exist, "sizes": sizes[:2], "restored": settings_snapshot(scene) == before}

    def pv_sheet_layout():
        lay = state["pv"]["contact_sheet"]
        w, h, arr = read_png(lay["path"])
        ok = ((w, h) == tuple(lay["size"]) == (lay["cols"] * 160, lay["rows"] * 90)
              and lay["cols"] * lay["rows"] >= 6 and lay["tile_size"] == [160, 90]
              and [t["shot"] for t in lay["tiles"]] == ["S010", "S010", "S020", "S020", "S030", "S030"])
        return ok, {k: lay[k] for k in ("cols", "rows", "size")}

    def pv_tile_colors():
        lay = state["pv"]["contact_sheet"]
        w, h, arr = read_png(lay["path"])
        worst = 0.0
        for t in lay["tiles"]:
            mean = tile_mean(arr, 160, 90, t["col"], t["row"], lay["rows"])
            expect = [srgb(c) for c in frame_color(t["frame"])]
            worst = max(worst, float(np.abs(mean - np.array(expect)).max()))
        return worst < 0.08, {"worst_abs_err": round(worst, 4)}

    def pv_subset():
        res = run("preview_frames.py", {"out_dir": pre, "shots": ["S020"], "frames_per_shot": 2,
                                        "resolution": [64, 36], "cols": 2})
        lay = res["contact_sheet"]
        return (list(res["shots"]) == ["S020"] and lay["cols"] == 2 and lay["rows"] == 1
                and len(res["files"]) == 2 and read_png(lay["path"])[:2] == (128, 36)), lay

    def pv_restore_on_failure():
        before = settings_snapshot(scene)
        try:
            run("preview_frames.py", {"out_dir": pre, "resolution": [160, 90], "engine": "NOT_AN_ENGINE"})
        except Exception:
            return settings_snapshot(scene) == before
        return False

    # ---------------- assemble_edit ----------------
    def ae_structure():
        before = settings_snapshot(scene)
        out_mp4 = os.path.join(edit_dir, "structure.mp4")
        res = run("assemble_edit.py", {"out_path": out_mp4, "resolution": [160, 90], "audio": [
            {"path": wav_a, "license": "CC0", "volume": 0.5, "channel": 2, "start_frame": 5, "title": "A"},
            {"path": wav_b, "license": "user-owned", "volume": 0.8, "channel": 3, "fade_in": 0.1, "fade_out": 0.1}]})
        state["ae"] = res
        edit = bpy.data.scenes["EDIT"]
        vids = [s for s in edit.sequence_editor.strips_all if s.type == "SCENE"]
        vids.sort(key=lambda s: s.frame_final_start)
        got = [(s.name, s.channel, s.frame_final_start, s.frame_final_end - 1, s.scene_camera.name) for s in vids]
        want = [("S010", 1, 1, 3, "CAM_S010"), ("S020", 1, 4, 6, "CAM_S020"), ("S030", 1, 7, 8, "CAM_S030")]
        sounds = {s.name: s for s in edit.sequence_editor.strips_all if s.type == "SOUND"}
        sa, sb = sounds.get("AUD_tone_a"), sounds.get("AUD_tone_b")
        ok = (got == want and sa and sb and abs(sa.volume - 0.5) < 1e-6 and sa.channel == 2
              and sa.frame_final_start == 5 and abs(sb.volume - 0.8) < 1e-6 and sb.channel == 3
              and settings_snapshot(scene) == before)
        return bool(ok), {"got": got, "src_unchanged": settings_snapshot(scene) == before}

    def ae_scene_strip_content():
        edit = bpy.data.scenes["EDIT"]
        s2 = edit.sequence_editor.strips_all["S020"]
        # first visible frame of S020 must map to source frame 4
        return s2.scene == scene and s2.frame_final_start - s2.frame_start == s2.frame_offset_start == 3, \
            {"offset": s2.frame_offset_start, "start": s2.frame_start}

    def ae_edit_stills():
        """Render stills straight from the EDIT scene (no mp4): each shot must show its own hue."""
        edit = bpy.data.scenes["EDIT"]
        im, r = edit.render.image_settings, edit.render
        saved = (im.media_type, im.file_format, r.filepath, r.use_file_extension, edit.frame_start, edit.frame_end)
        got = {}
        try:
            im.media_type, im.file_format = "IMAGE", "PNG"
            r.use_file_extension = True
            edit.frame_start, edit.frame_end = 1, 8
            r.filepath = os.path.join(edit_dir, "editseq_")
            # NOTE: frame_set + write_still does not re-evaluate a scene strip's source scene; render an animation.
            bpy.ops.render.render(animation=True, scene=edit.name)
        finally:
            im.media_type, im.file_format, r.filepath, r.use_file_extension, edit.frame_start, edit.frame_end = saved
        for f in (1, 2, 4, 5, 7, 8):
            w, h, arr = read_png(os.path.join(edit_dir, f"editseq_{f:04d}.png"))
            got[f] = [round(float(x), 2) for x in arr[h // 2, w // 2, :3]]
        dom = {f: int(np.argmax(c)) for f, c in got.items()}
        return dom == {1: 0, 2: 0, 4: 1, 5: 1, 7: 2, 8: 2}, got

    def ae_fades():
        edit = bpy.data.scenes["EDIT"]
        ad = edit.animation_data
        n = 0
        if ad and ad.action:
            for layer in ad.action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        n += sum(1 for fc in bag.fcurves if fc.data_path.endswith("volume"))
        keys = [s for s in state["ae"]["strips"] if s["name"] == "AUD_tone_b"][0]["keyframes"]
        return n >= 1 and len(keys) == 4, {"fcurves": n, "keys": keys}

    def ae_output_settings():
        edit = bpy.data.scenes["EDIT"]
        im, ff = edit.render.image_settings, edit.render.ffmpeg
        return (im.media_type == "VIDEO" and im.file_format == "FFMPEG" and ff.format == "MPEG4"
                and ff.codec == "H264" and ff.audio_codec == "AAC"), \
            [im.media_type, im.file_format, ff.format, ff.codec, ff.audio_codec]

    def ae_credits():
        with open(os.path.join(edit_dir, "audio_credits.json"), encoding="utf-8") as fh:
            entries = json.load(fh)["entries"]
        return sorted(e["license"] for e in entries) == ["CC0", "user-owned"], entries

    def ae_requires_license():
        try:
            run("assemble_edit.py", {"out_path": os.path.join(edit_dir, "x.mp4"), "audio": [{"path": wav_a}]})
        except ValueError as exc:
            return "license" in str(exc)
        return False

    def ae_refuses_foreign_scene():
        foreign = bpy.data.scenes.new("USER_EDIT")
        foreign.sequence_editor_create()
        try:
            run("assemble_edit.py", {"out_path": os.path.join(edit_dir, "f.mp4"), "edit_scene": "USER_EDIT"})
        except ValueError as exc:
            return "not made by" in str(exc) and bpy.data.scenes.get("USER_EDIT") is foreign, str(exc)
        finally:
            bpy.data.scenes.remove(foreign)
        return False, "no error"

    def ae_idempotent():
        scenes_before = len(bpy.data.scenes)
        run("assemble_edit.py", {"out_path": os.path.join(edit_dir, "structure.mp4"), "resolution": [160, 90],
                                 "audio": [{"path": wav_a, "license": "CC0", "start_frame": 5, "volume": 0.5}]})
        edit = bpy.data.scenes["EDIT"]
        types = sorted(s.type for s in edit.sequence_editor.strips_all)
        with open(os.path.join(edit_dir, "audio_credits.json"), encoding="utf-8") as fh:
            n_credits = len(json.load(fh)["entries"])
        return len(bpy.data.scenes) == scenes_before and types == ["SCENE", "SCENE", "SCENE", "SOUND"] \
            and n_credits == 2, types

    def ae_render():
        before = settings_snapshot(scene)
        out_mp4 = os.path.join(edit_dir, "short.mp4")
        res = run("assemble_edit.py", {"out_path": out_mp4, "resolution": [160, 90], "render": True, "frames": [1, 8],
                                       "audio": [{"path": wav_a, "license": "CC0", "start_frame": 5, "volume": 1.0}]})
        state["mp4"] = out_mp4
        size = os.path.getsize(out_mp4) if os.path.isfile(out_mp4) else 0
        clip = bpy.data.movieclips.load(out_mp4)
        info = {"frames": clip.frame_duration, "size": tuple(clip.size), "bytes": size}
        bpy.data.movieclips.remove(clip)
        ok = (size > 0 and info["frames"] == 8 and info["size"] == (160, 90)
              and res["rendered"]["bytes"] == size and settings_snapshot(scene) == before)
        state["verify"] = res.get("verify")
        return ok, info

    def ae_verify_with_audio():
        v = state.get("verify") or {}
        return (v.get("ok") is True and v.get("audio_stream") is True and v.get("frames") == 8
                and (v.get("audio_rms") or 0) > 0), v

    def ae_verify_without_audio():
        mp4 = os.path.join(edit_dir, "silent.mp4")
        res = run("assemble_edit.py", {"out_path": mp4, "resolution": [160, 90], "render": True, "frames": [1, 8]})
        v = res.get("verify") or {}
        try:
            import aud
            aud.Sound(mp4).data()
            stream_absent = False
        except Exception:
            stream_absent = True
        return (v.get("ok") is True and v.get("audio_expected") is False and "audio_stream" not in v
                and res["output"]["audio_codec"] == "NONE" and stream_absent), v

    def ae_decode_colors():
        frames = list(range(1, 9))
        cols = decode_frame_colors(state["mp4"], frames, edit_dir)
        failures = []
        for i, (sid, a, b) in enumerate(SHOTS):
            hit = False
            for f in range(a, b + 1):
                c = cols[f]
                others = [c[k] for k in range(3) if k != i]
                if c[i] > 0.5 and max(others) < 0.35:
                    hit = True
            if not hit:
                failures.append(sid)
        # no repeated frame: the frame-by-frame level fades within each shot, so consecutive frames differ
        distinct = len({round(cols[f][i], 1) for i, (_, a, b) in enumerate(SHOTS) for f in range(a, b + 1)})
        return not failures and distinct >= 3, {"failed_shots": failures, "decoded": {k: [round(x, 2) for x in v] for k, v in cols.items()}}

    def ae_audio_present():
        """Decode the rendered mp4's audio with aud: silent before the 4-frame offset, tone after."""
        try:
            import aud
            snd = aud.Sound(state["mp4"])
            rate, chans = snd.specs
            data = np.asarray(snd.data(), dtype=np.float32).reshape(-1, chans)[:, 0]
        except Exception as exc:  # API missing / cannot decode: do not fake a pass
            return None, f"aud could not decode the mp4 audio: {exc!r}"
        t = lambda s: int(s * rate)
        early = float(np.sqrt(np.mean(data[:t(0.10)] ** 2))) if len(data) > t(0.10) else None
        late = float(np.sqrt(np.mean(data[t(0.22):t(0.32)] ** 2))) if len(data) > t(0.32) else None
        info = {"rate": rate, "samples": len(data), "rms_before_offset": early, "rms_after_offset": late}
        if early is None or late is None:
            return False, info
        return (late > 0.1 and early < 0.25 * late), info

    def ae_scaled_not_cropped():
        """Source 320x180, edit 160x90: a white marker near the left edge of S010 must survive (a crop loses it)."""
        me = bpy.data.meshes.new("__FilmMarker")
        me.from_pydata([(-0.25, 0, -0.25), (0.25, 0, -0.25), (0.25, 0, 0.25), (-0.25, 0, 0.25)], [], [(0, 1, 2, 3)])
        marker = bpy.data.objects.new("__FilmMarker", me)
        scene.collection.objects.link(marker)
        marker.location = (-2.7, -0.05, 0)  # 35 mm at 6 m: the frame spans x = -3.09..3.09
        mat = bpy.data.materials.new("__FilmMarkerMat")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        emi, out = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeOutputMaterial")
        emi.inputs["Color"].default_value = (1, 1, 1, 1)
        nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
        me.materials.append(mat)
        try:
            mp4 = os.path.join(edit_dir, "scaled.mp4")
            res = run("assemble_edit.py", {"out_path": mp4, "resolution": [160, 90], "render": True, "frames": [1, 2]})
            left = decode_frame_colors(mp4, [1], edit_dir, region=(0.03, 0.09, 0.42, 0.58))[1]
            scales = [s.get("scale") for s in res["strips"] if s["type"] == "SCENE"]
            return min(left) > 0.6 and scales == [0.5, 0.5, 0.5], {"left_edge_rgb": [round(c, 2) for c in left],
                                                                     "scales": scales}
        finally:
            bpy.data.objects.remove(marker)
            bpy.data.meshes.remove(me)
            bpy.data.materials.remove(mat)

    def ae_scale_integer_percentage():
        """Source 320x180 at 33 % renders 105x59 (integer division), so the fit is computed from that."""
        old = scene.render.resolution_percentage
        scene.render.resolution_percentage = 33
        try:
            res = run("assemble_edit.py", {"out_path": os.path.join(edit_dir, "pct.mp4"), "resolution": [160, 90]})
        finally:
            scene.render.resolution_percentage = old
        want = round(min(160 / 105, 90 / 59), 5)
        scales = [s.get("scale") for s in res["strips"] if s["type"] == "SCENE"]
        return scales == [want] * 3, {"scales": scales, "want": want}

    def ae_audio_strip_reload():
        """Secondary evidence: the mp4 reloads as a sound strip with a positive duration."""
        sc = bpy.data.scenes.new("__FilmAudioProbe")
        try:
            sc.sequence_editor_create()
            strip = sc.sequence_editor.strips.new_sound(name="a", filepath=state["mp4"], channel=1, frame_start=1)
            return strip.frame_duration > 0, strip.frame_duration
        finally:
            bpy.data.scenes.remove(sc)

    return [
        ("shot_list.markers_bound", sl_apply), ("shot_list.camera_placement", sl_cam_placement),
        ("shot_list.idempotent_user_marker_kept", sl_idempotent), ("shot_list.overlap_rejected", sl_overlap),
        ("shot_list.validation", sl_validation), ("shot_list.merge_no_duplicate_markers", sl_merge_no_duplicate_markers),
        ("preview.files_and_restore", pv_files), ("preview.sheet_layout", pv_sheet_layout),
        ("preview.tile_colors", pv_tile_colors), ("preview.subset_cols", pv_subset),
        ("preview.restore_on_failure", pv_restore_on_failure),
        ("assemble.structure", ae_structure), ("assemble.scene_strip_trim", ae_scene_strip_content),
        ("assemble.edit_stills", ae_edit_stills), ("assemble.fades_keyframed", ae_fades), ("assemble.ffmpeg_settings", ae_output_settings),
        ("assemble.credits", ae_credits), ("assemble.license_required", ae_requires_license),
        ("assemble.refuses_foreign_scene", ae_refuses_foreign_scene), ("assemble.idempotent", ae_idempotent), ("assemble.render_8_frames", ae_render),
        ("assemble.verify_with_audio", ae_verify_with_audio), ("assemble.verify_without_audio", ae_verify_without_audio),
        ("assemble.decoded_shot_colors", ae_decode_colors), ("assemble.audio_samples", ae_audio_present),
        ("assemble.audio_strip_reload", ae_audio_strip_reload), ("assemble.scaled_not_cropped", ae_scaled_not_cropped),
        ("assemble.scale_integer_percentage", ae_scale_integer_percentage),
    ]


def main(out_dir=None, only=None):
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "blender-film-tests")
    os.makedirs(out_dir, exist_ok=True)
    window = bpy.context.window
    original = window.scene if window else bpy.context.scene
    scene = bpy.data.scenes.new("__FilmTests")
    if window:
        window.scene = scene
    scenes_before = {s.name for s in bpy.data.scenes}
    objs_before = {o.name for o in bpy.data.objects}
    results, passed, not_checked = [], 0, []
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]) if not window else _Null():
            build_fixture(scene)
            for case_id, fn in build_cases(out_dir, scene):
                if only and not any(case_id.startswith(o) for o in only):
                    continue
                try:
                    out = fn()
                    ok, detail = out if isinstance(out, tuple) else (out, None)
                    if ok is None:
                        not_checked.append({"case": case_id, "reason": detail})
                        results.append({"case": case_id, "ok": None})
                        continue
                    results.append({"case": case_id, "ok": bool(ok), "detail": None if ok else detail})
                except Exception:
                    results.append({"case": case_id, "ok": False, "error": traceback.format_exc()[-900:]})
                passed += results[-1]["ok"] is True
    finally:
        if window:
            window.scene = original
        for name in {s.name for s in bpy.data.scenes} - scenes_before:
            bpy.data.scenes.remove(bpy.data.scenes[name])
        bpy.data.scenes.remove(scene)
        for name in {o.name for o in bpy.data.objects} - objs_before:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        for coll in (bpy.data.meshes, bpy.data.cameras, bpy.data.materials, bpy.data.worlds, bpy.data.sounds,
                     bpy.data.collections):
            for item in [i for i in coll if i.users == 0 or i.name.startswith(("__Film", "CAM_", "COL_Cameras"))]:
                coll.remove(item)
    report = {"blender": bpy.app.version_string, "passed": passed, "total": len(results),
              "failures": [r for r in results if r["ok"] is False], "not_checked": not_checked,
              "cases": [r["case"] for r in results], "out_dir": out_dir}
    with open(os.path.join(out_dir, "film_tests_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


class _Null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    sys.exit(0 if not result["failures"] else 1)
