"""Apply a PS1/PSX-era look: low internal resolution, nearest-neighbour texture
filtering, vertex snapping (geometry nodes, per object), flat or Gouraud shading,
distance fog (mist pass mixed in the compositor), an ordered Bayer dither with reduced colour
levels (compositor, last stage), 32px posterized textures for untextured meshes, and Standard view transform.

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
    dither      (bool) ordered Bayer dither + colour quantization as the last compositor stage (default True).
                Run comp_grade BEFORE this script: a grade added afterwards is chained after the dither
    color_levels (int) levels per colour channel after quantization, 3..256 (default 32, i.e. 5 bits per channel)
    dither_size (int) Bayer matrix side: 2, 4 or 8 (default 4)

A compositor group shared with another scene is copied for this scene first (copy on write); the other scene keeps
the original and is not changed.

The dither works in display space (Linear Rec.709 -> sRGB -> add threshold -> posterize -> back), so with the
Standard view transform the 8-bit output has exactly `color_levels` values per channel. The threshold is a
render-sized image: after changing the render resolution, run this script again. Scene render dither_intensity
is set to 0 (Blender's own output noise would blur the levels).
"""
import hashlib
import json
import sys

import bmesh
import bpy

GROUP = "GN_PS1_VertexSnap"
DITHER_IMAGE = "SK_PS1_DitherThreshold"
OWNER_KEY = "sk_ps1_scene"  # custom property on a threshold image: the scene it was made for


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


def _is_ps1(node):
    return node.name.startswith("SK_PS1_")


def _unwind(node):
    """The non-PS1 socket that feeds PS1 `node` (through any chain of PS1 nodes), or None."""
    seen = set()
    while _is_ps1(node) and node.name not in seen:
        seen.add(node.name)
        linked = [i for i in node.inputs if i.is_linked and i.enabled]
        pick = next((i for i in linked if i.type == "RGBA"), linked[0] if linked else None)
        if pick is None:
            return None
        sock = pick.links[0].from_socket
        if not _is_ps1(sock.node):
            return sock
        node = sock.node
    return None


def _image_in_use(img):
    """True when any compositor/shader/node-group tree in the file still references `img`."""
    trees = [g for g in bpy.data.node_groups] + [s.compositing_node_group for s in bpy.data.scenes
                                                  if s.compositing_node_group is not None]
    trees += [m.node_tree for m in bpy.data.materials if m.node_tree]
    return any(getattr(n, "image", None) == img for t in trees for n in t.nodes)


def _tree(scene):
    """The scene compositing group (created if missing) with its Image output socket. A rerun splices every
    SK_PS1_ node out wherever it sits in the chain (nodes before and after stay connected) and drops this
    scene's old threshold image unless some other node tree still uses it."""
    tree = scene.compositing_node_group
    if tree is not None and tree.users - (1 if tree.use_fake_user else 0) > 1:
        # another scene uses this group: this scene gets its own copy, so the other scene is not changed
        tree = tree.copy()
        scene.compositing_node_group = tree
    if tree is None:
        tree = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
        scene.compositing_node_group = tree
    if not any(getattr(i, "in_out", None) == "OUTPUT" for i in tree.interface.items_tree):
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    ours = [n for n in tree.nodes if _is_ps1(n)]
    old_images = [n.image for n in ours if n.bl_idname == "CompositorNodeImage" and n.image is not None]
    bridges = []  # (feeding socket, consuming socket) for every link that leaves the PS1 group
    for node in ours:
        for out_sock in node.outputs:
            for lk in out_sock.links:
                if not _is_ps1(lk.to_node):
                    src = _unwind(node)
                    if src is not None:
                        bridges.append((src, lk.to_socket))
    for node in ours:
        tree.nodes.remove(node)
    for src, dst in bridges:
        if not dst.is_linked:
            tree.links.new(src, dst)
    for img in old_images:
        if img.get(OWNER_KEY) is not None and not _image_in_use(img):
            bpy.data.images.remove(img)
    return tree


