"""Pose-stress test for a skinned limb rig. Run `rig_check.py` first, then this, after skinning.

It poses the mapped limb bones through arms raised, elbows 130, knees 130, crouch, and forearm twist at 90 and 180
degrees, measures the evaluated mesh of each limb, and puts everything back. Rotations are about the bone's own local
axes: X is the bend axis, Y (the bone direction) is the twist axis. A twist is split evenly over the limb's twist
bones, so a rig with twist bones is judged on the twist it was built for.

Safety: the poses are set on a temporary action. In `finally` the original action (and slot), the scene frame, the
armature's pose position, every pose bone's transform and the IK/FK switch values are restored, and the temporary
action is removed with `bpy.data.actions.remove` (datablock removal, no file is deleted). It never saves the file.

Per (pose, limb) row the status is OK, NOT_REACHED, STRETCH, COLLAPSE, NON_FINITE, MISSING_ROLE, NO_ARMATURE_MODIFIER (no enabled Armature modifier that binds by vertex groups or envelopes),
NO_DEFORMATION (the pose was reached but the limb's vertices did not move: an inert skin) or NOT_CHECKED. Each pose is checked before measuring: the evaluated bone's rotation must be within 5 degrees of the
requested rotation (same axis, same direction, same angle), else the row is NOT_REACHED (a FAIL naming the bone,
the angle reached and how far it is from the request), so a constraint that blocks or redirects a pose (Limit
Rotation, IK) can never look like a healthy rest mesh. Measures on the evaluated mesh, per limb (the
vertices weighted to the limb's bones, and every edge touching one of them, so an unweighted ring that stays behind
stretches its edges):
  edge stretch p95   95th percentile of (posed edge length / rest edge length), all poses
  collapse ratio     minimum over cross-sections of the section's minimum width, posed / rest. The width is the
                     narrower principal spread of the section's points, projected onto the plane perpendicular to the
                     limb axis there, so a section squashed flat along one axis counts as collapsed (ratio 0).
                     Gated on the twist poses only (a bend pinches a little by nature)
  non-finite verts   any NaN or infinite evaluated vertex, all poses
  displacement ratio total vertex move of the limb (posed vs rest) divided by the move its own bones would give those
                     vertices if each followed its dominant bone rigidly; it scales with the pose and the limb size, and a
                     reached pose that moves nothing means the skin is inert (NO_DEFORMATION, FAIL)
A row whose required metric could not be measured (stretch always; collapse too on twist poses) is NOT_CHECKED, never a
PASS from the other metric. A run in which no row was measured at all is FAIL (exit 2), not a WARN.

Thresholds (calibrated on the fixtures in tests/blender/test_iter15_rig.py; each sits between the good and bad values
with a margin of at least 20% of the gap, and the test re-checks this on every run):
  COLLAPSE_MIN = 0.5     FAIL below (twist poses). Measured: good limb worst 0.9239 (twist 180 spread over 4 twist
                         bones, 45 degrees each); candy wrapper (one twist bone) 0.0000 (4.1e-08) at twist 180.
                         Gap 0.9239; the bound sits 0.4239 below good and 0.5 above bad (20% of the gap is 0.185).
  STRETCH_P95_MAX = 1.5  FAIL above (every pose). Measured: good limb worst 1.2309 (elbows 130); unweighted ring,
                         weakest failing pose 2.0820 (elbows 130; arms raised gives 10.656). Gap 0.8511; the bound
                         sits 0.2691 above good and 0.5820 below bad (20% of the gap is 0.170).
  DISPLACEMENT_RATIO_MIN = 0.3  FAIL below (every pose). Measured: good limbs smallest 0.99999999 (radius 0.15 and a
                         slender 0.02 limb, arm and leg); inert skin (zero envelopes) 0.0. Gap 1.0; the bound sits
                         0.7 below good and 0.3 above bad (20% of the gap is 0.2). It is a ratio, so it does not depend
                         on the limb's length or radius.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/stress_check.py", init_globals={"ARGS": {
        "armature": "ARM_Hero"}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python stress_check.py -- --args-file a.json` with `result_path`
and `run_id` in the args. The run counts only if the exit code is 0 or 2 (2 = FAIL verdict) AND `result_path` exists
with this `run_id`.

ARGS:
    armature     (str, required) armature object
    meshes       (list[str]|None) skinned meshes (every name must exist and be a mesh). Default: meshes with an
                 Armature modifier on this armature
    bone_map     (dict|None) {"arm.L": {"upper": "bone", "lower": "bone", "twist": ["bone", ...]}, ...}. A role with
                 several bones must be one parent-to-child chain: the angle is split along it and the chain's total is
                 checked. Limbs named
                 arm.* are posed with arm poses, leg.* with leg poses. `upper`/`lower` are a bone name (or a chain); `twist` is
                 a list (default: `lower` plus its descendants whose name contains "twist"). Default: found by name
                 roles among deform bones that a mesh is weighted to (controls are skipped; two unrelated candidates are
                 refused, naming them) (upper_arm/forearm/lower_arm, thigh/upper_leg, shin/calf/lower_leg, either side style). A limb
                 with some roles found and others missing, or a mapped bone that does not exist, FAILs
    poses        (list[str]|None) subset of arms_raised, elbows_130, knees_130, crouch, twist_90, twist_180
    fk_switches  (list[dict]|None) [{"bone": "hand_ctl.L" or "" for the armature object, "prop": "ik_fk",
                 "value": 0.0}] custom properties set while posing (to force FK) and restored afterwards
    result_path  (str|None) write the result (plus run_id) here as JSON at the end of a successful run
    run_id       (str|None) copied into the result file
"""
import json
import math
import os
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion

