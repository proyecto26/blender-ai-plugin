"""Create (or update) a Principled BSDF PBR material and assign it to objects.
Uses Blender 4+/5.x socket names. Optional texture paths are wired with the
correct color spaces (Base Color = sRGB, data maps = Non-Color).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/pbr_material.py", init_globals={"ARGS": {
        "name": "MAT_PaintedMetal", "base_color": [0.18, 0.2, 0.22], "metallic": 1.0, "roughness": 0.35,
        "objects": ["SM_Crate_01"]}})["result"]

ARGS:
    name            (str, required) material name (MAT_ prefix enforced)
    base_color      (list[3])  linear RGB 0-1
    metallic, roughness, specular_ior_level, coat_weight, emission_strength (float)
    emission_color  (list[3])
    textures        (dict)  optional {"base_color": path, "normal": path, "roughness": path,
                            "metallic": path, "orm": path, "emission": path}
    objects         (list[str]) objects to assign (replaces slot 0, or appends if none)
"""
import json
import os
import sys

import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _image_node(nodes, path, non_color, x, y):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    node = nodes.new("ShaderNodeTexImage")
    node.image = img
    node.location = (x, y)
    return node


def main(name, base_color=(0.8, 0.8, 0.8), metallic=0.0, roughness=0.5, specular_ior_level=0.5,
         coat_weight=0.0, emission_color=(1.0, 1.0, 1.0), emission_strength=0.0, textures=None, objects=None):
    if not name.startswith("MAT_"):
        name = "MAT_" + name
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    i = bsdf.inputs
    i["Base Color"].default_value = (*base_color, 1.0)
    i["Metallic"].default_value = metallic
    i["Roughness"].default_value = roughness
    i["Specular IOR Level"].default_value = specular_ior_level
    i["Coat Weight"].default_value = coat_weight
    i["Emission Color"].default_value = (*emission_color, 1.0)
    i["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = (*base_color, 1.0)  # viewport solid-mode color
    mat.metallic, mat.roughness = metallic, roughness

    wired, missing = [], []
    for key, path in (textures or {}).items():
        if not path or not os.path.exists(path):
            missing.append(key)
            continue
        y = -300 * len(wired)
        if key == "base_color":
            n = _image_node(nodes, path, False, -500, y)
            links.new(n.outputs["Color"], i["Base Color"])
        elif key == "normal":
            n = _image_node(nodes, path, True, -700, y)
            nm = nodes.new("ShaderNodeNormalMap")
            nm.location = (-300, y)
            links.new(n.outputs["Color"], nm.inputs["Color"])
            links.new(nm.outputs["Normal"], i["Normal"])
        elif key in ("roughness", "metallic"):
            n = _image_node(nodes, path, True, -500, y)
            links.new(n.outputs["Color"], i[key.capitalize()])
        elif key == "orm":  # R = AO (ignored by Principled), G = roughness, B = metallic
            n = _image_node(nodes, path, True, -700, y)
            sep = nodes.new("ShaderNodeSeparateColor")
            sep.location = (-300, y)
            links.new(n.outputs["Color"], sep.inputs["Color"])
            links.new(sep.outputs["Green"], i["Roughness"])
            links.new(sep.outputs["Blue"], i["Metallic"])
        elif key == "emission":
            n = _image_node(nodes, path, False, -500, y)
            links.new(n.outputs["Color"], i["Emission Color"])
        else:
            missing.append(key)
            continue
        wired.append(key)

    assigned = []
    for obj_name in objects or []:
        obj = bpy.data.objects.get(obj_name)
        if obj is None or not hasattr(obj.data, "materials"):
            continue
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        assigned.append(obj_name)
    return {"material": mat.name, "textures_wired": wired, "textures_missing": missing, "assigned": assigned}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
