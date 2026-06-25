"""Tests for v7.validator — AnalysisResult validation."""

import pytest

from v7.validator import (
    build_analysis_result,
    validate_analysis_result,
)


class TestBuildAnalysisResult:
    """Test AnalysisResult construction."""

    def test_minimal_enter_long(self):
        """Build a valid ENTER_LONG result."""
        result = build_analysis_result(
            request_id="req_001",
            decision="ENTER_LONG",
            confidence=0.78,
            stop_loss_price=62100.00,
            take_profit_price=67800.00,
            entry_price=64300.00,
            position_size_pct=5.0,
            reasoning="Bullish breakout with volume confirmation",
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
        )
        assert result["request_id"] == "req_001"
        assert result["decision"] == "ENTER_LONG"
        assert result["confidence"] == 0.78
        assert result["stop_loss_price"] == 62100.00
        assert result["take_profit_price"] == 67800.00
        assert result["entry_price"] == 64300.00
        assert result["position_size_pct"] == 5.0
        assert result["mode"] == "SWING"
        assert result["symbol"] == "BTCUSDT"
        assert "analysis_result_id" in result
        assert result["analysis_result_id"].startswith("ar_")
        assert "analysis_timestamp" in result

    def test_enter_short(self):
        """Build a valid ENTER_SHORT result."""
        result = build_analysis_result(
            request_id="req_002",
            decision="ENTER_SHORT",
            confidence=0.65,
            stop_loss_price=68000.00,
            take_profit_price=62000.00,
            entry_price=65000.00,
            position_size_pct=3.0,
            reasoning="Bearish divergence on 4h",
            model_signature="swing_v1@def456",
            mode="SWING",
            symbol="ETHUSDT",
        )
        assert result["decision"] == "ENTER_SHORT"
        assert result["symbol"] == "ETHUSDT"

    def test_hold_decision(self):
        """Build a HOLD result."""
        result = build_analysis_result(
            request_id="req_003",
            decision="HOLD",
            confidence=0.30,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            entry_price=0.0,
            position_size_pct=0.0,
            reasoning="Confidence below threshold",
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
        )
        assert result["decision"] == "HOLD"
        assert result["position_size_pct"] == 0.0

    def test_invalid_decision_raises(self):
        """Invalid decision should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid decision"):
            build_analysis_result(
                request_id="req_001",
                decision="BUY",
                confidence=0.50,
                stop_loss_price=100.0,
                take_profit_price=200.0,
                entry_price=150.0,
                position_size_pct=5.0,
                reasoning="",
                model_signature="x",
                mode="SWING",
                symbol="BTCUSDT",
            )

    def test_invalid_confidence_raises(self):
        """Confidence outside 0-1 should raise ValueError."""
        for bad_conf in (-0.1, 1.5, 2.0):
            with pytest.raises(ValueError, match="confidence"):
                build_analysis_result(
                    request_id="req_001",
                    decision="HOLD",
                    confidence=bad_conf,
                    stop_loss_price=0.0,
                    take_profit_price=0.0,
                    entry_price=0.0,
                    position_size_pct=0.0,
                    reasoning="",
                    model_signature="x",
                    mode="SWING",
                    symbol="BTCUSDT",
                )

    def test_negative_position_size_raises(self):
        """Negative position size should raise ValueError."""
        with pytest.raises(ValueError, match="position_size_pct"):
            build_analysis_result(
                request_id="req_001",
                decision="HOLD",
                confidence=0.50,
                stop_loss_price=0.0,
                take_profit_price=0.0,
                entry_price=0.0,
                position_size_pct=-1.0,
                reasoning="",
                model_signature="x",
                mode="SWING",
                symbol="BTCUSDT",
            )

    def test_custom_execution_eligibility(self):
        """Custom execution eligibility should be preserved."""
        eligibility = {
            "confidence_gate": True,
            "risk_gate": False,
            "regime_gate": True,
            "cost_gate": True,
            "overall_eligible": False,
        }
        result = build_analysis_result(
            request_id="req_004",
            decision="HOLD",
            confidence=0.60,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            entry_price=0.0,
            position_size_pct=0.0,
            reasoning="Risk gate failed",
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
            execution_eligibility=eligibility,
        )
        assert result["execution_eligibility"] == eligibility

    def test_default_execution_eligibility(self):
        """Default execution eligibility should pass all gates."""
        result = build_analysis_result(
            request_id="req_005",
            decision="ENTER_LONG",
            confidence=0.80,
            stop_loss_price=50.0,
            take_profit_price=80.0,
            entry_price=60.0,
            position_size_pct=5.0,
            reasoning="Test",
            model_signature="swing_v1@abc123",
            mode="SWING",
            symbol="BTCUSDT",
        )
        eg = result["execution_eligibility"]
        assert eg["confidence_gate"] is True
        assert eg["risk_gate"] is True
        assert eg["regime_gate"] is True
        assert eg["cost_gate"] is True
        assert eg["overall_eligible"] is True


class TestValidateAnalysisResult:
    """Test validation of AnalysisResult dicts."""

    def test_valid_fixture(self):
        """The canonical minimal fixture should validate clean."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.78,
            "stop_loss_price": 62100.00,
            "take_profit_price": 67800.00,
            "entry_price": 64300.00,
            "position_size_pct": 5.0,
            "reasoning": "Bullish breakout with volume confirmation",
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
        errors = validate_analysis_result(result)
        assert errors == []

    def test_long_stop_above_entry(self):
        """ENTER_LONG with stop above entry should be flagged."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.78,
            "stop_loss_price": 70000.00,  # Above entry
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
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("stop" in e.lower() for e in errors)

    def test_long_take_below_entry(self):
        """ENTER_LONG with take below entry should be flagged."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.78,
            "stop_loss_price": 62000.00,
            "take_profit_price": 63000.00,  # Below entry
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
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("take" in e.lower() or "profit" in e.lower() for e in errors)

    def test_short_stop_below_entry(self):
        """ENTER_SHORT with stop below entry should be flagged."""
        result = {
            "analysis_result_id": "ar_002",
            "request_id": "req_002",
            "decision": "ENTER_SHORT",
            "confidence": 0.65,
            "stop_loss_price": 64000.00,  # Below entry
            "take_profit_price": 62000.00,
            "entry_price": 65000.00,
            "position_size_pct": 3.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@def456",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "ETHUSDT",
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("stop" in e.lower() for e in errors)

    def test_short_take_above_entry(self):
        """ENTER_SHORT with take above entry should be flagged."""
        result = {
            "analysis_result_id": "ar_002",
            "request_id": "req_002",
            "decision": "ENTER_SHORT",
            "confidence": 0.65,
            "stop_loss_price": 66000.00,
            "take_profit_price": 67000.00,  # Above entry
            "entry_price": 65000.00,
            "position_size_pct": 3.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@def456",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "ETHUSDT",
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("take" in e.lower() or "profit" in e.lower() for e in errors)

    def test_eligibility_inconsistency_all_pass_but_overall_false(self):
        """All gates pass but overall_eligible false should be flagged."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "ENTER_LONG",
            "confidence": 0.78,
            "stop_loss_price": 62000.00,
            "take_profit_price": 68000.00,
            "entry_price": 65000.00,
            "position_size_pct": 5.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@abc123",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": True,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": False,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("overall" in e.lower() for e in errors)

    def test_eligibility_inconsistency_gate_fail_but_overall_true(self):
        """Some gate fails but overall_eligible true should be flagged."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "HOLD",
            "confidence": 0.30,
            "stop_loss_price": 0.0,
            "take_profit_price": 0.0,
            "entry_price": 0.0,
            "position_size_pct": 0.0,
            "reasoning": "Test",
            "model_signature": "swing_v1@abc123",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": False,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": True,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("overall" in e.lower() for e in errors)

    def test_hold_decision_no_price_checks(self):
        """HOLD decision should not trigger stop/take sanity checks."""
        result = {
            "analysis_result_id": "ar_001",
            "request_id": "req_001",
            "decision": "HOLD",
            "confidence": 0.30,
            "stop_loss_price": 0.0,
            "take_profit_price": 0.0,
            "entry_price": 0.0,
            "position_size_pct": 0.0,
            "reasoning": "No trade",
            "model_signature": "swing_v1@abc123",
            "analysis_timestamp": "2026-06-01T12:00:05Z",
            "execution_eligibility": {
                "confidence_gate": False,
                "risk_gate": True,
                "regime_gate": True,
                "cost_gate": True,
                "overall_eligible": False,
            },
            "mode": "SWING",
            "symbol": "BTCUSDT",
        }
        errors = validate_analysis_result(result)
        # Only the inconsistency error should fire (gates fail but overall true nope — wait, overall is False here)
        # Actually confidence_gate=False and overall_eligible=False is consistent, so no errors
        assert errors == []
