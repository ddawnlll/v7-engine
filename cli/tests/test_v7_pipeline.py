"""Integration tests for cli/v7_pipeline.py — dry-run only, no network.

Tests:
  1. PipelineConfig immutability and validation
  2. Dry-run output covers all steps
  3. Evidence emission is deterministic
  4. Step ordering is correct
  5. --real mode requires explicit flag
  6. PipelineRunner.run() returns valid PipelineResult
  7. CLI argument parsing
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import List

import numpy as np
import pytest

# Add cli to path for import
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ---------------------------------------------------------------------------
# PipelineConfig tests
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    """PipelineConfig validation and defaults."""

    def test_default_config(self):
        """Default config has sensible values."""
        from cli.v7_pipeline import PipelineConfig

        config = PipelineConfig()
        assert config.mode == "SWING"
        assert config.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        assert config.dry_run is True
        assert config.use_synthetic is True
        assert config.n_bars == 2000
        assert config.random_seed == 42
        assert config.force is False
        assert len(config.steps) == 7

    def test_config_to_dict(self):
        """Config serializes correctly."""
        from cli.v7_pipeline import PipelineConfig

        config = PipelineConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            dry_run=True,
        )
        d = config.to_dict()
        assert d["mode"] == "SWING"
        assert d["symbols"] == ["BTCUSDT"]
        assert d["pipeline_version"] == "0.2.0"
        assert d["dry_run"] is True

    def test_config_immutable(self):
        """PipelineConfig is frozen."""
        from cli.v7_pipeline import PipelineConfig

        config = PipelineConfig(mode="SWING")
        with pytest.raises(Exception):
            config.mode = "SCALP"  # type: ignore[misc]

    def test_custom_steps(self):
        """Custom steps override defaults."""
        from cli.v7_pipeline import PipelineConfig

        config = PipelineConfig(steps=("validate", "backfill", "labels"))
        assert config.steps == ("validate", "backfill", "labels")
        assert len(config.steps) == 3

    def test_all_modes_accepted(self):
        """All supported modes are accepted."""
        from cli.v7_pipeline import PipelineConfig, SUPPORTED_MODES

        for mode in SUPPORTED_MODES:
            config = PipelineConfig(mode=mode)
            assert config.mode == mode


# ---------------------------------------------------------------------------
# PipelineEvidence tests
# ---------------------------------------------------------------------------


class TestPipelineEvidence:
    """PipelineEvidence structure and serialization."""

    def test_evidence_creation(self):
        """Evidence is created with correct fields."""
        from cli.v7_pipeline import PipelineEvidence, StepStatus

        ev = PipelineEvidence(
            step="validate",
            status=StepStatus.COMPLETED.value,
        )
        assert ev.step == "validate"
        assert ev.status == "COMPLETED"
        assert ev.checksum == ""  # Not computed until _make_evidence
        assert ev.errors == []
        assert ev.warnings == []
        assert ev.artifacts == []

    def test_evidence_to_dict(self):
        """Evidence serializes to dict correctly."""
        from cli.v7_pipeline import PipelineEvidence, StepStatus

        ev = PipelineEvidence(
            step="backfill",
            status=StepStatus.COMPLETED.value,
            metrics={"total_bars": 6000},
            errors=[],
            warnings=["slow network"],
        )
        d = ev.to_dict()
        assert d["step"] == "backfill"
        assert d["status"] == "COMPLETED"
        assert d["metrics"]["total_bars"] == 6000
        assert d["warnings"] == ["slow network"]
        assert d["errors"] == []

    def test_evidence_json_serializable(self):
        """Evidence dict is JSON serializable."""
        from cli.v7_pipeline import PipelineEvidence, StepStatus

        ev = PipelineEvidence(
            step="train",
            status=StepStatus.COMPLETED.value,
            metrics={"accuracy": 0.42},
        )
        d = ev.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["step"] == "train"
        assert parsed["metrics"]["accuracy"] == 0.42


# ---------------------------------------------------------------------------
# PipelineRunner dry-run tests
# ---------------------------------------------------------------------------


class TestPipelineRunnerDryRun:
    """Dry-run pipeline tests (no network, no ML libraries)."""

    def test_dry_run_produces_evidence_for_all_steps(self, tmp_output_dir):
        """Dry-run produces evidence for all steps."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineRunner,
            PipelineVerdict,
        )

        config = PipelineConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        assert result.verdict == PipelineVerdict.DRY_RUN.value
        assert len(result.evidence) == len(config.steps)
        for ev, step_name in zip(result.evidence, config.steps):
            assert ev.step == step_name
            assert ev.status == "DRY_RUN"

    def test_dry_run_no_execution(self, tmp_output_dir):
        """Dry-run does not execute any real step."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineRunner,
            PipelineVerdict,
        )

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        assert result.verdict == PipelineVerdict.DRY_RUN.value
        # No artifacts should be created in output dir
        # (except possibly the dir itself)
        for ev in result.evidence:
            assert ev.status == "DRY_RUN"
            assert ev.duration_seconds == 0.0

    def test_dry_run_result_serializable(self, tmp_output_dir):
        """Dry-run PipelineResult is JSON serializable."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        d = result.to_dict()
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        assert parsed["verdict"] == "DRY_RUN"
        assert len(parsed["evidence"]) == len(config.steps)
        assert parsed["config"]["mode"] == "SWING"

    def test_dry_run_step_ordering(self, tmp_output_dir):
        """Steps execute in correct pipeline order."""
        from cli.v7_pipeline import (
            PIPELINE_STEPS,
            PipelineConfig,
            PipelineRunner,
        )

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        step_names = [ev.step for ev in result.evidence]
        assert step_names == list(PIPELINE_STEPS)

    def test_custom_steps_subset(self, tmp_output_dir):
        """Custom step subset produces fewer evidence entries."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        custom_steps = ("validate", "backfill", "labels")
        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
            steps=custom_steps,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        assert len(result.evidence) == len(custom_steps)
        step_names = [ev.step for ev in result.evidence]
        assert step_names == list(custom_steps)

    def test_dry_run_evidence_has_checksums(self, tmp_output_dir):
        """Dry-run evidence entries have deterministic checksums."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        for ev in result.evidence:
            assert ev.checksum != ""
            assert len(ev.checksum) == 16  # SHA-256 truncated to 16 chars

    def test_dry_run_deterministic(self, tmp_output_dir):
        """Same config produces same evidence (deterministic checksums)."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,
            output_dir=tmp_output_dir,
        )
        runner1 = PipelineRunner(config)
        result1 = runner1.run()

        runner2 = PipelineRunner(config)
        result2 = runner2.run()

        for ev1, ev2 in zip(result1.evidence, result2.evidence):
            assert ev1.step == ev2.step
            assert ev1.checksum == ev2.checksum
            assert ev1.metrics == ev2.metrics


# ---------------------------------------------------------------------------
# PipelineRunner real mode tests (synthetic data only)
# ---------------------------------------------------------------------------


class TestPipelineRunnerSynthetic:
    """Real execution tests with synthetic data (no network)."""

    def test_real_mode_requires_explicit(self, tmp_output_dir):
        """Pipeline does NOT run real steps unless dry_run=False."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        config = PipelineConfig(
            mode="SWING",
            dry_run=True,   # Explicitly dry-run
            output_dir=tmp_output_dir,
        )
        runner = PipelineRunner(config)
        result = runner.run()

        # All steps should be DRY_RUN
        for ev in result.evidence:
            assert ev.status == "DRY_RUN"

    def test_real_with_synthetic_runs_steps(self, tmp_output_dir):
        """Real mode with synthetic data actually runs pipeline steps."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineRunner,
            PipelineVerdict,
            StepStatus,
        )

        config = PipelineConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            dry_run=False,
            use_synthetic=True,
            n_bars=500,  # Small for fast test
            output_dir=tmp_output_dir,
            random_seed=42,
            steps=("validate", "backfill", "labels", "features"),
        )
        runner = PipelineRunner(config)
        result = runner.run()

        # All steps should complete
        for ev in result.evidence:
            assert ev.status == StepStatus.COMPLETED.value, (
                f"Step {ev.step} failed: {ev.errors}"
            )

        # Validate step metrics
        validate_ev = result.evidence[0]
        assert validate_ev.metrics["mode"] == "SWING"
        assert validate_ev.metrics["use_synthetic"] is True

        # Backfill step metrics
        backfill_ev = result.evidence[1]
        assert backfill_ev.metrics["use_synthetic"] is True
        assert backfill_ev.metrics["data_source"] == "synthetic"
        assert backfill_ev.metrics["total_bars"] == 500

        # Labels step metrics
        labels_ev = result.evidence[2]
        assert labels_ev.metrics["n_labels"] == 500
        assert labels_ev.metrics["label_method"] == "synthetic"

        # Features step metrics
        features_ev = result.evidence[3]
        assert features_ev.metrics["n_features"] > 0
        assert "feature_groups" in features_ev.metrics

    def test_validate_step_catches_invalid_mode(self, tmp_output_dir):
        """Validate step catches unsupported modes."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineRunner,
            StepStatus,
        )

        config = PipelineConfig(
            mode="INVALID_MODE",
            dry_run=False,
            use_synthetic=True,
            output_dir=tmp_output_dir,
            steps=("validate",),
        )
        runner = PipelineRunner(config)
        result = runner.run()

        validate_ev = result.evidence[0]
        assert validate_ev.status == StepStatus.FAILED.value
        assert len(validate_ev.errors) > 0
        assert any("Unsupported mode" in e for e in validate_ev.errors)

    def test_features_depends_on_backfill(self, tmp_output_dir):
        """Features step fails if backfill hasn't run."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineRunner,
            StepStatus,
        )

        config = PipelineConfig(
            mode="SWING",
            dry_run=False,
            use_synthetic=True,
            output_dir=tmp_output_dir,
            steps=("features",),  # Skip backfill and labels
        )
        runner = PipelineRunner(config)
        result = runner.run()

        features_ev = result.evidence[0]
        assert features_ev.status == StepStatus.FAILED.value
        assert any("No OHLCV data" in e for e in features_ev.errors)

    def test_pipeline_result_saved_for_real_mode(self, tmp_output_dir):
        """Real mode pipeline saves its result as JSON."""
        from cli.v7_pipeline import PipelineConfig, PipelineRunner

        config = PipelineConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            dry_run=False,
            use_synthetic=True,
            n_bars=300,
            output_dir=tmp_output_dir,
            random_seed=42,
            steps=("validate", "backfill", "labels", "features"),
        )
        runner = PipelineRunner(config)
        result = runner.run()

        # Check a report was saved
        reports_dir = os.path.join(tmp_output_dir, "reports")
        assert os.path.isdir(reports_dir), f"Reports dir not found: {reports_dir}"

        json_files = [f for f in os.listdir(reports_dir) if f.endswith(".json")]
        assert len(json_files) > 0, f"No JSON reports in {reports_dir}"


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------


class TestCLIArgumentParsing:
    """CLI argument parsing to PipelineConfig."""

    def test_default_args_produce_dry_run_config(self):
        """Default args produce dry-run config."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args(["--mode", "SWING"])
        assert config.mode == "SWING"
        assert config.dry_run is True
        assert config.use_synthetic is True

    def test_real_flag_enables_execution(self):
        """--real flag sets dry_run=False."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args(["--mode", "SWING", "--real"])
        assert config.dry_run is False

    def test_no_synthetic_disables_synthetic(self):
        """--no-synthetic sets use_synthetic=False."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args([
            "--mode", "SWING",
            "--no-synthetic",
            "--start", "2024-01-01",
            "--end", "2024-06-30",
        ])
        assert config.use_synthetic is False

    def test_symbols_parsed_correctly(self):
        """--symbols comma-separated list is parsed."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args(["--mode", "SWING", "--symbols", "BTCUSDT,ETHUSDT"])
        assert config.symbols == ("BTCUSDT", "ETHUSDT")

    def test_steps_parsed_correctly(self):
        """--steps comma-separated list is parsed."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args([
            "--mode", "SWING",
            "--steps", "validate,backfill",
        ])
        assert config.steps == ("validate", "backfill")

    def test_unknown_steps_filtered(self):
        """Unknown steps are filtered out with warning."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args([
            "--mode", "SWING",
            "--steps", "validate,unknown_step,backfill",
        ])
        assert "unknown_step" not in config.steps
        assert "validate" in config.steps
        assert "backfill" in config.steps

    def test_seed_and_n_bars_parsed(self):
        """--seed and --n-bars are parsed as integers."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args([
            "--mode", "SWING",
            "--seed", "123",
            "--n-bars", "500",
        ])
        assert config.random_seed == 123
        assert config.n_bars == 500

    def test_mode_converted_to_uppercase(self):
        """Mode is converted to uppercase."""
        from cli.v7_pipeline import _parse_args

        config = _parse_args(["--mode", "swing"])
        assert config.mode == "SWING"

    def test_mode_must_be_valid(self):
        """Invalid mode raises argparse error."""
        import argparse

        with pytest.raises(SystemExit):
            from cli.v7_pipeline import _parse_args

            _parse_args(["--mode", "INVALID"])


