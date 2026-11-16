"""Garment-versus-body penetration check over the rest pose and the limb stress poses. Read-only on your scene.

For the rest pose and each stress pose it evaluates the body and the garment (modifiers, armature deformation and
any shape keys included), then counts the garment vertices that sit INSIDE the body: for each garment vertex the
closest point on the evaluated body surface is found and the vertex is inside when it lies on the back side of that
surface point's normal by more than a small depth. Run it after a cloth bake or after skinning a garment to the same
armature as the body, before you trust the garment in motion.

Safety: poses are set on a temporary action. In `finally` the original action (and slot), the scene frame, the
armature's pose position, every pose bone's transform and the IK/FK switch values are restored, and the temporary
action is removed with `bpy.data.actions.remove` (datablock removal, no file is deleted). Nothing is saved, no mesh is
edited, selection and mode are not touched.

Per row the status is OK, PENETRATION (FAIL), NOT_REACHED (FAIL), NON_FINITE (FAIL), MISSING_ROLE (FAIL) or NOT_CHECKED.
  * The body must be a CLOSED mesh whose faces are consistently wound (every directed edge used exactly once and its
    reverse used once); otherwise "inside" is undefined and every row is NOT_CHECKED. Either facing is accepted
    (the signed volume of each connected shell decides which side of that shell is outside, so shells wound in
    opposite directions are each judged correctly, and every shell must keep its facing in every posed measurement). A run with no measured row is a FAIL ("measured nothing").
  * Coverage is the share of garment vertices that had a body surface point within `search_radius`. Below 0.9 the row
    is NOT_CHECKED, never a PASS: a garment that is nowhere near the body was not tested.
  * Each pose is checked before measuring: the evaluated bone's rotation must be within 5 degrees of the requested
    rotation (same as `rigging/scripts/stress_check.py`), else the limb's row is NOT_REACHED (a FAIL), so a blocked
    pose (Limit Rotation, IK) can never look like a healthy rest result, whatever the coverage.

Thresholds, calibrated on the fixtures in tests/blender/test_iter16_d.py (body radius 0.15, length 2, diagonal about 2.0):
  PENETRATION_TOL_REL = 0.005  (of the body bounding-box diagonal) a vertex deeper than this counts as inside
                               and any such vertex FAILs the row. Measured: loose garment worst depth 0.0 of
                               the diagonal (rest and arms raised); static garment poked through by the raised
                               arm 0.0144 of the diagonal. Gap 0.0144; the bound sits 0.0050 above good and
                               0.0094 below bad (20% of the gap is 0.0029).
  COVERAGE_MIN = 0.9           below this a row is NOT_CHECKED. Measured: loose and poke fixtures coverage 1.0; a garment
                               placed 5 units away 0.0.
  REACH_TOL_DEG = 5.0          as in stress_check.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/garment_check.py", init_globals={"ARGS": {
        "garment": "Shirt", "body": "Body", "armature": "ARM_Hero"}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python garment_check.py -- --args-file a.json` with `result_path`
and `run_id` in the args. The run counts only if the exit code is 0 or 2 (2 = FAIL verdict) AND `result_path` exists
with this `run_id`.

ARGS:
    garment       (str, required) the garment mesh object
    body          (str, required) the body mesh object (closed, consistently wound)
    armature      (str, required) the armature that poses the body (and normally the garment)
    bone_map      (dict|None) {"arm.L": {"upper": "bone", "lower": "bone", "twist": ["bone", ...]}, ...}; a role with
                  several bones must be one parent-to-child chain. Limbs named arm.* get arm poses, leg.* leg poses.
                  Default: found by name roles among deform bones (upper_arm/forearm/thigh/shin and similar, either
                  side style); a limb with some roles missing, or a mapped bone that does not exist, FAILs
    poses         (list[str]|None) subset of arms_raised, elbows_130, knees_130, crouch, twist_90, twist_180
                  (the rest pose is always measured)
    fk_switches   (list[dict]|None) [{"bone": "hand_ctl.L" or "" for the armature object, "prop": "ik_fk",
                  "value": 0.0}] custom properties set while posing and restored afterwards
    search_radius (float|None) how far from a garment vertex to look for a body surface point, in scene units.
                  Default 15% of the body's bounding-box diagonal
    result_path   (str|None) write the result (plus run_id) here as JSON at the end of a successful run
    run_id        (str|None) copied into the result file
"""
import json
import math
import os
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

