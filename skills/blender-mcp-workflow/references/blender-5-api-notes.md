# Blender 5.x API Notes

Verified live against **Blender 5.2.3 LTS** through the official MCP server. When unsure, call
`get_python_api_docs` - never guess from Blender 2.x/3.x memory.

## Removed or Renamed

| Old (do not use) | Blender 5.x |
|------------------|-------------|
| `mesh.use_auto_smooth`, `auto_smooth_angle` | Non-destructive: `bpy.ops.object.shade_auto_smooth(angle=...)` adds the **Smooth by Angle** geometry-nodes modifier. One-shot: `shade_smooth_by_angle(angle=...)` bakes sharp edges, no modifier |
| `scene.eevee.use_bloom` | Compositor **Glare** node, `Type` menu input = `Bloom` |
| `scene.eevee.use_ssr`, `use_gtao` | EEVEE ray tracing: `scene.eevee.use_raytracing`, `ray_tracing_method`, `use_fast_gi` |
| `BLENDER_EEVEE_NEXT` | `BLENDER_EEVEE` (engines: `BLENDER_EEVEE`, `CYCLES`, `BLENDER_WORKBENCH`) |
| `scene.node_tree` (compositor) | `scene.compositing_node_group` = a `CompositorNodeTree` node group; output via `NodeGroupOutput` |
| `CompositorNodeComposite` | Group Output of the compositor node group (Viewer still exists) |
| `CompositorNodeCombRGBA` / `SepRGBA` | `CompositorNodeCombineColor` / `SeparateColor` |
| `ShaderNodeSeparateRGB` / `CombineRGB` | `ShaderNodeSeparateColor` / `ShaderNodeCombineColor` |
| `ShaderNodeTexMusgrave` | `ShaderNodeTexNoise` (Musgrave types merged into Noise: fBM, multifractal, ...) |
| `GeometryNodeAlignRotationToVector` | `FunctionNodeAlignRotationToVector` |
| Compositor Glare `glare_type` property | Glare inputs are sockets: `Type`, `Quality`, `Threshold`, `Strength`, `Size`, ... |
| `scene.eevee.use_motion_blur` | `scene.render.use_motion_blur` |
| Geometry-nodes modifier inputs `mod["Socket_1"] = v` (ID properties) | **5.2+:** `mod.properties.inputs.Socket_1.value = v` (identifier from `node_group.interface.items_tree`); attribute-name toggles via `.attribute_name` |
| Curve to Mesh output `"Geometry"` | `GeometryNodeCurveToMesh` inputs `Curve`, `Profile Curve`, `Scale`, `Fill Caps`; output **`Mesh`**. Look up socket names with `[s.name for s in node.outputs if s.enabled]` instead of guessing |
| Fluid flow `flow_behavior = "CONTINUOUS"` | `flow_behavior` is `INFLOW` (continuous emission), `OUTFLOW` or `GEOMETRY`; `flow_type` is `SMOKE`, `FIRE`, `BOTH`, `LIQUID` |
| `Action.fcurves` | Layered actions: `action.layers[].strips[].channelbags[].fcurves` (or `anim_utils.action_get_channelbag_for_slot`) |

## Principled BSDF Input Names

`Base Color, Metallic, Roughness, IOR, Alpha, Normal, Weight, Diffuse Roughness, Subsurface Weight,
Subsurface Radius, Subsurface Scale, Subsurface IOR, Subsurface Anisotropy, Specular IOR Level,
Specular Tint, Anisotropic, Anisotropic Rotation, Tangent, Transmission Weight, Coat Weight,
Coat Roughness, Coat IOR, Coat Tint, Coat Normal, Sheen Weight, Sheen Roughness, Sheen Tint,
Emission Color, Emission Strength, Thin Film Thickness, Thin Film IOR, Thin Wall`

- "Specular 0.5" (old) = `Specular IOR Level` 0.5 (default).
- "Subsurface Color" is gone - subsurface uses `Base Color`; drive amount with `Subsurface Weight`.
- "Emission" (color) = `Emission Color`; it only glows when `Emission Strength` > 0.
- Always index sockets by name: `bsdf.inputs["Specular IOR Level"]`, never by number.

## Color Management

View transforms: `AgX` (default), `Filmic`, `Standard`, `Khronos PBR Neutral`, `Raw`, `False Color`.
AgX looks are prefixed: `"AgX - Punchy"`, `"AgX - Base Contrast"`, `"AgX - High Contrast"`, ...
Use `Standard` for pixel-exact stylized/pixel/UI work, `Khronos PBR Neutral` for product color accuracy.

## Still Valid

`ShaderNodeShaderToRGB` (EEVEE only), `ShaderNodeBsdfToon`, `ShaderNodeMix` (preferred over legacy
`ShaderNodeMixRGB`), `WEIGHTED_NORMAL`, `DECIMATE`, `REMESH`, `TRIANGULATE`, `LINEART` modifiers,
Grease Pencil v3 (`GREASEPENCIL` object type, `GREASE_PENCIL_*` modifiers), `CURVES` objects for hair,
`bpy.ops.export_scene.fbx`, `export_scene.gltf`, `wm.usd_export`, `wm.obj_export`, Cycles
`denoiser = "OPENIMAGEDENOISE"`, geometry node `interface` API (`node_group.interface.new_socket`).

## Patterns

```python
# Compositor in 5.x
scene = bpy.context.scene
tree = scene.compositing_node_group or bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
scene.compositing_node_group = tree
if not tree.interface.items_tree:
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = tree.nodes.new("CompositorNodeRLayers")
out = tree.nodes.new("NodeGroupOutput")
glare = tree.nodes.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"
tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], out.inputs[0])
```

```python
# Smooth by angle (replaces auto smooth) - operators need an object context
with bpy.context.temp_override(object=obj, active_object=obj,
                               selected_objects=[obj], selected_editable_objects=[obj]):
    bpy.ops.object.shade_auto_smooth(angle=math.radians(30))  # adds "Smooth by Angle" modifier
```

```python
# bmesh: build, index, write back, free. Index access needs a lookup table after any topology change.
import bmesh
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bm.verts.ensure_lookup_table()   # without it bm.verts[i] raises "outdated internal index table"
bm.faces.ensure_lookup_table()
bm.verts[0].co.z += 0.1
bm.to_mesh(mesh)                 # object mode; in edit mode use bmesh.from_edit_mesh / update_edit_mesh
bm.free()
mesh.update()
```
