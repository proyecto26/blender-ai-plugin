"""Fit named numeric properties so an object's silhouette matches reference masks (coordinate search).

Moves one property at a time up and down by a step, keeps a move that raises the mean IoU from
`silhouette_score.py` (the scorer in the same folder), and halves the steps when no move helps. It is a local
search: it finds the nearest good fit to the starting values, not a global one, and it fits only what you name.
Every property is put back unless `apply` is true. Bounded by `max_evals`.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/fit_search.py", init_globals={"ARGS": {
        "objects": ["SM_Crate"],
        "views": [{"camera": "CAM_Front", "reference": "C:/proj/ref/front.png"}],
        "params": [{"object": "SM_Crate", "path": "scale", "min": 0.2, "max": 3.0}],
        "max_evals": 60}})["result"]

ARGS:
    objects     (list[str], required) mesh objects whose union is the silhouette
    views       (list[dict], required) as in silhouette_score.py: {"camera", "reference", optional "mask"}
    params      (list[dict], required) each {"object": name, "path": RNA path from that object, "min", "max",
                optional "step" (first step, default a quarter of the range) and "tol" (stop when the step
                is below it, default step/32). An integer property never steps by less than 1
                and ignores tol: it is converged once its in-bounds neighbours were evaluated}. The path is read with the Blender data path rules, for example
                "scale" (all three axes move together), "scale[2]", "location[0]", "modifiers[\"Bevel\"].width" (double quotes: single quotes do not resolve).
                Only float and int properties that are not read-only. Everything is checked before any change.
    max_evals   (int) cap on silhouette evaluations, the first and the closing re-score of the best values included
                (default 60); `evals` is the true count. With 1 there is no re-score and `score_checked` is null
    apply       (bool) keep the best values (default false: all values are restored)
    bg_tol      (float) as in silhouette_score.py
    scripts_dir (str|None) folder holding silhouette_score.py; default = the folder of this script
"""
import json
import math
import os
import re
import runpy
import sys

import bpy

PATH_RE = re.compile(r"(?:(.*)\.)?([A-Za-z_]\w*)(?:\[(\d+)\])?")


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


class Param:
    """One searchable number: an RNA property (or one component, or all components together) of an object."""

    shared = {}  # (resolved owner pointer, property) -> committed raw value: params on one property share one state

    def __init__(self, spec):
        if not isinstance(spec, dict) or not {"object", "path", "min", "max"} <= set(spec):
            raise ValueError(f"each param needs object, path, min and max: {spec!r}")
        obj = bpy.data.objects.get(spec["object"])
        if obj is None:
            raise ValueError(f"param object not found: {spec['object']!r}")
        m = PATH_RE.fullmatch(spec["path"])
        if not m:
            raise ValueError(f"cannot read the path {spec['path']!r}")
        parent_path, self.name, idx = m.groups()
        try:
            self.owner = obj.path_resolve(parent_path) if parent_path else obj
        except ValueError as exc:
            raise ValueError(f"path {spec['path']!r} does not resolve on {obj.name!r}: {exc}") from None
        prop = self.owner.bl_rna.properties.get(self.name)
        if prop is None:
            raise ValueError(f"{spec['path']!r} on {obj.name!r}: no property {self.name!r}")
        if prop.type not in ("FLOAT", "INT"):
            raise ValueError(f"{spec['path']!r} is {prop.type}, only FLOAT and INT can be fitted")
        if prop.is_readonly:
            raise ValueError(f"{spec['path']!r} is read-only")
        n = prop.array_length
        self.index = int(idx) if idx is not None else None
        if self.index is not None and not (n and 0 <= self.index < n):
            raise ValueError(f"{spec['path']!r}: index {self.index} out of range (array length {n})")
        self.count = n
        self.integer = prop.type == "INT"
        self.label = f"{obj.name}.{spec['path']}"
        self.lo, self.hi = float(spec["min"]), float(spec["max"])
        if not self.lo < self.hi:
            raise ValueError(f"{self.label}: min must be below max")
        if self.integer:  # candidates are rounded, so the usable bounds are the integers inside [min, max]
            self.lo, self.hi = float(math.ceil(self.lo)), float(math.floor(self.hi))
            if self.lo > self.hi:
                raise ValueError(f"{self.label}: no integer lies between min and max")
        self.step = float(spec.get("step", (self.hi - self.lo) / 4))
        self.tol = float(spec.get("tol", self.step / 32))
        if self.integer:  # the smallest move that changes an integer is 1: a smaller step only rounds back to the start
            self.step = max(1.0, float(round(self.step)))
        if self.step <= 0 or self.tol <= 0:
            raise ValueError(f"{self.label}: step and tol must be positive")
        self.original = self._raw()
        # keyed on the resolved owner, so "modifiers[0].width" and "modifiers[\"Bevel\"].width" share one state
        self.key = (self.owner.as_pointer(), self.name)
        self.committed = Param.shared.setdefault(self.key, [self.original])  # [raw] holder, shared across params
        v = self.get()
        if not self.lo <= v <= self.hi:
            raise ValueError(f"{self.label}: start value {v} is outside [{self.lo}, {self.hi}]")

    def _raw(self):
        v = getattr(self.owner, self.name)
        return list(v) if self.count else v

    def get(self):
        v = self._raw()
        if not self.count:
            return float(v)
        return float(v[self.index if self.index is not None else 0])

    def set(self, value):
        """Write a candidate on top of the committed state of the property, so no other param's accepted value
        (or an untouched component of the original) is overwritten."""
        value = int(round(value)) if self.integer else float(value)
        if not self.count:
            setattr(self.owner, self.name, value)
            return
        cur = list(self.committed[0])
        if self.index is None:
            cur = [value] * self.count
        else:
            cur[self.index] = value
        setattr(self.owner, self.name, cur)

    def accept(self):
        """The current property value, as scored, becomes the committed state."""
        self.committed[0] = self._raw()

    def back_to_committed(self):
        """Undo a rejected candidate: put back the committed state of the whole property, which holds every
        accepted component and the original of every other one."""
        setattr(self.owner, self.name, self.committed[0])

    def restore(self):
        setattr(self.owner, self.name, self.original)
        self.committed[0] = self.original


