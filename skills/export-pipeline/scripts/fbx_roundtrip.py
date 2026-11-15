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

Actions. Imported actions are named `<imported armature>|<armature>|<action>`. The clips of one armature are the
actions whose every F-curve path resolves on it (what the exporter writes) plus its assigned action and NLA strip
actions, taken in export order (Blender's action order). Each expected name is matched exactly against an imported
name after dropping the two armature prefixes. The only difference allowed is a `.NNN` the importer added because
the full imported name already existed in the file before the import. So `Walk.001` exported and `Walk.002` imported
is a changed clip name and FAILs; imported actions nobody expected also FAIL. Armature dimensions are not compared
(the importer rebuilds bone lengths).
Dimensions of a skinned mesh: the exporter writes the rest shape with the other modifiers applied, so the source is
measured with its Armature modifier(s) switched off and the others evaluated; the switch is undone in `finally`.

Cleanup. Only the temporary scene and the datablocks the import created (objects, meshes, armatures, materials,
images, actions, cameras, lights, curves, collections, textures, node groups, found by session id before and after)
are removed. Selection, active object, the window's scene and the current frame are restored, also on failure.
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


def _world_dims(obj, evaluated):
    """Axis-aligned world extent [x, y, z] of a mesh object, or None when it has no vertices. `evaluated`: measure
    what the exporter writes, the mesh with modifiers applied but its Armature modifiers off (rest shape)."""
    switched = []
    if evaluated:
        for m in obj.modifiers:
            if m.type == "ARMATURE" and m.show_viewport:
                m.show_viewport = False
                switched.append(m)
        bpy.context.view_layer.update()
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
    else:
        ev, me = None, obj.data
    try:
        n = len(me.vertices)
        if not n:
            return None
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
    finally:
        if ev is not None:
            ev.to_mesh_clear()
        for m in switched:
            m.show_viewport = True
        if switched:
            bpy.context.view_layer.update()
    m = np.array([list(r) for r in obj.matrix_world], dtype=np.float64)
    w = co @ m[:3, :3].T + m[:3, 3]
    return [float(x) for x in (w.max(axis=0) - w.min(axis=0))]


def _fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                yield from bag.fcurves


def _clip_names(arm):
    """Names of the actions the exporter writes for this armature: its assigned action, its NLA strip actions and
    every action whose F-curve paths all resolve on it."""
    names = set()
    ad = arm.animation_data
    if ad:
        if ad.action:
            names.add(ad.action.name)
        for track in ad.nla_tracks:
            names.update(s.action.name for s in track.strips if s.action)
    for act in bpy.data.actions:
        curves = list(_fcurves(act))
        if not curves:
            continue
        ok = True
        for fc in curves:
            try:
                arm.path_resolve(fc.data_path)
            except (ValueError, TypeError):
                ok = False
                break
        if ok:
            names.add(act.name)
    return names


def _strip_prefixes(name, prefixes):
    for p in prefixes:
        if name.startswith(p + "|"):
            name = name[len(p) + 1:]
    return name


def _match_actions(expected, imported, imp_name, arm_name, pre_names):
    """Match expected clip names (export order) to imported action names. Exact, except a `.NNN` the importer added
    because the full imported name existed before the import. Returns (imported labels, importer_renamed, ok)."""
    stripped = [(n, _strip_prefixes(n, [imp_name, arm_name])) for n in imported]
    used, labels, renamed = set(), [], []
    ok = True
    for e in expected:
        hit = next((i for i, (n, s) in enumerate(stripped) if i not in used and s == e), None)
        if hit is None:
            hit = next((i for i, (n, s) in enumerate(stripped)
                        if i not in used and s.startswith(e) and re.fullmatch(r"\.\d{3,}", s[len(e):])
                        and SUFFIX_RE.sub("", n) in pre_names), None)
            if hit is not None:
                renamed.append(stripped[hit][0])
        if hit is None:
            ok = False
            continue
        used.add(hit)
        labels.append(e)
    extras = [s for i, (n, s) in enumerate(stripped) if i not in used]
    if extras:
        ok = False
    return labels + extras, renamed, ok


def _bones(arm):
    return {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}


def _check(status, **info):
    info["status"] = status
    return info


def _compare(orig, imp, tol, expected_clips, imported_clips, imp_name, pre_names=frozenset()):
    checks = {}
    if imp is None:
        return {"imported": _check("FAIL", reason=f"{orig.name} was exported but nothing with its id was imported")}
    checks["imported"] = _check("PASS", imported_name=imp.name)
    if imp.type != orig.type:
        checks["type"] = _check("FAIL", exported=orig.type, imported=imp.type)
        return checks
    if orig.type == "MESH":
        a = _world_dims(orig, evaluated=True)
        b = _world_dims(imp, evaluated=False)
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
            checks["actions"] = _check("PASS" if ok else "FAIL", exported=list(expected_clips), imported=got,
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
    expected = {}
    for o in targets:
        if o.type == "ARMATURE":
            names = _clip_names(o)
            expected[o.name] = [a.name for a in bpy.data.actions if a.name in names]  # export order
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
                                          bake_anim=True, global_scale=global_scale)
        if status != {"FINISHED"}:
            raise RuntimeError(f"FBX export did not finish (operator returned {status})")
        after_file = _stamp(out_path)
        if after_file is None or after_file == before_file:
            raise RuntimeError(f"export reported FINISHED but {out_path} is missing or unchanged")

        before = _snapshot()
        tmp_scene = bpy.data.scenes.new("__bap_roundtrip")
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
                imported_clips[rid] = [a.name for a in bpy.data.actions
                                       if a.session_uid not in before["actions"] and a.name.startswith(imp.name + "|")]
        out = {}
        for rid, orig in originals.items():
            imps = imported_by_id.get(rid) or [None]
            checks = _compare(orig, imps[0], tol, expected.get(orig.name, []) if orig.type == "ARMATURE" else [],
                              imported_clips.get(rid, []), imps[0].name if imps[0] else "", pre_action_names)
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
    result = {"verdict": _worst(verdicts) if verdicts else "FAIL", "run_id": run_id, "path": out_path,
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
