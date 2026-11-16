"""Process-level test of the headless exit-code and result-file contract (iteration 15, B1).

This starts real Blender processes, so run it with plain Python, not inside Blender:

    python3 tests/blender/test_iter15_exit_codes.py --blender <path to blender> [--out-dir <new folder>]

It runs validate_asset.py, clash_audit.py and uv_unwrap_check.py the way SKILL.md documents,

    blender -b f.blend --python-exit-code 1 --python <script> -- --args-file args.json

and checks the rule a caller must apply: a run succeeded only if the exit code is 0 or 2 AND `result_path` exists with
this run's `run_id`. Cases: PASS gives 0 and the file; FAIL gives 2 and the file; an exception gives 1 and no file; a
script path that does not exist writes no file (its exit code is measured and reported, not assumed); a stale file from an
earlier run_id is never accepted. Exit 0 when every case holds, 1 otherwise. The report is printed and written to
<out-dir>/iter15_exit_codes_report.json; the folder is kept so a failure can be inspected.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "skills", "blender-mcp-workflow", "scripts")
TIMEOUT_S = 300

BUILD = '''
import sys
import bmesh
import bpy


def cube(name, loc=(0, 0, 0), material=True, uv=True):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    bm.to_mesh(me)
    bm.free()
    if uv:
        layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            ax = max(range(3), key=lambda i: abs(poly.normal[i]))
            cell = ax * 2 + (poly.normal[ax] < 0)
            ui, vi = [i for i in range(3) if i != ax]
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                lo = (-0.5, -0.5, 0.0)
                layer.uv[li].vector = ((cell % 3) / 3 + 0.02 + 0.29 * (co[ui] - lo[ui]),
                                       (cell // 3) / 2 + 0.02 + 0.46 * (co[vi] - lo[vi]))
    if material:
        me.materials.append(bpy.data.materials.new("MAT_" + name))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
which = sys.argv[sys.argv.index("--") + 1]
path = sys.argv[sys.argv.index("--") + 2]


def uv_quad(name, stacked=False):
    """One quad whose UVs fill the tile; stacked adds a second quad on the very same UVs."""
    me = bpy.data.meshes.new(name)
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    faces = [(0, 1, 2, 3)]
    if stacked:
        verts += [(2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)]
        faces.append((4, 5, 6, 7))
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new(name="UVMap")
    for li in range(len(me.loops)):
        layer.uv[li].vector = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)][li % 4]
    bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, me))


if which == "uvgood":  # one quad filling the tile: no overlap, full coverage, no stretch -> PASS
    uv_quad("UV_Good")
elif which == "uvbad":  # two faces of one mesh on identical UVs -> overlap -> FAIL
    uv_quad("UV_Bad", stacked=True)
elif which == "good":
    cube("SM_Good")
elif which == "nofaces":  # a mesh with vertices and no faces: clash_audit has nothing to audit
    me = bpy.data.meshes.new("Loose")
    me.from_pydata([(0, 0, 0), (1, 0, 0)], [], [])
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Loose", me))
else:  # two cubes that cross each other, no material, no prefix
    cube("BadA", material=False)
    cube("BadB", loc=(0.25, 0.25, 0.25), material=False)
bpy.ops.wm.save_as_mainfile(filepath=path)
'''


def run_blender(blender, blend, script, args, folder, tag):
    """The documented headless call. Returns the exit code."""
    args_file = os.path.join(folder, f"{tag}_args.json")
    with open(args_file, "w", encoding="utf-8") as fh:
        json.dump(args, fh)
    cmd = [blender, "-b", blend, "--python-exit-code", "1", "--python", script, "--", "--args-file", args_file]
    done = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
    return done.returncode


def accepted(code, result_path, run_id):
    """The rule from SKILL.md: exit code 0 or 2, and a result file carrying this run_id."""
    if code not in (0, 2) or not os.path.isfile(result_path):
        return False
    try:
        with open(result_path, encoding="utf-8") as fh:
            return json.load(fh).get("run_id") == run_id
    except (OSError, ValueError):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", required=True)
    ap.add_argument("--out-dir", default=None)
    opts = ap.parse_args()
    folder = opts.out_dir or tempfile.mkdtemp(prefix="iter15-exit-")
    os.makedirs(folder, exist_ok=True)
    blender = opts.blender
    build = os.path.join(folder, "build.py")
    with open(build, "w", encoding="utf-8") as fh:
        fh.write(BUILD)
    blends = {}
    for which in ("good", "bad", "nofaces", "uvgood", "uvbad"):
        blends[which] = os.path.join(folder, f"{which}.blend")
        subprocess.run([blender, "-b", "--factory-startup", "--python", build, "--", which, blends[which]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S, check=True)
    validate = os.path.join(SCRIPTS, "validate_asset.py")
    clash = os.path.join(SCRIPTS, "clash_audit.py")
    uvcheck = os.path.join(ROOT, "skills", "uv-workflow", "scripts", "uv_unwrap_check.py")
    cases = []

    def case(name, script, blend, args, want_codes, want_file, want_verdict=None, pre_stale=False):
        result_path = os.path.join(folder, f"{name}.result.json")
        run_id = f"run-{name}"
        if pre_stale:
            with open(result_path, "w", encoding="utf-8") as fh:
                json.dump({"verdict": "PASS", "run_id": "old-run"}, fh)
        code = run_blender(blender, blend, script, {**args, "result_path": result_path, "run_id": run_id}, folder, name)
        doc = None
        if os.path.isfile(result_path):
            try:
                with open(result_path, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except ValueError:
                doc = {"unreadable": True}
        fresh = bool(doc) and doc.get("run_id") == run_id
        ok = ((want_codes is None or code in want_codes) and fresh == want_file and accepted(code, result_path, run_id) == want_file
              and (want_verdict is None or (doc or {}).get("verdict") == want_verdict)
              and not os.path.exists(result_path + ".tmp"))
        cases.append({"case": name, "exit_code": code, "wanted_codes": "any" if want_codes is None else list(want_codes),"file_with_this_run_id": fresh,
                      "wanted_file": want_file, "verdict": (doc or {}).get("verdict"), "accepted": accepted(code, result_path, run_id),
                      "ok": ok})

    case("validate_pass", validate, blends["good"], {"objects": ["SM_Good"]}, (0,), True, "PASS")
    case("validate_fail", validate, blends["bad"], {"objects": ["BadA"]}, (2,), True, "FAIL")
    case("validate_exception", validate, blends["good"], {"objects": ["NoSuchObject"]}, (1,), False)
    case("validate_stale_not_accepted", validate, blends["good"], {"objects": ["NoSuchObject"]}, (1,), False,
         pre_stale=True)
    case("clash_pass", clash, blends["good"], {"objects": ["SM_Good"]}, (0,), True, "PASS")
    case("clash_fail", clash, blends["bad"], {"objects": ["BadA", "BadB"]}, (2,), True, "FAIL")
    # nothing to audit is a FAIL verdict (exit 2) and must still leave the result file, like every other FAIL
    case("clash_nothing_to_audit", clash, blends["nofaces"], {"objects": ["Loose"]}, (2,), True, "FAIL")
    case("clash_exception", clash, blends["good"], {"objects": ["NoSuchObject"]}, (1,), False)
    # uv_unwrap_check.py as its own process: same contract (0 PASS, 2 FAIL, 1 on an exception and no file)
    case("uv_pass", uvcheck, blends["uvgood"], {"objects": ["UV_Good"]}, (0,), True, "PASS")
    case("uv_fail", uvcheck, blends["uvbad"], {"objects": ["UV_Bad"]}, (2,), True, "FAIL")
    case("uv_exception", uvcheck, blends["uvgood"], {"objects": ["UV_Good"], "method": "bogus"}, (1,), False)
    # a script path that does not exist: whatever Blender returns, no result file can exist, so the rule rejects it
    missing = os.path.join(folder, "no_such_script.py")
    case("missing_script", missing, blends["good"], {"objects": ["SM_Good"]}, None, False)

    report = {"passed": sum(c["ok"] for c in cases), "total": len(cases), "folder": folder, "cases": cases,
              "missing_script_exit_code": next(c["exit_code"] for c in cases if c["case"] == "missing_script")}
    with open(os.path.join(folder, "iter15_exit_codes_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
