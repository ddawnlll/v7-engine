"""
Tests for lib/market_data/contracts.py
"""

import math
from typing import Any

from lib.market_data.contracts import KlineRecord, MarketDataResult, DataQualityReport


def _make_kline(
    symbol: str = "BTCUSDT",
    timestamp: int = 1_000_000_000_000,
    **overrides: Any,
) -> KlineRecord:
    params: dict[str, Any] = dict(
        symbol=symbol,
        timestamp=timestamp,
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0,
        quote_volume=5_000_000.0,
        trade_count=1000,
        taker_buy_volume=55.0,
        taker_buy_quote_volume=2_750_000.0,
        interval="1h",
        source="binance",
        is_closed=True,
    )
    params.update(overrides)
    return KlineRecord(**params)


class TestKlineRecord:
    def test_basic_creation(self):
        r = _make_kline()
        assert r.symbol == "BTCUSDT"
        assert r.close == 50500.0
        assert r.interval == "1h"
        assert r.source == "binance"
        assert r.is_closed is True

    def test_zero_values(self):
        r = _make_kline(open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0)
        assert r.open == 0.0
        assert r.volume == 0.0

    def test_negative_values(self):
        r = _make_kline(close=-1.0)
        assert r.close == -1.0

    def test_large_values(self):
        r = _make_kline(
            open=1e8, high=1e8, low=1e8, close=1e8,
            volume=1e12, quote_volume=1e20,
            trade_count=2_000_000_000,
        )
        assert r.open == 1e8
        assert r.trade_count == 2_000_000_000

    def test_not_closed(self):
        r = _make_kline(is_closed=False)
        assert r.is_closed is False

    def test_custom_symbol_and_interval(self):
        r = _make_kline(symbol="ETHUSDT", interval="15m")
        assert r.symbol == "ETHUSDT"
        assert r.interval == "15m"


class TestMarketDataResult:
    def test_creation(self):
        records = [_make_kline(timestamp=1_000_000_000_000 + i * 3600_000) for i in range(5)]
        quality = DataQualityReport(
            total_expected=5, total_received=5,
            gap_count=0, duplicate_count=0,
            is_complete=True,
        )
        result = MarketDataResult(symbol="BTCUSDT", interval="1h", records=records, quality=quality)
        assert result.symbol == "BTCUSDT"
        assert len(result.records) == 5
        assert result.quality.is_complete

    def test_empty_records(self):
        quality = DataQualityReport(
            total_expected=0, total_received=0,
            gap_count=0, is_complete=True,
        )
        result = MarketDataResult(symbol="ETHUSDT", interval="1h", records=[], quality=quality)
        assert result.records == []
        assert result.quality.total_received == 0


class TestDataQualityReport:
    def test_creation(self):
        q = DataQualityReport(
            total_expected=100, total_received=98,
            gap_count=2, duplicate_count=1,
            is_complete=False,
            warnings=["Gaps found", "Duplicates found"],
        )
        assert q.total_expected == 100
        assert q.gap_count == 2
        assert q.is_complete is False
        assert len(q.warnings) == 2

    def test_default_values(self):
        q = DataQualityReport(total_expected=10, total_received=10)
        assert q.gap_count == 0
        assert q.duplicate_count == 0
        assert q.is_complete is True
        assert q.warnings == []

    def test_empty_warnings(self):
        q = DataQualityReport(total_expected=0, total_received=0)
        assert q.warnings == []
