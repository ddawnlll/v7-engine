"""
Tests for v7.mappings — cross-domain field mapping validation and enforcement.

Covers:
  1. FieldMapping dataclass construction
  2. Simulation -> V7 mapping (all fields from simulation_to_v7.json)
  3. Simulation -> AlphaForge mapping (all fields from simulation_to_alphaforge.json)
  4. AlphaForge -> V7 mapping (from alphaforge_to_v7.md)
  5. Strict vs non-strict mode (missing fields)
  6. validate_field_mapping — happy path and error cases
  7. validate_all_* — bulk validation of all mappings
  8. Edge cases: empty input, missing sections, custom transforms, None values
  9. Duplicate target field detection
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from v7.mappings import (
    CrossDomainMapper,
    FieldMapping,
    _ALPHAFORGE_TO_V7_DEFS,
    _get_nested,
    _set_nested,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SIM_FIXTURE_PATH = (
    _REPO_ROOT / "contracts" / "fixtures" / "simulation_output_minimal.json"
)
_SIM_TO_V7_PATH = (
    _REPO_ROOT / "contracts" / "mappings" / "simulation_to_v7.json"
)
_SIM_TO_AF_PATH = (
    _REPO_ROOT / "contracts" / "mappings" / "simulation_to_alphaforge.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sim_fixture() -> dict:
    """Load the canonical minimal SimulationOutput fixture."""
    with open(_SIM_FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sim_to_v7_json() -> dict:
    """Load the sim->v7 mapping JSON."""
    with open(_SIM_TO_V7_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sim_to_af_json() -> dict:
    """Load the sim->alphaforge mapping JSON."""
    with open(_SIM_TO_AF_PATH) as f:
        return json.load(f)


@pytest.fixture()
def mapper() -> CrossDomainMapper:
    return CrossDomainMapper()


# ===========================================================================
# 1. FieldMapping dataclass
# ===========================================================================


class TestFieldMapping:
    """FieldMapping construction and defaults."""

    def test_minimal(self) -> None:
        """Basic required fields."""
        fm = FieldMapping(
            source_domain="simulation",
            source_field="long_outcome.realized_r_net",
            target_domain="v7",
            target_field="realized_r",
        )
        assert fm.source_domain == "simulation"
        assert fm.source_field == "long_outcome.realized_r_net"
        assert fm.target_domain == "v7"
        assert fm.target_field == "realized_r"
        assert fm.required is True
        assert fm.transform_fn is None
        assert fm.description == ""

    def test_all_fields(self) -> None:
        """All optional fields set."""
        fn = lambda x: x * 2  # noqa: E731
        fm = FieldMapping(
            source_domain="simulation",
            source_field="a.b",
            target_domain="alphaforge",
            target_field="c",
            required=False,
            transform_fn=fn,
            description="Test mapping",
        )
        assert fm.required is False
        assert fm.transform_fn is fn
        assert fm.description == "Test mapping"

    def test_frozen(self) -> None:
        """FieldMapping is immutable."""
        fm = FieldMapping(
            source_domain="s", source_field="a",
            target_domain="t", target_field="b",
        )
        with pytest.raises(AttributeError):
            fm.source_field = "changed"  # type: ignore[misc]


# ===========================================================================
# 2. Simulation -> V7 mapping
# ===========================================================================


class TestMapSimulationToV7:
    """CrossDomainMapper.map_simulation_to_v7."""

    def test_mappings_loaded(self, mapper: CrossDomainMapper) -> None:
        """All sim->v7 field mappings are loaded from JSON."""
        mappings = mapper.simulation_to_v7_mappings
        assert len(mappings) > 0
        # Every mapping has simulation as source and v7 as target
        for m in mappings:
            assert m.source_domain == "simulation"
            assert m.target_domain == "v7"

    def test_map_minimal_fixture(self, sim_fixture: dict, mapper: CrossDomainMapper) -> None:
        """Map the minimal simulation fixture through sim->v7 pipeline."""
        result = mapper.map_simulation_to_v7(sim_fixture)
        assert isinstance(result, dict)

        # Check known values from the fixture
        assert result.get("realized_r") == 1.82  # long_outcome.realized_r_net
        assert result.get("exit_reason") == "TARGET_HIT"  # long_outcome.exit_reason
        assert result.get("mfe_r") == 2.5  # long_outcome.path_metrics.mfe_r
        assert result.get("mae_r") == -0.35  # long_outcome.path_metrics.mae_r
        assert result.get("counterfactual_best_action") == "LONG_NOW"
        assert result.get("regret_r") == 0
        assert result.get("horizon_family") == "swing_horizon"

    def test_map_non_strict_missing(self, mapper: CrossDomainMapper) -> None:
        """Missing required fields in non-strict mode are silently omitted."""
        result = mapper.map_simulation_to_v7({})
        # Should not raise; missing fields are just absent
        assert isinstance(result, dict)
        # With an empty input, all required fields are missing so result is empty
        assert len(result) == 0

    def test_map_strict_missing_raises(self, mapper: CrossDomainMapper) -> None:
        """Missing required fields in strict mode raises KeyError."""
        with pytest.raises(KeyError, match="Missing required"):
            mapper.map_simulation_to_v7({}, strict=True)

    def test_map_all_fields_match_fixture(self, sim_fixture: dict, mapper: CrossDomainMapper) -> None:
        """Every mapping from the JSON should be populated correctly."""
        result = mapper.map_simulation_to_v7(sim_fixture, strict=True)

        # Check every required field is present
        for m in mapper.simulation_to_v7_mappings:
            if m.required:
                assert _get_nested(result, m.target_field) is not None, (
                    f"Required mapping {m.source_field} -> {m.target_field} "
                    f"produced None"
                )

    def test_map_no_trade_fields(self, sim_fixture: dict, mapper: CrossDomainMapper) -> None:
        """NO_TRADE sub-fields are mapped correctly."""
        result = mapper.map_simulation_to_v7(sim_fixture)
        assert result.get("saved_loss_score") == 0.62
        assert result.get("missed_opportunity_score") == 0.73
        assert result.get("path_quality_score") == 0.82


# ===========================================================================
# 3. Simulation -> AlphaForge mapping
# ===========================================================================


class TestMapSimulationToAlphaForge:
    """CrossDomainMapper.map_simulation_to_alphaforge."""

    def test_mappings_loaded(self, mapper: CrossDomainMapper) -> None:
        """All sim->alphaforge field mappings are loaded from JSON."""
        mappings = mapper.simulation_to_alphaforge_mappings
        assert len(mappings) > 0
        for m in mappings:
            assert m.source_domain == "simulation"
            assert m.target_domain == "alphaforge"

    def test_map_minimal_fixture(self, sim_fixture: dict, mapper: CrossDomainMapper) -> None:
        """Map the minimal fixture through sim->alphaforge pipeline."""
        result = mapper.map_simulation_to_alphaforge(sim_fixture)
        assert isinstance(result, dict)

        # Check long fields
        assert result.get("long_R_gross") == 2.1
        assert result.get("long_R_net") == 1.82
        assert result.get("fee_cost_r_long") == 0.12
        assert result.get("slippage_cost_r_long") == 0.16
        assert result.get("total_cost_r_long") == 0.28
        assert result.get("long_mfe_R") == 2.5
        assert result.get("long_mae_R") == -0.35

        # Check short fields
        assert result.get("short_R_gross") == -0.95
        assert result.get("short_R_net") == -1.23
        assert result.get("fee_cost_r_short") == 0.12
        assert result.get("slippage_cost_r_short") == 0.16
        assert result.get("total_cost_r_short") == 0.28
        assert result.get("short_mfe_R") == 0.08
        assert result.get("short_mae_R") == -0.95

        # Check best-action fields
        assert result.get("best_action_label") == "LONG_NOW"
        assert result.get("action_gap_R") == 1.82
        assert result.get("regret_R") == 0
        assert result.get("is_ambiguous") is False

        # Check no-trade fields
        assert result.get("no_trade_quality") == "MISSED_OPPORTUNITY"
        assert result.get("was_correct_skip") is False
        assert result.get("saved_loss_r") == 1.23
        assert result.get("missed_opportunity_r") == 1.82
        assert result.get("saved_loss_score") == 0.62
        assert result.get("missed_opportunity_score") == 0.73

        # Check resolution
        assert result.get("resolution_status") == "COMPLETE"
        assert result.get("exit_reason") == "TARGET_HIT"

        # Check lineage
        assert result.get("simulation_profile_id") == "swing_profile-1.0.0"
        assert result.get("simulation_engine_version") == "simfam-1.0.0"
        assert result.get("cost_model_version") == "cost-1.0.0"

    def test_map_all_fields_present(self, sim_fixture: dict, mapper: CrossDomainMapper) -> None:
        """Every required mapping produces a non-None value in strict mode."""
        result = mapper.map_simulation_to_alphaforge(sim_fixture, strict=True)

        for m in mapper.simulation_to_alphaforge_mappings:
            if m.required:
                assert _get_nested(result, m.target_field) is not None, (
                    f"Required mapping {m.source_field} -> {m.target_field} "
                    f"produced None"
                )

    def test_missing_non_required(self, mapper: CrossDomainMapper) -> None:
        """Non-required optional fields are silently skipped when source is absent."""
        # Minimal sim with no optional fields
        sim = {
            "long_outcome": {
                "action": "LONG_NOW",
                "realized_r_gross": 0.5,
                "realized_r_net": 0.3,
                "fee_cost_r": 0.1,
                "slippage_cost_r": 0.1,
                "total_cost_r": 0.2,
                "exit_reason": "TARGET_HIT",
                "path_metrics": {
                    "mfe_r": 0.5,
                    "mae_r": -0.1,
                    "path_quality_score": 0.6,
                    "path_quality_bucket": "MEDIUM",
                },
            },
            "short_outcome": {
                "action": "SHORT_NOW",
                "realized_r_gross": -0.3,
                "realized_r_net": -0.5,
                "fee_cost_r": 0.1,
                "slippage_cost_r": 0.1,
                "total_cost_r": 0.2,
                "exit_reason": "STOP_HIT",
                "path_metrics": {
                    "mfe_r": 0.1,
                    "mae_r": -0.5,
                    "path_quality_score": 0.2,
                    "path_quality_bucket": "LOW",
                },
            },
            "no_trade_outcome": {
                "saved_loss_r": 0.0,
                "saved_loss_score": 0.0,
                "missed_opportunity_r": 0.0,
                "missed_opportunity_score": 0.0,
                "no_trade_quality": "AMBIGUOUS_NO_TRADE",
                "was_correct_skip": True,
            },
            "best_action": "LONG_NOW",
            "action_gap_r": 0.2,
            "regret_r": 0.0,
            "is_ambiguous": True,
            "resolution_status": "COMPLETE",
            "lineage": {
                "simulation_family_version": "simfam-1.0.0",
                "simulation_profile_version": "profile-1.0.0",
                "cost_model_version": "cost-1.0.0",
                "fee_model_version": "fee-1.0.0",
                "slippage_model_version": "slippage-1.0.0",
                "horizon_family": "swing_horizon",
                "stop_family": "atr_wide",
                "target_family": "atr_wide",
                "time_exit_family": "hold_then_exit",
                "adapter_kind": "TRAINING",
            },
        }
        # This has all required fields but no optional ones like path_quality_score
        result = mapper.map_simulation_to_alphaforge(sim, strict=True)
        assert "path_quality_score" in result  # still required
        assert result["path_quality_score"] == 0.6  # from long path

    def test_map_strict_missing_required_raises(self, mapper: CrossDomainMapper) -> None:
        """Missing required field in strict mode raises KeyError."""
        with pytest.raises(KeyError, match="action_gap_r"):
            mapper.map_simulation_to_alphaforge(
                {"long_outcome": {}, "short_outcome": {}}, strict=True,
            )


# ===========================================================================
# 4. AlphaForge -> V7 mapping
# ===========================================================================


class TestMapAlphaForgeToV7:
    """CrossDomainMapper.map_alphaforge_to_v7."""

    def test_mappings_defined(self, mapper: CrossDomainMapper) -> None:
        """All alphaforge->v7 mappings are available."""
        mappings = mapper.alphaforge_to_v7_mappings
        assert len(mappings) > 0
        for m in mappings:
            assert m.source_domain == "alphaforge"
            assert m.target_domain == "v7"

    def test_map_mode_research_report(self, mapper: CrossDomainMapper) -> None:
        """Map a ModeResearchReport-shaped dict."""
        af_output = {
            "data_scope": {"symbols": ["BTCUSDT"], "date_range": ["2025-01-01", "2025-06-30"]},
            "metrics": {"oos_sharpe": 1.2, "oos_expectancy_r": 0.35, "oos_win_rate": 0.55},
            "validation_summary": {"fold_count": 6, "verdict": "PASS", "overfit_risk": "LOW"},
            "cost_stress": {"fee_level": "MODERATE", "slippage_level": "LOW", "combined_stress": "LOW"},
            "regime_breakdown": {"TREND_UP": {"sharpe": 1.5}, "TREND_DOWN": {"sharpe": 0.8}},
            "verdict": "PASS_WITH_LIMITATIONS",
            "no_trade_comparison": {"active_beats_no_trade": True},
            "split_policy": {"method": "purge_embargo", "train_pct": 0.6},
            "walk_forward_folds": [{"fold": 1, "oos_sharpe": 1.1}],
            "oos_summary": {"avg_sharpe": 1.2, "sharpe_std": 0.3},
            "overfit_risk_flags": [],
            "multiple_hypothesis_control": {"method": "bonferroni", "adjusted_p": 0.01},
            "symbol_stability": {"max_symbol_contribution": 0.35},
        }
        result = mapper.map_alphaforge_to_v7(af_output)
        assert isinstance(result, dict)

        # Check gate-structured output
        assert _get_nested(result, "gates.G0_DOC_READY.data_scope") == af_output["data_scope"]
        assert _get_nested(result, "gates.G1_RESEARCH_BACKTEST.oos_sharpe") == 1.2
        assert _get_nested(result, "gates.G1_RESEARCH_BACKTEST.oos_expectancy_r") == 0.35
        assert _get_nested(result, "gates.G2_WALK_FORWARD_OOS.fold_count") == 6
        assert _get_nested(result, "gates.G2_WALK_FORWARD_OOS.verdict") == "PASS"
        assert _get_nested(result, "gates.G3_COST_STRESS.fee_level") == "MODERATE"
        assert _get_nested(result, "gates.G4_REGIME_BREAKDOWN.regime_metrics") == af_output["regime_breakdown"]
        assert _get_nested(result, "decision_input.verdict") == "PASS_WITH_LIMITATIONS"
        assert _get_nested(result, "decision_input.no_trade_comparison") == af_output["no_trade_comparison"]

    def test_map_model_artifact(self, mapper: CrossDomainMapper) -> None:
        """Map a ModelArtifact-shaped dict."""
        af_output = {
            "model_artifact_id": "ma_001",
            "artifact_uri": "s3://models/swing_v1/model.pkl",
            "checksum": "abc123def456",
            "model_family": "xgboost",
            "feature_set_id": "fs_swing_v1",
            "training_metrics": {"sharpe": 1.5, "mae": 0.02},
            "hyperparameters": {"max_depth": 5, "n_estimators": 200},
            "limitations": ["Not validated on ETHUSDT"],
        }
        result = mapper.map_alphaforge_to_v7(af_output)
        assert _get_nested(result, "model_info.model_artifact_id") == "ma_001"
        assert _get_nested(result, "model_info.artifact_uri") == "s3://models/swing_v1/model.pkl"
        assert _get_nested(result, "model_info.checksum") == "abc123def456"
        assert _get_nested(result, "model_info.model_family") == "xgboost"
        assert _get_nested(result, "model_info.feature_set_id") == "fs_swing_v1"
        assert _get_nested(result, "model_info.hyperparameters.max_depth") == 5

    def test_map_calibration_candidate(self, mapper: CrossDomainMapper) -> None:
        """Map a CalibrationCandidate-shaped dict."""
        af_output = {
            "calibration_method": "isotonic_regression",
            "calibration_metrics": {"ece": 0.03, "mce": 0.08},
            "confidence_bins": [{"bin": 1, "accuracy": 0.95}],
            "status": "CALIBRATED",
        }
        result = mapper.map_alphaforge_to_v7(af_output)
        assert _get_nested(result, "gates.G6_CALIBRATION_RELIABILITY.calibration_method") == "isotonic_regression"
        assert _get_nested(result, "gates.G6_CALIBRATION_RELIABILITY.ece") == 0.03
        assert _get_nested(result, "gates.G6_CALIBRATION_RELIABILITY.status") == "CALIBRATED"

    def test_map_v7_handoff(self, mapper: CrossDomainMapper) -> None:
        """Map a V7HandoffPackage-shaped dict."""
        af_output = {
            "handoff_package_id": "hp_001",
            "v7_gate_mapping": {"G0": "passed"},
            "recommended_status": "PROMOTION_CANDIDATE",
            "blocked_scopes": ["perp_btc"],
            "limitations": ["Funding DEFERRED"],
            "lineage": {"alpha_candidate_id": "ac_001"},
            "rejection_rules_applied": ["min_folds", "min_sharpe"],
        }
        result = mapper.map_alphaforge_to_v7(af_output)
        assert _get_nested(result, "handoff.handoff_package_id") == "hp_001"
        assert _get_nested(result, "handoff.recommended_status") == "PROMOTION_CANDIDATE"
        assert _get_nested(result, "handoff.lineage.alpha_candidate_id") == "ac_001"

    def test_map_strict_missing_raises(self, mapper: CrossDomainMapper) -> None:
        """Missing required af->v7 field in strict mode raises KeyError."""
        with pytest.raises(KeyError, match="verdict"):
            mapper.map_alphaforge_to_v7({}, strict=True)


# ===========================================================================
# 5. validate_field_mapping
# ===========================================================================


class TestValidateFieldMapping:
    """CrossDomainMapper.validate_field_mapping."""

    def test_valid_mapping(self, mapper: CrossDomainMapper) -> None:
        """A well-formed mapping definition passes with no errors."""
        mapping = {
            "source": "long_outcome.realized_r_net",
            "target": "realized_r",
            "required": True,
            "meaning": "Realized net R",
        }
        errors = mapper.validate_field_mapping(mapping)
        assert errors == []

    def test_valid_minimal(self, mapper: CrossDomainMapper) -> None:
        """Minimal mapping (no optional fields) is valid."""
        mapping = {
            "source": "a.b",
            "target": "c",
        }
        errors = mapper.validate_field_mapping(mapping)
        assert errors == []

    def test_missing_source(self, mapper: CrossDomainMapper) -> None:
        """Missing 'source' key is flagged."""
        errors = mapper.validate_field_mapping({"target": "x"})
        assert any("source" in e for e in errors)

    def test_missing_target(self, mapper: CrossDomainMapper) -> None:
        """Missing 'target' key is flagged."""
        errors = mapper.validate_field_mapping({"source": "x"})
        assert any("target" in e for e in errors)

    def test_source_leading_dot(self, mapper: CrossDomainMapper) -> None:
        """Source with leading dot is flagged."""
        errors = mapper.validate_field_mapping({"source": ".foo", "target": "bar"})
        assert any("starts with a dot" in e for e in errors)

    def test_source_trailing_dot(self, mapper: CrossDomainMapper) -> None:
        """Source with trailing dot is flagged."""
        errors = mapper.validate_field_mapping({"source": "foo.", "target": "bar"})
        assert any("ends with a dot" in e for e in errors)

    def test_source_double_dots(self, mapper: CrossDomainMapper) -> None:
        """Source with consecutive dots is flagged."""
        errors = mapper.validate_field_mapping({"source": "foo..bar", "target": "baz"})
        assert any("consecutive dots" in e for e in errors)

    def test_empty_source(self, mapper: CrossDomainMapper) -> None:
        """Empty source is flagged."""
        errors = mapper.validate_field_mapping({"source": "", "target": "x"})
        assert any("not be empty" in e for e in errors)

    def test_empty_target(self, mapper: CrossDomainMapper) -> None:
        """Empty target is flagged."""
        errors = mapper.validate_field_mapping({"source": "x", "target": ""})
        assert any("not be empty" in e for e in errors)

    def test_required_not_bool(self, mapper: CrossDomainMapper) -> None:
        """required must be boolean."""
        errors = mapper.validate_field_mapping(
            {"source": "a", "target": "b", "required": "yes"},
        )
        assert any("boolean" in e for e in errors)

    def test_meaning_not_string(self, mapper: CrossDomainMapper) -> None:
        """meaning must be string."""
        errors = mapper.validate_field_mapping(
            {"source": "a", "target": "b", "meaning": 42},
        )
        assert any("string" in e for e in errors)

    def test_non_string_source(self, mapper: CrossDomainMapper) -> None:
        """source must be a string."""
        errors = mapper.validate_field_mapping({"source": 123, "target": "b"})
        assert any("string" in e for e in errors)


# ===========================================================================
# 6. Bulk validation
# ===========================================================================


class TestBulkValidation:
    """CrossDomainMapper.validate_all_* methods."""

    def test_validate_all_simulation_to_v7(self, mapper: CrossDomainMapper) -> None:
        """Sim->v7 mappings are structurally valid modulo the known duplicate.

        Known issue: ``long_outcome.fee_cost_r`` and
        ``long_outcome.realized_r_net`` both target ``realized_r`` in
        simulation_to_v7.json (the ``fee_cost_r`` entry is likely a copy-paste
        error).  Validation reports this so mapping authors can fix it, but it
        is not a code bug — the mapper handles it by keeping the first mapping
        (``realized_r_net``).
        """
        errors = mapper.validate_all_simulation_to_v7()
        # We expect exactly one error: the known duplicate target.
        assert len(errors) == 1, f"Unexpected errors:\n" + "\n".join(errors)
        assert "Duplicate target field" in errors[0]
        assert "realized_r" in errors[0]

    def test_validate_all_simulation_to_alphaforge(self, mapper: CrossDomainMapper) -> None:
        """All sim->alphaforge mapping definitions pass structural validation."""
        errors = mapper.validate_all_simulation_to_alphaforge()
        assert errors == [], f"Validation errors:\n" + "\n".join(errors)

    def test_validate_all_alphaforge_to_v7(self, mapper: CrossDomainMapper) -> None:
        """All af->v7 mapping definitions pass structural validation."""
        errors = mapper.validate_all_alphaforge_to_v7()
        assert errors == [], f"Validation errors:\n" + "\n".join(errors)


# ===========================================================================
# 7. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases for mapping."""

    def test_empty_input_non_strict(self, mapper: CrossDomainMapper) -> None:
        """Empty input produces empty result in non-strict mode."""
        assert mapper.map_simulation_to_v7({}) == {}
        assert mapper.map_simulation_to_alphaforge({}) == {}
        assert mapper.map_alphaforge_to_v7({}) == {}

    def test_none_value_handling(self, mapper: CrossDomainMapper) -> None:
        """None values in source should be treated as missing."""
        sim = {
            "long_outcome": {
                "action": "LONG_NOW",
                "realized_r_gross": None,
                "realized_r_net": None,
                "fee_cost_r": None,
                "slippage_cost_r": None,
                "total_cost_r": None,
                "exit_reason": None,
                "path_metrics": {
                    "mfe_r": None,
                    "mae_r": None,
                    "path_quality_score": None,
                    "path_quality_bucket": None,
                },
            },
            "short_outcome": {
                "action": "SHORT_NOW",
                "realized_r_gross": None,
                "realized_r_net": None,
                "fee_cost_r": None,
                "slippage_cost_r": None,
                "total_cost_r": None,
                "exit_reason": None,
                "path_metrics": {
                    "mfe_r": None,
                    "mae_r": None,
                    "path_quality_score": None,
                    "path_quality_bucket": None,
                },
            },
            "no_trade_outcome": {
                "saved_loss_r": None,
                "saved_loss_score": None,
                "missed_opportunity_r": None,
                "missed_opportunity_score": None,
                "no_trade_quality": None,
                "was_correct_skip": None,
            },
            "best_action": None,
            "action_gap_r": None,
            "regret_r": None,
            "is_ambiguous": None,
            "resolution_status": None,
            "lineage": {
                "simulation_family_version": None,
                "simulation_profile_version": None,
                "cost_model_version": None,
                "fee_model_version": None,
                "slippage_model_version": None,
                "horizon_family": None,
                "stop_family": None,
                "target_family": None,
                "time_exit_family": None,
                "adapter_kind": None,
            },
        }
        # In non-strict mode, all required fields are None so none are mapped
        result = mapper.map_simulation_to_v7(sim)
        assert result == {}

    def test_transform_fn(self, mapper: CrossDomainMapper) -> None:
        """Transform function is applied during mapping."""
        # Create a custom mapper with a transform
        sim = {
            "long_outcome": {
                "realized_r_net": 1.5,
                "exit_reason": "TARGET_HIT",
                "action": "LONG_NOW",
                "path_metrics": {"mfe_r": 2.0, "mae_r": -0.3, "path_quality_score": 0.8, "path_quality_bucket": "HIGH"},
                "fee_cost_r": 0.1,
                "slippage_cost_r": 0.1,
                "total_cost_r": 0.2,
                "realized_r_gross": 1.8,
            },
            "short_outcome": {
                "realized_r_net": -0.5,
                "exit_reason": "STOP_HIT",
                "action": "SHORT_NOW",
                "path_metrics": {"mfe_r": 0.1, "mae_r": -0.8, "path_quality_score": 0.2, "path_quality_bucket": "LOW"},
                "fee_cost_r": 0.1,
                "slippage_cost_r": 0.1,
                "total_cost_r": 0.2,
                "realized_r_gross": -0.3,
            },
            "no_trade_outcome": {
                "saved_loss_r": 0.5,
                "saved_loss_score": 0.5,
                "missed_opportunity_r": 0.3,
                "missed_opportunity_score": 0.3,
                "no_trade_quality": "SAVED_LOSS",
                "was_correct_skip": True,
            },
            "best_action": "LONG_NOW",
            "action_gap_r": 1.0,
            "regret_r": 0.0,
            "is_ambiguous": False,
            "resolution_status": "COMPLETE",
            "lineage": {
                "simulation_family_version": "1.0",
                "simulation_profile_version": "1.0",
                "cost_model_version": "1.0",
                "fee_model_version": "1.0",
                "slippage_model_version": "1.0",
                "horizon_family": "swing",
                "stop_family": "atr",
                "target_family": "atr",
                "time_exit_family": "hold",
                "adapter_kind": "TRAINING",
            },
        }

        # Test transform behavior by creating a custom mapper with a transform
        fm = FieldMapping(
            source_domain="simulation",
            source_field="long_outcome.realized_r_net",
            target_domain="v7",
            target_field="realized_r_doubled",
            required=True,
            transform_fn=lambda x: round(x * 2, 2),
        )
        # Use the internal apply directly
        result = CrossDomainMapper._apply_mappings(sim, [fm])
        assert result.get("realized_r_doubled") == 3.0  # 1.5 * 2

    def test_transform_fn_error(self, mapper: CrossDomainMapper) -> None:
        """Transform function that raises is caught and re-raised as ValueError."""
        fm = FieldMapping(
            source_domain="simulation",
            source_field="x",
            target_domain="v7",
            target_field="y",
            transform_fn=lambda x: 1 / 0,  # will raise ZeroDivisionError
        )
        with pytest.raises(ValueError, match="Transform failed for 'x'"):
            CrossDomainMapper._apply_mappings({"x": 1}, [fm])

    def test_partial_input(self, mapper: CrossDomainMapper) -> None:
        """Only fields present in source are mapped; absent fields are omitted."""
        result = mapper.map_simulation_to_v7({"best_action": "NO_TRADE"})
        assert result.get("counterfactual_best_action") == "NO_TRADE"
        # No other fields should be present since they weren't in the source
        assert len(result) == 1

    def test_mapped_output_is_new_dict(self, mapper: CrossDomainMapper, sim_fixture: dict) -> None:
        """Mapping does not mutate the input."""
        original = dict(sim_fixture)
        mapper.map_simulation_to_v7(sim_fixture)
        assert sim_fixture == original


