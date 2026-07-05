"""
No-trade behavior validation — detect no-trade patterns, compare to baseline,
and analyze false no-trade decisions.

Domain rules:
- A model that avoids all trades may look safe but is not automatically good.
- No-trade quality measures: correct skip, saved loss, missed opportunity,
  over-suppression, under-suppression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class NoTradeReport:
    """Report of no-trade behavior analysis.

    Attributes:
        timestamp: When the analysis was performed.
        total_decisions: Total number of decision events analyzed.
        no_trade_count: Count of NO_TRADE decisions.
        no_trade_rate: Fraction of decisions that were NO_TRADE.
        correct_no_trades: Count of NO_TRADE decisions that avoided a loss.
        saved_loss_r: Total R saved by correct no-trades.
        missed_opportunities: Count of NO_TRADE decisions that missed a gain.
        missed_opportunity_r: Total R missed by incorrect no-trades.
        over_suppression: Count of NO_TRADE decisions where decision model
                          was too conservative relative to signal.
        under_suppression: Count of NO_TRADE decisions that should have
                           been NO_TRADE but weren't (false positives).
        patterns: Dict of detected pattern names to their severity.
        metrics: Dict of computed metrics (rates, ratios).
    """

    timestamp: str = ""
    total_decisions: int = 0
    no_trade_count: int = 0
    no_trade_rate: float = 0.0
    correct_no_trades: int = 0
    saved_loss_r: float = 0.0
    missed_opportunities: int = 0
    missed_opportunity_r: float = 0.0
    over_suppression: int = 0
    under_suppression: int = 0
    patterns: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class NoTradeDelta:
    """Delta between two no-trade reports (current vs baseline)."""

    no_trade_rate_delta: float = 0.0
    correct_rate_delta: float = 0.0
    saved_loss_r_delta: float = 0.0
    missed_opportunity_r_delta: float = 0.0
    over_suppression_delta: int = 0
    under_suppression_delta: int = 0
    significant: bool = False
    detail: str = ""


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_no_trade_patterns(decisions: list[dict[str, Any]]) -> NoTradeReport:
    """Detect no-trade patterns from a list of decision events.

    Each decision dict should contain:
      - decision: str — "LONG_NOW", "SHORT_NOW", or "NO_TRADE"
      - outcome_r: float — realized R (positive=win, negative=loss)
      - expected_r: float — expected R at decision time
      - confidence: float — model confidence (0-1)

    Args:
        decisions: List of decision event dicts.

    Returns:
        A NoTradeReport with detected patterns and metrics.
    """
    if not decisions:
        return NoTradeReport(
            timestamp=_default_ts(),
            total_decisions=0,
            metrics={"no_trade_rate": 0.0, "correct_no_trade_rate": 0.0},
        )

    total = len(decisions)
    no_trade_decisions = [d for d in decisions if d.get("decision") == "NO_TRADE"]
    no_trade_count = len(no_trade_decisions)
    no_trade_rate = no_trade_count / total if total > 0 else 0.0

    # Analyze each no-trade decision
    correct_no_trades = 0
    saved_loss_r = 0.0
    missed_opportunities = 0
    missed_opportunity_r = 0.0

    for d in no_trade_decisions:
        outcome_r = d.get("outcome_r", 0.0)
        expected_r = d.get("expected_r", 0.0)

        # A correct no-trade is one where the outcome would have been negative
        if outcome_r < 0:
            correct_no_trades += 1
            saved_loss_r += abs(outcome_r)
        elif outcome_r > 0:
            # Missed opportunity: NO_TRADE when the outcome was positive
            missed_opportunities += 1
            missed_opportunity_r += outcome_r

    # Detect over-suppression: NO_TRADE when expected_r was strongly positive
    over_suppression = sum(
        1 for d in no_trade_decisions
        if d.get("expected_r", 0) > 0.5 and d.get("decision") == "NO_TRADE"
    )

    # Detect under-suppression: LONG/SHORT when outcome_r was strongly negative
    non_no_trade = [d for d in decisions if d.get("decision") in ("LONG_NOW", "SHORT_NOW")]
    under_suppression = sum(
        1 for d in non_no_trade
        if d.get("outcome_r", 0) < -1.0
    )

    # Build pattern detections
    patterns: dict[str, str] = {}
    if no_trade_rate > 0.7:
        patterns["excessive_no_trade"] = (
            f"HIGH: no_trade_rate={no_trade_rate:.1%} > 70% — model may be overly cautious"
        )
    elif no_trade_rate > 0.5:
        patterns["elevated_no_trade"] = (
            f"MODERATE: no_trade_rate={no_trade_rate:.1%} above 50% — review suppression causes"
        )

    correct_rate = correct_no_trades / max(no_trade_count, 1)
    if correct_rate < 0.4:
        patterns["low_correct_rate"] = (
            f"HIGH: correct_no_trade_rate={correct_rate:.1%} < 40% — most no-trades miss opportunities"
        )

    if missed_opportunity_r > saved_loss_r * 1.5 and saved_loss_r > 0:
        patterns["net_harmful_avoidance"] = (
            f"HIGH: missed_opportunity_r ({missed_opportunity_r:.2f}) > 1.5× "
            f"saved_loss_r ({saved_loss_r:.2f}) — no-trade avoidance destroys value"
        )

    if over_suppression > no_trade_count * 0.3:
        patterns["over_suppression"] = (
            f"HIGH: {over_suppression}/{no_trade_count} no-trades had strong positive expected R"
        )

    metrics: dict[str, float] = {
        "no_trade_rate": round(no_trade_rate, 4),
        "correct_no_trade_rate": round(correct_rate, 4),
        "avg_saved_loss_r": round(saved_loss_r / max(correct_no_trades, 1), 4),
        "avg_missed_opportunity_r": round(missed_opportunity_r / max(missed_opportunities, 1), 4),
        "saved_vs_missed_ratio": round(
            saved_loss_r / max(missed_opportunity_r, 0.001), 4
        ),
    }

    return NoTradeReport(
        timestamp=_default_ts(),
        total_decisions=total,
        no_trade_count=no_trade_count,
        no_trade_rate=round(no_trade_rate, 4),
        correct_no_trades=correct_no_trades,
        saved_loss_r=round(saved_loss_r, 4),
        missed_opportunities=missed_opportunities,
        missed_opportunity_r=round(missed_opportunity_r, 4),
        over_suppression=over_suppression,
        under_suppression=under_suppression,
        patterns=patterns,
        metrics=metrics,
    )


def compare_to_baseline(
    report: NoTradeReport,
    baseline: NoTradeReport,
    *,
    threshold: float = 0.1,
) -> NoTradeDelta:
    """Compare a no-trade report to a baseline report.

    Args:
        report: Current no-trade report.
        baseline: Baseline no-trade report to compare against.
        threshold: Significant change threshold for no_trade_rate (default 0.1).

    Returns:
        A NoTradeDelta with deltas and significance flag.
    """
    no_trade_rate_delta = report.no_trade_rate - baseline.no_trade_rate

    report_correct_rate = report.metrics.get("correct_no_trade_rate", 0.0)
    baseline_correct_rate = baseline.metrics.get("correct_no_trade_rate", 0.0)
    correct_rate_delta = report_correct_rate - baseline_correct_rate

    saved_loss_r_delta = report.saved_loss_r - baseline.saved_loss_r
    missed_opportunity_r_delta = report.missed_opportunity_r - baseline.missed_opportunity_r
    over_suppression_delta = report.over_suppression - baseline.over_suppression
    under_suppression_delta = report.under_suppression - baseline.under_suppression

    significant = abs(no_trade_rate_delta) > threshold
    detail_parts: list[str] = []
    if abs(no_trade_rate_delta) > threshold:
        direction = "increase" if no_trade_rate_delta > 0 else "decrease"
        detail_parts.append(f"no_trade_rate {direction} by {abs(no_trade_rate_delta):.1%}")
    if abs(correct_rate_delta) > threshold:
        direction = "improvement" if correct_rate_delta > 0 else "degradation"
        detail_parts.append(f"correct_rate {direction} of {abs(correct_rate_delta):.1%}")

    return NoTradeDelta(
        no_trade_rate_delta=round(no_trade_rate_delta, 4),
        correct_rate_delta=round(correct_rate_delta, 4),
        saved_loss_r_delta=round(saved_loss_r_delta, 4),
        missed_opportunity_r_delta=round(missed_opportunity_r_delta, 4),
        over_suppression_delta=over_suppression_delta,
        under_suppression_delta=under_suppression_delta,
        significant=significant,
        detail="; ".join(detail_parts) if detail_parts else "No significant changes",
    )


def analyze_false_no_trades(
    decisions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze false no-trade decisions against realized outcomes.

    A false no-trade is a NO_TRADE decision where the outcome was actually
    profitable (missed opportunity). This function cross-references decisions
    with their realized outcomes.

    Args:
        decisions: List of decision event dicts (must have timestamp/event_id).
        outcomes: List of outcome event dicts (must have timestamp/event_id).

    Returns:
        Dict with false_no_trade analysis: count, rate, total_missed_r,
        patterns, and per-decision breakdown.
    """
    # Index outcomes by event_id for fast lookup
    outcome_by_id: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        eid = o.get("event_id", "")
        if eid:
            outcome_by_id[eid] = o

    false_no_trades: list[dict[str, Any]] = []
    total_no_trades = 0
    total_missed_r = 0.0

    for d in decisions:
        if d.get("decision") != "NO_TRADE":
            continue
        total_no_trades += 1

        eid = d.get("event_id", "")
        outcome = outcome_by_id.get(eid, {})
        outcome_r = outcome.get("outcome_r") or d.get("outcome_r", 0.0)

        if outcome_r > 0:
            false_no_trades.append({
                "event_id": eid,
                "expected_r": d.get("expected_r", 0.0),
                "outcome_r": outcome_r,
                "missed_r": outcome_r,
                "confidence": d.get("confidence", 0.0),
            })
            total_missed_r += outcome_r

    # Compute aggregate patterns
    false_rate = len(false_no_trades) / max(total_no_trades, 1)

    patterns: dict[str, str] = {}
    if false_rate > 0.5:
        patterns["high_false_no_trade_rate"] = (
            f"HIGH: {false_rate:.1%} of no-trades were false (missed opportunities)"
        )
    if total_missed_r > 10.0:
        patterns["large_missed_pnl"] = (
            f"HIGH: total missed R={total_missed_r:.2f}"
        )

    return {
        "total_no_trades": total_no_trades,
        "false_no_trade_count": len(false_no_trades),
        "false_no_trade_rate": round(false_rate, 4),
        "total_missed_r": round(total_missed_r, 4),
        "avg_missed_r": round(total_missed_r / max(len(false_no_trades), 1), 4),
        "patterns": patterns,
        "false_no_trades": false_no_trades[:20],  # Limit to 20 entries
    }
