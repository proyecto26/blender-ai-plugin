"""Set up rigid bodies: ensure a rigid body world, make objects ACTIVE or PASSIVE
with a collision shape and mass from a material density, configure the cache
range, and optionally bake.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/rigid_body_setup.py", init_globals={"ARGS": {
        "active": ["SM_Crate_01"], "passive": ["GEO_Ground"], "material": "wood", "frames": 120}})["result"]

ARGS:
    active   (list[str]) dynamic objects
    passive  (list[str]) static colliders (floors, walls)
    shape    (str) CONVEX_HULL | BOX | SPHERE | MESH (default CONVEX_HULL; MESH only for passive)
    material (str) wood | metal | stone | plastic | rubber | glass (sets density, friction, bounciness)
    frames   (int) simulation length (default 120)
    substeps (int) substeps per frame (default 10)
    bake     (bool) bake to cache (default False)
"""
import json
import sys

import bpy

MATERIALS = {  # density kg/m3, friction, restitution
    "wood": (700, 0.6, 0.2), "metal": (7800, 0.4, 0.1), "stone": (2500, 0.8, 0.05),
    "plastic": (950, 0.4, 0.4), "rubber": (1100, 0.9, 0.8), "glass": (2500, 0.3, 0.1),
}


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


def _add_rb(obj, kind):
    if obj.rigid_body is None:
        with bpy.context.temp_override(object=obj, active_object=obj,
                                       selected_objects=[obj], selected_editable_objects=[obj]):
            bpy.ops.rigidbody.object_add(type=kind)
    obj.rigid_body.type = kind
    return obj.rigid_body


def main(active=(), passive=(), shape="CONVEX_HULL", material="wood", frames=120, substeps=10, bake=False):
    scene = bpy.context.scene
    if scene.rigidbody_world is None:
        with bpy.context.temp_override(scene=scene):
            bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    world.substeps_per_frame = substeps
    world.solver_iterations = 10
    world.point_cache.frame_start = scene.frame_start
    world.point_cache.frame_end = scene.frame_start + frames
    density, friction, bounce = MATERIALS.get(material, MATERIALS["wood"])
    report = {"active": {}, "passive": []}
    for name in active:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        rb = _add_rb(obj, "ACTIVE")
        rb.collision_shape = shape if shape != "MESH" else "CONVEX_HULL"
        dx, dy, dz = obj.dimensions
        volume = max(dx * dy * dz * (0.52 if shape == "SPHERE" else 1.0), 1e-6)
        rb.mass = round(density * volume, 3)
        rb.friction, rb.restitution = friction, bounce
        rb.use_margin, rb.collision_margin = True, 0.001
        report["active"][obj.name] = {"mass_kg": rb.mass, "shape": rb.collision_shape}
    for name in passive:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        rb = _add_rb(obj, "PASSIVE")
        rb.collision_shape = "MESH" if shape == "MESH" or max(obj.dimensions) > 5 else "CONVEX_HULL"
        rb.friction = friction
        report["passive"].append(obj.name)
    if bake:
        with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
            bpy.ops.ptcache.bake(bake=True)
        report["baked"] = world.point_cache.is_baked
    report.update({"frames": [world.point_cache.frame_start, world.point_cache.frame_end],
                   "substeps": world.substeps_per_frame, "material": material})
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
