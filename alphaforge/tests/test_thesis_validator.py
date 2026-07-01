"""Tests for ThesisValidator — alpha thesis validation against evidence.

Tests SUPPORTED, REFUTED, and INCONCLUSIVE verdicts; rejection rule
application; cross-reference between expected and actual evidence;
evidence bundling; and edge cases.

WS-06-NO-FAKE-TESTS: Negative/structural tests only — verify the validator
logic, not model outputs.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

import pytest

from alphaforge.lifecycle.state_machine import AlphaThesisState
from alphaforge.validation.contracts import NOT_EVALUATED, Mode
from alphaforge.validation.thesis_validator import (
    AlphaThesis,
    CostStressEvidence,
    NoTradeComparison,
    OverfitRiskAssessment,
    RegimeBreakdownEvidence,
    SymbolStabilityEvidence,
    ThesisValidator,
    ThesisVerdict,
    ValidationEvidence,
    WFVEvidence,
)


# =========================================================================
# Helpers
# =========================================================================


def _make_validator() -> ThesisValidator:
    return ThesisValidator()


def _make_thesis(
    thesis_id: str = "TH_001",
    hypothesis: str = "BTC leads altcoins with 1-4h delay.",
    mode: Mode = Mode.SWING,
    expected_evidence: Dict[str, Any] | None = None,
    rejection_criteria: List[str] | None = None,
) -> AlphaThesis:
    return AlphaThesis(
        thesis_id=thesis_id,
        hypothesis=hypothesis,
        mode=mode,
        expected_evidence=expected_evidence or {},
        rejection_criteria=rejection_criteria or [],
        status="PROPOSED",
    )


def _make_positive_wfv() -> WFVEvidence:
    """WFV evidence that strongly supports a thesis."""
    return WFVEvidence(
        fold_count=6,
        oos_expectancy=2.0,
        oos_sharpe=1.2,
        oos_win_rate=0.60,
        oos_max_drawdown=-0.15,
        oos_profit_factor=2.5,
        oos_trades_count=150,
        oos_positive_expectancy=True,
        fold_stability_score=0.80,
    )


def _make_negative_wfv() -> WFVEvidence:
    """WFV evidence that refutes a thesis."""
    return WFVEvidence(
        fold_count=3,
        oos_expectancy=-0.5,
        oos_sharpe=-0.3,
        oos_win_rate=0.35,
        oos_max_drawdown=-0.60,
        oos_profit_factor=0.8,
        oos_trades_count=80,
        oos_positive_expectancy=False,
        fold_stability_score=0.30,
    )


def _make_surviving_cost_stress() -> CostStressEvidence:
    """Cost stress where edge survives all scenarios."""
    return CostStressEvidence(
        fee_stress_edge_survives=True,
        slippage_stress_edge_survives=True,
        spread_stress_edge_survives=True,
        combined_stress_edge_survives=True,
        break_even_cost_total_pct=0.15,
        cost_edge_destroyed=False,
        funding_deferred=True,
    )


def _make_failing_cost_stress() -> CostStressEvidence:
    """Cost stress where edge is destroyed."""
    return CostStressEvidence(
        fee_stress_edge_survives=False,
        slippage_stress_edge_survives=False,
        spread_stress_edge_survives=False,
        combined_stress_edge_survives=False,
        break_even_cost_total_pct=0.02,
        cost_edge_destroyed=True,
        funding_deferred=True,
    )


def _make_broad_regime() -> RegimeBreakdownEvidence:
    """Regime breakdown where edge works across all regimes."""
    return RegimeBreakdownEvidence(
        edge_present_in_regimes=["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"],
        edge_only_in_rare_regime=False,
        rare_regime_untradeable=False,
        regime_count=4,
        regimes_with_edge=4,
    )


def _make_narrow_regime() -> RegimeBreakdownEvidence:
    """Regime breakdown where edge only in one rare regime."""
    return RegimeBreakdownEvidence(
        edge_present_in_regimes=["TRANSITION"],
        edge_only_in_rare_regime=True,
        rare_regime_untradeable=True,
        regime_count=4,
        regimes_with_edge=1,
    )


def _make_positive_no_trade() -> NoTradeComparison:
    """NO_TRADE comparison where active beats baseline."""
    return NoTradeComparison(
        active_beats_no_trade=True,
        long_better_than_no_trade=True,
        short_better_than_no_trade=False,
        saved_loss_r=0.3,
        missed_opportunity_r=0.1,
    )


def _make_negative_no_trade() -> NoTradeComparison:
    """NO_TRADE comparison where active loses to baseline."""
    return NoTradeComparison(
        active_beats_no_trade=False,
        long_better_than_no_trade=False,
        short_better_than_no_trade=False,
        saved_loss_r=0.0,
        missed_opportunity_r=0.5,
    )


def _make_good_symbol_stability() -> SymbolStabilityEvidence:
    """Symbol stability with multi-symbol coverage."""
    return SymbolStabilityEvidence(
        symbols_tested=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        symbol_count=3,
        max_single_symbol_concentration=0.25,
        max_cluster_concentration=0.45,
        single_symbol_limitation=False,
        cross_symbol_variance=0.05,
    )


def _make_bad_symbol_stability() -> SymbolStabilityEvidence:
    """Symbol stability with single-symbol overfit."""
    return SymbolStabilityEvidence(
        symbols_tested=["BTCUSDT"],
        symbol_count=1,
        max_single_symbol_concentration=1.0,
        max_cluster_concentration=1.0,
        single_symbol_limitation=True,
        cross_symbol_variance=0.0,
    )


def _make_low_overfit() -> OverfitRiskAssessment:
    """Low overfit risk."""
    return OverfitRiskAssessment(
        overall_risk="LOW",
        train_oos_gap="LOW",
        fold_instability="LOW",
        purge_violation_detected=False,
    )


def _make_critical_overfit() -> OverfitRiskAssessment:
    """Critical overfit risk."""
    return OverfitRiskAssessment(
        overall_risk="CRITICAL",
        train_oos_gap="HIGH",
        fold_instability="HIGH",
        purge_violation_detected=True,
    )


def _make_all_supporting_evidence() -> ValidationEvidence:
    """Evidence bundle where everything supports the thesis."""
    return ValidationEvidence(
        wfv=_make_positive_wfv(),
        cost_stress=_make_surviving_cost_stress(),
        regime_breakdown=_make_broad_regime(),
        no_trade=_make_positive_no_trade(),
        symbol_stability=_make_good_symbol_stability(),
        overfit=_make_low_overfit(),
        mht_correction_method="FDR",
        data_snooping_risk_flag="LOW",
    )


def _make_all_refuting_evidence() -> ValidationEvidence:
    """Evidence bundle where everything refutes the thesis."""
    return ValidationEvidence(
        wfv=_make_negative_wfv(),
        cost_stress=_make_failing_cost_stress(),
        regime_breakdown=_make_narrow_regime(),
        no_trade=_make_negative_no_trade(),
        symbol_stability=_make_bad_symbol_stability(),
        overfit=_make_critical_overfit(),
        mht_correction_method="NONE_APPLIED",
        data_snooping_risk_flag="CRITICAL",
    )


# =========================================================================
# SUPPORTED verdict tests
# =========================================================================


class TestSupportedVerdict:
    """Tests where all evidence supports the thesis hypothesis."""

    def test_all_evidence_supports_yields_supported(self):
        """When all evidence categories are positive, verdict is SUPPORTED."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = _make_all_supporting_evidence()

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED, (
            f"Expected SUPPORTED, got {result.verdict}. Notes: {result.notes}"
        )
        assert "SUPPORTED" in result.notes
        # SUPPORTED from PROPOSED advances one pipeline step → DATA_READY
        assert result.status == AlphaThesisState.DATA_READY

    def test_supported_wfv_plus_cost_stress_suffices(self):
        """SUPPORTED verdict when WFV and cost stress are positive, even if
        other categories are not evaluated."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            cost_stress=_make_surviving_cost_stress(),
            no_trade=_make_positive_no_trade(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED

    def test_positive_wfv_and_no_trade_supports(self):
        """Positive WFV + NO_TRADE edge, with cost/regime not evaluated, is
        SUPPORTED (partial confirmations > inconclusive)."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            no_trade=_make_positive_no_trade(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        # Strong confirmations from WFV + NO_TRADE + overfit are enough
        assert result.verdict == ThesisVerdict.SUPPORTED


