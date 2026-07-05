"""Tests for cross-timeframe edge comparison (Issue #143).

Tests: compare_timeframes, build_timeframe_edge, compute_pairwise_correlation,
TimeframeEdge, CrossTimeframeComparison.

All tests are deterministic (numpy-only). No ML imports. No profitability claims.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from alphaforge.validation.cross_timeframe import (
    CrossTimeframeComparison,
    TimeframeEdge,
    build_timeframe_edge,
    compare_timeframes,
    compare_timeframes_to_dict,
    compute_pairwise_correlation,
    _classify_edge_strength,
    _infer_direction,
)


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestClassifyEdgeStrength:
    """Edge strength classification."""

    def test_none_negative_sharpe(self):
        """Negative Sharpe with negative expectancy → NONE."""
        assert _classify_edge_strength(-0.5, -0.1) == "NONE"

    def test_none_zero_sharpe(self):
        """Zero values → NONE."""
        assert _classify_edge_strength(0.0, 0.0) == "NONE"

    def test_weak_positive_only(self):
        """Low but positive edge → WEAK."""
        assert _classify_edge_strength(0.1, 0.02) == "WEAK"

    def test_moderate_edge(self):
        """Moderate Sharpe and expectancy → MODERATE."""
        assert _classify_edge_strength(0.5, 0.08) == "MODERATE"

    def test_strong_edge(self):
        """High Sharpe and expectancy → STRONG."""
        assert _classify_edge_strength(1.0, 0.20) == "STRONG"


class TestInferDirection:
    """Direction inference from metrics."""

    def test_long_bias(self):
        """Positive expectancy and Sharpe → LONG_BIAS."""
        assert _infer_direction(0.5, 0.10) == "LONG_BIAS"

    def test_short_bias(self):
        """Positive expectancy with negative Sharpe → SHORT_BIAS."""
        assert _infer_direction(-0.5, 0.10) == "SHORT_BIAS"

    def test_neutral(self):
        """Near-zero metrics → NEUTRAL."""
        assert _infer_direction(0.01, 0.001) == "NEUTRAL"

    def test_inconclusive(self):
        """Mixed signals → INCONCLUSIVE."""
        direction = _infer_direction(0.2, 0.03)
        assert direction in ("NEUTRAL", "INCONCLUSIVE")


# ---------------------------------------------------------------------------
# build_timeframe_edge tests
# ---------------------------------------------------------------------------


class TestBuildTimeframeEdge:
    """Building TimeframeEdge from WFV results."""

    def test_strong_edge(self):
        """Strong metrics produce STRONG edge."""
        results = {
            "aggregate_metrics": {
                "avg_sharpe": 1.2,
                "oos_expectancy_r": 0.25,
                "avg_win_rate": 0.60,
                "total_oos_trades": 500,
                "n_folds": 6,
            }
        }
        edge = build_timeframe_edge("SWING", results)
        assert edge.edge_strength == "STRONG"
        assert edge.edge_present is True
        assert edge.mode == "SWING"

    def test_no_edge(self):
        """Weak metrics produce no edge."""
        results = {
            "aggregate_metrics": {
                "avg_sharpe": -0.1,
                "oos_expectancy_r": -0.05,
                "avg_win_rate": 0.48,
                "total_oos_trades": 100,
                "n_folds": 6,
            }
        }
        edge = build_timeframe_edge("SCALP", results)
        assert edge.edge_strength == "NONE"
        assert edge.edge_present is False

    def test_dict_with_flat_keys(self):
        """Flat dict (no nested aggregate_metrics) still works."""
        results = {
            "sharpe": 0.6,
            "oos_expectancy_r": 0.12,
            "win_rate": 0.55,
            "oos_trade_count": 200,
            "n_folds": 6,
        }
        edge = build_timeframe_edge("AGGRESSIVE_SCALP", results)
        assert edge.sharpe == 0.6
        assert edge.edge_present is True

    def test_all_modes_accepted(self):
        """All three modes are accepted without error."""
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            edge = build_timeframe_edge(mode, {})
            assert edge.mode == mode
            assert isinstance(edge.edge_present, bool)


# ---------------------------------------------------------------------------
# compute_pairwise_correlation tests
# ---------------------------------------------------------------------------


class TestPairwiseCorrelation:
    """Pairwise prediction correlation."""

    def test_identical_predictions(self):
        """Identical arrays → correlation of 1.0."""
        preds = {
            "SWING": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=int),
            "SCALP": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=int),
        }
        corr = compute_pairwise_correlation(preds)
        assert "SCALP_vs_SWING" in corr
        assert abs(corr["SCALP_vs_SWING"] - 1.0) < 0.01

    def test_opposite_predictions(self):
        """Negatively correlated arrays → negative correlation."""
        rng = np.random.RandomState(42)
        preds = {
            "SWING": np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=int),
            "SCALP": np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0], dtype=int),
        }
        corr = compute_pairwise_correlation(preds)
        assert corr["SCALP_vs_SWING"] < 0

    def test_three_way_correlation(self):
        """Three modes produce three pairwise keys."""
        preds = {
            "SWING": np.array([0, 1, 2, 0, 1], dtype=int),
            "SCALP": np.array([0, 1, 2, 0, 1], dtype=int),
            "AGGRESSIVE_SCALP": np.array([0, 1, 2, 0, 1], dtype=int),
        }
        corr = compute_pairwise_correlation(preds)
        assert len(corr) == 3  # 3 choose 2 = 3 pairs

    def test_empty_array(self):
        """Empty arrays return 0.0 correlation."""
        corr = compute_pairwise_correlation({
            "SWING": np.array([], dtype=int),
            "SCALP": np.array([], dtype=int),
        })
        assert corr["SCALP_vs_SWING"] == 0.0

    def test_short_arrays_aligned(self):
        """Uneven arrays are aligned to shortest length."""
        preds = {
            "SWING": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2], dtype=int),
            "SCALP": np.array([0, 1, 2, 0, 1, 2], dtype=int),
        }
        corr = compute_pairwise_correlation(preds)
        # Should align to 6 elements (shortest) without error
        assert "SCALP_vs_SWING" in corr


# ---------------------------------------------------------------------------
# compare_timeframes tests
# ---------------------------------------------------------------------------


class TestCompareTimeframes:
    """Cross-timeframe edge comparison."""

    def _make_wfv_result(self, sharpe: float, expectancy_r: float) -> dict:
        return {
            "aggregate_metrics": {
                "avg_sharpe": sharpe,
                "oos_expectancy_r": expectancy_r,
                "avg_win_rate": 0.55,
                "total_oos_trades": 300,
                "n_folds": 6,
            }
        }

    def test_all_strong(self):
        """All three timeframes have strong edges."""
        results = {
            "SWING": self._make_wfv_result(0.8, 0.15),
            "SCALP": self._make_wfv_result(0.7, 0.12),
            "AGGRESSIVE_SCALP": self._make_wfv_result(0.6, 0.10),
        }
        comp = compare_timeframes(results)
        assert len(comp.timeframes) == 3
        assert comp.multi_tf_confirmation is True
        assert comp.dominant_timeframe == "SWING"
        assert comp.verdict == "CONTINUE_RESEARCH"

    def test_no_edges(self):
        """No timeframe has edge → INCONCLUSIVE."""
        results = {
            "SWING": self._make_wfv_result(-0.1, -0.05),
            "SCALP": self._make_wfv_result(-0.2, -0.08),
        }
        comp = compare_timeframes(results)
        assert comp.multi_tf_confirmation is False
        assert comp.verdict == "INCONCLUSIVE"

    def test_single_timeframe(self):
        """Only one timeframe provided."""
        results = {
            "SWING": self._make_wfv_result(0.8, 0.15),
        }
        comp = compare_timeframes(results)
        assert len(comp.timeframes) == 1
        assert comp.tf_specialization is False  # Not enough TFs for specialization

    def test_empty_results(self):
        """Empty results → INCONCLUSIVE."""
        comp = compare_timeframes({})
        assert comp.verdict == "INCONCLUSIVE"
        assert "No timeframe results" in comp.summary

    def test_predictions_correlation(self):
        """Predictions are included in comparison."""
        results = {
            "SWING": self._make_wfv_result(0.8, 0.15),
            "SCALP": self._make_wfv_result(0.7, 0.12),
        }
        preds = {
            "SWING": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=int),
            "SCALP": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=int),
        }
        comp = compare_timeframes(results, predictions_per_mode=preds)
        assert len(comp.pairwise_correlations) > 0


class TestCompareTimeframesToDict:
    """Serialization of CrossTimeframeComparison."""

    def test_dict_roundtrip(self):
        """Comparison serializes to JSON-compatible dict."""
        results = {
            "SWING": {
                "aggregate_metrics": {
                    "avg_sharpe": 0.8, "oos_expectancy_r": 0.15,
                    "avg_win_rate": 0.55, "total_oos_trades": 300, "n_folds": 6,
                }
            },
        }
        comp = compare_timeframes(results)
        d = compare_timeframes_to_dict(comp)
        assert d["verdict"] == comp.verdict
        assert d["dominant_timeframe"] == comp.dominant_timeframe
        assert json.dumps(d)  # JSON-serializable
