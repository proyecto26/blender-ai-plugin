#!/usr/bin/env python3
"""Check score_run.py on two small traces: one with every defect, one without. Run: python tests/agent_runs/test_score_run.py"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_run  # noqa: E402

T0 = 1000000.0


def assistant(*content):
    return {"type": "assistant", "message": {"content": list(content)}}


def text(body):
    return {"type": "text", "text": body}


def tool(call_id, name, **inp):
    return {"type": "tool_use", "id": call_id, "name": name, "input": inp}


def done(call_id):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]}}


def write_trace(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for t, event in rows:
            fh.write(json.dumps({"t": t, "line": json.dumps(event)}) + "\n")


def score(tmp, rows, manifest, status, log_body, minimized):
    trace, man, st, log, mon, skills = (os.path.join(tmp, n) for n in
                                        ("t.jsonl", "m.json", "s.json", "r.log", "mon.csv", "skills"))
    os.makedirs(skills, exist_ok=True)
    for name in ("lighting", "prop-artist"):
        os.makedirs(os.path.join(skills, name), exist_ok=True)
    write_trace(trace, rows)
    json.dump(manifest, open(man, "w", encoding="utf-8"))
    json.dump(status, open(st, "w", encoding="utf-8"))
    open(log, "w", encoding="utf-8").write(log_body)
    clock = score_run.local_clock(T0)
    open(mon, "w", encoding="utf-8").write("time,pid,minimized\n" + f"{clock},1,{minimized}\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        score_run.main(["--trace", trace, "--skills-dir", skills, "--manifest", man, "--status", st, "--log", log,
                        "--monitor", mon])
    return {r["finding"]: r["verdict"] for r in json.loads(out.getvalue())}


BAD_FINAL = ("| Stage | Skill |\n|---|---|\n| light | `lighting` |\nEl registro no contiene errores. UV correctas.\n"
             "Relay the stage table as is; the skill names are how each stage is re-run.")
BAD = [
    (T0, assistant(tool("a", score_run.LIVE_CODE, code="p.compute_device_type = 'OPTIX'"))),
    (T0 + 10, done("a")),
    (T0 + 20, assistant(tool("b", "Bash", command="blender -b f.blend --python r.py", run_in_background=True))),
    (T0 + 21, done("b")),
    (T0 + 22, {"type": "result", "subtype": "success", "result": "Listo."}),
    (T0 + 200, {"type": "result", "subtype": "success", "result": BAD_FINAL}),
]
BAD_MANIFEST = {"events": [{"stage": s, "verdict": "PASS", "time": "2026-01-01T00:00:00+00:00"}
                           for s in ("inspect", "light_camera", "model")]}
GOOD_FINAL = "| Stage | Skill |\n|---|---|\n| model | `prop-artist` |\n| light | script only: `lighting` |\nHecho."
GOOD = [
    (T0, assistant(text("La ventana sale negra, restaurala por favor."), tool("s", "Skill", skill="p:prop-artist"))),
    (T0 + 1, done("s")),
    (T0 + 2, assistant(text("Se congelara unos 10 s."), tool("a", score_run.LIVE_CODE, code="import bpy"))),
    (T0 + 12, done("a")),
    (T0 + 20, assistant(text("Render en marcha, estado en out/render_status.json."),
                        tool("b", "Bash", command="blender -b f.blend --python r.py", run_in_background=True))),
    (T0 + 21, done("b")),
    (T0 + 22, {"type": "result", "subtype": "success", "result": "Sigue en curso."}),
    (T0 + 200, {"type": "result", "subtype": "success", "result": GOOD_FINAL}),
]
GOOD_MANIFEST = {"events": [{"stage": "inspect", "verdict": "NOT_CHECKED", "time": "2026-01-01T00:00:00+00:00"},
                            {"stage": "model", "verdict": "PASS", "time": "2026-01-01T00:01:00+00:00"},
                            {"stage": "light_camera", "verdict": "PASS", "time": "2026-01-01T00:02:00+00:00"}]}
STATUS = {"state": "done", "ended": T0 + 100}


def extra_cases():
    empty = {"calls": [], "results": [], "texts": []}
    live = lambda code: {"calls": [{"name": score_run.LIVE_CODE, "input": {"code": code}, "t": None}]}
    final = lambda body, t=T0: dict(empty, results=[{"t": t, "text": body}])
    inspect = lambda reason: {"events": [{"stage": "inspect", "verdict": "PASS", "time": "t", "reason": reason}]}
    batch = {"calls": [{"name": "Bash", "input": {"command": "run_manifest.py stage='model' stage='look_dev' stage='validate'"}, "t": None}]}
    metadata = {"calls": [{"name": "Bash", "input": {"command": "run_manifest.py brief='model look_dev validate'"}, "t": None}]}
    with tempfile.TemporaryDirectory() as tmp:
        def finish(run, status):
            path = os.path.join(tmp, "s.json")
            json.dump(status, open(path, "w", encoding="utf-8"))
            return score_run.score_finish(run, argparse.Namespace(status=path, deliverable=None))["verdict"]
        checks = [
            ("two assignments are not a restore", score_run.score_preferences(
                live("p.compute_device_type = 'CUDA'\np.compute_device_type = 'OPTIX'"))["verdict"], "FLAG"),
            ("inspect PASS with no viewport", score_run.score_gates(empty, inspect("no viewport screenshot"))["verdict"], "FLAG"),
            ("inspect PASS with a viewport seen", score_run.score_gates(
                empty, inspect("Viewport screenshot reviewed; scene is visible"))["verdict"], "OK"),
            ("batch is read from the call", score_run.score_gates(batch, {"events": inspect("ok")["events"]})["verdict"], "FLAG"),
            ("names in metadata are not gates", score_run.score_gates(metadata, inspect("ok"))["verdict"], "OK"),
            ("honest handoff scored after the render ended", finish(
                final("Still running; see out/render_status.json"), {"state": "done", "ended": T0 + 100}), "NOTE"),
            ("honest handoff", finish(final("Still running; see out/render_status.json"), {"state": "running"}), "NOTE"),
            ("silent unfinished job", finish(final("Done."), {"state": "running"}), "FLAG"),
            ("raw trace has no timings", finish(final("Done.", None), {"state": "done", "ended": T0}), "SKIP"),
        ]
    return [(name, "", want, got) for name, got, want in checks if got != want]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        bad = score(tmp, BAD, BAD_MANIFEST, STATUS, "", True)
        good = score(tmp, GOOD, GOOD_MANIFEST, STATUS, "x", True)
    expect_bad = {"preferences": "FLAG", "window": "FLAG", "closing_line": "FLAG", "claims": "FLAG", "skills": "FLAG",
                  "gates": "FLAG", "announcements": "FLAG", "finish": "FLAG"}
    expect_good = {"preferences": "OK", "window": "OK", "closing_line": "OK", "claims": "OK", "skills": "OK",
                   "gates": "OK", "announcements": "OK", "finish": "NOTE"}
    failures = [("bad", k, v, bad.get(k)) for k, v in expect_bad.items() if bad.get(k) != v]
    failures += extra_cases()
    failures += [("good", k, v, good.get(k)) for k, v in expect_good.items() if good.get(k) != v]
    print(json.dumps({"passed": not failures, "failures": failures, "bad": bad, "good": good}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
