"""Tests for v7 pipeline — model registry + AnalysisResult builder."""

from v7.pipeline import ModelRegistry, build_analysis_result


class TestModelRegistry:
    def test_register_and_get(self):
        reg = ModelRegistry()
        reg.register("SWING", "fold_0", {"model": "test"})
        bundle = reg.get("SWING", "fold_0")
        assert bundle == {"model": "test"}

    def test_get_latest_fold(self):
        reg = ModelRegistry()
        reg.register("SWING", "fold_0", {"model": "v0"})
        reg.register("SWING", "fold_1", {"model": "v1"})
        bundle = reg.get("SWING")  # no fold specified → latest
        assert bundle == {"model": "v1"}

    def test_get_unknown_mode(self):
        reg = ModelRegistry()
        assert reg.get("UNKNOWN") is None

    def test_list_modes(self):
        reg = ModelRegistry()
        reg.register("SWING", "f0", {})
        reg.register("SCALP", "f0", {})
        assert reg.list_modes() == ["SCALP", "SWING"]


class TestBuildAnalysisResult:
    def test_actionable_long(self):
        alpha = {
            "calibrated_probabilities": {"long": 0.7, "short": 0.1, "no_trade": 0.2},
            "expected_r": {"long": 0.5, "short": -0.3},
            "alpha_scores": {"long_alpha_R": 0.3, "short_alpha_R": 0.0, "directional_edge_R": 0.5},
            "confidence": 0.8,
            "confidence_kind": "calibrated",
        }
        policy = {
            "recommended_action": "LONG_NOW",
            "direction": "LONG",
            "is_actionable": True,
            "confidence": 0.8,
            "confidence_kind": "calibrated",
            "decision_reason": "alpha_long_wins",
            "scores": {"long_alpha_R": 0.3, "short_alpha_R": 0.0},
            "policy": {"mode": "SWING"},
        }
        result = build_analysis_result(alpha, policy, "BTCUSDT", "SWING", "2026-01-01T00:00:00Z")
        assert result["symbol"] == "BTCUSDT"
        assert result["decision"]["recommended_action"] == "LONG_NOW"
        assert result["status"]["is_actionable"] is True
        assert result["status"]["signal_status"] == "SIGNAL"
        assert result["engine_name"] == "v7_alphaforge_xgb"

    def test_not_actionable(self):
        alpha = {"calibrated_probabilities": {"long": 0.3, "short": 0.2, "no_trade": 0.5},
                 "expected_r": {"long": 0.0, "short": 0.0},
                 "alpha_scores": {"long_alpha_R": 0.0, "short_alpha_R": 0.0, "directional_edge_R": 0.0},
                 "confidence": 0.3, "confidence_kind": "raw"}
        policy = {"recommended_action": "NO_TRADE", "direction": "NONE", "is_actionable": False,
                  "confidence": 0.3, "confidence_kind": "raw", "decision_reason": "confidence_below_threshold",
                  "scores": {}, "policy": {}}
        result = build_analysis_result(alpha, policy, "ETHUSDT", "SCALP", "2026-01-01T00:00:00Z")
        assert result["status"]["signal_status"] == "NO_TRADE"
        assert result["status"]["is_actionable"] is False
