# Mocap cleanup

Motion capture arrives as a key on every frame of every channel. It carries sensor noise, single-frame spikes, rotation
flips and drift. Clean it in this order; each step makes the next one safer.

| # | Step | What goes wrong if skipped |
|---|---|---|
| 1 | Match scene fps and frame range to the capture | everything plays fast or slow, loops do not close |
| 2 | Unwrap Euler rotations | a 360 degree flip between two frames spins the limb in one frame |
| 3 | Remove spikes | one bad frame becomes a visible pop; smoothing alone smears it over its neighbours |
| 4 | Smooth lightly | jitter stays; or, over-smoothed, hits and footfalls go soft |
| 5 | Reduce keys | hundreds of keys per channel make the clip impossible to edit |
| 6 | Fix foot contact and root drift | feet slide, the character wanders off the loop |
| 7 | Check the cycle seam and the export | pop at the loop point; engine sees different curves |

## Starting values

These are starting points for a 30 fps clip, to be tuned by looking at the curves.

| Setting | Start | Notes |
|---|---|---|
| Spike test | value more than 0.5 m (location) or 0.5 rad (rotation) from the median of 5 neighbours | tune to the clip's speed: a fast punch legitimately moves far in a few frames |
| Smoothing | gaussian, sigma 1 to 2 frames | stay at 1 for impacts, hit reactions and anything that must snap |
| Key reduction tolerance | 0.005 m on location, 0.01 rad (about 0.6 degrees) on rotation | the largest error the simplified curve may have at any original frame |
| Keep keys on | contact frames, loop start and end | reduction can remove a key that defines a plant |

## Recipe (tested)

Makes a synthetic capture on an empty named `MocapDemo`: a sine move with noise, one 1.5 m spike at frame 41, and a rotation
that jumps by 2 pi at frame 71. It then unwraps, despikes, smooths and reduces the keys, and checks against the known clean
curve. The sine and noise come from a fixed seed, so the numbers are repeatable. It raises if the cleaned curve is not
closer to the truth than the noisy one, if keys are not reduced, if the rotation still flips, or if the cleaned rotation
has drifted from the true ramp (so a rotation replaced by a constant fails). Everything it creates carries a `recipe_owner`
tag; re-running removes only tagged data from an earlier run, and an object or action of yours with the same name is left alone.

