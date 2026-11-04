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
        checks += b_cases(tmp)
        checks += round6_cases(tmp)
        checks += fix14a_cases()
        checks += flag_cases()
        checks += args_file_cases()
        checks += plan_state_cases()
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


def edits_then_launch(first, calls, command=PS_LAUNCH):
    """Write the args file (dict), then incremental calls (name, input) that touch it, then launch silently."""
    rows, t = [(T0, assistant(tool("w", "Write", file_path="C:\\run\\args.json", content=first if isinstance(first, str) else json.dumps(first)))), (T0 + 1, done("w"))], T0 + 2
    for i, (name, inp) in enumerate(calls):
        rows += [(t, assistant(tool(f"e{i}", name, **inp))), (t + 1, done(f"e{i}"))]
        t += 2
    rows += [(t, assistant(tool("j", "PowerShell", command=command))), (t + 1, done("j"))]
    return replay(rows)


def incremental_edit_cases():
    """An args file changed by Edit (no out_dir in the call) still decides whether `plan` exempts the launch."""
    path = "C:\\run\\args.json"
    on = {"out_dir": "C:\\run\\out", "plan": True}
    off = {"out_dir": "C:\\run\\out", "plan": False}
    edit = lambda old, new: ("Edit", {"file_path": path, "old_string": old, "new_string": new})
    return [
        ("Edit turns plan true into false: a real job", announce(edits_then_launch(on, [edit("true", "false")])), "FLAG"),
        ("Edit turns plan false into true: a plan", announce(edits_then_launch(off, [edit("false", "true")])), "OK"),
        ("Edit elsewhere keeps the plan", announce(edits_then_launch(on, [edit("out", "out2")])), "OK"),
        ("two Edits, last one turns plan off", announce(edits_then_launch(on, [edit("out", "o"), edit("true", "false")])), "FLAG"),
        ("Edit that matches nothing: cannot reconstruct, no exemption", announce(edits_then_launch(on, [edit("zzz", "yyy")])), "FLAG"),
        ("shell rewrite of the file: cannot reconstruct, no exemption", announce(edits_then_launch(on, [
            ("PowerShell", {"command": "(Get-Content C:\\run\\args.json) -replace 'true','false' | Set-Content C:\\run\\args.json"})])), "FLAG"),
        ("shell read of the file does not change it", announce(edits_then_launch(on, [
            ("PowerShell", {"command": "Get-Content C:\\run\\args.json"})])), "OK"),
    ]


