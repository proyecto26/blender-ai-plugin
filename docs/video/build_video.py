"""Render the Blender AI Plugin demo video with Blender itself, using the plugin's
own skill scripts for every look (materials, light rigs, cameras, compositor
grades, PS1/voxel/isometric/toon styles, LODs, collision).

Every shot is defined in timeline.json. Each look starts from a factory-reset
scene, so shots are deterministic and independent. Run headless only:

    blender -b --factory-startup --python docs/video/build_video.py -- '{"stills": true}'
    blender -b --factory-startup --python docs/video/build_video.py -- '{"shots": ["toon"]}'
    blender -b --factory-startup --python docs/video/build_video.py -- '{}'        # full render

ARGS:
    out_dir  (str)        default docs/video/build
    shots    (list[str])  subset of shot ids (default all)
    stills   (bool)       render one mid-shot frame per shot + overlay (review contact sheet)
    samples  (int)        EEVEE render samples (default 32)
    scale    (int)        resolution percentage (default 100)
"""
import json
import math
import os
import runpy
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
SKILLS = os.path.join(REPO, "skills")
TIMELINE = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
ACCENT = tuple(TIMELINE["accent"])


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def skill(_skill, _script, **args):
    """Run a plugin skill script exactly like an agent would through the MCP."""
    return runpy.run_path(os.path.join(SKILLS, _skill, "scripts", _script), init_globals={"ARGS": args})["result"]


# --------------------------------------------------------------------------- scene building

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = TIMELINE["resolution"]
    scene.render.fps = TIMELINE["fps"]
    world = bpy.data.worlds.new("WRL_Video")
    scene.world = world
    return scene


