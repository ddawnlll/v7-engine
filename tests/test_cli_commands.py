"""
CLI command tests — verify help output, dry-run behavior, and gates.

All tests execute the CLI package directly via `python3 -m cli` with
PYTHONPATH set so the `cli` package is discoverable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CLI_CMD = [sys.executable, "-m", "cli"]
CLI_ENV = {**os.environ, "PYTHONPATH": "alphaforge/src:.", "PYTHONDONTWRITEBYTECODE": "1"}


def _run_cli(*args: str) -> subprocess.CompletedProcessor:
    """Run the CLI with the given arguments and return the CompletedProcess."""
    return subprocess.run(
        [*CLI_CMD, *args],
        capture_output=True,
        text=True,
        env=CLI_ENV,
        cwd=REPO_ROOT,
    )


# ── Help output ──────────────────────────────────────────────────


def test_cli_help_top_level() -> None:
    """`python3 -m cli --help` lists all expected commands."""
    result = _run_cli("--help")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    expected = ["backfill", "simulate", "build-dataset", "train", "wfv",
                "report", "pipeline", "validate", "help"]
    for cmd in expected:
        assert cmd in result.stdout, f"Missing command '{cmd}' in --help output"


def test_cli_help_subcommand() -> None:
    """`python3 -m cli help` produces usage text."""
    result = _run_cli("help")
    assert result.returncode == 0
    # Should contain usage information
    assert "usage:" in result.stdout or "V7 Engine" in result.stdout or "backfill" in result.stdout


# ── Dry-run mode ─────────────────────────────────────────────────


def test_cli_validate_dry_run() -> None:
    """validate --dry-run prints DRY RUN lines."""
    result = _run_cli("validate", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


def test_cli_backfill_dry_run() -> None:
    """backfill --dry-run with all options prints expected values."""
    result = _run_cli(
        "backfill",
        "--dry-run",
        "--symbols", "BTCUSDT",
        "--intervals", "4h",
        "--start", "2024-01-01",
        "--end", "2024-01-02",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout
    assert "BTCUSDT" in result.stdout
    assert "4h" in result.stdout
    assert "2024-01-01" in result.stdout
    assert "2024-01-02" in result.stdout


def test_cli_simulate_dry_run() -> None:
    """simulate --dry-run prints mode and symbols."""
    result = _run_cli("simulate", "--dry-run", "--mode", "SWING", "--symbols", "BTCUSDT")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout
    assert "SWING" in result.stdout


def test_cli_build_dataset_dry_run() -> None:
    """build-dataset --dry-run prints DRY RUN."""
    result = _run_cli("build-dataset", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


def test_cli_report_dry_run() -> None:
    """report --dry-run prints DRY RUN."""
    result = _run_cli("report", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


# ── Gates ─────────────────────────────────────────────────────────


def test_cli_train_dry_run_gated() -> None:
    """train --dry-run prints GATE message (not authorized)."""
    result = _run_cli("train", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "GATE" in result.stdout or "not yet authorized" in result.stdout


def test_cli_train_real_mode_gated() -> None:
    """train without --dry-run and without --force exits 1."""
    result = _run_cli("train")
    assert result.returncode == 1
    assert "GATE" in result.stdout or "not yet authorized" in result.stdout


def test_cli_train_dry_run_force() -> None:
    """train --dry-run --force bypasses gate."""
    result = _run_cli("train", "--dry-run", "--force")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


def test_cli_wfv_dry_run_gated() -> None:
    """wfv --dry-run prints GATE message."""
    result = _run_cli("wfv", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "GATE" in result.stdout or "requires trained model" in result.stdout


def test_cli_wfv_real_mode_gated() -> None:
    """wfv without --dry-run exits 1."""
    result = _run_cli("wfv")
    assert result.returncode == 1
    assert "GATE" in result.stdout or "requires trained model" in result.stdout


# ── Error paths ───────────────────────────────────────────────────


def test_cli_backfill_bad_date() -> None:
    """backfill with malformed date should still produce usable error."""
    result = _run_cli("backfill", "--dry-run", "--start", "not-a-date")
    # The CLI parses the date and may fail or proceed with dry-run
    assert result.returncode == 0 or "error" in result.stderr.lower() or "usage" in result.stderr.lower()


def test_cli_backfill_unknown_symbols() -> None:
    """backfill --dry-run with weird symbols still runs (dry-run skips actual download)."""
    result = _run_cli("backfill", "--dry-run", "--symbols", "NONEXISTENT")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


def test_cli_simulate_missing_flag_defaults() -> None:
    """simulate --dry-run without --mode or --symbols uses defaults."""
    result = _run_cli("simulate", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout


def test_cli_train_bad_force_usage() -> None:
    """train without --force exits non-zero in real mode."""
    result = _run_cli("train")
    assert result.returncode != 0
    assert "GATE" in result.stdout or "not authorized" in result.stdout


def test_cli_report_with_mode_flag() -> None:
    """report --dry-run --mode SWING works."""
    result = _run_cli("report", "--dry-run", "--mode", "SWING")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY RUN" in result.stdout
    assert "SWING" in result.stdout


def test_cli_unknown_command() -> None:
    """An unknown subcommand should exit 1."""
    result = _run_cli("nonexistent-command")
    assert result.returncode != 0


def test_cli_empty_args() -> None:
    """No args should print help and exit 0."""
    result = _run_cli()
    assert result.returncode == 0


# ── Pipeline dry-run ──────────────────────────────────────────────


def test_cli_pipeline_dry_run() -> None:
    """pipeline --dry-run walks through all steps."""
    result = _run_cli("pipeline", "--dry-run")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Every step should appear
    for step in ["validate", "backfill", "simulate", "build-dataset",
                 "train", "wfv", "report"]:
        assert step in result.stdout.lower() or step in result.stdout.lower()
