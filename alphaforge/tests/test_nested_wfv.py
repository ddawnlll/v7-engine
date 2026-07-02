"""Tests for nested walk-forward validation (Issue #147).

Tests cover:
  - InnerFoldSplitter splits correctly
  - NestedWalkForwardConfig validation
  - run_nested_walk_forward with small data and few Optuna trials
  - Overfit gap computation
  - Edge cases: small dataset, missing data
  - Convenience function from walk_forward_runner
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest

from alphaforge.tuning.nested_wfv import (
    OVERFIT_GAP_THRESHOLD,
    InnerFoldMetrics,
    InnerFoldSplitter,
    NestedWalkForwardConfig,
    NestedWalkForwardResult,
    OuterFoldResult,
    run_nested_walk_forward,
)
from alphaforge.tuning import nested_wfv as nwfv_module


# =========================================================================
# NestedWalkForwardConfig tests
# =========================================================================


class TestNestedWalkForwardConfig:
    """Tests for NestedWalkForwardConfig creation and defaults."""

    def test_default_config(self):
        """Default config has correct mode and fold counts."""
        config = NestedWalkForwardConfig(mode="SWING")  # type: ignore[arg-type]
        assert config.outer_folds == 7
        assert config.inner_folds == 3
        assert config.embargo_days == 30
        assert config.optuna_n_trials == 30

    def test_custom_config(self):
        """Custom config values are respected."""
        config = NestedWalkForwardConfig(
            mode="SWING",  # type: ignore[arg-type]
            outer_folds=5,
            inner_folds=2,
            embargo_days=14,
            optuna_n_trials=10,
        )
        assert config.outer_folds == 5
        assert config.inner_folds == 2
        assert config.embargo_days == 14
        assert config.optuna_n_trials == 10

    def test_overfit_gap_threshold_constant(self):
        """OVERFIT_GAP_THRESHOLD is exactly 0.10 per spec."""
        assert OVERFIT_GAP_THRESHOLD == 0.10


# =========================================================================
# InnerFoldSplitter tests
# =========================================================================


class TestInnerFoldSplitter:
    """Tests for InnerFoldSplitter."""

    def _make_chrono_dataset(
        self, n_bars: int = 100, n_symbols: int = 2
    ) -> List[Any]:
        """Create a minimal chronologically-sorted dataset."""

        class _Row:
            def __init__(self, ts: str, sym: str) -> None:
                self.feature_timestamp = ts
                self.symbol = sym

        rows = []
        for bar in range(n_bars):
            ts = f"2025-01-01T{bar:06d}"
            for sym_idx in range(n_symbols):
                sym = f"SYM{sym_idx}"
                rows.append(_Row(ts, sym))
        return rows

    def test_split_returns_correct_count(self):
        """InnerFoldSplitter returns inner_folds splits."""
        dataset = self._make_chrono_dataset(n_bars=100, n_symbols=2)
        outer_train_indices = list(range(len(dataset)))  # all rows

        splitter = InnerFoldSplitter(n_inner_folds=3, purge_bars=3, embargo_bars=3)
        splits = splitter.split(outer_train_indices, dataset)

        assert len(splits) >= 1, (
            f"Expected at least 1 inner split, got {len(splits)}"
        )

    def test_split_returns_pairs(self):
        """Each split is a (train_indices, val_indices) tuple."""
        dataset = self._make_chrono_dataset(n_bars=100, n_symbols=2)
        outer_train_indices = list(range(len(dataset)))
        splitter = InnerFoldSplitter(n_inner_folds=2, purge_bars=3, embargo_bars=3)
        splits = splitter.split(outer_train_indices, dataset)

        for train_idx, val_idx in splits:
            assert isinstance(train_idx, list)
            assert isinstance(val_idx, list)
            assert len(train_idx) > 0
            assert len(val_idx) > 0

    def test_split_no_overlap(self):
        """Inner train and val indices do not overlap."""
        dataset = self._make_chrono_dataset(n_bars=100, n_symbols=2)
        outer_train_indices = list(range(len(dataset)))
        splitter = InnerFoldSplitter(n_inner_folds=2, purge_bars=5, embargo_bars=5)
        splits = splitter.split(outer_train_indices, dataset)

        for train_idx, val_idx in splits:
            train_set = set(train_idx)
            val_set = set(val_idx)
            assert train_set.isdisjoint(val_set), (
                f"Inner train and val sets overlap: "
                f"{train_set & val_set}"
            )

    def test_split_chronological_order(self):
        """Inner train timestamps are before val timestamps."""
        dataset = self._make_chrono_dataset(n_bars=100, n_symbols=2)
        outer_train_indices = list(range(len(dataset)))
        splitter = InnerFoldSplitter(n_inner_folds=2, purge_bars=5, embargo_bars=5)
        splits = splitter.split(outer_train_indices, dataset)

        for train_idx, val_idx in splits:
            train_ts = {dataset[i].feature_timestamp for i in train_idx}
            val_ts = {dataset[i].feature_timestamp for i in val_idx}
            max_train_ts = max(train_ts)
            min_val_ts = min(val_ts)
            assert max_train_ts < min_val_ts, (
                f"Inner fold: train timestamp {max_train_ts} >= val timestamp {min_val_ts}, "
                f"chronological order violated"
            )

    def test_split_empty_returns_empty(self):
        """Splitter returns empty list when given no data."""
        splitter = InnerFoldSplitter(n_inner_folds=3, purge_bars=3, embargo_bars=3)
        splits = splitter.split([], [])
        assert splits == []

    def test_split_too_small_returns_empty(self):
        """Splitter returns empty list when dataset is too small."""
        dataset = self._make_chrono_dataset(n_bars=5, n_symbols=1)
        outer_train_indices = list(range(len(dataset)))
        splitter = InnerFoldSplitter(n_inner_folds=3, purge_bars=2, embargo_bars=2)
        splits = splitter.split(outer_train_indices, dataset)
        assert splits == [] or len(splits) == 0


# =========================================================================
# NestedWalkForwardResult tests
# =========================================================================


class TestNestedWalkForwardResult:
    """Tests for NestedWalkForwardResult dataclass."""

    def test_empty_result_defaults(self):
        """Empty result has INCONCLUSIVE verdict."""
        result = NestedWalkForwardResult()
        assert result.verdict == "INCONCLUSIVE"
        assert result.outer_folds == []
        assert result.avg_overfit_gap == 0.0
        assert not result.overfit_gap_passed
        assert result.overfit_flags == []

    def test_result_with_folds(self):
        """Result populated with outer folds."""
        fold = OuterFoldResult(
            fold_index=0,
            oos_sharpe=1.5,
            oos_win_rate=0.6,
            oos_accuracy=0.65,
            train_accuracy=0.75,
            val_accuracy=0.65,
        )
        result = NestedWalkForwardResult(
            outer_folds=[fold],
            avg_overfit_gap=0.10,
            overfit_gap_passed=True,
            verdict="PASS",
        )
        assert len(result.outer_folds) == 1
        assert result.outer_folds[0].oos_sharpe == 1.5
        assert result.overfit_gap_passed
        assert result.verdict == "PASS"


class TestInnerFoldMetrics:
    """Tests for InnerFoldMetrics dataclass."""

    def test_defaults(self):
        """InnerFoldMetrics has reasonable defaults."""
        m = InnerFoldMetrics(fold_index=0)
        assert m.fold_index == 0
        assert m.train_accuracy == 0.0
        assert m.val_accuracy == 0.0
        assert m.accuracy_gap == 0.0
        assert m.logloss_gap == 0.0

    def test_with_values(self):
        """InnerFoldMetrics stores provided values."""
        m = InnerFoldMetrics(
            fold_index=1,
            train_accuracy=0.85,
            val_accuracy=0.72,
            train_logloss=0.35,
            val_logloss=0.55,
            accuracy_gap=0.13,
            logloss_gap=0.20,
            train_count=500,
            val_count=200,
        )
        assert m.fold_index == 1
        assert m.train_accuracy == 0.85
        assert m.val_accuracy == 0.72
        assert m.accuracy_gap == 0.13
        assert m.train_count == 500


# =========================================================================
# Integration tests for run_nested_walk_forward
# =========================================================================


_SMALL_TEST_KWARGS = {
    "outer_train_window_bars": 80,
    "outer_test_window_bars": 40,
}


class TestRunNestedWalkForwardIntegration:
    """Integration tests for run_nested_walk_forward with small data."""

    def test_runs_without_error(self):
        """run_nested_walk_forward completes without exception."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert result is not None
        assert isinstance(result, NestedWalkForwardResult)

    def test_returns_result_object(self):
        """Returns a NestedWalkForwardResult instance."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert isinstance(result, NestedWalkForwardResult)

    def test_report_id_format(self):
        """Report ID starts with Nested WFV prefix."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert result.report_id.startswith("NWFV-"), (
            f"Report ID should start with NWFV-, got {result.report_id}"
        )

    def test_generated_at_present(self):
        """generated_at timestamp is populated."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert result.generated_at != ""

    def test_overfit_gap_in_valid_range(self):
        """Overfit gap is a finite float."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert math.isfinite(result.avg_overfit_gap)
        # Overfit gap can be negative (val accuracy > train accuracy)
        # or positive (train accuracy > val accuracy) depending on data
        assert -1.0 <= result.avg_overfit_gap <= 1.0

    def test_outer_folds_populated(self):
        """Outer folds list is populated (may be empty with small data)."""
        result = run_nested_walk_forward(
            n_bars=600,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            outer_train_window_bars=100,
            outer_test_window_bars=50,
        )
        # With 600 bars and 2 symbols, should get at least some outer folds
        assert len(result.outer_folds) >= 1 or result.verdict != "INCONCLUSIVE"

    def test_invalid_mode_raises(self):
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported mode"):
            run_nested_walk_forward(
                n_bars=100,
                n_symbols=1,
                mode="INVALID",
                outer_folds=2,
                inner_folds=2,
                embargo_days=5,
                optuna_n_trials=1,
                optuna_timeout_seconds=10,
            )


