"""
V7 pipeline — bridges model evidence to V7 runtime decisions.

This module is the final integration layer. It:
1. Receives market state from V7 runtime
2. Runs model inference + calibration
3. Applies policy gates
4. Returns AnalysisResult-compatible dict to runtime

Domain boundary: V7 owns policy acceptance.
AlphaForge imports are lazy (inside function bodies) to respect boundary.
"""
from __future__ import annotations

from typing import Any


# ── Placeholder model registry ─────────────────────────────────────

class ModelRegistry:
    """Holds trained AlphaForge model bundles keyed by (mode, fold_id).

    In production, this loads artifacts from disk/registry.
    """

    def __init__(self):
        self._bundles: dict[str, dict[str, Any]] = {}

    def register(self, mode: str, fold_id: str, bundle: dict[str, Any]) -> None:
        key = f"{mode}_{fold_id}"
        self._bundles[key] = bundle

    def get(self, mode: str, fold_id: str = "latest") -> dict[str, Any] | None:
        key = f"{mode}_{fold_id}"
        if key in self._bundles:
            return self._bundles[key]
        # Fallback: find the latest fold for this mode
        candidates = {k: v for k, v in self._bundles.items() if k.startswith(f"{mode}_")}
        if not candidates:
            return None
        return candidates[sorted(candidates.keys())[-1]]

    def list_modes(self) -> list[str]:
        modes: set[str] = set()
        for key in self._bundles:
            modes.add(key.split("_")[0])
        return sorted(modes)


# ── Inference pipeline ─────────────────────────────────────────────

def build_analysis_result(
    alpha_output: dict[str, Any],
    policy_result: dict[str, Any],
    symbol: str,
    mode: str,
    timestamp: str,
) -> dict[str, Any]:
    """Build an AnalysisResult-compatible dict from alpha + policy outputs.

    Args:
        alpha_output: Output from alphaforge.calibration.engine.predict_calibrated.
        policy_result: Output from alphaforge.policy.bridge.evaluate_policy.
        symbol: Trading symbol.
        mode: Trading mode.
        timestamp: Decision timestamp.

    Returns:
        AnalysisResult dict compatible with V7 runtime contracts.
    """
    cal = alpha_output.get("calibrated_probabilities", {})
    scores = policy_result.get("scores", {})

    return {
        "symbol": symbol,
        "mode": mode,
        "decision_timestamp": timestamp,
        "contract_version": "v7-analysis-result-1.0.0",
        "engine_name": "v7_alphaforge_xgb",
        "engine_version": "v1",
        "status": {
            "signal_status": "SIGNAL" if policy_result.get("is_actionable") else "NO_TRADE",
            "decision_status": "VALID" if policy_result.get("is_actionable") else "FILTERED",
            "is_actionable": policy_result.get("is_actionable", False),
        },
        "decision": {
            "recommended_action": policy_result.get("recommended_action", "NO_TRADE"),
            "direction": policy_result.get("direction", "NONE"),
            "decision_summary": policy_result.get("decision_reason", ""),
        },
        "scores": {
            "confidence": policy_result.get("confidence", 0.0),
            "confidence_kind": policy_result.get("confidence_kind", "raw"),
            "probability": {
                "long": cal.get("long", 0.0),
                "short": cal.get("short", 0.0),
                "no_trade": cal.get("no_trade", 0.0),
            },
            "expected_r": scores.get("expected_r_long", 0.0),
            "long_score": scores.get("long_alpha_R", 0.0),
            "short_score": scores.get("short_alpha_R", 0.0),
        },
        "policy": policy_result.get("policy", {}),
    }


def run_inference(
    features: dict[str, float],
    feature_keys: list[str],
    model_bundle: dict[str, Any],
    mode: str = "SWING",
    regime: str | None = None,
    symbol: str = "",
    timestamp: str = "",
    calibrator=None,
) -> dict[str, Any]:
    """Run full inference: predict → calibrate → policy → AnalysisResult.

    Args:
        features: Feature name → value dict.
        feature_keys: Ordered feature keys matching training.
        model_bundle: Bundle from ModelTrainer.train_fold().
        mode: Trading mode.
        regime: Optional regime label.
        symbol: Trading symbol.
        timestamp: Decision timestamp.
        calibrator: Optional fitted Calibrator.

    Returns:
        AnalysisResult-compatible dict.
    """
    import importlib
    cal = importlib.import_module("alphaforge.calibration.engine")
    pol = importlib.import_module("alphaforge.policy.bridge")

    alpha_output = cal.predict_calibrated(model_bundle, features, feature_keys, calibrator)
    policy_result = pol.evaluate_policy(alpha_output, mode=mode, regime=regime)
    return build_analysis_result(alpha_output, policy_result, symbol, mode, timestamp)
