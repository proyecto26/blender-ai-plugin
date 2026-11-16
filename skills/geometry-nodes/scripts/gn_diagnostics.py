"""Diagnose Geometry Nodes modifiers without changing anything that is left changed: per modifier, is the node group
there, does its Group Output deliver Geometry, did the nodes report warnings or errors, and is the evaluated result
empty. Read only on data; the only temporary change is hiding the viewport visibility of the modifiers AFTER the one
being measured so the result is that modifier's own output; it is restored in `finally`, also on failure.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/gn_diagnostics.py", init_globals={"ARGS": {
        "objects": ["Terrain"]}})["result"]

ARGS:
    objects     (list[str]) objects to inspect (default: every object with a Geometry Nodes modifier)
    max_ms      (float)     WARN when a modifier's own evaluation time exceeds this many milliseconds
                            (default none: the time is only reported)
    result_path (str)       write the result (plus run_id) as JSON here, atomically, on success
    run_id      (str)       copied into the result and the file

Checks per modifier (PASS, WARN, FAIL or NOT_CHECKED; modifier verdict is FAIL if any FAIL, else WARN if any WARN or
NOT_CHECKED, else PASS; overall is the worst; no modifier found is FAIL with a note):
    node_group          FAIL when the modifier has no node group.
    group_output        FAIL when the group has no Geometry output socket, no Group Output node, or the active
                        Group Output has no linked Geometry input.
    node_warnings       the modifier's node messages: an ERROR is FAIL, a WARNING is WARN, INFO is listed only.
    evaluated_geometry  FAIL when the geometry after this modifier (later modifiers temporarily hidden in the
                        viewport) has no component at all. Components counted: mesh vertices, curve points, point
                        cloud points, volume grids, instances (unrealized instances count), Grease Pencil layers.
                        A curve-only or instance-only output is NOT empty. NOT_CHECKED when the modifier or
                        object is hidden in the viewport (Blender does not evaluate it).
    timing              WARN only when `max_ms` is given and exceeded; `execution_ms` is the modifier's own timing
                        (0 when Blender reused a cached result).
Listed only (key "info", never a verdict): a Geometry input nothing inside the group uses (a generator such as a
Cube straight into Group Output is valid) and every other group input that is not linked inside the group (it keeps
its default).
"""
import json
import math
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


