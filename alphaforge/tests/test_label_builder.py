"""Tests for alphaforge.labels.builder — SimulationOutput to AlphaForgeLabel."""

import pytest
from alphaforge.labels.builder import AlphaForgeError, build_label, build_labels


def _make_sim_output(**overrides) -> dict:
    """Create a minimal valid SimulationOutput dict."""
    base = {
        "symbol": "BTCUSDT",
        "decision_timestamp": "2026-06-01T12:00:00Z",
        "mode": "SWING",
        "primary_interval": "4h",
        "resolution_status": "COMPLETE",
        "is_ambiguous": False,
        "best_action": "LONG_NOW",
        "action_gap_r": 0.5,
        "regret_r": 0.0,
        "lineage": {
            "simulation_family_version": "simfam-1.0.0",
        },
        "long_outcome": {
            "realized_r_net": 1.0,
            "path_metrics": {
                "mfe_r": 2.0,
                "mae_r": -0.3,
                "path_quality_score": 0.85,
            },
        },
        "short_outcome": {
            "realized_r_net": -0.5,
            "path_metrics": {
                "mfe_r": 0.0,
                "mae_r": -1.5,
                "path_quality_score": 0.0,
            },
        },
        "no_trade_outcome": {
            "saved_loss_score": 0.5,
            "missed_opportunity_score": 0.0,
        },
    }
    base.update(overrides)
    return base


# ── Classification ──────────────────────────────────────────────────

class TestClassification:
    def test_long_now(self):
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 1.0},
            short_outcome={"realized_r_net": -0.5},
            mode="SWING",
        ))
        assert label["best_action_label"] == "LONG_NOW"
        assert label["label_validity"] == "VALID"

    def test_short_now(self):
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": -0.5},
            short_outcome={"realized_r_net": 1.0},
            mode="SWING",
        ))
        assert label["best_action_label"] == "SHORT_NOW"
        assert label["label_validity"] == "VALID"

    def test_no_trade_below_min_edge(self):
        """Best R below min_action_edge_r → NO_TRADE.
        Gap must be >= ambiguity_margin (0.20 for SWING) to not short-circuit."""
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 0.30},
            short_outcome={"realized_r_net": 0.00},
            mode="SWING",
        ), min_action_edge_r=0.35)
        # gap = 0.30 >= 0.20, best_r = 0.30 < 0.35 → NO_TRADE
        assert label["best_action_label"] == "NO_TRADE"

    def test_ambiguous_gap(self):
        """Gap below ambiguity_margin_r → AMBIGUOUS_STATE."""
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 0.4},
            short_outcome={"realized_r_net": 0.35},
            mode="SWING",
        ), ambiguity_margin_r=0.20)
        # gap = 0.05 < 0.20 → ambiguous
        assert label["best_action_label"] == "AMBIGUOUS_STATE"
        assert label["label_validity"] == "AMBIGUOUS"

    def test_ambiguous_flag_from_simulation(self):
        """is_ambiguous=True → AMBIGUOUS_STATE regardless of gap."""
        label = build_label(_make_sim_output(is_ambiguous=True))
        assert label["best_action_label"] == "AMBIGUOUS_STATE"
        assert label["label_validity"] == "AMBIGUOUS"

    def test_unresolved_invalid(self):
        """UNRESOLVED resolution → INVALID."""
        label = build_label(_make_sim_output(resolution_status="UNRESOLVED"))
        assert label["label_validity"] == "INVALID"
        assert label["best_action_label"] == "INVALID_OR_UNRESOLVED"

    def test_invalidated(self):
        label = build_label(_make_sim_output(resolution_status="INVALIDATED"))
        assert label["label_validity"] == "INVALID"

    def test_scalp_thresholds(self):
        """SCALP uses tighter thresholds."""
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 0.2},
            short_outcome={"realized_r_net": -0.1},
            mode="SCALP",
        ))
        # SCALP min_action_edge = 0.15, gap = 0.3
        # best_r = 0.2 >= 0.15, gap = 0.3 >= 0.10
        # long > short → LONG_NOW
        assert label["best_action_label"] == "LONG_NOW"

    def test_aggressive_scalp_thresholds(self):
        """AGGRESSIVE_SCALP has tightest thresholds, defaults to NO_TRADE."""
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 0.06},
            short_outcome={"realized_r_net": -0.04},
            mode="AGGRESSIVE_SCALP",
        ))
        # min_action_edge = 0.08, best_r = 0.06 < 0.08 → NO_TRADE
        assert label["best_action_label"] == "NO_TRADE"


