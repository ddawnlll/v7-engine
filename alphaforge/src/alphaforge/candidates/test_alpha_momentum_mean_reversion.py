"""Tests for MomentumMeanReversionAlpha.

Uses a synthetic 100-day random walk to verify:
  - Output length matches input length.
  - All entries after the warm-up period are non-NaN.
  - The momentum and mean-reversion components are negatively correlated
    (they encode opposite trading hypotheses).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure alphaforge/src is importable (src/ layout)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.candidates.alpha_momentum_mean_reversion import (
    MomentumMeanReversionAlpha,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def random_walk_data() -> pd.DataFrame:
    """Generate 100 days of synthetic price data from a random walk.

    Returns
    -------
    pd.DataFrame
        Columns: ``['close', 'returns']``, length 100.
    """
    rng = np.random.default_rng(seed=42)
    n = 100

    # Daily log-returns: N(0, 0.02²) ≈ 2 % daily vol
    daily_returns = rng.normal(loc=0.0, scale=0.02, size=n)

    # Price from cumulative product of returns (start at 100)
    price = 100.0 * np.exp(np.cumsum(daily_returns))

    index = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"close": price, "returns": daily_returns},
        index=index,
    )
    return df


# ============================================================================
# Tests
# ============================================================================


class TestMomentumMeanReversionAlpha:
    """Test suite for the hybrid alpha candidate."""

    def test_output_length(self, random_walk_data: pd.DataFrame) -> None:
        """Output Series must have the same length as the input."""
        alpha = MomentumMeanReversionAlpha()
        signals = alpha.generate_signals(random_walk_data)
        assert len(signals) == len(random_walk_data)

    def test_output_index_aligned(self, random_walk_data: pd.DataFrame) -> None:
        """Output Series must be aligned to the input index."""
        alpha = MomentumMeanReversionAlpha()
        signals = alpha.generate_signals(random_walk_data)
        pd.testing.assert_index_equal(signals.index, random_walk_data.index)

    def test_warmup_nans(self, random_walk_data: pd.DataFrame) -> None:
        """First (window - 1) entries should be NaN (warm-up).

        The longest warm-up is zscore_window=20 (rolling std needs 20
        observations).  After the 20th entry everything should be finite.
        """
        alpha = MomentumMeanReversionAlpha(momentum_window=20, zscore_window=20)
        signals = alpha.generate_signals(random_walk_data)

        # First 19 entries may be NaN (need 20 obs for the rolling std)
        first_nan_region = signals.iloc[:19]
        assert first_nan_region.isna().all(), (
            f"Expected NaN in warm-up region (first 19), "
            f"got {first_nan_region.isna().sum()} NaN / {len(first_nan_region)}"
        )

        # From index 20 onwards everything should be finite
        valid_region = signals.iloc[20:]
        assert valid_region.notna().all(), (
            f"Expected no NaN after warm-up, "
            f"got {valid_region.isna().sum()} NaN / {len(valid_region)}"
        )

    def test_momentum_mean_rev_correlation_negative(
        self, random_walk_data: pd.DataFrame
    ) -> None:
        """Momentum and mean-reversion components should be negatively correlated.

        The momentum factor follows trends (high when recent returns are
        positive).  The mean-reversion z-score measures price deviation from
        the rolling mean — when momentum is up, price tends to be above its
        mean (positive z-score).  Because the combination formula subtracts
        the z-score, the two components encode opposite hypotheses, yielding
        a negative Pearson correlation.
        """
        alpha = MomentumMeanReversionAlpha(momentum_window=20, zscore_window=20)

        # Compute components directly (available as public methods)
        momentum = alpha.momentum_signal(random_walk_data)
        mean_rev = alpha.mean_reversion_signal(random_walk_data)

        # Drop overlap NaN region (both need 20 warm-up observations)
        valid = momentum.notna() & mean_rev.notna()

        if valid.sum() < 10:
            pytest.skip("Too few overlapping valid observations for correlation test")

        mom_valid = momentum[valid]
        mrev_valid = mean_rev[valid]

        corr = mom_valid.corr(mrev_valid)
        assert corr < 0, (
            f"Expected negative correlation between momentum and mean-reversion "
            f"components, got {corr:.4f}"
        )

    @pytest.mark.parametrize(
        "momentum_window, zscore_window",
        [
            (10, 10),
            (30, 20),
            (20, 30),
        ],
    )
    def test_different_windows(
        self,
        random_walk_data: pd.DataFrame,
        momentum_window: int,
        zscore_window: int,
    ) -> None:
        """Alpha works correctly with different window parameterizations."""
        alpha = MomentumMeanReversionAlpha(
            momentum_window=momentum_window,
            zscore_window=zscore_window,
        )
        signals = alpha.generate_signals(random_walk_data)

        assert len(signals) == len(random_walk_data)
        # Warm-up = max(window) - 1 entries can be NaN
        warmup = max(momentum_window, zscore_window) - 1
        valid_region = signals.iloc[warmup:]
        assert valid_region.notna().all(), (
            f"NaNs found after warm-up period ({warmup}) "
            f"for windows ({momentum_window}, {zscore_window})"
        )

    def test_empty_data_raises(self) -> None:
        """Empty DataFrame should propagate as an empty Series (not crash)."""
        alpha = MomentumMeanReversionAlpha()
        empty = pd.DataFrame({"close": [], "returns": []})
        signals = alpha.generate_signals(empty)
        assert len(signals) == 0

    def test_single_row_data(self) -> None:
        """Single row of data should return NaN (insufficient for windows)."""
        alpha = MomentumMeanReversionAlpha()
        single = pd.DataFrame(
            {"close": [100.0], "returns": [0.01]},
            index=pd.DatetimeIndex(["2020-01-01"]),
        )
        signals = alpha.generate_signals(single)
        assert len(signals) == 1
        assert pd.isna(signals.iloc[0])