COLLAPSE_MIN = 0.5
STRETCH_P95_MAX = 1.5
REACH_TOL_DEG = 5.0
DISPLACEMENT_RATIO_MIN = 0.3
POSES = {  # pose -> {limb kind: [(role, local axis index, degrees)]}
    "arms_raised": {"arm": [("upper", 0, 90.0)]},
    "elbows_130": {"arm": [("lower", 0, 130.0)]},
    "knees_130": {"leg": [("lower", 0, 130.0)]},
    "crouch": {"leg": [("upper", 0, 80.0), ("lower", 0, 130.0)]},
    "twist_90": {"arm": [("twist", 1, 90.0)]},
    "twist_180": {"arm": [("twist", 1, 180.0)]},
}
TWIST_POSES = {"twist_90", "twist_180"}
RANK = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}

SIDE_WORDS = "Left|Right|left|right|LEFT|RIGHT|L|R|l|r"
SUFFIX = re.compile(rf"^(.*?)[._-]({SIDE_WORDS})$")
PREFIX = re.compile(rf"^({SIDE_WORDS})[._-](.+)$")
ROLE_RE = {
    ("arm", "upper"): re.compile(r"(upper[_.\- ]?arm|arm[_.\- ]?upper|upperarm)", re.I),
    ("arm", "lower"): re.compile(r"(fore[_.\- ]?arm|lower[_.\- ]?arm|arm[_.\- ]?lower|lowerarm)", re.I),
    ("leg", "upper"): re.compile(r"(upper[_.\- ]?leg|thigh|leg[_.\- ]?upper|upperleg)", re.I),
    ("leg", "lower"): re.compile(r"(lower[_.\- ]?leg|shin|calf|leg[_.\- ]?lower|lowerleg)", re.I),
}


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


def _side_of(name):
    """(core name, 'L'|'R') from a suffix or prefix side marker, else (name, None)."""
    for rx, ci, si in ((SUFFIX, 1, 2), (PREFIX, 2, 1)):
        m = rx.match(name)
        if m and m.group(ci):
            s = m.group(si)[0].upper()
            return m.group(ci), s
    return name, None


def _as_list(v):
    if v is None:
        return None
    return [v] if isinstance(v, str) else list(v)


