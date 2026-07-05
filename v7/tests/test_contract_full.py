"""
Comprehensive V7 AnalysisRequest / AnalysisResult contract tests.

Covers:
  1. Full AnalysisRequest builder — all required sections and fields
  2. Full AnalysisResult validator — all required sections and V7-style decisions
  3. Serialization / deserialization round-trips
  4. Schema version alignment verification
  5. Contract validation — edge cases, cross-field consistency, enforcement
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from v7.builder import build_analysis_request, validate_analysis_request
from v7.validator import build_analysis_result, validate_analysis_result

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REQUEST_SCHEMA_PATH = (
    _REPO_ROOT / "contracts" / "schemas" / "analysis_request.schema.json"
)
_RESULT_SCHEMA_PATH = (
    _REPO_ROOT / "contracts" / "schemas" / "analysis_result.schema.json"
)
_REQUEST_FIXTURE_PATH = (
    _REPO_ROOT / "contracts" / "fixtures" / "analysis_request_minimal.json"
)
_RESULT_FIXTURE_PATH = (
    _REPO_ROOT / "contracts" / "fixtures" / "analysis_result_minimal.json"
)


# ===========================================================================
# 1. FULL AnalysisRequest BUILDER
# ===========================================================================

class TestFullAnalysisRequestBuilder:
    """Exercises every required section and field of the V7 AnalysisRequest."""

    def test_all_required_sections_present(self):
        """Builder emits contract, identity, scope, canonical_state."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        assert "contract" in req
        assert "identity" in req
        assert "scope" in req
        assert "canonical_state" in req

    def test_contract_section_all_fields(self):
        """Contract section has all 4 required fields."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            request_kind="replay_eval",
        )
        c = req["contract"]
        assert c["contract_version"] == "v7-0.2"
        assert c["state_schema_version"] == "state-0.2"
        assert c["snapshot_builder_version"] == "snapshot-0.2"
        assert c["request_kind"] == "replay_eval"

    def test_identity_section_all_fields(self):
        """Identity section has request_id and timestamp_utc."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            run_id="test_run_001",
        )
        i = req["identity"]
        assert i["request_id"].startswith("req_")
        assert i["timestamp_utc"].endswith("Z")
        assert i["run_id"] == "test_run_001"

    def test_scope_section_all_required_fields(self):
        """Scope section contains all 5 required fields plus defaults."""
        req = build_analysis_request(
            mode="AGGRESSIVE_SCALP",
            symbol="ETHUSDT",
            model_scope="aggressive_scalp_v1",
            exchange="BINANCE",
            market_type="PERP",
        )
        s = req["scope"]
        assert s["symbol"] == "ETHUSDT"
        assert s["requested_trade_mode"] == "AGGRESSIVE_SCALP"
        assert s["model_scope"] == "aggressive_scalp_v1"
        assert s["primary_interval"] == "15m"
        assert s["analysis_mode"] == "live"
        assert s["exchange"] == "BINANCE"
        assert s["market_type"] == "PERP"

    def test_canonical_state_minimal_shape(self):
        """Minimal canonical_state has 5 sub-sections."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        cs = req["canonical_state"]
        assert "raw_window" in cs
        assert "derived_state" in cs
        assert "context" in cs
        assert "quality" in cs
        assert "metadata" in cs
        # raw_window structure
        rw = cs["raw_window"]
        assert "window_length" in rw
        assert "candles" in rw
        # metadata has identity
        md = cs["metadata"]
        assert md["symbol"] == "BTCUSDT"

    def test_mode_default_interval_mapping(self):
        """Each mode produces correct default intervals."""
        cases = {
            "SWING": ("4h", ["1d"], ["1h"]),
            "SCALP": ("1h", ["4h"], ["15m"]),
            "AGGRESSIVE_SCALP": ("15m", ["1h"], ["5m"]),
        }
        for mode, (pri, ctx, ref) in cases.items():
            req = build_analysis_request(mode=mode, symbol="XRPUSDT", model_scope=f"{mode.lower()}_v1")
            s = req["scope"]
            assert s["primary_interval"] == pri, f"{mode}: primary"
            assert s["context_intervals"] == ctx, f"{mode}: context"
            assert s["refinement_intervals"] == ref, f"{mode}: refinement"

    def test_interval_overrides(self):
        """Explicit interval overrides should win over mode defaults."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            primary_interval="1h",
            context_intervals=["4h", "1d"],
            refinement_intervals=["30m"],
        )
        s = req["scope"]
        assert s["primary_interval"] == "1h"
        assert s["context_intervals"] == ["4h", "1d"]
        assert s["refinement_intervals"] == ["30m"]

    def test_all_request_kinds(self):
        """All 5 request_kind values are accepted."""
        for rk in ("live_scan", "paper_scan", "replay_eval", "shadow", "validation"):
            req = build_analysis_request(
                mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
                request_kind=rk,
            )
            assert req["contract"]["request_kind"] == rk

    def test_all_analysis_modes(self):
        """All 5 analysis_mode values are accepted."""
        for am in ("live", "paper", "replay", "shadow", "validation"):
            req = build_analysis_request(
                mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
                analysis_mode=am,
            )
            assert req["scope"]["analysis_mode"] == am

    def test_optional_sections_added_when_provided(self):
        """All optional sections appear when provided."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            state_views={"primary": "4h"},
            deterministic_context={"volatility_bucket": "HIGH"},
            runtime_context={"engine_timeout_ms": 500},
            quality_and_freshness={"stale_flag": False},
            degradation_context={"missing_htf_context": True},
            portfolio_context={"open_position_count": 3},
            risk_context={"cooldown_active": False},
            lineage={"analysis_batch_id": "batch_001"},
        )
        assert req["state_views"]["primary"] == "4h"
        assert req["deterministic_context"]["volatility_bucket"] == "HIGH"
        assert req["runtime_context"]["engine_timeout_ms"] == 500
        assert req["quality_and_freshness"]["stale_flag"] is False
        assert req["degradation_context"]["missing_htf_context"] is True
        assert req["portfolio_context"]["open_position_count"] == 3
        assert req["risk_context"]["cooldown_active"] is False
        assert req["lineage"]["analysis_batch_id"] == "batch_001"

    def test_builder_schema_validation_passes(self):
        """Builder output always passes schema validation."""
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            req = build_analysis_request(
                mode=mode, symbol="BTCUSDT", model_scope=f"{mode.lower()}_v1",
            )
            # Should not raise
            schema = json.loads(_REQUEST_SCHEMA_PATH.read_text())
            jsonschema.validate(instance=req, schema=schema)

    def test_invalid_mode_rejected(self):
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            build_analysis_request(mode="INVALID", symbol="BTCUSDT", model_scope="v1")

    def test_empty_symbol_rejected(self):
        """Empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            build_analysis_request(mode="SWING", symbol="", model_scope="v1")

    def test_empty_model_scope_rejected(self):
        """Empty model_scope raises ValueError."""
        with pytest.raises(ValueError, match="model_scope"):
            build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="")


