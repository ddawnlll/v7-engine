"""Tests for alphaforge.sprint.cost_sanity.

Validates that CostSanityChecker.check() correctly:
1. Computes per-period cost drag from fee and slippage bps
2. Applies cost drag to gross returns
3. Reports net return, cost drag, cost drag %, and sanity pass
4. Handles edge cases (empty data, zero costs, negative values)
"""

from __future__ import annotations

import pandas as pd
import pytest

from alphaforge.sprint.cost_sanity import (
    CostSanityChecker,
    CostSanityReport,
)


# ── TESTS: CostSanityChecker.check() ──────────────────────────────────


class TestCostSanityChecker:
    """Tests for CostSanityChecker.check()."""

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _series(values: list[float]) -> pd.Series:
        return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="1h"))

    # -- normal case ---------------------------------------------------

    def test_normal_case(self):
        """Normal case: known fee/slippage produces exact cost_drag."""
        returns = self._series([3.0] * 10)
        report = CostSanityChecker().check(returns, fee_bps=4.0, slippage_bps=1.0)

        # cost_per_period = 2 * (4 + 1) / 10000 = 0.001
        # gross_return = 30.0
        # cost_drag = 0.001 * 10 = 0.01
        # net_return = 30.0 - 0.01 = 29.99
        # cost_drag_pct = 0.01 / 30.0 * 100 = 0.03333...
        assert report.gross_return == 30.0
        assert abs(report.cost_drag - 0.01) < 1e-12
        assert abs(report.net_return - 29.99) < 1e-12
        assert abs(report.cost_drag_pct - 0.01 / 30.0 * 100.0) < 1e-12
        assert report.sanity_pass is True

    def test_zero_fee(self):
        """Zero fee and zero slippage → cost_drag = 0, net = gross."""
        returns = self._series([2.0] * 5)
        report = CostSanityChecker().check(returns, fee_bps=0.0, slippage_bps=0.0)

        assert report.gross_return == 10.0
        assert report.cost_drag == 0.0
        assert report.net_return == 10.0
        assert report.sanity_pass is True

    def test_zero_fee_nonzero_slippage(self):
        """Zero fee but non-zero slippage → cost_drag only from slippage."""
        returns = self._series([1.0] * 5)
        report = CostSanityChecker().check(returns, fee_bps=0.0, slippage_bps=2.0)

        # cost_per_period = 2 * 2.0 / 10000 = 0.0004
        # cost_drag = 0.0004 * 5 = 0.002
        assert abs(report.cost_drag - 0.002) < 1e-12
        assert abs(report.net_return - (5.0 - 0.002)) < 1e-12

    def test_negative_cost_noop(self):
        """Negative fee_bps (rebate) -> cost_drag is negative (net > gross)."""
        returns = self._series([1.0] * 5)
        report = CostSanityChecker().check(returns, fee_bps=-2.0, slippage_bps=0.0)

        # cost_per_period = 2 * (-2.0) / 10000 = -0.0004
        # cost_drag = -0.0004 * 5 = -0.002
        # net_return = 5.0 - (-0.002) = 5.002
        assert report.cost_drag < 0
        assert report.net_return > report.gross_return
        assert report.sanity_pass is True

    def test_negative_slippage(self):
        """Negative slippage_bps → cost_drag is negative."""
        returns = self._series([1.0] * 5)
        report = CostSanityChecker().check(returns, fee_bps=0.0, slippage_bps=-1.0)
        assert report.cost_drag < 0
        assert report.net_return > report.gross_return

    def test_negative_returns(self):
        """Negative gross returns: costs add to the loss."""
        returns = self._series([-2.0] * 5)
        report = CostSanityChecker().check(returns, fee_bps=4.0, slippage_bps=1.0)

        assert report.gross_return == -10.0
        assert report.cost_drag > 0
        assert report.net_return < report.gross_return  # costs make it worse
        assert report.sanity_pass is False

    def test_weak_signal_drowned_by_high_costs(self):
        """Weak signal + high costs → net_return < 0, sanity fails."""
        returns = self._series([0.01] * 10)
        report = CostSanityChecker().check(returns, fee_bps=100.0, slippage_bps=50.0)

        # cost_per_period = 2 * 150 / 10000 = 0.03
        # gross_return = 0.1
        # cost_drag = 0.03 * 10 = 0.3
        # net_return = 0.1 - 0.3 = -0.2
        assert report.net_return < 0
        assert report.sanity_pass is False

    # -- edge cases ----------------------------------------------------

    def test_empty_series(self):
        """Empty series → report with zeros and sanity_pass=False."""
        report = CostSanityChecker().check(pd.Series([], dtype=float))

        assert report.gross_return == 0.0
        assert report.net_return == 0.0
        assert report.cost_drag == 0.0
        assert report.cost_drag_pct == 0.0
        assert report.sanity_pass is False

    def test_single_value(self):
        """Single-element series works correctly."""
        returns = self._series([5.0])
        report = CostSanityChecker().check(returns, fee_bps=4.0, slippage_bps=1.0)

        # cost_per_period = 0.001, cost_drag = 0.001
        assert report.gross_return == 5.0
        assert abs(report.cost_drag - 0.001) < 1e-12
        assert report.sanity_pass is True

    def test_all_zero_returns(self):
        """Zero returns: cost_drag > 0 makes net negative."""
        returns = self._series([0.0] * 10)
        report = CostSanityChecker().check(returns, fee_bps=4.0, slippage_bps=1.0)

        assert report.gross_return == 0.0
        assert report.cost_drag > 0
        assert report.net_return < 0
        assert report.cost_drag_pct == 0.0  # division by zero avoided
        assert report.sanity_pass is False

    def test_default_parameters(self):
        """Defaults for fee_bps, slippage_bps, holding_period are used."""
        returns = self._series([10.0] * 3)
        report = CostSanityChecker().check(returns)

        # Default: fee_bps=4.0, slippage_bps=1.0
        # cost_per_period = 0.001, cost_drag = 0.003
        assert abs(report.cost_drag - 0.003) < 1e-12
        assert report.sanity_pass is True

    def test_holding_period_ignored(self):
        """holding_period does not affect computation in current model."""
        returns = self._series([3.0] * 10)
        r1 = CostSanityChecker().check(returns, holding_period=1.0)
        r5 = CostSanityChecker().check(returns, holding_period=5.0)

        assert abs(r1.cost_drag - r5.cost_drag) < 1e-12


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
        )

        with pytest.raises(AttributeError):
            report.gross_return = 2.0  # type: ignore[misc]

    def test_equality(self):
        """Test that two identical reports are equal."""
        report1 = CostSanityReport(
            gross_return=1.0,
            net_return=0.8,
            cost_drag=0.2,
            cost_drag_pct=20.0,
            sanity_pass=True,
        )
        report2 = CostSanityReport(
            gross_return=1.0,
            net_return=0.8,
            cost_drag=0.2,
            cost_drag_pct=20.0,
            sanity_pass=True,
        )

        assert report1 == report2

    def test_inequality(self):
        """Test that different reports are not equal."""
        r1 = CostSanityReport(1.0, 0.8, 0.2, 20.0, True)
        r2 = CostSanityReport(1.0, 0.8, 0.2, 20.0, False)

        assert r1 != r2
