"""
Tests for lib/costs/ — fees and slippage.
"""

import pytest
from lib.costs.fees import estimate_fee, estimate_maker_fee, estimate_taker_fee
from lib.costs.slippage import get_slippage


# =====================================================================
# Fees
# =====================================================================

class TestEstimateFee:
    def test_maker_default(self):
        assert estimate_maker_fee(10_000.0) == 1.0  # 0.01%

    def test_taker_default(self):
        assert estimate_taker_fee(10_000.0) == 4.0  # 0.04%

    def test_explicit_tier(self):
        assert estimate_fee(10_000.0, "maker") == 1.0
        assert estimate_fee(10_000.0, "taker") == 4.0

    def test_custom_rate(self):
        assert estimate_fee(10_000.0, "maker", maker_rate=0.0005) == 5.0
        assert estimate_fee(10_000.0, "taker", taker_rate=0.001) == 10.0

    def test_zero_notional(self):
        assert estimate_maker_fee(0.0) == 0.0

    def test_negative_notional(self):
        assert estimate_maker_fee(-1000.0) == -0.1  # negative fee for negative notional

    def test_large_notional(self):
        fee = estimate_taker_fee(1_000_000.0)
        assert fee == 400.0  # 0.04% of 1M

    def test_fractional_notional(self):
        fee = estimate_maker_fee(0.50)
        assert fee == 0.00005  # 0.01% of $0.50


# =====================================================================
# Slippage
# =====================================================================

class TestGetSlippage:
    def test_explicit_percentage(self):
        assert get_slippage(10_000.0, 100_000.0, slippage_pct=0.05) == 5.0

    def test_explicit_zero(self):
        assert get_slippage(10_000.0, 100_000.0, slippage_pct=0.0) == 0.0

    def test_estimated_slippage(self):
        slip = get_slippage(10_000.0, 100_000.0)
        assert slip > 0
        assert isinstance(slip, float)

    def test_small_trade(self):
        slip = get_slippage(100.0, 1_000_000.0)
        assert slip > 0

    def test_large_trade(self):
        slip = get_slippage(500_000.0, 100_000.0)
        assert slip > get_slippage(10_000.0, 100_000.0)  # larger trade = more slippage

    def test_zero_liquidity(self):
        slip = get_slippage(10_000.0, 0.0)
        assert slip == 0.0

    def test_zero_notional(self):
        slip = get_slippage(0.0, 100_000.0)
        assert slip == 0.0

    def test_zero_both(self):
        slip = get_slippage(0.0, 0.0)
        assert slip == 0.0
