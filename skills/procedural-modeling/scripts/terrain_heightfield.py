"""Build a seeded heightfield terrain mesh, optionally flattened into a corridor along a curve (a road bed).

Noise comes from `mathutils.noise.fractal`. That function is not controlled by `noise.seed_set`, so the seed
is turned into a sampling offset instead: the same seed always gives the same mesh, a different seed another.
Creates one new object and touches nothing else.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/terrain_heightfield.py", init_globals={"ARGS": {
        "name": "GEO_Terrain", "size": 60, "resolution": 129, "seed": 7, "height": 6,
        "corridor": {"curve": "CRV_Road", "half_width": 3, "falloff": 6}}})["result"]

ARGS:
    name        (str)   new object (and mesh) name (default "GEO_Terrain"); refused if the object exists unless replace
    size        (float) side length in meters, centred on `center` (default 50)
    resolution  (int)   vertices per side, 2..513 (default 65)
    seed        (int)   noise seed (default 0)
    height      (float) noise amplitude in meters (default 5)
    frequency   (float) noise features per meter, roughly 1 / feature size (default 0.04)
    octaves     (int)   fractal octaves 1..8 (default 5)
    center      (list[3]) world position of the terrain centre (default [0, 0, 0])
    corridor    (dict|None) flatten along a curve object:
                curve (str) curve object name; half_width (float) fully flat half width in m (default 3);
                falloff (float) blend distance outside the flat part in m (default 5); offset (float) lowers the
                bed below the curve by this many metres (default 0). Heights inside half_width equal the curve
                height (minus offset); the curve is read in world space and only its XY position and Z are used. Every spline
                of the curve object is flattened (reported as `splines`); a branching curve is refused.
    collection  (str|None) collection to link into (default: the scene collection)
    replace     (bool)  replace the mesh of an existing object of that name (default False = refuse); refused when that
                object has a parent, scale, rotation or delta transform, a rigid body, or a deforming modifier (Displace,
                Armature, Lattice, Curve, Hook, Shrinkwrap, Simple Deform, Wave, Geometry Nodes, Subdivision Surface, Multires, ...), because
                vertex Z is world height and those move the vertices after the fact
"""
import json
import random
import sys

import bpy
import numpy as np
from mathutils import Vector, noise


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


DEFORMING = {"DISPLACE", "ARMATURE", "LATTICE", "CURVE", "HOOK", "SHRINKWRAP", "SIMPLE_DEFORM", "WAVE", "CAST", "WARP",
             "MESH_DEFORM", "SURFACE_DEFORM", "LAPLACIANDEFORM", "CORRECTIVE_SMOOTH", "SMOOTH", "LAPLACIANSMOOTH", "OCEAN",
             "VOLUME_DISPLACE", "NODES", "SOFT_BODY", "CLOTH", "EXPLODE", "SCREW", "MESH_CACHE", "MESH_SEQUENCE_CACHE",
             # subdivision converges on a smoothed limit surface: peaks and pits sit off the stored vertex heights
             "SUBSURF", "MULTIRES"}


def _curve_polylines(name):
    """World-space polylines (each N x 3, in curve order) of the evaluated curve: one per connected chain, so a
    curve object with several splines yields several. A cyclic chain gets its closing segment."""
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "CURVE":
        raise ValueError(f"corridor curve {name!r} is not a curve object")
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    mesh = ev.to_mesh()
    try:
        pts = np.array([(obj.matrix_world @ v.co)[:] for v in mesh.vertices], dtype=np.float64)
        chains = _chains(mesh)
    finally:
        ev.to_mesh_clear()
    lines = []
    for order, closed in chains:
        if len(order) < 2:
            continue  # a lone point (a one-point spline) has no direction to flatten along
        line = pts[order]
        lines.append(np.vstack([line, line[:1]]) if closed else line)  # a cyclic chain needs its closing segment
    if not lines:
        raise ValueError(f"curve {name!r} evaluates to fewer than two points")
    return lines


