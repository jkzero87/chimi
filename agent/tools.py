"""Local tools for agente-local. Read tools plus write_file/delete_lines,
which modify the filesystem under ROOT (dry_run defaults to true on both).
Copied from llm/harness/tools.py 2026-08-15, adapted to import ROOT,
MAX_CHARS and GREP_MAX_MATCHES from config.py instead of hardcoding them.
"""
import ast, difflib, os, re, shutil, subprocess
from datetime import datetime
from pathlib import Path
from config import ROOT, MAX_CHARS, GREP_MAX_MATCHES, DELETE_REVIEW_MAX_LINES

TRUNCATION_NOTE = "\n[TRUNCADO en 4000 chars. Usa start_line y end_line para leer un rango]"

SAFE_CMDS = {"ls","cat","head","tail","wc","df","du","find","grep","git",
             "systemctl","docker","nvidia-smi","free","uname","which","ss","date","ps",
             "cp","diff"}

def _safe(p):
    q = Path(os.path.expanduser(str(p)))
    if not q.is_absolute():
        q = ROOT / q
    q = q.resolve()
    if q != ROOT and ROOT not in q.parents:
        raise ValueError(f"fuera del sandbox: {q}")
    if not q.exists():
        raise ValueError(f"no existe: {q} (las rutas relativas se resuelven desde {ROOT})")
    return q

def _safe_new(p):
    q = Path(os.path.expanduser(str(p)))
    if not q.is_absolute():
        q = ROOT / q
    q = q.resolve()
    if q != ROOT and ROOT not in q.parents:
        raise ValueError(f"fuera del sandbox: {q}")
    if not q.parent.exists():
        raise ValueError(f"el directorio padre no existe: {q.parent} (las rutas relativas se resuelven desde {ROOT})")
    return q

def list_dir(path="."):
    d = _safe(path)
    items = []
    for e in sorted(d.iterdir())[:200]:
        items.append(f"{'d' if e.is_dir() else '-'} {e.stat().st_size:>10} {e.name}")
    return "\n".join(items) or "(vacío)"

def read_file(path, start_line=None, end_line=None):
    f = _safe(path)
    txt = f.read_text(errors="replace")
    if start_line is not None and end_line is not None:
        lines = txt.split("\n")
        selected = lines[start_line - 1:end_line]
        txt = "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(selected))
    truncated = len(txt) > MAX_CHARS
    txt = txt[:MAX_CHARS]
    if truncated:
        txt += "\n[TRUNCADO en 4000 chars. Usa start_line y end_line para leer un rango]"
    return txt

def grep_files(pattern, path="."):
    d = _safe(path)
    out = subprocess.run(["grep","-rn","--binary-files=without-match","-m",str(GREP_MAX_MATCHES),pattern,str(d)],
                         capture_output=True, text=True, timeout=30)
    result = out.stdout or "(sin coincidencias)"
    truncated = len(result) > MAX_CHARS or result.count("\n") >= GREP_MAX_MATCHES
    result = result[:MAX_CHARS]
    if truncated:
        result += "\n[RESULTADO TRUNCADO: puede haber mas coincidencias]"
    return result

def run_safe_bash(cmd):
    if not cmd.strip():
        return "RECHAZADO: comando vacío"
    if "`" in cmd:
        return f"RECHAZADO: contiene backtick (sustitución de comandos no permitida): {cmd}"
    if "$(" in cmd:
        return f"RECHAZADO: contiene '$(' (sustitución de comandos no permitida): {cmd}"
    if ">" in cmd:
        return f"RECHAZADO: contiene '>' (redirección no permitida): {cmd}"
    if "<" in cmd:
        return f"RECHAZADO: contiene '<' (redirección no permitida): {cmd}"
    if "&" in cmd.replace("&&", ""):
        return f"RECHAZADO: contiene '&' suelto (solo se permite '&&' como separador): {cmd}"

    for seg in re.split(r"\|\||&&|[|;]", cmd):
        seg = seg.strip()
        if not seg:
            continue
        first = seg.split()[0]
        if first not in SAFE_CMDS:
            return f"RECHAZADO: segmento '{seg}' usa '{first}', no está en la lista de comandos seguros {sorted(SAFE_CMDS)}"

    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    return f"exit={out.returncode}\n{(out.stdout + out.stderr)[:MAX_CHARS]}"

