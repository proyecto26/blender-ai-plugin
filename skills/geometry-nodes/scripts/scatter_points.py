"""Build a reusable geometry-nodes scatter on a surface object: Distribute Points on
Faces -> Instance on Points (collection, random pick) with random rotation/scale,
aligned to the surface normal. Density, seed and scale are exposed as modifier inputs.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/scatter_points.py", init_globals={"ARGS": {
        "surface": "GEO_Ground", "collection": "COL_Rocks", "density": 5.0}})["result"]

ARGS:
    surface        (str, required)  mesh object that receives the modifier
    collection     (str, required)  collection whose objects get instanced
    density        (float) points per m^2 (default 2)
    seed           (int)
    scale_min, scale_max (float) random uniform scale range
    align_to_normal (bool)  default True (False = keep instances upright, e.g. trees)
    realize        (bool)  realize instances (needed for some exports; default False)
"""
import json
import sys

import bpy

GROUP_NAME = "GN_SkillScatter"


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _sock(sockets, name):
    """Return the enabled socket called *name* (nodes keep hidden per-type duplicates)."""
    for s in sockets:
        if s.name == name and s.enabled:
            return s
    raise KeyError(f"no enabled socket {name!r}; available: {[s.name for s in sockets if s.enabled]}")


def _build_group(align_to_normal, realize):
    name = f"{GROUP_NAME}{'_Align' if align_to_normal else ''}{'_Real' if realize else ''}"
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    try:
        _populate(ng, align_to_normal, realize)
    except Exception:
        bpy.data.node_groups.remove(ng)  # never leave a half-built group behind
        raise
    return ng


def _populate(ng, align_to_normal, realize):
    io = ng.interface
    io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    io.new_socket("Instances", in_out="INPUT", socket_type="NodeSocketCollection")
    s_density = io.new_socket("Density", in_out="INPUT", socket_type="NodeSocketFloat")
    s_density.default_value, s_density.min_value = 2.0, 0.0
    io.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt")
    s_min = io.new_socket("Scale Min", in_out="INPUT", socket_type="NodeSocketFloat")
    s_min.default_value = 0.8
    s_max = io.new_socket("Scale Max", in_out="INPUT", socket_type="NodeSocketFloat")
    s_max.default_value = 1.2
    io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n, l = ng.nodes, ng.links
    gin = n.new("NodeGroupInput"); gin.location = (-900, 0)
    gout = n.new("NodeGroupOutput"); gout.location = (700, 0)
    dist = n.new("GeometryNodeDistributePointsOnFaces"); dist.location = (-600, 0)
    dist.distribute_method = "RANDOM"
    col = n.new("GeometryNodeCollectionInfo"); col.location = (-600, -300)
    col.transform_space = "ORIGINAL"
    _sock(col.inputs, "Separate Children").default_value = True
    _sock(col.inputs, "Reset Children").default_value = True
    inst = n.new("GeometryNodeInstanceOnPoints"); inst.location = (200, 0)
    _sock(inst.inputs, "Pick Instance").default_value = True
    rnd_scale = n.new("FunctionNodeRandomValue"); rnd_scale.location = (-200, -350)
    rnd_scale.data_type = "FLOAT"
    rnd_rot = n.new("FunctionNodeRandomValue"); rnd_rot.location = (-400, -550)
    rnd_rot.data_type = "FLOAT"
    _sock(rnd_rot.inputs, "Max").default_value = 6.283185
    combine = n.new("ShaderNodeCombineXYZ"); combine.location = (-200, -550)
    join = n.new("GeometryNodeJoinGeometry"); join.location = (500, 0)

    l.new(_sock(gin.outputs, "Geometry"), _sock(dist.inputs, "Mesh"))
    l.new(_sock(gin.outputs, "Density"), _sock(dist.inputs, "Density"))
    l.new(_sock(gin.outputs, "Seed"), _sock(dist.inputs, "Seed"))
    l.new(_sock(gin.outputs, "Instances"), _sock(col.inputs, "Collection"))
    l.new(_sock(dist.outputs, "Points"), _sock(inst.inputs, "Points"))
    l.new(_sock(col.outputs, "Instances"), _sock(inst.inputs, "Instance"))
    l.new(_sock(gin.outputs, "Scale Min"), _sock(rnd_scale.inputs, "Min"))
    l.new(_sock(gin.outputs, "Scale Max"), _sock(rnd_scale.inputs, "Max"))
    l.new(_sock(gin.outputs, "Seed"), _sock(rnd_scale.inputs, "Seed"))
    l.new(_sock(rnd_scale.outputs, "Value"), _sock(inst.inputs, "Scale"))
    l.new(_sock(gin.outputs, "Seed"), _sock(rnd_rot.inputs, "Seed"))
    l.new(_sock(rnd_rot.outputs, "Value"), _sock(combine.inputs, "Z"))

    if align_to_normal:
        align = n.new("FunctionNodeAlignRotationToVector"); align.location = (-200, -150)
        align.axis = "Z"
        rotate = n.new("FunctionNodeRotateRotation"); rotate.location = (0, -250)
        rotate.rotation_space = "LOCAL"
        l.new(_sock(dist.outputs, "Rotation"), _sock(align.inputs, "Rotation"))
        l.new(_sock(dist.outputs, "Normal"), _sock(align.inputs, "Vector"))
        l.new(_sock(align.outputs, "Rotation"), _sock(rotate.inputs, "Rotation"))
        l.new(_sock(combine.outputs, "Vector"), _sock(rotate.inputs, "Rotate By"))
        l.new(_sock(rotate.outputs, "Rotation"), _sock(inst.inputs, "Rotation"))
    else:
        l.new(_sock(combine.outputs, "Vector"), _sock(inst.inputs, "Rotation"))

    last = _sock(inst.outputs, "Instances")
    if realize:
        real = n.new("GeometryNodeRealizeInstances"); real.location = (350, -100)
        l.new(last, _sock(real.inputs, "Geometry"))
        last = _sock(real.outputs, "Geometry")
    l.new(_sock(gin.outputs, "Geometry"), _sock(join.inputs, "Geometry"))
    l.new(last, _sock(join.inputs, "Geometry"))
    l.new(_sock(join.outputs, "Geometry"), _sock(gout.inputs, "Geometry"))


