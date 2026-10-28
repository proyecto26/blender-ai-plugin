"""Bake high-poly -> low-poly maps in Cycles (normal, AO, roughness, diffuse color)
to PNG files, with cage extrusion. Restores the render engine afterwards.
Requires the low-poly to have a UV map.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/bake_maps.py", init_globals={"ARGS": {
        "low": "SM_Crate_01", "high": "HP_Crate_01", "maps": ["normal", "ao"], "size": 2048, "out_dir": "/tmp/bakes"}})["result"]

ARGS:
    low      (str, required) low-poly target with UVs
    high     (str|None) high-poly source (None = bake the low-poly's own shading, e.g. AO)
    maps     (list[str]) normal | ao | roughness | diffuse | emit (default ["normal", "ao"])
    size     (int) square texture size (default 2048)
    extrusion (float) cage extrusion in meters (default 0.02)
    samples  (int) Cycles samples for AO (default 64)
    out_dir  (str, required)
"""
import json
import os
import sys

import bpy

BAKE_TYPES = {"normal": "NORMAL", "ao": "AO", "roughness": "ROUGHNESS", "diffuse": "DIFFUSE", "emit": "EMIT"}


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _target_node(low, image):
    """Every material on the low-poly needs an active, selected Image Texture node holding the bake image."""
    if not low.data.materials:
        low.data.materials.append(bpy.data.materials.new(f"MAT_{low.name}_Bake"))
    made = []
    for mat in low.data.materials:
        if mat is None:
            continue
        if hasattr(mat, "use_nodes") and not mat.use_nodes:
            mat.use_nodes = True
        nodes = mat.node_tree.nodes
        node = nodes.get("SK_BakeTarget") or nodes.new("ShaderNodeTexImage")
        node.name = node.label = "SK_BakeTarget"
        node.image = image
        for n in nodes:
            n.select = False
        node.select = True
        nodes.active = node
        made.append(mat.name)
    return made


def main(low, out_dir, high=None, maps=("normal", "ao"), size=2048, extrusion=0.02, samples=64):
    low_obj = bpy.data.objects.get(low)
    if low_obj is None or low_obj.type != "MESH":
        raise ValueError(f"low-poly mesh not found: {low}")
    if not low_obj.data.uv_layers:
        raise ValueError(f"{low} has no UV map - unwrap first (uv-workflow skill)")
    high_obj = bpy.data.objects.get(high) if high else None
    if high and high_obj is None:
        raise ValueError(f"high-poly not found: {high}")
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    prev_engine, prev_samples = scene.render.engine, None
    scene.render.engine = "CYCLES"
    prev_samples = scene.cycles.samples
    scene.cycles.samples = samples
    bake = scene.render.bake
    bake.use_selected_to_active = high_obj is not None
    bake.cage_extrusion = extrusion
    bake.margin = max(4, size // 128)
    written = []
    try:
        for key in maps:
            kind = BAKE_TYPES[key]
            name = f"T_{low_obj.name.removeprefix('SM_')}_{key.capitalize()}"
            image = bpy.data.images.get(name) or bpy.data.images.new(name, size, size, alpha=False,
                                                                     float_buffer=False)
            image.colorspace_settings.name = "sRGB" if key == "diffuse" else "Non-Color"
            _target_node(low_obj, image)
            selected = [low_obj] + ([high_obj] if high_obj else [])
            for o in scene.objects:
                o.select_set(o in selected)
            bpy.context.view_layer.objects.active = low_obj
            kwargs = {"type": kind}
            if kind == "DIFFUSE":
                kwargs["pass_filter"] = {"COLOR"}
            with bpy.context.temp_override(object=low_obj, active_object=low_obj,
                                           selected_objects=selected, selected_editable_objects=selected):
                bpy.ops.object.bake(**kwargs)
            path = os.path.join(out_dir, f"{name}.png")
            image.filepath_raw = path
            image.file_format = "PNG"
            image.save()
            written.append(path)
    finally:
        scene.cycles.samples = prev_samples
        scene.render.engine = prev_engine
    return {"images": written, "size": size, "selected_to_active": high_obj is not None}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
