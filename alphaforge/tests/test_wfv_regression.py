"""Walk-forward validation tests for the regression (reg:squarederror) objective.

Before this, ``--regression-objective`` was never fold-validated at all: the
final model was trained once on the full fit-set with a single non-purged
chronological split. These tests confirm walk_forward_validate(...,
regression_objective=True) now runs the SAME purge/embargo fold boundaries
as the classifier path, and reports MAE/RMSE/sign-correctness per fold.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.train import collect_regression_metrics, walk_forward_validate
from alphaforge.training.xgb_trainer import TrainingResult


def _mock_regression_result(predicted_value: float = 0.01) -> TrainingResult:
    model = MagicMock(spec=xgb.Booster)
    model.inplace_predict.side_effect = lambda matrix: np.full(
        len(matrix), predicted_value, dtype=np.float64
    )
    return TrainingResult(
        model=model,
        model_artifact={},
        model_binary_bytes=b"",
        train_metrics={"mse": 0.001, "rmse": 0.03},
        val_metrics={"mse": 0.001, "rmse": 0.03},
        training_duration_seconds=0.01,
    )


def _panel(n: int = 2000, n_features: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.RandomState(7)
    X = rng.normal(size=(n, n_features))
    net_r = rng.normal(loc=0.01, scale=0.05, size=n)
    y_int_unused = np.zeros(n, dtype=np.int32)
    return X, y_int_unused, net_r


def test_regression_objective_trains_reg_squarederror_per_fold():
    X, y_int, net_r = _panel()
    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_regression_result()
        results = walk_forward_validate(
            X, y_int, net_r, "SCALP", min_folds=3, regression_objective=True,
        )

    assert results
    for r in results:
        assert "val_mae" in r
        assert "val_rmse" in r
        assert "sign_correct_pct" in r
        assert "val_accuracy" not in r  # classifier-only key must not leak in

    # Every fold must have constructed the trainer with the regression objective.
    for call in trainer_cls.call_args_list:
        assert call.kwargs.get("objective") == "reg:squarederror"


def test_regression_objective_respects_same_purge_embargo_as_classifier():
    """The regression path must reuse the same fold-boundary computation —
    not skip purge/embargo like the pre-fix single full-set split did."""
    symbols_per_bar = 5
    n_bars = 400
    n = symbols_per_bar * n_bars
    timestamps = np.repeat(np.arange(n_bars, dtype=np.int64), symbols_per_bar)
    rng = np.random.RandomState(3)
    X = rng.normal(size=(n, 3))
    net_r = rng.normal(loc=0.01, scale=0.05, size=n)
    y_int_unused = np.zeros(n, dtype=np.int32)

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_regression_result()
        results = walk_forward_validate(
            X, y_int_unused, net_r, "SCALP", min_folds=3,
            regression_objective=True, timestamps=timestamps,
        )

    assert results
    # SCALP horizon is 12 and k=2, therefore 24 *time* bars purge/embargo —
    # identical boundary semantics to the classifier path (see
    # test_wfv_timestamp_boundaries.py::test_panel_boundaries_use_unique_timestamps_not_row_count).
    assert {r["purge_bars"] for r in results} == {24}
    assert {r["embargo_bars"] for r in results} == {24}


def test_regression_mae_rmse_reflect_prediction_error():
    n = 1500
    rng = np.random.RandomState(11)
    X = rng.normal(size=(n, 3))
    net_r = np.full(n, 0.05)  # constant true R
    y_int_unused = np.zeros(n, dtype=np.int32)

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_regression_result(predicted_value=0.02)
        results = walk_forward_validate(
            X, y_int_unused, net_r, "SCALP", min_folds=3, regression_objective=True,
        )

    assert results
    for r in results:
        # |0.05 - 0.02| = 0.03 exactly, constant across all validation rows.
        assert r["val_mae"] == pytest.approx(0.03, abs=1e-9)
        assert r["val_rmse"] == pytest.approx(0.03, abs=1e-9)
        # Both true and predicted R are positive -> sign always matches.
        assert r["sign_correct_pct"] == pytest.approx(100.0)


def test_collect_regression_metrics_aggregates_folds():
    fold_results = [
        {"val_mae": 0.02, "val_rmse": 0.03, "sign_correct_pct": 60.0, "n_train": 100, "n_val": 50, "net_r_expectancy": 0.01},
        {"val_mae": 0.04, "val_rmse": 0.05, "sign_correct_pct": 40.0, "n_train": 200, "n_val": 50, "net_r_expectancy": -0.01},
    ]
    metrics = collect_regression_metrics(fold_results, feature_names=["f0", "f1"])

    assert metrics["objective"] == "reg:squarederror"
    assert metrics["val_mae"] == pytest.approx(0.03)
    assert metrics["val_rmse"] == pytest.approx(0.04)
    assert metrics["sign_correct_pct"] == pytest.approx(50.0)
    assert metrics["n_folds"] == 2
    assert metrics["feature_count"] == 2
    assert metrics["fold_maes"] == [0.02, 0.04]
