"""
Tests for lib/market_data/binance/ — client, services, and integration.

Uses mocking to avoid real network calls.
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from lib.market_data.binance.client import BinanceClient, BinanceClientError
from lib.market_data.binance.klines_service import KlinesService, interval_to_minutes
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.market_data_service import BinanceMarketDataService


# =====================================================================
# BinanceClient
# =====================================================================

SAMPLE_KLINE_RAW = [
    1_500_000_000_000,   # open time
    "50000.0",           # open
    "51000.0",           # high
    "49000.0",           # low
    "50500.0",           # close
    "100.0",             # volume
    1_500_000_000_999,   # close time
    "5000000.0",         # quote volume
    1000,                # trade count
    "55.0",              # taker buy volume
    "2750000.0",         # taker buy quote volume
    "0",                 # ignore
]


class TestBinanceClient:
    def test_get_klines_success(self):
        mock_resp = Mock()
        mock_resp.json.return_value = [SAMPLE_KLINE_RAW]
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient()
        client._session.get = Mock(return_value=mock_resp)

        result = client.get_klines("BTCUSDT", "1h")
        assert len(result) == 1
        assert result[0][0] == 1_500_000_000_000
        assert result[0][4] == "50500.0"

    def test_get_klines_passes_params(self):
        mock_resp = Mock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient()
        client._session.get = Mock(return_value=mock_resp)

        client.get_klines("BTCUSDT", "1h", start_time=1_000_000_000_000, end_time=1_000_000_000_999, limit=500)
        args, kwargs = client._session.get.call_args
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        assert kwargs["params"]["interval"] == "1h"
        assert kwargs["params"]["startTime"] == 1_000_000_000_000
        assert kwargs["params"]["endTime"] == 1_000_000_000_999
        assert kwargs["params"]["limit"] == 500

    def test_get_klines_uppercases_symbol(self):
        mock_resp = Mock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient()
        client._session.get = Mock(return_value=mock_resp)

        client.get_klines("btcusdt", "1h")
        args, kwargs = client._session.get.call_args
        assert kwargs["params"]["symbol"] == "BTCUSDT"

    def test_get_klines_limits_to_1000(self):
        mock_resp = Mock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient()
        client._session.get = Mock(return_value=mock_resp)

        client.get_klines("BTCUSDT", "1h", limit=5000)
        args, kwargs = client._session.get.call_args
        assert kwargs["params"]["limit"] == 1000

    def test_get_klines_http_error_retries_then_raises(self):
        client = BinanceClient(max_retries=2, retry_delay_seconds=0.01)
        client._session.get = Mock(side_effect=requests.RequestException("timeout"))

        with pytest.raises(BinanceClientError, match="timeout"):
            client.get_klines("BTCUSDT", "1h")

        assert client._session.get.call_count == 2

    def test_get_klines_succeeds_on_retry(self):
        mock_resp = Mock()
        mock_resp.json.return_value = [SAMPLE_KLINE_RAW]
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient(max_retries=3, retry_delay_seconds=0.01)
        client._session.get = Mock(
            side_effect=[requests.RequestException("timeout"), mock_resp]
        )

        result = client.get_klines("BTCUSDT", "1h")
        assert len(result) == 1
        assert client._session.get.call_count == 2

    def test_get_funding_rate(self):
        mock_resp = Mock()
        mock_resp.json.return_value = [[1_500_000_000_000, "0.0001"]]
        mock_resp.raise_for_status.return_value = None

        client = BinanceClient()
        client._session.get = Mock(return_value=mock_resp)

        result = client.get_funding_rate("BTCUSDT")
        assert len(result) == 1
        assert result[0][1] == "0.0001"


# =====================================================================
# KlinesService
# =====================================================================

class TestKlinesService:
    def test_fetch_single_batch(self):
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW]

        service = KlinesService(client)
        records, report = service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000)

        assert len(records) == 1
        assert records[0].symbol == "BTCUSDT"
        assert records[0].close == 50500.0
        assert records[0].interval == "1h"
        assert records[0].source == "binance"

    def test_fetch_multiple_batches(self):
        client = Mock(spec=BinanceClient)
        # Return 1000 records first, then remaining
        batch1 = [SAMPLE_KLINE_RAW] * 1000
        batch2 = [SAMPLE_KLINE_RAW] * 50
        client.get_klines.side_effect = [batch1, batch2]

        service = KlinesService(client)
        records, report = service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_630_000_000)

        assert len(records) == 1050

    def test_fetch_caching(self):
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW]

        service = KlinesService(client)
        records1, _ = service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000)
        records2, _ = service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000, use_cache=True)

        assert records1 == records2
        # Client should only have been called once
        assert client.get_klines.call_count == 1

    def test_fetch_cache_bypass(self):
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW]

        service = KlinesService(client)
        service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000, use_cache=True)
        service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000, use_cache=False)

        assert client.get_klines.call_count == 2

    def test_fetch_returns_quality_report(self):
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW]

        service = KlinesService(client)
        records, report = service.fetch("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000)

        assert report.total_received == 1
        assert report.gap_count == 0

    def test_interval_to_minutes_valid(self):
        assert interval_to_minutes("1m") == 1
        assert interval_to_minutes("5m") == 5
        assert interval_to_minutes("15m") == 15
        assert interval_to_minutes("1h") == 60
        assert interval_to_minutes("4h") == 240
        assert interval_to_minutes("1d") == 1440

    def test_interval_to_minutes_invalid(self):
        with pytest.raises(ValueError, match="Unknown interval"):
            interval_to_minutes("invalid")


# =====================================================================
# FundingService
# =====================================================================

class TestFundingService:
    def test_fetch(self):
        client = Mock(spec=BinanceClient)
        client.get_funding_rate.return_value = [[1_500_000_000_000, "0.0001"]]

        service = FundingService(client)
        records = service.fetch("BTCUSDT")

        assert len(records) == 1
        assert records[0].symbol == "BTCUSDT"
        assert records[0].funding_rate == 0.0001
        assert records[0].source == "binance"


# =====================================================================
# BinanceMarketDataService (integration)
# =====================================================================

class TestBinanceMarketDataService:
    def test_get_klines(self):
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW]

        service = BinanceMarketDataService(client=client)
        result = service.get_klines("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000)

        assert result.symbol == "BTCUSDT"
        assert result.interval == "1h"
        assert len(result.records) == 1
        assert result.quality.total_received == 1

    def test_get_funding_rate(self):
        client = Mock(spec=BinanceClient)
        client.get_funding_rate.return_value = [[1_500_000_000_000, "0.0001"]]

        service = BinanceMarketDataService(client=client)
        records = service.get_funding_rate("BTCUSDT")

        assert len(records) == 1
        assert records[0].funding_rate == 0.0001
