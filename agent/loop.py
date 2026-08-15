"""Tool-use loop for agente-local. Copied from llm/harness/tools.py 2026-08-15,
adapted to import llm_json from agent.llm and PORT from config.py instead of
research.py/BRAIN_PORT.
"""
import sys
from config import PORT, MAX_HISTORY_CHARS
from agent.llm import llm_json
from agent.tools import TOOLS, SYSTEM

def _capped_history(entries):
    full = "".join(entries)
    if len(full) <= MAX_HISTORY_CHARS or len(entries) <= 1:
        return full

    first = entries[0]
    rest = entries[1:]
    budget = max(0, MAX_HISTORY_CHARS - len(first) - 60)

    kept = []
    total = 0
    for entry in reversed(rest):
        if total + len(entry) > budget:
            break
        kept.insert(0, entry)
        total += len(entry)

    omitted = len(rest) - len(kept)
    if omitted == 0:
        return full

    marker = f"\n[... {omitted} earlier observations omitted ...]\n"
    print(
        f"[loop] history capped: {omitted} observation(s) omitted "
        f"(history was {len(full)} chars, limit {MAX_HISTORY_CHARS})",
        file=sys.stderr,
    )
    return first + marker + "".join(kept)

def local_task(task, max_steps=5, verbose=True):
    history_entries = []
    for step in range(1, max_steps + 1):
        remaining = max_steps - step + 1
        urgency = "\nThis is your LAST step. You MUST set done=true and answer with what you have." if remaining == 1 else f"\nYou have {remaining} tool calls left. If you already have enough evidence, set done=true now."
        history = _capped_history(history_entries)
        user = f"Task: {task}\n\nObservations so far:\n{history or '(none)'}\n\nStep {step} of {max_steps}.{urgency}\n\nReturn only JSON."
        plan = llm_json(PORT, SYSTEM, user, temp=0.1, max_tokens=900)
        if not isinstance(plan, dict):
            return {"status": "ERROR", "answer": f"plan inválido: {plan}"}
        if plan.get("done") or not plan.get("tool"):
            return {"status": "OK", "answer": plan.get("answer", ""), "steps": step}
        name, args = plan.get("tool"), plan.get("args") or {}
        if verbose:
            print(f"  [{step}] {name}({args})")
        try:
            obs = TOOLS[name](**args) if name in TOOLS else f"herramienta desconocida: {name}"
        except Exception as e:
            obs = f"ERROR: {e}"
        history_entries.append(f"\n--- {name}({args}) ---\n{obs}\n")
    return {"status": "MAX_STEPS", "answer": "no terminé en los pasos permitidos", "history": "".join(history_entries)[-1500:]}
