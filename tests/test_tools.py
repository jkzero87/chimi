"""Tests for agent/tools.py. No running llama-server required. Every test's
ROOT is monkeypatched to pytest's tmp_path, so nothing is written outside it.
"""
import pytest

from agent import tools as t


@pytest.fixture(autouse=True)
def sandbox_root(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "ROOT", tmp_path)
    monkeypatch.setattr(t, "MAX_CHARS", 4000)
    monkeypatch.setattr(t, "GREP_MAX_MATCHES", 200)
    monkeypatch.setattr(t, "DELETE_REVIEW_MAX_LINES", 50)


# --- security: run_safe_bash ---

def test_ls_allowed():
    result = t.run_safe_bash("ls")
    assert result.startswith("exit=0")


def test_semicolon_separator_rejected():
    result = t.run_safe_bash("ls; echo PWNED")
    assert result.startswith("RECHAZADO")


def test_and_rm_rejected():
    result = t.run_safe_bash("ls && rm -rf /tmp/x")
    assert result.startswith("RECHAZADO")


def test_redirection_rejected():
    result = t.run_safe_bash("cat foo > bar")
    assert result.startswith("RECHAZADO")


def test_substitution_rejected():
    result = t.run_safe_bash("echo $(whoami)")
    assert result.startswith("RECHAZADO")


def test_pipe_of_two_safe_commands_allowed(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    result = t.run_safe_bash("find . -name '*.py' | head -3")
    assert not result.startswith("RECHAZADO")
    assert result.startswith("exit=")


# --- sandbox: _safe ---

def test_safe_outside_root_raises():
    with pytest.raises(ValueError, match="fuera del sandbox"):
        t._safe("/")


def test_safe_nonexistent_raises_and_mentions_root(tmp_path):
    with pytest.raises(ValueError) as exc:
        t._safe("no_existo_123.txt")
    assert str(tmp_path) in str(exc.value)


# --- tool contracts ---

def test_read_file_line_range(tmp_path):
    (tmp_path / "sample.txt").write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n")
    result = t.read_file("sample.txt", start_line=3, end_line=5)
    assert result == "3: line3\n4: line4\n5: line5"


def test_read_file_truncation_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "MAX_CHARS", 50)
    (tmp_path / "big.txt").write_text("x" * 500)
    result = t.read_file("big.txt")
    assert result.endswith("\n[TRUNCADO en 4000 chars. Usa start_line y end_line para leer un rango]")
    assert len(result.split("\n[TRUNCADO")[0]) == 50


def test_grep_files_truncation_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "GREP_MAX_MATCHES", 3)
    (tmp_path / "many.txt").write_text("\n".join(f"needle {i}" for i in range(10)) + "\n")
    result = t.grep_files("needle", ".")
    assert result.endswith("\n[RESULTADO TRUNCADO: puede haber mas coincidencias]")


# --- write_file ---

def test_write_file_dry_run_does_not_create(tmp_path):
    result = t.write_file("new.txt", "hello\n", dry_run=True)
    assert not (tmp_path / "new.txt").exists()
    assert "hello" in result