def plan_state_cases():
    """The plan exemption is granted only when the args file's latest state is known to say `plan: true`: from a full
    Write, then Edit / MultiEdit replays. Any other write spelling, however odd, makes it unknown."""
    path, other = "C:\\run\\args.json", "C:\\elsewhere\\args.json"
    on = {"out_dir": "C:\\run\\out", "plan": True}
    pretty = json.dumps(on, indent=2)
    pretty_old = '"out_dir": "C:\\\\run\\\\out",\n  "plan": true'
    sh = lambda cmd, name="Bash": (name, {"command": cmd})
    run = lambda calls, first=on: announce(edits_then_launch(first, calls))
    edit = lambda old, new, fp=path: ("Edit", {"file_path": fp, "old_string": old, "new_string": new})
    multi = ("MultiEdit", {"file_path": path, "edits": [{"old_string": pretty_old, "new_string": '"out_dir": "x",\n  "plan": false'}]})
    cases = [
        # Unknown state: a stale plan:true must not exempt a real render.
        ("Edit with out_dir in old_string, both lines edited", run([edit(pretty_old, '"out_dir": "C:\\\\run\\\\out2",\n  "plan": false')], pretty), "FLAG"),
        ("MultiEdit with out_dir in old_string", run([multi], pretty), "FLAG"),
        ("json.dump(d, open(p, 'w'))", run([sh("python -c \"import json; d=json.load(open('C:/run/args.json')); d['plan']=False; json.dump(d, open('C:/run/args.json','w'))\"")]), "FLAG"),
        ("json.dump line of a heredoc script", run([sh("python - <<'EOF'\nimport json\njson.dump(d, open('C:/run/args.json','w'))\nEOF")]), "FLAG"),
        ("python -c write_text", run([sh("python -c \"import pathlib; pathlib.Path('C:/run/args.json').write_text('{}')\"")]), "FLAG"),
        ("echo > rewrite", run([sh("echo '{}' > C:/run/args.json")]), "FLAG"),
        ("echo >> append", run([sh("echo x >> C:/run/args.json")]), "FLAG"),
        ("tee rewrite", run([sh("echo '{}' | tee C:/run/args.json")]), "FLAG"),
        ("cat piped into tee", run([sh("cat C:/run/args.json | tee C:/run/args.json")]), "FLAG"),
        ("Out-File rewrite", run([sh("'{}' | Out-File C:\\run\\args.json", "PowerShell")]), "FLAG"),
        ("PowerShell > redirect", run([sh("'{}' > C:\\run\\args.json", "PowerShell")]), "FLAG"),
        ("cp over the file", run([sh("cp C:/run/off.json C:/run/args.json")]), "FLAG"),
        ("mv over the file", run([sh("mv C:/run/off.json C:/run/args.json")]), "FLAG"),
        ("Copy-Item over the file", run([sh("Copy-Item C:\\run\\off.json C:\\run\\args.json", "PowerShell")]), "FLAG"),
        ("sed -i", run([sh("sed -i 's/true/false/' C:/run/args.json")]), "FLAG"),
        ("a read-only piece does not excuse a writing one", run([sh("cat C:/run/args.json; python w.py C:/run/args.json")]), "FLAG"),
        ("another tool naming the file", run([("NotebookEdit", {"notebook_path": "C:/run/args.json"})]), "FLAG"),
        ("no Write at all: a shell-created plan file is not known", announce(replay([
            (T0, assistant(tool("s", "Bash", command="echo '{\"out_dir\": \"C:/run/out\", \"plan\": true}' > C:/run/args.json"))), (T0 + 1, done("s")),
            (T0 + 2, assistant(tool("j", "PowerShell", command=PS_LAUNCH))), (T0 + 3, done("j"))])), "FLAG"),
        ("a later full Write of plan:true restores the exemption", announce(replay([
            (T0, assistant(tool("w", "Write", file_path=path, content=json.dumps(on)))), (T0 + 1, done("w")),
            (T0 + 2, assistant(tool("s", "Bash", command="cp a.json C:/run/args.json"))), (T0 + 3, done("s")),
            (T0 + 4, assistant(tool("w2", "Write", file_path=path, content=json.dumps(on)))), (T0 + 5, done("w2")),
            (T0 + 6, assistant(tool("j", "PowerShell", command=PS_LAUNCH))), (T0 + 7, done("j"))])), "OK"),
        # A mutation names this file however it is escaped; only two fully resolved absolute paths that differ are two files.
        ("sed -i on $OUT/args.json", run([sh('sed -i "s/true/false/" "$OUT/args.json"')]), "FLAG"),
        ("sed -i on a /c/run/args.json path", run([sh("sed -i 's/true/false/' /c/run/args.json")]), "FLAG"),
        ("cd then sed -i on ./args.json", run([sh("cd C:/run && sed -i 's/true/false/' ./args.json")]), "FLAG"),
        ("Set-Content -Path $dir\\args.json", run([sh("Set-Content -Path $dir\\args.json -Value '{}'", "PowerShell")]), "FLAG"),
        ("cat > quoted path with a space", announce(replay([
            (T0, assistant(tool("w", "Write", file_path="C:/my run/args.json", content=json.dumps(on)))), (T0 + 1, done("w")),
            (T0 + 2, assistant(tool("s", "Bash", command='cat > "C:/my run/args.json" <<X\n{}\nX'))), (T0 + 3, done("s")),
            (T0 + 4, assistant(tool("j", "PowerShell", command=PS_LAUNCH.replace("C:\\run\\args.json", "C:\\my run\\args.json")))),
            (T0 + 5, done("j"))])), "FLAG"),
        ("Edit file_path /c/run/args.json, old text missing", run([edit("zzz", "yyy", "/c/run/args.json")]), "FLAG"),
        ("Edit file_path /c/run/args.json turns plan off", run([edit("true", "false", "/c/run/args.json")]), "FLAG"),
        ("Edit of a different absolute folder (/c/ form)", run([edit("true", "false", "/c/elsewhere/args.json")]), "OK"),
        ("sed -i on a different absolute folder", run([sh("sed -i 's/true/false/' /c/elsewhere/args.json")]), "OK"),
        ("cat of a /c/ path", run([sh("cat /c/run/args.json")]), "OK"),
        ("cat of a quoted $OUT path", run([sh('cat "$OUT/args.json"')]), "OK"),
        ("a real plan step: plan:true written, nothing else", run([]), "OK"),
        # Established state: these leave the exemption alone.
        ("Read", run([("Read", {"file_path": path})]), "OK"),
        ("cat", run([sh("cat C:/run/args.json")]), "OK"),
        ("cat piped to grep", run([sh("cat C:/run/args.json | grep plan")]), "OK"),
        ("head and tail", run([sh("head -5 C:/run/args.json && tail -2 C:/run/args.json")]), "OK"),
        ("type", run([sh("type C:\\run\\args.json", "PowerShell")]), "OK"),
        ("Get-Content", run([sh("Get-Content C:\\run\\args.json", "PowerShell")]), "OK"),
        ("ls", run([sh("ls -l C:/run/args.json")]), "OK"),
        ("grep", run([sh("grep plan C:/run/args.json")]), "OK"),
        ("an unrelated shell command", run([sh("python make_other.py > out.txt")]), "OK"),
        ("a write to another file", run([sh("echo hi > C:/run/notes.txt")]), "OK"),
        ("the Blender launch itself, log redirected elsewhere",
         run([sh("blender -b f.blend --python r.py -- --args-file C:/run/args.json > log.txt 2>&1")]), "OK"),
        ("unrelated Edit keeps the plan", run([edit("out", "out2")]), "OK"),
        ("Edit with out_dir in old_string that keeps plan true", run([edit('"out_dir": "C:\\\\run\\\\out"', '"out_dir": "C:\\\\run\\\\o2"')], pretty), "OK"),
        ("Edit of another folder's args file", run([edit('"plan": true', '"plan": false', other)]), "OK"),
        ("shell write to another folder's args file", run([sh("echo {} > C:/elsewhere/args.json")]), "OK"),
        ("Edit turning plan on after a Write without it", run([edit("false", "true")], {"out_dir": "C:\\run\\out", "plan": False}), "OK"),
        # B4: a shell comment is not part of the command, so it cannot grant the exemption (this case used to expect OK).
        ("plan only in a shell comment", announce(launch_run(None, "PowerShell", PS_LAUNCH + ' # {"plan": true}', args_call=ARGS_FILE)), "FLAG"),
        ("plan only in a comment, Bash foreground", announce(launch_run(None, "Bash", 'blender -b scene.blend -a # {"plan": true}', took=90)), "FLAG"),
        ("# inside quotes is not a comment", announce(launch_run(None, "Bash", "blender -b scene.blend -a --args '# {\"plan\": true}'", took=90)), "OK"),
        ("inline plan in the launch command itself",
         announce(launch_run(None, "PowerShell", PS_LAUNCH + ' \'{"plan": true}\'', args_call=ARGS_FILE)), "OK"),
        ("inline escaped plan in the launch command", announce(launch_run(
            None, "Bash", 'blender -b scene.blend -a --args "{\\"plan\\": true}"', took=90)), "OK"),
    ]
    return cases


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
        ("grant is strict: a plan Written to another folder does not exempt a relative launch even after a Write there", announce(writes_then_launch([other, ("C:\\unrelated2\\args.json", other[1])], with_file("run\\args.json"))), "FLAG"),
        ("invalidate is loose: a $dir sed after a plan Write to the launched file", announce(edits_then_launch(plan[1], [("Bash", {"command": "sed -i s/true/false/ $dir/args.json"})], with_file("C:/run/args.json"))), "FLAG"),
        ("--args-file=path form, real file last", announce(writes_then_launch([other, real], eq_form)), "FLAG"),
        ("case and slash style differ", announce(writes_then_launch([("c:/RUN/args.json", plan[1])])), "OK"),
    ] + spaced_cases() + incremental_edit_cases()


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


