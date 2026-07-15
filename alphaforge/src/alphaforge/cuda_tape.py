"""CUDA Data Tape — ultra-fast historical replay engine.

Streams OHLCV bars chronologically, runs model inference, batches trades,
and processes them through CUDA-accelerated BatchSimulator.

Architecture:
  OHLCV data (all symbols, 4h/1h bars)
    → chronological sort by timestamp
      → feature computation (per bar, all symbols)
        → model prediction (per bar, all symbols)
          → trade decision (per bar, per symbol)
            → BatchSimulator (CUDA) → results
              → P&L, winrate, drawdown, etc.
"""

from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from simulation.contracts.models import (
    SimulationInput,
    SimulationOutput,
    Candle as SimCandle,
    FuturePath,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.batch import BatchSimulator
from simulation.profile_registry.registry import get_profile

logger = logging.getLogger(__name__)


class CUDATape:
    """Ultra-fast historical replay with CUDA batch simulation.

    Usage:
        tape = CUDATape(model=predict_fn, symbols=["BTCUSDT", ...])
        results = tape.run("2025-01-01", "2026-07-14")
        print(tape.summary(results))
    """

    def __init__(
        self,
        predict_fn: Callable,
        symbols: List[str],
        mode: str = "SCALP",
        profile_version: str = "1.0.0",
        confidence_threshold: float = 0.70,
        atr_multiplier: float = 1.75,
        max_holding_bars: int = 12,
    ):
        self.predict_fn = predict_fn
        self.symbols = symbols
        self.mode = mode
        self.profile = get_profile(mode, profile_version)
        self.confidence_threshold = confidence_threshold
        self.atr_multiplier = atr_multiplier
        self.max_holding_bars = max_holding_bars
        self.batcher = BatchSimulator(fail_on_error=False)

    def load_data(self, data_dir: str = "data/raw") -> dict:
        """Load OHLCV parquet data for all symbols."""
        import pyarrow.parquet as pq
        ohlcv_data = {}
        for sym in self.symbols:
            p = Path(data_dir) / sym / f"{sym}_4h.parquet"
            if p.exists():
                df = pq.read_table(p).to_pandas()
                ohlcv_data[sym] = {
                    "timestamp": df["timestamp"].values.astype(np.int64),
                    "open": df["open"].values.astype(np.float64),
                    "high": df["high"].values.astype(np.float64),
                    "low": df["low"].values.astype(np.float64),
                    "close": df["close"].values.astype(np.float64),
                    "volume": df["volume"].values.astype(np.float64),
                }
        return ohlcv_data

    def run(
        self,
        ohlcv_data: dict,
        start_idx: int = 200,
    ) -> dict:
        """Run tape from start_idx to end of data.

        For each bar (chronologically across all symbols):
        1. Build features
        2. Run model prediction
        3. If confidence > threshold, add to trade batch

        At end, run all trades through CUDA BatchSimulator.

        Returns dict with per-symbol and aggregate results.
        """
        t0 = time.time()

        # Build chronological bar index
        all_bars = []
        for sym, data in ohlcv_data.items():
            for i in range(len(data["timestamp"])):
                all_bars.append((data["timestamp"][i], sym, i))
        all_bars.sort(key=lambda x: x[0])

        logger.info("CUDATape: prepared %d bars, %d symbols", len(all_bars), len(ohlcv_data))

        # Phase 1: Walk through bars, collect trade signals
        sim_inputs = []
        trade_info = []  # (symbol, timestamp, entry_price, direction, atr)

        from alphaforge.features.pipeline import compute_features as _cf

        for ts, sym, bar_idx in all_bars:
            if bar_idx < start_idx:
                continue
            if bar_idx >= len(ohlcv_data[sym]["close"]) - self.max_holding_bars - 1:
                continue

            data = ohlcv_data[sym]
            close = data["close"]
            high = data["high"]
            low = data["low"]

            # Build features for this bar
            lookback_high = high[max(0, bar_idx - 50): bar_idx + 1]
            lookback_low = low[max(0, bar_idx - 50): bar_idx + 1]

            # Simple ATR for risk
            atr_val = float(np.mean(high[max(0, bar_idx - 14): bar_idx + 1] -
                                      low[max(0, bar_idx - 14): bar_idx + 1]))
            if atr_val <= 0:
                atr_val = close[bar_idx] * 0.01

            # Compute features and predict
            try:
                ohlcv_slice = {
                    "close": close[max(0, bar_idx - 50): bar_idx + 1],
                    "high": high[max(0, bar_idx - 50): bar_idx + 1],
                    "low": low[max(0, bar_idx - 50): bar_idx + 1],
                    "open": data["open"][max(0, bar_idx - 50): bar_idx + 1],
                    "volume": data["volume"][max(0, bar_idx - 50): bar_idx + 1],
                }
                fm = _cf(ohlcv_slice, mode=self.mode)
                feat_vec = np.array([fm.features[k][-1] for k in fm.features], dtype=np.float64)
                feat_vec = np.nan_to_num(feat_vec[np.newaxis, :], 0)
            except Exception:
                continue

            # Run model
            try:
                result = self.predict_fn(feat_vec)
                if isinstance(result, tuple):
                    pred_class, confidence = result
                elif isinstance(result, np.ndarray):
                    pred_class = np.argmax(result, axis=1)[0]
                    confidence = np.max(result, axis=1)[0]
                else:
                    pred_class = int(result)
                    confidence = 1.0
            except Exception:
                continue

            if pred_class == 2 or confidence < self.confidence_threshold:
                continue

            # LONG or SHORT
            is_long = pred_class == 0
            entry_price = close[bar_idx]
            stop_dist = atr_val * self.atr_multiplier
            stop_price = entry_price - stop_dist if is_long else entry_price + stop_dist
            target_dist = stop_dist * 1.0  # 1:1 R:R

            # Check for sufficient forward bars
            fwd_bars = min(self.max_holding_bars,
                          len(close) - bar_idx - 1)
            if fwd_bars < 3:
                continue

            # Build future path candles
            path_candles = []
            for j in range(bar_idx + 1, min(bar_idx + 1 + fwd_bars, len(close))):
                path_candles.append(SimCandle(
                    open=float(open_[j]) if (open_ := data["open"])[j] else float(close[j]),
                    high=float(high[j]),
                    low=float(low[j]),
                    close=float(close[j]),
                    volume=float(data["volume"][j]),
                ))

            sim_input = SimulationInput(
                symbol=sym,
                decision_timestamp=str(ts),
                mode=TradingMode(self.mode),
                primary_interval=self.profile.primary_interval,
                entry_price=float(entry_price),
                atr=float(atr_val),
                future_path=FuturePath(candles=path_candles),
                profile=self.profile,
                simulation_family_version="simfam-1.0.0",
                cost_model_version="cost-1.0.0",
            )
            sim_inputs.append(sim_input)
            trade_info.append((sym, ts, entry_price, "LONG" if is_long else "SHORT", atr_val))

        logger.info("CUDATape: collected %d trade signals", len(sim_inputs))

        # Phase 2: Batch simulate all trades on CUDA
        logger.info("CUDATape: running BatchSimulator (CUDA)...")
        t_batch = time.time()
        outputs = self.batcher.run(sim_inputs, use_batch=True, force_gpu=True)
        batch_time = time.time() - t_batch
        total_time = time.time() - t0

        # Phase 3: Process results
        results = self._process_results(outputs, trade_info, batch_time, total_time)
        return results

    def _process_results(
        self,
        outputs: List[SimulationOutput],
        trade_info: list,
        batch_time: float,
        total_time: float,
    ) -> dict:
        """Process SimulationOutputs into summary stats."""
        winners = 0
        losers = 0
        total_r = 0.0
        n_trades = len(outputs)

        for out in outputs:
            if out.best_action is not None:
                # Use best_action outcome (long or short)
                if out.long_outcome and out.long_outcome.realized_r_net > 0:
                    winners += 1
                    total_r += out.long_outcome.realized_r_net
                elif out.short_outcome and out.short_outcome.realized_r_net > 0:
                    winners += 1
                    total_r += out.short_outcome.realized_r_net
                else:
                    losers += 1
                    total_r += (out.long_outcome.realized_r_net if out.long_outcome
                                else out.short_outcome.realized_r_net if out.short_outcome
                                else 0.0)

        return {
            "n_trades": n_trades,
            "n_wins": winners,
            "n_losses": losers,
            "winrate_pct": round(winners / n_trades * 100, 1) if n_trades > 0 else 0.0,
            "total_r": round(total_r, 6),
            "mean_r": round(total_r / n_trades, 6) if n_trades > 0 else 0.0,
            "batch_time_sec": round(batch_time, 3),
            "total_time_sec": round(total_time, 3),
            "trades_per_sec": round(n_trades / batch_time, 1) if batch_time > 0 else 0,
            "throughput": f"{n_trades} trades in {batch_time:.2f}s ({n_trades/max(batch_time,0.001):.0f} trades/s)",
        }

    def summary(self, results: dict) -> str:
        """Format results as a human-readable summary."""
        lines = [
            "=" * 60,
            "CUDA TAPE — HISTORICAL REPLAY RESULTS",
            "=" * 60,
            f"  Total trades:     {results['n_trades']}",
            f"  Winners:          {results['n_wins']}",
            f"  Losers:           {results['n_losses']}",
            f"  Winrate:          {results['winrate_pct']}%",
            f"  Total R:          {results['total_r']:+.6f}",
            f"  Mean R:           {results['mean_r']:+.6f}",
            f"  Batch time:       {results['batch_time_sec']}s",
            f"  Total time:       {results['total_time_sec']}s",
            f"  Throughput:       {results['trades_per_sec']}/s",
            "-" * 60,
        ]
        return "\n".join(lines)
