"""Drawdown gate — blocks new trades when portfolio drawdown exceeds configured thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DrawdownThreshold:
    """A single drawdown level with its associated action."""

    pct: float
    action: str  # "warn", "degrade", "block"


@dataclass(frozen=True)
class DrawdownState:
    peak_equity: float = 0.0
    current_equity: float = 0.0
    drawdown_pct: float = 0.0
    blocked: bool = False
    block_reason: str | None = None
    blocked_at: str | None = None


class DrawdownGate:
    """Monitors equity drawdown and blocks new trades when thresholds are breached."""

    DEFAULT_THRESHOLDS = [
        DrawdownThreshold(pct=10.0, action="warn"),
        DrawdownThreshold(pct=20.0, action="degrade"),
        DrawdownThreshold(pct=30.0, action="block"),
    ]

    def __init__(
        self,
        thresholds: list[DrawdownThreshold] | None = None,
        recovery_hysteresis_pct: float = 5.0,
    ) -> None:
        self.thresholds = sorted(
            thresholds or self.DEFAULT_THRESHOLDS,
            key=lambda t: t.pct,
        )
        self.recovery_hysteresis_pct = recovery_hysteresis_pct
        self._state = DrawdownState()

    def update_equity(self, current_equity: float) -> DrawdownState:
        """Update the gate with the latest equity figure and recalculate drawdown."""
        if current_equity <= 0:
            return self._state

        if current_equity > self._state.peak_equity:
            self._state = DrawdownState(
                peak_equity=current_equity,
                current_equity=current_equity,
                drawdown_pct=0.0,
                blocked=False,
                block_reason=None,
                blocked_at=None,
            )
            return self._state

        dd_pct = ((self._state.peak_equity - current_equity) / self._state.peak_equity) * 100.0
        blocked = False
        block_reason = None
        blocked_at = None

        for threshold in reversed(self.thresholds):
            if dd_pct >= threshold.pct:
                blocked = threshold.action == "block"
                block_reason = f"drawdown {dd_pct:.1f}% >= {threshold.pct}% ({threshold.action})"
                if blocked and self._state.blocked:
                    blocked_at = self._state.blocked_at
                elif blocked:
                    blocked_at = datetime.now(timezone.utc).isoformat()
                break

        # Hysteresis: only unblock if drawdown recovers past threshold + hysteresis
        if self._state.blocked and not blocked:
            recover_target = self._state.drawdown_pct - self.recovery_hysteresis_pct
            if dd_pct > recover_target + 1e-6:
                blocked = True
                block_reason = self._state.block_reason
                blocked_at = self._state.blocked_at

        self._state = DrawdownState(
            peak_equity=self._state.peak_equity,
            current_equity=current_equity,
            drawdown_pct=dd_pct,
            blocked=blocked,
            block_reason=block_reason,
            blocked_at=blocked_at,
        )
        return self._state

    def check_drawdown(self) -> DrawdownState:
        """Return the current drawdown state."""
        return self._state

    def block_new_trades(self) -> bool:
        """Return True if new trades should be blocked right now."""
        return self._state.blocked

    def get_state(self) -> dict[str, Any]:
        """Return the drawdown state as a plain dict."""
        return {
            "peak_equity": self._state.peak_equity,
            "current_equity": self._state.current_equity,
            "drawdown_pct": self._state.drawdown_pct,
            "blocked": self._state.blocked,
            "block_reason": self._state.block_reason,
            "blocked_at": self._state.blocked_at,
        }
