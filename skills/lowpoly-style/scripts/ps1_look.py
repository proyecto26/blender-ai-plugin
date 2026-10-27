"""Apply a PS1/PSX-era look: low internal resolution, nearest-neighbour texture
filtering, vertex snapping (geometry nodes, per object), flat or Gouraud shading,
optional distance fog via world mist, and Standard view transform.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/ps1_look.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "snap": 0.02, "resolution": [320, 240]}})["result"]

ARGS:
    objects     (list[str]|None) meshes that get vertex snapping (default: none, render settings only)
    snap        (float) world-space snap grid in meters (default 0.02; 0 disables)
    resolution  (list[2]) render resolution (default [320, 240])
    flat        (bool) flat shading on objects (default False = smooth/Gouraud)
    fog         (bool) enable mist pass + darker world for fog in comp (default True)
"""
import json
import sys

import bpy

GROUP = "GN_PS1_VertexSnap"


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _sock(sockets, name):
    for s in sockets:
        if s.name == name and s.enabled:
            return s
    raise KeyError(name)


def _snap_group():
    ng = bpy.data.node_groups.get(GROUP)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
    try:
        io = ng.interface
        io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        grid = io.new_socket("Grid", in_out="INPUT", socket_type="NodeSocketFloat")
        grid.default_value, grid.min_value = 0.02, 0.0001
        io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        n, l = ng.nodes, ng.links
        gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
        pos = n.new("GeometryNodeInputPosition")
        snap = n.new("ShaderNodeVectorMath")
        snap.operation = "SNAP"
        combine = n.new("ShaderNodeCombineXYZ")
        setpos = n.new("GeometryNodeSetPosition")
        l.new(_sock(gin.outputs, "Grid"), _sock(combine.inputs, "X"))
        l.new(_sock(gin.outputs, "Grid"), _sock(combine.inputs, "Y"))
        l.new(_sock(gin.outputs, "Grid"), _sock(combine.inputs, "Z"))
        l.new(_sock(pos.outputs, "Position"), snap.inputs[0])
        l.new(_sock(combine.outputs, "Vector"), snap.inputs[1])
        l.new(_sock(gin.outputs, "Geometry"), _sock(setpos.inputs, "Geometry"))
        l.new(_sock(snap.outputs, "Vector"), _sock(setpos.inputs, "Position"))
        l.new(_sock(setpos.outputs, "Geometry"), _sock(gout.inputs, "Geometry"))
    except Exception:
        bpy.data.node_groups.remove(ng)
        raise
    return ng


def _set_input(mod, name, value):
    for item in mod.node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name == name:
            props = getattr(mod, "properties", None)
            if props is not None and hasattr(props, "inputs"):
                getattr(props.inputs, item.identifier).value = value
            else:
                mod[item.identifier] = value


def main(objects=None, snap=0.02, resolution=(320, 240), flat=False, fog=True):
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x, r.resolution_y = resolution
    r.resolution_percentage = 100
    r.filter_size = 0.0  # no AA softening: crisp, aliased edges
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    if r.engine == "BLENDER_EEVEE":
        scene.eevee.taa_render_samples = 1
        scene.eevee.use_raytracing = False
    nearest = 0
    for mat in bpy.data.materials:
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.bl_idname == "ShaderNodeTexImage":
                    node.interpolation = "Closest"
                    nearest += 1
    snapped = []
    if snap and objects:
        ng = _snap_group()
        for name in objects:
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                continue
            mod = obj.modifiers.get("PS1_VertexSnap") or obj.modifiers.new("PS1_VertexSnap", "NODES")
            mod.node_group = ng
            _set_input(mod, "Grid", float(snap))
            for poly in obj.data.polygons:
                poly.use_smooth = not flat
            snapped.append(obj.name)
    if fog:
        scene.view_layers[0].use_pass_mist = True
        if scene.world:
            scene.world.mist_settings.start = 2.0
            scene.world.mist_settings.depth = 25.0
    return {"resolution": list(resolution), "nearest_textures": nearest, "snapped": snapped,
            "view_transform": scene.view_settings.view_transform, "mist_pass": fog,
            "hint": "Pair with compositing comp_grade preset 'horror_vhs' for dithering/pixelation."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
