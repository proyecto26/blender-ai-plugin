"""Greybox / blockout builder: floor-pivoted primitives (box, cylinder, cone, rock, ramp, stairs, light),
optional ring/line/grid layouts, and a room/corridor shell with inward normals and emissive ceiling
fixtures. Pieces are ground-snapped by raycast, share one mesh per kind+size, get box-projected UVs and
grey materials. Re-running with the same `group` replaces only the objects this script made for it.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/blockout.py", init_globals={"ARGS": {
        "group": "Cover", "pieces": [{"kind": "box", "size": [1.8, 0.6, 1.1]}],
        "layout": {"pattern": "ring", "count": 6, "radius": 4.0, "center": "SM_Crate", "face_center": True}}})["result"]

ARGS:
    group       (str)   name prefix and idempotency key (required); objects are BLK_<group>_<kind>_NN
    pieces      (list)  each {kind, size:[x,y,z], at:[x,y] | [x,y,z], rot_z (deg), name, material, color}
                        kind: box | cylinder | cone | rock | ramp | stairs | light
                        at with 2 values -> ground-snapped; name overrides the generated name
                        light: {kind:"light", type:POINT|SPOT|AREA, color, energy, at, flicker (bool)}
    layout      (dict)  {pattern: ring | line | grid, count, radius | spacing, center: [x,y] | object,
                        face_center (bool), start_deg}; repeats `pieces` cyclically over the pattern
    room        (dict)  {size:[w,l,h], at:[x,y], wall:0.2, open_ends (bool), color,
                        fixtures:{size:[x,y], spacing, color, strength, lights (bool)}}; length runs along +Y
    ground      (str)   mesh to snap onto (default: lowest surface below, ignoring this group's pieces)
    bevel       (float) bevel width for box/ramp/stairs pieces (default 0)
    collection  (str)   default "COL_Blockout"
    seed        (int)   rock shape seed (default 0)
"""
import json
import math
import random
import sys

import bmesh
import bpy
from mathutils import Vector

GREY = (0.5, 0.5, 0.5)


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _material(name, color, emission=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    bsdf = next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def _box_uvs(bm):
    """Box projection: each face takes the two axes perpendicular to its dominant normal axis."""
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        u, v = [i for i in range(3) if i != ax]
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co[u], loop.vert.co[v])


def _build(kind, size, seed):
    sx, sy, sz = size
    bm = bmesh.new()
    if kind == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    elif kind in ("cylinder", "cone"):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5,
                              radius2=0.5 if kind == "cylinder" else 0.0, depth=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    elif kind == "rock":
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5)
        rng = random.Random(seed)
        for v in bm.verts:
            v.co *= rng.uniform(0.8, 1.15)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    elif kind == "ramp":  # rises along +Y
        h = [(-sx / 2, -sy / 2, -sz / 2), (sx / 2, -sy / 2, -sz / 2), (sx / 2, sy / 2, -sz / 2),
             (-sx / 2, sy / 2, -sz / 2), (sx / 2, sy / 2, sz / 2), (-sx / 2, sy / 2, sz / 2)]
        vs = [bm.verts.new(c) for c in h]
        for f in ((0, 3, 2, 1), (0, 1, 4, 5), (2, 3, 5, 4), (1, 2, 4), (0, 5, 3)):
            bm.faces.new([vs[i] for i in f])
    elif kind == "stairs":  # steps of ~0.18 m rise along +Y
        steps = max(1, round(sz / 0.18))
        for i in range(steps):
            g = bmesh.ops.create_cube(bm, size=1.0)["verts"]
            d = sy / steps
            bmesh.ops.scale(bm, vec=(sx, sy - i * d, sz * (i + 1) / steps), verts=g)
            bmesh.ops.translate(bm, vec=(0, i * d / 2, (sz * (i + 1) / steps - sz) / 2), verts=g)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=(0, 0, -min(v.co.z for v in bm.verts)), verts=bm.verts)  # pivot on the floor
    _box_uvs(bm)
    me = bpy.data.meshes.new("tmp")
    bm.to_mesh(me)
    bm.free()
    if kind in ("cylinder", "cone", "rock"):
        me.shade_smooth()
    return me


