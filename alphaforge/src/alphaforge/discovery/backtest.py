"""Simulation backtest bridge — runs trade signals through the simulation engine.

Takes structured TradeSignal objects and OHLCV data, constructs
``SimulationInput`` for each signal, simulates them through the
authoritative simulation engine, and returns structured results.

This is the bridge between AlphaForge (signal discovery) and Simulation
(economic truth).  It follows the same pattern as
``alphaforge.factors.simulation_adapter`` but for XGBoost model-derived
signals rather than factor scores.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from alphaforge.discovery import BacktestTradeResult, TradeSignal
from simulation.adapters.training_adapter import TrainingAdapter
from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from alphaforge.train import MODE_CONFIG

logger = logging.getLogger("alphaforge.discovery.backtest")

# Fill probability assumptions for MAKER execution mode
_FILL_ASSUMPTIONS = {
    "pessimistic": 0.50,  # bar must trade THROUGH price by 0.05%
    "base": 0.70,         # touch + 1 tick (existing default)
    "optimistic": 0.85,   # touch only
}


# ---------------------------------------------------------------------------
# Profile mapping
# ---------------------------------------------------------------------------


def _build_profile(mode: str, stop_mult: float, target_mult: float,
                   max_hold: int,
                   execution_mode: str = "TAKER",
                   maker_fill_assumption: str = "base") -> SimulationProfile:
    """Build a SimulationProfile from mode config parameters.

    Mirrors the pattern in ``factors.simulation_adapter._map_config_to_profile``
    but uses the canonical mode key rather than inferring from timeframe.

    Args:
        execution_mode: "TAKER" (default), "MAKER", or "HYBRID"
        maker_fill_assumption: Fill probability tier for MAKER mode.
            "pessimistic" (0.50), "base" (0.70), "optimistic" (0.85)
    """
    if mode == "SWING":
        trading_mode = TradingMode.SWING
        primary_interval = "4h"
    elif mode == "SCALP":
        trading_mode = TradingMode.SCALP
        primary_interval = "1h"
    elif mode == "AGGRESSIVE_SCALP":
        trading_mode = TradingMode.AGGRESSIVE_SCALP
        primary_interval = "15m"
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return SimulationProfile(
        profile_version="discovery-adapted-1.0.0",
        mode=trading_mode,
        primary_interval=primary_interval,
        max_holding_bars=max_hold,
        stop_multiplier=stop_mult,
        target_multiplier=target_mult,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=False,
        stop_method="atr_wide",
        target_method="atr_wide",
        mae_penalty_weight=1.0,
        cost_penalty_weight=1.0,
        time_penalty_weight=0.3,
        funding_rate=0.0,
        execution_mode=execution_mode,
        maker_fill_probability=_FILL_ASSUMPTIONS.get(maker_fill_assumption, 0.7),
        maker_fill_assumption=maker_fill_assumption,
    )


# ---------------------------------------------------------------------------
# Future path extraction
# ---------------------------------------------------------------------------


def _extract_future_candles(
    ohlcv: dict,
    symbol: str,
    timestamp: int,
    max_hold: int,
    search_index: dict | None = None,
) -> list[Candle]:
    """Extract forward OHLCV candles from *timestamp* for *symbol*.

    When a pre-built ``search_index`` is provided (from ``_build_search_index()``),
    uses pre-extracted per-symbol sub-arrays for O(1) lookup instead of
    full-array scans.
    """
    if search_index is not None:
        sym_data = search_index.get(symbol)
        if sym_data is None:
            return []
        ts_map = sym_data["ts_map"]
        start_idx = ts_map.get(timestamp, -1)
        if start_idx < 0:
            return []
        # Use pre-extracted sub-arrays — fast sequential access
        n = len(sym_data["close"])
        s = start_idx
        end = min(s + max_hold + 1, n)
        close_arr = sym_data["close"]
        high_arr = sym_data["high"]
        low_arr = sym_data["low"]
        open_arr = sym_data["open"]
        candles: list[Candle] = []
        for i in range(s, end):
            c = float(close_arr[i])
            h = float(high_arr[i])
            l = float(low_arr[i])
            o = float(open_arr[i])
            if np.isfinite(c) and np.isfinite(h) and np.isfinite(l) and np.isfinite(o):
                candles.append(Candle(open=o, high=h, low=l, close=c))
        return candles
    else:
        # Fallback: original full-array scan
        close_arr = ohlcv["close"].astype(np.float64)
        high_arr = ohlcv["high"].astype(np.float64)
        low_arr = ohlcv["low"].astype(np.float64)
        open_arr = ohlcv["open"].astype(np.float64)
        sym_arr = np.array([str(s) for s in ohlcv.get("symbol", [])], dtype=object)
        ts_arr = np.array(ohlcv.get("timestamp", np.arange(len(close_arr))), dtype=np.int64)
        matches = np.where((sym_arr == symbol) & (ts_arr == timestamp))[0]
        start_idx = int(matches[0]) if len(matches) > 0 else -1
        if start_idx < 0:
            return []
        n = len(sym_arr)
        candles: list[Candle] = []
        idx = start_idx
        collected = 0
        while idx < n and str(sym_arr[idx]) == symbol and collected < max_hold + 1:
            c = float(close_arr[idx])
            h = float(high_arr[idx])
            l = float(low_arr[idx])
            o = float(open_arr[idx])
            if np.isfinite(c) and np.isfinite(h) and np.isfinite(l) and np.isfinite(o):
                candles.append(Candle(open=o, high=h, low=l, close=c))
            collected += 1
            idx += 1
        return candles


def _build_search_index(ohlcv: dict) -> dict:
    """Build per-symbol sub-arrays and (timestamp → local index) lookup.

    Returns dict keyed by symbol, each containing:
      - ts_map: dict[int, int] — timestamp → local index
      - close/high/low/open: per-symbol sub-arrays
    """
    sym_arr = np.array([str(s) for s in ohlcv.get("symbol", [])], dtype=object)
    ts_arr = np.array(ohlcv.get("timestamp", np.arange(len(sym_arr))), dtype=np.int64)
    close_arr = ohlcv["close"].astype(np.float64)
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)
    open_arr = ohlcv["open"].astype(np.float64)

    # Group by symbol
    unique_syms = np.unique(sym_arr)
    index: dict[str, dict] = {}
    for sym in unique_syms:
        mask = sym_arr == sym
        idx = np.where(mask)[0]
        # Build ts_map: timestamp → local index (0-based within symbol's data)
        ts_local = ts_arr[idx]
        index[str(sym)] = {
            "ts_map": {int(ts_local[j]): int(j) for j in range(len(idx))},
            "close": close_arr[idx],
            "high": high_arr[idx],
            "low": low_arr[idx],
            "open": open_arr[idx],
        }
    return index


# ---------------------------------------------------------------------------
# Backtest entry point
# ---------------------------------------------------------------------------


def backtest_signals(
    signals: list[TradeSignal],
    ohlcv: dict,
    mode: str,
    adapter: TrainingAdapter | None = None,
    reject_on_missing_future: bool = False,
    execution_mode: str = "TAKER",
    maker_fill_assumption: str = "base",
    use_batch: bool = True,
) -> list[BacktestTradeResult]:
    """Run trade signals through the simulation engine.

    For each non-NO_TRADE signal, constructs a ``SimulationInput`` with the
    forward OHLCV path and runs it through the simulation engine via
    ``TrainingAdapter``.

    When ``use_batch`` is True (default) and there are many signals, uses the
    GPU/CPU-accelerated ``BatchSimulator`` to process all signals in a single
    batched call (avoids per-signal Python overhead).

    Parameters
    ----------
    signals:
        Trade signals from ``generate_trade_signals()``.
    ohlcv:
        OHLCV data dict (keys: ``close``, ``high``, ``low``, ``open``).
        Must be concatenated per-symbol with ``symbol`` and ``timestamp`` keys.
    mode:
        Trading mode key (e.g. ``'SWING'``).
    adapter:
        Pre-initialized ``TrainingAdapter`` (created fresh if not provided).
    reject_on_missing_future:
        If True, raises when a signal has no future path.  Default False
        skips those signals with a warning.
    use_batch:
        If True, use GPU/CPU-accelerated batch path (default True).
        Set False to force the original per-signal Python loop (debugging).

    Returns
    -------
    list[BacktestTradeResult]
        One result per successfully simulated trade.
    """
    cfg = MODE_CONFIG[mode]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    max_hold = cfg["max_hold"]

    profile = _build_profile(mode, stop_mult, target_mult, max_hold,
                             execution_mode=execution_mode,
                             maker_fill_assumption=maker_fill_assumption)

    # Build all SimulationInput objects first (this is fast with pre-built index)
    sim_inputs: list[SimulationInput] = []
    sig_index: list[int] = []  # maps sim_input index → signal index
    skipped_no_future = 0
    search_index = _build_search_index(ohlcv)  # O(N) once, then O(1) per signal

    for si, sig in enumerate(signals):
        future_candles = _extract_future_candles(
            ohlcv, sig.symbol, sig.timestamp, max_hold,
            search_index=search_index,
        )
        if len(future_candles) < 2:
            skipped_no_future += 1
            if reject_on_missing_future:
                raise ValueError(
                    f"No future path for {sig.symbol} at bar {sig.bar_index}"
                )
            continue

        sim_inputs.append(SimulationInput(
            symbol=sig.symbol,
            decision_timestamp=str(sig.timestamp),
            mode=profile.mode,
            primary_interval=profile.primary_interval,
            entry_price=sig.entry_price,
            atr=sig.atr,
            future_path=FuturePath(
                candles=future_candles,
                completeness_status="COMPLETE",
                expected_bars=max_hold,
            ),
            profile=profile,
        ))
        sig_index.append(si)

    if not sim_inputs:
        return []

    # Run simulations — batch path if available, else per-signal
    sim_outputs: list[SimulationOutput]
    skipped_degenerate = 0

    if use_batch and len(sim_inputs) >= 10:
        # GPU/CPU-accelerated batch path
        from simulation.engine.batch import BatchSimulator
        try:
            batcher = BatchSimulator()
            sim_outputs = batcher.run(sim_inputs, use_batch=True)
            logger.info(
                "Batched %d signals → %d simulated",
                len(signals), len(sim_outputs),
            )
        except Exception as e:
            logger.warning("Batch simulation failed (%s) — falling back", e)
            sim_outputs = []
            for idx, sim_input in enumerate(sim_inputs):
                try:
                    if adapter is None:
                        from simulation.adapters.training_adapter import TrainingAdapter
                        adapter = TrainingAdapter()
                    so = adapter.run(sim_input)
                    sim_outputs.append(so)
                except Exception as e2:
                    logger.warning("Sim failed for signal %d: %s",
                                   sig_index[idx], e2)
                    skipped_degenerate += 1
    else:
        # Original per-signal Python loop
        sim_outputs = []
        for idx, sim_input in enumerate(sim_inputs):
            try:
                if adapter is None:
                    from simulation.adapters.training_adapter import TrainingAdapter
                    adapter = TrainingAdapter()
                so = adapter.run(sim_input)
                sim_outputs.append(so)
            except Exception as e:
                logger.warning("Sim failed for signal %d: %s",
                               sig_index[idx], e)
                skipped_degenerate += 1

    # Build BacktestTradeResult from simulation outputs
    results: list[BacktestTradeResult] = []
    for idx, sim_output in enumerate(sim_outputs):
        sig = signals[sig_index[idx]]

        # Extract the outcome that matches our trade side
        if sig.side == "LONG":
            outcome = sim_output.long_outcome
        else:
            outcome = sim_output.short_outcome

        if outcome is None:
            skipped_degenerate += 1
            continue

        results.append(BacktestTradeResult(
            signal=sig,
            realized_r_net=outcome.realized_r_net,
            realized_r_gross=outcome.realized_r_gross,
            fee_cost_r=outcome.fee_cost_r,
            slippage_cost_r=outcome.slippage_cost_r,
            funding_cost_r=outcome.funding_cost_r,
            hold_bars=outcome.hold_duration_bars,
            exit_price=outcome.exit_price,
            exit_reason=outcome.exit_reason,
            path_quality_score=(
                outcome.path_metrics.path_quality_score
                if outcome.path_metrics else 0.0
            ),
            no_trade_saved_loss_r=sim_output.no_trade_outcome.saved_loss_r,
            no_trade_missed_opportunity_r=(
                sim_output.no_trade_outcome.missed_opportunity_r
            ),
        ))

    if skipped_no_future or skipped_degenerate:
        logger.info(
            "Backtest: %d/%d simulated, %d no-future, %d degenerate",
            len(results), len(signals), skipped_no_future, skipped_degenerate,
        )

    return results
