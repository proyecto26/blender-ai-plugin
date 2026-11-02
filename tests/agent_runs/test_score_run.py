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
    (T0 + 20, assistant(text("Render en marcha, unos 40 s, estado en out/render_status.json."),
                        tool("b", "Bash", command="blender -b f.blend --python r.py", run_in_background=True))),
    (T0 + 21, done("b")),
    (T0 + 22, {"type": "result", "subtype": "success", "result": "Sigue en curso."}),
    (T0 + 200, {"type": "result", "subtype": "success", "result": GOOD_FINAL}),
]
GOOD_MANIFEST = {"events": [{"stage": "inspect", "verdict": "NOT_CHECKED", "time": "2026-01-01T00:00:00+00:00"},
                            {"stage": "model", "verdict": "PASS", "time": "2026-01-01T00:01:00+00:00"},
                            {"stage": "light_camera", "verdict": "PASS", "time": "2026-01-01T00:02:00+00:00"}]}
STATUS = {"state": "done", "ended": T0 + 100}
BAD_RESTORED = [(T0 + 300, assistant(text("La captura salio negra."))),
                (T0 + 400, {"type": "result", "subtype": "success", "result": "Hecho."})]


def extra_cases():
    empty = {"calls": [], "results": [], "texts": []}
    live = lambda code: {"calls": [{"name": score_run.LIVE_CODE, "input": {"code": code}, "t": None}]}
    final = lambda body, t=T0: dict(empty, results=[{"t": t, "text": body}])
    inspect = lambda reason: {"events": [{"stage": "inspect", "verdict": "PASS", "time": "t", "reason": reason}]}
    batch = {"calls": [{"name": "Bash", "input": {"command": "run_manifest.py stage='model' stage='look_dev' stage='validate'"}, "t": None}]}
    metadata = {"calls": [{"name": "Bash", "input": {"command": "run_manifest.py brief='model look_dev validate'"}, "t": None}]}
    bash = lambda command: replay([(T0, assistant(tool("x", "Bash", command=command))), (T0 + 1, done("x"))])
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
            ("three gates inside one second, microsecond times", score_run.score_gates(empty, same_second_gates())["verdict"], "FLAG"),
            ("names in metadata are not gates", score_run.score_gates(metadata, inspect("ok"))["verdict"], "OK"),
            ("honest handoff scored after the render ended", finish(
                final("Still running; see out/render_status.json"), {"state": "done", "ended": T0 + 100}), "NOTE"),
            ("honest handoff", finish(final("Still running; see out/render_status.json"), {"state": "running"}), "NOTE"),
            ("silent unfinished job", finish(final("Done."), {"state": "running"}), "FLAG"),
            ("nohup job with no path in the text", score_run.score_announcements(
                bash('nohup blender -b f.blend --python r.py > log.txt 2>&1 &\necho "pid $!"'))["verdict"], "FLAG"),
            ("foreground render is not a background job", score_run.score_announcements(
                bash("blender -b f.blend --python r.py > log.txt 2>&1 && echo ok"))["verdict"], "OK"),
            ("raw trace has no timings", finish(final("Done.", None), {"state": "done", "ended": T0}), "SKIP"),
        ]
        checks += announcement_cases(tmp)
        checks += window_cases(tmp)
        checks += flag_cases()
        checks += args_file_cases()
    return [(name, "", want, got) for name, got, want in checks if got != want]


def replay(rows):
    """A run as score_run reads it, built from the same events a recorded session holds."""
    return score_run.collect(rows)


PS_LAUNCH = ('Start-Process -FilePath "C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\blender-launcher.exe" '
             '-ArgumentList "-b","C:\\run\\f.blend","--python","C:\\s\\background_render.py","--","--args-file","C:\\run\\args.json"')
FG_LAUNCH = 'blender-launcher.exe -b C:\\run\\f.blend --python C:\\s\\background_render.py -- --args-file C:\\run\\args.json'
ARGS_FILE = tool("w", "Write", file_path="C:\\run\\args.json", content=json.dumps({"out_dir": "C:\\run\\out"}))
PLAN_FILE = tool("w", "Write", file_path="C:\\run\\args.json", content=json.dumps({"out_dir": "C:\\run\\out", "plan": True}))
GOOD_SAY = "Rendering 4 frames in a separate Blender process, about 12 s. Progress: C:/run/out/render_status.json"


def launch_run(say, tool_name="PowerShell", command=PS_LAUNCH, args_call=ARGS_FILE, took=None, background=None):
    """A session: write the args file, optionally say something, launch the job."""
    inp = {"command": command}
    if background:
        inp["run_in_background"] = True
    rows = [(T0, assistant(args_call)), (T0 + 1, done("w"))]
    rows.append((T0 + 2, assistant(*(([text(say)] if say else []) + [tool("j", tool_name, **inp)]))))
    rows.append((T0 + 2 + (took or 1), done("j")))
    return replay(rows)


