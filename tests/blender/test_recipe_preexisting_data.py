"""Maintainer test: pre-existing same-name data must survive two runs of the six cleanup-sensitive recipes, and the
recipe's own data must not accumulate. Run:
    blender -b --factory-startup --python tests/blender/test_recipe_preexisting_data.py -- '{"out": "<dir>"}'
Writes <out>/preexisting_report.json and exits 1 when any recipe destroyed a decoy, errored, or accumulated data."""
import json, re, sys, traceback, os
import bpy
HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SK = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
_a = json.loads(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else {}
OUT = os.path.join(_a.get("out", os.environ.get("TEMP", ".")), "preexisting_report.json")
SPEC = {
 "animation/references/mocap-cleanup.md": [("objects","MocapDemo"),("actions","MocapDemo"),("actions","MocapDemo_Run"),("actions","MocapDemoAction")],
 "blender-mcp-workflow/references/reference-image-depth.md": [("objects","TriCamA"),("objects","TriCamB"),("cameras","TriCamA"),("cameras","TriCamB")],
 "geometry-nodes/references/scatter-systems.md": [("objects","ScatterGround"),("objects","ScatterBlocker"),("objects","ScatterRock"),("meshes","ScatterGround"),("meshes","ScatterBlocker"),("meshes","ScatterRock"),("node_groups","GN_Scatter_Masked"),("node_groups","GN_Scatter_Masked_mine"),("collections","ScatterSources")],
 "realistic-style/references/scan-match.md": [("objects","ScanSrc"),("objects","ScanLow"),("objects","ScanLowShifted"),("meshes","ScanSrc"),("meshes","ScanLow"),("meshes","ScanLowShifted")],
 "rigging/references/facial-shape-keys-drivers.md": [("objects","FaceDemo"),("objects","ARM_FaceDemo"),("meshes","FaceDemo"),("armatures","ARM_FaceDemo")],
 "unity-export/references/hdrp-material-mapping.md": [("images","T_metal"),("images","T_ao"),("images","T_rough"),("images","T_Test_MaskMap")],
}
KINDS = ("objects","actions","images","node_groups","meshes","cameras","armatures","collections")
def mk(kind, name):
    sc = bpy.context.scene
    if kind == "objects":
        d = bpy.data.objects.new(name, None); sc.collection.objects.link(d)
    elif kind == "actions": d = bpy.data.actions.new(name)
    elif kind == "images": d = bpy.data.images.new(name, 2, 2)
    elif kind == "node_groups": d = bpy.data.node_groups.new(name, "GeometryNodeTree")
    else: d = getattr(bpy.data, kind).new(name)
    d["decoy"] = 1
    if kind != "objects" and kind != "collections":
        d.use_fake_user = True
    return d
def decoys():
    out = {}
    for kind in KINDS:
        out[kind] = sorted(d.name for d in getattr(bpy.data, kind) if d.get("decoy"))
    return {k:v for k,v in out.items() if v}
def total():
    return {k: len([d for d in getattr(bpy.data,k) if not d.get("decoy")]) for k in KINDS}
res = {}
for rel, spec in SPEC.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for kind, name in spec: mk(kind, name)
    before = decoys()
    code = re.findall(r"```python\n(.*?)```", open(os.path.join(SK,*rel.split("/")),encoding="utf-8").read(), re.S)[0]
    r = {"decoys_before": before}
    try:
        counts=[]
        for run in range(2):
            g = {"__name__":"__mcp__"}
            exec(compile(code, rel, "exec"), g)
            r["result"] = g.get("result")
            counts.append(total())
        r["own_stable"] = counts[0] == counts[1]
        r["own_counts"] = counts
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"[:300]; r["tb"]=traceback.format_exc()[-500:]
    r["decoys_after"] = decoys(); r["survived"] = r["decoys_after"] == before
    res[rel] = r
json.dump(res, open(OUT,"w"), indent=1)

bad = [k for k, v in res.items() if not v["survived"] or v.get("error") or not v.get("own_stable")]
if bpy.app.background:
    sys.exit(1 if bad else 0)
