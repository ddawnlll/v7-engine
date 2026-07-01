"""Tests for the `tune` subcommand in cli/v7_engine.py.

Covers:
  1. CLI argument parsing for tune subcommand
  2. Dry-run mode
  3. _build_tune_comparison function
  4. _print_tune_report smoke test
  5. _save_tune_report writes JSON
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _make_mock_result(
    verdict: str = "INCONCLUSIVE",
    step_statuses: dict[str, str] | None = None,
) -> Any:
    """Build a minimal PipelineResult-like object for testing."""
    from cli.v7_pipeline import StepStatus

    statuses = step_statuses or {}

    class _MockPipelineResult:
        def __init__(self):
            self.verdict = verdict
            self.evidence = []

            for step in ["validate", "backfill", "labels", "features", "train", "wfv", "report"]:
                s = statuses.get(step, StepStatus.COMPLETED.value)
                self.evidence.append(self._make_ev(step, s))

        @staticmethod
        def _make_ev(step: str, status: str) -> Any:
            from cli.v7_pipeline import PipelineEvidence

            metrics = {}
            if step == "train":
                metrics = {"train_accuracy": 0.85, "val_accuracy": 0.72}
            elif step == "wfv":
                metrics = {"verdict": "PASS", "avg_sharpe": 0.45, "n_folds": 6}
            elif step == "backfill":
                metrics = {"total_bars": 6000, "data_source": "synthetic", "n_symbols": 3}

            return PipelineEvidence(
                step=step,
                status=status,
                metrics=metrics,
                errors=[] if status != "FAILED" else [f"{step} error"],
                warnings=[],
                duration_seconds=0.5,
            )

    return _MockPipelineResult()


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------


class TestTuneCLI:
    """Argument parsing for the `tune` subcommand."""

    def test_default_args(self):
        """Default tune args produce sensible defaults."""
        from cli.v7_engine import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["tune"])
        assert args.command == "tune"
        assert args.mode == "SWING"
        assert args.real is False
        assert args.symbols is None
        assert args.seed == 42
        assert args.n_bars == 2000
        assert args.force is False
        assert args.dry_run is False

    def test_custom_args(self):
        """Custom args are parsed correctly."""
        from cli.v7_engine import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "tune", "--mode", "SCALP", "--real",
            "--symbols", "BTCUSDT,ETHUSDT",
            "--seed", "99", "--n-bars", "500",
            "--data-dir", "/tmp/tune-output",
            "--force",
        ])
        assert args.command == "tune"
        assert args.mode == "SCALP"
        assert args.real is True
        assert args.symbols == "BTCUSDT,ETHUSDT"
        assert args.seed == 99
        assert args.n_bars == 500
        assert args.data_dir == "/tmp/tune-output"
        assert args.force is True

    def test_dry_run_flag(self):
        """--dry-run is accepted on the tune subcommand."""
        from cli.v7_engine import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["tune", "--mode", "SWING", "--dry-run"])
        assert args.dry_run is True

    def test_tune_shows_in_help(self):
        """Tune subcommand appears in help output."""
        from cli.v7_engine import _build_parser

        parser = _build_parser()
        help_text = parser.format_help()
        assert "tune" in help_text
        assert "synthetic baseline" in help_text


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


class TestTuneDryRun:
    """Tune subcommand dry-run behavior."""

    def test_dry_run_returns_zero(self):
        """Dry-run returns 0 and doesn't crash."""
        from cli.v7_engine import main

        ret = main(["tune", "--mode", "SWING", "--dry-run"])
        assert ret == 0

    def test_dry_run_with_real(self):
        """Dry-run with --real doesn't crash."""
        from cli.v7_engine import main

        ret = main(["tune", "--mode", "SWING", "--real", "--dry-run"])
        assert ret == 0


# ---------------------------------------------------------------------------
# _build_tune_comparison tests
# ---------------------------------------------------------------------------