def rewritten_plan_run():
    """The args file first holds plan:true, then is rewritten without it; the real job launches silently."""
    rows = [(T0, assistant(PLAN_FILE)), (T0 + 1, done("w")),
            (T0 + 2, assistant(tool("w2", "Write", file_path="C:\\run\\args.json", content=json.dumps({"out_dir": "C:\\run\\out"})))),
            (T0 + 3, done("w2")),
            (T0 + 4, assistant(tool("j", "PowerShell", command=PS_LAUNCH))), (T0 + 5, done("j"))]
    return replay(rows)


def read_back_run(say):
    """Write the args file, read it back (a call naming the file with no contents), say something, launch."""
    rows = [(T0, assistant(ARGS_FILE)), (T0 + 1, done("w")),
            (T0 + 2, assistant(tool("r", "Read", file_path="C:/run/args.json"))), (T0 + 3, done("r")),
            (T0 + 4, assistant(text(say), tool("j", "PowerShell", command=PS_LAUNCH))), (T0 + 5, done("j"))]
    return replay(rows)


def same_second_gates():
    ev = lambda stage, t: {"stage": stage, "verdict": "PASS", "time": t}
    return {"events": [ev("inspect", "2026-01-01T00:00:00.100000+00:00"), ev("model", "2026-01-01T00:00:00.300000+00:00"),
                       ev("light_camera", "2026-01-01T00:00:00.500000+00:00")]}


def writes_then_launch(writes, command=PS_LAUNCH, say=None, tool_name="PowerShell"):
    """Several Write calls (path, content dict) in order, then one launch."""
    rows, t = [], T0
    for i, (path, body) in enumerate(writes):
        rows += [(t, assistant(tool(f"w{i}", "Write", file_path=path, content=json.dumps(body)))), (t + 1, done(f"w{i}"))]
        t += 2
    rows += [(t, assistant(*(([text(say)] if say else []) + [tool("j", tool_name, command=command)]))), (t + 1, done("j"))]
    return replay(rows)


def flag_cases():
    """Every spelling of a Blender render, animation or script flag, launched silently: a job that is seen scores FLAG."""
    quiet = lambda cmd, **kw: announce(launch_run(None, "Bash", cmd, **kw))
    render = lambda cmd: quiet(cmd, took=90)  # a foreground run long enough to need a message
    return [
        ("-f 1 render, silent", render("blender -b scene.blend -f 1"), "FLAG"),
        ("-f before -b", render("blender scene.blend -f 1 -b"), "FLAG"),
        ("-a render, silent", render("blender -b scene.blend -a"), "FLAG"),
        ("--render-anim, silent", render("blender --background scene.blend --render-anim"), "FLAG"),
        ("--render-frame 1, silent", render("blender -b scene.blend --render-frame 1"), "FLAG"),
        ("--render-frame=1, silent", render("blender -b scene.blend --render-frame=1"), "FLAG"),
        ("combined -ba, silent", render("blender -ba scene.blend"), "FLAG"),
        ("combined -bf 1, silent", render("blender -bf 1 scene.blend"), "FLAG"),
        ("combined -f1, silent", render("blender -b scene.blend -f1"), "FLAG"),
        ("-P script in the background", quiet("blender -b scene.blend -P r.py", background=True), "FLAG"),
        ("--python-expr in the background", quiet("blender -b scene.blend --python-expr 'import bpy' &"), "FLAG"),
        ("--python-text in the background", quiet("blender -b scene.blend --python-text Run", background=True), "FLAG"),
        ("--python=file in the background", quiet("blender -b scene.blend --python=r.py", background=True), "FLAG"),
        ("PowerShell -ArgumentList with -f", announce(launch_run(None, command='Start-Process blender.exe -ArgumentList "-b","a.blend","-f","1"')), "FLAG"),
        ("second blender in a chain renders", render("blender -b a.blend --python-exit-code 1 && blender -b b.blend -f 1"), "FLAG"),
        ("blender.exe with a quoted path", render('"C:/Program Files/Blender/blender.exe" -b a.blend -f 1'), "FLAG"),
        # Not jobs: no background, no work, or the flag belongs to the script after `--`.
        ("no -b: a GUI session", render("blender scene.blend -f 1"), "OK"),
        ("-b alone", render("blender -b scene.blend"), "OK"),
        ("-F is the render format, not -f", render("blender -b scene.blend -F PNG"), "OK"),
        ("-B is not -b", render("blender -B scene.blend -f 1"), "OK"),
        ("-a after -- is the script's", render("blender -b scene.blend -- -a"), "OK"),
        ("--python-exit-code is not a script", render("blender -b scene.blend --python-exit-code 1"), "OK"),
        ("quick -P script is not a render", quiet("blender -b scene.blend -P r.py"), "OK"),
        ("flag text inside a quoted expression", quiet("blender -b scene.blend --python-expr 'print(\"-a\")'"), "OK"),
        ("announced -f render", announce(launch_run(GOOD_SAY, "Bash", "blender -b scene.blend -f 1", took=90)), "OK"),
    ]


