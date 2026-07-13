"""Kill switch — emergency halt that blocks all new trade execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class KillSwitchReason(str, Enum):
    MANUAL = "manual"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    DRAWDOWN = "drawdown"
    CIRCUIT_BREAKER = "circuit_breaker"
    EXTERNAL = "external"


@dataclass(frozen=True)
class KillSwitchConfig:
    """Thresholds that auto-trigger the kill switch."""

    auto_trigger_on_consecutive_losses: int = 0  # 0 = disabled
    auto_trigger_on_drawdown_pct: float = 0.0  # 0.0 = disabled
    auto_resume_after_minutes: int = 0  # 0 = manual resume only


@dataclass
class KillSwitchState:
    active: bool = False
    triggered_at: str | None = None
    reason: str | None = None
    auto_resume_at: str | None = None


class KillSwitch:
    """Emergency circuit that blocks all new trades when active."""

    def __init__(self, config: KillSwitchConfig | None = None) -> None:
        self.config = config or KillSwitchConfig()
        self._state = KillSwitchState()

    def trigger(self, reason: str = "manual") -> KillSwitchState:
        """Activate the kill switch and log a CRITICAL alert."""
        now = datetime.now(timezone.utc).isoformat()
        self._state = KillSwitchState(
            active=True,
            triggered_at=now,
            reason=reason,
        )
        if self.config.auto_resume_after_minutes > 0:
            from datetime import timedelta

            resume_dt = datetime.now(timezone.utc) + timedelta(minutes=self.config.auto_resume_after_minutes)
            self._state.auto_resume_at = resume_dt.isoformat()
        logger.critical(
            "KILL SWITCH TRIGGERED — reason=%s triggered_at=%s auto_resume_at=%s",
            reason,
            now,
            self._state.auto_resume_at or "manual_resume",
        )
        return self._state

    def release(self) -> KillSwitchState:
        """Deactivate the kill switch."""
        self._state = KillSwitchState()
        return self._state

    def is_active(self) -> bool:
        """Return True if the kill switch is currently blocking trades."""
        if not self._state.active:
            return False
        if self._state.auto_resume_at:
            now = datetime.now(timezone.utc)
            resume_dt = datetime.fromisoformat(self._state.auto_resume_at)
            if now >= resume_dt:
                self._state = KillSwitchState()
                return False
        return True

    def check_auto_conditions(
        self,
        consecutive_losses: int = 0,
        current_drawdown_pct: float = 0.0,
    ) -> bool:
        """Evaluate auto-trigger conditions; returns True if the switch was triggered."""
        if self._state.active:
            return False

        if (
            self.config.auto_trigger_on_consecutive_losses > 0
            and consecutive_losses >= self.config.auto_trigger_on_consecutive_losses
        ):
            self.trigger(reason=KillSwitchReason.CONSECUTIVE_LOSSES.value)
            return True

        if (
            self.config.auto_trigger_on_drawdown_pct > 0
            and current_drawdown_pct >= self.config.auto_trigger_on_drawdown_pct
        ):
            self.trigger(reason=KillSwitchReason.DRAWDOWN.value)
            return True

        return False

    def get_state(self) -> dict[str, Any]:
        """Return the current kill switch state as a plain dict."""
        self.is_active()  # refresh auto-resume
        return {
            "active": self._state.active,
            "triggered_at": self._state.triggered_at,
            "reason": self._state.reason,
            "auto_resume_at": self._state.auto_resume_at,
        }
