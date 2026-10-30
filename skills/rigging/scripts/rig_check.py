"""Read-only armature + skinning audit: deform bone count, .L/.R symmetry,
naming, vertex groups without bones, deform bones without weights, unweighted
vertices, and max influences per vertex (game engines usually cap at 4 or 8).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/rig_check.py", init_globals={"ARGS": {
        "armature": "ARM_Hero", "max_influences": 4}})["result"]

ARGS:
    armature        (str, required) armature object
    meshes          (list[str]|None) skinned meshes (default: children with an Armature modifier on it)
    max_influences  (int) default 4
"""
import json
import re
import sys

import bpy

SIDE = re.compile(r"(.*?)([._-])(L|R|l|r|Left|Right|left|right)$")
FLIP = {"L": "R", "R": "L", "l": "r", "r": "l", "Left": "Right", "Right": "Left", "left": "right", "right": "left"}


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


def main(armature, meshes=None, max_influences=4):
    arm = bpy.data.objects.get(armature)
    if arm is None or arm.type != "ARMATURE":
        raise ValueError(f"armature not found: {armature}")
    bones = arm.data.bones
    deform = [b.name for b in bones if b.use_deform]
    unpaired = []
    for b in bones:
        m = SIDE.match(b.name)
        if m:
            mirror = f"{m.group(1)}{m.group(2)}{FLIP[m.group(3)]}"
            if mirror not in bones:
                unpaired.append(b.name)
    if meshes:
        skinned = [bpy.data.objects[n] for n in meshes if n in bpy.data.objects]
    else:
        skinned = [o for o in bpy.data.objects if o.type == "MESH"
                   and any(md.type == "ARMATURE" and md.object == arm for md in o.modifiers)]
    mesh_reports = {}
    for obj in skinned:
        groups = {vg.index: vg.name for vg in obj.vertex_groups}
        weighted_groups, unweighted, over = set(), 0, 0
        for v in obj.data.vertices:
            infl = [g for g in v.groups if g.weight > 1e-4 and groups.get(g.group) in deform]
            if not infl:
                unweighted += 1
            if len(infl) > max_influences:
                over += 1
            weighted_groups.update(groups[g.group] for g in infl)
        mesh_reports[obj.name] = {
            "vertex_groups_without_bone": sorted(set(groups.values()) - set(b.name for b in bones)),
            "deform_bones_without_weights": sorted(set(deform) - weighted_groups),
            "unweighted_vertices": unweighted,
            f"vertices_over_{max_influences}_influences": over,
            "has_armature_modifier": any(md.type == "ARMATURE" for md in obj.modifiers),
        }
    issues = len(unpaired) + sum(r["unweighted_vertices"] + r[f"vertices_over_{max_influences}_influences"]
                                 for r in mesh_reports.values())
    return {"armature": arm.name, "bones": len(bones), "deform_bones": len(deform),
            "unpaired_side_bones": unpaired, "meshes": mesh_reports,
            "verdict": "PASS" if issues == 0 else "WARN",
            "naming_ok": arm.name.startswith(("ARM_", "RIG_", "SK_"))}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