def _scripts_dir(given):
    if given:
        return given
    here = globals().get("__file__")
    if not here:
        raise ValueError("cannot find silhouette_score.py: pass scripts_dir")
    return os.path.dirname(os.path.abspath(here))


def main(objects=None, views=None, params=None, max_evals=60, apply=False, bg_tol=0.1, scripts_dir=None):
    if not objects or not views or not params:
        raise ValueError("objects, views and params are required")
    max_evals = int(max_evals)
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    sil_path = os.path.join(_scripts_dir(scripts_dir), "silhouette_score.py")
    if not os.path.isfile(sil_path):
        raise ValueError(f"silhouette_score.py not found next to this script: {sil_path}")
    sil = runpy.run_path(sil_path, init_globals={"ARGS": {"_library": True}}, run_name="__silhouette_lib__")

    # Everything that can be wrong is checked here, before the first property changes.
    Param.shared.clear()
    ps = [Param(s) for s in params]
    cams, refs = [], []
    for v in views:
        if not isinstance(v, dict) or "camera" not in v or "reference" not in v:
            raise ValueError(f"each view needs camera and reference: {v!r}")
        cams.append(sil["_camera"](v["camera"]))
        mask, info = sil["load_reference"](v["reference"], v.get("mask", "auto"), float(bg_tol))
        if not mask.any():
            raise ValueError(f"the reference mask for {v['reference']!r} is empty")
        refs.append((mask, info))
    for n in objects:
        if bpy.data.objects.get(n) is None or bpy.data.objects[n].type != "MESH":
            raise ValueError(f"not a mesh object: {n!r}")

    def score():
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        tris = sil["collect_triangles"](objects, dg)
        total = 0.0
        for cam, (ref, info) in zip(cams, refs):
            m = sil["rasterize"](tris, cam, dg, info["width"], info["height"])
            u = int((m | ref).sum())
            total += int((m & ref).sum()) / u if u else 0.0
        return total / len(refs)

    history, evals = [], 0
    checked = max_evals >= 2  # the last evaluation re-scores the applied best values (score_checked); with 1 there is none
    budget = max_evals - 1 if checked else max_evals
    try:
        x = [p.get() for p in ps]
        starts = list(x)
        steps = [p.step for p in ps]
        best = score()
        evals = 1
        start_score = best
        history.append({"eval": 1, "score": round(best, 5), "values": [round(v, 5) for v in x]})
        converged = False
        while evals < budget:
            improved = False
            for i, p in enumerate(ps):
                for sign in (1, -1):
                    if evals >= budget:
                        break
                    cand = min(p.hi, max(p.lo, x[i] + sign * steps[i]))
                    if p.integer:
                        cand = float(round(cand))
                    if cand == x[i]:
                        continue
                    p.set(cand)
                    s = score()
                    evals += 1
                    if s > best + 1e-9:
                        best, improved = s, True
                        p.accept()
                        # a write can move other params that share this property: re-read them all
                        for k, q in enumerate(ps):
                            x[k] = q.get()
                        history.append({"eval": evals, "score": round(best, 5), "values": [round(v, 5) for v in x]})
                        break
                    p.back_to_committed()
            if not improved:
                # an integer is exhausted once a full sweep at step 1 found nothing (both in-bounds neighbours were
                # evaluated, or lie outside the bounds); a float is done when its halved step falls below tol
                done = [st <= 1.0 if p.integer else st / 2 < p.tol for st, p in zip(steps, ps)]
                steps = [max(1.0, float(math.ceil(st / 2))) if p.integer else st / 2 for st, p in zip(steps, ps)]
                if all(done):
                    converged = True
                    break
        for p in ps:
            p.back_to_committed()  # exactly the last scored state: accepted values kept, the rest as they started
        final_score = None
        if checked:
            final_score = score()  # the scene is at the best values here; the last evaluation of the budget
            evals += 1
    finally:
        if not apply:
            for p in ps:
                p.restore()
            bpy.context.view_layer.update()
    return {"best": [{"param": p.label, "value": round(v, 6), "start": round(s0, 6)}
                     for p, v, s0 in zip(ps, x, starts)],
            "score_start": round(start_score, 5), "score_best": round(best, 5), "score_checked": None if final_score is None else round(final_score, 5),
            "evals": evals, "max_evals": max_evals, "converged": converged, "applied": bool(apply),
            "restored": not apply, "history": history[-40:]}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
