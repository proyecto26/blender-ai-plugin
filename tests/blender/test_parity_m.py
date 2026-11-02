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


def run_all(out_dir):
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})

    os.makedirs(out_dir, exist_ok=True)
    for label, fn in (("flicker_check", run_flicker), ("scene_snapshot", run_snapshot),
                      ("surface_tools", run_surface), ("review_round1", run_review_round1)):
        try:
            fn(out_dir, check)
        except Exception:
            check(f"{label}: harness crashed", False, traceback.format_exc()[-800:])
    return results


def main(out_dir="/tmp/parity_m"):
    os.makedirs(out_dir, exist_ok=True)
    try:
        results = run_all(out_dir)
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