def _detect_limbs(arm, weighted):
    """Limbs by name role, among deform bones that a mesh is weighted to (controls such as `forearm_ctl.L` are not
    skinned and are skipped). Returns {limb: {"upper": [..], "lower": [..]}} (maybe partial or ambiguous)."""
    found = {}
    for b in arm.data.bones:
        core, side = _side_of(b.name)
        if side is None or "twist" in core.lower() or not b.use_deform or (weighted is not None and b.name not in weighted):
            continue
        for (kind, role), rx in ROLE_RE.items():
            if rx.search(core):
                found.setdefault(f"{kind}.{side}", {}).setdefault(role, []).append(b.name)
    return found


def _twist_default(arm, lower):
    out = list(lower)
    stack = [arm.data.bones[n] for n in lower if n in arm.data.bones]
    while stack:
        b = stack.pop(0)
        for c in b.children:
            if "twist" in c.name.lower() and c.name not in out:
                out.append(c.name)
                stack.append(c)
    return out


def _chain(arm, names):
    """`names` ordered from the top of a parent-to-child chain, or None when they do not form one."""
    bones = [arm.data.bones[n] for n in names if n in arm.data.bones]
    if len(bones) != len(names):
        return None
    for top in bones:
        order = [top]
        while True:
            nxt = [b for b in bones if b.parent == order[-1]]
            if len(nxt) != 1:
                break
            order.append(nxt[0])
        if len(order) == len(bones):
            return [b.name for b in order]
    return None


def _limb_map(arm, bone_map, weighted=None):
    """Resolve to {limb: {"upper": [...], "lower": [...], "twist": [...]}} plus {limb: [problems]}. A role with
    several bones must be one parent-to-child chain (the angle is split along it); anything else is refused, naming
    the bones, because splitting a bend over unrelated bones would weaken the pose."""
    raw = {k: {r: _as_list(v) for r, v in spec.items()} for k, spec in bone_map.items()} if bone_map \
        else _detect_limbs(arm, weighted)
    limbs, problems = {}, {}
    for name, spec in raw.items():
        probs = []
        spec = dict(spec)
        for role in ("upper", "lower"):
            if not spec.get(role):
                probs.append(f"missing role '{role}': name it in bone_map")
        if not spec.get("twist") and spec.get("lower"):
            spec["twist"] = _twist_default(arm, [n for n in spec["lower"] if n in arm.data.bones])
        for role, names in spec.items():
            for n in names or []:
                if n not in arm.data.bones:
                    probs.append(f"{role} bone not in the armature: {n}")
            if names and len(names) > 1 and all(n in arm.data.bones for n in names):
                ordered = _chain(arm, names)
                if ordered is None:
                    probs.append(f"ambiguous role '{role}': {', '.join(names)} are not one parent-to-child chain; "
                                 "name the one bone to pose in bone_map")
                else:
                    spec[role] = ordered
        limbs[name] = spec
        if probs:
            problems[name] = probs
    return limbs, problems


def _snapshot(arm, scene):
    ad = arm.animation_data
    snap = {"had_ad": ad is not None, "action": ad.action if ad else None,
            "slot": getattr(ad, "action_slot", None) if ad else None, "frame": scene.frame_current, "pose_position": arm.data.pose_position, "bones": {}}
    for pb in arm.pose.bones:
        snap["bones"][pb.name] = (pb.rotation_mode, tuple(pb.rotation_euler), tuple(pb.rotation_quaternion),
                                  tuple(pb.rotation_axis_angle), tuple(pb.location), tuple(pb.scale))
    return snap


def _restore(arm, scene, snap, tmp_action, switches):
    ad = arm.animation_data
    if ad is not None:
        ad.action = snap["action"]
        if snap["action"] is not None and snap["slot"] is not None:
            ad.action_slot = snap["slot"]
        if not snap["had_ad"]:
            arm.animation_data_clear()
    if tmp_action is not None and tmp_action.name in bpy.data.actions:
        bpy.data.actions.remove(tmp_action)
    arm.data.pose_position = snap["pose_position"]
    for pb in arm.pose.bones:
        mode, eul, quat, aa, loc, sc = snap["bones"][pb.name]
        pb.rotation_mode = mode
        pb.rotation_euler, pb.rotation_quaternion = eul, quat
        pb.rotation_axis_angle, pb.location, pb.scale = aa, loc, sc
    for holder, prop, old in switches:
        holder[prop] = old
    if scene.frame_current != snap["frame"]:
        scene.frame_set(snap["frame"])
    bpy.context.view_layer.update()