# ===========================================================================
# 2. FULL AnalysisResult BUILDER / VALIDATOR
# ===========================================================================

class TestFullAnalysisResultBuilder:
    """Exercises every required section and field of the V7 AnalysisResult."""

    def test_all_required_sections_present(self):
        """Builder emits contract, identity, status, decision, scores, fallback."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert "contract" in result
        assert "identity" in result
        assert "status" in result
        assert "decision" in result
        assert "scores" in result
        assert "fallback_and_degradation" in result

    def test_contract_section(self):
        """Contract section has all 3 required fields."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        c = result["contract"]
        assert c["contract_version"] == "v7-0.3"
        assert c["response_schema_version"] == "result-0.3"
        assert c["engine_output_version"] == "engine-out-0.3"

    def test_identity_section(self):
        """Identity section has all 4 required fields."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
            run_id="scan_123",
        )
        i = result["identity"]
        assert i["request_id"] == "req_001"
        assert i["engine_name"] == "v7"
        assert i["engine_version"] == "0.3.0"
        assert i["timestamp_utc"].endswith("Z")
        assert i["run_id"] == "scan_123"

    def test_status_section(self):
        """Status section has all 3 required fields."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="LONG_NOW",
            confidence=0.8,
            confidence_kind="CALIBRATED",
            expected_r=1.5,
            signal_status="SIGNAL",
            decision_status="VALID",
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        st = result["status"]
        assert st["signal_status"] == "SIGNAL"
        assert st["decision_status"] == "VALID"
        assert st["is_actionable"] is True

    def test_decision_section(self):
        """Decision section has all 3 required fields."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="SHORT_NOW",
            decision_summary="Bearish setup.",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        d = result["decision"]
        assert d["recommended_action"] == "SHORT_NOW"
        assert d["direction"] == "SHORT"
        assert d["decision_summary"] == "Bearish setup."

    def test_scores_section(self):
        """Scores section has all 3 required fields plus extras."""
        result = build_analysis_result(
            request_id="req_001",
            confidence=0.72,
            confidence_kind="CALIBRATED",
            expected_r=1.2,
            long_score=0.72,
            short_score=0.15,
            no_trade_score=0.20,
            decision_margin=0.52,
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        sc = result["scores"]
        assert sc["confidence"] == 0.72
        assert sc["confidence_kind"] == "CALIBRATED"
        assert sc["expected_r"] == 1.2
        assert sc["long_score"] == 0.72
        assert sc["short_score"] == 0.15
        assert sc["no_trade_score"] == 0.20
        assert sc["decision_margin"] == 0.52

    def test_execution_guidance_for_actionable_trade(self):
        """Actionable trade gets full execution_guidance."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="LONG_NOW",
            confidence=0.78,
            confidence_kind="CALIBRATED",
            expected_r=1.35,
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
            entry_price=64300.0,
            stop_loss=62100.0,
            take_profit=67800.0,
            time_sensitivity="STANDARD",
            entry_readiness="READY_NOW",
            entry_valid_for_bars=3,
            entry_zone=[64200.0, 64400.0],
            size_multiplier=0.75,
            risk_expression="MEDIUM",
            execution_notes="Wait for confirmation.",
        )
        eg = result["execution_guidance"]
        assert eg["entry_price"] == 64300.0
        assert eg["stop_loss"] == 62100.0
        assert eg["take_profit"] == 67800.0
        assert eg["time_sensitivity"] == "STANDARD"
        assert eg["entry_readiness"] == "READY_NOW"
        assert eg["entry_valid_for_bars"] == 3
        assert eg["entry_zone"] == [64200.0, 64400.0]
        assert eg["size_multiplier"] == 0.75
        assert eg["risk_expression"] == "MEDIUM"
        assert eg["execution_notes"] == "Wait for confirmation."

    def test_no_execution_guidance_for_no_trade(self):
        """NO_TRADE does not produce execution_guidance (unless read. provides)."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="NO_TRADE",
            model_scope="swing_v1",
            trade_mode="SWING",
        )
        assert "execution_guidance" not in result

    def test_fallback_section(self):
        """Fallback section has all required fields with fallback path."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
            fallback_used=True,
            degraded_reason="Missing HTF context",
            fallback_reason="HTF data unavailable",
            fallback_source="snapshot_builder",
            runtime_safe_action="NO_TRADE",
            is_timeout_fallback=True,
        )
        fb = result["fallback_and_degradation"]
        assert fb["fallback_used"] is True
        assert fb["degraded_reason"] == "Missing HTF context"
        assert fb["fallback_reason"] == "HTF data unavailable"
        assert fb["fallback_source"] == "snapshot_builder"
        assert fb["runtime_safe_action"] == "NO_TRADE"
        assert fb["is_timeout_fallback"] is True
        assert fb["is_schema_fallback"] is False

    def test_optional_sections_added_when_provided(self):
        """Optional sections appear when provided."""
        result = build_analysis_result(
            request_id="req_001",
            model_scope="swing_v1",
            trade_mode="SWING",
            request_link={"symbol": "BTCUSDT", "model_scope": "swing_v1"},
            uncertainty_and_quality={"uncertainty_score": 0.2, "is_ambiguous": False},
            deterministic_interaction={"deterministic_alignment": "ALIGNED"},
            observability={"analysis_latency_ms": 100.0},
            lineage={"analysis_batch_id": "batch_001"},
        )
        assert result["request_link"]["symbol"] == "BTCUSDT"
        assert result["uncertainty_and_quality"]["uncertainty_score"] == 0.2
        assert result["deterministic_interaction"]["deterministic_alignment"] == "ALIGNED"
        assert result["observability"]["analysis_latency_ms"] == 100.0
        assert result["lineage"]["analysis_batch_id"] == "batch_001"

    def test_action_direction_auto_map(self):
        """Direction auto-maps from recommended_action."""
        cases = [
            ("LONG_NOW", "LONG"),
            ("SHORT_NOW", "SHORT"),
            ("NO_TRADE", "NONE"),
        ]
        for action, expected_dir in cases:
            result = build_analysis_result(
                request_id="req_001",
                recommended_action=action,
                model_scope="swing_v1",
                trade_mode="SWING",
            )
            assert result["decision"]["direction"] == expected_dir, f"{action} -> {expected_dir}"

    def test_all_signal_statuses(self):
        """All 5 signal_status values accepted."""
        for ss in ("SIGNAL", "NO_TRADE", "FILTERED", "DEGRADED", "ERROR"):
            result = build_analysis_result(
                request_id="req_001",
                signal_status=ss,
                model_scope="swing_v1",
                trade_mode="SWING",
            )
            assert result["status"]["signal_status"] == ss

    def test_all_decision_statuses(self):
        """All 5 decision_status values accepted."""
        for ds in ("VALID", "LOW_CONFIDENCE", "BLOCKED", "DEGRADED", "FAILED"):
            result = build_analysis_result(
                request_id="req_001",
                decision_status=ds,
                model_scope="swing_v1",
                trade_mode="SWING",
            )
            assert result["status"]["decision_status"] == ds

    def test_all_time_sensitivities(self):
        """All 4 time_sensitivity values accepted."""
        for ts in ("IMMEDIATE", "STANDARD", "CAN_WAIT", "EXPIRING_SOON"):
            result = build_analysis_result(
                request_id="req_001",
                recommended_action="LONG_NOW",
                confidence=0.7,
                expected_r=1.0,
                is_actionable=True,
                time_sensitivity=ts,
                model_scope="swing_v1",
                trade_mode="SWING",
                entry_price=100.0,
                stop_loss=98.0,
                take_profit=105.0,
            )
            assert result["execution_guidance"]["time_sensitivity"] == ts

    def test_all_entry_readiness_values(self):
        """All 6 entry_readiness values accepted."""
        for er in ("READY_NOW", "WAIT", "CHASING", "EXPIRING", "MISSED", "NOT_APPLICABLE"):
            result = build_analysis_result(
                request_id="req_001",
                recommended_action="NO_TRADE",
                entry_readiness=er,
                model_scope="swing_v1",
                trade_mode="SWING",
            )
            assert result["execution_guidance"]["entry_readiness"] == er

    def test_builder_schema_validation_passes(self):
        """Builder output always passes schema validation."""
        result = build_analysis_result(
            request_id="req_001",
            recommended_action="LONG_NOW",
            confidence=0.78,
            confidence_kind="CALIBRATED",
            expected_r=1.35,
            is_actionable=True,
            model_scope="swing_v1",
            trade_mode="SWING",
            entry_price=64300.0,
            stop_loss=62100.0,
            take_profit=67800.0,
            time_sensitivity="STANDARD",
        )
        schema = json.loads(_RESULT_SCHEMA_PATH.read_text())
        jsonschema.validate(instance=result, schema=schema)

    def test_invalid_confidence_rejected(self):
        """Confidence out of range raises ValueError."""
        with pytest.raises(ValueError, match="confidence"):
            build_analysis_result(
                request_id="req_001", confidence=1.5,
                model_scope="swing_v1", trade_mode="SWING",
            )

    def test_invalid_action_rejected(self):
        """V6-style action raises ValueError."""
        with pytest.raises(ValueError, match="Invalid recommended_action"):
            build_analysis_result(
                request_id="req_001", recommended_action="ENTER_LONG",
                model_scope="swing_v1", trade_mode="SWING",
            )

    def test_invalid_trade_mode_rejected(self):
        """Invalid trade_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid trade_mode"):
            build_analysis_result(
                request_id="req_001", trade_mode="FUTURES",
                model_scope="swing_v1",
            )


# ===========================================================================
# 3. SERIALIZATION / DESERIALIZATION ROUND-TRIPS
# ===========================================================================

class TestSerializationRoundTrip:
    """JSON serialization/deserialization round-trip tests."""

    def test_request_round_trip(self):
        """AnalysisRequest serializes and deserializes without data loss."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            run_id="round_trip_test",
            state_views={"primary": "4h", "higher_timeframe": "1d"},
            lineage={"analysis_batch_id": "batch_rt_001"},
        )
        serialized = json.dumps(req, indent=2)
        deserialized = json.loads(serialized)

        assert deserialized["contract"]["contract_version"] == req["contract"]["contract_version"]
        assert deserialized["identity"]["request_id"] == req["identity"]["request_id"]
        assert deserialized["scope"]["symbol"] == "BTCUSDT"
        assert deserialized["scope"]["primary_interval"] == "4h"
        assert deserialized["state_views"]["primary"] == "4h"
        assert deserialized["lineage"]["analysis_batch_id"] == "batch_rt_001"

        # Re-validate after round-trip
        errors = validate_analysis_request(deserialized)
        assert errors == [], f"Round-trip request failed validation: {errors}"

    def test_result_round_trip(self):
        """AnalysisResult serializes and deserializes without data loss."""
        result = build_analysis_result(
            request_id="req_rt_001",
            recommended_action="LONG_NOW",
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
            observability={"analysis_latency_ms": 142.0},
            lineage={"analysis_batch_id": "batch_rt_001"},
        )
        serialized = json.dumps(result, indent=2)
        deserialized = json.loads(serialized)

        assert deserialized["decision"]["recommended_action"] == "LONG_NOW"
        assert deserialized["scores"]["confidence"] == 0.78
        assert deserialized["execution_guidance"]["entry_price"] == 64300.0
        assert deserialized["identity"]["request_id"] == "req_rt_001"

        # Re-validate after round-trip
        errors = validate_analysis_result(deserialized)
        assert errors == [], f"Round-trip result failed validation: {errors}"

    def test_no_trade_result_round_trip(self):
        """NO_TRADE result round-trips correctly without execution_guidance."""
        result = build_analysis_result(
            request_id="req_rt_002",
            recommended_action="NO_TRADE",
            model_scope="swing_v1",
            trade_mode="SWING",
            fallback_used=True,
            degraded_reason="Stale data",
        )
        serialized = json.dumps(result)
        deserialized = json.loads(serialized)

        assert deserialized["decision"]["recommended_action"] == "NO_TRADE"
        assert deserialized["status"]["is_actionable"] is False
        assert "execution_guidance" not in deserialized
        assert deserialized["fallback_and_degradation"]["fallback_used"] is True

        errors = validate_analysis_result(deserialized)
        assert errors == []

    def test_fixture_round_trip_and_validate(self):
        """Canonical fixture files survive round-trip and validation."""
        # Request fixture
        req_data = json.loads(_REQUEST_FIXTURE_PATH.read_text())
        req_round = json.loads(json.dumps(req_data))
        errors = validate_analysis_request(req_round)
        assert errors == [], f"Request fixture validation: {errors}"

        # Result fixture
        res_data = json.loads(_RESULT_FIXTURE_PATH.read_text())
        res_round = json.loads(json.dumps(res_data))
        errors = validate_analysis_result(res_round)
        assert errors == [], f"Result fixture validation: {errors}"

    def test_deep_copy_equivalence(self):
        """Deep-copied dicts validate and match originals."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        req_copy = copy.deepcopy(req)
        assert req_copy == req
        errors = validate_analysis_request(req_copy)
        assert errors == []

    def test_json_round_trip_preserves_nulls(self):
        """Null values in degradation_context survive JSON round-trip."""
        req = build_analysis_request(
            mode="SWING", symbol="BTCUSDT", model_scope="swing_v1",
            degradation_context=None,
        )
        serialized = json.dumps(req)
        deserialized = json.loads(serialized)
        assert deserialized["degradation_context"] is None


# ===========================================================================
# 4. SCHEMA VERSION ALIGNMENT
# ===========================================================================

class TestSchemaVersionAlignment:
    """Verifies version strings are consistent across builder, schema, and fixtures."""

    # Known current versions (when these change, update intentionally)
    REQUEST_CONTRACT_VERSION = "v7-0.2"
    REQUEST_STATE_SCHEMA_VERSION = "state-0.2"
    REQUEST_SNAPSHOT_BUILDER_VERSION = "snapshot-0.2"
    RESULT_CONTRACT_VERSION = "v7-0.3"
    RESULT_RESPONSE_SCHEMA_VERSION = "result-0.3"
    RESULT_ENGINE_OUTPUT_VERSION = "engine-out-0.3"

    def test_request_builder_uses_expected_contract_version(self):
        """Builder default contract_version matches expected."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        assert req["contract"]["contract_version"] == self.REQUEST_CONTRACT_VERSION

    def test_request_builder_uses_expected_state_schema_version(self):
        """Builder default state_schema_version matches expected."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        assert req["contract"]["state_schema_version"] == self.REQUEST_STATE_SCHEMA_VERSION

    def test_request_builder_uses_expected_snapshot_builder_version(self):
        """Builder default snapshot_builder_version matches expected."""
        req = build_analysis_request(mode="SWING", symbol="BTCUSDT", model_scope="swing_v1")
        assert req["contract"]["snapshot_builder_version"] == self.REQUEST_SNAPSHOT_BUILDER_VERSION

    def test_result_builder_uses_expected_contract_version(self):
        """Builder default contract_version matches expected."""
        result = build_analysis_result(
            request_id="req_001", model_scope="swing_v1", trade_mode="SWING",
        )
        assert result["contract"]["contract_version"] == self.RESULT_CONTRACT_VERSION

    def test_result_builder_uses_expected_response_schema_version(self):
        """Builder default response_schema_version matches expected."""
        result = build_analysis_result(
            request_id="req_001", model_scope="swing_v1", trade_mode="SWING",
        )
        assert result["contract"]["response_schema_version"] == self.RESULT_RESPONSE_SCHEMA_VERSION

    def test_result_builder_uses_expected_engine_output_version(self):
        """Builder default engine_output_version matches expected."""
        result = build_analysis_result(
            request_id="req_001", model_scope="swing_v1", trade_mode="SWING",
        )
        assert result["contract"]["engine_output_version"] == self.RESULT_ENGINE_OUTPUT_VERSION

    def test_request_fixture_version_alignment(self):
        """Fixture file uses consistent version strings."""
        fixture = json.loads(_REQUEST_FIXTURE_PATH.read_text())
        c = fixture["contract"]
        assert c["contract_version"] == self.REQUEST_CONTRACT_VERSION
        assert c["state_schema_version"] == self.REQUEST_STATE_SCHEMA_VERSION
        assert c["snapshot_builder_version"] == self.REQUEST_SNAPSHOT_BUILDER_VERSION

    def test_result_fixture_version_alignment(self):
        """Result fixture uses consistent version strings."""
        fixture = json.loads(_RESULT_FIXTURE_PATH.read_text())
        c = fixture["contract"]
        assert c["contract_version"] == self.RESULT_CONTRACT_VERSION
        assert c["response_schema_version"] == self.RESULT_RESPONSE_SCHEMA_VERSION
        assert c["engine_output_version"] == self.RESULT_ENGINE_OUTPUT_VERSION

    def test_schema_id_pattern(self):
        """Schema $id values follow expected pattern."""
        req_schema = json.loads(_REQUEST_SCHEMA_PATH.read_text())
        assert "analysis_request" in req_schema["$id"]

        res_schema = json.loads(_RESULT_SCHEMA_PATH.read_text())
        assert "analysis_result" in res_schema["$id"]

    def test_request_and_result_version_differ(self):
        """Request and result contract versions differ (as expected by V7 design)."""
        # Request is v7-0.2, Result is v7-0.3 — they track separately
        assert self.REQUEST_CONTRACT_VERSION != self.RESULT_CONTRACT_VERSION


# ===========================================================================
# 5. CONTRACT VALIDATION — EDGE CASES AND ENFORCEMENT
# ===========================================================================

class TestContractValidation:
    """Contract validation beyond basic builder checks."""

    # ------------------------------------------------------------------
    # AnalysisRequest validation
    # ------------------------------------------------------------------

    def test_request_missing_contract_section(self):
        """Missing contract section is caught by schema."""
        d: dict[str, Any] = {
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "SWING",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
            "canonical_state": {},
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_missing_identity_section(self):
        """Missing identity section is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "live_scan",
            },
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "SWING",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
            "canonical_state": {},
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_missing_scope_section(self):
        """Missing scope section is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "live_scan",
            },
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "canonical_state": {},
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_missing_canonical_state(self):
        """Missing canonical_state is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "live_scan",
            },
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "SWING",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_invalid_enum_request_kind(self):
        """Invalid enum in contract.request_kind is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "production",
            },
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "SWING",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
            "canonical_state": {},
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_invalid_trade_mode_enum(self):
        """Invalid requested_trade_mode is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "live_scan",
            },
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "INVALID",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
            "canonical_state": {},
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    def test_request_additional_properties_blocked(self):
        """Top-level additionalProperties are blocked."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.2", "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2", "request_kind": "live_scan",
            },
            "identity": {"request_id": "x", "timestamp_utc": "2026-01-01T00:00:00Z"},
            "scope": {
                "symbol": "BTCUSDT", "requested_trade_mode": "SWING",
                "model_scope": "v1", "primary_interval": "4h", "analysis_mode": "live",
            },
            "canonical_state": {},
            "unknown_field": "should_not_exist",
        }
        errors = validate_analysis_request(d)
        assert len(errors) > 0

    # ------------------------------------------------------------------
    # AnalysisResult validation
    # ------------------------------------------------------------------

    def test_result_missing_contract_section(self):
        """Missing contract section is caught by schema."""
        d: dict[str, Any] = {
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "FILTERED",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert len(errors) > 0

    def test_result_missing_identity_section(self):
        """Missing identity section is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "FILTERED",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert len(errors) > 0

    def test_result_missing_status_section(self):
        """Missing status section is caught by schema."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert len(errors) > 0

    def test_result_actionable_long_must_have_execution_guidance(self):
        """Actionable LONG_NOW/SHORT_NOW without execution_guidance errors."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "SIGNAL", "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW", "direction": "LONG",
                "decision_summary": "Test",
            },
            "scores": {"confidence": 0.5, "confidence_kind": "RAW", "expected_r": 0.5},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert any("execution_guidance" in e.lower() for e in errors)

    def test_result_actionable_long_missing_entry_price(self):
        """Actionable trade missing entry_price in guidance errors."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "SIGNAL", "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW", "direction": "LONG",
                "decision_summary": "Test",
            },
            "scores": {"confidence": 0.5, "confidence_kind": "RAW", "expected_r": 0.5},
            "execution_guidance": {
                "stop_loss": 98.0,
                "take_profit": 105.0,
                "time_sensitivity": "STANDARD",
                # Missing entry_price
            },
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert any("entry_price" in e.lower() for e in errors)

    def test_result_fallback_used_no_reason(self):
        """fallback_used=True with null degraded_reason flagged."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "DEGRADED", "decision_status": "DEGRADED",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "Degraded.",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": True, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert any("fallback" in e.lower() for e in errors)

    def test_result_direction_mismatch(self):
        """Direction mismatch with recommended_action flagged."""
        for action, wrong_dir in [("LONG_NOW", "SHORT"), ("SHORT_NOW", "LONG"), ("NO_TRADE", "LONG")]:
            d: dict[str, Any] = {
                "contract": {
                    "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                    "engine_output_version": "engine-out-0.3",
                },
                "identity": {
                    "request_id": "x", "engine_name": "v7",
                    "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
                },
                "status": {
                    "signal_status": "SIGNAL" if action != "NO_TRADE" else "NO_TRADE",
                    "decision_status": "VALID",
                    "is_actionable": action != "NO_TRADE",
                },
                "decision": {
                    "recommended_action": action,
                    "direction": wrong_dir,
                    "decision_summary": "Mismatch.",
                },
                "scores": {"confidence": 0.5, "confidence_kind": "RAW", "expected_r": 0.5},
                "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
            }
            if action in ("LONG_NOW", "SHORT_NOW") and d["status"]["is_actionable"]:
                d["execution_guidance"] = {
                    "entry_price": 100.0, "stop_loss": 98.0,
                    "take_profit": 105.0, "time_sensitivity": "STANDARD",
                }
            errors = validate_analysis_result(d)
            assert any("direction" in e.lower() for e in errors), f"{action} + {wrong_dir}"

    def test_result_no_trade_actionable_fails(self):
        """NO_TRADE with is_actionable=True flagged."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert any("actionable" in e.lower() for e in errors)

    def test_result_additional_properties_blocked(self):
        """Top-level additionalProperties are blocked."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "FILTERED",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
            "unknown_field": "should_not_exist",
        }
        errors = validate_analysis_result(d)
        assert len(errors) > 0

    def test_result_entry_valid_for_bars_out_of_range(self):
        """entry_valid_for_bars outside 0-5 is flagged."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "SIGNAL", "decision_status": "VALID",
                "is_actionable": True,
            },
            "decision": {
                "recommended_action": "LONG_NOW", "direction": "LONG",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.5, "confidence_kind": "RAW", "expected_r": 0.5},
            "execution_guidance": {
                "entry_price": 100.0, "stop_loss": 98.0,
                "take_profit": 105.0, "time_sensitivity": "STANDARD",
                "entry_valid_for_bars": 7,
            },
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert len(errors) > 0

    def test_request_link_trade_mode_mismatch(self):
        """request_link.trade_mode != identity.trade_mode flagged."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
                "trade_mode": "SWING",
            },
            "request_link": {
                "trade_mode": "SCALP",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {"fallback_used": False, "degraded_reason": None},
        }
        errors = validate_analysis_result(d)
        assert any("request_link" in e.lower() and "trade_mode" in e.lower() for e in errors)

    def test_result_fallback_used_false_with_reason(self):
        """fallback_used=False but degraded_reason provided flagged."""
        d: dict[str, Any] = {
            "contract": {
                "contract_version": "v7-0.3", "response_schema_version": "result-0.3",
                "engine_output_version": "engine-out-0.3",
            },
            "identity": {
                "request_id": "x", "engine_name": "v7",
                "engine_version": "0.3.0", "timestamp_utc": "2026-01-01T00:00:00Z",
            },
            "status": {
                "signal_status": "NO_TRADE", "decision_status": "VALID",
                "is_actionable": False,
            },
            "decision": {
                "recommended_action": "NO_TRADE", "direction": "NONE",
                "decision_summary": "",
            },
            "scores": {"confidence": 0.0, "confidence_kind": "RAW", "expected_r": 0.0},
            "fallback_and_degradation": {
                "fallback_used": False,
                "degraded_reason": "Something happened",
            },
        }
        errors = validate_analysis_result(d)
        assert any("fallback" in e.lower() for e in errors)
