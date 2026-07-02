"""
CandidateOutcomeBuilder — transforms SimulationOutput into mining-ready pyarrow Table.

Produces a flattened dataset with one row per SimulationOutput, containing:
  - Identity columns (symbol, timestamp, side, mode, timeframe)
  - Pre-entry features (computed from lookback market data available at decision time)
  - Outcome fields (realized R, costs, path metrics, exit reason)
  - Lineage fields (simulation_run_id, candidate_id)

Authority boundary: alphaforge/ consumes simulation/ outputs through this adapter.
This module does NOT import v7/, runtime/, or interface/.
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pyarrow as pa

from lib.indicators.atr import compute_atr
from lib.indicators.momentum import momentum
from lib.indicators.rolling import rolling_max, rolling_mean, rolling_min
from lib.indicators.spread import parkinson_spread
from lib.indicators.volatility import rolling_std
from lib.market_data.contracts import KlineRecord
from simulation.contracts.models import (
    ActionOutcome,
    SimulationOutput,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — feature computation lookback windows
# ---------------------------------------------------------------------------

SMA_PERIOD: int = 50
ATR_PERIOD: int = 14
MOMENTUM_PERIOD: int = 10
VOLUME_WINDOW: int = 20
VOLATILITY_WINDOW: int = 20
RANGE_WINDOW: int = 20
SLOPE_LOOKBACK: int = 10
MIN_LOOKBACK_BARS: int = SMA_PERIOD  # 50 — enough for all windows
PRICE_DECIMAL_PLACES: int = 8


# ---------------------------------------------------------------------------
# Pre-entry feature computation helpers
# ---------------------------------------------------------------------------


def _to_unix_ms(iso_str: str) -> int:
    """Convert ISO-8601 timestamp string to unix milliseconds."""
    dt = datetime.datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def _find_bar_index(
    records: List[KlineRecord], target_ts_unix_ms: int
) -> Optional[int]:
    """Binary-search for the bar whose timestamp matches target_ts_unix_ms.

    Returns the index, or None if not found.
    """
    lo, hi = 0, len(records) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        ts = records[mid].timestamp
        if ts == target_ts_unix_ms:
            return mid
        elif ts < target_ts_unix_ms:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def _find_entry_bar_index(
    records: List[KlineRecord], decision_timestamp_iso: str
) -> Optional[int]:
    """Convert decision timestamp to unix ms and find the bar index."""
    ts_ms = _to_unix_ms(decision_timestamp_iso)
    return _find_bar_index(records, ts_ms)


# ---------------------------------------------------------------------------
# SMA helper (numpy-based)
# ---------------------------------------------------------------------------


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average, NaN-padded at the start."""
    n = len(values)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = np.mean(values[i - period + 1 : i + 1])
    return result


