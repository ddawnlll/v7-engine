"""
lib/market_data/binance — Binance-specific client and services.

Import-boundary rule: this package must NOT import v7.* or alphaforge.*
"""

from lib.market_data.binance.client import BinanceClient, BinanceClientError
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService, FundingRecord
from lib.market_data.binance.market_data_service import BinanceMarketDataService

__all__ = [
    "BinanceClient", "BinanceClientError",
    "KlinesService",
    "FundingService", "FundingRecord",
    "BinanceMarketDataService",
]
