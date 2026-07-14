"""Simulation-authority R-multiple label generation.

Replaces forward-return labels with true economic R-multiples from a
triple-barrier simulation: stop, target, or timeout (whichver hits first).

SCALP profile: stop_mult=2.5, target_mult=2.5, max_holding=24 bars.
Cost: 8bps round-trip (taker fee).

R-multiple definition:
  R = PnL / risk_amount
  risk_amount = stop_distance (in price terms)
  LONG R: (exit - entry) / stop_distance
  SHORT R: (entry - exit) / stop_distance
  Cost deducted from PnL before R calculation.
"""
from __future__ import annotations
import numpy as np
from numba import njit

# SCALP defaults (from simulation/profiles/scalp.yaml)
_SCALP_STOP_MULT = 2.5
_SCALP_TARGET_MULT = 2.5
_SCALP_MAX_HOLDING = 24
_ROUND_TRIP_COST = 0.0008  # 8bps

# Forward-return label defaults
_FORWARD_LABEL_HORIZON = 12
_FORWARD_LABEL_THRESHOLD = 0.003


@njit
def generate_r_multiple_labels(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    stop_mult: float = 2.5,
    target_mult: float = 2.5,
    max_holding: int = 24,
    round_trip_cost: float = 0.0008,
    min_edge_r: float = 0.15,
    ambiguity_margin_r: float = 0.10,
):
    """Generate R-multiple labels via triple-barrier simulation.

    For each bar i:
    1. Compute ATR(14) as volatility proxy
    2. Set stop_dist = ATR * stop_mult, target_dist = ATR * target_mult
    3. Simulate forward path:
       - If low hits stop first: R = -stop_dist / risk = -1.0
       - If high hits target first: R = +target_dist / risk
       - Neither hits: R = (close[i+horizon] - entry) / risk
    4. Cost-honest: subtract round_trip_cost from gross R
    5. Pick direction: LONG or SHORT based on which has higher R
    6. If both within ambiguity_margin_r: NO_TRADE

    Returns: (ints_list, net_r_vals, long_r_vals, short_r_vals)
    """
    n = len(close)
    max_sample = n - max_holding - 1
    ints_list = np.empty(max_sample, dtype=np.int32)
    net_r_vals = np.zeros(max_sample, dtype=np.float64)
    long_r_vals = np.zeros(max_sample, dtype=np.float64)
    short_r_vals = np.zeros(max_sample, dtype=np.float64)

    for i in range(max_sample):
        entry_price = close[i]
        if entry_price <= 0:
            ints_list[i] = 2
            continue

        # ATR(14)
        atr_sum = 0.0
        atr_count = 0
        for k in range(max(0, i - 14), i + 1):
            prev = close[k - 1] if k > 0 else close[k]
            tr = max(high[k] - low[k], abs(high[k] - prev), abs(low[k] - prev))
            atr_sum += tr
            atr_count += 1
        atr = atr_sum / max(atr_count, 1)

        if atr <= 0 or atr > entry_price * 0.5:
            ints_list[i] = 2
            continue

        stop_dist = atr * stop_mult
        target_dist = atr * target_mult
        risk = stop_dist  # 1R = stop distance in price terms

        # LONG simulation
        long_r = 0.0
        for j in range(1, min(max_holding + 1, n - i)):
            if low[i + j] <= entry_price - stop_dist:
                long_r = -1.0  # stopped out
                break
            if high[i + j] >= entry_price + target_dist:
                long_r = target_dist / risk  # target hit
                break
            long_r = (close[i + j] - entry_price) / risk
        long_r -= round_trip_cost / risk  # cost-honest

        # SHORT simulation
        short_r = 0.0
        for j in range(1, min(max_holding + 1, n - i)):
            if high[i + j] >= entry_price + stop_dist:
                short_r = -1.0  # stopped out
                break
            if low[i + j] <= entry_price - target_dist:
                short_r = target_dist / risk  # target hit
                break
            short_r = (entry_price - close[i + j]) / risk
        short_r -= round_trip_cost / risk

        long_r_vals[i] = long_r
        short_r_vals[i] = short_r

        # Direction selection
        if abs(long_r - short_r) <= ambiguity_margin_r:
            ints_list[i] = 2  # NO_TRADE
            net_r_vals[i] = 0.0
        elif long_r > short_r and long_r > min_edge_r:
            ints_list[i] = 0  # LONG
            net_r_vals[i] = long_r
        elif short_r > long_r and short_r > min_edge_r:
            ints_list[i] = 1  # SHORT
            net_r_vals[i] = short_r
        else:
            ints_list[i] = 2  # NO_TRADE
            net_r_vals[i] = 0.0

    return ints_list, net_r_vals, long_r_vals, short_r_vals


def generate_r_multiple_labels_from_ohlcv(
    ohlcv: dict,
    stop_mult: float = _SCALP_STOP_MULT,
    target_mult: float = _SCALP_TARGET_MULT,
    max_holding: int = _SCALP_MAX_HOLDING,
    round_trip_cost: float = _ROUND_TRIP_COST,
    min_edge_r: float = 0.15,
    ambiguity_margin_r: float = 0.10,
):
    """High-level wrapper: generate R-multiple labels from OHLCV dict.

    Returns dict with keys:
      - ints: direction labels (0=LONG, 1=SHORT, 2=NO_TRADE)
      - net_r: net R-multiple per sample (cost-honest)
      - long_r: raw LONG R values
      - short_r: raw SHORT R values
    """
    close = ohlcv["close"].astype(np.float64)
    high = ohlcv["high"].astype(np.float64)
    low = ohlcv["low"].astype(np.float64)

    ints, net_r, long_r, short_r = generate_r_multiple_labels(
        close, high, low, stop_mult, target_mult, max_holding,
        round_trip_cost, min_edge_r, ambiguity_margin_r,
    )

    # Filter valid samples (ATR > 0 and within range)
    valid = ~np.isnan(net_r) & ~np.isinf(net_r)

    return {
        "ints": ints[valid],
        "net_r": net_r[valid],
        "long_r": long_r[valid],
        "short_r": short_r[valid],
        "n_valid": int(valid.sum()),
        "n_total": len(close),
    }
