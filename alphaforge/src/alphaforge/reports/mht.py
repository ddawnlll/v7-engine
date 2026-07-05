"""Multiple Hypothesis Testing (MHT) correction for AlphaForge reports.

Provides statistical corrections for multiple hypothesis testing and
data-snooping risk assessment. Used by the empirical report builder.

Critical distinction:
    trial_count is hypotheses tested, NOT oos_trade_count.
    trial_count = grid_search_combinations x thesis_count x feature_set_count

Classes:
    TrialLedger: Records all trial configurations tested during research.
        Auto-computes tested_hypothesis_count and trial_count_disclosure.

Functions:
    compute_trial_count: Count total trials from grid search, thesis, and feature dimensions.
    bonferroni_correction: Classic Bonferroni correction (alpha / n_trials).
    benjamini_hochberg: FDR control via Benjamini-Hochberg procedure.
    deflated_sharpe: Approximate deflated Sharpe ratio for multiple testing.
    compute_data_snooping_risk: Risk level based on trial count and MHT status.
    build_mht_section_from_ledger: Build a complete MHT control section from a TrialLedger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# TrialLedger — tracks what was tested
# ---------------------------------------------------------------------------


@dataclass
class TrialLedger:
    """Records all trial configurations tested during research.

    Tracks the full combinatoric space of symbols, parameter combinations,
    theses, and feature sets that were evaluated. Auto-computes
    tested_hypothesis_count and trial_count_disclosure from its dimensions.

    Each dimension is floored at 1 to avoid artificially zeroing out the
    product. This mirrors the safety semantics of compute_trial_count().

    Attributes:
        symbols: Market symbols tested (e.g. ["BTCUSDT", "ETHUSDT"]).
        param_combinations: Number of hyperparameter combinations tested
            (e.g. 49 for a 7x7 grid).
        thesis_ids: Alpha thesis IDs evaluated (e.g. ["ath-001"]).
        feature_set_ids: Feature set IDs tested (e.g. ["fs-001", "fs-002"]).
    """

    symbols: list[str] = field(default_factory=list)
    param_combinations: int = 1
    thesis_ids: list[str] = field(default_factory=list)
    feature_set_ids: list[str] = field(default_factory=list)

    @property
    def num_symbols(self) -> int:
        """Number of symbols, floored at 1."""
        return max(1, len(self.symbols))

    @property
    def num_theses(self) -> int:
        """Number of thesis IDs, floored at 1."""
        return max(1, len(self.thesis_ids))

    @property
    def num_feature_sets(self) -> int:
        """Number of feature set IDs, floored at 1."""
        return max(1, len(self.feature_set_ids))

    @property
    def tested_hypothesis_count(self) -> int:
        """Total distinct hypothesis tests = product of all dimensions.

        tested_hypothesis_count = num_symbols * param_combinations
                                  * num_theses * num_feature_sets
        """
        return max(
            1,
            self.num_symbols
            * max(1, self.param_combinations)
            * self.num_theses
            * self.num_feature_sets,
        )

    @property
    def trial_count_disclosure(self) -> int:
        """Synonym for tested_hypothesis_count.

        Provides the explicit trial_count_disclosure field required by the
        MHT schema. Always equals tested_hypothesis_count.
        """
        return self.tested_hypothesis_count


# ---------------------------------------------------------------------------
# Trial counting
# ---------------------------------------------------------------------------


def compute_trial_count(
    grid_search_combinations: int,
    thesis_count: int,
    feature_set_count: int,
) -> int:
    """Compute total trial count from all research dimensions.

    trial_count = product of grid_search_combinations x thesis_count x
    feature_set_count. Each dimension is floored at 1 to avoid artificially
    zeroing out the product. Minimum return is 1 to avoid division by zero
    in downstream correction formulas.

    Args:
        grid_search_combinations: Number of hyperparameter combinations
            tested (may be 0 if no grid search was performed).
        thesis_count: Number of alpha theses evaluated.
        feature_set_count: Number of feature sets tested.

    Returns:
        Total trial count, minimum 1.
    """
    g = max(1, grid_search_combinations)
    t = max(1, thesis_count)
    f = max(1, feature_set_count)
    return max(1, g * t * f)


# ---------------------------------------------------------------------------
# Bonferroni correction
# ---------------------------------------------------------------------------


def bonferroni_correction(alpha: float, n_trials: int) -> float:
    """Apply Bonferroni correction to significance threshold.

    adjusted_alpha = alpha / n_trials

    The Bonferroni correction is the most conservative MHT correction.
    It controls the family-wise error rate (FWER) by dividing the
    desired significance level by the number of independent tests.

    Args:
        alpha: Original significance threshold (e.g., 0.05).
        n_trials: Number of independent trials/hypotheses tested.

    Returns:
        Adjusted significance threshold. Returns original alpha when
        n_trials <= 0.
    """
    if n_trials <= 0:
        return alpha
    return alpha / n_trials


# ---------------------------------------------------------------------------
# Benjamini-Hochberg procedure (FDR control)
# ---------------------------------------------------------------------------


def benjamini_hochberg(
    p_values: Sequence[float],
    alpha: float,
) -> list[bool]:
    """Apply Benjamini-Hochberg procedure for false discovery rate control.

    Sorts p-values ascending, finds the largest rank i where
    p_i <= (i / m) * alpha. Rejects (declares significant) all
    hypotheses with p-value at or below that threshold.

    The Benjamini-Hochberg procedure controls the FDR (expected
    proportion of false discoveries among rejected hypotheses)
    at level alpha, under assumptions of independence or positive
    regression dependency.

    Args:
        p_values: Sequence of p-values from multiple hypothesis tests.
        alpha: Desired false discovery rate (e.g., 0.05).

    Returns:
        List of booleans same length as p_values, True where the
        hypothesis is rejected (deemed significant after correction).
    """
    m = len(p_values)
    if m == 0:
        return []

    # Annotate each p-value with its original index
    indexed: list[tuple[int, float]] = list(enumerate(p_values))
    # Sort by p-value ascending
    indexed.sort(key=lambda x: x[1])

    # Find the largest rank i where p_i <= (i / m) * alpha
    max_reject_rank = -1
    for rank, (_, p) in enumerate(indexed, start=1):
        threshold = (rank / m) * alpha
        if p <= threshold:
            max_reject_rank = rank

    # Build result array at original indices
    rejected = [False] * m
    if max_reject_rank >= 0:
        for i in range(max_reject_rank):
            original_idx = indexed[i][0]
            rejected[original_idx] = True

    return rejected


# ---------------------------------------------------------------------------
# Deflated Sharpe ratio
# ---------------------------------------------------------------------------


def deflated_sharpe(
    sharpe: float,
    n_trials: int,
    n_samples: int,
    gamma: float = 0.5,
) -> float:
    """Compute approximate deflated Sharpe ratio.

    Adjusts the observed Sharpe ratio downward to account for the
    inflation caused by multiple testing (data snooping / selection
    bias). When many strategies are tested, the maximum observed
    Sharpe overstates the true Sharpe of the best strategy.

    Uses a simple conservative approximation:
        deflated = sharpe / sqrt(1 + n_trials / n_samples)

    This always deflates when n_trials > 0 and converges to the
    original Sharpe as n_trials -> 0. The approximation treats each
    additional trial as increasing the effective noise floor, which
    reduces the effective signal-to-noise ratio.

    NOTE ON METHODOLOGY:
        method: APPROXIMATION
        assumption: Conservative adjustment proportional to trial burden
        promotion_eligible: false unless reviewed by a domain expert

    Args:
        sharpe: Observed Sharpe ratio before any correction.
        n_trials: Number of independent trials tested.
        n_samples: Number of independent return observations (e.g., OOS
            trade count or OOS bars).
        gamma: Ignored (kept for signature compatibility).

    Returns:
        Deflated Sharpe ratio. Returns the original Sharpe when
        n_trials <= 0 or n_samples <= 0 (no adjustment possible).
    """
    if n_trials <= 0 or n_samples <= 0:
        return sharpe

    return sharpe / math.sqrt(1.0 + n_trials / n_samples)


# ---------------------------------------------------------------------------
# Data-snooping risk assessment
# ---------------------------------------------------------------------------


def compute_data_snooping_risk(
    n_trials: int,
    mht_applied: bool,
    fold_count: int,
) -> str:
    """Compute data-snooping risk level.

    Assesses the risk that reported performance is inflated by
    data snooping (multiple testing on the same dataset). Based
    on trial count, whether MHT correction was applied, and the
    number of walk-forward validation folds.

    Args:
        n_trials: Total number of trials/hypotheses tested.
        mht_applied: Whether a valid MHT correction was applied.
        fold_count: Number of walk-forward validation folds.

    Returns:
        Risk level: 'CRITICAL', 'HIGH', 'MEDIUM', or 'LOW'.
    """
    if n_trials > 1000 and not mht_applied:
        return "CRITICAL"
    if n_trials > 100 and not mht_applied:
        return "HIGH"
    if n_trials > 10 or fold_count < 6:
        return "MEDIUM"
    if mht_applied and fold_count >= 6:
        return "LOW"
    # Default: few trials and adequate folds — low risk
    return "LOW"


# ---------------------------------------------------------------------------
# MHT section builder from TrialLedger
# ---------------------------------------------------------------------------


def build_mht_section_from_ledger(
    ledger: TrialLedger,
    correction_method: str = "NONE_APPLIED",
    fold_count: int = 6,
    oos_sharpe: float | None = None,
    oos_trade_count: int | None = None,
    alpha: float = 0.05,
    gamma: float = 0.5,
    rejected_candidate_count: int = 0,
) -> dict:
    """Build a complete MHT control section dict from a TrialLedger.

    This is the single entry point for producing a schema-valid
    ``multiple_hypothesis_control`` section. It auto-computes:

    - ``tested_hypothesis_count`` from the ledger dimensions
    - ``trial_count_disclosure`` from the ledger
    - ``corrected_significance`` via Bonferroni when a real correction
      method is selected
    - ``data_snooping_risk_flag`` from trial count, fold count, and
      correction status
    - ``deflated_sharpe_or_equivalent`` when OOS data is provided and
      a correction method is active
    - ``pbo_or_backtest_overfit_risk`` from the deflated Sharpe value

    Args:
        ledger: TrialLedger recording what was tested.
        correction_method: MHT correction method. Pass a real method
            (``"Bonferroni"``, ``"FDR"``, ``"Deflated_Sharpe"``,
            ``"PBO"``) to enable corrections. Default ``"NONE_APPLIED"``.
        fold_count: Number of walk-forward validation folds.
        oos_sharpe: Observed OOS Sharpe ratio (for deflated Sharpe).
        oos_trade_count: Number of OOS trades (n_samples for deflated
            Sharpe). Ignored when None or <= 0.
        alpha: Desired significance level (default 0.05).
        gamma: Correlation factor between trials for deflated Sharpe
            (default 0.5).
        rejected_candidate_count: Number of candidates rejected during
            research (default 0).

    Returns:
        Dict with all keys required by the ``multiple_hypothesis_control``
        schema property.
    """
    trial_count = ledger.tested_hypothesis_count
    has_real_method = correction_method not in ("NONE_APPLIED", "NONE")

    # Corrected significance
    corrected_alpha: float | None = None
    if has_real_method and correction_method == "Bonferroni":
        corrected_alpha = bonferroni_correction(alpha, trial_count)

    # Data-snooping risk
    risk_flag = compute_data_snooping_risk(
        n_trials=trial_count,
        mht_applied=has_real_method,
        fold_count=fold_count,
    )

    # Deflated Sharpe
    deflated_value: float | None = None
    pbo_risk: str = "NOT_RUN"
    if (
        has_real_method
        and oos_sharpe is not None
        and oos_trade_count is not None
        and oos_trade_count > 0
    ):
        deflated_value = deflated_sharpe(
            sharpe=oos_sharpe,
            n_trials=trial_count,
            n_samples=oos_trade_count,
            gamma=gamma,
        )
        deflated_value = round(deflated_value, 6)

        # Derive PBO / overfit risk from deflated Sharpe
        if deflated_value <= 0.0:
            pbo_risk = "CRITICAL" if trial_count > 100 else "HIGH"
        elif deflated_value < 0.3:
            pbo_risk = "MEDIUM"
        else:
            pbo_risk = "LOW"

    # Notes
    notes_parts: list[str] = []
    if not has_real_method and trial_count > 1:
        notes_parts.append(
            f"MHT correction not applied -- {trial_count} hypotheses tested "
            f"across {fold_count} folds without multiple comparison correction. "
            f"BLOCKING HOLD: correction_method={correction_method}, "
            f"trial_count={trial_count}. "
            f"Candidate promotion requires proper MHT correction "
            f"(Bonferroni, FDR, Deflated Sharpe, or PBO)."
        )
    notes_parts.append(
        f"Trial ledger: {ledger.num_symbols} symbols, "
        f"{ledger.param_combinations} param combinations, "
        f"{ledger.num_theses} theses, "
        f"{ledger.num_feature_sets} feature sets. "
        f"Total hypotheses tested: {trial_count}. "
        f"Correction: {correction_method}. "
        f"Data-snooping risk: {risk_flag}."
    )
    notes = " ".join(notes_parts)

    return {
        "tested_hypothesis_count": trial_count,
        "correction_method": correction_method,
        "corrected_significance": corrected_alpha,
        "data_snooping_risk_flag": risk_flag,
        "deflated_sharpe_or_equivalent": deflated_value,
        "pbo_or_backtest_overfit_risk": pbo_risk,
        "trial_count_disclosure": ledger.trial_count_disclosure,
        "rejected_candidate_count": rejected_candidate_count,
        "notes": notes,
    }
