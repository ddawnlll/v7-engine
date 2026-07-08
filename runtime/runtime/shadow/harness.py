"""Shadow harness — records paper trades and compares live execution against simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PaperTrade:
    """A single recorded paper trade for shadow comparison."""

    trade_id: str
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    notional: float
    mode: str
    signal_id: str | None = None
    sim_entry_price: float | None = None
    sim_exit_price: float | None = None
    sim_pnl: float | None = None
    live_exit_price: float | None = None
    live_pnl: float | None = None
    slippage_bps: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: str | None = None


class ShadowHarness:
    """Tracks paper trades and compares live execution against simulation targets."""

    def __init__(self) -> None:
        self._trades: dict[str, PaperTrade] = {}

    def record_trade(self, trade: PaperTrade) -> None:
        """Register a new paper trade."""
        self._trades[trade.trade_id] = trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
    ) -> PaperTrade | None:
        """Close a paper trade with the given exit price."""
        trade = self._trades.get(trade_id)
        if trade is None:
            return None
        trade.live_exit_price = exit_price
        sign = 1.0 if trade.side == "LONG" else -1.0
        trade.live_pnl = (exit_price - trade.entry_price) * trade.quantity * sign
        if trade.entry_price > 0:
            trade.slippage_bps = abs(exit_price - trade.entry_price) / trade.entry_price * 10_000
        trade.closed_at = datetime.now(timezone.utc).isoformat()
        return trade

    def get_trade(self, trade_id: str) -> PaperTrade | None:
        """Return a single trade by ID."""
        return self._trades.get(trade_id)

    def list_trades(self) -> list[PaperTrade]:
        """Return all recorded trades."""
        return list(self._trades.values())

    def compare_with_sim(
        self,
        trade_id: str,
    ) -> dict[str, Any] | None:
        """Compare live execution against simulation for a given trade.

        Returns a dict with deviation metrics, or None if the trade is missing.
        Stub implementation — full comparison logic will be built out later.
        """
        trade = self._trades.get(trade_id)
        if trade is None:
            return None

        if trade.live_pnl is None or trade.sim_pnl is None:
            return {
                "trade_id": trade_id,
                "status": "incomplete",
                "reason": "missing live or sim PnL data",
            }

        pnl_deviation = trade.live_pnl - trade.sim_pnl
        slippage = trade.slippage_bps or 0.0

        return {
            "trade_id": trade_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "sim_pnl": trade.sim_pnl,
            "live_pnl": trade.live_pnl,
            "pnl_deviation": pnl_deviation,
            "slippage_bps": slippage,
            "status": "compared",
        }

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate stats across all tracked trades."""
        trades = list(self._trades.values())
        closed = [t for t in trades if t.closed_at is not None]
        open_trades = [t for t in trades if t.closed_at is None]
        live_pnls = [t.live_pnl for t in closed if t.live_pnl is not None]
        return {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "open_trades": len(open_trades),
            "total_live_pnl": sum(live_pnls) if live_pnls else 0.0,
            "avg_slippage_bps": (
                sum(t.slippage_bps for t in closed if t.slippage_bps is not None)
                / max(1, len([t for t in closed if t.slippage_bps is not None]))
                if closed
                else 0.0
            ),
        }