def b_cases(tmp):
    """B1-B3 and the status-path half of B4."""
    esc_cmd = lambda out: 'blender -b f.blend --python r.py --args "{\\"out_dir\\": \\"' + out + '\\"}"'
    ps = lambda cmd: announce(launch_run(None, "PowerShell", cmd))
    sh90 = lambda cmd: announce(launch_run(None, "Bash", cmd, took=90))
    ps90 = lambda cmd: announce(launch_run(None, "PowerShell", cmd, took=90))
    plat = lambda cmd: score_run.detect_platform(replay([(T0, assistant(tool("x", "Bash", command=cmd))), (T0 + 1, done("x"))]))
    sent = lambda say, secs: announce(launch_run(say, "Bash", "blender -b f.blend --python r.py", background=True),
                                      {"started": T0, "ended": T0 + secs}, tmp)
    escaped_out = "C:\\\\\\\\renders\\\\\\\\x"  # as typed inside an escaped JSON string: C:\\\\renders\\\\x
    bg = lambda say, cmd: announce(launch_run(say, "Bash", cmd, background=True))
    return [
        # B1: a one-string -ArgumentList, and launches through a variable
        ("Start-Process one-string -ArgumentList with -a", ps('Start-Process blender -ArgumentList "-b scene.blend -a"'), "FLAG"),
        ("Start-Process one-string without a work flag", ps('Start-Process blender -ArgumentList "-b scene.blend"'), "OK"),
        ("& $blender launch", ps90("& $blender -b scene.blend -a"), "FLAG"),
        ("& $blender without -b", ps90("& $blender scene.blend -a"), "OK"),
        ('"$BLENDER" launch', sh90('"$BLENDER" -b scene.blend -a'), "FLAG"),
        ('& "$env:BLENDER" launch', ps90('& "$env:BLENDER" -b scene.blend -f 1'), "FLAG"),
        ("echo of $BLENDER is not a job", sh90('echo "$BLENDER"'), "OK"),
        ("another variable is not blender", sh90('"$OTHER" -b scene.blend -a'), "OK"),
        # B2: escaped inline JSON out_dir, and a URL is not a drive path
        ("escaped inline out_dir, real folder said", bg("About 12 s. Progress: C:/renders/x/render_status.json", esc_cmd(escaped_out)), "OK"),
        ("escaped inline out_dir, other folder said", bg("About 12 s. Progress: C:/other/render_status.json", esc_cmd(escaped_out)), "FLAG"),
        ("URL p:/ is not a Windows path", plat("curl https://example.com/p:/x"), "unknown"),
        ("URL plus /home is linux", plat("curl https://example.com/p:/x -o /home/u/f"), "linux"),
        ("a real drive path is Windows", plat('dir "C:\\run"'), "windows"),
        # B3: the total, not the first number
        ("stated total matches the render", sent("About 12 s per frame, 4 frames, total 48 s. Progress: C:/run/out/render_status.json", 48), "OK"),
        ("stated total far from the render", sent("About 10 s per frame, total 5 min. Progress: C:/run/out/render_status.json", 12), "FLAG"),
        ("sum of parts matches the render", sent("About 2 min 30 s. Progress: C:/run/out/render_status.json", 400), "OK"),
        ("sum of parts far from the render", sent("About 2 min 30 s. Progress: C:/run/out/render_status.json", 20), "FLAG"),
        # B4: the status path is the status file with a directory, not any slash
        ("slash elsewhere is not a status path", bg("About 12 s, and/or see render_status.json", "blender -b f.blend --python r.py"), "FLAG"),
        ("directory before render_status.json", bg("About 12 s, see out/render_status.json", "blender -b f.blend --python r.py"), "OK"),
        # Round 2 follow-ups
        ("echo of $BLENDER with flags launches nothing", announce(launch_run(None, "Bash", 'echo "$BLENDER" -b scene.blend -a')), "OK"),
        ("a quoted -a inside --python-expr is not a flag", announce(launch_run(None, "Bash", 'blender -b scene.blend --python-expr "-a if False else 0"')), "OK"),
        ("a URL query drive path does not decide the platform", plat("curl https://example.com/?next=p:/x -o /home/u/f"), "linux"),
        ("file URI drive path still decides the platform", plat("curl file:///C:/run/args.json -o /tmp/f"), "windows"),
        ("per-sample figure is not multiplied by frames", score_run.claimed_seconds("2 s per sample, 100 samples per frame, 40 frames"), None),
        ("per-frame figure is multiplied by frames", score_run.claimed_seconds("12 s per frame, 40 frames"), 480),
        ("a total stated after the duration wins", sent("About 12 s per frame, 48 s total. Progress: C:/run/out/render_status.json", 48), "OK"),
        ("render_status.json.bak is not the status file", bg("About 12 s, see out/render_status.json.bak", "blender -b f.blend --python r.py"), "FLAG"),
        ("status file ending a sentence", bg("About 12 s, see out/render_status.json.", "blender -b f.blend --python r.py"), "OK"),
        ("--args-file in a comment does not make a plan", announce(writes_then_launch(
            [("C:\\run\\args.json", {"out_dir": "C:\\run\\out", "plan": True})], command="blender -b scene.blend -a # --args-file C:/run/args.json", tool_name="Bash")), "FLAG"),
        # Round 3
        ("Start-Process single-quoted -ArgumentList with -a", ps("Start-Process blender -ArgumentList '-b scene.blend -a'"), "FLAG"),
        ("Start-Process single-quoted without a work flag", ps("Start-Process blender -ArgumentList '-b scene.blend'"), "OK"),
        ("comment after ;# does not exempt the plan", sh90("blender -b scene.blend -a ;# plan: true"), "FLAG"),
        ("comment after ; # does not exempt the plan", sh90("blender -b scene.blend -a; # plan: true"), "FLAG"),
        ("comment after && # does not exempt the plan", sh90("blender -b scene.blend -a && # plan: true"), "FLAG"),
        ("comment after | # does not exempt the plan", sh90("blender -b scene.blend -a | # plan: true"), "FLAG"),
        ("comment on the next line does not exempt the plan", sh90("blender -b scene.blend -a\n# plan: true"), "FLAG"),
        ("PowerShell ;# comment does not exempt the plan", ps90("blender -b scene.blend -a ;# plan: true"), "FLAG"),
        ("plan in a quoted argument still exempts", sh90("blender -b scene.blend -a --args '{\"plan\": true}'"), "OK"),
        ("per-frame figure and a total", sent("Each frame takes about 3 s, 40 frames, roughly 2 min. Progress: C:/run/out/render_status.json", 120), "OK"),
        ("compile phase and a whole-render figure", sent("About 30 s compile; whole render about 5 min. Progress: C:/run/out/render_status.json", 300), "OK"),
        ("per-frame times frame count", sent("Each frame takes about 3 s, 40 frames. Progress: C:/run/out/render_status.json", 120), "OK"),
        ("per-frame times frame count, far from the render", sent("Each frame takes about 3 s, 40 frames. Progress: C:/run/out/render_status.json", 1200), "FLAG"),
        ("whole figure far from the render still flags", sent("About 30 s compile; whole render about 5 min. Progress: C:/run/out/render_status.json", 20), "FLAG"),
    ]


