"""
Tests for lib/costs/r_costs.py — R-normalized cost functions.
"""

import pytest
from lib.costs.fees import estimate_fee
from lib.costs.slippage import get_slippage
from lib.costs.r_costs import fee_cost_r, slippage_cost_r, total_cost_r


class TestFeeCostR:
    def test_known_example(self):
        """Known example from the spec: notional=10000, atr=100, stop_mult=2.0,
        taker -> fee=4.0, cost_r=0.02."""
        result = fee_cost_r(
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            tier="taker",
        )
        assert result == pytest.approx(0.02, rel=1e-9)

    def test_maker_tier(self):
        """Maker fee should produce a smaller cost_r."""
        taker = fee_cost_r(10000, 10000, 100, 2.0, tier="taker")
        maker = fee_cost_r(10000, 10000, 100, 2.0, tier="maker")
        assert maker < taker

    def test_atr_zero_returns_zero(self):
        """atr=0 returns 0.0."""
        assert fee_cost_r(10000, 10000, 0, 2.0) == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        """stop_multiplier=0 returns 0.0."""
        assert fee_cost_r(10000, 10000, 100, 0) == 0.0

    def test_negative_atr_returns_zero(self):
        """atr<0 returns 0.0."""
        assert fee_cost_r(10000, 10000, -10, 2.0) == 0.0

    def test_zero_notional_returns_zero(self):
        """Zero notional produces zero fee, so cost_r is 0.0."""
        assert fee_cost_r(0, 10000, 100, 2.0) == 0.0

    def test_calls_estimate_fee(self):
        """Verify fee_cost_r uses estimate_fee (no reimplementation)."""
        fee = estimate_fee(50000, "taker")
        result = fee_cost_r(50000, 10000, 100, 2.0, tier="taker")
        assert result == pytest.approx(fee / (100 * 2.0), rel=1e-9)


class TestSlippageCostR:
    def test_basic(self):
        """slippage_cost_r with known inputs."""
        result = slippage_cost_r(
            notional=10000,
            entry_price=10000,
            atr=100,
            stop_multiplier=2.0,
            avg_liquidity=100000,
        )
        slippage = get_slippage(10000, 100000)
        assert result == pytest.approx(slippage / (100 * 2.0), rel=1e-9)

    def test_atr_zero_returns_zero(self):
        assert slippage_cost_r(10000, 10000, 0, 2.0) == 0.0

    def test_stop_multiplier_zero_returns_zero(self):
        assert slippage_cost_r(10000, 10000, 100, 0) == 0.0

    def test_negative_atr_returns_zero(self):
        assert slippage_cost_r(10000, 10000, -10, 2.0) == 0.0

    def test_zero_liquidity(self):
        """Zero liquidity returns 0.0 (no slippage estimate)."""
        result = slippage_cost_r(10000, 10000, 100, 2.0, avg_liquidity=0.0)
        assert result == 0.0


class TestTotalCostR:
    def test_sum_of_parts(self):
        """total_cost_r = fee_cost_r + slippage_cost_r (within float epsilon)."""
        fee = fee_cost_r(10000, 10000, 100, 2.0, tier="taker")
        slip = slippage_cost_r(10000, 10000, 100, 2.0, avg_liquidity=100000)
        total = total_cost_r(
            10000, 10000, 100, 2.0,
            tier="taker", avg_liquidity=100000,
        )
        assert total == pytest.approx(fee + slip, rel=1e-9)

    def test_atr_zero_returns_zero(self):
        assert total_cost_r(10000, 10000, 0, 2.0) == 0.0

    def test_all_defaults(self):
        """total_cost_r works with default arguments."""
        result = total_cost_r(10000, 10000, 100, 2.0)
        assert result > 0
