"""Smoke-test every skill script inside a real Blender (5.1+), in isolation.

Builds a throwaway test scene in a NEW scene datablock, runs each script with
representative ARGS, asserts on the returned result dict, then deletes the test
scene. Never saves the file.

Run headless (recommended):
    blender -b --factory-startup --python tests/blender/test_skill_scripts.py -- '{"out_dir": "/tmp/blender-skill-tests"}'

Or through the official Blender MCP, against a scratch .blend:
    execute_blender_code_for_cli(blend_file="/tmp/empty.blend", code=
        'import runpy; result = runpy.run_path("<repo>/tests/blender/test_skill_scripts.py", '
        'init_globals={"ARGS": {"out_dir": "/tmp/blender-skill-tests"}})["result"]')
"""
import json
import os
import runpy
import sys
import tempfile
import traceback

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _cube(name, size=1.0, loc=(0, 0, 0), collection=None, segments=0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if segments:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=segments, use_grid_fill=True)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, size / 2))
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    obj.location = loc
    return obj


def _sphere(name, radius=0.5, collection=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _grid(name, size=5.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=size)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def build_cases(out_dir):
    """Each case: (id, callable returning result, assertion on result)."""
    W = "blender-mcp-workflow"
    return [
        ("core.setup_collections", lambda: run(W, "setup_collections.py", {"asset": "Crate"}),
         lambda r: "COL_Crate_Export" in r["created"] + r["existing"]),
        ("core.scene_audit", lambda: run(W, "scene_audit.py", {"tri_budget": 100000}),
         lambda r: r["object_count"] > 0 and "naming_violations" in r),
        ("core.validate_asset", lambda: run(W, "validate_asset.py", {"objects": ["SM_Crate_01"], "tri_budget": 5000}),
         lambda r: r["objects"]["SM_Crate_01"]["checks"]["transforms_applied"]["status"] == "PASS"),
        ("core.capture_views", lambda: run(W, "capture_views.py", {"target": "SM_Crate_01", "out_dir": out_dir,
                                                                  "views": ["three_quarter"], "resolution": 128}),
         lambda r: all(os.path.exists(p) for p in r["images"])),
        ("hard-surface.bevel_stack", lambda: run("hard-surface", "bevel_stack.py", {"objects": ["SM_Crate_01"], "width": 0.02}),
         lambda r: r["objects"]["SM_Crate_01"]["evaluated_tris"] > 12),
        ("materials.pbr_material", lambda: run("materials", "pbr_material.py", {
            "name": "MAT_CratePaint", "base_color": [0.3, 0.2, 0.1], "roughness": 0.6, "objects": ["SM_Crate_01"]}),
         lambda r: r["assigned"] == ["SM_Crate_01"]),
        ("uv-workflow.uv_unwrap_check", lambda: run("uv-workflow", "uv_unwrap_check.py", {
            "objects": ["SM_Crate_01"], "unwrap": True, "texture_px": 1024}),
         lambda r: r["objects"]["SM_Crate_01"]["texel_density_px_per_m"] > 0),
        ("geometry-nodes.scatter_points", lambda: run("geometry-nodes", "scatter_points.py", {
            "surface": "GEO_Ground", "collection": "COL_Rocks", "density": 1.0}),
         lambda r: r["instances"] > 10),
        ("lighting.light_rig", lambda: run("lighting", "light_rig.py", {"preset": "studio_3pt", "target": "SM_Crate_01"}),
         lambda r: len(r["lights"]) == 3),
        ("lighting.light_rig_rerun", lambda: run("lighting", "light_rig.py", {"preset": "horror_practical"}),
         lambda r: len(r["lights"]) == 2 and len([o for o in bpy.data.collections["COL_Lights"].objects]) == 2),
        ("camera.camera_rig", lambda: run("camera-cinematography", "camera_rig.py", {
            "name": "CAM_Hero_01", "target": "SM_Crate_01", "lens_mm": 85, "dof_fstop": 2.8, "aspect": "16:9"}),
         lambda r: r["active"] and r["distance_m"] > 0),
        ("rendering.render_preset", lambda: run("rendering", "render_preset.py", {"preset": "cycles_preview"}),
         lambda r: r["engine"] == "CYCLES" and not r["skipped"]),
        ("rendering.render_preset_eevee", lambda: run("rendering", "render_preset.py", {"preset": "eevee_final"}),
         lambda r: r["engine"] == "BLENDER_EEVEE" and not r["skipped"]),
        ("compositing.comp_grade", lambda: run("compositing", "comp_grade.py", {"preset": "horror_vhs"}),
         lambda r: len(r["nodes"]) >= 4),
        ("compositing.comp_grade_rerun", lambda: run("compositing", "comp_grade.py", {"preset": "cinematic"}),
         lambda r: "SK_Pixelate" not in r["nodes"]),
        ("lod-pipeline.generate_lods", lambda: run("lod-pipeline", "generate_lods.py", {
            "object": "SM_Sphere_01", "ratios": [0.5, 0.25]}),
         lambda r: r["lods"][1]["tris"] < r["lods"][0]["tris"] and r["lods"][2]["tris"] < r["lods"][1]["tris"]),
        ("collision-proxy.make_collision", lambda: run("collision-proxy", "make_collision.py", {
            "objects": ["SM_Sphere_01"], "shape": "convex", "engine": "unreal", "max_hull_verts": 32}),
         lambda r: r["proxies"][0]["name"].startswith("UCX_SM_Sphere_01") and r["proxies"][0]["verts"] <= 32),
        ("export-pipeline.fbx", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "unreal", "out_path": os.path.join(out_dir, "SM_Crate_01.fbx")}),
         lambda r: r["exists"] and r["bytes"] > 1000),
        ("export-pipeline.glb", lambda: run("export-pipeline", "export_asset.py", {
            "objects": ["SM_Crate_01"], "engine": "web", "out_path": os.path.join(out_dir, "SM_Crate_01.glb")}),
         lambda r: r["exists"] and r["bytes"] > 500),
        ("unreal-export.export_unreal", lambda: run("unreal-export", "export_unreal.py", {
            "mesh": "SM_Sphere_01", "out_dir": out_dir, "strict": False}),
         lambda r: r["exported"] and r["collision"] and r["checks"]["prefix"] == "PASS"),
        ("unity-export.export_unity", lambda: run("unity-export", "export_unity.py", {
            "objects": ["SM_Crate_01"], "out_path": os.path.join(out_dir, "unity", "SM_Crate_01.fbx")}),
         lambda r: r["exported"]),
        ("godot-export.export_godot", lambda: run("godot-export", "export_godot.py", {
            "objects": ["SM_Crate_01", "SM_Crate_01-colonly"], "out_path": os.path.join(out_dir, "godot", "crate.glb")}),
         lambda r: r["exported"] and r["import_hints"].get("SM_Crate_01-colonly") == "-colonly"),
        ("rigging.rig_check", lambda: run("rigging", "rig_check.py", {"armature": "ARM_Test"}),
         lambda r: r["deform_bones"] == 3 and r["unpaired_side_bones"] == [] and "SK_Arm" in r["meshes"]),
        ("animation.turntable", lambda: run("animation", "turntable.py", {"target": "SM_Crate_01", "frames": 48}),
         lambda r: r["frames"][1] - r["frames"][0] == 47),
        ("lowpoly-style.ps1_look", lambda: run("lowpoly-style", "ps1_look.py", {"objects": ["SM_Sphere_01"], "snap": 0.05}),
         lambda r: r["snapped"] == ["SM_Sphere_01"] and r["resolution"] == [320, 240]),
        ("stylized-style.toon_material", lambda: run("stylized-style", "toon_material.py", {
            "name": "Toon_Test", "base_color": [0.9, 0.4, 0.3], "bands": 3, "objects": ["SM_Rock_A"], "outline": 0.01}),
         lambda r: r["outlined"] == ["SM_Rock_A"] and r["bands"] == 3),
        ("voxel-style.voxelize", lambda: run("voxel-style", "voxelize.py", {"objects": ["SM_Rock_B"], "voxel_size": 0.05}),
         lambda r: r["objects"]["SM_Rock_B"]["faces"] > 6),
        ("isometric-style.iso_camera", lambda: run("isometric-style", "iso_camera.py", {"projection": "dimetric_2_1", "pixel_tile": 32}),
         lambda r: r["ortho_scale"] > 0 and r["resolution"][0] % 32 == 0),
        ("physics-sim.rigid_body_setup", lambda: run("physics-sim", "rigid_body_setup.py", {
            "active": ["SM_Rock_B"], "passive": ["GEO_Ground"], "material": "stone", "frames": 20, "bake": True}),
         lambda r: r["active"]["SM_Rock_B"]["mass_kg"] > 0 and r.get("baked") is True),
        ("cloth-sim.cloth_setup", lambda: run("cloth-sim", "cloth_setup.py", {
            "cloth": "SM_Flag", "fabric": "silk", "pin_group": "Pin", "colliders": ["SM_Crate_01"]}),
         lambda r: r["pinned"] and r["colliders"] == ["SM_Crate_01"]),
        ("retopology.topology_report", lambda: run("retopology", "topology_report.py", {
            "objects": ["SM_Flag", "SM_Sphere_01"], "deforming": True}),
         lambda r: r["objects"]["SM_Flag"]["verdict"] == "PASS" and r["objects"]["SM_Sphere_01"]["tris"] > 0),
        ("asset-optimization.optimize_mesh", lambda: run("asset-optimization", "optimize_mesh.py", {
            "objects": ["SM_Dirty"], "merge_distance": 0.001}),
         lambda r: r["objects"]["SM_Dirty"]["after"]["verts"] < r["objects"]["SM_Dirty"]["before"]["verts"]),
        ("texture-workflow.bake_maps", lambda: run("texture-workflow", "bake_maps.py", {
            "low": "SM_Crate_01", "high": "HP_Crate_01", "maps": ["normal", "ao"], "size": 64, "samples": 4,
            "out_dir": os.path.join(out_dir, "bakes")}),
         lambda r: len(r["images"]) == 2 and all(os.path.exists(p) for p in r["images"])),
    ]


