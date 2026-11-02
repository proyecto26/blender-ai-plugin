"""Named snapshots of a scene's objects that you can list, diff and selectively restore, without ever touching the open
file's path or dirty state (unlike File > Save As, which makes the snapshot the open file).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/scene_snapshot.py",
                            init_globals={"ARGS": {"action": "save", "name": "before_bevel"}})["result"]

ARGS:
    action   (str, required) "save" | "list" | "diff" | "restore"
    dir      (str) folder holding snapshots. Default: "<folder of the open .blend>/snapshots"; required when the
             open file is unsaved. Created by save.
    name     (str) save: snapshot name (letters, digits, "_", "-", "."); default "snap_<timestamp>".
             restore: the snapshot to read.
    a, b     (str) diff: two snapshot names, or "current" for the live scene. Defaults: a = latest snapshot,
             b = "current".
    objects  (list[str]) restore: names of objects to bring back (required, and each must exist in the snapshot).
    tol      (float) diff: largest matrix-element change still counted as unchanged (default 1e-5).

save:    writes <dir>/<name>.blend (the scene's objects and the data they use, via bpy.data.libraries.write, a
         data-level write that does not go through File > Save) and <dir>/<name>.json (manifest: per object
         type, parent, collections, world matrix, mesh hash). Refuses an existing name. Nothing in the open
         session changes: file path, dirty flag, objects and selection are the same afterwards.
list:    snapshots in <dir>, oldest first (name, created, object count, size). Read-only.
diff:    added / removed / changed objects between two manifests: changed lists the largest transform delta,
         whether the mesh hash differs (base mesh vertices to 1e-5 and face corners; modifiers and materials are
         not hashed), and parent changes. Read-only.
restore: appends the named objects (and what they depend on, e.g. a parent or mesh) from the snapshot file into a
         "_Restored" collection under the scene collection. It removes and overwrites nothing: an object that still
         exists keeps its name and the restored copy gets Blender's ".001" name; `restored` maps requested name to the
         name it got, and `dependencies` lists extra objects the append pulled in. The file becomes dirty (it was edited).
"""
import hashlib
import json
import os
import re
import sys
import time

import bpy
import numpy as np

RESTORED = "_Restored"
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


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


def _snap_dir(dir_):
    if dir_:
        return os.path.abspath(dir_)
    if bpy.data.filepath:
        return os.path.join(os.path.dirname(bpy.data.filepath), "snapshots")
    raise ValueError("the open file is unsaved: pass 'dir'")


def _check_name(name):
    if not name or not NAME_RE.match(name) or name in (".", ".."):
        raise ValueError(f"snapshot name {name!r} must use letters, digits, '_', '-' and '.' only")