def test_write_file_dry_run_false_creates_and_backs_up(tmp_path):
    existing = tmp_path / "existing.txt"
    existing.write_text("old\n")
    result = t.write_file("existing.txt", "new\n", dry_run=False)
    assert existing.read_text() == "new\n"
    backups = list(tmp_path.glob("existing.txt.bak_*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "old\n"
    assert "[backup:" in result


def test_write_file_refuses_invalid_python(tmp_path):
    result = t.write_file("bad.py", "def broken(:\n", dry_run=False)
    assert result.startswith("RECHAZADO")
    assert not (tmp_path / "bad.py").exists()


def test_write_file_outside_root_raises():
    with pytest.raises(ValueError, match="fuera del sandbox"):
        t.write_file("/etc/pwned.txt", "x", dry_run=True)


# --- delete_lines ---

def test_delete_lines_dry_run_does_not_modify(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("a\nb\nc\nd\n")
    result = t.delete_lines("sample.txt", 2, 3, dry_run=True)
    assert f.read_text() == "a\nb\nc\nd\n"
    assert "b" in result


def test_delete_lines_out_of_range_names_line_count(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("a\nb\nc\n")
    n = len(f.read_text().split("\n"))
    result = t.delete_lines("sample.txt", 1, 99, dry_run=True)
    assert result.startswith("RECHAZADO")
    assert str(n) in result


def test_delete_lines_refuses_invalid_python_result(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def foo():\n    return 1\n")
    result = t.delete_lines("bad.py", 2, 2, dry_run=False)
    assert result.startswith("RECHAZADO")
    assert f.read_text() == "def foo():\n    return 1\n"


def test_delete_lines_dry_run_false_removes_range_and_backs_up(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("a\nb\nc\nd\n")
    t.delete_lines("sample.txt", 2, 3, dry_run=False)
    assert f.read_text() == "a\nd\n"
    backups = list(tmp_path.glob("sample.txt.bak_*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "a\nb\nc\nd\n"


# --- delete_lines: escalation policy (backlog item 5) ---

def test_delete_lines_clean_single_function_still_applies(tmp_path):
    f = tmp_path / "clean.py"
    f.write_text("def foo():\n    return 1\nx = 2\n")
    result = t.delete_lines("clean.py", 1, 2, dry_run=False)
    assert not result.startswith("RECHAZADO")
    assert f.read_text() == "x = 2\n"
    assert list(tmp_path.glob("clean.py.bak_*"))


def test_delete_lines_range_spanning_def_and_assignment_refused(tmp_path):
    f = tmp_path / "spans.py"
    original = "def foo():\n    return 1\nx = 2\n"
    f.write_text(original)
    result = t.delete_lines("spans.py", 1, 3, dry_run=False)
    assert result.startswith("RECHAZADO")
    assert f.read_text() == original
    assert not list(tmp_path.glob("spans.py.bak_*"))


def test_delete_lines_partial_function_coverage_refused(tmp_path):
    f = tmp_path / "partial.py"
    original = "def foo():\n    a = 1\n    b = 2\n    return a + b\n"
    f.write_text(original)
    result = t.delete_lines("partial.py", 2, 3, dry_run=False)
    assert result.startswith("RECHAZADO")
    assert f.read_text() == original
    assert not list(tmp_path.glob("partial.py.bak_*"))


def test_delete_lines_oversized_but_structurally_clean_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DELETE_REVIEW_MAX_LINES", 3)
    f = tmp_path / "big.py"
    original = "def foo():\n    a = 1\n    b = 2\n    return a + b\n"
    f.write_text(original)
    result = t.delete_lines("big.py", 1, 4, dry_run=False)
    assert result.startswith("RECHAZADO")
    assert f.read_text() == original
    assert not list(tmp_path.glob("big.py.bak_*"))


def test_delete_lines_override_allows_refused_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DELETE_REVIEW_MAX_LINES", 3)
    f = tmp_path / "big.py"
    f.write_text("def foo():\n    a = 1\n    b = 2\n    return a + b\n")
    result = t.delete_lines("big.py", 1, 4, dry_run=False, override=True)
    assert not result.startswith("RECHAZADO")
    assert f.read_text() == ""
    assert list(tmp_path.glob("big.py.bak_*"))


def test_delete_lines_oversized_non_python_file_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DELETE_REVIEW_MAX_LINES", 3)
    f = tmp_path / "big.txt"
    original = "a\nb\nc\nd\ne\n"
    f.write_text(original)
    result = t.delete_lines("big.txt", 1, 4, dry_run=False)
    assert result.startswith("RECHAZADO")
    assert f.read_text() == original
    assert not list(tmp_path.glob("big.txt.bak_*"))


def test_delete_lines_dry_run_unaffected_by_escalation_policy(tmp_path):
    f = tmp_path / "spans.py"
    original = "def foo():\n    return 1\nx = 2\n"
    f.write_text(original)
    result = t.delete_lines("spans.py", 1, 3, dry_run=True)
    assert not result.startswith("RECHAZADO")
    assert f.read_text() == original


def test_delete_lines_override_not_exposed_to_model():
    assert "override" not in t.SYSTEM
    assert "delete_lines(path, start_line, end_line, dry_run)" in t.SYSTEM


# --- check_syntax ---

def test_check_syntax_valid(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\ny = 2\n")
    result = t.check_syntax("ok.py")
    assert result.startswith("OK")


def test_check_syntax_invalid_reports_line(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n")
    result = t.check_syntax("bad.py")
    assert "line 1" in result


def test_check_syntax_non_python_refused(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    result = t.check_syntax("notes.txt")
    assert "not a .py file" in result


# --- function_ranges ---

_FUNCTION_RANGES_FIXTURE = "\n".join([
    "def thing():",              # 1
    "    return 1",              # 2
    "",                          # 3
    "",                          # 4
    "@decorator",                # 5
    "def thing():",              # 6
    "    return 2",              # 7
    "",                          # 8
    "",                          # 9
    "_orig_thing = thing",       # 10
    "",                          # 11
    "",                          # 12
    "def thing():",              # 13
    "    return _orig_thing() + 1",  # 14
    "",                          # 15
    "",                          # 16
    "class Foo:",                # 17
    "    def thing(self):",      # 18
    "        return 99",         # 19
    "",                          # 20
    "",                          # 21
    "def outer():",              # 22
    "    def thing():",          # 23
    "        return 100",        # 24
    "    return thing",          # 25
]) + "\n"


def _entry_line(result, range_marker):
    for line in result.splitlines():
        if range_marker in line:
            return line
    raise AssertionError(f"no line containing {range_marker!r} in:\n{result}")


def test_function_ranges_three_definitions_in_file_order(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")

    first = _entry_line(result, "1-2")
    second = _entry_line(result, "5-7")
    third = _entry_line(result, "13-14")

    assert result.index(first) < result.index(second) < result.index(third)


def test_function_ranges_only_last_is_live(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")

    assert "live=False" in _entry_line(result, "1-2")
    assert "live=False" in _entry_line(result, "5-7")
    assert "live=True" in _entry_line(result, "13-14")


def test_function_ranges_decorated_start_is_decorator_line(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")
    # decorator is on line 5, def on line 6 -- start_line must be 5, not 6
    assert "5-7" in result
    assert "6-7" not in result


def test_function_ranges_calls_orig(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")

    assert "_orig_thing" in _entry_line(result, "13-14")
    assert "_orig_thing" not in _entry_line(result, "1-2")
    assert "_orig_thing" not in _entry_line(result, "5-7")


def test_function_ranges_orig_assignment_line(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")
    assert "line 10" in result
    assert "_orig_thing = thing" in result


def test_function_ranges_ignores_nested_definitions(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "thing")
    # class Foo's thing (18-19) and outer()'s nested thing (23-24) are not module-level
    assert "18-19" not in result
    assert "23-24" not in result
    assert result.count("live=") == 3


def test_function_ranges_no_such_name(tmp_path):
    (tmp_path / "fixture.py").write_text(_FUNCTION_RANGES_FIXTURE)
    result = t.function_ranges("fixture.py", "nonexistent")
    assert "no module-level definition" in result


# --- allowlist: cp, diff added; interpreters still rejected ---

def test_cp_allowed(tmp_path):
    (tmp_path / "a.txt").write_text("hi\n")
    result = t.run_safe_bash("cp a.txt b.txt")
    assert not result.startswith("RECHAZADO")
    assert (tmp_path / "b.txt").read_text() == "hi\n"


def test_diff_allowed(tmp_path):
    (tmp_path / "a.txt").write_text("hi\n")
    (tmp_path / "b.txt").write_text("hi\n")
    result = t.run_safe_bash("diff a.txt b.txt")
    assert not result.startswith("RECHAZADO")


def test_python3_still_rejected():
    result = t.run_safe_bash("python3 -c 'x'")
    assert result.startswith("RECHAZADO")