def _fixtures(scene):
    """Extra objects for rigging, cloth, bake, cleanup and engine-export cases."""
    # Armature with spine + mirrored arms, and a skinned mesh weighted to all deform bones.
    arm_data = bpy.data.armatures.new("ARM_Test")
    arm = bpy.data.objects.new("ARM_Test", arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=[arm],
                                   selected_editable_objects=[arm]):
        bpy.ops.object.mode_set(mode="EDIT")
        spine = arm_data.edit_bones.new("spine")
        spine.head, spine.tail = (0, 0, 0), (0, 0, 1)
        for side, x in (("L", 1), ("R", -1)):
            b = arm_data.edit_bones.new(f"arm.{side}")
            b.head, b.tail, b.parent = (0, 0, 1), (x, 0, 1), spine
        bpy.ops.object.mode_set(mode="OBJECT")
    skin = _cube("SK_Arm", 1.0, segments=1)
    skin.location = (0, 3, 0)
    for bone in ("spine", "arm.L", "arm.R"):
        vg = skin.vertex_groups.new(name=bone)
        vg.add([v.index for v in skin.data.vertices], 0.33, "REPLACE")
    mod = skin.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    # Cloth plane with a pin group on one edge.
    me = bpy.data.meshes.new("SM_Flag")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=1.0)
    bm.to_mesh(me)
    bm.free()
    flag = bpy.data.objects.new("SM_Flag", me)
    scene.collection.objects.link(flag)
    flag.location = (0, -3, 2)
    pin = flag.vertex_groups.new(name="Pin")
    pin.add([v.index for v in me.vertices if v.co.x < -0.99], 1.0, "REPLACE")
    # High-poly bake source around the crate.
    hp = _sphere("HP_Crate_01", 0.75)
    hp.location = (0, 0, 0.5)
    # Mesh with duplicate vertices for cleanup.
    dirty = _cube("SM_Dirty", 0.5)
    dirty.location = (-3, 0, 0)
    bm = bmesh.new()
    bm.from_mesh(dirty.data)
    bmesh.ops.split_edges(bm, edges=bm.edges)
    bm.to_mesh(dirty.data)
    bm.free()
    # Godot collision-only twin.
    col_twin = _cube("SM_Crate_01-colonly", 1.0)
    col_twin.hide_render = True


