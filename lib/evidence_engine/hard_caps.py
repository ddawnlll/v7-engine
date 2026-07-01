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
