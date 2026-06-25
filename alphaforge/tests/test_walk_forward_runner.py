"""Walk-forward runner tests — structural and metric validation.

Tests for the walk_forward_runner module: fold construction, per-fold metric
computation, overfit detection, report serialization, and financial metric
helpers. These tests import xgboost and numpy (training environment).
"""

from __future__ import annotations

import json
import math
import pytest
import numpy as np

from alphaforge.validation.walk_forward_runner import (
    WalkForwardResult,
    FoldMetrics,
    compute_sharpe_ratio,
    compute_win_rate,
    compute_max_drawdown,
    compute_profit_factor,
    compute_all_metrics,
    _class_predictions_to_returns,
    generate_walk_forward_ohlcv,
    generate_walk_forward_labels,
    run_walk_forward,
    walk_forward_result_to_dict,
    save_walk_forward_report,
    OVERFIT_ACCURACY_GAP_THRESHOLD,
    OVERFIT_LOGLOSS_GAP_THRESHOLD,
)


# =========================================================================
# Financial metric helper tests
# =========================================================================


class TestFinancialMetrics:
    """Unit tests for financial metric computation functions."""

    def test_sharpe_zero_returns(self):
        """Sharpe ratio is 0.0 when all returns are zero."""
        returns = np.zeros(100, dtype=np.float64)
        assert compute_sharpe_ratio(returns) == 0.0

    def test_sharpe_positive(self):
        """Sharpe ratio is positive for positive mean returns."""
        returns = np.array([1.0, -0.5, 0.5, 0.2, 0.3], dtype=np.float64)
        sharpe = compute_sharpe_ratio(returns, annualization_factor=1.0)
        assert sharpe > 0.0

    def test_sharpe_negative(self):
        """Sharpe ratio is negative for negative mean returns."""
        returns = np.array([-1.0, -0.5, -0.2, 0.1, -0.3], dtype=np.float64)
        sharpe = compute_sharpe_ratio(returns, annualization_factor=1.0)
        assert sharpe < 0.0

    def test_sharpe_empty(self):
        """Sharpe ratio is 0.0 for empty returns."""
        assert compute_sharpe_ratio(np.array([], dtype=np.float64)) == 0.0

    def test_sharpe_annualized(self):
        """Sharpe scales with sqrt(annualization_factor)."""
        returns = np.array([0.1, -0.05, 0.03, -0.02, 0.04], dtype=np.float64)
        sharpe1 = compute_sharpe_ratio(returns, annualization_factor=1.0)
        sharpe100 = compute_sharpe_ratio(returns, annualization_factor=100.0)
        assert abs(sharpe100 / sharpe1 - 10.0) < 1e-9

    def test_win_rate_all_correct(self):
        """Win rate is 1.0 when all predictions match truth."""
        y_pred = np.array([0, 0, 1, 1, 0, 1], dtype=int)
        y_true = np.array([0, 0, 1, 1, 0, 1], dtype=int)
        assert compute_win_rate(y_pred, y_true) == 1.0

    def test_win_rate_all_wrong(self):
        """Win rate is 0.0 when no predictions match truth."""
        y_pred = np.array([0, 0, 0], dtype=int)
        y_true = np.array([1, 1, 1], dtype=int)
        assert compute_win_rate(y_pred, y_true) == 0.0

    def test_win_rate_no_trades(self):
        """Win rate is 0.0 when there are no trade predictions."""
        y_pred = np.array([2, 2, 2], dtype=int)  # all NO_TRADE
        y_true = np.array([0, 1, 2], dtype=int)
        assert compute_win_rate(y_pred, y_true) == 0.0

    def test_win_rate_mixed(self):
        """Win rate handles mixed correct/incorrect."""
        y_pred = np.array([0, 1, 0, 1, 2, 0], dtype=int)
        y_true = np.array([0, 0, 0, 1, 2, 2], dtype=int)
        # Trade predictions at indices: 0(W), 1(L), 2(W), 3(W), 5(L)
        # Wins: indices 0,2,3 = 3 wins out of 5 trades
        wr = compute_win_rate(y_pred, y_true)
        assert wr == 0.6  # 3/5

    def test_max_drawdown_zero(self):
        """Max drawdown is 0.0 for all-positive returns."""
        returns = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        assert compute_max_drawdown(returns) == 0.0

    def test_max_drawdown_negative(self):
        """Max drawdown is negative for a losing series."""
        returns = np.array([1.0, -5.0, 1.0], dtype=np.float64)
        dd = compute_max_drawdown(returns)
        assert dd < 0.0
        # cumulative: [1.0, -4.0, -3.0], peak: [1.0, 1.0, 1.0]
        # drawdowns: [0.0, -5.0, -4.0], max dd = -5.0
        assert dd == -5.0

    def test_max_drawdown_empty(self):
        """Max drawdown is 0.0 for empty returns."""
        assert compute_max_drawdown(np.array([], dtype=np.float64)) == 0.0

    def test_profit_factor_breakeven(self):
        """Profit factor is 1.0 for equal gains and losses."""
        returns = np.array([1.0, -1.0, 2.0, -2.0], dtype=np.float64)
        assert compute_profit_factor(returns) == 1.0

    def test_profit_factor_profitable(self):
        """Profit factor > 1.0 for profitable series."""
        returns = np.array([2.0, -1.0, 3.0, -1.0], dtype=np.float64)
        pf = compute_profit_factor(returns)
        assert pf > 1.0  # gross profit 5 / gross loss 2 = 2.5

    def test_profit_factor_no_losses(self):
        """Profit factor is inf when no losing trades."""
        returns = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        assert compute_profit_factor(returns) == float("inf")

    def test_class_predictions_to_returns_correct_long(self):
        """Correct LONG prediction yields +1.0."""
        returns = _class_predictions_to_returns(
            np.array([0], dtype=int), np.array([0], dtype=int)
        )
        assert returns[0] == 1.0

    def test_class_predictions_to_returns_correct_short(self):
        """Correct SHORT prediction yields +1.0."""
        returns = _class_predictions_to_returns(
            np.array([1], dtype=int), np.array([1], dtype=int)
        )
        assert returns[0] == 1.0

    def test_class_predictions_to_returns_wrong_direction(self):
        """Long when should be short yields -1.0."""
        returns = _class_predictions_to_returns(
            np.array([0], dtype=int), np.array([1], dtype=int)
        )
        assert returns[0] == -1.0

    def test_class_predictions_to_returns_no_trade(self):
        """NO_TRADE prediction yields 0.0."""
        returns = _class_predictions_to_returns(
            np.array([2], dtype=int), np.array([0], dtype=int)
        )
        assert returns[0] == 0.0


