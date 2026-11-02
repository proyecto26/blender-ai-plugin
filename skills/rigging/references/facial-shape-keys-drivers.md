# Facial shape keys driven by bones

Use this when a face needs poses a bone cannot make (lip corners, brow shape, cheek puff) but the animator should still
work with a few bone or slider controls. Shape keys hold the poses; drivers connect them to controls.

## Set of keys

Minimum (matches the game minimum in `SKILL.md`): `jaw_open`, `blink_L`, `blink_R`, `brow_up_L`, `brow_up_R`, `smile`.
Name left/right keys with the same `_L` / `_R` suffix as the bones. Add keys only for expressions the shot needs; every key
is one more morph target to export and to test.

Rules:

- The Basis key is the neutral face. Never edit it after other keys exist unless you intend to move them all.
- Edit a key by changing vertex positions only. Adding or deleting vertices after keys exist breaks all of them.
- One key per pose. Combinations (smile + jaw open) are the sum of two keys; when the sum looks wrong, add a corrective key
  and drive it from both (see below).
- Keys that must never go negative or above 1: set `slider_min = 0` and `slider_max = 1`. Outside that range the face
  stretches past the sculpted pose.

## Two ways to drive a key

| Control | Driver variable | Use for |
|---|---|---|
| Bone rotation (jaw, eyelid bone) | `TRANSFORMS`, bone target, `ROT_X`, `LOCAL_SPACE` | motion that is really a rotation |
| Custom property on a control bone | `SINGLE_PROP`, path `pose.bones["ctrl"]["smile"]` | sliders for expressions with no bone |

Use a simple expression. `min(max(rot / 0.5, 0.0), 1.0)` maps a 0.5 rad jaw rotation to 1.0 and clamps both ends. A simple
expression is evaluated without running Python script code, so it keeps working when Blender's auto-run of Python scripts is
off; expressions that call your own functions do not. Set `rotation_mode = 'XYZ'` on the pose bone: with the default
quaternion mode `rotation_euler` is ignored and the driver reads zero.

