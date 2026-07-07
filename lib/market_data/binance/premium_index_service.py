"""Premium Index klines service with time-range pagination.

Normalizes raw Binance premium index klines into PremiumIndexRecord.
The premium index shows the basis (mark price - index price) level.
Used by alphaforge.features.premium_index to compute contango/backwardation.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import interval_to_minutes

logger = logging.getLogger(__name__)

MAX_LIMIT = 1000


@dataclass
class PremiumIndexRecord:
    """Normalized premium index kline data point.

    Fields:
        symbol: Trading pair (e.g. BTCUSDT).
        timestamp: Unix ms open time.
        premium_open: Premium index open value.
        premium_high: Premium index high value.
        premium_low: Premium index low value.
        premium_close: Premium index close value (basis level).
        index_price: Underlying index price at close.
    """
    symbol: str
    timestamp: int
    premium_open: float
    premium_high: float
    premium_low: float
    premium_close: float
    index_price: float


class PremiumIndexService:
    """Fetch and normalize premium index klines with pagination.

    Usage:
        service = PremiumIndexService(client)
        records = service.fetch("BTCUSDT", "1h", start_time=..., end_time=...)
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[PremiumIndexRecord]:
        """Fetch premium index klines across a time range.

        Splits long ranges into 1000-record chunks, advancing by the
        interval length between requests.

        Args:
            symbol: Trading pair symbol.
            interval: Kline interval (e.g. "1h", "15m", "4h").
            start_time: Start timestamp in ms (optional).
            end_time: End timestamp in ms (optional).

        Returns:
            List of PremiumIndexRecord, oldest first.
        """
        all_records: list[PremiumIndexRecord] = []
        current_start = start_time
        step_ms = interval_to_minutes(interval) * 60_000

        while True:
            raw = self._client.get_premium_index_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_time,
                limit=MAX_LIMIT,
            )
            chunk = [self._normalize(symbol, r) for r in raw]
            all_records.extend(chunk)

            if len(raw) < MAX_LIMIT:
                break

            last_ts = int(raw[-1][0])
            current_start = last_ts + step_ms

            if end_time is not None and current_start >= end_time:
                break

        return all_records

    @staticmethod
    def _normalize(symbol: str, raw: list) -> PremiumIndexRecord:
        """Convert raw Binance premium index kline to PremiumIndexRecord.

        Raw format: [openTime, open, high, low, close, indexPrice, ...]
        """
        return PremiumIndexRecord(
            symbol=symbol,
            timestamp=int(raw[0]),
            premium_open=float(raw[1]),
            premium_high=float(raw[2]),
            premium_low=float(raw[3]),
            premium_close=float(raw[4]),
            index_price=float(raw[5]),
        )