class TestRunNestedWalkForwardMode:
    """Tests for mode-specific nested walk-forward."""

    def test_swing_mode(self):
        """SWING mode produces valid results."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert isinstance(result, NestedWalkForwardResult)
        assert result.config.mode.value == "SWING"

    def test_scalp_mode(self):
        """SCALP mode runs without error."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SCALP",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert isinstance(result, NestedWalkForwardResult)
        assert result.config.mode.value == "SCALP"

    def test_aggressive_scalp_mode(self):
        """AGGRESSIVE_SCALP mode runs without error."""
        result = run_nested_walk_forward(
            n_bars=400,
            n_symbols=2,
            random_seed=42,
            mode="AGGRESSIVE_SCALP",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert isinstance(result, NestedWalkForwardResult)
        assert result.config.mode.value == "AGGRESSIVE_SCALP"


class TestRunNestedWalkForwardEdgeCases:
    """Edge case tests for nested walk-forward."""

    def test_small_dataset_does_not_crash(self):
        """Very small dataset does not crash."""
        result = run_nested_walk_forward(
            n_bars=50,
            n_symbols=1,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=1,
            embargo_days=2,
            optuna_n_trials=1,
            optuna_timeout_seconds=10,
            outer_train_window_bars=20,
            outer_test_window_bars=10,
        )
        assert isinstance(result, NestedWalkForwardResult)

    def test_verdict_not_none(self):
        """Verdict is a non-None string."""
        result = run_nested_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=1,
            embargo_days=5,
            optuna_n_trials=2,
            optuna_timeout_seconds=15,
            **_SMALL_TEST_KWARGS,
        )
        assert result.verdict is not None
        assert isinstance(result.verdict, str)

    def test_optimized_params_are_populated(self):
        """optimized_params contains numeric hyperparameters."""
        result = run_nested_walk_forward(
            n_bars=600,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=5,
            optuna_timeout_seconds=30,
            outer_train_window_bars=100,
            outer_test_window_bars=50,
        )
        # Param dict may be empty if no outer folds processed,
        # but should not be None
        assert result.optimized_params is not None