PENETRATION_TOL_REL = 0.005
COVERAGE_MIN = 0.9
REACH_TOL_DEG = 5.0
SEARCH_REL = 0.15
POSES = {  # pose -> {limb kind: [(role, local axis index, degrees)]}
    "arms_raised": {"arm": [("upper", 0, 90.0)]},
    "elbows_130": {"arm": [("lower", 0, 130.0)]},
    "knees_130": {"leg": [("lower", 0, 130.0)]},
    "crouch": {"leg": [("upper", 0, 80.0), ("lower", 0, 130.0)]},
    "twist_90": {"arm": [("twist", 1, 90.0)]},
    "twist_180": {"arm": [("twist", 1, 180.0)]},
}
RANK = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}
SIDE = "Left|Right|left|right|LEFT|RIGHT|L|R|l|r"
SUFFIX = re.compile(rf"^(.*?)[._-]({SIDE})$")
PREFIX = re.compile(rf"^({SIDE})[._-](.+)$")
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


def _as_list(v):
    return None if v is None else ([v] if isinstance(v, str) else list(v))


def _side_of(name):
    for rx, core_i, side_i in ((SUFFIX, 1, 2), (PREFIX, 2, 1)):
        m = rx.match(name)
        if m and m.group(core_i):
            return m.group(core_i), m.group(side_i)[0].upper()
    return name, None


def _detect_limbs(arm, weighted):
    """{limb: {"upper": [..], "lower": [..]}} by name role among deform bones; bones a mesh is weighted to win."""
    found = {}
    for b in arm.data.bones:
        core, side = _side_of(b.name)
        if side is None or "twist" in core.lower() or not b.use_deform:
            continue
        for (kind, role), rx in ROLE_RE.items():
            if rx.search(core):
                found.setdefault(f"{kind}.{side}", {}).setdefault(role, []).append(b.name)
    for spec in found.values():
        for role, names in spec.items():
            keep = [n for n in names if n in weighted]
            if keep:
                spec[role] = keep
    return found


def _chain(arm, names):
    """`names` ordered top-down when they form one parent-to-child chain, else None."""
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


def _twist_default(arm, lower):
    out, stack = list(lower), [arm.data.bones[n] for n in lower if n in arm.data.bones]
    while stack:
        for c in stack.pop(0).children:
            if "twist" in c.name.lower() and c.name not in out:
                out.append(c.name)
                stack.append(c)
    return out


def _limb_map(arm, bone_map, weighted):
    raw = ({k: {r: _as_list(v) for r, v in spec.items()} for k, spec in bone_map.items()} if bone_map
           else _detect_limbs(arm, weighted))
    limbs, problems = {}, {}
    for name, spec in raw.items():
        spec, probs = dict(spec), []
        for role in ("upper", "lower"):
            if not spec.get(role):
                probs.append(f"missing role '{role}': name it in bone_map")
        if not spec.get("twist") and spec.get("lower"):
            spec["twist"] = _twist_default(arm, [n for n in spec["lower"] if n in arm.data.bones])
        for role, names in list(spec.items()):
            for n in names or []:
                if n not in arm.data.bones:
                    probs.append(f"{role} bone not in the armature: {n}")
            if names and len(names) > 1 and all(n in arm.data.bones for n in names):
                ordered = _chain(arm, names)
                if ordered is None:
                    probs.append(f"ambiguous role '{role}': {', '.join(names)} are not one parent-to-child chain")
                else:
                    spec[role] = ordered
        limbs[name] = spec
        if probs:
            problems[name] = probs
    return limbs, problems


def _snapshot(arm, scene):
    ad = arm.animation_data
    snap = {"had_ad": ad is not None, "action": ad.action if ad else None,
            "slot": getattr(ad, "action_slot", None) if ad else None, "frame": scene.frame_current,
            "pose_position": arm.data.pose_position, "bones": {}}
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


def _quat_off(a, b):
    a, b = a.normalized(), b.normalized()
    return math.degrees(2.0 * math.acos(min(1.0, abs(a.dot(b)))))


