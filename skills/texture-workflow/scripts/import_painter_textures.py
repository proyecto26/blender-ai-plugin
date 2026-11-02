"""Wire exported PBR texture maps (for example from Substance 3D Painter) into a new Principled BSDF material, by file name.

Files are matched by keywords in the name (see PATTERNS; override or extend with `patterns`). Colour maps load as sRGB,
data maps (roughness, metallic, normal, height, opacity, packed ORM, AO) as Non-Color. Creates a new material only;
refuses to touch an existing one. The maps are read from disk, nothing is exported or deleted.
Painter itself is NOT exercised by the tests: they use synthetic maps with these names.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/import_painter_textures.py", init_globals={"ARGS": {
        "folder": "D:/tex/crate", "texture_set": "Crate", "material": "MAT_Crate",
        "normal_convention": "OPENGL", "assign_to": ["SM_Crate_01"]}})["result"]

ARGS:
    folder             (str)  folder holding the exported image files (png jpg jpeg tga tif tiff exr)
    material           (str)  new material name (default "MAT_<texture_set>" or "MAT_Painter"); refused if it exists
    texture_set        (str|None) only files whose name contains this text (case-insensitive)
    normal_convention  (str)  "OPENGL" (default) or "DIRECTX": how the normal maps on disk were written. DIRECTX
                       inserts a green-channel invert before the Normal Map node. Check your export settings;
                       this script cannot tell from the file.
    patterns           (dict|None) extra keywords per map kind, e.g. {"roughness": ["rgh"]}; kinds are
                       base_color, roughness, metallic, normal, height, ao, emissive, opacity, orm
    ao                 (str)  "skip" (default) or "multiply" (multiplies AO into Base Color: not PBR-correct, off by default)
    height_strength    (float) Bump node strength when a height map is found (default 0.5)
    assign_to          (list[str]|None) mesh objects that get the material appended as a new slot
    pack               (bool) pack the images into the .blend (default False)

UDIM tile files (name.1001.png) are reported in `skipped_udim` and not wired.
"""
import json
import os
import re
import sys

import bpy

# Words of 4 characters or fewer match whole name tokens only ("orm" must not match inside "normal");
# longer words match anywhere in the name. Order matters: the packed ORM map is tried first.
PATTERNS = {
    "orm": ["orm", "occlusionroughnessmetallic", "occlusion_roughness_metallic"],
    "base_color": ["basecolor", "base_color", "base-color", "albedo", "diffuse", "color", "colour"],
    "roughness": ["roughness", "rough"],
    "metallic": ["metallic", "metalness", "metal"],
    "normal": ["normal", "nrm", "nor"],
    "height": ["height", "displacement", "disp", "bump"],
    "ao": ["ambientocclusion", "ambient_occlusion", "occlusion", "ao"],
    "emissive": ["emissive", "emission", "emit"],
    "opacity": ["opacity", "alpha", "transparency"],
}
COLOR_KINDS = {"base_color", "emissive"}
EXTS = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr"}
UDIM_RE = re.compile(r"\.\d{4}\.[A-Za-z0-9]+$")


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


def _classify(filename, patterns):
    stem = os.path.splitext(filename)[0].lower()
    tokens = set(re.split(r"[^a-z0-9]+", stem))
    for kind, words in patterns.items():  # whole name tokens first: "MetalDoor_Normal" is a normal map, not metallic
        if any(w in tokens for w in words):
            return kind
    for kind, words in patterns.items():
        if any(len(w) > 4 and w in stem for w in words):
            return kind
    return None


def _sock(sockets, name):
    for s in sockets:
        if s.name == name:
            return s
    raise KeyError(f"no socket {name!r}: {[s.name for s in sockets]}")


