"""Tests for v7.builder — AnalysisRequest construction and validation."""

import pytest

from v7.builder import (
    build_analysis_request,
    validate_analysis_request,
)


class TestBuildAnalysisRequest:
    """Test AnalysisRequest construction."""

    def test_minimal_swing_request(self):
        """Build a minimal valid SWING request."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
        )
        assert req["mode"] == "SWING"
        assert req["symbol"] == "BTCUSDT"
        assert req["model_scope"] == "swing_v1"
        assert req["requested_trade_mode"] == "SWING"
        assert req["caller"] == "v7_runtime"
        assert "request_id" in req
        assert req["request_id"].startswith("req_")
        assert "timestamp" in req

    def test_all_modes_accepted(self):
        """All three modes should build successfully."""
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            req = build_analysis_request(
                mode=mode,
                symbol="ETHUSDT",
                model_scope=f"{mode.lower()}_v1",
            )
            assert req["mode"] == mode
            assert req["requested_trade_mode"] == mode

    def test_custom_request_id(self):
        """Custom request_id should be preserved."""
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            request_id="my_custom_req_123",
        )
        assert req["request_id"] == "my_custom_req_123"

    def test_custom_timestamp(self):
        """Custom timestamp should be preserved."""
        ts = "2024-01-15T12:00:00Z"
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            timestamp=ts,
        )
        assert req["timestamp"] == ts

    def test_different_callers(self):
        """All valid callers should be accepted."""
        for caller in ("v7_runtime", "replay_tool", "paper_scan", "shadow"):
            req = build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                caller=caller,
            )
            assert req["caller"] == caller

    def test_invalid_mode_raises(self):
        """Invalid mode should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            build_analysis_request(
                mode="DAY_TRADING",
                symbol="BTCUSDT",
                model_scope="day_v1",
            )

    def test_invalid_caller_raises(self):
        """Invalid caller should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid caller"):
            build_analysis_request(
                mode="SWING",
                symbol="BTCUSDT",
                model_scope="swing_v1",
                caller="unknown_caller",
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

    def test_with_raw_signal(self):
        """Request with optional raw_signal payload."""
        signal = {"alpha_id": "funding_divergence", "strength": 0.75}
        req = build_analysis_request(
            mode="SWING",
            symbol="BTCUSDT",
            model_scope="swing_v1",
            raw_signal=signal,
        )
        assert req["raw_signal"] == signal

    def test_symbol_uppercased(self):
        """Symbol should be uppercased."""
        req = build_analysis_request(
            mode="SWING",
            symbol="btcusdt",
            model_scope="swing_v1",
        )
        assert req["symbol"] == "BTCUSDT"


class TestValidateAnalysisRequest:
    """Test validation of existing AnalysisRequest dicts."""

    def test_valid_fixture(self):
        """The canonical minimal fixture should validate clean."""
        req = {
            "request_id": "req_001",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        errors = validate_analysis_request(req)
        assert errors == []

    def test_missing_required_field(self):
        """Missing required field should produce error."""
        req = {
            "request_id": "req_001",
            "mode": "SWING",
            # Missing symbol
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        errors = validate_analysis_request(req)
        assert len(errors) > 0
        assert any("required" in e.lower() or "symbol" in e.lower() for e in errors)

    def test_mode_mismatch(self):
        """mode and requested_trade_mode should match."""
        req = {
            "request_id": "req_002",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SCALP",
            "model_scope": "swing_v1",
            "caller": "v7_runtime",
        }
        errors = validate_analysis_request(req)
        assert len(errors) > 0
        assert any("SWING" in e and "SCALP" in e for e in errors)

    def test_unknown_caller(self):
        """Unknown caller should be flagged."""
        req = {
            "request_id": "req_003",
            "mode": "SWING",
            "symbol": "BTCUSDT",
            "timestamp": "2026-06-01T12:00:00Z",
            "requested_trade_mode": "SWING",
            "model_scope": "swing_v1",
            "caller": "unknown_caller",
        }
        errors = validate_analysis_request(req)
        assert len(errors) > 0
        assert any("caller" in e.lower() for e in errors)
