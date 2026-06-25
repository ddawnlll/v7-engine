"""Tests for v7.policy — policy acceptance layer."""

import pytest

from v7.policy import (
    PolicyResult,
    build_decision_event,
    evaluate_policy,
)


class TestEvaluatePolicy:
    """Test policy evaluation for trade candidates."""

    def _swing_request(self, **overrides):
        """Helper: build a minimal SWING AnalysisRequest."""
        base = {
            "request_id": "req_test_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        base.update(overrides)
        return base

    def test_strong_signal_passes(self):
        """Strong signal with high confidence and positive expected R passes."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.2,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert result.passed is True
        assert result.decision == "ENTER_LONG"
        assert result.confidence == 0.78
        assert result.expected_r > 0
        assert result.position_size_pct > 0
        assert result.stop_loss_price > 0
        assert result.take_profit_price > 0
        assert result.stop_loss_price < result.entry_price  # Long stop below entry
        assert result.take_profit_price > result.entry_price  # Long target above entry

    def test_short_passes(self):
        """Short direction should pass with correct stop/take."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.72,
            expected_r_gross=0.9,
            entry_price=65000.0,
            atr=1800.0,
            notional=10000.0,
            direction="SHORT",
        )
        assert result.passed is True
        assert result.decision == "ENTER_SHORT"
        # For shorts: stop above entry, target below entry
        assert result.stop_loss_price > result.entry_price
        assert result.take_profit_price < result.entry_price

    def test_low_confidence_rejected(self):
        """Confidence below threshold should be rejected."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.40,  # Below SWING min_confidence=0.55
            expected_r_gross=0.80,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert result.passed is False
        assert result.decision == "HOLD"
        assert result.gates["confidence_gate"] is False
        assert "confidence" in result.reason.lower()

    def test_negative_expected_r_rejected(self):
        """Negative expected R after costs should be rejected."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=0.01,  # Very small, eaten by costs
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert result.passed is False
        assert result.decision == "HOLD"
        assert result.gates["cost_gate"] is False

    def test_scalp_blocked_by_hold(self):
        """SCALP mode should be blocked by HOLD status."""
        request = self._swing_request(mode="SCALP", requested_trade_mode="SCALP")
        result = evaluate_policy(
            request=request,
            confidence=0.80,
            expected_r_gross=0.50,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert result.passed is False
        assert result.decision == "HOLD"
        assert result.gates["mode_lock"] is False
        assert "HOLD" in result.reason

    def test_aggressive_scalp_blocked_by_hold(self):
        """AGGRESSIVE_SCALP mode should be blocked by HOLD status."""
        request = self._swing_request(
            mode="AGGRESSIVE_SCALP", requested_trade_mode="AGGRESSIVE_SCALP"
        )
        result = evaluate_policy(
            request=request,
            confidence=0.85,
            expected_r_gross=0.30,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert result.passed is False
        assert result.decision == "HOLD"
        assert result.gates["mode_lock"] is False

    def test_zero_atr_returns_hold(self):
        """Zero ATR should result in HOLD (no risk computation)."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.80,
            expected_r_gross=1.0,
            entry_price=64300.0,
            atr=0.0,
            notional=10000.0,
        )
        assert result.passed is False
        assert result.decision == "HOLD"

    def test_cost_computation_with_funding(self):
        """Funding cost should be included in total cost."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.2,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
            funding_rate=0.0001,
            holding_bars=20,
        )
        # Should still pass with strong signal even with funding costs
        assert result.passed is True
        assert result.total_cost_r > 0
        # Total cost should be higher with funding
        result_no_funding = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.2,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
            funding_rate=0.0,
            holding_bars=0,
        )
        assert result.total_cost_r > result_no_funding.total_cost_r

    def test_all_gates_in_output(self):
        """PolicyResult should include all gate results."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.2,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        assert "confidence_gate" in result.gates
        assert "cost_gate" in result.gates
        assert "risk_gate" in result.gates
        assert "regime_gate" in result.gates
        assert "overall_eligible" in result.gates
        assert result.gates["overall_eligible"] is True

    def test_policy_result_immutable(self):
        """PolicyResult should be frozen."""
        request = self._swing_request()
        result = evaluate_policy(
            request=request,
            confidence=0.78,
            expected_r_gross=1.2,
            entry_price=64300.0,
            atr=1800.0,
            notional=10000.0,
        )
        with pytest.raises(Exception):
            result.passed = False  # type: ignore


class TestBuildDecisionEvent:
    """Test DecisionEvent construction."""

    def test_minimal_event(self):
        """Build a minimal DecisionEvent from an AnalysisResult."""
        analysis_result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.78,
            "stop_loss_price": 62100.00,
            "take_profit_price": 67800.00,
            "entry_price": 64300.00,
            "position_size_pct": 5.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@abc123",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        event = build_decision_event(analysis_result=analysis_result)
        assert event["event_id"].startswith("evt_")
        assert event["analysis_result_id"] == "ar_001"
        assert event["decision"] == "ENTER_LONG"
        assert event["venue"] == "paper_trading"
        assert event["event_type"] == "ORDER_PLACED"
        assert event["status"] == "SUCCESS"
        assert "executed_at" in event

    def test_with_order_id(self):
        """Event with order_id."""
        result = {
            "analysis_result_id": "ar_002",
            "decision": "ENTER_LONG",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
        }
        event = build_decision_event(
            analysis_result=result,
            venue="binance_futures",
            order_id="ord_binance_abc123",
            event_type="ORDER_FILLED",
            status="SUCCESS",
        )
        assert event["order_id"] == "ord_binance_abc123"
        assert event["venue"] == "binance_futures"
        assert event["event_type"] == "ORDER_FILLED"

    def test_with_metadata(self):
        """Event with metadata."""
        result = {
            "analysis_result_id": "ar_003",
            "decision": "HOLD",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
        }
        metadata = {"filled_qty": 0.05, "fill_price": 64300.50, "commission": 0.0032}
        event = build_decision_event(
            analysis_result=result,
            decision_event_id="evt_001",
            metadata=metadata,
        )
        assert event["event_id"] == "evt_001"
        assert event["metadata"] == metadata

    def test_hold_decision_event(self):
        """HOLD decisions should produce valid events."""
        result = {
            "analysis_result_id": "ar_004",
            "decision": "HOLD",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
        }
        event = build_decision_event(
            analysis_result=result,
            event_type="ERROR",
            status="FAILED",
        )
        assert event["decision"] == "HOLD"
        assert event["event_type"] == "ERROR"
        assert event["status"] == "FAILED"
