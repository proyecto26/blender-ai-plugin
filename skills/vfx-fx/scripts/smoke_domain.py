"""Mantaflow gas setup: a tight domain box around an emitter object plus a flow on that
emitter, with a Principled Volume material on the domain. Low preview resolution by default;
bake is not started (bake is slow - ask first). Re-running updates the same domain.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/smoke_domain.py", init_globals={"ARGS": {
        "emitter": "SM_Crate", "flow_type": "BOTH"}})["result"]

ARGS:
    emitter     (str)   mesh that emits (required); its own transform is left untouched
    flow_type   (str)   SMOKE | FIRE | BOTH (default BOTH)
    resolution  (int)   domain resolution divisions (default 48, raise for final bake)
    padding     (float) metres of domain around the emitter sides (default 1.0)
    height      (float) metres of domain above the emitter (default 3.5)
    frame_end   (int)   cache end frame (default 120)
    collection  (str)   default "COL_FX"
"""
import json
import sys

import bpy
from mathutils import Vector


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _volume_material(flow_type):
    mat = bpy.data.materials.get("MAT_FX_Smoke") or bpy.data.materials.new("MAT_FX_Smoke")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 1.0
    vol.inputs["Color"].default_value = (0.35, 0.35, 0.35, 1.0)
    if flow_type in ("FIRE", "BOTH"):
        vol.inputs["Blackbody Intensity"].default_value = 1.0
        vol.inputs["Temperature"].default_value = 1500.0
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def main(emitter, flow_type="BOTH", resolution=48, padding=1.0, height=3.5, frame_end=120,
         collection="COL_FX"):
    src = bpy.data.objects.get(emitter)
    if src is None or src.type != "MESH":
        raise ValueError(f"emitter mesh not found: {emitter}")
    if flow_type not in ("SMOKE", "FIRE", "BOTH"):
        raise ValueError("flow_type must be SMOKE, FIRE or BOTH")

    corners = [src.matrix_world @ Vector(c) for c in src.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    lo -= Vector((padding, padding, 0.2))
    hi += Vector((padding, padding, height))
    size = hi - lo

    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection)
        bpy.context.scene.collection.children.link(col)
    name = f"FX_Domain_{src.name}"
    dom = bpy.data.objects.get(name)
    if dom is None:
        me = bpy.data.meshes.new(name)
        me.from_pydata([(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)], [],
                       [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
        dom = bpy.data.objects.new(name, me)
        col.objects.link(dom)
    dom.location = (lo + hi) / 2
    dom.scale = size
    dom.display_type = "WIRE"

    dmod = dom.modifiers.get("Fluid") or dom.modifiers.new("Fluid", "FLUID")
    dmod.fluid_type = "DOMAIN"
    ds = dmod.domain_settings
    ds.domain_type = "GAS"
    ds.resolution_max = int(resolution)
    ds.use_collision_border_top = False  # let smoke leave through the top
    ds.cache_frame_end = int(frame_end)
    if dom.data.materials:
        dom.data.materials[0] = _volume_material(flow_type)
    else:
        dom.data.materials.append(_volume_material(flow_type))

    fmod = src.modifiers.get("Fluid") or src.modifiers.new("Fluid", "FLUID")
    fmod.fluid_type = "FLOW"
    fs = fmod.flow_settings
    fs.flow_type = flow_type
    fs.flow_behavior = "INFLOW"   # continuous emission (enum: INFLOW, OUTFLOW, GEOMETRY)
    fs.flow_source = "MESH"
    fs.surface_distance = 0.05
    if flow_type in ("FIRE", "BOTH"):
        fs.fuel_amount = 1.0

    return {"domain": dom.name, "emitter": src.name, "flow_type": flow_type,
            "flow_behavior": fs.flow_behavior, "resolution": ds.resolution_max,
            "domain_size_m": [round(v, 2) for v in size], "material": dom.data.materials[0].name,
            "hint": "Preview at this resolution; raise resolution and bake (Cycles for fire) only after approval."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
