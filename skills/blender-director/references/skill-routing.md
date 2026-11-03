# Skill Routing Reference

Extended routing tables for the Blender Director.

## By Engine Target

| Engine | Export Skill | Notes |
|--------|--------------|-------|
| Unity | unity-export | GLB/GLTF modern; FBX for humanoid/legacy |
| Unreal | unreal-export | FBX; UCX collision; verify cm scale |
| Godot | godot-export | GLTF/GLB preferred |
| Generic / multi | export-pipeline | Confirm axis and scale; then engine skill if known |

## By Production Phase

| Phase | Lead Skill | Validators |
|-------|------------|------------|
| Reference analysis | blender-director + reference-image-match | reference-analysis-template |
| Genre / style / world lock | matching genre/style/world/mood skill | production brief |
| Blockout | blender-modeler / discipline skill | blender-director |
| Detail pass | discipline skill | asset-optimization |
| UV pass | uv-workflow | texture-workflow |
| Look dev | lookdev + materials | style skill, qa-review |
| Camera / shot | camera-cinematography | rendering |
| FX / sim | vfx-fx / physics-sim / cloth-sim | compositing |
| Reference compare | rendering + lighting | visual-match-checklist |
| Scene layout | scene-assembly + set-dressing | qa-review |
| Performance | asset-optimization + lod-pipeline | collision-proxy |
| Delivery | unity-export / unreal-export / godot-export / export-pipeline | qa-review + validation-checklist |

## Style + Discipline Matrix (core)

|  | Hard Surface | Prop | Vehicle | Environment | Character | Creature |
|--|-------------|------|---------|-------------|-----------|----------|
| Horror | + horror-style | + horror-style | + horror-style | + horror-style | + horror-style | + horror-style |
| PSX Horror | + psx-horror-style | + psx-horror-style | + psx-horror-style | + psx-horror-style | + psx-horror-style | + psx-horror-style |
| Lowpoly | + lowpoly-style | + lowpoly-style | + lowpoly-style | + lowpoly-style | + lowpoly-style | + lowpoly-style |
| Anime | + anime-style | + anime-style | + anime-style | + anime-style | + anime-style | + anime-style |
| Voxel | + voxel-style | + voxel-style | + voxel-style | + voxel-style | + voxel-style | + voxel-style |
| Isometric | + isometric-style | + isometric-style | + isometric-style | + isometric-style | + isometric-style | + isometric-style |
| Stylized | + stylized-style | + stylized-style | + stylized-style | + stylized-style | + stylized-style | + stylized-style |
| Realistic | + realistic-style | + realistic-style | + realistic-style | + realistic-style | + realistic-style | + realistic-style |

Add world/mood/genre packs on top (e.g. `sci-fi-punk-worlds` + `neon-retrofuturism` + `genre-shooter`).

## Pack Routers (load references inside)

| Pack | Examples covered in refs |
|------|--------------------------|
| sci-fi-punk-worlds | hard sci-fi, space, cyber/steam/diesel/atom/solar/bio/clockpunk |
| fantasy-worlds | medieval, high/dark/urban fantasy |
| historical-worlds | western, pirate, samurai, viking, ancients, victorian, military |
| apocalypse-worlds | wasteland, zombie, dystopia/utopia, alien invasion |
| biome-worlds | underwater, desert, arctic, jungle, underground, floating islands |
| indie-horror-aesthetics | Silent Hill, Fear to Fathom, Puppet Combo, corporate, cabin/hospital/forest |
| character-archetypes | fantasy races, horror bodies, sci-fi bodies, role kits |
| visual-console-eras | PS1–PS5, CRT, VHS, DOS, arcade, film grain |
| painterly-style | watercolor, oil |
| stop-motion-craft-style | claymation, paper craft |
| genre-rpg | JRPG, CRPG, ARPG, MMORPG |
| genre-shooter | FPS, TPS, BR, extraction |
| genre-strategy-sim | RTS, TBS, TD, MOBA, city/colony/life/farming sim |

## Parallel vs Sequential

**Sequential (default):** Genre/style lock → Modeling → UV → Materials → Lookdev → Export

**Never share one live session.** Two agents must not edit the same open Blender session, not even in separate
collections: both change one scene, one undo stack, one selection and one active object, so one agent's operator can act on
the other's objects, and an undo rolls back both. Collections do not isolate them.

**Parallel is allowed only like this:**
- Work with no Blender session at all: reference gathering, mood boards, shot lists, budgets, reading the engine docs.
- Separate saved copies. The owner saves copies of the file (`save_as_mainfile(copy=True)`) to new paths. Each helper agent
  opens its own copy in its own Blender process (background is fine) and works only on its stage: for example materials on
  one copy, collision proxies and LODs on another. Helpers do not touch the owner's open file.
- One owner merges. When a helper reports done, the owner appends the helper's named objects, materials or collections into
  the live file, checks for name clashes first, and runs the stage's gate on the merged result. A helper's own gate result does
  not count for the merged file.
- Only stages that touch different data run in parallel (materials and collision proxies, for example). Anything where one
  depends on the other's output stays sequential, as in the list below.

Whether this saves time has not been measured: the copy, the merge and the re-check cost time too. For a single asset, run
the stages one after another in the live session.

**Never parallel:**
- Retopology before sculpt complete
- Export before validation / qa-review
- Rigging before final topology locked
- Engine export before LOD/collision plan when required
