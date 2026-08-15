"""Local tools for agente-local. READ-ONLY: nothing here modifies the system.
Copied from llm/harness/tools.py 2026-08-15, adapted to import ROOT,
MAX_CHARS and GREP_MAX_MATCHES from config.py instead of hardcoding them.
"""
import os, subprocess
from pathlib import Path
from config import ROOT, MAX_CHARS, GREP_MAX_MATCHES

SAFE_CMDS = {"ls","cat","head","tail","wc","df","du","find","grep","git",
             "systemctl","docker","nvidia-smi","free","uname","which","ss","date","ps"}

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
    first = cmd.strip().split()[0] if cmd.strip() else ""
    if first not in SAFE_CMDS:
        return f"RECHAZADO: '{first}' no está en la lista de comandos seguros {sorted(SAFE_CMDS)}"
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    return f"exit={out.returncode}\n{(out.stdout + out.stderr)[:MAX_CHARS]}"

TOOLS = {"list_dir": list_dir, "read_file": read_file,
         "grep_files": grep_files, "run_safe_bash": run_safe_bash}

SYSTEM = """You are a local assistant on the user's Linux PC. Answer using ONLY real tool output.
Available tools:
- list_dir(path)            list a directory
- read_file(path, start_line, end_line)  read a text file, optionally a line range
- grep_files(pattern, path) search text recursively
- run_safe_bash(cmd)        safe read-only commands (ls, df, git, systemctl, nvidia-smi, ...)

Return ONLY JSON:
{"thought":"short","tool":"name or null","args":{...},"done":false,"answer":""}
Set done=true and fill answer when you have enough real output. Answer in the user's language.
Never invent file contents or command output."""
