---
type: llm
---

Look only at the FINAL full fixed script in the response (ignore any quoted original code or explanation).
PASS if that final script: (1) has no `use_bloom`/`bloom_intensity`, no `use_auto_smooth`/`auto_smooth_angle`, no `scene.node_tree` or `scene.use_nodes`, no `ShaderNodeSeparateRGB`, no Principled input named exactly "Specular", and no `glare_type` attribute; (2) builds the compositor through `scene.compositing_node_group` with a Group Output instead of a Composite node; (3) contains no version-check branches or fallbacks for older Blender.
FAIL if any one of these is violated or there is no complete final script.
