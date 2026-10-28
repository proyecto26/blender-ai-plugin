"""Apply a PS1/PSX-era look: low internal resolution, nearest-neighbour texture
filtering, vertex snapping (geometry nodes, per object), flat or Gouraud shading,
distance fog (mist pass mixed in the compositor), 32px posterized textures for untextured meshes,
and Standard view transform.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/ps1_look.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "snap": 0.02, "resolution": [320, 240]}})["result"]

ARGS:
    objects     (list[str]|None) meshes that get vertex snapping (default: none, render settings only)
    snap        (float) world-space snap grid in meters (default 0.02; 0 disables)
    resolution  (list[2]) render resolution (default [320, 240])
    flat        (bool) flat shading on objects (default False = smooth/Gouraud)
    fog         (bool|list[3]) compositor distance fog from the mist pass; a list sets the fog colour
                (default True = dark blue-grey)
    texture     (bool) give listed meshes without a material a 32px posterized texture with
                nearest filtering and box projection (default True)
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
    """Set a geometry-nodes modifier input by its interface name (mod.properties.inputs, Blender 5.2+)."""
    for item in mod.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            getattr(mod.properties.inputs, item.identifier).value = value
            return
    raise KeyError(f"modifier input not found: {name}")


def _ps1_material(obj, seed):
    """32x32 posterized noise texture in a per-object tint, Closest filtering, box-projected."""
    import random
    rnd = random.Random(seed)
    tint = [0.25 + 0.6 * rnd.random() for _ in range(3)]
    img = bpy.data.images.new(f"TX_PS1_{obj.name}", 32, 32)
    px = []
    for _ in range(32 * 32):
        shade = (0.55, 0.75, 0.9, 1.0)[rnd.randrange(4)]  # 4-level posterize
        px += [c * shade for c in tint] + [1.0]
    img.pixels = px
    img.pack()
    mat = bpy.data.materials.new(f"MAT_PS1_{obj.name}")
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation, tex.projection, tex.projection_blend = img, "Closest", "BOX", 0.0
    coords = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coords.outputs["Object"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    obj.data.materials.append(mat)
    return mat.name


def _fog(scene, colour):
    """Mix the image toward the fog colour by the mist pass (5.2 compositor, SK_ nodes only)."""
    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
        scene.compositing_node_group = tree
    if not any(getattr(i, "in_out", None) == "OUTPUT" for i in tree.interface.items_tree):
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    for node in [n for n in tree.nodes if n.name.startswith("SK_PS1_")]:
        tree.nodes.remove(node)
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None) \
        or tree.nodes.new("CompositorNodeRLayers")
    out = next((n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"), None) \
        or tree.nodes.new("NodeGroupOutput")
    upstream = out.inputs[0].links[0].from_socket if out.inputs[0].is_linked else _sock(rl.outputs, "Image")
    mix = tree.nodes.new("ShaderNodeMix")
    mix.name = mix.label = "SK_PS1_Fog"
    mix.data_type, mix.blend_type = "RGBA", "MIX"
    a, b = [s for s in mix.inputs if s.enabled and s.bl_idname == "NodeSocketColor"]
    b.default_value = (*colour, 1.0)
    tree.links.new(_sock(rl.outputs, "Mist"), _sock(mix.inputs, "Factor"))
    tree.links.new(upstream, a)
    tree.links.new(next(s for s in mix.outputs if s.enabled), out.inputs[0])
    return mix.name


def main(objects=None, snap=0.02, resolution=(320, 240), flat=False, fog=True, texture=True):
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
    textured = []
    if texture:
        for i, name in enumerate(objects or []):
            obj = bpy.data.objects.get(name)
            if obj and obj.type == "MESH" and not any(s.material for s in obj.material_slots):
                textured.append(_ps1_material(obj, i))
    fog_node = None
    if fog:
        colour = tuple(fog) if isinstance(fog, (list, tuple)) else (0.18, 0.2, 0.24)
        scene.view_layers[0].use_pass_mist = True
        world = scene.world or bpy.data.worlds.new("WRL_PS1")
        scene.world = world
        world.mist_settings.start, world.mist_settings.depth = 2.0, 25.0
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg:
            bg.inputs["Color"].default_value = (*colour, 1.0)
        fog_node = _fog(scene, colour)
    return {"resolution": list(resolution), "nearest_textures": nearest, "snapped": snapped,
            "textured": textured, "fog_node": fog_node,
            "view_transform": scene.view_settings.view_transform, "mist_pass": fog,
            "hint": "Pair with compositing comp_grade preset 'horror_vhs' for dithering/pixelation."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
