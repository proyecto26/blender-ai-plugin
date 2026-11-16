"""Bake high-poly -> low-poly maps in Cycles (normal, AO, roughness, metallic, diffuse color) to PNG files, with
several high-poly sources, a cage, a ray distance, a chosen UV map, OpenGL/DirectX normals and ORM packing.
Restores the render engine afterwards. Requires the low-poly to have a UV map.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/bake_maps.py", init_globals={"ARGS": {
        "low": "SM_Crate_01", "high": "HP_Crate_01", "maps": ["normal", "ao"], "size": 2048, "out_dir": "/tmp/bakes"}})["result"]

ARGS:
    low      (str, required) low-poly target with UVs
    high     (str|list[str]|None) high-poly source(s) (None = bake the low-poly's own shading, e.g. AO). With
             several, all are selected and rays hit whichever is nearest
    maps     (list[str]) normal | ao | roughness | metallic | diffuse | emit (default ["normal", "ao"])
    size     (int) square texture size (default 2048)
    extrusion (float) cage extrusion in meters (default 0.02); ignored when `cage` is given
    cage     (str|None) name of a cage object (needs `high`); replaces the extrusion
    max_ray_distance (float) Cycles max ray distance, 0 = unlimited (default 0)
    uv_layer (str|None) UV map of the low-poly to bake into (default: its active UV map). The active UV map is
             put back afterwards
    normal_convention (str) "OPENGL" (default, Blender's own: green up) or "DIRECTX" (green flipped, 1 - g)
    orm      (bool) also write one image T_<name>_Orm with AO in R, roughness in G, metallic in B. The three
             maps are baked (and written) even when not listed in `maps`
    overwrite (bool) default False. An image datablock of a target name that already exists (at any size) or an
             existing output file is refused before any bake. With True the datablock is reused (scaled to
             `size` when needed): its pixels, colorspace and file path change, and the file is replaced
    samples  (int) Cycles samples for AO (default 64)
    out_dir  (str, required)

Metallic: Cycles has no metallic pass, so for the bake the Surface of every material on the bake source (the
high-poly when given, else the low-poly) is temporarily fed by an Emission node carrying the Principled
metallic value (or the node linked into it; a colour is turned into grey by a temporary RGB to BW node, which is
Blender's own implicit colour -> float rule, and a vector by the average of its components); the original link and the temporary node are put back in `finally`,
also when the bake fails. A material with no Principled BSDF bakes 0. Group nodes are not looked into.

If a bake fails midway, the images and SK_BakeTarget nodes this run created are removed again (files already
written stay) and a node that already existed gets its previous image back. Selection, the active object, the
bake settings, the active UV map and the material node selection are put back afterwards (on success the
SK_BakeTarget image node stays in each material by design).
"""
import contextlib
import json
import os
import sys

import bpy
import numpy as np

BAKE_TYPES = {"normal": "NORMAL", "ao": "AO", "roughness": "ROUGHNESS", "metallic": "EMIT", "diffuse": "DIFFUSE",
              "emit": "EMIT"}
SRGB_MAPS = {"diffuse"}


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


def _target_node(low, image, saved, log):
    """Every material on the low-poly needs an active, selected Image Texture node holding the bake image."""
    if not low.data.materials:
        low.data.materials.append(bpy.data.materials.new(f"MAT_{low.name}_Bake"))
    for mat in low.data.materials:
        if mat is None:
            continue
        nodes = mat.node_tree.nodes
        if mat.name not in saved:  # node selection as the user left it, put back after the bake
            saved[mat.name] = (nodes.active.name if nodes.active else None, [n.name for n in nodes if n.select])
        node = nodes.get("SK_BakeTarget")
        if node is None:
            node = nodes.new("ShaderNodeTexImage")
            log["created_nodes"].append((mat.name, "SK_BakeTarget"))
        elif (mat.name, "SK_BakeTarget") not in log["prev_images"]:
            log["prev_images"][(mat.name, "SK_BakeTarget")] = node.image
        node.name = node.label = "SK_BakeTarget"
        node.image = image
        for n in nodes:
            n.select = False
        node.select = True
        nodes.active = node


