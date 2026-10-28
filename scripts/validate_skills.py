#!/usr/bin/env python3
"""Static validation for every skill in skills/ (no Blender, no dependencies).

Checks per skill:
  - SKILL.md exists with YAML frontmatter; `name` matches the folder (Agent Skills spec:
    lowercase a-z0-9-, <= 64 chars), `description` present and <= 1024 chars
  - no duplicate frontmatter keys
  - metadata.related-skills all resolve to existing skills
  - every `references/...` / `scripts/...` path mentioned in SKILL.md exists in the skill
  - self-contained: no `../` paths escaping the skill folder
  - no removed Blender API names (see blender-mcp-workflow/references/blender-5-api-notes.md): an error inside
    fenced code blocks or scripts, a warning in prose; no bpy.app.version fallbacks (Blender 5.2+ only)
  - scripts: parse as Python, expose main(), read ARGS, have a module docstring with ARGS:
    and never shell out or touch the network

Usage: python3 scripts/validate_skills.py [--json]
Exit code 0 = no errors (warnings allowed).
"""
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
DEPRECATED = {
    r"\buse_auto_smooth\b": "use shade_auto_smooth / Smooth by Angle modifier",
    r"\beevee\.use_bloom\b|\buse_bloom\b": "use compositor Glare node (Type=Bloom)",
    r"\buse_ssr\b|\buse_gtao\b": "use eevee.use_raytracing / use_fast_gi",
    r"BLENDER_EEVEE_NEXT": "engine id is BLENDER_EEVEE",
    r"scene\.node_tree\b": "use scene.compositing_node_group",
    r"ShaderNodeTexMusgrave|Musgrave Texture": "Musgrave merged into Noise Texture",
    r"ShaderNodeSeparateRGB|ShaderNodeCombineRGB|CompositorNodeCombRGBA|CompositorNodeSepRGBA": "use Separate/Combine Color",
    r"Subsurface Color\"?\s*[:=]": "removed in 4.0; tint via Base Color",
    r"get_viewport_screenshot|get_scene_info": "third-party MCP tool; use the official Blender MCP tools",
    r"\w\[[\"']Socket_\d+[\"']\]\s*=": "use mod.properties.inputs.<identifier>.value (Blender 5.2)",
}
FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
# Detected with the AST (not substrings), so names like `socket_type` never false-positive.
FORBIDDEN_MODULES = {"subprocess": "spawns processes", "socket": "network access", "urllib": "network access",
                     "requests": "network access", "http": "network access", "ftplib": "network access",
                     "shutil": "bulk file operations", "ctypes": "native code"}
FORBIDDEN_CALLS = {"eval": "dynamic code", "exec": "dynamic code", "__import__": "dynamic import",
                   "os.system": "spawns processes", "os.popen": "spawns processes", "os.remove": "deletes files",
                   "os.unlink": "deletes files", "os.rmdir": "deletes folders"}


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return None, ["missing frontmatter"]
    end = text.find("\n---", 4)
    if end == -1:
        return None, ["unterminated frontmatter"]
    data, errors, seen, current = {}, [], set(), None
    for raw in text[4:end].splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, value = raw.strip().partition(":")
        scope = key if indent == 0 else f"{current}.{key}"
        if scope in seen:
            errors.append(f"duplicate frontmatter key '{scope}'")
        seen.add(scope)
        if indent == 0:
            current = key
            data[key] = value.strip().strip('"') if value.strip() else {}
        elif isinstance(data.get(current), dict):
            data[current][key] = value.strip().strip('"')
    return data, errors