def _coords(obj, dg):
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        arr = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", arr)
    finally:
        ev.to_mesh_clear()
    return arr.reshape(-1, 3)


def _quat_off(a, b):
    """Degrees of rotation between two rotations (q and -q are the same rotation)."""
    a, b = a.normalized(), b.normalized()
    return math.degrees(2.0 * math.acos(min(1.0, abs(a.dot(b)))))


def _reached(arm_eval, arm, name, axis, degrees):
    """(rotation magnitude, distance from the requested rotation), both in degrees. The evaluated bone's rotation
    relative to its rest pose, constraints included, is compared with the requested rotation about the local axis,
    so a rotation about another axis or in the opposite direction is far from it even at the same magnitude."""
    bone = arm.data.bones[name]
    pb = arm_eval.pose.bones[name]
    if bone.parent:
        rest_local = bone.parent.matrix_local.inverted() @ bone.matrix_local
        parent_pose = arm_eval.pose.bones[bone.parent.name].matrix
    else:
        rest_local, parent_pose = bone.matrix_local, Matrix.Identity(4)
    basis = rest_local.inverted() @ parent_pose.inverted() @ pb.matrix
    q = basis.to_quaternion()
    v = [0.0, 0.0, 0.0]
    v[axis] = 1.0
    return math.degrees(q.angle), _quat_off(q, Quaternion(v, math.radians(degrees)))


def _chain_off(arm_eval, arm, bones, axis, degrees):
    """Degrees between the rotation of the whole chain (parent of its first bone to its last bone) and the requested
    total rotation about the local axis."""
    first, last = arm.data.bones[bones[0]], arm.data.bones[bones[-1]]
    if first.parent:
        rest_f, pose_f = first.parent.matrix_local, arm_eval.pose.bones[first.parent.name].matrix
    else:
        rest_f, pose_f = Matrix.Identity(4), Matrix.Identity(4)
    total = (rest_f.inverted() @ last.matrix_local).inverted() @ pose_f.inverted() @ arm_eval.pose.bones[bones[-1]].matrix
    v = [0.0, 0.0, 0.0]
    v[axis] = 1.0
    return _quat_off(total.to_quaternion(), Quaternion(v, math.radians(degrees)))


def _dominant(obj, verts, bone_names):
    """Name of the highest-weighted bone group of each given vertex ('' when none)."""
    gname = {vg.index: vg.name for vg in obj.vertex_groups if vg.name in bone_names}
    out = []
    for i in verts:
        best, bw = "", 1e-4
        for g in obj.data.vertices[i].groups:
            if g.group in gname and g.weight > bw:
                best, bw = gname[g.group], g.weight
        out.append(best)
    return np.array(out, dtype=object)


def _expected_positions(rest, verts, dom, arm_eval, arm, obj):
    """Where the limb's vertices would be if each moved rigidly with its dominant bone (mesh space)."""
    t = np.array(arm.matrix_world.inverted() @ obj.matrix_world)
    p = np.c_[rest[verts], np.ones(len(verts))]
    pa = (t @ p.T).T
    exp = pa.copy()
    for bn in set(dom):
        if not bn:
            continue
        idx = dom == bn
        m = np.array(arm_eval.pose.bones[bn].matrix @ arm.data.bones[bn].matrix_local.inverted())
        exp[idx] = (m @ pa[idx].T).T
    return (np.linalg.inv(t) @ exp.T).T[:, :3]


