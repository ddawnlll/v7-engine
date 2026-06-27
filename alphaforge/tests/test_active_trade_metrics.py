"""Tests for compute_oos_metrics — active trade metric computations.

Tests: count correctness, net-R arithmetic, edge cases (all NO_TRADE,
all LONG_NOW, zero active trades), exposure_pct, avg_net_R guard, and
oos_trade_count consistency.

No profitability claims. No real market data. 10+ tests.
"""

from __future__ import annotations

import math

import pytest

# ---------------------------------------------------------------------------
# Function under test
# ---------------------------------------------------------------------------


def compute_oos_metrics(
    labels: list[str],
    gross_r_list: list[float],
    fee_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> dict:
    """Compute out-of-sample active trade metrics from label decisions.

    Args:
        labels: List of decision labels ('LONG_NOW', 'SHORT_NOW', 'NO_TRADE').
        gross_r_list: Gross R-multiple for each decision (same length as labels).
        fee_pct: Per-trade fee cost as fraction of R (default 0.0).
        slippage_pct: Per-trade slippage cost as fraction of R (default 0.0).

    Returns:
        Dict with active trade metrics:
            active_trade_count, long_trade_count, short_trade_count,
            no_trade_count, total_gross_R, total_fee_cost_R,
            total_slippage_cost_R, total_net_R,
            avg_net_R_per_active_trade, exposure_pct, oos_trade_count.
    """
    total_decisions = len(labels)

    long_trade_count = sum(1 for l in labels if l == "LONG_NOW")
    short_trade_count = sum(1 for l in labels if l == "SHORT_NOW")
    no_trade_count = sum(1 for l in labels if l == "NO_TRADE")
    active_trade_count = long_trade_count + short_trade_count

    total_gross_R = sum(gross_r_list)

    total_fee_cost_R = fee_pct * active_trade_count
    total_slippage_cost_R = slippage_pct * active_trade_count
    total_net_R = total_gross_R - total_fee_cost_R - total_slippage_cost_R

    exposure_pct = (
        round(active_trade_count / total_decisions * 100, 2)
        if total_decisions > 0
        else 0.0
    )

    avg_net_R_per_active_trade = (
        round(total_net_R / active_trade_count, 6)
        if active_trade_count > 0
        else 0.0
    )

    return {
        "active_trade_count": active_trade_count,
        "long_trade_count": long_trade_count,
        "short_trade_count": short_trade_count,
        "no_trade_count": no_trade_count,
        "total_gross_R": round(total_gross_R, 6),
        "total_fee_cost_R": round(total_fee_cost_R, 6),
        "total_slippage_cost_R": round(total_slippage_cost_R, 6),
        "total_net_R": round(total_net_R, 6),
        "avg_net_R_per_active_trade": avg_net_R_per_active_trade,
        "exposure_pct": exposure_pct,
        "oos_trade_count": active_trade_count,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mixed_labels() -> tuple[list[str], list[float]]:
    """10 decisions: 4 LONG, 3 SHORT, 3 NO_TRADE."""
    labels = [
        "LONG_NOW", "LONG_NOW", "NO_TRADE", "SHORT_NOW",
        "LONG_NOW", "NO_TRADE", "SHORT_NOW", "LONG_NOW",
        "SHORT_NOW", "NO_TRADE",
    ]
    gross_r = [0.5, 0.3, 0.0, 0.2, 0.4, 0.0, -0.1, 0.6, 0.1, 0.0]
    return labels, gross_r


def _all_no_trade() -> tuple[list[str], list[float]]:
    """5 decisions, all NO_TRADE."""
    labels = ["NO_TRADE", "NO_TRADE", "NO_TRADE", "NO_TRADE", "NO_TRADE"]
    gross_r = [0.0, 0.0, 0.0, 0.0, 0.0]
    return labels, gross_r


def _all_long() -> tuple[list[str], list[float]]:
    """5 decisions, all LONG_NOW."""
    labels = ["LONG_NOW", "LONG_NOW", "LONG_NOW", "LONG_NOW", "LONG_NOW"]
    gross_r = [0.2, 0.3, 0.1, 0.4, 0.5]
    return labels, gross_r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeOosMetrics:
    """Tests for compute_oos_metrics."""

    def test_returns_correct_counts_mixed(self):
        """compute_oos_metrics returns correct long/short/no_trade counts."""
        labels, gross = _mixed_labels()
        m = compute_oos_metrics(labels, gross)
        assert m["long_trade_count"] == 4
        assert m["short_trade_count"] == 3
        assert m["no_trade_count"] == 3
        assert m["active_trade_count"] == 7

    def test_active_trade_count_eq_long_plus_short(self):
        """active_trade_count == long_trade_count + short_trade_count."""
        labels, gross = _mixed_labels()
        m = compute_oos_metrics(labels, gross)
        assert m["active_trade_count"] == m["long_trade_count"] + m["short_trade_count"]

    def test_total_net_R_eq_gross_minus_costs(self):
        """total_net_R == total_gross_R - total_fee_cost_R - total_slippage_cost_R."""
        labels, gross = _mixed_labels()
        fee = 0.04
        slip = 0.02
        m = compute_oos_metrics(labels, gross, fee_pct=fee, slippage_pct=slip)
        expected_net = m["total_gross_R"] - m["total_fee_cost_R"] - m["total_slippage_cost_R"]
        assert m["total_net_R"] == pytest.approx(expected_net, abs=1e-6)

    def test_all_no_trade_active_count_zero(self):
        """All NO_TRADE -> active_trade_count = 0."""
        labels, gross = _all_no_trade()
        m = compute_oos_metrics(labels, gross)
        assert m["active_trade_count"] == 0
        assert m["long_trade_count"] == 0
        assert m["short_trade_count"] == 0
        assert m["no_trade_count"] == 5

    def test_all_no_trade_zero_costs(self):
        """All NO_TRADE -> costs are zero (no active trades to charge)."""
        labels, gross = _all_no_trade()
        m = compute_oos_metrics(labels, gross, fee_pct=0.04, slippage_pct=0.02)
        assert m["total_fee_cost_R"] == 0.0
        assert m["total_slippage_cost_R"] == 0.0
        assert m["total_net_R"] == 0.0

    def test_all_long_no_trade_count_zero(self):
        """All LONG_NOW -> no_trade_count = 0."""
        labels, gross = _all_long()
        m = compute_oos_metrics(labels, gross)
        assert m["no_trade_count"] == 0
        assert m["active_trade_count"] == 5
        assert m["long_trade_count"] == 5

    def test_exposure_pct_formula(self):
        """exposure_pct = active_trade_count / total_decisions * 100."""
        labels, gross = _mixed_labels()
        m = compute_oos_metrics(labels, gross)
        expected = round(7 / 10 * 100, 2)
        assert m["exposure_pct"] == expected

    def test_exposure_pct_zero_when_all_no_trade(self):
        """All NO_TRADE -> exposure_pct = 0.0."""
        labels, gross = _all_no_trade()
        m = compute_oos_metrics(labels, gross)
        assert m["exposure_pct"] == 0.0

    def test_exposure_pct_100_when_all_long(self):
        """All LONG_NOW -> exposure_pct = 100.0."""
        labels, gross = _all_long()
        m = compute_oos_metrics(labels, gross)
        assert m["exposure_pct"] == 100.0

    def test_avg_net_R_per_active_trade_zero_when_active_zero(self):
        """When active_trade_count=0, avg_net_R_per_active_trade is 0.0, not NaN."""
        labels, gross = _all_no_trade()
        m = compute_oos_metrics(labels, gross)
        assert m["avg_net_R_per_active_trade"] == 0.0
        assert not math.isnan(m["avg_net_R_per_active_trade"])

    def test_avg_net_R_per_active_trade_formula(self):
        """avg_net_R_per_active_trade = total_net_R / active_trade_count."""
        labels, gross = _mixed_labels()
        m = compute_oos_metrics(labels, gross, fee_pct=0.04, slippage_pct=0.02)
        expected = round(m["total_net_R"] / m["active_trade_count"], 6)
        assert m["avg_net_R_per_active_trade"] == expected

    def test_oos_trade_count_eq_active_trade_count(self):
        """oos_trade_count == active_trade_count (same concept)."""
        labels, gross = _mixed_labels()
        m = compute_oos_metrics(labels, gross)
        assert m["oos_trade_count"] == m["active_trade_count"]

    def test_oos_trade_count_zero_when_all_no_trade(self):
        """All NO_TRADE -> oos_trade_count == 0."""
        labels, gross = _all_no_trade()
        m = compute_oos_metrics(labels, gross)
        assert m["oos_trade_count"] == 0

    def test_cost_calculation_per_active_trade(self):
        """Costs scale with active_trade_count, not total_decisions."""
        labels = ["LONG_NOW", "NO_TRADE", "LONG_NOW"]
        gross = [1.0, 0.0, 1.0]
        fee = 0.1
        m = compute_oos_metrics(labels, gross, fee_pct=fee)
        # 2 active trades * 0.1 fee = 0.2
        assert m["total_fee_cost_R"] == pytest.approx(0.2, abs=1e-6)

    def test_total_gross_R_sum(self):
        """total_gross_R is the raw sum of all gross_r_list entries (including NO_TRADE)."""
        labels = ["LONG_NOW", "NO_TRADE", "SHORT_NOW"]
        gross = [0.5, 0.0, 0.3]
        m = compute_oos_metrics(labels, gross)
        assert m["total_gross_R"] == pytest.approx(0.8, abs=1e-6)

    def test_empty_input_returns_zeros(self):
        """Empty label list returns all zeros, no crash."""
        m = compute_oos_metrics([], [])
        assert m["active_trade_count"] == 0
        assert m["oos_trade_count"] == 0
        assert m["exposure_pct"] == 0.0
        assert m["avg_net_R_per_active_trade"] == 0.0
        assert not math.isnan(m["avg_net_R_per_active_trade"])
