"""Safety gate chain — composes KillSwitch, DrawdownGate, PositionLimiter,
and SymbolCap into a single mandatory check that runs before every trade.

This module is deliberately free of orchestrator / DB dependencies so it
can be imported in tests without bootstrapping the full v6 stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.runtime.safety.drawdown_gate import DrawdownGate
from runtime.runtime.safety.kill_switch import KillSwitch, KillSwitchConfig
from runtime.runtime.safety.position_limiter import PositionLimiter
from runtime.runtime.safety.symbol_cap import SymbolCap


@dataclass(frozen=True)
class SafetyCheckResult:
    """Typed result from a safety gate check — records why a trade was blocked.

    This is the lineage record for a safety rejection.
    """

    gate: str
    passed: bool
    reason: str | None = None
    detail: dict[str, Any] | None = field(default_factory=dict)


class SafetyGateChain:
    """Composes KillSwitch, DrawdownGate, PositionLimiter, SymbolCap
    into a mandatory gate chain checked before every trade.

    Guards fire in the canonical order below.  The first guard that
    rejects the trade short-circuits the rest.  A ``None`` return from
    :meth:`check_all` means *all gates passed*.
    """

    def __init__(
        self,
        kill_switch: KillSwitch | None = None,
        drawdown_gate: DrawdownGate | None = None,
        position_limiter: PositionLimiter | None = None,
        symbol_cap: SymbolCap | None = None,
    ) -> None:
        self.kill_switch = kill_switch or KillSwitch(
            KillSwitchConfig(auto_trigger_on_drawdown_pct=30.0)
        )
        self.drawdown_gate = drawdown_gate or DrawdownGate()
        self.position_limiter = position_limiter or PositionLimiter()
        self.symbol_cap = symbol_cap or SymbolCap()

    def check_all(
        self,
        signal: dict[str, Any],
        *,
        equity: float | None = None,
        proposed_notional: float | None = None,
        current_positions: list[dict[str, Any]] | None = None,
        current_exposures: dict[str, dict[str, Any]] | None = None,
    ) -> SafetyCheckResult | None:
        """Check all four gates in order.  Returns the first ``SafetyCheckResult``
        with ``passed=False``, or ``None`` if every gate passes.

        Parameters
        ----------
        signal : dict
            Trade signal being evaluated.  Used to extract symbol, notional etc.
        equity : float or None
            Current portfolio equity (needed for drawdown gate).
        proposed_notional : float or None
            Notional value of the proposed trade.  Falls back to ``signal`` keys.
        current_positions : list[dict] or None
            Currently open positions (for position limiter).
        current_exposures : dict[str, dict] or None
            Current symbol exposures (for symbol cap).
        """
        # 1. KillSwitch — fail-closed if active
        if self.kill_switch.is_active():
            state = self.kill_switch.get_state()
            return SafetyCheckResult(
                gate="KILL_SWITCH",
                passed=False,
                reason=f"Kill switch active: {state.get('reason')}",
                detail={"state": state},
            )

        # 2. DrawdownGate — check equity threshold
        #    Also feed equity drawdown into KillSwitch auto-trigger so the
        #    kill-switch's own drawdown logic fires from live data, not just
        #    from manual trigger() calls (Issue #333).
        dd_pct: float = 0.0
        if equity is not None:
            dd_state = self.drawdown_gate.update_equity(equity)
            dd_pct = dd_state.drawdown_pct
            self.kill_switch.check_auto_conditions(current_drawdown_pct=dd_pct)
        if self.drawdown_gate.block_new_trades():
            dd_state = self.drawdown_gate.get_state()
            return SafetyCheckResult(
                gate="DRAWDOWN_GATE",
                passed=False,
                reason=dd_state.get("block_reason") or "drawdown threshold breached",
                detail=dd_state,
            )

        # 3. PositionLimiter — check position exposure limits
        notional = proposed_notional
        if notional is None:
            notional = abs(
                float(signal.get("notional", 0))
                or float(signal.get("entry", 0)) * float(signal.get("quantity", signal.get("qty", 0)))
            )
        violation = self.position_limiter.reject_if_over_limit(
            notional,
            current_positions or [],
        )
        if violation is not None:
            return SafetyCheckResult(
                gate="POSITION_LIMITER",
                passed=False,
                reason=violation.message,
                detail={"rule": violation.rule, "current": violation.current, "limit": violation.limit},
            )

        # 4. SymbolCap — check per-symbol and aggregate caps
        symbol = signal.get("symbol", "")
        violation = self.symbol_cap.check_symbol_exposure(
            symbol,
            notional,
            current_exposures or {},
        )
        if violation is not None:
            return SafetyCheckResult(
                gate="SYMBOL_CAP",
                passed=False,
                reason=violation.message,
                detail={"rule": violation.rule, "symbol": violation.symbol, "current": violation.current, "limit": violation.limit},
            )

        return None
