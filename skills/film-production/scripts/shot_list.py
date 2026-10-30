"""Apply a shot list to the current scene: one timeline marker per shot (named by the shot id, at the
shot's start frame, bound to the shot's camera), the scene frame range/fps, and the shared film contract
`scene["film_shots"]` (a JSON string that other skills read).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/shot_list.py", init_globals={"ARGS": {
        "fps": 24,
        "shots": [{"id": "S010", "start": 1, "end": 48, "camera": "CAM_S010", "lens_mm": 35,
                   "motion": "still", "beat": "Setup", "description": "Wide of the mascot at the door",
                   "camera_location": [0, -6, 1.5], "look_at": [0, 0, 1]}]}})["result"]

ARGS:
    shots          (list) each: id (str, unique), start (int), end (int, >= start), camera (str, default
                   "CAM_<id>"), lens_mm (float, optional), motion ("still"|"moving", default "still"),
                   beat (str), description (str), camera_location ([x,y,z], optional), look_at ([x,y,z], optional).
                   camera_location/look_at only apply to cameras this script creates.
    fps            (int)  scene frame rate (default 24)
    create_cameras (bool) create missing cameras (default True); False makes a missing camera an error.
                   Created cameras sit at camera_location (default origin) looking at look_at (default -Y).
    replace        (bool) default True: this call's shot list replaces the previous one (markers of the old
                   shots are removed). False merges into the existing list. User markers (names that are
                   not a shot id) are never touched.
Returns the shot table, frame range, created cameras and warnings. Raises ValueError listing every
validation problem (duplicate ids, start > end, overlaps, missing cameras) before changing the scene.
"""
import json
import math
import sys

import bpy
from mathutils import Vector

MOTIONS = ("still", "moving")


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


def _cameras_collection(scene):
    col = bpy.data.collections.get("COL_Cameras")
    if col is None:
        col = bpy.data.collections.new("COL_Cameras")
    if col not in scene.collection.children_recursive:
        scene.collection.children.link(col)
    return col


def _make_camera(scene, name, lens, location, look_at):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.lens = lens if lens else 35.0
    _cameras_collection(scene).objects.link(cam)
    cam.location = Vector(location or (0.0, 0.0, 0.0))
    if look_at is not None:
        direction = Vector(look_at) - cam.location
        if direction.length > 1e-6:
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    else:
        cam.rotation_euler = (math.pi / 2, 0.0, math.pi)  # looks along -Y
    return cam


def _normalize(raw_shots, create_cameras):
    problems, shots = [], []
    for i, raw in enumerate(raw_shots):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            problems.append(f"shot #{i}: needs a non-empty string 'id'")
            continue
        sid = raw["id"]
        try:
            start, end = int(raw["start"]), int(raw["end"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"{sid}: needs integer 'start' and 'end'")
            continue
        if start > end:
            problems.append(f"{sid}: start {start} > end {end}")
        motion = raw.get("motion", "still")
        if motion not in MOTIONS:
            problems.append(f"{sid}: motion must be one of {MOTIONS}")
        shots.append({"id": sid, "start": start, "end": end, "camera": raw.get("camera") or f"CAM_{sid}",
                      "lens_mm": raw.get("lens_mm"), "motion": motion, "beat": raw.get("beat", ""),
                      "description": raw.get("description", ""), "camera_location": raw.get("camera_location"),
                      "look_at": raw.get("look_at")})
    return shots, problems


def _validate(shots, create_cameras):
    problems = []
    seen = set()
    for s in shots:
        if s["id"] in seen:
            problems.append(f"duplicate shot id {s['id']}")
        seen.add(s["id"])
        obj = bpy.data.objects.get(s["camera"])
        if obj is None and not create_cameras:
            problems.append(f"{s['id']}: camera '{s['camera']}' does not exist (create_cameras is false)")
        elif obj is not None and obj.type != "CAMERA":
            problems.append(f"{s['id']}: object '{s['camera']}' is not a camera")
    ordered = sorted(shots, key=lambda s: s["start"])
    for a, b in zip(ordered, ordered[1:]):
        if b["start"] <= a["end"]:
            problems.append(f"overlap: {a['id']} ({a['start']}-{a['end']}) and {b['id']} ({b['start']}-{b['end']})")
    return ordered, problems


def main(shots=None, fps=24, create_cameras=True, replace=True):
    if not shots:
        raise ValueError("'shots' must be a non-empty list")
    scene = bpy.context.scene
    new_shots, problems = _normalize(shots, create_cameras)

    previous = []
    if scene.get("film_shots"):
        try:
            previous = json.loads(scene["film_shots"]).get("shots", [])
        except (json.JSONDecodeError, AttributeError):
            previous = []
    new_ids = {s["id"] for s in new_shots}
    stale_ids = {p["id"] for p in previous} | new_ids  # our markers: rebuilt for every shot in the result
    if replace:
        merged = list(new_shots)
    else:
        kept = [p for p in previous if p["id"] not in new_ids]
        merged = [dict(p, camera_location=None, look_at=None) for p in kept] + list(new_shots)
    ordered, more = _validate(merged, create_cameras)
    problems += more
    if problems:
        raise ValueError("invalid shot list: " + "; ".join(problems))

    warnings, created = [], []
    for s in ordered:
        cam = bpy.data.objects.get(s["camera"])
        if cam is None:
            cam = _make_camera(scene, s["camera"], s["lens_mm"], s["camera_location"], s["look_at"])
            created.append(cam.name)
        else:
            if s["lens_mm"]:
                cam.data.lens = float(s["lens_mm"])
            if s["camera_location"] is not None or s["look_at"] is not None:
                if s["camera"] not in created:
                    warnings.append(f"{s['id']}: camera {cam.name} already exists; camera_location/look_at ignored")
        s["lens_mm"] = round(cam.data.lens, 3)
    cam_use = {}
    for s in ordered:
        cam_use.setdefault(s["camera"], []).append(s["id"])
    for cam_name, ids in cam_use.items():
        if len(ids) > 1:
            warnings.append(f"camera {cam_name} is shared by {', '.join(ids)}")

    # markers: replace only our own (named by shot id); user markers are untouched
    for marker in [m for m in scene.timeline_markers if m.name in stale_ids]:
        scene.timeline_markers.remove(marker)
    for s in ordered:
        marker = scene.timeline_markers.new(s["id"], frame=s["start"])
        marker.camera = bpy.data.objects[s["camera"]]

    scene.render.fps = int(fps)
    scene.render.fps_base = 1.0
    scene.frame_start = ordered[0]["start"]
    scene.frame_end = max(s["end"] for s in ordered)

    contract_shots = [{k: s[k] for k in ("id", "start", "end", "camera", "lens_mm", "motion", "beat", "description")}
                      for s in ordered]
    scene["film_shots"] = json.dumps({"version": 1, "fps": int(fps), "shots": contract_shots})

    table, prev_end = [], None
    for s in contract_shots:
        frames = s["end"] - s["start"] + 1
        gap = None if prev_end is None else s["start"] - prev_end - 1
        if gap:
            warnings.append(f"{s['id']}: {gap}-frame gap before this shot")
        table.append(dict(s, frames=frames, seconds=round(frames / fps, 3), gap_before=gap))
        prev_end = s["end"]
    return {"shots": table, "fps": int(fps), "frame_range": [scene.frame_start, scene.frame_end],
            "total_frames": sum(t["frames"] for t in table),
            "markers": [{"name": m.name, "frame": m.frame, "camera": m.camera.name if m.camera else None}
                        for m in scene.timeline_markers],
            "created_cameras": created, "warnings": warnings}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
