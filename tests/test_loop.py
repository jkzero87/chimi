"""Tests for the per-profile history cap in agent/loop.py. No running
llama-server required: llm_json is monkeypatched to a stub that immediately
finishes the task, so we only observe the cap logic and its "capped" flag.
"""
import config
from agent import loop as l


def _stub_llm_json_factory(n_calls_before_done=0):
    calls = {"n": 0}

    def _stub(port, system, user, temp=0.1, max_tokens=900):
        calls["n"] += 1
        if calls["n"] > n_calls_before_done:
            return {"done": True, "answer": "ok"}
        return {"tool": "list_dir", "args": {"path": "."}}

    return _stub


def test_fast_profile_uses_12000():
    assert l.PROFILE_MAX_HISTORY_CHARS["fast"] == 12000


def test_deep_profile_uses_40000():
    assert l.PROFILE_MAX_HISTORY_CHARS["deep"] == 40000


def test_local_task_defaults_to_config_max_history_chars(monkeypatch):
    seen = {}

    def fake_capped_history(entries, max_history_chars):
        seen["cap"] = max_history_chars
        return "".join(entries), False

    monkeypatch.setattr(l, "_capped_history", fake_capped_history)
    monkeypatch.setattr(l, "llm_json", _stub_llm_json_factory())

    l.local_task("task", max_steps=1)

    assert seen["cap"] == config.MAX_HISTORY_CHARS


def test_explicit_cap_wins_over_default(monkeypatch):
    seen = {}

    def fake_capped_history(entries, max_history_chars):
        seen["cap"] = max_history_chars
        return "".join(entries), False

    monkeypatch.setattr(l, "_capped_history", fake_capped_history)
    monkeypatch.setattr(l, "llm_json", _stub_llm_json_factory())

    l.local_task("task", max_steps=1, max_history_chars=999)

    assert seen["cap"] == 999


def test_local_task_defaults_to_config_planner_max_tokens(monkeypatch):
    seen = {}

    def fake_llm_json(port, system, user, temp=0.1, max_tokens=900):
        seen["max_tokens"] = max_tokens
        return {"done": True, "answer": "ok"}

    monkeypatch.setattr(l, "llm_json", fake_llm_json)

    l.local_task("task", max_steps=1)

    assert seen["max_tokens"] == config.PLANNER_MAX_TOKENS


def test_explicit_max_tokens_wins_over_default(monkeypatch):
    seen = {}

    def fake_llm_json(port, system, user, temp=0.1, max_tokens=900):
        seen["max_tokens"] = max_tokens
        return {"done": True, "answer": "ok"}

    monkeypatch.setattr(l, "llm_json", fake_llm_json)

    l.local_task("task", max_steps=1, max_tokens=1234)

    assert seen["max_tokens"] == 1234


def test_run_task_passes_fast_cap_when_no_escalation(monkeypatch):
    seen = {}

    def fake_local_task(task, max_steps, verbose, max_history_chars):
        seen["cap"] = max_history_chars
        return {"status": "OK", "answer": "ok", "steps": 1, "history_capped": False}

    monkeypatch.setattr(l, "ensure", lambda profile: None)
    monkeypatch.setattr(l, "local_task", fake_local_task)

    result = l.run_task("task", max_steps=14)

    assert seen["cap"] == l.PROFILE_MAX_HISTORY_CHARS["fast"]
    assert result["profile"] == "fast"


def test_run_task_passes_deep_cap_on_escalation(monkeypatch):
    caps_seen = []
    ensured = []

    def fake_local_task(task, max_steps, verbose, max_history_chars):
        caps_seen.append(max_history_chars)
        return {"status": "MAX_STEPS", "answer": "no terminé", "history_capped": False}

    monkeypatch.setattr(l, "ensure", lambda profile: ensured.append(profile))
    monkeypatch.setattr(l, "local_task", fake_local_task)

    result = l.run_task("task", max_steps=14)

    assert caps_seen == [
        l.PROFILE_MAX_HISTORY_CHARS["fast"],
        l.PROFILE_MAX_HISTORY_CHARS["deep"],
    ]
    assert ensured == ["fast", "deep"]
    assert result["profile"] == "deep"
    assert result["escalation_reason"] == "max_steps"