class TestBuildTuneComparison:
    """Tests for _build_tune_comparison."""

    def test_synthetic_only(self):
        """Synthetic-only comparison builds correct structure."""
        from cli.v7_engine import _build_tune_comparison

        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))

        assert comp["tune_report_version"] == "0.1.0"
        assert comp["config"]["mode"] == "SWING"
        assert comp["config"]["symbols"] == ["BTCUSDT"]
        assert comp["synthetic"]["verdict"] == "PASS"
        assert "real" not in comp
        assert "metrics" in comp
        assert comp["metrics"]["synthetic_train_accuracy"] == 0.85
        assert comp["metrics"]["synthetic_wfv_verdict"] == "PASS"

    def test_synthetic_and_real(self):
        """Synthetic + real comparison includes both sections."""
        from cli.v7_engine import _build_tune_comparison

        syn = _make_mock_result(verdict="PASS")
        real = _make_mock_result(verdict="PASS_WITH_WARNINGS")
        comp = _build_tune_comparison(syn, real, "SWING", ("BTCUSDT", "ETHUSDT"))

        assert "synthetic" in comp
        assert "real" in comp
        assert comp["synthetic"]["verdict"] == "PASS"
        assert comp["real"]["verdict"] == "PASS_WITH_WARNINGS"
        assert comp["metrics"]["real_train_accuracy"] == 0.85
        assert comp["metrics"]["real_wfv_verdict"] == "PASS"

    def test_metrics_extracted_per_step(self):
        """Each step's metrics are extracted into the comparison."""
        from cli.v7_engine import _build_tune_comparison

        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))

        for step in ["validate", "backfill", "labels", "features", "train", "wfv", "report"]:
            assert step in comp["synthetic"]["steps"], f"Missing step: {step}"
            assert "status" in comp["synthetic"]["steps"][step]
            assert "metrics" in comp["synthetic"]["steps"][step]

    def test_failed_steps_record_errors(self):
        """Failed steps have errors captured in comparison."""
        from cli.v7_engine import _build_tune_comparison

        syn = _make_mock_result(
            verdict="FAIL",
            step_statuses={"train": "FAILED"},
        )
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))

        train_info = comp["synthetic"]["steps"]["train"]
        assert train_info["status"] == "FAILED"
        assert len(train_info["errors"]) > 0


# ---------------------------------------------------------------------------
# _print_tune_report smoke test
# ---------------------------------------------------------------------------


class TestPrintTuneReport:
    """Smoke tests for _print_tune_report (no crash)."""

    def test_print_synthetic_only(self, capsys):
        """Printing synthetic-only report doesn't crash."""
        from cli.v7_engine import _build_tune_comparison, _print_tune_report

        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))
        _print_tune_report(comp)

        captured = capsys.readouterr()
        assert "Synthetic Verdict" in captured.out
        assert "backfill" in captured.out

    def test_print_synthetic_and_real(self, capsys):
        """Printing synthetic+real report doesn't crash."""
        from cli.v7_engine import _build_tune_comparison, _print_tune_report

        syn = _make_mock_result(verdict="PASS")
        real = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, real, "SWING", ("BTCUSDT",))
        _print_tune_report(comp)

        captured = capsys.readouterr()
        assert "Real Verdict" in captured.out
        assert "Accuracy Comparison" in captured.out


# ---------------------------------------------------------------------------
# _save_tune_report tests
# ---------------------------------------------------------------------------


class TestSaveTuneReport:
    """Tests for _save_tune_report."""

    def test_saves_json(self, tmp_dir):
        """Report is saved as valid JSON."""
        from cli.v7_engine import _build_tune_comparison, _save_tune_report

        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))
        path = _save_tune_report(comp, tmp_dir, "SWING")

        assert os.path.isfile(path)
        assert path.endswith(".json")

        with open(path) as f:
            data = json.load(f)

        assert data["tune_report_version"] == "0.1.0"
        assert data["config"]["mode"] == "SWING"

    def test_filename_contains_mode_and_timestamp(self, tmp_dir):
        """Filename includes mode and timestamp."""
        from cli.v7_engine import _build_tune_comparison, _save_tune_report

        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))
        path = _save_tune_report(comp, tmp_dir, "SWING")

        basename = os.path.basename(path)
        assert "tune_comparison" in basename
        assert "swing" in basename
        assert basename.endswith(".json")

    def test_report_dir_created(self, tmp_dir):
        """Report directory is created if it doesn't exist."""
        from cli.v7_engine import _build_tune_comparison, _save_tune_report

        nested = os.path.join(tmp_dir, "deep", "nested")
        syn = _make_mock_result(verdict="PASS")
        comp = _build_tune_comparison(syn, None, "SWING", ("BTCUSDT",))
        path = _save_tune_report(comp, nested, "SWING")

        assert os.path.isfile(path)
        assert os.path.isdir(os.path.join(nested, "reports"))