def _backup(q):
    backup = q.with_name(q.name + f".bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(q, backup)
    return backup

def _diff_result(diff_text, backup=None):
    if backup is not None:
        diff_text += f"\n[backup: {backup}]"
    truncated = len(diff_text) > MAX_CHARS
    diff_text = diff_text[:MAX_CHARS]
    if truncated:
        diff_text += TRUNCATION_NOTE
    return diff_text or "(sin cambios)"

def write_file(path, content, dry_run=True):
    q = _safe_new(path)
    if q.suffix == ".py":
        try:
            ast.parse(content)
        except SyntaxError as e:
            return f"RECHAZADO: sintaxis Python inválida en {q}: {e}"

    current = q.read_text(errors="replace") if q.exists() else ""
    diff = "".join(difflib.unified_diff(
        current.splitlines(keepends=True), content.splitlines(keepends=True),
        fromfile=str(q), tofile=str(q),
    ))

    if dry_run:
        return _diff_result(diff)

    backup = _backup(q) if q.exists() else None
    q.write_text(content)
    return _diff_result(diff, backup)

def _covers_single_top_level_definition(text, start_line, end_line):
    """True if start_line..end_line (1-indexed, inclusive) is exactly one
    module-level def/class, optionally plus trailing blank lines up to (but
    not including) the next non-blank content. Same ast approach as
    function_ranges: a decorator's line counts as the start, end_lineno as
    the end. False (not just "unknown") if the text isn't parseable Python.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False

    lines = text.split("\n")
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        def_start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        def_end = node.end_lineno
        if start_line != def_start or end_line < def_end:
            continue
        if end_line == def_end:
            return True
        trailing = lines[def_end:end_line]
        if all(line.strip() == "" for line in trailing):
            return True
    return False

def delete_lines(path, start_line, end_line, dry_run=True, override=False):
    q = _safe(path)
    txt = q.read_text(errors="replace")
    lines = txt.split("\n")
    n = len(lines)
    if start_line < 1 or end_line < start_line or end_line > n:
        return f"RECHAZADO: rango {start_line}-{end_line} fuera de límites; el archivo tiene {n} líneas"

    new_content = "\n".join(lines[:start_line - 1] + lines[end_line:])

    if q.suffix == ".py":
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            return f"RECHAZADO: el resultado tendría sintaxis Python inválida: {e}"

    diff = "".join(difflib.unified_diff(
        txt.splitlines(keepends=True), new_content.splitlines(keepends=True),
        fromfile=str(q), tofile=str(q),
    ))

    if dry_run:
        return _diff_result(diff)

    if not override:
        size = end_line - start_line + 1
        size_trips = size > DELETE_REVIEW_MAX_LINES
        structural_trips = q.suffix == ".py" and not _covers_single_top_level_definition(txt, start_line, end_line)
        if structural_trips or size_trips:
            reasons = []
            if structural_trips:
                reasons.append(
                    "el rango no corresponde exactamente a una única definición de "
                    "nivel superior (como mucho puede sobrar líneas en blanco al final)"
                )
            if size_trips:
                reasons.append(
                    f"el rango tiene {size} líneas, más del límite de revisión "
                    f"({DELETE_REVIEW_MAX_LINES})"
                )
            return (
                "RECHAZADO: requiere revisión humana antes de aplicarse ("
                + "; ".join(reasons) + "). Diff que se habría aplicado:\n"
                + _diff_result(diff)
            )

    backup = _backup(q)
    q.write_text(new_content)
    return _diff_result(diff, backup)

def check_syntax(path):
    q = _safe(path)
    if q.suffix != ".py":
        return f"{q} is not a .py file; nothing to check"
    src = q.read_text(errors="replace")
    try:
        ast.parse(src)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno}, offset {e.offset})"
    n = len(src.split("\n"))
    return f"OK: valid Python ({n} lines)"

def _calls_orig(node):
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            n = sub.func.id
            if (n.startswith("_orig") or n.startswith("_original")) and n not in found:
                found.append(n)
    return found

def _orig_assignments(tree, name):
    found = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Name) and node.value.id == name):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and (target.id.startswith("_orig") or target.id.startswith("_original")):
                found.append((target.id, node.lineno))
    return found

def function_ranges(path, name):
    q = _safe(path)
    if q.suffix != ".py":
        return f"{q} is not a .py file; nothing to inspect"
    tree = ast.parse(q.read_text(errors="replace"))

    defs = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not defs:
        return f"no module-level definition of '{name}' found in {q}"

    lines = []
    for i, node in enumerate(defs):
        start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        end = node.end_lineno
        live = (i == len(defs) - 1)
        calls = _calls_orig(node)
        lines.append(f"{name} at lines {start}-{end}: live={live} calls_orig={calls}")

    assigns = _orig_assignments(tree, name)
    if assigns:
        lines.append(f"module-level _orig/_original assignments pointing at '{name}':")
        for target_id, lineno in assigns:
            lines.append(f"  line {lineno}: {target_id} = {name}")
    else:
        lines.append(f"no module-level _orig/_original assignment found for '{name}'")

    return "\n".join(lines)

TOOLS = {"list_dir": list_dir, "read_file": read_file,
         "grep_files": grep_files, "run_safe_bash": run_safe_bash,
         "write_file": write_file, "delete_lines": delete_lines,
         "check_syntax": check_syntax, "function_ranges": function_ranges}

SYSTEM = """You are a local assistant on the user's Linux PC. Answer using ONLY real tool output.
Available tools:
- list_dir(path)            list a directory
- read_file(path, start_line, end_line)  read a text file, optionally a line range
- grep_files(pattern, path) search text recursively
- run_safe_bash(cmd)        safe read-only commands (ls, df, git, systemctl, nvidia-smi, ...)
- write_file(path, content, dry_run)      create or overwrite a file. dry_run defaults to
                                           true and only returns a diff without writing. You
                                           MUST show the diff and get the user's approval
                                           before calling again with dry_run=false.
- delete_lines(path, start_line, end_line, dry_run)  remove a 1-indexed inclusive line range.
                                           dry_run defaults to true and only returns a diff
                                           without writing. You MUST show the diff and get the
                                           user's approval before calling again with dry_run=false.
- check_syntax(path)        parse a .py file with ast.parse; reports OK or the exact SyntaxError
                             (line and offset).
- function_ranges(path, name)  for a .py file, list every MODULE-LEVEL def/async def named `name`
                             in file order, each with its start line (decorator line if
                             decorated), end line, whether it is the live (last) one, and any
                             _orig/_original names it calls; also lists module-level
                             `_orig... = name` assignments. Does not look inside classes or
                             other functions.
The 'path' argument is a filesystem path ONLY. Never include words from the user's sentence in
it (prepositions like 'en', 'in', 'the'). Paths are relative to the user's home directory.
When asked to locate or delete a function, use function_ranges to get its exact boundaries
rather than inferring them from grep output or reading around it.

Return ONLY JSON:
{"thought":"short","tool":"name or null","args":{...},"done":false,"answer":""}
Set done=true and fill answer when you have enough real output. Answer in the user's language.
Never invent file contents or command output."""
