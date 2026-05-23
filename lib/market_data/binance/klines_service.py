"""
Klines fetching service with caching and normalization.

Dependent layer on top of BinanceClient. Handles:
- Raw → KlineRecord normalization
- Time-range splitting (Binance limit is 1000 per call)
- Caching (in-memory dict by default)
"""

import logging
from typing import Optional

from lib.market_data.binance.client import BinanceClient
from lib.market_data.contracts import KlineRecord
from lib.market_data.quality import compute_expected_count, build_quality_report, DataQualityReport

logger = logging.getLogger(__name__)

# Interval → minutes mapping
_INTERVAL_TO_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


def interval_to_minutes(interval: str) -> int:
    """Convert interval string to minutes."""
    if interval not in _INTERVAL_TO_MINUTES:
        raise ValueError(f"Unknown interval: {interval}")
    return _INTERVAL_TO_MINUTES[interval]


class KlinesService:
    """Klines fetch service with caching and normalization.

    One instance per symbol/interval combination is typical.
    Use MarketDataService for multi-symbol orchestration.
    """

    def __init__(
        self,
        client: BinanceClient,
        cache: Optional[dict[tuple[str, str, int, int], list[KlineRecord]]] = None,
    ) -> None:
        self._client = client
        self._cache: dict[tuple[str, str, int, int], list[KlineRecord]] = cache or {}

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        use_cache: bool = True,
    ) -> tuple[list[KlineRecord], DataQualityReport]:
        """Fetch klines for symbol/interval in [start_time, end_time).

        Returns (records, quality_report).
        """
        cache_key = (symbol, interval, start_time, end_time)
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            n = interval_to_minutes(interval)
            report = build_quality_report(cached, n, len(cached))
            return cached, report

        records = self._fetch_range(symbol, interval, start_time, end_time)
        self._cache[cache_key] = records

        interval_min = interval_to_minutes(interval)
        expected = compute_expected_count(start_time, end_time, interval_min)
        report = build_quality_report(records, interval_min, expected)

        return records, report

    def _fetch_range(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> list[KlineRecord]:
        """Fetch full time range, splitting into 1000-candle chunks."""
        all_records: list[KlineRecord] = []
        current_start = start_time

        while current_start < end_time:
            raw = self._client.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                limit=1000,
            )
            if not raw:
                break

            records = [self._normalize(symbol, interval, r) for r in raw]
            all_records.extend(records)

            # Advance: last candle's timestamp + interval
            last_ts = records[-1].timestamp
            current_start = last_ts + interval_to_minutes(interval) * 60_000

            # If we got fewer than 1000, we hit the end
            if len(raw) < 1000:
                break

        return all_records

    @staticmethod
    def _normalize(symbol: str, interval: str, raw: list) -> KlineRecord:
        """Convert a raw Binance kline list to KlineRecord."""
        return KlineRecord(
            symbol=symbol,
            timestamp=int(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
            quote_volume=float(raw[7]),
            trade_count=int(raw[8]),
            taker_buy_volume=float(raw[9]),
            taker_buy_quote_volume=float(raw[10]),
            interval=interval,
            source="binance",
            is_closed=True,
        )
