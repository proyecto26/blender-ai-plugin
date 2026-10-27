---
type: llm
---

PASS if the plan covers, in a sensible order: blockout, hard-surface detailing (bevels/weighted normals), UV unwrap with texel density, PBR materials or baking, a triangle-budget check against ~3k, LODs, UCX_ collision, and FBX export with Unreal-correct settings (scale/units, forward axis or +X forward, smoothing), plus a validation step before export.
FAIL if it skips validation, ignores the triangle budget, omits collision or LODs, or is mostly "click this menu" UI narration without concrete settings or code.