def main(out_dir=None, only=None):
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "blender-skill-tests")
    os.makedirs(out_dir, exist_ok=True)
    window = bpy.context.window
    original_scene = window.scene if window else bpy.context.scene
    scene = bpy.data.scenes.new("__SkillTests")
    if window:
        window.scene = scene
    created_before = {c.name for c in bpy.data.collections}
    results, passed = [], 0
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]) if not window else _nullctx():
            _cube("SM_Crate_01", 1.0)
            _sphere("SM_Sphere_01", 0.5).location = (2.5, 0, 0.5)
            _grid("GEO_Ground", 5.0)
            rocks = bpy.data.collections.new("COL_Rocks")
            scene.collection.children.link(rocks)
            _cube("SM_Rock_A", 0.2, collection=rocks)
            _cube("SM_Rock_B", 0.3, collection=rocks)
            _fixtures(scene)
            for case_id, fn, check in build_cases(out_dir):
                if only and not any(case_id.startswith(o) for o in only):
                    continue
                try:
                    res = fn()
                    ok = bool(check(res))
                    results.append({"case": case_id, "ok": ok, "result": res if not ok else None})
                except Exception:
                    results.append({"case": case_id, "ok": False, "error": traceback.format_exc()[-800:]})
                passed += results[-1]["ok"]
    finally:
        if window:
            window.scene = original_scene
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for name in {c.name for c in bpy.data.collections} - created_before:
            bpy.data.collections.remove(bpy.data.collections[name])
    return {"blender": bpy.app.version_string, "passed": passed, "total": len(results),
            "failures": [r for r in results if not r["ok"]], "cases": [r["case"] for r in results], "out_dir": out_dir}


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] == result["total"] else 1)
