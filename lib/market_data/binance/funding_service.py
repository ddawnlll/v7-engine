"""
Funding rate history service with time-range pagination.

Normalizes raw Binance funding rate data into simple records.
Handles long time ranges by splitting into chunks of up to 1000 records
and advancing by the Binance funding interval (8 hours = 28 800 000 ms).
"""

import logging
from dataclasses import dataclass
from typing import Optional

from lib.market_data.binance.client import BinanceClient

logger = logging.getLogger(__name__)

# Binance funding interval in milliseconds (8 hours)
FUNDING_INTERVAL_MS = 28_800_000
# Maximum records per Binance funding rate response
MAX_LIMIT = 1000


@dataclass
class FundingRecord:
    symbol: str
    timestamp: int
    funding_rate: float
    source: str = "binance"


class FundingService:
    """Fetch and normalize funding rate history with pagination.

    Splits long time ranges into chunks of up to 1000 records and advances
    by the funding interval (8h) between requests.  If a chunk returns fewer
    than 1000 records the end of available data has been reached.
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[FundingRecord]:
        """Fetch funding rate history for a symbol across time ranges.

        Iterates over 1000-record chunks starting at *start_time* and
        advancing by the 8-hour funding interval on each iteration.
        Stops when *end_time* is reached or the API returns fewer than
        1000 records (end of data).
        """
        all_records: list[FundingRecord] = []
        current_start = start_time

        while True:
            raw = self._client.get_funding_rate(
                symbol=symbol,
                start_time=current_start,
                end_time=end_time,
                limit=MAX_LIMIT,
            )
            chunk = [self._normalize(symbol, r) for r in raw]
            all_records.extend(chunk)

            # Fewer than MAX_LIMIT records means we've reached the end
            if len(raw) < MAX_LIMIT:
                break

            # Advance by one funding interval (8 hours)
            last_ts = int(raw[-1][0])
            current_start = last_ts + FUNDING_INTERVAL_MS

            # Stop if we've passed end_time
            if end_time is not None and current_start >= end_time:
                break

        return all_records

    @staticmethod
    def _normalize(symbol: str, raw: list) -> FundingRecord:
        return FundingRecord(
            symbol=symbol,
            timestamp=int(raw[0]),
            funding_rate=float(raw[1]),
        )
