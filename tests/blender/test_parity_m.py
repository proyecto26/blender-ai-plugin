"""Headless Blender tests for batch M of iteration 12: film-production/flicker_check.py and
blender-mcp-workflow/scene_snapshot.py. Synthesises frame sequences with known flicker and a scratch .blend, runs the
scripts, asserts on the results and writes <out_dir>/parity_m_report.json (passed / total / failed). A crash is recorded
as a failed check, so the report always exists.

    blender -b --factory-startup --python tests/blender/test_parity_m.py -- '{"out_dir": "/tmp/parity_m"}'
"""
import json
import os
import runpy
import sys
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "skills"))
W, H = 128, 64


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def run(skill, script, args):
    path = os.path.join(SKILLS, skill, "scripts", script)
    return runpy.run_path(path, init_globals={"ARGS": args}, run_name="__skill_test__")["result"]


def save_gray(path, arr):
    """arr: (h, w) floats 0-1, stored as raw values in an 8-bit PNG (Non-Color, so nothing is converted)."""
    h, w = arr.shape
    img = bpy.data.images.new("tmp_flicker_fixture", w, h, alpha=True)
    try:
        img.colorspace_settings.name = "Non-Color"
        rgba = np.ones((h, w, 4), dtype=np.float32)
        rgba[..., :3] = np.clip(arr[::-1], 0, 1)[..., None]
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def write_seq(folder, frames, pattern="f_{:02d}.png"):
    os.makedirs(folder, exist_ok=True)
    paths = []
    for i, fr in enumerate(frames):
        p = os.path.join(folder, pattern.format(i))
        save_gray(p, fr)
        paths.append(p)
    return paths


def noise_world(width, seed):
    """Lightly smoothed noise, values about 0.25..0.65: a texture with no repeats."""
    rng = np.random.default_rng(seed)
    t = rng.random((H + 2, width + 2)).astype(np.float32)
    s = sum(t[dy:dy + H, dx:dx + width] for dy in range(3) for dx in range(3)) / 9.0
    return 0.05 + 1.2 * (s - s.min()) / (s.max() - s.min()) * 0.5


def pan(world, n, speed):
    return [world[:, t * speed:t * speed + W].copy() for t in range(n)]


def stripes_world(width, period=8, lo=0.1, hi=0.9, ramp=0.0):
    x = np.arange(width)
    row = np.where((x // (period // 2)) % 2 == 0, hi, lo).astype(np.float32)
    if ramp:
        row = lo + (row - lo) * 0.3 + ramp * x / width
    return np.tile(row, (H, 1)).astype(np.float32)


def bump(frame, x0, y0, x1, y1, d):
    out = frame.copy()
    out[y0:y1, x0:x1] += d
    return out


def run_flicker(out_dir, check):
    base = os.path.join(out_dir, "flicker")
    n_img = len(bpy.data.images)
    N = 9

    # fixture sanity: the byte round trip is faithful, and the naive second difference WOULD fail the stripes pan
    stripes = stripes_world(W + N * 3 + 8)
    s_frames = pan(stripes, N, 3)
    naive = max(float(np.abs(s_frames[t - 1] - 2 * s_frames[t] + s_frames[t + 1]).max()) for t in range(1, N - 1))
    # (this one is a PIXELWISE naive metric; the block-mean case needs a period that does not divide the block, see
    # run_review_round1)
    check("fixture: naive pixelwise second difference on a stripe pan is large (the case it gets wrong)", naive > 0.5, naive)

    # 1. static scene, local flicker in frame 4 over one block-aligned region
    w0 = noise_world(W, 1)
    fr = [w0.copy() for _ in range(N)]
    fr[4] = bump(fr[4], 32, 16, 64, 48, 0.15)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "local"), fr)})
    ev = r["events"]
    check("local flicker: verdict flicker", r["verdict"] == "flicker", r["verdict"])
    check("local flicker: one event at frame 4, kind local", len(ev) == 1 and ev[0]["frame"] == 4 and ev[0]["kind"] == "local",
          ev[:1])
    check("local flicker: region is the flickering box", ev and ev[0]["region_px"] == [32, 16, 64, 48], ev[:1])
    check("local flicker: positive deviation (brighter than neighbours)", ev and ev[0]["mean_deviation"] > 0.1, ev[:1])

    # 2. a clean noise pan passes
    world = noise_world(W + N * 3 + 8, 2)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "pan"), pan(world, N, 3))})
    check("clean pan: verdict pass, no events", r["verdict"] == "pass" and not r["events"], (r["verdict"], r["events"][:1]))
    check("clean pan: most blocks measured", r["measured_share"] > 0.6, r["measured_share"])

    # 3. constant-speed pan over high-contrast stripes passes; stripes are periodic but equally bright
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "stripes"), s_frames)})
    check("stripe pan: verdict pass (naive metric would flag it)", r["verdict"] == "pass" and not r["events"],
          (r["verdict"], r["events"][:1]))
    check("stripe pan: ambiguity is harmless when rivals have equal brightness", r["not_measured"]["ambiguous"] == 0,
          r["not_measured"])

    # 4. flicker inside a panning shot is still found (box fixed in frame 4's own coordinates)
    fr = pan(world, N, 2)
    fr[4] = bump(fr[4], 48, 32, 80, 64, 0.15)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "pan_flicker"), fr)})
    ev = r["events"]
    check("flicker in a pan: detected at frame 4", r["verdict"] == "flicker" and len(ev) == 1 and ev[0]["frame"] == 4,
          (r["verdict"], ev[:1]))
    check("flicker in a pan: region is the flickering box", ev and ev[0]["region_px"] == [48, 32, 80, 64], ev[:1])

    # 5. a global exposure pop is reported as such
    fr = pan(world, N, 2)
    fr[4] = fr[4] + 0.1
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "pop"), fr)})
    ev = r["events"]
    check("exposure pop: global_exposure at frame 4",
          len(ev) == 1 and ev[0]["frame"] == 4 and ev[0]["kind"] == "global_exposure", ev[:1])

    # 6. an occluded / unmatched region is not_measured, counted, and never scored as a pass or as flicker
    rng = np.random.default_rng(9)
    fr = [w0.copy() for _ in range(N)]
    fr[4][16:48, 16:48] = 0.2 + 0.6 * rng.random((32, 32)).astype(np.float32)  # something enters for one frame
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "occluded"), fr)})
    pf = {p["frame"]: p for p in r["per_frame"]}
    check("occlusion: its 4 blocks are not_measured (high_residual) in frame 4", pf[4]["not_measured"]["high_residual"] >= 4,
          pf[4]["not_measured"])
    check("occlusion: counted in the output total", r["not_measured"]["high_residual"] >= 4 and r["not_measured"]["blocks"] >= 4,
          r["not_measured"])
    check("occlusion: those blocks are not scored (no event, measured < total in frame 4)",
          not r["events"] and pf[4]["measured"] <= r["total_blocks"] // r["evaluated_frames"] - 4, (r["events"][:1], pf[4]))

    # 7. motion faster than the window: not_measured, verdict inconclusive, never pass
    fast_world = noise_world(W + N * 12 + 8, 3)
    paths = write_seq(os.path.join(base, "fast"), pan(fast_world, N, 12))
    r = run("film-production", "flicker_check.py", {"paths": paths, "max_motion_px": 4})
    check("fast motion (12px, window 4): inconclusive, not pass", r["verdict"] == "inconclusive", r["verdict"])
    check("fast motion: nearly everything counted as high_residual",
          r["not_measured"]["high_residual"] > 0.8 * r["total_blocks"], r["not_measured"])
    r = run("film-production", "flicker_check.py", {"paths": paths, "max_motion_px": 16})
    check("fast motion inside a wide enough window: pass", r["verdict"] == "pass" and not r["events"], r["verdict"])
    fr = pan(fast_world, N, 12)
    fr[4] = bump(fr[4], 48, 16, 80, 48, 0.15)
    paths = write_seq(os.path.join(base, "fast_flicker"), fr)
    r = run("film-production", "flicker_check.py", {"paths": paths, "max_motion_px": 4})
    check("fast motion + real flicker, window too small: still not a pass", r["verdict"] != "pass", r["verdict"])
    r = run("film-production", "flicker_check.py", {"paths": paths, "max_motion_px": 16})
    check("fast motion + real flicker, wide window: detected at frame 4",
          r["verdict"] == "flicker" and r["events"][0]["frame"] == 4, (r["verdict"], r["events"][:1]))

    # 8. periodic pattern whose repeats differ in brightness: ambiguous, not measured
    ramp = stripes_world(W + N * 3 + 8, ramp=0.5)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "ramp"), pan(ramp, N, 3))})
    check("periodic + brightness ramp: ambiguous blocks are counted and not scored",
          r["not_measured"]["ambiguous"] > 0 and not r["events"], (r["verdict"], r["not_measured"]))

    # 9. folder input is read in natural order (f_10 after f_9) and reports the right file
    fr = [w0.copy() for _ in range(12)]
    fr[9] = bump(fr[9], 0, 0, 32, 32, 0.15)
    folder = os.path.join(base, "natural")
    write_seq(folder, fr, "shot_{}.png")
    r = run("film-production", "flicker_check.py", {"dir": folder})
    check("dir input, natural order: event at frame 9 = shot_9.png",
          len(r["events"]) == 1 and r["events"][0]["frame"] == 9 and r["events"][0]["file"] == "shot_9.png", r["events"][:1])

    # 10. bad input, and no leaked images
    def raises(fn):
        try:
            fn()
        except ValueError as exc:
            return str(exc)
        return None
    check("two frames refused", raises(lambda: run("film-production", "flicker_check.py", {"paths": paths[:2]})) is not None)
    check("paths and dir together refused",
          raises(lambda: run("film-production", "flicker_check.py", {"paths": paths, "dir": folder})) is not None)
    check("no images leaked", len(bpy.data.images) == n_img, f"{n_img} -> {len(bpy.data.images)}")


