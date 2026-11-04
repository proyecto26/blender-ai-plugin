# Matching a model to a scan

Use this when a scan (your own photogrammetry, or an asset from a scan library) is the truth and a clean model has to agree
with it: a retopologised game mesh, a rebuilt prop, or a library asset placed in a scene that must look like the same
material and size. Cleaning the scan itself is in `scan-cleanup.md`.

## Order of work

1. Scale the scan from a real measurement (below).
2. Align the model to the scan: same origin, same forward axis, same orientation. Three landmarks you can find on both
   (two ends and one side point) are enough to check it by eye.
3. Measure the surface distance (recipe below). Fix the worst areas first.
4. Match the material: render scan and model under the same flat light and compare patches (below).
5. Only then bake. Baking from a misaligned or off-scale source puts wrong detail on the model.

## Scale from one measurement

Measure something real on the object (a tape measure on a door, a ruler in the photo, a part with a standard size). Then
`scale = real_metres / measured_scan_units`. Apply it to the scan and apply the scale (Ctrl+A). Check with a second
measurement on a different axis: if the two scale factors differ by more than 1%, the scan is stretched and needs fixing
before anything else.

## Surface distance check

For a game mesh, the question is how far the model's surface strays from the scan's. Measure both ways, because one
direction hides one kind of error:

- model to scan: points of the model that float above or sink below the scan (distance from model vertices to scan surface);
- scan to model: parts of the scan the model misses, such as a handle or a recess (distance from scan vertices to the model's
  surface). `tests/blender/test_iter13_docs.py` runs this direction on a scan with a small block standing off the sphere that the
  model lacks: model to scan worst case is 0.002 m while scan to model reports 0.356 m (Blender 5.2.3).

Starting tolerances, as a share of the object's bounding-box diagonal: mean under 0.2%, worst case under 1.5% for a
background asset, under 0.5% for a hero asset. A 1 m prop with a 1.7 m diagonal then allows worst-case 25 mm off for
background and 8.5 mm for hero. These are starting values to tune against what the camera can see. Do not apply them to the
decimated high-poly stage, which is judged by silhouette.

### Recipe (tested)

Builds a dense sphere as the "scan" and a 32 by 16 sphere as the "model" at the same size, measures both ways, and checks
that the check can fail: the same model shifted 5 cm must exceed the worst-case tolerance. The measurement reads the
evaluated mesh (modifiers such as Shrinkwrap or Displace count; a model pushed 5 cm by a modifier must fail) and refuses
an object in Edit Mode (leave Edit Mode first; the evaluated mesh would lag the live edit). It raises on any mismatch.
Everything it creates carries a `recipe_owner` tag; re-running removes only tagged data from an earlier run, and same-name
objects or meshes you already have are left alone (the recipe's copies get a `.001` suffix).

```python
import bpy
import bmesh
from mathutils.bvhtree import BVHTree

# Remove only data this recipe tagged on an earlier run; never look anything up by name.
TAG, OWNER = "recipe_owner", "scan-match"
for coll in (bpy.data.objects, bpy.data.meshes):
    for stale in [d for d in coll if d.get(TAG) == OWNER]:
        coll.remove(stale)

sc = bpy.context.scene

def sphere(name, loc, dense):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    if dense:
        bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.5)
    else:
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.5)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob[TAG] = me[TAG] = OWNER
    ob.location = loc
    sc.collection.objects.link(ob)
    return ob

scan = sphere("ScanSrc", (0, 0, 0), True)
low = sphere("ScanLow", (0, 0, 0), False)
shifted = sphere("ScanLowShifted", (0.05, 0, 0), False)
bpy.context.view_layer.update()

def world_bvh(ob):
    """World-space BVH of the object as it renders now: the evaluated mesh, so modifiers (Shrinkwrap, Displace) count.
    Edit Mode is refused, because the evaluated mesh then lags the live edit; leave Edit Mode first."""
    if ob.mode == "EDIT":
        raise RuntimeError(f"{ob.name} is in Edit Mode; switch to Object Mode before measuring")
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ev.to_mesh_clear()
    bm.transform(ob.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    pts = [v.co.copy() for v in bm.verts]
    bm.free()
    return tree, pts

def deviation(a, b):
    """Distances from every vertex of a to the surface of b."""
    tree_b, _ = world_bvh(b)
    _, pts_a = world_bvh(a)
    d = [tree_b.find_nearest(p)[3] for p in pts_a]
    return sum(d) / len(d), max(d)

def diagonal(ob):
    dims = ob.dimensions
    return (dims.x ** 2 + dims.y ** 2 + dims.z ** 2) ** 0.5

def verdict(model, mean_tol=0.002, worst_tol=0.015):
    diag = diagonal(scan)
    m2s = deviation(model, scan)       # model vertices to the scan surface
    s2m = deviation(scan, model)       # scan vertices to the model surface
    worst = max(m2s[1], s2m[1])
    mean = max(m2s[0], s2m[0])
    return {"mean_pct": round(100 * mean / diag, 3), "worst_pct": round(100 * worst / diag, 3),
            "ok": mean / diag <= mean_tol and worst / diag <= worst_tol}

good = verdict(low)
bad = verdict(shifted)
assert good["ok"], good
assert not bad["ok"], f"a 5 cm shift passed the check: {bad}"

# The check must also see the model as it is now: modifiers count, and Edit Mode is refused.
modded = sphere("ScanLowModded", (0, 0, 0), False)
disp = modded.modifiers.new("Push", "DISPLACE")
disp.strength, disp.mid_level = 0.05, 0.0  # no texture: pushes every vertex 5 cm along its normal
bpy.context.view_layer.update()
with_mod = verdict(modded)
assert not with_mod["ok"], f"a model pushed 5 cm by a modifier passed the check: {with_mod}"
edit_refused = False
bpy.context.view_layer.objects.active = low
low.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
try:
    verdict(low)
except RuntimeError:
    edit_refused = True
finally:
    bpy.ops.object.mode_set(mode="OBJECT")
assert edit_refused, "verdict() measured a model that is in Edit Mode"
result = {"matching_model": good, "shifted_model": bad, "modifier_model": with_mod, "edit_mode_refused": edit_refused}
```

Result when run on Blender 5.2.3: matching model mean 0.15% and worst 0.26% of the diagonal (pass); the model shifted 5 cm
mean 1.45% and worst 3.11% (fail).

What the checks prove: the two-way measurement passes a model that matches and fails one that is 5 cm off. A pass here does
not mean the model is good, only that it stays within the tolerance of the scan. Missing fine detail (rivets, a seam) is the
bake's job.

## Material match

Render the scan and the model with the same flat, neutral light and the same camera. Compare three or four patches of the
same area by eye side by side, and with the average colour of each patch. If the averages differ by more than about 10% in
lightness, the model's albedo is wrong; if lightness agrees but the surface reads different, roughness is wrong.
Values for common materials are in `pbr-values.md`. If the scan's albedo carries shadows, remove them first
(`scan-cleanup.md`, Albedo Extraction).

## Library scans (Megascans)

Check the terms before you use a library scan in a project. As Epic's FAQ states: Megascans stopped being buyable with
points from 2025 and are sold on Fab; assets you acquired earlier stay under the licence in force when you got them;
Quixel.com and Bridge hold them but are to be sunset eventually, so download what you need to disk; Fab offers Unreal and
Unity formats and others, with no one-click export into 3D tools, so assets are downloaded and imported by hand. Source:
https://forums.unrealengine.com/t/quixel-to-fab-transition-faqs/2033839 . This plugin does not download assets from inside
Blender: fetch the files yourself, then import and scale them as above.
