"""Wire exported PBR texture maps (for example from Substance 3D Painter) into a new Principled BSDF material, by file name.

Files are matched by the keyword that ends the name (see PATTERNS and _classify; override or extend with `patterns`). Colour maps load as sRGB,
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
    normal_convention  (str|None) "OPENGL", "DIRECTX" or "AUTO": how the normal map on disk was written. DIRECTX inserts
                       a green-channel invert before the Normal Map node. Decision order: this argument, then the file name
                       (a "DirectX"/"DX" token means DIRECTX, "OpenGL"/"GL" means OPENGL; Painter's export presets put that
                       token in the name), else OPENGL. An explicit value that disagrees with the file name warns, and the
                       explicit value wins. The pixels never flip green by themselves: with no argument and no name hint the
                       map is wired as OPENGL, and if its pixels look like DirectX the result carries
                       `normal_convention_suggestion: "directx"` plus a warning. "AUTO" lets the pixels decide (after the file
                       name). The test: a map made from a height field is that field's gradient, so its gradient field has
                       almost no curl under the right green convention; the curl is measured at full resolution under both,
                       and counts only when one is 4x lower and the other clearly above noise. AUTO can be WRONG for a map
                       that is not height-derived (hand-painted, some bakes) or whose red channel is inverted (that swaps the
                       two scores); flat, near-flat, stripe-only and noisy maps give no answer.
                       Result: `normal_convention_source` ("argument", "filename", "content" [AUTO only], "default"; None
                       without a normal map), `normal_convention_scores` (both curls and their ratio, when the pixels were
                       read) and `normal_convention_suggestion`.
    patterns           (dict|None) extra keywords per map kind, e.g. {"roughness": ["rgh"]}; kinds are
                       base_color, roughness, metallic, normal, height, ao, emissive, opacity, orm
    ao                 (str)  "skip" (default) or "multiply" (multiplies AO into Base Color: not PBR-correct, off by default)
    height_strength    (float) Bump node strength when a height map is found (default 0.5)
    assign_to          (list[str]|None) mesh objects that get the material appended as a new slot. Mesh data shared
                       with an object that is NOT listed is refused (the new slot would appear on it too): list every
                       object sharing the data, or make it single-user. A shared mesh listed through all its objects
                       gets the slot once.
    pack               (bool) pack the images into the .blend (default False)

UDIM tile files (name.1001.png) are reported in `skipped_udim` and not wired.
"""
import json
import os
import re
import sys

import bpy
import numpy as np

# The map kind is read from the end of the file name (see _classify). Order matters: the packed ORM map is tried first.
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


NOISE_TAIL = re.compile(r"^(\d+|v\d+|\d+k|opengl|directx|gl|dx)$")  # resolution / version / convention suffixes


def _norm(word):
    return re.sub(r"[^a-z0-9]+", "", word.lower())


def _classify(filename, patterns):
    """Map kind from the END of the file name, where exporters put it ("Metal_Panel_Normal" is a normal map; the
    asset name before it is not a map kind). Trailing resolution/version/convention tokens (2k, v2, DirectX) are
    ignored. Longest tail first, so a spelled-out compound ("occlusion_roughness_metallic", "base_color") beats the
    single words inside it; then the last token alone; then, for a camelCase name with no separator
    ("MetalDoorNormal"), a long keyword the name ends with."""
    stem = os.path.splitext(filename)[0].lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if t]
    while len(tokens) > 1 and NOISE_TAIL.match(tokens[-1]):
        tokens.pop()
    if not tokens:
        return None
    for n in (3, 2, 1):  # patterns is ordered: the packed ORM kind is first, so it wins a tie
        if n > len(tokens):
            continue
        tail = "".join(tokens[-n:])
        for kind, words in patterns.items():
            if any(_norm(w) == tail and (n == 1 or len(_norm(w)) > 4) for w in words):
                return kind
    last = tokens[-1]
    for kind, words in patterns.items():
        if any(len(_norm(w)) > 4 and last.endswith(_norm(w)) for w in words):
            return kind
    return None


def _sock(sockets, name):
    for s in sockets:
        if s.name == name:
            return s
    raise KeyError(f"no socket {name!r}: {[s.name for s in sockets]}")


