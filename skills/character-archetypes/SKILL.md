---
name: character-archetypes
description: "Character archetype looks: elf, vampire, knight, assassin, mecha. Use for 'design an elf' silhouette and costume before modeling."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: world
  stage: brief
  requires: "animation, camera-cinematography, lighting, materials"
  triggers: archetype, elf, dwarf, orc, goblin, vampire, werewolf, zombie, alien, mecha, android, knight, assassin, superhero, villain, witch, wizard, cowboy, soldier
  related-skills: character-artist, creature-artist, anime-style, realistic-style, materials
---

# Character Archetypes

Use this skill to lock silhouette, materials, and proportion language for a role/race before modeling.

## Load refs for family
Fantasy ancestries · Horror undead/monsters · Sci-fi bodytypes · Role kits (knight, ninja, detective, etc.)

## Recipe

Goal: a readable role presentation in a hero shot: 85 mm lens, subject fills 70% of frame height, three-point light (key:fill about 3:1), one signature material per archetype.

1. Light with `lighting/light_rig.py` preset `studio_3pt` (hero/knight/wizard), `horror_practical` (vampire, werewolf, undead), `neon_night` (android, mecha, cyber assassin).
2. Signature material with `materials/pbr_material.py`: armor `metallic` 1.0 `roughness` 0.35; orc/goblin skin `[0.2, 0.3, 0.12]` `roughness` 0.6; android shell `coat_weight` 0.5; glowing runes via `emission_color` + `emission_strength` 3.
3. Optional toon read (anime/chibi/superhero): `stylized-style/toon_material.py` with `bands` 3, `outline` 0.01.
4. Frame with `camera-cinematography/camera_rig.py` (`lens_mm` 85, `elevation_deg` 5 for heroic low angle, `dof_fstop` 2.8), and check the silhouette with `animation/turntable.py`.
5. Proportion cheat sheet (heads tall): realistic 7.5, heroic 8-8.5, chibi 2-3, dwarf 5-6, orc 8 with wide shoulders, mecha 6-9.

```python
import runpy
skills = "<skills_dir>"  # parent folder of this skill (the plugin's skills/ directory)
target = "SM_Asset"      # object to style / dress
r = {}
r["light"] = runpy.run_path(f"{skills}/lighting/scripts/light_rig.py", init_globals={"ARGS": {"preset": "studio_3pt", "target": target}})["result"]
r["mat"] = runpy.run_path(f"{skills}/materials/scripts/pbr_material.py", init_globals={"ARGS": {"name": "MAT_KnightSteel", "base_color": [0.55, 0.56, 0.58], "metallic": 1.0, "roughness": 0.35, "objects": [target]}})["result"]
r["cam"] = runpy.run_path(f"{skills}/camera-cinematography/scripts/camera_rig.py", init_globals={"ARGS": {"target": target, "lens_mm": 85, "elevation_deg": 5, "dof_fstop": 2.8}})["result"]
r["turn"] = runpy.run_path(f"{skills}/animation/scripts/turntable.py", init_globals={"ARGS": {"target": target, "frames": 120, "set_active": False}})["result"]
result = r
```