def round6_cases(tmp):
    """Shell shapes a token matcher can still read (the scorer tokenizes; it does not parse the shell), judged per
    invocation, and the duration claims that were misread."""
    run = lambda say, cmd, name="Bash", secs=None, took=90: announce(
        launch_run(say, name, cmd, took=took), {"started": T0, "ended": T0 + secs} if secs else None, tmp)
    st = " Status: C:/proj/out/render_status.json"
    script = "C:/s/background_render.py"
    plan = f"blender -b f.blend --python {script} -- '{{\"plan\": true, \"out_dir\": \"C:/x\"}}'"
    real = f"blender -b f.blend --python {script} -- '{{\"out_dir\": \"C:/x\"}}'"
    return [
        # Unannounced renders hidden behind a subshell, `bash -c`, or a versioned / full-path executable name.
        ("subshell with a trailing &", run(None, "(blender -b scene.blend -a > log.txt 2>&1 &)"), "FLAG"),
        ("bash -c payload", run(None, "bash -c 'blender -b scene.blend -a'"), "FLAG"),
        ("cmd /c payload", run(None, 'cmd /c "blender.exe -b scene.blend -a"'), "FLAG"),
        ("versioned blender-4.2", run(None, "blender-4.2 -b scene.blend -a"), "FLAG"),
        ("blender.exe", run(None, "blender.exe -b scene.blend -a"), "FLAG"),
        ("Blender 5.2/blender.exe", run(None, '"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b scene.blend -a'), "FLAG"),
        ("bash -c with a probe is not a render", run(None, "bash -c 'blender -b scene.blend --python probe.py'", took=5), "OK"),
        # Each invocation is judged by its own arguments: a plan chained to the real render exempts only itself.
        ("plan alone", run(None, plan, took=8), "OK"),
        ("plan && real render", run(None, f"{plan} && {real}", took=120), "FLAG"),
        ("plan ; real render", run(None, f"{plan} ; {real}", took=120), "FLAG"),
        ("plan, newline, real render", run(None, f"{plan}\n{real}", took=120), "FLAG"),
        ("real render && plan: the plan is exempt, the render is not", run(None, f"{real} && {plan}", took=120), "FLAG"),
        ("plan with a line continuation is still one command", run(None, f"blender -b f.blend \\\n --python {script} -- '{{\"plan\": true}}'", took=8), "OK"),
        # plan: true somewhere other than the script's own arguments.
        ("plan in an echo", run(None, f"echo '{{\"plan\": true}}'; {real}", took=120), "FLAG"),
        ("plan in a : no-op", run(None, f": '{{\"plan\": true}}'; {real}", took=120), "FLAG"),
        ("plan in --python-expr", run(None, f"blender -b f.blend --python-expr 'plan: true' --python {script} -- '{{\"out_dir\": \"C:/x\"}}'", took=120), "FLAG"),
        # A status path that is a URL is not a file the user can open.
        ("status path as a URL", run("About 2 min. Status: https://example.com/render_status.json", "blender -b scene.blend -a", secs=120), "FLAG"),
        ("status path as a file URL", run("About 2 min. Status: file:///C:/proj/out/render_status.json", "blender -b scene.blend -a", secs=120), "OK"),
        # An executable held in a variable.
        ("PowerShell $exe", run(None, '$exe = "blender"; & $exe -b scene.blend -a', "PowerShell"), "FLAG"),
        ("sh exe=blender", run(None, "exe=blender; $exe -b scene.blend -a"), "FLAG"),
        ('sh exe="blender"', run(None, 'exe="blender"; "$exe" -b scene.blend -a'), "FLAG"),
        ("a variable that is not blender", run(None, 'exe=ffmpeg; $exe -b scene.blend -a'), "OK"),
        # Duration claims.
        ("2m30s is 150 s", run("About 2m30s." + st, "blender -b scene.blend -a", secs=150), "OK"),
        ("range: the upper bound", run("Between 30 s and 2 min." + st, "blender -b scene.blend -a", secs=110), "OK"),
        ("range with to", run("30 s to 2 min." + st, "blender -b scene.blend -a", secs=110), "OK"),
        ("range: far above its upper bound", run("Between 30 s and 2 min." + st, "blender -b scene.blend -a", secs=3000), "FLAG"),
        ("per-frame figure, no frame count anywhere", run("About 2 s per frame." + st, "blender -b scene.blend -a", secs=300), "FLAG"),
        ("per-frame figure, job -s/-e gives 150 frames", run("About 2 s per frame." + st, "blender -b scene.blend -s 1 -e 150 -a", secs=300), "OK"),
        ("per-frame figure, job -s/-e gives 10 frames", run("About 2 s per frame." + st, "blender -b scene.blend -s 1 -e 10 -a", secs=300), "FLAG"),
        ("per-frame figure, a single -f frame", run("About 2 s per frame." + st, "blender -b scene.blend -f 5", secs=2), "OK"),
        ("frame_count: -f wins over -s/-e", score_run.frame_count("-b scene.blend -s 1 -e 150 -f 5".split()), 1),
        ("frame_count: -f list", score_run.frame_count("-b scene.blend -f 1,3,5".split()), 3),
        ("per-frame figure, a -f list through the command tokenizer", run("About 2 s per frame." + st, "blender -b scene.blend -f 1,3,5,7,9", secs=10), "OK"),
        ("per-frame figure, a -f list, far off", run("About 2 s per frame." + st, "blender -b scene.blend -f 1,3,5,7,9", secs=200), "FLAG"),
        ("job_segments: a -f list through the tokenizer counts every frame", score_run.job_segments("blender -b scene.blend -f 1,3,5,7,9")[0]["frames"], 5),
        ("job_segments: a -f list with a range", score_run.job_segments("blender -b scene.blend -f 1..3,4")[0]["frames"], 4),
        ("job_segments: a number after -f separated by a space is not a frame", score_run.job_segments("blender -b scene.blend -f 5 3")[0]["frames"], 1),
        ("frame_count: -f range", score_run.frame_count("-b scene.blend -f 1..5".split()), 5),
        ("frame_count: -f range beats -s/-e", score_run.frame_count("-b scene.blend -s 1 -e 150 -f 1..5".split()), 5),
        ("frame_count: --render-frame=", score_run.frame_count("-b scene.blend -s 1 -e 150 --render-frame=7".split()), 1),
        ("frame_count: relative -f is unknown", score_run.frame_count("-b scene.blend -f +2".split()), None),
        ("frame_count: -a keeps the range", score_run.frame_count("-b scene.blend -s 1 -e 150 -a".split()), 150),
        ("per-frame figure, -s/-e with -f renders one frame", run("About 2 s per frame." + st, "blender -b scene.blend -s 1 -e 150 -f 5", secs=2), "OK"),
        ("chained plan to C:/plan then render to C:/actual, only the plan path said",
         run("About 2 min. Status: C:/plan/render_status.json", plan.replace("C:/x", "C:/plan") + " && " + real.replace("C:/x", "C:/actual"), secs=120), "FLAG"),
        ("chained plan then render, the render path said",
         run("About 2 min. Status: C:/actual/render_status.json", plan.replace("C:/x", "C:/plan") + " && " + real.replace("C:/x", "C:/actual"), secs=120), "OK"),
        ("claimed_seconds: 2m30s", score_run.claimed_seconds("about 2m30s"), 150),
        ("claimed_seconds: range upper bound", score_run.claimed_seconds("between 30 s and 2 min"), 120),
        ("claimed_seconds: 2 min 30 s still sums", score_run.claimed_seconds("2 min 30 s"), 150),
        ("claimed_seconds: per-frame needs a count", score_run.claimed_seconds("2 s per frame"), None),
        ("claimed_seconds: per-frame with the job's count", score_run.claimed_seconds("2 s per frame", 150), 300),
        # Unchanged: ordinary runs.
        ("Start-Process announced", run("Rendering, about 2 min." + st, "Start-Process -FilePath blender -ArgumentList '-b','C:/p/scene.blend','-a'", "PowerShell", secs=120), "OK"),
        ("short probe in the foreground", run(None, "blender -b --factory-startup --python probe.py", took=10), "OK"),
        ("~90s", run("~90s." + st, "blender -b scene.blend -a", secs=95), "OK"),
        ("1 h 5 min", run("About 1 h 5 min." + st, "blender -b scene.blend -a", secs=3900), "OK"),
        ("quoted status path with spaces", run('About 2 min. Status: "C:/My Proj/out/render_status.json"', "blender -b scene.blend -a", secs=120), "OK"),
    ]


