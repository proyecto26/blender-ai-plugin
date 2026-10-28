"""HD-2D sprite: a vertical plane carrying a pixel-art image (nearest-neighbour, alpha cut-out),
pivot at its feet, standing on the ground (raycast) and turned on Z to face the camera.
Without an image path it generates a placeholder pixel character so the setup is testable.
Pair with camera-cinematography's camera_rig.py for the tilt-shift DoF.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/sprite_billboard.py", init_globals={"ARGS": {
        "name": "SPR_Hero", "location": [0, 0], "height": 1.6}})["result"]

ARGS:
    name      (str)   object name (default "SPR_Hero")
    image     (str)   path to a PNG sprite; omitted -> generated 16x16 placeholder
    location  (list)  [x, y] ground position (default [0, 0])
    height    (float) sprite height in metres (default 1.6); width follows the image aspect
    camera    (str)   camera to face (default scene camera)
    pixels    (int)   placeholder resolution (default 16)
    ground    (str)   mesh to stand on (default: lowest surface under the location)
"""
import json
import math
import sys

import bpy
from mathutils import Vector


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _placeholder(name, n):
    img = bpy.data.images.get(name) or bpy.data.images.new(name, n, n, alpha=True)
    px = []
    for y in range(n):
        for x in range(n):
            body = abs(x - n / 2 + 0.5) < n * 0.22 and n * 0.1 <= y < n * 0.62
            head = (x - n / 2 + 0.5) ** 2 + (y - n * 0.75) ** 2 < (n * 0.17) ** 2
            if head:
                px += [0.95, 0.78, 0.62, 1.0]
            elif body:
                px += [0.2, 0.35, 0.8, 1.0]
            else:
                px += [0.0, 0.0, 0.0, 0.0]
    img.pixels.foreach_set(px)
    img.pack()
    return img


def _material(name, img):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"  # crisp pixels
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.surface_render_method = "DITHERED"
    return mat


def _ground_z(xy, ground, sprite):
    """Z of *ground* under xy; without *ground*, the lowest surface hit (so props on top are skipped)."""
    dg = bpy.context.evaluated_depsgraph_get()
    down = Vector((0, 0, -1))
    if ground:
        g = bpy.data.objects[ground]
        inv = g.matrix_world.inverted()
        ok, loc, _n, _i = g.evaluated_get(dg).ray_cast(inv @ Vector((xy[0], xy[1], 1000.0)), inv.to_3x3() @ down)
        return (g.matrix_world @ loc).z if ok else 0.0
    z, origin = None, Vector((xy[0], xy[1], 1000.0))
    for _ in range(32):
        ok, loc, _n, _i, hit_obj, _m = bpy.context.scene.ray_cast(dg, origin, down)
        if not ok:
            break
        if hit_obj != sprite:
            z = loc.z
        origin = loc + down * 1e-3
    return z if z is not None else 0.0


def main(name="SPR_Hero", image=None, location=(0, 0), height=1.6, camera=None, pixels=16, ground=None):
    img = bpy.data.images.load(image, check_existing=True) if image else _placeholder(f"IMG_{name}", pixels)
    w_px, h_px = img.size
    width = height * w_px / h_px

    me = bpy.data.meshes.get(f"ME_{name}") or bpy.data.meshes.new(f"ME_{name}")
    me.clear_geometry()
    hw = width / 2
    me.from_pydata([(-hw, 0, 0), (hw, 0, 0), (hw, 0, height), (-hw, 0, height)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = co
    me.materials.clear()
    me.materials.append(_material(f"MAT_{name}", img))

    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
    obj.data = me

    obj.location = (location[0], location[1], _ground_z(location, ground, obj))

    cam = bpy.data.objects.get(camera) if camera else bpy.context.scene.camera
    if cam:
        d = cam.matrix_world.translation - obj.location
        obj.rotation_euler = (0.0, 0.0, math.atan2(d.y, d.x) - math.pi / 2)  # plane normal is -Y
    return {"object": obj.name, "image": img.name, "size_px": [w_px, h_px],
            "size_m": [round(width, 3), height], "location": [round(v, 3) for v in obj.location],
            "facing": cam.name if cam else None, "interpolation": "Closest"}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
