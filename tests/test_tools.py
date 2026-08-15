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
