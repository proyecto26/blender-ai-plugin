# Scatter Systems

How to place many instances on a surface so the result looks placed, not sprinkled: choose the count, mask where things may
grow, keep them out of things that are in the way, and keep the result repeatable.

Node and socket names below were read from Blender 5.2 (`GeometryNodeDistributePointsOnFaces` and the others named in the
recipe). The recipe at the end builds the whole system and checks it.

## Starting values

| Scatter | Density | Scale | Rotation | Mask |
|---|---|---|---|---|
| Rock on cliff | 0.3 to 1.0 per m2 | 0.5 to 2.0 (per axis 0.8 to 1.2) | random Z; align to normal optional | exclude slope above 45 degrees |
| Grass | 5 to 20 per m2 | 0.8 to 1.2 | random Z | upward faces only: normal dot Z above 0.7 |
| Debris | clustered, minimum spacing 0.3 m | 0.6 to 1.4 | random | density painted near the source |

## Distribute: random or Poisson

`Distribute Points on Faces` has two modes (`distribute_method`): `RANDOM` and `POISSON`.

| Mode | Use | Cost |
|---|---|---|
| `RANDOM` | grass, gravel, anything small and dense; clumps and gaps are fine | input `Density` |
| `POISSON` | rocks, trees, props that must not overlap each other | inputs `Distance Min`, `Density Max`, `Density Factor` replace `Density` |

Inputs both modes share: `Mesh`, `Selection`, `Seed`. In `POISSON` mode, `Distance Min` is the least spacing between points, `Density Max` the ceiling and
`Density Factor` the 0 to 1 multiplier; feed a mask into `Density Factor` there, where `RANDOM` mode takes it in `Density`. The same seed on the same mesh gives the same points
(checked in the recipe); change the seed to re-roll. Outputs: `Points`, `Normal`, `Rotation`. Apply scale on the surface
object first, so a density of 4 means 4 per square metre in the world and not in the mesh's own units.

## Density masks

Two ways to say "less here, none there":

- Vertex group (or any float attribute): read it with `Named Attribute`, multiply it into `Density`. Weight 0 gives no
  points, 1 gives full density, 0.5 gives half. A mask edge can be no sharper than the surface's faces (the recipe tolerates one 0.5 m
  cell at the edge): subdivide the surface where the edge matters. Paint the group in Weight Paint mode.
- Procedural: `Noise Texture` factor through `Map Range` into `Density` for natural patches, or the surface `Normal` (z
  component) compared to a threshold for slope.

Use `Selection` on `Instance on Points` to switch whole points off without changing the count of the others, and `Density`
to thin by area.

## Collision-aware scatter

