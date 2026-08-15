"""Tool-use loop for agente-local. Copied from llm/harness/tools.py 2026-08-15,
adapted to import llm_json from agent.llm and PORT from config.py instead of
research.py/BRAIN_PORT.
"""
from config import PORT
from agent.llm import llm_json
from agent.tools import TOOLS, SYSTEM

def local_task(task, max_steps=5, verbose=True):
    history = ""
    for step in range(1, max_steps + 1):
        remaining = max_steps - step + 1
        urgency = "\nThis is your LAST step. You MUST set done=true and answer with what you have." if remaining == 1 else f"\nYou have {remaining} tool calls left. If you already have enough evidence, set done=true now."
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
        history += f"\n--- {name}({args}) ---\n{obs}\n"
    return {"status": "MAX_STEPS", "answer": "no terminé en los pasos permitidos", "history": history[-1500:]}
