"""
DatasetSpec — immutable description of a required dataset.

Defines *what* data is needed for a research run or pipeline stage.
Used together with :class:`lib.data_lake.catalog.DataCatalog` to
discover gaps between what is needed and what has been ingested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SOURCES = frozenset({
    "binance",
    "coinalyze",
    "glassnode",
    "tardis",
    "crypto_lake",
    "custom",
})

VALID_MARKETS = frozenset({
    "um_futures",
    "cm_futures",
    "spot",
    "perpetual",
})

VALID_INTERVALS = frozenset({
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1mo",
})


# ---------------------------------------------------------------------------
# DatasetSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetSpec:
    """Immutable specification of a required dataset.

    Attributes:
        dataset_id: Unique identifier for this dataset spec.
        source: Data source name (e.g. ``"binance"``).
        market: Market type (e.g. ``"um_futures"``).
        symbols: Tuple of trading pair symbols (e.g. ``("BTCUSDT",)``).
        intervals: Tuple of candle intervals.
        data_types: Tuple of data type names (e.g. ``("klines", "funding_rate")``).
        start: Inclusive start of the required time range (UTC).
        end: Exclusive end of the required time range (UTC).
        priority: Dataset priority (``"P0"``, ``"P1"``, …).
        backtest_required: Whether this dataset is needed for backtesting.
        allow_synthetic: Whether synthetic data may be used as fallback.
    """

    dataset_id: str
    source: str
    market: str
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    data_types: tuple[str, ...]
    start: datetime
    end: datetime
    priority: str = "P0"
    backtest_required: bool = True
    allow_synthetic: bool = False

    def __post_init__(self) -> None:
        """Validate fields at construction time."""
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source {self.source!r}. "
                f"Must be one of {sorted(VALID_SOURCES)}"
            )
        if self.market not in VALID_MARKETS:
            raise ValueError(
                f"Invalid market {self.market!r}. "
                f"Must be one of {sorted(VALID_MARKETS)}"
            )
        bad = [i for i in self.intervals if i not in VALID_INTERVALS]
        if bad:
            raise ValueError(
                f"Invalid interval(s) {bad}. "
                f"Must be one of {sorted(VALID_INTERVALS)}"
            )
        if not self.symbols:
            raise ValueError("symbols must be non-empty")
        if not self.data_types:
            raise ValueError("data_types must be non-empty")
        if self.start >= self.end:
            raise ValueError(
                f"start ({self.start}) must be before end ({self.end})"
            )

    @property
    def interval_seconds(self) -> int:
        """Approximate seconds for a single bar of the primary interval.

        Used for coverage computation. Returns the smallest interval's
        duration in seconds.
        """
        _MULT: dict[str, int] = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "6h": 21600,
            "8h": 28800,
            "12h": 43200,
            "1d": 86400,
            "3d": 259200,
            "1w": 604800,
            "1mo": 2592000,
        }
        # Use the smallest interval for the most granular estimate
        return min(_MULT[i] for i in self.intervals)

    def expected_bar_count(self) -> int:
        """Rough estimate of total expected bars across all symbols and intervals.

        Uses the smallest interval's seconds for a conservative upper bound.
        """
        total_seconds = (self.end - self.start).total_seconds()
        if total_seconds <= 0:
            return 0
        bars_per_symbol_interval = int(total_seconds / self.interval_seconds)
        return bars_per_symbol_interval * len(self.symbols) * len(self.intervals)
