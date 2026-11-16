"""Check that a baked action alone reproduces the source motion, and that a cyclic action loops cleanly.

The target armature is evaluated with its bone constraints, its drivers and its NLA temporarily muted, every pose
bone reset to rest, and ONLY the baked action assigned, so a constraint or a driver can never supply the motion that
the keys lack. The source armature is evaluated as it plays. For every mapped bone and every frame the pose relative
to rest is compared (armature space, evaluated `matrix` against the bone's rest matrix, so two rigs with different
rest orientations or bone rolls can be compared):
  rotation     the armature-space rotation of (pose @ rest^-1); FAIL above ROT_MAX_DEG
  translation  the head's displacement from rest, the source one scaled by the ratio of rig heights (so proportions
               may differ); FAIL above TRANS_MAX_FRAC of the target rig height
  scale        the stretch relative to rest as a matrix in armature space (the bone's local scale carried through
               its rest orientation), so the same stretch in space matches whatever the bone roll, while an X
               stretch never matches a Z stretch. The two stretches are compared as S_target @ S_source^-1: its
               eigenvalues are the per-axis ratios along the principal axes, whatever the roll, and the metric is
               the largest |eigenvalue - 1|; FAIL above SCALE_MAX_REL
A cyclic check that cannot run (fewer than 3 frames) is NOT_CHECKED, so the overall verdict is at least WARN.
A mapped bone with no keys in the baked action is still measured (it simply stays at rest); when NO mapped bone has
keys the run is a FAIL ("measured nothing") and nothing is evaluated. The rig height is the Z extent of the rest
bones (the largest extent when flat). Armature objects are assumed to share orientation: the comparison is in
armature space.

Loop check (cyclic action, B3): the target pose at the first and the last sampled frame must match (rotation within
LOOP_ROT_DEG, location within LOOP_LOC_FRAC of the rig height) and the velocity across the seam, the step
last-1 -> last against the step first -> first+1 (a rotation vector in degrees / a displacement in rig heights),
may differ by at most VEL_REL of the larger one plus a floor (VEL_ROT_FLOOR_DEG per frame, VEL_LOC_FLOOR_FRAC of the
height per frame). A pop at the seam FAILs. With `root_motion=True` the root's translation is left out of the pose
comparison and only its velocity is checked; the other bones are compared relative to the root's travel.

State: the scene frame, the target's action (and slot, influence, blend type, NLA switch), the mute flags of its
bone constraints, drivers and NLA tracks, every pose bone's transform and both armatures' pose position are put
back in `finally`, also on failure. Nothing is saved and no datablock is created or removed.

Thresholds (the plan's values; tests/blender/test_iter16_b.py measures them and writes the numbers into its report).
Each is bracketed by boundary fixtures at 0.5x and 1.5x of the limit, so it sits 50% of the gap from both sides (the
rule asks at least 20%). Measured: a correct bake scores 0.0 on every metric.
  ROT_MAX_DEG = 2.0         boundary 1.0001 (PASS) / 3.0 (FAIL); rotation lost 40 and 80 degrees
  TRANS_MAX_FRAC = 0.01     boundary 0.005 / 0.015; piston bake without location keys 0.1 of the rig height
  SCALE_MAX_REL = 0.01      boundary 0.005 / 0.015; hydraulic (Stretch To, Y x2) bake without scale keys 0.5
                            (max |eigenvalue - 1| of the stretch ratio); an X stretch against a Z stretch 1.0; a 1.5% /
                            0.5% stretch on a bone rolled 45 degrees 0.015 (FAIL) / 0.005 (PASS)
  LOOP_ROT_DEG = 1.0        boundary 0.4973 / 1.4998; a ramp that never returns 90.0
  LOOP_LOC_FRAC = 0.005     boundary 0.0025 / 0.0075; a pop of 0.2 of the rig height 0.2
  VEL_REL = 0.25, VEL_ROT_FLOOR_DEG = 0.2, VEL_LOC_FLOOR_FRAC = 0.001
                            sine loop seam velocity difference 0.0; half-sine seam (equal poses, flipped direction)
                            15.66 degrees against an allowed 2.2. Boundary fixtures (difference of the two seam steps,
                            inside PASS / outside FAIL): rotation, steps near 10 deg/frame, 2.7 / 5.4 (allowed 3.6);
                            rotation floor, 0.15 / 0.5 (allowed 0.27); location, steps near 0.1 height/frame,
                            0.026 / 0.06 (allowed 0.035); location floor, 0.0008 / 0.002 (allowed 0.0013)

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/bake_check.py", init_globals={"ARGS": {
        "source": "ARM_Source", "target": "ARM_Game", "action": "AN_Walk_Baked"}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python bake_check.py -- --args-file a.json` with `result_path`
and `run_id` in the args. The run counts only if the exit code is 0 or 2 (2 = FAIL verdict) AND `result_path` exists
with this `run_id`.

ARGS:
    source       (str, required) armature object that plays the original motion
    target       (str, required) armature object that carries the baked action
    action       (str, required) name of the baked action
    bone_map     (dict|list|None) {"source bone": "target bone"}, or a list of names present in both rigs.
                 Default: every bone name that exists in both
    frames       (list[int]|None) [first, last]. Default: the baked action's frame range
    cyclic       (bool|None) run the loop check. Default: the action's `use_cyclic`
    root_motion  (bool) loop check only: leave the root's translation out of the pose comparison (default False)
    root_bone    (str|None) target bone treated as the root for `root_motion`. Default: the first mapped bone
                 whose parent is not mapped
    result_path  (str|None) write the result (plus run_id) here as JSON at the end of a successful run
    run_id       (str|None) copied into the result and the file
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ROT_MAX_DEG = 2.0
TRANS_MAX_FRAC = 0.01
SCALE_MAX_REL = 0.01
LOOP_ROT_DEG = 1.0
LOOP_LOC_FRAC = 0.005
VEL_REL = 0.25
VEL_ROT_FLOOR_DEG = 0.2
VEL_LOC_FLOOR_FRAC = 0.001
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


def _num(x, digits=4):
    return round(float(x), digits) if isinstance(x, (int, float)) and math.isfinite(x) else None


def _rig_height(arm):
    pts = []
    for b in arm.data.bones:
        pts += [b.head_local, b.tail_local]
    if not pts:
        return 0.0
    h = max(p.z for p in pts) - min(p.z for p in pts)
    if h < 1e-6:
        h = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
    return h


def _rot3(m):
    return m.to_3x3().normalized()


def _quat_deg(a, b):
    a, b = a.normalized(), b.normalized()
    return math.degrees(2.0 * math.acos(min(1.0, abs(a.dot(b)))))


def _rotvec_deg(q_from, q_to):
    """Rotation vector (axis * degrees, shortest way) taking q_from to q_to, armature space."""
    d = (q_to @ q_from.inverted()).normalized()
    if d.w < 0:
        d = Quaternion((-d.w, -d.x, -d.y, -d.z))
    axis, angle = d.to_axis_angle()
    return axis * math.degrees(angle)


def _keyed_bones(action, slot):
    """Names of the bones that have at least one keyframe in `action` for `slot`."""
    names = set()
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type != "KEYFRAME":
                continue
            cb = strip.channelbag(slot)
            if cb is None:
                continue
            for fc in cb.fcurves:
                dp = fc.data_path
                if dp.startswith('pose.bones["') and fc.keyframe_points:
                    names.add(dp[len('pose.bones["'):].split('"]', 1)[0])
    return names


def _pick_slot(ad, target):
    suitable = list(ad.action_suitable_slots)
    for s in suitable:
        if s.identifier == "OB" + target.name:
            return s
    return ad.action_slot or (suitable[0] if suitable else None)


class _Isolation:
    """Snapshot everything the measurement touches on the target (and the pose position of both rigs); restore it."""

    def __init__(self, scene, source, target):
        self.scene, self.source, self.target = scene, source, target
        ad = target.animation_data
        if ad is not None and ad.use_tweak_mode:
            raise ValueError(f"{target.name} is in NLA tweak mode: leave it before checking a bake")
        self.had_ad = ad is not None
        self.frame = (scene.frame_current, scene.frame_subframe)
        self.pose_pos = {o.name: o.data.pose_position for o in (source, target)}
        self.bones = {pb.name: (pb.rotation_mode, tuple(pb.location), tuple(pb.rotation_euler),
                                tuple(pb.rotation_quaternion), tuple(pb.rotation_axis_angle), tuple(pb.scale))
                      for pb in target.pose.bones}
        self.constraints = [(c, c.mute) for pb in target.pose.bones for c in pb.constraints]
        self.drivers, self.tracks = [], []
        self.ad_state = None
        for holder in (target, target.data):
            hd = holder.animation_data
            if hd is not None:
                self.drivers += [(fc, fc.mute) for fc in hd.drivers]
        if ad is not None:
            self.tracks = [(t, t.mute) for t in ad.nla_tracks]
            self.ad_state = (ad.action, ad.action_slot, ad.action_influence, ad.action_blend_type, ad.use_nla)

    def apply(self, action):
        for o in (self.source, self.target):
            o.data.pose_position = "POSE"
        for c, _m in self.constraints:
            c.mute = True
        for fc, _m in self.drivers:
            fc.mute = True
        for t, _m in self.tracks:
            t.mute = True
        for pb in self.target.pose.bones:
            pb.location = (0.0, 0.0, 0.0)
            pb.rotation_euler = (0.0, 0.0, 0.0)
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pb.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
            pb.scale = (1.0, 1.0, 1.0)
        ad = self.target.animation_data or self.target.animation_data_create()
        ad.use_nla = False
        ad.action_influence = 1.0
        ad.action_blend_type = "REPLACE"
        ad.action = action
        slot = _pick_slot(ad, self.target)
        if slot is not None:
            ad.action_slot = slot
        return ad.action_slot

    def restore(self):
        ad = self.target.animation_data
        if ad is not None and self.ad_state is not None:
            action, slot, infl, blend, use_nla = self.ad_state
            ad.action = action
            if action is not None and slot is not None:
                ad.action_slot = slot
            ad.action_influence, ad.action_blend_type, ad.use_nla = infl, blend, use_nla
        elif ad is not None and not self.had_ad:
            self.target.animation_data_clear()
        for t, m in self.tracks:
            t.mute = m
        for fc, m in self.drivers:
            fc.mute = m
        for c, m in self.constraints:
            c.mute = m
        for pb in self.target.pose.bones:
            mode, loc, eul, quat, aa, sc = self.bones[pb.name]
            pb.rotation_mode = mode
            pb.location, pb.rotation_euler, pb.rotation_quaternion = loc, eul, quat
            pb.rotation_axis_angle, pb.scale = aa, sc
        for o in (self.source, self.target):
            o.data.pose_position = self.pose_pos[o.name]
        self.scene.frame_set(self.frame[0], subframe=self.frame[1])
        bpy.context.view_layer.update()


def _stretch(rest, posed):
    """Armature-space stretch matrix: the local scale of (rest^-1 @ posed) carried through the rest orientation."""
    r3 = _rot3(rest)
    return r3 @ Matrix.Diagonal((rest.inverted() @ posed).to_scale()) @ r3.transposed()


def _stretch_off(a, b):
    """Largest per-axis ratio error between two stretch matrices: max |eigenvalue(b @ a^-1) - 1| (a: target, b: source)."""
    m = np.array([list(r) for r in a], dtype=float) @ np.linalg.inv(np.array([list(r) for r in b], dtype=float))
    return float(np.abs(np.linalg.eigvals(m) - 1.0).max())


def _loop_checks(bones, series, height, root, root_motion):
    """Per-bone seam checks on the target series {bone: {"q": [..], "d": [..]}}; returns {bone: {...}}."""
    out = {}
    root_d = series[root]["d"] if root in series else None
    for bn, s in series.items():
        q, d = s["q"], s["d"]
        if root_motion and bn != root and root_d is not None:
            d = [di - ri for di, ri in zip(d, root_d)]
        rot_pose = _quat_deg(q[0], q[-1])
        va, vb = _rotvec_deg(q[-2], q[-1]), _rotvec_deg(q[0], q[1])
        rot_vel_diff = (va - vb).length
        rot_vel_allowed = VEL_REL * max(va.length, vb.length) + VEL_ROT_FLOOR_DEG
        loc_pose = None if (root_motion and bn == root) else (d[-1] - d[0]).length / height
        la, lb = (d[-1] - d[-2]) / height, (d[1] - d[0]) / height
        loc_vel_diff = (la - lb).length
        loc_vel_allowed = VEL_REL * max(la.length, lb.length) + VEL_LOC_FLOOR_FRAC
        checks = {
            "rotation_pose": ("FAIL" if rot_pose > LOOP_ROT_DEG else "PASS", _num(rot_pose)),
            "rotation_velocity": ("FAIL" if rot_vel_diff > rot_vel_allowed else "PASS", _num(rot_vel_diff)),
            "location_velocity": ("FAIL" if loc_vel_diff > loc_vel_allowed else "PASS", _num(loc_vel_diff)),
        }
        if loc_pose is None:  # root_motion: left out on purpose (not a check that could not run)
            checks["location_pose"] = ("PASS", None)
        else:
            checks["location_pose"] = ("FAIL" if loc_pose > LOOP_LOC_FRAC else "PASS", _num(loc_pose))
        verdict = max((v for v, _x in checks.values()), key=lambda v: RANK[v])
        out[bn] = {"verdict": verdict, "root": bn == root and root_motion,
                   **{k: {"verdict": v, "value": x} for k, (v, x) in checks.items()}}
        if loc_pose is None:
            out[bn]["location_pose"]["excluded"] = True
    return out


def _worst(verdicts):
    w = "PASS"
    for v in verdicts:
        if RANK[v] > RANK[w]:
            w = v
    return "WARN" if w == "NOT_CHECKED" else w


def main(source, target, action, bone_map=None, frames=None, cyclic=None, root_motion=False, root_bone=None,
         result_path=None, run_id=None):
    scene = bpy.context.scene
    src, tgt = bpy.data.objects.get(source), bpy.data.objects.get(target)
    for name, o in ((source, src), (target, tgt)):
        if o is None or o.type != "ARMATURE":
            raise ValueError(f"armature not found: {name}")
    if src is tgt:
        raise ValueError("source and target must be different armatures")
    for o in (src, tgt):
        if o.name not in bpy.context.view_layer.objects:
            raise ValueError(f"{o.name} is not in the active view layer, so it cannot be evaluated")
    if bone_map is None:
        pairs = {n: n for n in src.data.bones.keys() if n in tgt.data.bones}
    elif isinstance(bone_map, dict):
        pairs = dict(bone_map)
    else:
        pairs = {n: n for n in bone_map}
    for s, t in pairs.items():
        if s not in src.data.bones or t not in tgt.data.bones:
            raise ValueError(f"mapped bone missing: {s!r} -> {t!r}")
    notes = []
    act = bpy.data.actions.get(action)
    result = {"source": src.name, "target": tgt.name, "action": action, "bones": {}, "loop": None,
              "thresholds": {"rotation_max_deg": ROT_MAX_DEG, "translation_max_frac": TRANS_MAX_FRAC,
                             "scale_max_rel": SCALE_MAX_REL, "loop_rotation_deg": LOOP_ROT_DEG,
                             "loop_location_frac": LOOP_LOC_FRAC, "velocity_rel": VEL_REL,
                             "velocity_rotation_floor_deg": VEL_ROT_FLOOR_DEG,
                             "velocity_location_floor_frac": VEL_LOC_FLOOR_FRAC},
              "notes": notes, "run_id": run_id}
    if act is None:
        notes.append(f"baked action {action!r} does not exist: nothing measured")
    elif not pairs:
        notes.append("no bone is mapped (no bone name exists in both rigs): nothing measured")
    else:
        _measure(scene, src, tgt, act, pairs, frames, cyclic, root_motion, root_bone, result, notes)
    verdicts = [b["verdict"] for b in result["bones"].values()]
    if result["loop"]:
        verdicts.append(result["loop"]["verdict"])
    verdict = _worst(verdicts)
    if not result["bones"]:
        verdict = "FAIL"
        if not any("nothing measured" in n or "measured nothing" in n for n in notes):
            notes.append("measured nothing: the verdict is FAIL")
    result["verdict"] = verdict
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        os.replace(tmp, result_path)
    return result


def _measure(scene, src, tgt, act, pairs, frames, cyclic, root_motion, root_bone, result, notes):
    iso = _Isolation(scene, src, tgt)
    try:
        slot = iso.apply(act)
        if slot is None:
            notes.append("the baked action has no slot usable on the target: nothing measured")
            return
        keyed = _keyed_bones(act, slot)
        mapped_keyed = {t for t in pairs.values() if t in keyed}
        if not mapped_keyed:
            notes.append("the baked action has no keys on any mapped bone: measured nothing")
            return
        if frames:
            f0, f1 = int(frames[0]), int(frames[1])
        else:
            f0, f1 = int(round(act.frame_range[0])), int(round(act.frame_range[1]))
        if f1 < f0:
            raise ValueError("frames must be [first, last] with last >= first")
        h_s, h_t = _rig_height(src), _rig_height(tgt)
        result["frames"] = [f0, f1]
        result["rig_height"] = {"source": _num(h_s), "target": _num(h_t),
                                "ratio": _num(h_t / h_s) if h_s > 1e-9 else None}
        if h_s <= 1e-9 or h_t <= 1e-9:
            notes.append("a rig has zero height: translation cannot be scaled; nothing measured")
            return
        ratio = h_t / h_s
        rest_s = {n: src.data.bones[n].matrix_local.copy() for n in pairs}
        rest_t = {n: tgt.data.bones[n].matrix_local.copy() for n in pairs.values()}
        rows = {t: {"q_s": [], "q_t": [], "d_s": [], "d_t": [], "sc_s": [], "sc_t": []} for t in pairs.values()}
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            s_ev, t_ev = src.evaluated_get(dg), tgt.evaluated_get(dg)
            for sn, tn in pairs.items():
                r = rows[tn]
                for ev, rest, bn, kq, kd, ks in ((s_ev, rest_s[sn], sn, "q_s", "d_s", "sc_s"),
                                                 (t_ev, rest_t[tn], tn, "q_t", "d_t", "sc_t")):
                    m = ev.pose.bones[bn].matrix.copy()
                    r[kq].append((_rot3(m) @ _rot3(rest).inverted()).to_quaternion())
                    r[kd].append(m.translation - rest.translation)
                    r[ks].append(_stretch(rest, m))
        tgt_to_src = {t: s for s, t in pairs.items()}
        for tn, r in rows.items():
            rot = max(_quat_deg(a, b) for a, b in zip(r["q_s"], r["q_t"]))
            trans = max((dt - ds * ratio).length for ds, dt in zip(r["d_s"], r["d_t"])) / h_t
            scale = max(_stretch_off(a, b) for a, b in zip(r["sc_t"], r["sc_s"]))
            vals = {"rotation": (rot, ROT_MAX_DEG), "translation": (trans, TRANS_MAX_FRAC),
                    "scale": (scale, SCALE_MAX_REL)}
            entry = {"source_bone": tgt_to_src[tn], "keyed": tn in keyed}
            for k, (v, lim) in vals.items():
                entry[k] = {"max": _num(v), "limit": lim,
                            "verdict": "FAIL" if (not math.isfinite(v) or v > lim) else "PASS"}
            entry["verdict"] = _worst(entry[k]["verdict"] for k in vals)
            result["bones"][tn] = entry
        do_loop = act.use_cyclic if cyclic is None else bool(cyclic)
        if do_loop:
            if f1 - f0 < 2:
                result["loop"] = {"verdict": "NOT_CHECKED", "bones": {},
                                  "note": "fewer than 3 frames: seam not checked"}
                notes.append("loop check NOT_CHECKED: the frame range is shorter than 3 frames")
                return
            names = list(rows)
            if root_bone is not None and root_bone not in rows:
                raise ValueError(f"root_bone {root_bone!r} is not a mapped target bone")
            root = root_bone or next((n for n in names if tgt.data.bones[n].parent is None
                                      or tgt.data.bones[n].parent.name not in rows), names[0])
            series = {n: {"q": rows[n]["q_t"], "d": rows[n]["d_t"]} for n in names}
            loop = _loop_checks(names, series, h_t, root, bool(root_motion))
            result["loop"] = {"verdict": _worst(b["verdict"] for b in loop.values()), "root_bone": root,
                              "root_motion": bool(root_motion), "bones": loop}
    finally:
        iso.restore()


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