def check_script(path):
    errors, warnings = [], []
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"{path.name}: syntax error {exc}"], []
    doc = ast.get_docstring(tree) or ""
    if "ARGS:" not in doc:
        warnings.append(f"{path.name}: docstring has no ARGS: section")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body):
        errors.append(f"{path.name}: no main() function")
    if 'globals().get("ARGS")' not in src:
        errors.append(f"{path.name}: does not read ARGS from globals()")
    code = src.replace(doc, "") if doc else src
    if re.search(r"bpy\.app\.version\b", code):
        errors.append(f"{path.name}: version branch (bpy.app.version); target Blender 5.2+ only")
    for pattern, fix in DEPRECATED.items():
        if re.search(pattern, code):
            errors.append(f"{path.name}: removed API ({fix})")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for mod in mods:
                if mod.split(".")[0] in FORBIDDEN_MODULES:
                    errors.append(f"{path.name}: imports '{mod}' ({FORBIDDEN_MODULES[mod.split('.')[0]]})")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                f"{fn.value.id}.{fn.attr}" if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else "")
            if name in FORBIDDEN_CALLS:
                errors.append(f"{path.name}: calls '{name}' ({FORBIDDEN_CALLS[name]})")
    return errors, warnings


def main():
    as_json = "--json" in sys.argv
    skills = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    names = {p.name for p in skills}
    report, total_errors, total_warnings = {}, 0, 0
    for skill in skills:
        errors, warnings = [], []
        md = skill / "SKILL.md"
        if not md.exists():
            report[skill.name] = {"errors": ["SKILL.md missing"], "warnings": []}
            total_errors += 1
            continue
        text = md.read_text(encoding="utf-8")
        fm, fm_errors = parse_frontmatter(text)
        errors += fm_errors
        if fm:
            if fm.get("name") != skill.name:
                errors.append(f"name '{fm.get('name')}' != folder '{skill.name}'")
            if not NAME_RE.match(skill.name) or len(skill.name) > 64:
                errors.append("folder name violates Agent Skills naming")
            desc = fm.get("description") or ""
            if not desc:
                errors.append("description missing")
            elif len(desc) > 1024:
                errors.append(f"description too long ({len(desc)} > 1024)")
            related = (fm.get("metadata") or {}).get("related-skills", "")
            for rel in [r.strip() for r in related.split(",") if r.strip()]:
                if rel not in names:
                    errors.append(f"related skill '{rel}' does not exist")
        all_text = text + "".join(p.read_text(encoding="utf-8") for p in skill.rglob("*.md") if p != md)
        if re.search(r"(?<![\w.])\.\./", all_text):
            errors.append("contains ../ path (skills must be self-contained)")
        for ref in set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", text)):
            if not (skill / ref).exists() and not ref.endswith("/"):
                # cross-skill pointers are written as "`<skill>` skill -> `references/x.md`"
                owner = re.search(r"`([a-z0-9-]+)` skill → `" + re.escape(ref) + "`", text)
                if not (owner and (SKILLS / owner.group(1) / ref).exists()):
                    errors.append(f"referenced file missing: {ref}")
        # Runnable code must never use removed APIs. Prose may name them (blender-mcp-workflow documents
        # them on purpose as a "do not use" list), but other skills get a warning for it.
        for f in [md, *skill.rglob("references/*.md")]:
            body = f.read_text(encoding="utf-8")
            code = "\n".join(FENCE_RE.findall(body))
            for pattern, fix in DEPRECATED.items():
                if re.search(pattern, code):
                    errors.append(f"{f.relative_to(skill)}: removed API in a code block ({fix})")
                elif skill.name != "blender-mcp-workflow" and re.search(pattern, body):
                    warnings.append(f"{f.relative_to(skill)}: deprecated API ({fix})")
        for script in sorted(skill.glob("scripts/*.py")):
            e, w = check_script(script)
            errors += e
            warnings += w
            if f"scripts/{script.name}" not in text:
                warnings.append(f"scripts/{script.name} not documented in SKILL.md")
        report[skill.name] = {"errors": errors, "warnings": warnings}
        total_errors += len(errors)
        total_warnings += len(warnings)
    summary = {"skills": len(skills), "scripts": len(list(SKILLS.glob("*/scripts/*.py"))),
               "errors": total_errors, "warnings": total_warnings}
    if as_json:
        print(json.dumps({"summary": summary, "skills": report}, indent=2))
    else:
        for name, r in report.items():
            for e in r["errors"]:
                print(f"ERROR {name}: {e}")
            for w in r["warnings"]:
                print(f"WARN  {name}: {w}")
        print(f"\n{summary['skills']} skills, {summary['scripts']} scripts, "
              f"{summary['errors']} errors, {summary['warnings']} warnings")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
