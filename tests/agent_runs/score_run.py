#!/usr/bin/env python3
"""Compare what an agent run claimed with what its session trace shows.

    python tests/agent_runs/score_run.py --trace run.jsonl --skills-dir skills
        [--monitor monitor.csv] [--manifest run_manifest.json] [--status render_status.json] [--log render.log]
        [--deliverable final.mp4] [--platform auto|windows|macos|linux]

The trace is `claude -p --output-format stream-json --verbose` output, raw or with each line wrapped as
{"t": epoch, "line": "..."} (timings need the wrapped form). Prints one verdict per finding: OK, FLAG, NOTE (worth
reading, not a defect) or SKIP (input missing). --strict exits 1 on any FLAG.

Window: a minimized window gives a black capture on Windows only (blender-mcp-workflow `references/live-session.md`). With
--platform windows (or auto, when the trace shows Windows paths or the PowerShell tool, or nothing decides) a minimized
sample needs a message to the user during the run. On macOS and Linux it is a NOTE: the screenshot still works, so the image
decides, and a blank one recorded as an inspect PASS is caught by the gates check.

Announcements: a Blender job launched in the background (Bash `&`, `nohup`, `run_in_background`; PowerShell `Start-Process`,
`Start-Job`, `run_in_background`), or a render run in the foreground, needs a message to the user BEFORE the launch that
names the real out_dir (taken from the launch command or the args file it names; without one, a path to render_status.json)
and a duration. With --status the duration is compared with the render's real time: more than 3 times off, and more than
5 s, is a FLAG. The plan step (`plan: true`) is exempt, since it produces the message.

Text matching is heuristic and every such check says so. One run shows one case, not general reliability, and the
score runs after the job, so it catches regressions rather than stopping a bad report.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

PRELOADED = {"blender-director", "blender-mcp-workflow"}
LIVE_CODE = "mcp__blender__execute_blender_code"
RUNNING_WORDS = r"still running|sigue|en curso|todav[ií]a|no ha terminado|cuando termine|when it finishes|in progress"
MINIMIZED_WORDS = r"minimi|restaur|restore|black|negr"
FREEZE_WORDS = r"congel|freez|bloque|block|not responding|no responde"
# A Bash job sent to the background (`nohup`, or a lone `&`, not `&&`, `2>&1` or `&>`), as agents do on macOS/Linux.
DETACHED = r"\bnohup\b|(?<![&>|])&(?![&>])"
# PowerShell has no trailing `&` (a leading one is the call operator); it detaches with these.
DETACHED_PS = r"\bStart-Process\b|\bStart-Job\b|-AsJob\b|\bstart\s+/b\b"
SHELLS = ("Bash", "PowerShell")
BLENDER_EXE = r"blender(?:-launcher)?(?:\.exe)?"
# Blender stops reading its own flags at `--`; what follows belongs to the script. Flags are case-sensitive (`-F` is not `-f`).
BG_FLAGS = {"-b", "--background"}
# Work that starts a job: render animation / frame, run a script. Short and long spellings, plus the `--flag=value` forms.
WORK_FLAGS = {"-a", "--render-anim", "-f", "--render-frame", "-P", "--python", "--python-text", "--python-expr"}
RENDER_FLAGS = {"-a", "--render-anim", "-f", "--render-frame"}
# Not valid Blender, but an agent may write `-ba` or `-bf 1`; scoring leans to seeing a job, so a cluster of the short
# letters b/a/f/P (optionally ending in digits, `-f1`) counts as each flag it contains.
SHORT_CLUSTER = r"-([bafP]+)\d*"
TOKEN = r"\"([^\"]*)\"|'([^']*)'|([^\s,\"']+)"
PIPE_END = {"&&", "||", ";", "|"}
PLAN_ON = r"[\"']?plan[\"']?\s*[:=]\s*[\"']?(?:true|\$true)\b"
DURATION = (r"(\d+(?:[.,]\d+)?)\s*(segundos?|seconds?|secs?|minutos?|minutes?|mins?|horas?|hours?|hrs?|s|h)\b")
UNIT_SECONDS = {"s": 1, "h": 3600}
FOREGROUND_LONG_S = 20
LOG_CLAIM = r"(registro|log)\b.{0,40}(no contiene errores|sin errores|no errors|is clean|limpio)"
UV_CLAIM = r"\buvs?\b.{0,20}(correct|ok\b)"
OPEN_CLAIM = r"(abre sin problema|opens? (fine|cleanly|without))"
NO_VIEWPORT = (r"\b(no|sin|without|not|cannot)\b.{0,40}(viewport|captur|screenshot)"
               r"|(viewport|captur|screenshot).{0,40}(black|negr|unavailable|no disponible)")
STAGE_NAME = r"""\bstage[\\"': =]+(inspect|brief|model|look_dev|light_camera|animate|film|handoff|validate|export|verify)\b"""


def parse_trace(path):
    events = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                outer = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = None
            if "line" in outer and "t" in outer:
                t = outer["t"]
                try:
                    outer = json.loads(outer["line"])
                except json.JSONDecodeError:
                    continue
            events.append((t, outer))
    return events


def collect(events):
    run = {"calls": [], "texts": [], "results": [], "by_id": {}}
    seq = 0
    for t, d in events:
        kind = d.get("type")
        if kind == "assistant":
            for c in d["message"]["content"]:
                seq += 1
                if c["type"] == "text" and c["text"].strip():
                    run["texts"].append({"t": t, "seq": seq, "text": c["text"], "child": bool(d.get("parent_tool_use_id"))})
                elif c["type"] == "tool_use":
                    call = {"t": t, "seq": seq, "end": None, "name": c["name"], "input": c["input"],
                            "child": bool(d.get("parent_tool_use_id")), "result": ""}
                    run["calls"].append(call)
                    run["by_id"][c["id"]] = call
        elif kind == "user" and isinstance(d["message"]["content"], list):
            for c in d["message"]["content"]:
                if c.get("type") == "tool_result" and c["tool_use_id"] in run["by_id"]:
                    call = run["by_id"][c["tool_use_id"]]
                    call["end"] = t
                    body = c.get("content")
                    call["result"] = body if isinstance(body, str) else " ".join(
                        i.get("text", "") for i in body or [] if isinstance(i, dict))
        elif kind == "result":
            run["results"].append({"t": t, "text": d.get("result") or "", "subtype": d.get("subtype")})
    return run


def verdict(finding, state, evidence, heuristic=False):
    return {"finding": finding, "verdict": state, "evidence": evidence, "heuristic": heuristic}


def score_preferences(run):
    bad = []
    for c in run["calls"]:
        if c["name"] != LIVE_CODE:
            continue
        code = c["input"].get("code", "")
        writes = re.search(r"compute_device_type\s*=[^=]", code)
        device_use = re.search(r"\b\w+\.use\s*=[^=]", code) and "devices" in code
        if writes or device_use:
            bad.append(c["t"])
    if bad:
        return verdict("preferences", "FLAG", f"{len(bad)} live call(s) write Cycles device preferences; check that "
                       "the user asked and that the old values came back", True)
    return verdict("preferences", "OK", "no live write to Cycles device preferences", True)


def minimized_spans(monitor):
    rows = list(csv.DictReader(open(monitor, encoding="utf-8-sig")))
    return [r["time"] for r in rows if r.get("minimized") == "True"]


def local_clock(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


def detect_platform(run):
    """windows | macos | linux, from the tools and paths in the trace; 'unknown' when nothing decides."""
    blob = " ".join(str(c["input"]) for c in run["calls"])
    if any(c["name"] == "PowerShell" for c in run["calls"]) or re.search(r"[A-Za-z]:[\\/]", blob):
        return "windows"
    if re.search(r"/Users/|/Applications/|\.app/", blob):
        return "macos"
    if re.search(r"/home/|/usr/|/tmp/", blob):
        return "linux"
    return "unknown"


def score_window(run, args, manifest):
    if not args.monitor:
        return verdict("window", "SKIP", "no --monitor")
    samples = minimized_spans(args.monitor)
    if not samples:
        return verdict("window", "OK", "window never minimized")
    platform = getattr(args, "platform", "auto") or "auto"
    if platform == "auto":
        platform = detect_platform(run)
    detail = f"minimized in {len(samples)} sample(s), {samples[0]} to {samples[-1]}"
    if platform in ("macos", "linux"):
        return verdict("window", "NOTE", f"{detail}; on {platform} a minimized window still captures, so the image decides, "
                       "not the window state (a blank capture recorded as an inspect PASS is flagged by the gates check)", True)
    # Only a message sent while the window was still minimized gives the user the chance to act on it.
    told = [x for x in run["texts"] if re.search(MINIMIZED_WORDS, x["text"], re.I) and not x["child"]
            and (x["t"] is None or local_clock(x["t"]) <= max(samples))]
    problems = []
    if not told:
        problems.append("the agent did not tell the user during the run")
    for e in (manifest or {}).get("events", []):
        if e["stage"] == "inspect" and e["verdict"] == "PASS":
            clock = datetime.fromisoformat(e["time"]).replace(
                tzinfo=datetime.fromisoformat(e["time"]).tzinfo or timezone.utc).astimezone().strftime("%H:%M:%S")
            if min(samples) <= clock <= max(samples):
                problems.append("inspect recorded PASS while minimized")
    detail += "" if platform == "windows" else " (platform not recognized, judged as Windows)"
    if problems:
        return verdict("window", "FLAG", detail + "; " + "; ".join(problems), True)
    return verdict("window", "OK", detail + "; user told, inspect not passed", True)


def score_closing_line(run):
    final = run["results"][-1]["text"] if run["results"] else ""
    if "Relay the stage table" in final:
        return verdict("closing_line", "FLAG", "the message to the user ends with the line meant for a calling agent")
    return verdict("closing_line", "OK", "no caller line in the message to the user")


def score_claims(run, args):
    final = run["results"][-1]["text"] if run["results"] else ""
    code = " ".join(str(c["input"]) for c in run["calls"])
    problems = []
    if re.search(LOG_CLAIM, final, re.I):
        if not args.log:
            return verdict("claims", "SKIP", "a log claim was made but no --log was given", True)
        if os.path.getsize(args.log) == 0:
            problems.append("claims a clean log, but the log is empty")
    if re.search(UV_CLAIM, final, re.I) and "uv_unwrap_check" not in code:
        problems.append("claims correct UVs without running uv_unwrap_check.py")
    if re.search(OPEN_CLAIM, final, re.I) and "open_mainfile" not in code and " -b " not in code:
        problems.append("claims the file opens, with no sign of opening it")
    if problems:
        return verdict("claims", "FLAG", "; ".join(problems), True)
    return verdict("claims", "OK", "no listed overclaim found", True)


def score_skills(run, args):
    known = set(os.listdir(args.skills_dir))
    loaded = set(PRELOADED)
    for c in run["calls"]:
        if c["name"] == "Skill":
            loaded.add(c["input"].get("skill", "").split(":")[-1])
    final = run["results"][-1]["text"] if run["results"] else ""
    named = set()
    for line in final.splitlines():
        if not line.lstrip().startswith("|") or "script only" in line.lower():
            continue
        cells = line.split("|")
        if len(cells) > 2:
            named.update(n for n in re.findall(r"[a-z0-9-]+", cells[2]) if n in known)
    missing = sorted(named - loaded)
    if missing:
        return verdict("skills", "FLAG", f"stage table names skills never loaded: {missing}", True)
    return verdict("skills", "OK", f"{len(named)} named in the stage table, all loaded", True)


def score_gates(run, manifest):
    if manifest is None:
        return verdict("gates", "SKIP", "no --manifest")
    events = manifest.get("events", [])
    if not events:
        return verdict("gates", "FLAG", "no gate was recorded")
    problems = []
    for c in run["calls"]:
        text = c["input"].get("code") or c["input"].get("command") or ""
        stages = re.findall(STAGE_NAME, text) if "run_manifest" in text else []
        if len(stages) >= 3:
            problems.append(f"one call writes {len(stages)} gates: {stages}")
    by_time = {}
    for e in events:
        by_time.setdefault(str(e["time"])[:19], []).append(e["stage"])
    # A loop writes gates with no literal stage= in its code, so also read the manifest's own timestamps.
    problems += [f"{len(v)} gates in the same second: {v}" for v in by_time.values() if len(v) >= 3]
    last = {}
    for i, e in enumerate(events):
        if e["verdict"] == "PASS":
            last[e["stage"]] = i
    for e in events:
        if e["stage"] == "inspect" and e["verdict"] == "PASS" and re.search(NO_VIEWPORT, e.get("reason") or "", re.I):
            problems.append("inspect recorded PASS while its reason says no viewport was seen")
    if "light_camera" in last and last.get("model", -1) > last["light_camera"]:
        problems.append("light_camera PASS is older than the last model PASS")
    if problems:
        return verdict("gates", "FLAG", "; ".join(problems), True)
    return verdict("gates", "OK", f"{len(events)} events, no call writes three or more", True)


def norm_path(text):
    return re.sub(r"/+", "/", text.replace("\\\\", "/").replace("\\", "/")).lower().rstrip("/")


def seconds_in(text):
    """Every duration stated in the text, in seconds."""
    found = []
    for number, unit in re.findall(DURATION, text, re.I):
        unit = unit.lower()
        scale = UNIT_SECONDS.get(unit) or (60 if unit.startswith("min") else 3600 if unit[0] == "h" else 1)
        found.append(float(number.replace(",", ".")) * scale)
    return found


def blender_segments(command):
    """Each Blender invocation in the command, as the flags Blender itself reads (up to `--` or the next shell operator).
    Quoted pieces and comma lists (PowerShell -ArgumentList "-b","f.blend") become separate tokens."""
    segments, current = [], None
    for quoted, single, bare in re.findall(TOKEN, command):
        tok = quoted or single or bare
        if re.fullmatch(BLENDER_EXE, tok.replace("\\", "/").rsplit("/", 1)[-1], re.I):
            current = []
            segments.append(current)
        elif current is not None:
            if tok == "--" or (bare and tok in PIPE_END):
                current = None
            else:
                current.append(tok)
    return segments


def flag_set(tokens, wanted):
    """Which of the wanted flags the tokens hold, in any spelling: `-f`, `--render-frame=1`, `-bf`, `-f1`."""
    found = set()
    for tok in tokens:
        name = tok.split("=", 1)[0] if tok.startswith("--") else tok
        if name in wanted:
            found.add(name)
        cluster = re.fullmatch(SHORT_CLUSTER, tok)
        if cluster:
            found |= {"-" + ch for ch in cluster.group(1) if "-" + ch in wanted}
    return found


def blender_job(command):
    """None, or {'render': bool}: a background Blender invocation that renders or runs a script."""
    job = None
    for tokens in blender_segments(command):
        if flag_set(tokens, BG_FLAGS) and flag_set(tokens, WORK_FLAGS):
            job = job or {"render": False}
            job["render"] = job["render"] or bool(flag_set(tokens, RENDER_FLAGS))
    if job and re.search(r"background_render\.py", command):
        job["render"] = True
    return job


def path_mentions(text, base):
    """Every path in the text that ends in the file name, normalized, as written (a bare name stays bare). A quoted
    string is taken whole, spaces included; outside quotes a path ends at whitespace."""
    flat = norm_path(text)
    tail = re.escape(base) + r"(?![\w.\-])"
    quoted = re.findall(r"[\"']([^\"'\n]*" + tail + ")", flat)
    rest = re.sub(r"([\"'])[^\"'\n]*\1", " ", flat)
    return quoted + re.findall(r"[^\s\"'`,;()=<>|&]*" + tail, rest)


def same_file(a, b):
    """Whether two normalized paths can name one file. Full paths must be equal. A path with no directory (just the name)
    gives no way to tell, so it matches by basename alone: a launch from the run folder may name the file bare, or an
    earlier call may have written it bare. A relative path with a directory matches the tail of a longer one."""
    if a == b or "/" not in a or "/" not in b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return not re.match(r"[a-z]:/|/|~", short) and long_.endswith("/" + short)


def related_text(call, run):
    """The launch command plus the text of the args file it names, if an earlier call wrote it."""
    command = call["input"].get("command", "")
    parts = [command]
    for groups in re.findall(r"--args-file[\"']?[\s,=]+(?:\"([^\"]+)\"|'([^']+)'|([^\s\"',]+))", command):
        ref = next(g for g in groups if g)
        ref = re.sub(r"^(?:\./|\.\./)+", "", norm_path(ref))
        base = ref.rsplit("/", 1)[-1]
        # Match by the whole normalized path: two folders can each hold an args.json. The name alone decides only
        # when the launch (or the earlier call) gives no directory, since then nothing else can tell them apart.
        # Only the latest earlier call that names the file: what it held when this job launched, not its history.
        # A call that only reads or mentions the file does not change it: the writer carries the out_dir.
        earlier = [c for c in run["calls"] if c is not call and c["seq"] < call["seq"]
                   and re.search(r"out_dir", str(c["input"]))
                   and any(same_file(m, ref) for m in path_mentions(str(c["input"]), base))]
        parts += [str(c["input"]) for c in earlier[-1:]]
    return "\n".join(parts)


def launch_kind(call, run):
    """None, or 'detached' / 'foreground' for a Blender job that needs a message before it starts."""
    if call["name"] not in SHELLS:
        return None
    command = call["input"].get("command", "")
    job = blender_job(command)
    if not job:
        return None
    if re.search(PLAN_ON, related_text(call, run), re.I):
        return None  # the plan step makes the message; it is not the job
    pattern = DETACHED if call["name"] == "Bash" else DETACHED_PS
    if call["input"].get("run_in_background") or re.search(pattern, command):
        return "detached"
    long = call["end"] is not None and call["t"] is not None and call["end"] - call["t"] > FOREGROUND_LONG_S
    if long or job["render"]:
        return "foreground"
    return None


def out_dirs(call, run):
    found = re.findall(r"out_dir[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", related_text(call, run))
    return [norm_path(p) for p in found]


def score_announcements(run, args=None):
    timed = [x for x in run["texts"] if x["t"] is not None]
    launches = [(c, launch_kind(c, run)) for c in run["calls"]]
    launches = [(c, k) for c, k in launches if k]
    problems, checked = [], 0
    for c in run["calls"]:
        if c["name"] == LIVE_CODE and c["t"] is not None and c["end"] and c["end"] - c["t"] > 5:
            before = [x["text"] for x in timed if c["t"] - 120 <= x["t"] <= c["t"]]
            if not any(re.search(FREEZE_WORDS, b, re.I) for b in before):
                problems.append(f"live call of {c['end'] - c['t']:.0f} s with no warning")
    if not launches and not any(c["t"] is not None for c in run["calls"]):
        return verdict("announcements", "SKIP", "the trace has no timings and no Blender job was launched")
    claimed = None
    for c, kind in launches:
        checked += 1
        before = [x for x in run["texts"] if not x["child"] and x["seq"] < c["seq"]
                  and (x["t"] is None or c["t"] is None or c["t"] - 900 <= x["t"] <= c["t"])]
        if not before:
            problems.append(f"{kind} Blender job with no message to the user before it")
            continue
        dirs = out_dirs(c, run)
        def has_path(text):
            flat = norm_path(text)
            # The folder as a whole path: "c:/run/outdated" is not "c:/run/out", "/x/run/out" is not "/run/out".
            return any(re.search(r"(?<![\w./\-])" + re.escape(d) + r"(?![\w.\-])", flat) for d in dirs) if dirs else bool(re.search(r"render_status", text) and re.search(r"[\\/]", text))
        full = [x for x in before if has_path(x["text"]) and seconds_in(x["text"])]
        if not full:
            missing = []
            if not any(has_path(x["text"]) for x in before):
                missing.append("the real out_dir" if dirs else "a path to render_status.json")
            if not any(seconds_in(x["text"]) for x in before):
                missing.append("a duration")
            problems.append(f"{kind} Blender job announced without {' or '.join(missing)}")
            continue
        claimed = seconds_in(full[-1]["text"])[0]
    if claimed is not None and args is not None and getattr(args, "status", None):
        status = json.load(open(args.status, encoding="utf-8"))
        if status.get("started") and status.get("ended"):
            actual = status["ended"] - status["started"]
            if abs(claimed - actual) > 5 and (claimed > actual * 3 or claimed < actual / 3):
                problems.append(f"the message said {claimed:.0f} s and the render took {actual:.0f} s")
    if problems:
        return verdict("announcements", "FLAG", "; ".join(problems), True)
    if checked:
        return verdict("announcements", "OK", f"{checked} Blender job(s) announced before launch with the real path and a duration", True)
    return verdict("announcements", "OK", "long calls warned; no Blender job launched", True)


def score_finish(run, args):
    if not args.status:
        return verdict("finish", "SKIP", "no --status")
    status = json.load(open(args.status, encoding="utf-8"))
    ended = status.get("ended")
    if not run["results"]:
        return verdict("finish", "FLAG", "the session produced no result")
    final = run["results"][-1]
    if status.get("state") == "running":
        if re.search(RUNNING_WORDS, final["text"], re.I) and "render_status" in final["text"]:
            return verdict("finish", "NOTE", "handed off as still running, with the status file", True)
        return verdict("finish", "FLAG", "the render is still running and the last result does not say so", True)
    if not ended or status.get("state") != "done":
        return verdict("finish", "FLAG", f"the render status is {status.get('state')}, not done")
    if final["t"] is None:
        return verdict("finish", "SKIP", "the trace has no timings")
    if args.deliverable and not os.path.exists(args.deliverable):
        return verdict("finish", "FLAG", f"the deliverable does not exist: {args.deliverable}")
    if args.deliverable and os.path.getmtime(args.deliverable) > final["t"]:
        return verdict("finish", "FLAG", "the deliverable was written after the session finished")
    early = [r for r in run["results"] if r["t"] is not None and r["t"] < ended]
    if final["t"] < ended:
        if re.search(RUNNING_WORDS, final["text"], re.I) and "render_status" in final["text"]:
            return verdict("finish", "NOTE", "handed off as still running, with the status file", True)
        return verdict("finish", "FLAG", "the session finished before the render did")
    silent = [r for r in early if not re.search(RUNNING_WORDS, r["text"], re.I)]
    if silent:
        return verdict("finish", "FLAG", "a result before the render finished does not say it is still running", True)
    if early:
        return verdict("finish", "NOTE", f"{len(early)} result event(s) before the render ended, each saying it was "
                       "still running; a program reading only the first result gets an unfinished state", True)
    checked = "; the deliverable exists" if args.deliverable else "; no --deliverable, so the video was not checked"
    return verdict("finish", "OK", "every result came after the render ended" + checked)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare what an agent run claimed with what its session trace shows.")
    ap.add_argument("--trace", required=True)
    ap.add_argument("--skills-dir", required=True)
    ap.add_argument("--monitor")
    ap.add_argument("--manifest")
    ap.add_argument("--status")
    ap.add_argument("--log")
    ap.add_argument("--deliverable")
    ap.add_argument("--platform", choices=("auto", "windows", "macos", "linux"), default="auto",
                    help="where the run happened; decides whether a minimized window is a defect (Windows only)")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    run = collect(parse_trace(args.trace))
    manifest = json.load(open(args.manifest, encoding="utf-8")) if args.manifest else None
    report = [score_preferences(run), score_window(run, args, manifest), score_closing_line(run),
              score_claims(run, args), score_skills(run, args), score_gates(run, manifest),
              score_announcements(run, args), score_finish(run, args)]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if args.strict and any(r["verdict"] == "FLAG" for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
