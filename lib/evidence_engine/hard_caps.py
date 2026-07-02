from __future__ import annotations

from dataclasses import dataclass, field

# ------------------------------------------------------------------
# Literature-derived hard caps (V1-V10).
#
# These rules implement the research dossier's guardrails and are
# *not* tunable hyper-parameters — they encode domain constraints.
#
# Each rule returns either a score cap (0-100), an anomaly flag, or
# a blocked action string.
# ------------------------------------------------------------------

# Maximum allowed level for an alpha candidate when hard caps are
# fully satisfied.
_FULL_SCORE = 100

# Modes that trigger an orderbook penalty under V6.
_ORDERBOOK_PENALTY_MODES = frozenset({"SWING"})

# Claims that require real (non-synthetic) data to be asserted.
# These are checked by RealDataGate during alpha promotion.
REAL_DATA_REQUIRED_CLAIMS: frozenset[str] = frozenset({
    "ALPHA_HAS_EDGE",
    "MODEL_BEATS_BASELINES",
    "FEATURE_FAMILY_HAS_SIGNAL",
    "V7_RESEARCH_BACKTEST_READY",
    "V7_WALK_FORWARD_READY",
    "V7_PROMOTION_CANDIDATE",
})


@dataclass
class RealDataGateResult:
    """Result of a RealDataGate evaluation.

    Attributes:
        passed: Whether the gate passed.
        max_alpha_score: Maximum alpha score (15 = synthetic, 100 = real).
        alpha_candidate: Whether the alpha can proceed to promotion.
        reason: Human-readable explanation.
        blocked_actions: Actions blocked by this result.
    """
    passed: bool
    max_alpha_score: int = 0
    alpha_candidate: bool = False
    reason: str = ""
    blocked_actions: list[str] = field(default_factory=list)


class RealDataGate:
    """Gate that checks whether a claim is backed by real (non-synthetic) data.

    Required claims (REAL_DATA_REQUIRED_CLAIMS) MUST have a real-data passport.
    Non-required claims always pass.
    """

    def evaluate(
        self,
        claim: str,
        passport: object | None,
    ) -> RealDataGateResult:
        """Evaluate a claim against the real-data requirement.

        Args:
            claim: The claim string (e.g. "ALPHA_HAS_EDGE").
            passport: A DataPassport-like object or None.

        Returns:
            RealDataGateResult with pass/fail decision.
        """
        # Non-required claims always pass
        if claim not in REAL_DATA_REQUIRED_CLAIMS:
            return RealDataGateResult(
                passed=True,
                max_alpha_score=100,
                alpha_candidate=True,
                reason="Claim does not require real data",
            )

        # Required claims need a valid real-data passport
        if passport is None:
            return RealDataGateResult(
                passed=False,
                max_alpha_score=15,
                alpha_candidate=False,
                reason="Required claim requires real data, but no DataPassport was provided",
            )

        if not getattr(passport, "is_real_data", False):
            return RealDataGateResult(
                passed=False,
                max_alpha_score=15,
                alpha_candidate=False,
                reason=f"Claim '{claim}' requires real data, but passport does not provide real data",
            )

        is_trustworthy = getattr(passport, "is_trustworthy_for_context", lambda: True)()
        if not is_trustworthy:
            return RealDataGateResult(
                passed=False,
                max_alpha_score=50,
                alpha_candidate=True,
                reason=f"Claim '{claim}' uses real data but passport fails context check",
            )

        return RealDataGateResult(
            passed=True,
            max_alpha_score=100,
            alpha_candidate=True,
            reason=f"Claim '{claim}' satisfied by real data passport",
        )


@dataclass
class HardCapResult:
    """Output of the hard-cap engine for a single evaluation point."""

    # Score caps (None = no cap applied)
    economic_score_cap: float | None = None
    behavior_score_cap: float | None = None
    validation_score_cap: float | None = None
    data_quality_cap: float | None = None
    proximity_cap: float | None = None

    # Anomaly flags
    anomaly_flags: list[str] = field(default_factory=list)

    # Blocked / allowed actions
    blocked_actions: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)