def _linear_slope(values: np.ndarray, lookback: int) -> np.ndarray:
    """Least-squares slope over the last `lookback` values.

    Returns NaN at indices < lookback.
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < lookback:
        return result
    x = np.arange(lookback, dtype=np.float64)
    x_mean = np.mean(x)
    x_centered = x - x_mean
    denom = np.sum(x_centered ** 2)
    if denom == 0.0:
        return result
    for i in range(lookback - 1, n):
        y = values[i - lookback + 1 : i + 1]
        y_mean = np.mean(y)
        slope = np.sum((y - y_mean) * x_centered) / denom
        result[i] = slope
    return result


# ---------------------------------------------------------------------------
# Pre-entry feature calculator
# ---------------------------------------------------------------------------


def _compute_pre_entry_features(
    records: List[KlineRecord],
    entry_idx: int,
    btc_records: Optional[List[KlineRecord]] = None,
    funding_value: Optional[float] = None,
) -> Dict[str, any]:
    """Compute all pre-entry features at the entry bar index.

    All features use only data from indices [0, entry_idx] — strictly causal.
    Returns a dict keyed by feature name.
    """
    n_bars = entry_idx + 1  # total bars available up to (and including) entry

    # Extract OHLCV arrays up to entry
    closes = np.array([r.close for r in records[:n_bars]], dtype=np.float64)
    highs = np.array([r.high for r in records[:n_bars]], dtype=np.float64)
    lows = np.array([r.low for r in records[:n_bars]], dtype=np.float64)
    volumes = np.array([r.volume for r in records[:n_bars]], dtype=np.float64)
    last_close = closes[-1]
    last_high = highs[-1]
    last_low = lows[-1]

    # --- atr_pct: ATR(14) / close * 100 ---
    atr_values = np.array(
        compute_atr(
            highs.tolist(), lows.tolist(), closes.tolist(), period=ATR_PERIOD
        ),
        dtype=np.float64,
    )
    last_atr = atr_values[-1] if len(atr_values) > 0 else np.nan
    atr_pct = (last_atr / last_close * 100.0) if (
        not np.isnan(last_atr) and last_close > 0
    ) else np.nan

    # --- regime_trend: up / range / down ---
    sma50 = _sma(closes, SMA_PERIOD)[-1] if n_bars >= SMA_PERIOD else np.nan
    slope_val = _linear_slope(closes, SLOPE_LOOKBACK)[-1] if n_bars >= SLOPE_LOOKBACK else np.nan
    if not np.isnan(sma50) and not np.isnan(slope_val):
        if last_close > sma50 * 1.005 and slope_val > 0:
            regime_trend = "up"
        elif last_close < sma50 * 0.995 and slope_val < 0:
            regime_trend = "down"
        else:
            regime_trend = "range"
    else:
        regime_trend = "range"

    # --- volatility_percentile: percentile rank of ATR/close over window ---
    if n_bars >= VOLATILITY_WINDOW and not np.isnan(last_atr):
        atr_pct_series = np.full(n_bars, np.nan, dtype=np.float64)
        atr_all = np.array(
            compute_atr(
                highs.tolist(), lows.tolist(), closes.tolist(), period=ATR_PERIOD
            ),
            dtype=np.float64,
        )
        for i in range(ATR_PERIOD, n_bars):
            if closes[i] > 0 and not np.isnan(atr_all[i]):
                atr_pct_series[i] = atr_all[i] / closes[i] * 100.0
        window = atr_pct_series[-VOLATILITY_WINDOW:]
        valid = window[~np.isnan(window)]
        if len(valid) >= 5:
            current = atr_pct_series[-1]
            below = np.sum(valid <= current)
            volatility_percentile = below / len(valid) * 100.0
        else:
            volatility_percentile = 50.0
    else:
        volatility_percentile = 50.0

    # --- momentum_rank: min-max normalized momentum(10) over window ---
    if n_bars >= MOMENTUM_PERIOD + 1:
        mom_values = np.array(
            momentum(closes.tolist(), period=MOMENTUM_PERIOD),
            dtype=np.float64,
        )
        current_mom = mom_values[-1]
        window_mom = mom_values[-VOLATILITY_WINDOW:] if n_bars >= VOLATILITY_WINDOW + MOMENTUM_PERIOD else mom_values[MOMENTUM_PERIOD:]
        valid_mom = window_mom[~np.isnan(window_mom)]
        if len(valid_mom) >= 3:
            min_m, max_m = np.min(valid_mom), np.max(valid_mom)
            if max_m > min_m:
                momentum_rank = (current_mom - min_m) / (max_m - min_m)
            else:
                momentum_rank = 0.5
        else:
            momentum_rank = 0.5
    else:
        momentum_rank = 0.5

    # --- volume_zscore: z-score of latest volume within rolling window ---
    if n_bars >= VOLUME_WINDOW:
        vol_window = volumes[-VOLUME_WINDOW:]
        vol_mean = np.nanmean(vol_window)
        vol_std = np.nanstd(vol_window)
        volume_zscore = (volumes[-1] - vol_mean) / vol_std if vol_std > 1e-14 else 0.0
    else:
        volume_zscore = 0.0

    # --- btc_regime ---
    if btc_records is not None and len(btc_records) > 0:
        # Find the BTC bar at or before entry timestamp
        entry_ts = records[entry_idx].timestamp
        btc_idx = _find_bar_index(btc_records, entry_ts)
        if btc_idx is not None and btc_idx >= SMA_PERIOD:
            btc_closes = np.array([r.close for r in btc_records[: btc_idx + 1]], dtype=np.float64)
            btc_sma50 = _sma(btc_closes, SMA_PERIOD)[-1]
            btc_slope = _linear_slope(btc_closes, SLOPE_LOOKBACK)[-1]
            btc_close = btc_closes[-1]
            if not np.isnan(btc_sma50) and not np.isnan(btc_slope):
                if btc_close > btc_sma50 * 1.005 and btc_slope > 0:
                    btc_regime = "up"
                elif btc_close < btc_sma50 * 0.995 and btc_slope < 0:
                    btc_regime = "down"
                else:
                    btc_regime = "range"
            else:
                btc_regime = "range"
        else:
            btc_regime = "range"
    else:
        btc_regime = "range"

    # --- pullback_atr: (rolling_high_max - close) / ATR ---
    if n_bars >= RANGE_WINDOW and not np.isnan(last_atr) and last_atr > 0:
        recent_high = rolling_max(closes.tolist(), period=RANGE_WINDOW)[-1]
        pullback_atr = (recent_high - last_close) / last_atr if recent_high > last_close else 0.0
    else:
        pullback_atr = 0.0

    # --- distance_to_range_high: how close price is to recent range ---
    if n_bars >= RANGE_WINDOW:
        range_high = rolling_max(highs.tolist(), period=RANGE_WINDOW)[-1]
        range_low = rolling_min(lows.tolist(), period=RANGE_WINDOW)[-1]
        if range_high > range_low:
            distance_to_range_high = (last_close - range_low) / (range_high - range_low)
        else:
            distance_to_range_high = 0.5
    else:
        distance_to_range_high = 0.5

    # --- spread_proxy: parkinson spread estimate at entry bar ---
    spread_values = parkinson_spread(
        highs.tolist(), lows.tolist()
    )
    spread_proxy = spread_values[-1] if spread_values else 0.0

    # --- funding_context ---
    if funding_value is not None:
        funding_context = funding_value
    else:
        funding_context = 0.0

    return {
        "regime_trend": regime_trend,
        "volatility_percentile": volatility_percentile,
        "momentum_rank": momentum_rank,
        "volume_zscore": volume_zscore,
        "atr_pct": atr_pct,
        "btc_regime": btc_regime,
        "pullback_atr": pullback_atr,
        "distance_to_range_high": distance_to_range_high,
        "spread_proxy": spread_proxy,
        "funding_context": funding_context,
    }


# ---------------------------------------------------------------------------
# Side mapping
# ---------------------------------------------------------------------------


def _action_to_side(best_action: str) -> str:
    """Map simulation best_action to dataset side string.

    LONG_NOW -> LONG, SHORT_NOW -> SHORT, everything else stays as-is
    for traceability (NO_TRADE, AMBIGUOUS_STATE).
    """
    if best_action == "LONG_NOW":
        return "LONG"
    elif best_action == "SHORT_NOW":
        return "SHORT"
    return best_action


# ---------------------------------------------------------------------------
# Outcome extraction
# ---------------------------------------------------------------------------


def _pick_outcome(
    best_action: str, long_outcome: ActionOutcome, short_outcome: ActionOutcome
) -> ActionOutcome:
    """Return the ActionOutcome corresponding to the best action.

    For NO_TRADE and AMBIGUOUS_STATE, returns long_outcome as fallback
    (all outcome fields will be zero/empty).
    """
    if best_action == "SHORT_NOW":
        return short_outcome
    return long_outcome


# ---------------------------------------------------------------------------
# MarketDataContext
# ---------------------------------------------------------------------------


class MarketDataContext:
    """Container for OHLCV market data needed by CandidateOutcomeBuilder.

    Attributes:
        records: Ordered list of KlineRecords (oldest first).
    """

    def __init__(self, records: List[KlineRecord]) -> None:
        if not records:
            raise ValueError("MarketDataContext must have at least one record")
        # Validate ordering
        for i in range(1, len(records)):
            if records[i].timestamp < records[i - 1].timestamp:
                raise ValueError("MarketDataContext records must be ordered by timestamp (oldest first)")
        self.records = records


# ---------------------------------------------------------------------------
# BFunding data context
# ---------------------------------------------------------------------------


def _lookup_funding(
    funding_data: Optional[Dict[str, List[float]]],
    symbol: str,
    entry_idx: int,
) -> Optional[float]:
    """Look up the funding rate for a symbol at the entry index.

    Returns None if no funding data is available.
    """
    if funding_data is None:
        return None
    rates = funding_data.get(symbol)
    if rates is None or entry_idx >= len(rates):
        return None
    return rates[entry_idx]


# ---------------------------------------------------------------------------
# Generate unique candidate_id
# ---------------------------------------------------------------------------


def _make_candidate_id(simulation_run_id: str, symbol: str, idx: int) -> str:
    """Create a unique candidate identifier from simulation run context."""
    return f"{simulation_run_id}_{symbol}_{idx}"


# ---------------------------------------------------------------------------
# CandidateOutcomeBuilder
# ---------------------------------------------------------------------------


class CandidateOutcomeBuilder:
    """Builds a mining-ready CandidateOutcomeDataset (pyarrow Table) from
    simulation outputs and market data context.

    Usage::

        builder = CandidateOutcomeBuilder(
            market_data={"BTCUSDT": MarketDataContext(records)},
            lookback_bars=100,
        )
        table = builder.build(simulation_outputs)
    """

    def __init__(
        self,
        market_data: Dict[str, MarketDataContext],
        btc_market_data: Optional[MarketDataContext] = None,
        funding_data: Optional[Dict[str, List[float]]] = None,
        lookback_bars: int = MIN_LOOKBACK_BARS,
    ) -> None:
        """Initialize the builder with market data context.

        Args:
            market_data: Dict mapping symbol (e.g. "BTCUSDT") to a
                MarketDataContext containing ordered KlineRecords.
            btc_market_data: Optional MarketDataContext for BTC regime
                detection. Must contain the same-timestamp records as the
                per-symbol data.
            funding_data: Optional dict mapping symbol to a list of funding
                rate values, one per KlineRecord bar.
            lookback_bars: Minimum number of lookback bars required for
                pre-entry feature computation (default 50).
        """
        self._market_data = market_data
        self._btc_market_data = btc_market_data
        self._funding_data = funding_data
        self._lookback_bars = lookback_bars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, simulation_outputs: List[SimulationOutput]) -> pa.Table:
        """Transform simulation outputs into a mining-ready pyarrow Table.

        Each row corresponds to one SimulationOutput. Pre-entry features
        are computed from the market data context at the decision point.
        Rows where the symbol's market data is not found or the entry bar
        cannot be located are skipped with a warning.

        Args:
            simulation_outputs: List of SimulationOutput from the simulation
                engine.

        Returns:
            pyarrow Table with the columns described in the module docstring.
            Returns an empty table with the correct schema if no valid rows.
        """
        if not simulation_outputs:
            logger.info("build() called with empty simulation_outputs list")
            return self._empty_table()

        rows: List[Dict[str, any]] = []

        for idx, sim_out in enumerate(simulation_outputs):
            try:
                row = self._process_single(sim_out, idx)
                if row is not None:
                    rows.append(row)
            except Exception:
                logger.exception(
                    "Error processing simulation output #%d (run=%s, symbol=%s)",
                    idx,
                    sim_out.simulation_run_id,
                    sim_out.symbol,
                )
                continue

        if not rows:
            logger.warning("No valid rows were produced from %d simulation outputs", len(simulation_outputs))
            return self._empty_table()

        return self._rows_to_table(rows)

    # ------------------------------------------------------------------
    # Internal: process one simulation output
    # ------------------------------------------------------------------

    def _process_single(
        self, sim_out: SimulationOutput, idx: int
    ) -> Optional[Dict[str, any]]:
        """Process a single SimulationOutput into a row dict.

        Returns None if the output cannot be processed (missing market data,
        insufficient lookback, etc.).
        """
        # Find market data for this symbol
        mdc = self._market_data.get(sim_out.symbol)
        if mdc is None:
            logger.debug(
                "No market data for symbol %s (run=%s), skipping",
                sim_out.symbol,
                sim_out.simulation_run_id,
            )
            return None

        records = mdc.records

        # Locate the entry bar index
        entry_idx = _find_entry_bar_index(records, sim_out.decision_timestamp)
        if entry_idx is None:
            logger.debug(
                "Cannot locate bar for timestamp %s (symbol=%s, run=%s), skipping",
                sim_out.decision_timestamp,
                sim_out.symbol,
                sim_out.simulation_run_id,
            )
            return None

        # Ensure sufficient lookback for feature computation
        if entry_idx < self._lookback_bars:
            logger.debug(
                "Insufficient lookback: entry_idx=%d < lookback_bars=%d (symbol=%s), skipping",
                entry_idx,
                self._lookback_bars,
                sim_out.symbol,
            )
            return None

        # Pre-entry features
        btc_records = self._btc_market_data.records if self._btc_market_data is not None else None
        funding_val = _lookup_funding(self._funding_data, sim_out.symbol, entry_idx)
        features = _compute_pre_entry_features(
            records, entry_idx,
            btc_records=btc_records,
            funding_value=funding_val,
        )

        # Side
        side = _action_to_side(sim_out.best_action)

        # Outcome — pick the relevant ActionOutcome for the best action
        outcome = _pick_outcome(
            sim_out.best_action,
            sim_out.long_outcome,
            sim_out.short_outcome,
        )

        # Timestamp (unix ms)
        timestamp_ms = _to_unix_ms(sim_out.decision_timestamp)

        # Lineage
        candidate_id = _make_candidate_id(
            sim_out.simulation_run_id,
            sim_out.symbol,
            idx,
        )

        return {
            # Identity
            "symbol": sim_out.symbol,
            "timestamp": timestamp_ms,
            "side": side,
            "mode": sim_out.mode,
            "timeframe": sim_out.primary_interval,
            # Pre-entry features
            **features,
            # Outcome fields
            "net_R": outcome.realized_r_net if outcome is not None else 0.0,
            "gross_R": outcome.realized_r_gross if outcome is not None else 0.0,
            "cost_R": outcome.total_cost_r if outcome is not None else 0.0,
            "mfe_R": outcome.path_metrics.mfe_r if outcome is not None else 0.0,
            "mae_R": outcome.path_metrics.mae_r if outcome is not None else 0.0,
            "exit_reason": outcome.exit_reason if outcome is not None else "",
            "hold_duration": int(outcome.hold_duration_bars) if outcome is not None else 0,
            # Lineage
            "simulation_run_id": sim_out.simulation_run_id,
            "candidate_id": candidate_id,
        }

    # ------------------------------------------------------------------
    # Schema and table building
    # ------------------------------------------------------------------

    @staticmethod
    def _schema() -> pa.Schema:
        """Define the canonical schema for the output table."""
        return pa.schema([
            # Identity
            pa.field("symbol", pa.string()),
            pa.field("timestamp", pa.int64()),
            pa.field("side", pa.string()),
            pa.field("mode", pa.string()),
            pa.field("timeframe", pa.string()),
            # Pre-entry features
            pa.field("regime_trend", pa.string()),
            pa.field("volatility_percentile", pa.float64()),
            pa.field("momentum_rank", pa.float64()),
            pa.field("volume_zscore", pa.float64()),
            pa.field("atr_pct", pa.float64()),
            pa.field("btc_regime", pa.string()),
            pa.field("pullback_atr", pa.float64()),
            pa.field("distance_to_range_high", pa.float64()),
            pa.field("spread_proxy", pa.float64()),
            pa.field("funding_context", pa.float64()),
            # Outcome fields
            pa.field("net_R", pa.float64()),
            pa.field("gross_R", pa.float64()),
            pa.field("cost_R", pa.float64()),
            pa.field("mfe_R", pa.float64()),
            pa.field("mae_R", pa.float64()),
            pa.field("exit_reason", pa.string()),
            pa.field("hold_duration", pa.int64()),
            # Lineage
            pa.field("simulation_run_id", pa.string()),
            pa.field("candidate_id", pa.string()),
        ])

    @staticmethod
    def _empty_table() -> pa.Table:
        """Return an empty table with the correct schema."""
        schema = CandidateOutcomeBuilder._schema()
        return pa.Table.from_pydict({field.name: [] for field in schema}, schema=schema)

    @staticmethod
    def _rows_to_table(rows: List[Dict[str, any]]) -> pa.Table:
        """Convert a list of row dicts to a typed pyarrow Table.

        Casts each column to the canonical schema to ensure type correctness.
        """
        schema = CandidateOutcomeBuilder._schema()
        table = pa.Table.from_pylist(rows, schema=schema)
        return table.cast(schema)
