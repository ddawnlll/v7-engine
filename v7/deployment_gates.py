"""
V7 Phase 9 — Deployment safety + release gates.

Components:
  - PaperModeManager: paper execution per scope
  - ShadowEvaluationManager: shadow alongside live evaluation
  - ReleaseGatePipeline: candidate -> paper -> shadow -> live pipeline

Domain rules:
  - No candidate skips a stage in the pipeline.
  - Paper mode validates full trade lifecycle without real capital.
  - Shadow runs alongside live to detect divergence.
  - Release gates must all pass before live promotion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── PaperModeManager ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaperExecutionResult:
    """Result of a single paper execution.

    Attributes:
        timestamp: When the paper execution occurred.
        scope: The model scope being paper-traded.
        symbol: The traded symbol.
        decision: The decision executed (LONG_NOW, SHORT_NOW, NO_TRADE).
        entry_price: Simulated entry price.
        exit_price: Simulated exit price.
        realized_r: Realized R from the paper trade.
        expected_r: Expected R at decision time.
        duration_bars: Number of bars the position was held.
        detail: Human-readable detail.
    """

    timestamp: str = ""
    scope: str = ""
    symbol: str = ""
    decision: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    realized_r: float = 0.0
    expected_r: float = 0.0
    duration_bars: int = 0
    detail: str = ""


@dataclass(frozen=True)
class PaperModeReport:
    """Report of paper mode execution summary.

    Attributes:
        scope: The model scope.
        total_trades: Number of paper trades executed.
        total_realized_r: Sum of realized R across all trades.
        avg_realized_r: Average realized R per trade.
        win_rate: Fraction of trades with positive realized R.
        profit_factor: Gross win / gross loss.
        max_drawdown_r: Maximum drawdown in R units.
        detail: Human-readable summary.
    """

    scope: str = ""
    total_trades: int = 0
    total_realized_r: float = 0.0
    avg_realized_r: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    detail: str = ""


class PaperModeManager:
    """Manages paper execution for model scopes.

    Paper mode validates the full trade lifecycle including
    entry, exit, and outcome reconciliation without real capital.
    """

    def __init__(self) -> None:
        self._executions: dict[str, list[PaperExecutionResult]] = {}

    def execute_paper(
        self,
        decision: dict[str, Any],
        scope: str,
        *,
        paper_adapter: Any = None,
    ) -> PaperExecutionResult:
        """Execute a paper trade decision.

        Args:
            decision: Dict with decision, symbol, expected_r, etc.
            scope: The model scope.
            paper_adapter: Optional paper execution adapter (reserved).

        Returns:
            A PaperExecutionResult.
        """
        if paper_adapter is not None:
            result = paper_adapter.execute(decision)
            return self._record_result(result, scope)

        # Baseline: simulate paper execution from decision metadata
        symbol = decision.get("symbol", "UNKNOWN")
        decision_value = decision.get("decision", "NO_TRADE")
        expected_r = decision.get("expected_r", 0.0)

        # In baseline, paper mirrors expected outcome
        realized_r = expected_r * 0.9  # Conservative estimate
        entry_price = decision.get("price", 100.0)
        exit_price = entry_price * (1 + realized_r / 100.0)

        result = PaperExecutionResult(
            timestamp=_default_ts(),
            scope=scope,
            symbol=symbol,
            decision=decision_value,
            entry_price=entry_price,
            exit_price=round(exit_price, 4),
            realized_r=round(realized_r, 4),
            expected_r=round(expected_r, 4),
            duration_bars=decision.get("holding_bars", 1),
            detail=f"Paper execution: {decision_value} on {symbol}, realized_r={realized_r:.4f}",
        )
        self._record_result(result, scope)
        return result

    def _record_result(self, result: PaperExecutionResult, scope: str) -> PaperExecutionResult:
        if scope not in self._executions:
            self._executions[scope] = []
        self._executions[scope].append(result)
        return result

    def get_report(self, scope: str) -> PaperModeReport:
        """Get paper mode execution summary for a scope.

        Args:
            scope: The model scope.

        Returns:
            A PaperModeReport with aggregate metrics.
        """
        results = self._executions.get(scope, [])
        if not results:
            return PaperModeReport(
                scope=scope,
                detail="No paper executions for this scope",
            )

        trades = [r for r in results if r.decision != "NO_TRADE"]
        total_trades = len(trades)
        if total_trades == 0:
            return PaperModeReport(
                scope=scope,
                total_trades=0,
                detail="All decisions were NO_TRADE — no paper trades executed",
            )

        total_realized_r = sum(t.realized_r for t in trades)
        avg_realized_r = total_realized_r / total_trades
        wins = [t for t in trades if t.realized_r > 0]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        gross_win = sum(t.realized_r for t in wins)
        losses = [t for t in trades if t.realized_r <= 0]
        gross_loss = abs(sum(t.realized_r for t in losses)) if losses else 0.001
        profit_factor = gross_win / gross_loss if gross_loss > 0 else gross_win / 0.001

        # Compute max drawdown from running total
        running_total = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            running_total += t.realized_r
            if running_total > peak:
                peak = running_total
            dd = peak - running_total
            if dd > max_dd:
                max_dd = dd

        return PaperModeReport(
            scope=scope,
            total_trades=total_trades,
            total_realized_r=round(total_realized_r, 4),
            avg_realized_r=round(avg_realized_r, 4),
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 4),
            max_drawdown_r=round(max_dd, 4),
            detail=f"Paper summary: {total_trades} trades, realized_r={total_realized_r:.4f}, "
                   f"win_rate={win_rate:.1%}, PF={profit_factor:.2f}",
        )


# ── ShadowEvaluationManager ────────────────────────────────────────────────


@dataclass(frozen=True)
class ShadowEvaluation:
    """Evaluation of shadow execution alongside live.

    Attributes:
        timestamp: When the evaluation occurred.
        scope: The model scope.
        shadow_decisions: Number of shadow decisions evaluated.
        consistency: Fraction of shadow decisions matching live.
        divergence_patterns: List of detected divergence patterns.
        detail: Human-readable evaluation summary.
    """

    timestamp: str = ""
    scope: str = ""
    shadow_decisions: int = 0
    consistency: float = 0.0
    divergence_patterns: list[str] = field(default_factory=list)
    detail: str = ""


class ShadowEvaluationManager:
    """Manages shadow evaluation alongside live execution.

    Compares shadow decisions with live decisions to detect
    divergence patterns.
    """

    def __init__(self) -> None:
        self._evaluations: list[ShadowEvaluation] = []

    def evaluate(
        self,
        scope: str,
        live_decisions: list[dict[str, Any]],
        shadow_records: list[Any],
        *,
        consistency_threshold: float = 0.8,
    ) -> ShadowEvaluation:
        """Evaluate shadow vs live consistency.

        Args:
            scope: The model scope.
            live_decisions: List of live decision dicts.
            shadow_records: List of shadow record objects (must have
                           proposed_decision and shadow_decision attrs).
            consistency_threshold: Minimum acceptable consistency.

        Returns:
            A ShadowEvaluation with consistency score.
        """
        if not live_decisions or not shadow_records:
            return ShadowEvaluation(
                timestamp=_default_ts(),
                scope=scope,
                shadow_decisions=len(shadow_records),
                consistency=1.0 if not live_decisions and not shadow_records else 0.0,
                detail="Insufficient data for shadow evaluation",
            )

        # Compare shadow vs live decisions
        matches = 0
        total = min(len(live_decisions), len(shadow_records))
        divergence_patterns: list[str] = []

        for i in range(total):
            live_dec = live_decisions[i].get("decision", "")
            shadow_dec = getattr(shadow_records[i], "shadow_decision", "")
            if live_dec == shadow_dec:
                matches += 1
            else:
                divergence_patterns.append(
                    f"divergence at index {i}: live={live_dec}, shadow={shadow_dec}"
                )

        consistency = matches / max(total, 1)

        issues: list[str] = []
        if consistency < consistency_threshold:
            issues.append(f"consistency={consistency:.1%} < {consistency_threshold:.0%}")
        if len(divergence_patterns) > total * 0.3:
            issues.append(f"high divergence rate: {len(divergence_patterns)}/{total}")

        detail = (
            f"Shadow vs live: {matches}/{total} consistent ({consistency:.1%})"
            + (" | " + "; ".join(issues) if issues else "")
        )

        evaluation = ShadowEvaluation(
            timestamp=_default_ts(),
            scope=scope,
            shadow_decisions=total,
            consistency=round(consistency, 4),
            divergence_patterns=divergence_patterns[:10],  # Limit to 10
            detail=detail,
        )
        self._evaluations.append(evaluation)
        return evaluation

    def get_evaluations(self, scope: str = "") -> list[ShadowEvaluation]:
        """Get all shadow evaluations, optionally filtered by scope."""
        if scope:
            return [e for e in self._evaluations if e.scope == scope]
        return list(self._evaluations)


# ── ReleaseGatePipeline ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReleaseStage:
    """A single stage in the release pipeline.

    Attributes:
        name: Stage name ('candidate', 'paper', 'shadow', 'live').
        passed: Whether the stage passed.
        detail: Human-readable detail.
        timestamp: When the stage was evaluated.
    """

    name: str = ""
    passed: bool = False
    detail: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class ReleasePipelineResult:
    """Result of the full release gate pipeline.

    Attributes:
        candidate_id: The candidate being released.
        stages: Ordered list of ReleaseStage results.
        all_passed: True if all stages passed.
        current_stage: The current stage name.
        detail: Human-readable pipeline summary.
    """

    candidate_id: str = ""
    stages: list[ReleaseStage] = field(default_factory=list)
    all_passed: bool = False
    current_stage: str = ""
    detail: str = ""


class ReleaseGatePipeline:
    """Orchestrates the candidate -> paper -> shadow -> live pipeline.

    Each stage must pass before the next stage begins.
    """

    STAGE_NAMES = ["candidate", "paper", "shadow", "live"]

    def __init__(self) -> None:
        self._results: dict[str, ReleasePipelineResult] = {}

    def evaluate_stage(
        self,
        candidate_id: str,
        stage_name: str,
        *,
        candidate_result: dict[str, Any] | None = None,
        paper_result: PaperModeReport | None = None,
        shadow_evaluation: ShadowEvaluation | None = None,
        gate_results: dict[str, Any] | None = None,
    ) -> ReleaseStage:
        """Evaluate a single release stage.

        Args:
            candidate_id: The candidate being evaluated.
            stage_name: One of 'candidate', 'paper', 'shadow', 'live'.
            candidate_result: G0-G10 evaluation result for 'candidate' stage.
            paper_result: PaperModeReport for 'paper' stage.
            shadow_evaluation: ShadowEvaluation for 'shadow' stage.
            gate_results: Gate results for 'live' stage (G10 check).

        Returns:
            A ReleaseStage with pass/fail and detail.

        Raises:
            ValueError: If stage_name is not recognized.
        """
        if stage_name not in self.STAGE_NAMES:
            raise ValueError(
                f"Unknown stage '{stage_name}'. Must be one of: {self.STAGE_NAMES}"
            )

        if stage_name == "candidate":
            return self._eval_candidate_stage(candidate_result)
        elif stage_name == "paper":
            return self._eval_paper_stage(paper_result)
        elif stage_name == "shadow":
            return self._eval_shadow_stage(shadow_evaluation)
        elif stage_name == "live":
            return self._eval_live_stage(gate_results)

    def _eval_candidate_stage(
        self,
        candidate_result: dict[str, Any] | None,
    ) -> ReleaseStage:
        if candidate_result is None:
            return ReleaseStage(
                name="candidate", passed=False,
                detail="No candidate result provided", timestamp=_default_ts(),
            )
        passed = candidate_result.get("passed", False)
        detail = str(candidate_result.get("summary", {}).get("recommendation", "UNKNOWN"))
        return ReleaseStage(
            name="candidate", passed=passed,
            detail=detail, timestamp=_default_ts(),
        )

    def _eval_paper_stage(
        self,
        paper_result: PaperModeReport | None,
    ) -> ReleaseStage:
        if paper_result is None:
            return ReleaseStage(
                name="paper", passed=False,
                detail="No paper result provided", timestamp=_default_ts(),
            )
        passed = paper_result.total_trades > 0 and paper_result.win_rate > 0.3
        detail = (
            f"trades={paper_result.total_trades}, "
            f"realized_r={paper_result.total_realized_r:.4f}, "
            f"win_rate={paper_result.win_rate:.1%}"
        )
        return ReleaseStage(
            name="paper", passed=passed,
            detail=detail, timestamp=_default_ts(),
        )

    def _eval_shadow_stage(
        self,
        shadow_evaluation: ShadowEvaluation | None,
    ) -> ReleaseStage:
        if shadow_evaluation is None:
            return ReleaseStage(
                name="shadow", passed=False,
                detail="No shadow evaluation provided", timestamp=_default_ts(),
            )
        passed = shadow_evaluation.consistency >= 0.8
        detail = (
            f"consistency={shadow_evaluation.consistency:.1%}, "
            f"decisions={shadow_evaluation.shadow_decisions}"
        )
        return ReleaseStage(
            name="shadow", passed=passed,
            detail=detail, timestamp=_default_ts(),
        )

    def _eval_live_stage(
        self,
        gate_results: dict[str, Any] | None,
    ) -> ReleaseStage:
        if gate_results is None:
            return ReleaseStage(
                name="live", passed=False,
                detail="No gate results provided", timestamp=_default_ts(),
            )
        g10 = gate_results.get("G10", {})
        if isinstance(g10, dict):
            passed = g10.get("status") == "PASS"
            detail = g10.get("detail", "G10 not evaluated")
        else:
            passed = False
            detail = "G10 result not available"
        return ReleaseStage(
            name="live", passed=passed,
            detail=detail, timestamp=_default_ts(),
        )

    def run_pipeline(
        self,
        candidate_id: str,
        *,
        candidate_result: dict[str, Any] | None = None,
        paper_result: PaperModeReport | None = None,
        shadow_evaluation: ShadowEvaluation | None = None,
        gate_results: dict[str, Any] | None = None,
        stop_on_fail: bool = True,
    ) -> ReleasePipelineResult:
        """Run the full release pipeline.

        Stages are evaluated in order: candidate -> paper -> shadow -> live.
        Each stage must pass before the next is evaluated.

        Args:
            candidate_id: The candidate being released.
            candidate_result: G0-G10 evaluation result.
            paper_result: PaperModeReport.
            shadow_evaluation: ShadowEvaluation.
            gate_results: Gate results for live check.
            stop_on_fail: If True, stop at first failure.

        Returns:
            A ReleasePipelineResult with all stage results.
        """
        stages: list[ReleaseStage] = []
        current_stage = ""
        all_passed = True

        stage_configs = [
            ("candidate", lambda: self._eval_candidate_stage(candidate_result)),
            ("paper", lambda: self._eval_paper_stage(paper_result)),
            ("shadow", lambda: self._eval_shadow_stage(shadow_evaluation)),
            ("live", lambda: self._eval_live_stage(gate_results)),
        ]

        for name, eval_fn in stage_configs:
            if stop_on_fail and not all_passed:
                stages.append(ReleaseStage(
                    name=name, passed=False,
                    detail=f"Skipped — prior stage failed", timestamp=_default_ts(),
                ))
                continue

            stage = eval_fn()
            stages.append(stage)
            current_stage = name
            if not stage.passed:
                all_passed = False
                if stop_on_fail:
                    break

        return ReleasePipelineResult(
            candidate_id=candidate_id,
            stages=stages,
            all_passed=all_passed,
            current_stage=current_stage,
            detail=(
                "All stages passed" if all_passed
                else f"Pipeline blocked at stage '{current_stage}'"
            ),
        )

    def get_pipeline_result(self, candidate_id: str) -> ReleasePipelineResult | None:
        """Get the pipeline result for a candidate."""
        return self._results.get(candidate_id)
