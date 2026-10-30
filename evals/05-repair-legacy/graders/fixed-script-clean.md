---
type: llm
---

Look only at the executable code of the FINAL full fixed script in the response. Ignore the quoted original code, the explanation, and `#` comments (a comment such as `# was glare_type = ...` documenting the old API is fine; judge only what the code executes).
PASS if that final script: (1) has no `use_bloom`/`bloom_intensity`, no `use_auto_smooth`/`auto_smooth_angle`, no `scene.node_tree` or `scene.use_nodes`, no `ShaderNodeSeparateRGB`, no Principled input named exactly "Specular", and no `glare_type` attribute; (2) builds the compositor through `scene.compositing_node_group` with a Group Output instead of a Composite node; (3) contains no version-check branches or fallbacks for older Blender.
FAIL if any one of these is violated or there is no complete final script.
