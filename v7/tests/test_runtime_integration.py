"""Tests for v7.runtime_integration — V7PipelineExecutor."""

from __future__ import annotations

import pytest

from v7.lifecycle import DecisionEventManager, TradeOutcomeManager
from v7.mappings import CrossDomainMapper
from v7.policy import PolicyResult
from v7.router import RouteResult
from v7.runtime_integration import (
    EligibilityResult,
    V7PipelineExecutor,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def minimal_raw_input() -> dict:
    """Minimal valid raw_input for build_analysis_request."""
    return {
        "mode": "SWING",
        "symbol": "BTCUSDT",
        "model_scope": "swing_v1",
    }


@pytest.fixture
def swing_analysis_result() -> dict:
    """A valid SWING AnalysisResult (nested V7 contract shape).

    Note: the result contract section must NOT contain state_schema_version
    or snapshot_builder_version — those belong in the AnalysisRequest
    contract section, not the AnalysisResult contract section.
    """
    return {
        "contract": {
            "contract_version": "v7-0.3",
            "response_schema_version": "result-0.3",
            "engine_output_version": "engine-out-0.3",
        },
        "identity": {
            "request_id": "req_001",
            "engine_name": "v7",
            "engine_version": "0.3.0",
            "timestamp_utc": "2026-07-05T12:00:00Z",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "run_id": "scan_001",
        },
        "request_link": {
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "request_contract_version": "v7-0.2",
            "request_kind_seen": "live_scan",
            "label_horizon_family": "swing_horizon",
        },
        "status": {
            "signal_status": "SIGNAL",
            "decision_status": "VALID",
            "is_actionable": True,
        },
        "decision": {
            "recommended_action": "LONG_NOW",
            "direction": "LONG",
            "decision_summary": "Trend continuation setup.",
        },
        "scores": {
            "confidence": 0.78,
            "confidence_kind": "RAW",
            "expected_r": 1.35,
            "long_score": 0.81,
            "short_score": 0.10,
            "no_trade_score": 0.18,
            "decision_margin": 0.42,
        },
        "execution_guidance": {
            "entry_price": 64300.0,
            "stop_loss": 62100.0,
            "take_profit": 67800.0,
            "time_sensitivity": "STANDARD",
            "entry_readiness": "READY_NOW",
            "entry_valid_for_bars": 3,
        },
        "uncertainty_and_quality": {
            "uncertainty_score": 0.25,
            "uncertainty_type": "EPISTEMIC",
            "decision_quality": "HIGH",
            "quality_flags": [],
        },
        "fallback_and_degradation": {
            "fallback_used": False,
            "degraded_reason": None,
        },
        "observability": {
            "analysis_latency_ms": 142.0,
            "warnings": [],
            "review_tags": ["trend", "momentum_breakout"],
        },
        "lineage": {
            "analysis_batch_id": "batch_001",
            "decision_session_id": "session_001",
        },
    }


@pytest.fixture
def no_trade_result() -> dict:
    """A valid SWING AnalysisResult with NO_TRADE."""
    return {
        "contract": {
            "contract_version": "v7-0.3",
            "response_schema_version": "result-0.3",
            "engine_output_version": "engine-out-0.3",
        },
        "identity": {
            "request_id": "req_002",
            "engine_name": "v7",
            "engine_version": "0.3.0",
            "timestamp_utc": "2026-07-05T13:00:00Z",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
        },
        "request_link": {
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "request_kind_seen": "live_scan",
        },
        "status": {
            "signal_status": "NO_TRADE",
            "decision_status": "VALID",
            "is_actionable": False,
        },
        "decision": {
            "recommended_action": "NO_TRADE",
            "direction": "NONE",
            "decision_summary": "Low conviction, conflicting signals.",
        },
        "scores": {
            "confidence": 0.22,
            "confidence_kind": "RAW",
            "expected_r": 0.05,
            "long_score": 0.25,
            "short_score": 0.20,
            "no_trade_score": 0.82,
        },
        "fallback_and_degradation": {
            "fallback_used": False,
            "degraded_reason": None,
        },
        "observability": {
            "warnings": [],
        },
    }


# =========================================================================
# Tests — Pipeline steps (unit)
# =========================================================================


class TestExecuteRequest:
    """V7PipelineExecutor.execute_request()"""

    def test_builds_valid_request(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        })
        assert isinstance(request, dict)
        assert request["scope"]["symbol"] == "BTCUSDT"
        assert request["scope"]["requested_trade_mode"] == "SWING"
        assert request["scope"]["model_scope"] == "swing_v1"
        assert "contract" in request
        assert "identity" in request
        assert "canonical_state" in request

    def test_raises_on_missing_mode(self) -> None:
        executor = V7PipelineExecutor()
        with pytest.raises(TypeError):
            executor.execute_request({
                "symbol": "BTCUSDT",
                "model_scope": "swing_v1",
            })