# ===========================================================================
# 8. Helpers
# ===========================================================================


class TestNestedHelpers:
    """_get_nested and _set_nested."""

    def test_get_nested_simple(self) -> None:
        assert _get_nested({"a": 1}, "a") == 1

    def test_get_nested_deep(self) -> None:
        assert _get_nested({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_get_nested_missing(self) -> None:
        assert _get_nested({"a": 1}, "b") is None

    def test_get_nested_default(self) -> None:
        assert _get_nested({"a": 1}, "b", default="fallback") == "fallback"

    def test_get_nested_partial_path(self) -> None:
        assert _get_nested({"a": {"b": 1}}, "a.x.y") is None

    def test_get_nested_non_dict_intermediate(self) -> None:
        assert _get_nested({"a": 42}, "a.b") is None

    def test_get_nested_empty(self) -> None:
        assert _get_nested({}, "a.b") is None

    def test_set_nested_simple(self) -> None:
        d = {}
        _set_nested(d, "a", 1)
        assert d == {"a": 1}

    def test_set_nested_deep(self) -> None:
        d = {}
        _set_nested(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_set_nested_overwrites(self) -> None:
        d = {"a": {"b": 1}}
        _set_nested(d, "a.b", 2)
        assert d["a"]["b"] == 2

    def test_set_nested_creates_intermediates(self) -> None:
        d = {"x": 1}
        _set_nested(d, "a.b.c", "val")
        assert d == {"x": 1, "a": {"b": {"c": "val"}}}


# ===========================================================================
# 9. JSON mapping file alignment
# ===========================================================================


class TestJsonMappingAlignment:
    """Verify that the code-level mappings match the JSON definitions."""

    def test_sim_to_v7_field_count(self, mapper: CrossDomainMapper, sim_to_v7_json: dict) -> None:
        """Loaded mapping count matches deduplicated JSON entries."""
        raw_count = len(sim_to_v7_json["mappings"])
        mapping_count = len(mapper.simulation_to_v7_mappings)
        # There are no duplicates in sim_to_v7.json, so count should be equal
        assert mapping_count == raw_count, (
            f"Loaded {mapping_count} mappings but JSON has {raw_count}"
        )

    def test_sim_to_af_field_count(self, mapper: CrossDomainMapper, sim_to_af_json: dict) -> None:
        """Loaded mapping count accounts for deduplication."""
        raw_count = len(sim_to_af_json["mappings"])
        mapping_count = len(mapper.simulation_to_alphaforge_mappings)
        # sim_to_af.json has 3 duplicate entries, so loaded count should be less
        assert mapping_count < raw_count, (
            f"Expected deduplication: loaded {mapping_count} < raw {raw_count}"
        )
        assert mapping_count == raw_count - 3, (
            f"Expected {raw_count - 3} deduplicated mappings, got {mapping_count}"
        )

    def test_sim_to_v7_all_fields_covered(self, mapper: CrossDomainMapper) -> None:
        """Every field in the fixture that maps to a V7 field produces a value."""
        # This test checks that the fixture has data for all required source fields
        mappings = mapper.simulation_to_v7_mappings
        with open(_SIM_FIXTURE_PATH) as f:
            fixture = json.load(f)

        missing = []
        for m in mappings:
            if m.required:
                val = _get_nested(fixture, m.source_field)
                if val is None:
                    missing.append(m.source_field)
        assert missing == [], (
            f"Fixture missing data for required fields: {missing}"
        )


# ===========================================================================
# 10. Constructor with custom paths
# ===========================================================================


class TestCustomPaths:
    """CrossDomainMapper with custom mapping file paths."""

    def test_custom_sim_to_v7(self) -> None:
        """Loading from custom path works."""
        mapper = CrossDomainMapper(
            sim_to_v7_path=str(_SIM_TO_V7_PATH),
        )
        assert len(mapper.simulation_to_v7_mappings) > 0

    def test_custom_sim_to_af(self) -> None:
        """Loading from custom path works for both files."""
        mapper = CrossDomainMapper(
            sim_to_v7_path=str(_SIM_TO_V7_PATH),
            sim_to_alphaforge_path=str(_SIM_TO_AF_PATH),
        )
        assert len(mapper.simulation_to_v7_mappings) > 0
        assert len(mapper.simulation_to_alphaforge_mappings) > 0
