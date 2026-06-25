"""
Integration test: funding market-data fetch → pagination → cost adapter.

Verifies the end-to-end path from FundingService (with time-range
pagination) through to the funding_cost_r function, using mocked
Binance API responses. No real network calls.
"""

from unittest.mock import Mock

import pytest

from lib.market_data.binance.funding_service import (
    FUNDING_INTERVAL_MS,
    MAX_LIMIT,
    FundingService,
)
from simulation.engine.funding import funding_cost_r

# Arbitrary base timestamp (ms)
TS_BASE = 1_700_000_000_000


def _make_raw_record(timestamp: int, rate: float = 0.0001) -> list:
    return [timestamp, str(rate)]


def _make_chunk(count: int, start_ts: int = TS_BASE, rate: float = 0.0001) -> list[list]:
    return [
        _make_raw_record(start_ts + i * FUNDING_INTERVAL_MS, rate)
        for i in range(count)
    ]


class TestFundingMarketDataToSimulation:
    """Integration tests connecting funding data fetch to cost calculation."""

    def test_single_chunk_to_cost(self):
        """Single funding chunk: fetch → cost for each record."""
        mock_client = Mock()
        mock_client.get_funding_rate.return_value = _make_chunk(10)

        svc = FundingService(mock_client)
        records = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(records) == 10

        # Compute cost for each record assuming 1-bar hold at 100k notional
        for rec in records:
            cost = funding_cost_r(
                notional=100_000.0,
                funding_rate=rec.funding_rate,
                holding_bars=1,
            )
            # Each record has funding_rate=0.0001, so 100k * 0.0001 * 1 = 10
            assert cost == 10.0

    def test_multi_chunk_to_cost(self):
        """Multiple paginated chunks: all records flow to cost correctly."""
        mock_client = Mock()
        chunk1 = _make_chunk(MAX_LIMIT, start_ts=TS_BASE)
        chunk2 = _make_chunk(37, start_ts=TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS)
        mock_client.get_funding_rate.side_effect = [chunk1, chunk2]

        svc = FundingService(mock_client)
        records = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(records) == MAX_LIMIT + 37

        # Aggregated cost for 8-hour hold at 50k notional
        total_cost = sum(
            funding_cost_r(
                notional=50_000.0,
                funding_rate=r.funding_rate,
                holding_bars=8,
            )
            for r in records
        )
        # Each record: 50000 * 0.0001 * 8 = 40
        # Total: 1037 * 40 = 41480
        assert total_cost == pytest.approx((MAX_LIMIT + 37) * 40.0)

    def test_varying_funding_rates_through_pipeline(self):
        """Different funding rates are correctly propagated through pagination."""
        mock_client = Mock()
        # Two chunks with different rates; first chunk must be MAX_LIMIT size
        # so pagination continues (fetch stops when len(raw) < MAX_LIMIT).
        chunk1 = _make_chunk(MAX_LIMIT, start_ts=TS_BASE, rate=0.0001)
        chunk2_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk2 = _make_chunk(3, start_ts=chunk2_start, rate=0.0002)
        mock_client.get_funding_rate.side_effect = [chunk1, chunk2]

        svc = FundingService(mock_client)
        records = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(records) == MAX_LIMIT + 3

        costs = [
            funding_cost_r(notional=100_000.0, funding_rate=r.funding_rate, holding_bars=1)
            for r in records
        ]
        # First MAX_LIMIT: 100k * 0.0001 * 1 = 10
        assert costs[:MAX_LIMIT] == [10.0] * MAX_LIMIT
        # Last 3: 100k * 0.0002 * 1 = 20
        assert costs[MAX_LIMIT:] == [20.0] * 3

    def test_empty_funding_to_cost(self):
        """Empty funding fetch results in zero total cost."""
        mock_client = Mock()
        mock_client.get_funding_rate.return_value = []

        svc = FundingService(mock_client)
        records = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(records) == 0

        total_cost = sum(
            funding_cost_r(notional=100_000.0, funding_rate=r.funding_rate, holding_bars=1)
            for r in records
        )
        assert total_cost == 0.0

    def test_negative_rates_through_pipeline(self):
        """Negative funding rates flow through the pipeline correctly."""
        mock_client = Mock()
        # Negative funding rate scenario (shorts pay longs)
        raw = [
            _make_raw_record(TS_BASE, rate=-0.0001),
            _make_raw_record(TS_BASE + FUNDING_INTERVAL_MS, rate=-0.0002),
        ]
        mock_client.get_funding_rate.return_value = raw

        svc = FundingService(mock_client)
        records = svc.fetch("BTCUSDT", start_time=TS_BASE)

        # Long position with negative rate => negative cost (gain)
        long_cost = sum(
            funding_cost_r(notional=100_000.0, funding_rate=r.funding_rate, holding_bars=1)
            for r in records
        )
        # 100k * -0.0001 * 1 + 100k * -0.0002 * 1 = -10 + -20 = -30
        assert long_cost == -30.0

        # Short position (negative notional) with negative rate => positive cost
        short_cost = sum(
            funding_cost_r(notional=-100_000.0, funding_rate=r.funding_rate, holding_bars=1)
            for r in records
        )
        # -100k * -0.0001 * 1 + -100k * -0.0002 * 1 = 10 + 20 = 30
        assert short_cost == 30.0
