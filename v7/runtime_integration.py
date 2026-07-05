"""
V7PipelineExecutor — wires the full V7 runtime pipeline.

Integration flow (per v7/docs/runtime/runtime_integration.md):
  1. Request Builder            -> AnalysisRequest
  2. Mode Router                -> RouteResult
  3. Result Validation          -> error list
  4. Policy Evaluation          -> PolicyResult
  5. Execution Eligibility      -> EligibilityResult
  6. Event Materialization      -> DecisionEvent
  7. Outcome Attachment         -> TradeOutcome

Domain boundaries preserved:
  - v7/builder.py       owns request construction
  - v7/router.py        owns mode dispatch
  - v7/policy.py        owns policy acceptance
  - v7/validator.py     owns result validation
  - v7/lifecycle.py     owns event/outcome lifecycle
  - v7/mappings.py      owns cross-domain field mapping
  - simulation/adapters owns simulation execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from v7.builder import build_analysis_request, validate_analysis_request

# ── Internal helpers ─────────────────────────────────────────────────


def _ensure_mode_at_top(request: dict) -> None:
    """Ensure ``mode`` key exists at the top level of *request*.

    ``build_analysis_request`` places the trading mode in
    ``scope.requested_trade_mode``. The router and other consumers expect
    a top-level ``mode`` key.  This helper bridges transparently so caller
    code doesn't need to know the internal key layout.
    """
    if "mode" not in request or not request["mode"]:
        scope_mode = request.get("scope", {}).get("requested_trade_mode", "")
        if scope_mode:
            request["mode"] = scope_mode
from v7.lifecycle import DecisionEventManager, TradeOutcomeManager
from v7.mappings import CrossDomainMapper
from v7.policy import PolicyResult, evaluate_policy
from v7.router import (
    LOCKED_INITIAL_BASELINE,
    RouteResult,
    get_mode_profile,
    route_request,
)
from v7.validator import validate_analysis_result, validate_result_against_request


# =========================================================================
# EligibilityResult (basic — used when full EligibilityStack isn't available)
# =========================================================================


@dataclass(frozen=True)
class EligibilityResult:
    """Result of execution eligibility checks.

    Attributes:
        passed: True if all eligibility gates pass.
        gates: Per-gate pass/fail detail.
        reason: Human-readable explanation.
    """

    passed: bool
    gates: dict[str, bool] = field(default_factory=dict)
    reason: str = ""


# =========================================================================
# V7PipelineExecutor
# =========================================================================


class V7PipelineExecutor:
    """Orchestrates the full V7 runtime pipeline end-to-end.

    Each step wraps a dedicated V7 module (builder, router, policy, lifecycle)
    with consistent error handling and return types.

    Usage::

        executor = V7PipelineExecutor()
        result = executor.run_full_pipeline(
            raw_input={
                "mode": "SWING",
                "symbol": "BTCUSDT",
                "model_scope": "swing_v1",
            },
            analysis_result=analysis_result,
            atr=245.0,
            notional=10000.0,
        )
    """

    def __init__(
        self,
        event_manager: DecisionEventManager | None = None,
        outcome_manager: TradeOutcomeManager | None = None,
        mapper: CrossDomainMapper | None = None,
    ) -> None:
        self._event_manager = event_manager or DecisionEventManager()
        self._outcome_manager = outcome_manager or TradeOutcomeManager()
        self._mapper = mapper or CrossDomainMapper()

    # ------------------------------------------------------------------
    # Step 1: Request execution
    # ------------------------------------------------------------------

    def execute_request(self, raw_input: dict) -> dict:
        """Build a contract-valid AnalysisRequest from *raw_input*.

        Args:
            raw_input: Keyword arguments for
                       ``v7.builder.build_analysis_request()``.
                       At minimum must contain ``mode``, ``symbol``,
                       and ``model_scope``.

        Returns:
            A validated AnalysisRequest dict.

        Raises:
            ValueError: If required fields are missing.
        """
        return build_analysis_request(**raw_input)

    # ------------------------------------------------------------------
    # Step 2: Route and validate
    # ------------------------------------------------------------------

    def route_and_validate(self, request: dict) -> RouteResult:
        """Route the request through the mode router with scope validation.

        Wraps ``v7.router.route_request`` with ``validate_scope=True``.
        The ``route_request`` function expects ``mode`` at the top level of
        the request dict, but ``build_analysis_request`` places
        ``requested_trade_mode`` under ``scope``. We bridge that here so
        callers are not required to know about the internal key layout.

        Args:
            request: A validated AnalysisRequest dict (built by
                     ``build_analysis_request`` or equivalent form).

        Returns:
            RouteResult indicating whether the mode is allowed.
        """
        # Bridge the scope.requested_trade_mode to top-level mode key
        _ensure_mode_at_top(request)
        return route_request(request, validate_scope=True)

    # ------------------------------------------------------------------
    # Step 3: Result cross-validation
    # ------------------------------------------------------------------

    def validate_result(
        self,
        request: dict,
        result: dict,
    ) -> list[str]:
        """Cross-validate an AnalysisResult against its originating request.

        Runs both ``validate_analysis_result`` for structural validity and
        ``validate_result_against_request`` for request linkage consistency.

        Args:
            request: The originating AnalysisRequest dict.
            result: The AnalysisResult dict to validate.

        Returns:
            List of validation error messages (empty = valid).
        """
        errors = validate_analysis_result(result)
        if errors:
            return errors
        return validate_result_against_request(result, request)

    # ------------------------------------------------------------------
    # Step 4: Policy evaluation
    # ------------------------------------------------------------------

    def evaluate_policy(
        self,
        request: dict,
        result: dict,
        atr: float = 0.0,
        notional: float = 10000.0,
        taker_fee_bps: float = 4.0,
        slippage_bps: float = 1.0,
        funding_rate: float = 0.0,
        holding_bars: int = 0,
    ) -> PolicyResult:
        """Evaluate policy gates against the engine's AnalysisResult.

        Extracts confidence, expected R, entry price, and direction from
        the AnalysisResult and passes them through ``policy.evaluate_policy``.
        Market data (ATR, notional) is accepted as explicit parameters since
        it is not modelled in the AnalysisRequest contract.

        Args:
            request: The originating AnalysisRequest dict.
            result:  The AnalysisResult dict from the engine.
            atr: Current ATR value (required for cost computation).
            notional: Notional position value in quote currency.
            taker_fee_bps: Fee in basis points.
            slippage_bps: Slippage in basis points.
            funding_rate: Per-bar funding rate.
            holding_bars: Expected holding bars for funding cost.

        Returns:
            PolicyResult with gate status and decision.
        """
        scores = result.get("scores", {})
        decision = result.get("decision", {})
        guidance = result.get("execution_guidance", {})

        confidence = scores.get("confidence", 0.0)
        expected_r_gross = scores.get("expected_r", 0.0)
        entry_price = guidance.get("entry_price", 0.0)
        direction = decision.get("direction", "LONG")

        return evaluate_policy(
            request=request,
            confidence=confidence,
            expected_r_gross=expected_r_gross,
            entry_price=entry_price,
            atr=atr,
            notional=notional,
            direction=direction,
            taker_fee_bps=taker_fee_bps,
            slippage_bps=slippage_bps,
            funding_rate=funding_rate,
            holding_bars=holding_bars,
        )

    # ------------------------------------------------------------------
    # Step 5: Execution eligibility
    # ------------------------------------------------------------------

    def check_eligibility(
        self,
        request: dict,
        context: dict | None = None,
    ) -> EligibilityResult:
        """Check basic execution eligibility for the request.

        Since the full ``EligibilityStack`` (Issue #39) is not yet
        implemented, this performs a minimal mode-lock gate:
          - If the requested mode is LOCKED_INITIAL_BASELINE, eligibility
            passes at the basic level.
          - If the mode is HOLD, eligibility is denied with the hold reason.

        Args:
            request: The AnalysisRequest dict.
            context: Optional additional context dict for future gates
                     (exchange availability, cooldowns, etc.). Currently
                     unused but reserved for forward compatibility.

        Returns:
            EligibilityResult with gate status.
        """
        _ensure_mode_at_top(request)
        mode = request.get("mode", request.get("requested_trade_mode", ""))
        if not mode:
            return EligibilityResult(
                passed=False,
                gates={"structural_valid": False},
                reason="No trade mode found in request",
            )

        try:
            profile = get_mode_profile(mode)
        except ValueError:
            return EligibilityResult(
                passed=False,
                gates={"mode_lock": False},
                reason=f"Unknown mode '{mode}'",
            )

        status = profile.get("status", "HOLD")
        if status != LOCKED_INITIAL_BASELINE:
            return EligibilityResult(
                passed=False,
                gates={"mode_lock": False},
                reason=profile.get(
                    "hold_reason", f"Mode '{mode}' is on HOLD"
                ),
            )

        return EligibilityResult(
            passed=True,
            gates={
                "mode_lock": True,
                "structural_valid": True,
            },
            reason="Basic eligibility checks passed",
        )

    # ------------------------------------------------------------------
    # Step 6: DecisionEvent materialization
    # ------------------------------------------------------------------

    def materialize_event(
        self,
        request: dict,
        result: dict,
        venue: str = "paper_trading",
        **kwargs: Any,
    ) -> dict:
        """Create a full nested DecisionEvent from request + result.

        Delegates to ``DecisionEventManager.create()``.

        Args:
            request: The originating AnalysisRequest dict.
            result:  The AnalysisResult dict.
            venue:   Execution venue identifier.
            **kwargs: Additional keyword arguments forwarded to
                      ``DecisionEventManager.create()``.

        Returns:
            Full nested DecisionEvent dict.
        """
        return self._event_manager.create(
            analysis_result=result,
            venue=venue,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Step 7: TradeOutcome attachment
    # ------------------------------------------------------------------

    def attach_outcome(
        self,
        event: dict,
        sim_output: dict | None = None,
        outcome_source: str = "PAPER_EXECUTION",
        execution_path: str = "PAPER_EXECUTED",
        **kwargs: Any,
    ) -> dict:
        """Create a TradeOutcome from a DecisionEvent + optional sim output.

        Args:
            event: A DecisionEvent dict (full nested shape).
            sim_output: Optional SimulationOutput dict from the simulation
                        engine. If provided, it is mapped to the outcome's
                        realized_outcome section via CrossDomainMapper.
            outcome_source: Source of outcome truth.
            execution_path: How decision was executed.
            **kwargs: Additional keyword arguments forwarded to
                      ``TradeOutcomeManager.create()``.

        Returns:
            Full nested TradeOutcome dict.
        """
        # Map simulation output to realized outcome if provided
        realized_outcome = None
        path_metrics = None
        comparative_outcome = None

        if sim_output is not None:
            mapped = self._mapper.map_simulation_to_v7(sim_output)
            realized_outcome = mapped.get("realized_outcome")
            path_metrics = mapped.get("path_metrics")
            comparative_outcome = mapped.get("comparative_outcome")

        outcome = self._outcome_manager.create(
            decision_event=event,
            outcome_source=outcome_source,
            execution_path=execution_path,
            realized_outcome=realized_outcome,
            path_metrics=path_metrics,
            comparative_outcome=comparative_outcome,
            **kwargs,
        )

        # Link the outcome back to the event
        event_id = event.get("identity", {}).get("decision_event_id")
        outcome_id = outcome.get("identity", {}).get("trade_outcome_id")
        if event_id and outcome_id:
            self._event_manager.update(
                event_id,
                trade_outcome_id=outcome_id,
                outcome_status="PENDING",
            )

        return outcome

    # ------------------------------------------------------------------
    # Full pipeline orchestration
    # ------------------------------------------------------------------

    def run_full_pipeline(
        self,
        raw_input: dict,
        analysis_result: dict,
        atr: float = 0.0,
        notional: float = 10000.0,
        sim_output: dict | None = None,
        venue: str = "paper_trading",
        context: dict | None = None,
        eligibility_context: dict | None = None,
        outcome_source: str = "PAPER_EXECUTION",
        execution_path: str = "PAPER_EXECUTED",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the full V7 runtime pipeline and return all artifacts.

        This is the primary orchestration entrypoint. It runs all seven
        pipeline steps in order and returns a dict with every artifact
        so the caller can inspect, persist, or log each stage.

        Args:
            raw_input: Keyword arguments for
                       ``v7.builder.build_analysis_request()``.
            analysis_result: The AnalysisResult dict from the engine.
            atr: Current ATR value for cost computation.
            notional: Notional position value.
            sim_output: Optional SimulationOutput for outcome attachment.
            venue: Execution venue identifier.
            context: Optional context dict (reserved, currently unused).
            eligibility_context: Optional context for eligibility checks.
            outcome_source: Source of outcome truth.
            execution_path: How the decision was executed.
            **kwargs: Additional keyword arguments forwarded to
                      ``materialize_event`` and ``attach_outcome``.

        Returns:
            Dict with keys:
              - request: AnalysisRequest dict
              - route_result: RouteResult dataclass
              - validation_errors: list of error strings
              - policy_result: PolicyResult dataclass
              - eligibility_result: EligibilityResult dataclass
              - decision_event: DecisionEvent dict
              - trade_outcome: TradeOutcome dict (or None if event creation
                               was not possible)
        """
        # Step 1: Build request
        request = self.execute_request(raw_input)

        # Step 2: Route and validate
        route_result = self.route_and_validate(request)

        # Step 3: Cross-validate result
        validation_errors = self.validate_result(request, analysis_result)

        # Step 4: Evaluate policy
        policy_result = self.evaluate_policy(
            request=request,
            result=analysis_result,
            atr=atr,
            notional=notional,
        )

        # Step 5: Check eligibility
        eligibility_result = self.check_eligibility(
            request=request,
            context=eligibility_context,
        )

        # Step 6: Materialize event
        decision_event = self.materialize_event(
            request=request,
            result=analysis_result,
            venue=venue,
        )

        # Step 7: Attach outcome
        trade_outcome = None
        if sim_output is not None:
            trade_outcome = self.attach_outcome(
                event=decision_event,
                sim_output=sim_output,
                outcome_source=outcome_source,
                execution_path=execution_path,
            )

        return {
            "request": request,
            "route_result": route_result,
            "validation_errors": validation_errors,
            "policy_result": policy_result,
            "eligibility_result": eligibility_result,
            "decision_event": decision_event,
            "trade_outcome": trade_outcome,
        }
