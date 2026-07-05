"""
Paper/Replay Evaluation Mode — Issues #19 & #20.

Provides:
  - PaperMode:    single-scenario paper forward simulation with no-trade validation
  - ReplayMode:   multi-scenario historical replay with batch outcome collection
  - EvaluationDriver: combined paper + replay evaluation report

Each mode wraps a ``simulation/adapters`` driver and produces V7 contract-family
outputs (DecisionEvent, TradeOutcome) via the lifecycle managers.

Usage::

    from v7.evaluation import EvaluationDriver

    driver = EvaluationDriver()
    report = driver.run_evaluation(
        symbol="BTCUSDT",
        mode="SWING",
        model_scope="swing_v1",
        paper_sim_input=sim_input,
        replay_sim_inputs=[sim_input_1, sim_input_2],
    )
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from simulation.adapters import PaperDriver, ReplayDriver
from simulation.contracts.models import SimulationInput
from v7.builder import build_analysis_request
from v7.lifecycle import DecisionEventManager, TradeOutcomeManager
from v7.mappings import CrossDomainMapper
from v7.validator import build_analysis_result


# =========================================================================
# Helpers
# =========================================================================


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================================
# PaperMode
# =========================================================================


class PaperMode:
    """Single-scenario paper forward simulation.

    Runs one ``SimulationInput`` through ``PaperDriver`` and produces a
    single ``DecisionEvent`` and ``TradeOutcome``.
    """

    def __init__(
        self,
        paper_driver: PaperDriver | None = None,
        event_manager: DecisionEventManager | None = None,
        outcome_manager: TradeOutcomeManager | None = None,
        mapper: CrossDomainMapper | None = None,
    ) -> None:
        self._driver = paper_driver or PaperDriver()
        self._event_manager = event_manager or DecisionEventManager()
        self._outcome_manager = outcome_manager or TradeOutcomeManager()
        self._mapper = mapper or CrossDomainMapper()

    def run(
        self,
        symbol: str,
        mode: str,
        model_scope: str,
        sim_input: SimulationInput,
        analysis_result: dict | None = None,
        request_kind: str = "paper_scan",
        venue: str = "paper_trading",
        outcome_source: str = "PAPER_EXECUTION",
        execution_path: str = "PAPER_EXECUTED",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a paper simulation and produce lifecycle artifacts.

        Args:
            symbol: Trading symbol (e.g. 'BTCUSDT').
            mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
            model_scope: Model scope identifier (e.g. 'swing_v1').
            sim_input: SimulationInput for the paper run.
            analysis_result: Optional pre-built AnalysisResult dict.
                             If omitted, a minimal result is auto-built from
                             the simulation output.
            request_kind: Request kind for the AnalysisRequest.
            venue: Execution venue identifier.
            outcome_source: Source label for the TradeOutcome.
            execution_path: Execution path label.
            **kwargs: Forwarded to ``DecisionEventManager.create()``.

        Returns:
            Dict with keys:
              - request:         AnalysisRequest dict
              - sim_output:      SimulationOutput from PaperDriver
              - decision_event:  DecisionEvent dict
              - trade_outcome:   TradeOutcome dict
              - no_trade_validation: no-trade comparison dict
        """
        # Build a minimal AnalysisRequest for metadata
        request = build_analysis_request(
            mode=mode,
            symbol=symbol,
            model_scope=model_scope,
            request_kind=request_kind,
            analysis_mode="paper",
            caller="paper_scan",
        )

        # Run the paper simulation
        sim_output = self._driver.run(sim_input)

        # Build or accept an AnalysisResult
        resolved_result = analysis_result
        if resolved_result is None:
            resolved_result = self._build_minimal_result(
                request=request,
                sim_output=sim_output,
                model_scope=model_scope,
                trade_mode=mode,
            )

        # Create DecisionEvent
        decision_event = self._event_manager.create(
            analysis_result=resolved_result,
            venue=venue,
            **kwargs,
        )

        # Map simulation output to outcome
        mapped = self._mapper.map_simulation_to_v7(sim_output)

        # Create TradeOutcome
        trade_outcome = self._outcome_manager.create(
            decision_event=decision_event,
            outcome_source=outcome_source,
            execution_path=execution_path,
            realized_outcome=mapped.get("realized_outcome"),
            path_metrics=mapped.get("path_metrics"),
            comparative_outcome=mapped.get("comparative_outcome"),
        )

        # Link outcome to event
        event_id = decision_event.get("identity", {}).get("decision_event_id")
        outcome_id = trade_outcome.get("identity", {}).get("trade_outcome_id")
        if event_id and outcome_id:
            self._event_manager.update(
                event_id,
                trade_outcome_id=outcome_id,
                outcome_status="PENDING",
            )

        # No-trade validation: compare expected vs actual
        no_trade_validation = self._validate_no_trade(
            analysis_result=resolved_result,
            sim_output=sim_output,
        )

        return {
            "request": request,
            "sim_output": sim_output,
            "decision_event": decision_event,
            "trade_outcome": trade_outcome,
            "no_trade_validation": no_trade_validation,
        }

    @staticmethod
    def _normalize_action(action: str) -> str:
        """Map a simulation best_action to a valid AnalysisResult action.

        ``AMBIGUOUS_STATE`` is a valid simulation resolution but not an
        allowed ``recommended_action`` in the AnalysisResult contract.
        We normalise it to ``NO_TRADE`` since ambiguity means no clear
        directional edge.
        """
        _VALID = frozenset({"LONG_NOW", "SHORT_NOW", "NO_TRADE"})
        if action in _VALID:
            return action
        return "NO_TRADE"

    def _build_minimal_result(
        self,
        request: dict,
        sim_output: Any,
        model_scope: str,
        trade_mode: str,
    ) -> dict:
        """Build a minimal AnalysisResult from a SimulationOutput."""
        best_action = sim_output.best_action if hasattr(sim_output, "best_action") else "NO_TRADE"
        normalized = self._normalize_action(best_action)
        request_id = request.get("identity", {}).get("request_id", "unknown")
        symbol = request.get("scope", {}).get("symbol", "UNKNOWN")
        primary_interval = request.get("scope", {}).get("primary_interval", "unknown")

        return build_analysis_result(
            request_id=request_id,
            recommended_action=normalized,
            model_scope=model_scope,
            trade_mode=trade_mode,
            request_link={
                "symbol": symbol,
                "model_scope": model_scope,
                "trade_mode": trade_mode,
                "primary_interval": primary_interval,
            },
        )

    def _validate_no_trade(
        self,
        analysis_result: dict,
        sim_output: Any,
    ) -> dict[str, Any]:
        """Validate no-trade behaviour: expected vs actual.

        Compares what the engine recommended (from AnalysisResult) against
        what the paper simulation determined would have been optimal.
        """
        engine_action = (
            analysis_result.get("decision", {})
            .get("recommended_action", "NO_TRADE")
        )
        sim_best_action = (
            sim_output.best_action if hasattr(sim_output, "best_action") else "UNKNOWN"
        )

        expected_no_trade = engine_action == "NO_TRADE"
        actual_no_trade = sim_best_action == "NO_TRADE"

        return {
            "engine_recommended_action": engine_action,
            "simulation_best_action": sim_best_action,
            "expected_no_trade": expected_no_trade,
            "actual_no_trade": actual_no_trade,
            "match": (
                "MATCH" if engine_action == sim_best_action
                else "MISMATCH"
            ),
        }


