"""
V7 Policy Acceptance Layer.

Core rule:
  confidence >= threshold AND expected_value > 0 after costs

This module evaluates whether a trade decision passes policy gates:
  1. Confidence gate: model confidence >= mode-specific min_confidence
  2. Cost gate: expected net value > 0 after fee + slippage + funding
  3. Risk gate: position size within limits, stop/take sane
  4. Regime gate: placeholder (always passes in initial baseline)

Uses simulation/engine/costs for cost computation.

Decision outputs follow the AnalysisResult contract schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from simulation.engine.costs import (
    compute_entry_risk,
    fee_cost_r,
    slippage_cost_r,
    total_cost_r,
)

from v7.router import HOLD, LOCKED_INITIAL_BASELINE, get_mode_profile


@dataclass(frozen=True)
class PolicyResult:
    """Output of policy evaluation.

    Attributes:
        decision: Trade decision — ENTER_LONG, ENTER_SHORT, or HOLD.
        confidence: Confidence score 0-1.
        expected_r: Expected R-multiple after costs (net).
        passed: Whether all policy gates passed.
        gates: Per-gate pass/fail detail.
        reason: Human-readable explanation.
        stop_loss_price: Recommended stop-loss (float, or 0.0 for HOLD).
        take_profit_price: Recommended take-profit (float, or 0.0 for HOLD).
        entry_price: Recommended entry price (float, or 0.0 for HOLD).
        position_size_pct: Recommended position size %.
        total_cost_r: Total estimated cost in R-multiples.
    """

    decision: str
    confidence: float
    expected_r: float
    passed: bool
    gates: dict[str, bool]
    reason: str
    stop_loss_price: float
    take_profit_price: float
    entry_price: float
    position_size_pct: float
    total_cost_r: float = 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_policy(
    *,
    request: dict[str, Any],
    confidence: float,
    expected_r_gross: float,
    entry_price: float,
    atr: float,
    notional: float,
    direction: str = "LONG",
    taker_fee_bps: float = 4.0,
    slippage_bps: float = 1.0,
    funding_rate: float = 0.0,
    holding_bars: int = 0,
) -> PolicyResult:
    """Evaluate whether a trade candidate passes all policy gates.

    This is the single entry-point for V7 policy acceptance.

    Args:
        request: The validated AnalysisRequest dict.
        confidence: Model confidence score 0-1.
        expected_r_gross: Expected R-multiple before costs (gross).
        entry_price: Recommended entry price in quote currency.
        atr: Current ATR value for stop/target sizing.
        notional: Notional position size in quote currency.
        direction: LONG or SHORT.
        taker_fee_bps: Fee in basis points (default 4.0 = 0.04%).
        slippage_bps: Slippage in basis points (default 1.0 = 0.01%).
        funding_rate: Per-bar funding rate (default 0.0).
        holding_bars: Expected holding bars for funding cost.

    Returns:
        PolicyResult with decision, confidence, gates, and reason.
    """
    mode = request.get("mode", "SWING")
    profile = get_mode_profile(mode)
    status = profile.get("status", HOLD)

    # === Gate 0: Mode lock ===
    if status != LOCKED_INITIAL_BASELINE:
        return PolicyResult(
            decision="HOLD",
            confidence=confidence,
            expected_r=0.0,
            passed=False,
            gates={"mode_lock": False},
            reason=f"Mode '{mode}' is on HOLD: {profile.get('hold_reason', 'No reason provided')}",
            stop_loss_price=0.0,
            take_profit_price=0.0,
            entry_price=0.0,
            position_size_pct=0.0,
        )

    # Mode-specific thresholds
    min_confidence = profile.get("min_confidence", 0.55)
    min_expected_r = profile.get("min_expected_r", 0.20)
    max_position_pct = profile.get("max_position_size_pct", 10.0)
    stop_mult = profile.get("stop_multiplier", 2.0)
    target_mult = profile.get("target_multiplier", 2.5)

    # === Gate 1: Confidence gate ===
    confidence_gate = confidence >= min_confidence

    # === Cost computation ===
    entry_risk = compute_entry_risk(atr, stop_mult)
    if entry_risk <= 0:
        # Cannot size risk — default to HOLD
        return PolicyResult(
            decision="HOLD",
            confidence=confidence,
            expected_r=0.0,
            passed=False,
            gates={"confidence_gate": confidence_gate, "cost_gate": False},
            reason="Entry risk is zero or negative (ATR or stop multiplier invalid)",
            stop_loss_price=0.0,
            take_profit_price=0.0,
            entry_price=entry_price,
            position_size_pct=0.0,
        )

    fcr, scr, fund_r, tcr = total_cost_r(
        notional=notional,
        entry_price=entry_price,
        atr=atr,
        stop_multiplier=stop_mult,
        taker_fee_bps=taker_fee_bps,
        slippage_bps=slippage_bps,
        funding_rate=funding_rate,
        holding_bars=holding_bars,
    )

    # Net expected R after costs
    expected_r_net = expected_r_gross - tcr

    # === Gate 2: Cost gate (expected value > 0 after costs) ===
    cost_gate = expected_r_net > 0 and expected_r_net >= min_expected_r

    # === Gate 3: Position sizing ===
    position_size_pct = min(max_position_pct, max(0.0, (expected_r_net * 2.5)))
    risk_gate = position_size_pct > 0

    # === Gate 4: Regime gate (placeholder — always passes in baseline) ===
    regime_gate = True

    # === Decision ===
    all_gates = confidence_gate and cost_gate and risk_gate and regime_gate

    if all_gates:
        # Compute stop/take prices
        if direction.upper() == "SHORT":
            stop_loss = entry_price + (atr * stop_mult)
            take_profit = entry_price - (atr * target_mult)
            decision = "ENTER_SHORT"
        else:
            stop_loss = entry_price - (atr * stop_mult)
            take_profit = entry_price + (atr * target_mult)
            decision = "ENTER_LONG"

        reason = (
            f"Policy PASSED: confidence={confidence:.3f} (>={min_confidence}), "
            f"expected_r_net={expected_r_net:.4f} (>={min_expected_r}), "
            f"total_cost_r={tcr:.4f} (fee={fcr:.4f} slip={scr:.4f} fund={fund_r:.4f})"
        )
    else:
        decision = "HOLD"
        stop_loss = 0.0
        take_profit = 0.0
        position_size_pct = 0.0

        failures = []
        if not confidence_gate:
            failures.append(f"confidence {confidence:.3f} < {min_confidence}")
        if not cost_gate:
            failures.append(
                f"expected_r_net {expected_r_net:.4f} < {min_expected_r}"
            )
        if not risk_gate:
            failures.append("position_size_pct <= 0")
        reason = f"Policy REJECTED: {'; '.join(failures)}"

    return PolicyResult(
        decision=decision,
        confidence=confidence,
        expected_r=expected_r_net,
        passed=all_gates,
        gates={
            "confidence_gate": confidence_gate,
            "cost_gate": cost_gate,
            "risk_gate": risk_gate,
            "regime_gate": regime_gate,
            "overall_eligible": all_gates,
        },
        reason=reason,
        stop_loss_price=round(stop_loss, 2),
        take_profit_price=round(take_profit, 2),
        entry_price=entry_price,
        position_size_pct=round(position_size_pct, 4),
        total_cost_r=tcr,
    )


def build_decision_event(
    *,
    analysis_result: dict[str, Any],
    venue: str = "paper_trading",
    decision_event_id: str | None = None,
    order_id: str | None = None,
    position_id: str | None = None,
    event_type: str = "ORDER_PLACED",
    status: str = "SUCCESS",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a full nested DecisionEvent from a V7 AnalysisResult.

    Delegates to DecisionEventManager to produce the full contract shape
    (contract, identity, lineage, scope, request_summary, decision_summary,
    runtime_interpretation, execution_linkage, outcome_linkage, observability).

    Args:
        analysis_result: V7 AnalysisResult dict (nested contract shape).
        venue: Execution venue identifier.
        decision_event_id: Override auto-generated event ID.
        order_id: Optional exchange/broker order ID.
        position_id: Optional exchange/broker position ID.
        event_type: ORDER_PLACED, ORDER_FILLED, ORDER_REJECTED,
                    POSITION_OPENED, POSITION_CLOSED, or ERROR.
        status: SUCCESS, PARTIAL, FAILED, or PENDING.
        metadata: Optional arbitrary metadata dict.

    Returns:
        Full nested DecisionEvent dict.
    """
    from v7.lifecycle import DecisionEventManager

    manager = DecisionEventManager()
    return manager.create(
        analysis_result=analysis_result,
        venue=venue,
        decision_event_id=decision_event_id,
        event_type=event_type,
        status=status,
        order_id=order_id,
        position_id=position_id,
        metadata=metadata,
    )


