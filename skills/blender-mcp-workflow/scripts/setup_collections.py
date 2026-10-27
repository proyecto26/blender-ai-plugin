"""Create the standard COL_ production hierarchy (idempotent, non-destructive).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/setup_collections.py",
                            init_globals={"ARGS": {"asset": "Crate"}})["result"]

ARGS:
    asset    (str|None)  optional asset name; nests the hierarchy under COL_<asset>
    layout   (list[str]) collection suffixes to create (default production layout)
    hide     (list[str]) suffixes hidden in viewport + render (default Reference/HighPoly)
"""
import json
import sys

import bpy

DEFAULT_LAYOUT = ["Reference", "Blockout", "HighPoly", "LowPoly", "Collision", "Lights", "Cameras", "Export"]
DEFAULT_HIDDEN = ["Reference", "HighPoly"]


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _ensure(name, parent):
    col = bpy.data.collections.get(name)
    created = col is None
    if created:
        col = bpy.data.collections.new(name)
    if col.name not in parent.children:
        parent.children.link(col)
    return col, created


def main(asset=None, layout=None, hide=None):
    layout = layout or DEFAULT_LAYOUT
    hide = DEFAULT_HIDDEN if hide is None else hide
    scene_root = bpy.context.scene.collection
    root, root_created = (_ensure(f"COL_{asset}", scene_root) if asset else (scene_root, False))
    created, existing = [], []
    prefix = f"COL_{asset}_" if asset else "COL_"
    for suffix in layout:
        col, was_created = _ensure(prefix + suffix, root)
        (created if was_created else existing).append(col.name)
        if suffix in hide:
            col.hide_render = True
            col.hide_viewport = False  # keep visible in the outliner; hide per view layer below
            layer_col = _find_layer_collection(bpy.context.view_layer.layer_collection, col.name)
            if layer_col:
                layer_col.hide_viewport = True
    return {"root": root.name, "root_created": root_created, "created": created, "existing": existing}


def _find_layer_collection(layer_col, name):
    if layer_col.name == name:
        return layer_col
    for child in layer_col.children:
        found = _find_layer_collection(child, name)
        if found:
            return found
    return None


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