# =========================================================================
# ReplayMode
# =========================================================================


@dataclass
class ReplaySummary:
    """Aggregate summary statistics for a replay evaluation batch.

    Attributes:
        count: Number of replay runs.
        no_trade_count: Number of runs that resulted in NO_TRADE.
        trade_count: Number of runs that resulted in a directional trade.
        no_trade_rate: Fraction of runs that were NO_TRADE.
        avg_r: Mean realized R across all runs.
        median_r: Median realized R across all runs.
        std_r: Standard deviation of realized R.
        avg_fee_cost_r: Mean fee cost in R.
        avg_slippage_cost_r: Mean slippage cost in R.
        total_cost_r: Mean total cost in R.
        win_rate: Fraction of trades with positive realized R.
        avg_hold_bars: Mean hold duration in bars.
    """

    count: int = 0
    no_trade_count: int = 0
    trade_count: int = 0
    no_trade_rate: float = 0.0
    avg_r: float = 0.0
    median_r: float = 0.0
    std_r: float = 0.0
    avg_fee_cost_r: float = 0.0
    avg_slippage_cost_r: float = 0.0
    total_cost_r: float = 0.0
    win_rate: float = 0.0
    avg_hold_bars: float = 0.0


class ReplayMode:
    """Multi-scenario historical replay evaluation.

    Runs multiple ``SimulationInput`` objects through ``ReplayDriver``,
    collects ``TradeOutcome`` for each, and produces aggregate summary
    statistics.
    """

    def __init__(
        self,
        replay_driver: ReplayDriver | None = None,
        outcome_manager: TradeOutcomeManager | None = None,
        mapper: CrossDomainMapper | None = None,
    ) -> None:
        self._driver = replay_driver or ReplayDriver()
        self._outcome_manager = outcome_manager or TradeOutcomeManager()
        self._mapper = mapper or CrossDomainMapper()

    def run(
        self,
        symbol: str,
        mode: str,
        model_scope: str,
        sim_inputs: list[SimulationInput],
        request_kind: str = "replay_eval",
        outcome_source: str = "REPLAY_PROJECTION",
        execution_path: str = "REPLAY_ONLY",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run replay over multiple simulation inputs.

        Args:
            symbol: Trading symbol.
            mode: Trading mode.
            model_scope: Model scope identifier.
            sim_inputs: List of SimulationInput objects to replay.
            request_kind: Request kind for the AnalysisRequest.
            outcome_source: Source label for each TradeOutcome.
            execution_path: Execution path label for each TradeOutcome.
            **kwargs: Forwarded to ``TradeOutcomeManager.create()``.

        Returns:
            Dict with keys:
              - outcomes: list of TradeOutcome dicts
              - summary: ReplaySummary dataclass
              - no_trade_analysis: aggregate no-trade comparison dict
        """
        outcomes: list[dict] = []
        realized_r_values: list[float] = []
        fee_costs: list[float] = []
        slippage_costs: list[float] = []
        total_costs: list[float] = []
        hold_bars: list[int] = []
        no_trade_count = 0
        wins = 0

        for sim_input in sim_inputs:
            # Run the replay simulation
            sim_output = self._driver.run(sim_input)

            # Build a minimal event-like structure for outcome creation.
            # We create a stub event dict with minimal identity/lineage.
            stub_event = self._build_stub_event(
                symbol=symbol,
                mode=mode,
                model_scope=model_scope,
                request_kind=request_kind,
            )

            # Map simulation output to outcome fields
            mapped = self._mapper.map_simulation_to_v7(sim_output)

            # Create TradeOutcome
            outcome = self._outcome_manager.create(
                decision_event=stub_event,
                outcome_source=outcome_source,
                execution_path=execution_path,
                realized_outcome=mapped.get("realized_outcome"),
                path_metrics=mapped.get("path_metrics"),
                comparative_outcome=mapped.get("comparative_outcome"),
                **kwargs,
            )
            outcomes.append(outcome)

            # Collect statistics
            realized = sim_output.long_outcome.realized_r_net if hasattr(sim_output, "long_outcome") else 0.0
            realized_r_values.append(realized)

            if hasattr(sim_output, "long_outcome"):
                fee_costs.append(sim_output.long_outcome.fee_cost_r)
                slippage_costs.append(sim_output.long_outcome.slippage_cost_r)
                total_costs.append(sim_output.long_outcome.total_cost_r)
                hold_bars.append(sim_output.long_outcome.hold_duration_bars)

            best_action = sim_output.best_action if hasattr(sim_output, "best_action") else ""
            if best_action == "NO_TRADE":
                no_trade_count += 1
            if realized > 0:
                wins += 1

        total = len(sim_inputs)
        trade_count = total - no_trade_count

        summary = ReplaySummary(
            count=total,
            no_trade_count=no_trade_count,
            trade_count=trade_count,
            no_trade_rate=no_trade_count / total if total > 0 else 0.0,
            avg_r=statistics.mean(realized_r_values) if realized_r_values else 0.0,
            median_r=statistics.median(realized_r_values) if realized_r_values else 0.0,
            std_r=statistics.stdev(realized_r_values) if len(realized_r_values) > 1 else 0.0,
            avg_fee_cost_r=statistics.mean(fee_costs) if fee_costs else 0.0,
            avg_slippage_cost_r=statistics.mean(slippage_costs) if slippage_costs else 0.0,
            total_cost_r=statistics.mean(total_costs) if total_costs else 0.0,
            win_rate=wins / total if total > 0 else 0.0,
            avg_hold_bars=statistics.mean(hold_bars) if hold_bars else 0.0,
        )

        no_trade_analysis = {
            "total_runs": total,
            "no_trade_runs": no_trade_count,
            "no_trade_rate": summary.no_trade_rate,
            "trade_runs": trade_count,
            "win_rate": summary.win_rate,
        }

        return {
            "outcomes": outcomes,
            "summary": summary,
            "no_trade_analysis": no_trade_analysis,
        }

    def _build_stub_event(
        self,
        symbol: str,
        mode: str,
        model_scope: str,
        request_kind: str,
    ) -> dict:
        """Build a minimal stub event for replay outcome creation.

        The stub provides enough identity/lineage fields for
        ``TradeOutcomeManager.create()`` to function.
        """
        return {
            "identity": {
                "decision_event_id": f"stub_{_utc_now()}",
                "request_id": f"replay_req_{_utc_now()}",
                "timestamp_utc": _utc_now(),
            },
            "lineage": {
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "request_kind": request_kind,
                "model_scope": model_scope,
                "trade_mode": mode,
            },
            "scope": {
                "symbol": symbol,
                "model_scope": model_scope,
                "trade_mode": mode,
            },
            "decision_summary": {
                "outcome_horizon_family": f"{mode.lower()}_horizon",
            },
            "execution_linkage": {},
        }


# =========================================================================
# EvaluationDriver
# =========================================================================


@dataclass
class EvaluationReport:
    """Structured report combining paper and replay evaluation results.

    Attributes:
        symbol: Evaluated symbol.
        mode: Trading mode.
        model_scope: Model scope.
        timestamp_utc: Report generation timestamp.
        paper: Dict with paper simulation results (or None).
        replay: Dict with replay simulation results (or None).
        aggregate_metrics: Combined summary metrics dict.
    """

    symbol: str
    mode: str
    model_scope: str
    timestamp_utc: str = ""
    paper: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None
    aggregate_metrics: dict[str, Any] = field(default_factory=dict)


class EvaluationDriver:
    """Combined paper + replay evaluation.

    Runs both ``PaperMode`` and ``ReplayMode`` and produces a structured
    ``EvaluationReport`` with aggregate metrics.
    """

    def __init__(
        self,
        paper_mode: PaperMode | None = None,
        replay_mode: ReplayMode | None = None,
    ) -> None:
        self._paper = paper_mode or PaperMode()
        self._replay = replay_mode or ReplayMode()

    def run_evaluation(
        self,
        symbol: str,
        mode: str,
        model_scope: str,
        paper_sim_input: SimulationInput | None = None,
        replay_sim_inputs: list[SimulationInput] | None = None,
        **kwargs: Any,
    ) -> EvaluationReport:
        """Run a combined paper + replay evaluation.

        Args:
            symbol: Trading symbol.
            mode: Trading mode.
            model_scope: Model scope identifier.
            paper_sim_input: SimulationInput for paper mode (optional).
            replay_sim_inputs: List of SimulationInputs for replay mode (optional).
            **kwargs: Forwarded to PaperMode.run() and ReplayMode.run().

        Returns:
            EvaluationReport with paper results, replay results, and aggregate
            metrics.
        """
        paper_result = None
        replay_result = None

        if paper_sim_input is not None:
            paper_result = self._paper.run(
                symbol=symbol,
                mode=mode,
                model_scope=model_scope,
                sim_input=paper_sim_input,
                **kwargs,
            )

        if replay_sim_inputs:
            replay_result = self._replay.run(
                symbol=symbol,
                mode=mode,
                model_scope=model_scope,
                sim_inputs=replay_sim_inputs,
                **kwargs,
            )

        # Build aggregate metrics
        aggregate_metrics = self._compute_aggregate_metrics(
            paper_result=paper_result,
            replay_result=replay_result,
        )

        return EvaluationReport(
            symbol=symbol,
            mode=mode,
            model_scope=model_scope,
            timestamp_utc=_utc_now(),
            paper=paper_result,
            replay=replay_result,
            aggregate_metrics=aggregate_metrics,
        )

    def _compute_aggregate_metrics(
        self,
        paper_result: dict[str, Any] | None,
        replay_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Compute combined summary metrics from paper and replay results."""
        metrics: dict[str, Any] = {
            "paper_completed": paper_result is not None,
            "replay_completed": replay_result is not None,
        }

        if paper_result is not None:
            ntv = paper_result.get("no_trade_validation", {})
            metrics["paper_no_trade_match"] = ntv.get("match")

        if replay_result is not None:
            summary = replay_result.get("summary")
            if summary is not None:
                metrics.update({
                    "replay_count": summary.count,
                    "replay_no_trade_rate": summary.no_trade_rate,
                    "replay_avg_r": summary.avg_r,
                    "replay_median_r": summary.median_r,
                    "replay_std_r": summary.std_r,
                    "replay_win_rate": summary.win_rate,
                    "replay_avg_hold_bars": summary.avg_hold_bars,
                })

        return metrics
