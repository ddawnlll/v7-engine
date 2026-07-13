"""Tests for the deterministic V7-Lite readiness gate (G0-G6)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from v7.lite.readiness_gate import (
    CANONICAL_SYMBOL_COUNT,
    CANONICAL_SYMBOLS,
    MODE_THRESHOLDS,
    REQUIRED_GATES,
    DataScope,
    GateEvidence,
    ReadinessGateError,
    compute_readiness,
    evaluate_gate,
    write_readiness_checkpoint,
)


def _canonical_scope() -> DataScope:
    return DataScope(
        symbols=CANONICAL_SYMBOLS,
        feature_count=61,
        start_ts=1_700_000_000_000,
        end_ts=1_800_000_000_000,
        uses_all_feature_groups=True,
    )


def _passing_evidence(mode: str) -> dict[str, GateEvidence]:
    t = MODE_THRESHOLDS[mode]
    return {
        "G0": GateEvidence(folds=int(t["min_folds"])),
        "G1": GateEvidence(
            expectancy_r=t["min_expectancy_r"] + 0.01,
            correct_no_trade_pct=t["min_correct_no_trade_pct"],
            pbo_risk="LOW",
            deflated_sharpe=0.5,
            mht_computed_real=True,
        ),
        "G2": GateEvidence(
            folds=t["min_folds"],
            oos_months=t["min_oos_months"],
            expectancy_r=t["min_expectancy_r"] + 0.01,
        ),
        "G3": GateEvidence(
            cost_stress_multiplier_survived=t["cost_stress_multiplier"],
            cost_adjusted_expectancy_r=t["min_cost_adjusted_expectancy_r"] + 0.01,
        ),
        "G4": GateEvidence(catastrophic_regime_loss=False),
        "G5": GateEvidence(
            trades=t["min_trades"],
            max_symbol_contribution_pct=t["max_symbol_contribution_pct"],
            max_cluster_contribution_pct=t["max_cluster_contribution_pct"],
        ),
        "G6": GateEvidence(
            calibration_error_pct=t["max_calibration_error_pct"],
            max_drawdown_pct=t["max_drawdown_pct"],
            saved_loss_r=t["min_saved_loss_r"],
        ),
    }


@pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
def test_full_pass_scenario_yields_100_pct(mode: str) -> None:
    readiness = compute_readiness(mode, _passing_evidence(mode), _canonical_scope())
    assert readiness.gate_completion_pct == 100.0
    assert readiness.quality_subscore_pct == 100.0
    assert all(r.passed for r in readiness.per_gate.values())


@pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
def test_g3_fails_just_under_cost_stress_threshold(mode: str) -> None:
    t = MODE_THRESHOLDS[mode]
    evidence = GateEvidence(
        cost_stress_multiplier_survived=t["cost_stress_multiplier"] - 0.01,
        cost_adjusted_expectancy_r=t["min_cost_adjusted_expectancy_r"] + 0.01,
    )
    result = evaluate_gate("G3", evidence, mode)
    assert not result.passed
    assert "edge_does_not_survive_cost_stress" in result.reasons


@pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
def test_g3_passes_exactly_at_cost_stress_threshold(mode: str) -> None:
    t = MODE_THRESHOLDS[mode]
    evidence = GateEvidence(
        cost_stress_multiplier_survived=t["cost_stress_multiplier"],
        cost_adjusted_expectancy_r=t["min_cost_adjusted_expectancy_r"],
    )
    result = evaluate_gate("G3", evidence, mode)
    assert result.passed


def test_g5_fails_when_single_symbol_dominates() -> None:
    t = MODE_THRESHOLDS["SCALP"]
    evidence = GateEvidence(
        trades=t["min_trades"],
        max_symbol_contribution_pct=t["max_symbol_contribution_pct"] + 0.01,
        max_cluster_contribution_pct=t["max_cluster_contribution_pct"],
    )
    result = evaluate_gate("G5", evidence, "SCALP")
    assert not result.passed
    assert "single_symbol_dominates_edge" in result.reasons


def test_g1_fails_on_mht_fallback_identity() -> None:
    evidence = GateEvidence(
        expectancy_r=0.2,
        correct_no_trade_pct=90.0,
        pbo_risk="LOW",
        deflated_sharpe=0.5,
        mht_computed_real=False,
    )
    result = evaluate_gate("G1", evidence, "SWING")
    assert not result.passed
    assert "mht_fallback_identity_not_real_computation" in result.reasons


def test_g4_fails_on_catastrophic_regime_loss() -> None:
    result = evaluate_gate("G4", GateEvidence(catastrophic_regime_loss=True), "SWING")
    assert not result.passed
    assert result.reasons == ("catastrophic_loss_in_a_regime",)


def test_partial_pass_gives_gate_completion_between_bounds() -> None:
    mode = "SCALP"
    evidence = _passing_evidence(mode)
    # Break exactly one gate (G6) by pushing drawdown over the limit.
    t = MODE_THRESHOLDS[mode]
    evidence["G6"] = GateEvidence(
        calibration_error_pct=t["max_calibration_error_pct"],
        max_drawdown_pct=t["max_drawdown_pct"] + 5.0,
        saved_loss_r=t["min_saved_loss_r"],
    )
    readiness = compute_readiness(mode, evidence, _canonical_scope())
    assert readiness.gate_completion_pct == pytest.approx(100.0 * 6 / 7)
    assert not readiness.per_gate["G6"].passed
    assert readiness.quality_subscore_pct < 100.0


def test_missing_gate_evidence_raises() -> None:
    mode = "SWING"
    evidence = _passing_evidence(mode)
    del evidence["G4"]
    with pytest.raises(ReadinessGateError, match="Missing evidence"):
        compute_readiness(mode, evidence, _canonical_scope())


def test_non_canonical_scope_raises_without_opt_out() -> None:
    scope = DataScope(
        symbols=frozenset({"BTCUSDT"}),
        feature_count=6,
        start_ts=0,
        end_ts=1,
    )
    with pytest.raises(ReadinessGateError, match="not canonical"):
        compute_readiness("SCALP", _passing_evidence("SCALP"), scope)


def test_non_canonical_scope_requires_reason_when_opted_out() -> None:
    scope = DataScope(symbols=frozenset({"BTCUSDT"}), feature_count=6, start_ts=0, end_ts=1)
    with pytest.raises(ReadinessGateError, match="partial_scope_reason"):
        compute_readiness(
            "SCALP", _passing_evidence("SCALP"), scope, allow_partial_scope=True
        )


def test_non_canonical_scope_succeeds_with_explicit_reason() -> None:
    scope = DataScope(symbols=frozenset({"BTCUSDT"}), feature_count=6, start_ts=0, end_ts=1)
    readiness = compute_readiness(
        "SCALP",
        _passing_evidence("SCALP"),
        scope,
        allow_partial_scope=True,
        partial_scope_reason="synthetic smoke test",
    )
    assert readiness.gate_completion_pct == 100.0
    assert not readiness.scope.is_canonical()


def test_unsupported_mode_raises() -> None:
    with pytest.raises(ReadinessGateError, match="Unsupported mode"):
        compute_readiness("SWANG", _passing_evidence("SWING"), _canonical_scope())


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    readiness = compute_readiness("SCALP", _passing_evidence("SCALP"), _canonical_scope())
    written = write_readiness_checkpoint(
        readiness,
        commands_run=["pytest v7/tests/test_lite_readiness_gate.py -q"],
        checkpoint_dir=tmp_path,
        scope_confirmation="synthetic round-trip test",
        safe_next_step="n/a",
    )
    assert written.exists()
    parsed = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert parsed["mode"] == "SCALP"
    assert parsed["v7_lite_readiness_percent"] == pytest.approx(100.0)
    assert parsed["result"] == "PASS"
    assert set(parsed["gate_results"].keys()) == set(REQUIRED_GATES)
    assert parsed["data_scope"]["symbol_count"] == CANONICAL_SYMBOL_COUNT


def test_checkpoint_result_is_hold_when_incomplete(tmp_path: Path) -> None:
    mode = "SWING"
    evidence = _passing_evidence(mode)
    del_gate = "G2"
    t = MODE_THRESHOLDS[mode]
    evidence[del_gate] = GateEvidence(folds=t["min_folds"] - 1, oos_months=t["min_oos_months"])
    readiness = compute_readiness(mode, evidence, _canonical_scope())
    written = write_readiness_checkpoint(
        readiness,
        commands_run=["pytest"],
        checkpoint_dir=tmp_path,
    )
    parsed = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert parsed["result"] == "HOLD"
    assert parsed["gate_results"]["G2"]["passed"] is False
    assert "gate:G2:" in "".join(parsed["remaining_holds"])


def test_checkpoint_id_auto_increments(tmp_path: Path) -> None:
    readiness = compute_readiness("SWING", _passing_evidence("SWING"), _canonical_scope())
    (tmp_path / "v7_lite_checkpoint_003_foo.accp.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "v7_lite_checkpoint_014_bar.accp.yaml").write_text("x", encoding="utf-8")
    written = write_readiness_checkpoint(
        readiness, commands_run=[], checkpoint_dir=tmp_path
    )
    parsed = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert parsed["checkpoint_id"] == "V7LITE-015"


def test_thresholds_match_evaluation_doc_pinned_values() -> None:
    """Cross-check a subset of MODE_THRESHOLDS against the documented table
    in v7/docs/pipeline/evaluation.md to catch doc/code drift."""
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "pipeline" / "evaluation.md"
    text = doc_path.read_text(encoding="utf-8")

    assert re.search(r"Minimum expectancy R.*?0\.15R.*?0\.05R.*?0\.03R", text, re.S)
    assert MODE_THRESHOLDS["SWING"]["min_expectancy_r"] == 0.15
    assert MODE_THRESHOLDS["SCALP"]["min_expectancy_r"] == 0.05
    assert MODE_THRESHOLDS["AGGRESSIVE_SCALP"]["min_expectancy_r"] == 0.03

    threshold_table = text.split("### Mode-Specific Promotion Thresholds")[1].split(
        "### SWING Baseline Rationale"
    )[0]
    assert "[HOLD]" not in threshold_table
    assert threshold_table.count("[LOCKED_INITIAL_BASELINE]") >= 3 * len(MODE_THRESHOLDS) - 3
