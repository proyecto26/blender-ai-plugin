"""Build the film edit in a separate EDIT scene: one scene strip per shot (in order, trimmed to the shot's
frame range, using that shot's camera), then sound strips from user-provided audio files, FFmpeg H.264/AAC
output, and optionally render the mp4. The source scene's settings are never changed. Rerunning rebuilds
the strips of the same edit scene.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/assemble_edit.py", init_globals={"ARGS": {
        "out_path": "<project>/film/final.mp4",
        "audio": [{"path": "<project>/music/theme.wav", "license": "CC0", "volume": 0.8, "fade_in": 1.0,
                   "fade_out": 2.0, "title": "Theme", "author": "someone"}],
        "render": False}})["result"]

ARGS:
    out_path      (str)  required; .mp4 path. <dir>/audio_credits.json is written next to it.
    source_scene  (str|None) scene holding film_shots (default: current scene)
    edit_scene    (str)  name of the edit scene (default "EDIT"; created, or rebuilt only if this script made it)
    audio         (list) each: path (str, an existing file the user provided), license (str, REQUIRED, e.g.
                  "CC0", "CC-BY-4.0", "user-owned"), channel (int, default 2+index), start_frame (int, edit
                  frame, default 1), volume (float, default 1.0), fade_in / fade_out (seconds, default 0),
                  and optional title, author, source_url, notes (copied to the credits file).
    render        (bool) render the edit scene's animation to out_path (default False); the rendered file is read
                  back into `verify`: frames and size, and with audio a decoded stream of the right length
    frames        ([start, end]|None) limit the edit frame range (for tests / quick checks)
    resolution    ([w, h]|None) edit resolution (default: the source scene's)
Shots are laid back to back from edit frame 1 (gaps in the source timeline are dropped). The script never
downloads audio and never generates sound. Without `audio` the mp4 gets no audio stream at all.
"""
import json
import os
import sys

import bpy


OWNER_KEY = "film_edit_owner"  # set on scenes this script creates; any other scene is never rebuilt


def _verify(path, frames_expected, size, fps, audio_expected):
    """Read the rendered mp4 back. Audio absence is known from the encoder setting, so it is only probed when
    audio was supplied; then a decode error or a stream of the wrong length is a FAIL, never a pass."""
    if not os.path.isfile(path):
        return {"checked": False, "ok": False, "reason": "no output file"}
    clip = bpy.data.movieclips.load(path)
    try:
        out = {"checked": True, "frames": clip.frame_duration, "size": list(clip.size),
               "audio_expected": audio_expected}
    finally:
        bpy.data.movieclips.remove(clip)
    ok = out["frames"] == frames_expected and out["size"] == list(size)
    if audio_expected:
        try:
            import aud
            import numpy as np
            snd = aud.Sound(path)
            rate = snd.specs[0]
            data = np.asarray(snd.data(), dtype=np.float32)
            seconds = len(data) / rate
            out.update(audio_stream=len(data) > 0, audio_seconds=round(seconds, 3),
                       audio_rms=round(float(np.sqrt(np.mean(data ** 2))) if len(data) else 0.0, 5))
            ok = ok and len(data) > 0 and abs(seconds - frames_expected / fps) <= 2 / fps + 0.05
        except Exception as exc:  # no stream or undecodable: the file does not carry the audio it should
            out.update(audio_stream=False, error=repr(exc))
            ok = False
    out["ok"] = ok
    return out

