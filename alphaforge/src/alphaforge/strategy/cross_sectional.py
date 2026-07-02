"""
v0.34A — Cross-Sectional Momentum Strategy Engine.

Non-ML profit baseline: rank symbols by momentum/trend at each
timestamp, long the strongest, short the weakest, skip the middle.
Economic gate prevents trading when expected spread < cost buffer.

Usage:
    from alphaforge.strategy.cross_sectional import (
        CrossSectionalMomentum,
        MomentumSignal,
        PortfolioResult,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "symbols": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
        "MATICUSDT", "NEARUSDT", "ATOMUSDT", "FILUSDT", "APTUSDT",
        "SUIUSDT", "OPUSDT", "ARBUSDT", "INJUSDT", "RUNEUSDT",
    ],
    "intervals": ["1h"],
    "start": "2023-01-01T00:00:00+00:00",
    "end": None,  # now
    # Momentum windows (in hours)
    "momentum_windows": [1, 4, 12, 24],
    # Portfolio
    "long_pct": 0.20,  # top 20%
    "short_pct": 0.20,  # bottom 20%
    "skip_pct": 0.60,  # middle 60%
    # Risk
    "max_exposure_pct": 0.40,  # max 40% gross exposure
    "max_symbols_per_side": 4,
    "volatility_target": 0.15,  # 15% annualized vol target per position
    "turnover_cap": 0.30,  # max 30% portfolio turnover per rebalance
    "cooldown_hours": 4,  # wait 4h after flip
    # Costs
    "taker_fee": 0.00045,
    "maker_fee": 0.00018,
    "slippage": 0.0005,
    "uncertainty_buffer": 0.001,
    # Rebalance
    "rebalance_hours": 4,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MomentumSignal:
    """Momentum/trend signal for one symbol at one timestamp."""

    timestamp: int
    symbol: str
    momentum_1h: float
    momentum_4h: float
    momentum_12h: float
    momentum_24h: float
    volatility: float
    composite_score: float
    rank: int = -1
    n_symbols: int = 0
    selected: str = "skip"  # "long", "short", "skip"

    @property
    def is_active(self) -> bool:
        return self.selected in ("long", "short")

    @property
    def direction(self) -> int:
        return 1 if self.selected == "long" else (-1 if self.selected == "short" else 0)


@dataclass(frozen=True)
class TradeResult:
    """Result of one executed trade leg."""

    timestamp: int
    symbol: str
    direction: int  # 1 = long, -1 = short
    entry_price: float
    exit_price: float
    gross_return: float
    cost: float
    net_return: float
    holding_hours: int
    reason: str = ""


@dataclass(frozen=True)
class PortfolioResult:
    """Full backtest result for the cross-sectional momentum strategy."""

    config: dict[str, Any] = field(default_factory=dict)
    trades: list[TradeResult] = field(default_factory=list)
    signals: list[MomentumSignal] = field(default_factory=list)
    symbol_returns: dict[str, float] = field(default_factory=dict)
    n_trades: int = 0
    n_long: int = 0
    n_short: int = 0
    gross_return: float = 0.0
    net_return: float = 0.0
    total_cost: float = 0.0
    max_drawdown: float = 0.0
    exposure_pct: float = 0.0
    turnover_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    n_rebalances: int = 0
    n_signals_generated: int = 0
    n_trades_gated: int = 0
    n_trades_executed: int = 0
    beat_no_trade: bool = False
    beat_random_ranker: bool = False
    pbo_risk: str = "NOT_CALCULATED"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Momentum scorer
# ---------------------------------------------------------------------------


def compute_momentum_score(
    closes: np.ndarray,
    windows: list[int] = DEFAULT_CONFIG["momentum_windows"],
) -> dict[str, float]:
    """Compute composite momentum score from multiple return horizons.

    Returns dict with individual momentum values and composite score.
    """
    n = len(closes)
    if n < max(windows):
        return {f"momentum_{w}h": 0.0 for w in windows} | {"composite": 0.0, "volatility": 0.0}

    result = {}
    returns = []
    for w in windows:
        mom = (closes[-1] - closes[-w - 1]) / max(closes[-w - 1], 1e-10)
        result[f"momentum_{w}h"] = float(mom)
        returns.append(mom)

    # Volatility (standard deviation of hourly returns over 24h)
    hourly_returns = np.diff(closes[-25:]) / np.maximum(closes[-25:-1], 1e-10)
    vol = float(np.std(hourly_returns)) if len(hourly_returns) > 1 else 0.0
    result["volatility"] = vol

    # Composite: weighted average with longer windows weighted more
    weights = np.array([0.1, 0.2, 0.3, 0.4])[:len(windows)]
    weights = weights / weights.sum()
    result["composite"] = float(np.dot(returns, weights))

    return result


# ---------------------------------------------------------------------------
# Cross-sectional ranker
# ---------------------------------------------------------------------------


def rank_symbols(
    symbol_data: dict[str, np.ndarray],
    timestamp_idx: int,
    windows: list[int],
) -> list[MomentumSignal]:
    """Rank all symbols at a given timestamp by composite momentum score.

    Args:
        symbol_data: dict mapping symbol -> close price array
        timestamp_idx: index into the arrays for current time
        windows: momentum computation windows

    Returns:
        List of MomentumSignal sorted by composite score descending.
    """
    signals = []
    for sym, closes in symbol_data.items():
        if timestamp_idx < max(windows):
            continue
        lookback = closes[max(0, timestamp_idx - max(windows)):timestamp_idx + 1]
        if len(lookback) < max(windows):
            continue

        score = compute_momentum_score(lookback, windows)
        signals.append(MomentumSignal(
            timestamp=timestamp_idx,
            symbol=sym,
            momentum_1h=score.get("momentum_1h", 0),
            momentum_4h=score.get("momentum_4h", 0),
            momentum_12h=score.get("momentum_12h", 0),
            momentum_24h=score.get("momentum_24h", 0),
            volatility=score.get("volatility", 0),
            composite_score=score.get("composite", 0),
        ))

    # Sort by composite score descending
    signals.sort(key=lambda s: s.composite_score, reverse=True)

    n = len(signals)
    for i, s in enumerate(signals):
        signals[i] = MomentumSignal(
            timestamp=s.timestamp,
            symbol=s.symbol,
            momentum_1h=s.momentum_1h,
            momentum_4h=s.momentum_4h,
            momentum_12h=s.momentum_12h,
            momentum_24h=s.momentum_24h,
            volatility=s.volatility,
            composite_score=s.composite_score,
            rank=i,
            n_symbols=n,
            selected=_select_side(i, n, DEFAULT_CONFIG),
        )

    return signals


def _select_side(rank: int, n: int, config: dict) -> str:
    """Assign long/short/skip based on rank percentile."""
    long_pct = config.get("long_pct", 0.20)
    short_pct = config.get("short_pct", 0.20)
    n_long = max(1, int(n * long_pct))
    n_short = max(1, int(n * short_pct))
    if rank < n_long:
        return "long"
    elif rank >= n - n_short:
        return "short"
    else:
        return "skip"


# ---------------------------------------------------------------------------
# Economic gate
# ---------------------------------------------------------------------------


def economic_gate(
    signal: MomentumSignal,
    price: float,
    config: dict,
    prev_side: str = "skip",
    cooldown_remaining: int = 0,
) -> tuple[bool, str]:
    """Decide whether to execute a signal.

    Returns (execute: bool, reason: str).
    """
    if cooldown_remaining > 0:
        return False, "cooldown"

    # Cost estimate
    taker = config.get("taker_fee", 0.00045)
    slippage = config.get("slippage", 0.0005)
    buffer = config.get("uncertainty_buffer", 0.001)
    roundtrip_cost = 2 * (taker + slippage) + buffer

    # Expected spread: absolute composite score proxies expected return
    expected_spread = abs(signal.composite_score)

    if expected_spread < roundtrip_cost:
        return False, f"spread {expected_spread:.6f} < cost {roundtrip_cost:.6f}"

    # Flip cooldown
    if signal.selected != prev_side and prev_side != "skip":
        return False, "flip_cooldown"

    return True, "pass"


# ---------------------------------------------------------------------------
# Portfolio backtester
# ---------------------------------------------------------------------------


def backtest_cross_sectional_momentum(
    symbol_data: dict[str, np.ndarray],
    timestamps: np.ndarray,
    prices: dict[str, np.ndarray],
    config: dict | None = None,
) -> PortfolioResult:
    """Run a full backtest of the cross-sectional momentum strategy.

    Args:
        symbol_data: dict[symbol -> close price array] (already aligned)
        timestamps: 1D array of timestamps for all symbols
        prices: dict[symbol -> close price array] (same as symbol_data)
        config: strategy config dict (uses DEFAULT_CONFIG if None)

    Returns:
        PortfolioResult with all performance metrics.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    windows = cfg["momentum_windows"]
    n_bars = len(timestamps)
    n_symbols = len(symbol_data)
    rebalance_every = cfg["rebalance_hours"]

    signals: list[MomentumSignal] = []
    trades: list[TradeResult] = []
    equity: list[float] = [1.0]
    n_gated = 0
    n_executed = 0
    n_cost_blocks = 0
    prev_positions: dict[str, int] = {}

    for bar in range(max(windows), n_bars):
        if (bar - max(windows)) % rebalance_every != 0:
            equity.append(equity[-1])
            continue

        # Rank symbols
        ranked = rank_symbols(symbol_data, bar, windows)
        signals.extend(ranked)

        # Apply economic gate
        active_positions: dict[str, int] = {}
        for signal in ranked:
            if not signal.is_active:
                continue
            if len(active_positions) >= cfg["max_symbols_per_side"] * 2:
                break

            price = prices[signal.symbol][bar]
            execute, reason = economic_gate(signal, price, cfg)
            if not execute:
                n_gated += 1
                if "cost" in reason:
                    n_cost_blocks += 1
                continue

            active_positions[signal.symbol] = signal.direction
            n_executed += 1

        # Compute portfolio return for this period
        if bar + 1 < n_bars:
            period_returns = []
            for sym, direction in active_positions.items():
                ret = (prices[sym][bar + 1] - prices[sym][bar]) / max(prices[sym][bar], 1e-10)
                period_returns.append(ret * direction)

            clean_returns = [r for r in period_returns if not np.isnan(r) and not np.isinf(r)]
            avg_return = float(np.mean(clean_returns)) if clean_returns else 0.0
            cost_charge = cfg["taker_fee"] + cfg["slippage"]

            # Track trades only when positions change
            for sym, direction in active_positions.items():
                if prev_positions.get(sym, 0) != direction:
                    trades.append(TradeResult(
                        timestamp=int(timestamps[bar]),
                        symbol=sym, direction=direction,
                        entry_price=prices[sym][bar],
                        exit_price=prices[sym][bar],
                        gross_return=0.0, cost=cost_charge, net_return=0.0,
                        holding_hours=rebalance_every, reason="entry",
                    ))
            for sym in list(prev_positions.keys()):
                if sym not in active_positions and prev_positions[sym] != 0:
                    trades.append(TradeResult(
                        timestamp=int(timestamps[bar]),
                        symbol=sym, direction=prev_positions[sym],
                        entry_price=prices[sym][bar],
                        exit_price=prices[sym][bar],
                        gross_return=0.0, cost=cost_charge, net_return=0.0,
                        holding_hours=rebalance_every, reason="exit",
                    ))

            prev_positions = active_positions
            equity.append(equity[-1] * (1 + avg_return - cost_charge))

    # Compute metrics
    equity_arr = np.array(equity)
    total_return = float(equity_arr[-1] - 1.0)
    n_trades = len(trades)
    peak = np.maximum.accumulate(equity_arr)
    dd = (equity_arr - peak) / peak
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0.0
    returns = np.diff(equity_arr)
    pos_r = returns[returns > 0].sum()
    neg_r = abs(returns[returns < 0].sum())
    pf = float(pos_r / max(neg_r, 1e-10)) if neg_r > 0 else 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(365 * 24))
    else:
        sharpe = 0.0
    total_possible = n_bars * n_symbols
    exposure = float(n_executed / max(total_possible, 1) * 100)
    n_long = sum(1 for t in trades if t.direction > 0)
    n_short = sum(1 for t in trades if t.direction < 0)

    return PortfolioResult(
        config=cfg,
        trades=trades,
        signals=signals,
        n_trades=n_trades,
        n_long=n_long,
        n_short=n_short,
        gross_return=total_return,
        net_return=total_return,
        total_cost=n_trades * (cfg["taker_fee"] + cfg["slippage"]),
        max_drawdown=round(max_dd, 4),
        exposure_pct=round(exposure, 1),
        turnover_pct=0.0,
        profit_factor=round(pf, 4),
        sharpe=round(sharpe, 4),
        n_rebalances=n_bars // rebalance_every,
        n_signals_generated=len(signals),
        n_trades_gated=n_gated,
        n_trades_executed=n_executed,
        beat_no_trade=total_return > 0,
        beat_random_ranker=False,
    )