# --- _capped_history truncation marker still fires with a parameterized cap ---

def test_capped_history_marker_fires_when_cap_exceeded():
    entries = ["a" * 100, "b" * 100, "c" * 100]
    history, capped = l._capped_history(entries, max_history_chars=150)
    assert capped is True
    assert "earlier observations omitted" in history


def test_capped_history_no_marker_under_cap():
    entries = ["a" * 100, "b" * 100]
    history, capped = l._capped_history(entries, max_history_chars=12000)
    assert capped is False
    assert "earlier observations omitted" not in history


# --- local_task must not surface raw model text or a failed call as status OK ---

def test_local_task_raw_text_flag_returns_error(monkeypatch):
    monkeypatch.setattr(l, "llm_json", lambda *a, **k: {
        "answer": "some raw thought blob", "raw_text": True,
    })

    result = l.local_task("task", max_steps=3)

    assert result["status"] == "ERROR"
    assert "raw_text" in result["answer"]
    assert "some raw thought blob" in result["answer"]


def test_local_task_call_failed_flag_returns_error(monkeypatch):
    monkeypatch.setattr(l, "llm_json", lambda *a, **k: {
        "call_failed": True, "error": "empty model content", "answer": "ERROR: empty model content",
    })

    result = l.local_task("task", max_steps=3)

    assert result["status"] == "ERROR"
    assert "call_failed" in result["answer"]


def test_local_task_well_formed_done_plan_still_ok(monkeypatch):
    monkeypatch.setattr(l, "llm_json", lambda *a, **k: {"done": True, "answer": "final answer"})

    result = l.local_task("task", max_steps=3)

    assert result["status"] == "OK"
    assert result["answer"] == "final answer"


def test_local_task_well_formed_tool_plan_proceeds_to_tool(monkeypatch):
    calls = {"n": 0}

    def fake_llm_json(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"tool": "fake_tool", "args": {}}
        return {"done": True, "answer": "ok"}

    tool_calls = []
    monkeypatch.setattr(l, "llm_json", fake_llm_json)
    monkeypatch.setattr(l, "TOOLS", {"fake_tool": lambda: tool_calls.append(1) or "observed"})

    result = l.local_task("task", max_steps=3)

    assert tool_calls == [1]
    assert result["status"] == "OK"


# --- local_task must return "tool_calls" (name + args, no observation) on every path ---

def test_local_task_tool_calls_recorded_on_ok_path(monkeypatch):
    calls = {"n": 0}

    def fake_llm_json(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"tool": "fake_tool", "args": {"path": "."}}
        return {"done": True, "answer": "ok"}

    monkeypatch.setattr(l, "llm_json", fake_llm_json)
    monkeypatch.setattr(l, "TOOLS", {"fake_tool": lambda **kw: "observed"})

    result = l.local_task("task", max_steps=3)

    assert result["status"] == "OK"
    assert result["tool_calls"] == [{"step": 1, "tool": "fake_tool", "args": {"path": "."}}]


def test_local_task_tool_calls_empty_when_no_tool_called(monkeypatch):
    monkeypatch.setattr(l, "llm_json", lambda *a, **k: {"done": True, "answer": "final"})

    result = l.local_task("task", max_steps=3)

    assert result["status"] == "OK"
    assert result["tool_calls"] == []


def test_local_task_tool_calls_recorded_on_max_steps_path(monkeypatch):
    monkeypatch.setattr(l, "llm_json", lambda *a, **k: {"tool": "fake_tool", "args": {}})
    monkeypatch.setattr(l, "TOOLS", {"fake_tool": lambda **kw: "observed"})

    result = l.local_task("task", max_steps=2)

    assert result["status"] == "MAX_STEPS"
    assert result["tool_calls"] == [
        {"step": 1, "tool": "fake_tool", "args": {}},
        {"step": 2, "tool": "fake_tool", "args": {}},
    ]
