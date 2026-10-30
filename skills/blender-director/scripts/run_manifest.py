"""Append stage events to a production run manifest (<out_dir>/run_manifest.json).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/run_manifest.py", init_globals={"ARGS": {
        "out_dir": "/tmp/run", "brief": {"asset": "SM_Crate", "target": "godot"},
        "stage": "validate", "skill": "blender-mcp-workflow", "script": "validate_asset.py",
        "args": {"objects": ["SM_Crate"]}, "result_summary": {"fails": 0, "warns": 0},
        "verdict": "PASS", "capture": "views/crate_3q.png"}})["result"]

The first call creates the file (with `brief`); with no `stage` it only creates / reports status.

ARGS:
    out_dir         (str, required) run folder; every path written or read stays inside it
    brief           (dict|str) production brief, stored when the manifest is created (or still empty)
    stage           (str) inspect | brief | model | look_dev | light_camera | animate | film | handoff |
                    validate | export | verify  (animate, film, handoff are optional: N/A unless recorded)
    skill, script   (str) what produced the evidence
    args            (dict) the ARGS passed to that script
    result_summary  (dict|str) the few numbers/verdicts that matter, not the whole result
    verdict         (str) PASS | FAIL | NOT_CHECKED | N/A   (NOT_CHECKED is never a pass)
    reason          (str) required for FAIL, N/A, NOT_CHECKED and for a PASS that accepts a WARN (warn=true)
    warn            (bool) PASS accepted despite a WARN (needs reason)
    capture         (str|None) screenshot / render path inside out_dir (relative paths resolve there)
    exports         (list[str]) files inside out_dir; their sha256 and size are recorded
    cause           (str) geometry | materials | lighting | camera | export | tool-error; required on the
                    second consecutive FAIL of the same stage (stop and report, no third blind retry)

Rules: a PASS for a stage is refused while an earlier stage's latest verdict is FAIL; a PASS for `export`
or `verify` also needs the latest `validate` verdict to be PASS or N/A (NOT_CHECKED / missing is refused). Nothing is ever
deleted. Result: events count, `gates` (latest verdict per stage), `blocked_by`, `stop`, `complete`
(every stage PASS or N/A).
"""
import datetime
import hashlib
import json
import os
import sys

STAGES = ["inspect", "brief", "model", "look_dev", "light_camera", "animate", "film", "handoff",
          "validate", "export", "verify"]
OPTIONAL = {"animate", "film", "handoff"}  # tracks most asset runs never enter; N/A until a verdict is recorded
VERDICTS = ["PASS", "FAIL", "NOT_CHECKED", "N/A"]
CAUSES = ["geometry", "materials", "lighting", "camera", "export", "tool-error"]
NAME = "run_manifest.json"


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


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _inside(out_dir, path):
    """Resolve path against out_dir; refuse anything that lands outside it."""
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(out_dir, path))
    root = os.path.realpath(out_dir)
    if os.path.commonpath([root, full]) != root:
        raise ValueError(f"path outside out_dir refused: {path}")
    return full, os.path.relpath(full, root).replace(os.sep, "/")


def _sha256(full):
    h = hashlib.sha256()
    with open(full, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gates(events):
    latest = {}
    for e in events:
        latest[e["stage"]] = e["verdict"]
    return {s: latest.get(s, "N/A" if s in OPTIONAL else "NOT_CHECKED") for s in STAGES}


def _blocked_by(events, stage):
    latest = _gates(events)
    for s in STAGES[:STAGES.index(stage)]:
        if latest[s] == "FAIL":
            return s
    return None


def _summary(manifest, extra=None):
    gates = _gates(manifest["events"])
    out = {"manifest": NAME, "events": len(manifest["events"]), "gates": gates,
           "blocked_by": next((s for s in STAGES if gates[s] == "FAIL"), None),
           "complete": all(v in ("PASS", "N/A") for v in gates.values())}
    out.update(extra or {})
    return out


def main(out_dir, brief=None, stage=None, skill=None, script=None, args=None, result_summary=None,
         verdict=None, reason=None, warn=False, capture=None, exports=None, cause=None):
    if not out_dir:
        raise ValueError("out_dir is required")
    os.makedirs(out_dir, exist_ok=True)
    path, _ = _inside(out_dir, NAME)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    else:
        manifest = {"schema": "run-manifest/1", "created": _now(), "brief": brief or {}, "events": []}
    if brief and not manifest.get("brief"):
        manifest["brief"] = brief
    stop = False
    if stage is not None:
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")
        if not (skill and script):
            raise ValueError("skill and script are required (use script='manual' for a visual-only check)")
        if verdict in ("FAIL", "N/A", "NOT_CHECKED") and not reason:
            raise ValueError(f"reason is required for verdict {verdict}")
        if verdict == "PASS" and warn and not reason:
            raise ValueError("a PASS that accepts a WARN needs a recorded reason")
        if verdict == "PASS":
            blocker = _blocked_by(manifest["events"], stage)
            if blocker:
                raise ValueError(f"stage '{stage}' is blocked: '{blocker}' is FAIL; fix it first")
            if stage in ("export", "verify"):
                gate = _gates(manifest["events"])["validate"]
                if gate not in ("PASS", "N/A"):
                    raise ValueError(f"stage '{stage}' cannot PASS while 'validate' is {gate}: "
                                     "record a validate PASS (or N/A with a reason) first")
        if cause is not None and cause not in CAUSES:
            raise ValueError(f"cause must be one of {CAUSES}")
        prev = [e for e in manifest["events"] if e["stage"] == stage]
        if verdict == "FAIL" and prev and prev[-1]["verdict"] == "FAIL":
            if not cause:
                raise ValueError(f"second consecutive FAIL at '{stage}': pass cause={CAUSES}, then stop "
                                 "and report to the user instead of retrying")
            stop = True
        cap_rel = _inside(out_dir, capture)[1] if capture else None
        files = []
        for f in exports or []:
            full, rel = _inside(out_dir, f)
            if not os.path.isfile(full):
                raise ValueError(f"export file not found: {f}")
            files.append({"path": rel, "sha256": _sha256(full), "bytes": os.path.getsize(full)})
        event = {"stage": stage, "skill": skill, "script": script, "args": args or {},
                 "result_summary": result_summary if result_summary is not None else {},
                 "verdict": verdict, "reason": reason, "capture": cap_rel, "time": _now()}
        if warn:
            event["warn"] = True
        if files:
            event["exports"] = files
        if cause:
            event["cause"] = cause
        if stop:
            event["stopped"] = True
        manifest["events"].append(event)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return _summary(manifest, {"stop": stop})


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if __name__ == "__main__" and "bpy" not in sys.modules:
    print(json.dumps(result, indent=2))
