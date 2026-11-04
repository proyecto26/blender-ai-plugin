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
names the real out_dir (taken from the launch command or the args file it names; without one, a render_status.json in the
folder of the job's -o / --render-output (frame pattern and a `//` prefix stripped, same rule on Windows and POSIX) or its
parent, nothing above or below; with neither, a path to render_status.json
checked by its file name only, and the OK says so) and a duration. With --status the duration is compared with the render's real time: more than 3 times off, and more than
5 s, is a FLAG. The plan step (`plan: true`) is exempt, since it produces the message; each Blender invocation is judged
by its own arguments (the text after `--`, or its args file), so a plan chained to the real render exempts only itself. A
per-frame figure needs a frame count (the message's, or the job's -s/-e/-f), else it is no duration. It matches tokens and
does not parse the shell: it reads `bash -c '...'`, `eval` / `Invoke-Expression` / `iex` payloads (only when that word is
invoked, not as the argument of echo, grep or git commit), `$(...)` and backtick bodies (not in single quotes,
to a depth of 4), a trailing `&`, versioned executable names, a variable assigned a Blender path, an alias defined earlier
in the same command and a variable holding a whole command line. An executable built at run time (`$(which blender) -b f
-a`, or a variable assigned from a substitution or from other variables) with Blender-shaped flags is a NOTE, never an
OK. Limits: a variable, alias or function defined in an earlier call or in the environment is not known (`$B -b f -a` with
B never assigned in the same command reads as no launch); `eval "$X"` with X unassigned or assigned from a substitution
is not read; a path or name assembled by concatenation (`${DIR}/bl${EXT}`) is not resolved; here-documents, `source`d
files and functions are not followed; the
`-o` folder is a hint, not the status folder, so a status file in a sibling folder of it is a FLAG that may be wrong.

