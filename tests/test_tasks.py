"""Tests for eval/tasks.py's chain_altnames variant: the rename must remove
every _orig/_original identifier, be deterministic, leave valid Python
behind, and never touch the frozen FIXTURE. setup_chain_altnames() creates
its sandbox under config.ROOT (home directory), same as a real eval run, so
tests clean it up explicitly rather than relying on tmp_path.
"""
import ast
import shutil

from eval import tasks as ev


def test_setup_chain_altnames_removes_all_orig_identifiers():
    sandbox = ev.setup_chain_altnames()
    try:
        text = (sandbox / "research.py").read_text()
        assert not ev._ORIG_NAME_RE.findall(text)
        ast.parse(text)  # still valid Python after the rename
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def test_setup_chain_altnames_is_deterministic():
    sandbox_a = ev.setup_chain_altnames()
    sandbox_b = ev.setup_chain_altnames()
    try:
        text_a = (sandbox_a / "research.py").read_text()
        text_b = (sandbox_b / "research.py").read_text()
        assert text_a == text_b
    finally:
        shutil.rmtree(sandbox_a, ignore_errors=True)
        shutil.rmtree(sandbox_b, ignore_errors=True)


def test_setup_chain_altnames_applies_expected_renames():
    sandbox = ev.setup_chain_altnames()
    try:
        text = (sandbox / "research.py").read_text()
        assert "prev_result_score" in text
        assert "prev_format_evidence" in text
        assert "old_bep_cap" in text
        assert "old_bep_quote" in text
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def test_setup_chain_altnames_does_not_modify_fixture():
    fixture_before = ev.FIXTURE.read_bytes()
    sandbox = ev.setup_chain_altnames()
    try:
        fixture_after = ev.FIXTURE.read_bytes()
        assert fixture_before == fixture_after
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
