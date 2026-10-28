"""Add a cloth simulation with a fabric preset, optional pin group, collision on
listed colliders, and cache range. Re-running updates the existing modifier.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/cloth_setup.py", init_globals={"ARGS": {
        "cloth": "SM_Flag", "fabric": "cotton", "pin_group": "Pin", "colliders": ["SM_Pole"]}})["result"]

ARGS:
    cloth      (str, required) mesh object (needs enough subdivisions to fold)
    fabric     (str) cotton | silk | denim | leather | rubber | heavy_canvas
    pin_group  (str|None) vertex group name for pinned vertices
    colliders  (list[str]) objects that get a Collision modifier
    frames     (int) cache length (default 120)
    self_collision (bool) default False (slower; enable for folds/layered cloth)
"""
import json
import sys

import bpy

FABRICS = {  # mass kg, tension/compression, shear, bending, air damping
    "cotton": (0.3, 15, 5, 0.5, 1.0),
    "silk": (0.15, 5, 5, 0.05, 1.0),
    "denim": (1.0, 40, 40, 10, 1.0),
    "leather": (0.4, 80, 80, 150, 1.0),
    "rubber": (3.0, 15, 15, 25, 1.0),
    "heavy_canvas": (0.8, 60, 50, 30, 2.0),
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def main(cloth, fabric="cotton", pin_group=None, colliders=(), frames=120, self_collision=False):
    obj = bpy.data.objects.get(cloth)
    if obj is None or obj.type != "MESH":
        raise ValueError(f"mesh not found: {cloth}")
    if fabric not in FABRICS:
        raise ValueError(f"fabric must be one of {sorted(FABRICS)}")
    mod = obj.modifiers.get("Cloth") or obj.modifiers.new("Cloth", "CLOTH")
    s = mod.settings
    mass, tension, shear, bending, air = FABRICS[fabric]
    s.mass = mass
    s.tension_stiffness = s.compression_stiffness = tension
    s.shear_stiffness = shear
    s.bending_stiffness = bending
    s.air_damping = air
    s.quality = 8
    if pin_group:
        if pin_group not in obj.vertex_groups:
            raise ValueError(f"vertex group not found: {pin_group}")
        s.vertex_group_mass = pin_group
    c = mod.collision_settings
    c.use_collision = True
    c.distance_min = 0.005
    c.use_self_collision = self_collision
    mod.point_cache.frame_start = bpy.context.scene.frame_start
    mod.point_cache.frame_end = bpy.context.scene.frame_start + frames
    added = []
    for name in colliders:
        col_obj = bpy.data.objects.get(name)
        if col_obj is None or col_obj.type != "MESH":
            continue
        if not any(m.type == "COLLISION" for m in col_obj.modifiers):
            col_obj.modifiers.new("Collision", "COLLISION")
        col_obj.collision.thickness_outer = 0.01
        added.append(col_obj.name)
    verts = len(obj.data.vertices)
    return {"cloth": obj.name, "fabric": fabric, "pinned": bool(pin_group), "colliders": added,
            "frames": [mod.point_cache.frame_start, mod.point_cache.frame_end], "vertices": verts,
            "warning": "low resolution - subdivide for believable folds" if verts < 200 else ""}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
