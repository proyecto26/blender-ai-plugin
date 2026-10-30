"""Run every inventoried ```python recipe from skills/**/*.md twice on a deterministic fixture.

Maintainer tooling (like test_skill_scripts.py); not shipped inside a skill. The inventory lives in
tests/blender/recipes.json: `entries` are complete recipes, `skip` documents exclusions with a reason.
Any ```python block found in the skills that is in neither list is "not inventoried" and makes the runner FAIL
(add it to `entries`, or to `skip` with a reason).

The fixture is rebuilt for EVERY entry (factory-empty scene), then that entry's block runs twice. Invariants:
  no_exception       neither run raises
  json_safe          `result`, when the block assigns it, is JSON-serialisable
  stable_counts      run 2 leaves equal counts of objects, meshes, materials, node_groups, collections
                     and total modifiers as run 1 (re-running a recipe must not accumulate data)
  camera_unoccluded  (camera recipes) rays from the active camera to the same 6 sample points camera_rig.py
                     uses (bbox centre, 4 side midpoints at mid height, top, inset 10%); fails if the centre is
                     blocked or more than half of the points are. Computed here independently of camera_rig.py.
                     Ignored: the subject, its children, hide_render objects, objects tagged `collision_proxy`
                     and fluid domains (they render as volumes, not as their box).

Run headless (Windows alias does not forward stdout, so the report goes to a file):
    blender -b --factory-startup --python tests/blender/run_recipes.py -- '{"out_dir": "/tmp/recipes"}'
Optional ARGS: "only": ["genre-shooter"] (substring filter on the entry file).
Writes <out_dir>/recipe_report.json; exits 1 when any entry fails or any block is not inventoried.
"""
import json
import os
import re
import sys
import traceback
import warnings

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
INVENTORY = os.path.join(HERE, "recipes.json")


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


# ---------------------------------------------------------------- fixture

def _box(sc, name, size, loc, scale=(1, 1, 1), uv=False, collection=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, size / 2))
    bm.to_mesh(me)
    bm.free()
    if uv:
        me.uv_layers.new(name="UVMap")
    o = bpy.data.objects.new(name, me)
    (collection or sc.collection).objects.link(o)
    o.location, o.scale = loc, scale
    return o