def _mesh(kind, size, seed):
    name = f"ME_BLK_{kind}_" + "x".join(f"{s:g}" for s in size) + (f"_s{seed}" if kind == "rock" else "")
    me = bpy.data.meshes.get(name)
    if me is None:
        me = _build(kind, size, seed)
        me.name = name
    return me


def _ground_z(xy, ground, skip):
    dg = bpy.context.evaluated_depsgraph_get()
    down = Vector((0, 0, -1))
    if ground:
        inv = ground.matrix_world.inverted()
        ok, loc, _n, _i = ground.evaluated_get(dg).ray_cast(inv @ Vector((xy[0], xy[1], 1000.0)), inv.to_3x3() @ down)
        return (ground.matrix_world @ loc).z if ok else 0.0
    z, origin = None, Vector((xy[0], xy[1], 1000.0))
    for _ in range(64):
        ok, loc, _n, _i, hit, _m = bpy.context.scene.ray_cast(dg, origin, down)
        if not ok:
            break
        if hit.get("blockout") not in skip:
            z = loc.z
        origin = loc + down * 1e-3
    return z if z is not None else 0.0


def _center(c):
    if isinstance(c, str):
        o = bpy.data.objects[c]
        pts = [o.matrix_world @ Vector(p) for p in o.bound_box]
        return Vector((sum(p.x for p in pts) / 8, sum(p.y for p in pts) / 8))
    return Vector((c[0], c[1])) if c else Vector((0, 0))


