"""Tests for LabelAdapter NO_TRADE quality classification and best action labels.

WS-02-NO-TRADE-TESTS: verify classify_no_trade_quality() returns correct category
for all 4 NO_TRADE quality types, test best_action_label mappings, deterministic
output, and label_validity filtering.
"""

import copy
import json
from pathlib import Path

import pytest

from alphaforge.labels.adapter import (
    LabelAdapter,
    NoTradeQuality,
    LabelValidity,
    adapt_simulation_output,
    classify_no_trade_quality,
    _REQUIRED_SIM_FIELDS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "fixtures"


def _load_sim_fixture() -> dict:
    """Load the minimal SimulationOutput fixture."""
    path = FIXTURE_DIR / "simulation_output_minimal.json"
    with open(path) as f:
        return json.load(f)


def _make_sim_fixture(**overrides) -> dict:
    """Return a deep-copied minimal SimulationOutput with optional overrides."""
    sim = copy.deepcopy(_load_sim_fixture())
    sim.update(overrides)
    return sim


# ---------------------------------------------------------------------------
# classify_no_trade_quality tests (AC-02-017 through AC-02-020)
# ---------------------------------------------------------------------------

class TestClassifyNoTradeQuality:
    """Tests for the classify_no_trade_quality() function."""

    def test_correct_no_trade_when_correct_skip_and_low_scores(self):
        """AC-02-017: CORRECT_NO_TRADE when was_correct_skip=True, both scores < 0.3."""
        result = classify_no_trade_quality({
            "was_correct_skip": True,
            "saved_loss_score": 0.1,
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 0.0,
            "missed_opportunity_r": 0.0,
            "no_trade_quality": "CORRECT_NO_TRADE",
        })
        assert result == NoTradeQuality.CORRECT_NO_TRADE.value

    def test_correct_no_trade_with_zero_scores(self):
        """CORRECT_NO_TRADE when both scores are exactly 0."""
        result = classify_no_trade_quality({
            "was_correct_skip": True,
            "saved_loss_score": 0.0,
            "missed_opportunity_score": 0.0,
            "saved_loss_r": 0.0,
            "missed_opportunity_r": 0.0,
            "no_trade_quality": "CORRECT_NO_TRADE",
        })
        assert result == NoTradeQuality.CORRECT_NO_TRADE.value

    def test_saved_loss_when_saved_high_and_missed_low(self):
        """AC-02-018: SAVED_LOSS when saved_loss_score >= 0.5 and > missed_opportunity_score."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.65,
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 1.3,
            "missed_opportunity_r": 0.1,
            "no_trade_quality": "SAVED_LOSS",
        })
        assert result == NoTradeQuality.SAVED_LOSS.value

    def test_saved_loss_exact_threshold(self):
        """SAVED_LOSS at exact threshold 0.5."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.5,
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 1.0,
            "missed_opportunity_r": 0.1,
            "no_trade_quality": "SAVED_LOSS",
        })
        assert result == NoTradeQuality.SAVED_LOSS.value

    def test_missed_opportunity_when_missed_high_and_saved_low(self):
        """AC-02-019: MISSED_OPPORTUNITY when missed_opportunity_score >= 0.5 and > saved_loss_score."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.1,
            "missed_opportunity_score": 0.75,
            "saved_loss_r": 0.1,
            "missed_opportunity_r": 1.5,
            "no_trade_quality": "MISSED_OPPORTUNITY",
        })
        assert result == NoTradeQuality.MISSED_OPPORTUNITY.value

    def test_missed_opportunity_exact_threshold(self):
        """MISSED_OPPORTUNITY at exact threshold 0.5."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.1,
            "missed_opportunity_score": 0.5,
            "saved_loss_r": 0.1,
            "missed_opportunity_r": 1.0,
            "no_trade_quality": "MISSED_OPPORTUNITY",
        })
        assert result == NoTradeQuality.MISSED_OPPORTUNITY.value

    def test_ambiguous_no_trade_scores_within_margin(self):
        """AC-02-020: AMBIGUOUS_NO_TRADE when |diff| < 0.2 and both < 0.5."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.35,
            "missed_opportunity_score": 0.40,
            "saved_loss_r": 0.35,
            "missed_opportunity_r": 0.40,
            "no_trade_quality": "AMBIGUOUS_NO_TRADE",
        })
        assert result == NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    def test_ambiguous_no_trade_equal_scores(self):
        """AMBIGUOUS_NO_TRADE when scores are equal."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.3,
            "missed_opportunity_score": 0.3,
            "saved_loss_r": 0.3,
            "missed_opportunity_r": 0.3,
            "no_trade_quality": "AMBIGUOUS_NO_TRADE",
        })
        assert result == NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    def test_ambiguous_no_trade_high_equal_scores(self):
        """AMBIGUOUS_NO_TRADE when both scores are high and equal (>= 0.5)."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.6,
            "missed_opportunity_score": 0.6,
            "saved_loss_r": 1.2,
            "missed_opportunity_r": 1.2,
            "no_trade_quality": "AMBIGUOUS_NO_TRADE",
        })
        assert result == NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    def test_edge_case_missing_fields_default_to_zero(self):
        """Missing optional fields default to 0 — should produce AMBIGUOUS_NO_TRADE."""
        result = classify_no_trade_quality({})
        assert result == NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    def test_edge_case_negative_scores(self):
        """Negative scores (if allowed) — treat as AMBIGUOUS_NO_TRADE."""
        result = classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": -0.1,
            "missed_opportunity_score": -0.1,
            "saved_loss_r": -0.1,
            "missed_opportunity_r": -0.1,
            "no_trade_quality": "AMBIGUOUS_NO_TRADE",
        })
        assert result == NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    def test_saved_loss_takes_priority_over_correct(self):
        """SAVED_LOSS trumps CORRECT_NO_TRADE when was_correct_skip=True but score high."""
        result = classify_no_trade_quality({
            "was_correct_skip": True,  # would be correct, but...
            "saved_loss_score": 0.8,   # score is very high
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 1.6,
            "missed_opportunity_r": 0.1,
            "no_trade_quality": "SAVED_LOSS",
        })
        assert result == NoTradeQuality.SAVED_LOSS.value

    def test_all_four_categories_returned(self):
        """Verify all four NO_TRADE quality categories can be produced."""
        categories_found = set()

        # CORRECT_NO_TRADE
        categories_found.add(classify_no_trade_quality({
            "was_correct_skip": True,
            "saved_loss_score": 0.1,
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 0.1,
            "missed_opportunity_r": 0.1,
            "no_trade_quality": "CORRECT_NO_TRADE",
        }))

        # SAVED_LOSS
        categories_found.add(classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.6,
            "missed_opportunity_score": 0.1,
            "saved_loss_r": 1.2,
            "missed_opportunity_r": 0.1,
            "no_trade_quality": "SAVED_LOSS",
        }))

        # MISSED_OPPORTUNITY
        categories_found.add(classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.1,
            "missed_opportunity_score": 0.7,
            "saved_loss_r": 0.1,
            "missed_opportunity_r": 1.4,
            "no_trade_quality": "MISSED_OPPORTUNITY",
        }))

        # AMBIGUOUS_NO_TRADE
        categories_found.add(classify_no_trade_quality({
            "was_correct_skip": False,
            "saved_loss_score": 0.3,
            "missed_opportunity_score": 0.3,
            "saved_loss_r": 0.3,
            "missed_opportunity_r": 0.3,
            "no_trade_quality": "AMBIGUOUS_NO_TRADE",
        }))

        expected = {
            NoTradeQuality.CORRECT_NO_TRADE.value,
            NoTradeQuality.SAVED_LOSS.value,
            NoTradeQuality.MISSED_OPPORTUNITY.value,
            NoTradeQuality.AMBIGUOUS_NO_TRADE.value,
        }
        assert categories_found == expected


# ---------------------------------------------------------------------------
# best_action_label tests (AC-02-021)
# ---------------------------------------------------------------------------

class TestBestActionLabel:
    """Tests for best_action_label mapping."""

    def test_long_now_action(self):
        """AC-02-021: best_action_label = LONG_NOW."""
        sim = _make_sim_fixture(best_action="LONG_NOW")
        label = adapt_simulation_output(sim)
        assert label["best_action_label"] == "LONG_NOW"

    def test_short_now_action(self):
        """AC-02-021: best_action_label = SHORT_NOW."""
        sim = _make_sim_fixture(best_action="SHORT_NOW")
        label = adapt_simulation_output(sim)
        assert label["best_action_label"] == "SHORT_NOW"

    def test_no_trade_action(self):
        """AC-02-021: best_action_label = NO_TRADE."""
        sim = _make_sim_fixture(best_action="NO_TRADE")
        label = adapt_simulation_output(sim)
        assert label["best_action_label"] == "NO_TRADE"

    def test_ambiguous_state_action(self):
        """AC-02-021: best_action_label = AMBIGUOUS_STATE."""
        sim = _make_sim_fixture(best_action="AMBIGUOUS_STATE")
        label = adapt_simulation_output(sim)
        assert label["best_action_label"] == "AMBIGUOUS_STATE"

    def test_best_action_after_cost_populated(self):
        """best_action_after_cost is populated when cost fields are present."""
        sim = _make_sim_fixture(best_action="LONG_NOW")
        label = adapt_simulation_output(sim)
        assert "best_action_after_cost" in label
        assert label["best_action_after_cost"] in (
            "LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"
        )

    def test_best_action_after_cost_no_trade_when_costs_consume(self):
        """best_action_after_cost falls back to NO_TRADE when costs consume edge."""
        sim = _make_sim_fixture(best_action="LONG_NOW")
        # Override long outcome to have gross > 0 but net <= 0
        sim["long_outcome"]["realized_r_gross"] = 0.5
        sim["long_outcome"]["realized_r_net"] = -0.1
        label = adapt_simulation_output(sim)
        assert label["best_action_after_cost"] == "NO_TRADE"


# ---------------------------------------------------------------------------
# Deterministic output tests (AC-02-022)
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    """Tests for deterministic (bit-for-bit identical) output."""

    def test_same_input_same_output(self):
        """AC-02-022: Two invocations with identical input produce deep-equal output."""
        sim = _load_sim_fixture()
        label1 = adapt_simulation_output(sim)
        label2 = adapt_simulation_output(sim)
        assert label1 == label2

    def test_deterministic_across_multiple_variants(self):
        """Deterministic output verified across 5+ fixture variants."""
        variants = [
            _make_sim_fixture(best_action="LONG_NOW"),
            _make_sim_fixture(best_action="NO_TRADE"),
            _make_sim_fixture(mode="SCALP", best_action="SHORT_NOW"),
            _make_sim_fixture(mode="AGGRESSIVE_SCALP", best_action="LONG_NOW"),
            _make_sim_fixture(
                best_action="NO_TRADE",
                resolution_status="UNRESOLVED",
            ),
            _make_sim_fixture(
                best_action="AMBIGUOUS_STATE",
                is_ambiguous=True,
            ),
            _make_sim_fixture(symbol="ETHUSDT"),
        ]
        for i, sim in enumerate(variants):
            label1 = adapt_simulation_output(sim)
            label2 = adapt_simulation_output(sim)
            assert label1 == label2, f"Variant {i} produced non-deterministic output"

    def test_json_serialization_identical(self):
        """Deterministic output also produces identical JSON strings."""
        sim = _load_sim_fixture()
        label1 = adapt_simulation_output(sim)
        label2 = adapt_simulation_output(sim)
        assert json.dumps(label1, sort_keys=True) == json.dumps(label2, sort_keys=True)


# ---------------------------------------------------------------------------
# label_validity filtering tests (AC-02-023)
# ---------------------------------------------------------------------------

class TestLabelValidity:
    """Tests for label_validity derivation."""

    def test_valid_for_complete_not_ambiguous(self):
        """AC-02-023: COMPLETE + not ambiguous → 'valid'."""
        sim = _make_sim_fixture(resolution_status="COMPLETE", is_ambiguous=False)
        label = adapt_simulation_output(sim)
        assert label["label_validity"] == LabelValidity.VALID.value

    def test_invalid_for_unresolved(self):
        """AC-02-023: UNRESOLVED → 'invalid'."""
        sim = _make_sim_fixture(resolution_status="UNRESOLVED", is_ambiguous=False)
        label = adapt_simulation_output(sim)
        assert label["label_validity"] == LabelValidity.INVALID.value

    def test_invalid_for_invalidated(self):
        """AC-02-023: INVALIDATED → 'invalid'."""
        sim = _make_sim_fixture(resolution_status="INVALIDATED", is_ambiguous=False)
        label = adapt_simulation_output(sim)
        assert label["label_validity"] == LabelValidity.INVALID.value

    def test_ambiguous_excluded_for_complete_and_ambiguous(self):
        """AC-02-023: COMPLETE + ambiguous → 'ambiguous_excluded'."""
        sim = _make_sim_fixture(resolution_status="COMPLETE", is_ambiguous=True)
        label = adapt_simulation_output(sim)
        assert label["label_validity"] == LabelValidity.AMBIGUOUS_EXCLUDED.value

    def test_label_still_produced_for_invalid_rows(self):
        """Invalid rows still produce labels (for consumer inspection)."""
        sim = _make_sim_fixture(resolution_status="UNRESOLVED")
        label = adapt_simulation_output(sim)
        assert "symbol" in label
        assert "timestamp" in label
        assert label["label_validity"] == "invalid"


# ---------------------------------------------------------------------------
# Input immutability test (AC-02-024)
# ---------------------------------------------------------------------------

class TestInputImmutability:
    """Tests that the adapter does not mutate the input dict."""

    def test_original_sim_output_unchanged(self):
        """AC-02-024: Original SimulationOutput dict is unchanged after adapter call."""
        sim = _load_sim_fixture()
        original = copy.deepcopy(sim)
        adapt_simulation_output(sim)
        assert sim == original, "Input SimulationOutput was mutated by adapter"

    def test_nested_structures_unchanged(self):
        """Nested sub-structs (long_outcome, etc.) are not mutated."""
        sim = _load_sim_fixture()
        original_long = copy.deepcopy(sim["long_outcome"])
        original_short = copy.deepcopy(sim["short_outcome"])
        original_no_trade = copy.deepcopy(sim["no_trade_outcome"])
        original_lineage = copy.deepcopy(sim["lineage"])

        adapt_simulation_output(sim)

        assert sim["long_outcome"] == original_long
        assert sim["short_outcome"] == original_short
        assert sim["no_trade_outcome"] == original_no_trade
        assert sim["lineage"] == original_lineage


# ---------------------------------------------------------------------------
# LabelAdapter class internals
# ---------------------------------------------------------------------------

class TestLabelAdapterInternals:
    """Tests for internal helper methods of LabelAdapter."""

    def test_detect_cost_consumed_edge_long(self):
        """Cost-consumed-edge detected on LONG side."""
        adapter = LabelAdapter()
        result = adapter._detect_cost_consumed_edge(
            long_R_gross=0.5, long_R_net=-0.1,
            short_R_gross=-0.3, short_R_net=-0.5
        )
        assert result is True

    def test_detect_cost_consumed_edge_short(self):
        """Cost-consumed-edge detected on SHORT side."""
        adapter = LabelAdapter()
        result = adapter._detect_cost_consumed_edge(
            long_R_gross=-0.1, long_R_net=-0.3,
            short_R_gross=0.3, short_R_net=-0.1
        )
        assert result is True

    def test_detect_cost_consumed_edge_none(self):
        """Cost-consumed-edge NOT detected when both sides non-consuming."""
        adapter = LabelAdapter()
        result = adapter._detect_cost_consumed_edge(
            long_R_gross=2.1, long_R_net=1.82,
            short_R_gross=-0.95, short_R_net=-1.23
        )
        assert result is False

    def test_derive_label_validity_complete_not_ambiguous(self):
        """_derive_label_validity: COMPLETE + not ambiguous → 'valid'."""
        adapter = LabelAdapter()
        assert adapter._derive_label_validity("COMPLETE", False) == "valid"

    def test_derive_label_validity_complete_ambiguous(self):
        """_derive_label_validity: COMPLETE + ambiguous → 'ambiguous_excluded'."""
        adapter = LabelAdapter()
        assert adapter._derive_label_validity("COMPLETE", True) == "ambiguous_excluded"

    def test_derive_label_validity_unresolved(self):
        """_derive_label_validity: UNRESOLVED → 'invalid'."""
        adapter = LabelAdapter()
        assert adapter._derive_label_validity("UNRESOLVED", False) == "invalid"

    def test_derive_label_validity_invalidated(self):
        """_derive_label_validity: INVALIDATED → 'invalid'."""
        adapter = LabelAdapter()
        assert adapter._derive_label_validity("INVALIDATED", True) == "invalid"

    def test_compute_best_action_after_cost_no_change(self):
        """best_action_after_cost unchanged when net is positive."""
        adapter = LabelAdapter()
        result = adapter._compute_best_action_after_cost(
            "LONG_NOW", 2.0, 1.5, -0.5, -0.8
        )
        assert result == "LONG_NOW"

    def test_compute_best_action_after_cost_consumed_long(self):
        """best_action_after_cost → NO_TRADE when long net consumed."""
        adapter = LabelAdapter()
        result = adapter._compute_best_action_after_cost(
            "LONG_NOW", 0.5, -0.1, -0.5, -0.8
        )
        assert result == "NO_TRADE"

    def test_compute_best_action_after_cost_consumed_short(self):
        """best_action_after_cost → NO_TRADE when short net consumed."""
        adapter = LabelAdapter()
        result = adapter._compute_best_action_after_cost(
            "SHORT_NOW", -0.5, -0.8, 0.3, -0.1
        )
        assert result == "NO_TRADE"
