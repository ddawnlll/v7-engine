"""Tests for small runtime services: observability, signal_features, engine_manifest,
improvement_registry, improvement_analytics, trace_service, attribution_integrity,
swing_patch_validation, decision_attribution."""

import json
from unittest.mock import MagicMock
from runtime.services.signal_features import build_signal_feature_vector, merge_labeled_outcome
from runtime.services.engine_manifest_service import EngineManifestService
from runtime.services.improvement_registry_service import register_component, DEFAULT_COMPONENTS
from runtime.services.improvement_analytics_service import ImprovementAnalyticsService
from runtime.services.trace_service import TraceService
from runtime.services.attribution_integrity_service import AttributionIntegrityService
from runtime.services.swing_patch_validation_service import SwingPatchValidationService


# ── observability ──────────────────────────────────────────────────

class TestLogEvent:
    def test_log_event_output(self, capsys):
        from runtime.services.observability import log_event
        log_event("test_event", key="value")
        captured = capsys.readouterr()
        payload = json.loads(captured.out.strip())
        assert payload["event"] == "test_event"
        assert payload["key"] == "value"
        assert "timestamp" in payload
        assert "pid" in payload


# ── signal_features ────────────────────────────────────────────────

class TestBuildSignalFeatureVector:
    def test_basic(self):
        signal = {
            "symbol": "BTCUSDT", "interval": "4h", "mode": "SWING",
            "direction": "LONG", "regime": "TRENDING", "trend": "BULLISH",
            "trend_strength": 0.8, "confidence_raw": 0.6, "confidence": 0.7,
            "probability_raw": 0.55, "probability": 0.65, "expected_value": 0.3,
            "risk_reward": 2.0,
            "advanced_analysis": {"probability_model": {"component_scores": {"trend": 0.8}}},
        }
        snapshot = {"atr": 100.0, "rsi": 55.0, "vol_ratio": 1.2}
        result = build_signal_feature_vector(signal, snapshot)
        assert result["symbol"] == "BTCUSDT"
        assert result["confidence_raw"] == 0.6
        assert result["atr"] == 100.0
        assert result["rsi"] == 55.0
        assert result["component_scores"] == {"trend": 0.8}

    def test_missing_optional(self):
        result = build_signal_feature_vector({}, {})
        assert result["symbol"] is None
        assert result["atr"] is None


class TestMergeLabeledOutcome:
    def test_win(self):
        features = {"symbol": "BTCUSDT"}
        outcome = {"realized_r": 0.5, "status": "CLOSED", "close_reason": "TARGET"}
        result = merge_labeled_outcome(features, outcome)
        assert result["outcome_label"] == "WIN"
        assert result["realized_r"] == 0.5

    def test_loss(self):
        result = merge_labeled_outcome({}, {"realized_r": -0.5})
        assert result["outcome_label"] == "LOSS"

    def test_no_features(self):
        result = merge_labeled_outcome(None, {"realized_r": 0.0})
        assert result["outcome_label"] == "FLAT"

    def test_preserves_features(self):
        result = merge_labeled_outcome({"symbol": "BTC"}, {"realized_r": 1.0})
        assert result["symbol"] == "BTC"


# ── engine_manifest_service ────────────────────────────────────────