```python
import math
import bpy
import numpy as np
from bpy_extras import anim_utils

# Everything this recipe creates is tagged; a re-run removes only tagged data from an earlier run. Data you already have
# with the same name is never touched: the new data simply gets a .001 name, and the recipe uses references, not names.
TAG = "recipe_owner"
OWNER = "mocap-cleanup"
for coll in (bpy.data.objects, bpy.data.actions):
    for stale in [d for d in coll if d.get(TAG) == OWNER]:
        coll.remove(stale)

# synthetic capture
n = 120
t = np.arange(n)
rng = np.random.default_rng(12)
truth = np.sin(t / 15.0)
noisy = truth + rng.normal(0.0, 0.03, n)
noisy[40] += 1.5                                           # spike at frame 41
rot = 3.0 + 0.02 * t
rot = np.where(t >= 70, rot - 2 * math.pi, rot)            # flip at frame 71
true_rot = 3.0 + 0.02 * t

ob = bpy.data.objects.new("MocapDemo", None)
bpy.context.scene.collection.objects.link(ob)
ob.rotation_mode = "XYZ"
for f in range(n):
    ob.location.x = float(noisy[f])
    ob.rotation_euler.z = float(rot[f])
    ob.keyframe_insert("location", index=0, frame=f + 1)
    ob.keyframe_insert("rotation_euler", index=2, frame=f + 1)
ob[TAG] = OWNER
ad = ob.animation_data
ad.action[TAG] = OWNER
bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
curves = {fc.data_path: fc for fc in bag.fcurves}

def read(fc):
    return np.array([k.co[1] for k in fc.keyframe_points])

def despike(v, limit, window=5):
    pad = window // 2
    padded = np.pad(v, pad, mode="edge")
    med = np.array([np.median(padded[i:i + window]) for i in range(len(v))])
    bad = np.abs(v - med) > limit
    return np.where(bad, med, v), int(bad.sum())

def smooth(v, sigma):
    r = int(3 * sigma)
    w = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    w /= w.sum()
    return np.convolve(np.pad(v, r, mode="edge"), w, mode="valid")

def reduce_keys(frames, v, tol):
    """Ramer-Douglas-Peucker on (frame, value): keep a key only if dropping it errs by more than tol."""
    keep = {0, len(v) - 1}
    stack = [(0, len(v) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        line = v[a] + (v[b] - v[a]) * (frames[a + 1:b] - frames[a]) / (frames[b] - frames[a])
        err = np.abs(v[a + 1:b] - line)
        i = int(err.argmax())
        if err[i] > tol:
            m = a + 1 + i
            keep.add(m)
            stack += [(a, m), (m, b)]
    return sorted(keep)

def rewrite(fc, frames, values, keep):
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(keep))
    for slot, i in zip(kp, keep):
        slot.co = (float(frames[i]), float(values[i]))
        slot.interpolation = "BEZIER"
    fc.update()

report = {}
for path, limit, tol, unwrap in (("location", 0.5, 0.005, False), ("rotation_euler", 0.5, 0.01, True)):
    fc = curves[path]
    frames = np.array([k.co[0] for k in fc.keyframe_points])
    v = read(fc)
    before_keys = len(v)
    if unwrap:
        v = np.unwrap(v)
    v, spikes = despike(v, limit)
    v = smooth(v, 1.5)
    keep = reduce_keys(frames, v, tol)
    rewrite(fc, frames, v, keep)
    report[path] = {"keys_before": before_keys, "keys_after": len(keep), "spikes_removed": spikes}

loc, rotc = curves["location"], curves["rotation_euler"]
frames = np.arange(1, n + 1)
after_loc = np.array([loc.evaluate(float(f)) for f in frames])
after_rot = np.array([rotc.evaluate(float(f)) for f in frames])
rms = lambda a, b: float(np.sqrt(np.mean((a - b) ** 2)))
report["rms_vs_truth_before"] = round(rms(noisy, truth), 4)
report["rms_vs_truth_after"] = round(rms(after_loc, truth), 4)
report["max_rot_step_before"] = round(float(np.abs(np.diff(rot)).max()), 3)
report["max_rot_step_after"] = round(float(np.abs(np.diff(after_rot)).max()), 3)
report["rot_rms_vs_truth_before"] = round(rms(rot - rot[0], true_rot - true_rot[0]), 4)
report["rot_rms_vs_truth_after"] = round(rms(after_rot - after_rot[0], true_rot - true_rot[0]), 4)

assert report["location"]["spikes_removed"] >= 1, "spike not found"
assert report["rms_vs_truth_after"] < report["rms_vs_truth_before"] / 3, report
assert report["location"]["keys_after"] < n / 2, report
assert report["max_rot_step_after"] < 0.5, report
assert report["rot_rms_vs_truth_after"] < 0.1, report      # the rotation must still follow the true ramp, not just stop flipping
assert report["rot_rms_vs_truth_after"] < report["rot_rms_vs_truth_before"] / 10, report
result = report
```

Result when run on Blender 5.2.3: location 120 keys down to 45 with 1 spike removed; rotation 120 keys down to 4; error against the
known curve 0.141 down to 0.016; largest rotation step between frames 6.26 rad down to 0.025; rotation error against the true ramp 4.06 rad down to 0.043. The smoothed rotation ends
sit about 0.04 rad off the truth because the filter pulls the first and last frames of a ramp toward their neighbours: for
a loop, keep the end frames out of the smoothing.

What the checks prove: on a clip with a known answer, the spike is removed, noise error drops, keys are reduced, and the
rotation flip is gone. They do not prove the settings suit your clip: real capture has foot contacts and fast moves
that a sine does not. Always scrub the cleaned curves next to the original.

Blender's Graph Editor has its own operators for the same jobs (Euler Filter, Clean Channels, Decimate, Smooth). They need a
Graph Editor area to run, so they are not in the recipe runner and are untested here; the recipe above works from any
context.

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Limb snaps or spins for one frame | Euler flip, or a spike | unwrap, then despike; check the value 1 frame either side |
| Punches and landings feel soft | smoothing sigma too high | sigma 1, or smooth only the channels that jitter |
| Cleaned curve overshoots between keys | Bezier handles on a coarse reduction | lower the tolerance, or use linear interpolation on those keys |
| Loop pops at the seam | first and last pose differ | blend the last frames toward the first, or cut the clip at matching poses |
| Feet slide on the ground | root motion and leg motion disagree | pin feet with IK on contact frames; do not fix by smoothing |
| Clip plays at the wrong speed | scene fps differs from capture fps | set fps first, then retime |