# =========================================================================
# REFUTED verdict tests
# =========================================================================


class TestRefutedVerdict:
    """Tests where evidence contradicts the thesis hypothesis."""

    def test_all_evidence_refutes_yields_refuted(self):
        """When all evidence categories refute, verdict is REFUTED."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = _make_all_refuting_evidence()

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED, (
            f"Expected REFUTED, got {result.verdict}. Notes: {result.notes}"
        )
        assert "REJECTED" in result.notes

    def test_negative_oos_expectancy_refutes(self):
        """Non-positive OOS expectancy alone refutes the thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_negative_wfv(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED
        assert "expectancy" in result.notes.lower()

    def test_no_trade_beats_active_refutes(self):
        """If NO_TRADE beats active trading, thesis is REFUTED."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            no_trade=_make_negative_no_trade(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_cost_edge_destroyed_refutes(self):
        """Edge destroyed by baseline costs refutes thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            cost_stress=_make_failing_cost_stress(),
            no_trade=_make_positive_no_trade(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_single_symbol_overfit_refutes(self):
        """Edge only on one symbol refutes thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            symbol_stability=_make_bad_symbol_stability(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_rare_regime_overfit_refutes(self):
        """Edge only in rare untradeable regime refutes thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            regime_breakdown=_make_narrow_regime(),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_critical_overfit_refutes(self):
        """Critical overfit risk refutes thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            overfit=_make_critical_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_expected_evidence_contradicted_refutes(self):
        """When expected_evidence sets a threshold that actual data does not
        meet, the thesis is REFUTED."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_oos_expectancy": 10.0},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),  # oos_expectancy=2.0
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_combined_stress_survival_failure_refutes(self):
        """Combined fee+slippage stress destroying the edge refutes thesis."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            cost_stress=CostStressEvidence(
                fee_stress_edge_survives=True,
                slippage_stress_edge_survives=True,
                combined_stress_edge_survives=False,
                cost_edge_destroyed=False,
            ),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED


# =========================================================================
# INCONCLUSIVE verdict tests
# =========================================================================


class TestInconclusiveVerdict:
    """Tests where evidence is insufficient for a conclusive verdict."""

    def test_no_evidence_yields_inconclusive(self):
        """When no evidence is provided, verdict is INCONCLUSIVE."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence()

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.INCONCLUSIVE
        assert "No evidence" in result.notes or "unevaluated" in result.notes.lower()
        assert "not yet evaluated" in result.notes.lower()

    def test_only_unchecked_expected_evidence_yields_inconclusive(self):
        """When expected_evidence references unevaluated metrics, INCONCLUSIVE."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_oos_expectancy": 1.0},
        )
        evidence = ValidationEvidence(overfit=_make_low_overfit())

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.INCONCLUSIVE

    def test_mixed_wfv_and_unevaluated_cost_yields_inconclusive(self):
        """Only 1 evidence category (WFV) confirmed, rest not evaluated —
        overall INCONCLUSIVE (needs >= 2 confirmed for SUPPORTED)."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_oos_expectancy": 1.0},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
        )

        result = v.validate(thesis, evidence)
        # WFV is positive, but only 1 category confirmed
        # Overfit/cost/regime/no_trade/symbol not evaluated
        assert result.verdict == ThesisVerdict.INCONCLUSIVE

    def test_no_expected_evidence_with_positive_evidence_inconclusive(self):
        """Positive wfv evidence without expected criteria -> inconclusive."""
        v = _make_validator()
        thesis = _make_thesis()  # No expected_evidence
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
        )

        result = v.validate(thesis, evidence)
        # WFV is positive and overfit not evaluated -> some confirmations,
        # some inconclusive: INCONCLUSIVE
        assert result.verdict == ThesisVerdict.INCONCLUSIVE


