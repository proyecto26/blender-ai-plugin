# Depth from several reference images

One photo gives a silhouette and proportions. It does not give depth: a nose can be 3 cm or 8 cm long and the front view
looks the same. With two or more views of the same object you can measure depth instead of guessing it. Use this after the
analysis in `reference-image-match.md` when a dimension on the unseen axis matters.

## Pick the method

| You have | Method | Accuracy you can expect |
|---|---|---|
| Front, side and top drawings or flat-on photos | Read each axis from the view that shows it | Good if the views were shot far away with a long lens; see the error table |
| Two or more perspective photos from different positions | Match a camera per photo, then intersect the rays through the same feature | Millimetres to centimetres, set by camera matching and click precision |
| One photo | Neither. Ask for another view, or mark the depth as a guess in the brief | No measurement |

## Method A: flat-on views

Each view shows two axes. Front shows X and Z, side shows Y and Z, top shows X and Y.

1. Pick one dimension you know in real units (a door 2.05 m, a wheel diameter). Scale = known metres / its length in pixels.
   Do this once per view, because each photo has its own scale.
2. Measure the shared axis in both views. Front and side both show height Z. If the two heights differ by more than 5%
   after scaling, one view is not flat-on or one scale is wrong. Fix that before measuring anything else.
3. Put each image on its own plane, aligned to its axes, at the scale from step 1, and build against all of them.

Perspective makes parts nearer the camera look larger. For a subject of depth E at distance D, the nearest face is magnified
about D / (D - E/2) against the middle:

| Distance D | Depth E | Near face looks larger by |
|---|---|---|
| 2 m | 1 m | 33% |
| 5 m | 1 m | 11% |
| 10 m | 1 m | 5% |

Photos taken from close up cannot be used as flat views for anything deep. Use method B for those.

## Method B: triangulation

