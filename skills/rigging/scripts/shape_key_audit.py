"""Read-only audit of the shape keys of meshes: dead keys, bad numbers, broken references, drivers, mirror pairs.

Nothing in the scene is changed (no selection, mode, frame, value or datablock); the only file written is `result_path`
when you pass one. Per mesh object that has shape keys, each check is PASS, WARN, FAIL or NOT_CHECKED:
  no_delta       WARN   a key (not the reference key) whose largest vertex delta from its relative key is below 1e-6 of
                        the mesh size (bounding-box diagonal of the reference key): it does nothing. Absolute keys
                        (`use_relative` off) are NOT_CHECKED.
  non_finite     FAIL   a key with a NaN or infinite coordinate.
  relative_key   FAIL   a key whose relative key is missing (not one of the mesh's keys).
  drivers        FAIL   a driver on the shape keys (or on the object, for a key value) that targets a missing object, a
                        missing bone of an armature target, or a key block that does not exist.
  mirror         FAIL   a `.L`/`.R` key pair whose deltas, mirrored across X, differ by more than 1% of the mesh
                        bounding-box diagonal. Each vertex must have exactly ONE reference-key vertex within 1e-4 of the
                        diagonal at its mirrored position and no two may share a match (strict rule, no nearest-wins:
                        coincident vertices cannot be paired safely); any vertex with none or several makes the pair
                        NOT_CHECKED, as does a key with no partner.
The object verdict is FAIL if any check FAILs, else WARN if any WARN or NOT_CHECKED, else PASS. The run verdict is the
worst; a run that measured nothing (no mesh with shape keys) is a FAIL with a note.

Thresholds (set from the fixtures in tests/blender/test_iter16_d.py, each at least 20% of the gap from good and bad):
  NO_DELTA_REL = 1e-6   (of the mesh size) a dead key measures 0.0; real keys measure orders of magnitude
                        above (the smallest fixture key moves 0.02 of the diagonal). A float-noise floor.
  MIRROR_REL = 0.01     (of the bounding-box diagonal) a correct mirrored pair measures 0.0; a pair with one
                        vertex moved 0.1 further measures 0.0348. Gap 0.0348; the bound sits 0.0100 above
                        good and 0.0248 below bad (20% of the gap is 0.0070).
  MATCH_REL = 1e-4      mirrored vertex matching distance.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/shape_key_audit.py", init_globals={"ARGS": {
        "meshes": ["Face"]}})["result"]

Headless: `blender -b f.blend --python-exit-code 1 --python shape_key_audit.py -- --args-file a.json` with
`result_path` and `run_id` in the args. The run counts only if the exit code is 0 or 2 (2 = FAIL verdict) AND
`result_path` exists with this `run_id`.

ARGS:
    meshes       (list[str]|None) mesh objects to audit (every name must exist and be a mesh). Default: every mesh
                 object that has shape keys
    result_path  (str|None) write the result (plus run_id) here as JSON at the end of a successful run
    run_id       (str|None) copied into the result file
"""
import json
import math
import os
import re
import sys

import bpy
import numpy as np
from mathutils import kdtree

NO_DELTA_REL = 1e-6
MIRROR_REL = 0.01
MATCH_REL = 1e-4
RANK = {"PASS": 0, "NOT_CHECKED": 1, "WARN": 1, "FAIL": 2}
BONE_RE = re.compile(r'pose\.bones\[\s*"([^"]+)"\s*\]')
KEY_RE = re.compile(r'key_blocks\[\s*"([^"]+)"\s*\]')
SIDE_RE = re.compile(r"^(.*)\.([LR])$")


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


def _coords(kb):
    arr = np.empty(len(kb.data) * 3, dtype=np.float64)
    kb.data.foreach_get("co", arr)
    return arr.reshape(-1, 3)