def _mesh_object(name, bm, collection=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def build_hero():
    """Procedural sci-fi supply crate: inset panels, top vents, side handles, light strip."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(1.3, 0.85, 0.8), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, 0.4), verts=bm.verts)
    bmesh.ops.inset_individual(bm, faces=list(bm.faces), thickness=0.07, depth=-0.035)
    for i in range(5):  # vents on the lid
        geom = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((-0.4 + i * 0.2, 0.0, 0.79))
                                     @ Matrix.Diagonal((0.1, 0.5, 0.05, 1)))
    for side in (-1, 1):  # handles
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.035, radius2=0.035, depth=0.4,
                              matrix=Matrix.Translation((side * 0.69, 0, 0.55)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    body = _mesh_object("SM_SupplyCrate", bm)
    body.data.uv_layers.new(name="UVMap")

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.432, 0.4)) @ Matrix.Diagonal((0.9, 0.02, 0.05, 1)))
    strip = _mesh_object("SM_SupplyCrate_Light", bm)
    strip.parent = body

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=8.0)
    ground = _mesh_object("GEO_Ground", bm)

    rocks = bpy.data.collections.new("COL_Rocks")
    bpy.context.scene.collection.children.link(rocks)
    for i, r in enumerate((0.07, 0.11, 0.05)):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
        rock = _mesh_object(f"SM_Rock_{i}", bm, rocks)
        rock.location.z = r * 0.4
    bpy.context.view_layer.layer_collection.children["COL_Rocks"].exclude = True
    skill("geometry-nodes", "scatter_points.py", surface="GEO_Ground", collection="COL_Rocks",
          density=1.2, seed=7, scale_min=0.6, scale_max=1.6, align_to_normal=False)
    return body, strip, ground


def emissive(obj, color, strength):
    mat = bpy.data.materials.new("MAT_Light")
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    mat.node_tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def hero_camera(azimuth=35, elevation=13, lens=50, fill=0.62, orbit=18, frames=48, target="SM_SupplyCrate"):
    cam = skill("camera-cinematography", "camera_rig.py", name="CAM_Hero", target=target, lens_mm=lens,
                azimuth_deg=azimuth, elevation_deg=elevation, fill=fill, aspect="16:9")
    orbit_camera(bpy.data.objects[cam["camera"]], orbit, frames)
    return cam


def orbit_camera(cam, degrees, frames):
    focus = cam.constraints["Track_Focus"].target if "Track_Focus" in cam.constraints else None
    center = focus.location.copy() if focus else Vector((0, 0, 0))
    pivot = bpy.data.objects.new("EMP_Orbit", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = center
    bpy.context.view_layer.update()
    world = cam.matrix_world.copy()
    cam.parent = pivot
    cam.matrix_world = world
    pivot.rotation_euler.z = 0
    pivot.keyframe_insert("rotation_euler", index=2, frame=1)
    pivot.rotation_euler.z = math.radians(degrees)
    pivot.keyframe_insert("rotation_euler", index=2, frame=frames)


def pbr_set(body, strip, ground, paint=(0.06, 0.22, 0.3), metal=0.85, rough=0.38, ground_color=(0.16, 0.16, 0.17),
            ground_rough=0.85, light_strength=12.0):
    skill("materials", "pbr_material.py", name="MAT_CratePaint", base_color=list(paint), metallic=metal,
          roughness=rough, coat_weight=0.2, objects=[body.name])
    skill("materials", "pbr_material.py", name="MAT_Ground", base_color=list(ground_color), roughness=ground_rough,
          objects=[ground.name])
    skill("materials", "pbr_material.py", name="MAT_Rock", base_color=[0.22, 0.2, 0.18], roughness=0.9,
          objects=[o.name for o in bpy.data.collections["COL_Rocks"].objects])
    emissive(strip, ACCENT, light_strength)


def eevee(samples, raytracing=True):
    skill("rendering", "render_preset.py", preset="eevee_final")
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_raytracing = raytracing


# --------------------------------------------------------------------------- looks

def look(name, frames, samples):
    reset()
    body, strip, ground = build_hero()
    sc = bpy.context.scene
    if name in ("clay", "bevel"):
        if name == "bevel":
            skill("hard-surface", "bevel_stack.py", objects=[body.name], width=0.03, segments=3)
        skill("rendering", "render_preset.py", preset="workbench_clay")
        sc.display.shading.single_color = (0.75, 0.74, 0.72)
        sc.display.shading.background_type = "WORLD" if hasattr(sc.display.shading, "background_type") else "THEME"
        sc.world.color = (0.05, 0.05, 0.06)
        if name == "bevel":
            hero_camera(frames=frames, azimuth=50, elevation=30, lens=85, fill=0.95, orbit=12)
        else:
            hero_camera(frames=frames)
        return
    skill("hard-surface", "bevel_stack.py", objects=[body.name], width=0.02, segments=3)
    if name == "pbr":
        pbr_set(body, strip, ground)
        skill("lighting", "light_rig.py", preset="studio_3pt", target=body.name)
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="clean")
        hero_camera(frames=frames, azimuth=25)
    elif name == "realistic":
        pbr_set(body, strip, ground, paint=(0.35, 0.3, 0.22), metal=0.6, rough=0.45, ground_color=(0.3, 0.26, 0.2))
        skill("lighting", "light_rig.py", preset="golden_hour", target=body.name)
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="cinematic")
        hero_camera(frames=frames, azimuth=-30, elevation=9, lens=65)
    elif name == "toon":
        skill("stylized-style", "toon_material.py", name="MAT_Toon_Crate", base_color=[0.95, 0.5, 0.18], bands=3,
              objects=[body.name], outline=0.012)
        skill("stylized-style", "toon_material.py", name="MAT_Toon_Ground", base_color=[0.38, 0.62, 0.86], bands=2,
              rim=0, objects=[ground.name])
        skill("stylized-style", "toon_material.py", name="MAT_Toon_Rock", base_color=[0.5, 0.46, 0.6], bands=2,
              rim=0, objects=[o.name for o in bpy.data.collections["COL_Rocks"].objects])
        emissive(strip, (1, 1, 0.9), 6)
        skill("lighting", "light_rig.py", preset="studio_3pt", target=body.name)
        skill("rendering", "render_preset.py", preset="stylized_flat")
        sc.eevee.taa_render_samples = samples
        skill("compositing", "comp_grade.py", preset="stylized_bloom")
        hero_camera(frames=frames, azimuth=40, elevation=18)
        sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.78, 0.95, 1)
    elif name == "ps1":
        pbr_set(body, strip, ground, paint=(0.25, 0.27, 0.22), rough=0.8, metal=0.2, ground_color=(0.1, 0.09, 0.08))
        skill("lighting", "light_rig.py", preset="horror_practical", target=body.name)
        eevee(samples, raytracing=False)
        skill("lowpoly-style", "ps1_look.py", objects=[body.name, ground.name], snap=0.04, resolution=[320, 240])
        skill("compositing", "comp_grade.py", preset="horror_vhs")
        cam = hero_camera(frames=frames, azimuth=15, elevation=20, lens=28, fill=0.55)
        sc.render.resolution_x, sc.render.resolution_y = 320, 240
    elif name == "voxel":
        pbr_set(body, strip, ground, paint=(0.2, 0.5, 0.25), metal=0.0, rough=0.7, ground_color=(0.45, 0.35, 0.22))
        skill("voxel-style", "voxelize.py", objects=[body.name], voxel_size=0.13)
        skill("lighting", "light_rig.py", preset="overcast", target=body.name)
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="clean")
        hero_camera(frames=frames, azimuth=30, elevation=22)
    elif name == "iso":
        pbr_set(body, strip, ground, paint=(0.85, 0.42, 0.25), metal=0.0, rough=0.6, ground_color=(0.42, 0.62, 0.38))
        for i, (x, y, rz) in enumerate(((1.8, 0.9, 0.4), (-1.6, 1.2, -0.3))):
            dup = body.copy()
            dup.name = f"SM_SupplyCrate_{i + 2}"
            dup.location = (x, y, 0)
            dup.rotation_euler.z = rz
            dup.scale = (0.7, 0.7, 0.7)
            sc.collection.objects.link(dup)
        skill("lighting", "light_rig.py", preset="golden_hour")
        eevee(samples)
        cam = skill("isometric-style", "iso_camera.py", projection="dimetric_2_1", padding=1.05)
        iso = bpy.data.objects[cam["camera"]]
        iso.data.ortho_scale = 7.0
        pivot = bpy.data.objects.new("EMP_Orbit", None)
        sc.collection.objects.link(pivot)
        bpy.context.view_layer.update()
        world = iso.matrix_world.copy()
        iso.parent = pivot
        iso.matrix_world = world
        pivot.keyframe_insert("rotation_euler", index=2, frame=1)
        pivot.rotation_euler.z = math.radians(25)
        pivot.keyframe_insert("rotation_euler", index=2, frame=frames)
    elif name == "noir":
        pbr_set(body, strip, ground, paint=(0.2, 0.2, 0.2), rough=0.3, ground_color=(0.08, 0.08, 0.08), ground_rough=0.25,
                light_strength=2)
        skill("lighting", "light_rig.py", preset="moonlight", target=body.name)
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="noir")
        hero_camera(frames=frames, azimuth=-55, elevation=8, lens=35)
    elif name in ("neon", "title", "stats", "cta"):
        pbr_set(body, strip, ground, paint=(0.04, 0.04, 0.06), metal=1.0, rough=0.25, ground_color=(0.02, 0.02, 0.03),
                ground_rough=0.12, light_strength=40)
        skill("lighting", "light_rig.py", preset="neon_night", target=body.name)
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="stylized_bloom")
        if name == "neon":
            hero_camera(frames=frames, azimuth=10, elevation=10, lens=40)
        else:
            sc.view_settings.exposure = -1.6 if name != "title" else -0.8
            hero_camera(frames=frames, azimuth=-20 if name != "cta" else 25, elevation=15, lens=35, fill=0.45,
                        orbit=30)
    elif name == "ship":
        pbr_set(body, strip, ground)
        ground.hide_render = True
        ground.hide_set(True)
        skill("lod-pipeline", "generate_lods.py", object=body.name, ratios=[0.4, 0.12], offset_x=1.7)
        skill("collision-proxy", "make_collision.py", objects=[body.name], shape="convex", engine="unreal")
        for proxy in [o for o in bpy.data.objects if o.name.startswith("UCX_")]:
            proxy.hide_render = False
            proxy.display_type = "WIRE"
            emissive(proxy, ACCENT, 3)
            mod = proxy.modifiers.new("Wire", "WIREFRAME")
            mod.thickness = 0.008
        skill("lighting", "light_rig.py", preset="studio_3pt")
        eevee(samples)
        skill("compositing", "comp_grade.py", preset="clean")
        hero_camera(frames=frames, azimuth=8, elevation=14, lens=40, fill=0.85, orbit=10, target=None)
    else:
        raise ValueError(f"unknown look {name}")


# --------------------------------------------------------------------------- overlay (captions)

def _fcurves(id_data):
    anim = id_data.animation_data
    action = anim.action if anim else None
    if action is None:
        return []
    if hasattr(action, "layers") and action.layers:
        return [fc for layer in action.layers for strip in layer.strips
                for bag in getattr(strip, "channelbags", []) for fc in bag.fcurves]
    return list(getattr(action, "fcurves", []))


def _ease(id_data):
    for fc in _fcurves(id_data):
        for kp in fc.keyframe_points:
            kp.interpolation = "EXPO"
            kp.easing = "EASE_OUT"


def _text(name, body, font, size, color, location, align="LEFT"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font and os.path.exists(font):
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.align_x = align
    cu.align_y = "BOTTOM"
    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    mat = bpy.data.materials.new(f"MAT_{name}")
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    tr = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.name = "Fade"
    links = mat.node_tree.links
    links.new(tr.outputs["BSDF"], mix.inputs[1])
    links.new(em.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    cu.materials.append(mat)
    return obj, mat


def _animate(obj, mat, start, frames, rise=0.35, peak=1.0):
    end = frames
    fade = mat.node_tree.nodes["Fade"].inputs[0]
    y = obj.location.y
    for f, v, dy in ((start, 0.0, -rise), (start + 12, peak, 0.0), (end - 8, peak, 0.0), (end, 0.0, 0.0)):
        fade.default_value = v
        fade.keyframe_insert("default_value", frame=f)
        obj.location.y = y + dy
        obj.keyframe_insert("location", index=1, frame=f)
    _ease(obj)
    _ease(mat.node_tree)


def overlay(shot, frames):
    reset()
    sc = bpy.context.scene
    sc.render.film_transparent = True
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = 8
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.color_mode = "RGBA"
    cam = bpy.data.objects.new("CAM_Overlay", bpy.data.cameras.new("CAM_Overlay"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 16.0
    cam.location = (0, 0, 10)
    sc.camera = cam
    fonts = TIMELINE["fonts"]
    if shot.get("big"):
        t, tm = _text("TXT_Title", shot["title"], fonts["display"], 1.15, (1, 1, 1), (0, 2.35, 0), "CENTER")
        g, gm = _text("TXT_Tag", shot["tag"], fonts["mono"], 0.4, ACCENT, (0, 1.55, 0), "CENTER")
        _animate(t, tm, 1, frames)
        _animate(g, gm, 6, frames)
    else:
        bar_bm = bmesh.new()
        bmesh.ops.create_grid(bar_bm, x_segments=1, y_segments=1, size=0.5,
                              matrix=Matrix.Translation((-7.25, -3.25, 0)) @ Matrix.Diagonal((0.12, 1.05, 1, 1)))
        bar = _mesh_object("BAR", bar_bm)
        _, bm_mat = _text("TXT_BarMat", " ", None, 0.1, ACCENT, (0, -20, 0))
        bar.data.materials.append(bm_mat)
        band_bm = bmesh.new()
        bmesh.ops.create_grid(band_bm, x_segments=1, y_segments=1, size=0.5,
                              matrix=Matrix.Translation((-3.0, -3.45, -0.1)) @ Matrix.Diagonal((10.5, 1.5, 1, 1)))
        band = _mesh_object("BAND", band_bm)
        _, band_mat = _text("TXT_BandMat", " ", None, 0.1, (0.0, 0.0, 0.0), (0, -20, 0))
        band.data.materials.append(band_mat)
        t, tm = _text("TXT_Title", shot["title"], fonts["display"], 0.7, (1, 1, 1), (-7.0, -3.3, 0))
        g, gm = _text("TXT_Tag", shot["tag"], fonts["mono"], 0.34, ACCENT, (-7.0, -3.92, 0))
        _animate(band, band_mat, 1, frames, rise=0.0, peak=0.55)
        _animate(t, tm, 1, frames)
        _animate(g, gm, 5, frames)
        _animate(bar, bm_mat, 1, frames, rise=0.0)


# --------------------------------------------------------------------------- render

def render(out_dir, frames, still):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    os.makedirs(out_dir, exist_ok=True)
    sc.render.image_settings.file_format = "PNG"
    if still:
        sc.frame_set(max(1, frames // 2))
        sc.render.filepath = os.path.join(out_dir, "still.png")
        bpy.ops.render.render(write_still=True)
    else:
        sc.render.filepath = os.path.join(out_dir, "")
        bpy.ops.render.render(animation=True)


def main(out_dir=None, shots=None, stills=False, samples=32, scale=100):
    out_dir = out_dir or os.path.join(HERE, "build")
    done = []
    for shot in TIMELINE["shots"]:
        if shots and shot["id"] not in shots:
            continue
        frames = shot["frames"]
        look(shot["look"], frames, samples)
        bpy.context.scene.render.resolution_percentage = scale
        render(os.path.join(out_dir, "frames", shot["id"]), frames, stills)
        overlay(shot, frames)
        bpy.context.scene.render.resolution_percentage = scale
        render(os.path.join(out_dir, "overlay", shot["id"]), frames, stills)
        done.append(shot["id"])
        print(f"[video] rendered {shot['id']} ({frames} frames, stills={stills})", flush=True)
    return {"shots": done, "out_dir": out_dir}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
print(json.dumps(result), flush=True)
