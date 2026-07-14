"""Tests for the cost-stress sweep (G3) instrumentation in collect_metrics.

The stress sweep applies an ADDITIONAL (multiplier - 1) * base_cost on top of
the base round-trip cost already deducted by the label generator — it must
not double-count or ignore the existing cost accounting.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.train import _ROUND_TRIP_COST_FRACTIONAL, collect_metrics, walk_forward_validate
from alphaforge.training.xgb_trainer import TrainingResult


def _mock_confident_long_result() -> TrainingResult:
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


def test_cost_stress_survives_at_1x_and_fails_at_high_multiplier():
    n = 600
    X = np.random.RandomState(9).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    # Small edge: +0.005R per active LONG trade after base cost.
    action_net_r = np.column_stack([np.full(n, 0.005), np.zeros(n), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_confident_long_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    stress = metrics["cost_stress"]
    assert stress["available"] is True
    assert stress["expectancy_r_by_multiplier"]["1.0x"] == pytest.approx(0.005, abs=1e-6)
    # Extra cost at 3x = 2 * 0.0008 = 0.0016; edge (0.005) survives that.
    assert stress["expectancy_r_by_multiplier"]["3.0x"] == pytest.approx(
        0.005 - 2 * _ROUND_TRIP_COST_FRACTIONAL, abs=1e-6
    )
    assert stress["max_multiplier_survived"] == 3.0


def test_cost_stress_edge_dies_under_stress_when_tiny():
    n = 600
    X = np.random.RandomState(10).normal(size=(n, 3))
    y = np.zeros(n, dtype=np.int32)
    # Tiny edge that base cost math (already deducted) leaves at +0.0005R —
    # doubling the round-trip cost (extra 0.0008 at 2x) should flip it negative.
    action_net_r = np.column_stack([np.full(n, 0.0005), np.zeros(n), np.zeros(n)])

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_confident_long_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3, action_net_r=action_net_r,
        )

    metrics = collect_metrics(results, X, feature_names=["f0", "f1", "f2"], mode="SCALP")
    stress = metrics["cost_stress"]
    assert stress["expectancy_r_by_multiplier"]["1.0x"] > 0
    assert stress["expectancy_r_by_multiplier"]["2.0x"] < 0
    # extra_cost(1.5x) = 0.5 * 0.0008 = 0.0004 -> 0.0005 - 0.0004 = 0.0001 > 0 (survives)
    # extra_cost(2.0x) = 1.0 * 0.0008 = 0.0008 -> 0.0005 - 0.0008 < 0 (fails)
    assert stress["max_multiplier_survived"] == 1.5
