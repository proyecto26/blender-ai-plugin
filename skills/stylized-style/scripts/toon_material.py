"""Create a cel/toon material (Diffuse -> Shader to RGB -> constant ColorRamp bands,
optional Fresnel rim) and optionally an inverted-hull outline (Solidify with
flipped normals + backface-culled black material). EEVEE only (Shader to RGB).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/toon_material.py", init_globals={"ARGS": {
        "name": "MAT_Toon_Hero", "base_color": [0.9, 0.35, 0.25], "bands": 3, "objects": ["SM_Hero"], "outline": 0.01}})["result"]

ARGS:
    name        (str) material name (MAT_ prefix enforced)
    base_color  (list[3]) lit color; shadow bands are derived darker/cooler
    bands       (int) 2-4 light bands (default 2 = anime two-tone)
    rim         (float) rim light strength 0-1 (default 0.3, 0 disables)
    objects     (list[str]) objects to assign
    outline     (float) outline thickness in meters (0 = none)
"""
import colorsys
import json
import sys

import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _sock(sockets, name):
    """Mix nodes keep hidden per-data-type sockets with the same name; pick the enabled one."""
    for s in sockets:
        if s.name == name and s.enabled:
            return s
    raise KeyError(name)


def _shade(rgb, value_mult, hue_shift):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return colorsys.hsv_to_rgb((h + hue_shift) % 1.0, min(1.0, s * 1.1), v * value_mult)


def _outline_material():
    mat = bpy.data.materials.get("MAT_Outline_Black")
    if mat:
        return mat
    mat = bpy.data.materials.new("MAT_Outline_Black")
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    mat.node_tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
    mat.use_backface_culling = True
    mat.diffuse_color = (0, 0, 0, 1)
    return mat


def main(name="MAT_Toon", base_color=(0.8, 0.5, 0.4), bands=2, rim=0.3, objects=None, outline=0.0):
    if not name.startswith("MAT_"):
        name = "MAT_" + name
    bands = max(2, min(4, int(bands)))
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    diffuse = nodes.new("ShaderNodeBsdfDiffuse"); diffuse.location = (-400, 0)
    to_rgb = nodes.new("ShaderNodeShaderToRGB"); to_rgb.location = (-200, 0)
    ramp = nodes.new("ShaderNodeValToRGB"); ramp.location = (0, 0)
    ramp.color_ramp.interpolation = "CONSTANT"
    elems = ramp.color_ramp.elements
    while len(elems) > 1:
        elems.remove(elems[-1])
    for i in range(bands):
        pos = i / bands if i else 0.0
        color = _shade(base_color, 0.35 + 0.65 * i / (bands - 1), -0.03 * (bands - 1 - i))
        elem = elems[0] if i == 0 else elems.new(pos + 0.5 / bands * 0.6)
        elem.color = (*color, 1.0)
    emission = nodes.new("ShaderNodeEmission"); emission.location = (300, 0)
    links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
    links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
    last_color = ramp.outputs["Color"]
    if rim > 0:
        fres = nodes.new("ShaderNodeFresnel"); fres.location = (0, -250)
        fres.inputs["IOR"].default_value = 1.6
        rim_ramp = nodes.new("ShaderNodeValToRGB"); rim_ramp.location = (200, -250)
        rim_ramp.color_ramp.interpolation = "CONSTANT"
        rim_ramp.color_ramp.elements[1].position = 0.6
        mix = nodes.new("ShaderNodeMix"); mix.location = (500, -100)
        mix.data_type = "RGBA"
        mix.blend_type = "ADD"
        links.new(fres.outputs["Fac"], rim_ramp.inputs["Fac"])
        _sock(mix.inputs, "Factor").default_value = rim
        links.new(last_color, _sock(mix.inputs, "A"))
        links.new(rim_ramp.outputs["Color"], _sock(mix.inputs, "B"))
        last_color = _sock(mix.outputs, "Result")
    links.new(last_color, emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (*base_color, 1.0)

    assigned, outlined = [], []
    outline_mat = _outline_material() if outline > 0 else None
    for obj_name in objects or []:
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.type != "MESH":
            continue
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        assigned.append(obj.name)
        if outline_mat:
            if outline_mat.name not in [m.name for m in obj.data.materials if m]:
                obj.data.materials.append(outline_mat)
            slot = [m.name if m else None for m in obj.data.materials].index(outline_mat.name)
            sol = obj.modifiers.get("Toon_Outline") or obj.modifiers.new("Toon_Outline", "SOLIDIFY")
            sol.thickness = -abs(outline)
            sol.offset = 1.0
            sol.use_flip_normals = True
            sol.use_rim = False
            sol.material_offset = slot
            outlined.append(obj.name)
    return {"material": mat.name, "bands": bands, "assigned": assigned, "outlined": outlined,
            "engine_note": "Shader to RGB works in EEVEE only; use Toon BSDF / Light Path tricks for Cycles."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