# ── Required fields ─────────────────────────────────────────────────

class TestRequiredFields:
    def test_all_required_present(self):
        label = build_label(_make_sim_output())
        assert label["symbol"] == "BTCUSDT"
        assert label["timestamp"] == "2026-06-01T12:00:00Z"
        assert label["mode"] == "SWING"
        assert label["label_interpretation_version"] == "labelint-1.0.0"
        assert label["long_R_net"] == 1.0
        assert label["short_R_net"] == -0.5
        assert label["best_action_label"] in ("LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE")
        assert label["label_validity"] in ("VALID", "AMBIGUOUS", "INVALID")

    def test_missing_realized_r_raises(self):
        with pytest.raises(AlphaForgeError):
            build_label(_make_sim_output(
                long_outcome={},
                short_outcome={},
            ))


# ── Optional fields ─────────────────────────────────────────────────

class TestOptionalFields:
    def test_path_metrics_included(self):
        label = build_label(_make_sim_output())
        assert label.get("long_mae_R") == -0.3
        assert label.get("long_mfe_R") == 2.0
        assert label.get("short_mae_R") == -1.5
        assert label.get("short_mfe_R") == 0.0

    def test_path_quality_uses_best_action(self):
        label = build_label(_make_sim_output(best_action="LONG_NOW"))
        assert label.get("path_quality_score") == 0.85

    def test_path_quality_short(self):
        label = build_label(_make_sim_output(
            best_action="SHORT_NOW",
            short_outcome={"realized_r_net": 1.0, "path_metrics": {"path_quality_score": 0.6}},
            long_outcome={"realized_r_net": -0.5, "path_metrics": {"path_quality_score": 0.2}},
        ))
        assert label.get("path_quality_score") == 0.6

    def test_no_trade_fields(self):
        label = build_label(_make_sim_output())
        assert label.get("saved_loss_score") == 0.5
        assert label.get("missed_opportunity_score") == 0.0

    def test_action_gap_and_regret(self):
        label = build_label(_make_sim_output(action_gap_r=0.35, regret_r=0.1))
        assert label.get("action_gap_R") == 0.35
        assert label.get("regret_R") == 0.1

    def test_missing_optionals_omitted(self):
        label = build_label(_make_sim_output(
            long_outcome={"realized_r_net": 1.0, "path_metrics": {}},
            short_outcome={"realized_r_net": -0.5, "path_metrics": {}},
            no_trade_outcome={},
        ))
        assert "long_mae_R" not in label
        assert "saved_loss_score" not in label


# ── batch build_labels ─────────────────────────────────────────────

class TestBatchBuild:
    def test_multiple_outputs(self):
        outputs = [_make_sim_output() for _ in range(3)]
        labels = build_labels(outputs)
        assert len(labels) == 3
        for label in labels:
            assert label["best_action_label"] == "LONG_NOW"

    def test_empty(self):
        assert build_labels([]) == []


# ── Mode defaults ───────────────────────────────────────────────────

class TestModeDefaults:
    def test_unknown_mode_falls_back(self):
        """Unknown mode → sensible defaults."""
        label = build_label(_make_sim_output(
            mode="UNKNOWN",
            long_outcome={"realized_r_net": 0.2},
            short_outcome={"realized_r_net": 0.0},
        ))
        # Falls back to min_action_edge=0.15, best_r=0.2 >= 0.15
        assert label["best_action_label"] == "LONG_NOW"
