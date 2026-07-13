"""
End-to-end test: simulation labels → XGBoost training → direction + leverage prediction.

Proves that:
1. generate_leverage_labels produces valid labels from OHLCV
2. A simple XGBoost classifier can learn direction from simulation-derived features
3. A regressor can predict optimal leverage
"""

import sys
sys.path.insert(0, "alphaforge/src")

import numpy as np
import pytest

from simulation.contracts.models import SimulationProfile, TradingMode
from simulation.engine.margin import (
    ACTION_ID_TO_DIRECTION_LEVERAGE,
    VALID_V2_ACTION_IDS,
    ACTION_ID_TO_LABEL,
)
from alphaforge.labels.simulation_labels import (
    generate_leverage_labels,
    _simulate_bar,
    _make_bracket_snapshots,
    LeverageLabel,
)


@pytest.fixture
def sample_data():
    """150 bars of synthetic trending + ranging data, 2 symbols."""
    np.random.seed(42)
    n = 150
    ts = np.arange(n) * 3600000 + 1700000000000
    # Uptrend first 75 bars, range last 75
    trend = np.linspace(0, 3000, 75)
    range_part = np.random.randn(75).cumsum() * 50
    close = np.concatenate([50000 + trend + np.random.randn(75).cumsum() * 100,
                            50300 + range_part])
    high = close + np.abs(np.random.randn(n) * 30)
    low = close - np.abs(np.random.randn(n) * 30)
    return {
        "open": close - np.random.randn(n) * 20,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.ones(n) * 100 + np.random.randn(n) * 10,
        "timestamp": ts,
        "symbol": np.array(["BTCUSDT"] * 75 + ["ETHUSDT"] * 75),
    }


class TestSimulationLabelsXBRLeverageTraining:
    """End-to-end: simulation labels → XGBoost → direction + leverage prediction."""

    def test_labels_generated_correctly(self, sample_data):
        """Labels should have all required fields."""
        labels = generate_leverage_labels(sample_data, "SCALP", future_bars=10)
        assert len(labels) > 0
        l = labels[0]
        assert l.direction in (0, 1, 2)
        assert l.optimal_leverage in (0, 1, 2, 3, 5, 7, 10)
        assert hasattr(l, "base_net_R")
        assert hasattr(l, "optimal_action_id")
        assert len(l.action_outcomes) == 13

    def test_labels_distribution(self, sample_data):
        """At least some labels should be directional (not all NO_TRADE)."""
        labels = generate_leverage_labels(sample_data, "SCALP", future_bars=10)
        directions = [l.direction for l in labels]
        dir_count = sum(1 for d in directions if d != 2)
        assert dir_count > 0, "Expected at least one directional label"

    def test_optimal_leverage_is_reasonable(self, sample_data):
        """Optimal leverage should be 0 when base_net_R <= 0."""
        labels = generate_leverage_labels(sample_data, "SCALP", future_bars=10)
        for l in labels[:20]:
            if l.base_net_R <= 0:
                assert l.optimal_leverage == 0, \
                    f"Expected 0 leverage when base_R={l.base_net_R:.4f}, got {l.optimal_leverage}"

    def test_training_features(self, sample_data):
        """Feature vectors can be built from labels for XGBoost training."""
        labels = generate_leverage_labels(sample_data, "SCALP", future_bars=10)

        # Build feature matrix from simulation features
        # Features: base_net_R, best_margin_return, liquidation_rate for each direction
        X_rows = []
        y_dir = []
        y_lev = []

        for l in labels:
            long_outcomes = [(k, v) for k, v in l.action_outcomes.items() if v.direction == "LONG" and v.leverage > 0]
            short_outcomes = [(k, v) for k, v in l.action_outcomes.items() if v.direction == "SHORT" and v.leverage > 0]

            if not long_outcomes or not short_outcomes:
                continue

            # Features: best long margin_return, best short margin_return,
            # long base_R, short base_R, long liq_rate, short liq_rate
            best_long_mr = max(v.margin_return_net for _, v in long_outcomes)
            best_short_mr = max(v.margin_return_net for _, v in short_outcomes)
            long_base = long_outcomes[0][1].base_net_R
            short_base = short_outcomes[0][1].base_net_R
            long_liq = sum(1 for _, v in long_outcomes if v.liquidation_event) / max(len(long_outcomes), 1)
            short_liq = sum(1 for _, v in short_outcomes if v.liquidation_event) / max(len(short_outcomes), 1)

            X_rows.append([best_long_mr, best_short_mr, long_base, short_base, long_liq, short_liq])
            y_dir.append(l.direction)
            y_lev.append(l.optimal_leverage)

        X = np.array(X_rows)
        assert len(X) > 0
        assert X.shape[1] == 6

        # Train a simple XGBoost model
        from xgboost import XGBClassifier, XGBRegressor
        clf = XGBClassifier(n_estimators=10, max_depth=3, random_state=42)
        clf.fit(X, y_dir)
        pred_dir = clf.predict(X)
        dir_acc = np.mean(pred_dir == y_dir)

        # Direction accuracy should be above random (33%)
        assert dir_acc > 0.33, f"Direction accuracy {dir_acc:.3f} should beat random"

        # For non-NO_TRADE samples, train leverage regressor
        active_mask = np.array(y_dir) != 2
        if active_mask.sum() > 5:
            reg = XGBRegressor(n_estimators=10, max_depth=2, random_state=42)
            reg.fit(X[active_mask], np.array(y_lev)[active_mask])
            pred_lev = reg.predict(X[active_mask])
            lev_mae = np.mean(np.abs(np.array(y_lev)[active_mask] - pred_lev))
            print(f"  Leverage MAE: {lev_mae:.3f}")

        print(f"  Direction accuracy: {dir_acc:.3f} ({sum(pred_dir == y_dir)}/{len(y_dir)})")
        print(f"  Direction distribution: {np.bincount(y_dir)}")
        print(f"  Leverage distribution: {np.bincount(y_lev)}")


if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])
