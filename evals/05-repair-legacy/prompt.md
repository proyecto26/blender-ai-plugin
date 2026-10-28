---
max_turns: 12
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill]
runs: 3
tags: [blender-5x-code]
---

This script worked in Blender 3.6. Make it work in Blender 5.2 and give me the full fixed script:

```python
import bpy
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.use_bloom = True
scene.eevee.bloom_intensity = 0.1
for obj in bpy.context.selected_objects:
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = 0.5236
mat = bpy.data.materials["Metal"]
nodes = mat.node_tree.nodes
sep = nodes.new("ShaderNodeSeparateRGB")
nodes["Principled BSDF"].inputs["Specular"].default_value = 0.8
scene.use_nodes = True
tree = scene.node_tree
glare = tree.nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
tree.links.new(tree.nodes["Render Layers"].outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], tree.nodes["Composite"].inputs["Image"])
```

Blender isn't connected to this chat; give me the code and I'll run it.