def _chains(mesh):
    """Every connected chain of the evaluated edges as (vertex indices in walk order, closed). Nothing is dropped:
    a vertex that branches (not possible for splines) is refused rather than silently skipped."""
    adj = {}
    for e in mesh.edges:
        a, b = e.vertices
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj:
        return [(list(range(len(mesh.vertices))), False)]
    if any(len(n) > 2 for n in adj.values()):
        raise ValueError("corridor curve branches (a vertex joins more than two segments); use plain splines")
    chains, seen = [], set()
    ends = sorted(v for v, n in adj.items() if len(n) == 1)
    for start in ends + sorted(adj):  # open chains from an end first, then whatever is left is a closed loop
        if start in seen:
            continue
        closed = len(adj[start]) == 2 and start not in ends
        order, cur = [start], start
        seen.add(start)
        while True:
            nxt = next((n for n in adj[cur] if n not in seen), None)
            if nxt is None:
                break
            order.append(nxt)
            seen.add(nxt)
            cur = nxt
        chains.append((order, closed))
    return chains


def _nearest_on_polyline(px, py, lines):
    """For every (px, py): distance in XY to the nearest of the polylines and that polyline's Z at the nearest point."""
    best_d = np.full(px.shape, np.inf)
    best_z = np.zeros(px.shape)
    for a, b in (seg for pts in lines for seg in zip(pts[:-1], pts[1:])):
        abx, aby = b[0] - a[0], b[1] - a[1]
        den = abx * abx + aby * aby
        t = np.zeros(px.shape) if den < 1e-12 else np.clip(((px - a[0]) * abx + (py - a[1]) * aby) / den, 0.0, 1.0)
        cx, cy = a[0] + t * abx, a[1] + t * aby
        d = np.hypot(px - cx, py - cy)
        closer = d < best_d
        best_d = np.where(closer, d, best_d)
        best_z = np.where(closer, a[2] + t * (b[2] - a[2]), best_z)
    return best_d, best_z