def _finite(x):
    """Copy of a result with every non-finite number replaced by None (JSON-safe)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    return x


def _check(name, verdict, **kw):
    return {"check": name, "verdict": verdict, **kw}


def _driver_problems(key, obj):
    """Problems of every driver that animates this mesh's shape keys (on the Key datablock and on the object)."""
    out = []
    holders = []
    if key.animation_data:
        holders.append((key.animation_data, "shape_keys"))
    if obj.animation_data:
        holders.append((obj.animation_data, "object"))
    for ad, where in holders:
        for fc in ad.drivers:
            path = fc.data_path
            if where == "object" and "key_blocks" not in path:
                continue
            m = KEY_RE.search(path)
            if m and m.group(1) not in key.key_blocks:
                out.append(f"driver on {path} targets a key block that does not exist")
            for var in fc.driver.variables:
                for i, t in enumerate(var.targets):
                    if i >= (2 if var.type in ("LOC_DIFF", "ROTATION_DIFF") else 1):
                        break
                    if t.id is None and var.type == "CONTEXT_PROP":
                        continue  # resolved from the evaluation context, no explicit ID by design
                    if t.id is None:
                        out.append(f"driver {path} variable '{var.name}' targets a missing object or datablock")
                        continue
                    arm = t.id if getattr(t.id, "type", "") == "ARMATURE" else None
                    if t.bone_target and arm is not None and t.bone_target not in arm.data.bones:
                        out.append(f"driver {path} variable '{var.name}' targets a missing bone: {t.bone_target}")
                    if var.type == "SINGLE_PROP" and arm is not None:
                        bm = BONE_RE.search(t.data_path)
                        if bm and bm.group(1) not in arm.data.bones:
                            out.append(f"driver {path} variable '{var.name}' targets a missing bone: {bm.group(1)}")
    return out


def _audit_object(obj):
    key = obj.data.shape_keys
    checks = []
    blocks = list(key.key_blocks)
    names = {kb.name for kb in blocks}
    ref = key.reference_key
    rc = _coords(ref)
    nverts = len(obj.data.vertices)
    finite_rows = np.isfinite(rc).all(axis=1)
    ref_finite = bool(finite_rows.all())
    fr = rc[finite_rows]
    diag = float(np.linalg.norm(fr.max(axis=0) - fr.min(axis=0))) if len(fr) else 0.0
    nonfinite = [kb.name for kb in blocks if not np.isfinite(_coords(kb)).all()]
    checks.append(_check("non_finite", "FAIL" if nonfinite else "PASS", keys=nonfinite))
    missing_rel = [kb.name for kb in blocks if kb.relative_key is None or kb.relative_key.name not in names]
    checks.append(_check("relative_key", "FAIL" if missing_rel else "PASS", keys=missing_rel))
    if not key.use_relative:
        checks.append(_check("no_delta", "NOT_CHECKED", reason="absolute shape keys (use_relative is off)"))
    elif diag <= 0.0:
        checks.append(_check("no_delta", "NOT_CHECKED", reason="the mesh has no size (zero bounding box)"))
    else:
        dead = []
        for kb in blocks:
            if kb == ref or kb.relative_key is None or kb.relative_key.name not in names or kb.name in nonfinite:
                continue
            rel = _coords(kb.relative_key)
            if len(rel) == len(_coords(kb)) and float(np.abs(_coords(kb) - rel).max()) < NO_DELTA_REL * diag:
                dead.append(kb.name)
        checks.append(_check("no_delta", "WARN" if dead else "PASS", keys=dead))
    problems = _driver_problems(key, obj)
    checks.append(_check("drivers", "FAIL" if problems else "PASS", problems=problems))
    # mirror pairs
    pairs = {}
    for kb in blocks:
        m = SIDE_RE.match(kb.name)
        if m:
            pairs.setdefault(m.group(1), {})[m.group(2)] = kb
    mirror = []
    match = None
    for base, sides in sorted(pairs.items()):
        if "L" not in sides or "R" not in sides:
            only = sides.get("L") or sides.get("R")
            mirror.append({"pair": base, "verdict": "NOT_CHECKED",
                           "reason": f"no mirror partner for {only.name}"})
            continue
        left, right = sides["L"], sides["R"]
        bad_keys = [k.name for k in (left, right) if k.name in nonfinite or k.relative_key is None
                    or k.relative_key.name not in names]
        if diag <= 0.0 or bad_keys or not ref_finite:
            mirror.append({"pair": base, "verdict": "NOT_CHECKED",
                           "reason": "mesh has no size" if diag <= 0.0 else
                          ("the reference key has non-finite coordinates" if not ref_finite
                           else f"unusable keys: {bad_keys}")})
            continue
        if match is None:
            tree = kdtree.KDTree(nverts)
            for i, co in enumerate(rc):
                tree.insert(tuple(co), i)
            tree.balance()
            match = np.full(nverts, -1, dtype=np.int64)
            ambiguous = 0
            for i, co in enumerate(rc):
                near = tree.find_range((-co[0], co[1], co[2]), MATCH_REL * diag)
                if len(near) == 1:
                    match[i] = near[0][1]
                elif len(near) > 1:
                    ambiguous += 1
            used = match[match >= 0]
            ambiguous += int(len(used) - len(np.unique(used)))
        unmatched = int((match < 0).sum())
        if unmatched:
            mirror.append({"pair": base, "verdict": "NOT_CHECKED",
                           "reason": f"{unmatched} vertices have no unique mirrored vertex within {MATCH_REL} of the "
                                     f"diagonal ({ambiguous} ambiguous: coincident vertices)"})
            continue
        if ambiguous:
            mirror.append({"pair": base, "verdict": "NOT_CHECKED",
                           "reason": "the mirror matching is not one-to-one (coincident vertices)"})
            continue
        dl = _coords(left) - _coords(left.relative_key)
        dr = _coords(right) - _coords(right.relative_key)
        mirrored = dl * np.array([-1.0, 1.0, 1.0])
        err = float(np.linalg.norm(mirrored - dr[match], axis=1).max()) if len(dl) else 0.0
        mirror.append({"pair": base, "verdict": "FAIL" if err > MIRROR_REL * diag else "PASS",
                       "max_mismatch": err, "max_mismatch_rel": err / diag})
    worst = "PASS"
    for p in mirror:
        if RANK[p["verdict"]] > RANK[worst]:
            worst = p["verdict"]
    checks.append(_check("mirror", worst if mirror else "PASS", pairs=mirror))
    verdict = "PASS"
    for c in checks:
        if RANK[c["verdict"]] > RANK[verdict]:
            verdict = c["verdict"]
    if verdict == "NOT_CHECKED":
        verdict = "WARN"
    return {"object": obj.name, "keys": [kb.name for kb in blocks], "diagonal": diag, "checks": checks,
            "verdict": verdict}


