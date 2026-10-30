"""Disposable working copies for destructive steps (apply transforms/modifiers, join, boolean apply,
remesh, decimate). The originals are never modified, so every step is recoverable.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/work_copy.py",
                            init_globals={"ARGS": {"action": "begin", "objects": ["SM_Crate"]}})["result"]

Flow: begin -> edit the copies (names are returned; e.g. fix_asset.py on "SM_Crate__work") -> check ->
accept or revert. Only one pending work set exists at a time (state lives in the scene custom
property "work_copy").

ARGS:
    action     (str, required) "begin" | "accept" | "revert" | "status"
    objects    (list[str]) begin only: objects to copy. Each copy is a full copy (object + its own data
               copy), named "<name>__work", linked into the "__Work" collection and re-parented /
               re-targeted (parent, modifier and constraint targets) to the other copies in the set.
    materials  (bool) begin only: also copy the materials in each slot (default False; use it when the
               step edits materials). Copied materials keep Blender's ".001" names.

accept:  every user of an original (children's parent, modifier/constraint targets, collection links,
         scene.camera ...) is moved onto its working copy with ID remap (`user_remap`); children outside
         the set keep their world transform (parent inverse is adjusted), and checkpoint originals keep
         their own parent / modifier / constraint links; the untouched
         original is linked into the excluded "__Checkpoint" collection and renamed "<name>__prev";
         the accepted copy (and its mesh data) takes the original name. "__Checkpoint" is never
         cleared by this script.
revert:  removes only the working copies and the datablocks they created (data and materials that no
         other object uses). Originals are untouched.
begin while a work set is pending is an error: accept or revert first.
"""
import json
import sys

import bpy

KEY = "work_copy"
WORK = "__Work"
CHECKPOINT = "__Checkpoint"
SUFFIX_WORK = "__work"
SUFFIX_PREV = "__prev"


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


def _state(scene):
    raw = scene.get(KEY)
    return json.loads(raw) if raw else None


def _layer_collection(layer_coll, name):
    if layer_coll.name == name:
        return layer_coll
    for child in layer_coll.children:
        found = _layer_collection(child, name)
        if found:
            return found
    return None


def _ensure_collection(scene, name, exclude=False):
    col = bpy.data.collections.get(name)
    created = col is None
    if created:
        col = bpy.data.collections.new(name)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    if exclude:
        for vl in scene.view_layers:
            lc = _layer_collection(vl.layer_collection, name)
            if lc:
                lc.exclude = True
    return col, created


def _retarget(new_obj, mapping):
    """Point parent, modifier and constraint object references at the matching working copies."""
    if new_obj.parent and new_obj.parent.name in mapping:
        new_obj.parent = mapping[new_obj.parent.name]
    for owner in list(new_obj.modifiers) + list(new_obj.constraints):
        for prop in owner.bl_rna.properties:
            if prop.type == "POINTER" and prop.fixed_type and prop.fixed_type.identifier == "Object" \
                    and not prop.is_readonly:
                target = getattr(owner, prop.identifier)
                if target is not None and target.name in mapping:
                    setattr(owner, prop.identifier, mapping[target.name])


def _begin(scene, objects, materials):
    if _state(scene):
        raise ValueError("a work set is already pending: call action 'accept' or 'revert' first")
    if not objects:
        raise ValueError("objects (list of object names) is required for begin")
    missing = [n for n in objects if n not in bpy.data.objects]
    if missing:
        raise ValueError(f"objects not found: {missing}")
    if len(set(objects)) != len(objects):
        raise ValueError("objects contains duplicates")
    clash = [n for n in objects if n + SUFFIX_WORK in bpy.data.objects]
    if clash:
        raise ValueError(f"working copy names already exist: {[n + SUFFIX_WORK for n in clash]}")
    work_col, work_created = _ensure_collection(scene, WORK)
    mapping, pairs = {}, []
    for name in objects:
        orig = bpy.data.objects[name]
        new = orig.copy()
        new.name = name + SUFFIX_WORK
        rec = {"original": name, "work": new.name, "data": None, "orig_data": None, "materials": []}
        if orig.data is not None:
            new.data = orig.data.copy()
            new.data.name = orig.data.name + SUFFIX_WORK
            rec["orig_data"], rec["data"] = orig.data.name, new.data.name
        if materials:
            for slot in new.material_slots:
                if slot.material is not None:
                    slot.material = slot.material.copy()
                    rec["materials"].append(slot.material.name)
        work_col.objects.link(new)
        mapping[name] = new
        pairs.append(rec)
    for name in objects:
        _retarget(mapping[name], mapping)
    scene[KEY] = json.dumps({"pairs": pairs, "work_collection_created": work_created})
    return {"action": "begin", "pairs": {p["original"]: p["work"] for p in pairs}, "collection": WORK,
            "materials_copied": [m for p in pairs for m in p["materials"]]}


def _resolve(state):
    objs = []
    for rec in state["pairs"]:
        orig, work = bpy.data.objects.get(rec["original"]), bpy.data.objects.get(rec["work"])
        if orig is None or work is None:
            raise ValueError(f"work set is incomplete (missing '{rec['original']}' or '{rec['work']}'): "
                             "action 'revert' clears it")
        objs.append((rec, orig, work))
    return objs


