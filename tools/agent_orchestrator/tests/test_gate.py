"""Tests for gate.py -- deterministic gate checks."""

import gate
from gate import GateConfig, run_gate


def test_all_pass(tmp_path):
    """All conditions met -> GateResult.verdict == PASS."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("worker log content")
    (tmp_path / "output.txt").write_text("test output")

    config = GateConfig(required_files=["output.txt"])
    result = run_gate(config, exit_code=0, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "PASS"


def test_fail_exit_code(tmp_path):
    """Non-zero exit code causes gate FAIL."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("worker log content")

    config = GateConfig()
    result = run_gate(config, exit_code=1, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "FAIL"
    assert result.check_results["exit_code_ok"] is False


def test_disabled_checks_skipped(tmp_path):
    """All checks disabled (empty config) -> PASS (no checks applied, none failed)."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("worker log content")

    config = GateConfig()
    result = run_gate(config, exit_code=0, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "PASS"


def test_report_fields_found(tmp_path):
    """Worker summary contains required fields -> field check passes."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("log")

    config = GateConfig(check_report_fields=True, report_required_fields=["train_start", "metric"])
    result = run_gate(
        config,
        exit_code=0,
        worker_log_path=str(log_file),
        repo_root=str(tmp_path),
        worker_summary="train_start: 2024-01-01, metric: 0.05, test_start: 2024-06-01",
    )

    assert result.verdict == "PASS"
    assert result.check_results["report_fields_ok"] is True


def test_report_fields_missing(tmp_path):
    """Summary missing required fields -> detected."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("log")

    config = GateConfig(check_report_fields=True, report_required_fields=["train_start", "n_combinations"])
    result = run_gate(
        config,
        exit_code=0,
        worker_log_path=str(log_file),
        repo_root=str(tmp_path),
        worker_summary="train_start: 2024-01-01",
    )

    assert result.verdict == "FAIL"
    assert result.check_results["report_fields_ok"] is False


def test_allowed_prefixes_valid(tmp_path, monkeypatch):
    """Porcelain lines within prefixes -> no violations."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("log")

    monkeypatch.setattr(gate, "_run_git_porcelain", lambda r: [" M candidates/alpha.py", "?? candidates/test.py"])
    monkeypatch.setattr(gate, "_run_git_diff", lambda r: "")

    config = GateConfig(check_git_clean=True, git_allowed_prefixes=["candidates/"])
    result = run_gate(config, exit_code=0, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "PASS"
    assert result.check_results["git_changes_in_allowed_paths"] is True


def test_allowed_prefixes_invalid(tmp_path, monkeypatch):
    """Porcelain lines outside prefixes -> violations detected."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("log")

    monkeypatch.setattr(gate, "_run_git_porcelain", lambda r: [" M src/main.py", "?? candidates/alpha.py"])
    monkeypatch.setattr(gate, "_run_git_diff", lambda r: "some diff")

    config = GateConfig(check_git_clean=True, git_allowed_prefixes=["candidates/"])
    result = run_gate(config, exit_code=0, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "FAIL"
    assert result.check_results["git_changes_in_allowed_paths"] is False


def test_denied_paths(tmp_path, monkeypatch):
    """Denied path prefix touched -> violation detected."""
    log_file = tmp_path / "claude_stream.jsonl"
    log_file.write_text("log")

    monkeypatch.setattr(gate, "_run_git_porcelain", lambda r: [" M v7/evaluation.py", "?? candidates/test.py"])

    config = GateConfig(git_denied_paths=["v7/evaluation.py"])
    result = run_gate(config, exit_code=0, worker_log_path=str(log_file), repo_root=str(tmp_path))

    assert result.verdict == "FAIL"
    assert result.check_results["git_no_denied_touches"] is False
