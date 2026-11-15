---
name: rigging
description: "Rigging: armatures, IK/FK, weight painting, facial rigs, drivers. Use when a rig bends wrongly, skinning breaks or bones are misnamed. Ships tested scripts. Not for keyframing (use animation)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: discipline
  stage: animate
  triggers: rig, rigging, armature, bone, IK, FK, weight paint, constraint, facial rig, driver
  related-skills: animation, character-artist, blender-modeler
---

# Rigging

Functional rigs supporting intended motion. Clean deformation. Engine-compatible bone hierarchies.

## When to Use

- Character/creature deformation rigs
- Mechanical constraint rigs
- Facial expression rigs
- Prop rigs (doors, vehicles, weapons)
- Before any animation work

## Workflow

```
Skeleton Design → Bone Placement → Hierarchy → Constraints/IK
    → Weight Painting → Deformation Test → Export Prep
```

## Armature Naming

Prefix: `ARM_[AssetName]`
Bones: `[region]_[name].L` / `.R` for sided bones (Blender's own convention, so X-axis mirror and Symmetrize work), e.g. `arm_upper.L`, `spine_01`, `jaw`. Use `.L`/`.R` everywhere: bones, shape keys, drivers. `rig_check` also understands `L_`/`R_` prefixes and `_L` suffixes in rigs you did not name.

## Bone Hierarchy

```
ARM_Character
├── root
├── spine_01 → spine_02 → spine_03
│   ├── clavicle.L → arm_upper.L → arm_lower.L → hand.L
│   └── clavicle.R → arm_upper.R → arm_lower.R → hand.R
├── leg_upper.L → leg_lower.L → foot.L → toe.L
└── leg_upper.R → leg_lower.R → foot.R → toe.R
```

## IK vs FK

| Use IK | Use FK |
|--------|--------|
| Legs (ground contact) | Spine (flexible arc) |
| Arms (hand placement) | Shoulder overlap |
| Feet planting | Finger detail |
| Mechanical reach | Whip/tail motion |

Standard: IK legs, FK spine; switchable arms for game characters.

## Constraints

| Constraint | Use |
|------------|-----|
| IK | Limb positioning |
| Copy Rotation | Mechanical sync |
| Limit Rotation | Joint ranges |
| Stretch To | Tentacles, pistons |
| Child Of | Weapon attach/detach |
| Shrinkwrap | Ground contact (use carefully) |

## Weight Painting

```
1. Automatic weights as starting point only
2. Clean weights: normalize per vertex (max 4 influences)
3. Smooth problematic areas (shoulders, hips)
4. Test extreme poses: T-pose, arms up, crouch, jaw open
5. Gradient weights at joints — no hard 1.0/0.0 at bend center
```

## Mechanical Rigs

- Empty objects as control handles
- Constraints instead of weight painting
- Hinge limits match real joint ranges
- Parent hierarchy mirrors mechanical assembly

## Facial Rigs

| Approach | Use Case |
|----------|----------|
| Bone-based | Game characters |
| Shape keys | Cinematics, dialog |
| Hybrid | Hero game characters |

Minimum game facial: jaw open, blink L/R, brow up/down.

## Drivers

- Gear rotation sync
- Auto eyelid blink
- Weapon reload mechanism
- Procedural antenna/wire motion

## MCP Integration

1. Create armature via MCP
2. Parent mesh with automatic weights via MCP
3. Query bone count and hierarchy
4. After skinning, run `scripts/rig_check.py` (structure and weights), then `scripts/stress_check.py` (poses the limbs and measures the deformation). Fix every FAIL before animating
5. Export armature with mesh via export-pipeline

## Deformation Test Poses

- T-pose / A-pose (bind pose)
- Arms fully raised
- Deep crouch
- Neck rotation extremes
- Jaw wide open (characters)

## Constraints

### MUST DO
- Rig after retopology complete
- Name bones consistently
- Limit bone influences to 4 per vertex (game engines)
- Test deformation at extremes before animation
- Document control scheme for animators

### MUST NOT DO
- Write code or snippets for Blender versions before 5.2, or add version fallbacks: this plugin targets 5.2+, and legacy branches teach users APIs that no longer exist
- Auto weights without cleanup (hero assets)
- Scale bones in bind pose
- Rig before topology validated
- Skip IK pole targets on limbs
- Mix multiple root bones without documentation

## Scripts

Tested on Blender 5.2 LTS via the official Blender MCP. Run with `execute_blender_code` (or headless,
see the `blender-mcp-workflow` skill); read the script header for every argument.
When the user will paste code into Blender themselves, give them the short `runpy` call with the absolute
path of this installed script and their ARGS. Don't inline or rewrite the script: the tested file is the point.

| Script | What it does |
|--------|--------------|
| `scripts/rig_check.py` | Read-only armature + skinning audit with a PASS/WARN/FAIL per check: zero-length bones, unapplied armature scale/rotation, `.L`/`.R` (or `L_`/`R_`) pairs and mirrored bone Z axes (3 degrees), an Armature modifier that targets this armature, non-finite weights, weight sums (0.001), unweighted vertices, influences per vertex (engines usually cap at 4 or 8). A missing or non-mesh name in `meshes` is an error. |
| `scripts/stress_check.py` | Poses the limb bones (arms raised, elbows and knees 130, crouch, forearm twist 90 and 180) on a temporary action and measures the evaluated mesh per limb: edge stretch, twist collapse, non-finite vertices. A pose the rig cannot reach (Limit Rotation, IK) is a FAIL `NOT_REACHED`, never a pass. Restores the file's pose, action and frame, saves nothing. |
| `scripts/shape_key_audit.py` | Read-only audit of shape keys with a PASS/WARN/FAIL per check: keys that do nothing, NaN or infinite coordinates, a missing relative key, drivers that target a missing object, bone or key, and `.L`/`.R` key pairs whose mirrored deltas differ by more than 1% of the mesh size (a pair that cannot be matched vertex by vertex is NOT_CHECKED). Changes nothing in the scene. |

```python
import runpy
result = runpy.run_path("<skill_dir>/scripts/rig_check.py", init_globals={"ARGS": {...}})["result"]
```

ARGS: `rig_check`: `armature`, `meshes`, `max_influences`. `stress_check`: `armature`, `meshes`, `bone_map` (`{"arm.L": {"upper": "arm_upper.L", "lower": "arm_lower.L", "twist": [...]}}`; default found by name), `poses`, `fk_switches` (custom properties to set to FK while posing). `shape_key_audit`: `meshes`. All three take `result_path` and `run_id`.

Stress thresholds: collapse ratio below 0.5 on a twist pose, or edge stretch p95 above 1.5 on any pose, is a FAIL. Bending and twisting about the bone's local X and Y axes. To pass a 180 degree twist, give the forearm twist bones (`..._twist_1`, `_2`, ...) and weight along them: one bone carrying the whole twist collapses the mesh (candy wrapper).

Headless: `blender -b f.blend --python-exit-code 1 --python <script> -- --args-file a.json` with `result_path` and `run_id` in the args. The run counts only if the exit code is 0 or 2 (2 means a FAIL verdict) and `result_path` exists with this `run_id`; any other outcome is a failed run, never a pass.

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Humanoid rig | `references/humanoid-rig.md` | Characters |
| Mechanical rig | `references/mechanical-rig.md` | Props, vehicles |
| Facial shape keys and drivers (tested recipe) | `references/facial-shape-keys-drivers.md` | Face poses driven by bones or sliders |
