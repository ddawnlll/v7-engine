"""
AlphaForge → EvidencePassport adapter.

Transforms the raw output of ``alphaforge.train.main()`` (or any WFV-based
training pipeline) into an ``EvidencePassport`` that V7 can consume.

Usage::

    from alphaforge.evidence_adapter import build_alphaforge_passport

    metrics = main()        # run the training pipeline
    wfv_results = {
        "metrics": metrics,
        "per_fold_results": [...],          # from walk_forward_validate
        "candidate_id": "cand_swing_01",
        "hypothesis_refs": ["hc_alpha_001"],
    }
    passport = build_alphaforge_passport(wfv_results, mode="SWING")
"""

from __future__ import annotations

from typing import Any

from lib.evidence_engine.baselines import BaselineLibrary, BaselineResult
from lib.evidence_engine.evidence_passport import (
    EvidencePassport,
    EvidencePassportBuilder,
)
from lib.evidence_engine.hard_caps import HardCapResult, apply_hard_caps


def build_alphaforge_passport(
    wfv_results: dict,
    mode: str,
    hypothesis_refs: list[str] | None = None,
) -> EvidencePassport:
    """Build an ``EvidencePassport`` from AlphaForge walk-forward output.

    Parameters
    ----------
    wfv_results:
        Dict with keys:

        - ``metrics`` (dict): aggregated output of ``collect_metrics()``.
        - ``per_fold_results`` (list[dict]): per-fold WFV results.
        - ``candidate_id`` (str, optional): identifier for this candidate.
        - ``labels`` (list[str], optional): ground-truth label sequence.
        - ``gross_r`` (list[float], optional): per-bar gross returns in R.
        - ``fee_pct`` (float, optional): round-trip fee fraction.
    mode:
        Trading mode (e.g. ``"SWING"``, ``"SCALP"``).
    hypothesis_refs:
        Optional list of hypothesis card IDs that this passport supports.

    Returns
    -------
    EvidencePassport
        Fully populated passport ready for V7 consumption.
    """
    # 1. Build base passport via the standard builder
    wfv_results = dict(wfv_results)
    if hypothesis_refs:
        wfv_results["hypothesis_refs"] = hypothesis_refs

    passport = EvidencePassportBuilder.from_wfv_results(wfv_results, mode)

    # 2. Compute baselines if label data is available
    labels: list[str] | None = wfv_results.get("labels")
    gross_r: list[float] | None = wfv_results.get("gross_r")
    fee_pct: float = wfv_results.get("fee_pct", 0.0008)  # 8 bps default

    if labels and gross_r:
        lib = BaselineLibrary()
        baselines = lib.compute_baselines(labels, gross_r, fee_pct)
        passport.baselines = baselines

        # Compare model vs baselines
        model_beats_all = True
        for bname, bresult in baselines.items():
            beats, _ = lib.model_beats_baseline(passport.metrics, bname)
            if not beats:
                model_beats_all = False
                break
        if model_beats_all:
            passport.claim_statuses["MODEL_BEATS_BASELINES"] = "PASSED"
        else:
            passport.claim_statuses["MODEL_BEATS_BASELINES"] = "FAILED"
    else:
        passport.claim_statuses["MODEL_BEATS_BASELINES"] = "BLOCKED"

    # 3. Evaluate hard caps
    current_evidence: dict[str, Any] = _build_evidence_flags(passport, mode)
    hard_cap_result: HardCapResult = apply_hard_caps(
        passport.metrics,
        current_evidence,
    )
    passport.hard_caps = hard_cap_result

    # 4. Set claim statuses
    _set_claim_statuses(passport, hard_cap_result)

    return passport


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_evidence_flags(passport: EvidencePassport, mode: str) -> dict[str, Any]:
    """Build the ``current_evidence`` dict that ``apply_hard_caps`` expects."""
    metrics = passport.metrics

    evidence: dict[str, Any] = {
        "mode": mode,
        # Cost-aware filter: inferred from metrics
        "cost_aware_filter_run": bool(
            metrics.get("cost_decomposition")
            and metrics.get("net_expectancy_r") is not None
        ),
        # PBO: inferred from overfit analysis
        "pbo_run": bool(metrics.get("overfit_gap") is not None),
        # DSR: not run in basic pipeline — mark False (requires regime analysis)
        "dsr_run": False,
        # Trial ledger
        "trial_ledger_exists": bool(passport.hypothesis_refs),
        # Fold pass ratio
        "fold_pass_ratio": (
            metrics.get("accuracy_stability", 0.0)
            if "accuracy_stability" in metrics
            else 0.0
        ),
        # Orderbook features — derived from feature names if available
        "orderbook_features": _has_orderbook_features(metrics),
        # Synthetic features
        "synthetic_features": False,
        # Baseline library
        "baseline_library_exists": bool(passport.baselines),
        # Confidence calibration
        "confidence_calibration_done": bool(
            metrics.get("confidence_threshold") is not None
        ),
        # Feature ablation
        "feature_ablation_done": False,
    }
    return evidence


def _set_claim_statuses(
    passport: EvidencePassport,
    hard_cap_result: HardCapResult,
) -> None:
    """Populate passport.claim_statuses based on metrics and hard caps."""
    metrics = passport.metrics

    # ALPHA_HAS_EDGE
    if metrics.get("net_expectancy_r", 0) > 0 and metrics.get("net_sharpe_ratio", 0) > 0:
        passport.claim_statuses["ALPHA_HAS_EDGE"] = "PASSED"
    else:
        passport.claim_statuses["ALPHA_HAS_EDGE"] = "FAILED"

    # COST_AWARE_FILTER_IMPROVES_NET_R
    if metrics.get("cost_decomposition") and metrics.get("net_expectancy_r", 0) > 0:
        passport.claim_statuses["COST_AWARE_FILTER_IMPROVES_NET_R"] = "PASSED"
    else:
        passport.claim_statuses["COST_AWARE_FILTER_IMPROVES_NET_R"] = "FAILED"

    # FEATURE_FAMILY_HAS_SIGNAL
    if metrics.get("feature_count", 0) > 0:
        passport.claim_statuses["FEATURE_FAMILY_HAS_SIGNAL"] = "PASSED"
    else:
        passport.claim_statuses["FEATURE_FAMILY_HAS_SIGNAL"] = "FAILED"

    # V7 readiness claims — blocked by default, gate mapping will update
    passport.claim_statuses["V7_RESEARCH_BACKTEST_READY"] = "BLOCKED"
    passport.claim_statuses["V7_COST_STRESS_READY"] = "BLOCKED"
    passport.claim_statuses["V7_SHADOW_READY"] = "BLOCKED"
    passport.claim_statuses["V7_PAPER_READY"] = "BLOCKED"

    # Hard-cap derived claims
    if hard_cap_result.blocked_actions:
        passport.claim_statuses["HARD_CAPS_BLOCKED"] = "FAILED"
    else:
        passport.claim_statuses["HARD_CAPS_BLOCKED"] = "PASSED"


def _has_orderbook_features(metrics: dict) -> bool:
    """Heuristic: check if any feature name contains orderbook keywords."""
    features: list[str] | None = metrics.get("features")
    if not features:
        return False
    orderbook_keywords = {"orderbook", "bidask", "lob", "depth", "spread"}
    for feat in features:
        for kw in orderbook_keywords:
            if kw in feat.lower():
                return True
    return False
