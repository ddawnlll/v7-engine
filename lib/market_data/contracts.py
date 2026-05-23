"""
Shared contracts for market data.

KlineRecord, MarketDataResult, and DataQualityReport are the standard
data shapes produced by the Shared Market Data Service and consumed by
both v7/ and alphaforge/.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KlineRecord:
    """A single kline/candlestick from Binance.

    Fields mirror the Binance kline response, with additional metadata.
    """
    symbol: str
    timestamp: int            # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_volume: float
    taker_buy_quote_volume: float
    interval: str             # e.g. "1h", "15m", "4h"
    source: str               # "binance"
    is_closed: bool


@dataclass
class DataQualityReport:
    """Quality assessment for a market data fetch operation."""
    total_expected: int
    total_received: int
    gap_count: int
    duplicate_count: int = 0
    is_complete: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class MarketDataResult:
    """Result of a market data fetch operation."""
    symbol: str
    interval: str
    records: list[KlineRecord]
    quality: DataQualityReport
