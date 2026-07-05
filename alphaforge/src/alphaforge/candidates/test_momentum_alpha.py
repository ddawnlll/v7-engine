"""Test script for MomentumAlpha.

Generates synthetic price data, runs the momentum alpha, computes
IC (rank information coefficient) and signal Sharpe ratio over
training and test periods, then prints the required report fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure alphaforge/src is importable (src/ layout)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.candidates.momentum_alpha import MomentumAlpha

# ── Parameters ──────────────────────────────────────────────────────────────
TRAIN_START = "2020-01-01"
TRAIN_END = "2022-12-31"
TEST_START = "2023-01-01"
TEST_END = "2023-12-31"
WINDOW = 20
N_DAYS = 1500  # enough to cover 2020-01-01 .. 2023-12-31
N_COMBINATIONS = 1  # single parameter setting


def generate_synthetic_data(
    n_days: int = N_DAYS,
    start: str = "2020-01-01",
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic daily price data from a geometric random walk.

    Returns
    -------
    pd.DataFrame
        Columns: ``['close', 'returns']`` with a daily DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    daily_ret = rng.normal(loc=0.0005, scale=0.02, size=n_days)  # slight drift
    price = 100.0 * np.exp(np.cumsum(daily_ret))
    index = pd.date_range(start, periods=n_days, freq="D")
    return pd.DataFrame(
        {"close": price, "returns": daily_ret},
        index=index,
    )


def compute_forward_returns(
    close: pd.Series,
    horizon: int = 1,
) -> pd.Series:
    """Compute forward N-period returns: close(t + horizon) / close(t) - 1."""
    return close.shift(-horizon) / close - 1.0


def rank_ic(signals: pd.Series, forward_ret: pd.Series) -> float:
    """Spearman rank correlation (IC) between signals and forward returns."""
    valid = signals.notna() & forward_ret.notna()
    if valid.sum() < 10:
        return float("nan")
    return signals[valid].corr(forward_ret[valid], method="spearman")


def signal_sharpe(signals: pd.Series) -> float:
    """Annualised Sharpe ratio of the signal series."""
    valid = signals.dropna()
    if len(valid) < 10:
        return float("nan")
    return float(valid.mean() / valid.std() * np.sqrt(252))


def main() -> None:
    # Generate data
    data = generate_synthetic_data()

    # Filter to train / test periods
    train_mask = (data.index >= pd.Timestamp(TRAIN_START)) & (
        data.index <= pd.Timestamp(TRAIN_END)
    )
    test_mask = (data.index >= pd.Timestamp(TEST_START)) & (
        data.index <= pd.Timestamp(TEST_END)
    )

    train_data = data.loc[train_mask].copy()
    test_data = data.loc[test_mask].copy()

    # Compute alpha signals (need extra history before train for warm-up)
    alpha = MomentumAlpha(window=WINDOW)
    # Use the period starting WINDOW days before train
    pre_train_start = pd.Timestamp(TRAIN_START) - pd.Timedelta(days=WINDOW + 5)
    extended_train = data.loc[data.index >= pre_train_start].copy()
    all_signals = alpha.generate_signals(extended_train)
    train_signals = all_signals.loc[train_data.index]
    test_signals = alpha.generate_signals(test_data)

    # Forward returns (1-day horizon for IC)
    train_fwd = compute_forward_returns(train_data["close"], horizon=1)
    test_fwd = compute_forward_returns(test_data["close"], horizon=1)

    # Metrics
    train_ic = rank_ic(train_signals, train_fwd)
    test_ic = rank_ic(test_signals, test_fwd)
    train_sharpe = signal_sharpe(train_signals)
    test_sharpe = signal_sharpe(test_signals)

    # ── Print report ──────────────────────────────────────────────────
    sep = "=" * 70
    print()
    print(sep)
    print("  MOMENTUM ALPHA TEST REPORT")
    print(sep)
    print(f"  Alpha:       MomentumAlpha (window={WINDOW})")
    print(f"  Data:        synthetic daily random walk")
    print(f"  Train:       {TRAIN_START}  to  {TRAIN_END}")
    print(f"  Test:        {TEST_START}  to  {TEST_END}")
    print(f"  N symbols:   1 (single-instrument)")
    print()
    print(f"  --- TRAIN ---")
    print(f"    Rank IC (h=1):           {train_ic:+.6f}")
    print(f"    Signal Sharpe (ann.):    {train_sharpe:+.4f}")
    print(f"    N observations:          {int(train_signals.notna().sum())}")
    print()
    print(f"  --- TEST ---")
    print(f"    Rank IC (h=1):           {test_ic:+.6f}")
    print(f"    Signal Sharpe (ann.):    {test_sharpe:+.4f}")
    print(f"    N observations:          {int(test_signals.notna().sum())}")
    print()
    print("  --- COMPLETION SUMMARY ---")
    print(f"  train_start:     {TRAIN_START}")
    print(f"  train_end:       {TRAIN_END}")
    print(f"  test_start:      {TEST_START}")
    print(f"  test_end:        {TEST_END}")
    print(f"  n_combinations:  {N_COMBINATIONS}")
    print(f"  metric (test IC): {test_ic:.6f}")
    print(f"  Status:          {'SUCCESS' if pd.notna(test_ic) else 'FAILURE'}")
    print(sep)


if __name__ == "__main__":
    main()