Text matching is heuristic and every such check says so. One run shows one case, not general reliability, and the
score runs after the job, so it catches regressions rather than stopping a bad report.
"""
import argparse
import csv
import json
import os
import posixpath
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
BLENDER_EXE = r"blender(?:-launcher|[-_]?\d+(?:\.\d+)*)?(?:\.exe)?"  # blender, blender-launcher.exe, blender-4.2, blender5.2.exe
# A launch through a variable: `& $blender`, `"$BLENDER"`, `& "$env:BLENDER"`, `${BLENDER_EXE}`.
BLENDER_VAR = r"\$\{?(?:env:)?blender(?:_?(?:exe|path|bin|launcher))?\}?"
# Blender stops reading its own flags at `--`; what follows belongs to the script. Flags are case-sensitive (`-F` is not `-f`).
BG_FLAGS = {"-b", "--background"}
# Work that starts a job: render animation / frame, run a script. Short and long spellings, plus the `--flag=value` forms.
WORK_FLAGS = {"-a", "--render-anim", "-f", "--render-frame", "-P", "--python", "--python-text", "--python-expr"}
RENDER_FLAGS = {"-a", "--render-anim", "-f", "--render-frame"}
# Not valid Blender, but an agent may write `-ba` or `-bf 1`; scoring leans to seeing a job, so a cluster of the short
# letters b/a/f/P (optionally ending in digits, `-f1`) counts as each flag it contains.
SHORT_CLUSTER = r"-([bafP]+)\d*"
# A drive-letter path: not the tail of a word or URL (`https://`, `example.com/p:/x`); `file:///C:/x` still counts.
DRIVE_PATH = r"(?:(?<![\w/.:\-])|(?<=file:///))[A-Za-z]:[\\/]"
# The status file with a directory in front of it (`out/render_status.json`), not a slash elsewhere in the message.
STATUS_PATH = r"[^\s\"'<>|*?]*[\\/]render_status\.json(?![\w\-]|\.\w)"
URL_SCHEME = r"\b(?!file:)[a-z][a-z0-9+.\-]*://"  # a URL is not a file the user can open (file:// is)
TOKEN = r"\"([^\"]*)\"|'([^']*)'|([;|]+|[^\s,\"';|]+)"
PIPE_END = {"&&", "||", ";", "|"}
PLAN_ON = r"[\"']?plan[\"']?\s*[:=]\s*[\"']?(?:true|\$true)\b"
# `2m30s`: a bare `m` counts as minutes only when digits follow it directly.
DURATION = (r"(\d+(?:[.,]\d+)?)\s*(segundos?|seconds?|secs?|minutos?|minutes?|mins?|horas?|hours?|hrs?|s|h|m(?=\d))(?:\b|(?<=m)(?=\d))")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}
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
    run = {"calls": [], "texts": [], "results": [], "by_id": {}, "cwd": None}
    seq = 0
    for t, d in events:
        kind = d.get("type")
        if kind == "system" and isinstance(d.get("cwd"), str) and run["cwd"] is None:
            run["cwd"] = d["cwd"]  # the session's working directory, from its init event
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
    blob = re.sub(r"\b(?!file:)[A-Za-z][A-Za-z0-9+.\-]*://[^\s\"')]*", " ", blob)  # a URL's path or query is not a local path
    if any(c["name"] == "PowerShell" for c in run["calls"]) or re.search(DRIVE_PATH, blob):
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
    flat = re.sub(r"/+", "/", text.replace("\\\\", "/").replace("\\", "/")).lower().rstrip("/")
    return re.sub(r"^/([a-z])(?=/)", r"\1:", flat)  # Git Bash /c/run -> c:/run


def seconds_in(text):
    """Every duration stated in the text, in seconds."""
    found = []
    for number, unit in re.findall(DURATION, text, re.I):
        unit = unit.lower()
        scale = UNIT_SECONDS.get(unit) or (60 if unit.startswith("min") else 3600 if unit[0] == "h" else 1)
        found.append(float(number.replace(",", ".")) * scale)
    return found


TOTAL_WORD = r"\b(?:total\w*|en total|overall|in all|altogether|en conjunto)\b[^\d]{0,12}$"
TOTAL_AFTER = r"\s*(?:\(|-)?\s*(?:in\s+)?(?:total|overall|in all|altogether|en total|en conjunto)\b"
UNITS = r"(?:frame|step|sample|tile|image|fotograma|paso|muestra)s?"
PER_AFTER = r"\s*(?:\b(?:per|a|each|por|cada)\b|/)\s*" + UNITS + r"\b"
PER_BEFORE = r"\b(?:each|every|per|cada)\s+" + UNITS + r"\b[^.;\d]*$"
FRAME = r"(?:frame|fotograma)s?"
PER_FRAME = PER_AFTER.replace(UNITS, FRAME)
PER_FRAME_BEFORE = PER_BEFORE.replace(UNITS, FRAME)
PHASE_AFTER = r"\s*(?:of\s+)?(?:compil\w*|start-?up|load\w*|set-?up|warm-?up|shader\w*|kernel\w*)"
WHOLE_BEFORE = r"\b(?:whole|entire|full|overall|in all|altogether|roughly|completo|toda|todo|en conjunto)\b[^\d.;]*$"
PART_JOIN = r"[\s,+]*(?:\b(?:and|y|e|plus)\b)?[\s,+]*"


RANGE_DASH = r"\s*(?:\bto\b|\bhasta\b|-|–|—)\s*"
RANGE_WORD = r"\s*(?:\band\b|\by\b|\bor\b|\bo\b)\s*"
RANGE_OPEN = r"\b(?:between|entre)\s*$"


def claimed_seconds(text, job_frames=None):
    """The total duration the message claims: a stated total (`total 48 s`), else the first figure. A figure written in
    parts (`2 min 30 s`, falling units) is the sum of its parts; a range (`30 s to 2 min`, `between 30 s and 2 min`) is its
    upper bound. A per-frame figure is multiplied by the frame count the message gives, else by `job_frames` (the job's
    own -s/-e/-f); with neither it says nothing about the whole job and the result is None."""
    groups = []  # [start, end, seconds, unit scale of the last part]
    for m in re.finditer(DURATION, text, re.I):
        unit = m.group(2).lower()
        scale = UNIT_SECONDS.get(unit) or (60 if unit.startswith("min") else 3600 if unit[0] == "h" else 1)
        value = float(m.group(1).replace(",", ".")) * scale
        prev = groups[-1] if groups else None
        gap = text[prev[1]:m.start()] if prev else ""
        follows_unit = re.match(PER_AFTER, text[m.end():m.end() + 25], re.I) or re.match(PHASE_AFTER, text[m.end():m.end() + 20], re.I)
        if prev and not follows_unit and (re.fullmatch(RANGE_DASH, gap, re.I) or (
                re.fullmatch(RANGE_WORD, gap, re.I) and re.search(RANGE_OPEN, text[max(0, prev[0] - 12):prev[0]], re.I))):
            prev[1], prev[2], prev[3] = m.end(), max(prev[2], value), max(prev[3], scale)
        elif prev and scale < prev[3] and re.fullmatch(PART_JOIN, text[prev[1]:m.start()], re.I):
            prev[1], prev[2], prev[3] = m.end(), prev[2] + value, scale
        else:
            groups.append([m.start(), m.end(), value, scale])
    if not groups:
        return None
    stated = [g for g in groups if re.search(TOTAL_WORD, text[max(0, g[0] - 16):g[0]], re.I)
              or re.match(TOTAL_AFTER, text[g[1]:g[1] + 20], re.I)]
    if stated:
        return stated[-1][2]
    # No stated total. A per-frame / per-step figure or a setup phase (`30 s compile`) is not the whole job.
    per_unit = [g for g in groups if re.match(PER_AFTER, text[g[1]:g[1] + 25], re.I)
                or re.search(PER_BEFORE, text[max(0, g[0] - 45):g[0]], re.I)]
    parts = [g for g in groups if re.match(PHASE_AFTER, text[g[1]:g[1] + 20], re.I)]
    whole = [g for g in groups if g not in per_unit and g not in parts]
    marked = [g for g in whole if re.search(WHOLE_BEFORE, text[max(0, g[0] - 25):g[0]], re.I)]
    if marked:
        return marked[-1][2]
    frames = re.search(r"(\d+)\s*(?:frames?|fotogramas?)\b", text, re.I)
    if per_unit:
        # Only a per-frame figure scales with the frame count; a per-sample or per-step one says nothing about the whole.
        per_frame = [g for g in per_unit if re.match(PER_FRAME, text[g[1]:g[1] + 25], re.I)
                     or re.search(PER_FRAME_BEFORE, text[max(0, g[0] - 45):g[0]], re.I)]
        if per_frame and (frames or job_frames):
            return per_frame[0][2] * (int(frames.group(1)) if frames else job_frames)
        if not whole:
            return None
    return (whole or groups)[0][2]


# Commands that print or inspect their words and never run them.
NON_LAUNCH = {"echo", "printf", "write-host", "write-output", "write-error", "cat", "type", "ls", "grep", "head", "tail",
              "get-content", "test", "set", "export", "which", "where", "file", "stat", "wc"}
# Blender flags whose next argument is one value, even when it starts with `-` and holds spaces.
VALUE_FLAGS = {"--python-expr", "--python-text", "--python", "-P", "--python-console", "--addons", "--app-template"}


# Shell operators that end one command (`&` backgrounds it); a `)` or `}` stuck to one (`&)`) is ignored.
SEG_END = PIPE_END | {"&"}
# A shell that takes the command to run as its next argument: `bash -c 'blender ...'`, `cmd /c "..."`.
SHELL_C = {"-c", "-lc", "-ic", "-command", "/c", "/k"}
# Blender stops reading flags at either of these; what follows belongs to the script.
FLAGS_END = {"--", "--args"}
ASSIGN = re.compile(r"\$?\{?(\w+)\}?=(.*)", re.S)


def _is_blender_name(path):
    return bool(re.fullmatch(BLENDER_EXE, path.replace("\\", "/").rsplit("/", 1)[-1].strip(), re.I))


# Words that run another command line: only their payload (`eval "..."`, `bash -c "..."`, `iex "..."`) is a launch. The same
# words as the argument of `echo`, `grep`, `git commit -m` ... are text.
EVALS = {"eval", "iex", "invoke-expression"}
INVOKERS = EVALS | {"builtin", "sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh", "sudo", "env", "nohup", "time",
                    "exec", "command", "xargs", "timeout", "nice", "stdbuf", "start", "call"}
# Words after which an executable may follow as an argument rather than at the start: `Start-Process $B -ArgumentList ...`.
# A word that only introduces the command after it (`if true; then eval ...`, `{ eval ...; }`).
KEYWORDS = {"then", "else", "do", "elif", "if", "while", "until", "{", "(", "!", "time"}
LAUNCHERS = {"builtin", "start-process", "start", "sudo", "env", "nohup", "time", "exec", "command", "xargs", "timeout", "nice",
             "invoke-command", "call", "stdbuf"}

SUBST = "__SUBST__"  # stands for a `$(...)` / backtick body in the text left behind once the body is scanned on its own


def _substitutions(command):
    """(outer, bodies): the command with each command substitution (`$(...)`, backticks) replaced by `$__SUBST__`, and the
    text of every such body. Bodies in single quotes and after a backslash are literal text and stay where they are."""
    out, bodies, i, quote = [], [], 0, None
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append(command[i:i + 2])
            i += 2
            continue
        if quote == "'":
            quote = None if ch == "'" else quote
        elif ch == "'" and quote is None:
            quote = "'"
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif ch == "$" and command[i + 1:i + 2] == "(" and command[i + 2:i + 3] != "(":
            depth, j = 1, i + 2
            while j < len(command) and depth:
                depth += {"(": 1, ")": -1}.get(command[j], 0)
                j += 1
            if depth == 0:
                bodies.append(command[i + 2:j - 1])
                out.append("$" + SUBST)
                i = j
                continue
        elif ch == "`":
            j = command.find("`", i + 1)
            if j > i + 1 and " " in command[i + 1:j]:
                bodies.append(command[i + 1:j])
                out.append("$" + SUBST)
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out), bodies


def join_continuations(command, shell="Bash"):
    """The command with each real line continuation joined into one line: in Bash an odd number of backslashes as the last
    character of a line outside quotes, in PowerShell a backtick as the last character outside a single-quoted string
    (a trailing backslash there is just a path, `-o C:\\out\\`). A continuation followed by a blank line, or by the end of
    the command, joins nothing: the next line is another command."""
    lines = command.split("\n")
    out, quote, i, carry = [], None, 0, ""
    ps = shell == "PowerShell"
    while i < len(lines):
        line = lines[i].rstrip("\r")
        cont, j = False, 0
        while j < len(line):
            ch = line[j]
            if quote == "'":
                quote = None if ch == "'" else quote
            elif ch == "'" or ch == '"':
                quote = None if quote == ch else (quote or ch)
            elif ch == ("`" if ps else "\\"):
                if j + 1 == len(line):
                    cont = quote is None or (quote == '"' and ps)
                j += 1  # the escaped character
            j += 1
        if cont and i + 1 < len(lines) and lines[i + 1].strip():
            carry += line[:-1] + " "
            i += 1
            continue
        out.append(carry + line)
        carry = ""
        i += 1
    return "\n".join(out)


def _scan(command, depth=0, env=None, shell="Bash"):
    """Each Blender invocation in the command: {'flags': what Blender itself reads (up to `--` / `--args`), 'raw': the text of
    the invocation up to the next shell operator or line, 'post': the text after `--` / `--args`}. Quoted pieces and comma
    list (PowerShell -ArgumentList "-b","f.blend") become separate tokens; the payload of `bash -c '...'`, of `eval` and of
    `$(...)` / backticks is scanned too (to a depth of 4); a variable that was assigned a Blender path (`exe=blender`,
    `$exe = "blender"`) counts as Blender, and so does an alias defined earlier in the same command (`alias b=blender`), and
    a variable holding a whole command (`cmd="blender -b f -a"; eval "$cmd"`). An executable that is built at run time
    (`$(which blender)`, a variable assigned from one) cannot be resolved: its segment is marked 'unresolved'. It tokenizes;
    it does not parse the shell. `eval` / `iex` / `bash -c` payloads are read only when that word starts a command (or follows
    sudo, env, nohup ...), never as the argument of echo, grep or git commit; a payload sees the variables, aliases and
    command texts of the command that holds it (`env`)."""
    segments, current = [], None
    command = join_continuations(command, shell)  # every level: a payload has its own lines, in its own shell's rules
    first, prev, end = None, None, 0  # first word of this shell piece; previous token; end of the previous match
    blender_vars, aliases, texts = (set(), {}, {}) if env is None else (set(env[0]), dict(env[1]), dict(env[2]))
    unresolved_vars = {SUBST.lower()} | (set() if env is None else set(env[3]))
    if depth < 4:
        command, bodies = _substitutions(command)
        for body in bodies:
            segments.extend(_scan(body, depth + 1, (blender_vars, aliases, texts, unresolved_vars), shell))
    toks = list(re.finditer(TOKEN, command))

    def close(at):
        nonlocal current
        if current is not None:
            current["raw"] = command[current.pop("start"):at]
            dd = current.pop("dd")
            current["post"] = command[dd:at] if dd is not None else ""
            current = None

    for i, m in enumerate(toks):
        groups = m.groups()
        tok = next(g for g in groups if g is not None)
        quoted, single, bare = groups
        gap = command[end:m.start()]
        if "\n" in gap:
            first = None
            close(end)
        prev_end, end = end, m.end()
        core = re.sub(r"^(?:\$\(|[({])+", "", tok) if bare is not None else tok
        last = core.replace("\\", "/").rsplit("/", 1)[-1]
        word = last.lower().removesuffix(".exe")
        at_start = first is None
        if at_start:
            first = word
        # `if true; then eval ...`, `{ eval ...`, `VAR=x eval ...`: the next word is the command.
        # Only an unquoted word is syntax: `"if" eval ...` runs a command named if.
        skip_to_next = at_start and bare is not None and (word in KEYWORDS or not core or re.fullmatch(r"\w+=.*", core) is not None)
        op = bare is not None and core.rstrip(")}") in SEG_END
        payload = quoted if quoted is not None else single
        env_now = (blender_vars, aliases, texts, unresolved_vars)
        if (current is None and payload is not None and prev and prev.lower() in SHELL_C | EVALS and first in INVOKERS
                and depth < 4):
            ref = re.fullmatch(r"\$\{?(\w+)\}?", payload.strip())
            inner = "PowerShell" if first in ("powershell", "pwsh") or first in ("iex", "invoke-expression") else (
                "Bash" if first in ("sh", "bash", "zsh", "dash", "ksh", "fish") else shell)  # the payload's own shell
            segments.extend(_scan(texts[ref.group(1).lower()] if ref and ref.group(1).lower() in texts else payload,
                                  depth + 1, env_now, inner))
            prev = tok
            continue
        # Remember `exe=blender` / `$exe = "blender"` / `exe="blender"`.
        if bare is not None:
            assign = ASSIGN.fullmatch(core)
            value = None
            if assign and not assign.group(2) and i + 1 < len(toks) and toks[i + 1].start() == m.end():
                value = next(g for g in toks[i + 1].groups() if g is not None)
                name = assign.group(1)
            elif assign:
                value, name = assign.group(2), assign.group(1)
            elif core == "=" and prev and re.fullmatch(r"\$\w+", prev) and i + 1 < len(toks):
                value, name = next(g for g in toks[i + 1].groups() if g is not None), prev[1:]
            if value is not None:
                v = value.strip("\"'")
                if prev and prev.lower() == "alias" and v.split() and _is_blender_name(v.split()[0]):
                    aliases[name.lower()] = v.split()[1:]
                elif _is_blender_name(v) or re.fullmatch(BLENDER_VAR, v, re.I):
                    blender_vars.add(name.lower())
                elif "$" in v:
                    unresolved_vars.add(name.lower())  # built at run time: cannot be read
                if re.search(r"\s", v):
                    texts[name.lower()] = v
        var = re.fullmatch(r"\$\{?(?:env:)?(\w+)\}?", core)
        is_exe = (re.fullmatch(BLENDER_EXE, last, re.I) or re.fullmatch(BLENDER_VAR, last, re.I)
                  or bool(var and var.group(1).lower() in blender_vars))
        alias = core.lower() if at_start and current is None and bare is not None and core.lower() in aliases else None
        # An executable may follow a launcher as an argument (`Start-Process $B ...`, `sudo $B ...`), not only start the command.
        exe_slot = at_start or (first in LAUNCHERS and current is None)
        unresolved = bool(exe_slot and not is_exe and var and var.group(1).lower() in unresolved_vars)
        runs_text = at_start or (prev is not None and prev.lower() in EVALS and first in EVALS)  # `$cmd`, `eval $cmd`
        whole = var.group(1).lower() if runs_text and bare is not None and var and var.group(1).lower() in texts else None
        if whole and depth < 4:
            segments.extend(_scan(texts[whole], depth + 1, env_now, shell))  # `$cmd` run as a command: its words are the command
        elif is_exe and first in NON_LAUNCH and word != first:
            pass  # `echo "$BLENDER" -b f.blend -a` prints; it launches nothing
        elif is_exe or alias or unresolved:
            close(prev_end)
            current = {"flags": list(aliases.get(alias, [])), "start": m.start(), "dd": None, "unresolved": unresolved}
            segments.append(current)
        elif current is not None:
            if op:
                close(prev_end)
            elif current["dd"] is not None:
                pass  # the script's own arguments
            elif tok in FLAGS_END:
                current["dd"] = m.end()
            elif (quoted or single) and tok.lstrip().startswith("-") and re.search(r"\s", tok) and prev not in VALUE_FLAGS:
                current["flags"].extend(tok.split())  # -ArgumentList "-b scene.blend -a": one string holding several flags
            else:
                current["flags"].append(tok)
        if op or skip_to_next:
            first = None
        prev = tok
    close(end)
    return segments


def blender_segments(command):
    """The flags Blender reads in each Blender invocation of the command (see _scan)."""
    return [s["flags"] for s in _scan(command) if not s["unresolved"]]


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


def frame_list_count(val):
    """How many frames a `-f` value renders: `5` is 1, `1,3,5` is 3, `1..5` is 5; relative (+N/-N) or odd forms give None."""
    total = 0
    for part in val.split(","):
        m = re.fullmatch(r"(\d+)(?:\.\.(\d+))?", part)
        if not m or (m.group(2) and int(m.group(2)) < int(m.group(1))):
            return None
        total += int(m.group(2)) - int(m.group(1)) + 1 if m.group(2) else 1
    return total


def frame_count(tokens, raw=None):
    """How many frames the invocation renders when its flags say so: the `-f` frames when given (Blender renders those and
    ignores -s/-e for them), else the -s/-e range, else None."""
    values, frames = {}, []
    for i, tok in enumerate(tokens):
        name, eq, val = tok.partition("=")
        name = {"--frame-start": "-s", "--frame-end": "-e", "--render-frame": "-f"}.get(name, name)
        if name in ("-s", "-e", "-f"):
            val = val if eq else (tokens[i + 1] if i + 1 < len(tokens) else "")
            if name == "-f":
                # the command tokenizer splits on commas, so "-f 1,3,5" arrives as "1", "3", "5": rejoin them
                j = i + (1 if eq else 2)
                while (j < len(tokens) and re.fullmatch(r"\d+(?:\.\.\d+)?", tokens[j])
                       and (raw is None or re.search(re.escape(val) + r"\s*,\s*" + re.escape(tokens[j]) + r"(?![\d.])", raw))):
                    val, j = val + "," + tokens[j], j + 1
                frames.append(val)
            elif re.fullmatch(r"[+-]?\d+", val):
                values[name] = int(val)
    if frames:
        counts = [frame_list_count(v) for v in frames]
        return None if None in counts else sum(counts)
    if "-s" in values and "-e" in values and values["-e"] >= values["-s"]:
        return values["-e"] - values["-s"] + 1
    return None


def job_segments(command, shell="Bash"):
    """Every background Blender invocation in the command that renders or runs a script, each with its own
    arguments: {'render', 'frames', 'raw', 'post'}."""
    jobs = []
    for seg in _scan(command, shell=shell):
        tokens = seg["flags"]
        if not seg["unresolved"] and flag_set(tokens, BG_FLAGS) and flag_set(tokens, WORK_FLAGS):
            jobs.append({"render": bool(flag_set(tokens, RENDER_FLAGS)) or "background_render.py" in seg["raw"],
                         "frames": frame_count(tokens, seg["raw"]), "raw": seg["raw"], "post": seg["post"],
                         "flags": tokens})
    return jobs


def unresolved_launches(command, shell="Bash"):
    """How many invocations have an executable built at run time (`$(which blender) -b f -a`, a variable assigned from one)
    and Blender-shaped flags: they may be a Blender job, and nothing here can tell."""
    return sum(1 for seg in _scan(command, shell=shell) if seg["unresolved"] and flag_set(seg["flags"], BG_FLAGS)
               and flag_set(seg["flags"], WORK_FLAGS))


def blender_job(command):
    """None, or {'render': bool}: a background Blender invocation that renders or runs a script."""
    jobs = job_segments(command)
    return {"render": any(j["render"] for j in jobs)} if jobs else None


ARG_TOKENS = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'|[^\s\"']+")
REDIRECT = re.compile(r">>?\s*(\"[^\"\n]*\"|'[^'\n]*'|[^\s\"'|&;<>]+)")


def path_mentions(text, base):
    """Every candidate path in the text that holds the file name itself, normalized (backslashes, Git Bash /c/x, case).
    The name is searched for directly, not parsed out of a path: a quoted string is one candidate, spaces included, and an
    unquoted word is cut at shell punctuation."""
    tail = re.compile(r"(?<![\w.\-])" + re.escape(base) + r"(?![\w.\-])")
    found = []
    for tok in ARG_TOKENS.findall(text):
        if len(tok) > 1 and tok[0] in "\"'" and tok[-1] == tok[0]:
            parts = [tok[1:-1]]
        else:
            parts = re.split(r"[=,;()<>|&`]", tok)
        for part in parts:
            norm = norm_path(part.strip())
            if tail.search(norm):
                found.append(norm)
    return found


def resolved(path):
    """A path that names one place on its own: a drive letter, and nothing left to expand."""
    return bool(re.match(r"[a-z]:/", path)) and not re.search(r"[$%~{}*?]", path)


def same_file(a, b):
    """The loose matching that INVALIDATES the plan state: whether two normalized paths can name one file. They are different files only when both are fully resolved absolute
    paths that differ. A relative path, a ./ path or one holding a variable has the same name and could be anywhere, so
    it counts as this file: the state is then unknown."""
    if resolved(a) and resolved(b):
        return a == b
    return True


def strict_same_file(a, b):
    """The matching that GRANTS the plan exemption. Equal paths; or a bare name against anything (one side has no
    directory); or a relative path with directories that is the tail of the other. A relative path never matches a
    different absolute folder."""
    if a == b or "/" not in a or "/" not in b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return not re.match(r"[a-z]:/|/|~", short) and long_.endswith("/" + short)


# A shell command naming the args file is a read only when each piece naming it starts with one of these (or is the
# Blender launch itself) and redirects nothing into the file. Anything else may have rewritten it.
READ_ONLY = {"cat", "type", "head", "tail", "get-content", "ls", "grep"}


def shell_may_write(raw, ref, base):
    """True when a shell command names the args file and is not plainly read-only. Leans to True: an unknown file costs
    one announcement, a stale `plan: true` hides a real render."""
    for piece in re.split(r"&&|\|\||[;|\n]", raw):
        if not any(same_file(m, ref) for m in path_mentions(piece, base)):
            continue
        for target in REDIRECT.findall(piece):
            if any(same_file(m, ref) for m in path_mentions(target, base)):
                return True
        if blender_segments(piece):
            continue
        words = re.findall(TOKEN, piece.lstrip(" \t&("))
        first = next(((q or sq or b) for q, sq, b in words), "")
        first = re.sub(r"\.exe$", "", first.replace("\\", "/").rsplit("/", 1)[-1].lower())
        if first not in READ_ONLY:
            return True
    return False


def args_file_text(call, run, ref, base):
    """What the args file held when this job launched, or its text with `plan` made unreadable when that is not known.
    The state is known only from a full `Write` (its content), then every later Edit / MultiEdit replayed on it. A Read,
    Grep, Glob, or a read-only shell command (see shell_may_write) changes nothing. Anything else naming the file (any
    other shell command, another tool, an Edit whose old text is not in the file, a Write with no text) makes the state
    unknown until the next full Write, so no plan exemption is granted."""
    text, unknown = "", True
    for c in run["calls"]:
        if c is call or c["seq"] >= call["seq"]:
            continue
        inp, name, raw = c["input"], c["name"], str(c["input"])
        if name in ("Write", "Edit", "MultiEdit"):
            names = path_mentions('"%s"' % inp.get("file_path", ""), base)  # quoted: a path may hold spaces
        elif name in SHELLS:
            raw = str(inp.get("command", ""))
            names = path_mentions(raw, base)
        else:
            names = path_mentions(raw, base)
        if not any(same_file(m, ref) for m in names):
            continue
        body = inp.get("content")
        strict = any(strict_same_file(m, ref) for m in names)  # only a strict match may establish or replay the state
        if name == "Write":
            if isinstance(body, str) and strict:
                text, unknown = body, False
            else:
                unknown = True
        elif name in ("Edit", "MultiEdit"):
            for e in inp.get("edits") or [inp]:
                old, new = e.get("old_string"), e.get("new_string")
                if not strict or unknown or not isinstance(old, str) or not isinstance(new, str) or not old or old not in text:
                    unknown = True
                else:
                    text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
        elif name in SHELLS:
            if shell_may_write(raw, ref, base):
                unknown = True
                if re.search(r"out_dir", raw):
                    text += "\n" + raw  # keep its out_dir readable for the announcement check; plan is neutralized
        elif name not in ("Read", "Grep", "Glob"):
            unknown = True
    return re.sub(PLAN_ON, "plan: unknown", text, flags=re.I) if unknown else text


def strip_comment(command):
    """The command without shell comments: a `#` that starts a word (after space, `;`, `|`, `&`) outside quotes, to the end of its line."""
    out = []
    for line in command.split("\n"):
        quote, i = None, 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\" and quote == '"' and i + 1 < len(line):
                    i += 1
                elif ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&("):
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def related_text(call, run, command=None):
    """The launch command (or the given part of it) plus the text of the args file it names, if an earlier call wrote it."""
    if command is None:
        command = strip_comment(call["input"].get("command", ""))
    return "\n".join([command] + args_texts(call, run, command))


def args_texts(call, run, command):
    """The text of each args file the command names (`--args-file X`), as it stood when this call launched."""
    parts = []
    for groups in re.findall(r"--args-file[\"']?[\s,=]+(?:\"([^\"]+)\"|'([^']+)'|([^\s\"',]+))", command):
        ref = next(g for g in groups if g)
        ref = re.sub(r"^(?:\./|\.\./)+", "", norm_path(ref))
        base = ref.rsplit("/", 1)[-1]
        # Match by the whole normalized path: two folders can each hold an args.json. The name alone decides only
        # when the launch (or the earlier call) gives no directory, since then nothing else can tell them apart.
        # What the file held when this job launched, not its history: see args_file_text.
        parts.append(args_file_text(call, run, ref, base))
    return parts


def is_plan(job, call, run):
    """Whether this one invocation is the plan step: `plan: true` in ITS OWN script arguments (the text after `--` /
    `--args`) or in the args file it names. `plan: true` in an `echo`, a `:` no-op, a `--python-expr`, or in another command
    of the same line exempts nothing."""
    own = job["post"] + "\n" + "\n".join(args_texts(call, run, job["raw"]))
    return bool(re.search(PLAN_ON, own.replace('\\"', '"'), re.I))


def launch_info(call, run):
    """(None, None, None), or ('detached' | 'foreground', frames, jobs): a Blender job that needs a message before it starts, and the
    frame count its own flags give (None when they give none). Each invocation is judged by its own arguments."""
    if call["name"] not in SHELLS:
        return None, None, None
    command = strip_comment(call["input"].get("command", ""))
    jobs = [j for j in job_segments(command, call["name"]) if not is_plan(j, call, run)]  # the plan step makes the message; it is not the job
    if not jobs:
        return None, None, None
    frames = next((j["frames"] for j in jobs if j["render"] and j["frames"]), None)
    pattern = DETACHED if call["name"] == "Bash" else DETACHED_PS
    if call["input"].get("run_in_background") or re.search(pattern, command):
        return "detached", frames, jobs
    long = call["end"] is not None and call["t"] is not None and call["end"] - call["t"] > FOREGROUND_LONG_S
    if long or any(j["render"] for j in jobs):
        return "foreground", frames, jobs
    return None, None, None


def launch_kind(call, run):
    """None, or 'detached' / 'foreground' for a Blender job that needs a message before it starts."""
    return launch_info(call, run)[0]


def out_dirs(call, run, jobs=None):
    # Inline JSON inside a command string arrives escaped: {\"out_dir\": \"C:\\\\x\"}.
    # Given jobs, only those invocations' own text and args files count, not another command of a chained line.
    if jobs is None:
        text = related_text(call, run)
    else:
        text = "\n".join(j["raw"] + "\n" + "\n".join(args_texts(call, run, j["raw"])) for j in jobs)
    text = text.replace('\\"', '"')
    found = re.findall(r"out_dir[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", text)
    return [norm_path(p) for p in found]


def status_path_in(text):
    """Whether the text names the status file as a path the user can open: a URL ending in render_status.json is not one."""
    return any(not re.search(URL_SCHEME, m.group(0), re.I) for m in re.finditer(STATUS_PATH, text))


CD_WORDS = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
CD_ANY = r"(?<![\w.\-])(?:cd|chdir|pushd|popd|set-location|sl|push-location|pop-location)(?![\w.\-])"
CD_VALUE_FLAGS = {"-path", "-literalpath"}
BLOCK_OPEN = {"if", "while", "until", "for", "case", "select", "function"}  # a cd inside one may not run
BLOCK_CLOSE = {"fi", "done", "esac"}


def cwd_at(command, raw, cwd, shell="Bash"):
    """The working directory where the invocation `raw` runs, read conservatively. A `cd` / `Set-Location` / `Push-Location` /
    `pushd` with a literal target moves the session's `cwd` only when it is a plain top-level command at the start of its
    sequence (the command start, after `;` or a newline), outside any ( ) or { } and any if/while/until/for/case block, and
    before the launch. ANY other mention of
    a directory change before the launch (after && || | &, in a group or conditional, in a payload or substitution, popd, a
    target that is not literal) makes the directory unknown (None), as does a launch that cannot be located in the command
    text; an unknown directory never resolves a relative path. With no directory change in the command, `cwd` is returned."""
    if not re.search(CD_ANY, command, re.I):
        return cwd
    text = join_continuations(command, shell)
    at = text.find(raw) if raw else -1
    if at < 0 or text.find(raw, at + 1) >= 0:
        return None  # the launch is in a payload, was joined from several lines, or appears twice: where it runs is unknown
    prefix = text[:at]
    toks, here, start, depth, prev_end = list(re.finditer(TOKEN, prefix)), cwd, True, 0, 0
    block = 0  # open shell compound commands (if/while/for/case ... fi/done/esac) before the launch
    i = 0
    while i < len(toks):
        m = toks[i]
        groups = m.groups()
        tok = next(g for g in groups if g is not None)
        bare = groups[2] is not None
        if "\n" in prefix[prev_end:m.start()]:
            start = True
        prev_end = m.end()
        opens = len(tok) - len(tok.lstrip("({")) if bare else 0
        closes = len(tok) - len(tok.rstrip(")}")) if bare else 0
        word = tok.strip("(){}").lower() if bare else ""
        if bare and tok.rstrip(")}") in SEG_END:
            depth = max(0, depth - closes)
            start = tok.rstrip(")}") == ";" and depth == 0  # only `;` (or a newline) starts a new top-level command
        elif word in CD_WORDS and bare and start and (depth or block):
            return None  # a directory change inside a group or a compound command may not run
        elif word in CD_WORDS and bare and start and depth == 0 and opens == 0 and not closes:
            j = i + 1
            while j < len(toks) and next(g for g in toks[j].groups() if g is not None).lower() in CD_VALUE_FLAGS:
                j += 1
            target = next(g for g in toks[j].groups() if g is not None) if j < len(toks) else None
            after = next((g for g in toks[j + 1].groups() if g is not None), "") if j + 1 < len(toks) else ""
            if target is None or target in PIPE_END or target == "&" or re.search(r"[$%~*?`(){}]|^-$", target):
                return None  # not a literal path
            if after.rstrip(")}") in ("|", "&"):
                return None  # the cd runs in a pipeline or in the background
            t = norm_path(target)
            if re.match(r"[a-z]:|/", t):
                here = t
            else:
                here = posixpath.normpath(norm_path(here) + "/" + t) if here else None
            start = False
            prev_end = toks[j].end()
            i = j
        else:
            if re.search(CD_ANY, tok, re.I):
                return None  # a directory change somewhere other than a plain top-level command
            if bare and start and word in BLOCK_OPEN:
                block += 1
            elif bare and start and word in BLOCK_CLOSE:
                block = max(0, block - 1)
            start = False
            depth += opens - closes
            if depth < 0:
                depth = 0
        i += 1
    return here


def render_dirs(jobs, cwd=None):
    """The folders the jobs write frames to (`-o C:/run/out/frame_####`, `-o /tmp/run/f_####`, `--render-output=//out/f_`):
    the path without its file-name prefix and without a leading `//` (relative to the .blend), slashes normalized. One rule
    for Windows, POSIX and relative paths; a bare file prefix (`-o frame_`) names no folder."""
    found = []
    for j in jobs:
        toks = j["flags"]
        for i, tok in enumerate(toks):
            name, eq, val = tok.partition("=")
            if name in ("-o", "--render-output"):
                val = (val if eq else (toks[i + 1] if i + 1 < len(toks) else "")).strip("\"'")
                val = val.replace("\\", "/")
                blend_relative = val.startswith("//")
                val = val[2:] if blend_relative else val
                while val.startswith("./"):
                    val = val[2:]
                folder = val if val.endswith("/") else val.rsplit("/", 1)[0] if "/" in val else ""
                folder = norm_path(folder) if folder.strip("/") or folder.startswith("/") else ""
                if folder and not blend_relative and cwd and not re.match(r"[a-z]:|/", folder):
                    folder = posixpath.normpath(norm_path(cwd) + "/" + folder)  # relative to where the run started
                if folder and "#" not in folder:
                    found.append(folder)
    return found


def related_dir(status_dir, hint):
    """The status file's folder is the render folder or its parent, nothing above and nothing below. A hint that is relative
    (`//out/`, or `./out/` when the run's directory is unknown) matches by its tail."""
    parent = hint.rsplit("/", 1)[0] if "/" in hint else None
    if re.match(r"[a-z]:/|/", hint):
        return status_dir == hint or status_dir == parent
    return any(status_dir == h or status_dir.endswith("/" + h) for h in (hint, parent) if h)


def score_announcements(run, args=None):
    timed = [x for x in run["texts"] if x["t"] is not None]
    launches = [(c,) + launch_info(c, run) for c in run["calls"]]
    launches = [(c, k, n, js) for c, k, n, js in launches if k]
    problems, checked, name_only, unresolved = [], 0, 0, 0
    for c in run["calls"]:
        if c["name"] in SHELLS:
            unresolved += unresolved_launches(strip_comment(c["input"].get("command", "")), c["name"])
        if c["name"] == LIVE_CODE and c["t"] is not None and c["end"] and c["end"] - c["t"] > 5:
            before = [x["text"] for x in timed if c["t"] - 120 <= x["t"] <= c["t"]]
            if not any(re.search(FREEZE_WORDS, b, re.I) for b in before):
                problems.append(f"live call of {c['end'] - c['t']:.0f} s with no warning")
    if not launches and not unresolved and not any(c["t"] is not None for c in run["calls"]):
        return verdict("announcements", "SKIP", "the trace has no timings and no Blender job was launched")
    claimed = None
    for c, kind, job_frames, job_list in launches:
        checked += 1
        before = [x for x in run["texts"] if not x["child"] and x["seq"] < c["seq"]
                  and (x["t"] is None or c["t"] is None or c["t"] - 900 <= x["t"] <= c["t"])]
        if not before:
            problems.append(f"{kind} Blender job with no message to the user before it")
            continue
        dirs = out_dirs(c, run, job_list)
        command = strip_comment(c["input"].get("command", ""))
        hints = [] if dirs else [h for j in job_list for h in render_dirs([j], cwd_at(command, j["raw"], run.get("cwd"), c["name"]))]
        name_only += 0 if dirs or hints else 1
        def has_path(text):
            flat = norm_path(text)
            # The folder as a whole path: "c:/run/outdated" is not "c:/run/out", "/x/run/out" is not "/run/out".
            if dirs:
                return any(re.search(r"(?<![\w./\-])" + re.escape(d) + r"(?![\w.\-])", flat) for d in dirs)
            if hints:
                # No out_dir given: the status file is in the folder the job renders to, or next to it.
                named = [norm_path(m.group(0)).rsplit("/", 1)[0] for m in re.finditer(STATUS_PATH, text)
                         if not re.search(URL_SCHEME, m.group(0), re.I)]
                return any((n and not re.match(r"[a-z]:|/", n)) or related_dir(n, h) for n in named for h in hints)
            return status_path_in(text)
        # A duration is usable when it speaks for the whole job: a per-frame figure needs a frame count (the message's, or
        # the job's own -s/-e/-f), a per-sample one never does.
        usable = lambda text: claimed_seconds(text, job_frames) is not None
        full = [x for x in before if has_path(x["text"]) and usable(x["text"])]
        if not full:
            missing = []
            if not any(has_path(x["text"]) for x in before):
                missing.append("the real out_dir" if dirs else "a path to render_status.json in the folder the job renders to"
                               if hints else "a path to render_status.json")
            if not any(usable(x["text"]) for x in before):
                missing.append("a duration")
            problems.append(f"{kind} Blender job announced without {' or '.join(missing)}")
            continue
        claimed = claimed_seconds(full[-1]["text"], job_frames)
    if claimed is not None and args is not None and getattr(args, "status", None):
        status = json.load(open(args.status, encoding="utf-8"))
        if status.get("started") and status.get("ended"):
            actual = status["ended"] - status["started"]
            if abs(claimed - actual) > 5 and (claimed > actual * 3 or claimed < actual / 3):
                problems.append(f"the message said {claimed:.0f} s and the render took {actual:.0f} s")
    if problems:
        return verdict("announcements", "FLAG", "; ".join(problems), True)
    if unresolved:
        return verdict("announcements", "NOTE", f"{unresolved} launch(es) whose executable is built at run time (command "
                       "substitution, or a variable assigned from one): they may be a Blender job, and the announcement "
                       "cannot be judged; read them by hand", True)
    if checked:
        blind = (f"; no out_dir or absolute -o in {name_only} job(s), so the status path was checked by its file name only"
                 if name_only else "")
        return verdict("announcements", "OK", f"{checked} Blender job(s) announced before launch with the real path and a duration" + blind, True)
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
