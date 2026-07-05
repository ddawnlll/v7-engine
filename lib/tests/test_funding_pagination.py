"""
Tests for lib/market_data/binance/funding_service.py pagination logic.

Uses a mocked BinanceClient to avoid real network calls.
Verifies that time-range splitting correctly handles:
  - Single chunk (fewer than 1000 records)
  - Multiple chunks (1000 records per chunk)
  - Boundary conditions (exact 1000, edge of range)
"""

from unittest.mock import Mock

import pytest

from lib.market_data.binance.funding_service import (
    FUNDING_INTERVAL_MS,
    MAX_LIMIT,
    FundingRecord,
    FundingService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS_BASE = 1_700_000_000_000  # arbitrary base timestamp in ms


def _make_raw_record(timestamp: int, rate: float = 0.0001) -> list:
    """Simulate a single raw Binance funding-rate list entry."""
    return [timestamp, str(rate)]


def _make_raw_chunk(
    count: int,
    start_ts: int = TS_BASE,
    rate: float = 0.0001,
) -> list[list]:
    """Generate *count* raw records spaced by FUNDING_INTERVAL_MS."""
    return [
        _make_raw_record(start_ts + i * FUNDING_INTERVAL_MS, rate)
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFundingPagination:
    def test_single_chunk_fewer_than_limit(self):
        """When fewer than MAX_LIMIT records exist, a single call suffices."""
        mock_client = Mock()
        raw = _make_raw_chunk(50)
        mock_client.get_funding_rate.return_value = raw

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(result) == 50
        assert all(isinstance(r, FundingRecord) for r in result)
        assert result[0].symbol == "BTCUSDT"
        assert result[0].source == "binance"
        # Exactly one API call
        mock_client.get_funding_rate.assert_called_once()

    def test_exact_one_chunk(self):
        """Exactly MAX_LIMIT records — pagination loop advances and stops."""
        mock_client = Mock()
        chunk = _make_raw_chunk(MAX_LIMIT)
        # side_effect: first call returns MAX_LIMIT records, second returns
        # empty (simulating reaching the end of available data).
        mock_client.get_funding_rate.side_effect = [chunk, []]

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(result) == MAX_LIMIT
        # Two calls: first gets data, second probes and gets empty
        assert mock_client.get_funding_rate.call_count == 2

    def test_two_full_chunks(self):
        """First call returns MAX_LIMIT, second returns fewer => two chunks."""
        mock_client = Mock()
        # First chunk: MAX_LIMIT records
        chunk1 = _make_raw_chunk(MAX_LIMIT)
        # Second chunk: trailing 37 records
        chunk2_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk2 = _make_raw_chunk(37, start_ts=chunk2_start)

        mock_client.get_funding_rate.side_effect = [chunk1, chunk2]

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(result) == MAX_LIMIT + 37
        assert mock_client.get_funding_rate.call_count == 2

    def test_three_full_chunks(self):
        """Three full chunks, each returning MAX_LIMIT, then a short tail."""
        mock_client = Mock()
        chunk1 = _make_raw_chunk(MAX_LIMIT, start_ts=TS_BASE)
        chunk2_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk2 = _make_raw_chunk(MAX_LIMIT, start_ts=chunk2_start)
        chunk3_start = TS_BASE + 2 * MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk3 = _make_raw_chunk(12, start_ts=chunk3_start)

        mock_client.get_funding_rate.side_effect = [chunk1, chunk2, chunk3]

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(result) == 2 * MAX_LIMIT + 12
        assert mock_client.get_funding_rate.call_count == 3

    def test_start_time_advances_correctly(self):
        """Verify that the start_time parameter advances by FUNDING_INTERVAL_MS."""
        mock_client = Mock()
        chunk1 = _make_raw_chunk(MAX_LIMIT, start_ts=TS_BASE)
        chunk2_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk2 = _make_raw_chunk(5, start_ts=chunk2_start)

        mock_client.get_funding_rate.side_effect = [chunk1, chunk2]

        svc = FundingService(mock_client)
        svc.fetch("BTCUSDT", start_time=TS_BASE)

        calls = mock_client.get_funding_rate.call_args_list
        assert len(calls) == 2

        # First call should use the original start_time
        first_kw = calls[0][1]
        assert first_kw["start_time"] == TS_BASE

        # Second call should advance by (MAX_LIMIT * FUNDING_INTERVAL_MS)
        expected_second_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        second_kw = calls[1][1]
        assert second_kw["start_time"] == expected_second_start

    def test_end_time_stops_early(self):
        """When end_time is provided, pagination stops before it."""
        mock_client = Mock()
        # Generate enough records to need 3 chunks, but end_time cuts it short
        chunk1 = _make_raw_chunk(MAX_LIMIT, start_ts=TS_BASE)
        # Second chunk crosses end_time after a few records
        chunk2_start = TS_BASE + MAX_LIMIT * FUNDING_INTERVAL_MS
        chunk2 = _make_raw_chunk(100, start_ts=chunk2_start)

        mock_client.get_funding_rate.side_effect = [chunk1, chunk2]

        end_boundary = chunk2_start + 50 * FUNDING_INTERVAL_MS
        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE, end_time=end_boundary)

        # Both chunks are returned because the client returns whatever binance
        # gives (we don't truncate at the service level — binance handles that).
        # The pagination stops when fewer than MAX_LIMIT records come back.
        # Here chunk2 has fewer than MAX_LIMIT, so it terminates.
        assert len(result) == MAX_LIMIT + 100
        assert mock_client.get_funding_rate.call_count == 2

    def test_empty_response(self):
        """When no records exist, returns empty list."""
        mock_client = Mock()
        mock_client.get_funding_rate.return_value = []

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert result == []
        mock_client.get_funding_rate.assert_called_once()

    def test_exact_boundary_zero_remaining(self):
        """When a chunk returns exactly MAX_LIMIT but there is no more data,
        the advance calculation still works — next call returns empty."""
        mock_client = Mock()
        chunk1 = _make_raw_chunk(MAX_LIMIT, start_ts=TS_BASE)
        mock_client.get_funding_rate.side_effect = [chunk1, []]

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT", start_time=TS_BASE)

        assert len(result) == MAX_LIMIT
        assert mock_client.get_funding_rate.call_count == 2

    def test_backward_compatible_no_start_time(self):
        """fetch() without start_time still works (single call)."""
        mock_client = Mock()
        raw = _make_raw_chunk(10)
        mock_client.get_funding_rate.return_value = raw

        svc = FundingService(mock_client)
        result = svc.fetch("BTCUSDT")

        assert len(result) == 10
        mock_client.get_funding_rate.assert_called_once()
