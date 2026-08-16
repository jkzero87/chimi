"""Tool-use loop for chimi. Copied from llm/harness/tools.py 2026-08-15,
adapted to import llm_json from agent.llm and PORT from config.py instead of
research.py/BRAIN_PORT.
"""
import sys
import config
from config import PORT
from agent.llm import llm_json
from agent.profiles import MAX_HISTORY_CHARS as PROFILE_MAX_HISTORY_CHARS
from agent.server import ensure
from agent.tools import TOOLS, SYSTEM

_CONTEXT_ERROR_MARKERS = ("context", "n_ctx", "too long", "exceed")

def _capped_history(entries, max_history_chars):
    full = "".join(entries)
    if len(full) <= max_history_chars or len(entries) <= 1:
        return full, False

    first = entries[0]
    rest = entries[1:]
    budget = max(0, max_history_chars - len(first) - 60)

    kept = []
    total = 0
    for entry in reversed(rest):
        if total + len(entry) > budget:
            break
        kept.insert(0, entry)
        total += len(entry)

    omitted = len(rest) - len(kept)
    if omitted == 0:
        return full, False

    marker = f"\n[... {omitted} earlier observations omitted ...]\n"
    print(
        f"[loop] history capped: {omitted} observation(s) omitted "
        f"(history was {len(full)} chars, limit {max_history_chars})",
        file=sys.stderr,
    )
    return first + marker + "".join(kept), True

def _is_context_error(message):
    lowered = message.lower()
    return any(marker in lowered for marker in _CONTEXT_ERROR_MARKERS)

def local_task(task, max_steps=5, verbose=True, max_history_chars=None, max_tokens=None):
    if max_history_chars is None:
        max_history_chars = config.MAX_HISTORY_CHARS
    if max_tokens is None:
        max_tokens = config.PLANNER_MAX_TOKENS
    history_entries = []
    tool_calls = []
    history_capped = False
    for step in range(1, max_steps + 1):
        remaining = max_steps - step + 1
        urgency = "\nThis is your LAST step. You MUST set done=true and answer with what you have." if remaining == 1 else f"\nYou have {remaining} tool calls left. If you already have enough evidence, set done=true now."
        history, capped = _capped_history(history_entries, max_history_chars)
        history_capped = history_capped or capped
        user = f"Task: {task}\n\nObservations so far:\n{history or '(none)'}\n\nStep {step} of {max_steps}.{urgency}\n\nReturn only JSON."
        try:
            plan = llm_json(PORT, SYSTEM, user, temp=0.1, max_tokens=max_tokens)
        except RuntimeError as e:
            if _is_context_error(str(e)):
                return {
                    "status": "CONTEXT_ERROR",
                    "answer": f"servidor reportó error de contexto: {e}",
                    "history_capped": history_capped,
                    "tool_calls": tool_calls,
                }
            raise
        if not isinstance(plan, dict):
            return {"status": "ERROR", "answer": f"plan inválido: {plan}", "history_capped": history_capped, "tool_calls": tool_calls}
        if plan.get("raw_text") or plan.get("call_failed"):
            flag = "raw_text" if plan.get("raw_text") else "call_failed"
            offending = str(plan.get("answer", ""))[:500]
            return {
                "status": "ERROR",
                "answer": f"el modelo no devolvió un plan JSON válido (flag={flag}): {offending}",
                "steps": step,
                "history_capped": history_capped,
                "tool_calls": tool_calls,
            }
        if plan.get("done") or not plan.get("tool"):
            return {
                "status": "OK",
                "answer": plan.get("answer", ""),
                "steps": step,
                "history_capped": history_capped,
                "tool_calls": tool_calls,
            }
        name, args = plan.get("tool"), plan.get("args") or {}
        tool_calls.append({"step": step, "tool": name, "args": args})
        if verbose:
            print(f"  [{step}] {name}({args})")
        try:
            obs = TOOLS[name](**args) if name in TOOLS else f"herramienta desconocida: {name}"
        except Exception as e:
            obs = f"ERROR: {e}"
        history_entries.append(f"\n--- {name}({args}) ---\n{obs}\n")
    return {
        "status": "MAX_STEPS",
        "answer": "no terminé en los pasos permitidos",
        "history": "".join(history_entries)[-1500:],
        "history_capped": history_capped,
        "tool_calls": tool_calls,
    }

def run_task(task, max_steps=14):
    ensure("fast")
    result = local_task(task, max_steps=max_steps, verbose=False, max_history_chars=PROFILE_MAX_HISTORY_CHARS["fast"])

    if result.get("status") == "MAX_STEPS":
        reason = "max_steps"
    elif result.get("history_capped"):
        reason = "history_capped"
    elif result.get("status") == "CONTEXT_ERROR":
        reason = "context_error"
    else:
        reason = None

    if reason is None:
        result["profile"] = "fast"
        return result

    ensure("deep")
    result = local_task(task, max_steps=max_steps, verbose=False, max_history_chars=PROFILE_MAX_HISTORY_CHARS["deep"])
    result["profile"] = "deep"
    result["escalation_reason"] = reason
    return result