def state_of_objects():
    return {o.name: (tuple(round(v, 6) for row in o.matrix_world for v in row), o.select_get()) for o in bpy.data.objects}


def run_snapshot(out_dir, check):
    base = os.path.join(out_dir, "snap")
    os.makedirs(base, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name, loc in (("A", (0, 0, 0)), ("B", (3, 0, 0)), ("C", (3, 2, 0))):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.active_object.name = name
    bpy.data.objects["C"].parent = bpy.data.objects["B"]
    bpy.data.objects["C"].matrix_parent_inverse = bpy.data.objects["B"].matrix_world.inverted()
    work = os.path.join(base, "work.blend")
    bpy.ops.wm.save_as_mainfile(filepath=work)
    snaps = os.path.join(base, "snapshots")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731

    # a dirty file: an undo push marks it modified, as an edit in the open window does
    bpy.ops.ed.undo_push(message="edit")
    dirty_before = bpy.data.is_dirty
    check("fixture: the file is dirty before save (so a changed dirty state would show)", dirty_before is True, dirty_before)
    objs_before = state_of_objects()
    r = snap(action="save", dir=snaps, name="s1")
    check("save: wrote .blend and manifest", os.path.getsize(r["blend"]) > 0 and os.path.exists(r["manifest"]), r)
    check("save: open file path unchanged", os.path.normcase(bpy.data.filepath) == os.path.normcase(work), bpy.data.filepath)
    check("save: dirty state unchanged (dirty stays dirty)", bpy.data.is_dirty == dirty_before, bpy.data.is_dirty)
    check("save: objects, transforms and selection unchanged", state_of_objects() == objs_before)
    manifest = json.load(open(r["manifest"], encoding="utf-8"))
    check("save: manifest lists the 3 objects with hashes",
          sorted(manifest["objects"]) == ["A", "B", "C"] and all("mesh_hash" in v for v in manifest["objects"].values()))

    # right after a real save: whatever the dirty flag says (headless Blender may report either), a snapshot keeps it
    bpy.ops.wm.save_as_mainfile(filepath=work)
    dirty_saved = bpy.data.is_dirty
    snap(action="save", dir=snaps, name="s_clean")
    check("save right after File > Save: dirty flag and path unchanged",
          bpy.data.is_dirty == dirty_saved and os.path.normcase(bpy.data.filepath) == os.path.normcase(work),
          (dirty_saved, bpy.data.is_dirty, bpy.data.filepath))

    def raises(**kw):
        try:
            snap(**kw)
        except ValueError as exc:
            return str(exc)
        return None
    check("save: existing name refused", "already exists" in (raises(action="save", dir=snaps, name="s1") or ""))
    check("save: path-like name refused", raises(action="save", dir=snaps, name="../evil") is not None)
    check("list: read-only, finds s1 and s_clean",
          [s["name"] for s in snap(action="list", dir=snaps)["snapshots"]] == ["s1", "s_clean"]
          or sorted(s["name"] for s in snap(action="list", dir=snaps)["snapshots"]) == ["s1", "s_clean"])
    check("default dir is <file folder>/snapshots", os.path.normcase(snap(action="list")["dir"]) == os.path.normcase(os.path.normpath(os.path.join(base, "snapshots"))))

    # edit the scene: move B (C follows), edit C's mesh, delete A, add D
    B, Cc = bpy.data.objects["B"], bpy.data.objects["C"]
    B.location.x += 1.0
    Cc.data.vertices[0].co.x += 0.5
    bpy.data.objects.remove(bpy.data.objects["A"])
    D = bpy.data.objects.new("D", None)
    bpy.context.scene.collection.objects.link(D)
    bpy.context.view_layer.update()
    path0, dirty0 = bpy.data.filepath, bpy.data.is_dirty
    d = snap(action="diff", dir=snaps, a="s1")
    ch = {c["name"]: c for c in d["changed"]}
    check("diff: added D, removed A", d["added"] == ["D"] and d["removed"] == ["A"], (d["added"], d["removed"]))
    check("diff: B moved by about 1, mesh not changed",
          "B" in ch and abs(ch["B"]["transform_delta"] - 1.0) < 1e-3 and "mesh_changed" not in ch["B"], ch.get("B"))
    check("diff: C mesh changed", "C" in ch and ch["C"].get("mesh_changed") is True, ch.get("C"))
    check("diff: nothing flagged for an untouched snapshot pair",
          snap(action="diff", dir=snaps, a="s1", b="s_clean") == {"action": "diff", "a": "s1", "b": "s_clean", "added": [],
                                                                  "removed": [], "changed": [], "unchanged": 3})
    check("diff and list: path and dirty state untouched", bpy.data.filepath == path0 and bpy.data.is_dirty == dirty0)

    # restore: A (deleted) comes back; B (still present, modified) comes back as a copy; nothing is removed
    before = set(o.name for o in bpy.data.objects)
    b_loc = tuple(bpy.data.objects["B"].location)
    r = snap(action="restore", dir=snaps, name="s1", objects=["A", "B"])
    after = set(o.name for o in bpy.data.objects)
    coll = bpy.data.collections.get("_Restored")
    check("restore: removes nothing", before <= after, before - after)
    check("restore: A is back in _Restored at its original place",
          coll is not None and r["restored"]["A"] in coll.objects
          and tuple(round(v, 4) for v in bpy.data.objects[r["restored"]["A"]].location) == (0.0, 0.0, 0.0), r)
    check("restore: existing B kept its edit, the copy is separate",
          tuple(bpy.data.objects["B"].location) == b_loc and r["restored"]["B"] != "B"
          and abs(bpy.data.objects[r["restored"]["B"]].location.x - 3.0) < 1e-4, (r["restored"], tuple(bpy.data.objects["B"].location)))
    check("restore: open file path unchanged", bpy.data.filepath == path0, bpy.data.filepath)
    n_obj = len(bpy.data.objects)
    check("restore: unknown object refused with nothing added",
          raises(action="restore", dir=snaps, name="s1", objects=["Nope"]) is not None and len(bpy.data.objects) == n_obj)
    r = snap(action="restore", dir=snaps, name="s1", objects=["C"])
    check("restore: a child brings its parent along and reports it",
          r["restored"]["C"] != "C" and len(r["dependencies"]) >= 1, r)

    # unsaved file: save needs a dir, and keeps the path empty
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    check("unsaved file: save without dir refused", raises(action="save", name="x") is not None)
    r = snap(action="save", dir=os.path.join(base, "unsaved"), name="u1")
    check("unsaved file: save with dir works and the path stays empty", os.path.exists(r["blend"]) and bpy.data.filepath == "",
          bpy.data.filepath)
    check("bad action refused", raises(action="explode") is not None)


def run_surface(out_dir, check):
    bpy.ops.wm.read_factory_settings(use_empty=True)

    def surf(**kw):
        return run("procedural-modeling", "surface_tools.py", kw)

    def raises(**kw):
        try:
            surf(**kw)
        except ValueError as exc:
            return str(exc)
        return None

    def mesh_xyz(name):
        o = bpy.data.objects[name]
        co = np.empty(len(o.data.vertices) * 3)
        o.data.vertices.foreach_get("co", co)
        return co.reshape(-1, 3)

    # loft through three rings of different point counts
    def ring(n, r, z):
        return [[r * np.cos(2 * np.pi * k / n), r * np.sin(2 * np.pi * k / n), z] for k in range(n)]
    secs = [ring(12, 1.0, 0.0), ring(20, 0.6, 1.0), ring(16, 0.8, 2.0)]
    r = surf(action="loft", sections=secs, count=16, closed=True, name="L")
    xyz = mesh_xyz(r["object"])
    check("loft: 3 sections x 16 points, closed faces wrap", (r["vertices"], r["faces"], r["rows"]) == (48, 32, 3), r)
    check("loft: rows sit on the section heights and radii",
          sorted(set(np.round(xyz[:, 2], 6))) == [0.0, 1.0, 2.0]
          and abs(np.hypot(xyz[16:32, 0], xyz[16:32, 1]).max() - 0.6) < 1e-6, sorted(set(np.round(xyz[:, 2], 6))))
    polys = [set(p.vertices) for p in bpy.data.objects[r["object"]].data.polygons]
    check("loft: closed ring has a face joining the last and first point, all faces are quads",
          any({15, 0} <= p for p in polys) and all(len(p) == 4 for p in polys))
    ro = surf(action="loft", sections=secs, count=16, closed=False, name="Lopen")
    check("loft: open sections give 15 quads per span and no wrap face", ro["faces"] == 30 and not any(
        {15, 0} <= set(p.vertices) for p in bpy.data.objects[ro["object"]].data.polygons), ro)
    r2 = surf(action="loft", sections=secs, count=16, closed=True, subdiv=1, name="L2")
    z2 = mesh_xyz(r2["object"])[:, 2]
    check("loft: subdiv adds rows but still passes through each section", r2["rows"] == 5
          and all(any(abs(z - h) < 1e-9 for z in z2) for h in (0.0, 1.0, 2.0)), r2)
    check("loft: one section refused", raises(action="loft", sections=[secs[0]]) is not None)

    # Coons patch with straight boundaries reproduces the bilinear surface z = x*y exactly
    xs = np.linspace(0, 1, 21)
    bt = [[x, 0, 0] for x in xs]
    tp = [[x, 1, x] for x in xs]
    lf = [[0, y, 0] for y in xs]
    rt = [[1, y, y] for y in xs]
    r = surf(action="patch", bottom=bt, top=tp, left=lf, right=rt, nu=11, nv=9, name="P")
    xyz = mesh_xyz(r["object"])
    err = float(np.abs(xyz[:, 2] - xyz[:, 0] * xyz[:, 1]).max())
    check("patch: interior matches z = x*y", err < 1e-6 and (r["rows"], r["cols"]) == (9, 11), err)
    # curved boundaries: the bottom row follows the parabola (points are spaced by arc length, so test the curve, not x)
    pb_ = [[x, 0, x * x] for x in xs]
    r = surf(action="patch", bottom=pb_, top=[[x, 1, x * x + 1] for x in xs], left=[[0, y, y * y] for y in xs],
             right=[[1, y, 1 + y * y] for y in xs], nu=11, nv=9, name="P2")
    xyz = mesh_xyz(r["object"])
    check("patch: curved bottom boundary lies on the input curve", abs(xyz[:11, 2] - xyz[:11, 0] ** 2).max() < 2e-3,
          abs(xyz[:11, 2] - xyz[:11, 0] ** 2).max())
    bad_top = [[x + 0.3, 1, x * x + 1] for x in xs]
    msg = raises(action="patch", bottom=bt, top=bad_top, left=lf, right=rt)
    check("patch: mismatched corners refused, naming them", msg and "corners" in msg and "top[0] vs left[-1]" in msg, msg)

    # continuity across x = 0 with grids: rows step in x (0.1), columns along y
    ys = np.linspace(0, 1, 11)

    def grid(f, x0, x1, ycols=ys, n=6):
        return [[[x, y, f(x)] for y in ycols] for x in np.linspace(x0, x1, n)]

    def cont(fa, fb, **kw):
        return surf(action="continuity", a_grid=grid(fa, -0.5, 0.0), b_grid=grid(fb, 0.0, 0.5), **kw)

    flat = cont(lambda x: 0.0, lambda x: 0.0)
    check("continuity: coplanar surfaces are G2", flat["level"] == "G2", flat)
    crease = cont(lambda x: 0.0, lambda x: x)
    check("continuity: creased join passes G0 and FAILS G1 (45 degrees)",
          crease["g0"]["ok"] and not crease["g1"]["ok"] and crease["level"] == "G0"
          and abs(crease["g1"]["max_angle_deg"] - 45.0) < 0.5, crease)
    jump = cont(lambda x: 0.0, lambda x: x * x)
    check("continuity: tangent join with a curvature jump passes G1 and FAILS G2",
          jump["g1"]["ok"] and not jump["g2"]["ok"] and jump["level"] == "G1" and jump["g2"]["max_curvature_jump"] > 1.5, jump)
    smooth = cont(lambda x: x * x, lambda x: x * x)
    check("continuity: one smooth parabola across the seam is G2", smooth["level"] == "G2", smooth)
    rev = surf(action="continuity", a_grid=grid(lambda x: 0.0, -0.5, 0.0),
               b_grid=grid(lambda x: 0.0, 0.0, 0.5, ycols=ys[::-1]))
    check("continuity: a boundary traversed the other way is matched and reported", rev["b_reversed"] and rev["level"] == "G2", rev)
    check("continuity: boundary shifted along the seam refused",
          "do not coincide" in (raises(action="continuity", a_grid=grid(lambda x: 0.0, -0.5, 0.0),
                                       b_grid=grid(lambda x: 0.0, 0.0, 0.5, ycols=ys + 0.5)) or ""))
    check("continuity: different point counts refused",
          "point counts" in (raises(action="continuity", a_grid=grid(lambda x: 0.0, -0.5, 0.0),
                                    b_grid=grid(lambda x: 0.0, 0.0, 0.5, ycols=ys[:9])) or ""))
    check("continuity: a seam that does not touch is refused",
          raises(action="continuity", a_grid=grid(lambda x: 0.0, -0.5, -0.1), b_grid=grid(lambda x: 0.0, 0.0, 0.5)) is not None)

    # continuity on mesh objects made by patch (columns run across the seam, so the seam is a column)
    def plane(x0, x1, name, z1=0.0):
        e = np.linspace(x0, x1, 11)
        zs = [z1 * (x - x0) / (x1 - x0) for x in e]
        return surf(action="patch", name=name, nu=11, nv=9,
                    bottom=[[x, 0, z] for x, z in zip(e, zs)], top=[[x, 1, z] for x, z in zip(e, zs)],
                    left=[[x0, y, 0] for y in np.linspace(0, 1, 9)], right=[[x1, y, z1] for y in np.linspace(0, 1, 9)])
    pa, pb = plane(-1, 0, "PA"), plane(0, 1, "PB")
    o = surf(action="continuity", a=pa["object"], a_shape=[9, 11], edge_a="last_col",
             b=pb["object"], b_shape=[9, 11], edge_b="first_col")
    check("continuity on objects: two coplanar patches are G2", o["level"] == "G2", o)
    pc = plane(0, 1, "PC", z1=1.0)
    o = surf(action="continuity", a=pa["object"], a_shape=[9, 11], edge_a="last_col",
             b=pc["object"], b_shape=[9, 11], edge_b="first_col")
    check("continuity on objects: a patch that rises 45 degrees fails G1", o["level"] == "G0" and not o["g1"]["ok"], o)
    check("continuity: wrong shape refused",
          raises(action="continuity", a=pa["object"], a_shape=[9, 10], b=pb["object"], b_shape=[9, 11]) is not None)
    check("surface_tools: bad action refused", raises(action="explode") is not None)


def run_review_round1(out_dir, check):
    """Findings from the round-1 review of batch M. Each check failed on 667898c before its fix."""
    base = os.path.join(out_dir, "review1")
    rng = np.random.default_rng(21)

    def noise(h, w):
        t = rng.random((h + 2, w + 2)).astype(np.float32)
        s = sum(t[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)) / 9.0
        return 0.05 + 0.6 * (s - s.min()) / (s.max() - s.min())

    def seq_with_bump(name, h, w, box):
        w0 = noise(h, w)
        fr = [w0.copy() for _ in range(9)]
        x0, y0, x1, y1 = box
        fr[4][y0:y1, x0:x1] += 0.15
        return run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, name), fr)})

    # M-A: a size that is not a multiple of the block must not hide a flicker in the leftover strip (1080 = 67*16 + 8)
    r = seq_with_bump("strip_bottom", 72, 128, (32, 64, 64, 72))
    check("strip: flicker confined to the 8 bottom rows (72 px high, block 16) is found",
          r["verdict"] == "flicker" and r["events"] and r["events"][0]["frame"] == 4
          and r["events"][0]["region_px"][3] == 72, (r["verdict"], r["events"][:1]))
    r = seq_with_bump("strip_right", 64, 132, (128, 16, 132, 48))
    check("strip: flicker confined to the 4 right columns (132 px wide, block 16) is found",
          r["verdict"] == "flicker" and r["events"] and r["events"][0]["frame"] == 4
          and r["events"][0]["region_px"][2] == 132, (r["verdict"], r["events"][:1]))
    r = seq_with_bump("strip_clean", 72, 132, (0, 0, 0, 0))
    check("strip: an odd-sized clean static sequence still passes", r["verdict"] == "pass" and not r["events"],
          (r["verdict"], r["events"][:1]))

    # M-B: stripes whose period (12) does not divide the block (16): block means move with the phase, so a naive
    # block-mean second difference fails on a clean pan, and the motion-compensated check must not
    N = 9
    x = np.arange(W + N * 3 + 12)
    row = np.where((x // 6) % 2 == 0, 0.9, 0.1).astype(np.float32)
    world = np.tile(row, (H, 1))
    fr = pan(world, N, 3)
    bm = [f.reshape(H // 16, 16, W // 16, 16).mean(axis=(1, 3)) for f in fr]
    naive_block = max(float(np.abs(bm[t - 1] - 2 * bm[t] + bm[t + 1]).max()) for t in range(1, N - 1))
    check("stripes P=12 vs block 16: a naive block-mean second difference exceeds the 0.03 threshold (it would flag)",
          naive_block > 0.1, naive_block)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "stripes12"), fr)})
    check("stripes P=12 vs block 16: clean pan passes", r["verdict"] == "pass" and not r["events"],
          (r["verdict"], r["events"][:1], r["not_measured"]))
    fr[4] = bump(fr[4], 32, 16, 64, 48, 0.15)
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "stripes12_f"), fr)})
    check("stripes P=12: flicker inside the pan is found at frame 4",
          r["verdict"] == "flicker" and r["events"] and r["events"][0]["frame"] == 4, (r["verdict"], r["events"][:1]))

    # M-C: scene_snapshot hash must see polygon boundaries and loose edges
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1.5, 0), (0, 1.5, 0), (-1, 1, 0)]
    me = bpy.data.meshes.new("Topo")
    me.from_pydata(pts, [], [(0, 1, 2), (3, 4, 5)])
    ob = bpy.data.objects.new("Topo", me)
    bpy.context.scene.collection.objects.link(ob)
    me2 = bpy.data.meshes.new("Loose")
    me2.from_pydata(pts, [], [(0, 1, 2)])
    ob2 = bpy.data.objects.new("Loose", me2)
    bpy.context.scene.collection.objects.link(ob2)
    bpy.context.view_layer.update()
    snaps = os.path.join(base, "snaps")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731
    snap(action="save", dir=snaps, name="t1")
    # same vertices, same flattened corner list, different polygon boundaries: two triangles -> one hexagon
    me.clear_geometry()
    me.from_pydata(pts, [], [(0, 1, 2, 3, 4, 5)])
    # same vertices and faces, one extra loose edge
    me2.clear_geometry()
    me2.from_pydata(pts, [(3, 4)], [(0, 1, 2)])
    bpy.context.view_layer.update()
    d = snap(action="diff", dir=snaps, a="t1")
    ch = {c["name"]: c for c in d["changed"]}
    check("snapshot: two triangles -> one hexagon over the same vertices is reported as a mesh change",
          ch.get("Topo", {}).get("mesh_changed") is True, d)
    check("snapshot: an added loose edge is reported as a mesh change",
          ch.get("Loose", {}).get("mesh_changed") is True, d)

    # M-D: G2 must not depend on the grid parameterisation. One surface z = x^2; b is sampled with a sheared grid
    ys = np.linspace(0, 1, 11)

    def sg(f, x0, x1, shear, n=6):
        return [[[x, y + shear * x, f(x)] for y in ys] for x in np.linspace(x0, x1, n)]
    res = run("procedural-modeling", "surface_tools.py",
              {"action": "continuity", "a_grid": sg(lambda x: x * x, -0.5, 0.0, 0.0), "b_grid": sg(lambda x: x * x, 0.0, 0.5, 1.0)})
    check("continuity G2: the same smooth surface sampled with a sheared grid on one side is still G2",
          res["level"] == "G2", res)
    res = run("procedural-modeling", "surface_tools.py",
              {"action": "continuity", "a_grid": sg(lambda x: 0.0, -0.5, 0.0, 0.0), "b_grid": sg(lambda x: x * x, 0.0, 0.5, 1.0)})
    check("continuity G2: a real curvature jump is still caught under shear",
          res["level"] == "G1" and res["g2"]["max_curvature_jump"] > 1.5, res)
    res = run("procedural-modeling", "surface_tools.py",
              {"action": "continuity", "a_grid": sg(lambda x: x * x, -0.5, 0.0, 0.7), "b_grid": sg(lambda x: x * x, 0.0, 0.5, -0.4)})
    check("continuity G2: different shears on both sides of one smooth surface are still G2", res["level"] == "G2", res)
    ys4 = np.linspace(0, 1, 4)
    res = run("procedural-modeling", "surface_tools.py",
              {"action": "continuity",
               "a_grid": [[[x, y, 0.0] for y in ys4] for x in np.linspace(-0.5, 0, 6)],
               "b_grid": [[[x, y, x * x] for y in ys4] for x in np.linspace(0, 0.5, 6)]})
    check("continuity G2: a seam with only 4 points reports g2 not_measured (ok null) and stops at G1, no wrong G2 verdict",
          res["g2"]["ok"] is None and "not_measured" in res["g2"] and res["level"] == "G1", res)


