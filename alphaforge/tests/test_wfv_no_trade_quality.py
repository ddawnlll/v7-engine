"""Tests for the no-trade-quality instrumentation added to walk_forward_validate
and collect_metrics (train.py-local approximation of CORRECT_NO_TRADE /
SAVED_LOSS / MISSED_OPPORTUNITY from the counterfactual best-of-{LONG,SHORT}
net R at each NO_TRADE decision)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.train import collect_metrics, walk_forward_validate
from alphaforge.training.xgb_trainer import TrainingResult


def _mock_all_no_trade_result() -> TrainingResult:
    """Model that always predicts NO_TRADE (low confidence on all 3 classes)."""
    model = MagicMock(spec=xgb.Booster)
    model.inplace_predict.side_effect = lambda matrix: np.tile(
        np.array([[0.34, 0.33, 0.33]], dtype=np.float64), (len(matrix), 1)
    )
    return TrainingResult(
        model=model, model_artifact={}, model_binary_bytes=b"",
        train_metrics={"accuracy": 0.34, "logloss": 1.0},
        val_metrics={"accuracy": 0.34, "logloss": 1.0},
        training_duration_seconds=0.01,
    )


def test_no_trade_quality_correct_when_neither_direction_profitable():
    n = 500
    X = np.random.RandomState(1).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    # Both LONG and SHORT would have lost money -> skipping was correct.
    action_net_r = np.column_stack([np.full(n, -0.05), np.full(n, -0.03), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_all_no_trade_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    assert results
    for r in results:
        assert r["no_trade_count"] == r["n_val"]
        assert r["no_trade_correct_count"] == r["n_val"]
        assert r["no_trade_missed_count"] == 0
        # best_r = max(-0.05, -0.03) = -0.03 < 0 -> loss saved by skipping.
        assert all(v == pytest.approx(0.03) for v in r["no_trade_saved_loss_values"])

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["no_trade_quality"]["correct_no_trade_pct"] == pytest.approx(100.0)
    assert metrics["no_trade_quality"]["missed_opportunity_pct"] == pytest.approx(0.0)


def test_no_trade_quality_missed_opportunity_when_strong_edge_skipped():
    n = 500
    X = np.random.RandomState(2).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    # LONG would have earned +0.20R -> skipping was a missed opportunity.
    action_net_r = np.column_stack([np.full(n, 0.20), np.full(n, -0.02), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_all_no_trade_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["no_trade_quality"]["missed_opportunity_pct"] == pytest.approx(100.0)
    assert metrics["no_trade_quality"]["correct_no_trade_pct"] == pytest.approx(0.0)


def test_no_trade_quality_saved_loss_recorded_for_negative_counterfactual():
    n = 400
    X = np.random.RandomState(3).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack([np.full(n, -0.15), np.full(n, -0.30), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_all_no_trade_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    for r in results:
        assert all(v == pytest.approx(0.15) for v in r["no_trade_saved_loss_values"])

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    assert metrics["no_trade_quality"]["saved_loss_r"] == pytest.approx(0.15)