def apply_hard_caps(metrics: dict, current_evidence: dict) -> HardCapResult:
    """Evaluate all V1-V10 hard caps against the current metrics/evidence.

    Parameters
    ----------
    metrics:
        Dictionary of numeric performance metrics (e.g. ``net_sharpe``,
        ``net_profit_factor``, ``fold_pass_ratio``, ``economic_score``, …).
    current_evidence:
        Dictionary of boolean/flag evidence keys (e.g.
        ``cost_aware_filter_run``, ``pbo_run``, ``dsr_run``,
        ``trial_ledger_exists``, ``baseline_library_exists``,
        ``confidence_calibration_done``, ``feature_ablation_done``,
        ``synthetic_features``, ``orderbook_features``, ``mode``).

    Returns
    -------
    HardCapResult
        Populated caps, flags, and action lists.
    """
    result = HardCapResult()

    # -- V1: Cost-aware filter ----------------------------------------
    if not current_evidence.get("cost_aware_filter_run", False):
        result.economic_score_cap = min(
            result.economic_score_cap or _FULL_SCORE,
            20,
        )
        result.blocked_actions.append("V1: cost-aware filter not run")

    # -- V2: PBO (Prediction Bias Optimisation) -----------------------
    pbo_run = current_evidence.get("pbo_run", False)
    if not pbo_run:
        result.validation_score_cap = min(
            result.validation_score_cap or _FULL_SCORE,
            35,
        )
        result.blocked_actions.append("V2: PBO not run — no alpha candidate")

    # -- V3: DSR (Distribution Shift Robustness) ----------------------
    dsr_run = current_evidence.get("dsr_run", False)
    if not dsr_run:
        if not current_evidence.get("pbo_run", False):
            # If PBO also not run, the net_sharpe is doubly unreliable;
            # we still flag here rather than duplicate the block.
            pass
        result.anomaly_flags.append(
            "V3: DSR not run — net_sharpe flagged unreliable"
        )

    # -- V4: Trial ledger ---------------------------------------------
    if not current_evidence.get("trial_ledger_exists", False):
        result.blocked_actions.append("V4: no trial ledger — all claims blocked")

    # -- V5: Fold pass ratio ------------------------------------------
    fold_pass_ratio = metrics.get("fold_pass_ratio", 0.0)
    if fold_pass_ratio == 0.0:
        result.proximity_cap = min(
            result.proximity_cap or _FULL_SCORE,
            35,
        )
        result.blocked_actions.append(
            "V5: fold_pass_ratio = 0 — proximity cap 35"
        )

    # -- V6: SWING + orderbook features --------------------------------
    mode = current_evidence.get("mode", "")
    orderbook_features = current_evidence.get("orderbook_features", False)
    if mode in _ORDERBOOK_PENALTY_MODES and orderbook_features:
        result.anomaly_flags.append(
            "V6: SWING mode with orderbook features — behavior penalty applicable"
        )
        result.behavior_score_cap = min(
            result.behavior_score_cap or _FULL_SCORE,
            50,  # substantial cap
        )

    # -- V7: Synthetic features + high PF/Sharpe -----------------------
    synthetic = current_evidence.get("synthetic_features", False)
    pf = metrics.get("net_profit_factor", 0.0)
    sharpe = metrics.get("net_sharpe", 0.0)
    if synthetic and pf > 3.0 and sharpe > 2.0:
        result.anomaly_flags.append(
            "V7: synthetic features with high PF/Sharpe — possible overfitting"
        )
        # No numeric cap per the rule, but block any promotion action.
        result.blocked_actions.append(
            "V7: synthetic + high PF/Sharpe — overfitting anomaly"
        )

    # -- V8: Baseline library -----------------------------------------
    if not current_evidence.get("baseline_library_exists", False):
        result.allowed_actions.append("RESEARCH_CANDIDATE")
        result.blocked_actions.append(
            "V8: no baseline library — max level RESEARCH_CANDIDATE"
        )

    # -- V9: Confidence calibration -----------------------------------
    if not current_evidence.get("confidence_calibration_done", False):
        result.behavior_score_cap = min(
            result.behavior_score_cap or _FULL_SCORE,
            30,
        )
        result.blocked_actions.append(
            "V9: no confidence calibration — behavior cap 30"
        )

    # -- V10: Feature ablation ----------------------------------------
    if not current_evidence.get("feature_ablation_done", False):
        result.proximity_cap = min(
            result.proximity_cap or _FULL_SCORE,
            40,
        )
        result.blocked_actions.append(
            "V10: no feature ablation — proximity cap 40"
        )

    return result
