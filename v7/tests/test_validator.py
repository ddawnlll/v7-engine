"""Tests for v7.validator — V7 AnalysisResult construction and validation."""

import pytest

from v7.validator import (
    build_analysis_result,
    validate_analysis_result,
    validate_result_against_request,
)


class TestBuildAnalysisResult:
    """Test V7 AnalysisResult construction."""

    def test_minimal_no_trade(self):
        """Build a minimal NO_TRADE result with V7 nested shape."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        # Top-level required sections
        assert "contract" in result
        assert "identity" in result
        assert "status" in result
        assert "decision" in result
        assert "scores" in result
        assert "fallback_and_degradation" in result
        assert "request_link" in result

        # Contract section
        assert result["contract"]["contract_version"] == "v7-0.3"

        # Identity section
        assert result["identity"]["request_id"] == "req_001"
        assert result["identity"]["engine_name"] == "v7"
        assert "timestamp_utc" in result["identity"]

        # Status (default NO_TRADE)
        assert result["status"]["signal_status"] == "NO_TRADE"
        assert result["status"]["decision_status"] == "VALID"
        assert result["status"]["is_actionable"] is False

        # Decision (default NO_TRADE)
        assert result["decision"]["recommended_action"] == "NO_TRADE"
        assert result["decision"]["direction"] == "NONE"

        # Scores (default zeros)
        assert result["scores"]["confidence"] == 0.0
        assert result["scores"]["confidence_kind"] == "RAW"

        # Fallback (default no fallback)
        assert result["fallback_and_degradation"]["fallback_used"] is False

    def test_actionable_long_now(self):
        """Build a fully actionable LONG_NOW result."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="LONG_NOW",
            direction="LONG",
            decision_summary="Bullish breakout with volume confirmation.",
            confidence=0.78,
            confidence_kind="CALIBRATED",
            expected_r=1.35,
            signal_status="SIGNAL",
            decision_status="VALID",
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
            entry_price=64300.0,
            stop_loss=62100.0,
            take_profit=67800.0,
            time_sensitivity="STANDARD",
            entry_readiness="READY_NOW",
            entry_valid_for_bars=3,
            long_score=0.81,
            short_score=0.10,
            no_trade_score=0.18,
        )
        assert result["decision"]["recommended_action"] == "LONG_NOW"
        assert result["decision"]["direction"] == "LONG"
        assert result["status"]["is_actionable"] is True
        assert result["status"]["signal_status"] == "SIGNAL"
        assert result["execution_guidance"]["entry_price"] == 64300.0
        assert result["execution_guidance"]["stop_loss"] == 62100.0
        assert result["execution_guidance"]["take_profit"] == 67800.0
        assert result["execution_guidance"]["time_sensitivity"] == "STANDARD"
        assert result["execution_guidance"]["entry_readiness"] == "READY_NOW"
        assert result["execution_guidance"]["entry_valid_for_bars"] == 3
        assert result["scores"]["long_score"] == 0.81
        assert result["scores"]["short_score"] == 0.10
        assert result["scores"]["no_trade_score"] == 0.18

    def test_actionable_short_now(self):
        """Build a fully actionable SHORT_NOW result."""
        result = build_analysis_result(
            request_id="req_002",
            recommended_action="SHORT_NOW",
            decision_summary="Bearish divergence on 4h.",
            confidence=0.65,
            confidence_kind="CALIBRATED",
            expected_r=1.1,
            signal_status="SIGNAL",
            decision_status="VALID",
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
            entry_price=65000.0,
            stop_loss=66000.0,
            take_profit=62000.0,
            time_sensitivity="IMMEDIATE",
            entry_readiness="READY_NOW",
            entry_valid_for_bars=2,
            short_score=0.79,
        )
        assert result["decision"]["recommended_action"] == "SHORT_NOW"
        assert result["decision"]["direction"] == "SHORT"
        assert result["execution_guidance"]["time_sensitivity"] == "IMMEDIATE"

    def test_implicit_direction_from_action(self):
        """Direction should be auto-set from action when omitted."""
        result = build_analysis_result(
            request_id="req_003",
            recommended_action="LONG_NOW",
            decision_summary="Test",
            confidence=0.5,
            confidence_kind="RAW",
            expected_r=0.5,
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert result["decision"]["direction"] == "LONG"

        result2 = build_analysis_result(
            request_id="req_004",
            recommended_action="SHORT_NOW",
            decision_summary="Test",
            confidence=0.5,
            confidence_kind="RAW",
            expected_r=0.5,
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert result2["decision"]["direction"] == "SHORT"

    def test_invalid_recommended_action_raises(self):
        """Invalid recommended_action should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid recommended_action"):
            build_analysis_result(
                request_id="req_001",
                recommended_action="ENTER_LONG",
                model_scope="swing_v1",
                trade_mode="SWING",
            )

    def test_invalid_confidence_raises(self):
        """Confidence outside 0-1 should raise ValueError."""
        for bad_conf in (-0.1, 1.5):
            with pytest.raises(ValueError, match="confidence"):
                build_analysis_result(
                    request_id="req_001",
                    confidence=bad_conf,
                    model_scope="swing_v1",
                    trade_mode="SWING",
                )

    def test_invalid_time_sensitivity_raises(self):
        """Invalid time_sensitivity should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid time_sensitivity"):
            build_analysis_result(
                request_id="req_001",
                time_sensitivity="URGENT",
                model_scope="swing_v1",
                trade_mode="SWING",
            )

    def test_invalid_entry_readiness_raises(self):
        """Invalid entry_readiness should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid entry_readiness"):
            build_analysis_result(
                request_id="req_001",
                entry_readiness="UNKNOWN",
                model_scope="swing_v1",
                trade_mode="SWING",
            )

    def test_custom_contract_versions(self):
        """Custom contract version overrides should propagate."""
        result = build_analysis_result(
            request_id="req_001",
            contract_version="v7-0.4-rc1",
            response_schema_version="result-0.4-rc1",
            engine_output_version="engine-out-0.4-rc1",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert result["contract"]["contract_version"] == "v7-0.4-rc1"
        assert result["contract"]["response_schema_version"] == "result-0.4-rc1"
        assert result["contract"]["engine_output_version"] == "engine-out-0.4-rc1"

    def test_with_optional_sections(self):
        """Optional sections should be added if provided."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
            uncertainty_and_quality={"uncertainty_score": 0.2, "is_ambiguous": False},
            observability={"analysis_latency_ms": 142.0, "reason_summary": "Test"},
            lineage={"analysis_batch_id": "batch_001"},
        )
        assert result["uncertainty_and_quality"]["uncertainty_score"] == 0.2
        assert result["observability"]["analysis_latency_ms"] == 142.0
        assert result["lineage"]["analysis_batch_id"] == "batch_001"

    def test_run_id_in_identity(self):
        """run_id should appear in identity section when provided."""
        result = build_analysis_result(
            request_id="req_001",
            run_id="scan_456",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert result["identity"]["run_id"] == "scan_456"

    def test_full_entry_zone(self):
        """Entry zone should be preserved when provided."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="LONG_NOW",
            confidence=0.7,
            confidence_kind="RAW",
            expected_r=1.0,
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=105.0,
            time_sensitivity="STANDARD",
            entry_zone=[99.5, 100.5],
        )
        assert result["execution_guidance"]["entry_zone"] == [99.5, 100.5]


class TestValidateAnalysisResult:
    """Test validation of V7 AnalysisResult dicts."""

    def test_valid_no_trade_fixture(self):
        """A well-formed no-trade fixture should validate clean."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert errors == []

    def test_valid_actionable_trade_fixture(self):
        """A well-formed actionable trade should validate clean."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "SIGNAL",
                "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW",
                "direction": "LONG",
                "decision_summary": "Bullish setup.",
            },
            "scores": {
                "confidence": 0.78,
                "confidence_kind": "CALIBRATED",
                "expected_r": 1.35,
            },
            "execution_guidance": {
                "entry_price": 64300.0,
                "stop_loss": 62100.0,
                "take_profit": 67800.0,
                "time_sensitivity": "STANDARD",
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert errors == []

    def test_action_direction_mismatch(self):
        """Mismatched action and direction should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "SIGNAL",
                "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW",
                "direction": "SHORT",
                "decision_summary": "Mismatch.",
            },
            "scores": {
                "confidence": 0.78,
                "confidence_kind": "CALIBRATED",
                "expected_r": 1.35,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("direction" in e.lower() for e in errors)

    def test_no_trade_actionable_flag(self):
        """NO_TRADE with is_actionable=True should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade but actionable?",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("actionable" in e.lower() for e in errors)

    def test_actionable_missing_execution_guidance(self):
        """Actionable trade without execution_guidance should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "SIGNAL",
                "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW",
                "direction": "LONG",
                "decision_summary": "No guidance.",
            },
            "scores": {
                "confidence": 0.78,
                "confidence_kind": "CALIBRATED",
                "expected_r": 1.35,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("execution_guidance" in e.lower() for e in errors)

    def test_fallback_inconsistency(self):
        """fallback_used true but degraded_reason null should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "DEGRADED",
                "decision_status": "DEGRADED",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "Degraded.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "fallback_and_degradation": {
                "fallback_used": True,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("fallback" in e.lower() for e in errors)

    def test_entry_valid_for_bars_out_of_range(self):
        """entry_valid_for_bars outside 0-5 should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "SIGNAL",
                "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW",
                "direction": "LONG",
                "decision_summary": "Bad bars.",
            },
            "scores": {
                "confidence": 0.78,
                "confidence_kind": "CALIBRATED",
                "expected_r": 1.35,
            },
            "execution_guidance": {
                "entry_price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 105.0,
                "time_sensitivity": "STANDARD",
                "entry_valid_for_bars": 10,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0

    def test_decision_status_failed_but_actionable(self):
        """FAILED decision_status with is_actionable=True should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "ERROR",
                "decision_status": "FAILED",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "Failed.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "fallback_and_degradation": {
                "fallback_used": True,
                "degraded_reason": "Engine error",
            },
        }
        errors = validate_analysis_result(result)
        assert len(errors) > 0
        assert any("actionable" in e.lower() for e in errors)


class TestValidateAnalysisResultRequestLink:
    """Test enhanced request_link validation."""

    def test_request_link_model_scope_mismatch(self):
        """request_link.model_scope != identity.model_scope should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
                "model_scope": "swing_v1",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "request_link": {
                "model_scope": "scalp_v1",
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert any("model_scope" in e.lower() for e in errors)

    def test_request_link_symbol_empty(self):
        """Empty request_link.symbol should be flagged."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "request_link": {
                "symbol": "",
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert any("symbol" in e.lower() for e in errors)

    def test_request_link_symbol_valid(self):
        """Valid request_link.symbol should not cause errors."""
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
                "model_scope": "swing_v1",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "request_link": {
                "symbol": "BTCUSDT",
                "model_scope": "swing_v1",
                "trade_mode": "SWING",
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        errors = validate_analysis_result(result)
        assert errors == []


class TestValidateResultAgainstRequest:
    """Test cross-document validation."""

    def _make_request(self, **overrides: str) -> dict:
        req = {
            "contract": {
                "contract_version": "v7-0.2",
                "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2",
                "request_kind": "live_scan",
            },
            "identity": {
                "request_id": "req_001",
                "timestamp_utc": "2026-07-05T12:00:00Z",
            },
            "scope": {
                "symbol": "BTCUSDT",
                "requested_trade_mode": "SWING",
                "model_scope": "swing_v1",
                "primary_interval": "4h",
                "analysis_mode": "live",
            },
            "canonical_state": {"minimal": True},
        }
        # Apply overrides
        for key, value in overrides.items():
            parts = key.split(".")
            target = req
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return req

    def _make_result(self, **overrides: str) -> dict:
        result = {
            "contract": {
                "contract_version": "v7-0.3",
                "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "req_001",
                "engine_name": "v7",
                "engine_version": "0.3.0",
                "timestamp_utc": "2026-07-05T12:00:01Z",
            },
            "status": {
                "signal_status": "NO_TRADE",
                "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE",
                "direction": "NONE",
                "decision_summary": "No trade.",
            },
            "scores": {
                "confidence": 0.0,
                "confidence_kind": "RAW",
                "expected_r": 0.0,
            },
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": None,
            },
        }
        for key, value in overrides.items():
            parts = key.split(".")
            target = result
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return result

    def test_request_id_match(self):
        """Matching request_ids should validate clean."""
        req = self._make_request()
        result = self._make_result()
        errors = validate_result_against_request(result, req)
        assert errors == []

    def test_request_id_mismatch(self):
        """Mismatched request_ids should be flagged."""
        req = self._make_request()
        result = self._make_result(**{"identity.request_id": "req_999"})
        errors = validate_result_against_request(result, req)
        assert any("request_id" in e.lower() for e in errors)

    def test_symbol_mismatch(self):
        """request_link.symbol != request.scope.symbol should be flagged."""
        req = self._make_request()
        result = self._make_result(**{"request_link.symbol": "ETHUSDT"})
        errors = validate_result_against_request(result, req)
        assert any("symbol" in e.lower() for e in errors)

    def test_model_scope_mismatch(self):
        """request_link.model_scope != request.scope.model_scope should be flagged."""
        req = self._make_request()
        result = self._make_result(**{"request_link.model_scope": "scalp_v1"})
        errors = validate_result_against_request(result, req)
        assert any("model_scope" in e.lower() for e in errors)

    def test_trade_mode_mismatch(self):
        """request_link.trade_mode != request.scope.requested_trade_mode should be flagged."""
        req = self._make_request()
        result = self._make_result(**{"request_link.trade_mode": "SCALP"})
        errors = validate_result_against_request(result, req)
        assert any("trade_mode" in e.lower() for e in errors)

    def test_primary_interval_mismatch(self):
        """request_link.primary_interval != request.scope.primary_interval should be flagged."""
        req = self._make_request()
        result = self._make_result(**{"request_link.primary_interval": "1h"})
        errors = validate_result_against_request(result, req)
        assert any("primary_interval" in e.lower() for e in errors)

    def test_contract_version_mismatch(self):
        """request_link.request_contract_version != contract_version should be flagged."""
        req = self._make_request()
        result = self._make_result(
            **{"request_link.request_contract_version": "v7-0.5"}
        )
        errors = validate_result_against_request(result, req)
        assert any("contract_version" in e.lower() for e in errors)

    def test_lineage_batch_id_mismatch(self):
        """lineage.analysis_batch_id mismatch should be flagged."""
        req = self._make_request(
            **{"lineage.analysis_batch_id": "batch_001"}
        )
        result = self._make_result(
            **{"lineage.analysis_batch_id": "batch_002"}
        )
        errors = validate_result_against_request(result, req)
        assert any("batch_id" in e.lower() for e in errors)

    def test_lineage_session_id_consistency(self):
        """Matching lineage.decision_session_id should validate clean."""
        req = self._make_request(
            **{"lineage.decision_session_id": "session_001"}
        )
        result = self._make_result(
            **{"lineage.decision_session_id": "session_001"}
        )
        errors = validate_result_against_request(result, req)
        assert errors == []

    def test_omit_request_link_does_not_cause_errors(self):
        """Missing request_link should not produce cross-doc errors."""
        req = self._make_request()
        result = self._make_result()
        # Remove request_link from result
        result.pop("request_link", None)
        errors = validate_result_against_request(result, req)
        assert errors == []
