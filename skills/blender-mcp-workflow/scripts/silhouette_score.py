"""Silhouette score of mesh objects against reference masks, per camera (read-only, no render needed).

Projects the evaluated triangles of the named objects through each named camera (lens, sensor fit, shift,
orthographic, and the near/far clip planes are honoured; triangles are clipped, so an object partly behind the
camera is cut where a render would cut it), rasterizes them with numpy at the reference image's size, and compares
with the reference mask: IoU, bounding-box drift and centroid drift per view, then a verdict against a threshold.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/silhouette_score.py", init_globals={"ARGS": {
        "objects": ["SM_Crate"],
        "views": [{"camera": "CAM_Front", "reference": "C:/proj/ref/front.png"}],
        "min_iou": 0.9}})["result"]

The silhouette is the union of the projected triangles: other objects do not hide it (name only the subject), and
features thinner than a pixel can drop out. Mask rows are top-down: bbox y counts from the top of the image.
Reference mask: the alpha channel when the image has any alpha below 1, otherwise everything that differs from the
background colour, which is read from the four corners (they must agree, or the script refuses and asks for an
alpha image). An object or camera that is not in the view layer (excluded collection) is refused, because its transform
is not evaluated. The loaded image datablocks are removed again; the scene is not changed.

ARGS:
    objects   (list[str], required) mesh objects whose union is the subject
    views     (list[dict], required) each {"camera": object name, "reference": image path,
              optional "mask": "auto" (default) | "alpha" | "background"}
    min_iou   (float) per-view pass threshold (default 0.9); the verdict is PASS only if every view passes
    bg_tol    (float) colour distance (0-1) from the background that counts as subject (default 0.1)
"""
import json
import math
import os
import sys

import bpy
import numpy as np


def _cli_args():
    """ARGS after `--`: one JSON object, or `--args-file <path.json>` (quoting-proof on every shell)."""
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not raw:
        return {}
    if raw[0] == "--args-file":
        with open(raw[1], encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"ARGS after '--' must be one JSON object, got {raw[0]!r}; "
                         "cmd/PowerShell mangle JSON quotes, so pass --args-file <path.json> instead") from exc


