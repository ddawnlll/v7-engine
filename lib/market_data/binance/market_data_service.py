"""
Market Data Service — top-level orchestration for market data retrieval.

Wires together BinanceClient, KlinesService, and FundingService.
Single entry point for both v7/ and alphaforge/ to fetch market data.
"""

import logging
from typing import Optional

from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.open_interest_service import OpenInterestService, OpenInterestRecord
from lib.market_data.binance.premium_index_service import PremiumIndexService, PremiumIndexRecord
from lib.market_data.contracts import KlineRecord, MarketDataResult, DataQualityReport

logger = logging.getLogger(__name__)


class BinanceMarketDataService:
    """Top-level market data service.

    Usage:
        service = BinanceMarketDataService()
        result = service.get_klines("BTCUSDT", "1h",
                                     start_time=..., end_time=...)

    Both v7/ and alphaforge/ should use this class (via dependency injection)
    instead of calling BinanceClient or KlinesService directly.
    """

    def __init__(
        self,
        client: Optional[BinanceClient] = None,
        klines: Optional[KlinesService] = None,
        funding: Optional[FundingService] = None,
        open_interest: Optional[OpenInterestService] = None,
        premium_index: Optional[PremiumIndexService] = None,
    ) -> None:
        self._client = client or BinanceClient()
        self._klines = klines or KlinesService(self._client)
        self._funding = funding or FundingService(self._client)
        self._oi = open_interest or OpenInterestService(self._client)
        self._premium = premium_index or PremiumIndexService(self._client)

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> MarketDataResult:
        """Fetch klines and return a structured result with quality report."""
        records, quality = self._klines.fetch(symbol, interval, start_time, end_time)
        return MarketDataResult(
            symbol=symbol,
            interval=interval,
            records=records,
            quality=quality,
        )

    def get_funding_rate(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list:
        """Fetch funding rate history."""
        return self._funding.fetch(symbol, start_time, end_time)

    def get_open_interest(
        self,
        symbol: str,
        period: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[OpenInterestRecord]:
        """Fetch open interest history."""
        return self._oi.fetch(symbol, period, start_time, end_time)

    def get_premium_index(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[PremiumIndexRecord]:
        """Fetch premium index klines."""
        return self._premium.fetch(symbol, interval, start_time, end_time)