def _mesh_hash(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    corners = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", corners)
    h = hashlib.sha1()
    h.update(np.round(co, 5).tobytes())
    h.update(corners.tobytes())
    return h.hexdigest()[:16]


def _manifest(name):
    scene = bpy.context.scene
    objs = {}
    for o in scene.objects:
        entry = {"type": o.type, "parent": o.parent.name if o.parent else None,
                 "collections": sorted(c.name for c in o.users_collection),
                 "matrix_world": [round(v, 6) for row in o.matrix_world for v in row]}
        if o.type == "MESH":
            entry["mesh_hash"] = _mesh_hash(o)
            entry["vertices"] = len(o.data.vertices)
        objs[o.name] = entry
    return {"version": 1, "name": name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_file": os.path.basename(bpy.data.filepath), "scene": scene.name, "objects": objs}


def _manifest_path(d, name):
    return os.path.join(d, name + ".json")


def _read_manifest(d, name):
    if name == "current":
        return _manifest("current")
    _check_name(name)
    p = _manifest_path(d, name)
    if not os.path.exists(p):
        raise ValueError(f"no snapshot named {name!r} in {d}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _list(d):
    rows = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    m = json.load(fh)
                blend = os.path.join(d, m["name"] + ".blend")
                if m.get("version") == 1 and os.path.exists(blend):
                    rows.append({"name": m["name"], "created": m["created"], "objects": len(m["objects"]),
                                 "bytes": os.path.getsize(blend), "path": blend})
            except (OSError, ValueError, KeyError):
                continue
    rows.sort(key=lambda r: (r["created"], r["name"]))
    return rows


def _save(d, name):
    if name is None:
        name = "snap_" + time.strftime("%Y%m%d_%H%M%S")
    _check_name(name)
    blend, js = os.path.join(d, name + ".blend"), _manifest_path(d, name)
    if os.path.exists(blend) or os.path.exists(js):
        raise ValueError(f"snapshot {name!r} already exists in {d}; pick another name")
    objs = list(bpy.context.scene.objects)
    if not objs:
        raise ValueError("the scene has no objects to snapshot")
    manifest = _manifest(name)
    os.makedirs(d, exist_ok=True)
    bpy.data.libraries.write(blend, set(objs), compress=True)
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    return {"name": name, "blend": blend, "manifest": js, "objects": len(objs), "bytes": os.path.getsize(blend)}


def _diff(ma, mb, tol):
    a, b = ma["objects"], mb["objects"]
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = []
    for n in sorted(set(a) & set(b)):
        x, y = a[n], b[n]
        delta = max(abs(p - q) for p, q in zip(x["matrix_world"], y["matrix_world"]))
        entry = {}
        if delta > tol:
            entry["transform_delta"] = round(delta, 6)
        if x.get("mesh_hash") != y.get("mesh_hash"):
            entry["mesh_changed"] = True
        if x["parent"] != y["parent"]:
            entry["parent"] = [x["parent"], y["parent"]]
        if x["type"] != y["type"]:
            entry["type"] = [x["type"], y["type"]]
        if entry:
            entry["name"] = n
            changed.append(entry)
    return {"a": ma["name"], "b": mb["name"], "added": added, "removed": removed, "changed": changed,
            "unchanged": len(set(a) & set(b)) - len(changed)}


def _restore(d, name, objects):
    if not name:
        raise ValueError("restore needs 'name'")
    if not objects:
        raise ValueError("restore needs 'objects' (a non-empty list of object names)")
    manifest = _read_manifest(d, name)
    missing = [o for o in objects if o not in manifest["objects"]]
    if missing:
        raise ValueError(f"not in snapshot {name!r}: {missing}")
    blend = os.path.join(d, name + ".blend")
    if not os.path.exists(blend):
        raise ValueError(f"snapshot file missing: {blend}")
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(blend, link=False) as (data_from, data_to):
        absent = [o for o in objects if o not in data_from.objects]
        if absent:
            raise ValueError(f"not in {blend}: {absent}")
        data_to.objects = list(objects)
    requested = dict(zip(objects, (o.name if o else None for o in data_to.objects)))
    scene = bpy.context.scene
    coll = bpy.data.collections.get(RESTORED)
    if coll is None:
        coll = bpy.data.collections.new(RESTORED)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.name not in coll.objects:
            coll.objects.link(o)
    got = set(requested.values())
    return {"restored": requested, "dependencies": sorted(o.name for o in new if o.name not in got),
            "collection": coll.name}


def main(action=None, dir=None, name=None, a=None, b=None, objects=None, tol=1e-5):
    if action not in ("save", "list", "diff", "restore"):
        raise ValueError("'action' must be save | list | diff | restore")
    d = _snap_dir(dir)
    if action == "save":
        return {"action": action, **_save(d, name)}
    if action == "list":
        return {"action": action, "dir": d, "snapshots": _list(d)}
    if action == "diff":
        if a is None:
            rows = _list(d)
            if not rows:
                raise ValueError(f"no snapshots in {d}")
            a = rows[-1]["name"]
        return {"action": action, **_diff(_read_manifest(d, a), _read_manifest(d, b or "current"), float(tol))}
    return {"action": action, **_restore(d, name, objects)}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
