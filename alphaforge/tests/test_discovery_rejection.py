"""Tests for discovery rejection engine.

Tests: evaluate_alpha, rejection_to_verdict.
"""

from __future__ import annotations

import pytest

from alphaforge.discovery.rejection import (
    DEFAULT_THRESHOLDS,
    evaluate_alpha,
    rejection_to_verdict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_metrics(
    n_trades: int = 100,
    expectancy_r: float = 0.15,
    sharpe: float = 0.8,
    pf: float = 1.5,
    max_dd: float = -2.0,
    win_rate: float = 0.55,
    cost_drag: float = 20.0,
    dominant_share: float = 0.30,
) -> dict:
    return {
        "metadata": {
            "total_trades": n_trades,
            "long_trades": n_trades // 2,
            "short_trades": n_trades // 2,
        },
        "return_metrics": {
            "total_gross_R": n_trades * 0.25,
            "total_net_R": n_trades * expectancy_r,
            "avg_net_R": expectancy_r,
            "median_net_R": expectancy_r * 0.9,
            "expectancy_R": expectancy_r,
        },
        "risk_metrics": {
            "profit_factor": pf,
            "sharpe_ratio": sharpe,
            "max_drawdown_R": max_dd,
            "calmar_ratio": abs(expectancy_r / max_dd) if max_dd != 0 else 0,
            "win_rate": win_rate,
            "avg_hold_bars": 5.0,
            "avg_path_quality": 0.65,
        },
        "exit_breakdown": {
            "stop_hit": int(n_trades * 0.3),
            "target_hit": int(n_trades * 0.5),
            "time_exit": int(n_trades * 0.2),
            "other": 0,
            "stop_pct": 30.0,
            "target_pct": 50.0,
            "time_exit_pct": 20.0,
        },
        "cost_decomposition": {
            "total_fee_cost_R": n_trades * 0.04,
            "total_slippage_cost_R": n_trades * 0.02,
            "total_funding_cost_R": 0.0,
            "total_cost_R": n_trades * 0.06,
            "avg_cost_per_trade_R": 0.06,
            "cost_drag_pct": cost_drag,
        },
        "symbol_breakdown": {
            "symbols": {
                "BTCUSDT": {"total_net_R": expectancy_r * n_trades * 0.6, "trade_count": int(n_trades * 0.6)},
                "ETHUSDT": {"total_net_R": expectancy_r * n_trades * 0.4, "trade_count": int(n_trades * 0.4)},
            },
            "best_symbol": "BTCUSDT",
            "dominant_share": dominant_share,
        },
        "side_breakdown": {
            "long": {"count": n_trades // 2, "total_net_R": expectancy_r * n_trades * 0.5, "avg_net_R": expectancy_r, "win_rate": win_rate},
            "short": {"count": n_trades // 2, "total_net_R": expectancy_r * n_trades * 0.5, "avg_net_R": expectancy_r, "win_rate": win_rate},
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvaluateAlpha:
    """Tests for evaluate_alpha()."""

    def test_promotes_strong_alpha(self):
        """All criteria passing produces PROMOTE."""
        metrics = _make_metrics()
        result = evaluate_alpha(metrics, mode="SWING")

        assert result["decision"] == "PROMOTE"
        assert all(r["passed"] for r in result["reasons"])

    def test_rejects_low_trades(self):
        """Insufficient trade count produces REJECT."""
        metrics = _make_metrics(n_trades=5)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        rule = next(r for r in result["reasons"] if r["rule"] == "MIN_TRADES")
        assert not rule["passed"]

    def test_rejects_negative_expectancy(self):
        """Negative expectancy produces REJECT."""
        metrics = _make_metrics(expectancy_r=-0.05)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        rule = next(r for r in result["reasons"] if r["rule"] == "EXPECTANCY_R")
        assert not rule["passed"]

    def test_rejects_low_profit_factor(self):
        """Profit factor below 1.0 produces REJECT."""
        metrics = _make_metrics(pf=0.85)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        rule = next(r for r in result["reasons"] if r["rule"] == "PROFIT_FACTOR")
        assert not rule["passed"]

    def test_rejects_deep_drawdown(self):
        """Excessive drawdown produces REJECT."""
        metrics = _make_metrics(max_dd=-8.0)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        rule = next(r for r in result["reasons"] if r["rule"] == "MAX_DRAWDOWN")
        assert not rule["passed"]

    def test_rejects_low_sharpe(self):
        """Low Sharpe produces REJECT."""
        metrics = _make_metrics(sharpe=0.1)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        rule = next(r for r in result["reasons"] if r["rule"] == "SHARPE")
        assert not rule["passed"]

    def test_watches_low_win_rate(self):
        """Low win rate (non-critical) produces WATCH."""
        metrics = _make_metrics(win_rate=0.25)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "WATCH"
        rule = next(r for r in result["reasons"] if r["rule"] == "WIN_RATE")
        assert not rule["passed"]

    def test_watches_high_concentration(self):
        """High symbol concentration (non-critical) produces WATCH."""
        metrics = _make_metrics(dominant_share=0.75)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "WATCH"

    def test_watches_high_cost_drag(self):
        """High cost drag (non-critical) produces WATCH."""
        metrics = _make_metrics(cost_drag=80.0)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "WATCH"

    def test_rejects_with_multiple_failures(self):
        """Multiple critical failures produce REJECT with all failed rules listed."""
        metrics = _make_metrics(n_trades=5, expectancy_r=-0.1, pf=0.5)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"
        failed_critical = [r for r in result["reasons"] if r["critical"] and not r["passed"]]
        assert len(failed_critical) >= 2  # at least MIN_TRADES + EXPECTANCY_R

    def test_accepts_boundary_values(self):
        """Values exactly at threshold pass."""
        metrics = _make_metrics(
            expectancy_r=0.10, sharpe=0.5, pf=1.2, win_rate=0.35,
        )
        result = evaluate_alpha(metrics)

        assert result["decision"] in ("PROMOTE", "WATCH")
        critical_failed = [r for r in result["reasons"] if r["critical"] and not r["passed"]]
        assert len(critical_failed) == 0

    def test_empty_metrics_are_rejected(self):
        """Fully zero metrics produce REJECT."""
        metrics = _make_metrics(n_trades=0, expectancy_r=0, sharpe=0, pf=0)
        result = evaluate_alpha(metrics)

        assert result["decision"] == "REJECT"

    def test_returns_all_reasons(self):
        """Result contains expected reason structure."""
        metrics = _make_metrics()
        result = evaluate_alpha(metrics)

        assert "reasons" in result
        assert len(result["reasons"]) == len(DEFAULT_THRESHOLDS)
        for r in result["reasons"]:
            assert "rule" in r
            assert "passed" in r
            assert "critical" in r
            assert "detail" in r


class TestRejectionToVerdict:
    """Tests for rejection_to_verdict()."""

    def test_reject_maps_to_reject(self):
        assert rejection_to_verdict("REJECT") == "REJECT"

    def test_watch_maps_to_continue_research(self):
        assert rejection_to_verdict("WATCH") == "CONTINUE_RESEARCH"

    def test_promote_maps_to_candidate(self):
        assert rejection_to_verdict("PROMOTE") == "CANDIDATE_FOR_V7_GATES"

    def test_unknown_defaults_to_continue_research(self):
        assert rejection_to_verdict("UNKNOWN") == "CONTINUE_RESEARCH"