class TestRouteAndValidate:
    """V7PipelineExecutor.route_and_validate()"""

    def test_swing_is_allowed(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        })
        result = executor.route_and_validate(request)
        assert isinstance(result, RouteResult)
        assert result.allowed is True
        assert result.mode == "SWING"

    def test_scalp_hold_blocks(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SCALP",
            "symbol": "BTCUSDT",
            "model_scope": "scalp_v1",
        })
        result = executor.route_and_validate(request)
        assert isinstance(result, RouteResult)
        assert result.allowed is False
        assert result.block_reason != ""

    def test_scope_mismatch_raises(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "scalp_v1",  # mismatch!
        })
        with pytest.raises(ValueError, match="Scope mismatch"):
            executor.route_and_validate(request)

    def test_unknown_mode(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        })
        # Override the requested mode to something invalid
        request["mode"] = "UNKNOWN"
        with pytest.raises(ValueError, match="Unknown mode"):
            executor.route_and_validate(request)


class TestValidateResult:
    """V7PipelineExecutor.validate_result()"""

    def test_valid_result_passes(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        # Make the result's request_id match the request's request_id
        result = dict(swing_analysis_result)
        result["identity"] = dict(result["identity"])
        result["identity"]["request_id"] = request["identity"]["request_id"]
        errors = executor.validate_result(request, result)
        assert errors == []

    def test_mismatched_request_id(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        # Change the result request_id to force a mismatch
        result = dict(swing_analysis_result)
        result["identity"] = dict(result["identity"])
        result["identity"]["request_id"] = "wrong_req"
        errors = executor.validate_result(request, result)
        assert any("request_id" in e for e in errors)

    def test_invalid_actionable_no_trade(self, minimal_raw_input, no_trade_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        # Make NO_TRADE result incorrectly actionable
        result = dict(no_trade_result)
        result["status"] = dict(result["status"])
        result["status"]["is_actionable"] = True
        errors = executor.validate_result(request, result)
        assert len(errors) > 0


class TestEvaluatePolicy:
    """V7PipelineExecutor.evaluate_policy()"""

    def test_swing_long_passes(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        policy_result = executor.evaluate_policy(
            request=request,
            result=swing_analysis_result,
            atr=245.0,
            notional=10000.0,
        )
        assert isinstance(policy_result, PolicyResult)
        assert policy_result.decision in ("ENTER_LONG", "ENTER_SHORT", "HOLD")
        assert 0.0 <= policy_result.confidence <= 1.0

    def test_low_confidence_triggers_hold(self, minimal_raw_input, no_trade_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        policy_result = executor.evaluate_policy(
            request=request,
            result=no_trade_result,
            atr=245.0,
            notional=10000.0,
        )
        assert policy_result.passed is False
        # With confidence 0.22 and SWING min_confidence=0.55, confidence gate fails
        assert policy_result.gates.get("confidence_gate") is False

    def test_defaults_when_fields_missing(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        })
        empty_result = {
            "scores": {},
            "decision": {},
            "execution_guidance": {},
            "status": {},
        }
        policy_result = executor.evaluate_policy(
            request=request,
            result=empty_result,
            atr=100.0,
            notional=10000.0,
        )
        # With all zero defaults, policy should reject
        assert policy_result.passed is False
        assert policy_result.decision == "HOLD"


class TestCheckEligibility:
    """V7PipelineExecutor.check_eligibility()"""

    def test_swing_passes(self, minimal_raw_input) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        result = executor.check_eligibility(request)
        assert isinstance(result, EligibilityResult)
        assert result.passed is True

    def test_scalp_blocked(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SCALP",
            "symbol": "BTCUSDT",
            "model_scope": "scalp_v1",
        })
        result = executor.check_eligibility(request)
        assert result.passed is False
        assert result.reason != ""

    def test_unknown_mode_blocked(self) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request({
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        })
        request["requested_trade_mode"] = "UNKNOWN"
        request["mode"] = "UNKNOWN"
        result = executor.check_eligibility(request)
        assert result.passed is False

    def test_missing_mode(self) -> None:
        executor = V7PipelineExecutor()
        result = executor.check_eligibility({"no_mode": "here"})
        assert result.passed is False
        assert "No trade mode found" in result.reason


class TestMaterializeEvent:
    """V7PipelineExecutor.materialize_event()"""

    def test_creates_valid_event(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result)
        assert isinstance(event, dict)
        assert "contract" in event
        assert "identity" in event
        assert "lineage" in event
        assert "scope" in event
        assert event["execution_linkage"]["execution_path"] == "PAPER_EXECUTED"

    def test_venue_propagates(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result, venue="replay")
        assert event["execution_linkage"]["execution_path"] == "REPLAY_ONLY"

    def test_outcome_linkage_starts_pending(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result)
        ol = event["outcome_linkage"]
        assert ol["trade_outcome_id"] is None
        assert ol["outcome_status"] == "PENDING"

    def test_invalid_event_type_raises(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        with pytest.raises(Exception):
            executor.materialize_event(request, swing_analysis_result, event_type="INVALID")


class TestAttachOutcome:
    """V7PipelineExecutor.attach_outcome()"""

    def test_creates_outcome(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result)
        outcome = executor.attach_outcome(event)
        assert isinstance(outcome, dict)
        assert "contract" in outcome
        assert "identity" in outcome
        assert outcome["resolution_status"]["outcome_status"] == "PENDING"

    def test_event_linked_to_outcome(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result)
        outcome = executor.attach_outcome(event)
        event_id = event.get("identity", {}).get("decision_event_id")
        updated_event = executor._event_manager.get(event_id)
        assert updated_event is not None
        ol = updated_event["outcome_linkage"]
        assert ol["trade_outcome_id"] == outcome.get("identity", {}).get("trade_outcome_id")

    def test_replay_outcome_source(self, minimal_raw_input, swing_analysis_result) -> None:
        executor = V7PipelineExecutor()
        request = executor.execute_request(minimal_raw_input)
        event = executor.materialize_event(request, swing_analysis_result)
        outcome = executor.attach_outcome(
            event,
            outcome_source="REPLAY_PROJECTION",
            execution_path="REPLAY_ONLY",
        )
        lineage = outcome.get("lineage", {})
        assert lineage.get("outcome_source") == "REPLAY_PROJECTION"
        es = outcome.get("execution_summary", {})
        assert es.get("execution_path") == "REPLAY_ONLY"


# =========================================================================
# Tests — Full pipeline
# =========================================================================


class TestRunFullPipeline:
    """V7PipelineExecutor.run_full_pipeline()"""

    def test_full_pipeline_all_artifacts(self, minimal_raw_input, swing_analysis_result) -> None:
        """Test that run_full_pipeline produces all expected artifacts.

        Uses a fixed request_id in raw_input so the pipeline-internal
        request_id matches the analysis_result fixture.
        """
        executor = V7PipelineExecutor()
        shared_request_id = "shared_pipeline_req_001"
        raw_input = dict(minimal_raw_input)
        raw_input["request_id"] = shared_request_id
        result_result = dict(swing_analysis_result)
        result_result["identity"] = dict(result_result["identity"])
        result_result["identity"]["request_id"] = shared_request_id
        result = executor.run_full_pipeline(
            raw_input=raw_input,
            analysis_result=result_result,
            atr=245.0,
            notional=10000.0,
            sim_output=None,
        )
        assert isinstance(result, dict)
        assert "request" in result
        assert "route_result" in result
        assert "validation_errors" in result
        assert "policy_result" in result
        assert "eligibility_result" in result
        assert "decision_event" in result
        assert "trade_outcome" in result

        # Request should be valid
        assert result["request"]["scope"]["symbol"] == "BTCUSDT"
        # Route should allow SWING
        assert result["route_result"].allowed is True
        # Validation should pass
        assert result["validation_errors"] == []
        # Eligibility should pass
        assert result["eligibility_result"].passed is True
        # Event should be created
        assert result["decision_event"]["scope"]["symbol"] == "BTCUSDT"
        # Outcome is None when no sim_output provided
        assert result["trade_outcome"] is None

    def test_full_pipeline_with_sim_output(self, minimal_raw_input, swing_analysis_result) -> None:
        """Test full pipeline with a dict-style sim_output."""
        executor = V7PipelineExecutor()
        shared_request_id = "pipeline_sim_req_001"
        raw_input = dict(minimal_raw_input)
        raw_input["request_id"] = shared_request_id
        result_result = dict(swing_analysis_result)
        result_result["identity"] = dict(result_result["identity"])
        result_result["identity"]["request_id"] = shared_request_id
        sim_output = {
            "simulation_run_id": "sim_001",
            "symbol": "BTCUSDT",
            "best_action": "LONG_NOW",
            "resolution_status": "COMPLETE",
            "long_outcome": {
                "realized_r_net": 1.25,
                "fee_cost_r": 0.08,
                "slippage_cost_r": 0.02,
                "funding_cost_r": 0.0,
                "total_cost_r": 0.10,
                "hold_duration_bars": 10,
                "exit_reason": "TARGET_HIT",
            },
            "short_outcome": {
                "realized_r_net": -0.45,
            },
            "no_trade_outcome": {
                "saved_loss_r": 0.0,
                "missed_opportunity_r": 0.0,
            },
        }
        result = executor.run_full_pipeline(
            raw_input=raw_input,
            analysis_result=result_result,
            atr=245.0,
            notional=10000.0,
            sim_output=sim_output,
        )
        # TradeOutcome should be created when sim_output is provided
        assert result["trade_outcome"] is not None
        outcome = result["trade_outcome"]
        assert outcome["resolution_status"]["outcome_status"] == "PENDING"

        # Event should link to outcome
        event = result["decision_event"]
        event_id = event.get("identity", {}).get("decision_event_id")
        updated_event = executor._event_manager.get(event_id)
        assert updated_event is not None
        assert updated_event["outcome_linkage"]["trade_outcome_id"] is not None

    def test_aggressive_scalp_blocked(self, minimal_raw_input, swing_analysis_result) -> None:
        """Aggressive_scalp should be blocked by route and eligibility."""
        executor = V7PipelineExecutor()
        agg_input = {
            "mode": "AGGRESSIVE_SCALP",
            "symbol": "BTCUSDT",
            "model_scope": "aggressive_scalp_v1",
        }
        result = executor.run_full_pipeline(
            raw_input=agg_input,
            analysis_result=swing_analysis_result,
            atr=50.0,
            notional=5000.0,
        )
        assert result["route_result"].allowed is False
        assert result["eligibility_result"].passed is False

    def test_default_managers_created(self) -> None:
        """Executor creates its own managers when none provided."""
        executor = V7PipelineExecutor()
        assert isinstance(executor._event_manager, DecisionEventManager)
        assert isinstance(executor._outcome_manager, TradeOutcomeManager)
        assert isinstance(executor._mapper, CrossDomainMapper)

    def test_custom_managers_injected(self) -> None:
        """Executor accepts custom managers."""
        custom_event = DecisionEventManager()
        custom_outcome = TradeOutcomeManager()
        custom_mapper = CrossDomainMapper()
        executor = V7PipelineExecutor(
            event_manager=custom_event,
            outcome_manager=custom_outcome,
            mapper=custom_mapper,
        )
        assert executor._event_manager is custom_event
        assert executor._outcome_manager is custom_outcome
        assert executor._mapper is custom_mapper