def _image_name(low_obj, key):
    return f"T_{low_obj.name.removeprefix('SM_')}_{key.capitalize()}"


def _socket(node, identifier, outputs=False):
    for s in (node.outputs if outputs else node.inputs):
        if s.identifier == identifier:
            return s
    return None


@contextlib.contextmanager
def _metallic_as_emission(objs):
    """Feed every material Surface on `objs` from an Emission node that carries the metallic value; undo in finally."""
    done = []  # (tree, emission name, output node name, original (node, identifier, muted) or None, extra node names)
    try:
        seen = set()
        for o in objs:
            for slot in o.material_slots:
                mat = slot.material
                if mat is None or mat.node_tree is None or mat.name in seen:
                    continue
                seen.add(mat.name)
                tree = mat.node_tree
                out = tree.get_output_node("CYCLES")
                if out is None:
                    continue
                surf = out.inputs["Surface"]
                orig = None
                if surf.links:
                    lk = surf.links[0]
                    orig = (lk.from_node.name, lk.from_socket.identifier, lk.is_muted)
                prin = tree.nodes.get(orig[0]) if orig else None
                if prin is None or prin.bl_idname != "ShaderNodeBsdfPrincipled":
                    prin = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
                src = prin.inputs["Metallic"] if prin is not None else None
                feed = (src.links[0].from_node.name, src.links[0].from_socket.identifier,
                        src.links[0].from_socket.type) if src is not None and src.links else None
                value = float(src.default_value) if src is not None and not feed else 0.0
                em = tree.nodes.new("ShaderNodeEmission")
                em.name = "SK_BakeMetallic"
                extra = []
                done.append((tree, em.name, out.name, orig, extra))
                if feed:
                    source = _socket(tree.nodes[feed[0]], feed[1], outputs=True)
                    if feed[2] == "RGBA":  # Blender's implicit colour -> float is the luminance: do it explicitly
                        conv = tree.nodes.new("ShaderNodeRGBToBW")
                        extra.append(conv.name)
                        tree.links.new(source, conv.inputs["Color"])
                        tree.links.new(conv.outputs["Val"], em.inputs["Color"])
                    elif feed[2] == "VECTOR":  # vector -> float is the average of the components
                        conv = tree.nodes.new("ShaderNodeVectorMath")
                        conv.operation = "DOT_PRODUCT"
                        extra.append(conv.name)
                        conv.inputs[1].default_value = (1 / 3, 1 / 3, 1 / 3)
                        tree.links.new(source, conv.inputs[0])
                        tree.links.new(conv.outputs["Value"], em.inputs["Color"])
                    else:
                        tree.links.new(source, em.inputs["Color"])
                else:
                    em.inputs["Color"].default_value = (value, value, value, 1.0)
                em.inputs["Strength"].default_value = 1.0
                tree.links.new(em.outputs["Emission"], surf)
        yield len(done)
    finally:
        for tree, em_name, out_name, orig, extra in done:
            for name in [em_name] + extra:
                node = tree.nodes.get(name)
                if node is not None:
                    tree.nodes.remove(node)
            out = tree.nodes.get(out_name)
            if orig is not None and out is not None and tree.nodes.get(orig[0]) is not None:
                sock = _socket(tree.nodes[orig[0]], orig[1], outputs=True)
                if sock is not None:
                    lk = tree.links.new(sock, out.inputs["Surface"])
                    lk.is_muted = orig[2]


def _check_target(name, path, overwrite):
    existing = bpy.data.images.get(name)
    if existing is not None and not overwrite:
        raise ValueError(f"image {name!r} already exists ({existing.size[0]}x{existing.size[1]}); remove or "
                         "rename it, or pass overwrite=True to reuse it (its pixels, colorspace and path change)")
    if os.path.exists(path) and not overwrite:
        raise ValueError(f"output file {path!r} already exists; pass overwrite=True to replace it")


