"""Render low-resolution preview stills of chosen shots (from scene["film_shots"]) and build a contact sheet
PNG so the agent can Read one image and judge every shot. All render settings it touches are restored.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/preview_frames.py", init_globals={"ARGS": {
        "out_dir": "<project>/film/previews", "shots": ["S010", "S020"], "frames_per_shot": 3}})["result"]

ARGS:
    out_dir          (str)  required; stills are written to <out_dir>/<shot>_<frame>.png
    shots            (list|None) shot ids to render (default: all, in shot order)
    frames_per_shot  (int)  default 3: first/middle/last; 1 = middle, 2 = first/last, n = evenly spaced
    resolution       ([w,h]) default [480, 270]
    engine           (str)  default "BLENDER_EEVEE"
    samples          (int)  default 8 (EEVEE render samples)
    sheet            (bool) build <out_dir>/contact_sheet.png (default True)
    cols             (int|None) contact sheet columns (default: auto from the tile aspect)
Returns file paths, the sheet layout (cols, rows, tile size, tile -> shot/frame) and the active camera per
shot. Restores frame, camera, resolution, engine, samples, filepath, file format and colour mode in `finally`.
Timeline markers bound to cameras would switch the camera at render time, so their bindings are lifted while
rendering and put back afterwards: each preview shows the shot's own camera.
"""
import json
import math
import os
import sys

import bpy
import numpy as np


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


def _pick_frames(start, end, n):
    if n <= 1:
        return [(start + end) // 2]
    frames = sorted({int(round(start + (end - start) * i / (n - 1))) for i in range(n)})
    return frames


def _build_sheet(tiles, cols, tile_w, tile_h, path):
    rows = math.ceil(len(tiles) / cols)
    sheet = np.zeros((rows * tile_h, cols * tile_w, 4), dtype=np.float32)
    sheet[..., 3] = 1.0
    layout = []
    for k, (png, shot, frame) in enumerate(tiles):
        img = bpy.data.images.load(png)
        try:
            if tuple(img.size) != (tile_w, tile_h):
                raise ValueError(f"{png} is {tuple(img.size)}, expected {(tile_w, tile_h)}")
            buf = np.empty(tile_w * tile_h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            buf = buf.reshape(tile_h, tile_w, 4)
        finally:
            bpy.data.images.remove(img)
        col, row = k % cols, k // cols  # row 0 is the top row of the sheet
        y0 = (rows - 1 - row) * tile_h  # pixel rows are stored bottom-up
        sheet[y0:y0 + tile_h, col * tile_w:(col + 1) * tile_w, :] = buf
        layout.append({"tile": k, "col": col, "row": row, "shot": shot, "frame": frame})
    out = bpy.data.images.new("film_contact_sheet", cols * tile_w, rows * tile_h, alpha=False)
    try:
        out.pixels.foreach_set(sheet.ravel())
        out.filepath_raw = path
        out.file_format = "PNG"
        out.save()
    finally:
        bpy.data.images.remove(out)
    return rows, layout


def main(out_dir=None, shots=None, frames_per_shot=3, resolution=(480, 270), engine="BLENDER_EEVEE",
         samples=8, sheet=True, cols=None):
    if not out_dir:
        raise ValueError("'out_dir' is required")
    scene = bpy.context.scene
    if not scene.get("film_shots"):
        raise ValueError("scene has no film_shots; run shot_list.py first")
    table = json.loads(scene["film_shots"])["shots"]
    if shots:
        unknown = [s for s in shots if s not in {t["id"] for t in table}]
        if unknown:
            raise ValueError(f"unknown shot ids: {unknown}")
        table = [t for t in table if t["id"] in set(shots)]
    for t in table:
        if bpy.data.objects.get(t["camera"]) is None:
            raise ValueError(f"{t['id']}: camera '{t['camera']}' not found")
    os.makedirs(out_dir, exist_ok=True)
    w, h = int(resolution[0]), int(resolution[1])

    r, im = scene.render, scene.render.image_settings
    saved = {"frame": scene.frame_current, "camera": scene.camera, "rx": r.resolution_x, "ry": r.resolution_y,
             "pct": r.resolution_percentage, "engine": r.engine, "filepath": r.filepath,
             "media": im.media_type, "fmt": im.file_format, "color_mode": im.color_mode,
             "samples": scene.eevee.taa_render_samples, "ext": r.use_file_extension}
    files, tiles, per_shot = [], [], {}
    bound = [(m, m.camera) for m in scene.timeline_markers if m.camera]
    try:
        for m, _ in bound:
            m.camera = None
        r.engine = engine
        if engine == "BLENDER_EEVEE":
            scene.eevee.taa_render_samples = int(samples)
        r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
        im.media_type = "IMAGE"
        im.file_format = "PNG"
        im.color_mode = "RGB"
        r.use_file_extension = True
        for t in table:
            cam = bpy.data.objects[t["camera"]]
            per_shot[t["id"]] = {"camera": cam.name, "frames": []}
            for frame in _pick_frames(t["start"], t["end"], int(frames_per_shot)):
                scene.frame_set(frame)
                scene.camera = cam
                base = os.path.join(out_dir, f"{t['id']}_{frame}")
                r.filepath = base
                bpy.ops.render.render(write_still=True)
                png = base + ".png"
                if not os.path.exists(png):
                    raise RuntimeError(f"render did not write {png}")
                files.append(png)
                tiles.append((png, t["id"], frame))
                per_shot[t["id"]]["frames"].append(frame)
        layout = None
        if sheet and tiles:
            ncols = int(cols) if cols else max(1, min(len(tiles), math.ceil(math.sqrt(len(tiles) * w / h))))
            sheet_path = os.path.join(out_dir, "contact_sheet.png")
            rows, tile_map = _build_sheet(tiles, ncols, w, h, sheet_path)
            layout = {"path": sheet_path, "cols": ncols, "rows": rows, "tile_size": [w, h],
                      "size": [ncols * w, rows * h], "tiles": tile_map}
    finally:
        for m, c in bound:
            m.camera = c
        scene.frame_set(saved["frame"])
        scene.camera = saved["camera"]
        r.resolution_x, r.resolution_y, r.resolution_percentage = saved["rx"], saved["ry"], saved["pct"]
        r.engine = saved["engine"]
        scene.eevee.taa_render_samples = saved["samples"]
        r.filepath = saved["filepath"]
        r.use_file_extension = saved["ext"]
        im.media_type = saved["media"]
        im.file_format = saved["fmt"]
        im.color_mode = saved["color_mode"]
    return {"files": files, "contact_sheet": layout, "shots": per_shot, "resolution": [w, h], "engine": engine,
            "samples": int(samples)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