def _ends(tree):
    """(render layers node, group output node, socket currently feeding the output)."""
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None) \
        or tree.nodes.new("CompositorNodeRLayers")
    out = next((n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"), None) \
        or tree.nodes.new("NodeGroupOutput")
    upstream = out.inputs[0].links[0].from_socket if out.inputs[0].is_linked else _sock(rl.outputs, "Image")
    return rl, out, upstream


def _fog(tree, colour):
    """Mix the image toward the fog colour by the mist pass (5.2 compositor, SK_ nodes only)."""
    rl, out, upstream = _ends(tree)
    mix = tree.nodes.new("ShaderNodeMix")
    mix.name = mix.label = "SK_PS1_Fog"
    mix.data_type, mix.blend_type = "RGBA", "MIX"
    a, b = [s for s in mix.inputs if s.enabled and s.bl_idname == "NodeSocketColor"]
    b.default_value = (*colour, 1.0)
    tree.links.new(_sock(rl.outputs, "Mist"), _sock(mix.inputs, "Factor"))
    tree.links.new(upstream, a)
    tree.links.new(next(s for s in mix.outputs if s.enabled), out.inputs[0])
    return mix.name


def _bayer(n):
    """n x n Bayer index matrix (n a power of two), values 0..n*n-1."""
    import numpy as np
    m = np.array([[0]])
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return m


def _threshold_image(scene, size, steps):
    """Render-sized float image holding the Bayer threshold (m + 0.5) / n^2 divided by `steps`, Non-Color."""
    import numpy as np
    r = scene.render
    w = max(1, r.resolution_x * r.resolution_percentage // 100)
    h = max(1, r.resolution_y * r.resolution_percentage // 100)
    # Names are only labels (Blender suffixes a collision); ownership is decided by the nodes that reference the image.
    digest = hashlib.sha1(scene.name.encode("utf-8")).hexdigest()[:10]
    name = f"{DITHER_IMAGE}_{digest}_{scene.name}"[:63]
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=True, is_data=True)
    img[OWNER_KEY] = scene.name
    img.colorspace_settings.name = "Non-Color"
    m = _bayer(size)
    t = (m + 0.5) / float(size * size) / float(steps)
    ys, xs = np.mgrid[0:h, 0:w]  # row 0 is the bottom row, as in image.pixels
    plane = t[ys % size, xs % size].astype(np.float32)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[:, :, 0] = px[:, :, 1] = px[:, :, 2] = plane
    img.pixels.foreach_set(px.ravel())
    img.pack()
    return img


def _dither(tree, scene, levels, size):
    """Quantize to `levels` per channel with an ordered Bayer threshold, in display (sRGB) space."""
    steps = levels - 1
    rl, out, upstream = _ends(tree)
    img = _threshold_image(scene, size, steps)

    def add(kind, name):
        node = tree.nodes.new(kind)
        node.name = node.label = name
        return node
    to_srgb = add("CompositorNodeConvertColorSpace", "SK_PS1_DitherToSRGB")
    to_srgb.from_color_space, to_srgb.to_color_space = "Linear Rec.709", "sRGB"
    thr = add("CompositorNodeImage", "SK_PS1_DitherThreshold")
    thr.image = img
    mix = add("ShaderNodeMix", "SK_PS1_DitherAdd")
    mix.data_type, mix.blend_type, mix.clamp_result = "RGBA", "ADD", True
    _sock(mix.inputs, "Factor").default_value = 1.0
    colour = [s for s in mix.inputs if s.enabled and s.bl_idname == "NodeSocketColor"]
    post = add("CompositorNodePosterize", "SK_PS1_DitherPosterize")
    _sock(post.inputs, "Steps").default_value = float(steps)
    to_lin = add("CompositorNodeConvertColorSpace", "SK_PS1_DitherToLinear")
    to_lin.from_color_space, to_lin.to_color_space = "sRGB", "Linear Rec.709"
    links = tree.links
    links.new(upstream, _sock(to_srgb.inputs, "Image"))
    links.new(_sock(to_srgb.outputs, "Image"), colour[0])
    links.new(_sock(thr.outputs, "Image"), colour[1])
    links.new(next(s for s in mix.outputs if s.enabled), _sock(post.inputs, "Image"))
    links.new(_sock(post.outputs, "Image"), _sock(to_lin.inputs, "Image"))
    links.new(_sock(to_lin.outputs, "Image"), out.inputs[0])
    return {"levels": levels, "size": size, "image": img.name, "resolution": [img.size[0], img.size[1]]}


def main(objects=None, snap=0.02, resolution=(320, 240), flat=False, fog=True, texture=True,
         dither=True, color_levels=32, dither_size=4):
    if dither:
        color_levels, dither_size = int(color_levels), int(dither_size)
        if not 3 <= color_levels <= 256:
            raise ValueError("color_levels must be 3..256")
        if dither_size not in (2, 4, 8):
            raise ValueError("dither_size must be 2, 4 or 8")
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
            if obj.mode == "EDIT":  # the live faces are the BMesh; obj.data.polygons would be overwritten on exit
                ebm = bmesh.from_edit_mesh(obj.data)
                for face in ebm.faces:
                    face.smooth = not flat
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            else:
                for poly in obj.data.polygons:
                    poly.use_smooth = not flat
            snapped.append(obj.name)
    textured = []
    if texture:
        for i, name in enumerate(objects or []):
            obj = bpy.data.objects.get(name)
            if obj and obj.type == "MESH" and not any(s.material for s in obj.material_slots):
                textured.append(_ps1_material(obj, i))
    existing = scene.compositing_node_group
    # With both stages off, still clear this script's own nodes from an earlier run (never create a tree for that).
    has_ours = existing is not None and any(n.name.startswith("SK_PS1_") for n in existing.nodes)
    tree = _tree(scene) if (fog or dither or has_ours) else None
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
        fog_node = _fog(tree, colour)
    dither_info = None
    if dither:
        scene.render.use_compositing = True
        scene.render.dither_intensity = 0.0
        dither_info = _dither(tree, scene, color_levels, dither_size)
    return {"resolution": list(resolution), "nearest_textures": nearest, "snapped": snapped,
            "textured": textured, "fog_node": fog_node,
            "view_transform": scene.view_settings.view_transform, "mist_pass": fog,
            "dither": dither_info,
            "hint": "comp_grade does not dither: dithering is this script's `dither` stage. Run comp_grade first "
                    "(it chains after whatever feeds the output), then this script so the dither stays the last stage."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
