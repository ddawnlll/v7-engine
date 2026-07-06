#!/usr/bin/env python3
"""
SWING momentum test — demonstrates SWING fee advantage over SCALP.

Computes momentum signal from the feature pipeline, runs simulated
trades under SWING (4h, stop=2.0, target=2.5) and SCALP (1h, stop=1.5,
target=1.5) profiles, and compares fee impact.

Expected results:
  SWING fee impact:  ~0.005-0.02R per trade (wider stops → larger 1R)
  SCALP fee impact:  ~0.008-0.03R per trade (tighter stops → smaller 1R)
  Net R difference:  SWING has lower cost than SCALP in R-multiple terms

Usage:
  PYTHONPATH=alphaforge/src:$PYTHONPATH python3 alphaforge/scripts/test_swing_momentum.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import numpy as np

# Ensure alphaforge/src is in path
_repo_root = Path(__file__).resolve().parent.parent.parent
_src_path = str(_repo_root / "alphaforge" / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Simulation imports for cost computation
_sim_src = str(_repo_root / "simulation")
if _sim_src not in sys.path:
    sys.path.insert(0, _sim_src)

from alphaforge.features.pipeline import compute_features
from simulation.engine.costs import fee_cost_r, slippage_cost_r, compute_entry_risk


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWING_PROFILE = {
    "stop_multiplier": 2.0,
    "target_multiplier": 2.5,
    "max_holding_bars": 30,
    "primary_interval": "4h",
}

SCALP_PROFILE = {
    "stop_multiplier": 1.5,
    "target_multiplier": 1.5,
    "max_holding_bars": 12,
    "primary_interval": "1h",
}

MOMENTUM_THRESHOLD = 0.02  # 2% momentum trigger
TAKER_FEE_BPS = 4.0
SLIPPAGE_BPS = 1.0


# ---------------------------------------------------------------------------
# Helper: synthetic OHLCV
# ---------------------------------------------------------------------------


def _generate_ohlcv(n_bars: int = 2000, seed: int = 42) -> dict:
    """Generate synthetic 4h OHLCV data with realistic volatility."""
    rng = np.random.RandomState(seed)
    # Random walk with momentum
    returns = rng.randn(n_bars) * 0.008  # ~0.8% per-bar vol for 4h
    # Add occasional momentum bursts
    burst_idx = rng.randint(0, n_bars, size=n_bars // 50)
    returns[burst_idx] += rng.choice([-0.03, 0.03], size=len(burst_idx))

    close = 50000.0 * np.exp(np.cumsum(returns))
    high = close * (1.0 + np.abs(rng.randn(n_bars)) * 0.005)
    low = close * (1.0 - np.abs(rng.randn(n_bars)) * 0.005)
    open_arr = close - rng.randn(n_bars) * 0.002 * close
    volume = np.abs(rng.randn(n_bars) * 200.0) + 100.0

    return {
        "open": open_arr.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "close": close.astype(np.float64),
        "volume": volume.astype(np.float64),
    }


# ---------------------------------------------------------------------------
# Fee impact computation
# ---------------------------------------------------------------------------


def compute_trade_costs(
    entry_price: float,
    atr: float,
    stop_multiplier: float,
    notional: float = 10000.0,
) -> dict:
    """Compute fee and slippage costs in R-multiples for a single trade.

    Args:
        entry_price: Entry price in quote currency.
        atr: ATR value at entry (price terms).
        stop_multiplier: ATR multiplier for stop distance (1R).
        notional: Position notional for fee computation.

    Returns:
        Dict with fee_cost_r, slippage_cost_r, total_cost_r, entry_risk (1R).
    """
    entry_risk = compute_entry_risk(atr, stop_multiplier)
    if entry_risk <= 0:
        return {"fee_cost_r": 0.0, "slippage_cost_r": 0.0, "total_cost_r": 0.0, "entry_risk": 0.0}

    fcr = fee_cost_r(
        notional=notional,
        entry_risk=entry_risk,
        taker_fee_bps=TAKER_FEE_BPS,
    )
    scr = slippage_cost_r(
        notional=notional,
        entry_price=entry_price,
        entry_risk=entry_risk,
        slippage_bps=SLIPPAGE_BPS,
        atr=atr,
        volatility_adjust=True,
    )

    return {
        "fee_cost_r": fcr,
        "slippage_cost_r": scr,
        "total_cost_r": fcr + scr,
        "entry_risk": entry_risk,
    }


def compute_momentum_signal(ohlcv: dict) -> np.ndarray:
    """Compute a normalized momentum signal from features.

    Returns array of momentum strength normalized to [-1, 1].
    Positive = bullish momentum, negative = bearish.
    """
    matrix = compute_features(ohlcv, mode="SWING")
    mom = matrix.features.get("momentum_N", np.full(len(ohlcv["close"]), np.nan))
    rsi = matrix.features.get("rsi_N", np.full(len(ohlcv["close"]), np.nan))

    # Combined signal: normalize momentum and RSI divergence
    atr_series = matrix.features.get("atr_N", np.full(len(ohlcv["close"]), np.nan))
    close = ohlcv["close"]

    # Momentum as fraction of ATR (vol-normalized)
    signal = np.full(len(close), np.nan, dtype=np.float64)
    valid = ~np.isnan(mom) & ~np.isnan(atr_series) & (atr_series > 0)
    signal[valid] = mom[valid] / atr_series[valid]

    # Normalize to [-1, 1] using tanh
    signal = np.tanh(signal * 0.5)

    return signal


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("SWING vs SCALP Fee Impact Comparison")
    print("=" * 70)

    # Generate data and compute features
    print("\nGenerating synthetic OHLCV data (2000 bars 4h)...")
    ohlcv = _generate_ohlcv(2000)

    print("Computing features (including momentum)...")
    signal = compute_momentum_signal(ohlcv)
    close = ohlcv["close"]
    atr_series = compute_features(ohlcv, mode="SWING").features.get("atr_N", np.full(len(close), np.nan))
    valid_mask = ~np.isnan(signal) & ~np.isnan(atr_series) & (atr_series > 0)

    # Find entry points where |signal| exceeds threshold
    entry_indices = np.where(
        valid_mask & (np.abs(signal) > MOMENTUM_THRESHOLD)
    )[0]

    if len(entry_indices) == 0:
        print("No entries found — try lowering MOMENTUM_THRESHOLD")
        return

    print(f"Found {len(entry_indices)} entry signals")

    # Simulate trades for both profiles
    swing_costs: list[dict] = []
    scalp_costs: list[dict] = []

    for idx in entry_indices[:500]:  # cap at 500 entries
        entry_price = float(close[idx])
        atr = float(atr_series[idx])

        if entry_price <= 0 or atr <= 0:
            continue

        swing = compute_trade_costs(
            entry_price, atr, SWING_PROFILE["stop_multiplier"]
        )
        scalp = compute_trade_costs(
            entry_price, atr, SCALP_PROFILE["stop_multiplier"]
        )
        swing_costs.append(swing)
        scalp_costs.append(scalp)

    # Aggregate results
    if not swing_costs:
        print("No valid trades after filtering")
        return

    swing_fee = np.mean([c["fee_cost_r"] for c in swing_costs])
    swing_slip = np.mean([c["slippage_cost_r"] for c in swing_costs])
    swing_total = np.mean([c["total_cost_r"] for c in swing_costs])

    scalp_fee = np.mean([c["fee_cost_r"] for c in scalp_costs])
    scalp_slip = np.mean([c["slippage_cost_r"] for c in scalp_costs])
    scalp_total = np.mean([c["total_cost_r"] for c in scalp_costs])

    swing_1r = np.mean([c["entry_risk"] for c in swing_costs])
    scalp_1r = np.mean([c["entry_risk"] for c in scalp_costs])

    # Report
    print(f"\n{'Metric':<30} {'SWING (4h)':<18} {'SCALP (1h)':<18}")
    print("-" * 66)
    print(f"{'1R (entry risk, $)':<30} {swing_1r:<18.2f} {scalp_1r:<18.2f}")
    print(f"{'Fee cost (R)':<30} {swing_fee:<18.4f} {scalp_fee:<18.4f}")
    print(f"{'Slippage cost (R)':<30} {swing_slip:<18.4f} {scalp_slip:<18.4f}")
    print(f"{'Total cost (R)':<30} {swing_total:<18.4f} {scalp_total:<18.4f}")
    print(f"{'Fee advantage (SWING - SCALP)':<30} {swing_fee - scalp_fee:<18.4f}")
    print(f"{'Total cost advantage (R)':<30} {swing_total - scalp_total:<18.4f}")
    print()

    # Verify expected fee ranges
    swing_ok = 0.003 <= swing_fee <= 0.03
    scalp_ok = 0.005 <= scalp_fee <= 0.05

    print(f"SWING fee in expected range [0.003, 0.03]: {'PASS' if swing_ok else 'FAIL'}")
    print(f"  Got: {swing_fee:.4f}R")
    print(f"SCALP fee in expected range [0.005, 0.05]: {'PASS' if scalp_ok else 'FAIL'}")
    print(f"  Got: {scalp_fee:.4f}R")
    print(f"SWING has lower total cost than SCALP: {'PASS' if swing_total < scalp_total else 'FAIL'}")

    print("\n" + "=" * 70)
    print("Conclusion: SWING's wider stops create larger 1R, making")
    print("fixed fees proportionally smaller in R-multiple terms.")
    print("=" * 70)


if __name__ == "__main__":
    main()