Corrective key: add a key named `smile_jaw_fix`, then drive its value with `smile * jaw_open` (two `SINGLE_PROP` variables
reading the other keys' values). It is 0 unless both are on. This corrective setup is not in the tested recipe below.

## Recipe (tested)

Builds a sphere face proxy, an armature with a `jaw` bone and a `ctrl` bone, two shape keys with drivers, then checks the
result. It raises if a driver is invalid or the evaluated mesh does not move by the expected amount. Everything it creates
carries a `recipe_owner` tag; re-running removes only tagged data from an earlier run. An object, mesh or armature of yours
that happens to be named `FaceDemo` or `ARM_FaceDemo` is not touched (the recipe's copies get a `.001` suffix).

```python
import bpy
import bmesh

# Remove only data this recipe tagged on an earlier run; never look anything up by name.
TAG, OWNER = "recipe_owner", "facial-shape-keys-drivers"
for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures):
    for stale in [d for d in coll if d.get(TAG) == OWNER]:
        coll.remove(stale)

sc = bpy.context.scene
me = bpy.data.meshes.new("FaceDemo")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
bm.to_mesh(me)
bm.free()
face = bpy.data.objects.new("FaceDemo", me)
face[TAG] = me[TAG] = OWNER
sc.collection.objects.link(face)

# keys: Basis, jaw_open (lower third drops 0.3), smile (verts with |x| > 0.6 rise 0.1)
face.shape_key_add(name="Basis")
jaw_key = face.shape_key_add(name="jaw_open")
smile_key = face.shape_key_add(name="smile")
for i, v in enumerate(me.vertices):
    if v.co.z < -0.3:
        jaw_key.data[i].co.z = v.co.z - 0.3
    if abs(v.co.x) > 0.6:
        smile_key.data[i].co.z = v.co.z + 0.1
for k in (jaw_key, smile_key):
    k.slider_min, k.slider_max = 0.0, 1.0

# controls
arm = bpy.data.armatures.new("ARM_FaceDemo")
rig = bpy.data.objects.new("ARM_FaceDemo", arm)
rig[TAG] = arm[TAG] = OWNER
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
jaw = arm.edit_bones.new("jaw")
jaw.head, jaw.tail = (0, 0, 0), (0, -0.3, 0)
ctrl = arm.edit_bones.new("ctrl")
ctrl.head, ctrl.tail = (1.5, 0, 0), (1.5, 0, 0.2)
bpy.ops.object.mode_set(mode="OBJECT")
rig.pose.bones["jaw"].rotation_mode = "XYZ"
rig.pose.bones["ctrl"]["smile"] = 0.0

# drivers live on the Key datablock
keys = me.shape_keys
d = keys.driver_add('key_blocks["jaw_open"].value').driver
d.type = "SCRIPTED"
var = d.variables.new()
var.name = "rot"
var.type = "TRANSFORMS"
tgt = var.targets[0]
tgt.id, tgt.bone_target = rig, "jaw"
tgt.transform_type, tgt.transform_space = "ROT_X", "LOCAL_SPACE"
d.expression = "min(max(rot / 0.5, 0.0), 1.0)"

d2 = keys.driver_add('key_blocks["smile"].value').driver
d2.type = "SCRIPTED"
var2 = d2.variables.new()
var2.name = "s"
var2.type = "SINGLE_PROP"
var2.targets[0].id = rig
var2.targets[0].data_path = 'pose.bones["ctrl"]["smile"]'
d2.expression = "min(max(s, 0.0), 1.0)"

def lowest_z():
    bpy.context.view_layer.update()
    ev = face.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return min(v.co.z for v in ev.data.vertices)

rest = lowest_z()
rig.pose.bones["jaw"].rotation_euler.x = 0.25           # half of 0.5 rad
half = lowest_z()
rig.pose.bones["jaw"].rotation_euler.x = 2.0            # far past the clamp
full = lowest_z()
rig.pose.bones["jaw"].rotation_euler.x = 0.0
rig.pose.bones["ctrl"]["smile"] = 1.0
bpy.context.view_layer.update()
smile_value = keys.key_blocks["smile"].value

valid = [fc.driver.is_valid for fc in keys.animation_data.drivers]
assert all(valid) and len(valid) == 2, f"invalid driver: {valid}"
assert abs((rest - half) - 0.15) < 0.01, f"half jaw moved {rest - half}, expected 0.15"
assert abs((rest - full) - 0.30) < 0.01, f"clamped jaw moved {rest - full}, expected 0.30"
assert abs(smile_value - 1.0) < 1e-4, f"smile driver gave {smile_value}"
result = {"drivers_valid": valid, "jaw_half_drop": round(rest - half, 4), "jaw_full_drop": round(rest - full, 4),
          "smile_value": round(smile_value, 4), "keys": [k.name for k in keys.key_blocks]}
```

Result when run on Blender 5.2.3: both drivers valid, jaw key drops the lowest vertex 0.15 at half rotation and 0.30 when
over-rotated, smile key reads 1.0.

What the checks prove: the driver paths resolve (`is_valid`), the bone rotation reaches the key value, the clamp holds when
the bone is over-rotated, and a custom property drives a second key. They do not judge how a real face looks.

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Key value never changes | pose bone is in quaternion mode, or the variable reads the wrong axis | `rotation_mode = 'XYZ'`; pick the axis the bone really turns on |
| Driver field red or `is_valid` False | bone name or data path misspelled | copy the name from `rig.pose.bones`; custom property must exist before the driver evaluates |
| Face stretches past the sculpt | no clamp, slider range open | clamp in the expression and set `slider_min`/`slider_max` |
| Two keys together look wrong | both move the same verts | corrective key driven by both |
| Keys vanish after editing the mesh | vertex count changed | rebuild keys; never add or delete vertices once keys exist |

## Before export

Drivers are Blender-side wiring. For a game engine, export the shape keys themselves and drive them there, or bake the
driven values to keyframes on the action first; what a given exporter does with unbaked drivers is not tested here. Keep key
names stable between Blender and the engine so the same name can be found on both sides. In Unreal, morph targets are not supported on a mesh rendered with
Nanite (see the `unreal-export` skill, `references/nanite-prep.md`).
