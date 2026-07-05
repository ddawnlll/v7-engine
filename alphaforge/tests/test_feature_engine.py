"""Tests for alphaforge.features.engine — multi-timeframe feature computation."""

import math
from alphaforge.features.engine import (
    compute_primary_features,
    compute_context_features,
    compute_refinement_features,
    compute_all_features,
    _rsi,
    _ema,
    _sma,
    _bollinger_position,
    _zscore,
)


def _candle(close: float, open_p: float = 0, high: float = 0, low: float = 0, volume: float = 1000.0, **kw) -> dict:
    return {"open": open_p or close, "high": high or close * 1.01, "low": low or close * 0.99, "close": close, "volume": volume, **kw}


def _uptrend(num: int = 30) -> list[dict]:
    return [_candle(100.0 + i * 0.5, volume=1000 + i * 10) for i in range(num)]


def _flat(num: int = 30) -> list[dict]:
    return [_candle(100.0, volume=1000.0) for _ in range(num)]


def _downtrend(num: int = 30) -> list[dict]:
    return [_candle(100.0 - i * 0.5, volume=1000 - i * 10) for i in range(num)]


# ── Pure helpers ───────────────────────────────────────────────────

class TestHelpers:
    def test_ema(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        ema3 = _ema(values, 3)
        assert ema3 > 0

    def test_sma(self):
        assert _sma([1, 2, 3, 4, 5], 3) == 4.0  # (3+4+5)/3

    def test_sma_short(self):
        assert _sma([1, 2], 5) == 2.0  # last value

    def test_rsi_all_gains(self):
        assert _rsi([100, 101, 102, 103, 104, 105], 5) == 100.0

    def test_rsi_all_losses(self):
        assert _rsi([105, 104, 103, 102, 101, 100], 5) == 0.0

    def test_rsi_flat(self):
        assert _rsi([100, 100, 100, 100, 100, 100], 5) == 50.0

    def test_bollinger_position(self):
        # price = sma → mid band
        assert abs(_bollinger_position(100, 100, 5) - 0.5) < 0.01
        # price = lower band (sma - 2*std)
        assert abs(_bollinger_position(90, 100, 5) - 0.0) < 0.01
        # price = upper band (sma + 2*std)
        assert abs(_bollinger_position(110, 100, 5) - 1.0) < 0.01

    def test_zscore(self):
        result = _zscore(10, [1, 2, 3, 4, 5, 10])
        assert result > 0


# ── Primary features ───────────────────────────────────────────────

class TestPrimaryFeatures:
    def test_uptrend_returns_features(self):
        candles = _uptrend(30)
        # Override last candle to have a real body
        candles[-1]["open"] = candles[-2]["close"]
        features = compute_primary_features(candles)
        assert len(features) > 10
        assert features["return_1"] > 0
        assert features["rsi_14"] > 50

    def test_downtrend(self):
        features = compute_primary_features(_downtrend(30))
        assert features["return_6"] < 0
        assert features["rsi_14"] < 50

    def test_flat_market(self):
        features = compute_primary_features(_flat(30))
        assert abs(features["return_1"]) < 0.001
        assert abs(features["rsi_14"] - 50) < 1

    def test_empty_returns_empty(self):
        assert compute_primary_features([]) == {}

    def test_single_candle(self):
        features = compute_primary_features([_candle(100.0)])
        assert features.get("return_1") is not None

    def test_all_expected_keys_present(self):
        features = compute_primary_features(_uptrend(60))
        expected = ["return_1", "return_2", "return_3", "return_6", "return_12", "return_24",
                     "log_return_1", "volatility_6", "volatility_12", "volatility_24",
                     "atr_14", "body_to_range_ratio", "upper_wick_ratio", "lower_wick_ratio",
                     "rsi_14", "ma_distance_20", "ma_distance_50", "ema_distance_20",
                     "bollinger_position", "volume_zscore_20"]
        for key in expected:
            assert key in features, f"Missing: {key}"


# ── Context features ───────────────────────────────────────────────

class TestContextFeatures:
    def test_uptrend(self):
        features = compute_context_features(_uptrend(60))
        assert features["context_return_3"] > 0
        assert features["context_trend_strength"] > 0

    def test_downtrend(self):
        features = compute_context_features(_downtrend(60))
        assert features["context_trend_strength"] < 0

    def test_empty(self):
        assert compute_context_features([]) == {}

    def test_range_compression(self):
        tight = _flat(30)
        features = compute_context_features(tight)
        assert features["context_range_compression"] <= 1.0


# ── Refinement features ────────────────────────────────────────────

class TestRefinementFeatures:
    def test_uptrend(self):
        features = compute_refinement_features(_uptrend(30))
        assert "refinement_return_1" in features
        assert features["refinement_micro_momentum"] > 0

    def test_empty(self):
        assert compute_refinement_features([]) == {}


# ── Combined pipeline ──────────────────────────────────────────────

class TestCombinedFeatures:
    def test_primary_only(self):
        result = compute_all_features(_uptrend(30))
        assert len(result["features"]) > 10
        assert result["metadata"]["primary_candles"] == 30
        assert result["metadata"]["context_candles"] == 0

    def test_all_timeframes(self):
        result = compute_all_features(
            _uptrend(30),
            context_ohlcv=_uptrend(60),
            refinement_ohlcv=_uptrend(120),
        )
        assert result["metadata"]["context_candles"] == 60
        assert result["metadata"]["refinement_candles"] == 120
        assert "context_return_3" in result["features"]
        assert "refinement_return_1" in result["features"]

    def test_version_passthrough(self):
        result = compute_all_features(_uptrend(30), feature_schema_version="feat-2.0.0")
        assert result["metadata"]["feature_schema_version"] == "feat-2.0.0"