# =========================================================================
# Cross-reference tests
# =========================================================================


class TestCrossReference:
    """Tests for expected_evidence vs actual_evidence cross-referencing."""

    def test_expected_expectancy_met(self):
        """When actual OOS expectancy meets expected minimum, it confirms."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_oos_expectancy": 1.5},
        )
        evidence = _make_all_supporting_evidence()  # oos_expectancy=2.0

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED

    def test_expected_win_rate_not_met_refutes(self):
        """When actual win rate is below expected, it refutes."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_win_rate": 0.80},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),  # win_rate=0.60
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_expected_folds_met(self):
        """When actual folds meet expected min, it confirms."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_folds": 6},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),  # fold_count=6
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED

    def test_expected_folds_not_met_refutes(self):
        """When actual folds < expected, it refutes."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_folds": 12},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),  # fold_count=6
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_expected_regime_coverage_not_met_refutes(self):
        """When actual regimes_with_edge < expected, it refutes."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_regimes_with_edge": 3},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            regime_breakdown=RegimeBreakdownEvidence(
                regime_count=4,
                regimes_with_edge=1,
                edge_present_in_regimes=["TREND_UP"],
            ),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_expected_symbol_count_not_met_refutes(self):
        """When actual symbol_count < expected, it refutes."""
        v = _make_validator()
        thesis = _make_thesis(
            expected_evidence={"min_symbols": 5},
        )
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            symbol_stability=_make_good_symbol_stability(),  # 3 symbols
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED


# =========================================================================
# Evidence dataclass tests
# =========================================================================


class TestEvidenceDataclasses:
    """Tests for evidence dataclass behavior."""

    def test_wfv_evidence_is_evaluated(self):
        """WFVEvidence.is_evaluated() returns True when OOS expectancy set."""
        assert _make_positive_wfv().is_evaluated() is True
        assert WFVEvidence().is_evaluated() is False

    def test_cost_stress_is_evaluated(self):
        """CostStressEvidence.is_evaluated() returns True when fee stress set."""
        assert _make_surviving_cost_stress().is_evaluated() is True
        assert CostStressEvidence().is_evaluated() is False

    def test_no_trade_is_evaluated(self):
        """NoTradeComparison.is_evaluated() returns True when active_beats set."""
        assert _make_positive_no_trade().is_evaluated() is True
        assert NoTradeComparison().is_evaluated() is False

    def test_symbol_stability_is_evaluated(self):
        """SymbolStabilityEvidence.is_evaluated() returns True when conc set."""
        assert _make_good_symbol_stability().is_evaluated() is True
        assert SymbolStabilityEvidence().is_evaluated() is False

    def test_overfit_is_evaluated(self):
        """OverfitRiskAssessment.is_evaluated() returns True when risk set."""
        assert _make_low_overfit().is_evaluated() is True
        assert OverfitRiskAssessment().is_evaluated() is False

    def test_validation_evidence_is_any_evaluated(self):
        """ValidationEvidence.is_any_evaluated with at least one component."""
        empty = ValidationEvidence()
        assert empty.is_any_evaluated is False

        partial = ValidationEvidence(wfv=_make_positive_wfv())
        assert partial.is_any_evaluated is True

    def test_regime_breakdown_edge_in_all_regimes(self):
        """RegimeBreakdownEvidence.edge_in_all_regimes() behavior."""
        rb = _make_broad_regime()
        assert rb.edge_in_all_regimes() is True
        assert rb.edge_in_no_regime() is False

        narrow = _make_narrow_regime()
        assert narrow.edge_in_all_regimes() is False
        assert narrow.edge_in_no_regime() is False

        none_regime = RegimeBreakdownEvidence(regime_count=4, regimes_with_edge=0)
        assert none_regime.edge_in_no_regime() is True

    def test_symbol_stability_concentration_violations(self):
        """SymbolStabilityEvidence concentration limit checks."""
        good = _make_good_symbol_stability()
        assert good.violates_concentration_limit() is False
        assert good.violates_cluster_limit() is False

        bad = SymbolStabilityEvidence(
            symbol_count=2,
            max_single_symbol_concentration=0.60,  # > 0.40
            max_cluster_concentration=0.80,  # > 0.60
        )
        assert bad.violates_concentration_limit() is True
        assert bad.violates_cluster_limit() is True

    def test_overfit_is_critical(self):
        """OverfitRiskAssessment.is_critical() behavior."""
        assert _make_critical_overfit().is_critical() is True
        assert _make_low_overfit().is_critical() is False


# =========================================================================
# ThesisVerdict enum tests
# =========================================================================


class TestThesisVerdict:
    """Tests for ThesisVerdict enum."""

    def test_verdict_values(self):
        assert ThesisVerdict.SUPPORTED.value == "SUPPORTED"
        assert ThesisVerdict.REFUTED.value == "REFUTED"
        assert ThesisVerdict.INCONCLUSIVE.value == "INCONCLUSIVE"

    def test_verdict_is_string_enum(self):
        assert isinstance(ThesisVerdict.SUPPORTED, str)
        assert ThesisVerdict.SUPPORTED == "SUPPORTED"


# =========================================================================
# AlphaThesis dataclass tests
# =========================================================================


class TestAlphaThesis:
    """Tests for AlphaThesis dataclass."""

    def test_thesis_is_frozen(self):
        thesis = _make_thesis()
        with pytest.raises(dataclasses.FrozenInstanceError):
            thesis.verdict = ThesisVerdict.SUPPORTED  # type: ignore[misc]

    def test_thesis_defaults(self):
        thesis = AlphaThesis(
            thesis_id="TH_001",
            hypothesis="Test hypothesis.",
        )
        assert thesis.mode == Mode.SWING
        assert thesis.verdict == ThesisVerdict.INCONCLUSIVE
        assert thesis.status == "PROPOSED"
        assert thesis.expected_evidence == {}
        assert thesis.rejection_criteria == []

    def test_thesis_id_must_be_string(self):
        thesis = AlphaThesis(
            thesis_id="TH_002",
            hypothesis="Another hypothesis.",
        )
        assert isinstance(thesis.thesis_id, str)
        assert len(thesis.thesis_id) > 0


# =========================================================================
# Rejection rules coverage tests
# =========================================================================


class TestRejectionRules:
    """Tests for specific rejection rules from alpha_thesis_lifecycle.md."""

    def test_no_trade_beats_both_sides_refutes(self):
        """Rule: If NO_TRADE beats both directional actions, REJECT."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_positive_wfv(),
            no_trade=NoTradeComparison(
                active_beats_no_trade=False,
                long_better_than_no_trade=False,
                short_better_than_no_trade=False,
            ),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_non_positive_oos_expectancy_refutes(self):
        """Rule: Non-positive OOS expectancy is a rejection criterion."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=_make_negative_wfv(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED

    def test_excessive_drawdown_refutes(self):
        """Rule: Drawdown exceeding threshold refutes."""
        v = _make_validator()
        thesis = _make_thesis()
        evidence = ValidationEvidence(
            wfv=WFVEvidence(
                fold_count=6,
                oos_expectancy=1.0,
                oos_sharpe=0.8,
                oos_win_rate=0.55,
                oos_max_drawdown=-0.65,
                oos_positive_expectancy=True,
            ),
            overfit=_make_low_overfit(),
        )

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.REFUTED


# =========================================================================
# Mode-aware tests
# =========================================================================


class TestModeAwareValidation:
    """Tests that thesis validation is mode-aware."""

    def test_scalp_thesis_validates(self):
        """SCALP mode thesis can be validated."""
        v = _make_validator()
        thesis = AlphaThesis(
            thesis_id="TH_SCALP_001",
            hypothesis="Altcoin delay after BTC moves in fast timeframes.",
            mode=Mode.SCALP,
            expected_evidence={"min_oos_expectancy": 0.10},
        )
        evidence = _make_all_supporting_evidence()

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED
        assert result.mode == Mode.SCALP

    def test_aggressive_scalp_thesis_validates(self):
        """AGGRESSIVE_SCALP mode thesis can be validated."""
        v = _make_validator()
        thesis = AlphaThesis(
            thesis_id="TH_AGSCALP_001",
            hypothesis="Microstructure patterns in 5m candles.",
            mode=Mode.AGGRESSIVE_SCALP,
        )
        evidence = _make_all_supporting_evidence()

        result = v.validate(thesis, evidence)
        assert result.verdict == ThesisVerdict.SUPPORTED
        assert result.mode == Mode.AGGRESSIVE_SCALP


# =========================================================================
# No-ML-import scan
# =========================================================================


class TestNoMLImports:
    """Verify zero ML library imports in thesis_validator module."""

    def test_no_xgboost_import(self):
        """thesis_validator.py contains zero xgboost/sklearn/tf/torch imports."""
        forbidden = [
            "xgboost", "XGBClassifier", "XGBRegressor",
            "sklearn", "tensorflow", "torch",
        ]
        import alphaforge.validation.thesis_validator as tvmod

        for term in forbidden:
            assert not hasattr(tvmod, term), (
                f"thesis_validator.py has attribute '{term}'"
            )

    def test_no_fit_call_in_source(self):
        """No 'model.fit(', '.fit(', or '=fit(' in thesis_validator source."""
        import inspect
        import alphaforge.validation.thesis_validator as tvmod

        src = inspect.getsource(tvmod)
        # Check for ML-style .fit( calls on an object (not method name prefixes like _check_overfit)
        ml_patterns = [".fit(", "=fit(", " fit("]
        for pattern in ml_patterns:
            assert pattern not in src, (
                f"thesis_validator.py contains ML fit() pattern '{pattern}'"
            )