def fix14a_cases():
    """Shell shapes that hide a launch (eval, command substitution, backticks, aliases, a variable holding a command), an
    executable built at run time (a NOTE: unreadable, not a pass), and a status path judged with no out_dir."""
    sh = lambda cmd, say=None: announce(launch_run(say, "Bash", cmd, took=90))
    ps = lambda cmd: announce(launch_run(None, "PowerShell", cmd, took=90))
    R = "blender -b scene.blend -a"
    say = lambda path: "About 12 s. Progress: " + path
    detail = lambda cmd, said=None: score_run.score_announcements(launch_run(said, "Bash", cmd, took=90))["evidence"]
    return [
        ("eval of a double-quoted launch", sh(f'eval "{R}"'), "FLAG"),
        ("eval of a single-quoted launch", sh(f"eval '{R}'"), "FLAG"),
        ("eval of bare words", sh(f"eval {R}"), "FLAG"),
        ("command substitution inside quotes", sh(f'echo "$({R})"'), "FLAG"),
        ("command substitution in an assignment", sh(f"x=$({R})"), "FLAG"),
        ("nested substitution", sh(f"echo $(echo $({R}))"), "FLAG"),
        ("backticks", sh(f"x=`{R}`"), "FLAG"),
        ("backticks inside quotes", sh(f'echo "`{R}`"'), "FLAG"),
        ("eval inside sh -c", sh("sh -c 'eval \"%s\"'" % R), "FLAG"),
        ("alias of the bare executable", sh("alias b=blender; b -b scene.blend -a"), "FLAG"),
        ("alias holding flags", sh("alias b='blender -b scene.blend'; b -a"), "FLAG"),
        ("alias that is not blender", sh("alias b=ffmpeg; b -b scene.blend -a"), "OK"),
        ("variable holding a whole command, eval", sh(f'cmd="{R}"; eval "$cmd"'), "FLAG"),
        ("variable holding a whole command, sh -c", sh(f'cmd="{R}"; sh -c "$cmd"'), "FLAG"),
        ("variable holding a whole command, run as $cmd", sh(f'cmd="{R}"; $cmd'), "FLAG"),
        ("variable assigned blender, still read", sh("B=blender; $B -b scene.blend -a"), "FLAG"),
        ("variable assigned $BLENDER, still read", sh("B=$BLENDER; $B -b scene.blend -a"), "FLAG"),
        # Not launches: printed, literal, or unrelated.
        ("single-quoted substitution is literal text", sh(f"echo '$({R})'"), "OK"),
        ("substitution of an unrelated command", sh('echo "$(date)"; ls'), "OK"),
        ("eval of an unrelated command", sh('eval "$(ssh-agent)"'), "OK"),
        ("PowerShell backtick continuation is not a substitution", ps("blender -b scene.blend `\n --python probe.py"), "OK"),
        # An executable built at run time cannot be read: NOTE, never a silent OK.
        ("executable from a substitution", sh("$(which blender) -b scene.blend -a"), "NOTE"),
        ("executable from a quoted substitution", sh('"$(which blender)" -b scene.blend -a'), "NOTE"),
        ("variable assigned from a substitution", sh("B=$(which blender); $B -b scene.blend -a"), "NOTE"),
        ("variable assigned from backticks", sh("B=`which blender`; $B -b scene.blend -a"), "NOTE"),
        ("variable built from other variables", sh('B="$DIR/$NAME"; $B -b scene.blend -a'), "NOTE"),
        ("run-time executable without Blender-shaped flags", sh("$(which python) script.py"), "OK"),
        ("a readable launch next to an unreadable one is still judged", sh(f"{R}; $(which blender) -b x.blend -a"), "FLAG"),
        # The status path with no out_dir: the folder the job renders to, when it says so.
        ("no out_dir, -o folder and the status file in it", sh("blender -b f.blend -o C:/run/out/frame_#### -a", say("C:/run/out/render_status.json")), "OK"),
        ("no out_dir, -o folder and the status file elsewhere", sh("blender -b f.blend -o C:/run/out/frame_#### -a", say("C:/other/render_status.json")), "FLAG"),
        ("no out_dir, -o folder and the status file one level up", sh("blender -b f.blend -o C:/run/out/frames/f_#### -a", say("C:/run/out/render_status.json")), "OK"),
        ("no out_dir, --render-output= folder with a slash", sh("blender -b f.blend --render-output=C:/run/out/ -a", say("C:/run/out/render_status.json")), "OK"),
        ("no out_dir, relative -o decides nothing", sh("blender -b f.blend -o //out/f_#### -a", say("C:/anywhere/render_status.json")), "OK"),
        ("no out_dir and no -o: the evidence says the name only was checked",
         "file name only" in detail("blender -b f.blend -a", say("C:/anywhere/render_status.json")), True),
        ("with an out_dir the evidence has no such caveat",
         "file name only" in detail('blender -b f.blend --python r.py -- \'{"out_dir": "C:/run/out"}\'', say("C:/run/out/render_status.json")), False),
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
