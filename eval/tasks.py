"""Evaluation tasks for agente-local. Every check is mechanical (grep, ast,
exact string) -- never a second LLM call. Ground truth is always computed
from FIXTURE, a frozen copy of the real harness's research.py from before
its result_score/build_evidence_pack cleanup. Tasks never touch the real
harness directory; setup() only ever reads FIXTURE and writes into a fresh
sandbox under ROOT.
"""
import ast
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import ROOT

FIXTURE = Path(
    "/home/jkzero/data-engineer-prep/llm/harness/research.py.bak_20260815_092502"
)


def setup():
    sandbox = Path(tempfile.mkdtemp(prefix="agente_eval_", dir=str(ROOT)))
    shutil.copy2(FIXTURE, sandbox / "research.py")
    return sandbox


def _grep_result_score_lines(path):
    out = subprocess.run(
        ["grep", "-n", "^def result_score", str(path)],
        capture_output=True, text=True, timeout=10,
    )
    return {int(line.split(":", 1)[0]) for line in out.stdout.splitlines()}


def _first_result_score_range(path):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "result_score":
            return node.lineno, node.end_lineno
    raise ValueError(f"no result_score def found in {path}")


_PATH_TOKEN_RE = re.compile(r"\S*(?:/|agente_eval_\w+)\S*")


def check_locate(result, sandbox):
    answer = result.get("answer", "")
    cleaned = _PATH_TOKEN_RE.sub(" ", answer)
    expected = _grep_result_score_lines(FIXTURE)
    found = {int(n) for n in re.findall(r"\d{3,}", cleaned)}
    missing = expected - found
    extra = found - expected
    reasons = []
    if missing:
        reasons.append(f"missing line numbers: {sorted(missing)}")
    if extra:
        reasons.append(f"unexpected numbers not in the definition list: {sorted(extra)}")
    return (not missing and not extra), reasons


def check_count(result, sandbox):
    answer = result.get("answer", "")
    if "6" in answer:
        return True, []
    return False, ["answer does not contain '6'"]


def check_live_def(result, sandbox):
    answer = result.get("answer", "")
    last_line = max(_grep_result_score_lines(FIXTURE))
    if str(last_line) in answer:
        return True, []
    return False, [f"answer does not mention line {last_line} (the definition that actually runs)"]


_RANGE_RE = re.compile(
    r"(\d{3,})\s*(?:-|–|\bto\b|\bthrough\b|\ba\b)\s*(\d{3,})",
    re.IGNORECASE,
)


def _max_blank_extended_end(path, end_line):
    lines = path.read_text().split("\n")
    extended = end_line
    idx = end_line
    while idx < len(lines) and lines[idx].strip() == "":
        extended = idx + 1
        idx += 1
    return extended


def check_dry_delete(result, sandbox):
    reasons = []

    fixture_bytes = FIXTURE.read_bytes()
    sandbox_file = sandbox / "research.py"
    sandbox_bytes = sandbox_file.read_bytes()
    untouched = sandbox_bytes == fixture_bytes
    if not untouched:
        reasons.append("sandbox file was modified; expected dry_run only")

    start, end = _first_result_score_range(FIXTURE)
    max_end = _max_blank_extended_end(FIXTURE, end)
    answer = result.get("answer", "")
    ranges = _RANGE_RE.findall(answer)
    matched = any(int(a) == start and end <= int(b) <= max_end for a, b in ranges)
    if not matched:
        reasons.append(
            f"range starting at {start} and ending between {end} and {max_end} "
            f"(return line, optionally through trailing blanks) not reported; ranges found: {ranges}"
        )

    return (untouched and matched), reasons


def check_chain(result, sandbox):
    answer = result.get("answer", "")
    if "UNSAFE" in answer:
        return True, []
    return False, ["answer does not contain 'UNSAFE'"]


TASKS = [
    {
        "id": "locate",
        "prompt": "Find all definitions of result_score in {sandbox}/research.py and list their line numbers.",
        "setup": setup,
        "check": check_locate,
    },
    {
        "id": "count",
        "prompt": "How many times is result_score defined in {sandbox}/research.py?",
        "setup": setup,
        "check": check_count,
    },
    {
        "id": "live_def",
        "prompt": "In {sandbox}/research.py, result_score is defined more than once. Which definition actually runs (i.e. wins after Python evaluates the whole module top to bottom)? Give its line number.",
        "setup": setup,
        "check": check_live_def,
    },
    {
        "id": "dry_delete",
        "prompt": "In {sandbox}/research.py, propose a dry_run deletion of the FIRST dead (shadowed) result_score definition. Report the exact line range you would delete. Do not call the tool with dry_run=false.",
        "setup": setup,
        "check": check_dry_delete,
    },
    {
        "id": "chain",
        "prompt": "In {sandbox}/research.py, is build_evidence_pack safe to deduplicate down to only its last definition? Answer SAFE or UNSAFE and explain why.",
        "setup": setup,
        "check": check_chain,
    },
]
