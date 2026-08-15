#!/usr/bin/env python3
"""Eval CLI for agente-local. Runs local_task against fresh sandboxes and
checks results mechanically. Never touches the real harness directory --
sandboxes are created and destroyed under ROOT for each task.
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.loop import local_task
from agent.server import ensure
from config import ROOT, DEFAULT_PROFILE
from eval.tasks import TASKS

RESULTS_PATH = Path(__file__).resolve().parent / "results.jsonl"
MAX_STEPS = 14


def run_task(task, profile, run_id):
    sandbox = task["setup"]()
    try:
        rel_sandbox = sandbox.relative_to(ROOT)
        prompt = task["prompt"].format(sandbox=str(rel_sandbox))

        start = time.monotonic()
        result = local_task(prompt, max_steps=MAX_STEPS, verbose=False)
        elapsed = time.monotonic() - start

        passed, reasons = task["check"](result, sandbox)

        return {
            "run_id": run_id,
            "id": task["id"],
            "profile": profile,
            "passed": passed,
            "reasons": reasons,
            "steps": result.get("steps"),
            "seconds": round(elapsed, 2),
            "status": result.get("status"),
            "answer": result.get("answer"),
        }
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="agente-local eval suite")
    parser.add_argument("--profile", choices=["fast", "deep"], default=DEFAULT_PROFILE)
    parser.add_argument("--only")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    tasks = [tk for tk in TASKS if args.only is None or tk["id"] == args.only]
    if not tasks:
        print(f"no task with id={args.only!r}")
        sys.exit(1)

    ensure(args.profile)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    total = 0
    passed_count = 0

    with open(RESULTS_PATH, "a") as f:
        for _ in range(args.runs):
            for task in tasks:
                record = run_task(task, args.profile, run_id)
                total += 1
                if record["passed"]:
                    passed_count += 1
                status = "PASS" if record["passed"] else "FAIL"
                print(
                    f"[{record['id']}] {status} profile={record['profile']} "
                    f"steps={record['steps']} seconds={record['seconds']} "
                    f"reasons={record['reasons']}"
                )
                f.write(json.dumps(record) + "\n")
                f.flush()

    print(f"\n{passed_count}/{total} passed")


if __name__ == "__main__":
    main()