def _axis_quat(axis, degrees):
    v = [0.0, 0.0, 0.0]
    v[axis] = 1.0
    return Quaternion(v, math.radians(degrees))


def _reached(arm_eval, arm, name, axis, degrees):
    """(rotation magnitude, distance from the requested rotation) in degrees, constraints included."""
    bone, pb = arm.data.bones[name], arm_eval.pose.bones[name]
    if bone.parent:
        rest_local = bone.parent.matrix_local.inverted() @ bone.matrix_local
        parent_pose = arm_eval.pose.bones[bone.parent.name].matrix
    else:
        rest_local, parent_pose = bone.matrix_local, Matrix.Identity(4)
    q = (rest_local.inverted() @ parent_pose.inverted() @ pb.matrix).to_quaternion()
    return math.degrees(q.angle), _quat_off(q, _axis_quat(axis, degrees))


def _chain_off(arm_eval, arm, bones, axis, degrees):
    first, last = arm.data.bones[bones[0]], arm.data.bones[bones[-1]]
    if first.parent:
        rest_f, pose_f = first.parent.matrix_local, arm_eval.pose.bones[first.parent.name].matrix
    else:
        rest_f, pose_f = Matrix.Identity(4), Matrix.Identity(4)
    total = ((rest_f.inverted() @ last.matrix_local).inverted() @ pose_f.inverted()
             @ arm_eval.pose.bones[bones[-1]].matrix)
    return _quat_off(total.to_quaternion(), _axis_quat(axis, degrees))


def _world_mesh(obj, dg):
    """(world vertex array, triangle index array, directed-edge keys, polygon count) of the evaluated mesh."""
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        mw = np.array(ev.matrix_world)
        world = (mw[:3, :3] @ co.reshape(-1, 3).T).T + mw[:3, 3]
        me.calc_loop_triangles()
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        npoly, nloop = len(me.polygons), len(me.loops)
        start = np.empty(npoly, dtype=np.int64)
        total = np.empty(npoly, dtype=np.int64)
        me.polygons.foreach_get("loop_start", start)
        me.polygons.foreach_get("loop_total", total)
        vidx = np.empty(nloop, dtype=np.int64)
        me.loops.foreach_get("vertex_index", vidx)
    finally:
        ev.to_mesh_clear()
    loop_poly = np.repeat(np.arange(npoly), total)
    nxt = np.arange(nloop) + 1
    last = np.arange(nloop) == (start + total - 1)[loop_poly]
    nxt[last] = start[loop_poly][last]
    directed = vidx * max(n, 1) + vidx[nxt]
    return world, tris.reshape(-1, 3), directed, n


def _closed_and_wound(directed, n):
    """True when every directed edge appears once and so does its reverse (closed, manifold, consistently wound)."""
    if len(directed) == 0:
        return False
    keys, counts = np.unique(directed, return_counts=True)
    if (counts != 1).any():
        return False
    a, b = keys // n, keys % n
    return bool(np.isin(b * n + a, keys).all())


def _shell_labels(tris, n):
    """Connected-shell label of every triangle (vertices joined through shared triangles)."""
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b, c in tris:
        ra, rb, rc = find(int(a)), find(int(b)), find(int(c))
        parent[rb] = ra
        parent[find(rc)] = ra
    roots = np.array([find(int(t)) for t in tris[:, 0]])
    _u, labels = np.unique(roots, return_inverse=True)
    return labels


def _shell_volumes(world, tris, labels):
    """Signed volume of every connected shell (one value per label)."""
    a, b, c = world[tris[:, 0]], world[tris[:, 1]], world[tris[:, 2]]
    per_tri = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    vol = np.zeros(int(labels.max()) + 1 if len(labels) else 0)
    np.add.at(vol, labels, per_tri)
    return vol


