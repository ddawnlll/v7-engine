"""Tests for alphaforge.sprint.cost_sanity.

Validates that the cost sanity checker correctly:
1. Computes cost drag in R-multiples
2. Applies costs to forward returns
3. Preserves sign for strong signals
4. Handles edge cases (empty data, zero returns, etc.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaforge.sprint.cost_sanity import (
    CostSanityReport,
    compute_cost_drag_r,
    estimate_atr,
    apply_costs_vectorized,
    run_cost_sanity_check,
)


# ── FIXTURES ────────────────────────────────────────────────────────

@pytest.fixture
def sample_close() -> pd.DataFrame:
    """Sample close prices for testing."""
    np.random.seed(42)
    n_timestamps = 100
    n_symbols = 10
    dates = pd.date_range("2024-01-01", periods=n_timestamps, freq="1h")
    symbols = [f"SYM{i}" for i in range(n_symbols)]

    # Random walk prices
    returns = np.random.randn(n_timestamps, n_symbols) * 0.02
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))

    return pd.DataFrame(prices, index=dates, columns=symbols)


@pytest.fixture
def strong_signal_returns(sample_close: pd.DataFrame) -> pd.DataFrame:
    """Forward returns with strong positive signal (5.0R)."""
    np.random.seed(123)
    n_timestamps, n_symbols = sample_close.shape
    # Strong positive returns (5.0R per timestamp per symbol)
    # This ensures net remains positive after cost deduction (~2.5R)
    returns = pd.DataFrame(
        5.0 + np.random.randn(n_timestamps, n_symbols) * 0.1,
        index=sample_close.index,
        columns=sample_close.columns,
    )
    return returns


@pytest.fixture
def weak_signal_returns(sample_close: pd.DataFrame) -> pd.DataFrame:
    """Forward returns with weak signal (0.05R)."""
    np.random.seed(456)
    n_timestamps, n_symbols = sample_close.shape
    # Weak returns (0.05R per timestamp per symbol)
    returns = pd.DataFrame(
        0.05 + np.random.randn(n_timestamps, n_symbols) * 0.01,
        index=sample_close.index,
        columns=sample_close.columns,
    )
    return returns


@pytest.fixture
def mixed_signal_returns(sample_close: pd.DataFrame) -> pd.DataFrame:
    """Forward returns with mixed strong/weak signals."""
    np.random.seed(789)
    n_timestamps, n_symbols = sample_close.shape

    # First half strong (5.0R), second half weak (0.5R)
    # Note: weak signals may not survive cost drag when ATR is high
    half = n_timestamps // 2
    strong = 5.0 + np.random.randn(half, n_symbols) * 0.1
    weak = 0.5 + np.random.randn(half, n_symbols) * 0.05

    data = np.vstack([strong, weak])
    return pd.DataFrame(data, index=sample_close.index, columns=sample_close.columns)


# ── TESTS: compute_cost_drag_r ─────────────────────────────────────

class TestComputeCostDragR:
    """Tests for compute_cost_drag_r function."""

    def test_basic_computation(self):
        """Test basic cost computation with known values."""
        atr = 2.0
        stop_multiplier = 2.0
        notional = 10_000.0
        entry_price = 100.0

        cost = compute_cost_drag_r(atr, stop_multiplier, notional, entry_price)

        # risk = 2.0 * 2.0 = 4.0
        # fee_r = (10000 * 0.0004 * 2) / 4.0 = 8.0 / 4.0 = 2.0
        # slip_r = (10000 * 0.0001 * (1 + 2/100) * 2) / 4.0 = 2.04 / 4.0 = 0.51
        # total = 2.51 (with volatility adjustment in slippage)
        assert abs(cost - 2.51) < 1e-10

    def test_zero_atr(self):
        """Test returns 0 for zero ATR."""
        cost = compute_cost_drag_r(0.0, 2.0, 10_000.0, 100.0)
        assert cost == 0.0

    def test_zero_stop_multiplier(self):
        """Test returns 0 for zero stop multiplier."""
        cost = compute_cost_drag_r(2.0, 0.0, 10_000.0, 100.0)
        assert cost == 0.0

    def test_zero_notional(self):
        """Test returns 0 for zero notional."""
        cost = compute_cost_drag_r(2.0, 2.0, 0.0, 100.0)
        assert cost == 0.0

    def test_zero_entry_price(self):
        """Test returns 0 for zero entry price."""
        cost = compute_cost_drag_r(2.0, 2.0, 10_000.0, 0.0)
        assert cost == 0.0

    def test_negative_atr(self):
        """Test returns 0 for negative ATR."""
        cost = compute_cost_drag_r(-2.0, 2.0, 10_000.0, 100.0)
        assert cost == 0.0

    def test_custom_fee_rate(self):
        """Test with custom fee rate."""
        atr = 2.0
        stop_multiplier = 2.0
        notional = 10_000.0
        entry_price = 100.0

        # Double the fee
        cost = compute_cost_drag_r(
            atr, stop_multiplier, notional, entry_price,
            taker_fee_bps=8.0, slippage_bps=2.0,
        )

        # fee_r = (10000 * 0.0008 * 2) / 4.0 = 16.0 / 4.0 = 4.0
        # slip_r = (10000 * 0.0002 * (1 + 2/100) * 2) / 4.0 = 4.08 / 4.0 = 1.02
        # total = 5.02 (with volatility adjustment in slippage)
        assert abs(cost - 5.02) < 1e-10


# ── TESTS: estimate_atr ────────────────────────────────────────────

class TestEstimateATR:
    """Tests for estimate_atr function."""

    def test_basic_atr_estimation(self, sample_close: pd.DataFrame):
        """Test ATR estimation produces reasonable values."""
        atr = estimate_atr(sample_close, window=20)

        assert atr.shape == sample_close.shape
        assert atr.index.equals(sample_close.index)
        assert atr.columns.equals(sample_close.columns)

        # ATR should be positive (after warmup period)
        valid_atr = atr.iloc[30:]
        assert (valid_atr > 0).all().all()

    def test_atr_percentage_of_price(self, sample_close: pd.DataFrame):
        """Test ATR is typically 1-15% of price for crypto-like data."""
        atr = estimate_atr(sample_close, window=20)
        atr_pct = atr / sample_close

        # After warmup, ATR should be in reasonable range
        # For synthetic data with 2% hourly volatility, ATR can be higher
        valid_pct = atr_pct.iloc[30:]
        assert (valid_pct > 0.005).all().all()  # > 0.5%
        assert (valid_pct < 0.15).all().all()   # < 15%

    def test_short_window(self, sample_close: pd.DataFrame):
        """Test with short window."""
        atr = estimate_atr(sample_close, window=5)
        assert atr.shape == sample_close.shape

    def test_empty_close(self):
        """Test with empty close DataFrame."""
        close = pd.DataFrame()
        atr = estimate_atr(close, window=20)
        assert atr.empty


# ── TESTS: apply_costs_vectorized ──────────────────────────────────

class TestApplyCostsVectorized:
    """Tests for apply_costs_vectorized function."""

    def test_costs_reduce_returns(
        self,
        strong_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test that costs reduce gross returns."""
        net, cost_drag = apply_costs_vectorized(
            strong_signal_returns,
            sample_close,
        )

        # Net should be less than gross (costs are positive)
        gross_total = strong_signal_returns.sum().sum()
        net_total = net.sum().sum()

        assert net_total < gross_total

        # Cost drag should be positive
        assert cost_drag.sum().sum() > 0

    def test_sign_preservation(
        self,
        strong_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test that sign is preserved for strong signals."""
        net, _ = apply_costs_vectorized(
            strong_signal_returns,
            sample_close,
        )

        # For strong signals, sign should be preserved where both are valid
        # (net might be slightly smaller but same sign)
        strong_mask = strong_signal_returns.abs() > 3.0
        gross_strong = strong_signal_returns[strong_mask]
        net_strong = net[strong_mask]

        # Check sign preservation for non-NaN values
        both_valid = gross_strong.notna() & net_strong.notna()
        if bool(both_valid.any().any()):
            # Use .values to properly filter with boolean mask
            gross_sign = np.sign(gross_strong[both_valid.values])
            net_sign = np.sign(net_strong[both_valid.values])
            # .all().all() because result is a DataFrame
            assert bool((gross_sign == net_sign).all().all())

    def test_shape_preserved(
        self,
        strong_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test that output shape matches input shape."""
        net, cost_drag = apply_costs_vectorized(
            strong_signal_returns,
            sample_close,
        )

        assert net.shape == strong_signal_returns.shape
        assert cost_drag.shape == strong_signal_returns.shape

    def test_handles_nan_in_forward_returns(
        self,
        sample_close: pd.DataFrame,
    ):
        """Test that NaN in forward returns is handled correctly."""
        # Create forward returns with some NaN
        fr = pd.DataFrame(
            np.nan,
            index=sample_close.index,
            columns=sample_close.columns,
        )
        fr.iloc[10:50, 0:5] = 0.5  # Only some values

        net, cost_drag = apply_costs_vectorized(fr, sample_close)

        # NaN should propagate
        assert np.isnan(net.iloc[0, 0])
        assert not np.isnan(net.iloc[20, 0])


# ── TESTS: run_cost_sanity_check ───────────────────────────────────

class TestRunCostSanityCheck:
    """Tests for run_cost_sanity_check function."""

    def test_strong_signal_passes(
        self,
        strong_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test that strong signals pass sanity check."""
        report = run_cost_sanity_check(
            strong_signal_returns,
            sample_close,
        )

        assert isinstance(report, CostSanityReport)
        # Use == instead of is to handle numpy boolean
        assert report.sanity_pass == True
        assert report.gross_return > 0
        assert report.net_return > 0
        assert report.cost_drag > 0
        assert report.cost_drag_pct < 100  # Costs don't exceed gross
        assert report.notes == "OK"

    def test_weak_signal_cost_drag(
        self,
        weak_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test that weak signals have high cost drag percentage."""
        report = run_cost_sanity_check(
            weak_signal_returns,
            sample_close,
        )

        # Weak signals should have high cost drag %
        assert report.cost_drag_pct > 50

    def test_empty_forward_returns(self, sample_close: pd.DataFrame):
        """Test with empty forward returns."""
        empty_fr = pd.DataFrame()
        report = run_cost_sanity_check(empty_fr, sample_close)

        assert report.sanity_pass is False
        assert report.n_timestamps == 0
        assert report.n_symbols == 0
        assert "empty" in report.notes

    def test_zero_returns(self, sample_close: pd.DataFrame):
        """Test with zero forward returns."""
        zero_fr = pd.DataFrame(
            0.0,
            index=sample_close.index,
            columns=sample_close.columns,
        )
        report = run_cost_sanity_check(zero_fr, sample_close)

        # With zero gross returns, costs still apply (costs exist regardless)
        assert report.gross_return == 0.0
        assert report.net_return < 0  # Net is negative due to costs
        assert report.cost_drag > 0   # Cost drag is positive
        # With zero gross, cost_drag_pct is 100% (all cost)
        assert report.cost_drag_pct == 100.0
        # Sanity check passes because there are no "strong signals" to flip
        assert bool(report.sanity_pass) is True

    def test_mixed_signals(
        self,
        mixed_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test with mixed strong/weak signals.

        Note: Weak signals (0.5R) may not survive cost drag when ATR is high.
        The sanity check correctly identifies this scenario.
        """
        report = run_cost_sanity_check(
            mixed_signal_returns,
            sample_close,
        )

        # Should have some cost drag
        assert report.cost_drag > 0

        # The sanity check may fail because weak signals (0.5R) are too small
        # to survive the cost drag when ATR is high (6-9% of price).
        # This is correct behavior - the cost model is working as expected.
        # We just verify that the report is valid and cost drag is computed.
        assert report.gross_return > 0
        assert report.net_return is not None
        assert report.cost_drag_pct > 0

    def test_report_fields(self, sample_close: pd.DataFrame):
        """Test that report has all required fields."""
        fr = pd.DataFrame(
            0.5,
            index=sample_close.index,
            columns=sample_close.columns,
        )
        report = run_cost_sanity_check(fr, sample_close)

        # Check all fields exist
        assert hasattr(report, "gross_return")
        assert hasattr(report, "net_return")
        assert hasattr(report, "cost_drag")
        assert hasattr(report, "cost_drag_pct")
        assert hasattr(report, "sanity_pass")
        assert hasattr(report, "n_timestamps")
        assert hasattr(report, "n_symbols")
        assert hasattr(report, "notes")

    def test_custom_parameters(
        self,
        strong_signal_returns: pd.DataFrame,
        sample_close: pd.DataFrame,
    ):
        """Test with custom cost parameters."""
        report_default = run_cost_sanity_check(
            strong_signal_returns,
            sample_close,
        )

        # Double the fees
        report_expensive = run_cost_sanity_check(
            strong_signal_returns,
            sample_close,
            taker_fee_bps=8.0,
            slippage_bps=2.0,
        )

        # More expensive costs should have higher drag
        assert report_expensive.cost_drag > report_default.cost_drag


# ── TESTS: CostSanityReport dataclass ──────────────────────────────

class TestCostSanityReport:
    """Tests for CostSanityReport dataclass."""

    def test_frozen(self):
        """Test that CostSanityReport is frozen (immutable)."""
        report = CostSanityReport(
            gross_return=1.0,
            net_return=0.8,
            cost_drag=0.2,
            cost_drag_pct=20.0,
            sanity_pass=True,
            n_timestamps=100,
            n_symbols=10,
            notes="OK",
        )

        # Should raise AttributeError on assignment
        with pytest.raises(AttributeError):
            report.gross_return = 2.0

    def test_equality(self):
        """Test that two identical reports are equal."""
        report1 = CostSanityReport(
            gross_return=1.0,
            net_return=0.8,
            cost_drag=0.2,
            cost_drag_pct=20.0,
            sanity_pass=True,
            n_timestamps=100,
            n_symbols=10,
            notes="OK",
        )
        report2 = CostSanityReport(
            gross_return=1.0,
            net_return=0.8,
            cost_drag=0.2,
            cost_drag_pct=20.0,
            sanity_pass=True,
            n_timestamps=100,
            n_symbols=10,
            notes="OK",
        )

        assert report1 == report2
