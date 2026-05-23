"""
Funding rate history service.

Normalizes raw Binance funding rate data into simple records.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from lib.market_data.binance.client import BinanceClient

logger = logging.getLogger(__name__)


@dataclass
class FundingRecord:
    symbol: str
    timestamp: int
    funding_rate: float
    source: str = "binance"


class FundingService:
    """Fetch and normalize funding rate history."""

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[FundingRecord]:
        """Fetch funding rate history for a symbol."""
        raw = self._client.get_funding_rate(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        return [self._normalize(symbol, r) for r in raw]

    @staticmethod
    def _normalize(symbol: str, raw: list) -> FundingRecord:
        return FundingRecord(
            symbol=symbol,
            timestamp=int(raw[0]),
            funding_rate=float(raw[1]),
        )