# ---------------------------------------------------------------------------
# Synthetic data tests
# ---------------------------------------------------------------------------


class TestSyntheticData:
    """Tests for synthetic data generation."""

    def test_synthetic_ohlcv_shape(self):
        """Synthetic OHLCV has correct shape."""
        from cli.v7_pipeline import _generate_synthetic_ohlcv

        ohlcv = _generate_synthetic_ohlcv(
            n_bars=100,
            symbols=("BTCUSDT", "ETHUSDT"),
            random_seed=42,
        )

        assert ohlcv["close"].shape == (200,)  # 100 bars * 2 symbols
        assert ohlcv["high"].shape == (200,)
        assert ohlcv["low"].shape == (200,)
        assert ohlcv["open"].shape == (200,)
        assert ohlcv["volume"].shape == (200,)
        assert len(ohlcv["symbol"]) == 200

    def test_synthetic_ohlcv_deterministic(self):
        """Synthetic OHLCV is deterministic for same seed."""
        from cli.v7_pipeline import _generate_synthetic_ohlcv

        ohlcv1 = _generate_synthetic_ohlcv(
            n_bars=100,
            symbols=("BTCUSDT",),
            random_seed=42,
        )
        ohlcv2 = _generate_synthetic_ohlcv(
            n_bars=100,
            symbols=("BTCUSDT",),
            random_seed=42,
        )

        assert np.array_equal(ohlcv1["close"], ohlcv2["close"])
        assert np.array_equal(ohlcv1["high"], ohlcv2["high"])
        assert np.array_equal(ohlcv1["volume"], ohlcv2["volume"])

    def test_synthetic_ohlcv_different_seed_different_data(self):
        """Different seeds produce different OHLCV data."""
        from cli.v7_pipeline import _generate_synthetic_ohlcv

        import numpy as np

        ohlcv1 = _generate_synthetic_ohlcv(
            n_bars=100,
            symbols=("BTCUSDT",),
            random_seed=42,
        )
        ohlcv2 = _generate_synthetic_ohlcv(
            n_bars=100,
            symbols=("BTCUSDT",),
            random_seed=99,
        )

        assert not np.array_equal(ohlcv1["close"], ohlcv2["close"])

    def test_synthetic_labels_shape(self):
        """Synthetic labels have correct shape and values."""
        from cli.v7_pipeline import _generate_synthetic_labels

        labels = _generate_synthetic_labels(n_samples=300, random_seed=42)
        assert labels.shape == (300,)
        unique = set(labels)
        assert unique.issubset({"LONG_NOW", "SHORT_NOW", "NO_TRADE"})

    def test_synthetic_labels_deterministic(self):
        """Synthetic labels are deterministic for same seed."""
        from cli.v7_pipeline import _generate_synthetic_labels

        labels1 = _generate_synthetic_labels(n_samples=300, random_seed=42)
        labels2 = _generate_synthetic_labels(n_samples=300, random_seed=42)

        assert np.array_equal(labels1, labels2)