def _limb_sets(obj, bone_names, rest, edges):
    """Vertices weighted to the limb's bones, the edges that touch them, and cross-section bins along the limb axis."""
    gidx = {vg.index for vg in obj.vertex_groups if vg.name in bone_names}
    verts = np.array([i for i, v in enumerate(obj.data.vertices)
                      if any(g.group in gidx and g.weight > 1e-4 for g in v.groups)], dtype=np.int64)
    if len(verts) < 4:
        return verts, edges[:0], []
    member = np.zeros(len(rest), dtype=bool)
    member[verts] = True
    limb_edges = edges[member[edges[:, 0]] | member[edges[:, 1]]]
    pts = rest[verts]
    centred = pts - pts.mean(axis=0)
    axis = np.linalg.eigh(centred.T @ centred)[1][:, -1]
    t = centred @ axis
    nb = max(4, min(24, len(verts) // 6))
    which = np.minimum(((t - t.min()) / max(np.ptp(t), 1e-9) * nb).astype(int), nb - 1)
    bins = [verts[which == k] for k in range(nb) if (which == k).sum() >= 4]
    return verts, limb_edges, bins


def _section_widths(co, bins):
    """Minimum width of each cross-section: the section's points are projected onto the plane perpendicular to the
    limb axis there (the line through the neighbouring section centres), and the narrower principal spread of that
    2D point cloud is the width. A circle gives r/sqrt(2); a section squashed flat along one axis gives 0."""
    centres = np.array([co[idx].mean(axis=0) for idx in bins])
    out = []
    for k, idx in enumerate(bins):
        axis = centres[min(k + 1, len(bins) - 1)] - centres[max(k - 1, 0)]
        norm = np.linalg.norm(axis)
        if norm < 1e-12:
            out.append(0.0)
            continue
        axis /= norm
        q = co[idx] - centres[k]
        q = q - np.outer(q @ axis, axis)
        s = np.linalg.svd(q, compute_uv=False)
        out.append(float(s[1] / math.sqrt(len(idx))))
    return out


def _measure(rest, posed, limb_edges, bins, verts=None, expected=None):
    finite_all = bool(np.isfinite(posed).all())
    out = {"non_finite_vertices": int((~np.isfinite(posed).all(axis=1)).sum())}
    if not finite_all:
        out.update(edge_stretch_p95=None, collapse_ratio=None)
        return out
    if len(limb_edges):
        rl = np.linalg.norm(rest[limb_edges[:, 0]] - rest[limb_edges[:, 1]], axis=1)
        pl = np.linalg.norm(posed[limb_edges[:, 0]] - posed[limb_edges[:, 1]], axis=1)
        ok = rl > 1e-9
        out["edge_stretch_p95"] = float(np.percentile(pl[ok] / rl[ok], 95)) if ok.any() else None
    else:
        out["edge_stretch_p95"] = None
    if verts is not None and expected is not None:
        # how much the mesh really moved, against how far the limb's own bones carry those vertices
        want = float(np.linalg.norm(expected - rest[verts], axis=1).sum())
        got = float(np.linalg.norm(posed[verts] - rest[verts], axis=1).sum())
        out["displacement_ratio"] = got / want if want > 1e-12 else None
    ratios = []
    if len(bins) >= 2:
        for w0, w1 in zip(_section_widths(rest, bins), _section_widths(posed, bins)):
            if w0 > 1e-9:
                ratios.append(w1 / w0)
    out["collapse_ratio"] = min(ratios) if ratios else None
    return out


def _gate(pose, m):
    """(status, verdict) for one measured row."""
    if m["non_finite_vertices"]:
        return "NON_FINITE", "FAIL"
    if m["edge_stretch_p95"] is not None and m["edge_stretch_p95"] > STRETCH_P95_MAX:
        return "STRETCH", "FAIL"
    if pose in TWIST_POSES and m["collapse_ratio"] is not None and m["collapse_ratio"] < COLLAPSE_MIN:
        return "COLLAPSE", "FAIL"
    if m.get("displacement_ratio") is not None and m["displacement_ratio"] < DISPLACEMENT_RATIO_MIN:
        return "NO_DEFORMATION", "FAIL"
    # a metric the pose needs but could not be measured is never a pass on the strength of the other one
    if m["edge_stretch_p95"] is None or (pose in TWIST_POSES and m["collapse_ratio"] is None) \
            or ("displacement_ratio" in m and m["displacement_ratio"] is None):
        return "NOT_CHECKED", "NOT_CHECKED"
    return "OK", "PASS"


def main(armature, meshes=None, bone_map=None, poses=None, fk_switches=None, result_path=None, run_id=None):
    arm = bpy.data.objects.get(armature)
    if arm is None or arm.type != "ARMATURE":
        raise ValueError(f"armature not found: {armature}")
    if meshes:
        objs = []
        for n in meshes:
            o = bpy.data.objects.get(n)
            if o is None or o.type != "MESH":
                raise ValueError(f"mesh not found (or not a mesh object): {n}")
            objs.append(o)
    else:
        objs = [o for o in bpy.data.objects if o.type == "MESH"
                and any(md.type == "ARMATURE" and md.object == arm for md in o.modifiers)]
    names = list(poses) if poses else list(POSES)
    bad = [p for p in names if p not in POSES]
    if bad:
        raise ValueError(f"unknown poses {bad}; choose from {sorted(POSES)}")
    scene = bpy.context.scene
    weighted = {vg.name for o in objs for vg in o.vertex_groups} if objs else None
    limbs, problems = _limb_map(arm, bone_map, weighted)
    rows, notes = [], []
    for name, probs in problems.items():
        rows.append({"pose": "all", "limb": name, "mesh": None, "status": "MISSING_ROLE", "verdict": "FAIL",
                     "problems": probs})
    if not limbs:
        notes.append("no limbs found by name roles: pass `bone_map`")
    if not objs:
        notes.append("no skinned meshes found: pass `meshes` or add an Armature modifier that targets this armature")
    switches = []
    for sw in fk_switches or []:
        holder = arm.pose.bones[sw["bone"]] if sw.get("bone") else arm
        switches.append((holder, sw["prop"], holder[sw["prop"]], float(sw.get("value", 0.0))))
    good = {n: s for n, s in limbs.items() if n not in problems}
    snap = _snapshot(arm, scene)
    tmp_action = None
    try:
        if good and objs:
            tmp_action = bpy.data.actions.new("_stress_check_tmp")
            ad = arm.animation_data or arm.animation_data_create()
            ad.action = tmp_action
            for holder, prop, _old, val in switches:
                holder[prop] = val
            arm.data.pose_position = "REST"
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            base = {}
            for o in objs:
                mods = [md for md in o.modifiers if md.type == "ARMATURE" and md.object == arm and md.show_viewport
                        and (md.use_vertex_groups or md.use_bone_envelopes)]
                rest = _coords(o, dg)
                if not mods:
                    base[o.name] = ("NO_ARMATURE_MODIFIER", None)
                elif len(rest) != len(o.data.vertices):
                    base[o.name] = ("NOT_CHECKED", "evaluated vertex count differs from the base mesh "
                                    "(a modifier before the Armature modifier changes topology)")
                else:
                    edges = np.empty(len(o.data.edges) * 2, dtype=np.int64)
                    o.data.edges.foreach_get("vertices", edges)
                    edges = edges.reshape(-1, 2)
                    sets = {ln: _limb_sets(o, {b for r in ("upper", "lower", "twist") for b in spec.get(r, [])}, rest, edges)
                            for ln, spec in good.items()}
                    doms = {ln: _dominant(o, sets[ln][0], {b.name for b in arm.data.bones}) for ln in good}
                    base[o.name] = ("OK", (rest, sets, doms))
            arm.data.pose_position = "POSE"
            for pose in names:
                spec = POSES[pose]
                posed_limbs, requested = [], {}
                for ln, lspec in good.items():
                    kind = ln.split(".")[0]
                    for role, axis, deg in spec.get(kind, []):
                        bones = lspec.get(role) or []
                        for bn in bones:
                            requested[bn] = (axis, deg / len(bones))
                        if bones and ln not in posed_limbs:
                            posed_limbs.append(ln)
                if not posed_limbs:
                    continue
                for pb in arm.pose.bones:
                    pb.rotation_mode = "XYZ"
                    pb.rotation_euler = (0.0, 0.0, 0.0)
                    pb.location = (0.0, 0.0, 0.0)
                    pb.scale = (1.0, 1.0, 1.0)
                for bn, (axis, deg) in requested.items():
                    e = [0.0, 0.0, 0.0]
                    e[axis] = math.radians(deg)
                    arm.pose.bones[bn].rotation_euler = e
                bpy.context.view_layer.update()
                dg = bpy.context.evaluated_depsgraph_get()
                arm_eval = arm.evaluated_get(dg)
                for ln in posed_limbs:
                    lspec = good[ln]
                    reach, blocked = [], False
                    for role, axis, deg in spec.get(ln.split(".")[0], []):
                        bones = lspec.get(role) or []
                        if len(bones) > 1:
                            total_off = _chain_off(arm_eval, arm, bones, axis, deg)
                            reach.append({"chain": bones, "axis": "XYZ"[axis], "requested_total_deg": deg,
                                          "off_requested_deg": round(total_off, 2)})
                            if total_off > REACH_TOL_DEG:
                                blocked = True
                        for bn in bones:
                            want = deg / len(bones)
                            got, off = _reached(arm_eval, arm, bn, axis, want)
                            reach.append({"bone": bn, "axis": "XYZ"[axis], "requested_deg": round(want, 2),
                                          "reached_deg": round(got, 2), "off_requested_deg": round(off, 2)})
                            if off > REACH_TOL_DEG:
                                blocked = True
                    if blocked:
                        rows.append({"pose": pose, "limb": ln, "mesh": None, "status": "NOT_REACHED",
                                     "verdict": "FAIL", "reach": reach})
                        continue
                    for o in objs:
                        state, payload = base[o.name]
                        row = {"pose": pose, "limb": ln, "mesh": o.name, "reach": reach}
                        if state != "OK":
                            row.update(status=state, verdict="FAIL" if state == "NO_ARMATURE_MODIFIER" else "NOT_CHECKED",
                                       reason=payload)
                        else:
                            rest, sets, doms = payload
                            verts, limb_edges, bins = sets[ln]
                            if len(verts) < 4:
                                row.update(status="NOT_CHECKED", verdict="NOT_CHECKED",
                                           reason="fewer than 4 vertices are weighted to this limb's bones")
                            else:
                                m = _measure(rest, _coords(o, dg), limb_edges, bins, verts,
                                         _expected_positions(rest, verts, doms[ln], arm_eval, arm, o))
                                status, verdict = _gate(pose, m)
                                row.update(m, status=status, verdict=verdict)
                        rows.append(row)
    finally:
        _restore(arm, scene, snap, tmp_action, [(h, p, old) for h, p, old, _v in switches])
    verdict = "FAIL" if not rows else "PASS"
    for r in rows:
        if RANK[r["verdict"]] > RANK[verdict]:
            verdict = r["verdict"]
    if verdict == "NOT_CHECKED":
        verdict = "WARN"
    if not any(r["status"] in ("OK", "STRETCH", "COLLAPSE", "NON_FINITE") for r in rows):
        verdict = "FAIL"
        if "measured nothing" not in notes:
            notes.append("measured nothing: no pose produced a measurement, so the verdict is FAIL")
    if not objs or not limbs:
        verdict = "FAIL"
    summary = {}
    for r in rows:
        s = summary.setdefault(r["limb"], {"verdict": "PASS", "failures": []})
        if RANK[r["verdict"]] > RANK[s["verdict"]]:
            s["verdict"] = r["verdict"]
        if r["verdict"] == "FAIL":
            s["failures"].append(f"{r['pose']}:{r['status']}")
    result = {"armature": arm.name, "limbs": limbs, "meshes": [o.name for o in objs], "rows": rows,
              "summary": summary, "thresholds": {"collapse_min": COLLAPSE_MIN, "stretch_p95_max": STRETCH_P95_MAX,
                                                 "reach_tolerance_deg": REACH_TOL_DEG, "displacement_ratio_min": DISPLACEMENT_RATIO_MIN},
              "notes": notes, "verdict": verdict}
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
