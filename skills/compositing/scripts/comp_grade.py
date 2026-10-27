"""Build a compositor grade with the Blender 5.x API (scene.compositing_node_group,
Group Output, socket-based Glare). Replaces only nodes this script created
(names starting "SK_"), so a user's own compositor nodes are kept.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/comp_grade.py",
                            init_globals={"ARGS": {"preset": "cinematic"}})["result"]

ARGS:
    preset (str) clean | cinematic | horror_vhs | stylized_bloom | noir
"""
import json
import sys

import bpy

PRESETS = {
    "clean": {"bloom": None, "lift_gamma_gain": None, "saturation": 1.0, "lens": 0.0, "pixel": None},
    "cinematic": {"bloom": (0.9, 0.35), "lift_gamma_gain": ((0.98, 1.0, 1.04), (1.0, 1.0, 0.98), (1.04, 1.0, 0.95)),
                  "saturation": 0.95, "lens": 0.01, "pixel": None},
    "horror_vhs": {"bloom": (0.6, 0.5), "lift_gamma_gain": ((1.0, 1.03, 1.0), (0.95, 1.0, 0.95), (0.9, 1.0, 0.92)),
                   "saturation": 0.6, "lens": 0.04, "pixel": 2},
    "stylized_bloom": {"bloom": (0.7, 0.8), "lift_gamma_gain": None, "saturation": 1.15, "lens": 0.0, "pixel": None},
    "noir": {"bloom": (1.0, 0.2), "lift_gamma_gain": None, "saturation": 0.0, "lens": 0.02, "pixel": None},
}


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


def main(preset="cinematic"):
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    cfg = PRESETS[preset]
    scene = bpy.context.scene
    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
        scene.compositing_node_group = tree
    if not any(getattr(i, "in_out", None) == "OUTPUT" for i in tree.interface.items_tree):
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    for node in [n for n in tree.nodes if n.name.startswith("SK_")]:
        tree.nodes.remove(node)
    nodes, links = tree.nodes, tree.links

    def add(kind, name, x):
        node = nodes.new(kind)
        node.name = node.label = name
        node.location = (x, 0)
        return node

    rl = next((n for n in nodes if n.bl_idname == "CompositorNodeRLayers"), None) or add("CompositorNodeRLayers", "SK_RenderLayers", -800)
    out = next((n for n in nodes if n.bl_idname == "NodeGroupOutput"), None) or add("NodeGroupOutput", "SK_Output", 900)
    chain = [_sock(rl.outputs, "Image")]
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
    links.new(chain[-1], out.inputs[0])
    return {"preset": preset, "tree": tree.name, "nodes": built, "link_count": len(tree.links)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