def _cli_args():
    if "--" not in sys.argv:
        return {}
    raw = sys.argv[sys.argv.index("--") + 1:]
    if not raw:
        return {}
    try:
        if raw[0] == "--args-file":
            if len(raw) < 2:
                raise ValueError("--args-file needs a path")
            with open(raw[1], encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(raw[0])
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"ARGS must be a JSON object or '--args-file <path.json>': {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("ARGS must be a JSON object")
    return data


TEMP_CHANNEL = 64


def _copy_color_management(src, dst):
    dst.display_settings.display_device = src.display_settings.display_device
    sv, dv = src.view_settings, dst.view_settings
    dv.view_transform = sv.view_transform
    dv.look = sv.look
    dv.exposure = sv.exposure
    dv.gamma = sv.gamma


def _check_audio(items):
    problems = []
    for i, a in enumerate(items):
        if not isinstance(a, dict) or not a.get("path"):
            problems.append(f"audio[{i}]: needs 'path'")
            continue
        if not os.path.isfile(a["path"]):
            problems.append(f"audio[{i}]: file not found: {a['path']}")
        if not a.get("license"):
            problems.append(f"audio[{i}]: 'license' is required (e.g. CC0, CC-BY-4.0, user-owned)")
    if problems:
        raise ValueError("invalid audio: " + "; ".join(problems))


def _add_audio(edit, items, fps):
    strips_out, info = [], []
    end_of_film = edit.frame_end
    for i, a in enumerate(items):
        channel = int(a.get("channel", 2 + i))
        start = int(a.get("start_frame", 1))
        volume = float(a.get("volume", 1.0))
        name = f"AUD_{os.path.splitext(os.path.basename(a['path']))[0]}"
        strip = edit.sequence_editor.strips.new_sound(name=name, filepath=os.path.abspath(a["path"]),
                                                      channel=channel, frame_start=start)
        strip.volume = volume
        f0 = strip.frame_final_start
        f1 = min(strip.frame_final_end - 1, end_of_film)
        fade_in = int(round(float(a.get("fade_in", 0)) * fps))
        fade_out = int(round(float(a.get("fade_out", 0)) * fps))
        keys = []
        if fade_in > 0:
            keys += [(f0, 0.0), (min(f0 + fade_in, f1), volume)]
        if fade_out > 0:
            keys += [(max(f1 - fade_out, f0), volume), (f1, 0.0)]
        for frame, value in keys:
            strip.volume = value
            strip.keyframe_insert("volume", frame=frame)
        strip.volume = volume  # restore the static value; keyframes drive it on playback/render
        sound = strip.sound
        strips_out.append({"name": strip.name, "type": "SOUND", "channel": strip.channel,
                           "frame_start": strip.frame_final_start, "frame_end": strip.frame_final_end - 1,
                           "volume": volume, "fades": {"in_frames": fade_in, "out_frames": fade_out},
                           "keyframes": [list(k) for k in keys]})
        info.append({"path": a["path"], "strip": strip.name, "frame_duration": strip.frame_duration,
                     "seconds": round(strip.frame_duration / fps, 3),
                     "samplerate": getattr(sound, "samplerate", None),
                     "channels": getattr(sound, "channels", None), "license": a["license"]})
    return strips_out, info


def _write_credits(out_dir, items):
    path = os.path.join(out_dir, "audio_credits.json")
    entries = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                for e in json.load(fh).get("entries", []):
                    entries[e["file"]] = e
        except (json.JSONDecodeError, OSError, AttributeError, KeyError):
            entries = {}
    for i, a in enumerate(items):
        key = os.path.abspath(a["path"]).replace("\\", "/")
        entry = {"file": key, "license": a["license"], "channel": int(a.get("channel", 2 + i)),
                 "start_frame": int(a.get("start_frame", 1)), "volume": float(a.get("volume", 1.0))}
        for opt in ("title", "author", "source_url", "notes"):
            if a.get(opt):
                entry[opt] = a[opt]
        entries[key] = entry
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"entries": list(entries.values())}, fh, indent=2)
    return path