def _drop_work_collection(state):
    col = bpy.data.collections.get(WORK)
    if col is not None and not col.objects and not col.children and state.get("work_collection_created"):
        bpy.data.collections.remove(col)


def _snapshot_refs(obj):
    """Intra-set references of an object: parent link and Object pointers on modifiers / constraints."""
    ptrs = []
    for kind, owners in (("modifiers", obj.modifiers), ("constraints", obj.constraints)):
        for i, owner in enumerate(owners):
            for prop in owner.bl_rna.properties:
                if prop.type == "POINTER" and prop.fixed_type and prop.fixed_type.identifier == "Object" \
                        and not prop.is_readonly:
                    ptrs.append((kind, i, prop.identifier, getattr(owner, prop.identifier)))
    return {"parent": obj.parent, "parent_type": obj.parent_type, "parent_bone": obj.parent_bone,
            "pinv": obj.matrix_parent_inverse.copy(), "ptrs": ptrs}


def _restore_refs(obj, snap):
    obj.parent = snap["parent"]
    if snap["parent"] is not None:
        obj.parent_type = snap["parent_type"]
        if snap["parent_type"] == "BONE":
            obj.parent_bone = snap["parent_bone"]
    obj.matrix_parent_inverse = snap["pinv"]
    for kind, i, ident, target in snap["ptrs"]:
        owners = obj.modifiers if kind == "modifiers" else obj.constraints
        if i < len(owners) and getattr(owners[i], ident) is not target:
            setattr(owners[i], ident, target)


def _accept(scene, state):
    pairs = _resolve(state)
    # user_remap on one original also re-points the other originals' parent/modifier/constraint links;
    # remember them so the checkpoint originals can be put back exactly as they were.
    snaps = [(orig, _snapshot_refs(orig)) for _, orig, _w in pairs]
    # Children outside the set follow the copy but keep their world transform: the copy may have a
    # different world matrix (e.g. applied scale), which is folded into each child's parent inverse.
    for vl in scene.view_layers:
        vl.update()
    in_set = {o for _, o, _w in pairs} | {w for _, _o, w in pairs}
    follow = {orig: [(c, orig.matrix_world.copy(), work.matrix_world.copy())
                     for c in bpy.data.objects if c.parent is orig and c not in in_set]
              for _, orig, work in pairs}
    cp_col, _ = _ensure_collection(scene, CHECKPOINT, exclude=True)
    accepted = {}
    for rec, orig, work in pairs:
        homes = [c for c in orig.users_collection if c.name != WORK]
        orig_name, orig_data = orig.name, rec["orig_data"]
        orig.user_remap(work)
        for child, orig_w, work_w in follow[orig]:
            if child.parent is work:
                child.matrix_parent_inverse = work_w.inverted_safe() @ orig_w @ child.matrix_parent_inverse
        for col in homes:
            if work.name not in col.objects:
                col.objects.link(work)
        for col in list(work.users_collection):
            if col.name == WORK:
                col.objects.unlink(work)
        cp_col.objects.link(orig)
        orig.name = orig_name + SUFFIX_PREV
        work.name = orig_name
        if orig_data and work.data is not None and work.data is not orig.data:
            orig.data.name = orig_data + SUFFIX_PREV
            work.data.name = orig_data
        accepted[orig_name] = {"accepted": work.name, "checkpoint": orig.name}
    for orig, snap in snaps:
        _restore_refs(orig, snap)
    _drop_work_collection(state)
    del scene[KEY]
    return {"action": "accept", "accepted": accepted, "checkpoint_collection": CHECKPOINT}


def _revert(scene, state):
    removed_objects, removed_data = [], []
    originals = {rec["original"] for rec in state["pairs"]}
    for rec in state["pairs"]:
        work = bpy.data.objects.get(rec["work"])
        orig = bpy.data.objects.get(rec["original"])
        if work is not None and work.name not in originals:
            data = work.data
            bpy.data.objects.remove(work, do_unlink=True)
            removed_objects.append(rec["work"])
            if data is not None and data.users == 0 and (orig is None or data is not orig.data):
                removed_data.append(data.name)
                bpy.data.batch_remove([data])
        for mat_name in rec["materials"]:
            mat = bpy.data.materials.get(mat_name)
            if mat is not None and mat.users == 0:
                bpy.data.batch_remove([mat])
                removed_data.append(mat_name)
    _drop_work_collection(state)
    del scene[KEY]
    return {"action": "revert", "removed_objects": removed_objects, "removed_data": removed_data}


def _status(scene, state):
    if not state:
        return {"action": "status", "pending": False}
    pairs = {}
    for rec in state["pairs"]:
        pairs[rec["original"]] = {"work": rec["work"],
                                  "original_present": rec["original"] in bpy.data.objects,
                                  "work_present": rec["work"] in bpy.data.objects}
    return {"action": "status", "pending": True, "pairs": pairs}


def main(action, objects=None, materials=False):
    scene = bpy.context.scene
    state = _state(scene)
    if action == "begin":
        return _begin(scene, objects, materials)
    if action == "status":
        return _status(scene, state)
    if action not in ("accept", "revert"):
        raise ValueError("action must be begin | accept | revert | status")
    if not state:
        raise ValueError(f"no pending work set: nothing to {action}")
    return _accept(scene, state) if action == "accept" else _revert(scene, state)


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
