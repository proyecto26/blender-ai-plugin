# Preparing meshes for Nanite

Nanite is Unreal's virtualized geometry system. The facts below are from Epic's Nanite page, read for this file (the page was
labelled Unreal Engine 5.8; check the page for your engine version):
https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine

Nothing here was run in Unreal. The Blender-side advice is derived from those facts and is marked as such.

## What Epic states

| Topic | Statement (paraphrased) |
|---|---|
| LODs | Level of detail is handled automatically; static meshes need no manual LOD chain. Skeletal meshes use animation LODs, not geometry LODs. |
| Authoring | Authoring content for Nanite is no different from traditional meshes. Multiple UV sets and vertex colours are supported. |
| Triangle budget | The page gives no triangle count or size limit; it says practical limits remain and should be measured for the content and hardware. |
| Materials | Opaque and Masked blend modes are supported. An unsupported material gets the default material and a warning is logged. |
| Translucency | Translucent materials are not supported on Nanite meshes, so mesh decals (which need translucent) are out too. Projected decals still work. |
| Vertex deformation | World Position Offset works but the displacement must be clamped to control cluster culling. |
| Morph targets | Not supported with Nanite. |
| Tangents | Per-vertex tangents are not stored; tangents are derived in the pixel shader, which can cause discontinuities at edges. |
| Instances | At most 16 million instances in the scene (streamed-in instances count). |
| Platform | Needs DirectX 12 with Shader Model 6 on current console and desktop platforms. |
| Ray tracing | The Fallback Mesh is used by default; lowering Fallback Relative Error keeps more of the source triangles. |
| Lightmap UVs | If you do not use baked lighting, disable Generate Lightmap UVs on import. |

## What that means in Blender (derived, not tested in Unreal)

1. **Skip the LOD chain for a Nanite static mesh.** The `lod-pipeline` skill is still needed for meshes that will not use
   Nanite (translucent, morph-target, or non-DX12 targets).
2. **Do not decimate hero geometry just for Nanite.** Keep the triangle count the shot needs and measure on the target
   hardware; Epic gives no number to aim at. The polycount budgets in `blender-mcp-workflow` still apply to meshes that
   are not Nanite.
3. **Split by material type.** Put glass, water and anything translucent on its own mesh, which will not be Nanite. Keep
   opaque and alpha-masked parts (leaves, hair cards, chain-link) on Nanite meshes.
4. **Do not export shape keys on a mesh you will turn Nanite on for.** Facial and corrective morphs belong on a separate,
   non-Nanite head mesh. See the `rigging` skill, `references/facial-shape-keys-drivers.md`.
5. **Normal-map edges.** The page says tangents are derived in the pixel shader and may cause discontinuities at edges, so
   look at hard-edged bevels in a normal-map view after import.
6. **Scatter counts.** Count instances from a Blender scatter against the 16 million limit before building a very dense
   scene; most scenes are far below it.
7. **Fallback Mesh.** Ray tracing uses it by default. If ray-traced shadows or reflections show a coarser silhouette than
   the rendered view, lower Fallback Relative Error in the Static Mesh Editor.
8. **Clean meshes anyway.** Epic's page gives no extra Nanite-specific authoring rule, so the usual ones hold: applied
   transforms, no loose or degenerate geometry, consistent normals (`validate_asset.py` in `blender-mcp-workflow`).

## Check in the editor

- Enable Nanite on the mesh; look at the Nanite visualization modes for clusters and overdraw.
- Open the material and confirm the blend mode is Opaque or Masked. If the mesh shows the default grey material, the blend mode
  is the first suspect.
- Compare triangle counts in Blender and in the editor's Nanite statistics so you know the import kept them.

Record the Nanite decision per asset (on or off, and why) in the import checklist (`unreal-checklist.md`).
