"""Read-only armature + skinning audit. Run it after skinning, then run `stress_check.py`.

Per-check verdicts are PASS, WARN, FAIL or NOT_CHECKED. A mesh is FAIL if any check FAILs, else WARN if any check
WARNs or is NOT_CHECKED, else PASS; the overall verdict is the worst mesh/armature check. Measuring nothing is FAIL.

Checks on the armature: `zero_length_bones` (FAIL: shorter than 0.1 mm), `armature_transform` (WARN: unapplied scale or rotation, which
breaks exports and constraints), `side_pairs` (WARN: a bone named for one side with no partner; prefixes `L_`/`R_`
and `Left_`, and suffixes `.L`/`_L`/`-L`/`.Left` are all accepted), `mirrored_z_axes` (FAIL: a position-mirrored pair
whose bone Z axes are more than 3 degrees apart once mirrored; pairs that are not position-mirrored are listed as
`asymmetric_pairs` and never fail), `naming` (WARN).
Checks per skinned mesh: `armature_modifier` (FAIL: needs an enabled Armature modifier whose object is THIS armature),
`non_finite_weights` (FAIL), `weight_sums` (FAIL: sum over deform groups off from 1 by more than 0.001 on any
weighted vertex), `unweighted_vertices` (WARN), `influences` (WARN: more than `max_influences`),
`vertex_groups_without_bone` (WARN), `deform_bones_without_weights` (WARN).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/rig_check.py", init_globals={"ARGS": {
        "armature": "ARM_Hero", "max_influences": 4}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python rig_check.py -- --args-file a.json` with `result_path` and
`run_id` in the args. The run counts only if the exit code is 0 or 2 (2 = FAIL verdict) AND `result_path` exists with
this `run_id`.

ARGS:
    armature        (str, required) armature object
    meshes          (list[str]|None) skinned meshes. Every name must exist and be a mesh (else an error). Default:
                    meshes that have an Armature modifier on this armature
    max_influences  (int) default 4
    result_path     (str|None) write the result (plus run_id) here as JSON at the end of a successful run
    run_id          (str|None) copied into the result file
"""
import json
import math
import os
import re
import sys

import bpy
from mathutils import Vector

SIDE_WORDS = "Left|Right|left|right|LEFT|RIGHT|L|R|l|r"
SUFFIX = re.compile(rf"^(.*?)([._-])({SIDE_WORDS})$")
PREFIX = re.compile(rf"^({SIDE_WORDS})([._-])(.+)$")
FLIP = {"L": "R", "R": "L", "l": "r", "r": "l", "Left": "Right", "Right": "Left", "left": "right", "right": "left",
        "LEFT": "RIGHT", "RIGHT": "LEFT"}
Z_AXIS_TOL_DEG = 3.0
WEIGHT_SUM_TOL = 0.001
RANK = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}


def _cli_args():
    """ARGS after `--`: one JSON object, or `--args-file <path.json>` (quoting-proof on every shell)."""
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not raw:
        return {}
    if raw[0] == "--args-file":
        with open(raw[1], encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"ARGS after '--' must be one JSON object, got {raw[0]!r}; "
                         "cmd/PowerShell mangle JSON quotes, so pass --args-file <path.json> instead") from exc


def mirror_name(name):
    """The other side's name for `name`, accepting suffix (`arm.L`, `arm_L`) and prefix (`L_arm`) styles, else None."""
    m = SUFFIX.match(name)
    if m and m.group(1):
        return f"{m.group(1)}{m.group(2)}{FLIP[m.group(3)]}"
    m = PREFIX.match(name)
    if m:
        return f"{FLIP[m.group(1)]}{m.group(2)}{m.group(3)}"
    return None


def _check(verdict, **detail):
    return {"verdict": verdict, **detail}


def _worst(checks):
    verdicts = [c["verdict"] for c in checks.values()]
    if not verdicts:
        return "FAIL"
    worst = max(verdicts, key=lambda v: RANK[v])
    return worst if worst != "NOT_CHECKED" else "WARN"


