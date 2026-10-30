---
max_turns: 4
timeout_seconds: 180
allowed_tools: [Skill, Read]
runs: 1
tags: [routing, negative]
---

My GDScript CharacterBody2D keeps sliding after I stop pressing keys. Here's func _physics_process(delta): velocity.x = move_toward(velocity.x, 0, 10). What's wrong?
