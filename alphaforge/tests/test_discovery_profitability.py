"""Tests for discovery profitability analysis.

Tests: analyze_profitability.
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.discovery import BacktestTradeResult, TradeSignal
from alphaforge.discovery.profitability import analyze_profitability


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_signal(bar_index=0, side="LONG", symbol="BTCUSDT") -> TradeSignal:
    return TradeSignal(
        bar_index=bar_index, timestamp=bar_index * 3600_000_000_000,
        symbol=symbol, side=side, entry_price=100.0,
        atr=2.0, stop_price=98.0 if side == "LONG" else 102.0,
        target_price=106.0 if side == "LONG" else 94.0,
        confidence=0.85, model_score=0.85, initial_risk=2.0,
    )


def _make_trade(net_r: float, side: str = "LONG", symbol: str = "BTCUSDT",
                exit_reason: str = "TARGET_HIT", hold: int = 5,
                gross_r: float | None = None) -> BacktestTradeResult:
    if gross_r is None:
        gross_r = net_r + 0.08  # ~8bps cost
    return BacktestTradeResult(
        signal=_make_signal(side=side, symbol=symbol),
        realized_r_net=net_r,
        realized_r_gross=gross_r,
        fee_cost_r=0.04,
        slippage_cost_r=0.02,
        funding_cost_r=0.0,
        hold_bars=hold,
        exit_price=102.0 if side == "LONG" else 98.0,
        exit_reason=exit_reason,
        path_quality_score=0.7,
        no_trade_saved_loss_r=0.0,
        no_trade_missed_opportunity_r=0.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeProfitability:
    """Tests for analyze_profitability()."""

    def test_empty_trades(self):
        """Empty trade list returns zero-safe metrics."""
        metrics = analyze_profitability([])
        assert metrics["metadata"]["total_trades"] == 0
        assert metrics["return_metrics"]["total_net_R"] == 0.0
        assert metrics["risk_metrics"]["profit_factor"] == 0.0

    def test_all_winning_trades(self):
        """All-winning trades: PF=inf, WR=1.0, drawdown=0."""
        trades = [_make_trade(0.5, "LONG"), _make_trade(0.3, "SHORT")]
        metrics = analyze_profitability(trades)
        risk = metrics["risk_metrics"]

        assert metrics["metadata"]["total_trades"] == 2
        assert risk["win_rate"] == 1.0
        assert risk["profit_factor"] == float("inf")
        assert risk["max_drawdown_R"] == 0.0
        assert risk["sharpe_ratio"] > 0

    def test_mixed_trades(self):
        """Mixed winning/losing trades: PF>0, WR in (0,1), DD<0."""
        trades = [
            _make_trade(0.5, "LONG"),
            _make_trade(-0.3, "SHORT"),
            _make_trade(0.2, "LONG"),
            _make_trade(-0.1, "SHORT"),
        ]
        metrics = analyze_profitability(trades)
        risk = metrics["risk_metrics"]

        assert metrics["metadata"]["total_trades"] == 4
        assert 0 < risk["win_rate"] < 1.0
        assert risk["profit_factor"] > 0
        assert risk["max_drawdown_R"] <= 0  # at least one loss

    def test_all_losing_trades(self):
        """All-losing: PF=0, WR=0, DD<0."""
        trades = [
            _make_trade(-0.5, "LONG"),
            _make_trade(-0.3, "SHORT"),
        ]
        metrics = analyze_profitability(trades)
        risk = metrics["risk_metrics"]

        assert risk["win_rate"] == 0.0
        assert risk["profit_factor"] == 0.0
        assert risk["max_drawdown_R"] < 0

    def test_exit_breakdown(self):
        """Exit reasons are correctly counted."""
        trades = [
            _make_trade(0.5, exit_reason="TARGET_HIT"),
            _make_trade(-0.3, exit_reason="STOP_HIT"),
            _make_trade(0.2, exit_reason="TIME_EXIT"),
        ]
        metrics = analyze_profitability(trades)
        eb = metrics["exit_breakdown"]

        assert eb["target_hit"] == 1
        assert eb["stop_hit"] == 1
        assert eb["time_exit"] == 1

    def test_symbol_breakdown(self):
        """Per-symbol breakdown is correct."""
        trades = [
            _make_trade(0.5, symbol="BTCUSDT"),
            _make_trade(0.3, symbol="ETHUSDT"),
            _make_trade(-0.2, symbol="BTCUSDT"),
        ]
        metrics = analyze_profitability(trades)
        sb = metrics["symbol_breakdown"]

        assert "BTCUSDT" in sb["symbols"]
        assert "ETHUSDT" in sb["symbols"]
        assert sb["symbols"]["BTCUSDT"]["trade_count"] == 2
        assert sb["symbols"]["ETHUSDT"]["trade_count"] == 1

    def test_side_breakdown(self):
        """Long vs short breakdown is correct."""
        trades = [
            _make_trade(0.5, "LONG"),
            _make_trade(0.3, "SHORT"),
            _make_trade(-0.2, "LONG"),
        ]
        metrics = analyze_profitability(trades)
        sd = metrics["side_breakdown"]

        assert sd["long"]["count"] == 2
        assert sd["short"]["count"] == 1
        assert sd["long"]["total_net_R"] > 0

    def test_single_trade(self):
        """Single trade produces valid metrics."""
        trades = [_make_trade(0.5)]
        metrics = analyze_profitability(trades)

        assert metrics["metadata"]["total_trades"] == 1
        assert metrics["return_metrics"]["total_net_R"] == 0.5
        assert metrics["risk_metrics"]["win_rate"] == 1.0
