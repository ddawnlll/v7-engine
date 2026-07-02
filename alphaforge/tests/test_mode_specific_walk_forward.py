"""Tests for mode-specific walk-forward validation (Issue #143).

Tests that run_walk_forward() works correctly with SCALP and AGGRESSIVE_SCALP
modes, using mode-specific hyperparameters, annualization factors, and configs.

All tests are deterministic (same seed = same output). These tests IMPORT
xgboost and numpy (training environment).
"""
from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import math

import numpy as np
import pytest

from alphaforge.validation.walk_forward_runner import (
    MODE_ANNUALIZATION,
    MODE_RUNNER_PURGE_BARS,
    MODE_RUNNER_EMBARGO_BARS,
    WalkForwardResult,
    compute_all_metrics,
    run_walk_forward,
)


# =========================================================================
# Mode-specific annualization factors
# =========================================================================


class TestModeAnnualizationFactors:
    """Mode-specific annualization factors for Sharpe computation."""

    def test_swing_factor(self):
        """SWING 4h: 365 * 6 = 2190 bars/year."""
        assert MODE_ANNUALIZATION["SWING"] == 2190.0

    def test_scalp_factor(self):
        """SCALP 1h: 365 * 24 = 8760 bars/year."""
        assert MODE_ANNUALIZATION["SCALP"] == 8760.0

    def test_aggressive_scalp_factor(self):
        """AGGRESSIVE_SCALP 15m: 365 * 96 = 35040 bars/year."""
        assert MODE_ANNUALIZATION["AGGRESSIVE_SCALP"] == 35040.0


class TestModeRunnerPurgeEmbargo:
    """Mode-specific purge and embargo bars."""

    def test_swing_purge(self):
        assert MODE_RUNNER_PURGE_BARS["SWING"] == 20

    def test_scalp_purge(self):
        assert MODE_RUNNER_PURGE_BARS["SCALP"] == 100

    def test_aggressive_scalp_purge(self):
        assert MODE_RUNNER_PURGE_BARS["AGGRESSIVE_SCALP"] == 200

    def test_embargo_match_purge(self):
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            assert MODE_RUNNER_EMBARGO_BARS[mode] == MODE_RUNNER_PURGE_BARS[mode]


# =========================================================================
# Mode-specific walk-forward runs
# =========================================================================


class TestScalpWalkForward:
    """SCALP mode walk-forward validation."""

    @pytest.fixture
    def result(self) -> WalkForwardResult:
        return run_walk_forward(
            n_bars=400,
            n_symbols=3,
            random_seed=42,
            train_window_bars=300,
            test_window_bars=150,
            min_folds=3,
            mode="SCALP",
        )

    def test_runs_without_error(self, result):
        assert result is not None
        assert isinstance(result, WalkForwardResult)

    def test_min_folds_met(self, result):
        assert len(result.folds) >= 2

    def test_each_fold_valid_metrics(self, result):
        for fm in result.folds:
            assert 0.0 <= fm.train_accuracy <= 1.0
            assert 0.0 <= fm.val_accuracy <= 1.0
            assert fm.total_trades >= 0

    def test_report_id_contains_scalp(self, result):
        assert result.report_id.startswith("WFV-SCALP-")

    def test_config_mode_is_scalp(self, result):
        assert result.config_summary["mode"] == "SCALP"


class TestAggressiveScalpWalkForward:
    """AGGRESSIVE_SCALP mode walk-forward validation.

    Uses a larger dataset and test window to accommodate AGGRESSIVE_SCALP's
    higher purge requirements (purge < test_window_bars must hold).
    """

    @pytest.fixture
    def result(self) -> WalkForwardResult:
        return run_walk_forward(
            n_bars=800,
            n_symbols=3,
            random_seed=42,
            train_window_bars=300,
            test_window_bars=400,
            min_folds=3,
            mode="AGGRESSIVE_SCALP",
        )

    def test_runs_without_error(self, result):
        assert result is not None
        assert isinstance(result, WalkForwardResult)

    def test_min_folds_met(self, result):
        assert len(result.folds) >= 2

    def test_report_id_contains_aggressive_scalp(self, result):
        assert result.report_id.startswith("WFV-AGGRESSIVE_SCALP-")

    def test_config_mode_is_aggressive_scalp(self, result):
        assert result.config_summary["mode"] == "AGGRESSIVE_SCALP"


class TestSwingWalkForwardBackwardCompat:
    """SWING mode still works with old default parameters."""

    @pytest.fixture
    def result(self) -> WalkForwardResult:
        return run_walk_forward(
            n_bars=500,
            n_symbols=3,
            random_seed=42,
            train_window_bars=200,
            test_window_bars=100,
            min_folds=3,
        )

    def test_report_id_contains_swing(self, result):
        """Default mode is SWING."""
        assert result.report_id.startswith("WFV-SWING-")

    def test_config_mode_is_swing(self, result):
        assert result.config_summary["mode"] == "SWING"


class TestInvalidMode:
    """Invalid mode raises error."""

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Unsupported mode"):
            run_walk_forward(mode="INVALID_MODE")


# =========================================================================
# compute_all_metrics with different annualization factors
# =========================================================================


class TestComputeAllMetricsAnnualization:
    """compute_all_metrics with mode-specific annualization."""

    def test_default_is_swing(self):
        """Default annualization factor is SWING (2190)."""
        y_pred = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        y_true = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        metrics = compute_all_metrics(y_pred, y_true)
        assert "sharpe" in metrics
        assert math.isfinite(metrics["sharpe"])

    def test_scalp_annualization(self):
        """SCALP annualization changes Sharpe magnitude."""
        y_pred = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        y_true = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        swing = compute_all_metrics(y_pred, y_true, annualization_factor=2190.0)
        scalp = compute_all_metrics(y_pred, y_true, annualization_factor=8760.0)
        # Same returns, higher annualization = higher Sharpe
        assert scalp["sharpe"] > swing["sharpe"]

    def test_aggressive_scalp_annualization(self):
        """AGGRESSIVE_SCALP annualization is highest."""
        y_pred = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        y_true = np.array([0, 0, 1, 1, 0, 0, 1, 2, 2, 0], dtype=int)
        swing = compute_all_metrics(y_pred, y_true, annualization_factor=2190.0)
        agg = compute_all_metrics(y_pred, y_true, annualization_factor=35040.0)
        assert agg["sharpe"] > swing["sharpe"]
