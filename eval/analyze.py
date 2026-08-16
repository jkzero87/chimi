"""Analysis over eval/results.jsonl. Replaces the ad-hoc `python3 -c`
one-liners used for every measurement so far -- one of them truncated an
"answer" field for display and read significance into the cut. This module
never touches "answer" at all, for that reason.

results.jsonl spans schema changes made the same day it was created, so a
record here may be missing keys another record has. Every function below
counts those instead of raising.
"""
import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent / "results.jsonl"

_MISSING = object()


def load(path=RESULTS_PATH):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def runs(records):
    """Distinct run_ids present, with counts. Returns a list of
    {"run_id": ..., "count": ...} dicts, ordered by run_id ascending (which
    is chronological, since run_id is a YYYYMMDD_HHMMSS timestamp).
    """
    counts = {}
    for r in records:
        run_id = r.get("run_id")
        counts[run_id] = counts.get(run_id, 0) + 1
    ordered = sorted(counts, key=lambda rid: (rid is None, rid or ""))
    return [{"run_id": rid, "count": counts[rid]} for rid in ordered]


def _stats(values):
    if not values:
        return {"median": None, "min": None, "max": None}
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def summarize(records, run_id=None, task_id=None):
    """Summary of records matching run_id/task_id (task_id filters on the
    "id" field). A missing key on a record is counted under
    missing_fields, never allowed to raise or to silently skew a rate.
    """
    filtered = [
        r for r in records
        if (run_id is None or r.get("run_id") == run_id)
        and (task_id is None or r.get("id") == task_id)
    ]
    n = len(filtered)

    passed = failed = missing_passed = 0
    status_breakdown = {}
    missing_status = 0
    steps_values = []
    missing_steps = 0
    seconds_values = []
    missing_seconds = 0

    for r in filtered:
        passed_val = r.get("passed", _MISSING)
        if passed_val is _MISSING or passed_val is None:
            missing_passed += 1
        elif passed_val:
            passed += 1
        else:
            failed += 1

        status_val = r.get("status", _MISSING)
        if status_val is _MISSING or status_val is None:
            missing_status += 1
        else:
            status_breakdown[status_val] = status_breakdown.get(status_val, 0) + 1

        steps_val = r.get("steps", _MISSING)
        if steps_val is _MISSING or steps_val is None:
            missing_steps += 1
        else:
            steps_values.append(steps_val)

        seconds_val = r.get("seconds", _MISSING)
        if seconds_val is _MISSING or seconds_val is None:
            missing_seconds += 1
        else:
            seconds_values.append(seconds_val)

    return {
        "n": n,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / n) if n else None,
        "status_breakdown": status_breakdown,
        "steps": _stats(steps_values),
        "seconds": _stats(seconds_values),
        "missing_fields": {
            "passed": missing_passed,
            "status": missing_status,
            "steps": missing_steps,
            "seconds": missing_seconds,
        },
    }


def compare(records, run_id_a, run_id_b, task_id=None):
    """Both summaries plus b-minus-a differences in pass_rate and median
    seconds (None if either side has no data to diff)."""
    a = summarize(records, run_id=run_id_a, task_id=task_id)
    b = summarize(records, run_id=run_id_b, task_id=task_id)

    pass_rate_diff = None
    if a["pass_rate"] is not None and b["pass_rate"] is not None:
        pass_rate_diff = b["pass_rate"] - a["pass_rate"]

    median_seconds_diff = None
    if a["seconds"]["median"] is not None and b["seconds"]["median"] is not None:
        median_seconds_diff = b["seconds"]["median"] - a["seconds"]["median"]

    return {
        "a": a,
        "b": b,
        "pass_rate_diff": pass_rate_diff,
        "median_seconds_diff": median_seconds_diff,
    }


def _format_timestamp(run_id):
    try:
        return datetime.strptime(run_id, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "unknown"


def _fmt_rate(rate):
    return "n/a" if rate is None else f"{rate:.1%}"


def _fmt_diff_rate(diff):
    return "n/a" if diff is None else f"{diff:+.1%}"


def _fmt_diff_seconds(diff):
    return "n/a" if diff is None else f"{diff:+.2f}"


def _print_summary(label, summary):
    print(
        f"{label}: n={summary['n']} passed={summary['passed']} "
        f"failed={summary['failed']} pass_rate={_fmt_rate(summary['pass_rate'])}"
    )
    print(f"  status_breakdown={summary['status_breakdown']}")
    steps, seconds = summary["steps"], summary["seconds"]
    print(f"  steps:   median={steps['median']} min={steps['min']} max={steps['max']}")
    print(f"  seconds: median={seconds['median']} min={seconds['min']} max={seconds['max']}")
    missing = summary["missing_fields"]
    if any(missing.values()):
        print(f"  missing_fields={missing}")


def main():
    parser = argparse.ArgumentParser(description="Analyze eval/results.jsonl")
    parser.add_argument("--path", default=str(RESULTS_PATH), help="path to results.jsonl")
    parser.add_argument("--task", metavar="TASK_ID", help="restrict --run/--compare to one task id")
    parser.add_argument("--list", action="store_true", help="list run_ids with counts and timestamps")
    parser.add_argument("--run", metavar="RUN_ID", help="summarize one run_id")
    parser.add_argument("--compare", nargs=2, metavar=("RUN_ID_A", "RUN_ID_B"), help="compare two run_ids")
    args = parser.parse_args()

    records = load(Path(args.path))

    if args.list:
        for row in runs(records):
            print(f"{row['run_id']}  n={row['count']}  {_format_timestamp(row['run_id'])}")
        return

    if args.run:
        _print_summary(args.run, summarize(records, run_id=args.run, task_id=args.task))
        return

    if args.compare:
        run_id_a, run_id_b = args.compare
        result = compare(records, run_id_a, run_id_b, task_id=args.task)
        _print_summary(run_id_a, result["a"])
        _print_summary(run_id_b, result["b"])
        print(
            f"diff: pass_rate={_fmt_diff_rate(result['pass_rate_diff'])} "
            f"median_seconds={_fmt_diff_seconds(result['median_seconds_diff'])}"
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