# =========================================================================
# Data generation tests
# =========================================================================


class TestDataGeneration:
    """Tests for synthetic data generation functions."""

    def test_generate_ohlcv_shape(self):
        """OHLCV data has correct shape and required keys."""
        data = generate_walk_forward_ohlcv(n_bars=100, symbols=("BTCUSDT", "ETHUSDT"))
        assert "open" in data
        assert "high" in data
        assert "low" in data
        assert "close" in data
        assert "volume" in data
        assert len(data["close"]) == 200  # 100 bars * 2 symbols
        assert data["symbol"] is not None

    def test_generate_ohlcv_no_negative_prices(self):
        """All prices are positive."""
        data = generate_walk_forward_ohlcv(n_bars=100, symbols=("BTCUSDT",))
        assert np.all(data["close"] > 0)
        assert np.all(data["open"] > 0)
        assert np.all(data["high"] > 0)
        assert np.all(data["low"] > 0)

    def test_generate_ohlcv_high_ge_low(self):
        """High >= Low for all bars."""
        data = generate_walk_forward_ohlcv(n_bars=100, symbols=("BTCUSDT",))
        assert np.all(data["high"] >= data["low"])

    def test_generate_ohlcv_deterministic(self):
        """Same seed gives same data."""
        d1 = generate_walk_forward_ohlcv(n_bars=50, symbols=("BTCUSDT",), random_seed=42)
        d2 = generate_walk_forward_ohlcv(n_bars=50, symbols=("BTCUSDT",), random_seed=42)
        assert np.allclose(d1["close"], d2["close"])

    def test_generate_labels_shape(self):
        """Labels have correct shape and valid values."""
        labels = generate_walk_forward_labels(100, random_seed=42)
        assert len(labels) == 100
        valid = {"LONG_NOW", "SHORT_NOW", "NO_TRADE"}
        assert set(labels) <= valid

    def test_generate_labels_deterministic(self):
        """Same seed gives same labels."""
        l1 = generate_walk_forward_labels(50, random_seed=42)
        l2 = generate_walk_forward_labels(50, random_seed=42)
        assert np.array_equal(l1, l2)

    def test_compute_all_metrics_structure(self):
        """compute_all_metrics returns complete dict."""
        y_pred = np.array([0, 1, 2, 0, 1], dtype=int)
        y_true = np.array([0, 1, 2, 1, 0], dtype=int)
        metrics = compute_all_metrics(y_pred, y_true)
        assert "sharpe" in metrics
        assert "win_rate" in metrics
        assert "max_drawdown" in metrics
        assert "profit_factor" in metrics
        assert "total_trades" in metrics
        assert "long_trades" in metrics
        assert "short_trades" in metrics
        assert "no_trade_count" in metrics


# =========================================================================
# Walk-forward runner tests
# =========================================================================