def main(out_path=None, source_scene=None, edit_scene="EDIT", audio=None, render=False, frames=None,
         resolution=None):
    if not out_path:
        raise ValueError("'out_path' is required")
    if not out_path.lower().endswith(".mp4"):
        raise ValueError("out_path must end with .mp4")
    src = bpy.data.scenes.get(source_scene) if source_scene else bpy.context.scene
    if src is None:
        raise ValueError(f"source scene not found: {source_scene}")
    if edit_scene == src.name:
        raise ValueError("edit_scene must differ from the source scene")
    if not src.get("film_shots"):
        raise ValueError("source scene has no film_shots; run shot_list.py first")
    contract = json.loads(src["film_shots"])
    shots = sorted(contract["shots"], key=lambda s: s["start"])
    fps = int(contract.get("fps", src.render.fps))
    audio = audio or []
    _check_audio(audio)
    for s in shots:
        cam = bpy.data.objects.get(s["camera"])
        if cam is None:
            raise ValueError(f"{s['id']}: camera '{s['camera']}' not found")
        if s["start"] < src.frame_start or s["end"] > src.frame_end:
            raise ValueError(f"{s['id']} {s['start']}-{s['end']} is outside the source frame range "
                             f"{src.frame_start}-{src.frame_end}; rerun shot_list.py")
    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)

    edit = bpy.data.scenes.get(edit_scene)
    if edit is not None and not edit.get(OWNER_KEY):
        raise ValueError(f"scene '{edit_scene}' exists and was not made by assemble_edit.py; "
                         "pass another edit_scene name (nothing was changed)")
    if edit is None:
        edit = bpy.data.scenes.new(edit_scene)
        edit[OWNER_KEY] = True
    if edit.animation_data:
        edit.animation_data_clear()
    edit.sequence_editor_create()
    seq = edit.sequence_editor
    for old in list(seq.strips_all):
        seq.strips.remove(old)

    cursor, strips_out = 1, []
    for s in shots:
        strip = seq.strips.new_scene(name=s["id"], scene=src, channel=TEMP_CHANNEL, frame_start=cursor)
        strip.scene_camera = bpy.data.objects[s["camera"]]
        strip.frame_offset_start = s["start"] - src.frame_start
        strip.frame_offset_end = src.frame_end - s["end"]
        strip.frame_start = cursor - strip.frame_offset_start
        strip.channel = 1
        strips_out.append({"name": strip.name, "type": "SCENE", "channel": strip.channel, "camera": s["camera"],
                           "frame_start": strip.frame_final_start, "frame_end": strip.frame_final_end - 1,
                           "frames": strip.frame_final_duration})
        cursor += s["end"] - s["start"] + 1
    total = cursor - 1

    edit.render.fps = fps
    edit.render.fps_base = 1.0
    edit.frame_start = 1
    edit.frame_end = total
    if frames:
        edit.frame_start, edit.frame_end = int(frames[0]), min(int(frames[1]), total)
    edit.render.resolution_x, edit.render.resolution_y = (
        (int(resolution[0]), int(resolution[1])) if resolution else (src.render.resolution_x, src.render.resolution_y))
    edit.render.resolution_percentage = 100
    edit.render.use_sequencer = True
    _copy_color_management(src, edit)

    sound_strips, audio_info = _add_audio(edit, audio, fps)

    im, ff = edit.render.image_settings, edit.render.ffmpeg
    im.media_type = "VIDEO"
    im.file_format = "FFMPEG"
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "MEDIUM"
    ff.ffmpeg_preset = "GOOD"
    ff.audio_codec = "AAC" if audio else "NONE"  # no silent track when no audio was supplied
    ff.audio_bitrate = 192
    ff.audio_mixrate = 48000
    ff.audio_channels = "STEREO"
    edit.render.use_file_extension = False
    edit.render.filepath = out_path

    credits_path = _write_credits(out_dir, audio) if audio else None
    rendered = verify = None
    if render:
        bpy.ops.render.render(animation=True, scene=edit.name)
        rendered = {"exists": os.path.isfile(out_path), "bytes": os.path.getsize(out_path) if os.path.isfile(out_path) else 0}
        verify = _verify(out_path, edit.frame_end - edit.frame_start + 1,
                         (edit.render.resolution_x, edit.render.resolution_y), fps, bool(audio))
    return {"edit_scene": edit.name, "strips": strips_out + sound_strips, "total_frames": total,
            "frame_range": [edit.frame_start, edit.frame_end], "fps": fps,
            "resolution": [edit.render.resolution_x, edit.render.resolution_y], "audio": audio_info,
            "output": {"media_type": im.media_type, "file_format": im.file_format, "container": ff.format,
                       "codec": ff.codec, "audio_codec": ff.audio_codec, "path": out_path},
            "audio_credits": credits_path, "rendered": rendered, "verify": verify}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
