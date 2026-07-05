"""
End-to-end SWING mode test: AnalysisRequest -> validate -> route -> policy -> DecisionEvent.

This is the canonical integration test for TR-07 V7 Policy Acceptance.
SWING is LOCKED_INITIAL_BASELINE — this must pass.
"""

import json

import jsonschema

from v7.builder import build_analysis_request, validate_analysis_request
from v7.gates.evaluator import GateStatus, evaluate_candidate, get_promotion_summary
from v7.policy import build_decision_event, evaluate_policy
from v7.router import LOCKED_INITIAL_BASELINE, route_request
from v7.validator import build_analysis_result, validate_analysis_result


class TestSwingEndToEnd:
    """Full SWING mode pipeline: request -> result -> event."""

    def test_full_swing_pipeline_strong_signal(self):
        """End-to-end: strong SWING signal passes all gates and produces DecisionEvent."""
        # Step 1: Build AnalysisRequest
        request = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            caller="v7_runtime",
        )
        assert validate_analysis_request(request) == []

        # Step 2: Route to mode
        route = route_request(request)
        assert route.allowed is True
        assert route.mode == "SWING"
        assert route.profile["status"] == LOCKED_INITIAL_BASELINE

        # Step 3: Evaluate policy with strong signal
        policy_result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.20,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
            direction="LONG",
        )
        assert policy_result.passed is True
        assert policy_result.decision == "ENTER_LONG"
        assert policy_result.confidence == 0.78
        assert policy_result.expected_r > 0
        assert policy_result.stop_loss_price > 0
        assert policy_result.take_profit_price > 0
        assert policy_result.stop_loss_price < policy_result.entry_price
        assert policy_result.take_profit_price > policy_result.entry_price

        # Step 4: Build AnalysisResult from policy output
        analysis_result = build_analysis_result(
            request_id=request["request_id"],
            decision=policy_result.decision,
            confidence=policy_result.confidence,
            stop_loss_price=policy_result.stop_loss_price,
            take_profit_price=policy_result.take_profit_price,
            entry_price=policy_result.entry_price,
            position_size_pct=policy_result.position_size_pct,
            reasoning=policy_result.reason,
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
            execution_eligibility=policy_result.gates,
        )
        assert validate_analysis_result(analysis_result) == []

        # Step 5: Build DecisionEvent from AnalysisResult
        event = build_decision_event(
            analysis_result=analysis_result,
            venue="paper_trading",
        )
        assert event["event_id"].startswith("evt_")
        assert event["analysis_result_id"] == analysis_result["analysis_result_id"]
        assert event["decision"] == "ENTER_LONG"
        assert event["status"] == "SUCCESS"

    def test_full_swing_pipeline_weak_signal_rejected(self):
        """End-to-end: weak signal should be rejected by policy."""
        request = build_analysis_request(
            mode="SWING",
            symbol="ETHUSDT",
            model_scope="swing_v1",
        )
        route = route_request(request)
        assert route.allowed is True

        # Weak confidence
        policy_result = evaluate_policy(
            request=request,
            confidence=0.30,
            expected_r_gross=0.50,
            entry_price=3200.0,
            atr=120.0,
            notional=5000.0,
        )
        assert policy_result.passed is False
        assert policy_result.decision == "HOLD"

        # HOLD decisions still produce valid AnalysisResult
        analysis_result = build_analysis_result(
            request_id=request["request_id"],
            decision="HOLD",
            confidence=0.30,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            entry_price=0.0,
            position_size_pct=0.0,
            reasoning=policy_result.reason,
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="ETHUSDT",
            execution_eligibility=policy_result.gates,
        )
        assert validate_analysis_result(analysis_result) == []

        # Even HOLD decisions produce valid DecisionEvents
        event = build_decision_event(
            analysis_result=analysis_result,
            event_type="ERROR",
            status="FAILED",
        )
        assert event["decision"] == "HOLD"

    def test_full_pipeline_contract_schema_validation(self):
        """All outputs should validate against their contract schemas."""
        import json
        from pathlib import Path

        # Load schemas
        contracts_dir = (
            Path(__file__).resolve().parent.parent.parent / "contracts" / "schemas"
        )
        request_schema = json.loads(
            (contracts_dir / "analysis_request.schema.json").read_text()
        )
        result_schema = json.loads(
            (contracts_dir / "analysis_result.schema.json").read_text()
        )
        event_schema = json.loads(
            (contracts_dir / "decision_event.schema.json").read_text()
        )

        # Build pipeline
        request = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
        )
        jsonschema.validate(instance=request, schema=request_schema)

        policy_result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.20,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )

        analysis_result = build_analysis_result(
            request_id=request["request_id"],
            decision=policy_result.decision,
            confidence=policy_result.confidence,
            stop_loss_price=policy_result.stop_loss_price,
            take_profit_price=policy_result.take_profit_price,
            entry_price=policy_result.entry_price,
            position_size_pct=policy_result.position_size_pct,
            reasoning=policy_result.reason,
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
        )
        jsonschema.validate(instance=analysis_result, schema=result_schema)

        event = build_decision_event(analysis_result=analysis_result)
        jsonschema.validate(instance=event, schema=event_schema)

    def test_router_integration_with_policy(self):
        """Router should correctly identify allowed/blocked modes for policy."""
        # SWING: allowed
        swing_req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1"
        )
        swing_route = route_request(swing_req)
        assert swing_route.allowed is True

        # SCALP: blocked
        scalp_req = build_analysis_request(
            mode="SCALP", symbol="ETHUSDT", model_scope="scalp_v1"
        )
        scalp_route = route_request(scalp_req)
        assert scalp_route.allowed is False
        assert "empirical evidence" in scalp_route.block_reason.lower()

        # AGGRESSIVE_SCALP: blocked
        agg_req = build_analysis_request(
            mode="AGGRESSIVE_SCALP", symbol="BTCUSDT", model_scope="aggressive_scalp_v1"
        )
        agg_route = route_request(agg_req)
        assert agg_route.allowed is False

    def test_gates_evaluation_on_policy_output(self):
        """G0-G10 gates should evaluate policy output."""
        request = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1"
        )
        policy_result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.20,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )

        candidate = {
            "request_id": request["request_id"],
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
        }
        ctx = {
            "expectancy_r": policy_result.expected_r,
            "expected_r_net": policy_result.expected_r,
            "expected_r_gross": 1.20,
            "ece": 0.05,
            "model_signature": "swing_v1@abc123",
        }
        gate_results = evaluate_candidate(candidate, ctx)
        summary = get_promotion_summary(gate_results)
        assert summary["passed"] is True
        assert "PROMOTE" in summary["recommendation"]
