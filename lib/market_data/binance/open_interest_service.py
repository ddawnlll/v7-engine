"""Open Interest history service with time-range pagination.

Normalizes raw Binance open interest data into OpenInterestRecord.
Pagination: up to 500 records per call, advance by period interval.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from lib.market_data.binance.client import BinanceClient

logger = logging.getLogger(__name__)

# Period string → milliseconds for pagination advance
_PERIOD_MS: dict[str, int] = {
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

MAX_LIMIT = 500


@dataclass
class OpenInterestRecord:
    """Normalized open interest data point.

    Fields:
        symbol: Trading pair (e.g. BTCUSDT).
        timestamp: Unix ms of the data point.
        open_interest: Number of outstanding contracts.
        open_interest_value: Notional value in USD.
    """
    symbol: str
    timestamp: int
    open_interest: float
    open_interest_value: float


class OpenInterestService:
    """Fetch and normalize open interest history with pagination.

    Usage:
        service = OpenInterestService(client)
        records = service.fetch("BTCUSDT", start_time=..., end_time=...)
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(
        self,
        symbol: str,
        period: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[OpenInterestRecord]:
        """Fetch open interest history across a time range.

        Splits long ranges into 500-record chunks, advancing by one
        period interval between requests.

        Args:
            symbol: Trading pair symbol.
            period: Aggregation interval ("5m","15m","30m","1h","2h","4h","6h","12h","1d").
            start_time: Start timestamp in ms (optional).
            end_time: End timestamp in ms (optional).

        Returns:
            List of OpenInterestRecord, newest usually last.
        """
        all_records: list[OpenInterestRecord] = []
        current_start = start_time
        period_ms = _PERIOD_MS.get(period, 3_600_000)

        while True:
            raw = self._client.get_open_interest_hist(
                symbol=symbol,
                period=period,
                start_time=current_start,
                end_time=end_time,
                limit=MAX_LIMIT,
            )
            chunk = [self._normalize(symbol, r) for r in raw]
            all_records.extend(chunk)

            # Fewer than MAX_LIMIT means we've reached the end
            if len(raw) < MAX_LIMIT:
                break

            # Advance by one period
            last_ts = int(raw[-1][0])
            current_start = last_ts + period_ms

            if end_time is not None and current_start >= end_time:
                break

        return all_records

    @staticmethod
    def _normalize(symbol: str, raw: list) -> OpenInterestRecord:
        """Convert a raw Binance open interest response to OpenInterestRecord.

        Raw format: [timestamp, symbol, openInterest, openInterestValue, fundingRate]
        """
        return OpenInterestRecord(
            symbol=symbol,
            timestamp=int(raw[0]),
            open_interest=float(raw[1]),
            open_interest_value=float(raw[2]),
        )