def _measure(garment_world, body_world, body_tris, tri_sign, tol, radius):
    """Penetration numbers of the garment vertices against the body surface."""
    out = {"garment_vertices": int(len(garment_world))}
    if not np.isfinite(garment_world).all() or not np.isfinite(body_world).all():
        out["non_finite"] = True
        return out
    tree = BVHTree.FromPolygons([Vector(v) for v in body_world], [tuple(int(i) for i in t) for t in body_tris],
                                all_triangles=True)
    covered, depths = 0, np.zeros(len(garment_world))
    for i, p in enumerate(garment_world):
        loc, nrm, idx, _dist = tree.find_nearest(Vector(p), radius)
        if loc is None:
            continue
        covered += 1
        depth = -(Vector(p) - loc).dot(nrm) * tri_sign[idx]
        depths[i] = max(0.0, depth)
    inside = depths > tol
    out.update(covered_vertices=covered, coverage=covered / len(garment_world) if len(garment_world) else 0.0,
               penetrating_vertices=int(inside.sum()), max_depth=float(depths.max()) if len(depths) else 0.0)
    out["penetrating_share"] = out["penetrating_vertices"] / len(garment_world) if len(garment_world) else 0.0
    return out


def _row_from(pose, m, diag):
    row = {"pose": pose, "limb": None, **{k: v for k, v in m.items()}}
    if m.get("non_finite"):
        row.update(status="NON_FINITE", verdict="FAIL")
    elif m["garment_vertices"] == 0 or m["coverage"] < COVERAGE_MIN:
        row.update(status="NOT_CHECKED", verdict="NOT_CHECKED",
                   reason=f"coverage {m.get('coverage', 0.0):.3f} is below {COVERAGE_MIN}: too few garment vertices "
                          "had a body surface point in range (raise search_radius or check the garment is on the body)")
    elif m["penetrating_vertices"]:
        row.update(status="PENETRATION", verdict="FAIL")
    else:
        row.update(status="OK", verdict="PASS")
    row["max_depth_rel"] = (m.get("max_depth", 0.0) / diag) if diag else None
    return row