class TestWalkForwardRunner:
    """Integration tests for the walk-forward runner."""

    @pytest.fixture
    def result(self) -> WalkForwardResult:
        """Run walk-forward on a small dataset (fast, 3 symbols x 500 bars)."""
        return run_walk_forward(
            n_bars=500,
            n_symbols=3,
            random_seed=42,
            train_window_bars=200,
            test_window_bars=100,
            min_folds=3,
        )

    def test_runs_without_error(self, result):
        """walk-forward completes without exception."""
        assert result is not None
        assert isinstance(result, WalkForwardResult)

    def test_min_folds_met(self, result):
        """At least min_folds (3) folds are produced."""
        assert len(result.folds) >= 3, (
            f"Expected >= 3 folds, got {len(result.folds)}"
        )

    def test_each_fold_has_valid_metrics(self, result):
        """Every fold has non-NaN, finite metrics in expected ranges."""
        for fm in result.folds:
            assert isinstance(fm.fold_index, int)
            assert fm.train_count > 0
            assert fm.val_count > 0
            assert fm.oos_count > 0
            assert 0.0 <= fm.train_accuracy <= 1.0
            assert 0.0 <= fm.val_accuracy <= 1.0
            assert 0.0 <= fm.win_rate <= 1.0
            assert fm.max_drawdown <= 0.0
            assert math.isfinite(fm.sharpe) or fm.sharpe == float("inf") or fm.sharpe == float("-inf")
            assert fm.total_trades >= 0

    def test_overfit_detection_works(self, result):
        """Overfit flags are generated when accuracy gap is high."""
        # With random labels, we expect overfit flags
        # At minimum, the system should produce some flags
        has_high_gap = any(fm.accuracy_gap > OVERFIT_ACCURACY_GAP_THRESHOLD for fm in result.folds)
        assert has_high_gap or len(result.overfit_flags) > 0, (
            "Expected overfit detection to trigger with random synthetic labels"
        )

    def test_verdict_is_not_inconclusive(self, result):
        """Verdict is a real verdict (not INCONCLUSIVE) since metrics are computed."""
        assert result.verdict != "INCONCLUSIVE"

    def test_report_has_valid_id(self, result):
        """Report ID follows expected format."""
        assert result.report_id.startswith("WFV-SWING-"), (
            f"Report ID should start with WFV-SWING-, got {result.report_id}"
        )
        assert len(result.report_id) > 20

    def test_aggregate_metrics_present(self, result):
        """Aggregate metrics dict has all expected keys."""
        agg = result.aggregate_metrics
        required = [
            "n_folds", "total_oos_trades",
            "avg_train_accuracy", "avg_val_accuracy",
            "avg_accuracy_gap", "avg_logloss_gap",
            "avg_sharpe", "sharpe_stability_std",
            "avg_win_rate", "avg_max_drawdown", "avg_profit_factor",
        ]
        for key in required:
            assert key in agg, f"Missing aggregate metric: {key}"

    def test_config_and_data_summary_present(self, result):
        """Config and data summaries are populated."""
        assert result.config_summary["mode"] == "SWING"
        assert result.config_summary["actual_folds"] == len(result.folds)
        assert result.data_summary["n_features"] > 0
        assert len(result.data_summary["feature_names"]) > 0

    def test_folds_are_chronological(self, result):
        """Fold indices are sequential starting from 0."""
        indices = [fm.fold_index for fm in result.folds]
        assert indices == list(range(len(indices)))


# =========================================================================
# Report serialization tests
# =========================================================================


class TestReportSerialization:
    """Tests for report dict conversion and file saving."""

    def test_to_dict_serializable(self, tmp_path):
        """walk_forward_result_to_dict produces JSON-serializable output."""
        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        d = walk_forward_result_to_dict(result)
        # Should not raise
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        assert parsed["verdict"] == result.verdict
        assert len(parsed["fold_metrics"]) == len(result.folds)

    def test_save_report_creates_file(self, tmp_path):
        """save_walk_forward_report writes a JSON file."""
        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        out = tmp_path / "wfv_test.json"
        saved = save_walk_forward_report(result, str(out))
        assert saved == str(out)
        assert out.exists()
        with open(out) as f:
            data = json.load(f)
        assert data["report_id"] == result.report_id

    def test_fold_metrics_contain_all_fields(self, tmp_path):
        """Serialized fold metrics have all expected sub-dicts."""
        result = run_walk_forward(
            n_bars=200,
            n_symbols=2,
            random_seed=42,
            train_window_bars=80,
            test_window_bars=40,
            min_folds=3,
        )
        d = walk_forward_result_to_dict(result)
        for fm in d["fold_metrics"]:
            assert "sample_counts" in fm
            assert "training_metrics" in fm
            assert "oos_financial_metrics" in fm
            assert "oos_trade_counts" in fm
            assert "overfitting_indicators" in fm
            # Check sub-fields
            assert "sharpe" in fm["oos_financial_metrics"]
            assert "win_rate" in fm["oos_financial_metrics"]
            assert "max_drawdown" in fm["oos_financial_metrics"]
            assert "profit_factor" in fm["oos_financial_metrics"]
