"""
simulation/authority — TEK source of truth for costs, stop/target, and label simulation.

This is the SINGLE authority module. Requirements:
  - Every system component (evaluator, fast_simulator, XGBoost train.py, …)
    MUST call these functions rather than reimplementing cost/label logic.
  - Any file found with hardcoded cost constants (fee_pct=0.*, DEFAULT_TAKER_FEE_BPS,
    TOTAL_COST_RATE, round_trip_cost_r, etc.) FAILS CI — unless it is this file.
  - The golden parity test (test_authority.py) verifies that every label code path
    produces the same R as a direct simulation.engine call.

Import boundary: authority.py may import from simulation.engine and simulation.contracts.
Must NOT import from other domain packages (v7/alphaforge/runtime/interface).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Tuple

import numpy as np

from simulation.contracts.models import (
    ActionOutcome,
    Candle,
    FuturePath,
    NoTradeOutcome,
    PathMetrics,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.costs import (
    DEFAULT_MAKER_FEE_BPS,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_TAKER_FEE_BPS,
    compute_entry_risk,
    fee_cost_r,
    slippage_cost_r,
    total_cost_r,
)
from simulation.engine.engine import simulate


# ═══════════════════════════════════════════════════════════════════════
# 1. Authoritative Mode Profiles
# ═══════════════════════════════════════════════════════════════════════
# Source of truth: simulation/docs/profiles.md
# SWING target multiplier kept at 2.5 per golden test (profiles.md says 2.0 — TBD).

AUTHORITY_PROFILES: dict[str, SimulationProfile] = {
    "SCALP": SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SCALP,
        primary_interval="1h",
        max_holding_bars=12,
        stop_multiplier=1.5,
        target_multiplier=1.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.15,
        no_trade_default=True,
        mae_penalty_weight=2.0,
        cost_penalty_weight=2.0,
        time_penalty_weight=1.5,
    ),
}

VALID_MODES = frozenset(AUTHORITY_PROFILES.keys())


def get_profile(mode: str) -> SimulationProfile:
    """Return the authoritative simulation profile for a trading mode.

    Raises ValueError for unknown modes — no silent fallback.
    """
    profile = AUTHORITY_PROFILES.get(mode.upper())
    if profile is None:
        raise ValueError(
            f"Unknown trading mode: {mode}. "
            f"Valid modes: {sorted(VALID_MODES)}"
        )
    return profile


# ═══════════════════════════════════════════════════════════════════════
# 2. Cost Authority
# ═══════════════════════════════════════════════════════════════════════
# These are the ONLY functions that compute or expose costs.
# No other module may redefine fee_pct, slippage_bps, total_cost_r, etc.

COST_CONSTANTS = MappingProxyType({
    "taker_fee_bps": DEFAULT_TAKER_FEE_BPS,          # 4.0 bps (0.04%)
    "maker_fee_bps": DEFAULT_MAKER_FEE_BPS,           # 2.0 bps (0.02%)
    "slippage_bps": DEFAULT_SLIPPAGE_BPS,             # 1.0 bps (0.01%)
    "round_trip_taker_fee_bps": DEFAULT_TAKER_FEE_BPS * 2,   # 8.0 bps
    "round_trip_slippage_bps": DEFAULT_SLIPPAGE_BPS * 2,     # 2.0 bps
    "total_round_trip_cost_bps": (DEFAULT_TAKER_FEE_BPS + DEFAULT_SLIPPAGE_BPS) * 2,  # 10.0 bps
})


def get_cost_constants() -> dict:
    """Return authoritative cost constants (read-only copy)."""
    return dict(COST_CONSTANTS)


def get_cost_per_trade_r(
    notional: float,
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    holding_bars: int = 0,
    funding_rate: float = 0.0,
) -> Tuple[float, float, float, float]:
    """Compute all costs in R-multiples via the authoritative cost model.

    Returns (fee_cost_r, slippage_cost_r, funding_cost_r, total_cost_r).
    Every pipeline component MUST call this instead of reimplementing cost logic.
    """
    return total_cost_r(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=stop_multiplier,
        funding_rate=funding_rate,
        holding_bars=holding_bars,
    )


def get_stop_target_multipliers(mode: str) -> Tuple[float, float]:
    """Get authoritative stop/target multipliers for a mode.

    Returns (stop_multiplier, target_multiplier).
    """
    profile = get_profile(mode)
    return profile.stop_multiplier, profile.target_multiplier


def get_ambiguity_and_edge(mode: str) -> Tuple[float, float]:
    """Get authoritative ambiguity margin and min action edge.

    Returns (ambiguity_margin_r, min_action_edge_r).
    """
    profile = get_profile(mode)
    return profile.ambiguity_margin_r, profile.min_action_edge_r


# ═══════════════════════════════════════════════════════════════════════
# 3. Label Authority — Single-Row Simulation
# ═══════════════════════════════════════════════════════════════════════

def label_via_simulation(
    entry_price: float,
    atr: float,
    future_highs: list[float],
    future_lows: list[float],
    future_closes: list[float],
    mode: str,
    symbol: str = "",
    decision_timestamp: str = "",
) -> SimulationOutput:
    """Generate labels via the authoritative simulation engine (single row).

    This is the reference implementation for label generation.
    Every pipeline (evaluator, fast_simulator, XGBoost) MUST produce
    labels that match this function — verified by the golden parity test.

    For bulk generation, use generate_labels_bulk() which is a
    performance-optimized equivalent verified against this function.
    """
    profile = get_profile(mode)
    n_candles = min(
        len(future_highs), len(future_lows), len(future_closes),
        profile.max_holding_bars,
    )

    candles = [
        Candle(
            open=future_closes[i - 1] if i > 0 else entry_price,
            high=future_highs[i],
            low=future_lows[i],
            close=future_closes[i],
        )
        for i in range(n_candles)
    ]

    sim_input = SimulationInput(
        symbol=symbol,
        decision_timestamp=decision_timestamp or "",
        mode=TradingMode[mode.upper()],
        primary_interval=profile.primary_interval,
        entry_price=entry_price,
        atr=atr,
        future_path=FuturePath(candles=candles),
        profile=profile,
    )

    return simulate(sim_input)


# ═══════════════════════════════════════════════════════════════════════
# 4. Bulk Label Generation (fast path)
# ═══════════════════════════════════════════════════════════════════════
# Performance-optimized bulk label generator.
# MUST produce results equivalent to calling label_via_simulation() per row.
# Verified by the golden parity test.

def generate_labels_bulk(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    mode: str,
    **kwargs,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bulk label generation via per-row simulation.engine calls.

    Calls ``label_via_simulation()`` for each valid row — guaranteed to match
    the simulation engine's output exactly (100% parity).

    For SCALP with ~24K bars × 16 symbols ≈ 384K rows, estimated runtime
    is ~430 seconds (precedent: 233K trades in 262s through TrainingAdapter).

    Returns:
        (int_labels, gross_r, net_r,
         long_gross, short_gross, long_net, short_net)
    Where int_labels: 0=LONG_NOW, 1=SHORT_NOW, 2=NO_TRADE
    """
    profile = get_profile(mode)
    max_hold = profile.max_holding_bars

    n = len(closes)
    out_len = n - max_hold - 1
    if out_len <= 0:
        return (
            np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64),
        )

    ints = np.empty(out_len, dtype=np.int32)
    gross_ret = np.empty(out_len, dtype=np.float64)
    net_ret = np.empty(out_len, dtype=np.float64)
    long_gross = np.empty(out_len, dtype=np.float64)
    short_gross = np.empty(out_len, dtype=np.float64)
    long_net = np.empty(out_len, dtype=np.float64)
    short_net = np.empty(out_len, dtype=np.float64)

    for i in range(out_len):
        entry = float(closes[i])

        # ATR (same calc as simulation engine)
        atr_sum = atr_cnt = 0
        for k in range(max(0, i - 14), i + 1):
            if k == 0:
                tr = float(highs[k] - lows[k])
            else:
                tr = max(highs[k] - lows[k], abs(highs[k] - closes[k - 1]),
                         abs(lows[k] - closes[k - 1]))
            atr_sum += tr
            atr_cnt += 1
        atr_val = atr_sum / max(atr_cnt, 1)

        future_highs = highs[i + 1: i + 1 + max_hold].tolist()
        future_lows = lows[i + 1: i + 1 + max_hold].tolist()
        future_closes = closes[i + 1: i + 1 + max_hold].tolist()

        if not future_highs:
            ints[i] = 2
            gross_ret[i] = net_ret[i] = 0.0
            long_gross[i] = short_gross[i] = long_net[i] = short_net[i] = 0.0
            continue

        sim = label_via_simulation(
            entry, atr_val,
            future_highs=future_highs,
            future_lows=future_lows,
            future_closes=future_closes,
            mode=mode,
        )

        # Map simulation output
        action_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2, "AMBIGUOUS_STATE": 2}
        ints[i] = action_map.get(sim.best_action, 2)

        # Cost in fractional return space from sim outputs
        if sim.best_action == "LONG_NOW":
            long_gross[i] = sim.long_outcome.realized_r_gross
            short_gross[i] = 0.0
            long_net[i] = sim.long_outcome.realized_r_net
            short_net[i] = 0.0
            gross_ret[i] = long_gross[i]
            net_ret[i] = long_net[i]
        elif sim.best_action == "SHORT_NOW":
            long_gross[i] = 0.0
            short_gross[i] = sim.short_outcome.realized_r_gross
            long_net[i] = 0.0
            short_net[i] = sim.short_outcome.realized_r_net
            gross_ret[i] = short_gross[i]
            net_ret[i] = short_net[i]
        else:
            long_gross[i] = short_gross[i] = long_net[i] = short_net[i] = 0.0
            gross_ret[i] = net_ret[i] = 0.0

    return ints, gross_ret, net_ret, long_gross, short_gross, long_net, short_net