NORMAL_TOKENS = ("normal", "nrm", "nor")
DETECT_MAX_PIXELS = 4_000_000  # measure at most about this many pixels, in full-resolution strips (never downsampled)
DETECT_STRIP = 128             # rows per strip
DETECT_MARGIN = 4.0            # the losing convention's curl must be at least this many times the winner's
DETECT_MIN_SIGNAL = 0.004      # ...and the loser's curl must exceed this (8-bit quantisation noise sits near 0.001-0.002)


def _strip_curl(rgb):
    """Sum and count of |d gy/dx - d gx/dy| for both green conventions over one full-resolution strip. The gradients
    (-nx/nz, -ny/nz) are formed per pixel BEFORE any averaging: averaging normals first does not preserve integrability."""
    n = rgb[:, :, :3].astype(np.float32) * 2.0 - 1.0
    nz = n[:, :, 2]
    ok = nz > 0.2  # steep or invalid (non-normal) pixels make the division blow up: leave them out
    safe = np.where(ok, nz, 1.0)
    gx, gy = -n[:, :, 0] / safe, -n[:, :, 1] / safe
    m = ok[1:-1, 1:-1] & ok[1:-1, 2:] & ok[1:-1, :-2] & ok[2:, 1:-1] & ok[:-2, 1:-1]
    dgx_dv = (gx[2:, 1:-1] - gx[:-2, 1:-1]) * 0.5
    dgy_du = (gy[1:-1, 2:] - gy[1:-1, :-2]) * 0.5
    return (float(np.abs(dgy_du - dgx_dv)[m].sum()), float(np.abs(-dgy_du - dgx_dv)[m].sum()),
            int(m.sum()), int(ok.sum()), int(ok.size))


