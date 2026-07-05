"""
Tests for simulation/engine/funding.py funding cost model.

Verifies the simple perpetual-swap funding cost formula:
  funding_cost_r = notional * funding_rate * holding_bars
"""

import pytest

from simulation.engine.funding import funding_cost_r


class TestFundingCostR:
    """Test the funding_cost_r function."""

    def test_positive_rate_long_position(self):
        """Long position pays positive funding rate -> positive cost."""
        # 1 bp per bar, 100k notional, held 8 bars (e.g. 8h on 1h bars)
        cost = funding_cost_r(notional=100_000.0, funding_rate=0.0001, holding_bars=8)
        assert cost == 80.0

    def test_negative_rate_long_position(self):
        """Long position receives negative funding rate -> negative cost (gain)."""
        cost = funding_cost_r(notional=100_000.0, funding_rate=-0.0001, holding_bars=8)
        assert cost == -80.0

    def test_positive_rate_short_position(self):
        """Short position (negative notional) pays positive rate -> negative cost (gain).
        Actually for short: you receive funding when rate is positive.
        notional is negative for short, so notional * rate = negative * positive = negative.
        """
        cost = funding_cost_r(notional=-100_000.0, funding_rate=0.0001, holding_bars=8)
        assert cost == -80.0

    def test_negative_rate_short_position(self):
        """Short position with negative rate -> positive cost (pay)."""
        cost = funding_cost_r(notional=-100_000.0, funding_rate=-0.0001, holding_bars=8)
        assert cost == 80.0

    def test_single_bar_hold(self):
        """Holding for exactly one bar."""
        cost = funding_cost_r(notional=50_000.0, funding_rate=0.0002, holding_bars=1)
        assert cost == 10.0

    def test_zero_notional(self):
        """Zero notional => zero cost."""
        cost = funding_cost_r(notional=0.0, funding_rate=0.0001, holding_bars=10)
        assert cost == 0.0

    def test_zero_funding_rate(self):
        """Zero funding rate => zero cost."""
        cost = funding_cost_r(notional=100_000.0, funding_rate=0.0, holding_bars=10)
        assert cost == 0.0

    def test_zero_holding_bars(self):
        """Zero holding bars => zero cost."""
        cost = funding_cost_r(notional=100_000.0, funding_rate=0.0001, holding_bars=0)
        assert cost == 0.0

    def test_very_small_rate(self):
        """Very small funding rate (0.1 bp) with large notional."""
        cost = funding_cost_r(notional=1_000_000.0, funding_rate=0.00001, holding_bars=24)
        assert cost == 240.0

    def test_very_large_holding_bars(self):
        """Held for many bars."""
        cost = funding_cost_r(notional=10_000.0, funding_rate=0.0001, holding_bars=1000)
        assert cost == 1000.0

    def test_funding_status_imported(self):
        """Verify the funding module has the expected status constant."""
        from simulation.engine import funding as fmod
        assert hasattr(fmod, "funding_status")
        assert fmod.funding_status == "IMPLEMENTED"

    def test_funding_module_docstring_classification(self):
        """The module docstring must contain a classification marker."""
        from simulation.engine import funding as fmod
        doc = fmod.__doc__ or ""
        assert "IMPLEMENTED" in doc

    def test_integer_notional(self):
        """Integer notional is handled correctly."""
        cost = funding_cost_r(notional=100000, funding_rate=0.0001, holding_bars=8)
        assert cost == 80.0

    def test_high_funding_rate(self):
        """High funding rate scenario (e.g. volatile market)."""
        # 10 bp per bar for extreme scenario
        cost = funding_cost_r(notional=50_000.0, funding_rate=0.001, holding_bars=4)
        assert cost == 200.0