def _json_safe(x):
    """NaN/inf become None, recursively, so the result is valid JSON."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x


def _worst(statuses):
    s = set(statuses)
    if "FAIL" in s:
        return "FAIL"
    if "WARN" in s or "NOT_CHECKED" in s:
        return "WARN"
    return "PASS"


def _check(status, note=None, **extra):
    d = {"status": status}
    if note:
        d["note"] = note
    d.update(extra)
    return d


def classify_message(kind):
    """Node message type -> verdict contribution: ERROR FAIL, WARNING WARN, anything else (INFO) only listed."""
    k = str(kind).upper()
    return "FAIL" if k == "ERROR" else "WARN" if k == "WARNING" else "PASS"


def _group_input_info(ng):
    """(info list) geometry inputs nothing uses, and other inputs not linked inside the group."""
    used = set()
    for n in ng.nodes:
        if n.bl_idname == "NodeGroupInput":
            for s in n.outputs:
                if s.is_linked:
                    used.add(s.identifier)
    info = []
    for item in ng.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT" or item.identifier in used:
            continue
        if item.socket_type == "NodeSocketGeometry":
            info.append({"kind": "geometry_input_unused", "input": item.name,
                         "note": "nothing in the group uses this Geometry input (valid for a generator)"})
        else:
            info.append({"kind": "input_unlinked", "input": item.name,
                         "note": "not linked inside the group; it keeps its default"})
    return info


def _group_output_check(ng):
    outs = [i for i in ng.interface.items_tree
            if i.item_type == "SOCKET" and i.in_out == "OUTPUT" and i.socket_type == "NodeSocketGeometry"]
    if not outs:
        return _check("FAIL", "the group has no Geometry output socket")
    nodes = [n for n in ng.nodes if n.bl_idname == "NodeGroupOutput"]
    if not nodes:
        return _check("FAIL", "the group has no Group Output node")
    node = next((n for n in nodes if n.is_active_output), nodes[0])
    ids = {i.identifier for i in outs}
    linked = [s for s in node.inputs if s.identifier in ids and s.is_linked]
    if not linked:
        return _check("FAIL", "the Group Output has no link into its Geometry input")
    return _check("PASS")


def _components(g):
    c = {"mesh_vertices": 0, "curve_points": 0, "pointcloud_points": 0, "volume_grids": 0, "instances": 0,
         "grease_pencil_layers": 0}
    if g.mesh is not None:
        c["mesh_vertices"] = len(g.mesh.vertices)
    if g.curves is not None:
        c["curve_points"] = len(g.curves.points)
    if g.pointcloud is not None:
        c["pointcloud_points"] = len(g.pointcloud.points)
    if g.volume is not None:
        c["volume_grids"] = len(g.volume.grids)
    inst = g.instances_pointcloud()
    refs = g.instance_references()
    c["instances"] = max(len(inst.points) if inst is not None else 0, len(refs) if refs else 0)
    if g.grease_pencil is not None:
        c["grease_pencil_layers"] = len(g.grease_pencil.layers)
    return c


def _evaluate(obj, mod):
    """Evaluate with every later modifier hidden in the viewport; returns (components, warnings, ms).
    The visibility is restored in finally."""
    mods = list(obj.modifiers)
    later = [m for m in mods[mods.index(mod) + 1:] if m.show_viewport]
    try:
        for m in later:
            m.show_viewport = False
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        g = obj.evaluated_get(dg).evaluated_geometry()
        comps = _components(g)
        warnings = [(w.type, w.message) for w in mod.node_warnings]
        return comps, warnings, mod.execution_time * 1000.0
    finally:
        for m in later:
            m.show_viewport = True
        bpy.context.view_layer.update()


def _modifier(obj, mod, max_ms):
    checks, info = {}, []
    ng = mod.node_group
    if ng is None:
        checks["node_group"] = _check("FAIL", "the modifier has no node group")
        for k in ("group_output", "node_warnings", "evaluated_geometry"):
            checks[k] = _check("NOT_CHECKED", "no node group")
        return {"object": obj.name, "modifier": mod.name, "node_group": None, "checks": checks, "info": info,
                "execution_ms": None, "verdict": "FAIL"}
    checks["node_group"] = _check("PASS", name=ng.name)
    checks["group_output"] = _group_output_check(ng)
    info = _group_input_info(ng)
    ms = None
    visible = mod.show_viewport and not obj.hide_viewport and obj.visible_get()
    if not visible:
        why = "the modifier or object is hidden in the viewport, so Blender does not evaluate it"
        for k in ("node_warnings", "evaluated_geometry"):
            checks[k] = _check("NOT_CHECKED", why)
    else:
        comps, warnings, ms = _evaluate(obj, mod)
        msgs = [{"type": t, "message": m} for t, m in warnings]
        w = _worst([classify_message(t) for t, _m in warnings]) if warnings else "PASS"
        checks["node_warnings"] = _check(w, messages=msgs)
        empty = not any(comps.values())
        checks["evaluated_geometry"] = _check("FAIL" if empty else "PASS",
                                              "no geometry component of any kind" if empty else None,
                                              components=comps)
    if ms is None:
        checks["timing"] = _check("NOT_CHECKED", "not evaluated")
    elif max_ms is None:
        checks["timing"] = _check("PASS", "reported only: no max_ms given")
    else:
        checks["timing"] = _check("WARN" if ms > max_ms else "PASS", limit_ms=max_ms)
    return {"object": obj.name, "modifier": mod.name, "node_group": ng.name, "checks": checks, "info": info,
            "execution_ms": ms, "verdict": _worst([c["status"] for c in checks.values()])}


def main(objects=None, max_ms=None, result_path=None, run_id=None):
    if objects is None:
        objs = [o for o in bpy.data.objects if any(m.type == "NODES" for m in o.modifiers)]
    else:
        objs = []
        for name in objects:
            o = bpy.data.objects.get(name)
            if o is None:
                raise ValueError(f"object not found: {name}")
            objs.append(o)
    entries = [_modifier(o, m, max_ms) for o in objs for m in o.modifiers if m.type == "NODES"]
    if entries:
        verdict, note = _worst([e["verdict"] for e in entries]), None
    else:
        verdict, note = "FAIL", "no Geometry Nodes modifier measured"
    result = {"verdict": verdict, "run_id": run_id, "modifiers": entries}
    if note:
        result["note"] = note
    result = _json_safe(result)
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, allow_nan=False)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
