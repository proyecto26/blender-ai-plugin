"""Export objects to a NEW FBX file, import it back into a temporary scene, compare the copy with the originals,
then remove the copy. Verdict script: PASS, WARN or FAIL (exit code 2 on FAIL when run headless).

Compared per exported object: imported at all and of the same type; world dimensions of meshes (0.1 %, per axis,
axis-aligned world bounding box of the exported geometry); bone names and bone parents of armatures; action names
of armatures that have animation. An exported object with no imported match is a FAIL entry naming it. A check that
cannot run is NOT_CHECKED (object verdict WARN), never PASS.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/fbx_roundtrip.py", init_globals={"ARGS": {
        "objects": ["SM_Crate_01"], "out_path": "D:/out/crate_check.fbx"}})["result"]

ARGS:
    out_path      (str, required) .fbx file to write. A file that already exists is refused (ValueError, nothing
                  written, nothing changed) unless overwrite=True. The file is kept.
    objects       (list[str]|None) objects to export (default: the selected objects). Only mesh, armature and empty
                  objects are exported; others are listed under `skipped`.
    overwrite     (bool) allow replacing an existing out_path (default False)
    tol           (float) relative tolerance for dimensions (default 0.001 = 0.1 %)
    global_scale  (float) FBX exporter global scale (default 1.0); anything but 1.0 is expected to FAIL the
                  dimension check, which is how a wrongly scaled export is caught
    result_path   (str|None) write the result (plus run_id) as JSON here, atomically, on success
    run_id        (str|None) copied into the result

Identity. The import runs into the same file, so Blender renames clashes (SM_Box -> SM_Box.001) and names alone
cannot pair objects. Before the export every exported object gets a temporary custom property `bap_rt_id` (a
counter) and the exporter writes custom properties; the imported objects are the set that appeared during the
import and are matched by that id, never by name. The property is removed from the originals in `finally`. An
object that already has `bap_rt_id` is refused before anything is changed.

Actions. Imported actions are named `<imported armature>|<armature>|<take>` (all-actions takes) or
`<imported armature>|<strip>` (NLA takes). The script passes bake_anim_use_nla_strips=True and
bake_anim_use_all_actions=True and models the exporter's take rules (read from its fbx_animations):
  - NLA pass, scene-wide: one take per unmuted strip of an unmuted track of EVERY exported object with animation_data,
    named after the strip, and each take bakes every exported object. So a static armature (no animation_data)
    exported next to an animated one still gets an action for each strip take, and is expected to;
  - all-actions pass, per object: nothing for an object without animation_data or with a read-only `action` (NLA tweak
    mode); otherwise one take per action in Blender's action order that is the assigned action (with a slot) or has a
    non-empty channelbag whose F-curve paths all resolve on the object.
Per armature the expected list is the scene's NLA takes followed by its own all-actions takes; the i-th expected take
is compared with the i-th imported action of that armature (imported actions in creation order, `session_uid`, i.e.
the file's take order) after dropping the two armature prefixes. `takes` in the result is the same comparison as a
set over all armatures. The only name difference allowed is a `.NNN` the importer added or replaced because the full
imported name (`<rig>|<strip>` for NLA takes, `<rig>|<armature>|<action>` for all-actions takes) already existed in
the file before the import. So `Walk.001` exported and `Walk.002` imported is a
changed clip name and FAILs, as are missing, extra or swapped takes. Only take NAMES are compared, not their F-curves.
Not modelled: takes of non-armature objects (not compared), strip influence/blend/solo (a take is written regardless),
drivers, dupli-instanced objects. Armature dimensions are not compared (the importer rebuilds bone lengths).
Time and state: every dimension is measured at one scene-wide frame per side, so animation anywhere (the object, a
parent, a constraint) is compared at the same moment. Source: the earliest frame any exported take starts from (an
action's first key for all-actions takes, a strip's frame_start for NLA takes); imported: the earliest first key over
all actions the import created. With no takes the current frame is used. The user's frame is put back. If takes
start at different frames no single frame matches all of them: the earliest is used, so an asset whose takes begin at
different frames and move geometry differently there may not be comparable.
The geometry is the exception: the exporter freezes the evaluated mesh at the user's frame, so the object-space
vertices are taken there (animated modifiers such as an Array count included) and only the transform chain is read at
the take start; the two are then combined.
The active take must match too: each imported object is given the imported action of its source object's active
action (cleared when the source has none); the imported scene is temporary, so nothing is restored there. Every piece
of state that decides an evaluated transform at measurement time:
  - frame: matched (scene-wide, above);
  - active action: matched (above); no counterpart imported -> dimensions NOT_CHECKED, never FAIL;
  - action slot: an active action without a slot animates nothing and is treated as "no action"; imported actions
    hold a single slot, so slot choice is not applicable;
  - NLA tweak mode, and unmuted NLA tracks/strips on any exported object: the import has no NLA tracks, so
    dimensions are NOT_CHECKED; muted tracks and strips do not count (they do not evaluate);
  - constraints, drivers, animated shape-key values: not modelled (the exporter bakes the evaluated result at the
    source frame; the importer keeps the value from the user's frame), so such assets may report a false FAIL.

Dimensions: measured the way the exporter decides. If the mesh has a modifier other than Armature that is enabled
for viewport or render, the exporter evaluates the mesh (current shape key values included) and writes that as the
base geometry, so the source is evaluated the same way, after setting pose_position = 'REST' on every armature its
Armature modifiers point at (the exporter's own mechanism: anything that follows the rig, such as a bone-parented
mirror object, moves back to rest too). Otherwise the exporter writes the mesh data (the Basis) and the shape keys as shape keys, so the
source is read raw. The imported mesh is always read raw. Every pose_position is put back in `finally`.

Cleanup. Only the temporary scene and the datablocks the import created (objects, meshes, armatures, materials,
images, actions, cameras, lights, curves, collections, textures, node groups, found by session id before and after)
are removed. The temporary scene gets the source scene's unit settings (the importer scales by them). Selection, active object, the window's scene and the current frame are restored, also on failure.
The user's .blend file is never saved or opened.

Measured on Blender 5.3 (fixtures in tests/blender/test_iter16_v.py): a faithful round trip gives a relative
dimension difference below 1e-6 (tolerance 1e-3); global_scale 2 gives 0.5 (symmetric relative difference of a factor of 2). The tolerance sits far
from both.
"""
import json
import math
import os
import re
import sys