def main(name="GEO_Terrain", size=50.0, resolution=65, seed=0, height=5.0, frequency=0.04, octaves=5,
         center=(0.0, 0.0, 0.0), corridor=None, collection=None, replace=False):
    resolution, octaves = int(resolution), int(octaves)
    if not 2 <= resolution <= 513:
        raise ValueError("resolution must be 2..513")
    if not 1 <= octaves <= 8:
        raise ValueError("octaves must be 1..8")
    if size <= 0:
        raise ValueError("size must be > 0")
    existing = bpy.data.objects.get(name)
    if existing is not None and not replace:
        raise ValueError(f"object {name!r} exists; pass replace=true to give it a new mesh (a mesh shared with other objects is left alone; the object gets its own)")
    if existing is not None and existing.type != "MESH":
        raise ValueError(f"object {name!r} exists and is not a mesh")
    if existing is not None:
        if existing.mode == "EDIT" or existing.data.is_editmode:
            raise ValueError(f"object {name!r} is in Edit Mode: leave Edit Mode (Tab) and run again; nothing was changed.")
        if existing.data.shape_keys is not None:
            raise ValueError(f"mesh of {name!r} has shape keys: replacing its geometry would leave stale keys, so nothing was "
                             "changed. Remove the shape keys (or delete the object) and run again.")
        # a transform that reasserts later (keyframes, drivers, constraints) cannot be caught by comparing the current matrix
        ad = existing.animation_data
        if ad is not None and (ad.action is not None or len(ad.drivers) or len(ad.nla_tracks)):
            what = ("an action (keyframes)" if ad.action is not None
                    else "a driver" if len(ad.drivers) else "an NLA track (a pushed-down action)")
            raise ValueError(f"object {name!r} has {what}: it would move the terrain again after replace writes world-space "
                             "heights, so nothing was changed. Remove the animation data (or delete the object) and run again.")
        if len(existing.constraints):
            raise ValueError(f"object {name!r} has a constraint ({existing.constraints[0].type}): it would move the terrain "
                             "after replace writes world-space heights, so nothing was changed. Remove the constraints "
                             "(or delete the object) and run again.")
        if existing.rigid_body is not None:
            raise ValueError(f"object {name!r} has a rigid body: the simulation moves it, so vertex Z no longer equals world "
                             "height. Remove the rigid body (or delete the object) and run again; nothing was changed.")
        deform = next((m for m in existing.modifiers if m.type in DEFORMING), None)
        if deform is not None:
            raise ValueError(f"object {name!r} has a {deform.type} modifier ({deform.name!r}): it changes where the vertices end "
                             "up, so vertex Z no longer equals world height. Remove the modifier (or delete the object) and "
                             "run again; nothing was changed.")
        bpy.context.view_layer.update()
        mw = existing.matrix_world
        linear_off = max(abs(mw[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3)) > 1e-6
        moved_off = (mw.translation - existing.location).length > 1e-6  # delta location, a constraint, a parent offset
        bad = [what for what, off in (("a parent", existing.parent is not None),
                                      ("a world transform other than a plain move (scale, rotation, delta transform "
                                       "or constraint)", linear_off or moved_off)) if off]
        if bad:
            raise ValueError(f"object {name!r} has {', '.join(bad)}: replace writes world-space heights and resets only the "
                             "location, so the terrain would land at the wrong height. Clear the parent, scale, rotation, "
                             "delta transforms and constraints (or delete the object) and run again.")
    target_coll = bpy.data.collections.get(collection) if collection else bpy.context.scene.collection
    if target_coll is None:
        raise ValueError(f"collection {collection!r} not found")
    rng = random.Random(int(seed))
    off = Vector((rng.uniform(-1000, 1000), rng.uniform(-1000, 1000), rng.uniform(-1000, 1000)))
    cx, cy, cz = center
    xs = np.linspace(-size / 2, size / 2, resolution)
    gx, gy = np.meshgrid(xs, xs)
    wx, wy = gx + cx, gy + cy
    z = np.empty(gx.shape)
    for j in range(resolution):
        for i in range(resolution):
            p = Vector((wx[j, i] * frequency, wy[j, i] * frequency, 0.0)) + off
            z[j, i] = noise.fractal(p, 1.0, 2.0, octaves, noise_basis="PERLIN_ORIGINAL")
    z = z * height + cz
    info = None
    if corridor:
        lines = _curve_polylines(corridor["curve"])
        half = float(corridor.get("half_width", 3.0))
        fall = max(1e-6, float(corridor.get("falloff", 5.0)))
        bed = float(corridor.get("offset", 0.0))
        dist, cz_curve = _nearest_on_polyline(wx, wy, lines)
        w = np.clip(1.0 - (dist - half) / fall, 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)  # smoothstep; exactly 1 inside half_width
        z = z * (1.0 - w) + (cz_curve - bed) * w
        info = {"curve": corridor["curve"], "half_width": half, "falloff": fall, "offset": bed,
                "splines": len(lines),
                "curve_points": int(sum(len(p) for p in lines)), "flat_vertices": int((dist <= half).sum())}
    # x/y are relative to the object origin, which sits at (center.x, center.y, 0); z is already world height
    verts = [(float(gx[j, i]), float(gy[j, i]), float(z[j, i])) for j in range(resolution)
             for i in range(resolution)]
    faces = [(j * resolution + i, j * resolution + i + 1, (j + 1) * resolution + i + 1, (j + 1) * resolution + i)
             for j in range(resolution - 1) for i in range(resolution - 1)]
    if existing is not None:
        obj = existing
        if existing.data.users > 1:  # linked duplicates: never edit a mesh another object uses
            mesh = bpy.data.meshes.new(name)
            for mat in existing.data.materials:
                mesh.materials.append(mat)
            existing.data = mesh
        else:
            mesh = existing.data
            mesh.clear_geometry()
    else:
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        target_coll.objects.link(obj)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj.location = (cx, cy, 0.0)
    return {"object": obj.name, "vertices": len(verts), "faces": len(faces), "seed": int(seed),
            "z_min": float(z.min()), "z_max": float(z.max()), "corridor": info,
            "note": "Vertex Z is world height; the object origin is at (center.x, center.y, 0)."}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
