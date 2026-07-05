"""ThesisValidator — validate alpha theses against empirical evidence.

Evaluates whether observed evidence from walk-forward validation, cost stress,
regime breakdown, NO_TRADE comparison, symbol stability, and overfit assessment
supports or refutes an alpha thesis hypothesis.

Each thesis carries: hypothesis, expected_evidence, actual_evidence, verdict.
Verdicts: SUPPORTED (evidence confirms), REFUTED (evidence contradicts),
INCONCLUSIVE (insufficient evidence either way).

This module imports ZERO ML libraries (no xgboost, sklearn, tensorflow, torch).
Validation is evidence-gate logic only — no model training, no metrics computation.

Domain boundary: AlphaForge owns thesis validation. V7 owns final acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from alphaforge.lifecycle.state_machine import (
    AlphaThesisState,
    ThesisStateMachine,
)
from alphaforge.validation.contracts import NOT_EVALUATED, Mode


# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------


class ThesisVerdict(str, Enum):
    """Validation verdict for an alpha thesis.

    SUPPORTED: observed evidence matches expected evidence — hypothesis confirmed.
    REFUTED:   observed evidence contradicts expected evidence — hypothesis rejected.
    INCONCLUSIVE: insufficient evidence or mixed signal — more research needed.
    """

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Evidence dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WFVEvidence:
    """Walk-forward validation evidence for thesis evaluation.

    All float fields are Optional[float] — None means NOT_EVALUATED.
    """

    fold_count: int = 0
    oos_expectancy: Optional[float] = None
    oos_sharpe: Optional[float] = None
    oos_win_rate: Optional[float] = None
    oos_max_drawdown: Optional[float] = None
    oos_profit_factor: Optional[float] = None
    oos_trades_count: int = 0
    oos_positive_expectancy: bool = False
    fold_stability_score: Optional[float] = None

    def is_evaluated(self) -> bool:
        """True if at least core OOS metrics are populated (not None)."""
        return self.oos_expectancy is not None


@dataclass(frozen=True)
class CostStressEvidence:
    """Cost stress analysis evidence for thesis evaluation.

    Tracks whether the edge survives under fee, slippage, and combined stress.
    """

    fee_stress_edge_survives: Optional[bool] = None
    slippage_stress_edge_survives: Optional[bool] = None
    spread_stress_edge_survives: Optional[bool] = None
    combined_stress_edge_survives: Optional[bool] = None
    break_even_cost_total_pct: Optional[float] = None
    cost_edge_destroyed: bool = False
    funding_deferred: bool = True

    def is_evaluated(self) -> bool:
        """True if stress survival checks are populated."""
        return self.fee_stress_edge_survives is not None


@dataclass(frozen=True)
class RegimeBreakdownEvidence:
    """Regime breakdown evidence for thesis evaluation.

    Uses V7 canonical regime taxonomy: TREND_UP, TREND_DOWN, RANGE, TRANSITION.
    """

    edge_present_in_regimes: List[str] = field(default_factory=list)
    edge_only_in_rare_regime: bool = False
    rare_regime_untradeable: bool = False
    regime_count: int = 0
    regimes_with_edge: int = 0

    def edge_in_all_regimes(self) -> bool:
        """True if edge is present in all four canonical regimes."""
        return self.regimes_with_edge >= 4

    def edge_in_no_regime(self) -> bool:
        """True if edge is absent from all regimes."""
        return self.regime_count > 0 and self.regimes_with_edge == 0


@dataclass(frozen=True)
class NoTradeComparison:
    """NO_TRADE comparison evidence for thesis evaluation.

    Answers: is the alpha better than doing nothing?
    """

    active_beats_no_trade: Optional[bool] = None
    long_better_than_no_trade: Optional[bool] = None
    short_better_than_no_trade: Optional[bool] = None
    saved_loss_r: Optional[float] = None
    missed_opportunity_r: Optional[float] = None

    def is_evaluated(self) -> bool:
        """True if active_beats_no_trade is populated."""
        return self.active_beats_no_trade is not None


@dataclass(frozen=True)
class SymbolStabilityEvidence:
    """Symbol stability evidence for thesis evaluation.

    Tracks symbol concentration and cross-symbol variance.
    MAX_SINGLE_SYMBOL_CONCENTRATION = 0.40 per V7 G5.
    MAX_CLUSTER_CONCENTRATION = 0.60 per V7 G5.
    """

    MAX_SINGLE_SYMBOL_CONCENTRATION: float = 0.40
    MAX_CLUSTER_CONCENTRATION: float = 0.60

    symbols_tested: List[str] = field(default_factory=list)
    symbol_count: int = 0
    max_single_symbol_concentration: Optional[float] = None
    max_cluster_concentration: Optional[float] = None
    single_symbol_limitation: bool = False
    cross_symbol_variance: Optional[float] = None

    def is_evaluated(self) -> bool:
        """True if symbol stability metrics are populated."""
        return self.max_single_symbol_concentration is not None

    def violates_concentration_limit(self) -> bool:
        """True if single-symbol concentration exceeds 40% limit."""
        if self.max_single_symbol_concentration is None:
            return False
        return self.max_single_symbol_concentration > self.MAX_SINGLE_SYMBOL_CONCENTRATION

    def violates_cluster_limit(self) -> bool:
        """True if cluster concentration exceeds 60% limit."""
        if self.max_cluster_concentration is None:
            return False
        return self.max_cluster_concentration > self.MAX_CLUSTER_CONCENTRATION


@dataclass(frozen=True)
class OverfitRiskAssessment:
    """Overfit risk assessment for thesis evaluation.

    Captures the overfit risk indicators from validation.
    """

    overall_risk: str = "NOT_EVALUATED"  # LOW, MEDIUM, HIGH, CRITICAL, NOT_EVALUATED
    train_oos_gap: Optional[str] = None
    fold_instability: Optional[str] = None
    feature_to_sample_ratio: Optional[str] = None
    top_feature_dominance: Optional[str] = None
    calibration_degradation: Optional[str] = None
    purge_violation_detected: bool = False

    def is_evaluated(self) -> bool:
        """True if overfit assessment has been performed."""
        return self.overall_risk != "NOT_EVALUATED"

    def is_critical(self) -> bool:
        """True if overfit risk is CRITICAL."""
        return self.overall_risk == "CRITICAL"


@dataclass(frozen=True)
class ValidationEvidence:
    """Aggregated validation evidence for thesis evaluation.

    Bundles all evidence categories: WFV, cost stress, regime breakdown,
    NO_TRADE comparison, symbol stability, overfit assessment, and MHT controls.
    """

    wfv: WFVEvidence = field(default_factory=WFVEvidence)
    cost_stress: CostStressEvidence = field(default_factory=CostStressEvidence)
    regime_breakdown: RegimeBreakdownEvidence = field(
        default_factory=RegimeBreakdownEvidence
    )
    no_trade: NoTradeComparison = field(default_factory=NoTradeComparison)
    symbol_stability: SymbolStabilityEvidence = field(
        default_factory=SymbolStabilityEvidence
    )
    overfit: OverfitRiskAssessment = field(default_factory=OverfitRiskAssessment)
    mht_correction_method: str = "NONE_APPLIED"
    data_snooping_risk_flag: str = "HIGH"

    @property
    def is_any_evaluated(self) -> bool:
        """True if at least one evidence category has actual data."""
        return (
            self.wfv.is_evaluated()
            or self.cost_stress.is_evaluated()
            or self.no_trade.is_evaluated()
            or self.symbol_stability.is_evaluated()
            or self.overfit.is_evaluated()
        )


# ---------------------------------------------------------------------------
# Alpha Thesis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlphaThesis:
    """A formal alpha thesis — hypothesis with expected and actual evidence.

    Fields:
        thesis_id: Unique identifier.
        hypothesis: Core hypothesis statement.
        mode: Trading mode this thesis targets.
        expected_evidence: Dict describing what evidence would SUPPORT the thesis.
        actual_evidence: Dict summarizing what evidence was observed.
        verdict: Computed verdict (SUPPORTED / REFUTED / INCONCLUSIVE).
        rejection_criteria: Explicit criteria that would refute the thesis.
        status: Lifecycle state per alpha_thesis_lifecycle.md (AlphaThesisState enum).
        state_machine: ThesisStateMachine managing the lifecycle transitions.
        notes: Additional context or explanation of verdict.
    """

    thesis_id: str
    hypothesis: str
    mode: Mode = Mode.SWING
    expected_evidence: Dict[str, Any] = field(default_factory=dict)
    actual_evidence: Dict[str, Any] = field(default_factory=dict)
    verdict: ThesisVerdict = ThesisVerdict.INCONCLUSIVE
    rejection_criteria: List[str] = field(default_factory=list)
    status: AlphaThesisState = AlphaThesisState.PROPOSED
    state_machine: Optional[ThesisStateMachine] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# ThesisValidator
# ---------------------------------------------------------------------------


class ThesisValidator:
    """Validate alpha theses against empirical evidence.

    Evaluates whether observed evidence from walk-forward validation, cost
    stress, regime breakdown, NO_TRADE comparison, symbol stability, and
    overfit assessment supports or refutes the thesis hypothesis.

    The validator applies the rejection rules from alpha_thesis_lifecycle.md
    and cross-references expected evidence against actual evidence.
    """

    # ------------------------------------------------------------------
    # Pipeline advancement
    # ------------------------------------------------------------------

    @staticmethod
    def _advance_pipeline(sm: ThesisStateMachine) -> ThesisStateMachine:
        """Advance the state machine to the next logical state in the pipeline.

        Supports the normal forward progression:
        PROPOSED → DATA_READY → FEATURED → SIMULATED → TRAINED → VALIDATED
        """
        _PIPELINE_ORDER = [
            AlphaThesisState.PROPOSED,
            AlphaThesisState.DATA_READY,
            AlphaThesisState.FEATURED,
            AlphaThesisState.SIMULATED,
            AlphaThesisState.TRAINED,
            AlphaThesisState.VALIDATED,
        ]
        current = sm.current_state
        for i, state in enumerate(_PIPELINE_ORDER):
            if state == current and i + 1 < len(_PIPELINE_ORDER):
                next_state = _PIPELINE_ORDER[i + 1]
                # Use the appropriate transition method
                if next_state == AlphaThesisState.DATA_READY:
                    return sm.mark_data_ready(notes="Pipeline advancement: data ready.")
                elif next_state == AlphaThesisState.FEATURED:
                    return sm.mark_featured(notes="Pipeline advancement: featured.")
                elif next_state == AlphaThesisState.SIMULATED:
                    return sm.mark_simulated(notes="Pipeline advancement: simulated.")
                elif next_state == AlphaThesisState.TRAINED:
                    return sm.mark_trained(notes="Pipeline advancement: trained.")
                elif next_state == AlphaThesisState.VALIDATED:
                    return sm.mark_validated(notes="Pipeline advancement: validated.")
        # If already at VALIDATED or beyond, no pipeline advancement
        return sm

    def validate(
        self,
        thesis: AlphaThesis,
        evidence: ValidationEvidence,
    ) -> AlphaThesis:
        """Validate a thesis against evidence and return a new thesis with verdict.

        Args:
            thesis: The alpha thesis to validate.
            evidence: Aggregated validation evidence.

        Returns:
            A new AlphaThesis with verdict and notes populated.

        The verdict logic:
        - REFUTED: Any rejection criterion fires, or evidence contradicts hypothesis.
        - SUPPORTED: All evaluated evidence categories confirm the thesis.
        - INCONCLUSIVE: No refuted evidence, but insufficient support or no evidence.
        """
        refutations: List[str] = []
        confirmations: List[str] = []
        inconclusive_reasons: List[str] = []

        # 1. Check hard rejection rules from alpha_thesis_lifecycle.md
        refutations.extend(self._check_rejection_rules(thesis, evidence))

        # 2. Check WFV evidence
        wfv_result = self._check_wfv(evidence)
        if wfv_result["refuted"]:
            refutations.extend(wfv_result["reasons"])
        elif wfv_result["supported"]:
            confirmations.extend(wfv_result["reasons"])
        else:
            inconclusive_reasons.extend(wfv_result["reasons"])

        # 3. Check cost stress evidence
        cost_result = self._check_cost_stress(evidence)
        if cost_result["refuted"]:
            refutations.extend(cost_result["reasons"])
        elif cost_result["supported"]:
            confirmations.extend(cost_result["reasons"])
        else:
            inconclusive_reasons.extend(cost_result["reasons"])

        # 4. Check regime breakdown evidence
        regime_result = self._check_regime_breakdown(evidence)
        if regime_result["refuted"]:
            refutations.extend(regime_result["reasons"])
        elif regime_result["supported"]:
            confirmations.extend(regime_result["reasons"])
        else:
            inconclusive_reasons.extend(regime_result["reasons"])

        # 5. Check NO_TRADE comparison
        notrade_result = self._check_no_trade(evidence)
        if notrade_result["refuted"]:
            refutations.extend(notrade_result["reasons"])
        elif notrade_result["supported"]:
            confirmations.extend(notrade_result["reasons"])
        else:
            inconclusive_reasons.extend(notrade_result["reasons"])

        # 6. Check symbol stability
        symbol_result = self._check_symbol_stability(evidence)
        if symbol_result["refuted"]:
            refutations.extend(symbol_result["reasons"])
        elif symbol_result["supported"]:
            confirmations.extend(symbol_result["reasons"])
        else:
            inconclusive_reasons.extend(symbol_result["reasons"])

        # 7. Check overfit risk
        overfit_result = self._check_overfit(evidence)
        if overfit_result["refuted"]:
            refutations.extend(overfit_result["reasons"])
        elif overfit_result["supported"]:
            confirmations.extend(overfit_result["reasons"])
        else:
            inconclusive_reasons.extend(overfit_result["reasons"])

        # 8. Cross-reference expected vs actual evidence
        cross_result = self._cross_reference(thesis, evidence)
        if cross_result["refuted"]:
            refutations.extend(cross_result["reasons"])
        elif cross_result["supported"]:
            confirmations.extend(cross_result["reasons"])
        else:
            inconclusive_reasons.extend(cross_result["reasons"])

        # Determine verdict
        # Count how many evidence categories confirmed (WFV, cost, regime,
        # no_trade, symbol, overfit).  Cross-reference is a filter, not a
        # confirmation source — it only adds refutations.
        confirmed_categories = sum(
            1
            for r in [
                wfv_result,
                cost_result,
                regime_result,
                notrade_result,
                symbol_result,
                overfit_result,
            ]
            if r["supported"]
        )

        if refutations:
            verdict = ThesisVerdict.REFUTED
            notes = (
                f"REJECTED: {len(refutations)} evidence categories refute the thesis. "
                + "; ".join(refutations)
            )
        elif confirmed_categories >= 2:
            verdict = ThesisVerdict.SUPPORTED
            notes = (
                f"SUPPORTED: {confirmed_categories} evidence categories support "
                f"the thesis. "
                + "; ".join(confirmations)
            )
            if inconclusive_reasons:
                notes += (
                    " | Unevaluated: " + "; ".join(inconclusive_reasons)
                )
        elif confirmed_categories >= 1:
            verdict = ThesisVerdict.INCONCLUSIVE
            notes = (
                f"INCONCLUSIVE: only {confirmed_categories} evidence "
                f"categor{'y' if confirmed_categories == 1 else 'ies'} "
                f"confirmed, {len(inconclusive_reasons)} unevaluated. "
                + "; ".join(confirmations)
                + " | Unevaluated: "
                + "; ".join(inconclusive_reasons)
            )
        elif inconclusive_reasons:
            verdict = ThesisVerdict.INCONCLUSIVE
            notes = (
                f"INCONCLUSIVE: {len(inconclusive_reasons)} evidence categories "
                f"are unevaluated or insufficient. "
                + "; ".join(inconclusive_reasons)
            )
        else:
            verdict = ThesisVerdict.INCONCLUSIVE
            notes = "No evidence available for evaluation."

        # Compute lifecycle state via state machine
        current_status = thesis.status
        if isinstance(current_status, str) and not isinstance(current_status, AlphaThesisState):
            # Handle legacy string status (backward compat)
            try:
                current_status = AlphaThesisState(current_status)
            except ValueError:
                current_status = AlphaThesisState.PROPOSED

        sm = thesis.state_machine or ThesisStateMachine(current_state=current_status)

        if verdict == ThesisVerdict.SUPPORTED:
            # Advance state along the pipeline
            if sm.current_state == AlphaThesisState.VALIDATED:
                sm = sm.promote_to_v7_candidate(
                    notes="Validation supports thesis — promoting to V7 candidate.",
                )
            elif sm.current_state in (
                AlphaThesisState.PROPOSED,
                AlphaThesisState.DATA_READY,
                AlphaThesisState.FEATURED,
                AlphaThesisState.SIMULATED,
                AlphaThesisState.TRAINED,
            ):
                # Advance to next state in pipeline
                sm = self._advance_pipeline(sm)
            return AlphaThesis(
                thesis_id=thesis.thesis_id,
                hypothesis=thesis.hypothesis,
                mode=thesis.mode,
                expected_evidence=thesis.expected_evidence,
                actual_evidence=thesis.actual_evidence,
                verdict=verdict,
                rejection_criteria=thesis.rejection_criteria,
                status=sm.current_state,
                state_machine=sm,
                notes=notes,
            )
        elif verdict == ThesisVerdict.REFUTED:
            sm = sm.reject(
                rejection_rules_fired=thesis.rejection_criteria or ["Evidence refutes thesis hypothesis."],
                rejection_detail=notes,
                notes=notes,
            )
            return AlphaThesis(
                thesis_id=thesis.thesis_id,
                hypothesis=thesis.hypothesis,
                mode=thesis.mode,
                expected_evidence=thesis.expected_evidence,
                actual_evidence=thesis.actual_evidence,
                verdict=verdict,
                rejection_criteria=thesis.rejection_criteria,
                status=sm.current_state,
                state_machine=sm,
                notes=notes,
            )
        else:
            # INCONCLUSIVE — continue research if from VALIDATED,
            # otherwise keep current state
            if sm.current_state == AlphaThesisState.VALIDATED:
                sm = sm.continue_research(
                    notes="Validation inconclusive — continuing research.",
                )
            return AlphaThesis(
                thesis_id=thesis.thesis_id,
                hypothesis=thesis.hypothesis,
                mode=thesis.mode,
                expected_evidence=thesis.expected_evidence,
                actual_evidence=thesis.actual_evidence,
                verdict=verdict,
                rejection_criteria=thesis.rejection_criteria,
                status=sm.current_state,
                state_machine=sm,
                notes=notes,
            )

    # ------------------------------------------------------------------
    # Rejection rules (alpha_thesis_lifecycle.md)
    # ------------------------------------------------------------------

    def _check_rejection_rules(
        self,
        thesis: AlphaThesis,
        evidence: ValidationEvidence,
    ) -> List[str]:
        """Apply hard rejection rules from alpha_thesis_lifecycle.md.

        Returns list of rejection reasons (empty if none fire).
        """
        refutations: List[str] = []

        # Rule 1: NO_TRADE beats directional
        if evidence.no_trade.is_evaluated():
            if evidence.no_trade.active_beats_no_trade is False:
                refutations.append(
                    "NO_TRADE beats directional: active trading underperforms doing nothing "
                    "after costs."
                )

        # Rule 2: Non-positive OOS expectancy
        if evidence.wfv.is_evaluated():
            if evidence.wfv.oos_positive_expectancy is False:
                refutations.append(
                    f"Non-positive OOS expectancy: "
                    f"oos_expectancy={evidence.wfv.oos_expectancy}."
                )

        # Rule 3: Cost stress flips edge negative
        if evidence.cost_stress.is_evaluated():
            if evidence.cost_stress.combined_stress_edge_survives is False:
                refutations.append(
                    "Cost stress flips edge negative: combined fee+slippage+spread "
                    "stress eliminates edge."
                )
            if evidence.cost_stress.cost_edge_destroyed:
                refutations.append(
                    "Edge destroyed at baseline costs."
                )

        # Rule 4: Single-symbol overfitting
        if evidence.symbol_stability.is_evaluated():
            if evidence.symbol_stability.single_symbol_limitation:
                refutations.append(
                    "Single-symbol overfitting: edge only demonstrated on one symbol "
                    "without documented rationale."
                )
            if evidence.symbol_stability.violates_concentration_limit():
                refutations.append(
                    f"Single-symbol concentration {evidence.symbol_stability.max_single_symbol_concentration} "
                    f"exceeds {evidence.symbol_stability.MAX_SINGLE_SYMBOL_CONCENTRATION} limit."
                )

        # Rule 5: Rare-regime overfitting
        if evidence.regime_breakdown.edge_only_in_rare_regime:
            refutations.append(
                "Rare-regime overfitting: edge only appears in a regime that is "
                "untradeable or too rare."
            )
        if evidence.regime_breakdown.rare_regime_untradeable:
            refutations.append(
                "Rare regime is untradeable."
            )
        if evidence.regime_breakdown.edge_in_no_regime():
            refutations.append(
                "Edge absent from all evaluated regimes."
            )

        # Rule 6: Feature leakage (purge violation)
        if evidence.overfit.purge_violation_detected:
            refutations.append(
                "Feature leakage detected: purge violation in train-test separation."
            )

        # Rule 7: Funding deferred and required
        if evidence.cost_stress.funding_deferred:
            # Not an automatic refutation, but noted
            pass

        # Rule 8: Excessive drawdown (check if wfv has drawdown data)
        if evidence.wfv.is_evaluated() and evidence.wfv.oos_max_drawdown is not None:
            if evidence.wfv.oos_max_drawdown < -0.50:  # 50% drawdown threshold
                refutations.append(
                    f"Excessive drawdown: max drawdown {evidence.wfv.oos_max_drawdown} "
                    f"exceeds mode-allowed threshold."
                )

        # Rule 9: Unusable calibration (captured in overfit)
        if evidence.overfit.is_critical():
            refutations.append(
                "Critical overfit risk: calibration quality is unreliable."
            )

        # Rule 10: Missing lineage / checksum (structural — not checked here)

        return refutations

    # ------------------------------------------------------------------
    # Evidence check methods
    # ------------------------------------------------------------------

    def _check_wfv(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check walk-forward validation evidence.

        Returns dict with refuted/supported/reasons keys.
        """
        wfv = evidence.wfv

        if not wfv.is_evaluated():
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["WFV metrics not yet evaluated."],
            }

        refutations: List[str] = []
        confirmations: List[str] = []

        # Positive OOS expectancy
        if wfv.oos_positive_expectancy:
            confirmations.append(
                f"Positive OOS expectancy: oos_expectancy={wfv.oos_expectancy}."
            )
        else:
            refutations.append(
                f"Non-positive OOS expectancy: oos_expectancy={wfv.oos_expectancy}."
            )

        # Sharpe ratio
        if wfv.oos_sharpe is not None:
            if wfv.oos_sharpe > 0.5:
                confirmations.append(
                    f"Acceptable OOS Sharpe: {wfv.oos_sharpe}."
                )
            elif wfv.oos_sharpe <= 0:
                refutations.append(
                    f"Non-positive OOS Sharpe: {wfv.oos_sharpe}."
                )

        # Win rate
        if wfv.oos_win_rate is not None and wfv.oos_win_rate > 0.50:
            confirmations.append(f"OOS win rate above 50%: {wfv.oos_win_rate}.")

        # Fold count minimum
        if wfv.fold_count >= 6:
            confirmations.append(f"Minimum folds satisfied: {wfv.fold_count}.")
        elif wfv.fold_count > 0:
            refutations.append(
                f"Insufficient folds: {wfv.fold_count} < 6 minimum."
            )

        if refutations:
            return {"refuted": True, "supported": False, "reasons": refutations}
        elif confirmations:
            return {"refuted": False, "supported": True, "reasons": confirmations}
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["WFV evidence present but inconclusive."],
        }

    def _check_cost_stress(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check cost stress evidence.

        Returns dict with refuted/supported/reasons keys.
        """
        cost = evidence.cost_stress

        if not cost.is_evaluated():
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["Cost stress not yet evaluated."],
            }

        refutations: List[str] = []
        confirmations: List[str] = []

        # Edge survives fee stress
        if cost.fee_stress_edge_survives is True:
            confirmations.append("Edge survives fee stress.")
        elif cost.fee_stress_edge_survives is False:
            refutations.append("Edge destroyed by fee stress.")

        # Edge survives slippage stress
        if cost.slippage_stress_edge_survives is True:
            confirmations.append("Edge survives slippage stress.")
        elif cost.slippage_stress_edge_survives is False:
            refutations.append("Edge destroyed by slippage stress.")

        # Edge survives combined stress
        if cost.combined_stress_edge_survives is True:
            confirmations.append("Edge survives combined cost stress.")
        elif cost.combined_stress_edge_survives is False:
            refutations.append("Edge destroyed by combined cost stress.")

        # Cost edge destroyed at baseline
        if cost.cost_edge_destroyed:
            refutations.append("Edge destroyed at baseline costs.")

        if refutations:
            return {"refuted": True, "supported": False, "reasons": refutations}
        elif confirmations:
            return {"refuted": False, "supported": True, "reasons": confirmations}
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["Cost stress evidence present but inconclusive."],
        }

    def _check_regime_breakdown(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check regime breakdown evidence.

        Returns dict with refuted/supported/reasons keys.
        """
        rb = evidence.regime_breakdown

        # If no regime data, not refuted — just inconclusive
        if rb.regime_count == 0:
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["Regime breakdown not yet evaluated."],
            }

        refutations: List[str] = []
        confirmations: List[str] = []

        # Edge only in rare regime
        if rb.edge_only_in_rare_regime:
            refutations.append(
                "Edge only present in rare regime — not tradeable at scale."
            )
        if rb.rare_regime_untradeable:
            refutations.append("Rare regime is untradeable.")

        # Edge absent from all regimes
        if rb.edge_in_no_regime():
            refutations.append("Edge absent from all evaluated regimes.")

        # Edge in multiple regimes
        if rb.regimes_with_edge >= 2:
            confirmations.append(
                f"Edge present in {rb.regimes_with_edge}/{rb.regime_count} regimes."
            )

        if rb.edge_in_all_regimes():
            confirmations.append("Edge present in all 4 canonical regimes.")

        if refutations:
            return {"refuted": True, "supported": False, "reasons": refutations}
        elif confirmations:
            return {"refuted": False, "supported": True, "reasons": confirmations}
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["Regime evidence present but inconclusive."],
        }

    def _check_no_trade(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check NO_TRADE comparison evidence.

        Returns dict with refuted/supported/reasons keys.
        """
        nt = evidence.no_trade

        if not nt.is_evaluated():
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["NO_TRADE comparison not yet evaluated."],
            }

        if nt.active_beats_no_trade is True:
            return {
                "refuted": False,
                "supported": True,
                "reasons": ["Active trading beats NO_TRADE baseline."],
            }
        elif nt.active_beats_no_trade is False:
            return {
                "refuted": True,
                "supported": False,
                "reasons": ["NO_TRADE beats active trading — alpha is worse than doing nothing."],
            }
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["NO_TRADE comparison present but inconclusive."],
        }

    def _check_symbol_stability(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check symbol stability evidence.

        Returns dict with refuted/supported/reasons keys.
        """
        ss = evidence.symbol_stability

        if not ss.is_evaluated():
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["Symbol stability not yet evaluated."],
            }

        refutations: List[str] = []
        confirmations: List[str] = []

        # Single symbol limitation
        if ss.single_symbol_limitation:
            refutations.append(
                "Single-symbol limitation: edge not demonstrated across multiple symbols."
            )

        # Symbol count
        if ss.symbol_count >= 2:
            confirmations.append(
                f"Multi-symbol coverage: {ss.symbol_count} symbols tested."
            )
        elif ss.symbol_count == 1:
            refutations.append(
                "Only 1 symbol tested — edge may be symbol-specific."
            )

        # Concentration limits
        if ss.violates_concentration_limit():
            refutations.append(
                f"Symbol concentration {ss.max_single_symbol_concentration} "
                f"exceeds {ss.MAX_SINGLE_SYMBOL_CONCENTRATION} limit."
            )
        else:
            confirmations.append("Symbol concentration within limits.")

        if ss.violates_cluster_limit():
            refutations.append(
                f"Cluster concentration {ss.max_cluster_concentration} "
                f"exceeds {ss.MAX_CLUSTER_CONCENTRATION} limit."
            )

        if refutations:
            return {"refuted": True, "supported": False, "reasons": refutations}
        elif confirmations:
            return {"refuted": False, "supported": True, "reasons": confirmations}
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["Symbol stability present but inconclusive."],
        }

    def _check_overfit(self, evidence: ValidationEvidence) -> Dict[str, Any]:
        """Check overfit risk assessment.

        Returns dict with refuted/supported/reasons keys.
        """
        of = evidence.overfit

        if not of.is_evaluated():
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["Overfit risk not yet assessed."],
            }

        # Critical overfit is a refutation
        if of.is_critical():
            return {
                "refuted": True,
                "supported": False,
                "reasons": ["CRITICAL overfit risk — model unreliable."],
            }

        # Purge violation
        if of.purge_violation_detected:
            return {
                "refuted": True,
                "supported": False,
                "reasons": ["Purge violation detected — train-test leakage."],
            }

        # HIGH risk is a concern but not an automatic refutation
        if of.overall_risk == "HIGH":
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["HIGH overfit risk — edge may not generalize."],
            }

        # LOW or MEDIUM risk
        return {
            "refuted": False,
            "supported": True,
            "reasons": [f"Overfit risk {of.overall_risk} — acceptable."],
        }

    def _cross_reference(
        self,
        thesis: AlphaThesis,
        evidence: ValidationEvidence,
    ) -> Dict[str, Any]:
        """Cross-reference expected evidence against actual evidence.

        Compares thesis.expected_evidence keys against actual observed values.

        Returns dict with refuted/supported/reasons keys.
        """
        if not thesis.expected_evidence:
            return {
                "refuted": False,
                "supported": True,
                "reasons": ["No expected evidence criteria defined for thesis."],
            }

        if not evidence.is_any_evaluated:
            return {
                "refuted": False,
                "supported": False,
                "reasons": ["No actual evidence available for cross-reference."],
            }

        refutations: List[str] = []
        confirmations: List[str] = []
        unchecked: List[str] = []

        expected = thesis.expected_evidence

        # Check expected OOS expectancy
        if "min_oos_expectancy" in expected:
            min_exp = expected["min_oos_expectancy"]
            if evidence.wfv.is_evaluated() and evidence.wfv.oos_expectancy is not None:
                actual = evidence.wfv.oos_expectancy
                if actual >= min_exp:
                    confirmations.append(
                        f"OOS expectancy {actual} >= expected {min_exp}."
                    )
                else:
                    refutations.append(
                        f"OOS expectancy {actual} < expected {min_exp}."
                    )
            else:
                unchecked.append("min_oos_expectancy (WFV not evaluated)")

        # Check expected win rate
        if "min_win_rate" in expected:
            min_wr = expected["min_win_rate"]
            if evidence.wfv.is_evaluated() and evidence.wfv.oos_win_rate is not None:
                actual = evidence.wfv.oos_win_rate
                if actual >= min_wr:
                    confirmations.append(f"Win rate {actual} >= expected {min_wr}.")
                else:
                    refutations.append(f"Win rate {actual} < expected {min_wr}.")
            else:
                unchecked.append("min_win_rate (WFV not evaluated)")

        # Check expected fold count
        if "min_folds" in expected:
            min_f = expected["min_folds"]
            actual = evidence.wfv.fold_count
            if actual >= min_f:
                confirmations.append(f"Fold count {actual} >= expected {min_f}.")
            else:
                refutations.append(f"Fold count {actual} < expected {min_f}.")

        # Check expected number of regimes with edge
        if "min_regimes_with_edge" in expected:
            min_reg = expected["min_regimes_with_edge"]
            actual = evidence.regime_breakdown.regimes_with_edge
            if actual >= min_reg:
                confirmations.append(
                    f"Regime coverage {actual} >= expected {min_reg}."
                )
            else:
                refutations.append(
                    f"Regime coverage {actual} < expected {min_reg}."
                )

        # Check expected symbol count
        if "min_symbols" in expected:
            min_sym = expected["min_symbols"]
            actual = evidence.symbol_stability.symbol_count
            if actual >= min_sym:
                confirmations.append(
                    f"Symbol count {actual} >= expected {min_sym}."
                )
            else:
                refutations.append(
                    f"Symbol count {actual} < expected {min_sym}."
                )

        # If nothing was checked, inconclusive
        if not refutations and not confirmations and unchecked:
            return {
                "refuted": False,
                "supported": False,
                "reasons": [f"Expected evidence not checkable: {', '.join(unchecked)}."],
            }

        if refutations:
            return {"refuted": True, "supported": False, "reasons": refutations}
        elif confirmations:
            all_reasons = confirmations + [
                f"Unchecked: {', '.join(unchecked)}" for _ in [0] if unchecked
            ]
            return {"refuted": False, "supported": True, "reasons": all_reasons}
        return {
            "refuted": False,
            "supported": False,
            "reasons": ["Cross-reference inconclusive."],
        }