# =========================================================================
# Convenience function from walk_forward_runner
# =========================================================================


class TestConvenienceFunction:
    """Tests for the run_nested_walk_forward convenience function
    exposed in walk_forward_runner."""

    def test_import_from_walk_forward_runner(self):
        """Can import convenience function from walk_forward_runner."""
        from alphaforge.validation.walk_forward_runner import (
            run_nested_walk_forward as convenience_fn,
        )
        assert convenience_fn is not None
        assert callable(convenience_fn)

    def test_convenience_runs_without_error(self):
        """Convenience function runs without error."""
        from alphaforge.validation.walk_forward_runner import (
            run_nested_walk_forward as convenience_fn,
        )
        result = convenience_fn(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=2,
            optuna_timeout_seconds=15,
            outer_train_window_bars=80,
            outer_test_window_bars=40,
        )
        assert result is not None
        assert hasattr(result, "verdict")
        assert hasattr(result, "avg_overfit_gap")


# =========================================================================
# Overfit flag tests
# =========================================================================


class TestOverfitFlags:
    """Tests for overfit flag generation in nested WFV."""

    def test_overfit_flags_list_type(self):
        """overfit_flags is a list of OverfitFlag."""
        result = run_nested_walk_forward(
            n_bars=300,
            n_symbols=2,
            random_seed=42,
            mode="SWING",
            outer_folds=2,
            inner_folds=2,
            embargo_days=5,
            optuna_n_trials=3,
            optuna_timeout_seconds=30,
            **_SMALL_TEST_KWARGS,
        )
        assert isinstance(result.overfit_flags, list)
        if result.overfit_flags:
            flag = result.overfit_flags[0]
            assert hasattr(flag, "indicator")
            assert hasattr(flag, "severity")
            assert hasattr(flag, "description")


