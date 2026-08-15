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
