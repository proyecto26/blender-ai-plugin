"""Score a routing eval run: route (first specialist fired; router skills may precede it), recall, forbidden.

`claude plugin eval` reports whether a Skill call matched anywhere in a run; routing quality needs the
ORDER of calls, which only the per-run trace has. Run the suite with --keep-temp and --json, then:

    python tests/routing/score_routing.py <result.json> --cases evals-routing [--out report.json]
    python tests/routing/score_routing.py <result.json> --cases evals-orchestrator --subagents

Each case dir carries expect.json: {"expected": <skill|null>, "cluster": str, "also_ok": [...],
"forbidden": [...]}. expected null means no plugin skill may fire ("forbidden": ["*"]).
--subagents also counts Skill calls made inside subagents (the orchestrator path).
Maintainer tooling: reads files only, runs nothing.
"""
import argparse
import collections
import json
import pathlib
import sys

PLUGIN = "blender-ai-plugin:"
ROUTERS = {"blender-director", "blender-mcp-workflow"}  # may fire before the specialist
SKILLS = {p.parent.name for p in (pathlib.Path(__file__).resolve().parents[2] / "skills").glob("*/SKILL.md")}


def _blocks(ev):
    """tool_use/text blocks of an assistant event; other events carry a string or no message."""
    msg = ev.get("message")
    return (msg.get("content") or []) if isinstance(msg, dict) and ev.get("type") == "assistant" else []


def _skill_calls(trace_path, subagents, only_subagents=False):
    """Plugin skill names in call order (namespace stripped). only_subagents: calls made inside a subagent."""
    calls = []
    for line in pathlib.Path(trace_path).read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("type") != "assistant":
            continue
        if ev.get("parent_tool_use_id") and not subagents:
            continue
        if only_subagents and not ev.get("parent_tool_use_id"):
            continue
        for block in _blocks(ev):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                name = str((block.get("input") or {}).get("skill", ""))
                if name.startswith(PLUGIN):
                    calls.append(name[len(PLUGIN):])
                elif name in SKILLS:
                    calls.append(name)  # un-namespaced call to one of this plugin's skills
    return calls


def _agent_called(trace_path, agent):
    for line in pathlib.Path(trace_path).read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        for block in _blocks(ev):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Agent":
                if agent in str((block.get("input") or {}).get("subagent_type", "")):
                    return True
    return False


def score(result, cases_dir, subagents=False, agent=None):
    rows = []
    for case in result["cases"]:
        exp_path = pathlib.Path(cases_dir) / case["name"] / "expect.json"
        if not exp_path.exists():
            continue
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        for run in case["arms"].get("with", []):
            trace = run.get("tracePath")
            if run.get("error") or not trace or not pathlib.Path(trace).exists():
                seen = _skill_calls(trace, subagents) if trace and pathlib.Path(trace).exists() else []
                if exp.get("expected") is None:
                    bad = bool(seen)
                else:
                    bad = any(s in seen for s in exp.get("forbidden") or [] if s != "*")
                row = {"case": case["name"], "cluster": exp["cluster"], "expected": exp.get("expected"),
                       "error": run.get("error") or "no trace", "primary": False, "strict": False,
                       "recall": False, "forbidden_hit": bad, "mediated": False}
                if agent and exp.get("cluster") != "delegation":
                    row["orchestrated"] = False  # a failed orchestrator run is a miss, not a skipped row
                rows.append(row)
                continue
            calls = _skill_calls(trace, subagents)
            expected = exp.get("expected")
            forbidden = exp.get("forbidden") or []
            first = calls[0] if calls else None
            routed = calls if expected in ROUTERS else [c for c in calls if c not in ROUTERS]
            route_first = routed[0] if routed else None
            if expected is None:
                primary = strict = recall = not calls
                hit_forbidden = bool(calls)
            else:
                primary = route_first == expected
                strict = first == expected
                recall = expected in calls or any(s in calls for s in exp.get("also_ok") or [])
                hit_forbidden = any(s in calls for s in forbidden if s != "*")  # anywhere in the run
            row = {"case": case["name"], "cluster": exp["cluster"], "expected": expected, "first": first,
                   "calls": calls, "route_first": route_first, "primary": primary, "strict": strict,
                   "mediated": first in ROUTERS and expected not in ROUTERS, "recall": recall, "forbidden_hit": hit_forbidden}
            if agent:
                row["agent_called"] = _agent_called(trace, agent)
                want_agent = exp.get("agent", True)
                req = exp.get("required") or []
                inside = _skill_calls(trace, True, only_subagents=True)  # loaded by the agent, not the parent
                row["required_missing"] = [s for s in req if s not in inside]
                if exp.get("cluster") != "delegation":  # delegation cases only report whether the agent was used
                    row["orchestrated"] = (row["agent_called"] == want_agent) and not row["required_missing"]                         and not hit_forbidden
            rows.append(row)
    ok = rows  # errors count as misses (frozen protocol)
    by = collections.defaultdict(list)
    for r in ok:
        by[r["cluster"]].append(r)

    def rate(rs, k):
        return round(sum(1 for r in rs if r[k]) / len(rs), 3) if rs else None

    return {
        "runs": len(rows), "errors": sum(1 for r in rows if "error" in r),
        "route": rate(ok, "primary"), "strict_first": rate(ok, "strict"), "mediated": rate(ok, "mediated"), "recall": rate(ok, "recall"),
        "forbidden_hits": sum(1 for r in ok if r["forbidden_hit"]),
        "clusters": {c: {"n": len(rs), "route": rate(rs, "primary"), "recall": rate(rs, "recall")}
                     for c, rs in sorted(by.items())},
        "orchestrated": rate([r for r in ok if "orchestrated" in r], "orchestrated") if agent else None,
        "delegation_rate": rate([r for r in ok if r.get("cluster") == "delegation"], "agent_called") if agent else None,
        "confusions": sorted(f'{r["expected"]} -> {r.get("route_first") or r.get("error")}' for r in ok if not r["primary"]),
        "rows": rows,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--subagents", action="store_true")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    result = json.loads(pathlib.Path(a.result).read_text(encoding="utf-8"))
    rep = score(result, a.cases, a.subagents, a.agent)
    rep["meta"] = {"claudeVersion": result.get("claudeVersion"), "startedAt": result.get("startedAt"),
                   "costUsd": result.get("costUsd")}
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    brief = {k: rep[k] for k in ("runs", "errors", "orchestrated", "route", "strict_first", "mediated", "recall", "forbidden_hits", "clusters")}
    print(json.dumps(brief, indent=1))
    print("confusions:", *rep["confusions"], sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
