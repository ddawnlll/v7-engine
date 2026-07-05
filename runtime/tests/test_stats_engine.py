"""Tests for runtime/services/stats_engine.py.

Layer 1: Pure functions (_confidence_band, _as_float, _aggregate)
Layer 2: _closed_orders (mock repos + cache)
Layer 3: get_confidence_weights (mock _closed_orders)
Layer 4: get_learning_multiplier (mock _closed_orders)
Layer 5: calculate_stats (mock _closed_orders + cache)
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

from runtime.services import stats_engine


# ── Helpers ──────────────────────────────────────────────────────────

def _clear_caches():
    stats_engine._STATS_CACHE["ts"] = 0.0
    stats_engine._STATS_CACHE["stats"] = None
    stats_engine._ORDERS_CACHE.clear()
    stats_engine._CONFIDENCE_WEIGHTS_CACHE.clear()


def _order(
    realized_r: float = 0.0,
    symbol: str = "BTCUSDT",
    interval: str = "4h",
    mode: str = "SWING",
    direction: str = "LONG",
    regime: str = "TRENDING",
    confidence: float = 50.0,
    status: str = "CLOSED",
    source: str = "auto",
    factors: list[dict] | None = None,
) -> dict[str, Any]:
    """Produce an enriched order dict matching _closed_orders() output format."""
    return {
        "symbol": symbol,
        "interval": interval,
        "mode": mode,
        "direction": direction,
        "confidence": confidence,
        "status": status,
        "source": source,
        "realized_r": realized_r,
        "regime": regime,
        "factors": factors or [],
        "confidence_band": stats_engine._confidence_band(confidence),
    }


# ── _confidence_band ─────────────────────────────────────────────────

class TestConfidenceBand:
    """_confidence_band maps a float to a bucket string."""

    def test_below_40(self):
        assert stats_engine._confidence_band(0.0) == "0-40"
        assert stats_engine._confidence_band(39.9) == "0-40"

    def test_40_to_60(self):
        assert stats_engine._confidence_band(40.0) == "40-60"
        assert stats_engine._confidence_band(59.9) == "40-60"

    def test_60_to_80(self):
        assert stats_engine._confidence_band(60.0) == "60-80"
        assert stats_engine._confidence_band(79.9) == "60-80"

    def test_80_and_above(self):
        assert stats_engine._confidence_band(80.0) == "80-100"
        assert stats_engine._confidence_band(100.0) == "80-100"
        assert stats_engine._confidence_band(999.0) == "80-100"

    def test_none_or_zero(self):
        assert stats_engine._confidence_band(0) == "0-40"
        assert stats_engine._confidence_band(None) == "0-40"  # type: ignore

    def test_negative(self):
        assert stats_engine._confidence_band(-5.0) == "0-40"


# ── _aggregate ───────────────────────────────────────────────────────

class TestAggregate:
    """_aggregate computes summary stats from a list of orders."""

    def test_empty_orders(self):
        result = stats_engine._aggregate([])
        assert result["count"] == 0
        assert result["winrate"] == 0.0
        assert result["net_r"] == 0.0
        assert result["profit_factor"] == 0.0

    def test_all_wins(self):
        orders = [_order(r) for r in [0.5, 1.0, 2.0]]
        result = stats_engine._aggregate(orders)
        assert result["count"] == 3
        assert result["wins"] == 3
        assert result["losses"] == 0
        assert result["winrate"] == 100.0
        assert result["net_r"] == 3.5
        assert result["profit_factor"] == 3.5  # no gross_loss → profit = gross

    def test_all_losses(self):
        orders = [_order(r) for r in [-0.5, -1.0, -2.0]]
        result = stats_engine._aggregate(orders)
        assert result["count"] == 3
        assert result["wins"] == 0
        assert result["losses"] == 3
        assert result["winrate"] == 0.0
        assert result["net_r"] == -3.5

    def test_mixed_wins_and_losses(self):
        orders = [_order(r) for r in [1.0, -0.5, 0.5, -1.0, 2.0]]
        result = stats_engine._aggregate(orders)
        assert result["count"] == 5
        assert result["wins"] == 3
        assert result["losses"] == 2
        assert result["winrate"] == 60.0
        assert result["net_r"] == 2.0  # 3.5 - 1.5

    def test_profit_factor_no_losses(self):
        orders = [_order(r) for r in [1.0, 2.0]]
        result = stats_engine._aggregate(orders)
        assert result["profit_factor"] == 3.0  # gross_profit only

    def test_profit_factor_equal_wins_losses(self):
        orders = [_order(r) for r in [1.0, -1.0]]
        result = stats_engine._aggregate(orders)
        assert result["profit_factor"] == 1.0

    def test_avg_win_and_avg_loss(self):
        orders = [_order(r) for r in [2.0, 4.0, -1.0, -3.0]]
        result = stats_engine._aggregate(orders)
        assert result["avg_win"] == 3.0  # (2+4)/2
        assert result["avg_loss"] == 2.0  # (1+3)/2

    def test_single_order(self):
        orders = [_order(0.5)]
        result = stats_engine._aggregate(orders)
        assert result["count"] == 1
        assert result["winrate"] == 100.0
        assert result["avg_r"] == 0.5

    def test_zero_realized_r_counts_as_loss(self):
        orders = [_order(0.0)]
        result = stats_engine._aggregate(orders)
        assert result["wins"] == 0
        assert result["losses"] == 1


# ── _closed_orders ─────────────────────────────────────────────────

def _raw_order(
    realized_r: float = 0.0,
    symbol: str = "BTCUSDT",
    confidence: float = 50.0,
    status: str = "CLOSED",
) -> dict[str, Any]:
    """Raw order format — payload is already a dict (SQLAlchemy JSON col deserialized)."""
    return {
        "symbol": symbol,
        "interval": "4h",
        "mode": "SWING",
        "direction": "LONG",
        "confidence": confidence,
        "status": status,
        "source": "auto",
        "signal_id": None,
        "payload": {"realized_r": realized_r, "signal": {"regime": "TRENDING", "summary": f"{symbol} test"}},
    }


class TestClosedOrders:
    """_closed_orders fetches from repos and caches."""

    def _mock_repos(self, return_orders: list[dict] | None = None):
        if return_orders is None:
            return_orders = []
        order_repo = MagicMock()
        order_repo.list_orders.return_value = return_orders
        signal_repo = MagicMock()
        return order_repo, signal_repo

    def test_empty(self):
        _clear_caches()
        repo, signal_repo = self._mock_repos([])
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__.return_value = MagicMock()
            result = stats_engine._closed_orders()
        assert result == []

    def test_with_data(self):
        _clear_caches()
        orders = [
            _raw_order(0.5, symbol="BTCUSDT"),
            _raw_order(-0.3, symbol="ETHUSDT"),
        ]
        repo, signal_repo = self._mock_repos(orders)
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__.return_value = MagicMock()
            result = stats_engine._closed_orders()
        assert len(result) == 2
        assert result[0]["symbol"] == "BTCUSDT"
        assert result[0]["realized_r"] == 0.5
        assert result[0]["confidence_band"] == "40-60"

    def test_cache_hit(self):
        _clear_caches()
        repo, signal_repo = self._mock_repos([_raw_order(1.0)])
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__.return_value = MagicMock()
            first = stats_engine._closed_orders()
        repo2, signal_repo2 = self._mock_repos([])
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo2),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo2),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
        ):
            second = stats_engine._closed_orders()
        assert len(second) == 1
        repo2.list_orders.assert_not_called()

    def test_filters_open_orders(self):
        _clear_caches()
        orders = [
            _raw_order(0.5, status="CLOSED"),
            _raw_order(0.5, status="OPEN"),
        ]
        repo, signal_repo = self._mock_repos(orders)
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__.return_value = MagicMock()
            result = stats_engine._closed_orders()
        assert len(result) == 1

    def test_cache_ttl_expiry(self):
        _clear_caches()
        repo, signal_repo = self._mock_repos([_raw_order(1.0)])
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__.return_value = MagicMock()
            first = stats_engine._closed_orders()

        fresh_time = time.time() + 31.0
        repo2, signal_repo2 = self._mock_repos([_raw_order(2.0)])
        with (
            patch("runtime.services.stats_engine.OrderRepository", return_value=repo2),
            patch("runtime.services.stats_engine.SignalRepository", return_value=signal_repo2),
            patch("runtime.services.stats_engine.get_database_url", return_value="sqlite://"),
            patch("runtime.services.stats_engine.session_scope") as mock_scope2,
            patch("runtime.services.stats_engine.time") as mock_time,
        ):
            mock_time.time.return_value = fresh_time
            mock_scope2.return_value.__enter__.return_value = MagicMock()
            second = stats_engine._closed_orders()
        assert len(second) == 1
        assert second[0]["realized_r"] == 2.0


# ── calculate_stats ─────────────────────────────────────────────────

class TestCalculateStats:
    def test_no_orders(self):
        _clear_caches()
        with patch("runtime.services.stats_engine._closed_orders", return_value=[]):
            result = stats_engine.calculate_stats()
        assert result["total"] == 0
        assert "No resolved trades" in result["message"]

    def test_with_orders(self):
        _clear_caches()
        orders = [
            _order(1.0, symbol="BTCUSDT", mode="SWING", regime="TRENDING", direction="LONG", confidence=70.0),
            _order(-0.5, symbol="ETHUSDT", mode="SWING", regime="TRENDING", direction="SHORT", confidence=50.0),
            _order(2.0, symbol="BTCUSDT", mode="SCALP", regime="RANGING", direction="LONG", confidence=85.0),
        ]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.calculate_stats()

        assert result["resolved"] == 3
        global_stats = result["global"]
        assert global_stats["winrate"] == 66.67  # 2/3
        assert global_stats["net_r"] == 2.5

        # Groupings exist
        assert "BTCUSDT" in result["by_symbol"]
        assert "SWING" in result["by_mode"]
        assert "TRENDING" in result["by_regime"]

    def test_cache_hit(self):
        _clear_caches()
        with patch("runtime.services.stats_engine._closed_orders", return_value=[_order(1.0)]):
            first = stats_engine.calculate_stats()

        with patch("runtime.services.stats_engine._closed_orders", return_value=[]) as mock_co:
            second = stats_engine.calculate_stats()
        assert second["resolved"] == 1  # from cache, not empty
        mock_co.assert_not_called()

    def test_cache_ttl(self):
        _clear_caches()
        with patch("runtime.services.stats_engine._closed_orders", return_value=[_order(1.0)]):
            first = stats_engine.calculate_stats()

        fresh_time = time.time() + 11.0  # past 10s TTL
        with (
            patch("runtime.services.stats_engine._closed_orders", return_value=[_order(2.0)]) as mock_co,
            patch("runtime.services.stats_engine.time") as mock_time,
        ):
            mock_time.time.return_value = fresh_time
            second = stats_engine.calculate_stats()
        assert second["global"]["net_r"] == 2.0  # fresh data
        mock_co.assert_called_once()


# ── get_learning_multiplier ─────────────────────────────────────────

class TestGetLearningMultiplier:
    def test_no_orders(self):
        _clear_caches()
        with patch("runtime.services.stats_engine._closed_orders", return_value=[]):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "4h", "TRENDING", "SWING", "LONG", 50.0)
        assert result["multiplier"] == 1.0
        assert result["scope"] == "none"

    def test_exact_scope_strong_performance(self):
        _clear_caches()
        # 5 orders matching EXACT scope with win_rate >= 65 and pf >= 1.4 → multiplier 1.2
        orders = [_order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "4h", "TRENDING", "SWING", "LONG", 55.0)
        assert result["multiplier"] == 1.2
        assert result["scope"] == "EXACT"
        assert result["sample_size"] == 5

    def test_exact_scope_poor_performance(self):
        _clear_caches()
        orders = [_order(-1.0, symbol="BTCUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "4h", "TRENDING", "SWING", "LONG", 55.0)
        assert result["multiplier"] == 0.75
        assert result["scope"] == "EXACT"

    def test_falls_back_to_regime_scope(self):
        _clear_caches()
        # Mix of symbols/modes/intervals — no 5+ EXACT matches, but 5+ REGIME matches
        orders = [
            _order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0),
            _order(1.0, symbol="ETHUSDT", interval="1h", mode="SWING", direction="SHORT", regime="TRENDING", confidence=55.0),
            _order(1.0, symbol="SOLUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0),
            _order(1.0, symbol="DOGEUSDT", interval="1h", mode="SWING", direction="SHORT", regime="TRENDING", confidence=55.0),
            _order(1.0, symbol="ADAUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0),
        ]
        # Request a combo not in exact (e.g., different interval)
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "15m", "TRENDING", "SWING", "LONG", 55.0)
        assert result["scope"] == "REGIME"
        assert result["multiplier"] >= 1.0  # all wins → strong

    def test_empty_factors_not_included(self):
        """Factors list can be None or empty — should not crash."""
        _clear_caches()
        orders = [_order(1.0, symbol="BTCUSDT") for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "4h", "TRENDING", "SWING", "LONG", 55.0)
        assert result["scope"] == "EXACT"

    def test_moderate_performance_multiplier_1_1(self):
        _clear_caches()
        # 3 wins (0.5 each) + 2 losses (0.6 each)
        # wr = 60% (>=58), pf = 1.5/1.2 = 1.25 (>=1.1) → multiplier 1.1
        wins = [_order(0.5, symbol="BTCUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0) for _ in range(3)]
        losses = [_order(-0.6, symbol="BTCUSDT", interval="4h", mode="SWING", direction="LONG", regime="TRENDING", confidence=55.0) for _ in range(2)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=wins + losses):
            result = stats_engine.get_learning_multiplier("BTCUSDT", "4h", "TRENDING", "SWING", "LONG", 55.0)
        assert result["multiplier"] == 1.1
        assert result["scope"] == "EXACT"


# ── get_confidence_weights ──────────────────────────────────────────

class TestGetConfidenceWeights:
    def test_insufficient_data(self):
        _clear_caches()
        # Only 4 orders — not enough (need 5)
        orders = [_order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", regime="TRENDING") for _ in range(4)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_confidence_weights("BTCUSDT", "4h", "TRENDING", "SWING")
        assert result is None

    def test_no_factors_returns_none(self):
        _clear_caches()
        orders = [_order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", regime="TRENDING", factors=[]) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_confidence_weights("BTCUSDT", "4h", "TRENDING", "SWING")
        assert result is None

    def test_returns_normalized_weights(self):
        _clear_caches()
        factors = [
            {"role": "TREND", "score": 0.8, "weight": 1.0, "used": True},
            {"role": "STRUCTURE", "score": 0.8, "weight": 1.0, "used": True},
        ]
        orders = [_order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", regime="TRENDING", factors=factors) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_confidence_weights("BTCUSDT", "4h", "TRENDING", "SWING")
        assert result is not None
        assert "trend" in result
        assert "structure" in result
        assert "momentum" in result
        assert "volume" in result
        # All positive, normalized to sum ~1.0
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01

    def test_unused_factors_excluded(self):
        _clear_caches()
        factors = [
            {"role": "TREND", "score": 0.8, "weight": 1.0, "used": True},
            {"role": "MOMENTUM", "score": 0.9, "weight": 1.0, "used": False},  # unused
        ]
        orders = [_order(1.0, symbol="BTCUSDT", interval="4h", mode="SWING", regime="TRENDING", factors=factors) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_confidence_weights("BTCUSDT", "4h", "TRENDING", "SWING")
        assert result is not None
        assert result["momentum"] == 0.0  # No contribution from unused factor

    def test_negative_realized_r_does_not_contribute(self):
        _clear_caches()
        factors = [{"role": "TREND", "score": 1.0, "weight": 1.0, "used": True}]
        orders = [_order(-1.0, symbol="BTCUSDT", interval="4h", mode="SWING", regime="TRENDING", factors=factors) for _ in range(5)]
        with patch("runtime.services.stats_engine._closed_orders", return_value=orders):
            result = stats_engine.get_confidence_weights("BTCUSDT", "4h", "TRENDING", "SWING")
        # All orders lost money → max(0, realized_r) = 0 → all scores 0 → no weights
        assert result is None


# ── Module-level cleanup ─────────────────────────────────────────────

def teardown_module():
    _clear_caches()
