"""
V7 Risk Manager — Hard Safety Guards.

Domain authority:
  - Owns hard risk controls applied after policy + portfolio stages
  - Determines execution eligibility (not economic actionability)
  - Cannot be overridden by model confidence or expected-R

Pipeline position: policy -> portfolio -> risk -> runtime execution eligibility

Design per:
  - v7/docs/pipeline/risk.md
  - v7/docs/implementation/phase_7_portfolio_risk_and_runtime_integration.md

Key principles:
  - No hidden risk veto
  - Hard guards stay hard
  - Model confidence cannot override operational limits
  - Separate economic actionability from execution eligibility
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Default risk configuration (LOCK_CANDIDATE per pipeline/risk.md)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict[str, Any] = {
    "max_drawdown_pct": 25.0,
    "max_exposure_per_symbol_pct": 10.0,
    "kill_switch_enabled": True,
    "max_daily_loss_pct": 5.0,
}


# ---------------------------------------------------------------------------
# RiskResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskResult:
    """Output of risk hard-guard evaluation.

    Attributes:
        risk_ok: True if all guards pass (no hard blocks).
        blocking_guards: Names of guards that blocked execution.
        drawdown_state: Current drawdown metrics.
        warnings: Non-blocking advisory warnings.
    """

    risk_ok: bool = True
    blocking_guards: list[str] = field(default_factory=list)
    drawdown_state: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GuardResult (internal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardResult:
    """Result of a single guard check."""

    passed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------


class RiskManager:
    """Hard safety gates applied after portfolio suppression.

    Guards (all checked by check_hard_guards):
      1. max_drawdown — cumulative drawdown exceeds configured threshold
      2. max_exposure_per_symbol — any single symbol over limit
      3. kill_switch_active — global kill switch engaged
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config: dict[str, Any] = {**DEFAULT_CONFIG, **(config or {})}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def check_hard_guards(
        self,
        portfolio_result: PortfolioResult | None,
        account_state: dict[str, Any],
    ) -> RiskResult:
        """Evaluate all hard risk guards against current state + portfolio output.

        Args:
            portfolio_result: Output from PortfolioManager.evaluate_portfolio().
                              May be None if portfolio stage was skipped.
            account_state: Dict with account-level state. Expected keys:
                - account_value (float): Current account value.
                - peak_value (float): Peak account value (for drawdown calc).
                - current_drawdown_pct (float, optional): Pre-computed drawdown.
                - total_exposure_pct (float): Current total exposure.
                - positions (dict): Current positions {symbol: {size_pct, ...}}.
                - kill_switch_active (bool): Whether kill switch is engaged.
                - daily_loss_pct (float): Today's P&L as % of account.
                - mode (str, optional): Current trading mode for mode-specific limits.

        Returns:
            RiskResult with guard outcomes.
        """
        blocking_guards: list[str] = []
        warnings: list[str] = []

        # Compute drawdown state
        drawdown_state = self._compute_drawdown_state(account_state)

        # ---- Guard 1: Max Drawdown ----
        guard_result = self._check_max_drawdown(drawdown_state, account_state)
        if not guard_result.passed:
            blocking_guards.append("max_drawdown")
        if guard_result.metadata:
            drawdown_state.update(guard_result.metadata)
        if guard_result.reason:
            warnings.append(guard_result.reason)

        # ---- Guard 2: Max Exposure Per Symbol ----
        guard_result = self._check_max_exposure_per_symbol(
            portfolio_result, account_state
        )
        if not guard_result.passed:
            blocking_guards.append("max_exposure_per_symbol")
        if guard_result.reason:
            warnings.append(guard_result.reason)

        # ---- Guard 3: Kill Switch ----
        guard_result = self._check_kill_switch(account_state)
        if not guard_result.passed:
            blocking_guards.append("kill_switch_active")
        if guard_result.reason:
            warnings.append(guard_result.reason)

        # ---- Account integrity check ----
        guard_result = self._check_account_integrity(account_state)
        if not guard_result.passed:
            blocking_guards.append("account_integrity")
        if guard_result.reason:
            warnings.append(guard_result.reason)

        risk_ok = len(blocking_guards) == 0

        return RiskResult(
            risk_ok=risk_ok,
            blocking_guards=blocking_guards,
            drawdown_state=drawdown_state,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Individual guard checks (public for unit testing)
    # ------------------------------------------------------------------

    def check_max_drawdown(
        self, account_state: dict[str, Any]
    ) -> GuardResult:
        """Check whether current drawdown exceeds the configured threshold."""
        drawdown_state = self._compute_drawdown_state(account_state)
        return self._check_max_drawdown(drawdown_state, account_state)

    def check_max_exposure_per_symbol(
        self,
        portfolio_result: PortfolioResult | None,
        account_state: dict[str, Any],
    ) -> GuardResult:
        """Check whether any symbol exceeds per-symbol exposure limit."""
        return self._check_max_exposure_per_symbol(portfolio_result, account_state)

    def check_kill_switch(
        self, account_state: dict[str, Any]
    ) -> GuardResult:
        """Check whether the global kill switch is active."""
        return self._check_kill_switch(account_state)

    def check_account_integrity(
        self, account_state: dict[str, Any]
    ) -> GuardResult:
        """Check that account state has minimum integrity for execution."""
        return self._check_account_integrity(account_state)

    # ------------------------------------------------------------------
    # Internal guard implementations
    # ------------------------------------------------------------------

    def _compute_drawdown_state(
        self, account_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute current drawdown metrics from account state."""
        account_value = float(account_state.get("account_value", 0.0))
        peak_value = float(
            account_state.get("peak_value", account_value)
        )

        if account_value <= 0 or peak_value <= 0:
            return {
                "current_drawdown_pct": 0.0,
                "account_value": account_value,
                "peak_value": peak_value,
                "drawdown_status": "INSUFFICIENT_DATA",
            }

        current_drawdown_pct = account_state.get(
            "current_drawdown_pct",
            max(0.0, (peak_value - account_value) / peak_value * 100.0),
        )

        return {
            "current_drawdown_pct": round(current_drawdown_pct, 4),
            "account_value": round(account_value, 2),
            "peak_value": round(peak_value, 2),
        }

    def _check_max_drawdown(
        self,
        drawdown_state: dict[str, Any],
        account_state: dict[str, Any],
    ) -> GuardResult:
        """Guard: cumulative drawdown must be below configured threshold."""
        max_drawdown_pct = self.config.get("max_drawdown_pct", 25.0)
        current_drawdown_pct = drawdown_state.get("current_drawdown_pct", 0.0)

        if current_drawdown_pct >= max_drawdown_pct:
            return GuardResult(
                passed=False,
                reason=(
                    f"Drawdown {current_drawdown_pct:.2f}% exceeds "
                    f"max_drawdown_pct {max_drawdown_pct:.2f}%"
                ),
                metadata={"drawdown_breach": True},
            )

        return GuardResult(
            passed=True,
            reason=(
                f"Drawdown {current_drawdown_pct:.2f}% within limit "
                f"{max_drawdown_pct:.2f}%"
            ),
        )

    def _check_max_exposure_per_symbol(
        self,
        portfolio_result: PortfolioResult | None,
        account_state: dict[str, Any],
    ) -> GuardResult:
        """Guard: no single symbol exceeds per-symbol exposure limit."""
        max_exp_pct = self.config.get("max_exposure_per_symbol_pct", 10.0)
        positions = account_state.get("positions", {})

        # Check current positions
        over_limit_symbols: list[str] = []
        for symbol, pos_data in positions.items():
            if isinstance(pos_data, dict):
                size = float(
                    pos_data.get("size_pct", pos_data.get("exposure_pct", 0.0))
                )
                if size > max_exp_pct:
                    over_limit_symbols.append(f"{symbol}={size:.2f}%")

        # Also check proposed positions from portfolio result
        if portfolio_result is not None:
            for d in portfolio_result.ranked:
                symbol = d.get("symbol", "")
                proposed = d.get("position_size_pct", 0.0)
                if not isinstance(proposed, (int, float)):
                    continue
                # Always check combined (current + proposed) exposure
                current = positions.get(symbol, {})
                combined = proposed
                if isinstance(current, dict):
                    current_size = float(
                        current.get("size_pct", current.get("exposure_pct", 0.0))
                    )
                    combined = proposed + current_size
                if combined > max_exp_pct:
                    over_limit_symbols.append(
                        f"{symbol}={combined:.2f}% (current + proposed)"
                    )

        if over_limit_symbols:
            return GuardResult(
                passed=False,
                reason=(
                    f"Symbol exposure exceeds {max_exp_pct}%: "
                    f"{', '.join(over_limit_symbols)}"
                ),
            )

        return GuardResult(passed=True, reason="All symbols within per-symbol exposure limit")

    def _check_kill_switch(
        self, account_state: dict[str, Any]
    ) -> GuardResult:
        """Guard: global kill switch must not be active."""
        if not self.config.get("kill_switch_enabled", True):
            return GuardResult(
                passed=True,
                reason="Kill switch is disabled in config — guard skipped",
            )

        kill_active = account_state.get("kill_switch_active", False)
        if kill_active:
            return GuardResult(
                passed=False,
                reason="Global kill switch is active — all trading blocked",
            )

        return GuardResult(passed=True, reason="Kill switch is inactive")

    def _check_account_integrity(
        self, account_state: dict[str, Any]
    ) -> GuardResult:
        """Guard: account state must have minimum integrity."""
        account_value = account_state.get("account_value")
        if account_value is None:
            return GuardResult(
                passed=False,
                reason="Account value is missing — insufficient integrity for execution",
            )

        if not isinstance(account_value, (int, float)) or account_value <= 0:
            return GuardResult(
                passed=False,
                reason=f"Invalid account value: {account_value}",
            )

        return GuardResult(passed=True, reason="Account integrity OK")


# Forward reference for type hint
from v7.portfolio import PortfolioResult