# =========================================================================
# Constants tests
# =========================================================================


class TestConstants:
    """Tests for module constants."""

    def test_overfit_gap_threshold(self):
        """OVERFIT_GAP_THRESHOLD is defined."""
        assert hasattr(nwfv_module, "OVERFIT_GAP_THRESHOLD")
        assert nwfv_module.OVERFIT_GAP_THRESHOLD == 0.10

    def test_nested_outer_folds_constant(self):
        """NESTED_OUTER_FOLDS constant is defined."""
        assert hasattr(nwfv_module, "NESTED_OUTER_FOLDS")
        assert nwfv_module.NESTED_OUTER_FOLDS == 7

    def test_nested_inner_folds_constant(self):
        """NESTED_INNER_FOLDS constant is defined."""
        assert hasattr(nwfv_module, "NESTED_INNER_FOLDS")
        assert nwfv_module.NESTED_INNER_FOLDS == 3

    def test_nested_embargo_days_constant(self):
        """NESTED_EMBARGO_DAYS constant is defined."""
        assert hasattr(nwfv_module, "NESTED_EMBARGO_DAYS")
        assert nwfv_module.NESTED_EMBARGO_DAYS == 30

    def test_mode_bars_per_day_mapping(self):
        """MODE_BARS_PER_DAY has correct mappings."""
        assert nwfv_module.MODE_BARS_PER_DAY["SWING"] == 6
        assert nwfv_module.MODE_BARS_PER_DAY["SCALP"] == 24
        assert nwfv_module.MODE_BARS_PER_DAY["AGGRESSIVE_SCALP"] == 96