def args_file_cases():
    real = ("C:\\run\\args.json", {"out_dir": "C:\\run\\out"})
    other = ("C:\\unrelated\\args.json", {"out_dir": "C:\\unrelated\\out", "plan": True})
    plan = ("C:\\run\\args.json", {"out_dir": "C:\\run\\out", "plan": True})
    with_file = lambda ref: PS_LAUNCH.replace("C:\\run\\args.json", ref)
    eq_form = PS_LAUNCH.replace('"--args-file","C:\\run\\args.json"', '"--args-file=C:\\run\\args.json"')
    return [
        ("same basename in another folder does not exempt a real job", announce(writes_then_launch([real, other])), "FLAG"),
        ("same basename, forward slashes", announce(writes_then_launch(
            [("C:/run/args.json", real[1]), ("C:/unrelated/args.json", other[1])], with_file("C:/run/args.json"))), "FLAG"),
        ("order swapped: the plan file is the launched one", announce(writes_then_launch([other, plan])), "OK"),
        ("only the unrelated plan file was written", announce(writes_then_launch([other])), "FLAG"),
        ("launch names a bare file: the name decides", announce(writes_then_launch([plan], with_file("args.json"))), "OK"),
        ("launch names .\\args.json: the name decides", announce(writes_then_launch([plan], with_file(".\\args.json"))), "OK"),
        ("earlier write is a bare name", announce(writes_then_launch([("args.json", plan[1])])), "OK"),
        ("relative folder tail matches the absolute write", announce(writes_then_launch([plan], with_file("run\\args.json"))), "OK"),
        ("relative folder tail does not match another folder", announce(writes_then_launch([other], with_file("run\\args.json"))), "FLAG"),
        ("--args-file=path form, real file last", announce(writes_then_launch([other, real], eq_form)), "FLAG"),
        ("case and slash style differ", announce(writes_then_launch([("c:/RUN/args.json", plan[1])])), "OK"),
    ] + spaced_cases()


def spaced_cases():
    """Paths with spaces: a quoted path is one token, in the args-file match and in the output-folder check."""
    real = (r"C:\my run\args.json", {"out_dir": r"C:\my run\out"})
    other = (r"C:\my unrelated\args.json", {"out_dir": r"C:\my unrelated\out", "plan": True})
    plan = (real[0], dict(real[1], plan=True))
    ps = PS_LAUNCH.replace("C:\\run\\args.json", real[0])
    bash = "blender-launcher.exe -b C:/run/f.blend --python C:/s/background_render.py -- --args-file '%s'" % "C:/my run/args.json"
    bash_dq = bash.replace("'", '"')
    bash_eq = bash.replace("--args-file '", "--args-file=\"").rstrip("'") + '"'
    say_real = "Rendering 4 frames, about 12 s. Progress: C:/my run/out/render_status.json"
    say_other = "Rendering 4 frames, about 12 s. Progress: C:/my unrelated/out/render_status.json"
    say_prefix = "Rendering 4 frames, about 12 s. Progress: C:/my/render_status.json"
    one = lambda writes, cmd, say=None, tool_name="PowerShell": announce(writes_then_launch(writes, cmd, say, tool_name))
    return [
        ("spaced: unrelated plan file does not exempt a real job", one([real, other], ps), "FLAG"),
        ("spaced bash single quotes: same", one([real, other], bash, tool_name="Bash"), "FLAG"),
        ("spaced bash double quotes: same", one([real, other], bash_dq, tool_name="Bash"), "FLAG"),
        ("spaced --args-file=\"..\": same", one([real, other], bash_eq, tool_name="Bash"), "FLAG"),
        ("spaced: the launched plan file does exempt", one([other, plan], ps), "OK"),
        ("spaced: announcing the unrelated folder is not enough", one([real, other], ps, say_other), "FLAG"),
        ("spaced: announcing only the shared prefix is not enough", one([real], ps, say_prefix), "FLAG"),
        ("spaced: announcing the real folder is enough", one([real, other], ps, say_real), "OK"),
    ]


