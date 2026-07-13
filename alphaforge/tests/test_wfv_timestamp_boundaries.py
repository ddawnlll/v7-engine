"""Timestamp-aware boundary tests for canonical walk-forward validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

from alphaforge.train import collect_metrics, evaluate_frozen_holdout, walk_forward_validate
from alphaforge.training.xgb_trainer import TrainingResult


def _mock_result() -> TrainingResult:
    model = MagicMock(spec=xgb.Booster)
    model.inplace_predict.side_effect = lambda matrix: np.tile(
        np.array([[0.7, 0.2, 0.1]], dtype=np.float64), (len(matrix), 1)
    )
    return TrainingResult(
        model=model,
        model_artifact={},
        model_binary_bytes=b"",
        train_metrics={"accuracy": 0.7, "logloss": 0.5},
        val_metrics={"accuracy": 0.6, "logloss": 0.6},
        training_duration_seconds=0.01,
    )


def test_panel_boundaries_use_unique_timestamps_not_row_count():
    """A 10-symbol panel purges 2x horizon time bars, not 2x horizon rows."""
    symbols_per_bar = 10
    n_bars = 200
    n = symbols_per_bar * n_bars
    timestamps = np.repeat(np.arange(n_bars, dtype=np.int64), symbols_per_bar)
    X = np.zeros((n, 3), dtype=np.float64)
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack((np.full(n, 0.01), np.zeros(n), np.zeros(n)))

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3,
            action_net_r=action_net_r, timestamps=timestamps,
        )

    assert results
    # SCALP horizon is 12 and k=2, therefore 24 *time* bars = 240 panel rows.
    assert {result["purge_bars"] for result in results} == {24}
    assert {result["embargo_bars"] for result in results} == {24}
    assert {result["purge_period"] for result in results} == {240}
    assert {result["embargo_period"] for result in results} == {240}


def test_metrics_preserve_compact_fold_evidence():
    """Saved reports retain enough per-fold data to audit a specialist."""
    metrics = collect_metrics(
        [{
            "fold": 1, "val_accuracy": 0.5, "train_accuracy": 0.6,
            "active_trade_count": 3, "n_val": 10, "net_r_expectancy": 0.02,
            "purge_bars": 24, "embargo_bars": 24,
            "long_count": 2, "short_count": 1, "no_trade_count": 7,
            "low_conf_count": 7,
        }],
        np.zeros((10, 2)), ["a", "b"],
    )
    assert metrics["fold_summaries"] == [{
        "fold": 1, "net_expectancy_r": 0.02, "active_trades": 3,
        "exposure_pct": 30.0, "purge_bars": 24, "embargo_bars": 24,
    }]


def test_decision_trace_carries_aligned_realization_timestamp():
    """Replay consumers receive a per-decision exit time, not a guessed one."""
    n = 400
    timestamps = np.arange(n, dtype=np.int64)
    exit_timestamps = timestamps + 12
    X = np.zeros((n, 3), dtype=np.float64)
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack((np.full(n, 0.01), np.zeros(n), np.zeros(n)))

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = _mock_result()
        results = walk_forward_validate(
            X, y, action_net_r[:, 0], "SCALP", min_folds=3,
            action_net_r=action_net_r, timestamps=timestamps,
            exit_timestamps=exit_timestamps, capture_decision_trace=True,
        )

    assert results
    assert results[0]["decision_exit_timestamps"]
    assert all(
        exit_ts == entry_ts + 12
        for entry_ts, exit_ts in zip(
            results[0]["decision_timestamps"],
            results[0]["decision_exit_timestamps"],
        )
    )


def test_frozen_holdout_purges_crossing_labels_and_traces_only_post_cutoff(tmp_path):
    """The pre-cutoff model cannot train on outcomes realized after cutoff."""
    n = 240
    base_ns = 1782864000000000000  # 2026-07-01T00:00:00Z
    timestamps = base_ns + np.arange(n, dtype=np.int64) * 1_000_000_000
    exits = timestamps + 12 * 1_000_000_000
    cutoff_index = 120
    cutoff = "2026-07-01T00:02:00Z"
    X = np.zeros((n, 3), dtype=np.float64)
    y = np.zeros(n, dtype=np.int32)
    action_net_r = np.column_stack((np.full(n, 0.01), np.zeros(n), np.zeros(n)))
    model = MagicMock(spec=xgb.Booster)
    model.inplace_predict.side_effect = lambda matrix: np.tile(
        np.array([[0.8, 0.1, 0.1]], dtype=np.float64), (len(matrix), 1)
    )
    training = _mock_result()
    training.model = model

    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as trainer_cls:
        trainer_cls.return_value.train.return_value = training
        result = evaluate_frozen_holdout(
            X, y, action_net_r, timestamps, exits,
            np.array(["BTCUSDT"] * n, dtype=object),
            mode="SCALP", cutoff=cutoff, trace_path=tmp_path / "holdout.jsonl",
        )

    # Entries 108..119 have outcomes after cutoff and must be purged.
    assert result["training_samples"] == cutoff_index - 12
    assert result["crossing_label_count_purged"] == 12
    assert result["holdout_samples"] == n - cutoff_index
    rows = [line for line in (tmp_path / "holdout.jsonl").read_text().splitlines() if line]
    assert len(rows) == n - cutoff_index
    assert all(int(__import__("json").loads(line)["timestamp"]) >= timestamps[cutoff_index] for line in rows)
    with pytest.raises(FileExistsError, match="already exists"):
        evaluate_frozen_holdout(
            X, y, action_net_r, timestamps, exits,
            np.array(["BTCUSDT"] * n, dtype=object),
            mode="SCALP", cutoff=cutoff, trace_path=tmp_path / "holdout.jsonl",
        )
