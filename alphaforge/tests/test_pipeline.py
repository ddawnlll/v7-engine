"""Tests for alphaforge.pipeline — end-to-end training pipeline."""

import json
from train_pipeline import run_pipeline


def _sim_input(symbol: str = "BTCUSDT", ts: str = "2025-01-01T12:00:00Z", **overrides) -> dict:
    # Clear uptrend candles to ensure unambiguous LONG_NOW labels
    candles = []
    for i in range(5):
        base = 50200 + i * 800
        candles.append({"open": base, "high": base + 600, "low": base - 200, "close": base + 400})

    base = {
        "symbol": symbol,
        "decision_timestamp": ts,
        "mode": "SWING",
        "primary_interval": "4h",
        "entry_price": 50000.0,
        "atr": 1000.0,
        "simulation_family_version": "simfam-1.0.0",
        "future_path": {"candles": candles},
        "profile": {
            "profile_version": "swing-1.0",
            "mode": "SWING",
            "primary_interval": "4h",
            "max_holding_bars": 30,
            "stop_multiplier": 2.0,
            "target_multiplier": 2.5,
            "ambiguity_margin_r": 0.20,
            "min_action_edge_r": 0.35,
            "no_trade_default": False,
        },
        "ohlcv": [
            {"close": 100.0 + i * 1.0, "open": 99.5 + i, "high": 100.5 + i, "low": 99.0 + i, "volume": 1000.0 + i * 10}
            for i in range(60)
        ],
    }
    base.update(overrides)
    return base


class TestRunPipeline:
    def test_pipeline_completes(self):
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT"]
        months = list(range(1, 13))
        inputs = []
        for sym in symbols:
            for m in months:
                inputs.append(_sim_input(sym, f"2025-{m:02d}-15T12:00:00Z"))
        result = run_pipeline(
            inputs,
            mode="SWING",
            fold_config={"min_train_days": 60, "train_window_days": 120, "val_window_days": 60},
            model_params={"classifier": {"n_estimators": 10}, "regressor": {"n_estimators": 10}},
        )
        assert result["status"] == "complete"
        assert result["num_folds"] >= 1
        assert result["model_bundles"]
        assert "evaluation" in result
        assert "trading" in result["evaluation"]

    def test_insufficient_data(self):
        result = run_pipeline([], mode="SWING")
        assert result["status"] in ("no_aligned_rows", "insufficient_data")
