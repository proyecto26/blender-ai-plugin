"""Build a compositor grade with the Blender 5.x API (scene.compositing_node_group,
Group Output, socket-based Glare). Replaces only nodes this script created
(its own SK_ nodes), so a user's nodes and other scripts' SK_ stages (PS1 fog) are kept;
the grade is chained after whatever already feeds the output.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/comp_grade.py",
                            init_globals={"ARGS": {"preset": "cinematic"}})["result"]

ARGS:
    preset   (str)   clean | cinematic | horror_vhs | stylized_bloom | noir
    vignette (float) 0..1 edge darkening; overrides the preset (cinematic 0.35, horror_vhs 0.5)
    warmth   (float) -1..1 tint of the highlights (gain); >0 warm, <0 cool; overrides the preset gain
    posterize (int)  colour steps per channel (Posterize node), e.g. 4 for an 8-bit/NES palette; off by default
"""
import json
import sys

import bpy

PRESETS = {
    "clean": {"bloom": None, "lift_gamma_gain": None, "saturation": 1.0, "lens": 0.0, "pixel": None},
    "cinematic": {"bloom": (0.9, 0.35), "lift_gamma_gain": ((0.98, 1.0, 1.04), (1.0, 1.0, 0.98), (1.04, 1.0, 0.95)),
                  "saturation": 0.95, "lens": 0.01, "pixel": None, "vignette": 0.35},
    "horror_vhs": {"bloom": (0.6, 0.5), "lift_gamma_gain": ((1.0, 1.03, 1.0), (0.95, 1.0, 0.95), (0.9, 1.0, 0.92)),
                   "saturation": 0.6, "lens": 0.04, "pixel": 2, "vignette": 0.5},
    "stylized_bloom": {"bloom": (0.7, 0.8), "lift_gamma_gain": None, "saturation": 1.15, "lens": 0.0, "pixel": None},
    "noir": {"bloom": (1.0, 0.2), "lift_gamma_gain": None, "saturation": 0.0, "lens": 0.02, "pixel": None},
}


OWN_NODES = {"SK_Bloom", "SK_ColorBalance", "SK_Saturation", "SK_Lens", "SK_Pixelate",
             "SK_VignetteMask", "SK_VignetteBlur", "SK_Vignette", "SK_Posterize"}

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
    raise KeyError(f"no enabled socket {name!r}: {[s.name for s in sockets if s.enabled]}")