class TestEngineManifest:
    def _service(self):
        return EngineManifestService(registry_service=MagicMock())

    def test_param_hash(self):
        h1 = EngineManifestService._param_hash({"a": 1}, {"b": True})
        h2 = EngineManifestService._param_hash({"a": 1}, {"b": True})
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 40

    def test_param_hash_different(self):
        h1 = EngineManifestService._param_hash({"a": 1}, {})
        h2 = EngineManifestService._param_hash({"a": 2}, {})
        assert h1 != h2

    def test_change_creation(self):
        current = {"run_id": "r1", "started_at_utc": "2026-01-01T00:00:00Z"}
        result = EngineManifestService._change("component_enabled", "c1", None, {"version": "1.0"}, current)
        assert result["change_type"] == "component_enabled"
        assert result["change_reason"] == "component enabled"
        assert result["change_id"].startswith("chg-")

    def test_compute_changes_none_prior(self):
        svc = self._service()
        changes = svc._compute_changes({"run_id": "r1", "enabled_component_ids": ["a"], "component_snapshot": [{"component_id": "a", "version": "1"}]}, None)
        assert changes == []

    def test_compute_changes_enabled_component(self):
        svc = self._service()
        current = {"run_id": "r2", "started_at_utc": "2026-01-02T00:00:00Z", "enabled_component_ids": ["a", "b"], "component_snapshot": [{"component_id": "a", "version": "1"}, {"component_id": "b", "version": "1"}]}
        prior = {"run_id": "r1", "started_at_utc": "2026-01-01T00:00:00Z", "enabled_component_ids": ["a"], "component_snapshot": [{"component_id": "a", "version": "1"}]}
        changes = svc._compute_changes(current, prior)
        # Both component_enabled + component_added are generated for the same component
        assert any(c["change_type"] == "component_enabled" and c["component_id"] == "b" for c in changes)
        assert any(c["change_type"] == "component_added" and c["component_id"] == "b" for c in changes)

    def test_compute_changes_disabled_component(self):
        svc = self._service()
        current = {"run_id": "r2", "started_at_utc": "2026-01-02T00:00:00Z", "enabled_component_ids": ["a"], "component_snapshot": [{"component_id": "a", "version": "1"}]}
        prior = {"run_id": "r1", "started_at_utc": "2026-01-01T00:00:00Z", "enabled_component_ids": ["a", "b"], "component_snapshot": [{"component_id": "a", "version": "1"}, {"component_id": "b", "version": "1"}]}
        changes = svc._compute_changes(current, prior)
        assert len(changes) == 1
        assert changes[0]["change_type"] == "component_disabled"

    def test_compute_changes_version_change(self):
        svc = self._service()
        current = {"run_id": "r2", "started_at_utc": "2026-01-02T00:00:00Z", "enabled_component_ids": ["a"], "component_snapshot": [{"component_id": "a", "version": "2"}]}
        prior = {"run_id": "r1", "started_at_utc": "2026-01-01T00:00:00Z", "enabled_component_ids": ["a"], "component_snapshot": [{"component_id": "a", "version": "1"}]}
        changes = svc._compute_changes(current, prior)
        assert len(changes) == 1
        assert changes[0]["change_type"] == "version_replaced"

    def test_param_hash_change_detected(self):
        svc = self._service()
        current = {"run_id": "r2", "started_at_utc": "2026-01-02T00:00:00Z", "enabled_component_ids": [], "component_snapshot": [], "param_hash": "abc"}
        prior = {"run_id": "r1", "started_at_utc": "2026-01-01T00:00:00Z", "enabled_component_ids": [], "component_snapshot": [], "param_hash": "def"}
        changes = svc._compute_changes(current, prior)
        assert any(c["change_type"] == "parameter_changed" for c in changes)


# ── improvement_registry_service ──────────────────────────────────

class TestImprovementRegistry:
    def test_register_component(self):
        result = register_component({"component_id": "test_comp", "component_name": "Test", "module_path": "mod", "object_name": "obj", "version": "v1"})
        assert result["component_id"] == "test_comp"
        assert result["status"] == "ACTIVE"
        assert "implementation_fingerprint" in result
        # Clean up
        from runtime.services.improvement_registry_service import REGISTRY
        REGISTRY.pop("test_comp", None)

    def test_default_components_have_required_fields(self):
        for comp in DEFAULT_COMPONENTS:
            assert "component_id" in comp
            assert "component_type" in comp
            assert "version" in comp


# ── improvement_analytics_service ──────────────────────────────────

