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


# ---------------------------------------------------------------------------
# Profile mapping
# ---------------------------------------------------------------------------


def _build_profile(mode: str, stop_mult: float, target_mult: float,
                   max_hold: int) -> SimulationProfile:
    """Build a SimulationProfile from mode config parameters.

    Mirrors the pattern in ``factors.simulation_adapter._map_config_to_profile``
    but uses the canonical mode key rather than inferring from timeframe.
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
    )


# ---------------------------------------------------------------------------
# Future path extraction
# ---------------------------------------------------------------------------


def _extract_future_candles(
    ohlcv: dict,
    symbol: str,
    timestamp: int,
    max_hold: int,
) -> list[Candle]:
    """Extract forward OHLCV candles from *timestamp* for *symbol*.

    Finds the bar in the raw OHLCV data matching (*symbol*, *timestamp*),
    then collects up to *max_hold + 1* subsequent bars for the same symbol.

    Returns an empty list if the entry bar is not found or not enough
    future data exists.
    """
    close_arr = ohlcv["close"].astype(np.float64)
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)
    open_arr = ohlcv["open"].astype(np.float64)
    ts_arr = np.array(ohlcv.get("timestamp", np.arange(len(close_arr))), dtype=np.int64)
    sym_arr = np.array([str(s) for s in ohlcv.get("symbol", [])], dtype=object)

    # Find the entry bar index
    matches = np.where((sym_arr == symbol) & (ts_arr == timestamp))[0]
    if len(matches) == 0:
        return []
    start_idx = matches[0]
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


# ---------------------------------------------------------------------------
# Backtest entry point
# ---------------------------------------------------------------------------


def backtest_signals(
    signals: list[TradeSignal],
    ohlcv: dict,
    mode: str,
    adapter: TrainingAdapter | None = None,
    reject_on_missing_future: bool = False,
) -> list[BacktestTradeResult]:
    """Run trade signals through the simulation engine.

    For each non-NO_TRADE signal, constructs a ``SimulationInput`` with the
    forward OHLCV path and runs it through the simulation engine via
    ``TrainingAdapter``.

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

    Returns
    -------
    list[BacktestTradeResult]
        One result per successfully simulated trade.
    """
    cfg = MODE_CONFIG[mode]
    stop_mult = cfg["stop_mult"]
    target_mult = cfg["target_mult"]
    max_hold = cfg["max_hold"]

    profile = _build_profile(mode, stop_mult, target_mult, max_hold)
    sim_adapter = adapter if adapter is not None else TrainingAdapter()

    results: list[BacktestTradeResult] = []
    skipped_no_future = 0
    skipped_degenerate = 0

    for sig in signals:
        # Extract future candles by (symbol, timestamp)
        future_candles = _extract_future_candles(
            ohlcv, sig.symbol, sig.timestamp, max_hold,
        )

        if len(future_candles) < 2:
            skipped_no_future += 1
            if reject_on_missing_future:
                raise ValueError(
                    f"No future path for {sig.symbol} at bar {sig.bar_index}"
                )
            continue

        # Build SimulationInput
        sim_input = SimulationInput(
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
        )

        # Run simulation
        try:
            sim_output: SimulationOutput = sim_adapter.run(sim_input)
        except Exception as e:
            logger.warning("Simulation failed for %s bar %d: %s",
                           sig.symbol, sig.bar_index, e)
            continue

        # Extract the outcome that matches our trade side
        if sig.side == "LONG":
            outcome = sim_output.long_outcome
        else:
            outcome = sim_output.short_outcome

        if outcome is None:
            skipped_degenerate += 1
            continue

        # Build result
        result = BacktestTradeResult(
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
        )
        results.append(result)

    if skipped_no_future or skipped_degenerate:
        logger.info(
            "Backtest: %d/%d simulated, %d no-future, %d degenerate",
            len(results), len(signals), skipped_no_future, skipped_degenerate,
        )

    return results