def main(folder, material=None, texture_set=None, normal_convention="OPENGL", patterns=None, ao="skip",
         height_strength=0.5, assign_to=None, pack=False):
    if not os.path.isdir(folder):
        raise ValueError(f"folder not found: {folder}")
    convention = str(normal_convention).upper()
    if convention not in ("OPENGL", "DIRECTX"):
        raise ValueError("normal_convention must be OPENGL or DIRECTX")
    if ao not in ("skip", "multiply"):
        raise ValueError("ao must be 'skip' or 'multiply'")
    merged = {k: list(v) for k, v in PATTERNS.items()}
    for kind, words in (patterns or {}).items():
        if kind not in merged:
            raise ValueError(f"unknown map kind {kind!r}; choose from {sorted(merged)}")
        merged[kind] = [w.lower() for w in words] + merged[kind]
    name = material or (f"MAT_{texture_set}" if texture_set else "MAT_Painter")
    if name in bpy.data.materials:
        raise ValueError(f"material {name!r} already exists; pick another name (this script never edits a material)")
    targets = []
    for obj_name in assign_to or []:
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.type != "MESH":
            raise ValueError(f"assign_to: {obj_name!r} is not a mesh object")
        targets.append(obj)

    found, unmatched, skipped_udim, ambiguous = {}, [], [], []
    for fn in sorted(os.listdir(folder)):
        if os.path.splitext(fn)[1].lower() not in EXTS:
            continue
        if texture_set and texture_set.lower() not in fn.lower():
            continue
        if UDIM_RE.search(fn):
            skipped_udim.append(fn)
            continue
        kind = _classify(fn, merged)
        if kind is None:
            unmatched.append(fn)
        elif kind in found:
            ambiguous.append({"kind": kind, "kept": found[kind], "ignored": fn})
        else:
            found[kind] = fn
    if not found:
        raise ValueError(f"no texture maps matched in {folder} (unmatched: {unmatched[:10]})")

    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    nodes, links = nt.nodes, nt.links
    wired, images, row = {}, [], [0]

    def load(kind):
        path, space = os.path.join(folder, found[kind]), "sRGB" if kind in COLOR_KINDS else "Non-Color"
        img = bpy.data.images.load(path, check_existing=True)
        if img.users and img.colorspace_settings.name != space:
            # already used elsewhere: changing its colour space would change every material using it
            img = bpy.data.images.load(path, check_existing=False)
        img.colorspace_settings.name = space
        if pack:
            img.pack()
        images.append(img.name)
        node = nodes.new("ShaderNodeTexImage")
        node.image = img
        node.name = node.label = f"TEX_{kind}"
        node.location = (-900, 300 - 280 * row[0])
        row[0] += 1
        return node

    if "base_color" in found:
        tex = load("base_color")
        out = _sock(tex.outputs, "Color")
        if ao == "multiply" and "ao" in found:
            ao_tex = load("ao")
            mix = nodes.new("ShaderNodeMix")
            mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
            _sock(mix.inputs, "Factor").default_value = 1.0
            a, b = [s for s in mix.inputs if s.enabled and s.bl_idname == "NodeSocketColor"]
            links.new(out, a)
            links.new(_sock(ao_tex.outputs, "Color"), b)
            out = next(s for s in mix.outputs if s.enabled)
            wired["ao"] = "Base Color (multiply)"
        links.new(out, _sock(bsdf.inputs, "Base Color"))
        wired["base_color"] = "Base Color"
    if "orm" in found:
        tex = load("orm")
        sep = nodes.new("ShaderNodeSeparateColor")
        sep.mode = "RGB"
        links.new(_sock(tex.outputs, "Color"), _sock(sep.inputs, "Color"))
        links.new(_sock(sep.outputs, "Green"), _sock(bsdf.inputs, "Roughness"))
        links.new(_sock(sep.outputs, "Blue"), _sock(bsdf.inputs, "Metallic"))
        wired["orm"] = "Roughness (G) + Metallic (B); R (occlusion) not wired"
    if "roughness" in found and "orm" not in found:
        links.new(_sock(load("roughness").outputs, "Color"), _sock(bsdf.inputs, "Roughness"))
        wired["roughness"] = "Roughness"
    if "metallic" in found and "orm" not in found:
        links.new(_sock(load("metallic").outputs, "Color"), _sock(bsdf.inputs, "Metallic"))
        wired["metallic"] = "Metallic"
    normal_src = None
    if "normal" in found:
        tex = load("normal")
        colour = _sock(tex.outputs, "Color")
        if convention == "DIRECTX":
            sep = nodes.new("ShaderNodeSeparateColor")
            sep.mode = "RGB"
            sep.name = sep.label = "FLIP_G_Separate"
            inv = nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.name = inv.label = "FLIP_G_Invert"
            inv.inputs[0].default_value = 1.0
            comb = nodes.new("ShaderNodeCombineColor")
            comb.mode = "RGB"
            comb.name = comb.label = "FLIP_G_Combine"
            links.new(colour, _sock(sep.inputs, "Color"))
            links.new(_sock(sep.outputs, "Green"), inv.inputs[1])
            links.new(_sock(sep.outputs, "Red"), _sock(comb.inputs, "Red"))
            links.new(inv.outputs[0], _sock(comb.inputs, "Green"))
            links.new(_sock(sep.outputs, "Blue"), _sock(comb.inputs, "Blue"))
            colour = _sock(comb.outputs, "Color")
        nm = nodes.new("ShaderNodeNormalMap")
        links.new(colour, _sock(nm.inputs, "Color"))
        normal_src = _sock(nm.outputs, "Normal")
        wired["normal"] = "Normal Map" + (" (green flipped)" if convention == "DIRECTX" else "")
    if "height" in found:
        bump = nodes.new("ShaderNodeBump")
        _sock(bump.inputs, "Strength").default_value = float(height_strength)
        links.new(_sock(load("height").outputs, "Color"), _sock(bump.inputs, "Height"))
        if normal_src is not None:
            links.new(normal_src, _sock(bump.inputs, "Normal"))
        normal_src = _sock(bump.outputs, "Normal")
        wired["height"] = "Bump -> Normal"
    if normal_src is not None:
        links.new(normal_src, _sock(bsdf.inputs, "Normal"))
    if "emissive" in found:
        links.new(_sock(load("emissive").outputs, "Color"), _sock(bsdf.inputs, "Emission Color"))
        _sock(bsdf.inputs, "Emission Strength").default_value = 1.0
        wired["emissive"] = "Emission Color"
    if "opacity" in found:
        links.new(_sock(load("opacity").outputs, "Color"), _sock(bsdf.inputs, "Alpha"))
        wired["opacity"] = "Alpha"
    if "ao" in found and "ao" not in wired:
        wired["ao"] = "not wired (ao='skip')"
    for obj in targets:
        obj.data.materials.append(mat)
    return {"material": mat.name, "files": found, "wired": wired, "images": images, "unmatched": unmatched,
            "ambiguous": ambiguous, "skipped_udim": skipped_udim, "normal_convention": convention,
            "assigned": [o.name for o in targets]}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
