"""CandidateOutcomeDataset v002 — side-specific rows, no side oracle.

Each row represents a single SimulationOutput for one side (LONG/SHORT).
No best-of-side selection. No local simulation. Simulation is the only
outcome truth authority.

Research labels are derived from SimulationOutput fields only.
All pre-entry features must be observable at or before the timestamp.

Authority boundary:
  - simulation/ owns outcome truth (net_R, gross_R, MFE, MAE, exit)
  - alphaforge/ owns research labels, feature computation, dataset assembly
  - alphaforge/ does NOT compute stop/target/horizon/cost truth
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATASET_VERSION = "v002"

# Derived label thresholds (configurable)
PROFIT_BUCKET_EDGES = [-0.5, -0.1, 0.0, 0.1, 0.5]  # net_R boundaries
STRONG_WIN_THRESHOLD = 0.5  # net_R > this = strong win
BAD_STATE_THRESHOLD = -0.5  # net_R < this = bad state


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _v002_schema() -> pa.Schema:
    """Canonical schema for CandidateOutcomeDataset v002."""
    return pa.schema([
        # Identity
        pa.field("row_id", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("timestamp", pa.int64()),
        pa.field("timeframe", pa.string()),
        pa.field("mode", pa.string()),
        pa.field("side", pa.string()),  # LONG or SHORT — never "best"
        pa.field("simulation_profile_id", pa.string()),
        pa.field("dataset_version", pa.string()),
        # Pre-entry features (observable at/before timestamp)
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
        # Simulation truth (passed through, not recomputed)
        pa.field("gross_R", pa.float64()),
        pa.field("net_R", pa.float64()),
        pa.field("cost_R", pa.float64()),
        pa.field("mfe_R", pa.float64()),
        pa.field("mae_R", pa.float64()),
        pa.field("bars_held", pa.int64()),
        pa.field("exit_reason", pa.string()),
        pa.field("is_valid", pa.bool_()),
        pa.field("rejection_reason", pa.string()),
        # Derived research labels
        pa.field("profit_bucket", pa.string()),
        pa.field("is_profitable_state", pa.bool_()),
        pa.field("is_strong_win", pa.bool_()),
        pa.field("is_bad_state", pa.bool_()),
        pa.field("excess_net_R", pa.float64()),
        pa.field("excess_profit_bucket", pa.string()),
        # Lineage
        pa.field("simulation_run_id", pa.string()),
        pa.field("candidate_id", pa.string()),
    ])


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _make_row_id(symbol: str, timestamp_ms: int, side: str, idx: int) -> str:
    """Deterministic row identifier."""
    raw = f"{symbol}_{timestamp_ms}_{side}_{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _derive_profit_bucket(net_R: float) -> str:
    """Map net_R to a human-readable profit bucket."""
    if net_R <= PROFIT_BUCKET_EDGES[0]:
        return "big_loss"
    elif net_R <= PROFIT_BUCKET_EDGES[1]:
        return "loss"
    elif net_R <= PROFIT_BUCKET_EDGES[2]:
        return "breakeven"
    elif net_R <= PROFIT_BUCKET_EDGES[3]:
        return "small_win"
    elif net_R <= PROFIT_BUCKET_EDGES[4]:
        return "win"
    else:
        return "big_win"


def _derive_excess_bucket(excess: float) -> str:
    """Map excess_net_R to a bucket."""
    if excess <= -0.3:
        return "far_below_baseline"
    elif excess <= -0.05:
        return "below_baseline"
    elif excess <= 0.05:
        return "at_baseline"
    elif excess <= 0.3:
        return "above_baseline"
    else:
        return "far_above_baseline"


# ---------------------------------------------------------------------------
# CandidateOutcomeDatasetBuilder
# ---------------------------------------------------------------------------

class CandidateOutcomeDatasetBuilder:
    """Builds CandidateOutcomeDataset v002 from SimulationOutput + market data.

    Key design constraints:
    - Each SimulationOutput produces TWO rows (LONG + SHORT) when both sides
      have outcomes. NO best-of-side selection.
    - Simulation truth fields are passed through from SimulationOutput,
      never recomputed.
    - Pre-entry features are computed from market data available at/before
      the decision timestamp.
    - Research labels are derived from SimulationOutput fields only.

    Usage::

        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            btc_market_data=btc_records,
        )
        table = builder.build(simulation_outputs)
        summary = builder.compute_summary(table)
    """

    def __init__(
        self,
        market_data: Dict[str, List[Any]],
        btc_market_data: Optional[List[Any]] = None,
        funding_data: Optional[Dict[str, List[float]]] = None,
        lookback_bars: int = 50,
    ) -> None:
        self._market_data = market_data
        self._btc_market_data = btc_market_data
        self._funding_data = funding_data
        self._lookback_bars = lookback_bars

    def build(
        self,
        simulation_outputs: List[Any],
        excess_net_R: Optional[np.ndarray] = None,
    ) -> pa.Table:
        """Build the v002 dataset from simulation outputs.

        Args:
            simulation_outputs: List of SimulationOutput from simulation engine.
            excess_net_R: Optional pre-computed excess_net_R array (same length
                as simulation_outputs). If None, excess_net_R = net_R (no baseline
                normalization applied yet).

        Returns:
            pyarrow Table with v002 schema.
        """
        if not simulation_outputs:
            logger.info("build() called with empty simulation_outputs")
            return pa.Table.from_pydict(
                {f.name: [] for f in _v002_schema()},
                schema=_v002_schema(),
            )

        rows: List[Dict[str, Any]] = []

        for idx, sim_out in enumerate(simulation_outputs):
            # Emit LONG row
            long_row = self._build_row(sim_out, "LONG", idx, excess_net_R)
            if long_row is not None:
                rows.append(long_row)

            # Emit SHORT row
            short_row = self._build_row(sim_out, "SHORT", idx, excess_net_R)
            if short_row is not None:
                rows.append(short_row)

        if not rows:
            logger.warning("No valid rows from %d simulation outputs", len(simulation_outputs))
            return pa.Table.from_pydict(
                {f.name: [] for f in _v002_schema()},
                schema=_v002_schema(),
            )

        table = pa.Table.from_pylist(rows, schema=_v002_schema())
        return table.cast(_v002_schema())

    def _build_row(
        self,
        sim_out: Any,
        side: str,
        idx: int,
        excess_net_R: Optional[np.ndarray],
    ) -> Optional[Dict[str, Any]]:
        """Build a single row for one side of a simulation output."""
        # Select outcome based on side
        if side == "LONG":
            outcome = sim_out.long_outcome
        else:
            outcome = sim_out.short_outcome

        # Skip if outcome is None
        if outcome is None:
            return None

        # Compute pre-entry features
        features = self._compute_features(sim_out, idx)
        if features is None:
            return None

        # Extract simulation truth (pass-through, never recomputed)
        net_R = float(getattr(outcome, "realized_r_net", 0.0))
        gross_R = float(getattr(outcome, "realized_r_gross", 0.0))
        cost_R = float(getattr(outcome, "total_cost_r", 0.0))

        path_metrics = getattr(outcome, "path_metrics", None)
        mfe_R = float(getattr(path_metrics, "mfe_r", 0.0)) if path_metrics else 0.0
        mae_R = float(getattr(path_metrics, "mae_r", 0.0)) if path_metrics else 0.0
        bars_held = int(getattr(outcome, "hold_duration_bars", 0))
        exit_reason = str(getattr(outcome, "exit_reason", ""))

        # Validity check
        is_valid = net_R != 0.0 or bars_held > 0
        rejection_reason = "" if is_valid else "zero_outcome"

        # Excess net_R (from pre-computed array or identity)
        excess = net_R
        if excess_net_R is not None and idx < len(excess_net_R):
            excess = float(excess_net_R[idx])

        # Derived research labels
        profit_bucket = _derive_profit_bucket(net_R)
        excess_bucket = _derive_excess_bucket(excess)

        # Identity
        ts_ms = int(getattr(sim_out, "decision_timestamp", "2020-01-01T00:00:00Z")
                     .replace("-", "").replace("T", "").replace(":", "")[:13]) if False else 0
        try:
            dt = datetime.fromisoformat(str(sim_out.decision_timestamp))
            ts_ms = int(dt.timestamp() * 1000)
        except Exception:
            ts_ms = 0

        row_id = _make_row_id(sim_out.symbol, ts_ms, side, idx)
        candidate_id = f"{sim_out.simulation_run_id}_{sim_out.symbol}_{side}_{idx}"

        row = {
            # Identity
            "row_id": row_id,
            "symbol": sim_out.symbol,
            "timestamp": ts_ms,
            "timeframe": str(getattr(sim_out, "primary_interval", "")),
            "mode": str(getattr(sim_out, "mode", "")),
            "side": side,
            "simulation_profile_id": str(getattr(sim_out, "simulation_profile_id", "")),
            "dataset_version": DATASET_VERSION,
            # Pre-entry features
            **features,
            # Simulation truth (pass-through)
            "gross_R": gross_R,
            "net_R": net_R,
            "cost_R": cost_R,
            "mfe_R": mfe_R,
            "mae_R": mae_R,
            "bars_held": bars_held,
            "exit_reason": exit_reason,
            "is_valid": is_valid,
            "rejection_reason": rejection_reason,
            # Derived research labels
            "profit_bucket": profit_bucket,
            "is_profitable_state": net_R > 0,
            "is_strong_win": net_R > STRONG_WIN_THRESHOLD,
            "is_bad_state": net_R < BAD_STATE_THRESHOLD,
            "excess_net_R": excess,
            "excess_profit_bucket": excess_bucket,
            # Lineage
            "simulation_run_id": str(sim_out.simulation_run_id),
            "candidate_id": candidate_id,
        }

        return row

    def _compute_features(
        self, sim_out: Any, idx: int
    ) -> Optional[Dict[str, Any]]:
        """Compute pre-entry features from market data.

        All features use only data available at or before the decision timestamp.
        Returns None if features cannot be computed (missing data, insufficient lookback).
        """
        symbol = sim_out.symbol
        mdc = self._market_data.get(symbol)
        if mdc is None:
            return None

        records = mdc if isinstance(mdc, list) else mdc.records if hasattr(mdc, "records") else None
        if records is None or len(records) < self._lookback_bars:
            return None

        # Find entry bar index by timestamp
        try:
            dt = datetime.fromisoformat(str(sim_out.decision_timestamp))
            target_ts = int(dt.timestamp() * 1000)
        except Exception:
            return None

        # Binary search for timestamp
        lo, hi = 0, len(records) - 1
        entry_idx = None
        while lo <= hi:
            mid = (lo + hi) // 2
            ts = records[mid].timestamp
            if ts == target_ts:
                entry_idx = mid
                break
            elif ts < target_ts:
                lo = mid + 1
            else:
                hi = mid - 1
        if entry_idx is None:
            return None
        if entry_idx < self._lookback_bars:
            return None

        # Extract OHLCV arrays up to entry
        n = entry_idx + 1
        closes = np.array([r.close for r in records[:n]], dtype=np.float64)
        highs = np.array([r.high for r in records[:n]], dtype=np.float64)
        lows = np.array([r.low for r in records[:n]], dtype=np.float64)
        volumes = np.array([r.volume for r in records[:n]], dtype=np.float64)

        last_close = closes[-1]
        if last_close <= 0:
            return None

        # ATR — inline vectorized (no import dependency)
        n_bars = len(closes)
        tr = np.zeros(n_bars)
        tr[0] = highs[0] - lows[0]
        if n_bars > 1:
            tr[1:] = np.maximum(
                highs[1:] - lows[1:],
                np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
            )
        atr_raw = np.full(n_bars, np.nan)
        if n_bars >= 14:
            atr_raw[13] = np.mean(tr[:14])
            for _i in range(14, n_bars):
                atr_raw[_i] = (atr_raw[_i - 1] * 13 + tr[_i]) / 14
        last_atr = atr_raw[-1] if len(atr_raw) > 0 else 0.0
        atr_pct = (last_atr / last_close * 100.0) if last_atr > 0 else 0.0

        # SMA50
        sma50 = np.full(n, np.nan)
        if n >= 50:
            cs = np.cumsum(closes)
            sma50[49:] = (cs[49:] - np.concatenate([[0.0], cs[:n - 50]])) / 50

        # Linear slope
        slope_lookback = 10
        slope = np.nan
        if n >= slope_lookback:
            y = closes[-slope_lookback:]
            x = np.arange(slope_lookback, dtype=np.float64)
            xm = np.mean(x)
            xc = x - xm
            den = np.sum(xc ** 2)
            if den > 0:
                slope = float(np.sum((y - np.mean(y)) * xc) / den)

        # Regime
        sma50_val = sma50[-1] if not np.isnan(sma50[-1]) else None
        if sma50_val is not None and not np.isnan(slope):
            if last_close > sma50_val * 1.005 and slope > 0:
                regime_trend = "up"
            elif last_close < sma50_val * 0.995 and slope < 0:
                regime_trend = "down"
            else:
                regime_trend = "range"
        else:
            regime_trend = "range"

        # Volatility percentile
        volatility_window = 20
        vol_pct = 50.0
        if n >= volatility_window and atr_raw[-1] > 0:
            atr_pct_series = np.full(n, np.nan)
            for i in range(14, n):
                if closes[i] > 0 and not np.isnan(atr_raw[i]):
                    atr_pct_series[i] = atr_raw[i] / closes[i] * 100.0
            window = atr_pct_series[-volatility_window:]
            valid = window[~np.isnan(window)]
            if len(valid) >= 5:
                current = atr_pct_series[-1]
                vol_pct = float(np.sum(valid <= current) / len(valid) * 100.0)

        # Momentum rank
        momentum_period = 10
        mom_rank = 0.5
        if n >= momentum_period + 1:
            mom_raw = np.full(n, np.nan)
            valid_mask = closes[momentum_period:] > 0
            mom_raw[momentum_period:][valid_mask] = (
                (closes[momentum_period:][valid_mask] - closes[:n - momentum_period][valid_mask])
                / closes[:n - momentum_period][valid_mask]
            )
            if n >= momentum_period + volatility_window:
                window_mom = mom_raw[-volatility_window:]
            else:
                window_mom = mom_raw[momentum_period:]
            valid_mom = window_mom[~np.isnan(window_mom)]
            if len(valid_mom) >= 3:
                mn, mx = np.min(valid_mom), np.max(valid_mom)
                if mx > mn:
                    mom_rank = float((mom_raw[-1] - mn) / (mx - mn))

        # Volume zscore
        volume_window = 20
        vol_zscore = 0.0
        if n >= volume_window:
            vw = volumes[-volume_window:]
            vm, vs = np.mean(vw), np.std(vw)
            if vs > 1e-14:
                vol_zscore = float((volumes[-1] - vm) / vs)

        # Pullback ATR
        range_window = 20
        pullback_atr = 0.0
        if n >= range_window and last_atr > 0:
            recent_high = float(np.max(closes[-range_window:]))
            if recent_high > last_close:
                pullback_atr = (recent_high - last_close) / last_atr

        # Distance to range high
        dist_range = 0.5
        if n >= range_window:
            range_high = float(np.max(highs[-range_window:]))
            range_low = float(np.min(lows[-range_window:]))
            if range_high > range_low:
                dist_range = (last_close - range_low) / (range_high - range_low)

        # BTC regime
        btc_regime = "range"
        if self._btc_market_data and len(self._btc_market_data) > 50:
            btc_records = self._btc_market_data
            btc_closes = np.array([r.close for r in btc_records[:n]], dtype=np.float64) if len(btc_records) >= n else np.array([r.close for r in btc_records], dtype=np.float64)
            btc_n = len(btc_closes)
            if btc_n >= 50:
                btc_cs = np.cumsum(btc_closes)
                btc_sma = np.full(btc_n, np.nan)
                btc_sma[49:] = (btc_cs[49:] - np.concatenate([[0.0], btc_cs[:btc_n - 50]])) / 50
                btc_slope = np.nan
                if btc_n >= 10:
                    y = btc_closes[-10:]
                    x = np.arange(10, dtype=np.float64)
                    xc = x - np.mean(x)
                    den = np.sum(xc ** 2)
                    if den > 0:
                        btc_slope = float(np.sum((y - np.mean(y)) * xc) / den)
                btc_close = btc_closes[-1]
                btc_sma_val = btc_sma[-1] if not np.isnan(btc_sma[-1]) else None
                if btc_sma_val is not None and not np.isnan(btc_slope):
                    if btc_close > btc_sma_val * 1.005 and btc_slope > 0:
                        btc_regime = "up"
                    elif btc_close < btc_sma_val * 0.995 and btc_slope < 0:
                        btc_regime = "down"

        return {
            "regime_trend": regime_trend,
            "volatility_percentile": vol_pct,
            "momentum_rank": mom_rank,
            "volume_zscore": vol_zscore,
            "atr_pct": atr_pct,
            "btc_regime": btc_regime,
            "pullback_atr": pullback_atr,
            "distance_to_range_high": dist_range,
            "spread_proxy": 0.0,
            "funding_context": 0.0,
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def compute_summary(self, table: pa.Table) -> Dict[str, Any]:
        """Compute a comprehensive summary of the dataset."""
        n = table.num_rows
        if n == 0:
            return {"row_count": 0}

        summary: Dict[str, Any] = {
            "row_count": n,
            "dataset_version": DATASET_VERSION,
            "symbol_count": len(set(table.column("symbol").to_pylist())),
            "timeframe_count": len(set(table.column("timeframe").to_pylist())),
            "mode_count": len(set(table.column("mode").to_pylist())),
        }

        # Side distribution
        sides = table.column("side").to_pylist()
        summary["side_distribution"] = {
            "LONG": sides.count("LONG"),
            "SHORT": sides.count("SHORT"),
        }

        # Validity
        valid = table.column("is_valid").to_pylist()
        summary["invalid_row_count"] = valid.count(False)

        # Rejection reasons
        rejections = table.column("rejection_reason").to_pylist()
        rejection_types = {}
        for r in rejections:
            if r:
                rejection_types[r] = rejection_types.get(r, 0) + 1
        summary["rejection_reasons"] = rejection_types

        # net_R distribution
        net_R = table.column("net_R").to_numpy().astype(float)
        summary["net_R_distribution"] = {
            "mean": float(np.nanmean(net_R)),
            "median": float(np.nanmedian(net_R)),
            "std": float(np.nanstd(net_R)),
            "min": float(np.nanmin(net_R)),
            "max": float(np.nanmax(net_R)),
            "positive_rate": float(np.mean(net_R > 0)),
        }

        # gross_R distribution
        gross_R = table.column("gross_R").to_numpy().astype(float)
        summary["gross_R_distribution"] = {
            "mean": float(np.nanmean(gross_R)),
            "median": float(np.nanmedian(gross_R)),
        }

        # cost_R distribution
        cost_R = table.column("cost_R").to_numpy().astype(float)
        summary["cost_R_distribution"] = {
            "mean": float(np.nanmean(cost_R)),
            "median": float(np.nanmedian(cost_R)),
        }

        # MFE/MAE
        mfe = table.column("mfe_R").to_numpy().astype(float)
        mae = table.column("mae_R").to_numpy().astype(float)
        summary["mfe_R_distribution"] = {
            "mean": float(np.nanmean(mfe)),
            "median": float(np.nanmedian(mfe)),
        }
        summary["mae_R_distribution"] = {
            "mean": float(np.nanmean(mae)),
            "median": float(np.nanmedian(mae)),
        }

        # By-mode summary
        modes = table.column("mode").to_pylist()
        mode_groups: Dict[str, List[float]] = {}
        for i, m in enumerate(modes):
            mode_groups.setdefault(m, []).append(float(net_R[i]))
        summary["by_mode"] = {
            m: {
                "count": len(vals),
                "mean_net_R": float(np.mean(vals)) if vals else 0.0,
                "positive_rate": float(np.mean(np.array(vals) > 0)) if vals else 0.0,
            }
            for m, vals in mode_groups.items()
        }

        # By-side summary
        side_groups: Dict[str, List[float]] = {}
        for i, s in enumerate(sides):
            side_groups.setdefault(s, []).append(float(net_R[i]))
        summary["by_side"] = {
            s: {
                "count": len(vals),
                "mean_net_R": float(np.mean(vals)) if vals else 0.0,
                "positive_rate": float(np.mean(np.array(vals) > 0)) if vals else 0.0,
            }
            for s, vals in side_groups.items()
        }

        # By-symbol summary
        symbols = table.column("symbol").to_pylist()
        sym_groups: Dict[str, List[float]] = {}
        for i, s in enumerate(symbols):
            sym_groups.setdefault(s, []).append(float(net_R[i]))
        summary["by_symbol"] = {
            s: {
                "count": len(vals),
                "mean_net_R": float(np.mean(vals)) if vals else 0.0,
                "positive_rate": float(np.mean(np.array(vals) > 0)) if vals else 0.0,
            }
            for s, vals in sym_groups.items()
        }

        # Leakage guard
        summary["leakage_guard"] = {
            "side_oracle_removed": True,  # v002 never picks best side
            "local_simulation_absent": True,  # never computes stop/target
            "future_leakage_check": "no_outcome_in_features",
        }

        return summary
