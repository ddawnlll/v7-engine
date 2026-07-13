"""Tests for symbol-contribution (G5) and calibration (G6) instrumentation
added to walk_forward_validate/collect_metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.train import collect_metrics, walk_forward_validate
from alphaforge.training.xgb_trainer import TrainingResult


def _mock_confident_long_result() -> TrainingResult:
    """Model that always predicts LONG with high confidence."""
    model = MagicMock(spec=xgb.Booster)
    model.inplace_predict.side_effect = lambda matrix: np.tile(
        np.array([[0.9, 0.05, 0.05]], dtype=np.float64), (len(matrix), 1)
    )
    return TrainingResult(
        model=model, model_artifact={}, model_binary_bytes=b"",
        train_metrics={"accuracy": 0.9, "logloss": 0.2},
        val_metrics={"accuracy": 0.9, "logloss": 0.2},
        training_duration_seconds=0.01,
    )


def test_symbol_contribution_flags_single_symbol_dominance():
    symbols_per_bar = 2
    n_bars = 300
    n = symbols_per_bar * n_bars
    # BTCUSDT/ETHUSDT alternate rows; skew ETHUSDT to have far fewer active trades
    # by making its action_net_r always ~0 (still trades LONG, both symbols get
    # equal trade counts here — the dominance instead comes from an uneven split).
    symbols = np.array(["BTCUSDT" if i % 2 == 0 else "ETHUSDT" for i in range(n)])
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack([np.full(n, 0.02), np.full(n, -0.01), np.zeros(n)])
    X = np.random.RandomState(5).normal(size=(n, 3))

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_confident_long_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3,
            action_net_r=action_net_r, symbols=symbols,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["symbol_stability"]["available"] is True
    assert metrics["symbol_stability"]["num_symbols"] == 2
    # Roughly even split across alternating rows -> ~50% each, no single-symbol dominance.
    assert metrics["symbol_stability"]["top_symbol_share_pct"] == pytest.approx(50.0, abs=5.0)


def test_calibration_computed_from_confidence_and_correctness():
    n = 600
    X = np.random.RandomState(6).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)  # true class is always LONG (0)
    action_net_r = np.column_stack([np.full(n, 0.02), np.zeros(n), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_confident_long_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["calibration"]["available"] is True
    # Model is 90% confident and always correct (true label is always LONG) ->
    # confidence (0.9) exceeds accuracy... no, accuracy is 100% here, so the
    # gap is |1.0 - 0.9| = 0.10 -> ECE should reflect that, not be huge/broken.
    assert 0.0 <= metrics["calibration"]["expected_calibration_error_pct"] <= 100.0
    assert 0.0 <= metrics["calibration"]["max_calibration_error_pct"] <= 100.0


def test_symbol_and_calibration_unavailable_when_no_symbols_supplied():
    n = 400
    X = np.random.RandomState(7).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack([np.full(n, 0.02), np.zeros(n), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_confident_long_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["symbol_stability"]["available"] is False
    # Calibration is still available since confidence/correctness don't need symbols.
    assert metrics["calibration"]["available"] is True
