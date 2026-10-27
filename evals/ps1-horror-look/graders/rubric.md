---
type: llm
---

PASS if the answer gives concrete Blender settings for most of: low resolution render (e.g. 320x240) upscaled with nearest-neighbour, vertex snapping/jitter, nearest ("Closest") texture interpolation with small textures, low poly counts, fog/darkness with practical or limited lights, and a gritty post grade (dither, noise, colour reduction).
FAIL if it is generic "make it dark and spooky" advice, recommends high-poly/ray-traced realism, or relies on Blender 4.1-or-older APIs such as use_bloom or scene.node_tree.