def _armature_checks(arm, max_influences):
    bones = arm.data.bones
    checks = {}
    zero = sorted(b.name for b in bones if b.length < 1e-4)
    checks["zero_length_bones"] = _check("FAIL" if zero else "PASS", bones=zero)
    scale, rot = tuple(arm.scale), tuple(arm.rotation_euler)
    bad_scale = any(abs(s - 1.0) > 1e-4 for s in scale)
    bad_rot = arm.rotation_mode == "QUATERNION" and (abs(arm.rotation_quaternion.w - 1.0) > 1e-5) or \
        (arm.rotation_mode not in ("QUATERNION", "AXIS_ANGLE") and any(abs(r) > 1e-5 for r in rot))
    checks["armature_transform"] = _check("WARN" if bad_scale or bad_rot else "PASS", scale=[round(s, 5) for s in scale],
                                          rotation_euler=[round(r, 5) for r in rot],
                                          fix="apply scale and rotation (Ctrl+A) on the armature and its meshes")
    unpaired, pairs = [], []
    for b in bones:
        other = mirror_name(b.name)
        if other is None:
            continue
        if other not in bones:
            unpaired.append(b.name)
        elif b.name < other:
            pairs.append((b, bones[other]))
    checks["side_pairs"] = _check("WARN" if unpaired else "PASS", unpaired_side_bones=sorted(unpaired))
    bad_z, asym = [], []
    for a, b in pairs:
        ha, hb = a.head_local, b.head_local
        tol = 1e-3 + 0.01 * max(a.length, b.length)
        mirrored_head = (-ha.x - hb.x) ** 2 + (ha.y - hb.y) ** 2 + (ha.z - hb.z) ** 2
        ta, tb = a.tail_local, b.tail_local
        mirrored_tail = (-ta.x - tb.x) ** 2 + (ta.y - tb.y) ** 2 + (ta.z - tb.z) ** 2
        if math.sqrt(mirrored_head) > tol or math.sqrt(mirrored_tail) > tol:
            asym.append([a.name, b.name])
            continue
        za = a.matrix_local.col[2].xyz
        zb = b.matrix_local.col[2].xyz
        angle = math.degrees(Vector((-za.x, za.y, za.z)).angle(zb, 0.0))
        if angle > Z_AXIS_TOL_DEG:
            bad_z.append({"pair": [a.name, b.name], "degrees_apart": round(angle, 2)})
    checks["mirrored_z_axes"] = _check("FAIL" if bad_z else "PASS", mismatched=bad_z, asymmetric_pairs=asym,
                                       tolerance_deg=Z_AXIS_TOL_DEG)
    checks["naming"] = _check("PASS" if arm.name.startswith(("ARM_", "RIG_", "SK_")) else "WARN",
                              expected="ARM_, RIG_ or SK_ prefix")
    return checks


def _mesh_checks(obj, arm, max_influences):
    bones = arm.data.bones
    deform = {b.name for b in bones if b.use_deform}
    groups = {vg.index: vg.name for vg in obj.vertex_groups}
    mods = [md for md in obj.modifiers if md.type == "ARMATURE" and md.object == arm]
    enabled = [md for md in mods if md.show_viewport]
    unweighted = over = nonfinite = bad_sum = 0
    weighted_groups = set()
    worst_sum = 0.0
    for v in obj.data.vertices:
        total, count = 0.0, 0
        for g in v.groups:
            w = g.weight
            if not math.isfinite(w):
                nonfinite += 1
                continue
            if groups.get(g.group) in deform:
                total += w
                if w > 1e-4:
                    count += 1
                    weighted_groups.add(groups[g.group])
        if count == 0:
            unweighted += 1
        else:
            if abs(total - 1.0) > WEIGHT_SUM_TOL:
                bad_sum += 1
                worst_sum = max(worst_sum, abs(total - 1.0))
            if count > max_influences:
                over += 1
    no_bone = sorted(set(groups.values()) - {b.name for b in bones})
    checks = {
        "armature_modifier": _check("PASS" if enabled else "FAIL", modifiers_targeting_this_armature=len(mods),
                                    enabled=len(enabled)),
        "non_finite_weights": _check("FAIL" if nonfinite else "PASS", count=nonfinite),
        "weight_sums": _check("FAIL" if bad_sum else "PASS", vertices_off=bad_sum,
                              worst_deviation=round(worst_sum, 5), tolerance=WEIGHT_SUM_TOL),
        "unweighted_vertices": _check("WARN" if unweighted else "PASS", count=unweighted),
        "influences": _check("WARN" if over else "PASS", vertices_over=over, max_influences=max_influences),
        "vertex_groups_without_bone": _check("WARN" if no_bone else "PASS", groups=no_bone),
        "deform_bones_without_weights": _check("WARN" if deform - weighted_groups else "PASS",
                                               bones=sorted(deform - weighted_groups)),
    }
    return checks


def main(armature, meshes=None, max_influences=4, result_path=None, run_id=None):
    arm = bpy.data.objects.get(armature)
    if arm is None or arm.type != "ARMATURE":
        raise ValueError(f"armature not found: {armature}")
    if meshes:
        skinned = []
        for n in meshes:
            o = bpy.data.objects.get(n)
            if o is None or o.type != "MESH":
                raise ValueError(f"mesh not found (or not a mesh object): {n}")
            skinned.append(o)
    else:
        skinned = [o for o in bpy.data.objects if o.type == "MESH"
                   and any(md.type == "ARMATURE" and md.object == arm for md in o.modifiers)]
    bones = arm.data.bones
    arm_checks = _armature_checks(arm, max_influences)
    mesh_reports, notes = {}, []
    for obj in skinned:
        checks = _mesh_checks(obj, arm, max_influences)
        mesh_reports[obj.name] = {"verdict": _worst(checks), "checks": checks}
    if not skinned:
        notes.append("no skinned meshes found: nothing was measured on the skinning, so the verdict is FAIL; "
                     "pass `meshes` or add an Armature modifier that targets this armature")
    overall = _worst(arm_checks)
    if not skinned:
        overall = "FAIL"
    for rep in mesh_reports.values():
        if RANK[rep["verdict"]] > RANK[overall]:
            overall = rep["verdict"]
    side = arm_checks["side_pairs"]
    result = {"armature": arm.name, "bones": len(bones), "deform_bones": sum(1 for b in bones if b.use_deform),
              "unpaired_side_bones": side["unpaired_side_bones"], "checks": arm_checks, "meshes": mesh_reports,
              "notes": notes, "verdict": overall, "naming_ok": arm_checks["naming"]["verdict"] == "PASS"}
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**result, "run_id": run_id}, fh, indent=2)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