class TestImprovementAnalytics:
    def test_sample_reliability(self):
        assert ImprovementAnalyticsService._sample_reliability(0, 10) == "LOW_SAMPLE"
        assert ImprovementAnalyticsService._sample_reliability(3, 10) == "LOW_SAMPLE"
        assert ImprovementAnalyticsService._sample_reliability(7, 10) == "BUILDING_SAMPLE"
        assert ImprovementAnalyticsService._sample_reliability(12, 10) == "MIXED"
        assert ImprovementAnalyticsService._sample_reliability(25, 10) == "STABLE"

    def test_confidence_bucket(self):
        assert ImprovementAnalyticsService._confidence_bucket(55.0) == "50-60"
        assert ImprovementAnalyticsService._confidence_bucket(75.0) == "70-80"
        assert ImprovementAnalyticsService._confidence_bucket(0.0) == "0-10"
        assert ImprovementAnalyticsService._confidence_bucket(95.0) == "90-100"

    def test_avg_r(self):
        rows = [{"realized_r": 1.0}, {"realized_r": -0.5}, {"realized_r": 2.0}]
        assert ImprovementAnalyticsService._avg_r(rows) == 2.5 / 3

    def test_avg_r_empty(self):
        assert ImprovementAnalyticsService._avg_r([]) == 0.0

    def test_profit_factor(self):
        rows = [{"realized_r": 2.0}, {"realized_r": -0.5}]
        assert ImprovementAnalyticsService._profit_factor(rows) == 4.0

    def test_max_drawdown(self):
        rows = [{"realized_r": 3.0, "created_at_utc": "2026-01-01T00:00:00Z"},
                {"realized_r": -1.0, "created_at_utc": "2026-01-02T00:00:00Z"}]
        # equity: 3 -> 2, peak=3, dd = equity-peak = -1, abs = 1
        assert ImprovementAnalyticsService._max_drawdown(rows) == 1.0

    def test_distribution(self):
        rows = [{"failure_source": "A"}, {"failure_source": "A"}, {"failure_source": "B"}]
        assert ImprovementAnalyticsService._distribution(rows, "failure_source") == {"A": 2, "B": 1}

    def test_recommend(self):
        row = {"component_id": "c1", "label": "C1", "avg_realized_r": 0.5, "expectancy_delta_vs_baseline": 0.3, "sample_reliability": "STABLE"}
        result = ImprovementAnalyticsService._recommend(row, "PROMOTE", "good")
        assert result["action"] == "PROMOTE"
        assert result["avg_realized_r"] == 0.5

    def test_get_recent_changes(self):
        changes = [{"component_id": "c1", "change_type": "component_enabled"}]
        result = ImprovementAnalyticsService.get_recent_changes(changes)
        assert result["by_change_type"]["component_enabled"] == 1
        assert len(result["items"]) == 1

    def test_aggregate_group(self):
        rows = [{"trades_affected": 10, "avg_realized_r": 0.5}, {"trades_affected": 5, "avg_realized_r": 0.3}]
        # Just test it doesn't crash
        result = ImprovementAnalyticsService._aggregate_group(rows, "component_type")
        assert isinstance(result, list)

    def test_safety_notes(self):
        assert ImprovementAnalyticsService._safety_notes({"provisional": True, "summary": "test"}) != []
        assert ImprovementAnalyticsService._safety_notes({"provisional": False}) == []


# ── trace_service ──────────────────────────────────────────────────

class TestTraceService:
    def test_imports(self):
        from runtime.services.trace_service import TraceService
        assert TraceService is not None


# ── attribution_integrity_service ──────────────────────────────────

class TestAttributionIntegrity:
    def test_evaluate_empty(self):
        service = AttributionIntegrityService()
        # Just test import and basic instantiation
        assert service is not None
        assert hasattr(service, "evaluate")


# ── swing_patch_validation_service ─────────────────────────────────

class TestSwingPatchValidation:
    def test_imports(self):
        svc = SwingPatchValidationService()
        assert svc is not None