def _expand(pieces, layout):
    if not layout:
        return [dict(p) for p in pieces]
    pat, n = layout.get("pattern", "ring"), int(layout.get("count", len(pieces)))
    c = _center(layout.get("center"))
    out = []
    for i in range(n):
        p = dict(pieces[i % len(pieces)])
        if pat == "ring":
            a = math.radians(layout.get("start_deg", 0)) + 2 * math.pi * i / n
            p["at"] = [c.x + math.cos(a) * layout["radius"], c.y + math.sin(a) * layout["radius"]]
            if layout.get("face_center"):  # local +Y towards the centre
                p["rot_z"] = math.degrees(a) + 90
        elif pat == "line":
            p["at"] = [c.x, c.y + i * layout["spacing"]]
        elif pat == "grid":
            k = math.ceil(math.sqrt(n))
            p["at"] = [c.x + (i % k) * layout["spacing"], c.y + (i // k) * layout["spacing"]]
        else:
            raise ValueError(f"unknown pattern {pat!r}")
        if p.get("name"):
            p["name"] = f"{p['name']}_{i + 1}"
        out.append(p)
    return out


def _flicker(light):
    """Keyframe energy once and add a Noise F-modifier (Blender 5 layered actions: fcurves live in a channelbag)."""
    from bpy_extras.anim_utils import action_get_channelbag_for_slot
    light.keyframe_insert("energy", frame=1)
    ad = light.animation_data
    fc = action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves.find("energy")
    mod = fc.modifiers.new("NOISE")
    mod.scale, mod.strength = 4.0, light.energy * 0.6


def main(group, pieces=None, layout=None, room=None, ground=None, bevel=0.0, collection="COL_Blockout", seed=0):
    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection)
        bpy.context.scene.collection.children.link(col)
    for o in [o for o in bpy.data.objects if o.get("blockout") == group]:
        data = o.data
        bpy.data.objects.remove(o)
        if isinstance(data, bpy.types.Light) and data.users == 0:
            bpy.data.lights.remove(data)
    gnd = bpy.data.objects[ground] if ground else None
    made, counts = [], {}

    def link(obj, kind, name=None):
        counts[kind] = counts.get(kind, 0) + 1
        obj.name = name or f"BLK_{group}_{kind}_{counts[kind]:02d}"
        obj["blockout"] = group
        col.objects.link(obj)
        made.append(obj)
        return obj

    for i, p in enumerate(_expand(pieces or [], layout)):
        kind, at = p["kind"], list(p.get("at", [0, 0]))
        z = at[2] if len(at) == 3 else _ground_z(at, gnd, {group})
        if kind == "light":
            ld = bpy.data.lights.new(f"LT_BLK_{group}_{i}", p.get("type", "POINT"))
            ld.color, ld.energy = p.get("color", (1.0, 0.55, 0.2)), p.get("energy", 150.0)
            obj = link(bpy.data.objects.new("tmp", ld), "light", p.get("name"))
            obj.location = (at[0], at[1], z)
            if p.get("flicker"):
                _flicker(ld)
            continue
        size = p.get("size", [1, 1, 1])
        me = _mesh(kind, size, seed + i if kind == "rock" else seed)
        mat = bpy.data.materials.get(p["material"]) if p.get("material") else _material(
            "MAT_Blockout_" + "".join(f"{round(c * 9):d}" for c in p.get("color", GREY)), p.get("color", GREY))
        if not me.materials:
            me.materials.append(mat)
        obj = link(bpy.data.objects.new("tmp", me), kind, p.get("name"))
        if p.get("material") or p.get("color"):
            obj.material_slots[0].link = "OBJECT"
            obj.material_slots[0].material = mat
        obj.location = (at[0], at[1], z)
        obj.rotation_euler.z = math.radians(p.get("rot_z", 0.0))
        if bevel and kind in ("box", "ramp", "stairs"):
            b = obj.modifiers.new("Bevel", "BEVEL")
            b.width, b.segments, b.limit_method = bevel, 2, "ANGLE"

    if room:
        w, length, h = room["size"]
        t = room.get("wall", 0.2)
        at = room.get("at", [0, 0])
        z0 = at[2] if len(at) == 3 else _ground_z(at, gnd, {group})
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(w, length, h), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0, length / 2, h / 2), verts=bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if room.get("open_ends", True):
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.y) > 0.9], context="FACES")
        bmesh.ops.reverse_faces(bm, faces=bm.faces)  # normals point inward: the camera is inside
        _box_uvs(bm)
        me = bpy.data.meshes.new(f"ME_BLK_{group}_room")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(_material(f"MAT_Blockout_{group}_Room", room.get("color", (0.72, 0.66, 0.42))))
        shell = link(bpy.data.objects.new("tmp", me), "room")
        shell.location = (at[0], at[1], z0)
        if t:
            s = shell.modifiers.new("Thickness", "SOLIDIFY")
            s.thickness, s.offset = t, 1.0  # grows outward from the inward-facing shell
        fx = room.get("fixtures")
        if fx:
            fw, fl = fx.get("size", [0.6, 1.2])
            spacing = fx.get("spacing", 2.4)
            fme = bpy.data.meshes.get(f"ME_BLK_{group}_fixture") or bpy.data.meshes.new(f"ME_BLK_{group}_fixture")
            fme.clear_geometry()
            fme.from_pydata([(-fw / 2, -fl / 2, 0), (-fw / 2, fl / 2, 0), (fw / 2, fl / 2, 0), (fw / 2, -fl / 2, 0)],
                            [], [(0, 1, 2, 3)])  # normal faces down (-Z)
            fme.materials.clear()
            fme.materials.append(_material(f"MAT_Blockout_{group}_Fixture", fx.get("color", (1.0, 0.97, 0.85)),
                                           fx.get("strength", 8.0)))
            n = max(1, int(length // spacing))
            for k in range(n):
                y = at[1] + (k + 0.5) * length / n
                f = link(bpy.data.objects.new("tmp", fme), "fixture")
                f.location = (at[0], y, z0 + h - 0.01)
                if fx.get("lights", True):
                    ld = bpy.data.lights.new(f"LT_BLK_{group}_{k}", "AREA")
                    ld.shape, ld.size, ld.size_y = "RECTANGLE", fw, fl
                    ld.energy, ld.color = fx.get("energy", 60.0), fx.get("color", (1.0, 0.97, 0.85))
                    lo = link(bpy.data.objects.new("tmp", ld), "light")
                    lo.location = (at[0], y, z0 + h - 0.05)

    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    centres = [o.matrix_world.translation for o in meshes if o.get("blockout") == group and "fixture" not in o.name]
    gaps = [(a - b).length for i, a in enumerate(centres) for b in centres[i + 1:]]
    return {"group": group, "collection": col.name, "objects": [o.name for o in made],
            "counts": counts, "min_spacing": round(min(gaps), 3) if gaps else None,
            "dimensions": {o.name: [round(v, 3) for v in o.dimensions] for o in meshes[:24]}}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
