"""Preflight report of the running Blender (read-only): what this session can do before you plan around it.

Reports the Blender version, the registered render engines and the scene's current engine, the enabled add-ons, the
Cycles compute devices (only when the Cycles add-on is enabled) and, for every enum you name, its real values. Nothing
in the file changes: no datablock is created, the selection, active object, mode, frame, render engine, add-on list
and Cycles device preferences are left exactly as found, and `bpy.data.is_dirty` is not touched. Cycles devices come
from the engine's own device query (`_cycles.available_devices`), not from `preferences.devices`, because asking the
preferences to list devices fills in their stored device entries, which is a change.

An enum name is `Class.property` (for example `BooleanModifier.solver`; a leading `bpy.types.` is accepted). A name that
is malformed, names an unknown class or property, or a property that is not an enum becomes an entry
`{"error": "..."}` under that name; it never stops the report. An enum whose values depend on the context (a dynamic
enum) is reported with an empty `values` list and a `note`.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/env_report.py",
                            init_globals={"ARGS": {"enums": ["BooleanModifier.solver"]}})["result"]

Headless: `blender -b --factory-startup --python <skill_dir>/scripts/env_report.py -- --args-file a.json` prints the
result as JSON. It never fails the process; `result_path` is the way to read it back reliably.

ARGS:
    enums       (list[str]|None) enum properties to resolve, as "Class.property"
    result_path (str|None)       write the result dict plus "run_id" there as JSON (temp file, then replace) at the
                                 end of a successful run; a run that raised writes nothing
    run_id      (str|None)       echoed into that file so a caller can tell this run's file from an older one
"""
import json
import os
import sys

import bpy


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


def _engines(scene):
    """Registered render engines: the built-in enum values plus every engine class that registered itself."""
    found = [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items]
    for cls in bpy.types.RenderEngine.__subclasses__():
        ident = getattr(cls, "bl_idname", None)
        if ident and ident not in found:
            found.append(ident)
    return found


def _cycles():
    """Cycles add-on state and its devices, read without refreshing the stored preference entries."""
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return {"present": False, "note": "the Cycles add-on is not enabled"}
    prefs = addon.preferences
    out = {"present": True, "compute_device_type": prefs.compute_device_type,
           "stored_devices": [{"name": d.name, "type": d.type, "use": bool(d.use)} for d in prefs.devices]}
    try:
        import _cycles
    except ImportError as exc:
        out["devices"] = {"status": "NOT_CHECKED", "reason": f"the Cycles engine module did not import: {exc}"}
        return out
    devices, types = {}, [t[0] for t in prefs.get_device_types(bpy.context) if t[0] != "NONE"]
    for dev_type in types + ["CPU"]:
        rows = _cycles.available_devices(dev_type)
        devices[dev_type] = [{"name": r[0], "type": r[1], "id": r[2]} for r in rows]
    out["devices"] = devices
    out["gpu_types_offered"] = types
    return out


def _enum(spec):
    bare = spec[len("bpy.types."):] if isinstance(spec, str) and spec.startswith("bpy.types.") else spec
    if not isinstance(bare, str) or bare.count(".") != 1 or not all(bare.split(".")):
        return {"error": f"{spec!r} is not 'Class.property'"}
    cls_name, prop_name = bare.split(".")
    cls = getattr(bpy.types, cls_name, None)
    if cls is None or not hasattr(cls, "bl_rna"):
        return {"error": f"unknown class bpy.types.{cls_name}"}
    prop = cls.bl_rna.properties.get(prop_name)
    if prop is None:
        return {"error": f"bpy.types.{cls_name} has no property {prop_name!r}"}
    if prop.type != "ENUM":
        return {"error": f"{spec} is a {prop.type} property, not an enum"}
    values = [{"id": e.identifier, "name": e.name} for e in prop.enum_items]
    out = {"values": [v["id"] for v in values], "items": values, "flag": bool(prop.is_enum_flag)}
    if not values:
        out["note"] = "the values depend on the context and are empty here"
    return out


def _write_result(path, result, run_id):
    """Result plus run_id as JSON: temp file, then replace, so a reader never sees half of it."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({**result, "run_id": run_id}, fh, indent=2)
    os.replace(tmp, path)


def main(enums=None, result_path=None, run_id=None):
    if enums is not None and (not isinstance(enums, list) or not all(isinstance(e, str) for e in enums)):
        raise ValueError(f"enums must be a list of 'Class.property' strings, got {enums!r}")
    scene = bpy.context.scene
    result = {
        "blender": {"version": [int(p) for p in bpy.app.version_string.split()[0].split(".") if p.isdigit()],
                    "version_string": bpy.app.version_string,
                    "background": bool(bpy.app.background)},
        "render_engines": _engines(scene),
        "scene_engine": scene.render.engine,
        "addons_enabled": sorted(bpy.context.preferences.addons.keys()),
        "cycles": _cycles(),
        "enums": {name: _enum(name) for name in (enums or [])},
    }
    if result_path:
        _write_result(result_path, result, run_id)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
