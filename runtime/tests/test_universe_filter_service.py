"""Tests for runtime/services/universe_filter_service.py.

Covers: settings parsing, stop-hit detection, seeding, consecutive hits,
stop rate, cooldown, microstructure, and the disabled state.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from runtime.services.universe_filter_service import UniverseFilterService
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


# ── Test helpers ─────────────────────────────────────────────────────

@dataclass
class FakeOrder:
    payload_json: str = "{}"
    symbol: str = "BTCUSDT"
    profile_id: str = PAPER_PROFILE_ID
    status: str = "CLOSED"
    closed_at_utc: str = ""
    opened_at_utc: str = ""
    signal_id: str = ""


@dataclass
class FakeSignal:
    snapshot_json: str = "{}"


def fake_json(payload: dict) -> str:
    import json
    return json.dumps(payload)


def _make_service(settings_repo=None):
    return UniverseFilterService(settings_repo=settings_repo or MagicMock())


def _make_session_mock(rows: list | None = None):
    """Mock session for _evaluate_session.

    Chain: query(A, B).outerjoin(...).filter(...).filter(...).order_by(...).all()
    """
    session = MagicMock()
    if rows is not None:
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    else:
        session.query.return_value.outerjoin.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return session


# ── Settings parsing ─────────────────────────────────────────────────

class TestSettings:
    def test_defaults(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={})
        assert result["enabled"] is True
        assert result["rules"]["lookback_trades"] == 12
        assert result["rules"]["max_consecutive_stop_hits"] == 3
        assert result["rules"]["max_stop_hit_rate_pct"] == 70.0
        assert result["rules"]["cooldown_minutes"] == 240

    def test_disabled(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={"SYMBOL_THROTTLE_ENABLED": "false"})
        assert result["enabled"] is False
        # When disabled, symbols should not be throttled
        for item in result["items"]:
            assert item["throttled"] is False

    def test_custom_settings(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_LOOKBACK_TRADES": "20",
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "5",
            "SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT": "80.0",
            "SYMBOL_THROTTLE_COOLDOWN_MINUTES": "120",
        })
        assert result["rules"]["lookback_trades"] == 20
        assert result["rules"]["max_consecutive_stop_hits"] == 5
        assert result["rules"]["max_stop_hit_rate_pct"] == 80.0
        assert result["rules"]["cooldown_minutes"] == 120

    def test_enabled_truthy_values(self):
        service = _make_service()
        session = _make_session_mock()
        for val in ("1", "true", "yes", "on"):
            result = service._evaluate_session(session, settings={"SYMBOL_THROTTLE_ENABLED": val})
            assert result["enabled"] is True

    def test_enabled_falsy_values(self):
        service = _make_service()
        session = _make_session_mock()
        for val in ("0", "false", "no", "off", ""):
            result = service._evaluate_session(session, settings={"SYMBOL_THROTTLE_ENABLED": val})
            assert result["enabled"] is False


# ── Seeded throttling ───────────────────────────────────────────────

class TestSeeded:
    def test_seeded_symbol_throttled(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_SEEDED_SYMBOLS": "BTCUSDT,ETHUSDT",
        })
        symbols = {item["symbol"] for item in result["items"]}
        assert "BTCUSDT" in symbols
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["seeded"] is True
        assert "seeded_guardrail" in btc["active_rules"]
        assert btc["throttled"] is True

    def test_seeded_disabled_when_throttle_off(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_ENABLED": "false",
            "SYMBOL_THROTTLE_SEEDED_SYMBOLS": "BTCUSDT",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["seeded"] is True
        assert btc["throttled"] is False


# ── Consecutive stop hits ────────────────────────────────────────────

class TestConsecutiveStopHits:
    def test_consecutive_stops_trigger_throttle(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=1)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=2)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=3)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=(now - timedelta(hours=4)).isoformat(), symbol="BTCUSDT"), None),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "3",
            "SYMBOL_THROTTLE_LOOKBACK_TRADES": "10",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["consecutive_stop_hits"] == 3
        assert "consecutive_stop_hits" in btc["active_rules"]
        assert btc["throttled"] is True

    def test_consecutive_stops_below_threshold(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=1)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=(now - timedelta(hours=2)).isoformat(), symbol="BTCUSDT"), None),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "3",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["consecutive_stop_hits"] == 1  # only first order is HIT_SL, second breaks streak
        assert btc["throttled"] is False


# ── Rolling stop rate ────────────────────────────────────────────────

class TestStopRate:
    def test_high_stop_rate_triggers_throttle(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        # 4 out of 5 = 80% > 70% threshold
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=1)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=2)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=(now - timedelta(hours=3)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=4)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=5)).isoformat(), symbol="BTCUSDT"), None),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={})
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["stop_hits"] == 4
        assert btc["stop_hit_rate_pct"] >= 70.0
        assert "rolling_stop_rate" in btc["active_rules"]
        assert btc["throttled"] is True


# ── Cooldown ─────────────────────────────────────────────────────────

class TestCooldown:
    def test_cooldown_expired_does_not_throttle(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=300)).isoformat(), symbol="BTCUSDT"), None),
        ]
        session = _make_session_mock(orders)
        # Cooldown = 240 min, but last stop was 300 hours ago → cooldown expired
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "1",
            "SYMBOL_THROTTLE_COOLDOWN_MINUTES": "240",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["throttled"] is False
        assert btc["cooldown_remaining_minutes"] is None


# ── Multi-symbol ─────────────────────────────────────────────────────

class TestMultiSymbol:
    def test_multiple_symbols_independent(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        orders = [
            # BTC: 1 stop out of 3 trades = 33% stop rate (below 70%)
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=1)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=(now - timedelta(hours=2)).isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=(now - timedelta(hours=3)).isoformat(), symbol="BTCUSDT"), None),
            # ETH: 3 stops in a row (consecutive=3 > threshold=2)
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=1)).isoformat(), symbol="ETHUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=2)).isoformat(), symbol="ETHUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "HIT_SL"}), closed_at_utc=(now - timedelta(hours=3)).isoformat(), symbol="ETHUSDT"), None),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS": "2",
            "SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT": "70.0",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        eth = next(item for item in result["items"] if item["symbol"] == "ETHUSDT")
        assert btc["throttled"] is False   # 1 stop hit, below threshold
        assert eth["throttled"] is True    # 3 stops, exceeds threshold


# ── Microstructure ──────────────────────────────────────────────────

class TestMicrostructure:
    def test_no_signals_returns_empty_micro(self):
        service = _make_service()
        session = _make_session_mock()
        result = service._evaluate_session(session, settings={
            "SYMBOL_THROTTLE_SEEDED_SYMBOLS": "BTCUSDT",
        })
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["microstructure"]["samples"] == 0
        assert btc["microstructure"]["sweep_frequency"] == 0.0

    def test_microstructure_with_signals(self):
        signal = FakeSignal(snapshot_json=fake_json({
            "orderbook_spread_bps": 0.5,
            "orderbook_microprice_deviation_bps": 0.1,
            "trade_intensity": 2.0,
            "vol_ratio": 1.5,
            "bullish_sweep": True,
            "recent_high": 51000,
            "recent_low": 49000,
            "price": 50000,
        }))
        service = _make_service()
        now = datetime.now(timezone.utc)
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), symbol="BTCUSDT", closed_at_utc=now.isoformat()), signal),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={})
        btc = next(item for item in result["items"] if item["symbol"] == "BTCUSDT")
        assert btc["microstructure"]["samples"] == 1
        assert btc["microstructure"]["avg_spread_bps"] == 0.5
        assert btc["microstructure"]["sweep_frequency"] > 0


# ── Requested symbols ────────────────────────────────────────────────

class TestRequestedSymbols:
    def test_filters_to_requested_symbols_only(self):
        service = _make_service()
        now = datetime.now(timezone.utc)
        # BTC has no stop hits, ETH is filtered out entirely
        orders = [
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=now.isoformat(), symbol="BTCUSDT"), None),
            (FakeOrder(payload_json=fake_json({"close_reason": "TP_HIT"}), closed_at_utc=now.isoformat(), symbol="ETHUSDT"), None),
        ]
        session = _make_session_mock(orders)
        result = service._evaluate_session(session, settings={}, symbols=["BTCUSDT"])
        symbols = {item["symbol"] for item in result["items"]}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" not in symbols


# ── No orders ────────────────────────────────────────────────────────

class TestNoOrders:
    def test_empty_orders(self):
        service = _make_service()
        session = _make_session_mock([])
        result = service._evaluate_session(session, settings={})
        assert result["total_symbols"] == 0
        assert result["total_throttled"] == 0