def main(meshes=None, result_path=None, run_id=None):
    if meshes:
        objs = []
        for n in meshes:
            o = bpy.data.objects.get(n)
            if o is None or o.type != "MESH":
                raise ValueError(f"mesh not found (or not a mesh object): {n}")
            objs.append(o)
    else:
        objs = [o for o in bpy.data.objects if o.type == "MESH" and o.data.shape_keys]
    rows, notes = [], []
    for o in objs:
        if not o.data.shape_keys or not o.data.shape_keys.key_blocks:
            rows.append({"object": o.name, "keys": [], "checks": [], "verdict": "WARN",
                         "reason": "the mesh has no shape keys"})
        else:
            rows.append(_audit_object(o))
    verdict = "PASS"
    for r in rows:
        if RANK[r["verdict"]] > RANK[verdict]:
            verdict = r["verdict"]
    if not any(r["checks"] for r in rows):
        verdict = "FAIL"
        notes.append("measured nothing: no mesh with shape keys was audited, so the verdict is FAIL")
    result = _finite({"objects": rows, "thresholds": {"no_delta_rel": NO_DELTA_REL, "mirror_rel": MIRROR_REL,
                                              "match_rel": MATCH_REL}, "notes": notes, "verdict": verdict})
    if result_path:
        tmp = result_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**result, "run_id": run_id}, fh, indent=2)
        os.replace(tmp, result_path)
    return result


ARGS = globals().get("ARGS")
if ARGS is None:
    ARGS = _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
    if result.get("verdict") == "FAIL":
        sys.exit(2)