def announce(run, status=None, tmp=None):
    args = argparse.Namespace(status=None)
    if status is not None:
        args.status = os.path.join(tmp, "st.json")
        json.dump(status, open(args.status, "w", encoding="utf-8"))
    return score_run.score_announcements(run, args)["verdict"]


def announcement_cases(tmp):
    slow = {"started": T0, "ended": T0 + 120}
    return [
        # Baselines that told the user nothing must be FLAG, not merely "not OK".
        ("PowerShell Start-Process, no message", announce(launch_run(None)), "FLAG"),
        ("Bash nohup job, no message", announce(launch_run(None, "Bash", "nohup blender -b f.blend --python r.py > log.txt 2>&1 &")), "FLAG"),
        ("run_in_background job, no message", announce(launch_run(None, "Bash", "blender -b f.blend --python r.py", background=True)), "FLAG"),
        ("foreground render of 90 s, no message", announce(launch_run(None, "Bash", FG_LAUNCH, took=90)), "FLAG"),
        ("foreground background_render.py, no message, untimed", announce(launch_run(None, "Bash", FG_LAUNCH)), "FLAG"),
        # A message that is not the real thing is not enough.
        ("generic path, not the real out_dir", announce(launch_run("Rendering in the background, about 12 s, see render_status.json")), "FLAG"),
        ("another folder's path", announce(launch_run("About 12 s. Progress: C:/other/out/render_status.json")), "FLAG"),
        ("prefix-sharing folder is not the real one", announce(launch_run("About 12 s. Progress: C:/run/outdated/render_status.json")), "FLAG"),
        ("nested folder is not the real one", announce(launch_run("About 12 s. Progress: C:/run/out/sub/render_status.json")), "OK"),
        ("args read back, then a wrong folder announced", announce(read_back_run("About 12 s. Progress: C:/wrong/out/render_status.json")), "FLAG"),
        ("args read back, real folder announced", announce(read_back_run(GOOD_SAY)), "OK"),
        ("plan args rewritten without plan, then a silent real job", announce(rewritten_plan_run()), "FLAG"),
        ("no duration", announce(launch_run("Rendering. Progress: C:/run/out/render_status.json")), "FLAG"),
        # Valid ones.
        ("PowerShell launch announced with path and duration", announce(launch_run(GOOD_SAY)), "OK"),
        ("backslash path in the message", announce(launch_run("About 12 s. Progress: C:\\run\\out\\render_status.json")), "OK"),
        ("minutes are a duration", announce(launch_run("About 2 minutos. Progress: C:/run/out/render_status.json")), "OK"),
        ("foreground render announced", announce(launch_run(GOOD_SAY, "Bash", FG_LAUNCH, took=90)), "OK"),
        ("the plan step needs no message", announce(launch_run(None, "Bash", FG_LAUNCH, args_call=PLAN_FILE, took=60)), "OK"),
        ("a quick script is not a render job", announce(launch_run(None, "PowerShell", '& "blender-launcher.exe" -b f.blend --python r.py')), "OK"),
        # The duration said must match what the render took.
        ("said 12 s, took 120 s", announce(launch_run(GOOD_SAY), slow, tmp), "FLAG"),
        ("said 110 s, took 120 s", announce(launch_run(GOOD_SAY.replace("12 s", "110 s")), slow, tmp), "OK"),
    ]


def window_cases(tmp):
    mon = os.path.join(tmp, "m.csv")
    open(mon, "w", encoding="utf-8").write("time,pid,minimized\n" + f"{score_run.local_clock(T0)},1,True\n")
    silent_win = replay([(T0, assistant(tool("a", "PowerShell", command="Get-Date"))), (T0 + 1, done("a"))])
    silent_mac = replay([(T0, assistant(tool("a", "Bash", command="ls /Users/me/proj"))), (T0 + 1, done("a"))])
    window = lambda run, platform: score_run.score_window(run, argparse.Namespace(monitor=mon, platform=platform), None)["verdict"]
    return [
        ("minimized, never told, Windows", window(silent_win, "windows"), "FLAG"),
        ("minimized, never told, macOS: the image decides", window(silent_mac, "macos"), "NOTE"),
        ("minimized, platform read from Windows paths", window(silent_win, "auto"), "FLAG"),
        ("minimized, platform read from macOS paths", window(silent_mac, "auto"), "NOTE"),
    ]


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
    with tempfile.TemporaryDirectory() as tmp:
        late = list(BAD_RESTORED)
        got = score(tmp, late, GOOD_MANIFEST, STATUS, "x", True)["window"]
    if got != "FLAG":
        failures.append(("told only after the window was restored", "", "FLAG", got))
    failures += [("good", k, v, good.get(k)) for k, v in expect_good.items() if good.get(k) != v]
    print(json.dumps({"passed": not failures, "failures": failures, "bad": bad, "good": good}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
