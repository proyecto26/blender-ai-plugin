#!/usr/bin/env python3
"""Compare what an agent run claimed with what its session trace shows.

    python tests/agent_runs/score_run.py --trace run.jsonl --skills-dir skills
        [--monitor monitor.csv] [--manifest run_manifest.json] [--status render_status.json] [--log render.log]
        [--deliverable final.mp4]

The trace is `claude -p --output-format stream-json --verbose` output, raw or with each line wrapped as
{"t": epoch, "line": "..."} (timings need the wrapped form). Prints one verdict per finding: OK, FLAG, NOTE (worth
reading, not a defect) or SKIP (input missing). --strict exits 1 on any FLAG.

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
    for t, d in events:
        kind = d.get("type")
        if kind == "assistant":
            for c in d["message"]["content"]:
                if c["type"] == "text" and c["text"].strip():
                    run["texts"].append({"t": t, "text": c["text"], "child": bool(d.get("parent_tool_use_id"))})
                elif c["type"] == "tool_use":
                    call = {"t": t, "end": None, "name": c["name"], "input": c["input"],
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


def score_window(run, args, manifest):
    if not args.monitor:
        return verdict("window", "SKIP", "no --monitor")
    samples = minimized_spans(args.monitor)
    if not samples:
        return verdict("window", "OK", "window never minimized")
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
    detail = f"minimized in {len(samples)} sample(s), {samples[0]} to {samples[-1]}"
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
        by_time.setdefault(e["time"], []).append(e["stage"])
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


def score_announcements(run):
    if not any(c["t"] is not None for c in run["calls"]):
        return verdict("announcements", "SKIP", "the trace has no timings")
    timed = [x for x in run["texts"] if x["t"] is not None]
    problems = []
    for c in run["calls"]:
        if c["name"] == LIVE_CODE and c["end"] and c["end"] - c["t"] > 5:
            before = [x["text"] for x in timed if c["t"] - 120 <= x["t"] <= c["t"]]
            if not any(re.search(FREEZE_WORDS, b, re.I) for b in before):
                problems.append(f"live call of {c['end'] - c['t']:.0f} s with no warning")
        if c["name"] == "Bash" and c["input"].get("run_in_background") and re.search(r"(-b|--background)\b.*--python",
                                                                                      c["input"].get("command", "")):
            near = [x["text"] for x in timed if c["t"] - 30 <= x["t"] <= c["t"] + 60]
            if not any(re.search(r"render_status|status|[\\/]", n) for n in near):
                problems.append("background job started with no path or status file in the text")
    if problems:
        return verdict("announcements", "FLAG", "; ".join(problems), True)
    return verdict("announcements", "OK", "long calls warned, background job path given", True)


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
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    run = collect(parse_trace(args.trace))
    manifest = json.load(open(args.manifest, encoding="utf-8")) if args.manifest else None
    report = [score_preferences(run), score_window(run, args, manifest), score_closing_line(run),
              score_claims(run, args), score_skills(run, args), score_gates(run, manifest),
              score_announcements(run), score_finish(run, args)]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if args.strict and any(r["verdict"] == "FLAG" for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
