"""Tests for eval/analyze.py. Uses small in-memory record lists, never the
real eval/results.jsonl.
"""
from eval import analyze as a


def _rec(run_id="r1", id="chain", passed=True, status="OK", steps=3, seconds=15.0):
    return {
        "run_id": run_id, "id": id, "passed": passed,
        "status": status, "steps": steps, "seconds": seconds,
    }


# --- summarize: counts ---

def test_summarize_counts_n_passed_failed():
    records = [_rec(passed=True), _rec(passed=True), _rec(passed=False)]
    s = a.summarize(records)
    assert s["n"] == 3
    assert s["passed"] == 2
    assert s["failed"] == 1
    assert s["pass_rate"] == 2 / 3


def test_summarize_empty_records_no_crash():
    s = a.summarize([])
    assert s["n"] == 0
    assert s["pass_rate"] is None
    assert s["steps"] == {"median": None, "min": None, "max": None}
    assert s["seconds"] == {"median": None, "min": None, "max": None}


# --- status breakdown ---

def test_status_breakdown_counts_each_status():
    records = [
        _rec(status="OK"), _rec(status="OK"), _rec(status="ERROR"),
        _rec(status="MAX_STEPS"),
    ]
    s = a.summarize(records)
    assert s["status_breakdown"] == {"OK": 2, "ERROR": 1, "MAX_STEPS": 1}


# --- filtering ---

def test_filter_by_run_id():
    records = [_rec(run_id="r1"), _rec(run_id="r1"), _rec(run_id="r2")]
    s = a.summarize(records, run_id="r1")
    assert s["n"] == 2


def test_filter_by_task_id():
    records = [_rec(id="chain"), _rec(id="chain"), _rec(id="count")]
    s = a.summarize(records, task_id="chain")
    assert s["n"] == 2


def test_filter_by_run_id_and_task_id_combined():
    records = [
        _rec(run_id="r1", id="chain"),
        _rec(run_id="r1", id="count"),
        _rec(run_id="r2", id="chain"),
    ]
    s = a.summarize(records, run_id="r1", task_id="chain")
    assert s["n"] == 1


# --- missing keys must not crash, and must be counted ---

def test_missing_passed_key_counted_not_crashed():
    records = [_rec(), {"run_id": "r1", "id": "chain"}]
    s = a.summarize(records)
    assert s["n"] == 2
    assert s["passed"] == 1
    assert s["failed"] == 0
    assert s["missing_fields"]["passed"] == 1


def test_missing_status_key_excluded_from_breakdown():
    records = [_rec(status="OK"), {"run_id": "r1", "id": "chain"}]
    s = a.summarize(records)
    assert s["status_breakdown"] == {"OK": 1}
    assert s["missing_fields"]["status"] == 1


def test_missing_steps_and_seconds_excluded_from_stats():
    records = [
        _rec(steps=3, seconds=10.0),
        {"run_id": "r1", "id": "chain", "passed": True, "status": "OK"},
    ]
    s = a.summarize(records)
    assert s["steps"] == {"median": 3, "min": 3, "max": 3}
    assert s["seconds"] == {"median": 10.0, "min": 10.0, "max": 10.0}
    assert s["missing_fields"]["steps"] == 1
    assert s["missing_fields"]["seconds"] == 1


def test_pass_rate_denominator_is_n_not_just_complete_records():
    records = [_rec(passed=True), {"run_id": "r1", "id": "chain"}]
    s = a.summarize(records)
    assert s["n"] == 2
    assert s["pass_rate"] == 1 / 2


# --- runs() ---

def test_runs_counts_and_orders_by_run_id():
    records = [_rec(run_id="20260815_1000"), _rec(run_id="20260815_0900"), _rec(run_id="20260815_0900")]
    result = a.runs(records)
    assert result == [
        {"run_id": "20260815_0900", "count": 2},
        {"run_id": "20260815_1000", "count": 1},
    ]


def test_runs_missing_run_id_not_crashed():
    records = [_rec(run_id="r1"), {"id": "chain"}]
    result = a.runs(records)
    run_ids = [row["run_id"] for row in result]
    assert "r1" in run_ids
    assert None in run_ids


# --- compare() ---

def test_compare_reports_pass_rate_and_seconds_diff():
    records = (
        [_rec(run_id="before", passed=True, seconds=20.0)] * 9
        + [_rec(run_id="before", passed=False, seconds=20.0)]
        + [_rec(run_id="after", passed=True, seconds=15.0)] * 10
    )
    result = a.compare(records, "before", "after")
    assert result["a"]["n"] == 10
    assert result["b"]["n"] == 10
    assert result["a"]["pass_rate"] == 0.9
    assert result["b"]["pass_rate"] == 1.0
    assert result["pass_rate_diff"] == 1.0 - 0.9
    assert result["median_seconds_diff"] == 15.0 - 20.0


def test_compare_with_no_data_on_one_side_gives_none_diff():
    records = [_rec(run_id="only_one")]
    result = a.compare(records, "only_one", "missing")
    assert result["b"]["n"] == 0
    assert result["pass_rate_diff"] is None
    assert result["median_seconds_diff"] is None


def test_compare_respects_task_id_filter():
    records = [
        _rec(run_id="before", id="chain", passed=False),
        _rec(run_id="before", id="count", passed=True),
        _rec(run_id="after", id="chain", passed=True),
        _rec(run_id="after", id="count", passed=True),
    ]
    result = a.compare(records, "before", "after", task_id="chain")
    assert result["a"]["n"] == 1
    assert result["a"]["passed"] == 0
    assert result["b"]["n"] == 1
    assert result["b"]["passed"] == 1