def main(garment, body, armature, bone_map=None, poses=None, fk_switches=None, search_radius=None,
         result_path=None, run_id=None):
    arm = bpy.data.objects.get(armature)
    if arm is None or arm.type != "ARMATURE":
        raise ValueError(f"armature not found: {armature}")
    gar, bod = bpy.data.objects.get(garment), bpy.data.objects.get(body)
    for label, o, n in (("garment", gar, garment), ("body", bod, body)):
        if o is None or o.type != "MESH":
            raise ValueError(f"{label} mesh not found (or not a mesh object): {n}")
    if gar == bod:
        raise ValueError("garment and body must be different objects")
    names = list(poses) if poses else list(POSES)
    bad = [p for p in names if p not in POSES]
    if bad:
        raise ValueError(f"unknown poses {bad}; choose from {sorted(POSES)}")
    scene = bpy.context.scene
    weighted = {vg.name for o in (gar, bod) for vg in o.vertex_groups}
    limbs, problems = _limb_map(arm, bone_map, weighted)
    rows, notes = [], []
    for name, probs in problems.items():
        rows.append({"pose": "all", "limb": name, "status": "MISSING_ROLE", "verdict": "FAIL", "problems": probs})
    good = {n: s for n, s in limbs.items() if n not in problems}
    if not limbs:
        notes.append("no limbs found by name roles: pass `bone_map`")
    switches = []
    for sw in fk_switches or []:
        holder = arm.pose.bones[sw["bone"]] if sw.get("bone") else arm
        switches.append((holder, sw["prop"], holder[sw["prop"]], float(sw.get("value", 0.0))))
    snap = _snapshot(arm, scene)
    tmp_action = None
    body_info = {}
    try:
        tmp_action = bpy.data.actions.new("_garment_check_tmp")
        ad = arm.animation_data or arm.animation_data_create()
        ad.action = tmp_action
        for holder, prop, _old, val in switches:
            holder[prop] = val
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        bworld, btris, directed, nverts = _world_mesh(bod, dg)
        closed = _closed_and_wound(directed, nverts) and len(btris) > 0
        if not closed:
            rows.append({"pose": "rest", "limb": None, "status": "NOT_CHECKED", "verdict": "NOT_CHECKED",
                         "reason": "the body is not a closed, consistently wound mesh: 'inside the body' is "
                                   "undefined (fix holes, flipped faces or non-manifold edges)"})
        else:
            # Facing is decided per connected shell: a mesh may hold shells wound in opposite directions (an
            # inward-wound arm next to an outward torso), and one global sign would invert the smaller shell. Every
            # shell must also keep its facing in each posed measurement.
            labels = _shell_labels(btris, nverts)
            shell_vol = _shell_volumes(bworld, btris, labels)
            shell_sign = np.where(shell_vol > 0, 1.0, -1.0)
            tri_sign = shell_sign[labels]
            vol = float(shell_vol.sum())
            diag = float(np.linalg.norm(bworld.max(axis=0) - bworld.min(axis=0)))
            tol = PENETRATION_TOL_REL * diag
            radius = float(search_radius) if search_radius is not None else SEARCH_REL * diag
            body_info = {"body_volume": vol, "body_diagonal": diag, "penetration_tol": tol, "search_radius": radius}

            def measure(pose_name):
                dgx = bpy.context.evaluated_depsgraph_get()
                bw, bt, bd, bn = _world_mesh(bod, dgx)
                if not (_closed_and_wound(bd, bn) and len(bt) > 0 and np.isfinite(bw).all()
                        and bn == nverts and len(bt) == len(btris)
                        and (_shell_volumes(bw, bt, labels) * shell_sign > 0).all()):
                    return {"pose": pose_name, "limb": None, "status": "NOT_CHECKED", "verdict": "NOT_CHECKED",
                            "reason": "the evaluated body is not a closed, consistently wound mesh (or its facing "
                                      "flipped, in some shell) in this pose, so 'inside the body' is undefined here"}
                gw, _gt, _gd, _gn = _world_mesh(gar, dgx)
                return _row_from(pose_name, _measure(gw, bw, bt, tri_sign, tol, radius), diag)

            rows.append(measure("rest"))
            arm.data.pose_position = "POSE"
            for pose in names:
                spec = POSES[pose]
                posed_limbs, requested = [], {}
                for ln, lspec in good.items():
                    for role, axis, deg in spec.get(ln.split(".")[0], []):
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
                arm_eval = arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
                blocked_any = False
                for ln in posed_limbs:
                    lspec, reach, blocked = good[ln], [], False
                    for role, axis, deg in spec.get(ln.split(".")[0], []):
                        bones = lspec.get(role) or []
                        if len(bones) > 1:
                            off = _chain_off(arm_eval, arm, bones, axis, deg)
                            reach.append({"chain": bones, "axis": "XYZ"[axis], "requested_total_deg": deg,
                                          "off_requested_deg": round(off, 2)})
                            blocked = blocked or off > REACH_TOL_DEG
                        for bn in bones:
                            want = deg / len(bones)
                            got, off = _reached(arm_eval, arm, bn, axis, want)
                            reach.append({"bone": bn, "axis": "XYZ"[axis], "requested_deg": round(want, 2),
                                          "reached_deg": round(got, 2), "off_requested_deg": round(off, 2)})
                            blocked = blocked or off > REACH_TOL_DEG
                    if blocked:
                        blocked_any = True
                        rows.append({"pose": pose, "limb": ln, "status": "NOT_REACHED", "verdict": "FAIL",
                                     "reach": reach})
                if not blocked_any:
                    rows.append(measure(pose))
    finally:
        _restore(arm, scene, snap, tmp_action, [(h, p, old) for h, p, old, _v in switches])
    verdict = "PASS" if rows else "FAIL"
    for r in rows:
        if RANK[r["verdict"]] > RANK[verdict]:
            verdict = r["verdict"]
    if verdict == "NOT_CHECKED":
        verdict = "WARN"
    if not any(r["status"] in ("OK", "PENETRATION", "NON_FINITE") for r in rows):
        verdict = "FAIL"
        notes.append("measured nothing: no pose produced a measurement, so the verdict is FAIL")
    if not limbs:
        verdict = "FAIL"
    result = {"armature": arm.name, "garment": gar.name, "body": bod.name, "limbs": good, "rows": rows,
              "body_info": body_info,
              "thresholds": {"penetration_tol_rel": PENETRATION_TOL_REL, "coverage_min": COVERAGE_MIN,
                             "reach_tolerance_deg": REACH_TOL_DEG, "search_rel": SEARCH_REL},
              "notes": notes, "verdict": verdict}
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**result, "run_id": run_id}, fh, indent=2)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS")
if ARGS is None:
    ARGS = _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