def run_review_round2(out_dir, check):
    """Findings from the round-2 review of batch M. Each check failed on c954846 before its fix."""
    base = os.path.join(out_dir, "review2")

    # M1: two independent events in disjoint regions on adjacent frames must both be reported (static, no motion)
    rng = np.random.default_rng(5)
    t = rng.random((H + 2, W + 2)).astype(np.float32)
    w0 = 0.05 + 0.6 * (sum(t[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)) / 9.0 - 0.3)
    fr = [w0.copy() for _ in range(9)]
    fr[4] = bump(fr[4], 0, 0, 32, 32, 0.2)    # region A, frame 4, +0.2
    fr[5] = bump(fr[5], 64, 16, 96, 48, 0.1)  # region B, frame 5, +0.1
    r = run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, "adjacent"), fr), "max_motion_px": 0})
    by = {e["frame"]: e for e in r["events"]}
    check("flicker: independent events on adjacent frames (A@4 +0.2, B@5 +0.1) are both reported",
          sorted(by) == [4, 5], [(e["frame"], e["region_px"]) for e in r["events"]])
    if 4 in by and 5 in by:
        check("flicker: frame 4 reports region A only (no echo of B), frame 5 reports region B only",
              by[4]["region_px"][2] <= 32 and by[5]["region_px"][0] >= 64 and by[5]["region_px"][2] <= 96,
              (by[4]["region_px"], by[5]["region_px"]))
    else:
        check("flicker: frame 4 reports region A only, frame 5 region B only", False, sorted(by))

    # M3: a saved .blend with an unpacked texture at //textures/albedo.png; the snapshot lives in another folder
    bpy.ops.wm.read_factory_settings(use_empty=True)
    proj = os.path.join(base, "proj")
    tex = os.path.join(proj, "textures", "albedo.png")
    os.makedirs(os.path.dirname(tex), exist_ok=True)
    save_gray(tex, np.random.default_rng(1).random((8, 8)).astype(np.float32))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(proj, "work.blend"))
    me = bpy.data.meshes.new("Tri")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new("Textured", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("TexMat")
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(tex)
    img.filepath = "//textures/albedo.png"
    node.image = img
    me.materials.append(mat)
    bpy.context.view_layer.update()
    check("snapshot fixture: the image path is relative and resolves to the real file",
          img.filepath.startswith("//") and os.path.normcase(os.path.abspath(bpy.path.abspath(img.filepath))) == os.path.normcase(os.path.abspath(tex)),
          (img.filepath, bpy.path.abspath(img.filepath)))
    snaps = os.path.join(proj, "snapshots")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731
    snap(action="save", name="tx")
    check("snapshot: default dir is <file folder>/snapshots", os.path.exists(os.path.join(snaps, "tx.blend")))
    bpy.data.objects.remove(ob)  # restore into a scene where the original is gone
    bpy.data.materials.remove(mat)
    bpy.data.images.remove(img)
    snap(action="restore", dir=snaps, name="tx", objects=["Textured"])
    rm = bpy.data.objects["Textured"].active_material
    ri = next(n.image for n in rm.node_tree.nodes if n.type == "TEX_IMAGE")
    got = os.path.normcase(os.path.abspath(bpy.path.abspath(ri.filepath)))
    check("snapshot: restored material's image path resolves to the real texture file",
          got == os.path.normcase(os.path.abspath(tex)) and os.path.exists(got), (ri.filepath, got))


def run_review_round3(out_dir, check):
    """Findings from the round-3 review of batch M. Each check failed on e834bf1 before its fix."""
    base = os.path.join(out_dir, "review3")

    # M1: one flicker on a panning shot yields one event, not the flicker plus its two motion-matched echoes
    world = noise_world(W + 9 * 16, 33)
    fr = pan(world, 9, 16)
    fr[4] = bump(fr[4], 32, 16, 48, 32, 0.15)
    r = run("film-production", "flicker_check.py",
            {"paths": write_seq(os.path.join(base, "pan16"), fr), "block": 16, "max_motion_px": 16})
    check("flicker: one +0.15 flicker on a 16 px/frame pan reports exactly one event (frame 4)",
          [e["frame"] for e in r["events"]] == [4], [(e["frame"], e["region_px"]) for e in r["events"]])

    # same class, unaligned speeds: still one event
    for tag, speed in (("pan5", 5), ("pan11", 11)):
        w2 = noise_world(W + 9 * speed, 34 + speed)
        f2 = pan(w2, 9, speed)
        f2[4] = bump(f2[4], 32, 16, 48, 32, 0.15)
        r = run("film-production", "flicker_check.py",
                {"paths": write_seq(os.path.join(base, tag), f2), "block": 16, "max_motion_px": 16})
        check(f"flicker: one flicker on a {speed} px/frame pan reports one event at frame 4",
              [e["frame"] for e in r["events"]] == [4], [(e["frame"], e["region_px"]) for e in r["events"]])

    # two independent events on adjacent frames both survive, static and panning
    rng = np.random.default_rng(8)
    t = rng.random((H + 2, W + 2)).astype(np.float32)
    w0 = 0.05 + 0.6 * (sum(t[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)) / 9.0 - 0.3)
    fr = [w0.copy() for _ in range(9)]
    fr[4] = bump(fr[4], 0, 0, 16, 16, 0.2)
    fr[5] = bump(fr[5], 96, 32, 112, 48, 0.1)
    r = run("film-production", "flicker_check.py",
            {"paths": write_seq(os.path.join(base, "adj_static"), fr), "block": 16, "max_motion_px": 8})
    check("flicker: static event @4 and independent event @5 both reported",
          sorted(e["frame"] for e in r["events"]) == [4, 5], [(e["frame"], e["region_px"]) for e in r["events"]])
    world = noise_world(W + 9 * 16, 35)
    fr = pan(world, 9, 16)
    fr[4] = bump(fr[4], 32, 16, 48, 32, 0.2)
    fr[5] = bump(fr[5], 96, 32, 112, 48, 0.1)
    r = run("film-production", "flicker_check.py",
            {"paths": write_seq(os.path.join(base, "adj_pan"), fr), "block": 16, "max_motion_px": 16})
    check("flicker: two independent events on adjacent frames of a pan are both reported",
          sorted(e["frame"] for e in r["events"]) == [4, 5], [(e["frame"], e["region_px"]) for e in r["events"]])

    # M3: reserved selector and other colliding names are refused by save, and by restore
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Q")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new("Qo", me)
    bpy.context.scene.collection.objects.link(ob)
    snaps = os.path.join(base, "snaps")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731

    def refused(**kw):
        try:
            snap(**kw)
        except ValueError:
            return True
        return False

    for bad in ("current", "Current", "CURRENT", "nul", "NUL.v2", "com1", "aux", "snap.", "x" * 101):
        check(f"snapshot: save name {bad[:12]!r} is refused", refused(action="save", dir=snaps, name=bad))
    left = os.listdir(snaps) if os.path.isdir(snaps) else []
    check("snapshot: nothing was written by the refused names", not left, left)
    check("snapshot: restore from 'current' is refused", refused(action="restore", dir=snaps, name="current", objects=["Qo"]))
    snap(action="save", dir=snaps, name="good-1.v2")
    bpy.data.objects["Qo"].location.x = 3.0
    bpy.context.view_layer.update()
    d = snap(action="diff", dir=snaps, a="good-1.v2")
    check("snapshot: diff of a normal name against the live scene still works", [c["name"] for c in d["changed"]] == ["Qo"], d)


def run_review_round4(out_dir, check):
    """Findings from the round-4 review of batch M. Each check failed on 5cdc393 before its fix."""
    import bmesh
    base = os.path.join(out_dir, "review4")
    snaps = os.path.join(base, "snaps")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731
    surf = lambda **kw: run("procedural-modeling", "surface_tools.py", kw)  # noqa: E731

    def refused(fn, **kw):
        try:
            fn(**kw)
        except ValueError as exc:
            return str(exc)
        return None

    def stored_xs(o):
        return [round(v.co.x, 4) for v in o.data.vertices]

    # M3: diff against the live scene sees an edit made in Edit Mode, and reading it changes nothing
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    cube.name = "E"
    snap(action="save", dir=snaps, name="e0")
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(cube.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].co.x += 0.5
    bmesh.update_edit_mesh(cube.data)
    stale = stored_xs(cube)
    d = snap(action="diff", dir=snaps, a="e0")
    check("M3: diff in Edit Mode reports the edit-mesh change (not a stale 'unchanged')",
          [c["name"] for c in d["changed"]] == ["E"] and d["changed"][0].get("mesh_changed") is True, d)
    bm = bmesh.from_edit_mesh(cube.data)
    bm.verts.ensure_lookup_table()
    check("M3: reading left the mode, the edit data and the stored mesh as they were",
          cube.mode == "EDIT" and abs(bm.verts[0].co.x - (stale[0] + 0.5)) < 1e-4 and stored_xs(cube) == stale,
          (cube.mode, stored_xs(cube), stale))
    # moving the vertex back makes it match the snapshot again (the edit-mesh hash has the same layout as object mode)
    bm.verts[0].co.x -= 0.5
    bmesh.update_edit_mesh(cube.data)
    d = snap(action="diff", dir=snaps, a="e0")
    check("M3: Edit Mode mesh identical to the snapshot is reported unchanged", d["changed"] == [] and d["unchanged"] == 1, d)
    # save would write the stale object-mode mesh while the manifest described the edit mesh: refused, nothing written
    msg = refused(snap, action="save", dir=snaps, name="e1")
    check("M3: save in Edit Mode is refused clearly and writes nothing",
          msg is not None and "Edit Mode" in msg and not os.path.exists(os.path.join(snaps, "e1.json"))
          and not os.path.exists(os.path.join(snaps, "e1.blend")), msg)
    bpy.ops.object.mode_set(mode="OBJECT")
    check("M3: after leaving Edit Mode save works again", os.path.exists(snap(action="save", dir=snaps, name="e1")["blend"]))

    # M2: object-backed continuity reads the edit mesh, so a crease made in Edit Mode is seen
    bpy.ops.wm.read_factory_settings(use_empty=True)

    def plane(x0, x1, name, z1=0.0):
        e = np.linspace(x0, x1, 11)
        zs = [z1 * (x - x0) / (x1 - x0) for x in e]
        return surf(action="patch", name=name, nu=11, nv=9,
                    bottom=[[x, 0, z] for x, z in zip(e, zs)], top=[[x, 1, z] for x, z in zip(e, zs)],
                    left=[[x0, y, 0] for y in np.linspace(0, 1, 9)], right=[[x1, y, z1] for y in np.linspace(0, 1, 9)])
    pa, pb = plane(-1, 0, "QA"), plane(0, 1, "QB")
    cont = lambda: surf(action="continuity", a=pa["object"], a_shape=[9, 11], edge_a="last_col",  # noqa: E731
                        b=pb["object"], b_shape=[9, 11], edge_b="first_col")
    check("M2: fixture - two coplanar patches are G2 in Object Mode", cont()["level"] == "G2")
    ob = bpy.data.objects[pb["object"]]
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:  # lift everything past the seam column (x > 0.05) by x: a 45 degree crease, edit mesh only
        if v.co.x > 0.05:
            v.co.z += v.co.x
    bmesh.update_edit_mesh(ob.data)
    stale = stored_xs(ob)
    res = cont()
    check("M2: continuity in Edit Mode scores the edit mesh (crease -> not G1), not the stale smooth one",
          res["level"] == "G0" and not res["g1"]["ok"], res)
    bm = bmesh.from_edit_mesh(ob.data)
    check("M2: reading left Edit Mode and the stored mesh alone", ob.mode == "EDIT" and stored_xs(ob) == stale and len(bm.verts) == 99)
    check("M2: shape is checked against the edit mesh vertex count",
          "does not match 99" in (refused(surf, action="continuity", a=pa["object"], a_shape=[9, 11], edge_a="last_col",
                                           b=pb["object"], b_shape=[9, 10], edge_b="first_col") or ""))
    bpy.ops.object.mode_set(mode="OBJECT")

    # M3 (low): restore must not touch the existing dirty mesh, and the restored copy carries the snapshot geometry
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n, loc in (("P", (0, 0, 0)), ("Q", (4, 0, 0))):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.active_object.name = n
    q = bpy.data.objects["Q"]
    q.parent = bpy.data.objects["P"]
    q.matrix_parent_inverse = bpy.data.objects["P"].matrix_world.inverted()
    orig = [round(v.co.x, 4) for v in q.data.vertices]
    snaps2 = os.path.join(base, "snaps2")
    snap(action="save", dir=snaps2, name="r0")
    q.data.vertices[0].co.x += 0.75
    edited = [round(v.co.x, 4) for v in q.data.vertices]
    mesh_name = q.data.name
    r = snap(action="restore", dir=snaps2, name="r0", objects=["Q"])
    new_q = bpy.data.objects[r["restored"]["Q"]]
    check("restore: the existing object's mesh keeps its edit (same datablock, same coordinates)",
          bpy.data.objects["Q"].data.name == mesh_name and stored_xs(bpy.data.objects["Q"]) == edited,
          (bpy.data.objects["Q"].data.name, mesh_name))
    check("restore: the restored copy has its own mesh with the snapshot geometry, not the edit",
          new_q is not bpy.data.objects["Q"] and new_q.data is not bpy.data.objects["Q"].data
          and stored_xs(new_q) == orig and orig != edited, (stored_xs(new_q), orig, edited))


def run_review_round5(out_dir, check):
    """Findings from the round-5 review of batch M. Each check failed on 03f5808 before its fix."""
    import bmesh
    base = os.path.join(out_dir, "review5")
    snaps = os.path.join(base, "snaps")
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731

    # M3: unchanged meshes of any shape hash the same in Edit Mode and Object Mode
    def shape_wire(me):
        me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1), (1, 2)], [])

    def shape_loose(me):
        me.from_pydata([(0, 0, 0), (1, 0, 0), (2, 3, 4)], [], [])

    def shape_empty(me):
        pass

    def shape_mixed(me):
        me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (5, 5, 5), (6, 5, 5), (9, 9, 9)],
                       [(3, 4)], [(0, 1, 2)])

    for label, build in (("faceless wire", shape_wire), ("loose vertices", shape_loose), ("empty mesh", shape_empty),
                         ("face + loose edge + loose vertex", shape_mixed)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        me = bpy.data.meshes.new("M5")
        build(me)
        me.update()
        ob = bpy.data.objects.new("W", me)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        d5 = os.path.join(snaps, label.replace(" ", "_").replace("+", "p"))
        snap(action="save", dir=d5, name="w0")
        bpy.ops.object.mode_set(mode="EDIT")
        d = snap(action="diff", dir=d5, a="w0")
        check(f"M3 (r5): entering Edit Mode on a {label} mesh does not change its hash",
              d["changed"] == [] and d["unchanged"] == 1, d)
        bpy.ops.object.mode_set(mode="OBJECT")

    # M3: restoring a collection instance does not expose its source collection
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    src = bpy.data.collections.new("SRC")  # deliberately not linked to the scene
    cube_me = bpy.data.meshes.new("SRCmesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(cube_me)
    bm.free()
    cube = bpy.data.objects.new("SrcCube", cube_me)
    src.objects.link(cube)
    inst = bpy.data.objects.new("Inst", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = src
    inst.location = (10, 0, 0)
    scene.collection.objects.link(inst)
    bpy.ops.mesh.primitive_cube_add(location=(0, 5, 0))
    bpy.context.active_object.name = "Keep"
    d6 = os.path.join(base, "inst")
    snap(action="save", dir=d6, name="i0")

    def world_xs():
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        return sorted(round(i.matrix_world.translation.x, 3) for i in dg.object_instances
                      if i.object.type == "MESH" and i.object.name.startswith(("SrcCube", "Keep")))

    scene_before = sorted(o.name for o in scene.objects)
    colls_before = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
    objs_before = set(bpy.data.objects.keys())
    xs_before = world_xs()
    r = snap(action="restore", dir=d6, name="i0", objects=["Inst"])
    new_inst = bpy.data.objects[r["restored"]["Inst"]]
    in_scene = sorted(o.name for o in scene.objects)
    check("M3 (r5): restoring an instance links only that object into the scene",
          sorted(set(in_scene) - set(scene_before)) == [new_inst.name], in_scene)
    check("M3 (r5): the instance's source cube is not independently visible",
          not any(o.name.startswith("SrcCube") for o in scene.objects)
          and world_xs() == sorted(xs_before + [10.0]), (world_xs(), xs_before))
    check("M3 (r5): the restored instance still points at a collection holding the cube",
          new_inst.instance_collection is not None and any(o.name.startswith("SrcCube") for o in new_inst.instance_collection.objects)
          and abs(new_inst.location.x - 10.0) < 1e-4, new_inst.instance_collection)
    check("M3 (r5): existing objects and collections are unchanged",
          objs_before <= set(bpy.data.objects.keys()) and "Inst" in scene.objects and "SrcCube" in src.objects
          and all(sorted(o.name for o in bpy.data.collections[n].objects) == v for n, v in colls_before.items()),
          colls_before)

    # M3: a restored child still sits where it was saved, and its restored parent is not newly visible
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n, loc in (("P", (0, 0, 0)), ("Q", (4, 0, 0))):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.active_object.name = n
    q = bpy.data.objects["Q"]
    q.parent = bpy.data.objects["P"]
    q.matrix_parent_inverse = bpy.data.objects["P"].matrix_world.inverted()
    bpy.data.objects["P"].location = (0, 2, 0)
    bpy.context.view_layer.update()
    saved_world = [round(v, 4) for row in q.matrix_world for v in row]
    d7 = os.path.join(base, "parent")
    snap(action="save", dir=d7, name="p0")
    names0 = sorted(o.name for o in bpy.context.view_layer.objects)
    r = snap(action="restore", dir=d7, name="p0", objects=["Q"])
    bpy.context.view_layer.update()
    nq = bpy.data.objects[r["restored"]["Q"]]
    check("M3 (r5): only the requested child is linked; its parent stays out of the scene",
          sorted(set(o.name for o in bpy.context.view_layer.objects) - set(names0)) == [nq.name]
          and nq.parent is not None and nq.parent.name not in bpy.context.view_layer.objects
          and r["dependencies"] == [nq.parent.name], (r, [o.name for o in bpy.context.scene.objects]))
    check("M3 (r5): the restored child appears where it was saved",
          [round(v, 4) for row in nq.matrix_world for v in row] == saved_world, (list(nq.matrix_world), saved_world))


def run_review_round6(out_dir, check):
    """Restored dependencies must survive an actual save and reopen. Failed on 512e3e5 (parent purged as an orphan)."""
    import bmesh
    base = os.path.join(out_dir, "review6")
    os.makedirs(base, exist_ok=True)
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731

    def reopen(tag):
        path = os.path.join(base, tag + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)

    def eval_meshes():
        """[(object name, rounded world-space bbox min, max)] for every visible evaluated mesh instance."""
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        rows = []
        for inst in dg.object_instances:
            if inst.object.type != "MESH":
                continue
            me = inst.object.to_mesh()
            pts = np.array([tuple(inst.matrix_world @ v.co) for v in me.vertices])
            inst.object.to_mesh_clear()
            rows.append((inst.object.original.name, tuple(np.round(pts.min(0), 3)), tuple(np.round(pts.max(0), 3))))
        return sorted(rows)

    def cube(name, loc):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.active_object.name = name
        return bpy.context.active_object

    # 1. a child whose parent is not restored
    bpy.ops.wm.read_factory_settings(use_empty=True)
    p, q = cube("P", (0, 0, 0)), cube("Q", (0, 0, 1))
    p.location = (5, 0, 0)
    q.parent = p
    q.matrix_parent_inverse = p.matrix_world.inverted()
    bpy.context.view_layer.update()
    d = os.path.join(base, "parent")
    snap(action="save", dir=d, name="s")
    r = snap(action="restore", dir=d, name="s", objects=["Q"])
    nq_name = r["restored"]["Q"]
    reopen("parent")
    bpy.context.view_layer.update()
    nq = bpy.data.objects[nq_name]
    check("M3 (r6): after save and reopen the restored child still has its parent and sits at x=5",
          nq.parent is not None and abs(nq.matrix_world.translation.x - 5.0) < 1e-4
          and abs(nq.matrix_world.translation.z - 1.0) < 1e-4, (nq.parent, tuple(nq.matrix_world.translation)))
    check("M3 (r6): the reopened parent is not visible in the view layer",
          nq.parent is not None and nq.parent.name not in bpy.context.view_layer.objects, nq.parent)
    check("M3 (r6): no extra visible geometry after reopen (original P, Q plus the restored Q only)",
          len(eval_meshes()) == 3, eval_meshes())

    # 2. a rigged mesh whose armature is not restored
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.armature_add(location=(0, 0, 0))
    arm = bpy.context.active_object
    arm.name = "Arm"
    m = cube("Body", (0, 0, 0))
    m.vertex_groups.new(name="Bone").add(list(range(len(m.data.vertices))), 1.0, "REPLACE")
    mod = m.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    arm.pose.bones["Bone"].location = (0, 0, 2)
    bpy.context.view_layer.update()
    rig_before = [x for x in eval_meshes() if x[0] == "Body"]
    d = os.path.join(base, "rig")
    snap(action="save", dir=d, name="s")
    r = snap(action="restore", dir=d, name="s", objects=["Body"])
    nb_name = r["restored"]["Body"]
    reopen("rig")
    bpy.context.view_layer.update()
    nb = bpy.data.objects[nb_name]
    check("M3 (r6): a restored rigged mesh keeps its armature after save and reopen",
          nb.modifiers["Armature"].object is not None, nb.modifiers["Armature"].object)
    rig_after = [x for x in eval_meshes() if x[0] == nb_name]
    check("M3 (r6): the rig still deforms the mesh after reopen (evaluated bbox equals the original's)",
          len(rig_after) == 1 and bool(rig_before) and rig_after[0][1:] == rig_before[0][1:], (rig_after, rig_before))
    check("M3 (r6): the restored armature is not visible", nb.modifiers["Armature"].object is not None
          and nb.modifiers["Armature"].object.name not in bpy.context.view_layer.objects, "")

    # 3. a collection instance keeps working after reopen
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    src = bpy.data.collections.new("SRC")
    cme = bpy.data.meshes.new("SRCmesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(cme)
    bm.free()
    src.objects.link(bpy.data.objects.new("SrcCube", cme))
    inst = bpy.data.objects.new("Inst", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = src
    inst.location = (10, 0, 0)
    scene.collection.objects.link(inst)
    d = os.path.join(base, "inst")
    snap(action="save", dir=d, name="s")
    before = len(eval_meshes())
    r = snap(action="restore", dir=d, name="s", objects=["Inst"])
    ni_name = r["restored"]["Inst"]
    reopen("inst")
    ni = bpy.data.objects[ni_name]
    rows = eval_meshes()
    xs = sorted(round((a[1][0] + a[2][0]) / 2, 2) for a in rows)
    check("M3 (r6): after reopen the instance still points at its collection, at X=10, with one cube per instance",
          ni.instance_collection is not None and abs(ni.location.x - 10.0) < 1e-4 and len(rows) == before + 1
          and xs.count(10.0) == 2, (rows, xs))
    check("M3 (r6): the instance's source cube is not independently visible after reopen",
          not any(o.name.startswith("SrcCube") for o in bpy.context.view_layer.objects), "")


def run_all(out_dir, only=None):
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})

    os.makedirs(out_dir, exist_ok=True)
    for label, fn in (("flicker_check", run_flicker), ("scene_snapshot", run_snapshot),
                      ("surface_tools", run_surface), ("review_round1", run_review_round1),
                      ("review_round2", run_review_round2), ("review_round3", run_review_round3),
                      ("review_round4", run_review_round4), ("review_round5", run_review_round5),
                      ("review_round6", run_review_round6),
                      ("review_round7", run_review_round7), ("flash_frames", run_flash_frames),
                      ("snapshot_duplicates", run_snapshot_duplicates)):
        if only and label not in only:
            continue
        try:
            fn(out_dir, check)
        except Exception:
            check(f"{label}: harness crashed", False, traceback.format_exc()[-800:])
    return results


def run_review_round7(out_dir, check):
    """A restored dependency must be excluded in every view layer of the scene, not only the active one."""
    base = os.path.join(out_dir, "review7")
    os.makedirs(base, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for n, loc in (("P", (1, 2, 3)), ("C", (5, 0, 0))):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        bpy.context.active_object.name = n
    bpy.data.objects["C"].parent = bpy.data.objects["P"]
    bpy.context.scene.view_layers.new("VL2")
    d = os.path.join(base, "s")
    run("blender-mcp-workflow", "scene_snapshot.py", {"action": "save", "dir": d, "name": "a"})
    bpy.data.objects.remove(bpy.data.objects["C"])
    bpy.data.objects.remove(bpy.data.objects["P"])
    r = run("blender-mcp-workflow", "scene_snapshot.py", {"action": "restore", "dir": d, "name": "a", "objects": ["C"]})
    bpy.context.view_layer.update()
    parent = bpy.data.objects[r["dependencies"][0]]
    seen = {vl.name: parent.name in vl.objects for vl in bpy.context.scene.view_layers}
    check("M3 (r7): the restored parent is hidden in every view layer (two layers)",
          len(seen) == 2 and not any(seen.values()), seen)


def run_flash_frames(out_dir, check):
    """A black or white frame in a static noise sequence is an exposure pop (or inconclusive), never a pass."""
    base = os.path.join(out_dir, "flash")
    w0 = noise_world(W, 1)

    def go(name, fr, **kw):
        return run("film-production", "flicker_check.py", {"paths": write_seq(os.path.join(base, name), fr), **kw})

    for n in (9, 25):
        for label, val in (("black", 0.0), ("white", 1.0)):
            fr = [w0.copy() for _ in range(n)]
            fr[4] = np.full_like(w0, val)
            r = go(f"{label}{n}", fr)
            ev = [e for e in r["events"] if e["frame"] == 4]
            check(f"flash: {label} frame 4 of {n} is never a pass", r["verdict"] != "pass", (r["verdict"], r["measured_share"]))
            check(f"flash: {label} frame 4 of {n} is a global_exposure event on frame 4 and nothing else",
                  r["verdict"] == "flicker" and len(r["events"]) == 1 and len(ev) == 1 and ev[0]["kind"] == "global_exposure",
                  (r["verdict"], [(e["frame"], e["kind"]) for e in r["events"]]))
    # two bad frames in a row do not have the one-frame pop shape: inconclusive, and the output names them
    fr = [w0.copy() for _ in range(9)]
    fr[4] = np.zeros_like(w0)
    fr[5] = np.zeros_like(w0)
    r = go("black_pair", fr)
    named = {u["frame"] for u in r.get("unmeasured_frames", [])}
    check("flash: two consecutive black frames are inconclusive and name frames 4 and 5",
          r["verdict"] == "inconclusive" and {4, 5} <= named, (r["verdict"], sorted(named), [e["frame"] for e in r["events"]]))
    # a hard cut (a different, brighter scene from frame 5 on) is not a pop
    other = np.clip(noise_world(W, 7) + 0.2, 0, 1)
    fr = [w0.copy() for _ in range(5)] + [other.copy() for _ in range(4)]
    r = go("hardcut", fr)
    check("flash: a hard cut is not reported as a pop", not r["events"], [(e["frame"], e["kind"]) for e in r["events"]])
    check("flash: a hard cut is never a plain pass (its frames are unmeasured and named)",
          r["verdict"] == "inconclusive" and {4, 5} <= {u["frame"] for u in r.get("unmeasured_frames", [])},
          (r["verdict"], r.get("unmeasured_frames")))
    # unchanged behaviour: gain pops at frame 4, and a steady sequence
    for gain in (0.7, 1.2, 1.5, 2.0):
        fr = [w0.copy() for _ in range(9)]
        fr[4] = np.clip(fr[4] * gain, 0, 1)
        r = go(f"gain{gain}", fr)
        check(f"flash: gain {gain} at frame 4 is a single event on frame 4",
              r["verdict"] == "flicker" and [e["frame"] for e in r["events"]] == [4], (r["verdict"], [e["frame"] for e in r["events"]]))
    r = go("steady", [w0.copy() for _ in range(9)])
    check("flash: a steady sequence passes with no unmeasured frames",
          r["verdict"] == "pass" and not r["events"] and not r.get("unmeasured_frames"), (r["verdict"], r.get("unmeasured_frames")))
    fr = [w0.copy() for _ in range(9)]
    fr[4] = np.clip(fr[4] + 0.15, 0, 1)
    r = go("additive", fr)
    check("flash: an additive +0.15 pop at frame 4 is one global_exposure event",
          r["verdict"] == "flicker" and [(e["frame"], e["kind"]) for e in r["events"]] == [(4, "global_exposure")], r["events"][:1])


def run_snapshot_duplicates(out_dir, check):
    """restore with a repeated name used to segfault Blender when the library-load context closed."""
    base = os.path.join(out_dir, "dupnames")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name, loc in (("A", (0, 0, 0)), ("B", (3, 0, 0))):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.active_object.name = name
    snap = lambda **kw: run("blender-mcp-workflow", "scene_snapshot.py", kw)  # noqa: E731
    d = os.path.join(base, "s")
    snap(action="save", dir=d, name="a")
    before = {o.name for o in bpy.data.objects}
    r = snap(action="restore", dir=d, name="a", objects=["A", "A"])
    new = sorted({o.name for o in bpy.data.objects} - before)
    check("restore: ['A','A'] returns without crashing and adds exactly one copy", len(new) == 1 and list(r["restored"]) == ["A"],
          (new, r))
    before = {o.name for o in bpy.data.objects}
    r = snap(action="restore", dir=d, name="a", objects=["B", "A", "B", "A", "B"])
    new = sorted({o.name for o in bpy.data.objects} - before)
    check("restore: repeated names are deduplicated in order (B, A), one copy each",
          list(r["restored"]) == ["B", "A"] and len(new) == 2 and set(r["restored"].values()) == set(new), (new, r))
    before = {o.name for o in bpy.data.objects}
    r1 = snap(action="restore", dir=d, name="a", objects=["A"])
    r2 = snap(action="restore", dir=d, name="a", objects=["A"])
    new = {o.name for o in bpy.data.objects} - before
    check("restore: the same name across two calls gives two distinct copies, both in _Restored",
          r1["restored"]["A"] != r2["restored"]["A"] and new == {r1["restored"]["A"], r2["restored"]["A"]}
          and all(n in bpy.data.collections["_Restored"].objects for n in new), (r1, r2, sorted(new)))
    m = bpy.data.objects[r["restored"]["A"]]
    check("restore: the copy is at its saved place", tuple(round(v, 4) for v in m.location) == (0.0, 0.0, 0.0), tuple(m.location))


def main(out_dir="/tmp/parity_m", only=None):
    os.makedirs(out_dir, exist_ok=True)
    try:
        results = run_all(out_dir, only)
    except Exception:
        results = [{"name": "harness", "ok": False, "detail": traceback.format_exc()[-800:]}]
    failures = [r for r in results if not r["ok"]]
    report = {"passed": len(results) - len(failures), "total": len(results), "failed": len(failures),
              "failures": failures, "results": results}
    with open(os.path.join(out_dir, "parity_m_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps({k: result[k] for k in ("passed", "total", "failed", "failures")}, indent=2))
    sys.exit(0 if not result["failures"] else 1)