def _get_image(name, size, created, overwrite, colorspace):
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
        created.append(name)
    image.colorspace_settings.name = colorspace  # first: changing it reloads the buffer
    if tuple(image.size) != (size, size):  # only reachable with overwrite=True
        if image.source == "GENERATED":
            image.generated_width = image.generated_height = size
        else:
            image.scale(size, size)
    return image


def _pixels(image):
    arr = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(arr)
    return arr


def main(low, out_dir, high=None, maps=("normal", "ao"), size=2048, extrusion=0.02, samples=64, cage=None,
         max_ray_distance=0.0, uv_layer=None, normal_convention="OPENGL", orm=False, overwrite=False):
    low_obj = bpy.data.objects.get(low)
    if low_obj is None or low_obj.type != "MESH":
        raise ValueError(f"low-poly mesh not found: {low}")
    if not low_obj.data.uv_layers:
        raise ValueError(f"{low} has no UV map - unwrap first (uv-workflow skill)")
    high_names = [] if not high else ([high] if isinstance(high, str) else list(high))
    high_objs = []
    for hn in high_names:
        h = bpy.data.objects.get(hn)
        if h is None:
            raise ValueError(f"high-poly not found: {hn}")
        if h is low_obj:
            raise ValueError("the low-poly cannot be its own high-poly source")
        high_objs.append(h)
    maps = list(maps)
    unknown = [k for k in maps if k not in BAKE_TYPES]
    if unknown:
        raise ValueError(f"unknown maps {unknown}; use {list(BAKE_TYPES)}")
    convention = str(normal_convention).upper()
    if convention not in ("OPENGL", "DIRECTX"):
        raise ValueError(f"normal_convention must be OPENGL or DIRECTX, got {normal_convention!r}")
    cage_obj = None
    if cage:
        if not high_objs:
            raise ValueError("cage needs a high-poly source")
        cage_obj = bpy.data.objects.get(cage)
        if cage_obj is None or cage_obj.type != "MESH":
            raise ValueError(f"cage mesh not found: {cage}")
    layer = None
    if uv_layer:
        layer = low_obj.data.uv_layers.get(uv_layer)
        if layer is None:
            raise ValueError(f"{low} has no UV map named {uv_layer!r}; it has {[u.name for u in low_obj.data.uv_layers]}")
    to_bake = list(maps)
    if orm:
        to_bake += [k for k in ("ao", "roughness", "metallic") if k not in to_bake]
    outputs = {key: (_image_name(low_obj, key), os.path.join(out_dir, f"{_image_name(low_obj, key)}.png"))
               for key in to_bake}
    if orm:
        outputs["orm"] = (_image_name(low_obj, "orm"), os.path.join(out_dir, f"{_image_name(low_obj, 'orm')}.png"))
    for name, path in outputs.values():
        _check_target(name, path, overwrite)
    os.makedirs(out_dir, exist_ok=True)

    scene = bpy.context.scene
    prev_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    prev_samples = scene.cycles.samples
    scene.cycles.samples = samples
    bake = scene.render.bake
    prev_bake = (bake.use_selected_to_active, bake.cage_extrusion, bake.margin, bake.use_cage, bake.cage_object,
                 bake.max_ray_distance)
    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = [o for o in scene.objects if o.select_get()]
    prev_uv = low_obj.data.uv_layers.active
    saved_nodes = {}
    log = {"created_nodes": [], "prev_images": {}}
    created_images = []
    bake.use_selected_to_active = bool(high_objs)
    bake.cage_extrusion = extrusion
    bake.use_cage = cage_obj is not None
    bake.cage_object = cage_obj
    bake.max_ray_distance = max_ray_distance
    bake.margin = max(4, size // 128)
    if layer is not None:
        low_obj.data.uv_layers.active = layer
    written, sizes, baked = [], {}, {}
    ok = False
    try:
        for key in to_bake:
            kind = BAKE_TYPES[key]
            name, path = outputs[key]
            image = _get_image(name, size, created_images, overwrite, "sRGB" if key in SRGB_MAPS else "Non-Color")
            _target_node(low_obj, image, saved_nodes, log)
            selected = [low_obj] + high_objs
            for o in scene.objects:
                o.select_set(o in selected)
            bpy.context.view_layer.objects.active = low_obj
            kwargs = {"type": kind}
            if kind == "DIFFUSE":
                kwargs["pass_filter"] = {"COLOR"}
            source = high_objs or [low_obj]
            with contextlib.ExitStack() as stack:
                if key == "metallic":
                    stack.enter_context(_metallic_as_emission(source))
                with bpy.context.temp_override(object=low_obj, active_object=low_obj,
                                               selected_objects=selected, selected_editable_objects=selected):
                    result = bpy.ops.object.bake(**kwargs)
            if "FINISHED" not in result:
                raise RuntimeError(f"bake {key} on {low_obj.name} returned {sorted(result)}; nothing saved for it")
            if key == "normal" and convention == "DIRECTX":
                px = _pixels(image)
                px[1::4] = 1.0 - px[1::4]
                image.pixels.foreach_set(px)
                image.update()
            image.filepath_raw = path
            image.file_format = "PNG"
            image.save()
            baked[key] = image
            written.append(path)
            sizes[key] = list(image.size)
        orm_path = None
        if orm:
            name, orm_path = outputs["orm"]
            image = _get_image(name, size, created_images, overwrite, "Non-Color")
            packed = np.ones(size * size * 4, dtype=np.float32)
            for ch, key in enumerate(("ao", "roughness", "metallic")):
                src = _pixels(baked[key])
                packed[ch::4] = src[0::4]
            image.pixels.foreach_set(packed)
            image.update()
            image.filepath_raw = orm_path
            image.file_format = "PNG"
            image.save()
            written.append(orm_path)
            sizes["orm"] = list(image.size)
        ok = True
    finally:
        if not ok:
            for mat_name, node_name in log["created_nodes"]:
                mat = bpy.data.materials.get(mat_name)
                if mat is not None and mat.node_tree is not None and mat.node_tree.nodes.get(node_name):
                    mat.node_tree.nodes.remove(mat.node_tree.nodes[node_name])
            for (mat_name, node_name), prev in log["prev_images"].items():
                mat = bpy.data.materials.get(mat_name)
                node = mat.node_tree.nodes.get(node_name) if mat is not None and mat.node_tree else None
                if node is not None:
                    node.image = prev
            for name in created_images:
                img = bpy.data.images.get(name)
                if img is not None:
                    bpy.data.images.remove(img)
        for mat_name, (active, selected_nodes) in saved_nodes.items():
            mat = bpy.data.materials.get(mat_name)
            if mat is None or mat.node_tree is None:
                continue
            for n in mat.node_tree.nodes:
                n.select = n.name in selected_nodes
            mat.node_tree.nodes.active = mat.node_tree.nodes.get(active) if active else None
        (bake.use_selected_to_active, bake.cage_extrusion, bake.margin, bake.use_cage, bake.cage_object,
         bake.max_ray_distance) = prev_bake
        if prev_uv is not None:
            low_obj.data.uv_layers.active = prev_uv
        for o in scene.objects:
            o.select_set(o in prev_selected)
        view_layer.objects.active = prev_active
        scene.cycles.samples = prev_samples
        scene.render.engine = prev_engine
    return {"images": written, "size": size, "sizes": sizes, "selected_to_active": bool(high_objs),
            "high": [h.name for h in high_objs], "cage": cage, "uv_layer": layer.name if layer else None,
            "normal_convention": convention, "orm": orm_path, "overwrite": bool(overwrite)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
