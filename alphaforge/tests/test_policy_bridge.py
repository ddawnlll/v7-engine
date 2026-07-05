"""Tests for alphaforge.policy.bridge — V7 policy gate integration."""

from alphaforge.policy.bridge import evaluate_policy, MODE_POLICY


def _alpha(**overrides) -> dict:
    """Minimal alpha output from calibration."""
    base = {
        "calibrated_probabilities": {"long": 0.6, "short": 0.2, "no_trade": 0.2},
        "expected_r": {"long": 0.5, "short": -0.3},
        "alpha_scores": {"long_alpha_R": 0.25, "short_alpha_R": 0.0, "directional_edge_R": 0.5},
        "confidence": 0.7,
        "confidence_kind": "calibrated",
    }
    base.update(overrides)
    return base


class TestEvaluatePolicy:
    def test_long_wins(self):
        result = evaluate_policy(_alpha(), mode="SWING")
        assert result["recommended_action"] == "LONG_NOW"
        assert result["direction"] == "LONG"
        assert result["is_actionable"] is True

    def test_no_trade_low_confidence(self):
        result = evaluate_policy(_alpha(confidence=0.3), mode="SWING")
        assert result["recommended_action"] == "NO_TRADE"
        assert result["is_actionable"] is False
        assert "confidence" in result["decision_reason"]

    def test_no_trade_no_alpha_passes(self):
        """Both alpha scores below thresholds."""
        result = evaluate_policy(
            _alpha(alpha_scores={"long_alpha_R": 0.01, "short_alpha_R": 0.0, "directional_edge_R": 0.0}),
            mode="SWING",
        )
        assert result["recommended_action"] == "NO_TRADE"

    def test_short_wins_on_higher_alpha(self):
        result = evaluate_policy(
            _alpha(
                calibrated_probabilities={"long": 0.2, "short": 0.6, "no_trade": 0.2},
                expected_r={"long": -0.3, "short": 0.5},
                alpha_scores={"long_alpha_R": 0.0, "short_alpha_R": 0.25, "directional_edge_R": -0.5},
            ),
            mode="SWING",
        )
        assert result["recommended_action"] == "SHORT_NOW"

    def test_both_pass_picks_higher_alpha(self):
        """Both long and short pass → pick higher alpha."""
        result = evaluate_policy(
            _alpha(
                alpha_scores={"long_alpha_R": 0.30, "short_alpha_R": 0.25, "directional_edge_R": 0.5},
            ),
            mode="SWING",
        )
        assert result["recommended_action"] == "LONG_NOW"

    def test_regime_blocks_short(self):
        """TREND_UP regime soft-blocks SHORT."""
        result = evaluate_policy(
            _alpha(
                calibrated_probabilities={"long": 0.2, "short": 0.7, "no_trade": 0.1},
                expected_r={"long": -0.3, "short": 0.5},
                alpha_scores={"long_alpha_R": 0.0, "short_alpha_R": 0.35, "directional_edge_R": -0.5},
            ),
            mode="SWING", regime="TREND_UP",
        )
        # Short is blocked by regime, long doesn't pass → NO_TRADE
        assert result["recommended_action"] == "NO_TRADE"
        assert result["policy"]["regime_constraints"]

    def test_gate_results_tracked(self):
        result = evaluate_policy(_alpha(confidence=0.3), mode="SWING")
        gates = result["policy"]["gates"]
        assert "confidence_gate" in gates
        assert "long_alpha_gate" in gates

    def test_threshold_override(self):
        """Override min_confidence to a lower value."""
        result = evaluate_policy(
            _alpha(confidence=0.5),
            mode="SWING", min_confidence=0.4,
        )
        assert result["recommended_action"] == "LONG_NOW"

    def test_scalp_mode(self):
        result = evaluate_policy(
            _alpha(
                calibrated_probabilities={"long": 0.55, "short": 0.25, "no_trade": 0.2},
                expected_r={"long": 0.2, "short": -0.1},
                alpha_scores={"long_alpha_R": 0.08, "short_alpha_R": 0.0, "directional_edge_R": 0.2},
            ),
            mode="SCALP",
        )
        # SCALP: min_confidence=0.60, confidence=0.55 < 0.60 → NO_TRADE
        assert result["recommended_action"] == "NO_TRADE"

    def test_aggressive_scalp(self):
        result = evaluate_policy(
            _alpha(
                calibrated_probabilities={"long": 0.7, "short": 0.1, "no_trade": 0.2},
                expected_r={"long": 0.1, "short": -0.05},
                alpha_scores={"long_alpha_R": 0.07, "short_alpha_R": 0.0, "directional_edge_R": 0.15},
            ),
            mode="AGGRESSIVE_SCALP",
        )
        # min_confidence=0.65, confidence=0.7 >= 0.65 ✓
        # min_long_alpha_R=0.06, long_alpha=0.07 >= 0.06 ✓
        # require_expected_R_above=0.08, exp_r_long=0.1 >= 0.08 ✓
        assert result["recommended_action"] == "LONG_NOW"

    def test_no_trade_no_actionable(self):
        result = evaluate_policy(_alpha(), mode="SWING")
        assert result["is_actionable"] == (result["recommended_action"] != "NO_TRADE")