def build_fixture(extras):
    """Empty factory scene + GEO_Ground, SM_Asset (scaled, no UVs), SM_Crate, SM_Crate_01 (UVs), SM_Sword, Camera, Sun."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    me = bpy.data.meshes.new("GEO_Ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=24, y_segments=24, size=25)
    for v in bm.verts:
        v.co.z = 0.15 * ((v.co.x * 0.3) % 1.0 - 0.5)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    sc.collection.objects.link(bpy.data.objects.new("GEO_Ground", me))
    _box(sc, "SM_Asset", 1.0, (0, 0, 0), scale=(1.2, 0.8, 1.5))
    _box(sc, "SM_Crate", 1.0, (3, 1, 0))
    _box(sc, "SM_Crate_01", 1.0, (-3, 1, 0), uv=True)
    _box(sc, "SM_Sword", 0.2, (1.5, -2, 0), scale=(0.3, 0.3, 6))
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    cam.location, cam.rotation_euler = (7, -7, 4), (1.1, 0, 0.785)
    sc.camera = cam
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sc.collection.objects.link(sun)
    sun.location = (0, 0, 10)
    for coll in extras.get("collections", []):
        col = bpy.data.collections.new(coll["name"])
        sc.collection.children.link(col)
        for spec in coll.get("objects", []):
            _box(sc, spec["name"], spec.get("size", 0.5), tuple(spec.get("loc", (0, 0, 0))), collection=col)
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- invariants

def counts():
    return {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials),
            "node_groups": len(bpy.data.node_groups), "collections": len(bpy.data.collections),
            "modifiers": sum(len(o.modifiers) for o in bpy.data.objects)}


def json_safe(value):
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def _ignorable(obj, subject_set):
    return (obj in subject_set or obj.hide_render or obj.get("collision_proxy") is not None
            or any(m.type == "FLUID" and m.fluid_type == "DOMAIN" for m in obj.modifiers))


def _cast_blocked(sc, dg, origin, target, subject_set, info):
    """True if something non-ignorable lies between origin and target."""
    total = (target - origin).length
    if total <= 1e-4:
        return False
    direction = (target - origin) / total
    travelled = 0.0
    for _ in range(16):
        start = origin + direction * travelled
        hit, loc, _n, _i, obj, _m = sc.ray_cast(dg, start, direction, distance=max(total - travelled, 0.0))
        if not hit:
            return False
        if not _ignorable(obj, subject_set):
            info[obj.name] = {"type": obj.type, "display_type": obj.display_type,
                              "fluid": [m.fluid_type for m in obj.modifiers if m.type == "FLUID"]}
            return True
        travelled += (loc - start).length + 1e-3
        if travelled >= total:
            return False
    return False


def occluders(subject_name):
    """Independent occlusion check: rays from the active camera to 6 sample points on the subject's bounds."""
    sc = bpy.context.scene
    cam, subject = sc.camera, bpy.data.objects.get(subject_name)
    if cam is None or subject is None:
        return {"checked": False, "reason": "no active camera" if cam is None else f"subject {subject_name} missing"}
    bpy.context.view_layer.update()
    subject_set = {subject, *subject.children_recursive}
    pts = [subject.matrix_world @ Vector(c) for c in subject.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre, half = (lo + hi) / 2, (hi - lo) / 2 * 0.9
    samples = [centre, centre + Vector((half.x, 0, 0)), centre + Vector((-half.x, 0, 0)),
               centre + Vector((0, half.y, 0)), centre + Vector((0, -half.y, 0)), centre + Vector((0, 0, half.z))]
    origin = cam.matrix_world.translation.copy()
    dg = bpy.context.evaluated_depsgraph_get()
    info = {}
    blocked = [_cast_blocked(sc, dg, origin, p, subject_set, info) for p in samples]
    return {"checked": True, "occluded_by": sorted(info), "blocker_info": info, "centre_blocked": blocked[0],
            "blocked_points": sum(blocked), "points": len(samples)}


# ---------------------------------------------------------------- run

def load_blocks(path):
    return re.findall(r"```python\n(.*?)```", open(path, encoding="utf-8").read(), re.S)


def run_block(code, rel, skill_name):
    code = code.replace("<skills_dir>", SKILLS.replace("\\", "/")).replace(
        "<skill_dir>", f"{SKILLS}/{skill_name}".replace("\\", "/"))
    g = {"__name__": "__mcp__"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        exec(compile(code, rel, "exec"), g)  # maintainer test tool: runs the repo's own documented recipes
    return g.get("result"), [str(w.message)[:160] for w in caught][:3]


def run_entry(entry, blocks):
    rel, idx = entry["file"], entry["block"]
    out = {"file": rel, "block": idx, "status": "pass", "failures": []}
    if idx >= len(blocks):
        out.update(status="fail", failures=[f"inventory is stale: {rel} has only {len(blocks)} python blocks"])
        return out
    skill_name = rel.split("/")[0]
    snaps, results, warns = [], [], []
    for run in range(2):
        try:
            res, w = run_block(blocks[idx], f"{rel}#{idx}", skill_name)
        except Exception as exc:
            out["status"] = "fail"
            out["failures"].append(f"run {run + 1}: {type(exc).__name__}: {exc}"[:400])
            out["traceback"] = traceback.format_exc()[-700:]
            return out
        results.append(res)
        warns += w
        snaps.append(counts())
        if "json_safe" in entry["invariants"] and not json_safe(res):
            out["failures"].append(f"run {run + 1}: result is not JSON-safe ({type(res).__name__})")
    out["counts"] = snaps[0]
    if "stable_counts" in entry["invariants"] and snaps[0] != snaps[1]:
        diff = {k: [snaps[0][k], snaps[1][k]] for k in snaps[0] if snaps[0][k] != snaps[1][k]}
        out["failures"].append(f"counts drift between run 1 and run 2 (run1, run2): {diff}")
    if entry.get("camera") and "camera_unoccluded" in entry["invariants"]:
        occ = occluders(entry.get("subject", "SM_Asset"))
        out["occlusion"] = occ
        if not occ.get("checked"):
            out["failures"].append(f"camera occlusion not checked: {occ['reason']}")
        elif occ["centre_blocked"] or occ["blocked_points"] * 2 > occ["points"]:
            out["failures"].append(f"active camera is occluded by {occ['occluded_by']} "
                                   f"({occ['blocked_points']}/{occ['points']} sample points blocked, "
                                   f"centre blocked: {occ['centre_blocked']})")
    if warns:
        out["warnings"] = warns
    if out["failures"]:
        out["status"] = "fail"
    return out


def main(out_dir=None, only=None):
    out_dir = out_dir or os.path.join(os.environ.get("TEMP", "."), "blender-recipe-runs")
    os.makedirs(out_dir, exist_ok=True)
    inv = json.load(open(INVENTORY, encoding="utf-8"))
    inventoried = {(e["file"], e["block"]) for e in inv["entries"]}
    declared_skip = {(s["file"], s["block"]): s["reason"] for s in inv["skip"]}
    results, skipped, by_file = [], [], {}
    for e in inv["entries"]:
        by_file.setdefault(e["file"], []).append(e)
    for rel, entries in sorted(by_file.items()):
        if only and not any(o in rel for o in only):
            continue
        blocks = load_blocks(os.path.join(SKILLS, *rel.split("/")))
        for entry in entries:
            build_fixture(entry.get("fixture_extras", {}))  # deterministic, rebuilt per entry (so entries cannot leak into each other)
            results.append(run_entry(entry, blocks))
    for path_dir, _d, files in os.walk(SKILLS):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(path_dir, fn), SKILLS).replace("\\", "/")
            for i, _b in enumerate(load_blocks(os.path.join(path_dir, fn))):
                if (rel, i) in inventoried:
                    continue
                skipped.append({"file": rel, "block": i, "reason": declared_skip.get((rel, i), "not inventoried")})
    skipped.sort(key=lambda s: (s["file"], s["block"]))
    passed = sum(r["status"] == "pass" for r in results)
    not_inventoried = [s for s in skipped if s["reason"] == "not inventoried"]
    summary = {"blender": bpy.app.version_string, "ran": len(results), "passed": passed, "failed": len(results) - passed,
               "not_inventoried": len(not_inventoried),
               "entries_with_warnings": sum(1 for r in results if r.get("warnings")),
               "skipped": len(skipped), "skip_reasons": _tally(skipped), "out_dir": out_dir}
    report = {"summary": summary, "failures": [r for r in results if r["status"] != "pass"], "not_inventoried": not_inventoried,
              "results": results,
              "skipped": skipped}
    with open(os.path.join(out_dir, "recipe_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    return summary


def _tally(items):
    tally = {}
    for it in items:
        key = it["reason"].split(":")[0]
        tally[key] = tally.get(key, 0) + 1
    return tally


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["failed"] == 0 and result["not_inventoried"] == 0 else 1)
