# Bloober Team lane

Bloober Team is a Polish studio. This file lists what is observable about the look of four of its games, then what a Blender
scene can do with it. The first part is sourced; the second part is interpretation and is labelled so.

## What the sources say (paraphrased)

| Game | Observable | Source |
|---|---|---|
| Layers of Fear (2016) | First person. A Victorian mansion that changes around the player as they explore, used for puzzles and scares. Heavily dimmed. Built in Unity. | https://en.wikipedia.org/wiki/Layers_of_Fear |
| Observer | First person, cyberpunk Krakow in 2084. Art draws on 1980s and 1990s Eastern European architecture and Soviet-style propaganda, with Blade Runner among its influences. Hacking sequences use changing level design with compression-artefact effects. Unreal Engine 4. | https://en.wikipedia.org/wiki/Observer_(video_game) |
| Blair Witch | First person, 1996 Black Hills Forest, Maryland. Found-footage influences (REC, Paranormal Activity). The flashlight is the player's main defence, and a camcorder plays tapes that change objects in the world. Unreal Engine 4. | https://en.wikipedia.org/wiki/Blair_Witch_(video_game) |
| Silent Hill 2 (2024) | A remake of the 2001 game. A town in thick fog; the Otherworld marked by rust, wire fences and darkness. Unreal Engine 5. | https://en.wikipedia.org/wiki/Silent_Hill_2_(2024_video_game) |

Not confirmed in the sources checked, so not used here: the mechanics behind the shifting rooms (for example whether they
change only out of view), the camera style of the remake, and any rendering details beyond the engines.

## What to do in Blender (interpretation, not a claim about the games)

| Observed cue | Scene move | Skill |
|---|---|---|
| Dim, close first-person interiors | One practical light source, low ambient; eye height 1.6 m, ceilings 2.4 to 2.7 m | `lighting`, `indie-horror-aesthetics` SKILL.md |
| House that changes around the player | Build rooms from a modular kit and keep two layouts of the same room as separate collections, so a shot can switch between them | `environment-artist` -> `references/modular-kits.md` |
| Period interior (Victorian) | Period materials and props | `historical-worlds` |
| Dense cyberpunk Eastern-bloc city | Concrete block architecture, hand-lettered signage, propaganda-poster decals, neon accents | `sci-fi-punk-worlds` -> `references/cyberpunk.md`, `brutalist-mood` |
| Digital glitch spaces | A compositing pass with blocky compression artefacts and offset colour channels in the glitch shots only | `compositing` |
| Found-footage forest | Narrow flashlight cone as the only light, camcorder framing, grain | `analog-found-footage-horror`, `lighting` |
| Fog and rusted otherworld | Fog as a volume or depth fade, dark grey-white; rusted metal and wire fences | `lighting`, `materials`, and the Silent Hill recipe in `SKILL.md` |

Pick one lane per scene (see the rule in `SKILL.md`). Do not copy a game's characters, creatures or specific rooms; use the
cues above to set the mood and keep the set pieces your own.
