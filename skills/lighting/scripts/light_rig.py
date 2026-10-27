"""Create a named lighting preset (lights + world + color management) inside a
COL_Lights collection. Re-running replaces only the lights this script created
(prefix LGT_Rig_), never user lights.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/light_rig.py",
                            init_globals={"ARGS": {"preset": "studio_3pt", "target": "SM_Crate_01"}})["result"]

ARGS:
    preset  (str)  studio_3pt | golden_hour | overcast | moonlight | horror_practical | neon_night
    target  (str|None) object to aim at / scale the rig to (default: scene bounds of visible meshes)
    collection (str) default "COL_Lights"
    set_world  (bool) also set world color/strength (default True)
"""
import json
import math
import sys

import bpy
from mathutils import Vector

# Each light: (type, energy W (sun = W/m2 irradiance), color, azimuth deg, elevation deg, distance factor, size)
PRESETS = {
    "studio_3pt": {
        "lights": [("AREA", 600, (1.0, 0.96, 0.92), -40, 35, 2.2, 1.5),     # key
                   ("AREA", 180, (0.92, 0.95, 1.0), 50, 15, 2.5, 2.5),      # fill
                   ("AREA", 450, (1.0, 1.0, 1.0), 160, 45, 2.0, 0.8)],      # rim
        "world": ((0.05, 0.05, 0.055), 1.0), "look": "AgX - Base Contrast", "exposure": 0.0},
    "golden_hour": {
        "lights": [("SUN", 4.0, (1.0, 0.72, 0.45), -60, 8, 1, 2.0),
                   ("AREA", 120, (0.55, 0.65, 1.0), 120, 30, 3.0, 4.0)],
        "world": ((0.35, 0.45, 0.65), 0.6), "look": "AgX - Punchy", "exposure": 0.0},
    "overcast": {
        "lights": [("SUN", 1.5, (0.9, 0.93, 1.0), 20, 60, 1, 15.0)],
        "world": ((0.6, 0.65, 0.7), 1.2), "look": "AgX - Base Contrast", "exposure": 0.0},
    "moonlight": {
        "lights": [("SUN", 0.4, (0.55, 0.65, 1.0), 30, 35, 1, 0.5),
                   ("POINT", 60, (1.0, 0.6, 0.3), -80, 10, 1.5, 0.1)],
        "world": ((0.01, 0.015, 0.03), 0.5), "look": "AgX - High Contrast", "exposure": -0.5},
    "horror_practical": {
        "lights": [("SPOT", 300, (1.0, 0.85, 0.65), 10, 70, 1.5, 0.05),
                   ("POINT", 25, (0.4, 1.0, 0.6), 140, 5, 1.8, 0.05)],
        "world": ((0.003, 0.003, 0.004), 1.0), "look": "AgX - High Contrast", "exposure": -0.3},
    "neon_night": {
        "lights": [("AREA", 400, (1.0, 0.1, 0.6), -70, 10, 1.6, 2.0),
                   ("AREA", 400, (0.1, 0.6, 1.0), 70, 10, 1.6, 2.0),
                   ("AREA", 120, (0.6, 0.3, 1.0), 180, 40, 2.0, 1.0)],
        "world": ((0.01, 0.005, 0.02), 1.0), "look": "AgX - Punchy", "exposure": 0.0},
}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _bounds(target):
    scene = bpy.context.scene
    objs = [bpy.data.objects[target]] if target else [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    if not objs:
        return Vector((0, 0, 0)), 2.0
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, max((hi - lo).length, 0.5)


def main(preset="studio_3pt", target=None, collection="COL_Lights", set_world=True):
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    if target and target not in bpy.data.objects:
        raise ValueError(f"object not found: {target}")
    scene = bpy.context.scene
    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection)
        scene.collection.children.link(col)
    for obj in [o for o in col.objects if o.name.startswith("LGT_Rig_")]:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            bpy.data.lights.remove(data)

    cfg = PRESETS[preset]
    center, size = _bounds(target)
    made = []
    for i, (kind, energy, color, az, el, dist, light_size) in enumerate(cfg["lights"]):
        data = bpy.data.lights.new(f"LGT_Rig_{preset}_{i}", kind)
        data.color = color
        data.energy = energy * (size ** 2 / 4 if kind != "SUN" else 1)  # keep exposure stable across scales
        if kind == "AREA":
            data.size = light_size * size / 2
        elif kind == "SUN":
            data.angle = math.radians(light_size)
        elif kind == "SPOT":
            data.spot_size = math.radians(55)
            data.spot_blend = 0.4
            data.shadow_soft_size = light_size
        else:
            data.shadow_soft_size = light_size
        obj = bpy.data.objects.new(data.name, data)
        col.objects.link(obj)
        a, e = math.radians(az), math.radians(el)
        direction = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
        obj.location = center + direction * size * dist
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
        made.append(obj.name)

    if set_world:
        world = scene.world or bpy.data.worlds.new("WRL_Rig")
        scene.world = world
        if hasattr(world, "use_nodes") and not world.use_nodes:
            world.use_nodes = True
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is None:
            bg = world.node_tree.nodes.new("ShaderNodeBackground")
            out = next((n for n in world.node_tree.nodes if n.type == "OUTPUT_WORLD"), None) \
                or world.node_tree.nodes.new("ShaderNodeOutputWorld")
            world.node_tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
        (r, g, b), strength = cfg["world"]
        bg.inputs["Color"].default_value = (r, g, b, 1.0)
        bg.inputs["Strength"].default_value = strength
    vs = scene.view_settings
    vs.view_transform = "AgX"
    vs.look = cfg["look"]
    vs.exposure = cfg["exposure"]
    return {"preset": preset, "lights": made, "collection": col.name,
            "view_transform": vs.view_transform, "look": vs.look, "rig_scale_m": round(size, 3)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