def _detect_normal_convention(rgb):
    """Which green convention does the tangent-space normal map in rgb (float (H, W, >=3), 0..1) look like?
    A normal map derived from a height field is the gradient of it, so its gradient field is curl-free under the right
    green convention; the wrong one adds 2*d2h/dxdy. Returns ("OPENGL" | "DIRECTX" | None, info); None = cannot tell
    (flat, no mixed x/y variation, scores too close). This is evidence, not identification: a map that is not a height
    gradient, or whose RED channel is inverted, swaps or scrambles the two scores."""
    h, w = rgb.shape[:2]
    info = {"opengl_curl": None, "directx_curl": None, "ratio": None, "valid_fraction": None}
    if h < 3 or w < 3:
        return None, info
    n_strips = max(1, -(-(h - 2) // DETECT_STRIP))
    keep = max(8, DETECT_MAX_PIXELS // max(1, DETECT_STRIP * w))
    picks = range(n_strips) if n_strips <= keep else sorted({int(i * n_strips / keep) for i in range(keep)})
    sg = sd = 0.0
    cnt = okc = tot = 0
    for i in picks:
        r0 = i * DETECT_STRIP
        g, d, c, o, t = _strip_curl(rgb[r0:min(h, r0 + DETECT_STRIP + 2)])
        sg, sd, cnt, okc, tot = sg + g, sd + d, cnt + c, okc + o, tot + t
    info["valid_fraction"] = round(okc / max(tot, 1), 3)
    if cnt < 64 or okc < 0.5 * tot:
        return None, info
    gl, dx = sg / cnt, sd / cnt
    info.update(opengl_curl=round(gl, 5), directx_curl=round(dx, 5))
    lo, hi = min(gl, dx), max(gl, dx)
    info["ratio"] = round(hi / max(lo, 1e-9), 2)
    if hi < DETECT_MIN_SIGNAL or hi < DETECT_MARGIN * lo:
        return None, info
    return ("OPENGL" if gl < dx else "DIRECTX"), info


def _read_rgb(img):
    w, h = img.size
    buf = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape(h, w, img.channels)


def main(folder, material=None, texture_set=None, normal_convention=None, patterns=None, ao="skip",
         height_strength=0.5, assign_to=None, pack=False):
    if not os.path.isdir(folder):
        raise ValueError(f"folder not found: {folder}")
    convention = None if normal_convention is None else str(normal_convention).upper()
    if convention not in (None, "OPENGL", "DIRECTX", "AUTO"):
        raise ValueError("normal_convention must be OPENGL, DIRECTX or AUTO")
    auto = convention == "AUTO"
    if auto:
        convention = None
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
        if obj not in targets:
            targets.append(obj)
    listed = {o.name for o in targets}
    for obj in targets:
        others = [o.name for o in bpy.data.objects if o.type == "MESH" and o.data is obj.data and o.name not in listed]
        if others:
            raise ValueError(f"assign_to: {obj.name!r} shares its mesh data with {others}, which are not listed; a new slot "
                             "would appear on them too. List them as well, or make the mesh single-user, and run again. "
                             "Nothing was changed.")

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

    warnings = []
    conv_source, conv_scores, conv_suggestion = None, None, None
    if "normal" in found:
        toks = [t for t in re.split(r"[^a-z0-9]+", os.path.splitext(found["normal"])[0].lower()) if t]
        conv_at = [(i, "DIRECTX" if t in ("directx", "dx") else "OPENGL")
                   for i, t in enumerate(toks) if t in ("directx", "dx", "opengl", "gl")]
        named = None
        if conv_at:
            # the convention suffix sits next to the normal token ("Armor_Normal_OpenGL"); a stray "DX_" asset prefix
            # elsewhere in the name must not outvote it
            n_at = max((i for i, t in enumerate(toks) if t in NORMAL_TOKENS), default=len(toks))
            named = min(conv_at, key=lambda c: (abs(c[0] - n_at), c[0] < n_at))[1]
            if len({c for _, c in conv_at}) > 1:
                warnings.append(f"normal map {found['normal']!r} names both DirectX and OpenGL; used {named}, the one next "
                                "to the 'normal' token. Pass normal_convention to override.")
        if convention is not None:
            conv_source = "argument"
            if named is not None and named != convention:
                warnings.append(f"normal_convention={convention} disagrees with the file name {found['normal']!r} ({named}); "
                                f"using {convention} as asked.")
        elif named is not None:
            convention, conv_source = named, "filename"
        else:
            conv_source = "content" if auto else "default"  # settled once the image is loaded, below
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
        if conv_source in ("content", "default"):
            guess, conv_scores = _detect_normal_convention(_read_rgb(tex.image))
            if conv_source == "content":  # normal_convention="auto": the pixels may flip green
                if guess is None:
                    convention, conv_source = "OPENGL", "default"
                    warnings.append(f"normal_convention='auto': normal map {found['normal']!r} names no convention and its pixels "
                                    f"do not settle it (curl scores {conv_scores}); assumed OPENGL (no green flip).")
                else:
                    convention = guess
                    warnings.append(f"normal_convention='auto': read {guess} from the pixels of {found['normal']!r} (curl scores "
                                    f"{conv_scores}). This can be wrong for a map that is not the gradient of a height field "
                                    "(hand-painted, some bakes) or whose red channel is inverted; pass normal_convention to be sure.")
            else:  # no argument, no name hint: OpenGL as before; DirectX-looking pixels are only a suggestion
                convention = "OPENGL"
                if guess == "DIRECTX":
                    conv_suggestion = "directx"
                    warnings.append(f"normal map {found['normal']!r} does not name its convention; assumed OPENGL (no green flip), "
                                    f"but its pixels look like DirectX (curl scores {conv_scores}). Not flipped: that test can be "
                                    "wrong for maps that are not height-derived or have an inverted red channel. If it is DirectX, "
                                    "pass normal_convention='DIRECTX' (or 'auto' to let the pixels decide).")
                else:
                    warnings.append(f"normal map {found['normal']!r} does not name its convention; assumed OPENGL (no green flip). "
                                    "If it was exported for DirectX, pass normal_convention='DIRECTX'.")
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
    done = set()
    for obj in targets:
        if obj.data.name in done:
            continue
        done.add(obj.data.name)
        obj.data.materials.append(mat)
    return {"material": mat.name, "files": found, "wired": wired, "images": images, "unmatched": unmatched,
            "ambiguous": ambiguous, "skipped_udim": skipped_udim, "normal_convention": convention or "OPENGL", "normal_convention_source": conv_source,
            "normal_convention_scores": conv_scores,
            "normal_convention_suggestion": conv_suggestion,
            "assigned": [o.name for o in targets], "warnings": warnings}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
