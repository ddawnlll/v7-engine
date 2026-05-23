"""
lib/market_data — Shared market data contracts and quality checks.

Use `lib.market_data.binance.BinanceMarketDataService` for data retrieval.
"""

from lib.market_data.contracts import KlineRecord, MarketDataResult, DataQualityReport

__all__ = ["KlineRecord", "MarketDataResult", "DataQualityReport"]