Instances should stay out of things already in the scene. Geometry nodes cannot see other objects on their own: bring the
blocker in with `Object Info` (its `Geometry` output), feed that to `Geometry Proximity` (target `Geometry`; its `Sample
Position` defaults to each point's position), and keep points whose `Distance` is greater than the clearance, through a
`Compare` into `Selection`.

Proximity measures the distance to the nearest surface, so a point deep inside a closed blocker is far from every surface and
would pass that test. When the blocker can contain points (a box sunk into the ground), also fire a `Raycast` from each point
and drop it when the ray's first hit is a back face (`Hit Normal` dot ray direction is positive); the recipe below does this.
It works only for a closed mesh with outward normals.

Set `Object Info` to `Relative` (`transform_space`). With the default `Original` the blocker's geometry is read at its own
origin, not where it stands, and the clearance check silently measures the wrong place; the first version of the recipe below
failed its check for exactly this reason.

Clearance is the blocker's reach plus half the instance's width. A rock 0.4 m wide near a wall wants 0.2 m plus the gap
you want to see.

This stops points landing inside the blocker. It does not stop an instance's own mesh from overlapping a neighbour instance:
for that use `POISSON` with a minimum distance at least the instance width. Raycast (`Raycast` node: `Target Geometry`,
`Source Position`, `Ray Direction`, `Ray Length`; outputs `Is Hit`, `Hit Position`, `Hit Normal`) is the tool to drop points
onto a surface below or to test a line of sight; it is not needed for clearance from a blocker that points cannot lie inside.

## Instancing

`Instance on Points` takes `Points`, `Selection`, `Instance`, `Pick Instance`, `Instance Index`, `Rotation`, `Scale`.

- One source object: connect it to `Instance`.
- Several variants: `Collection Info` with `Separate Children` on, `Reset Children` on, and `Pick Instance` on. Each point
  takes a random child unless `Instance Index` says otherwise. Exclude the source collection in the view layer so only
  instances render.
- Random scale: `Random Value` (Float) with `Min`, `Max`, `Seed` into `Scale`. Reuse the seed input so one number re-rolls
  everything.
- Align to ground: take `Rotation` from the Distribute node.
- A finished scatter has to become real geometry only for export: `Realize Instances` once, at the end, and count triangles
  afterwards. The `geometry-nodes` skill's `scripts/scatter_points.py` builds a simpler scatter with these options.

## Performance cap

Cap the count by capping density, not by keeping the first N points by index: index order follows the mesh, not a fair
random sample, so an index cut can empty whole areas (not measured here). Use `density = min(density, cap / surface_area)`. This is a soft cap, not a hard one: Distribute Points on Faces places a random count around density times area. Measured on Blender 5.2.3 on a 10 m by 10 m flat grid, 100 seeds at cap 500 (density 5.0): 471 to 530 points, mean 499.75, 50 of the 100 seeds over the cap; at cap 100: 72 to 133, 45 over. If the limit is hard, leave headroom: the worst seed was 6% over at 500 and 33% over at 100 (a different surface or mesh may differ). A hard cap was not implemented here.

Background: 500 instances. Hero zone: 2000 at most. Check the number from the evaluated depsgraph, as in the recipe.

## Recipe (tested)

Builds `GN_Scatter_Masked` on a ground plane `ScatterGround` with a blocker box `ScatterBlocker` and a rock in the
collection `ScatterSources`. The blocker is a closed 3 m box that straddles the ground, so some ground points lie 1.5 m
inside it. It then runs checks that can fail: a density mask on half the plane, clearance around the blocker (first with
the blocker moved away, to prove points would otherwise land inside it), no point left inside the closed blocker, the same
seed twice, and a different seed. It raises on any failure. Everything it creates carries a `recipe_owner` tag; re-running
removes only tagged data from an earlier run, and same-name objects, meshes, node groups or collections you already have are
left alone (the recipe's copies get a `.001` suffix).

```python
import bpy
import bmesh

# Everything this recipe creates is tagged; a re-run removes only tagged data from an earlier run. Data you already have
# with the same name is never touched: the new data gets a .001 name, and the recipe holds references instead of names.
TAG, OWNER = "recipe_owner", "scatter-systems"
for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.node_groups, bpy.data.collections):
    for stale in [d for d in coll if d.get(TAG) == OWNER]:
        coll.remove(stale)

sc = bpy.context.scene

def box_mesh(name, size, loc):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, size / 2))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob[TAG] = me[TAG] = OWNER
    ob.location = loc
    return ob

# ground: 10 m x 10 m, 20 x 20 faces (0.5 m cells), flat at z = 0
me = bpy.data.meshes.new("ScatterGround")
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=20, y_segments=20, size=5.0)
bm.to_mesh(me)
bm.free()
ground = bpy.data.objects.new("ScatterGround", me)
ground[TAG] = me[TAG] = OWNER
sc.collection.objects.link(ground)
xs = [v.co.x for v in me.vertices]
assert abs(max(xs) - 5.0) < 1e-4 and abs(min(xs) + 5.0) < 1e-4, "ground is not 10 m wide"
area = 100.0

# density mask: weight 1 where x >= 0, else 0
vg = ground.vertex_groups.new(name="density")
vg.add([v.index for v in me.vertices if v.co.x >= 0], 1.0, "REPLACE")
vg.add([v.index for v in me.vertices if v.co.x < 0], 0.0, "REPLACE")

# a closed 3 m box that straddles the ground: x 1..4, y -1.5..1.5, z -1.5..1.5, so ground points inside it are 1.5 m deep
blocker = box_mesh("ScatterBlocker", 3.0, (2.5, 0.0, -1.5))
sc.collection.objects.link(blocker)

src = bpy.data.collections.new("ScatterSources")
src[TAG] = OWNER
sc.collection.children.link(src)
rock = box_mesh("ScatterRock", 0.2, (0, 0, 0))
src.objects.link(rock)
bpy.context.view_layer.layer_collection.children[src.name].exclude = True

def sock(sockets, name):
    return next(s for s in sockets if s.name == name and s.enabled)

ng = bpy.data.node_groups.new("GN_Scatter_Masked", "GeometryNodeTree")
ng[TAG] = OWNER
io = ng.interface
io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
io.new_socket("Instances", in_out="INPUT", socket_type="NodeSocketCollection")
io.new_socket("Density", in_out="INPUT", socket_type="NodeSocketFloat")
io.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt")
io.new_socket("Clearance", in_out="INPUT", socket_type="NodeSocketFloat")
io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
N, L = ng.nodes, ng.links
gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
dist = N.new("GeometryNodeDistributePointsOnFaces")
dist.distribute_method = "RANDOM"
mask = N.new("GeometryNodeInputNamedAttribute")
mask.data_type = "FLOAT"
sock(mask.inputs, "Name").default_value = "density"
mul = N.new("ShaderNodeMath")
mul.operation = "MULTIPLY"
blk = N.new("GeometryNodeObjectInfo")
blk.transform_space = "RELATIVE"
sock(blk.inputs, "Object").default_value = blocker
near = N.new("GeometryNodeProximity")
far = N.new("FunctionNodeCompare")
far.data_type = "FLOAT"
far.operation = "GREATER_THAN"
# Proximity measures the distance to the NEAREST SURFACE, so a point deep inside a closed blocker still looks far away.
# Fire a ray up from each point: from inside a closed mesh the first thing it hits is a back face (its normal points
# along the ray). Inside = hit AND normal . direction > 0.
up = N.new("ShaderNodeCombineXYZ")
up.inputs["Z"].default_value = 1.0
inside_ray = N.new("GeometryNodeRaycast")
inside_dot = N.new("ShaderNodeVectorMath")
inside_dot.operation = "DOT_PRODUCT"
back = N.new("FunctionNodeCompare")
back.data_type = "FLOAT"
back.operation = "GREATER_THAN"
inside = N.new("FunctionNodeBooleanMath")
inside.operation = "AND"
outside = N.new("FunctionNodeBooleanMath")
outside.operation = "NOT"
keep = N.new("FunctionNodeBooleanMath")
keep.operation = "AND"
col = N.new("GeometryNodeCollectionInfo")
sock(col.inputs, "Separate Children").default_value = True
sock(col.inputs, "Reset Children").default_value = True
rnd = N.new("FunctionNodeRandomValue")
rnd.data_type = "FLOAT"
sock(rnd.inputs, "Min").default_value = 0.8
sock(rnd.inputs, "Max").default_value = 1.2
inst = N.new("GeometryNodeInstanceOnPoints")
sock(inst.inputs, "Pick Instance").default_value = True
join = N.new("GeometryNodeJoinGeometry")

L.new(sock(gin.outputs, "Geometry"), sock(dist.inputs, "Mesh"))
L.new(sock(gin.outputs, "Seed"), sock(dist.inputs, "Seed"))
L.new(sock(gin.outputs, "Density"), mul.inputs[0])
L.new(sock(mask.outputs, "Attribute"), mul.inputs[1])
L.new(sock(mul.outputs, "Value"), sock(dist.inputs, "Density"))
L.new(sock(blk.outputs, "Geometry"), sock(near.inputs, "Geometry"))
L.new(sock(near.outputs, "Distance"), sock(far.inputs, "A"))
L.new(sock(gin.outputs, "Clearance"), sock(far.inputs, "B"))
L.new(sock(blk.outputs, "Geometry"), sock(inside_ray.inputs, "Target Geometry"))
L.new(sock(up.outputs, "Vector"), sock(inside_ray.inputs, "Ray Direction"))
L.new(sock(inside_ray.outputs, "Hit Normal"), inside_dot.inputs[0])
L.new(sock(up.outputs, "Vector"), inside_dot.inputs[1])
L.new(sock(inside_dot.outputs, "Value"), sock(back.inputs, "A"))
L.new(sock(inside_ray.outputs, "Is Hit"), inside.inputs[0])
L.new(sock(back.outputs, "Result"), inside.inputs[1])
L.new(sock(inside.outputs, "Boolean"), outside.inputs[0])
L.new(sock(far.outputs, "Result"), keep.inputs[0])
L.new(sock(outside.outputs, "Boolean"), keep.inputs[1])
L.new(sock(keep.outputs, "Boolean"), sock(inst.inputs, "Selection"))
L.new(sock(dist.outputs, "Points"), sock(inst.inputs, "Points"))
L.new(sock(dist.outputs, "Rotation"), sock(inst.inputs, "Rotation"))
L.new(sock(gin.outputs, "Instances"), sock(col.inputs, "Collection"))
L.new(sock(col.outputs, "Instances"), sock(inst.inputs, "Instance"))
L.new(sock(gin.outputs, "Seed"), sock(rnd.inputs, "Seed"))
L.new(sock(rnd.outputs, "Value"), sock(inst.inputs, "Scale"))
L.new(sock(gin.outputs, "Geometry"), sock(join.inputs, "Geometry"))
L.new(sock(inst.outputs, "Instances"), sock(join.inputs, "Geometry"))
L.new(sock(join.outputs, "Geometry"), sock(gout.inputs, "Geometry"))

mod = ground.modifiers.new("GN_Scatter", "NODES")
mod.node_group = ng

def set_input(name, value):
    item = next(i for i in ng.interface.items_tree
                if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == name)
    getattr(mod.properties.inputs, item.identifier).value = value

def points(seed, clearance, density=4.0):
    set_input("Instances", src)
    set_input("Density", density)
    set_input("Seed", seed)
    set_input("Clearance", clearance)
    ground.update_tag()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    return sorted((round(i.matrix_world.translation.x, 4), round(i.matrix_world.translation.y, 4))
                  for i in dg.object_instances if i.is_instance and i.parent and i.parent.original == ground)

def blocker_gap(p):
    # the points lie on z = 0, where the blocker's cross-section is x in [1, 4], y in [-1.5, 1.5] with vertical sides:
    # a point inside it has gap 0, one outside has its distance to that rectangle
    dx = max(1.0 - p[0], 0.0, p[0] - 4.0)
    dy = max(abs(p[1]) - 1.5, 0.0)
    return (dx * dx + dy * dy) ** 0.5

open_run = points(seed=1, clearance=0.0)
clear_run = points(seed=1, clearance=0.75)
again = points(seed=1, clearance=0.75)
other = points(seed=2, clearance=0.75)

assert len(open_run) > 100, f"too few instances to test: {len(open_run)}"
assert min(p[0] for p in open_run) > -0.5 - 1e-3, "density mask leaked into the zero-weight half"
assert any(0.0 < blocker_gap(p) < 0.75 for p in open_run), "test is blind: nothing was near the blocker's outside"
assert all(blocker_gap(p) >= 0.75 - 1e-3 for p in clear_run), "instances inside the clearance"
def deep_inside(p):                    # more than 1 m from every side of the box's cross-section (box is 1.5 m deep)
    return 2.0 <= p[0] <= 3.0 and abs(p[1]) <= 0.5
blocker.location.x += 100.0            # move the blocker away to see what the scatter would place without it
free_run = points(seed=1, clearance=0.0)
blocker.location.x -= 100.0
assert any(deep_inside(p) for p in free_run), "test is blind: the scatter puts no point deep inside the blocker's spot"
assert not any(deep_inside(p) for p in open_run), "points deep inside a closed blocker were kept (clearance 0)"
assert not any(deep_inside(p) for p in clear_run), "points deep inside a closed blocker were kept"
assert len(clear_run) < len(open_run), "clearance removed nothing"
assert again == clear_run, "same seed gave a different result"
assert other != clear_run, "different seed gave the same result"
assert len(open_run) <= 4.0 * area / 2 * 1.6, "more instances than the density allows"

result = {"instances_free": len(free_run), "instances_open": len(open_run), "instances_with_clearance": len(clear_run),
          "removed_by_clearance": len(open_run) - len(clear_run), "min_x_open": min(p[0] for p in open_run),
          "min_gap_to_blocker": round(min(blocker_gap(p) for p in clear_run), 3),
          "same_seed_equal": again == clear_run, "other_seed_differs": other != clear_run}
```

Result when run on Blender 5.2.3: 218 instances with the blocker away, 176 with it in place at clearance 0 (the ones inside it are
gone), 140 with clearance 0.75, nearest instance 0.76 m from the blocker, lowest x of a masked instance -0.497, same seed
equal, other seed different.

What the checks prove: the mask keeps points off the zero-weight half, clearance removes points near the blocker and points
inside it (and the test would fail if the blocker never mattered), seeds behave. The inside test is a ray fired straight up
from each point: it needs a closed blocker with outward-facing normals, and it reads a point as inside when the first
surface the ray meets is a back face. An open mesh, flipped normals, or a blocker whose inside is open to the sky along +Z
because of a hole will not be detected; plain distance (the clearance check) still applies to those. They do not judge how it looks, and the instance count line
is only an upper-bound sanity check, not a measure of density accuracy.