Needs a camera for each photo: position, direction, and focal length (from the photo's metadata if it has any). Place each
camera in Blender so the known parts of the model land on the matching parts of the photo, then for each feature read the
pixel position in each photo and intersect the two rays.

Error you should expect: one pixel of click error moves a point sideways by about `Z * sensor_width_mm / (lens_mm * width_px)`
at distance Z. With a 36 mm sensor, a 50 mm lens and a 1920 px image, 1 px is 1.9 mm at 5 m. Depth error grows when the two
rays are close to parallel, so use views at least 15 degrees apart, ideally 45 to 90.

Check each point by its ray gap, the distance between the two rays at their closest approach. A gap of a few millimetres
means the two clicks agree. A gap of centimetres means you clicked different features, or a camera is off.

### Recipe (tested)

Two cameras look at known points. Each point is projected to pixel coordinates, 0.5 px of noise is added, and the point is
triangulated back. It raises if any point comes back more than 1 cm off, if the ray gap is large for a correct pair, or if
a deliberately wrong pair (the same feature clicked 100 px away in one view) does not show a large ray gap. It also
refuses rays that are nearly parallel (under 15 degrees apart) or nearly opposite (over 165 degrees, which makes the
intersection equation divide by zero), and a result that lies behind either camera. Its objects carry a tag, so a re-run
removes only its own; same-name objects you already have are left alone.

```python
import math
import random
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

# A re-run removes only data this recipe tagged. Same-name data you already have is never touched: the new camera gets a
# .001 name, and the recipe holds references instead of looking things up by name.
TAG, OWNER = "recipe_owner", "reference-image-depth"
for coll in (bpy.data.objects, bpy.data.cameras):
    for stale in [d for d in coll if d.get(TAG) == OWNER]:
        coll.remove(stale)

sc = bpy.context.scene     # uses the scene's own render resolution and the camera sensor settings

def make_cam(name, loc, aim):
    cam = bpy.data.cameras.new(name)
    cam.lens = 50.0
    ob = bpy.data.objects.new(name, cam)
    ob[TAG] = cam[TAG] = OWNER
    sc.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob

cam_a = make_cam("TriCamA", (4.0, -4.0, 2.0), (0.0, 0.0, 0.5))
cam_b = make_cam("TriCamB", (-4.0, -3.0, 2.0), (0.0, 0.0, 0.5))
bpy.context.view_layer.update()

def to_pixel(cam, p):
    uv = world_to_camera_view(sc, cam, Vector(p))     # x right, y up, both 0..1 across the render frame
    return uv.x, uv.y

def ray(cam, uv):
    frame = cam.data.view_frame(scene=sc)            # frame corners in camera space, at one depth along -Z
    left, right = min(v.x for v in frame), max(v.x for v in frame)
    bottom, top = min(v.y for v in frame), max(v.y for v in frame)
    local = Vector((left + uv[0] * (right - left), bottom + uv[1] * (top - bottom), frame[0].z))
    return cam.matrix_world.translation.copy(), (cam.matrix_world.to_3x3() @ local).normalized()

def triangulate(ray_a, ray_b):
    (o1, d1), (o2, d2) = ray_a, ray_b
    angle = math.degrees(d1.angle(d2))
    if angle < 15.0 or angle > 165.0:
        raise ValueError(f"rays are {angle:.1f} degrees apart: nearly parallel or opposite, depth is not measurable")
    w = o1 - o2
    a, b, c, d, e = d1.dot(d1), d1.dot(d2), d2.dot(d2), d1.dot(w), d2.dot(w)
    den = a * c - b * b
    s, t = (b * e - c * d) / den, (a * e - b * d) / den
    if s <= 0.0 or t <= 0.0:
        raise ValueError("the rays meet behind a camera: the two clicks cannot be the same point")
    p1, p2 = o1 + d1 * s, o2 + d2 * t
    return (p1 + p2) / 2, (p1 - p2).length

random.seed(7)
px = 1.0 / sc.render.resolution_x
def noisy(uv):
    return uv[0] + random.uniform(-0.5, 0.5) * px, uv[1] + random.uniform(-0.5, 0.5) * px

points = [(0.3, 0.2, 0.5), (-0.4, 0.1, 1.2), (0.0, -0.3, 0.1), (0.5, 0.5, 0.9)]
errors, gaps = [], []
for p in points:
    est, gap = triangulate(ray(cam_a, noisy(to_pixel(cam_a, p))), ray(cam_b, noisy(to_pixel(cam_b, p))))
    errors.append((est - Vector(p)).length)
    gaps.append(gap)

# wrong pair: the same feature, clicked 100 px away in camera B
uv_b = to_pixel(cam_b, points[0])
wrong = (uv_b[0] + 100 * px, uv_b[1])
_, wrong_gap = triangulate(ray(cam_a, to_pixel(cam_a, points[0])), ray(cam_b, wrong))

def refused(ray_a, ray_b):
    try:
        triangulate(ray_a, ray_b)
    except ValueError as exc:
        return str(exc)
    return None

o = Vector((0.0, 0.0, 0.0))
up, down, tilt = Vector((0, 0, 1)), Vector((0, 0, -1)), Vector((0, math.sin(math.radians(5)), math.cos(math.radians(5))))
assert refused((o, up), (Vector((1, 0, 0)), down)), "opposing rays were not refused"
assert refused((o, up), (Vector((1, 0, 0)), up)), "parallel rays were not refused"
assert refused((o, up), (Vector((1, 0, 0)), tilt)), "rays 5 degrees apart were not refused"
assert refused((o, Vector((1, 0, 0))), (Vector((5, -5, 0)), Vector((0, -1, 0)))), "a point behind a camera was accepted"
assert max(errors) < 0.01, f"triangulated point off by {max(errors)} m"
assert max(gaps) < 0.01, f"ray gap {max(gaps)} m on a correct pair"
assert wrong_gap > 0.05, f"wrong pair was not flagged (gap {wrong_gap})"
result = {"max_error_m": round(max(errors), 5), "max_gap_m": round(max(gaps), 5), "wrong_pair_gap_m": round(wrong_gap, 4),
          "degenerate_rays_refused": 4}
```

Result when run on Blender 5.2.3: largest point error 1.4 mm, largest ray gap 0.5 mm on correct pairs, 56 mm ray gap on the
wrong pair. Four degenerate cases are refused: opposing rays (the unguarded formula raised `ZeroDivisionError` at 180
degrees), parallel rays, rays 5 degrees apart, and rays that meet behind a camera.

What the checks prove: with known cameras the ray intersection recovers points to millimetres, and a bad click shows up as
a large gap. They do not cover the hard part in practice, which is getting the cameras right from real photos. Blender's
motion tracking solver is built for video clips; whether it suits a few stills was not tested here.

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Heights from two views disagree by over 5% | a view is not flat-on, or one scale is wrong | re-measure the known dimension in each view |
| Ray gap of centimetres on one point | different features clicked, or a camera is off | re-click; check the camera with a point you trust |
| Depth jumps by centimetres between nearly identical clicks | rays almost parallel | add a view from further around |
| All points off in the same direction | a camera position or lens is wrong | recheck that camera first, using the lens from the photo metadata |
| Model fits the front photo and looks thin from the side | depth was guessed | measure or ask for the missing view |
