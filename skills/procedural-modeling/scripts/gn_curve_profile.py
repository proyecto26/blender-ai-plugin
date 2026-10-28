"""Procedural pipe / cable / rail: a poly-curve object swept by a circular profile with
Geometry Nodes (Curve to Mesh + Curve Circle). Radius and Resolution are exposed on the
modifier so they stay editable. Re-running with the same name updates the object in place.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/gn_curve_profile.py", init_globals={"ARGS": {
        "name": "GEO_Pipe", "points": [[0, -5, 0.5], [0, 5, 0.5]], "radius": 0.15}})["result"]

ARGS:
    name        (str)   object name (default "GEO_Pipe")
    points      (list)  [[x, y, z], ...] curve points in world space, at least 2
    radius      (float) profile radius in metres (default 0.1)
    resolution  (int)   profile segments (default 16)
    cyclic      (bool)  close the curve (default False)
    fill_caps   (bool)  cap open ends (default True)
    collection  (str)   collection to link into (default: scene collection)
"""
import json
import sys

import bpy

GROUP_NAME = "GN_CurveProfile"


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _sock(sockets, name):
    """Return the enabled socket called *name* (nodes keep hidden per-type duplicates)."""
    for s in sockets:
        if s.name == name and s.enabled:
            return s
    raise KeyError(f"no enabled socket {name!r}; available: {[s.name for s in sockets if s.enabled]}")


def _build_group():
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    try:
        io = ng.interface
        io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        s_radius = io.new_socket("Radius", in_out="INPUT", socket_type="NodeSocketFloat")
        s_radius.default_value, s_radius.min_value = 0.1, 0.0
        s_res = io.new_socket("Resolution", in_out="INPUT", socket_type="NodeSocketInt")
        s_res.default_value, s_res.min_value = 16, 3
        s_caps = io.new_socket("Fill Caps", in_out="INPUT", socket_type="NodeSocketBool")
        s_caps.default_value = True
        io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        n, l = ng.nodes, ng.links
        gin = n.new("NodeGroupInput"); gin.location = (-600, 0)
        gout = n.new("NodeGroupOutput"); gout.location = (400, 0)
        circle = n.new("GeometryNodeCurvePrimitiveCircle"); circle.location = (-300, -200)
        circle.mode = "RADIUS"
        c2m = n.new("GeometryNodeCurveToMesh"); c2m.location = (0, 0)
        smooth = n.new("GeometryNodeSetShadeSmooth"); smooth.location = (200, 0)

        l.new(_sock(gin.outputs, "Radius"), _sock(circle.inputs, "Radius"))
        l.new(_sock(gin.outputs, "Resolution"), _sock(circle.inputs, "Resolution"))
        l.new(_sock(gin.outputs, "Geometry"), _sock(c2m.inputs, "Curve"))
        l.new(_sock(circle.outputs, "Curve"), _sock(c2m.inputs, "Profile Curve"))
        l.new(_sock(gin.outputs, "Fill Caps"), _sock(c2m.inputs, "Fill Caps"))
        # Curve to Mesh outputs "Mesh" (not "Geometry") in Blender 5.x
        l.new(_sock(c2m.outputs, "Mesh"), _sock(smooth.inputs, "Mesh"))
        l.new(_sock(smooth.outputs, "Mesh"), _sock(gout.inputs, "Geometry"))
    except Exception:
        bpy.data.node_groups.remove(ng)  # never leave a half-built group behind
        raise
    return ng


def _set_input(mod, name, value):
    """Set a geometry-nodes modifier input by its interface name (mod.properties.inputs, Blender 5.2+)."""
    for item in mod.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            getattr(mod.properties.inputs, item.identifier).value = value
            return
    raise KeyError(f"modifier input not found: {name}")


def main(points, name="GEO_Pipe", radius=0.1, resolution=16, cyclic=False, fill_caps=True,
         collection=None):
    if len(points) < 2:
        raise ValueError("points needs at least 2 entries")
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type != "CURVE":
        raise ValueError(f"{name} exists and is not a curve object")
    if obj is None:
        curve = bpy.data.curves.new(name, "CURVE")
        curve.dimensions = "3D"
        obj = bpy.data.objects.new(name, curve)
        target = bpy.data.collections.get(collection) if collection else bpy.context.scene.collection
        if target is None:
            raise ValueError(f"collection not found: {collection}")
        target.objects.link(obj)
    curve = obj.data
    curve.splines.clear()
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (co[0], co[1], co[2], 1.0)
    spline.use_cyclic_u = bool(cyclic)

    mod = obj.modifiers.get("GN_Pipe") or obj.modifiers.new("GN_Pipe", "NODES")
    mod.node_group = _build_group()
    _set_input(mod, "Radius", float(radius))
    _set_input(mod, "Resolution", int(resolution))
    _set_input(mod, "Fill Caps", bool(fill_caps))

    obj.update_tag()
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = obj.evaluated_get(dg).to_mesh()
    stats = {"verts": len(mesh.vertices), "faces": len(mesh.polygons)}
    obj.evaluated_get(dg).to_mesh_clear()
    return {"object": obj.name, "modifier": mod.name, "node_group": mod.node_group.name,
            "radius": radius, "resolution": resolution, "evaluated": stats,
            "hint": "Edit Radius/Resolution on the modifier; apply it only before export."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