def main(preset="cinematic", vignette=None, warmth=None, posterize=None):
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    cfg = dict(PRESETS[preset])
    if vignette is not None:
        cfg["vignette"] = max(0.0, min(1.0, float(vignette)))
    if warmth is not None:
        w = max(-1.0, min(1.0, float(warmth))) * 0.1
        lift, gamma, _ = cfg["lift_gamma_gain"] or ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), None)
        cfg["lift_gamma_gain"] = (lift, gamma, (1.0 + w, 1.0, 1.0 - w))
    scene = bpy.context.scene
    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
        scene.compositing_node_group = tree
    if not any(getattr(i, "in_out", None) == "OUTPUT" for i in tree.interface.items_tree):
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    nodes, links = tree.nodes, tree.links
    # Remove only this script's nodes; other SK_ stages (e.g. lowpoly-style SK_PS1_Fog) stay in the
    # chain. Inputs they lose are reconnected to whatever fed the old grade.
    own = [n for n in nodes if n.name in OWN_NODES]
    own_names = {n.name for n in own}
    feed = next((l.from_socket for n in own for l in links
                 if l.to_node == n and l.from_node.name not in own_names
                 and l.to_socket.bl_idname == "NodeSocketColor"), None)
    orphaned = [l.to_socket for l in links
                if l.from_node.name in own_names and l.to_node.name not in own_names
                and l.to_node.bl_idname != "NodeGroupOutput"]
    for node in own:
        nodes.remove(node)

    def add(kind, name, x):
        node = nodes.new(kind)
        node.name = node.label = name
        node.location = (x, 0)
        return node

    rl = next((n for n in nodes if n.bl_idname == "CompositorNodeRLayers"), None) or add("CompositorNodeRLayers", "SK_RenderLayers", -800)
    out = next((n for n in nodes if n.bl_idname == "NodeGroupOutput"), None) or add("NodeGroupOutput", "SK_Output", 900)
    for sock in orphaned:
        links.new(feed or _sock(rl.outputs, "Image"), sock)
    # Grade on top of the existing chain (fog, user nodes) instead of straight from Render Layers
    chain = [out.inputs[0].links[0].from_socket if out.inputs[0].is_linked else _sock(rl.outputs, "Image")]
    built, x = [], -500

    if cfg["bloom"]:
        threshold, strength = cfg["bloom"]
        glare = add("CompositorNodeGlare", "SK_Bloom", x); x += 220
        _sock(glare.inputs, "Type").default_value = "Bloom"
        _sock(glare.inputs, "Threshold").default_value = threshold
        _sock(glare.inputs, "Strength").default_value = strength
        links.new(chain[-1], _sock(glare.inputs, "Image")); chain.append(_sock(glare.outputs, "Image")); built.append(glare.name)
    if cfg["lift_gamma_gain"]:
        cb = add("CompositorNodeColorBalance", "SK_ColorBalance", x); x += 220
        lift, gamma, gain = cfg["lift_gamma_gain"]
        for label, value in (("Lift", lift), ("Gamma", gamma), ("Gain", gain)):
            for s in cb.inputs:
                if s.enabled and s.name.startswith(label) and s.bl_idname == "NodeSocketColor":
                    s.default_value = (*value, 1.0)
                    break
        links.new(chain[-1], _sock(cb.inputs, "Image")); chain.append(_sock(cb.outputs, "Image")); built.append(cb.name)
    if cfg["saturation"] != 1.0:
        hs = add("CompositorNodeHueSat", "SK_Saturation", x); x += 220
        _sock(hs.inputs, "Saturation").default_value = cfg["saturation"]
        links.new(chain[-1], _sock(hs.inputs, "Image")); chain.append(_sock(hs.outputs, "Image")); built.append(hs.name)
    if cfg["lens"]:
        lens = add("CompositorNodeLensdist", "SK_Lens", x); x += 220
        for s in lens.inputs:
            if s.enabled and s.name in ("Dispersion",):
                s.default_value = cfg["lens"]
        links.new(chain[-1], _sock(lens.inputs, "Image")); chain.append(_sock(lens.outputs, "Image")); built.append(lens.name)
    if cfg["pixel"]:
        px = add("CompositorNodePixelate", "SK_Pixelate", x); x += 220
        for s in px.inputs:
            if s.enabled and s.name == "Size":
                s.default_value = cfg["pixel"]
        links.new(chain[-1], _sock(px.inputs, "Color") if any(s.name == "Color" and s.enabled for s in px.inputs)
                  else _sock(px.inputs, "Image"))
        chain.append(px.outputs[0]); built.append(px.name)
    if posterize:
        post = add("CompositorNodePosterize", "SK_Posterize", x); x += 220
        _sock(post.inputs, "Steps").default_value = max(2, int(posterize))
        links.new(chain[-1], _sock(post.inputs, "Image")); chain.append(_sock(post.outputs, "Image")); built.append(post.name)
    if cfg.get("vignette"):
        # Ellipse Mask (white centre) -> Blur (soft edge) -> Mix MULTIPLY over the image.
        # 5.2: mask/blur settings are input sockets; Mix is ShaderNodeMix with data_type RGBA.
        mask = add("CompositorNodeEllipseMask", "SK_VignetteMask", x - 220); mask.location.y = -320
        _sock(mask.inputs, "Size").default_value = (0.95, 0.95)
        blur = add("CompositorNodeBlur", "SK_VignetteBlur", x); blur.location.y = -320
        _sock(blur.inputs, "Size").default_value = (180, 180)
        links.new(_sock(mask.outputs, "Mask"), _sock(blur.inputs, "Image"))
        mix = add("ShaderNodeMix", "SK_Vignette", x + 220); x += 440
        mix.data_type, mix.blend_type, mix.clamp_result = "RGBA", "MULTIPLY", True
        colour = [s for s in mix.inputs if s.enabled and s.bl_idname == "NodeSocketColor"]
        _sock(mix.inputs, "Factor").default_value = cfg["vignette"]
        links.new(chain[-1], colour[0]); links.new(_sock(blur.outputs, "Image"), colour[1])
        chain.append(next(s for s in mix.outputs if s.enabled))
        built += [mask.name, blur.name, mix.name]
    links.new(chain[-1], out.inputs[0])
    return {"preset": preset, "tree": tree.name, "nodes": built, "link_count": len(tree.links),
            "vignette": cfg.get("vignette") or 0.0, "posterize": int(posterize) if posterize else None}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