import bpy
import numpy as np

TAG = "bap_rt_id"
EXPORT_TYPES = {"MESH", "ARMATURE", "EMPTY"}
SUFFIX_RE = re.compile(r"\.\d{3,}$")
COLLECTIONS = ("objects", "meshes", "armatures", "materials", "images", "actions", "cameras", "lights", "curves",
               "collections", "textures", "node_groups")
REMOVE_ORDER = COLLECTIONS  # objects first, then the data they used
ORDER = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}


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


def _stamp(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _worst(verdicts):
    """Object/overall verdict: FAIL if any FAIL, else WARN if any WARN or NOT_CHECKED, else PASS."""
    if "FAIL" in verdicts:
        return "FAIL"
    if "WARN" in verdicts or "NOT_CHECKED" in verdicts:
        return "WARN"
    return "PASS"


def _json_safe(v):
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def _snapshot():
    return {c: {i.session_uid for i in getattr(bpy.data, c)} for c in COLLECTIONS}


def _exporter_evaluates(obj):
    """The exporter's own test (fbx_data_from_scene, use_mesh_modifiers=True, ARMATURE exported): it evaluates the
    mesh when some modifier other than an Armature modifier is enabled for viewport or render. Otherwise it writes
    the mesh data (the Basis) and the shape keys as shape keys."""
    return any(m.type != "ARMATURE" and (m.show_render or m.show_viewport) for m in obj.modifiers)


def _local_points(obj, exporter_view):
    """Object-space vertex positions (n, 3) of a mesh object at the CURRENT frame, or None when it has no vertices.
    `exporter_view`: what the exporter writes as base geometry: the evaluated mesh (current shape key values, modifiers
    applied, rigs in rest pose) when the exporter evaluates, else the raw mesh data. The imported object is read raw
    (False). The exporter freezes this geometry at the user's frame, so callers take it there."""
    backups, ev = [], None
    try:
        if exporter_view and _exporter_evaluates(obj):
            for m in obj.modifiers:  # the exporter's own mechanism: every armature the mesh's Armature modifiers
                if m.type == "ARMATURE" and m.object and m.object.type == "ARMATURE":  # point at goes to REST
                    arm = m.object.data
                    if arm.pose_position != "REST":
                        backups.append((arm, arm.pose_position))
                        arm.pose_position = "REST"
            bpy.context.view_layer.update()
            ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            me = ev.to_mesh()
        else:
            me = obj.data
        n = len(me.vertices)
        if not n:
            return None
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
    finally:
        if ev is not None:
            ev.to_mesh_clear()
        for arm, mode in backups:
            arm.pose_position = mode
        if backups:
            bpy.context.view_layer.update()
    return co


def _dims_from(co, obj):
    """World extent [x, y, z] of object-space points under the object's CURRENT world matrix, or None for no points."""
    if co is None:
        return None
    m = np.array([list(r) for r in obj.matrix_world], dtype=np.float64)
    w = co @ m[:3, :3].T + m[:3, 3]
    return [float(x) for x in (w.max(axis=0) - w.min(axis=0))]


def _world_dims(obj, exporter_view):
    """Geometry and transform at the current frame (see _local_points, _dims_from)."""
    return _dims_from(_local_points(obj, exporter_view), obj)


def _resolves(arm, fc):
    path = fc.data_path + ("[%d]" % fc.array_index if fc.array_index else "")
    try:
        arm.path_resolve(path)
    except (ValueError, TypeError):
        return False
    return True


def _action_valid_for(arm, act):
    """The exporter's rule (find_validate_action_slot): some non-empty channelbag of the action has every F-curve
    resolving on the object."""
    for layer in act.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                if bag.fcurves and all(_resolves(arm, fc) for fc in bag.fcurves):
                    return True
    return False


def _nla_takes(exported):
    """Scene-wide NLA takes: the exporter's NLA pass (bake_anim_use_nla_strips) writes one take per unmuted strip of an
    unmuted track of every exported object that has animation_data, named after the STRIP, and bakes EVERY exported
    object into each of them (force_keep), so every imported armature gets an action for each of these takes, also a
    static one. `exported` is in the exporter's object order (view layer order)."""
    takes = []
    for ob in exported:
        ad = ob.animation_data
        if not ad:
            continue
        for track in ad.nla_tracks:
            if track.mute:
                continue
            takes.extend(st.name for st in track.strips if not st.mute)
    return takes


def _expected_takes(arm, nla_takes):
    """The takes the exporter writes for this armature with the options main() passes (bake_anim_use_nla_strips and
    bake_anim_use_all_actions both True). Rules modelled from the exporter source (fbx_animations):
      - NLA pass, scene-wide (see _nla_takes): every NLA take of every exported object appears on this armature too;
      - all-actions pass, per object: nothing for an object without animation_data, nothing when its `action` is
        read-only (NLA tweak mode); otherwise one take per action in Blender's action order that is the assigned
        action (with a slot) or has a non-empty channelbag whose F-curve paths all resolve on the object.
    Returns (name, kind) pairs, kind "nla" or "action" (the two import under different names).
    Not modelled: takes of non-armature objects (not compared), strip influence/blend/solo (a take is written
    regardless), drivers, dupli-instanced objects, and the F-curves inside a take (names only are compared)."""
    takes = [(n, "nla") for n in nla_takes]
    ad = arm.animation_data
    if ad and not ad.is_property_readonly("action"):
        for act in bpy.data.actions:
            if act == ad.action:
                if ad.action_slot:
                    takes.append((act.name, "action"))
            elif _action_valid_for(arm, act):
                takes.append((act.name, "action"))
    return takes


def _strip_prefixes(name, prefixes):
    for p in prefixes:
        if name.startswith(p + "|"):
            name = name[len(p) + 1:]
    return name


def _match_actions(expected, imported, imp_name, arm_name, pre_names):
    """Pair the i-th expected clip (export order) with the i-th imported clip (creation order, see main) and compare
    names. `expected` holds (name, kind) pairs: kind "nla" takes import as `<imported rig>|<strip>`, kind "action"
    takes as `<imported rig>|<rig>|<action>`. Exact, except that the importer renames a take whose full name
    already existed before the import: it then ends in its own `.NNN` (added, or replacing the clip's own number).
    Returns (imported labels, importer_renamed, ok)."""
    labels, renamed = [], []
    ok = len(expected) == len(imported)
    for i, name in enumerate(imported):
        got = _strip_prefixes(name, [imp_name, arm_name])
        e, kind = expected[i] if i < len(expected) else (None, None)
        if e is None:
            labels.append(got)
        elif got == e:
            labels.append(e)
        elif got != e and SUFFIX_RE.sub("", got) == SUFFIX_RE.sub("", e) \
                and (f"{imp_name}|{e}" if kind == "nla" else f"{imp_name}|{arm_name}|{e}") in pre_names:
            labels.append(e)
            renamed.append(name)
        else:
            labels.append(got)
            ok = False
    return labels, renamed, ok


def _bones(arm):
    return {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}


def _check(status, **info):
    info["status"] = status
    return info


def _source_start(exported, nla_takes):
    """The one scene-wide frame the exporter's takes start from: each all-actions take is baked from its action's first
    key (`act.frame_range`), each NLA take from its strip's `frame_start`. The earliest of them over every exported
    object, or None when the export writes no takes (then nothing is animated and the current frame is used)."""
    starts = []
    for ob in exported:
        for name, kind in _expected_takes(ob, []):
            if kind == "action":
                starts.append(bpy.data.actions[name].frame_range[0])
        ad = ob.animation_data
        if ad:
            for track in ad.nla_tracks:
                if not track.mute:
                    starts.extend(st.frame_start for st in track.strips if not st.mute)
    return math.floor(min(starts)) if starts else None


def _imported_start(new_actions):
    """The matching imported frame: the earliest first key over all actions the import created, or None."""
    firsts = [a.frame_range[0] for a in new_actions]
    return math.floor(min(firsts)) if firsts else None


def _pose_state_mismatch(exported):
    """Why the evaluated transforms cannot be matched on the import, or None. NLA strips (unmuted track, unmuted strip)
    and NLA tweak mode contribute to the source's evaluated transforms, but the import has no NLA tracks."""
    for ob in exported:
        ad = ob.animation_data
        if not ad:
            continue
        if ad.use_tweak_mode:
            return f"{ob.name} is in NLA tweak mode; the import has no NLA tracks"
        if any(not t.mute and any(not st.mute for st in t.strips) for t in ad.nla_tracks):
            return f"NLA strips on {ob.name} drive the source transforms; the import has no NLA tracks"
    return None


def _set_imported_actions(originals, imported_by_id, new_actions, pre_names):
    """Give each imported object the imported action that corresponds to its source object's active action (cleared
    when the source has none), so both sides are evaluated in the same take. Returns a reason string when some
    active take has no imported counterpart (dimensions are then NOT_CHECKED), else None. Temporary data: nothing to
    restore."""
    by_name = {a.name: a for a in new_actions}
    for rid, orig in originals.items():
        imp = (imported_by_id.get(rid) or [None])[0]
        ad = orig.animation_data
        if imp is None or not ad:
            continue
        src = ad.action if ad.action and ad.action_slot else None  # no slot: nothing is animated
        if imp.animation_data is None:
            if src is None:
                continue
            imp.animation_data_create()
        if src is None:
            imp.animation_data.action = None
            continue
        full = f"{imp.name}|{orig.name}|{src.name}"
        hit = by_name.get(full)
        if hit is None and full in pre_names:  # the importer renumbered it (`Walk.001` -> `Walk.002`, `Walk` -> `Walk.001`)
            others = {f"{imp.name}|{orig.name}|{n}" for n, kind in _expected_takes(orig, []) if kind == "action"} - {full}
            hit = next((a for n, a in by_name.items()
                        if n not in others and SUFFIX_RE.sub("", n) == SUFFIX_RE.sub("", full)), None)
        if hit is None:
            return f"the active action {src.name} of {orig.name} has no imported take to evaluate"
        imp.animation_data.action = hit
        if imp.animation_data.action_slot is None and len(hit.slots):
            imp.animation_data.action_slot = hit.slots[0]
    return None


def _measure_all(scene, frame, items):
    """[(obj, local points)]: the world extent under each object's transform with `scene` at `frame` (None = leave it);
    the scene's frame is put back. The geometry is NOT re-evaluated at `frame`: the exporter froze it earlier."""
    if frame is None:
        return [_dims_from(co, o) for o, co in items]
    prev = scene.frame_current
    scene.frame_set(frame)
    try:
        return [_dims_from(co, o) for o, co in items]
    finally:
        scene.frame_set(prev)


def _compare(orig, imp, tol, expected_clips, imported_clips, imp_name, pre_names=frozenset(), dims=None):
    checks = {}
    if imp is None:
        return {"imported": _check("FAIL", reason=f"{orig.name} was exported but nothing with its id was imported")}
    checks["imported"] = _check("PASS", imported_name=imp.name)
    if imp.type != orig.type:
        checks["type"] = _check("FAIL", exported=orig.type, imported=imp.type)
        return checks
    if orig.type == "MESH":
        if isinstance(dims, dict):
            checks["dimensions"] = _check("NOT_CHECKED", reason=dims["skip"])
            return checks
        a, b = dims if dims is not None else (_world_dims(orig, True), _world_dims(imp, False))
        if a is None or b is None:
            checks["dimensions"] = _check("NOT_CHECKED", reason="a mesh with no vertices has no extent")
        else:
            rel = [abs(x - y) / max(abs(x), abs(y), 1e-9) if max(abs(x), abs(y)) > 1e-9 else 0.0
                   for x, y in zip(a, b)]
            checks["dimensions"] = _check("PASS" if max(rel) <= tol else "FAIL", exported=a, imported=b,
                                          max_relative_difference=max(rel), tolerance=tol)
    elif orig.type == "ARMATURE":
        ba, bb = _bones(orig), _bones(imp)
        missing, extra = sorted(set(ba) - set(bb)), sorted(set(bb) - set(ba))
        parents = {n: [ba[n], bb[n]] for n in ba if n in bb and ba[n] != bb[n]}
        checks["bones"] = _check("PASS" if not (missing or extra or parents) else "FAIL", count=len(ba),
                                 missing=missing, extra=extra, parent_changes=parents)
        if expected_clips or imported_clips:
            got, renamed, ok = _match_actions(expected_clips, imported_clips, imp_name, orig.name, pre_names)
            checks["actions"] = _check("PASS" if ok else "FAIL", exported=[n for n, _ in expected_clips], imported=got,
                                       importer_renamed=renamed)
    return checks


def main(out_path, objects=None, overwrite=False, tol=0.001, global_scale=1.0, result_path=None, run_id=None):
    if not str(out_path).lower().endswith(".fbx"):
        raise ValueError(f"out_path must end in .fbx, got {out_path}")
    if os.path.exists(out_path) and not overwrite:
        raise ValueError(f"{out_path} already exists; nothing was written. Pick a new name or pass overwrite=True")
    view_layer = bpy.context.view_layer
    if objects:
        missing = [n for n in objects if n not in bpy.data.objects]
        if missing:
            raise ValueError(f"objects not found: {missing}")
        picked = [bpy.data.objects[n] for n in objects]
    else:
        picked = list(bpy.context.selected_objects)
    targets = [o for o in picked if o.type in EXPORT_TYPES]
    skipped = [o.name for o in picked if o.type not in EXPORT_TYPES]
    if not targets:
        raise ValueError("nothing to export: pass objects or select mesh, armature or empty objects")
    outside = [o.name for o in targets if o.name not in view_layer.objects]
    if outside:
        raise ValueError(f"objects not in the current view layer (cannot be selected for export): {outside}")
    tagged = [o.name for o in targets if TAG in o.keys()]
    if tagged:
        raise ValueError(f"{TAG} already exists on {tagged}; remove it first, the script uses it for matching")
    if bpy.context.window is None:
        raise RuntimeError("no window to switch scenes with; run from the Blender UI or headless with a window")
    active = view_layer.objects.active
    if active and active.mode != "OBJECT":
        raise ValueError("leave edit/pose mode first (the exporter reads object data)")

    scene = bpy.context.scene
    window = bpy.context.window
    prev_sel = list(bpy.context.selected_objects)
    prev_frame = scene.frame_current
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    before_file = _stamp(out_path)
    exported_order = [o for o in view_layer.objects if o in targets]
    nla_takes = _nla_takes(exported_order)
    expected = {}
    for o in targets:
        if o.type == "ARMATURE":
            expected[o.name] = _expected_takes(o, nla_takes)
    pre_action_names = {a.name for a in bpy.data.actions}
    arm_names = {o.name: o for o in targets if o.type == "ARMATURE"}
    originals = {}
    tmp_scene = None
    before = None
    imported_by_id, imported_clips, extras = {}, {}, []
    try:
        for i, o in enumerate(targets, 1):
            o[TAG] = i
            originals[i] = o
        for o in prev_sel:
            o.select_set(False)
        for o in targets:
            o.select_set(True)
        view_layer.objects.active = targets[0]
        status = bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, use_mesh_modifiers=True,
                                          object_types=EXPORT_TYPES, add_leaf_bones=False, use_custom_props=True,
                                          bake_anim=True, bake_anim_use_nla_strips=True,
                                          bake_anim_use_all_actions=True, global_scale=global_scale)
        if status != {"FINISHED"}:
            raise RuntimeError(f"FBX export did not finish (operator returned {status})")
        after_file = _stamp(out_path)
        if after_file is None or after_file == before_file:
            raise RuntimeError(f"export reported FINISHED but {out_path} is missing or unchanged")

        before = _snapshot()
        tmp_scene = bpy.data.scenes.new("__bap_roundtrip")
        for prop in scene.unit_settings.bl_rna.properties:  # the importer scales by the scene's units
            if not prop.is_readonly and prop.identifier != "rna_type":
                setattr(tmp_scene.unit_settings, prop.identifier, getattr(scene.unit_settings, prop.identifier))
        window.scene = tmp_scene
        try:
            status = bpy.ops.import_scene.fbx(filepath=out_path)
        finally:
            window.scene = scene
        if status != {"FINISHED"}:
            raise RuntimeError(f"FBX import did not finish (operator returned {status})")
        tmp_scene.view_layers[0].update()
        for o in tmp_scene.objects:
            rid = o.get(TAG)
            if rid is None:
                extras.append(o.name)
            else:
                imported_by_id.setdefault(int(round(rid)), []).append(o)
        for rid, orig in originals.items():
            imp = (imported_by_id.get(rid) or [None])[0]
            if orig.type == "ARMATURE" and imp is not None:
                # session_uid grows with creation, so this is the order the importer made them: the file's take order
                made = [a for a in bpy.data.actions
                        if a.session_uid not in before["actions"] and a.name.startswith(imp.name + "|")]
                imported_clips[rid] = [a.name for a in sorted(made, key=lambda a: a.session_uid)]
        # Animated transforms (the object's own, a parent's, a constraint's...): ALL dimensions are measured at one
        # frame per side, the frame the exporter's takes start from (source) and the earliest first key of the imported
        # actions (temporary scene), not at whatever frame each scene sits on.
        pairs = [(rid, o, (imported_by_id.get(rid) or [None])[0]) for rid, o in originals.items()]
        pairs = [(rid, o, i) for rid, o, i in pairs if o.type == "MESH" and i is not None and i.type == "MESH"]
        new_actions = [a for a in bpy.data.actions if a.session_uid not in before["actions"]]
        skip = _pose_state_mismatch(targets)
        # Shape and transform are written at different times: the geometry is frozen at the user's frame (taken here,
        # before any frame change), the transform chain is read at the take start below.
        src_pts = [_local_points(o, True) for _, o, _ in pairs]
        imp_pts = [_local_points(i, False) for _, _, i in pairs]
        window.scene = tmp_scene
        try:
            if skip is None:
                skip = _set_imported_actions(originals, imported_by_id, new_actions, pre_action_names)
            if skip is None:
                imp_dims = _measure_all(tmp_scene, _imported_start(new_actions), [(i, c) for (_, _, i), c in zip(pairs, imp_pts)])
        finally:
            window.scene = scene
        if skip is None:
            src = _measure_all(scene, _source_start(targets, nla_takes), [(o, c) for (_, o, _), c in zip(pairs, src_pts)])
            dims = {rid: (a, b) for (rid, _, _), a, b in zip(pairs, src, imp_dims)}
        else:
            dims = {rid: {"skip": skip} for rid, _, _ in pairs}
        out = {}
        for rid, orig in originals.items():
            imps = imported_by_id.get(rid) or [None]
            checks = _compare(orig, imps[0], tol, expected.get(orig.name, []) if orig.type == "ARMATURE" else [],
                              imported_clips.get(rid, []), imps[0].name if imps[0] else "", pre_action_names, dims.get(rid))
            if len(imps) > 1:
                checks["unique_match"] = _check("FAIL", reason=f"{len(imps)} imported objects carry id {rid}")
            out[orig.name] = {"id": rid, "type": orig.type, "checks": checks,
                              "verdict": _worst([c["status"] for c in checks.values()])}
    finally:
        if before is not None:
            window.scene = scene
            _remove_created(before, tmp_scene)
        for o in targets:
            if TAG in o.keys():
                del o[TAG]
        for o in targets:
            o.select_set(False)
        for o in prev_sel:
            if o.name in bpy.data.objects:
                o.select_set(True)
        view_layer.objects.active = active
        if scene.frame_current != prev_frame:
            scene.frame_set(prev_frame)

    verdicts = [v["verdict"] for v in out.values()]
    exp_set, got_set = set(), set()
    for v in out.values():
        c = v["checks"].get("actions")
        if c:
            exp_set.update(c["exported"])
            got_set.update(c["imported"])
    result = {"verdict": _worst(verdicts) if verdicts else "FAIL", "run_id": run_id, "path": out_path,
              "takes": {"expected": sorted(exp_set), "imported": sorted(got_set)},
              "bytes": os.path.getsize(out_path), "objects": out, "skipped": skipped,
              "imported_without_id": extras}
    if not verdicts:
        result["note"] = "nothing was measured"
    result = _json_safe(result)
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, allow_nan=False)
        os.replace(tmp, result_path)
    return result


def _remove_created(before, tmp_scene):
    """Remove the temporary scene and every datablock created since `before`. Never touches older datablocks."""
    if tmp_scene is not None and tmp_scene.name in bpy.data.scenes:
        bpy.data.scenes.remove(tmp_scene)
    for c in REMOVE_ORDER:
        coll = getattr(bpy.data, c)
        for item in [i for i in coll if i.session_uid not in before[c]]:
            coll.remove(item)


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
