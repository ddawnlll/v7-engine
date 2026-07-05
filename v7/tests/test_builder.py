"""Tests for v7.builder — V7 AnalysisRequest construction and validation."""

import pytest

from v7.builder import (
    build_analysis_request,
    validate_analysis_request,
)


class TestBuildAnalysisRequest:
    """Test V7 AnalysisRequest construction."""

    def test_minimal_swing_request(self):
        """Build a minimal valid SWING request with V7 nested shape."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
        )
        # Top-level sections
        assert "contract" in req
        assert "identity" in req
        assert "scope" in req
        assert "canonical_state" in req

        # Contract section
        assert req["contract"]["contract_version"] == "v7-0.2"
        assert req["contract"]["request_kind"] == "live_scan"

        # Identity section
        assert req["identity"]["request_id"].startswith("req_")
        assert "timestamp_utc" in req["identity"]

        # Scope section
        assert req["scope"]["symbol"] == "BTCUSDT"
        assert req["scope"]["requested_trade_mode"] == "SWING"
        assert req["scope"]["model_scope"] == "swing_v1"
        assert req["scope"]["primary_interval"] == "4h"
        assert req["scope"]["analysis_mode"] == "live"
        assert req["scope"]["context_intervals"] == ["1d"]
        assert req["scope"]["refinement_intervals"] == ["1h"]

        # Canonical state
        cs = req["canonical_state"]
        assert "raw_window" in cs
        assert "derived_state" in cs
        assert "context" in cs
        assert "quality" in cs
        assert "metadata" in cs

    def test_all_modes_accepted(self):
        """All three modes should build with correct defaults."""
        expected = {
            "SWING": ("4h", ["1d"], ["1h"]),
            "SCALP": ("1h", ["4h"], ["15m"]),
            "AGGRESSIVE_SCALP": ("15m", ["1h"], ["5m"]),
        }
        for mode, (pri, ctx, ref) in expected.items():
            req = build_analysis_request(
                mode=mode,
                symbol="ETHUSDT",
                model_scope=f"{mode.lower()}_v1",
            )
            assert req["scope"]["primary_interval"] == pri
            assert req["scope"]["context_intervals"] == list(ctx)
            assert req["scope"]["refinement_intervals"] == list(ref)

    def test_custom_request_id(self):
        """Custom request_id should be preserved."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            request_id="my_custom_req_123",
        )
        assert req["identity"]["request_id"] == "my_custom_req_123"

    def test_custom_timestamp(self):
        """Custom timestamp should be preserved."""
        ts = "2024-01-15T12:00:00Z"
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            timestamp_utc=ts,
        )
        assert req["identity"]["timestamp_utc"] == ts

    def test_different_request_kinds(self):
        """All valid request_kinds should be accepted."""
        for rk in ("live_scan", "paper_scan", "replay_eval", "shadow", "validation"):
            req = build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                request_kind=rk,
            )
            assert req["contract"]["request_kind"] == rk

    def test_different_analysis_modes(self):
        """All valid analysis_modes should be accepted."""
        for am in ("live", "paper", "replay", "shadow", "validation"):
            req = build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                analysis_mode=am,
            )
            assert req["scope"]["analysis_mode"] == am

    def test_invalid_mode_raises(self):
        """Invalid mode should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            build_analysis_request(
                mode="DAY_TRADING",
                symbol="BTCUSDT",
                model_scope="day_v1",
            )

    def test_invalid_request_kind_raises(self):
        """Invalid request_kind should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid request_kind"):
            build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                request_kind="invalid_kind",
            )

    def test_invalid_analysis_mode_raises(self):
        """Invalid analysis_mode should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid analysis_mode"):
            build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                analysis_mode="production",
            )

    def test_empty_symbol_raises(self):
        """Empty symbol should raise ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            build_analysis_request(
                mode="SWING",
                symbol="",
                model_scope="swing_v1",
            )

    def test_empty_model_scope_raises(self):
        """Empty model_scope should raise ValueError."""
        with pytest.raises(ValueError, match="model_scope"):
            build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="",
            )

    def test_symbol_uppercased(self):
        """Symbol should be uppercased."""
        req = build_analysis_request(
            mode="SWING",
            symbol="btcusdt",
            model_scope="swing_v1",
        )
        assert req["scope"]["symbol"] == "BTCUSDT"

    def test_with_custom_canonical_state(self):
        """Custom canonical_state should be preserved."""
        custom_state = {"raw_window": {"custom": True}}
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            canonical_state=custom_state,
        )
        assert req["canonical_state"] is custom_state

    def test_with_optional_sections(self):
        """All optional sections should be added if provided."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            state_views={"primary": "4h", "higher_timeframe": "1d"},
            runtime_context={"source_context": "autonomous_loop"},
            quality_and_freshness={"stale_flag": False},
            lineage={"analysis_batch_id": "batch_001"},
        )
        assert req["state_views"]["primary"] == "4h"
        assert req["runtime_context"]["source_context"] == "autonomous_loop"
        assert req["quality_and_freshness"]["stale_flag"] is False
        assert req["lineage"]["analysis_batch_id"] == "batch_001"
        # degradation_context should be None (explicitly set)
        assert req["degradation_context"] is None

    def test_run_id_in_identity(self):
        """run_id should appear in identity section when provided."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            run_id="scan_456",
        )
        assert req["identity"]["run_id"] == "scan_456"

    def test_contract_version_override(self):
        """Contract version overrides should propagate."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            contract_version="v7-0.3-test",
            state_schema_version="state-0.3-test",
        )
        assert req["contract"]["contract_version"] == "v7-0.3-test"
        assert req["contract"]["state_schema_version"] == "state-0.3-test"

    def test_trace_id_in_identity(self):
        """trace_id should appear in identity section when provided."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            trace_id="trace_abc123",
        )
        assert req["identity"]["trace_id"] == "trace_abc123"

    def test_parent_decision_event_id_in_identity(self):
        """parent_decision_event_id should appear in identity when provided."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            parent_decision_event_id="de_789",
        )
        assert req["identity"]["parent_decision_event_id"] == "de_789"

    def test_trace_id_omitted_when_not_provided(self):
        """trace_id should not be in identity when not provided."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
        )
        assert "trace_id" not in req["identity"]

    def test_caller_validates_but_not_stored(self):
        """caller validation passes but field is not in V7 schema."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            caller="v7_runtime",
        )
        # caller is validated but not stored in V7 identity
        assert "caller" not in req


class TestValidateAnalysisRequest:
    """Test validation of existing V7 AnalysisRequest dicts."""

    def test_valid_fixture(self):
        """The canonical minimal fixture should validate clean."""
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
        errors = validate_analysis_request(req)
        assert errors == []

    def test_missing_required_section(self):
        """Missing required 'contract' section should be caught by schema."""
        req = {
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
        errors = validate_analysis_request(req)
        assert len(errors) > 0
        assert any("required" in e.lower() for e in errors)

    def test_missing_required_scope_field(self):
        """Missing 'analysis_mode' in scope should be caught."""
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
                # Missing analysis_mode
            },
            "canonical_state": {"minimal": True},
        }
        errors = validate_analysis_request(req)
        assert len(errors) > 0

    def test_invalid_request_kind(self):
        """Invalid request_kind should be flagged."""
        req = {
            "contract": {
                "contract_version": "v7-0.2",
                "state_schema_version": "state-0.2",
                "snapshot_builder_version": "snapshot-0.2",
                "request_kind": "invalid_kind",
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
        errors = validate_analysis_request(req)
        assert len(errors) > 0

    def test_unknown_analysis_mode(self):
        """Unknown analysis_mode should be flagged."""
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
                "analysis_mode": "production",
            },
            "canonical_state": {"minimal": True},
        }
        errors = validate_analysis_request(req)
        assert len(errors) > 0