def load_reference(path, mode="auto", bg_tol=0.1):
    """Reference mask as a bool array (h, w), top row first, and info. The image datablock is always removed."""
    if not os.path.isfile(path):
        raise ValueError(f"reference image not found: {path!r}")
    img = bpy.data.images.load(path, check_existing=False)
    try:
        try:
            img.colorspace_settings.name = "Non-Color"
        except (TypeError, RuntimeError):
            pass
        w, h = int(img.size[0]), int(img.size[1])
        if w * h == 0:
            raise ValueError(f"image has no pixels (unreadable file?): {path!r}")
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
    finally:
        bpy.data.images.remove(img)
    px = np.flipud(buf.reshape(h, w, 4))  # Blender stores the bottom row first
    has_alpha = bool(px[..., 3].min() < 0.99)
    if mode not in ("auto", "alpha", "background"):
        raise ValueError(f"mask must be auto, alpha or background, got {mode!r}")
    used = ("alpha" if has_alpha else "background") if mode == "auto" else mode
    if used == "alpha":
        if not has_alpha:
            raise ValueError(f"{path!r} has no transparent pixels, so alpha cannot give a mask")
        mask = px[..., 3] >= 0.5
    else:
        k = max(1, min(3, h // 4, w // 4))
        corners = [px[:k, :k, :3], px[:k, -k:, :3], px[-k:, :k, :3], px[-k:, -k:, :3]]
        means = np.array([c.reshape(-1, 3).mean(0) for c in corners])
        if np.abs(means - means.mean(0)).max() > 0.05:
            raise ValueError(f"the four corners of {path!r} differ, so the background colour is unknown; "
                             "render with a transparent background or a flat one")
        mask = np.abs(px[..., :3] - means.mean(0)).max(-1) > bg_tol
    return mask, {"width": w, "height": h, "mask_from": used}


def _require_in_view_layer(obj):
    """An object in an excluded collection is not evaluated, so its world matrix is whatever it was when it was last
    evaluated: scoring it would silently use a stale transform. Refused instead."""
    if obj.name not in bpy.context.view_layer.objects:
        raise ValueError(f"{obj.name!r} is not in the view layer (its collection is excluded or it is not linked to "
                         "the scene), so its transform is not evaluated; include the collection first")


def collect_triangles(names, depsgraph):
    """World-space triangles (n, 3, 3) of the evaluated meshes, modifiers included."""
    out = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError(f"not a mesh object: {name!r}")
        _require_in_view_layer(obj)
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            co = np.empty(n * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            m = np.array(obj.matrix_world, dtype=np.float64)
            world = co.reshape(n, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
            me.calc_loop_triangles()
            tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri)
            out.append(world[tri.reshape(-1, 3)])
        finally:
            ev.to_mesh_clear()
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def _clip(poly, axis_z, keep_below):
    """Sutherland-Hodgman against the plane z = axis_z; keep points with z < axis_z (keep_below) or z > axis_z."""
    res = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        pin = (p[2] < axis_z) if keep_below else (p[2] > axis_z)
        qin = (q[2] < axis_z) if keep_below else (q[2] > axis_z)
        if pin:
            res.append(p)
        if pin != qin:
            t = (axis_z - p[2]) / (q[2] - p[2])
            res.append(p + (q - p) * t)
    return res


def _fill(mask, t):
    """Set the pixels whose centre lies inside the triangle t (3, 2) in pixel coordinates."""
    h, w = mask.shape
    x0 = max(0, math.ceil(t[:, 0].min() - 0.5))
    x1 = min(w - 1, math.floor(t[:, 0].max() - 0.5))
    y0 = max(0, math.ceil(t[:, 1].min() - 0.5))
    y1 = min(h - 1, math.floor(t[:, 1].max() - 0.5))
    if x0 > x1 or y0 > y1:
        return
    xs = np.arange(x0, x1 + 1) + 0.5
    ys = (np.arange(y0, y1 + 1) + 0.5)[:, None]
    (ax, ay), (bx, by), (cx, cy) = t
    if abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) < 1e-12:
        return  # degenerate: no area
    d1 = (xs - bx) * (ay - by) - (ax - bx) * (ys - by)
    d2 = (xs - cx) * (by - cy) - (bx - cx) * (ys - cy)
    d3 = (xs - ax) * (cy - ay) - (cx - ax) * (ys - ay)
    neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    mask[y0:y1 + 1, x0:x1 + 1] |= ~(neg & pos)


def rasterize(tris_world, cam, depsgraph, width, height):
    """Bool mask (height, width), top row first, of the triangles as seen by the camera object `cam`."""
    mask = np.zeros((height, width), dtype=bool)
    if len(tris_world) == 0:
        return mask
    rd = depsgraph.scene.render  # a render with non-square pixels (pixel_aspect_x/y) is projected with the same aspect
    proj = np.array(cam.calc_matrix_camera(depsgraph, x=width, y=height, scale_x=float(rd.pixel_aspect_x),
                                           scale_y=float(rd.pixel_aspect_y)), dtype=np.float64)
    view = np.array(cam.matrix_world.normalized().inverted(), dtype=np.float64)
    near, far = float(cam.data.clip_start), float(cam.data.clip_end)
    flat = np.concatenate([tris_world.reshape(-1, 3), np.ones((len(tris_world) * 3, 1))], axis=1)
    pc = (flat @ view.T)[:, :3].reshape(-1, 3, 3)
    z = pc[:, :, 2]
    inside = np.all(z < -near, 1) & np.all(z > -far, 1)
    outside = np.all(z >= -near, 1) | np.all(z <= -far, 1)
    polys = [t for t in pc[inside]]
    for t in pc[~inside & ~outside]:  # straddles a clip plane: cut it
        poly = _clip(list(t), -near, True)
        poly = _clip(poly, -far, False) if poly else poly
        for k in range(1, len(poly) - 1):
            polys.append(np.array([poly[0], poly[k], poly[k + 1]]))
    if not polys:
        return mask
    p = np.array(polys)
    clip = np.concatenate([p, np.ones((len(p), 3, 1))], axis=2) @ proj.T
    ndc = clip[..., :2] / clip[..., 3:4]
    pix = np.stack([(ndc[..., 0] * 0.5 + 0.5) * width, (1.0 - (ndc[..., 1] * 0.5 + 0.5)) * height], axis=-1)
    for t in pix:
        _fill(mask, t)
    return mask


def compare(mask, ref):
    """IoU and drift between two (h, w) masks."""
    h, w = ref.shape
    diag = math.hypot(w, h)
    inter = int(np.logical_and(mask, ref).sum())
    union = int(np.logical_or(mask, ref).sum())

    def box(m):
        ys, xs = np.nonzero(m)
        if len(xs) == 0:
            return None
        return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], (float(xs.mean() + 0.5), float(ys.mean() + 0.5))

    bm, br = box(mask), box(ref)
    r = {"iou": round(inter / union, 5) if union else 0.0, "pixels_scored": int(mask.sum()),
         "pixels_reference": int(ref.sum()), "bbox_scored": bm[0] if bm else None, "bbox_reference": br[0] if br else None}
    if bm and br:
        r["bbox_drift_px"] = round(float(max(abs(a - b) for a, b in zip(bm[0], br[0]))), 3)
        dc = math.hypot(bm[1][0] - br[1][0], bm[1][1] - br[1][1])
        r["centroid_drift_px"] = round(dc, 3)
        r["centroid_drift_frac"] = round(dc / diag, 5)
        r["size_ratio"] = [round((bm[0][2] - bm[0][0]) / (br[0][2] - br[0][0]), 4),
                           round((bm[0][3] - bm[0][1]) / (br[0][3] - br[0][1]), 4)]
    else:
        r["note"] = "the scored silhouette is empty (object outside the view or behind the camera)"
    return r


def _camera(name):
    cam = bpy.data.objects.get(name)
    if cam is None or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {name!r}")
    _require_in_view_layer(cam)
    return cam


def main(objects=None, views=None, min_iou=0.9, bg_tol=0.1, _library=False):
    if _library:  # lets a sibling script (fit_search.py) reuse the functions above without scoring anything
        return {"library": True}
    if not objects:
        raise ValueError("objects (list of mesh object names) is required")
    if not views:
        raise ValueError("views (list of {camera, reference}) is required")
    bpy.context.view_layer.update()  # objects linked a moment ago join the view layer, and transforms are current
    refs = []
    for v in views:
        if not isinstance(v, dict) or "camera" not in v or "reference" not in v:
            raise ValueError(f"each view needs camera and reference: {v!r}")
        _camera(v["camera"])
        refs.append(load_reference(v["reference"], v.get("mask", "auto"), float(bg_tol)))
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tris = collect_triangles(objects, depsgraph)
    out = []
    for v, (ref, info) in zip(views, refs):
        if not ref.any():
            raise ValueError(f"the reference mask for {v['reference']!r} is empty; nothing to compare")
        m = rasterize(tris, _camera(v["camera"]), depsgraph, info["width"], info["height"])
        r = compare(m, ref)
        r.update({"camera": v["camera"], "reference": v["reference"], "mask_from": info["mask_from"],
                  "size": [info["width"], info["height"]], "pass": r["iou"] >= float(min_iou)})
        out.append(r)
    ious = [r["iou"] for r in out]
    return {"verdict": "PASS" if all(r["pass"] for r in out) else "FAIL", "threshold_iou": float(min_iou),
            "mean_iou": round(sum(ious) / len(ious), 5), "min_iou_found": min(ious), "views": out,
            "triangles": int(len(tris))}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