# ---------------------------------------------------------------------------
# PipelineResult tests
# ---------------------------------------------------------------------------


class TestPipelineResult:
    """PipelineResult serialization and verdict logic."""

    def test_result_to_dict(self, tmp_output_dir):
        """PipelineResult.to_dict() produces valid structure."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineResult,
            PipelineVerdict,
        )

        config = PipelineConfig(mode="SWING")
        result = PipelineResult(
            config=config,
            verdict=PipelineVerdict.DRY_RUN.value,
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:00:01Z",
            total_duration_seconds=1.0,
        )
        d = result.to_dict()
        assert d["pipeline_version"] == "0.2.0"
        assert d["verdict"] == "DRY_RUN"
        assert d["config"]["mode"] == "SWING"
        assert d["evidence"] == []

    def test_result_to_json(self, tmp_output_dir):
        """PipelineResult.to_json() produces valid JSON."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineResult,
            PipelineVerdict,
        )

        config = PipelineConfig(mode="SWING")
        result = PipelineResult(
            config=config,
            verdict=PipelineVerdict.DRY_RUN.value,
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["verdict"] == "DRY_RUN"

    def test_result_with_evidence(self, tmp_output_dir):
        """PipelineResult with evidence includes all steps."""
        from cli.v7_pipeline import (
            PipelineConfig,
            PipelineEvidence,
            PipelineResult,
            PipelineVerdict,
            StepStatus,
        )

        config = PipelineConfig(mode="SWING")
        result = PipelineResult(
            config=config,
            evidence=[
                PipelineEvidence(
                    step="validate",
                    status=StepStatus.COMPLETED.value,
                    metrics={"mode": "SWING"},
                ),
                PipelineEvidence(
                    step="backfill",
                    status=StepStatus.COMPLETED.value,
                    metrics={"total_bars": 6000},
                ),
            ],
            verdict=PipelineVerdict.PASS.value,
        )
        d = result.to_dict()
        assert len(d["evidence"]) == 2
        assert d["evidence"][0]["step"] == "validate"
        assert d["evidence"][0]["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# MakeEvidence helper tests
# ---------------------------------------------------------------------------


class TestMakeEvidence:
    """Tests for _make_evidence helper."""

    def test_make_evidence_computes_checksum(self):
        """_make_evidence computes SHA-256 checksum from metrics."""
        from cli.v7_pipeline import _make_evidence, StepStatus

        ev = _make_evidence(
            "test_step",
            StepStatus.COMPLETED.value,
            metrics={"a": 1, "b": 2},
        )
        assert ev.checksum != ""
        assert len(ev.checksum) == 16

    def test_make_evidence_deterministic(self):
        """Same metrics produce same checksum."""
        from cli.v7_pipeline import _make_evidence, StepStatus

        ev1 = _make_evidence(
            "test_step",
            StepStatus.COMPLETED.value,
            metrics={"a": 1, "b": 2},
        )
        ev2 = _make_evidence(
            "test_step",
            StepStatus.COMPLETED.value,
            metrics={"a": 1, "b": 2},
        )
        assert ev1.checksum == ev2.checksum

    def test_make_evidence_different_metrics_different_checksum(self):
        """Different metrics produce different checksums."""
        from cli.v7_pipeline import _make_evidence, StepStatus

        ev1 = _make_evidence(
            "test_step",
            StepStatus.COMPLETED.value,
            metrics={"a": 1, "b": 2},
        )
        ev2 = _make_evidence(
            "test_step",
            StepStatus.COMPLETED.value,
            metrics={"a": 1, "b": 3},
        )
        assert ev1.checksum != ev2.checksum

    def test_make_evidence_timestamp_set(self):
        """_make_evidence sets UTC timestamp."""
        from cli.v7_pipeline import _make_evidence, StepStatus

        ev = _make_evidence("test_step", StepStatus.COMPLETED.value)
        assert ev.timestamp != ""
        assert "T" in ev.timestamp  # ISO 8601

    def test_dry_run_evidence_all_steps(self):
        """_dry_run_evidence works for all steps."""
        from cli.v7_pipeline import (
            PIPELINE_STEPS,
            PipelineConfig,
            StepStatus,
            _dry_run_evidence,
        )

        config = PipelineConfig(mode="SWING")
        for step in PIPELINE_STEPS:
            ev = _dry_run_evidence(step, config)
            assert ev.step == step
            assert ev.status == StepStatus.DRY_RUN.value
            assert "mode" in ev.metrics
            assert ev.metrics["mode"] == "SWING"
            assert ev.metrics["dry_run"] is True


# ---------------------------------------------------------------------------
# StepStatus and PipelineVerdict enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Enum value tests."""

    def test_step_status_values(self):
        """StepStatus has expected values."""
        from cli.v7_pipeline import StepStatus

        assert StepStatus.PENDING.value == "PENDING"
        assert StepStatus.RUNNING.value == "RUNNING"
        assert StepStatus.COMPLETED.value == "COMPLETED"
        assert StepStatus.FAILED.value == "FAILED"
        assert StepStatus.SKIPPED.value == "SKIPPED"
        assert StepStatus.DRY_RUN.value == "DRY_RUN"

    def test_pipeline_verdict_values(self):
        """PipelineVerdict has expected values."""
        from cli.v7_pipeline import PipelineVerdict

        assert PipelineVerdict.PASS.value == "PASS"
        assert PipelineVerdict.PASS_WITH_WARNINGS.value == "PASS_WITH_WARNINGS"
        assert PipelineVerdict.FAIL.value == "FAIL"
        assert PipelineVerdict.INCONCLUSIVE.value == "INCONCLUSIVE"
        assert PipelineVerdict.DRY_RUN.value == "DRY_RUN"


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Pipeline constants tests."""

    def test_pipeline_steps_order(self):
        """PIPELINE_STEPS has correct order."""
        from cli.v7_pipeline import PIPELINE_STEPS

        assert PIPELINE_STEPS[0] == "validate"
        assert PIPELINE_STEPS[1] == "backfill"
        assert PIPELINE_STEPS[2] == "labels"
        assert PIPELINE_STEPS[3] == "features"
        assert PIPELINE_STEPS[4] == "train"
        assert PIPELINE_STEPS[5] == "wfv"
        assert PIPELINE_STEPS[6] == "report"

    def test_supported_modes(self):
        """SUPPORTED_MODES includes all three modes."""
        from cli.v7_pipeline import SUPPORTED_MODES

        assert "SWING" in SUPPORTED_MODES
        assert "SCALP" in SUPPORTED_MODES
        assert "AGGRESSIVE_SCALP" in SUPPORTED_MODES
        assert len(SUPPORTED_MODES) == 3

    def test_label_mapping(self):
        """Label-to-int mapping is correct."""
        from cli.v7_pipeline import (
            _LABEL_TO_INT,
            _INT_TO_LABEL,
            _NUM_CLASSES,
        )

        assert _LABEL_TO_INT["LONG_NOW"] == 0
        assert _LABEL_TO_INT["SHORT_NOW"] == 1
        assert _LABEL_TO_INT["NO_TRADE"] == 2
        assert _INT_TO_LABEL[0] == "LONG_NOW"
        assert _INT_TO_LABEL[1] == "SHORT_NOW"
        assert _INT_TO_LABEL[2] == "NO_TRADE"
        assert _NUM_CLASSES == 3
