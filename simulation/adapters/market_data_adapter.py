"""
MarketDataAdapter — bridges KlineRecords to SimulationInput.

This is the primary entry point for converting historical market data into
simulation-ready decision points for training label generation.

No network, no exchange API, no xgboost. Pure deterministic transformation.
"""

from __future__ import annotations

import datetime
import logging
from typing import List

from lib.indicators.atr import compute_atr
from lib.market_data.contracts import KlineRecord
from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
)

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    """Converts KlineRecords into SimulationInputs for batch simulation.

    For each eligible decision point (bar index with sufficient lookback and
    forward data), creates a SimulationInput with:
      - Entry price = bar close
      - ATR computed from lookback window
      - FuturePath of subsequent candles
    """

    def adapt_klines(
        self,
        records: List[KlineRecord],
        profile: SimulationProfile,
        lookback_bars: int = 20,
        forward_bars: int = 48,
    ) -> List[SimulationInput]:
        """Convert kline records to a list of SimulationInputs.

        Each eligible decision point is at bar index ``i`` (where ``i >= lookback_bars``
        and ``i + forward_bars < len(records)``). At that point:
          - Entry price = ``records[i].close``
          - ATR is computed from bars ``[i-lookback_bars, i-1]``
          - FuturePath covers bars ``[i+1, i+forward_bars]``

        Args:
            records: Ordered list of KlineRecords (oldest first).
            profile: SimulationProfile to use for each input.
            lookback_bars: Minimum number of prior bars needed for ATR.
            forward_bars: Number of future bars to include in FuturePath.

        Returns:
            List of SimulationInput, one per eligible decision point.
        """
        if len(records) < lookback_bars + forward_bars + 1:
            logger.warning(
                "Insufficient records: need at least %d, got %d",
                lookback_bars + forward_bars + 1,
                len(records),
            )
            return []

        results: List[SimulationInput] = []

        for i in range(lookback_bars, len(records) - forward_bars):
            # Lookback window for ATR: bars [i-lookback_bars, i-1]
            lookback = records[i - lookback_bars : i]

            # Entry price = current bar close
            entry_price = records[i].close

            # Compute ATR on lookback window
            atr_value = self._compute_atr(lookback)
            if atr_value is None or atr_value != atr_value:  # NaN check
                continue

            # Future path: bars after entry bar
            forward = records[i + 1 : i + 1 + forward_bars]
            future_path = self._build_future_path(forward, forward_bars)

            decision_ts = _timestamp_to_iso(records[i].timestamp)

            sim_input = SimulationInput(
                symbol=records[i].symbol,
                decision_timestamp=decision_ts,
                mode=profile.mode,
                primary_interval=profile.primary_interval,
                entry_price=entry_price,
                atr=round(atr_value, 8),
                future_path=future_path,
                profile=profile,
            )
            results.append(sim_input)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_atr(lookback: List[KlineRecord]) -> float | None:
        """Compute ATR over a lookback window of KlineRecords.

        Returns the final ATR value, or None if computation fails.
        """
        if len(lookback) < 15:  # period=14 needs at least 15 bars
            return None
        highs = [r.high for r in lookback]
        lows = [r.low for r in lookback]
        closes = [r.close for r in lookback]
        atr_values = compute_atr(highs, lows, closes, period=14)
        if not atr_values:
            return None
        return atr_values[-1]

    @staticmethod
    def _build_future_path(
        forward_records: List[KlineRecord], expected_bars: int
    ) -> FuturePath:
        """Build a FuturePath from a slice of forward KlineRecords."""
        candles = [
            Candle(
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                close_time_utc=_timestamp_to_iso(r.timestamp) if r.timestamp else "",
            )
            for r in forward_records
        ]
        return FuturePath(
            candles=candles,
            completeness_status="COMPLETE",
            expected_bars=expected_bars,
        )


def _timestamp_to_iso(ts_ms: int) -> str:
    """Convert unix-millisecond timestamp to ISO-8601 string."""
    return datetime.datetime.utcfromtimestamp(ts_ms / 1000.0).isoformat()
