#!/usr/bin/env python3
"""Static validation for every skill in skills/ (no Blender, no dependencies).

Checks per skill:
  - SKILL.md exists with YAML frontmatter; `name` matches the folder (Agent Skills spec:
    lowercase a-z0-9-, <= 64 chars), `description` present and <= 1024 chars
  - no duplicate frontmatter keys
  - strict scalars: an unquoted value containing ': ' or ' #', or starting with a YAML indicator, is an
    error ("quote the value"); double-quoted values are decoded before the length check; PyYAML, if
    importable, additionally parses the whole frontmatter
  - metadata.related-skills all resolve to existing skills
  - every `references/...` / `scripts/...` path mentioned in SKILL.md exists in the skill
  - self-contained: no `../` paths escaping the skill folder
  - no removed Blender API names (see blender-mcp-workflow/references/blender-5-api-notes.md): an error inside
    fenced code blocks or scripts, a warning in prose; no bpy.app.version fallbacks (Blender 5.2+ only)
  - scripts: parse as Python, expose main(), read ARGS, have a module docstring with ARGS:
    and never shell out or touch the network

Usage: python3 scripts/validate_skills.py [--json | --self-test]
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


YAML_BAD_START = {"@": "reserved indicator", "`": "reserved indicator", "%": "directive indicator",
                  "*": "alias indicator", "&": "anchor indicator", "!": "tag indicator",
                  "|": "block scalar indicator", ">": "block scalar indicator"}
BLOCK_SCALAR_RE = re.compile(r"[|>][+-]?\d*")
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "/": "/", "b": "\b", "f": "\f",
           "a": "\a", "e": "\x1b", " ": " ", "v": "\v", "N": "\x85", "_": "\xa0"}


def _decode_double(raw):
    """Decode a YAML double-quoted scalar (raw[0] == '"'). Returns (value, rest) or raises ValueError."""
    out, i = [], 1
    while i < len(raw):
        c = raw[i]
        if c == "\\":
            i += 1
            if i >= len(raw):
                raise ValueError("dangling backslash")
            e = raw[i]
            if e in "xuU":
                width = {"x": 2, "u": 4, "U": 8}[e]
                digits = raw[i + 1:i + 1 + width]
                if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                    raise ValueError(f"bad \\{e} escape")
                out.append(chr(int(digits, 16)))
                i += width
            elif e in ESCAPES:
                out.append(ESCAPES[e])
            else:
                raise ValueError(f"unknown escape \\{e}")
        elif c == '"':
            return "".join(out), raw[i + 1:]
        else:
            out.append(c)
        i += 1
    raise ValueError("unterminated double-quoted string")


def decode_scalar(raw):
    """Decode one frontmatter scalar the way YAML would. Returns (value, [errors]); never raises."""
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            value, rest = _decode_double(raw)
        except ValueError as exc:
            return raw, [f"invalid double-quoted value ({exc})"]
        if rest.strip() and not rest.strip().startswith("#"):
            return value, ["text after the closing quote"]
        return value, []
    if raw.startswith("'"):
        m = re.fullmatch(r"'((?:[^']|'')*)'\s*(#.*)?", raw)
        if not m:
            return raw, ["invalid single-quoted value (unterminated or text after the closing quote)"]
        return m.group(1).replace("''", "'"), []
    errors = []
    if raw and raw[0] in YAML_BAD_START and not BLOCK_SCALAR_RE.fullmatch(raw):
        errors.append(f"unquoted value starts with '{raw[0]}' ({YAML_BAD_START[raw[0]]}): quote the value")
    elif raw[:2] in ("- ", "? ") or raw in ("-", "?"):
        errors.append("unquoted value starts with a YAML sequence/key indicator: quote the value")
    elif raw and raw[0] in "[{":
        close = "]" if raw[0] == "[" else "}"
        if not raw.endswith(close):
            errors.append(f"unquoted value starts with '{raw[0]}' but is not a closed flow collection: quote the value")
    if ": " in raw or raw.endswith(":"):
        errors.append("unquoted value contains ': ' (YAML reads a nested mapping): quote the value")
    if " #" in raw:
        errors.append("unquoted value contains ' #' (YAML starts a comment there): quote the value")
    return raw, errors


def parse_frontmatter(text):
    """Lenient line parser plus strict scalar checks. Returns (data, errors); values are decoded scalars."""
    if not text.startswith("---\n"):
        return None, ["missing frontmatter"]
    end = text.find("\n---", 4)
    if end == -1:
        return None, ["unterminated frontmatter"]
    data, errors, seen, current = {}, [], set(), None
    lines = text[4:end].splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, value = raw.strip().partition(":")
        scope = key if indent == 0 else f"{current}.{key}"
        if scope in seen:
            errors.append(f"duplicate frontmatter key '{scope}'")
        seen.add(scope)
        if value.strip() and BLOCK_SCALAR_RE.fullmatch(value.strip()):
            block = []
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                block.append(lines[i].strip())
                i += 1
            decoded = " ".join(b for b in block if b)
        elif value.strip():
            decoded, scalar_errors = decode_scalar(value)
            errors += [f"{scope}: {e}" for e in scalar_errors]
        else:
            decoded = {}
        if indent == 0:
            current = key
            data[key] = decoded
        elif isinstance(data.get(current), dict):
            data[current][key] = decoded
    return data, errors


def yaml_strict_check(text):
    """Strict parse with PyYAML when it is importable; returns [] when PyYAML is absent."""
    try:
        import yaml
    except ImportError:
        return []
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end == -1:
        return []
    try:
        loaded = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        return [f"strict YAML parse failed: {str(exc).splitlines()[0]} (quote the value)"]
    if not isinstance(loaded, dict):
        return ["frontmatter is not a YAML mapping"]
    return []


SELF_TEST_GOOD = [
    "---\nname: x\ndescription: Plain text with a colon:no-space and 5# no comment\n---\n",
    '---\nname: x\ndescription: "Quoted: with colon, and # hash and \\"escapes\\""\n---\n',
    "---\nname: x\ndescription: 'Single: quoted'\n---\n",
    '---\nname: x\ndescription: >\n  folded text: allowed\n  here\nmetadata:\n  version: "1.0"\n---\n',
]
SELF_TEST_BAD = [
    "---\nname: x\ndescription: Use before: this breaks\n---\n",
    "---\nname: x\ndescription: text then # comment\n---\n",
    "---\nname: x\ndescription: @starts with at\n---\n",
    "---\nname: x\ndescription: `backtick start`\n---\n",
    "---\nname: x\ndescription: *alias start\n---\n",
    "---\nname: x\ndescription: [unclosed flow\n---\n",
    '---\nname: x\ndescription: "unterminated\n---\n',
    '---\nname: x\ndescription: "bad \\q escape"\n---\n',
    '---\nname: x\ndescription: "closed" trailing\n---\n',
]


def self_test():
    failures = []
    for n, text in enumerate(SELF_TEST_GOOD):
        _, errs = parse_frontmatter(text)
        errs += yaml_strict_check(text)
        if errs:
            failures.append(f"good sample {n} flagged: {errs}")
    for n, text in enumerate(SELF_TEST_BAD):
        _, errs = parse_frontmatter(text)
        if not errs:
            failures.append(f"bad sample {n} was not flagged: {text!r}")
    fm, _ = parse_frontmatter('---\nname: x\ndescription: "a\\tb\\u00e9 \\"q\\""\n---\n')
    if fm["description"] != 'a\tbé "q"':
        failures.append(f"double-quoted decode wrong: {fm['description']!r}")
    long_text = '---\nname: x\ndescription: "' + 'a\\"' * 400 + '"\n---\n'
    fm, errs = parse_frontmatter(long_text)
    if errs or len(fm["description"]) != 800:
        failures.append(f"escaped length should decode to 800 chars, got {len(fm['description'])} {errs}")
    for f in failures:
        print("SELF-TEST FAIL:", f)
    print(f"self-test: {len(SELF_TEST_GOOD)} good, {len(SELF_TEST_BAD)} bad samples, "
          f"{'OK' if not failures else str(len(failures)) + ' failure(s)'}")
    return 1 if failures else 0


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
    if "--self-test" in sys.argv:
        return self_test()
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
        errors += fm_errors + yaml_strict_check(text)
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