def _set_input(mod, name, value):
    """Set a geometry-nodes modifier input by its interface name.

    Blender 5.2+: mod.properties.inputs.<identifier>.value
    Blender 4.x / 5.0-5.1: ID property mod[identifier]
    """
    for item in mod.node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name == name:
            props = getattr(mod, "properties", None)
            if props is not None and hasattr(props, "inputs"):
                getattr(props.inputs, item.identifier).value = value
            else:
                mod[item.identifier] = value
            return
    raise KeyError(f"modifier input not found: {name}")


def main(surface, collection, density=2.0, seed=0, scale_min=0.8, scale_max=1.2,
         align_to_normal=True, realize=False):
    obj = bpy.data.objects.get(surface)
    col = bpy.data.collections.get(collection)
    if obj is None or obj.type != "MESH":
        raise ValueError(f"surface mesh not found: {surface}")
    if col is None:
        raise ValueError(f"collection not found: {collection}")
    ng = _build_group(align_to_normal, realize)
    mod = obj.modifiers.get("GN_Scatter") or obj.modifiers.new("GN_Scatter", "NODES")
    mod.node_group = ng
    _set_input(mod, "Instances", col)
    _set_input(mod, "Density", float(density))
    _set_input(mod, "Seed", int(seed))
    _set_input(mod, "Scale Min", float(scale_min))
    _set_input(mod, "Scale Max", float(scale_max))
    obj.update_tag()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    instances = sum(1 for inst in depsgraph.object_instances
                    if inst.is_instance and inst.parent and inst.parent.original == obj)
    return {"modifier": mod.name, "node_group": ng.name, "instances": instances,
            "hint": "Exclude the source collection from the view layer so only instances render."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
